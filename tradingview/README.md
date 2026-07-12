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
