# ib-trader

Real-time trading system: **16 C++ signal engines** on 1-minute bars (validated
WR≥70 + out-of-sample walk-forward per ticker), a **~0.3ms local signal pipeline**
(shared Alpaca websocket daemon + IBKR SIP daemon + kqueue dual-source readers), and a
**leveraged-ETF execution layer** on IBKR with broker-resident protection (OCA pairs:
recovery GTC + catastrophic stop). Double-purpose by design: signals drive a human
trading options; the executor autonomously trades leveraged ETFs on the same signals.

**Not financial advice. Live-money code — read the docs before touching anything.**

## Documentation

| Doc | What's in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full system design: data plane, signal engines, execution plane, file contracts, measured latencies |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Runbook: start/stop, kill switch, health checks, activation day, troubleshooting table |
| [docs/TRADING-RULES.md](docs/TRADING-RULES.md) | The trading law: owner orders, ETF map, bull/bear/bag rules, evidence trail, change control |
| [AGENTS.md](AGENTS.md) | Agent-facing operational law: standing orders, master trading playbook, per-component history |

## The system in five lines

```
Alpaca ws / IBKR TWS ─► C++ daemons ─► bars files ─► kqueue readers (~0.3ms)
  ─► 16 C++ signal bots (1.1µs/bar: capitulation/trend/terremoto engines)
      ├─► Mac banners + voice ─► HUMAN trades options (BUY NOW=call, BUY PUT=put)
      └─► operations logs ─► fleet_executor (ib_insync) ─► leveraged ETFs on IBKR TFSA
            bulls: sell-higher-only + bag w/ GTC+stop OCA · bears: quake-only, stopped, never overnight
```

## Quick start (existing installation)

```bash
zsh scripts/fleet_keepalive_start.sh   # everything signal-side + executor
zsh screener/ensure_all.sh            # ws daemon + scanner stack
rm data/etf_armed                      # KILL SWITCH (trading off; signals unaffected)
```

Key safety facts: the executor only trades when `data/etf_armed` exists AND account
NetLiq ≥ USD 500; circuit breakers (daily-loss halt −5%, sector concurrency cap,
gross leverage ≤1.5×, settled-cash budget) gate every buy; every position carries
broker-resident protective orders that work with this machine powered off; the
account (not local state) is the source of truth; full audit trail in
`data/etf_ledger.csv` **and** `trades.db` (`etf_operations`, `etf_signals`).

Legacy Python was deleted 2026-07-11 (recoverable from git history).
`day_trading_bot.py` remains only as a helper library imported by the screener stack.
