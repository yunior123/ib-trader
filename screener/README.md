# Top-Gainer Autonomous Trading System

Buy selective penny-stock **top gainers** at the open, sell higher, **never at a
loss**. Alerts go to Yunior (phone/Mac) AND to an autonomous Claude session that
decides and executes — with a deterministic watchdog that guarantees the sell so
a stalled Claude can never lose money. Strategy = his friend's millionaire
playbook: be selective, don't buy the blow-off top, sell high or breakeven.

## The loop problem — solved structurally
Telling Claude "work in a loop" is unreliable. So the loop does **not** live
inside Claude's agency:

1. **`claude_trader_loop.sh`** is a bash `while` loop (the Ralph Wiggum pattern,
   now also Anthropic's `/loop`). Each iteration is ONE fast headless
   `claude -p` decision that returns and is immediately re-invoked. If a call
   stalls or refuses, the next starts fresh in seconds.
2. **`watchdog.py`** owns any open position and enforces the never-loss exit
   **without any LLM**, checking price every second. Even if the Claude loop dies
   entirely, the position is managed and sold safely. This is the guarantee.

So there are two independent safety nets: the external bash loop (keeps Claude
alive) and the deterministic watchdog (keeps the money safe regardless of Claude).

## Components
| File | Role | Runs |
|---|---|---|
| `scanner.py` | 6 AM research → today's selective candidates (premarket movers, penny, liquid, not parabolic). Optional TradingAgents enrichment. Writes `watchlist_YYYYMMDD.json` + phone summary. | 6 AM (cron/launchd) |
| `alert_bot.py` | Watches watchlist for fresh in-window breakouts → phone/Mac alert + `signals.jsonl` for Claude. | always (acts 9:30–10:00) |
| `claude_trader_loop.sh` | Ralph loop: headless `claude -p` (model `claude-fable-5`, slim settings) decides selective buys. | trade window |
| `watchdog.py` + `watchdog_keepalive.sh` | Never-loss position manager, per-second, deterministic. | always |
| `exec_trade.py` | IBKR order executor (TFSA, US, whole shares, band-safe limits, breakeven floor). | on demand |
| `price.py` | Real last price: Finnhub `/quote` (sub-second) → Yahoo fallback. | lib |
| `state.py` | Atomic file-based coordination (position, signals, watchlist, decisions). | lib/CLI |

## Money-safety invariants (unit-tested in `test_screener.py`)
- **Never sell below floor** = `max(entry+1%, breakeven incl. both commissions)`.
  Under floor → hold the bag, keep watching, never realize a loss.
- **Live orders fire ONLY if `armed` file exists AND `SCREENER_LIVE=1`.**
  Otherwise every order is DRY (printed, not placed) — the whole pipeline runs
  and can be tested without touching the account.
- **Balance hard-cap (no negative balance):** every buy reads `AvailableFunds`
  LIVE from IBKR (never hardcoded), subtracts a fee/FX buffer (max(1.50 CAD, 10%)),
  converts CAD→USD at a conservative FX, and clamps the order to that budget —
  refusing entirely if it can't afford one whole share. Check anytime:
  `exec_trade.py balance`.
- US stocks only (Canadian + fractional are API-blocked). Whole shares.
- One position at a time, no averaging down. `SCREENER_ALLOC` (default 1.0) sets
  how much of the buffered budget to deploy.

## Operating it
```sh
# 6 AM research (or on demand with explicit tickers)
venv/bin/python screener/scanner.py

# bring up watchdog + alert bot + Claude loop (DRY until armed)
screener/start_all.sh

# check state anytime
venv/bin/python screener/state.py status

# GO LIVE (both required):
touch data/screener/armed
export SCREENER_LIVE=1        # in the shell that launches start_all.sh
# STOP LIVE:
rm data/screener/armed

# tests
venv/bin/python -m pytest screener/test_screener.py -q
```

## Data feed note
IBKR API real-time (`reqMktData`) still returns **Error 10089** (needs a paid
data subscription) even after the Non-Professional approval — verified
2026-07-09. So the system uses **Finnhub real-time quotes** (free key, sub-second,
verified) with Yahoo fallback. When Yunior adds Cboe One ($1/mo) and restarts
TWS, `price.py` can add an IBKR streaming source, but nothing is blocked today.
