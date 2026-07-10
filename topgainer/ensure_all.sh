#!/bin/zsh
# ensure_all.sh — supervisor del sistema topgainer ("working non stop", Yunior
# 2026-07-10). Relanza SOLO los componentes muertos; no toca nada vivo (a
# diferencia de start_all.sh, que hace pkill+restart completo — usar ese solo
# para arranques manuales limpios). launchd lo corre al login y cada 2 min
# (com.ibtrader.topgainer RunAtLoad + StartInterval): si el alert bot, el loop
# de Claude, el heartbeat o el keepalive del watchdog mueren a mitad del dia,
# reviven en <=2 min. Idempotente via pgrep.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
export TOPGAINER_LIVE="${TOPGAINER_LIVE:-1}"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
log() { echo "$(date '+%F %T') ensure: $1" >> "$ROOT/topgainer/ensure.log"; }

if ! pgrep -f "topgainer/watchdog_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/topgainer/watchdog_keepalive.sh" >/dev/null 2>&1 &
  log "watchdog_keepalive relanzado (pid $!)"
fi

if ! pgrep -x topgainer_alert >/dev/null && ! pgrep -f "topgainer/alert_bot.py" >/dev/null; then
  if [[ -x "$ROOT/topgainer/topgainer_alert" ]]; then
    nohup "$ROOT/topgainer/topgainer_alert" >>"$ROOT/topgainer/alert_bot.log" 2>&1 &
  else
    nohup "$PY" "$ROOT/topgainer/alert_bot.py" >>"$ROOT/topgainer/alert_bot.log" 2>&1 &
  fi
  log "alert bot relanzado (pid $!)"
fi

if ! pgrep -f "topgainer/claude_trader_loop.sh" >/dev/null; then
  nohup zsh "$ROOT/topgainer/claude_trader_loop.sh" >/dev/null 2>&1 &
  log "claude_trader_loop relanzado (pid $!)"
fi

if ! pgrep -f "topgainer/heartbeat.sh" >/dev/null; then
  nohup zsh "$ROOT/topgainer/heartbeat.sh" >/dev/null 2>&1 &
  log "heartbeat relanzado (pid $!)"
fi
