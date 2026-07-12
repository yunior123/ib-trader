# ib-trader — Operations Runbook

> How to run, verify, and fix the system. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md).
> Trading rules: [TRADING-RULES.md](TRADING-RULES.md). Written 2026-07-11.

## Start / stop

```bash
cd ~/Documents/GitHub/ib-trader

# START everything (idempotent — safe to re-run; this is also the reboot fix)
zsh scripts/fleet_keepalive_start.sh     # 16 bot keepalives + executor + ibkr daemon
zsh screener/ensure_all.sh              # ws daemon + screener stack (also pgrep-guarded)

# STOP trading only (signals keep running) — THE KILL SWITCH
rm data/etf_armed                        # executor → dry-run instantly, logs decisions only
touch data/etf_armed                     # re-arm

# STOP a single bot            # STOP everything
pkill -f nvda_keepalive && pkill -x nvda_signal_bot
                               pkill -f "_keepalive.sh"; pkill -f "signal_bot"; \
                               pkill -f "alpaca_ws_bridge"; pkill -f "ibkr_bar_bridge"; \
                               pkill -f "fleet_executor"
```

## Health check (run anytime)

```bash
echo "bots: $(pgrep -f 'signal_bot$' | wc -l)/16  keepalives: $(pgrep -f '_keepalive.sh' | wc -l)/17"
echo "ws-daemon: $(pgrep -f 'alpaca_ws_bridge NOK' | wc -l)/1  ibkr-daemon: $(pgrep -f 'ibkr_bar_bridge.py --daemon' | wc -l)/1"
echo "executor: $(pgrep -f 'fleet_executor.py' | wc -l)/1  armed: $([ -f data/etf_armed ] && echo YES || echo no)"
tail -3 ws_daemon.log            # expect: subscribed OK with 16 bars symbols
tail -3 fleet_executor.log       # expect: arrancando + IBKR conectado
tail -3 bridge_ibkr_fleet.log    # pre-subscription: "SIN PERMISOS (err 420) — reintento 10 min" is NORMAL
./venv/bin/python scripts/fleet_executor.py --selftest   # parser/map/floor invariants
```

## Activation day (funding the account)

1. Deposit **≥ CAD 750** (must clear **USD 500** — CAD 500 ≈ USD 365 bounces both gates).
2. Client Portal → buy “US Securities Snapshot and Futures Value Bundle” ($10/mo,
   waived at $30/mo commissions). Restart TWS.
3. Nothing else. Within 10 min `bridge_ibkr_fleet.log` shows
   `"SIP bars+NBBO suscritos (premium activo)"` per symbol (readers switch to SIP),
   and the executor's next BUY signal passes the equity gate and trades.
4. First-day watch: `tail -f fleet_executor.log` + `data/etf_ledger.csv` vs the IBKR
   Activity page. Every order the bot places must appear in both.

## Daily checks (1 minute)

- `grep -c BANNER fleet_executor.log` — anything new? Read the last few.
- `column -s, -t data/etf_ledger.csv | tail` — trades match IBKR activity?
- Bags: `python3 -c "import json;print({k:v for k,v in json.load(open('data/etf_positions.json'))['positions'].items() if v.get('bag')})"`
  — each bag must have its GTC + stop visible in TWS (OCA pair).
- TWS must be running and logged in (it is the only gateway; enable its auto-restart
  setting so the daily TWS restart doesn't require a human).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Nothing autostarts after reboot | macOS TCC blocks launchd in ~/Documents (LaunchAgents exit 78) | Run the two START commands manually; permanent fix: System Settings → Privacy → Full Disk Access → add `/bin/zsh`, then `rm` the stale LaunchAgent log files (they carry `com.apple.macl` xattrs) and `launchctl kickstart -k gui/$UID/com.ibtrader.fleet` |
| `err 420 / 10089` in bridge_ibkr_fleet.log | No API market-data subscription yet | Normal until the $10 bundle is active; prober retries every 10 min |
| Executor logs `SKIP BUY … equity < 500` | Account below the gate | Fund the account; this is the designed wait state |
| Executor logs `TWS caido, posicion IBKR — broker protege` | TWS down with an open position | Start TWS; server-side stops/GTCs protect meanwhile — do not panic-close |
| `PAPER BUY (fallback)` banner | TWS unreachable at a BUY signal | That order went to Alpaca **paper** (key is PK…): not real. Restart TWS |
| Bot silent all day | Reader/daemon died or market closed | Health check above; `tail bridge_<sym>.log`; keepalives revive in ≤30s |
| `ws: 405` in ws_daemon.log | quotes+trades subscription cap (30) exceeded | Lower WS_QUOTES or watchlist; bars don't count toward the cap |
| Duplicate keepalives | Manual start while LaunchAgent alive | `pkill -f <sym>_keepalive` then start once; keepalives self-dedupe bots via pkill |
| `SHORT DETECTADO` banner | A short exists in a fleet ETF | Bot never manages shorts; check TWS — if it isn't yours, investigate immediately |

## Where everything is logged

| Log | Content |
|---|---|
| `fleet_executor.log` | every signal seen, every decision + reason, banners |
| `data/etf_ledger.csv` | every executed operation with real commissions + pnl_usd (audit trail) |
| `trades.db` | SQLite: `etf_operations` (all trades/ops) + `etf_signals` (every parsed signal) |
| `<sym>_operations.log` | every bot signal (the executor's input; `WARMUP` = replay) |
| `<sym>_signals.log` | bot stdout (indicators, arms, trades with `t=`) |
| `ws_daemon.log`, `bridge_ibkr_fleet.log`, `bridge_<sym>.log` | data plane |
| `fleet_autostart.log` | keepalive/guard launches |

## Database queries (trades.db)

```bash
sqlite3 trades.db "SELECT * FROM etf_operations ORDER BY id DESC LIMIT 10"   # ultimas operaciones
sqlite3 trades.db "SELECT date(ts) d, SUM(pnl_usd) FROM etf_operations
                   WHERE event LIKE 'sell%' OR event LIKE 'closed%' GROUP BY d"  # PnL por dia
sqlite3 trades.db "SELECT base, action, COUNT(*) FROM etf_signals GROUP BY base, action"  # señales
sqlite3 trades.db "SELECT etf, COUNT(*), SUM(fee_usd) FROM etf_operations GROUP BY etf"   # fees
```
The daily-loss circuit breaker reads `etf_operations.pnl_usd` for today — if the DB
is ever corrupted, `rm trades.db` recreates it empty on next executor start (the CSV
retains full history and re-imports automatically into the empty table).

## Re-tuning / backtesting (see also scripts/*.py headers)

```bash
./venv/bin/python scripts/fleet_backtest_audit.py all 90   # fleet replay with live configs
./venv/bin/python scripts/fleet_wfo.py                     # walk-forward optimizer (train/OOS)
./venv/bin/python scripts/leveraged_backtest.py 90         # ETF-translation simulation
./venv/bin/python scripts/gen_charts.py && (cd charts && python3 -m http.server 8899)
```
Ship gate (standing order #7): WR ≥ 70% AND positive out-of-sample walk-forward, or OFF.
