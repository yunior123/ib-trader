# MenthorQ → ib-trader: 14 buildable features, ranked best-first

**Ground truth I verified in the repo before writing (matters for every item):**
- `data/opt_chain_<sym>.txt` (fetcher `scripts/opt_chain_cache.py`, 180s cycle, 26 syms) = **2 nearest expiries only** (`exps[:2]`), **20 nearest strikes** (`MAX_STRIKES=20`) → for QQQ that is **±1.4%**, not the ±6% `PCT_BAND` advertises. No monthly. Wings truncated.
- Greeks/IV **are** populated during RTH (real per-strike skew: QQQ 20260724 → 0.3189/0.3243/0.3302) and are **all `-1.0` outside RTH**. So `gex_core.flip_recompute()` (which needs ≥3 distinct IVs) silently never fires after hours, and `from_ibkr_cache()` line ~298 then **overwrites `flip` with `flip_static` anyway**. The re-priced flip the dossier recommends is already written and effectively disabled.
- **The cube history already exists**: `data/history/YYYY-MM-DD/opt_chain_<sym>_HHMM.txt` — 5-min snapshots, 26 syms, 2105 files on 07-24, 1009 on 07-23, 208 on 07-22, **nothing before 07-22**. Plus `data/history/<date>/levels.json`.
- `trades.db`: `signals` (3233 rows, 2026-07-15→07-25), `backtest_signal_outcomes` (2916), `poly_bars`, `poly_opt_bars` (71679 rows, 6 syms, **columns otk,sym,exp,strike,right,ts,o,h,l,c,v — NO OI, NO IV, NO greeks**), `peer_weights(target,peer,corr,beta,lead_min,weight,n)`.
- **Hard missing inputs, no workaround:** intraday OI (updates once/day), signed option trade classification per strike (`data/whale_flow_hist.jsonl` is `{vc,vp,pc}` per symbol, not per-strike with side), any option-cube history before 2026-07-22.

Everything below respects: signal-only, no yfinance on signal paths, fail-loud, C++ for per-bar hot paths, measured Wilson probabilities.

---

## 1. Gamma Δ-Flow — walls being built, not walls that exist
**Skill slug:** `gamma-delta-flow`
**Inspired by:** #35 Intraday Gamma Change ("the closest thing MenthorQ has to a real-time flow alarm") + Recommendation 1 "build the cube, not the scalars".

**What it computes**
1. Every 5 min, read the two latest chain snapshots for `sym` and build the cube keyed `(strike, exp)`: `{oi_c, oi_p, vol_c, vol_p, iv, gamma, delta}`.
2. Intraday OI is unavailable, so build **provisional OI**: `oi_prov[k,e,r] = oi[k,e,r] + κ(sym,dte_bucket) · Δvol[k,e,r]`, where `Δvol` is the change in the cumulative day-volume column between snapshots. **κ is measured, never guessed**: regress next-morning `oi` change against previous day's total `vol` per strike over all of `data/history/*/opt_chain_*_1555.txt` vs next day's `_0935.txt`. One κ per (sym, dte∈{0,1-7,8+}), refit weekly, stored with n and R².
3. `GEX_prov[k] = Σ_e Γ_BS(S,k,T_e,iv[k,e]) · oi_prov · 100 · S² · 0.01 · sign(right)` using `gex_core.bs_gamma` (dealer-long-calls, house convention).
4. **The signal is the derivative, not the level**: `dGEX[k]/dt` over 5/15/30-min windows, z-scored against that strike-band's own 3-day distribution. Emit: `building` (|GEX| growing at a strike above spot → ceiling hardening), `dissolving` (wall evaporating → break becomes cheap), `migrating` (argmax|GEX| moving toward/away from spot at X$/hour).
5. `wall_eta_min = (dist_to_wall) / (spot_velocity)` vs `wall_halflife_min` from the dissolve rate → "the wall dies before price arrives" is the tradeable statement.

**Inputs:** `data/opt_chain_<sym>.txt` (live), `data/history/<date>/opt_chain_<sym>_HHMM.txt` (Δ and κ fit), `scripts/gex_core.py` (`bs_gamma`, `build_gex`), `data/nbbo_<sym>.txt` (live spot; never the stale header spot). **New table** `gex_cube(sym,ts,exp,strike,right,oi,oi_prov,vol,iv,gamma,delta,gex,dex)` in `trades.db` — persist it, because the 5-min text files are the only copy and they are 3 days old.

**Output** `data/gamma_flow.json`:
```json
{"asof":1784..., "MU":{"walls":[{"strike":95,"gex":8.4e6,"sign":"+","dgex_15m":+2.1e6,
 "z":2.7,"state":"building","halflife_min":null},{"strike":92,"gex":-5.1e6,"sign":"-",
 "dgex_15m":-3.3e6,"z":-2.2,"state":"dissolving","halflife_min":22}],
 "net_gex_dt_15m":-4.0e6,"kappa":0.31,"kappa_n":880,"kappa_r2":0.62,"stale":false}}
```
Surfaces: new `direction_view` factor `gamma_flow` (weight 1.0, provisional 0.6 until calibrated) with `why[]` line "muro 95 endureciendo (z 2.7)"; chart overlay = wall bars coloured by Δ; voice **SIGNAL** on `dissolving` at the wall price is in play, never DANGER until measured.

**Decision rule:** wall `building` above spot + price approaching → **fade at the print** (2 readings, rule PRINT-O-NADA), target = next GEX level down. Wall `dissolving` on the path → **do not fade**; the "1st touch bounces 70%" prior is suspended and the breakout is allowed. Must pass: captain hierarchy (rule 12 — MU's building wall is void if SMH's captain flow is opposite), `optgate.py` spread ≤5% / OI>500 before any option vehicle, `%B` 1m+15m not stretched against the trade.

**Validation:** label every `building`/`dissolving` event in the history cube; outcome = signed return of the underlying at +5/+15/+30 min, plus "did price cross the wall within 60 min". Null: same event count drawn at random timestamps for the same sym/hour. Keep only buckets where Wilson 95% LB of directional hit rate > 55% **and** exceeds the null by ≥8pp with n≥60, registered via `calibration_ledger.py` as `setup_type='gamma_flow_build'|'gamma_flow_dissolve' × regime`. Report κ's R²; if R²<0.3 for a sym, ship the raw Δvol z-score only and say so.

**Effort:** M. Python (`scripts/gamma_flow.py`, 5-min cadence is not a hot path) + persist to sqlite; consumers in C++ read the JSON like `data/force.json`. Extends `gex_core.py`, new file.

**Kill risk:** κ is unstable — a large fraction of option volume is same-day closing/spreads, so `Δvol` may be near-orthogonal to real OI change, making provisional OI noise. Mitigation is honest reporting of R², not a fudge factor.

---

## 2. Flip Velocity — regime change ETA
**Skill slug:** `flip-velocity`
**Inspired by:** #10 HVL as the tradeable event + #35 "detect gamma flips as they form".

**What it computes**
1. Per 5-min snapshot compute **both** flips honestly: `flip_static` (zero crossing of cumulative net GEX, `gex_core._flip`) and `flip_repriced` (`gex_core.flip_recompute`, Newton/grid over hypothetical spot). **Fix the override at `from_ibkr_cache` line ~298** so `flip_repriced` wins during RTH and degrades loudly (`flip_src:"static_no_iv"`) outside it.
2. Report **all roots**, not the nearest — a second flip below spot is the trapdoor.
3. Time series → `v_flip = dflip/dt` (robust: Theil–Sen slope over last 6 points), `v_spot = dS/dt` over the same window.
4. `eta_min = (S − flip) / (v_flip − v_spot)` when the gap is closing; `converge = |v_flip| > |v_spot|` ⇒ the regime change is **dealer-driven** (positioning coming to price) rather than price-driven — the higher-conviction case.
5. `flip_stability`: dispersion of flip over the last 60 min normalized by `em`. High dispersion ⇒ the map is unreliable, veto.

**Inputs:** `data/history/<date>/opt_chain_<sym>_HHMM.txt`, `scripts/gex_core.py`, live `data/opt_chain_<sym>.txt` + `data/nbbo_<sym>.txt`, `scripts/chart_levels.py gen()` for the current snapshot.

**Output** `data/flip_track.json`: `{"QQQ":{"flip":709.4,"flip_src":"repriced","roots":[709.4,701.2],"v_flip_pct_hr":-0.18,"v_spot_pct_hr":+0.35,"eta_min":26,"converge":false,"stability":0.42,"regime":"POS","d_flip_pct":-0.6}}`. Surfaces: `direction_view` upgrades the existing `flip` factor from a static distance to distance **+ ETA + converge flag**; voice **DANGER** only on `eta_min<15 & converge=true` (pre-emptive, per the "retraso=dinero" rule); chart draws the flip with a velocity arrow; PDF page 1 gets "flip trajectory".

**Decision rule:** `converge=true & eta<20min` → the coming regime is NEG → **stop fading extremes, switch to breakout mode** (buy the break of the box, not the mean reversion), and per `negative-gamma-whipsaw` do not take direction from %B in the air. `converge=false` (spot chasing a static flip) → treat the crossing as noise, require a printed retest. Second root within 1×`em` below spot → **hard veto on bought 0DTE calls** (trapdoor). Gates: captain rule 12, bollinger check, `optgate.py`.

**Validation:** on the 3+ days of cube history (grow to ≥30 sessions before publishing probabilities), label flip crossings and measure realized 15/30/60-min absolute move and Kaufman efficiency ratio (`momentum_calc`) after the crossing, split by `converge`. Null: crossings where `converge=false`. Keep if `converge=true` shows median |move| ≥1.3× the null with n≥40 and Wilson LB of "efficiency>0.4" > the null.

**Effort:** S–M. Python (`scripts/flip_track.py`), plus a 3-line fix in `gex_core.from_ibkr_cache`. Extends `chart_levels.py`/`direction_view.py`.

**Kill risk:** with only ±1.4% of strikes for high-priced names, the cumulative GEX curve is truncated and the flip is an artifact of the window — this feature is only as good as feature #13's widening of the fetcher.

---

## 3. Per-Level Hit Rates vs a Random-Levels Null
**Skill slug:** `level-calibration`
**Inspired by:** GAP 9 — "no vendor in this space ships an empirically calibrated per-level hit rate"; plus the Trustpilot multiple-comparisons critique.

**What it computes**
1. For each session in `data/history/*` reconstruct the level set at 09:35 from the chain snapshot: `call_wall, put_wall, abs_wall(+sign), flip(all roots), em_hi, em_lo, oi_call_wall, oi_put_wall, gex_1..gex_10` (top-10 by |net_gex| inside the EM envelope, deduped to ≥1 strike interval, **sign kept**).
2. Replay 1-min bars and label per level: `touched` (H≥L_px≥L within bar), `rejected` (touched then closed ≥0.25×ATR away within 15 min without a 2-bar straddle break), `broke_and_ran` (crossed and extended ≥0.5×`em`), `broke_and_failed` (crossed then reclaimed).
3. **The null**: for each session draw 16 pseudo-levels from the same strike grid with the same distance-from-spot distribution, and compute identical statistics. Everything is reported as `rate` **and** `edge = rate − null_rate`.
4. Bucket by `level_type × regime(POS/NEG) × tod_bucket(9:45-10:30 / 10:30-11:30 / 11:30-14:00 / 14:00-15:30 / 15:30-16:00) × book_quality(feat #7)`. Wilson 95% CI on every cell; dead cells switched off (exactly the `signal-conditioning-layer` pattern).

**Inputs:** `data/history/<date>/opt_chain_<sym>_HHMM.txt`, `data/history/<date>/levels.json`, `data/backtest/bars30d_<sym>.csv` + `data/hist/bars_<sym>_1m_30d.txt` + `poly_bars` for the intraday replay, `scripts/gex_core.py`, `scripts/calibration_ledger.py`. **Missing:** cube history before 07-22 — cheapest fill is a Polygon backfill job writing OI/IV/greeks into a new `poly_opt_snap` table (`poly_opt_bars` has no OI/IV columns, so it cannot be reused).

**Output** `data/level_stats.json`, one record per bucket: `{"level":"call_wall","regime":"POS","tod":"0945_1030","n":73,"reject":0.63,"reject_ci":[0.51,0.74],"null_reject":0.49,"edge_pp":14,"break_run":0.18,"keep":true}`. Surfaces: `direction_view` replaces its constant `walls 1.0` weight with the **measured** per-bucket edge; the arrow's `prob` becomes defensible; every PDF wall verdict carries `n` and CI ("muro 95: rechaza 63% [51-74], n=73, null 49%"); banner shows `null` when a cell is dead.

**Decision rule:** a level is tradeable only if its bucket has `keep:true`. `edge_pp < 5` ⇒ the level is **decoration**, no voice, no trade — which is the honest implementation of NO-TRADE = POSICIÓN. `gex_1..10` levels that don't beat the null get dropped from the chart entirely (fewer lines = fewer false confirmations).

**Validation:** it *is* the validation layer; its own guard is walk-forward — fit buckets on sessions 1..N, test on N+1.., using the `walk-forward-validation` skill; plus Deflated Sharpe / False Strategy Theorem from `stats-trading-risk` because we are testing ~16 levels × 5 tod × 2 regimes = ~160 hypotheses.

**Effort:** M–L. Python (`scripts/level_calibration.py`), offline batch, extends `calibration_ledger.py`.

**Kill risk:** n. With 3 sessions of cube history the CIs will be uselessly wide for months, and the honest output is "insufficient data" — which is correct but unsatisfying. Do not let it publish numbers before n≥60 per cell.

---

## 4. Wall Decay Ledger — the doctrine constant, measured
**Skill slug:** `wall-decay`
**Inspired by:** #8/#9 first-touch fade vs failed-retest continuation; our own `oi-magnets-protocol` says "1st touch bounces ~70%, 3+ exhausted" — **hardcoded, which violates the house rule.**

**What it computes**
1. Per session per sym, track each level from `level_stats`' set. Maintain `touch_idx` (1,2,3+) with hysteresis: a touch counts only after price has left by ≥0.5×ATR(14,1m) and returned.
2. Per touch record `(touch_idx, regime, dGEX at that strike since last touch [feature #1], time since last touch, %B 1m/15m at touch, captain state)`.
3. Outcome: `bounce` (≥0.4×`em` away within 30 min), `pierce` (crossed but reclaimed), `break` (crossed + failed retest per the published MenthorQ trigger = price cannot reclaim within 3 bars).
4. Fit `P(bounce | touch_idx, regime, dGEX_sign)` with Wilson CI. Also fit the **retest-rejection inversion**: after a confirmed break, `P(old wall now acts as opposite-side level)`.

**Inputs:** same as #3, plus `data/gamma_flow.json` (feature 1) so decay is explained by real gamma disappearing rather than by a counter.

**Output** `data/wall_decay.json`: `{"MU":{"95":{"touch_idx":2,"p_bounce":0.52,"ci":[0.38,0.66],"n":41,"dgex_since_touch":-1.9e6,"verdict":"debilitado"}}}`. Surfaces: replaces the doctrine constant everywhere it is currently spoken; voice SIGNAL text becomes "muro 95, 2º toque, rebota 52% [38-66]"; PDF scenario tree branches weighted by it.

**Decision rule:** touch 1 with `dGEX≥0` → fade allowed at the print. Touch ≥3 **or** `dGEX<0` with `p_bounce` CI overlapping 50% → **no fade**; wait for break + failed retest, then trade continuation with the wall as inverted stop. Gates: PRINT-O-NADA, bollinger (banda reventada en contra = no fade), captain rule 12, `optgate.py`.

**Validation:** the fit is the backtest; guard against selection bias by requiring the same decay monotonicity to appear out-of-sample on a held-out ticker set (fit on QQQ/SPY/NVDA/MU, test on SMH/AMD/TSM). Keep the feature only if `p_bounce(touch1) − p_bounce(touch3+) ≥ 10pp` with non-overlapping CIs.

**Effort:** S–M. Python, extends `scripts/level_calibration.py` output; consumed by C++ bots via JSON.

**Kill risk:** touch definition sensitivity — with a different hysteresis threshold the decay gradient can vanish. Publish the sensitivity curve over 3 thresholds; if the effect only exists at one, it isn't real.

---

## 5. 25Δ Risk-Reversal Lead — hedging demand before price
**Skill slug:** `skew-lead`
**Inspired by:** #27 Skew (`RR = IV(25Δ put) − IV(25Δ call)`) + #23 Option Q-Score's "skew and slope of IV".

**What it computes**
1. From each RTH snapshot, we have per-contract `delta` and `iv`. Interpolate IV at |Δ|=0.25 on each side (monotone interpolation in delta space, per expiry), for the front expiry and the next.
2. `RR = IV_25p − IV_25c`; `smile_slope = (IV_25p − IV_atm)/0.25`; `term = IV_front − IV_next`.
3. **The signal is ΔRR, not RR**: `dRR_15m` z-scored against the sym's own 3-day distribution. Rising RR = puts bid up = hedging demand arriving; falling RR = call chase.
4. Measure the **lead**: cross-correlate `dRR` against forward underlying returns at +5/+10/+15/+30 min on the history cube, per sym, and store `lead_min` and peak correlation — same machinery as `peer_influence.py` already does for peers.
5. Cross-check against the espada-ballena doctrine: rising RR into a whale-CALLS print is the confirmation that the whale call is a **top** (dealers buying downside), not continuation.

**Inputs:** `data/opt_chain_<sym>.txt` + `data/history/.../opt_chain_<sym>_HHMM.txt` (delta and iv columns, RTH only — fail loud outside), `data/whale_flow_hist.jsonl`, `scripts/gex_core.py` for `iv_atm`. **Missing:** wings — |Δ|=0.25 may fall outside the 20-strike window for low-vol/high-price names; then interpolation extrapolates. Emit `rr_src:"extrapolated"` and exclude those from calibration until #13 widens the window.

**Output** `data/skew.json`: `{"NVDA":{"rr":0.021,"rr_pctile_3d":0.88,"drr_15m":+0.006,"z":2.4,"smile_slope":0.08,"term":+0.03,"lead_min":10,"corr":-0.31,"n":540,"src":"interpolated"}}`. Surfaces: new `direction_view` factor `skew` (weight starts 0.7, calibrated); voice SIGNAL "skew NVDA: puts pagando, z 2.4 → techo local"; chart sub-pane; PDF page 1.

**Decision rule:** `z(dRR) > 2` with the sym above its call wall → **fade / take profits**, do not add long. `z(dRR) < −2` below the put wall → floor forming, the espada-ballena call-scalp is armed. If the sym's `corr` at `lead_min` is not significant (|corr|<0.15 or n<200) the factor is **muted for that sym** — no fleet-wide constant. Gates: captain rule 12 (captain's own RR overrides the name's), bollinger, PRINT-O-NADA on the price level, `optgate.py`.

**Validation:** lead-lag regression on the cube history: forward return ~ z(dRR), per sym, HAC standard errors; null = shuffled timestamps. Keep syms whose Wilson LB of directional hit rate at the fitted `lead_min` > 54% with n≥200 (5-min obs accumulate fast: ~78/day/sym).

**Effort:** M. Python (`scripts/skew.py`); the per-bar consumer stays C++ via JSON. New file.

**Kill risk:** IBKR `modelGreeks.impliedVol` is a smoothed model output, not the exchange's IV — its skew may be too flat to carry information, and it is absent outside RTH.

---

## 6. Blind Spots — peer-projected level clusters
**Skill slug:** `blind-spots`
**Inspired by:** #15 Blind Spots (the only genuinely proprietary MenthorQ metric) + dossier §2.8's falsification recipe. **We already own the hard input they hide: `peer_weights`.**

**What it computes**
1. For target `X`, take peers from `trades.db peer_weights` (`corr`, `beta`, `lead_min`, `weight`, `n`) — already computed by `scripts/peer_influence.py`.
2. For each peer `P` compute its level set (`gex_core`), then project into X's price space with **beta, not ratio** (the improvement over MenthorQ's prior-close ratio): `K_X = S_X · (1 + β_{X,P} · (K_P/S_P − 1))`, using **live** `S_P` from `data/nbbo_<peer>.txt`, never a prior close.
3. Weight each projected level `w = |corr| · normalized(|net_gex| of that level in P) · book_quality(P)`.
4. Cluster on X's axis, bandwidth `0.10 × ATR(14, 1m of X)` (scale-free), score = Σw, emit top 10 as `BL1..BL10` with member list, and **explicitly label the ranking as overlap density, not probability** (their own caveat, honestly reproduced).
5. **Our differentiator: exploit `lead_min`.** A cluster whose dominant members are peers that lead X by ≥5 min and are *currently testing* that level = a **pre-alert** on X. This is literally "anticipar antes del pico".

**Inputs:** `trades.db peer_weights`, `data/opt_chain_<peer>.txt` for all fleet peers, `data/nbbo_<sym>.txt`, `scripts/gex_core.py`, `scripts/peer_influence.py`, Korea peers via `data/bars_samsung.txt` / `bars_skhynix.txt` (13h lead, per `korea-memoria`).

**Output** `data/blind_spots.json`: `{"MU":{"asof":...,"bl":[{"px":94.6,"score":2.9,"members":[{"peer":"SMH","level":"call_wall","corr":0.81,"lead_min":6},{"peer":"NVDA","level":"gex_2","corr":0.74,"lead_min":3}],"leading":true}],"note":"overlap density != probability"}}`. Surfaces: dashed grey lines on `charts/live.html`; `direction_view` factor `blind_spot` (small weight ≤0.6, and only for `leading:true` clusters); banner-only INFO unless a leading peer is printing at the cluster, then SIGNAL; PDF page 1 as "zonas ciegas".

**Decision rule:** (a) **never open a position directly into an opposing BL** (their published rule, and it matches "no comprar a través de un muro intermedio"); (b) BLs are **targets** — take partials / tighten stops there, not entry triggers; (c) entry only when a BL coincides with our own gamma level *and* the leading peer already rejected it. Gates: captain rule 12 (if the leading peer is the captain, this *is* the captain signal), PRINT-O-NADA, `optgate.py`.

**Validation:** two independent tests. (i) **Reaction test**: does |return| / bar-range compress or reverse within ±0.1×ATR of a BL more than at the random-16 null (feature #3's null machinery)? Keep if edge ≥6pp, Wilson LB>null, n≥100. (ii) **Falsification against the vendor** (dossier's highest-value experiment): the MenthorQ free tier gives SPX/QQQ BLs; grid-search {peer set, β vs ratio, bandwidth, weight formula} to minimize mean |BL_ours − BL_theirs| over 20 sessions. If a config lands within a few ticks on most levels, we have cloned a $129/mo product for free.

**Effort:** M. Python (`scripts/blind_spots.py`), extends `peer_influence.py`. New file.

**Kill risk:** overlap density genuinely may carry no information (their own disclaimer is suspiciously honest) — and with a 26-sym fleet all highly correlated to SMH/QQQ, clusters may just reproduce the index's own levels, adding nothing.

---

## 7. Book Quality Gate — thin / bifurcated / sign-tagged walls
**Skill slug:** `book-quality`
**Inspired by:** #2 Total GEX vs Net GEX ("high total + negative net = trade the levels, not the regime") + dossier Recommendation 3 "sign-tag every wall".

**What it computes** (honest overlap: `chart_levels.pressure` already = `net/Σ|·|`; this adds **scale, concentration and sign**, which pressure throws away)
1. `gross = Σ_k |GEX_k|`, `net = Σ_k GEX_k` (have), `bifurcation = gross/|net|`.
2. `book_pctile` = percentile of `gross` against that **ticker's own** trailing 20-session distribution (cross-asset comparable, the Volatility-Q-Score trick). Requires persisting `gross` daily — a 1-row-per-sym-per-snapshot append to the new `gex_cube`/`gex_daily` table.
3. `HHI = Σ (|GEX_k|/gross)²` → concentration. Low HHI + low `book_pctile` = **THIN BOOK**: for DRAM, SPCX, SKHY, NOK the walls are literally 3 contracts and every gamma verdict about them is noise.
4. **Sign tag** on `abs_wall`: `+` = pin (dealers dampen), `−` = trapdoor (dealers amplify). Today `abs_wall` is picked by max |GEX| and the sign is discarded.
5. Regime label: `STABLE_PIN` (net>0, high pctile, high HHI) / `BIFURCATED` (net<0, high gross → respect individual strikes, distrust the regime) / `THIN` (low pctile → map invalid) / `NEAR_FLIP` (existing degradation).

**Inputs:** `scripts/chart_levels.py gen()` output (`profile`, `net_gex`, `abs_wall`, `call_gex`/`put_gex`), `scripts/gex_core.py`, new `gex_daily` table for the percentile history.

**Output** extend `data/levels_<sym>.json` / `chart_levels.gen()` with `{"gross":..,"bifurcation":6.2,"book_pctile":0.18,"hhi":0.07,"abs_wall_sign":"-","book_label":"THIN"}`. Surfaces: `direction_view` **multiplies** the wall/flip/magnet factor weights by a book-quality coefficient instead of adding a factor; the PDF prints "libro FINO — mapa gamma no fiable, operar solo precio"; banner colour; voice suppressed entirely for THIN.

**Decision rule:** `THIN` → all gamma-derived voice muted, wall-based signals become banner-only, trade only price/momentum (this is a *veto* feature, and vetoes are where our measured money is). `BIFURCATED` → trade level-to-level scalps, **do not** take regime-direction trades; expect violent moves that still respect strikes. `abs_wall_sign = "−"` within ±1 strike of spot → **hard veto on bought 0DTE** (extends the existing pin rule to trapdoors, which currently look identical to pins). Gates: this gate runs *before* rule 12 and before `optgate.py`.

**Validation:** re-run `conditioned_backtest.py` / `backtest_signal_outcomes` splitting all existing wall/flip signals by `book_label`. The hypothesis is that THIN-book signals have hit rate ≤ chance. Keep the gate if muting THIN raises the surviving population's Wilson LB by ≥4pp while removing <25% of signals. n is available *today* (3233 signals since 07-15).

**Effort:** S. Python, edits `scripts/chart_levels.py` + `gex_core.py` (additive keys only, backup first per the golden rule).

**Kill risk:** 20 sessions of `gross` history is a weak percentile base, and `gross` scales with the truncated strike window, so the percentile mixes book size with window artifacts until #13 lands.

---

## 8. Asymmetric Expected Move, coverage-solved
**Skill slug:** `em-envelope`
**Inspired by:** #12 1D Expected Move + GAP 4 (their coverage is asymmetric: 87.62% above min vs 85.02% below max).

**What it computes** (upgrades the existing symmetric `em = spot·iv_atm·√T`)
1. Replace the single ATM IV print with the **ATM straddle mid**: `em_straddle ≈ 0.8 × (call_mid + put_mid)` at the strike nearest spot in the front expiry — we have bid/ask in the RTH chain, so this is 2 quotes, essentially free, and it embeds skew and event premium.
2. Asymmetric envelope: `hi = S·exp(+k_u·σ_c·√(D/252))`, `lo = S·exp(−k_d·σ_p·√(D/252))`, with `σ_c`/`σ_p` from the 25Δ call/put IVs (feature #5) and `D` = **calendar-aware** trading-day count (a Friday-close level must span 3 days — the current code does not).
3. **Solve `k_u`, `k_d` empirically per sym** so realized next-session coverage matches a target (start 85/87.5 to mirror their audited numbers), on `poly_bars` daily + `data/backtest/bars30d_<sym>.csv`. Do not guess the formula; match measured coverage. Report achieved coverage with Wilson CI.
4. **Earnings invalidation**: mark the envelope `invalid_reason:"earnings"` on the ticker's earnings date (Finviz Elite gives us the dates via `scripts/finviz_scan.py`) — MU/NVDA prints blow through a vol-scaled band routinely.
5. `em_exhaustion`: price reaching `hi` while `hi > call_wall` = exhaustion, not breakout (their published rule).

**Inputs:** `data/opt_chain_<sym>.txt` (bid/ask/iv/delta), `scripts/gex_core.py` (`em`, `iv_atm`), `poly_bars` + `data/backtest/bars30d_<sym>.csv` for the k-solve, `scripts/finviz_scan.py` earnings dates, `scripts/chart_levels.py`.

**Output** extend `gen()`: `{"em":..,"em_src":"straddle","em_hi":..,"em_lo":..,"k_u":1.08,"k_d":1.19,"cov_hi":0.86,"cov_hi_ci":[0.79,0.91],"cov_two_sided":0.71,"n":180,"invalid_reason":null}`. Surfaces: chart envelope; `direction_view` target clipping (GEX levels ranked **inside** the envelope, per their #11); PDF "valla del día"; SIGNAL voice at envelope touch with exhaustion label.

**Decision rule:** GEX/wall levels outside `[em_lo, em_hi]` are **not today's levels** — drop them from ranking and from targets (this is the single cheapest quality improvement to `direction_view.target`). Touch of `em_hi` above the call wall → fade / take profits, never chase. `invalid_reason` set → no envelope-based trade at all. Gates: PRINT-O-NADA at the edge, bollinger (%B extreme + envelope edge = the strongest fade confluence we can state), `optgate.py`.

**Validation:** rolling walk-forward coverage: fit `k_u,k_d` on sessions 1..N, measure realized coverage on N+1... Keep only if out-of-sample coverage is within ±4pp of target with n≥120 sym-sessions; report per-sym, and if a sym cannot be calibrated (thin chain), fall back to the symmetric `em` **and label it**.

**Effort:** S–M. Python, edits `gex_core.py` + `chart_levels.py`, new `scripts/em_calibrate.py` for the k-solve (offline, weekly).

**Kill risk:** front-expiry straddle on a 0DTE afternoon is not a "1-day" move at all; the D-count and the expiry choice have to be right or the envelope silently becomes a 3-hour band.

---

## 9. Close-Drift Engine — charm + DEX pin drag
**Skill slug:** `close-drift`
**Inspired by:** #4 Net DEX (with its inverted flow sign) + #14 Gamma Wall 0DTE pinning; `gex_core.bs_charm` exists and **nothing in our stack consumes it**.

**What it computes**
1. `DEX_k = Δ_k · OI_k · 100 · S` (dealer sign), `net_dex = Σ DEX_k`. Track intraday `d(net_dex)/dt`. **Encode the sign trap explicitly**: positive DEX = bullish customer positioning **but** implies MMs sell underlying to stay neutral (negative liquidity event). Two fields, never one: `dex_sentiment` and `dex_flow_impact`.
2. `CEX_k = charm_k · OI_k · 100 · S` via `gex_core.bs_charm` / `build_exposure(greek="charm")` — delta decay per unit time. Aggregate signed → **the mechanical hedge flow implied by the passage of time alone**, which is exactly what drags price into a pin between 14:00 and 16:00.
3. `drift_target` = the strike toward which cumulative charm-implied hedging points; `drift_force` = Σ|CEX| normalized by ADV (from `data/bars_<sym>_ibkr.txt` volume) → "how many shares of mechanical buying/selling per hour" — a size, not a vibe.
4. Only armed when `regime=POS` and `book_label != THIN`: charm pin requires dealers who dampen.

**Inputs:** `data/opt_chain_<sym>.txt` (delta column, RTH), `scripts/gex_core.py` (`bs_charm`, `build_exposure` — already written), `data/bars_<sym>_ibkr.txt` for ADV, `data/history/...` for the intraday `dDEX/dt` series.

**Output** `data/close_drift.json`: `{"QQQ":{"net_dex":-3.1e9,"dex_sentiment":"bearish","dex_flow_impact":"MM buys (positive liquidity)","ddex_30m":+2e8,"drift_target":686,"drift_force_sh_hr":420000,"pct_adv":0.031,"armed":true,"window":"14:05-16:00"}}`. Surfaces: `direction_view` factor `charm_drift` (weight 0.8, time-gated to the last 2 hours); voice SIGNAL at 14:05 "QQQ arrastre charm hacia 686, 3.1% del ADV/hora"; chart magnet marker; PDF's afternoon branch.

**Decision rule:** in the 14:00–16:00 window with `armed:true` and `drift_force > 2% ADV/hr`, trade **toward** `drift_target` from the near side only (never through an intermediate wall — post-mortem 2026-07-20), size small, exit by 15:45. If `abs_wall_sign="−"` (feature #7) the drift is a trapdoor not a pin → **no trade**. Explicit no-trade: levels stacked (drift target within 0.15% of the flip) = excessive chop, their published rule and ours. Gates: captain rule 12, PRINT-O-NADA on entry, `optgate.py` (0DTE ≤$200, spread ≤5%, OI>500).

**Validation:** on the cube history, regress 14:00→15:55 return on `drift_force × sign(drift_target − S_1400)`, controlling for morning return (to avoid re-discovering intraday momentum, per Baltussen et al.). Null: same trade taken toward a random strike. Keep if Wilson LB of "closed nearer to drift_target than to spot_1400" > 58% with n≥50 sym-sessions and it beats the null by ≥10pp.

**Effort:** M. Python for the exposure math (`scripts/close_drift.py`); the 14:00 arming loop is light, no C++ needed. Extends `gex_core.py` consumers.

**Kill risk:** charm-implied flow is dwarfed by index rebalance/MOC imbalance, which we cannot see — so `drift_force` may be real but irrelevant.

---

## 10. Level-Reaction Primitive (C++) — PRINT-O-NADA as a shared module
**Skill slug:** *(no skill; library)*
**Inspired by:** dossier §2.9 MenthorQ Reversal / Wick rules.

**What it computes** (needs **no option data at signal time** — the cheapest thing in this whole list)
1. Load the day's level set once (`data/levels_<sym>.json` from `chart_levels`), refresh on file mtime change (this also fixes MenthorQ's documented "alerts self-expire daily" defect by construction).
2. Per closed bar, for each level `L`:
   - `active(L)`: `high>L && low<L` **on both the current and previous bar** (= two readings crossing the level; this *is* PRINT-O-NADA, not "está cerca").
   - `REV_LONG`: prev bar red, current bar green, `active(L)`.
   - `REV_SHORT`: prev bar green, current bar red, `active(L)`.
   - `WICK_REJECT_UP`: `high>L && close<L && |high−close| > |open−close|`.
   - `BREAK_CONFIRMED`: closed across `L`, then failed to reclaim within 3 bars (their published Put-Support confirmation trigger).
3. Emits an event with `level_type`, `touch_idx` (shared with feature #4), and the bucket key for `calibration_ledger`.

**Inputs:** `data/bars_<sym>_ibkr.txt` (1m aggregated, already the bots' input), `data/levels_<sym>.json`, `data/level_stats.json` (feature #3) for the probability, `fleet_notify.h` for the notify path.

**Output** `scripts/level_react.cpp` → shared header `level_react.h` linked into every `*_signal_bot.cpp`, `price_alarm.cpp`, `scalper/whale_scalper.cpp`. Emits to `signals` table via `scripts/signals_db.py` path and to `data/level_events.jsonl`: `{"ts":..,"sym":"MU","level":"put_wall","px":92,"event":"REV_LONG","touch_idx":1,"prob":0.61,"ci":[0.5,0.71],"n":88}`.

**Decision rule:** only `REV_*` / `BREAK_CONFIRMED` events whose `level_stats` bucket has `keep:true` and Wilson LB ≥55% produce voice; everything else is banner. Gates in this order: book-quality (#7) → captain rule 12 → bollinger (band stretched against = no reversal trade) → `optgate.py` for vehicle choice.

**Validation:** immediately testable on data we already have — replay `data/hist/bars_<sym>_1m_30d.txt` (30 days, QQQ/NVDA/TSLA) + `data/backtest/bars30d_*.csv` against the levels reconstructed per session, via `scripts/backtest_replay.py` / `conditioned_backtest.py`. Null: the same reversal candle pattern at a **random** price with no level. Keep only if the level-conditioned version beats the pattern-alone version by ≥6pp (this is the whole point: does the level add anything to a red→green flip?).

**Effort:** S. **C++23** (fleet hot path, per the house rule), new `scripts/level_react.cpp` + header; one-line inclusion per bot.

**Kill risk:** the two-bar-straddle condition may be strictly worse than the bots' current ad-hoc triggers — and if the level adds <6pp over the bare candle flip, we've built a prettier way to lose.

---

## 11. Borrowed Map — gamma levels for our map-less tickers
**Skill slug:** `borrowed-map`
**Inspired by:** #17 Levels Conversion (and its admitted weakness: prior-day closes). We fix it with live basis.

**What it computes**
1. Identify map-less members of the fleet: DRAM, SPCX, SKHY, EWY, NOK, and the leveraged vehicles we actually trade (TQQQ/SOXL/SOXS/leveraged pairs in `data/leveraged_map.json`) — their option chains fail OI>500 / spread≤5% and their GEX profile is noise (verifiable via feature #7's `book_pctile`).
2. Choose a parent by measured relationship, not by hand: highest `corr` with sufficient `n` from `peer_weights` (SMH or MU for the memory ETFs, QQQ for XLK-ish, EWY↔SMH/Samsung).
3. Project each parent level with **live** basis: `K_child = S_child · (1 + β · (K_parent/S_parent − 1))`, `S_parent` from `data/nbbo_<parent>.txt` refreshed each tick, `β` from `peer_weights` refit weekly (for 3x ETFs β≈3 but **measure it**, decay makes it drift).
4. Report `basis_drift` = the change in `S_child/S_parent^β` since the open; if drift exceeds a threshold the borrowed map is stale → fail loud.

**Inputs:** `trades.db peer_weights`, `data/nbbo_<sym>.txt` (child and parent), `scripts/chart_levels.py gen(parent)`, `data/leveraged_map.json`, `scripts/peer_influence.py`.

**Output** `data/borrowed_map.json`: `{"DRAM":{"parent":"SMH","beta":1.62,"corr":0.78,"n":420,"levels":{"call_wall":31.4,"put_wall":29.8,"flip":30.6},"basis_drift_pct":0.21,"stale":false}}`. Surfaces: chart lines drawn dashed + labelled "prestado de SMH (β1.62)" — never as if native; `direction_view` for those syms gets its wall/flip factors from here at **reduced weight** (×|corr|); PDF for those tickers finally has a level page instead of "sin mapa".

**Decision rule:** for a map-less ticker, trade its borrowed levels **only** when the parent is simultaneously at the corresponding parent level (double print — this is rule 12 made mechanical: the captain's level *is* the signal). `basis_drift` beyond threshold or `corr<0.6` → no levels, banner only. Vehicle: since these tickers' options fail `optgate.py`, the decision output is shares / leveraged ETF, announced explicitly ("OPCIONES VETADAS").

**Validation:** does the child react at borrowed levels more than at the random-16 null (feature #3 null, run on the child)? Keep per (child, parent) pair if edge ≥6pp with n≥80. Also compare β-projection against naive ratio projection — publish which wins; if ratio wins, keep ratio.

**Effort:** S. Python (`scripts/borrowed_map.py`), extends `peer_influence.py` + `chart_levels.py`. New file.

**Kill risk:** leveraged-ETF path dependency and ETF-specific flow mean the child's own dealers hedge in the *child*, so parent levels may not map at all.

---

## 12. Tomorrow's Map Tonight — expiry-decayed provisional walls
**Skill slug:** `next-day-map`
**Inspired by:** #3 Net GEX multi-expiration ("is today's structure a same-day artifact or a structural wall?") + #33 Option Matrix change columns.

**What it computes**
1. At 16:05, take the last chain snapshot. **Remove all contracts expiring today** — their OI is about to be zero, yet the 4am plan currently maps the fleet using a cache that still contains them. This alone materially changes the Monday map.
2. Roll today's volume into OI with the measured κ from feature #1: `oi_tomorrow = oi + κ·vol` for surviving expiries, and **re-time** every contract (`T → T − 1/252`), which shifts gamma concentration toward the new front expiry.
3. Recompute the full level set on the re-timed provisional cube → tomorrow's `flip`, walls, `abs_wall` sign, envelope.
4. Emit **`delta_vs_today`** per level: what moved, how much, and why (expiry roll vs volume accretion). This is the sentiment-shift detector the Option Matrix's "change" columns provide.
5. Post-mortem the previous night's forecast against the actual 09:35 map — a self-scoring feature.

**Inputs:** `data/history/<date>/opt_chain_<sym>_1600.txt`, `data/gamma_flow.json` (κ), `scripts/gex_core.py`, `scripts/daily_fleet_plans.py` (consumer), `scripts/postmortem_run.sh` (self-scoring).

**Output** `data/next_day_map.json`: `{"asof":"2026-07-24T16:05","MU":{"today":{"flip":94.2,"call_wall":96},"tomorrow":{"flip":93.6,"call_wall":95,"abs_wall":94,"abs_wall_sign":"+"},"delta":[{"level":"call_wall","from":96,"to":95,"cause":"0DTE roll-off"}],"forecast_err_prev":0.18}}`. Surfaces: consumed by the 04:00 `daily_fleet_plans.py` run as the **primary** map (with the live 08:00 refresh overriding it); PDF page 1 "mapa de mañana"; nightly email; postmortem accuracy line.

**Decision rule:** the night-before order tickets (rule 10, "fichas de orden preparadas la víspera") are built from this map, not from today's stale one. If `forecast_err_prev` (mean |forecast − actual| / em) exceeds a threshold for a sym over the last 5 sessions, that sym's night map is **not** used for tickets — fail loud, revert to waiting for the 08:00 live snapshot.

**Validation:** direct and cheap — `|forecast(t) − actual 09:35 map(t+1)|` per level per sym, normalized by `em`, vs the naive baseline "tomorrow = today's map unchanged". Keep only if median normalized error beats the naive baseline by ≥20% over n≥30 sym-sessions.

**Effort:** S–M. Python (`scripts/next_day_map.py`), feeds `daily_fleet_plans.py` (back up the generator first, per the golden rule).

**Kill risk:** overnight OI change is dominated by new positioning we cannot see, so the naive "map unchanged" baseline may simply win — in which case the feature reduces to the expiry-roll fix, which is still worth having on its own.

---

## 13. Cube Widening — 3rd expiry + sparse wings (enabler, not cosmetics)
**Skill slug:** *(no skill; infra)*
**Inspired by:** #3 Multi-Expiration (0DTE vs monthly divergence) + GAP 1's note that per-strike IV at the wings is the likeliest source of vendor divergence.

**What it computes / changes**
1. `scripts/opt_chain_cache.py`: `exps = sorted(...)[:2]` → `[:2] + [nearest monthly (3rd-Friday) expiry]`, for a **priority subset** (QQQ, SPY, NVDA, MU, SMH, TSLA, AMD) to keep the cycle under `CYCLE_S=180`.
2. Strike selection: instead of the 20 nearest, take the 14 nearest **plus** a sparse ladder (every 3rd strike) out to the real `PCT_BAND=0.06`. Same TWS line count, radically better tails — which is what the flip and the 25Δ interpolation depend on.
3. New emitted fields per snapshot: `exp_kind` (0DTE/weekly/monthly), and the `net_gex` curve per expiry so the **0DTE-vs-monthly divergence** is computable.
4. Fail-loud instrumentation: log per-sym `greeks_ok_pct`; if <80% during RTH, write a `stale` flag into the file header so every downstream consumer can degrade honestly instead of silently defaulting `iv=0.3` (which is what `gex_core.from_ibkr_cache` does today).

**Inputs / Output:** edits `scripts/opt_chain_cache.py` (FLEET, `PCT_BAND`, `MAX_STRIKES`, `exps`) and the file header contract shared with `scripts/opt_quick.cpp` — **the header format is a hard contract; extend, never reorder columns.** Measure cycle time before/after; if >170s, split into two staggered daemons rather than dropping symbols.

**Decision rule it produces:** `multi_exp_divergence` — a wall present in 0DTE but absent in weekly+monthly is an **artifact that dies at 16:00** → fade the pin from 15:40, don't respect it tomorrow. Present in all three = structural → respect it, and it becomes a valid swing level. This is a real discriminator we cannot compute at all today.

**Validation:** classify walls as artifact vs structural on the history cube once widened; measure next-day survival of each class (does the wall strike remain the argmax?). Keep if structural walls survive ≥2× as often as artifacts, n≥60.

**Effort:** S (code) / M (validation + a week of waiting for history). Python, edits an existing daemon — **back up to `backup/` first**, additive fields only, and verify `opt_quick.cpp` still parses.

**Kill risk:** IBKR market-data line limits and cycle-time blowup on an 8GB Mac; the honest fallback is monthly expiry for 4 symbols only.

---

## 14. Mechanical Supply Gauge — vol-control & vol-barometer proxy
**Skill slug:** `mechanical-supply`
**Inspired by:** #38 Volatility Control Fund Model (the one verbatim formula: 1-month vs 3-month realized vol) + #39 LSVB.

**What it computes** (the only multi-day, non-intraday item here — orthogonal to everything we own)
1. `RV21` and `RV63`: annualized close-to-close realized vol from `poly_bars` daily (offline batch, so yfinance is permitted only as backup and never on a signal path).
2. `vc_signal = RV21/RV63 − 1`. Rising through 0 ⇒ vol-target funds mechanically **delever** (sell equities) over the following days; falling ⇒ re-lever. Report the *rate* of change, because the flow is proportional to it.
3. Cross-check with the VX term structure we already fetch (`cboe-data` skill): contango→backwardation flip is the same regime seen from the vol side; agreement of the two is the higher-conviction state.
4. LSVB proxy: dollar volume of long-vol vs short-vol ETFs (UVXY/VXX vs SVIX/SVXY) — available from IBKR bars if we add those symbols to the bridge (**currently missing**; cheapest proxy is VX term slope alone, which we already have, and to state honestly that the ETF-flow component is absent).
5. Combine into `supply_pressure ∈ [−1,+1]` with a **stated horizon of 1–5 days**, never intraday.

**Inputs:** `poly_bars` (daily closes, fleet), CBOE VX via the `cboe-data` skill, `data/gexa_snapshot.json` for context. Missing: vol-ETF dollar volume (add UVXY/VXX/SVIX to `ibkr_bar_bridge.py` if we want the full LSVB).

**Output** `data/mechanical_supply.json`: `{"asof":..,"rv21":0.214,"rv63":0.181,"vc_signal":+0.18,"vc_d5":+0.09,"vx_slope":-0.04,"agree":true,"supply_pressure":-0.55,"horizon_days":"1-5","lsvb":null,"lsvb_missing":"vol ETF volume not ingested"}`. Surfaces: `direction_view` factor `macro_supply` (small weight ≤0.5, and **only** applied to QQQ/SPY/SMH, the captains); the daily email and PDF header ("presión mecánica de venta 1-5 días"); banner-only, never voice (wrong timescale for a siren).

**Decision rule:** `supply_pressure < −0.4` with `agree=true` → **the day's dip-buy signals get their size halved and the "verde tarde = proteger" rule is enforced earlier**; do not carry bought premium overnight. `> +0.4` → dip-buys are allowed full size. This is a position-sizing modifier, not an entry signal — which is exactly how it should be framed and is where its honest edge lives.

**Validation:** regress next 1/3/5-day SPY & SMH returns and realized vol on `vc_signal` and its change, over as much `poly_bars` history as we can download (years, cheap). Null: the unconditional distribution. Keep only if the top/bottom `vc_signal` quintiles differ in mean 5-day return with Wilson/bootstrap CIs excluding zero **after** a Deflated-Sharpe adjustment (`stats-trading-risk` skill) for the handful of parameterizations tried.

**Effort:** S. Python (`scripts/mechanical_supply.py`), offline batch at 04:00 in the existing cron. New file.

**Kill risk:** it is a well-known published effect on a 1–5 day horizon and probably already in the price; and our entire edge is intraday, so even if true it may never change a decision.

---

## What I deliberately did **not** propose
- **Q-Score composite** — MenthorQ itself doesn't publish one; there is nothing to match, and `direction_view` already *is* our weighted composite. Building a second one competes with the arrow.
- **Seasonality score** — computable from `poly_bars` in an hour, but a 20-year 5-day-window mean on a 30-ticker semis fleet with 3 years of relevant regime is a hardcoded prior in disguise.
- **Momentum / breadth models (#40–45)** — `force_meter.py`, `momentum_calc.cpp`, `index_breadth.py`, `bollinger_alarm.py`, `pattern_detect.py` already cover every one of them.
- **Volume/OI-by-strike, bid/ask-by-strike, IV Rank, term structure charts, Option Matrix, screeners, CTA models** — respectively `opt_flow.txt`/`flow_pulse`, `optgate.py`, trivially derivable but purely descriptive, or (CTA) unmeasurable with our data.
- **Swing Trading Model bands** — "advanced machine learning, unspecified" with no published hit rates. Nothing to reproduce.

**One-line honest summary of the whole set:** items 1, 2, 5 and 9 are the anticipation engines (they act on *derivatives* of positioning, which is what moves before price); items 3, 4 and 7 are the measurement and veto layer that makes the rest honest; 10, 8, 11, 12, 13 are cheap high-certainty infrastructure; 6 is the highest-upside gamble (and it is falsifiable against the vendor's free tier); 14 is the only swing-horizon item and it is a sizing modifier, not a signal.