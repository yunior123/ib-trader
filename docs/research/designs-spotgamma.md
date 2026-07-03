## P0 prerequisites (verified today, both cheap, both block several features below)

- **IBKR chain cache is too narrow and its greeks are often absent.** `scripts/opt_chain_cache.py` writes `PCT_BAND=0.06`, `MAX_STRIKES=20`/expiry, **only the 2 nearest expiries** (`exps[:2]`). Verified greek coverage in `data/opt_chain_*.txt` right now: NVDA `0/40` rows with IV, NOK `0/8`, SPY `1/80`, MU `1/66` (bid/ask also `-1.00` outside RTH). So any "full book" GEX/flip/VT built only on this file is band-truncated and greek-starved.
- **Polygon full-chain snapshot IS entitled** (I probed it): `GET /v3/snapshot/options/{underlying}` returns, for **every expiry and strike**, `greeks{delta,gamma,theta,vega}`, `implied_volatility`, `open_interest`, `day{volume,...}`. → new nightly job `scripts/chain_full_snap.py` → `data/history/<date>/chain_full_<sym>.json`. This is the structural book for everything below. Polygon aggs are delayed → **batch/nightly only, never on a signal path**.
- **Polygon options tape is NOT entitled** (verified: `/v3/trades/O:...` and `/v3/quotes/O:...` → `NOT_AUTHORIZED`). So a true HIRO (Lee-Ready on OPRA prints) is off the table with today's spend. Everything below that smells like flow is deliberately built from **Δ(cumulative option volume) between 5-min chain snapshots**, which we already archive: `data/history/YYYY-MM-DD/opt_chain_<sym>_HHMM.txt` (2140 files on 2026-07-24, 1043 on 07-23, 245 on 07-22 — a 4-day-old and growing asset nobody is mining yet).
- **IV-inversion fallback** (bisection on mid, put-call-parity forward) added to `scripts/gex_core.py` so live paths survive `iv=-1`. `gex_core` already has `bs_gamma/bs_vanna/bs_charm/flip_recompute/wall_context/_T_of` — extend, don't rewrite.

---

## 1. Delta-Notional Flow (DNF) — `flow-delta-notional`

- **Inspired by**: HIRO (delta-notional signed flow) + HIRO Flow Alerts (per-symbol adaptive threshold).
- **What it computes**:
  1. Every 5 min, for each contract *i* in the chain snapshot: `Δv_i = vol_i(t) − vol_i(t−1)` (cumulative day volume differences; drop `Δv_i ≤ 0`).
  2. Sign it **without a tape** using a premium-residual test: expected mid change from spot/time alone `Δm̂_i = δ_i·ΔS + ½γ_i·ΔS² + θ_i·Δt`; residual `r_i = Δmid_i − Δm̂_i`. `sign_i = +1` if `r_i > κ·halfspread_i` (customer lifting offers), `−1` if `r_i < −κ·halfspread_i`, else **0 = dropped** (this is our G3 "hedged/passive print" filter). Start `κ = 0.5`, calibrate.
  3. `impact_i = sign_i · δ_i · Δv_i · 100 · S`, and **`+=` for puts too** — put delta is natively negative, so direction is automatic (this is precisely the V1→V2 bug documented in `open-gamma`; do not negate puts).
  4. `DNF = Σ impact_i`, split `dnf_calls / dnf_puts`; `velocity = DNF(t) − DNF(t−15m)`.
  5. Standardize per ticker: `z = velocity / σ_20d(velocity_same_window)` — z-scoring against the ticker's own trailing distribution gives the Flow-Alert threshold for free (G4+G5). Fire at `|z| ≥ 2.5` with hysteresis (must re-enter ±1.0 before re-arming) and a 10-min per-name cooldown.
- **Inputs from our stack**: live path = `data/opt_chain_<sym>.txt` (has `vol oi bid ask iv delta gamma` per line) refreshed by `opt_chain_cache.py`; `data/nbbo_<sym>.txt` for `ΔS`; greeks via `gex_core` IV-inversion when `-1`. Backtest path = `data/history/*/opt_chain_<sym>_HHMM.txt` + `trades.db poly_bars`. **MISSING**: true aggressor side (no options tape). Cheapest proxy is exactly the residual test in step 2; the honest fallback if it fails validation is unsigned `|Δv|`-weighted delta imbalance, i.e. what `opt_whale_watch.py` already does but delta-weighted instead of contract-count weighted.
- **Output**: `data/dnf_<sym>.json` → `{"sym","ts","dnf","dnf_calls","dnf_puts","velocity","z","window_min":5,"n_signed","n_dropped","pct_signed","state":"CALLS_PRESSING|PUTS_PRESSING|FLAT","stale_sec"}`. Surfaces as: new `direction_view.py` factor `dnf` (weight ~1.2, replacing part of `captain_flow`'s raw P/C), chart overlay line in `charts/live.html` (cumulative DNF pane), voice **SIGNAL** on `|z|≥2.5`, **DANGER** only when it coincides with a wall touch. `pct_signed < 35%` ⇒ publish `state:"UNRELIABLE"` and fail loud, never silently emit 0.
- **Decision rule**: **DNF flattening at a wall = local extreme, trade the reversion** (espada-ballena, but delta-weighted): at Call Wall with `velocity → 0` from positive ⇒ fade long / buy put; at Put Wall with `velocity → 0` from negative ⇒ buy call. Must still pass: print-2-readings at the wall, `optgate.py` spread ≤5% + OI>500 + premium ≤$200, Bollinger check (no fade into a 3-TF band-walk), and **rule 12** — if the governing captain's DNF is opposite, the name's DNF is banner-only, captain speaks.
- **Validation**: event study over `data/history` (grows 1 day per day, need ~40 sessions ⇒ decision ~2026-09) joined to `poly_bars` 1m: forward return at +1/+5/+15 min after each `|z|≥2.5` event, bucketed by `regime × time-of-day × wall-proximity`. **H0**: forward return distribution equals unconditional. Keep only buckets whose **Wilson lower bound ≥ 55% at n ≥ 60** via `calibration_ledger.py`; expect (per our own whale-scalper result) the fade to pay at **+5 min, not +1 min** — if the +5m edge doesn't reappear here, the signing step is worthless.
- **Effort**: **M** — C++23 hot path `dnf_pulse.cpp` next to `flow_pulse.cpp` (same snapshot-diff loop, same JSON writer); Python only for the offline event study (`scripts/dnf_backtest.py`).
- **Kill risk**: the residual signing is noise — option mids at 5-min granularity move mostly with IV, not aggression, so `sign_i` becomes a coin flip and DNF degenerates into unsigned volume we already have.

## 2. Volatility Trigger, frozen — `vol-trigger`

- **Inspired by**: Volatility Trigger™ / Hedge Wall (G1, G10).
- **What it computes**:
  1. Build `net_gex(K)` from the full nightly chain (`chain_full_<sym>.json`) via `gex_core.build_gex`, plus the continuous profile `G(S)` on a ±15% grid with `flip_recompute` (re-gamma at each hypothetical spot, bisection-refined).
  2. `VT = max{ K ≤ spot : net_gex(K) > 0 and net_gex(K) ≥ 0.05·Σ|net_gex| }` — the **last dense positive-gamma shelf below spot**, not the zero crossing. Fallback: listed strike nearest continuous Zero Gamma. Require a populated neighbour on each side (anti chain-truncation artifact).
  3. **Freeze `vt_open` at 09:35 ET** and do not re-flap it intraday (kills crying-wolf); publish `vt_live` separately for diagnostics.
  4. Approach alarm (the anticipation): `dist_vt = (spot − vt)/EM_day`; when `dist_vt < 0.35` **and** DNF velocity is negative **and** force phase ∈ {GIRO, AGOTAMIENTO} ⇒ pre-arm before the cross.
- **Inputs**: `data/history/<date>/chain_full_<sym>.json` (P0), `scripts/gex_core.py`, `scripts/chart_levels.py gen()` for `spot/em/flip/regime`, `data/force.json`, `data/dnf_<sym>.json`, `data/bars_<sym>_ibkr.txt`.
- **Output**: `charts/data/vt_<sym>.json` → `{"sym","vt_open","vt_live","zero_gamma","dist_vt_em","regime_vt":"ABOVE|BELOW","shelf_gex_pct","frozen_at","source":"polygon_full|ibkr_band"}`. Surfaces as a frozen horizontal line on `charts/live.html`, a `why[]` string in `direction_view.py` ("bajo VT 683 → momentum, no fadear"), page 1 of the daily PDF, voice **DANGER** on the first confirmed close below `vt_open`.
- **Decision rule**: `spot > vt_open` ⇒ mean-reversion licence: fade into Call Wall, sell/avoid chasing, flies OK. `spot < vt_open` ⇒ **momentum licence: fading is banned, widen stops, no pin trades, no premium selling**. Cross with 2 prints. Overrides Bollinger-fade signals (a stretched band against you below VT is continuation, not elastic rebound) — this is the rule-1 refinement.
- **Validation**: classify each of ~250 sessions in `poly_bars` by open-vs-`vt_open`; compute 5-min realized vol and Parkinson range per day; two-sample test. Target: reproduce a material split (SpotGamma publishes 13% vs 18% 5-day RV). **H0**: RV identical either side. Also log every cross into `backtest_signal_outcomes` with `source='vt_cross'`, horizons 15/60/390 min; keep if fade-hit-rate below VT drops **below** 45% (Wilson upper bound) — i.e. the value is a veto, not a signal.
- **Effort**: **M** — Python for the nightly level (`scripts/vol_trigger.py`, extends `gex_core`), C++ for the live approach watcher (fold into `price_alarm.cpp`, which already does level watching).
- **Kill risk**: with only 2 expiries and ±6% of strikes on the live path, the "last positive shelf" is an artifact of chain truncation and jumps around between days — making the frozen level arbitrary.

## 3. Wall decay ledger — `wall-decay`

- **Inspired by**: Call/Put Wall breach statistics (83%/89% hold) + `wall_strength_tracker` ΔOI build/break.
- **What it computes**: turns our folklore ("1st touch bounces ~70%, 3+ exhausted") into a measured table.
  1. Each session, freeze `call_wall`, `put_wall`, `abs_wall` at 09:35 from `chart_levels.gen()`.
  2. Scan `bars_<sym>_ibkr.txt` 1m: a **touch** = high/low within `0.10%·S` of the level; a new touch requires a prior excursion of ≥`0.25%·S` away (de-bounce). Count `touch_idx`.
  3. Outcome per touch at +15m: `REJECT` (moved ≥0.3% back inside), `BREAK` (closed ≥0.15% beyond for 2 bars), `CHOP`.
  4. Wall health from our 5-min chain history: `oi_delta_pct` (vs prior close) and `vol_at_strike / vol_at_strike_20d_median` at the wall strike ⇒ `BUILDING | HOLDING | WEAKENING`.
  5. Record `(sym_class, wall_type, touch_idx, regime, hour_bucket, health) → Wilson(reject rate)` in a new `trades.db` table `wall_touches`.
- **Inputs**: `charts/data/levels_<sym>.json`, `data/bars_<sym>_ibkr.txt`, `data/history/*/opt_chain_<sym>_HHMM.txt` (the only place intraday strike volume lives), `trades.db poly_bars` for pre-history back-fill of touches (levels can be recomputed retroactively from `data/history` chains — 4 days now, so back-fill from Polygon nightly chains is the real bulk).
- **Output**: `data/wall_stats.json` → `{"<class>|<type>|<touch_idx>|<regime>":{"n","reject","p","lo","hi","health_split":{...}}}` + per-symbol live `data/wall_live_<sym>.json` `{"wall","type","touch_idx","health","p_reject","p_lo","n"}`. Surfaces as: the probability spoken in every wall alarm ("call wall 690, 2º toque, régimen POS, rechazo 61% [IC 52-70, n=88]"), replaces the hardcoded 70% in `gamma-regime-walls`, and a `why[]` line.
- **Decision rule**: trade the wall **only** when `p_lo ≥ 0.55` for the current `(touch_idx, regime, health)` cell; `touch_idx ≥ 3` or `health=WEAKENING` ⇒ **flip to breakout side after retest-and-rejection**, never fade. Cell with `n < 30` ⇒ banner only, no voice, no ticket. Gates: print-2-readings, optgate, captain rule 12.
- **Validation**: this feature *is* the validation harness. **H0**: reject rate = 50% in every cell, and independent of `touch_idx`. Worth keeping if (a) at least 3 cells clear `p_lo ≥ 0.55` at `n ≥ 40`, and (b) a monotone decay in `touch_idx` survives a chi-square trend test. Wire through `calibration_ledger.record()` so it self-recalibrates.
- **Effort**: **S/M** — Python `scripts/wall_ledger.py` (offline, batch, joins bars+chains) + tiny read in the C++ bots. Extends `calibration_ledger.py`.
- **Kill risk**: n starves — 30 tickers × ~1 wall touch/day, split across regime×touch_idx×health, means many months before any cell clears Wilson; the honest outcome may be "no measurable difference between 1st and 3rd touch".

## 4. Level-reliability gate (Options Impact) — `impact-gate`

- **Inspired by**: Options Impact gauge + the "High Impact" scanner + HIRO Signal 30-day range card.
- **What it computes**: whether gamma levels deserve to be obeyed *for this ticker today*, before any of them are quoted.
  1. `gex_notional = Σ|GEX$(K)|` (per 1% move) from the chain.
  2. `stock_notional = ADV20_shares × price` from `bars_*_ibkr.txt` / `poly_bars`.
  3. `impact_raw = gex_notional / stock_notional`; `impact_pct` = percentile of `impact_raw` within (a) the fleet today and (b) that ticker's own trailing 60 days.
  4. Companion `flow_extremity` = today's `|DNF|` percentile in its own trailing 30-day range (the HIRO gauge dot).
  5. `level_trust = clamp(0.5·impact_pct + 0.5·flow_extremity)`.
- **Inputs**: `charts/data/levels_<sym>.json` (`net_gex`, `profile`), `data/bars_<sym>_ibkr.txt`, `trades.db poly_bars` for ADV20, `data/dnf_<sym>.json`.
- **Output**: `data/level_trust.json` → `{"<SYM>":{"impact_raw","impact_pct","flow_extremity","level_trust","tier":"GREEN|AMBER|RED","adv20","gex_notional"}}`. Surfaces as: a multiplier on the `flip/walls/magnet` weights inside `direction_view.py`, a colour badge on `charts/live.html`, a line in `signal_conditioning.conditioned_prob()`, and a hard filter for which tickers get gamma content in the PDF.
- **Decision rule**: `RED` (`level_trust < 0.33`) ⇒ **gamma levels are decoration for this name today**: no wall trade, no flip trade, no magnet target; only price/momentum/captain logic. `GREEN` (>0.66) ⇒ full weight and walls may be voiced as DANGER. Expected to permanently mute gamma talk on DRAM/SPCX/SKHY/EWY/NOK (illiquid chains) — which is the honest result, and directly implements the "no Yahoo-grade inputs on signal paths" spirit.
- **Validation**: re-run `conditioned_backtest.py` / `backtest_signal_outcomes` splitting every historical wall/flip signal by `level_trust` tercile. **H0**: hit rate independent of tercile. Keep if `GREEN` tercile hit rate exceeds `RED` by ≥8 points with non-overlapping Wilson intervals at `n ≥ 80` per tercile. This is cheap to test because we already have 2916 graded outcomes.
- **Effort**: **S** — Python `scripts/level_trust.py`; one read added to `direction_view.py` and `signal_conditioning.py`.
- **Kill risk**: `impact_raw` is dominated by chain breadth artifacts (our band-truncated IBKR chains under-count GEX for wide-strike names) so the ranking measures our data quality, not the market's — mitigated by computing it from the Polygon full chain only.

## 5. Signed dealer inventory from ΔOI reconciliation — `signed-oi`

- **Inspired by**: Synthetic OI / Options Inventory Model (G6); "signed GEX is the single biggest accuracy upgrade over naive GEX".
- **What it computes**: replaces the assumption "dealers long calls / short puts" with an estimate, using the overnight ΔOI as a hard constraint on our noisy intraday signing.
  1. Per strike/right: `ΔOI = OI(t+1 open) − OI(t open)` from consecutive nightly chains; `V_day` = day volume; intraday signed flow `F = Σ_t impact-sign-weighted Δv` from feature 1.
  2. Split volume into opening vs closing: `open_frac = clamp(|ΔOI| / V_day, 0, 1)`; opened contracts `= open_frac·V_day`, direction from `sign(F)`.
  3. **Reconciliation**: scale the signed intraday flow so `Σ signed_opening_flow = ΔOI` (least-squares projection onto the constraint) — this is the mechanism that turns per-trade guesses into stable inventory.
  4. `customer_inventory(K,right) += signed_opening_flow`; `dealer_inventory = −customer_inventory`. Persist cumulative per strike in `trades.db` table `dealer_inv`.
  5. Re-run `gex_core.build_gex` with `signed_oi` instead of `±OI` ⇒ `net_gex_signed`, `flip_signed`, plus **HVP** (`argmin_K net_gex_signed`) and **LVP** (`argmax_K`).
- **Inputs**: nightly `chain_full_<sym>.json` (P0), `data/history/*/opt_chain_<sym>_HHMM.txt`, feature 1's per-strike signed flow. **MISSING**: OCC opening/closing volume splits (SpotGamma licenses them). Cheapest proxy is exactly the `|ΔOI|/V_day` heuristic above; accept it and measure.
- **Output**: `charts/data/levels_signed_<sym>.json` (same shape as `levels_<sym>.json` + `"hvp"`, `"lvp"`, `"conv_err"`, `"assumption":"reconciled"`), and a diff block `{"flip_naive","flip_signed","delta_pct","regime_flip":bool}`. Surfaces as a second (dashed) flip line on the chart and a `why[]` line when the two disagree.
- **Decision rule**: when `flip_signed` and `flip_naive` disagree by more than `0.3%·S`, **the naive regime label is void** — no regime-conditional trade (no fade above flip, no momentum below) until they reconverge or the signed version is validated as the better predictor. Once validated, `flip_signed`/HVP/LVP replace the naive levels everywhere; **LVP = pin candidate (0DTE buying banned), HVP = acceleration strike (breakout side only)**.
- **Validation**: horse race on `poly_bars`: for each day, does `regime` (naive) or `regime_signed` better predict same-day realized vol and the sign of intraday momentum-vs-reversion? Score with the existing `engine_backtest` harness; **H0**: identical predictive power. Keep the signed version only if it wins on ≥55% of days with a Deflated-Sharpe-clean margin (`stats-trading-risk` skill) — we must not adopt complexity for its own sake.
- **Effort**: **L** — Python `scripts/signed_oi.py` (nightly batch, math-heavy, not a hot path) + `gex_core` accepting a signed-OI vector.
- **Kill risk**: `|ΔOI|/V_day` is hopeless when 0DTE volume dwarfs OI change (exactly our QQQ/SPY case: 238k volume vs 2348 OI at 685C, verified today), so the reconciliation has almost no leverage on the day that matters most.

## 6. Charm clock (EOD drift map) — `charm-clock`

- **Inspired by**: TRACE Charm Pressure heatmap + "spot migrates to the boundary where MM charm changes sign at EOD".
- **What it computes**: the direction and magnitude of the *passive*, time-decay-driven hedge flow between now and the close — i.e. the drift that exists even with zero news. `gex_core.bs_charm` already exists and is used nowhere.
  1. Charm exposure per strike: `CEX(K) = charm(K) · OI(K) · S · T` (one-calendar-day units), calls minus puts per `gflows` convention, dealer sign convention consistent with feature 5 (or naive if 5 fails).
  2. Evaluate on the spot grid `S ∈ [0.97S, 1.03S]` ⇒ `C(S)`. Find `S*` = the sign-change boundary of `C(S)` nearest spot = **the EOD magnet**.
  3. `drift_pressure = C(spot)` normalized by `ADV20 notional` ⇒ dollars of passive dealer buying/selling per remaining fraction of the day; scale by `(minutes_to_close/390)`.
  4. Publish `eod_target = S*`, `drift_dir = sign(S* − spot)`, `charm_conf = |C| density between spot and S*`.
- **Inputs**: `data/opt_chain_<sym>.txt` (0DTE + next expiry is *exactly* what charm needs — our narrow chain is fine here), `gex_core.bs_charm`, `chart_levels.gen()` for spot/EM, `data/bars_<sym>_ibkr.txt`. Floor `T` at 1h and **stop publishing 0DTE charm after 15:00** (formula blows up).
- **Output**: `data/charm_<sym>.json` → `{"sym","ts","eod_target","drift_dir","drift_pressure_pct_adv","charm_conf","minutes_left","valid_until":"15:00"}`. Surfaces as: a dotted target line on `charts/live.html`, a 13:30 voice **SIGNAL** ("charm empuja a QQQ hacia 686 al cierre, presión 0.4% ADV"), and a new page/paragraph in the daily PDF scenario tree.
- **Decision rule**: fires only in the 13:30–15:15 window (respects the "última hora solo gestión" rule): if `drift_dir` agrees with the force phase and `|eod_target − spot| ≥ 0.4·EM_remaining`, take the drift trade toward `eod_target`, exit at the target, never hold past 15:45. If `drift_pressure` is opposite the captain's DNF ⇒ **no trade** (rule 12). Options only if optgate passes (0DTE charm trades are the most spread-sensitive of all).
- **Validation**: from `poly_bars`, for each session compute `|close − eod_target(13:30)|` vs `|close − spot(13:30)|` vs `|close − max_pain|`. **H0**: charm target is no closer than spot-persistence. Keep if median absolute error is ≥15% lower than the spot-persistence baseline with a bootstrap CI excluding 0 (`stats-trading-risk` block bootstrap), n ≥ 120 sessions per symbol class.
- **Effort**: **M** — C++23 `charm_clock.cpp` for the live loop (fleet hot path, reuses the momentum_calc pattern) after a Python prototype validates the math against `gex_core`.
- **Kill risk**: charm at our OI granularity (20 strikes, 2 expiries) is dominated by the ATM strike and the "boundary" is just `spot` rounded to the nearest strike — i.e. the feature secretly reproduces max pain and adds nothing.

## 7. Ten-minute stability gauge — `stability-10`

- **Inspired by**: TRACE Stability Gauge (P[large move in next 10 min], live 09:30–15:30 only).
- **What it computes**: a **measured** probability, not a proprietary score.
  1. Label from history: `y = 1` if `|ret(t → t+10m)| > q80` of that symbol's 10-min absolute-return distribution for that hour bucket.
  2. Features, all already computed by us: local gamma density `Σ|net_gex(K)| for |K−S| ≤ 0.5%·S` normalized by total; `dist_to_flip / EM`; `dist_to_VT / EM`; 0DTE gamma share; `RV_5m / RV_5m_median(hour)`; `%B(20,2)` 1m from `momentum_calc`; `force` and `exhaustion` from `data/force.json`; `|DNF z|`; hour bucket from `timeofday_calib`; regime.
  3. Model: **bucketed empirical lookup first** (gamma-density tercile × dist-to-flip tercile × hour), logistic regression only if the buckets starve. No black box: publish `n` and Wilson CI per cell.
  4. `stability = 100·(1 − p_bigmove)`.
- **Inputs**: `trades.db poly_bars` (493k 1m rows — enough for labels today), `data/history/<date>/levels.json` (exists, currently 1 snapshot/day ⇒ **must be densified to 5 min**; that's a 2-line change in the chart bridge loop and the honest blocker), `data/force.json`, `momentum_calc` output, `data/dnf_<sym>.json`.
- **Output**: `data/stability_<sym>.json` → `{"sym","ts","stability","p_bigmove","p_lo","p_hi","n_cell","cell":"gdens2|flip1|h1030","valid":true}`; greyed/`valid:false` outside 09:30–15:30. Surfaces as a gauge in `charts/live.html`, a stop-width multiplier in `order_ticket.py`, and a **DANGER** voice when stability drops below its 10th percentile intraday.
- **Decision rule**: `stability ≥ 70` ⇒ range/pin/fade trades allowed, tight stops fine, premium-selling structures preferred. `stability ≤ 30` ⇒ **exit range trades, no pin trades, no premium selling, widen stops 1.5×, breakout side only**. Cells with `n < 50` ⇒ output `null` and stay silent (fail loud, never fake a number).
- **Validation**: walk-forward with the `walk-forward-validation` skill: fit buckets on months 1–k, test on k+1; calibration curve (predicted vs realized) must be within ±7 points across deciles, and Brier score must beat the unconditional base rate. **H0**: features carry no information ⇒ flat calibration curve. Also report Deflated Sharpe of the derived trade filter to kill the multiple-testing illusion.
- **Effort**: **M** — Python `scripts/stability10.py` (offline fit) + C++ evaluation of the frozen lookup table inside the existing fleet loop (table = a small JSON, no ML runtime).
- **Kill risk**: we lack the 5-min levels history to build features at label time (only 4 days), so the honest earliest ship date is ~2 months out — and by then the market regime that trained it is gone.

## 8. Fleet implied correlation → makes rule 12 measured — `cor-fleet`

- **Inspired by**: COR1M and its meta-rule ("low implied correlation ⇒ single-stock gamma levels most reliable; high ⇒ index flow overrides names").
- **What it computes**: converts the captain-hierarchy doctrine from a fixed rule into a state variable.
  1. `ρ_imp = (σ_idx² − Σ w_i²σ_i²) / (2 Σ_{i<j} w_i w_j σ_i σ_j)` using `iv_atm` for QQQ and its fleet components, weights from `index_breadth.py`. Same for SMH over the semis tropa.
  2. Realized counterpart `ρ_real` = mean pairwise 1-min return correlation over the last 60 min (rolling, from bars).
  3. `disp_score = ρ_imp − ρ_real` and percentile of `ρ_imp` vs its own trailing 60 days.
  4. Regime label: `MACRO` (ρ high) vs `DISPERSION` (ρ low).
- **Inputs**: `charts/data/levels_<sym>.json` (`iv_atm` per ticker), `scripts/index_breadth.py` weights (currently hardcoded + yfinance daily — acceptable, it's a 4am batch), `data/bars_*_ibkr.txt` for `ρ_real`, `trades.db peer_weights` (already has corr/beta/lead-lag from duckdb — reuse instead of recomputing).
- **Output**: `data/cor_fleet.json` → `{"ts","rho_imp_qqq","rho_imp_smh","rho_real_qqq","rho_pct_60d","regime":"MACRO|MIXED|DISPERSION","captain_weight","name_weight"}`. Surfaces as the *dynamic* weights `captain 1.4 → f(ρ)` and `components 1.3 → g(ρ)` in `direction_view.py`, a `why[]` line, and a banner in the cockpit.
- **Decision rule**: `MACRO` (`ρ_pct_60d > 0.7`) ⇒ **rule 12 at full strength**: name signals are annulled by an opposing captain, only SPY/QQQ/SMH get voice. `DISPERSION` (`< 0.3`) ⇒ single-name gamma levels are the tradable edge, an opposing captain only downgrades DANGER→SIGNAL instead of muting. MIXED ⇒ current behaviour. All still subject to `impact-gate` and the print rule.
- **Validation**: re-grade the 3233 rows in `signals` + 2916 in `backtest_signal_outcomes`, splitting name-level signals by the correlation regime of that day (reconstructible from `poly_bars` realized correlation even without IV history). **H0**: captain-override adds the same value in both regimes. Keep if the name-signal hit rate in DISPERSION exceeds the MACRO one by ≥8 points, Wilson non-overlapping, `n ≥ 100` each.
- **Effort**: **S** — Python `scripts/cor_fleet.py`, ~120 lines, reuses `peer_influence.py` and `index_breadth.py`.
- **Kill risk**: `iv_atm` coverage across the fleet is too thin/stale (verified: many chains have no IV at all) so `ρ_imp` is computed on 6 of 30 names and is really just a VIX proxy — in which case use `ρ_real` only and drop the "implied" claim.

## 9. Measured expected move + wall confluence — `em-measured`

- **Inspired by**: Implied 1-Day/5-Day Move (explicitly *not* an IV formula — a conditional historical quantile) + "confluence when an EM bound lands on a Wall".
- **What it computes**:
  1. `EM_measured(sym, state) = 68.3rd percentile of |1-day return|` conditioned on state = (VIX bucket from `cboe-data` VX front, `net_gex` sign+magnitude tercile, `dist_to_VT` bucket, earnings-day flag from Finviz Elite). Bucketed empirical lookup, computed on `poly_bars` daily aggregation; 5-day version analogous.
  2. Compare with the IV-derived `em` already in `chart_levels.gen()`; publish both and the ratio `em_iv / em_measured` (a cheap VRP read: >1.15 ⇒ options rich, prefer spreads/short premium structures; <0.85 ⇒ options cheap, buying is licensed).
  3. Range = `ref_price ± EM_measured`. **Confluence flag** when `|bound − call_wall| ≤ 0.15%·S` (or put wall) ⇒ the day's most probable turn point.
- **Inputs**: `trades.db poly_bars` (2 years, already local — this feature is testable *today*, no waiting), `charts/data/levels_<sym>.json`, CBOE VX via the `cboe-data` skill, Finviz Elite earnings dates, `data/vt_<sym>.json`.
- **Output**: `data/em_<sym>.json` → `{"sym","date","em_measured_pct","em_iv_pct","vrp_ratio","hi","lo","contain_rate_hist","contain_lo","n","confluence":{"side":"UP","level":690,"gap_pct":0.06}}`. Surfaces as: shaded band on the chart, the range printed on PDF page 1, and the "cobra en el imán" target in `order_ticket.py`.
- **Decision rule**: never target beyond `EM_measured` intraday (the target field in `direction_view` gets clamped). **Confluence + wall + print ⇒ the highest-conviction fade of the day**; no confluence ⇒ wall trades are downgraded to banner. If `vrp_ratio > 1.15`, buying premium is discouraged and the vehicle switches to shares/leveraged ETF (rule 4 + `optgate.py`).
- **Validation**: direct — measure containment of the close inside `ref ± EM_measured` across all fleet-days in `poly_bars`; calibrate the quantile so containment lands at 76% ± 3 out-of-sample (walk-forward, fit on year 1, test on year 2). **H0**: conditioning on GEX/VIX/VT state adds nothing over a plain 20-day ATR quantile — keep only if the conditional version's containment error is materially lower and the confluence subset shows a higher wall-reject rate than the non-confluence subset (Wilson, `n ≥ 60`).
- **Effort**: **S/M** — Python `scripts/em_measured.py`; extends `chart_levels.py` output by two keys.
- **Kill risk**: the conditioning buckets add nothing over ATR (very plausible), leaving a rebranded ATR band — though even then the *confluence* half retains value.

## 10. Vanna ramp / IV-crush forced-buying predictor — `vanna-ramp`

- **Inspired by**: SpotGamma Vanna Model (grey vs purple curves = spot-vol-adjusted dealer delta; the gap *is* the vanna flow) — G12.
- **What it computes**: how many dollars dealers must buy if IV falls, i.e. the melt-up fuel that exists *before* the melt-up.
  1. Fit spot-vol beta per ticker: regress `Δ iv_atm` on `ΔS/S` across our 5-min chain history (`iv_atm` from consecutive snapshots) ⇒ `β_sym` (expect ~4–8 for indices, higher short-dated).
  2. Dealer delta curve on the spot grid twice: `D_sticky(S)` (IV fixed) and `D_dyn(S)` (apply `ΔIV = −β·ΔS/S` to the whole surface, re-solve deltas).
  3. `vanna_gap(S) = D_dyn(S) − D_sticky(S)`; at spot: `gap_now`. `gap_now < 0` ⇒ net dealer **buying** required on any IV decline (bullish fuel); `> 0` ⇒ selling.
  4. **Event overlay**: on the day before a fleet earnings print (Finviz Elite dates), compute `crush_fuel = Σ vanna(K)·(iv_atm − iv_atm_post_median)` where the post-event IV drop is the *measured* median crush for that ticker from `poly_opt_bars` history. That number is the pre-positioned answer to "how far does it run after the print".
- **Inputs**: `charts/data/levels_<sym>.json` (`vex_profile`, `iv_atm` — vanna profile already exists via `gex_core.build_exposure(greek="vanna")`), `data/history/*/opt_chain_*` for the β regression, `trades.db poly_opt_bars` for measured post-earnings IV crush, Finviz Elite earnings calendar.
- **Output**: `data/vanna_<sym>.json` → `{"sym","beta_spotvol","beta_r2","gap_now_usd","gap_pct_adv","direction":"BUY_FUEL|SELL_FUEL","crush_fuel_usd","event_date","n_events"}`. Surfaces as a `why[]` factor (extends the existing `vex` handling), a PDF paragraph on earnings-eve plans, and an 09:45 voice SIGNAL the morning after a print.
- **Decision rule**: post-event, if `direction=BUY_FUEL` and `|gap_pct_adv| ≥ 0.3%` and price holds above the pre-print VT ⇒ **long continuation licensed in the 09:45–10:30 golden window** (not at the open, rule 7). Never used to *predict the print*, only the mechanical unwind after it — and never with bought premium held through the print (existing rule).
- **Validation**: event study on all fleet earnings in `poly_bars` (we have ~2 years × 30 names ≈ 200+ events): forward return day+1 open→close bucketed by `gap_pct_adv` tercile. **H0**: post-print drift independent of vanna gap. Keep if the top tercile's directional hit rate has `p_lo ≥ 0.58` at `n ≥ 60`; that is a genuinely tradable anticipation edge if it survives.
- **Effort**: **M** — Python `scripts/vanna_ramp.py` (extends `gex_core.build_exposure`); no C++ needed, it is a daily/event-driven computation.
- **Kill risk**: `β_spotvol` fitted on 4 days of 5-min IV data with mostly-missing IBKR IV is garbage, so `D_dyn` is fiction — needs the Polygon nightly snapshot history to accumulate first.

## 11. Pin clock (max pain + measured pin probability) — `pin-clock`

- **Inspired by**: Max Pain / pin probability with **measured** time-of-day factors (the `spotgamma-killer` factors are hand-invented; ours will not be) + Absolute Gamma pin.
- **What it computes**:
  1. `pain(K*) = Σ_{K<K*} callOI(K)(K*−K)·100 + Σ_{K>K*} putOI(K)(K−K*)·100`; `max_pain = argmin pain`. No greeks needed — works on NOK/DRAM/SPCX where IV is missing.
  2. `abs_wall` already exists in `chart_levels` (largest total |gamma|).
  3 **Measured** `P(|close − K_pin| ≤ ½ strike-width | hour, regime, |spot−pin|/EM, is_opex)` from `poly_bars` + nightly OI history — replaces the invented 0.30/0.50/0.80/0.95 hour factors.
  4. `pin_zone = [pin − ¼ width, pin + ¼ width]`, `escape_prob = 1 − p_pin`.
- **Inputs**: `charts/data/levels_<sym>.json` (`oi_*`, `abs_wall`), nightly `chain_full_<sym>.json` for full-expiry OI, `trades.db poly_bars`, `scripts/timeofday_calib.py` buckets.
- **Output**: `data/pin_<sym>.json` → `{"sym","max_pain","abs_wall","pin","width","p_pin","p_lo","n","hour_bucket","escape_prob","zone":[lo,hi],"verdict":"PIN_DAY|NEUTRAL|RELEASE"}`. Surfaces as a shaded zone on the chart, a **DANGER-class veto** in `order_ticket.py`, and a PDF scenario branch.
- **Decision rule**: `verdict=PIN_DAY` and spot inside `zone` ⇒ **0DTE bought premium prohibited** (already doctrine — now with a number attached), fade the edges of the zone toward the pin, sell/avoid directional. Escape only on a confirmed break of the zone with `stability-10 ≤ 30` and DNF agreeing. Vehicle check via `optgate.py` (premium ≤$200, spread ≤5%, OI>500).
- **Validation**: on all OPEX and 0DTE-heavy sessions in `poly_bars`, compare `|close − max_pain|` and `|close − abs_wall|` vs `|close − random nearby strike|` and vs `|close − open|`. **H0**: pinning is an illusion (equal distances). Literature (Ni-Pearson-Poteshman) says it should be measurable; keep only the cells where it is, with Wilson CI, `n ≥ 40` per hour bucket.
- **Effort**: **S** — Python `scripts/pin_clock.py`; the cheapest high-value item on this list because it needs no greeks and no new feed.
- **Kill risk**: for single names our OI is too thin for max pain to be stable day to day, so the "pin" jitters between strikes and the veto fires randomly.

## 12. Expiry roll-off clock — `expiry-unwind`

- **Inspired by**: Next Expiry Gamma% / Delta% (>25% = significant), Expiration Concentration (>20–30% rule), the "total minus next expiration" differencing toggle.
- **What it computes**: the regime that will exist *after* Friday, computed before Friday.
  1. Per expiry: `gamma_share_e = Σ|GEX_e| / Σ|GEX|`, `delta_share_e = Σ|DEX_e| / Σ|DEX|` (DEX = `δ·OI·S`, currently missing from our stack — add to `gex_core`).
  2. Flag `NEXT_EXP_HEAVY` when `gamma_share_next > 0.25` or `delta_share_next > 0.25`; note the calls-vs-puts split of the expiring delta.
  3. Recompute the **post-roll profile**: `G_ex_next(S)`, `flip_ex_next`, `call_wall_ex_next`, `put_wall_ex_next`, `vt_ex_next`. Publish the delta between today's levels and post-roll levels.
  4. Directional read: large **put** delta expiring ⇒ dealers cover ⇒ upward pressure post-expiry; large **call** delta expiring ⇒ dealers dump long hedges ⇒ downward pressure.
- **Inputs**: nightly `chain_full_<sym>.json` (**required** — the IBKR cache's 2 expiries cannot compute shares), `gex_core`, `chart_levels.gen(all_exp=True)`.
- **Output**: `data/expiry_<sym>.json` → `{"sym","next_exp","gamma_share","delta_share","expiring_side":"CALLS|PUTS","post_roll":{"flip","vt","call_wall","put_wall"},"level_shift_pct","verdict":"MAGNET_THEN_RELEASE|NEUTRAL"}`. Surfaces as a Thursday-PM/Friday-AM voice SIGNAL, a PDF scenario branch ("post-vencimiento el flip sube a X → el techo se muda"), and pre-loaded order tickets for Monday.
- **Decision rule**: `gamma_share_next > 0.30` ⇒ Friday is a **magnet day**: trade toward the dominant expiring strike, no breakout trades, no 0DTE outside the pin logic. Monday/next session: trade the post-roll levels, not the stale ones, in the direction implied by `expiring_side` — entered with the antelación rule 10 (ticket prepared the night before, bracket server-side).
- **Validation**: for every expiry in the `poly_bars` history, test whether the next session's realized direction agrees with `expiring_side` and whether realized vol rises after high-`gamma_share` expiries. **H0**: no relation. Keep if directional hit rate `p_lo ≥ 0.56` at `n ≥ 50` expiries, recorded per `setup_type='post_expiry_unwind'` in `calibration_ledger`.
- **Effort**: **S/M** — Python `scripts/expiry_unwind.py` (weekly batch, fits the existing 4am cron); adds DEX to `gex_core`.
- **Kill risk**: without OCC-grade OI our expiry shares are noisy, and the effect is already priced into the Monday gap before we can act (the classic post-expiry-drift decay).

## 13. Dark-pool accumulation index from FINRA — `dpi-lite`

- **Inspired by**: DPI / DIX (`DPI>60 ⇒ positive 60-day forward return`, `DPI<30 ⇒ negative`) — SpotGamma's is undisclosed, but the underlying data is public and free.
- **What it computes**: `DIX_sym = off_exchange_short_volume / off_exchange_total_volume` per day from FINRA's daily short-sale volume files (`cdn.finra.org` daily `CNMSshvol*.txt` — free, no auth, years of history, one file per day). Then: 5-day mean, percentile vs trailing 1 year, and a fleet-aggregate weighted by QQQ weights. The mechanic: a market maker absorbing a seller books the fill as a short sale, so a high off-exchange short ratio = institutional accumulation.
- **Inputs**: new fetcher `scripts/finra_shvol.py` → `trades.db` table `finra_shvol(sym, date, short_vol, short_exempt, total_vol, dix)`. Joined to `poly_bars` for forward returns. Nothing missing — this is the only genuinely new *free* feed in this whole list.
- **Output**: `data/dpi.json` → `{"<SYM>":{"dix","dix_5d","pct_1y","tier":"ACCUM|NEUTRAL|DISTRIB","n_days"},"fleet":{"dix_w","pct_1y"}}`. Surfaces as a slow-moving tailwind/headwind flag in the daily PDF and a low-weight (~0.4) `direction_view` factor; **never** a voice alarm (wrong timescale).
- **Decision rule**: it does not generate entries; it **sizes and biases** them. `tier=ACCUM` ⇒ dip-buy setups get full size and short setups get half; `DISTRIB` ⇒ inverse. Explicitly capped so it can never override captain rule 12 or a VT regime.
- **Validation**: this is the most honestly testable item here — we can download years of FINRA history *today* and reproduce (or refute) the published `>60/<30` thresholds on our own 30 tickers with 60-day forward returns. **H0**: no relation between DIX percentile and forward return. Note the prior: the independent Bayesian test of SqueezeMetrics found **DIX effects ≈ zero** while only "low GEX ⇒ bullish" survived. So the expected outcome is a *rejection* — and that is a cheap, valuable rejection that stops us paying attention to dark-pool lore. Keep only if the top-vs-bottom quintile forward-return spread is positive with a bootstrap CI excluding zero after BH-FDR across 30 tickers (`stats-trading-risk`).
- **Effort**: **S** — Python `scripts/finra_shvol.py` + a research notebook. Batch only.
- **Kill risk**: it simply has no edge (most likely outcome per the published replication), or FINRA's off-exchange aggregate is too coarse per-symbol to mean anything.

## 14. Gamma-squeeze candidate scanner — `squeeze-scan`

- **Inspired by**: the Squeeze / Gamma Squeeze scanners + the published amplifying conditions (near-term slightly-OTM call OI, low float, negative net GEX, high options volume vs ADV).
- **What it computes**: a weighted rank composite over the fleet + a Finviz-screened extension universe, refreshed pre-open Monday and daily at 08:30:
  1. `otm_call_gamma_per_float = Σ_{K in (S, 1.07S], DTE ≤ 10} γ(K)·callOI(K)·100 / shares_float`.
  2. `short_pressure = short_float_pct · days_to_cover` (Finviz Elite gives both — we already pay for this).
  3. `opt_vol_ratio = option_volume·100 / ADV20_shares`.
  4. `neg_gex_flag = 1 if net_gex < 0`.
  5. `squeeze_score = z(1)·0.35 + z(2)·0.30 + z(3)·0.20 + neg_gex_flag·0.15`, cross-sectionally z-scored; report the components, never just the score.
- **Inputs**: `chain_full_<sym>.json` (or `data/opt_chain_<sym>.txt` for the fleet), Finviz Elite export via `scripts/finviz_scan.py` / `finviz_scout.cpp` (short float, float, ADV), `charts/data/levels_<sym>.json` (`net_gex`), `data/bars_*_ibkr.txt`.
- **Output**: `data/squeeze_scan.json` → `[{"sym","squeeze_score","otm_call_gamma_float","short_float","days_to_cover","opt_vol_ratio","net_gex","rank","components":{...}}]`. Surfaces as a pre-open email/X-bot section, a PDF page for the top 3, and — only if a name is in the fleet and `impact-gate` is GREEN — a watch level (the lowest strike whose call OI dominates) armed in `price_alarm.cpp`.
- **Decision rule**: a squeeze candidate is **not** an entry. It is a *pre-armed level*: entry only when price prints through the identified near-term OTM call-OI cluster with DNF positive and the captain not opposed; then trade the continuation (band-walk expected, so the Bollinger veto is inverted here — a stretched upper band with 3-TF agreement is confirmation, per rule 1's band-walk clause). Vehicle per `optgate.py`; on illiquid squeeze names options are usually **VETADAS** ⇒ shares.
- **Validation**: build the score historically for the fleet + memory complex (MU/SKHY/DRAM/SNDK/WDC/STX have exactly the profile) using `poly_bars` + archived Finviz snapshots; measure `P(≥5% 3-day up-move | top-decile score)` vs base rate. **H0**: score-independent. Keep at `p_lo ≥ base_rate + 10pts`, `n ≥ 40` candidate-days. Log as `setup_type='gamma_squeeze'` in `calibration_ledger`.
- **Effort**: **S/M** — Python `scripts/squeeze_scan.py`, reuses the Finviz plumbing; extends the existing 4am plan generator.
- **Kill risk**: 4 conditions z-scored on 30 names is a multiple-testing machine that will fit last month's memory rally and nothing else; and archived Finviz short-float history may not exist, making the backtest look-ahead-contaminated.

---

### Deliberately NOT proposed
- **True HIRO / signed OPRA tape / Tape scanners / FlowPatrol** — verified `NOT_AUTHORIZED` on Polygon options trades+quotes; the only live route is IBKR `reqTickByTickData("AllLast")` on individual option contracts (`ibkr_bar_bridge.py:250` already does this for stocks), which is feasible for perhaps ±10 strikes of QQQ/SPY 0DTE inside the market-data-line budget. That is a **P1 spike, not a feature**: prototype on QQQ only, compare against feature 1's cheap proxy, and only then decide whether ThetaData/Polygon Advanced is worth the money.
- **Compass / IV-Rank + Risk-Reversal-Rank grid** — the published backtest is attractive (forward returns highest at RR rank < 0.2) but it needs **a year of 25Δ IV history per ticker** that we do not have. Correct move now is a zero-cost **logger** (append `iv_atm`, 25Δ call/put IV, `skew`, `iv_rank` from the nightly Polygon snapshot into a new `trades.db iv_hist` table); revisit as a feature in 2027.
- Anything cosmetic: Canvas-style workspaces, heatmap eye-candy, TRACE 5-day projections (reconstructible but purely decorative given we trade intraday), Founder's-Note-style prose (our narrator + PDFs already cover it).