# AGENTS.md — Project Conventions for ib-trader

## Overview
This is a rules-based swing-trading system for Interactive Brokers (IBKR).
It trades US equities (NASDAQ/NYSE) via IBKR SMART routing.
Each ticker gets its own dedicated bot file: `<ticker>_dip_bot.py`.

## Current Tickers
- **DRAM** (NASDAQ) — `dram_dip_bot.py`

## Project Structure
```
ib-trader/
├── config.py              # Base configuration (shared)
├── indicators.py          # EMA / RSI / ATR
├── risk.py                # Volatility-adjusted sizing
├── portfolio.py           # Persisted core/trading state
├── strategy.py            # Entry / exit / buyback logic
├── execution.py           # Order placement (dry-run aware)
├── ib_client.py           # IBKR connection & data fetch
├── logger.py              # Logging setup
├── database.py            # SQLite trade log
├── main.py                # Main loop (multi-symbol)
├── dram_dip_bot.py        # DRAM-specific dip bot (NEW)
├── requirements.txt
├── trades.db              # Trade history
├── state.json             # Portfolio state persistence
└── AGENTS.md              # This file
```

## Adding a New Ticker
1. Copy `dram_dip_bot.py` → `<TICKER>_dip_bot.py`
2. Update constants at top:
   - `TICKER_SYMBOL`
   - `TICKER_EXCHANGE` (use `"SMART"` for best price across NYSE/NASDAQ/BATS/EDGX)
   - `TICKER_CURRENCY` (usually `"USD"`)
3. Adjust strategy params in `DEFAULT_CONFIG` if needed
4. Test with `--mode backtest` first

## Data Fetching (no IBKR connection needed)
```bash
# Fetch real DRAM OHLCV from Yahoo Finance -> data/dram_15m.csv (60d) + data/dram_daily.csv (2y)
venv/bin/python scripts/fetch_dram_data.py
```
- Uses `yfinance` (handles Yahoo cookie/crumb auth; raw urllib requests get HTTP 429).
- DRAM listed 2026-04-02, so daily history starts there.
- 15m bars match the live bot's bar size — always backtest against `data/dram_15m.csv` first.

## Running DRAM Bot
```bash
# Backtest (fetch data from IBKR, simulate)
venv/bin/python dram_dip_bot.py --mode backtest --capital 70

# Backtest against a saved local CSV snapshot
venv/bin/python dram_dip_bot.py --mode backtest --data-file data/dram_15m.csv --capital 70

# Parameter sweep + stress tests against a local CSV (default: data/dram_15m.csv)
venv/bin/python scripts/dram_backtest_analysis.py data/dram_15m.csv

# Paper trading / dry-run smoke test (no orders sent, exits after one bar)
venv/bin/python dram_dip_bot.py --mode trade --port 7497 --once

# Live trading (REAL MONEY - TFSA only, requires confirmation)
venv/bin/python dram_dip_bot.py --mode trade --port 7496 --live
```

## Safety Rules
- **Default is DRY_RUN / paper mode**. No live orders sent unless `--live` flag + manual "YES" confirmation.
- Always test against **paper trading account first** (TWS port 7497, IB Gateway 4002).
- For DRAM, use paper trading for now. Do not run DRAM with `--live` during current testing.
- Live trading is restricted to the TFSA account `U26942420`; never use the cash account `U26642820` for live bot orders.
- Never point directly at live account without weeks of paper testing.
- `state.json` persists core/trading split across restarts. Delete to reset.

## Account Reference
| Account | Purpose | Last observed cash |
|---------|---------|--------------------|
| `U26642820` | Cash account | `2.50 CAD` |
| `U26942420` | TFSA account; only allowed live account | `2.50 CAD` |
| `DUR197573` | Paper trading account | Pending approval until 2026-07-07 |

Paper accounts normally appear as `DU...` accounts. If only `U...` accounts
are visible, treat the connected TWS session as live-account infrastructure and
use read-only/dry-run or switch TWS to paper before testing.

## Paper Trading Setup
1. Log in to IBKR Client Portal.
2. Open the user menu (head-and-shoulders icon) > `Settings`.
3. Go to `Account Configuration` > `Paper Trading Account`.
4. Confirm the paper username/account number. Current pending paper account: `DUR197573`.
5. Enable sharing real-time market data with the paper account if available.
6. Wait for IBKR approval/activation email if the account is still pending.
7. Restart TWS and choose `Paper Trading` on the login screen.
8. In TWS Paper, open `Edit` > `Global Configuration` > `API` > `Settings`.
9. Enable `ActiveX and Socket Clients`, keep `Read Only API` enabled for tests, and confirm socket port `7497`.
10. Re-run DRAM tests with `--port 7497`; never substitute live port `7496` for paper testing.

## Current Local TWS State
- As of 2026-07-06, local TWS is running as a macOS `JavaApplicationStub` window named `U26942420 Interactive Brokers`.
- Local TWS API port `7496` is open and exposes live `U...` accounts.
- Paper ports `7497` (TWS paper) and `4002` (IB Gateway paper) refused connections during testing.
- Do not use port `7496` for DRAM paper testing. Restart/log into TWS Paper first, then re-run the DRAM paper checks.

## Strategy: Dip Accumulator (Bollinger + RSI + Volume)
- **Entry**: Price at/below lower Bollinger Band (20, 2) AND RSI(14) ≤ 35 AND Volume ≥ 1.2× 20-bar MA
- **Exit**: Profit target ≥ 2% per lot (configurable). Optional trailing giveback.
- **Sizing**: Dynamic per-lot capital (default $70). Compounds from real account cash (up to 90% per lot).
- **Max lots**: 20. Max deployed capital: 90% of starting cash. If remaining deployable cash is below `capital_per_lot`, the simulated lot scales down instead of skipping the signal.
- **Never sells at a loss**. Thesis floor alert if price breaks below floor.
- Important: "Never sells at a loss" does **not** mean the strategy cannot lose money. Open lots can carry unrealized losses if DRAM keeps falling, and capital can remain tied up.

## DRAM Thesis Guardrails
- Working thesis: DRAM supply shortage is expected to support the DRAM trade through 2028, so the DRAM bot is long-biased and tries to accumulate dips, then take profit on rebounds.
- This thesis is **not** a guarantee. The bot must still be tested for drawdown, stale open lots, liquidity, bad fills, thesis breaks, symbol-specific news, and broad market selloffs.
- Backtests must report realized PnL and mark-to-market equity. A run with no realized losing sells can still be a bad run if open lots are deeply underwater.

## Backtest Results — Real Data (2026-07-06, 15m bars 2026-04-09 → 2026-07-06, $70 start)
- Buy & hold over window: **+103.7%** (DRAM ran ~$32 → $64.63); worst day −13.3%, max close drawdown −26.9%.
- Default config (BB 20/2.0, RSI≤35, vol×1.2, +2% take, cooldown 5): **+34.7%**, 14 buys / 13 sells, max equity DD −9.0%, max open-lot DD −12.9%.
- Best sweep config (BB std 1.5, RSI≤55, vol×0.8, +2% take, cooldown 5): **+72.4%**, 25 buys / 22 sells, max equity DD −10.0%.
- Stress (aggressive config, price gap after last bar): +5% rebound → +58.6%; −10% → +46.6%; −25% → +34.6%; −40% → +22.6%. Realized PnL survives; open lots carry the damage.
- Caveats: single 3-month window of a post-IPO melt-up — the strategy underperforms buy&hold in straight uptrends. Sweep winners are fit to this one window; do not treat +72% as expected forward return.

## Crash-Week Test — Real Data (last 7 sessions, 1m extended-hours bars, Jun 25 → Jul 6 2026, Sun 8pm→Fri 8pm Toronto window)
- Data: `data/dram_1m_7d.csv` (6,414 bars incl. pre/post market 4am–8pm ET; Jul 3 market holiday). DRAM fell **−17.75%** ($78.82 → $64.83, low $58.90).
- $70 capital: both configs **−15.9%** — first signal deploys the full $63 lot (90% cap), then no ammo left. With $70, "dip laddering" degenerates to one all-in buy.
- $700 capital, default: **−12.2%** (10 buys down the crash, 1 profitable scalp +$1.45, 9 lots open, worst lot −25.2%, max equity DD −19.6%).
- $700, sweep-winner config: **−13.5%** — *worse* than default in a crash, confirming the sweep params were overfit to the melt-up window.
- Takeaways: bot beats buy&hold slightly in a crash but still takes double-digit MTM losses; never-sell-at-a-loss means capital gets fully locked in underwater lots by day 2 of a sustained decline. Thesis floor / max drawdown guard matters more than entry tuning.

## Conventions
- All timestamps in UTC.
- Logging: `INFO` to stdout + `ib_trader.log`.
- Trade history in `trades.db` (SQLite).
- Indicator calculations use pandas `ewm` (exponential weighting).
- IBKR SMART routing for all US symbols (best price across venues).
- 15-min bars for live/paper, configurable for backtest.

## Dependencies
- `ib_insync>=0.9.86`
- `pandas>=1.5`
- `numpy>=1.23`

## Port Reference
| Environment | TWS | IB Gateway |
|-------------|-----|------------|
| Paper       | 7497 | 4002 |
| Live        | 7496 | 4001 |
