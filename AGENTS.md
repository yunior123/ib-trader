# AGENTS.md — ib-trader

## Overview
Rules-based dip/breakout trading system for Interactive Brokers (IBKR), US equities via SMART routing.
Main bot: **`day_trading_bot.py`** (multi-ticker via `--symbol`; formerly dram_dip_bot.py).
Legacy multi-symbol EMA system: `main.py` + config.py/strategy.py/etc (KOD, dormant).

## Yunior's Favorite Tickers (memo, 2026-07-06)
TSM, AMD, DRAM, ASML, SPCX, TSLA, NVDA, NOK, AAPL, INTC, TXN, MU, GOOGL, QCOM, SMH, SPY, QQQ
- Mostly semis + big tech + index ETFs. Backtest each before trading: params tuned on DRAM's volatility.
- 7d test 2026-07-06 ($500, defaults): bot only fires on real panic — big winners DRAM +4.5% (vs −21% B&H), TSM +4.6%, TXN +2.5%, GOOGL +3.0%, AAPL +2.4%; calm tickers (SPY/QQQ/SMH/MU/ASML) = 0 trades, in cash. Never lost realized money on any of 17.

## Strategy (day_trading_bot.py)
- **Entry** (`--entry-mode`): `dip` (DEFAULT: close ≤ BB(20, 3.0) lower AND RSI(14) ≤ 25 AND vol ≥ 1.2×MA20 → buy next bar open) | `reclaim` (same dip arms, buy on close > prior 10-bar high = bullish BOS; caught a dead-cat bounce on DRAM 60d — dip is more robust).
- **Exit** (`--exit-mode`): `breakout` (DEFAULT: ATR(14) Chandelier — ride rebound, exit on 3×ATR retrace from peak) | `fixed` (GTC limit at entry+target).
- **Never sell at a loss**: exit floor = max(entry × (1 + min_profit_pct), break-even incl. fees), enforced at fill. Realized PnL cannot be negative. Bag is held until recovery (unrealized losses possible — that's accepted risk).
- **Sizing**: `use_all_cash: True` — full balance each cycle, whole shares, compounding. Live buys use 98% (fee/slippage buffer; TFSA = cash account).
- **Costs modeled**: $1/order commission. With 1 share of a ~$70 stock, fees force the floor to ~+3%; commission drag fades with budget ≥ $500.
- Defaults: min_profit_pct 5.0 (floor), trail 3×ATR, max_lots 1, cooldown 0.

## Validated Results (real data, fees included, all realized-positive)
| Window ($500) | dip+breakout 3ATR (DEFAULT) | dip+fixed +5% |
|---|---|---|
| 14d crash 1m (DRAM −18%) | **+18.53%** | +13.47% |
| 7d crash 1m (DRAM −17.7%) | **+4.53%** | +4.51% |
| 60d 15m (DRAM +104%) | +13.39% | **+26.98%** |

Engine honesty: signal on completed bar → fill next bar open (no look-ahead); limit sells fill intrabar at limit-or-better; whole shares; commissions; same-bar exits blocked.

## Commands
```bash
# Fetch real data (yfinance; raw urllib gets 429). Any symbol:
venv/bin/python scripts/fetch_dram_data.py DRAM   # -> data/dram_15m.csv + dram_daily.csv

# Backtest
venv/bin/python day_trading_bot.py --mode backtest --data-file data/dram_1m_14d.csv --capital 500

# Param sweep
venv/bin/python scripts/dram_backtest_analysis.py data/dram_1m_14d.csv

# Paper trading smoke test (IB Gateway paper 4002 / TWS paper 7497)
venv/bin/python day_trading_bot.py --mode trade --port 4002 --once --wait-tws

# Production paper run (24/5 window + TWS wait + auto-reconnect)
venv/bin/python day_trading_bot.py --mode trade --port 4002 --schedule --wait-tws

# Live (REAL MONEY, TFSA only, manual YES confirmation)
venv/bin/python day_trading_bot.py --mode trade --port 7496 --live
```
Key flags: `--symbol/--exchange/--currency`, `--entry-mode dip|reclaim`, `--exit-mode breakout|fixed`,
`--min-profit-pct`, `--trail-atr-mult`, `--bb-std`, `--rsi-oversold`, `--commission`, `--schedule`, `--wait-tws`.

## 24/5 Operation (Sun 20:00 → Fri 20:00 Toronto)
- `--schedule` sleeps outside the window (DST-aware, edge-tested). `--wait-tws` socket-probes TWS/Gateway and waits instead of dying; also used on reconnect.
- launchd service: `cp scripts/com.ibtrader.dram.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.ibtrader.dram.plist` (RunAtLoad + KeepAlive; runner: `scripts/run_dram_bot.sh`).
- TWS/Gateway must be running & logged in (bot waits, can't start it). Use IB Gateway + Auto restart for unattended weeks. No web server needed.

## IBKR Integration (audited 2026-07-06)
- ib_insync 0.9.86 (imports prefer `ib_async` if installed). Verified: connect/qualifyContracts/reqHistoricalData/accountSummary/positions/openTrades/placeOrder/LimitOrder(tif=GTC).
- Live loop: acts on last COMPLETED bar only; reconnect guard; restart recovery (seeds lot from IBKR avgCost so breakout trail works after a crash); all sells are LIMIT ≥ floor — no loss possible even on slippage; cash-checked whole-share buys.
- Ports: TWS paper 7497 / live 7496; IB Gateway paper 4002 / live 4001. All closed as of 2026-07-06 (TWS not running).

## Accounts & Safety
| Account | Purpose |
|---|---|
| `U26642820` | Cash account — NEVER for live bot orders |
| `U26942420` | TFSA — only allowed live account (enforced in code) |
| `DUR197573` | Paper account (pending approval ~2026-07-07) |
- Default = paper/dry-run. Live needs `--live` + typed "YES". Weeks of paper testing before live.
- Paper accounts appear as `DU*`. If only `U*` visible, session is live infrastructure — read-only only.
- IB Gateway download: interactivebrokers.com → Technology → IB Gateway (login: IB API + Paper Trading; API port 4002; enable Socket Clients; Auto restart on).

## Conventions
- Timestamps UTC in data files; schedule logic in America/Toronto.
- Data files: `data/<sym>_{1m_7d,1m_14d,15m,daily}.csv` (columns: date,open,high,low,close,volume).
- Logging INFO → stdout + ib_trader.log; launchd logs → dram_bot_stdout/stderr.log.
- Deps: ib_insync≥0.9.86, pandas, numpy, yfinance (venv/, Python 3.9 — no `X | Y` type syntax).
- DRAM thesis: supply shortage through 2028, long-bias justified; thesis ≠ guarantee — backtests must report realized AND mark-to-market.
