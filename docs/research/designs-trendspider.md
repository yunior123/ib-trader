# TrendSpider → ib-trader: 13 buildable features, ranked best-first

Grounding done on the live repo. Verified assets that drive these proposals: `data/history/<date>/opt_chain_<sym>_HHMM.txt` (**5-minute archived chain snapshots, 26 syms, 2131 files on 2026-07-24, with bid/ask/vol/oi/iv/delta/gamma per strike** — this is the single most under-exploited dataset we own), `trades.db poly_bars` (1m, 30d, whole fleet), `data/whale_<sym>.txt` (signed tape prints ≥$50k, **trimmed to 15 min and truncated daily** — no history), `data/bars_<sym>_ibkr.txt` (1m, ~2 days, **rewritten by `warmup_sym`** = a real repaint vector), `nbbo_<sym>.txt` (single-line snapshot; only QQQ has history: `nbbo_hist_qqq_*.txt`), `trades.db signals` (3233 rows since 07-15, 7 sources), `backtest_signal_outcomes` (2916 rows). **5s bars are never persisted** (in-memory in `ibkr_bar_bridge.py`) — so nothing below assumes sub-minute data.

---

## 1. GEX Center-of-Mass Drift + Wall Turnover Velocity — `gex-drift`

**Inspired by**: Options Map (strike×expiry grid, *OI Change* metric, normalization "By Expiration") + their explicit non-feature: TrendSpider stops at the static greek×OI surface. We already own the surface; nobody owns its **time derivative**.

**What it computes** (per sym, every 5 min, and replayable over the archive):
1. For each archived snapshot at time *t*, run the existing `gex_core.from_ibkr_cache(path, spot, scale="dollar1pct")` → `profile{strike: gex}`, `flip`, `net_gex`.
2. Gamma center of mass: `CoM_t = Σ_K K·|GEX_t(K)| / Σ_K |GEX_t(K)|`. Signed variant `CoM⁺` over positive-gex strikes only (dealer-long = pinning mass).
3. Drift: `dCoM = (CoM_t − CoM_{t−3}) / ATR14_1m` (3 snapshots = 15 min), and `dFlip = (flip_t − flip_{t−3}) / ATR14`.
4. Wall turnover per strike (the intraday-live quantity; **OI from IBKR `reqTickers` is stale intraday, volume is not** — honesty point): `turn_t(K) = vol_t(K) / max(oi_t(K),1)`, and `dturn = turn_t − turn_{t−3}`. Wall being **eaten** = `turn > 1.25` and rising with price pressing it; wall being **built** = turnover flat, `|GEX(K)|` share of book rising.
5. Book concentration `HHI_t = Σ (|GEX(K)|/Σ|GEX|)²` — collapsing HHI = wall dissolving = breakout regime.
6. Emit `drift_dir` = sign(dCoM) with magnitude in ATR, plus `wall_state ∈ {BUILDING, HOLDING, EATEN, DISSOLVING}` per near wall.

**Inputs**: `data/history/<date>/opt_chain_<sym>_HHMM.txt` (backtest + intraday), live `data/opt_chain_<sym>.txt`, `scripts/gex_core.py`, `scripts/chart_levels.py gen()`, `trades.db poly_bars` for forward returns, `data/gexa_snapshot.json` for regime cross-check. Nothing missing. Caveat: `data/history/gexa_hist.jsonl` is mostly nulls — do not depend on it.

**Output**: `data/gex_drift.json` → `{"MU":{"com":934.8,"com_prev":931.2,"dcom_atr":0.42,"dflip_atr":0.31,"hhi":0.081,"hhi_slope":-0.004,"walls":[{"strike":935,"side":"C","turn":1.61,"dturn":0.44,"state":"EATEN","dist_atr":0.2}],"drift_dir":"UP","prob":null,"n":0,"ts":...}}`. Surfaces as a `direction_view.why[]` factor (new weight ~1.2, same tier as `captain_flow`), a chart overlay line for CoM (a moving magnet, not a static wall), and a SIGNAL voice only when `|dcom_atr| ≥ 0.4` and wall_state flips to EATEN.

**Decision rule**: trade *toward* CoM drift when `dCoM` and `dFlip` agree in sign and the near wall in that direction is `EATEN` or `DISSOLVING`; **no-trade / fade** if the wall between spot and CoM is `BUILDING` (this is memory `oi-magnets-protocol` "never buy through a wall", finally measured instead of counted by touches). Must still pass: print-2-readings on the level, `optgate.py` spread ≤5% / OI>500 / premium ≤$200, captain hierarchy (rule 12) — a name's drift is voided when SPY/QQQ or SMH drift opposes it, and the Bollinger 1m+15m %B check.

**Validation**: replay every archived snapshot (26 syms × ~80/day, growing ~2000 rows/session) → label with `poly_bars` forward 15m/30m/60m. Null hypothesis: forward return sign is independent of `sign(dCoM)` within the same gamma-regime bucket (use the regime's unconditional up-rate as baseline, not 50%). Non-overlapping sampling (one observation per 30 min per sym) + stationary bootstrap for CI. Register in `calibration_ledger.py` as `setup_type = "gexdrift_<state>" × regime`. Keep only buckets with `n ≥ 120` and Wilson lower bound ≥ baseline + 5pp. Today's archive is only 4 sessions — declare DATA-INSUFFICIENT until ~30 sessions.

**Effort**: M. Python for the replay/calibration (`scripts/gex_drift.py`, extends `gex_core`), then the live 5-min loop in C++ inside the existing `flow_pulse.cpp` cadence if latency matters. New file + `direction_view.py` factor.

**Kill risk**: IBKR intraday OI is snapshot-stale and volume-per-strike resets/lags, so `dCoM` may be dominated by spot moving under a static book (i.e. it's just price, re-labelled). Mitigation is mandatory: compute CoM at a **frozen spot** (`gen(sym, spot=spot_at_t0)`) as a control series and require the drift to survive after removing the spot-induced component.

---

## 2. Typed Level Events with ATR buffer + round-number flag — `level-events`

**Inspired by**: Dynamic Price Alerts (Touch / Bounce / BreakThrough with `Sensitivity` buffer and a mandatory candle close) + Osler (2000): published levels bounce 60.8% vs 56.2% random, and ~3.4pp of that 4.6pp is *round numbers*.

**What it computes**: one unified event stream over every level our stack already produces.
1. Level registry per sym: `OI_CALL_WALL, OI_PUT_WALL, ABS_WALL, FLIP, POC_DOM, NEAR_*` (from `chart_levels.gen()`), `KDE` (feature 8 output), `TRENDLINE` (feature 8), `AVWAP_*` (feature 9), `GAP_EDGE` (feature 12), `PREV_DAY_H/L`, `ON_H/L`, and a synthetic `ROUND` level set (nearest 0/5/00 increment).
2. Buffer `s = max(0.15×ATR14(1m), half_spread_from_nbbo, 1 tick)`.
3. On each **closed** 1m bar (bar-close hysteresis = our "print o nada", 2 readings):
 - `TOUCH`: `low ≤ L+s ∧ high ≥ L−s ∧ close on the original side`
 - `BREAK`: `open` and `close` on opposite sides of the band `[L−s, L+s]`
 - `BOUNCE`: `TOUCH` at *t* and no `BREAK` at *t+1*
 - `RETEST_REJECT`: `BREAK` at *t*, `TOUCH` from the far side within 5 bars, no re-break → the doctrine's inverted level.
4. Every event carries: level_type, is_round, dist_atr at event, regime, hour bucket, approach velocity (bars since last 0.5 ATR), touch ordinal (1st/2nd/3rd+ of the day for the decay rule).

**Inputs**: `data/bars_<sym>_ibkr.txt`, `data/nbbo_<sym>.txt`, `chart_levels.gen()`, `data/force.json`, `data/gexa_snapshot.json`. Backtest substrate: `trades.db poly_bars` + archived `data/history/<date>/opt_chain_*` to reconstruct the level set *as it was*. Nothing missing.

**Output**: new `trades.db level_events(ts, sym, level_type, level_px, event, is_round, touch_ord, dist_atr, regime, hour, bar_close)` + `data/level_events.json` (last 200 per sym) for the cockpit overlay (`charts/live.html` markers). Voice: SIGNAL on `BOUNCE`/`RETEST_REJECT` of a level whose calibrated bucket has Wilson-low ≥ threshold; INFO banner otherwise.

**Decision rule**: enter only on `BOUNCE` or `RETEST_REJECT`, never on `TOUCH` (consolidation) and never on a first `BREAK` without retest. Direction must agree with rule 12 captain, and the Bollinger check vetoes an elastic-band entry. Touch ordinal ≥3 downgrades bounce probability to its measured 3rd-touch bucket.

**Validation**: this *is* the calibration substrate. For each `(level_type × event × regime × hour × is_round)` cell, measure the barrier-label outcome (feature 3) and store in `calibration_ledger.py`. Null = the same event on a **random level** placed uniformly in the day's range with the same buffer (build 1000 synthetic level sets). Keep a cell only if Wilson-low beats the random-level rate by ≥4pp with n≥80; the honest expectation is 60% vs 56%, so any cell claiming 75% with n=20 gets thrown out.

**Effort**: M. C++ (`level_events.cpp`, new, fleet hot path, links `fleet_notify.h`) + Python replayer for calibration. Retires ad-hoc level logic scattered across the 24 `*_signal_bot.cpp`.

**Kill risk**: level count explodes (7 sources × 30 syms) → alarm spam and multiple-testing illusion; must be controlled by `signal_enable.json`-style dead-cell shutdown plus Bonferroni/BH-FDR over cells (we have the `stats-trading-risk` skill for that).

---

## 3. Triple-barrier labelling + purged walk-forward — `barrier-labels`

**Inspired by**: ML Quant Lab's label definition — binary "does price hit TP before SL within X candles", with `Conservative` (SL never touched) vs `Aggressive` modes — which is a *better* label than what we use, plus their documented methodological hole (no purged CV) which we should not copy.

**What it computes**: replaces/augments `backtest_signal_outcomes`' `(horizon, ret, win)` with path-dependent labels.
1. For each signal in `trades.db signals` (or each `level_events` row), set `TP = entry ± k_tp×ATR14`, `SL = entry ∓ k_sl×ATR14`, `H` bars, sweeping `k ∈ {0.5,0.75,1.0,1.5}`, `H ∈ {10,30,60,120}` minutes.
2. Walk the 1m path from *t+1*: label `1` if TP touched first (conservative: and SL never touched), `0` if SL first, `−1`/NaN if neither (time-out) — timeouts are **not** wins, a real bug class in horizon-return labelling.
3. Also record `MFE` (max favourable excursion, ATR units), `MAE`, `t_first_touch` — MFE/MAE distributions directly parameterise brackets and feed `momentum_decay.py`'s "when to cash at the magnet".
4. Walk-forward with **purging + embargo**: any training observation whose `[t, t+H]` overlaps the test window is dropped; embargo = H bars after the test block. Feed `scripts/fleet_wfo.py`.

**Inputs**: `trades.db signals`, `poly_bars` (1m, 30d), `data/hist/bars_*_1m_30d.txt`, `data/backtest/bars3mo5m_<sym>.csv` for longer-horizon variants. Missing: intrabar path finer than 1m → a 1m bar that touches both TP and SL is ambiguous; resolve conservatively (assume SL first) and count how often it happens (report it).

**Output**: new `trades.db barrier_outcomes(signal_id, sym, source, k_tp, k_sl, H, label, mode, mfe, mae, t_touch)`; aggregated into `data/calibration.json` via `calibration_ledger.py`; surfaces as the *number* on every arrow (`prob`) and as the bracket numbers in the daily PDF ("stop 0.75 ATR, target 1.0 ATR, measured p=0.58 [0.52–0.64]").

**Decision rule**: no signal is voiced with a probability unless it has a barrier-labelled bucket with n≥50; the chosen `(k_tp,k_sl,H)` per source is the one maximising Wilson-low of expectancy, not win rate — and if the best cell's expectancy CI includes 0, the source is NO-TRADE.

**Validation**: it *is* the validator. Cross-check: recompute existing `backtest_signal_outcomes` win rates under barrier labels and report the delta — expect current WRs to be optimistic (horizon returns ignore the stop being hit en route). That delta is the deliverable.

**Effort**: S/M, Python (`scripts/barrier_labels.py`, new; extends `calibration_ledger.py`, `eod_backtest.py`, `fleet_wfo.py`).

**Kill risk**: the ambiguous-bar problem plus only ~30 days of 1m history for the fleet → many cells stay DATA-INSUFFICIENT and the honest answer is "we don't know yet", which is politically unsatisfying but correct.

---

## 4. Volume-weighted OHLC series (Raindrop math, no raindrop chart) — `vw-drops`

**Inspired by**: Raindrop construction (§2.3) — but specifically the *plumbing* insight, not the chart: on a raindrop, `open ≡ leftVWAP`, `close ≡ rightVWAP`, `oc2 ≡ (L+R)/2`, so **every** indicator becomes volume-weighted for free. Their own white paper reports raindrop *patterns* lost money (−0.16% over 66 trades) — so we steal the series, not the patterns.

**What it computes** (P = 10m or 15m, halves built from stored 1m bars — 5–7 sub-bars per half, honest and sufficient; ticks are not available):
1. Sub-bar typical price `p_i = (h+l+c)/3`, weight `v_i`.
2. `leftVWAP = Σp·v / Σv` over first half; `rightVWAP` over second half; `high/low` = period extremes; `mass = Σp·v/Σv` over the whole period.
3. Volume-at-price ladder per half using 1m sub-bars distributed over `[l_i,h_i]` (uniform split — declare the approximation) → enables the Balloon test: both VWAPs `> low + 0.60·(high−low)` **and** ≥80% of period volume above 0.60 of body.
4. **The anticipation part (ours, not theirs)**: the right half updates every minute, so `migration_t = (rightVWAP_partial − leftVWAP) / (high−low)` is readable at minute 6 of a 10-minute period — a *half-bar-early* sentiment shift. Flip threshold 0.50, double-flip 0.33 exactly as published, but used as a **feature with measured follow-through**, never as a trigger.
5. Feed `oc2` as an alternate input series to BB(20,2)/%B, EMA momentum and RSI, producing a second, volume-weighted opinion.

**Inputs**: `data/bars_<sym>_ibkr.txt` (live), `trades.db poly_bars` (backtest). Missing: tick/5s data → periods <10m are forbidden; volumeless symbols are irrelevant (we trade ETFs/equities, all have volume).

**Output**: `data/vwdrops_<sym>.json` → `{"P":600,"drops":[{"t":...,"lv":934.1,"rv":935.9,"h":936.4,"l":933.2,"mass":935.0,"color":"GREEN","flip":0.62,"balloon":false,"migration_live":0.41,"minutes_in":6}],"pctB_vw":0.81}`; a second %B/force pair in `data/force.json` (`force_vw`); a `why[]` line "%B volume-weighted 0.81 vs price 0.66 → la fuerza está en el volumen"; chart overlay = left/right VWAP dashes.

**Decision rule**: when price-%B and VW-%B **disagree**, the volume-weighted one wins for continuation judgements (band-walk vs elastic rebound, doctrine rule 1) — but only if the disagreement bucket is measured. `migration_live ≥ 0.5` at ≥60% of the period elapsed = arm the alarm early; still requires the printed level (rule 2) and captain agreement.

**Validation**: over `poly_bars` 30d × 30 syms, compare calibration of "%B extreme → mean reversion" and "band-walk → continuation" using price series vs VW series, with barrier labels (feature 3). Null: VW series has identical hit rate to price series. Keep VW only if it wins by ≥3pp with non-overlapping n≥300, or if it strictly reduces false positives at equal recall. Separately, **replicate their negative result** on flips as a sanity check on our pipeline.

**Effort**: M. C++ for the live series inside `momentum_calc.cpp` (fleet hot path, adds `oc2` source switch); Python `scripts/vwdrops.py` for the backtest.

**Kill risk**: with only ~5 one-minute sub-bars per half, left/right VWAP ≈ half-period mean price, so the "volume weighting" adds almost nothing beyond a smoothed midpoint — the effect measured on real ticks (288.01 vs 287.57) may vanish at 1m granularity.

---

## 5. Signed whale-tape volume-at-price + absorption — `tape-absorb`

**Inspired by**: Volume-by-Price `ΔVolume` / Pyramid mode (bull volume left, bear right) + Unusual Options' `at_bid`/`at_ask` signed classification and `oiPercent = size/oi` unusualness ratio — applied to the **equity tape**, which we already capture and currently only consume as a scalar score inside the signal bots.

**What it computes** (rolling 15 min, per sym):
1. Read signed prints `EPOCH PX USD DIR` (DIR: +1 at/above ask, −1 at/below bid, 0 mid).
2. Bucket price into cells of `0.15×ATR14`; per cell `pos(b)=Σusd[d=+1]`, `neg(b)=Σusd[d=−1]`, `tot(b)`.
3. `tape_poc = argmax_b tot(b)`; `imbalance = (Σpos − Σneg)/Σ|usd|`, z-scored against the session's own distribution.
4. **Absorption** (the anticipation metric): `ABS(b) = neg(b) / (|Δprice_since_first_print_in_b| / ATR + 0.1)` — heavy at-bid selling that fails to move price down = supply being absorbed → up-break pending; symmetric `ABS⁺` for at-ask buying that fails to lift = distribution → down-break pending. This is the tape-level version of the espada-ballena logic (rule 11) but for the *underlying*, and it fires **before** the level breaks.
5. Cross-check with `opt_whale_watch.py`: agreement (tape absorption up + whale PUTS flow = floor) is the high-conviction cell.

**Inputs**: `data/whale_<sym>.txt`, `data/nbbo_<sym>.txt`, `data/bars_<sym>_ibkr.txt`. **MISSING**: (a) the tape is filtered at `WHALE_MIN_USD=50000` so it is a whale-only profile, not a true VbP — fine, arguably better, but must be named honestly; (b) it is **trimmed to the last 15 minutes and truncated daily** → *no history for backtesting*. Cheapest fix (a few lines in `ibkr_bar_bridge.py`): append every trimmed line to `trades.db equity_prints(ts, sym, px, usd, dir)` before truncation — ~1–3 MB/day. Interim proxy for validation: Lee-Ready sign on 1m `poly_bars` (close vs prior bar midpoint × volume) — declare it as a weak proxy.

**Output**: `data/tape_profile.json` → `{"MU":{"poc":934.6,"imbalance":-0.22,"imb_z":-1.8,"cells":[{"px":934.5,"pos":1.2e6,"neg":3.4e6,"abs":18.4}],"verdict":"ABSORCION_COMPRA","conf":null,"ts":...}}`. Surfaces as a cockpit horizontal histogram (mirrors `vex_profile` rendering), a `why[]` factor, and a SIGNAL voice when `ABS` z ≥ 2 **and** a `level-events` TOUCH is active at the same cell.

**Decision rule**: absorption at a printed level + captain not opposing = take the reversion scalp with tight stop (espada-ballena sizing: small, safe, take the small profit). Absorption **against** the captain (rule 12) = banner only, no voice. Options gate as always (≤$200, spread ≤5%, OI>500).

**Validation**: once `equity_prints` has ~20 sessions: label absorption events with barrier labels (0.75 ATR TP / 0.75 ATR SL, H=30m). Null = same event definition on shuffled print signs (destroys side information, preserves volume/price path) — 1000 shuffles, bootstrap CI. Keep if Wilson-low ≥ null mean + 5pp, n≥100.

**Effort**: S for the archiver, M for the engine. C++ (`tape_profile.cpp`, new; the signal bots already parse this file so the reader exists).

**Kill risk**: the $50k filter plus IBKR's SIP tick-by-tick side assignment (px vs our locally-cached bid/ask, prone to staleness) makes `dir` noisy enough that absorption is indistinguishable from mid-print clustering.

---

## 6. Truth-in-Analysis lock + repaint / data-adjustment detector — `truth-lock`

**Inspired by**: the Truth-in-Analysis timestamp (freeze the analysis so it cannot silently repaint) + Strategy Bots' "internal consistency check on every evaluation → auto-stop on signal movement or historical data adjustment".

**What it computes**: we have a *concrete* repaint vector — `warmup_sym()` in `ibkr_bar_bridge.py` truncates and rewrites two days of 1m bars, and the daily-plan/calibration jobs read that file after the fact.
1. Every signal emission writes a frozen context blob: spot, NBBO, the level set from `chart_levels.gen()`, `force.json`, regime, plus `bars_sha` = SHA-1 of the last 120 closed bars (`epoch|o|h|l|c|v`).
2. A watchdog (30s) recomputes `bars_sha` over the *same* epoch window; any change to an already-closed bar = **data adjustment**.
3. On detection: DANGER voice ("datos reescritos, análisis congelado inválido"), ntfy push, mark affected `signals` rows `data_adjusted=1` so `calibration_ledger.py` **excludes** them, and disarm any armed `order_engine` ticket for that sym (double-key must be re-armed manually).
4. Every artefact (PDF page, chart overlay, arrow) carries `lock_ts` = the instant its inputs were frozen, and the cockpit draws the vertical "truth line".

**Inputs**: `data/bars_<sym>_ibkr.txt`, `trades.db signals`, `data/force.json`, `chart_levels.gen()`, `order_engine` arm state, `data/history/<date>/` archives.

**Output**: new `trades.db signal_context(signal_id, lock_ts, bars_sha, spot, nbbo_bid, nbbo_ask, levels_json, regime, force_json)` + `data/truth_lock.json` `{"MU":{"lock_ts":...,"bars_sha":"ab12…","adjusted":false,"last_check":...}}`. Surfaces as DANGER voice + a red/blue lock indicator in `charts/live.html`.

**Decision rule**: `adjusted=true` for a sym ⇒ **NO-TRADE on that sym until re-locked** (no-trade is a position, rule 6). Any backtest run that includes data-adjusted windows must print the count and exclude them.

**Validation**: not a probability feature — validate by *injection*: rewrite a historical bar in a copy of the file and assert detection within one watchdog cycle; then measure the real-world incidence over 30 sessions (how many signals were computed on data that later changed). If incidence is 0 after a month, downgrade to a cheap assertion. The by-product — knowing what fraction of our measured win rate was computed on rewritten data — is worth the build on its own.

**Effort**: S. Python watchdog (`scripts/truth_lock.py`, new) + 5-line hooks in `speak.sh`/signal emitters and `calibration_ledger.py`.

**Kill risk**: benign rewrites are frequent (IBKR SIP backfill corrections at warmup), producing DANGER fatigue → must distinguish "bar values changed materially (>1 tick or >1% volume)" from cosmetic re-ordering, else it gets muted and becomes decoration.

---

## 7. Random-control null harness for every alarm source — `null-control`

**Inspired by**: Price Behavior Explorer's **Random Control (Mean)** — the average outcome of randomly-timed positions on the same sample; a strategy whose mean doesn't beat it is timing-free.

**What it computes**: for each of the 7 sources in `trades.db signals` (`signal, bollinger, cusum, whale, flow, structural, dip`) and each new feature above:
1. Take the source's realised entries (n, per sym, per hour bucket).
2. Generate N=2000 **time-matched, exposure-matched** synthetic entries: same sym, same hour-of-day distribution, same holding-period distribution, drawn from days in the same regime bucket.
3. Barrier-label both (feature 3) → `edge = p_signal − p_random`, with a stationary-bootstrap CI on the difference (not on the level).
4. Multiple-testing correction across sources × syms × buckets (BH-FDR), then Deflated Sharpe / PSR on the equity curve of each source (`stats-trading-risk` skill), plus Minimum Track Record Length: "this source needs N more trades before its Sharpe is believable".
5. Publish a monthly scoreboard and auto-write `data/signal_enable.json` (the mechanism already exists in `timeofday_calib.py`) to switch off sources whose edge CI includes 0.

**Inputs**: `trades.db signals`, `backtest_signal_outcomes`, new `barrier_outcomes`, `poly_bars`, `data/timeofday_factors.json`, `data/calibration.json`.

**Output**: `data/null_control.json` → `{"bollinger":{"n":1154,"p":0.54,"p_rand":0.512,"edge":0.028,"ci":[-0.004,0.061],"fdr_q":0.18,"dsr":0.31,"mtrl_trades":420,"verdict":"UNPROVEN"}}` + `docs/EDGE-SCOREBOARD-<date>.md` and a line in the daily email.

**Decision rule**: `verdict=UNPROVEN` ⇒ the source may print banners but **never voices SIGNAL and never sizes a trade**. `verdict=DEAD` (edge CI entirely ≤0) ⇒ disabled in `signal_enable.json`. This is the enforcement arm of "probabilidades reales aunque sean 44%".

**Validation**: self-validating; sanity check by feeding it a deliberately random source (coin-flip alarm) and confirming it returns edge≈0 with a tight CI.

**Effort**: S/M, Python (`scripts/null_control.py`, new; extends `conditioned_backtest.py`, `timeofday_calib.py`).

**Kill risk**: it will probably declare several beloved alarms UNPROVEN with 4 weeks of data, and the temptation will be to loosen the test rather than accept the verdict.

---

## 8. ATR-normalised auto-trendline engine + KDE level heatmap (islands-aware) — `trendline-engine`

**Inspired by**: Automated Trendline Detection + the published scoring variable set + Horizontal S/R heatmap (KDE, bandwidth 3×ATR, recency-weighted) + island (gap) segmentation.

**What it computes**:
1. Pivots = Williams fractals: `fractal_high(high, w)`, `fractal_low(low, w)` with `w` per TF `{1m:21, 5m:15, 15m:11}` (odd; monotone in TF as documented).
2. **Islands**: split the series wherever `|open_t − close_{t−1}| > 3×ATR14`; never pair pivots across a gap.
3. Enumerate same-type pivot pairs within an island with minimum separation = base points; line `L(i)=m·i+b` extrapolated to now; discard if `|L(now) − last_close| > 2.5×ATR14`.
4. Score with the published variables: `score = ((hits + (bounceUp+bounceDown) + 2·(peaksUp+peaksDown)) / (1+violations)) · (length/seriesLength)^0.5 / (1+priceDev50)`, where a "peak" touch requires a long bar (`range > 1.5×ATR14`) and `priceDev50` = median % deviation between line and `(H+L)/2`. Keep top 1%, hard cap 200 lines per sym.
5. Independently: KDE horizontal levels — `gaussian_kde(log(close), bw = 3.0×ATR_log, weights = recency ramp)` over 365 bars, sample 200 points, peaks by prominence ≥0.15·max → level prices `exp(x)`.
6. Confluence cell score = w1·(trendline projections in cell) + w2·(KDE density) + w3·(|GEX(K)| at that strike) + w4·(tape POC) + w5·is_round, cell height 0.25×ATR. Weights **fitted**, not guessed, against measured bounce rates.

**Inputs**: `data/bars_<sym>_ibkr.txt` (1m/5m/15m aggregations), `poly_bars` (backtest), `chart_levels.gen()` for the GEX term, `data/tape_profile.json`. Nothing missing — this is the cheapest feature data-wise.

**Output**: `data/levels_auto_<sym>.json` → `{"tf":"5m","lock_ts":...,"lines":[{"m":0.012,"b":930.1,"px_now":935.4,"score":3.81,"hits":6,"viol":1,"island":2,"kind":"support"}],"kde":[933.8,936.2,941.0],"confluence":[{"px":936.2,"score":0.87,"parts":{"tl":3,"kde":0.9,"gex":0.42,"round":0}}]}`. Feeds the `level-events` registry (feature 2), the cockpit overlay (solid = primary TF, dashed = HTF), and the daily PDF walls page as a second opinion on OI walls.

**Decision rule**: a trendline/KDE level is tradable only as a `BOUNCE`/`RETEST_REJECT` event (feature 2), never as a raw break; confluence score ≥ measured threshold upgrades the bucket. Breakout requires a **full 1m close** beyond the line (no wick breaks). Priority still yields to OI walls and the captain when they conflict.

**Validation**: the Osler benchmark is the honest prior — measure bounce rate at engine levels vs 1000 random levels per session; keep only if the edge is in the +4 to +5pp range with Wilson-low above the random rate, per `(tf × regime)` bucket. Also sweep `w ∈ {5,10,20}` and assert monotone decrease in line count (spec compliance test) and no line spanning a >3×ATR gap (unit test).

**Effort**: M/L. C++ (`trendline_engine.cpp`, new — O(pivots²) per sym × 3 TFs × 30 syms is the reason it can't be Python on an 8GB Mac); Python replicate for the backtest only. Registers into `chart_levels.py` output.

**Kill risk**: trendline levels are ~90% redundant with what OI walls + POC + prior-day H/L already give us, so the confluence weights collapse onto the terms we already have and the whole engine adds compute without adding information.

---

## 9. Event-anchored VWAP library with look-ahead guard — `avwap-anchors`

**Inspired by**: Anchored Indicators 101 — the anchor *taxonomy* (highest-volume candle, gap, blue-doji, HH/LL with a symmetric dominance window), `Continuous` mode required for honest backtests, and the explicit ban on continuous mode for forward-looking anchors. Plus the VbP-Ribbon band (bandwidth ∝ volume traded at that price) that nobody replicates.

**What it computes**:
1. Anchor detectors (per sym, per session): session open; **highest-volume 1m bar** (dominance window ±w/2); overnight gap open; **whale-print cluster** (≥$1M signed USD within 3 min from `whale_<sym>.txt`); **flip cross** (bar where price crossed `chart_levels.flip`); **captain-flow event** (timestamp of the last SPY/QQQ/SMH flow spike from `flow_pulse`); blue-doji raindrop (feature 4).
2. `AVWAP_t = Σ p·v / Σ v` from anchor→t (p = hlc3), reset at each anchor in continuous mode; forward-looking anchors (highest-volume, HH/LL) are **only** allowed non-continuously in live use and are excluded from backtests unless the dominance window is fully in the past — the guard is a hard assert, not a comment.
3. Bands: σ-bands and the VbP ribbon `width(p) ∝ volumeAtPrice(p)` from the anchored profile.
4. Features: `dist_atr` to each AVWAP, and the interpretation that matters — **"the whales from the 11:43 print are underwater by 0.6 ATR"** = fuel for capitulation/defence.

**Inputs**: `data/bars_<sym>_ibkr.txt`, `data/whale_<sym>.txt` (+ the new `equity_prints` archive for history), `chart_levels.gen()` (flip), `data/flow_pulse_probs.json`/`flow_pulse` output, `poly_bars` for backtest. Missing: whale history (same fix as feature 5).

**Output**: `data/avwap_<sym>.json` → `{"anchors":[{"kind":"WHALE_CLUSTER","t":...,"px":934.2,"avwap":934.9,"dist_atr":-0.6,"vol_share":0.18,"band_hi":936.1,"band_lo":933.7}],"nearest":{"kind":"GAP_OPEN","dist_atr":0.12}}`. Registers each AVWAP as a level in feature 2; cockpit overlay; `why[]` line.

**Decision rule**: price reclaiming a whale-anchored AVWAP from below (as a `BREAK` with 1m close) = the big buyers are back in profit → continuation long; price losing the gap-anchored AVWAP = gap-fill target opens (feature 12). Requires captain agreement and the standard options gates.

**Validation**: per anchor kind, barrier-label the `BOUNCE`/`BREAK` events. Null = AVWAP anchored at a **random bar** of the same session (same cumulative-VWAP machinery, no event) — this isolates the *anchor choice*, which is the actual claim. Keep anchor kinds whose edge over random-anchor is ≥3pp with n≥100.

**Effort**: S/M. C++ in `momentum_calc.cpp` (it already computes VWAP z-score) + Python anchor detector for backtest.

**Kill risk**: on 1m data within a single session, all anchors converge to session VWAP ± noise, so the "anchor library" collapses to one line and the taxonomy is cosmetic.

---

## 10. Composite ratio tape (captain-vs-troop, numerically) — `ratio-tape`

**Inspired by**: Composite Symbols (`=SMH/SPY`) with their documented OHLC re-derivation rule (High = max over the derived O/H/L/C, because ratios invert extremes) + Relative Strength.

**What it computes**:
1. Build synthetic series for a fixed pair list: `MU/SMH`, `SKHY/MU`, `NVDA/SMH`, `SMH/SPY`, `QQQ/SPY`, `EWY/SMH`, `GLD/SPY`, `SNDK/WDC`, plus the top-3 pairs per target from `trades.db peer_weights`.
2 Per 1m bar: `O = O_a/O_b`, `C = C_a/C_b`, then `H = max(O,H_a/H_b,L_a/L_b,C)`, `L = min(same)` — the documented re-derivation, which naive `H_a/H_b` gets wrong. No volume.
3. Run the existing stack on the ratio: BB(20,2) %B, EMA momentum, Kaufman efficiency, fractal pivots + trendline break (feature 8).
4. **The anticipation claim**: a ratio break precedes the absolute break by roughly `peer_weights.lead_min`; a troop name whose ratio-vs-captain breaks *up* while the captain is flat is the day's leader before the tape says so — and a troop whose ratio breaks up while the captain's absolute breaks down is exactly the rule-12 conflict, now with a number instead of a judgement call.

**Inputs**: `data/bars_<sym>_ibkr.txt` (all fleet, same epoch grid — must inner-join on epoch and drop unmatched minutes, declaring the drop rate), `trades.db peer_weights`, `poly_bars` for backtest, `signal_conditioning.py governing_captain()`.

**Output**: `data/ratio_tape.json` → `{"MU/SMH":{"c":0.412,"pctB":0.93,"pivot_break":"UP","z":2.1,"lead_min":7,"verdict":"MU LIDERA SEMIS","captain_state":"SMH_FLAT"}}`. Surfaces as a `why[]` factor inside `direction_view` (raises/lowers `fleet captain` 1.4 and `components` 1.3 terms), a banner ("líder del día"), and the daily PDF leadership page.

**Decision rule**: prefer the ticker whose ratio-vs-captain is breaking in the trade direction — this is the tie-breaker for **UNA TESIS = UN BOLETO** (of NVDA/QQQ/SOXS, the ratio-leader with the tightest spread gets the ticket). Ratio break *against* the captain = no-trade on the name (rule 12), not a contrarian entry.

**Validation**: over 30d `poly_bars`, test whether ratio %B/pivot-break at time *t* predicts the *name's* barrier-labelled outcome better than the name's own %B, and whether the lead time matches `peer_weights.lead_min`. Null: ratio adds nothing beyond the name's own momentum (compare nested calibration cells). Keep pairs individually; kill pairs whose CI includes 0 (expect most pairs to die; 2–3 survivors is a win).

**Effort**: S/M, Python first (`scripts/ratio_tape.py`, extends `peer_influence.py`), C++ only if it enters a hot path.

**Kill risk**: ratio breaks are dominated by the denominator's noise on 1m bars (two independent quote processes), producing whipsaw signals that lead nothing.

---

## 11. Expansion clock: seasonality of volatility, not of returns — `expansion-clock`

**Inspired by**: `request.seasonality(..., dataPoint ∈ {rvol, rsi, mfi, ma20})` — seasonality **of indicators**, which is far more actionable than seasonality of returns, plus the `time_of_day` granularity.

**What it computes** (distinct from `timeofday_calib.py`, which measures *signal-source win rate* by hour; this measures the *instrument's* volatility clock):
1. Over 30d of 1m `poly_bars`, bucket by minute-of-day (390 buckets, or 78 five-minute buckets for stability).
2. Per bucket, per sym: median Parkinson vol `σ_P = sqrt( ln(H/L)² / (4 ln2) )`, median RVOL `v_t / median(v_bucket)`, median BB(20) width, median `|ret|`.
3. Current state z-scores against the bucket's own history using MAD: `z_width = (width_now − med) / (1.4826·MAD)`.
4. **Expansion forecast**: `p_expand(Δ=30m) = P(range over next 30m ≥ 1.5× bucket median | z_width ≤ −1, regime, day-of-week)` — measured, per bucket, Wilson CI. Output the *time* of the next seasonal expansion bucket and the compression state now.
5. Same machinery gives the seasonal RSI/%B baseline, so "RSI 35" is read against "this bucket's median RSI is 42" instead of against 50.

**Inputs**: `trades.db poly_bars` (30d, whole fleet), `data/hist/bars_*_1m_30d.txt`, `data/backtest/bars3mo5m_*.csv` (3 months, 5m — better sample for week-of-year later), `data/gexa_snapshot.json` for regime conditioning. Missing: >3 months of intraday history → week-of-year/monthly seasonality is not honestly available; time-of-day is.

**Output**: `data/expansion_clock.json` → `{"MU":{"bucket":"11:15","z_width":-1.4,"z_rvol":-0.8,"next_expansion_bucket":"13:40","p_expand_30m":0.61,"ci":[0.53,0.68],"n":142,"state":"COMPRIMIDO"}}`. Surfaces as: arming/disarming of watchers (INFO banner "MU comprimido, ventana de expansión 13:40"), a PDF scenario-tree line, and a **gate** rather than a direction.

**Decision rule**: never take a breakout trade for direction from this feature. Use it to (a) arm alarms and prepare order tickets before the seasonal expansion window, (b) **veto premium buying during seasonal compression** (theta bleeds in the picadora 11:30–14:00, doctrine rule 7), (c) size down when current vol is already ≥1.5× the bucket median (the move is late).

**Validation**: split-sample — fit buckets on days 1–20, test on 21–30, then rolling. Null: `p_expand` is independent of `z_width` (compare to the unconditional expansion rate per bucket). Keep buckets with n≥120 and Wilson-low ≥ unconditional + 5pp. Register as `setup_type="expansion_<bucket>"` in `calibration_ledger.py`.

**Effort**: S, Python (`scripts/expansion_clock.py`, new; 4am batch, cheap). Feeds `inflation_score.py` and `momentum_decay.py`.

**Kill risk**: 30 days = ~21 observations per minute bucket per sym — sample too thin, so bucket medians are noise and the clock is astrology; needs aggressive bucket widening (5–15 min) and cross-sym pooling within SEMIS, which may wash out the ticker-specific clock that was the whole point.

---

## 12. Gap / island engine with measured fill probability — `gap-islands`

**Inspired by**: Islands ("never draw a trendline across a gap", `3×ATR14`), Gap Detector (`GapFactor`) and Gap Proximity (distance to nearest unfilled gap expressed in band units) — noting the vendor's two defaults disagree by design (0.5×ATR vs 3×ATR), which is exactly why we must measure `k` rather than adopt one.

**What it computes**:
1. Detect gaps at two scales: overnight (`|open_0930 − close_prev| > k_on × ATR14_daily`) and intraday 1m discontinuities (`|open_t − close_{t−1}| > k_id × ATR14_1m`, relevant in NOK/DRAM/SPCX and in the 09:30–09:45 auction we never trade).
2. Maintain an unfilled-gap registry per sym with edges (`gap_lo`, `gap_hi`, `age_days`, `size_atr`).
3. `gap_proximity = (price − nearest_unfilled_edge) / (ATR14 × mult)` — a scriptable scalar, exactly their Gap Proximity semantics.
4. **Measured fill probability**: `p_fill(by EOD | size_atr bucket, gamma regime, first-15m volume z, gap direction, captain state)` from history — this replaces folklore ("gaps always fill") with buckets.
5. Export gap edges as levels into feature 2 and gap boundaries as island cuts into feature 8.

**Inputs**: `poly_bars` (1m incl. extended hours — confirmed present, epoch range covers pre/post), `data/bars_<sym>_ibkr.txt`, `data/finviz_<sym>.txt` + Finviz earnings dates (to segregate earnings gaps, which behave differently), `chart_levels.gen()` for regime. Nothing missing.

**Output**: `data/gaps.json` → `{"MU":{"open_gaps":[{"lo":928.4,"hi":934.0,"size_atr":1.8,"dir":"UP","age_days":2,"p_fill_eod":0.44,"ci":[0.33,0.56],"n":61,"earnings_gap":false}],"proximity_atr":0.31,"nearest_edge":934.0}}`. Surfaces in the 09:45–10:30 golden-window plan (PDF page 3), as a magnet target in `direction_view.target/target_label`, and as a level in the cockpit.

**Decision rule**: trade *toward* an unfilled gap edge only when `p_fill` bucket Wilson-low > 0.55 **and** no OI wall sits between spot and the edge (the through-the-wall prohibition), with a print at the trigger level. Earnings gaps default to NO-TRADE for bought premium (doctrine: never hold a print with bought premium on earnings day).

**Validation**: 30d `poly_bars` × 30 syms gives ~600 overnight gaps at `k=0.5` (plenty). Sweep `k_on ∈ [0.3, 3.0]` and pick the threshold that maximises the *separation* between fill rates of gap vs non-gap opens, not the one that maximises fill rate. Null: fill rate equals the probability of touching an equally distant level in the opposite direction (a symmetric-touch null, which kills the "gaps are special" illusion). Keep only buckets beating that.

**Effort**: S, Python (`scripts/gaps.py`, new; overlaps nothing existing). Feeds `daily_fleet_plans.py`.

**Kill risk**: after conditioning on distance-in-ATR, gap fill is just "price touches a nearby level" — the symmetric-touch null eats the whole edge and the feature reduces to a level exporter (still useful for islands, but not a signal).

---

## 13. Fleet TechRank / Relative Performance percentile — `fleet-rank`

**Inspired by**: Relative Performance — the only fully published formula set they have: `Yearly = 0.4·P1Q + 0.2·P2Q + 0.2·P3Q + 0.2·P4Q`; `TechRank = 0.30·slowEMAdist + 0.30·slowROC(125) + 0.15·fastEMAdist + 0.15·fastROC(20) + 0.05·ppoSlope(12,26,9) + 0.05·RSI14`, on `HLC/3`, percentile-ranked, leader >80 / laggard <20.

**What it computes**: exactly those formulas, with `slowEMA=200`, `fastEMA=50`, on daily `HLC/3`, then percentile-ranked **within our universes** — full fleet (30), SEMIS troop (per `signal_conditioning.SEMIS`), and the memory-driven Korea-direct group — instead of SPX500. Honest degradation: our universe is 30 names, so a percentile is coarse (steps of 3.3) and must be reported with its `n`; the SEMIS sub-rank (≈15 names) is the more meaningful one. Add an intraday variant using 1m-derived `ROC(20 min)` z-scores for "who leads *today*".

**Inputs**: daily bars — `data/*_daily.csv` exist only for a few syms → **MISSING for the full fleet**. Cheapest proxy: `poly_bars` aggregated to daily gives 30 days (enough for `fastROC(20)` and EMA50 distance, **not** for `slowROC(125)`/EMA200) → run the 4-quarter/TechRank slow terms from a `yfinance` daily pull in the existing 4am batch job (allowed: offline/batch only, forbidden on signal paths), and mark the slow terms `stale_ok`.

**Output**: `data/fleet_rank.json` → `{"MU":{"techrank":91,"rp_yearly":88,"rank_fleet":29,"rank_semis":14,"pctile_fleet":96,"pctile_semis":93,"tag":"LIDER","intraday_z":2.3,"ts":...}}`. Surfaces in the daily email/X post ("líderes del día"), the PDF cover, and as a tie-breaker field on every arrow.

**Decision rule**: **UNA TESIS = UN BOLETO** arbitration — among correlated candidates expressing the same thesis, take the one with the highest `pctile_semis` *and* the tightest option spread; a `LAGGARD` (<20) is only traded on the short side. Never a standalone entry trigger; it's a vehicle-selection and no-tunnel-vision device (memory `fleet-wide-leader-watch`).

**Validation**: does `tag=LIDER` at day *t* predict next-day/next-3-day relative outperformance vs the fleet median, and do *signals* on leaders have a higher barrier-labelled hit rate than the same signals on laggards? Null: rank is uninformative — signal hit rate identical across rank terciles. Keep as a `direction_view` factor only if the top-vs-bottom tercile hit-rate gap has a Wilson-low above 0 with n≥150 per tercile; otherwise keep it purely as a reporting/vehicle-choice field (which needs no probability claim).

**Effort**: S, Python (`scripts/fleet_rank.py`, new; extends `fleet_pulse.py`/`daily_fleet_plans.py`).

**Kill risk**: with a 30-name universe of highly correlated semis, everything ranks near the same percentile on risk-on days — the rank carries no cross-sectional information precisely when we most want it.

---

### Deliberately rejected (so we don't rebuild what we have or can't feed)
Raindrop **patterns** as triggers (their own white paper: 66 trades, mean −0.16%); Dark Pool volume (3–5 week lag — unusable for anticipation); WSB/VADER sentiment (no edge path for a 30-name semis fleet, and it's a mention counter); TPO/Market Profile letters (we already have `poc_dom`/`profile`/`vex_profile`); Multi-Factor Alert builder UI (our C++ bots + `signal_conditioning.py` already are the predicate engine); the ML Quant Lab model zoo (Naive Bayes/KNN on TA features with no purged CV — we'd inherit their methodological hole; we take only their **label definition**, feature 3); Seasonality of *returns* by month/week (we have <4 months of intraday and 30 days of fleet 1m — the sample does not exist, so any monthly seasonality would be invented); Composite symbols with volume (they explicitly have none, and neither can we, so ratio features stay volume-free).