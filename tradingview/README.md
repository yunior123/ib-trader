# tradingview/ — Pine strategies + local backtest lab

## ultra_trend.pine (Pine v6 — the ULTRA trend system, GENERIC across 25 tickers)

Evolution of Confluence Master designed by a 4-lens multi-agent panel
(trend-follower / squeeze-breakout / market-structure / devil's-advocate),
then every proposed rule grid-tested (128 configs) and one-out ablated on
**25 tickers** (indices, mega-tech, semis, metals/oil ETFs, TQQQ, COIN/PLTR/
MSTR) with **one single config judged on the MEDIAN ticker** — the generic
mandate. Local replica: `backtest/bt_ultra.py`.

**Kept byte-for-byte** (panel unanimous + plateau-proven): Supertrend(10,3.5)
gate, confluence score, wide 4×ATR non-trailing stop, exit on flip / score<2.

**New, each earned its place in ablation** (train PF delta when removed):
- **EVENT entries** — Donchian-20 close breakout OR bull-pattern resumption
  (engulfing/hammer/inside-break closing above BB mid). State→event is the
  anti-chop fix (−0.34 PF if removed).
- **Pattern bonus** — bull pattern in last 3 bars = +1 score, 7-point scale,
  entry needs 5/7 (−0.55 PF if removed).
- **Bear tightening** — below a falling EMA200: score≥5 AND breakout only
  (−0.42 PF if removed). Not a binary lockout, so V-recoveries stay reachable.
- **Breakeven floor** — at +5×ATR open profit, stop ratchets to entry×1.002,
  never further (converts monsters into non-losers without being a trail).
- **YEARLY-anchored VWAP** — won the A/B vs monthly across the entire top-12.

**Tested and REJECTED** (ship as OFF toggles): extension veto, post-loss
cooldown (panel loved both; the 25-ticker median didn't), ADX gate (lags trend
births: CAGR 9.6→6.4%), squeeze precondition (starves: OOS median PF 1.27),
dip-buys (dead code in event mode), any tight trailing.

**Chart display is minimal by design** (Yunior 2026-07-12): Bollinger Bands +
BUY/SELL labels only. Everything else (score, RSI divergence, rvol, stop level)
lives in the Data Window. Logic untouched — re-verified identical medians.

**DRAM note**: the ticker is two different companies — Dataram 2016→jun-2017,
then an 8.8-year listing gap, and the current DRAM relisted 2026-04-02 with
only ~68 daily bars. The system's 200-bar indicators cannot arm on it yet
(needs ~200 bars ≈ Jan-2027); mixing segments across the gap is invalid. As of
2026-07-10 the raw components read: Supertrend DOWN, below BB mid, no breakout,
no bull pattern — the system would not touch DRAM today even if armed.

### Evidence (25 tickers, one config, punitive friction)

| Window | Median PF | Median WR | Median CAGR | Median maxDD | Trades |
|---|---|---|---|---|---|
| Full 2015→2026-07 | 2.67 | 42.9% | 8.5% | 41.4% | 755 |
| OOS 2024→ (unseen in tuning) | **2.89** | 50.0% | **13.4%** | 27.6% | 211 |
| Recent 2025→ | **2.78** | 50.0% | 12.9% | 21.5% | 126 |

vs the old confluence core on the same 25-ticker OOS: PF 2.64 / WR 41.7% /
DD 29.9% — Ultra wins on all three at equal CAGR. QQQ year-by-year: 8/11
positive, losers −3.8/−4.0/−9.1% (2022, vs QQQ −33%). Recent losers are the
names in real bear trends (MSTR −68% B&H, COIN −38% B&H) where it correctly
stays small/out. Honest read: still a trend profile (WR ~43-50%), still lags
raw B&H on parabolic single names; the payoff is surviving their 60-90% DDs.

## confluence_master.pine (Pine v6 strategy — the original proven core)

Single-file merge of the classic scripts, modernized to Pine v6 `strategy()` so
TradingView's Strategy Tester backtests it natively:

| Component | Origin | Role |
|---|---|---|
| RSI Divergence (fast 5 − slow 14) | v1 study | momentum thrust |
| Supertrend ATR(10)×3.5 | v4 "super good" script, ported 1:1 | trend gatekeeper |
| DEMA(200) | v6 indicator | slow trend line (Yunior: DEMA 200, not 9) |
| EMA(200) regime (MTF-able) | replaces the Multi-SMA/EMA/BB v3 monster | bull/bear filter |
| Bollinger 20/2.0 | v3 script | location (upper/lower half, dip tags) |
| VWAP + stdev bands (anchored M) | v2 VWAP Stdev Bands, now native `ta.vwap` | institutional level |
| Relative volume ≥ 1.2 | new | participation confirm |

**Logic**: Supertrend must be UP (mandatory). Six confluence checks score 0–6;
entry needs `minScore` (default 4). Optional dip-buy: uptrend + slow RSI ≤ 38 +
close ≤ lower BB. Exits: Supertrend flip, score < 2, or 4×ATR catastrophic stop.
Long-only by default (shorts available via input). 0.05% commission + 2-tick
slippage modeled in the script header.

## Backtest evidence (local replica, real Alpaca SIP daily bars 2015→2026-07)

Engine: `backtest/bt.py` replicates the Pine logic bar-for-bar. Friction is
deliberately punitive (0.05% commission + 0.05% adverse slippage per side,
next-bar-open fills, gaps through stops fill at the open, stop not active on
entry bar — matches Pine `strategy.exit` timing).

Shipped defaults = **plateau center** of a 216-config grid (top-10 configs are
all neighbors: stMult 3.5, atrStop 3–4, minScore 3–4 → not a curve-fit spike),
trained ≤ 2023-12-31, validated OOS 2024-01-01→2026-07.

### Full period 2015→2026 (shipped config, DEMA 200)

| Sym | Trades | WR | PF | Ret | CAGR | maxDD | Exposure | B&H ret / DD |
|---|---|---|---|---|---|---|---|---|
| QQQ  | 40 | 57.5% | 4.16 | +237%  | 12.3% | 20.3% | 55% | +616% / 35% |
| SPY  | 46 | 47.8% | 1.75 | +47%   | 3.7%  | 26.6% | 56% | +341% / 34% |
| TQQQ | 44 | 40.9% | 2.28 | +426%  | 17.1% | 50.4% | 50% | +3525% / 82% |
| NVDA | 46 | 45.7% | 4.34 | +1969% | 33.5% | 56.6% | 52% | +26651% / 66% |
| AAPL | 42 | 52.4% | 4.76 | +492%  | 18.5% | 19.9% | 51% | +1230% / 39% |
| AMD  | 60 | 40.0% | 3.09 | +1076% | 26.5% | 42.9% | 45% | +20040% / 65% |
| TSLA | 43 | 39.5% | 3.71 | +1125% | 27.0% | 58.8% | 39% | +2638% / 74% |

### Out-of-sample 2024→2026-07 (never seen during tuning)

PF ≥ 1.67 on all 7 tickers. QQQ: PF 6.04, WR 66.7%, +52.1% at 12% maxDD
(B&H: +83% at 23% DD). AMD: PF 4.01, +139% OOS.

### Year-by-year QQQ (regime robustness)

8 of 11 years positive. Losing years are all small: 2016 −3.7%, 2018 −5.8%,
**2022 −8.9% while QQQ dropped −33%** — the system sat in cash most of the bear.

### Honest read (what this is and isn't)

- It's a **trend-following profile**: WR ~40–58% with avg-win ≫ avg-loss and
  PF 2–4.6. It does NOT meet the fleet's WR≥70 ship-gate — that gate is for the
  C++ signal bots; this is a TradingView chart/alert tool.
- It underperforms raw B&H return on mega-bull names (any stopped trend system
  does) but wins on risk-adjusted terms: roughly half the drawdown at ~50%
  exposure, and it side-steps bear markets.
- Best fit: QQQ/index swing on Daily. On TQQQ it cuts the 82% B&H drawdown
  to 45% — that's the use case that matters for the leveraged-ETF playbook.

## combo_tl.pine + macd_mtf.pine (Pine v6 — Yunior's favorites, merged verbatim)

The main pair (per Yunior 2026-07-12): `combo_tl.pine` (overlay, 63/64 plot
counts): ① Supertrend (v4 classic, same port as ultra_trend incl. price↔line
highlighter fills), ② Multi SMA + BB MTF by RagingRocketBull (v3, BB fill
intact, EMA GROUP CUT to fit the budget), ③ Trendlines with Breaks [LuxAlgo]
(v5, 1:1), ④ Madrid MA Ribbon (v4, all 18 lines + 4-color logic).
`macd_mtf.pine` (pane): ⑤ CM_MacD_Ult_MTF by ChrisMoody (v3). Add both.

Constraints that shaped the packaging (TradingView hard limits, hit live
07-12): (a) one script can't own the price chart AND a pane without losing
fill() (no force_overlay on fills) → MACD separate; (b) the 64-plot-count
budget — series-colored plots cost 2, alertconditions 1, so the ribbon alone
is 36 counts. Cuts chosen in combo_tl to fit: the 5-EMA group (Yunior's call),
the SMA1 slot (original default length 0 = hidden anyway), and the redundant
"Direction Change" alert (Buy + Sell cover both flips).

Variants kept: `combo5.pine` (62/64) = same but WITH the full 5-EMA group and
WITHOUT trendlines; `trendlines_breaks.pine` = LuxAlgo standalone 1:1. Only
cosmetic loss everywhere: SMA circles unjoined (v3 `join=` removed from Pine).

## combo_yoel.pine (Pine v6 overlay — el sistema de Yoel Sardiñas, 30/64 plots)

Variante COMBO-YOEL que refleja EXACTO las 4 únicas herramientas de Yoel (caps
X-XII, pp.116-177; ni RSI/MACD/Supertrend ni stop-loss): ① Bollinger(SMA20,2σ)
banda+media+relleno, ② medias simples **20/40/100/200** (el set de Yoel —
reemplaza el grupo genérico RagingRocketBull y la cinta Madrid de combo_tl), ③
Trendlines with Breaks [LuxAlgo] reusado 1:1 (est.1-2 dependen de la ruptura de
trendline), ④ volumen vs MA50 como CONDICIÓN booleana `volume>ta.sma(volume,50)`
que gatea el FILTRO TRANSVERSAL de Yoel para est.5-8 (Pine no plotea el panel de
volumen en overlay). Las **8 estrategias** salen como plotshape + alertcondition:
E1/E2 cambio de tendencia (call/put), E3/E4 rebote de punto medio (call/put),
E5/E6 fuera-de-banda en apertura (put/call, ventana intradía), E7/E8 efecto imán
(call/put de regreso a la SMA20). Single-TF a propósito (cero repintado/look-
ahead): aplícalo en **1H** para est.1-4 y en **15m** para est.5-8, top-down como
manda el libro. Budget 30/64 (BB 3 + SMA40/100/200 3 + 2 trendlines series-color
×2 = 4 + 10 plotshapes + 10 alertconditions; SMA20 = base BB, no se duplica).
Señal-solamente. Crédito LuxAlgo CC BY-NC-SA 4.0.

## backtest/bt.py

```
python3 bt.py fetch [SYMS...]   # refresh daily bars (Alpaca SIP, adjustment=all)
python3 bt.py run   [SYMS...]   # shipped config, full period + buy&hold benchmark
python3 bt.py grid  [SYMS...]   # 216-config grid, train/OOS split, top-10 report
```

Data cached in `backtest/data/*.csv`. Keys read from repo `alpaca.env`.

## reference/

Original pasted scripts kept for provenance (Supertrend v4, RSI Divergence v1,
DEMA v6). The Multi-SMA/EMA/WMA/HMA-BB v3 and VWAP-Stdev v2 scripts were not
kept verbatim — their functionality is subsumed by native v6 `ta.vwap` bands
and the regime-EMA/BB blocks in confluence_master.



COMBO-TL — Supertrend + Multi SMA/BB (MTF) + Trendlines with Breaks + Madrid Ribbon

Four classic, battle-tested indicators merged into a single overlay script — original logic preserved 1:1, no repainting tricks added, no signals altered. One indicator slot instead of four.

What's inside

🟢 Supertrend (10, 3.0) — the classic version: trend line witharkers where a trend is born, Buy/Sell labels on the line, andthe price↔line highlighter fill. Source, ATR period, multiplier and ATR calculation method are configurable.

📊 Multi SMA + Bollinger Bands, multi-timeframe (based on Ragi four MA slots (20/50/100/200 by default) that can each be SMA,EMA, WMA, HMA, VWMA, SWMA, ALMA, RMA or LINREG, plus Bollinger Bands with their own MA type. Both groups accept a custom timeframe (e.g. show the Daily 200 SMA on an hourly chart — supports "4H"-style input), with the original X/Y point-density smoothing to tame MTF stair-stepping.

📐 Trendlines with Breaks (LuxAlgo) — pivot-based up/down trendlines with ATR/Stdev/Linreg slope, dashed extended lines, and "B" labels on confirmed breakouts. Backpainting toggle included: keep it on for clean visuals, turn it off for real-time line placement.

🌈 Madrid Moving Average Ribbon — the well-known 18-line ribbon (MA 5→90 vs MA 100), EMA or SMA. Lime = uptrend, green = buy-the-dip reentry, red = downtrend, maroon = sell-the-peak reentry.

Alerts (4)
- SuperTrend Buy / SuperTrend Sell
- Upward Breakout / Downward Breakout (trendline breaks)

Notes
- Each module has its own show/hide toggle and input group.
- The script sits at 63 of Pine's 64 plot budget — that's why cond (EMA) group isn't included; use the MA-type dropdown if you want the SMA slots to be EMAs.
- Works on any symbol and timeframe. Best paired with a MACD in a separate pane.

Credits — this is a merge/port to Pine v6 of open-source classics: Supertrend (community v4 classic), Multi SMA EMA WMA HMA BB MTF by RagingRocketBull (v3), Trendlines with Breaks by LuxAlgo (v5, CC BY-NC-SA 4.0), Madrid Moving Average Ribbon by Madrid (v4, MPL 2.0). All trading logic belongs to the
original authors; this script only unifies them into one slot.