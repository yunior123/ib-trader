#!/bin/zsh
# start_all.sh — bring up the whole top-gainer system.
# Components (each independent, each restart-safe):
#   watchdog_keepalive.sh  -> never-loss position manager (per-second)     [always]
#   alert_bot.py           -> watchlist breakout signals -> phone+claude   [always]
#   claude_trader_loop.sh  -> headless Claude decisions (Ralph loop)       [window]
# Scanner runs separately at 6 AM (cron/launchd) or on demand.
#
# LIVE ORDERS require BOTH:  touch data/topgainer/armed   AND  export TOPGAINER_LIVE=1
# Without them the system runs fully but exec_trade prints DRY orders.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

echo "== top-gainer system =="
echo "armed:      $([[ -f data/topgainer/armed ]] && echo YES || echo no)"
echo "TOPGAINER_LIVE=$TOPGAINER_LIVE"

pkill -f "topgainer/watchdog_keepalive.sh" 2>/dev/null
pkill -f "topgainer/alert_bot.py" 2>/dev/null
pkill -x topgainer_alert 2>/dev/null
pkill -x topgainer_watchdog 2>/dev/null
pkill -f "topgainer/claude_trader_loop.sh" 2>/dev/null
pkill -f "topgainer/heartbeat.sh" 2>/dev/null
sleep 1

nohup zsh "$ROOT/topgainer/watchdog_keepalive.sh" >/dev/null 2>&1 &
echo "watchdog keepalive pid $! (C++ topgainer_watchdog primary)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
# alert bot: C++ primary (avoid python — Yunior 2026-07-09), python fallback
if [[ -x "$ROOT/topgainer/topgainer_alert" ]]; then
  nohup "$ROOT/topgainer/topgainer_alert" >>"$ROOT/topgainer/alert_bot.log" 2>&1 &
else
  nohup "$PY" "$ROOT/topgainer/alert_bot.py" >>"$ROOT/topgainer/alert_bot.log" 2>&1 &
fi
echo "alert_bot pid $!"
nohup zsh "$ROOT/topgainer/claude_trader_loop.sh" >/dev/null 2>&1 &
echo "claude trader loop pid $!"
nohup zsh "$ROOT/topgainer/heartbeat.sh" >/dev/null 2>&1 &
echo "heartbeat pid $! (beeps every minute so you know it's alive)"
echo "up. logs: topgainer/*.log  | status: $PY topgainer/state.py status"
