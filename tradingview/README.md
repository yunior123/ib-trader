# tradingview/ — Pine strategies + local backtest lab

## confluence_master.pine (Pine v6 strategy — THE one file)

Single-file merge of the classic scripts, modernized to Pine v6 `strategy()` so
TradingView's Strategy Tester backtests it natively:

| Component | Origin | Role |
|---|---|---|
| RSI Divergence (fast 5 − slow 14) | v1 study | momentum thrust |
| Supertrend ATR(10)×3.5 | v4 "super good" script, ported 1:1 | trend gatekeeper |
| DEMA(9) | v6 indicator | fast trigger line |
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

### Full period 2015→2026 (shipped config)

| Sym | Trades | WR | PF | Ret | CAGR | maxDD | Exposure | B&H ret / DD |
|---|---|---|---|---|---|---|---|---|
| QQQ  | 59 | 52.5% | 3.45 | +215%  | 11.6% | 17.9% | 54% | +616% / 35% |
| SPY  | 58 | 51.7% | 2.07 | +68%   | 5.1%  | 22.1% | 55% | +341% / 34% |
| TQQQ | 71 | 40.8% | 2.00 | +373%  | 16.0% | 45.4% | 48% | +3525% / 82% |
| NVDA | 79 | 43.0% | 2.84 | +1353% | 29.1% | 51.0% | 48% | +26651% / 66% |
| AAPL | 65 | 46.2% | 3.36 | +427%  | 17.2% | 18.6% | 49% | +1230% / 39% |
| AMD  | 83 | 43.4% | 2.65 | +1235% | 28.0% | 37.6% | 41% | +20040% / 65% |
| TSLA | 61 | 44.3% | 4.64 | +2990% | 38.7% | 51.7% | 36% | +2638% / 74% |

### Out-of-sample 2024→2026-07 (never seen during tuning)

PF ≥ 1.75 on all 7 tickers. QQQ: PF 4.41, +48.6% at 11% maxDD (B&H: +83% at
23% DD). TSLA: PF 4.22, +77% vs B&H +64% at half the drawdown.

### Year-by-year QQQ (regime robustness)

8 of 11 years positive. Losing years are all small: 2016 −3.6%, 2018 −5.1%,
**2022 −4.4% while QQQ dropped −33%** — the system sat in cash most of the bear.

### Honest read (what this is and isn't)

- It's a **trend-following profile**: WR ~45–52% with avg-win ≫ avg-loss and
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
