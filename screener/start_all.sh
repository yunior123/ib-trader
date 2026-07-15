#!/bin/zsh
# start_all.sh — bring up the whole top-gainer system.
# Components (each independent, each restart-safe):
#   watchdog_keepalive.sh  -> never-loss position manager (per-second)     [always]
#   alert_bot.py           -> watchlist breakout signals -> phone+claude   [always]
#   claude_trader_loop.sh  -> headless Claude decisions (Ralph loop)       [window]
# Scanner runs separately at 6 AM (cron/launchd) or on demand.
#
# LIVE ORDERS require BOTH:  touch data/screener/armed   AND  export SCREENER_LIVE=1
# Without them the system runs fully but exec_trade prints DRY orders.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

echo "== top-gainer system =="
SIGNAL_ONLY=0; [[ -f data/screener/signal_only ]] && SIGNAL_ONLY=1
echo "signal_only: $([[ $SIGNAL_ONLY -eq 1 ]] && echo 'YES — señales solamente, sin trading')"
echo "armed:      $([[ -f data/screener/armed ]] && echo YES || echo no)"
[[ $SIGNAL_ONLY -eq 1 ]] && export SCREENER_LIVE=0
echo "SCREENER_LIVE=$SCREENER_LIVE"

pkill -f "screener/watchdog_keepalive.sh" 2>/dev/null
pkill -f "screener/alert_bot.py" 2>/dev/null
pkill -x screener_alert 2>/dev/null
pkill -x screener_watchdog 2>/dev/null
pkill -f "screener/claude_trader_loop.sh" 2>/dev/null
pkill -f "screener/heartbeat.sh" 2>/dev/null
sleep 1

nohup zsh "$ROOT/screener/watchdog_keepalive.sh" >/dev/null 2>&1 &
echo "watchdog keepalive pid $! (C++ screener_watchdog primary)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
# alert bot: C++ primary (avoid python — Yunior 2026-07-09), python fallback
if [[ -x "$ROOT/screener/screener_alert" ]]; then
  ALERT_POLL=1 nohup "$ROOT/screener/screener_alert" >>"$ROOT/screener/alert_bot.log" 2>&1 &   # poll 1s (orden 2026-07-15 blazing fast)
else
  nohup "$PY" "$ROOT/screener/alert_bot.py" >>"$ROOT/screener/alert_bot.log" 2>&1 &
fi
echo "alert_bot pid $!"
if [[ $SIGNAL_ONLY -eq 1 ]]; then
  echo "claude trader loop: OFF (signal_only)"
else
  nohup zsh "$ROOT/screener/claude_trader_loop.sh" >/dev/null 2>&1 &
  echo "claude trader loop pid $!"
fi

# daemon IBKR de flota (orden 2026-07-11 "ready for ibkr, alpaca fallback"):
# SIP bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt; auto-activa al comprar
# el sub ($10 SIP bundle, >= USD 500 equity). Reader C++ preferencia+fallback.
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup "$ROOT/venv/bin/python" "$ROOT/scripts/"ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO >>"$ROOT/bridge_ibkr_fleet.log" 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >>"$ROOT/fleet_autostart.log"
fi


# ejecutor de ETFs apalancados (dinero real cuando TFSA >= 450 USD + etf_armed)
if ! pgrep -f "scripts/executor_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/executor_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: executor_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# ALPACA RETIRADO (orden Yunior 2026-07-15 "no alpaca, only ibkr"): el daemon
# ws IEX ya no se lanza — flota 100%% IBKR (ibkr_bar_bridge); screener_alert
# usa Finnhub REST para quotes. Revivir: descomentar este bloque.
if false && ! pgrep -f "alpaca_ws_bridge NOK" >/dev/null && [[ -x "$ROOT/alpaca_ws_bridge" ]]; then
  nohup "$ROOT/alpaca_ws_bridge" NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO >>"$ROOT/ws_daemon.log" 2>&1 &
  echo "alpaca ws daemon pid $! (bars 1m NOK+SPCX+DRAM+TSLA, unica conexion ws Alpaca)"
fi
nohup zsh "$ROOT/screener/heartbeat.sh" >/dev/null 2>&1 &
echo "heartbeat pid $! (beeps every minute so you know it's alive)"
echo "up. logs: screener/*.log  | status: $PY screener/state.py status"
