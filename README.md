# IB Trader

A rules-based swing-trading loop for Interactive Brokers: trend + pullback
entries, a laddered partial-profit exit, a never-sold "core" position
alongside an actively-traded slice, and volatility-adjusted position sizing.

**This is a starting point for your own testing, not a finished profitable
strategy, and not financial advice.** Markets can trend against every rule
here for extended periods, and past performance of any rule set doesn't
predict future results.

## How it decides

- **Entry**: 50 EMA > 200 EMA and price > 200 EMA (uptrend), plus RSI < 35
  with price at/below the 20 EMA (pullback).
- **Sizing**: risks a fixed % of account equity per trade, scaled by ATR
  (wider ATR → smaller size).
- **Split**: a new position is split into a `CORE_FRACTION` that is never
  sold by the bot, and a `TRADING_FRACTION` that is scaled in/out.
- **Exit**: as gains from the trading slice's average cost cross each rung
  in `PROFIT_LADDER`, that fraction of the trading shares is sold. An
  overbought/overextended reading triggers a full trading-slice exit as a
  safety valve.
- **Buyback**: after a pullback from a recent high while still in an
  uptrend, the trading slice is rebuilt.

All of this is configurable in `config.py`.

## Setup

1. Install TWS or IB Gateway and enable the API:
   Configuration → API → Settings → check "Enable ActiveX and Socket
   Clients", and note the socket port.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Edit `config.py`:
   - `IB_PORT`: 7497 for TWS paper, 4002 for IB Gateway paper (start here),
     7496 / 4001 for live.
   - `SYMBOLS`, thresholds, sizing, and the profit ladder.
4. Run:
   ```
   python main.py
   ```

## Safety

- `DRY_RUN = True` by default. In this mode every decision is logged and
  written to `trades.db`, but **no order is ever sent to IBKR**.
- Only switch `DRY_RUN = False` after testing against a **paper trading**
  account for an extended period (weeks, across different market
  conditions) — never point it at a live account first.
- `state.json` persists the core/trading split and ladder progress across
  restarts. Delete it to reset a symbol's tracked state.
- `ib_trader.log` and `trades.db` record everything the bot decided and
  did, for review.
- There is no built-in kill switch beyond `Ctrl+C` / stopping the process —
  add monitoring/alerting before trusting this with real capital.

## Project layout

```
ib-trader/
├── config.py       strategy & connection settings
├── indicators.py   EMA / RSI / ATR
├── risk.py         volatility-adjusted position sizing
├── portfolio.py    persisted core/trading share state
├── strategy.py     entry / exit / buyback decision logic
├── execution.py    order placement (dry-run aware)
├── ib_client.py    IBKR connection & data fetch
├── logger.py       logging setup
├── database.py     SQLite trade log
├── main.py         the loop
└── requirements.txt
```
