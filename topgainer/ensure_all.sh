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
# SIGNAL-ONLY MODE (Yunior 2026-07-10): data/topgainer/signal_only present ->
# topgainer es el 5to bot de SEÑALES: nada de trading, ni Claude loop, ni LIVE.
SIGNAL_ONLY=0; [[ -f "$ROOT/data/topgainer/signal_only" ]] && SIGNAL_ONLY=1
if [[ $SIGNAL_ONLY -eq 1 ]]; then
  export TOPGAINER_LIVE=0
else
  export TOPGAINER_LIVE="${TOPGAINER_LIVE:-1}"
fi
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

if [[ $SIGNAL_ONLY -eq 1 ]]; then
  # señales solamente: el loop de trading no debe existir; matarlo si revivio
  if pgrep -f "topgainer/claude_trader_loop.sh" >/dev/null; then
    pkill -f "topgainer/claude_trader_loop.sh"
    log "signal_only: claude_trader_loop matado"
  fi
elif ! pgrep -f "topgainer/claude_trader_loop.sh" >/dev/null; then
  nohup zsh "$ROOT/topgainer/claude_trader_loop.sh" >/dev/null 2>&1 &
  log "claude_trader_loop relanzado (pid $!)"
fi

# ws daemon (C++): LA conexion Alpaca (limite 1/cuenta) — bars 1m nativos de
# NOK+SPCX+DRAM+TSLA a data/bars_*.txt; los bots los leen via "alpaca_ws_bridge read SYM"

# daemon IBKR de flota (orden 2026-07-11 "ready for ibkr, alpaca fallback"):
# SIP bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt; auto-activa al comprar
# el sub ($10 SIP bundle, >= USD 500 equity). Reader C++ preferencia+fallback.
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup "$ROOT/venv/bin/python" "$ROOT/scripts/"ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO >>"$ROOT/bridge_ibkr_fleet.log" 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >>"$ROOT/fleet_autostart.log"
fi

if ! pgrep -f "alpaca_ws_bridge NOK" >/dev/null && [[ -x "$ROOT/alpaca_ws_bridge" ]]; then
  nohup "$ROOT/alpaca_ws_bridge" NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO >>"$ROOT/ws_daemon.log" 2>&1 &
  log "alpaca_ws_bridge daemon relanzado (pid $!)"
fi

# email/telegram ELIMINADOS (Yunior 2026-07-10): solo Mac, fleet_notify.h C++

if ! pgrep -f "topgainer/heartbeat.sh" >/dev/null; then
  nohup zsh "$ROOT/topgainer/heartbeat.sh" >/dev/null 2>&1 &
  log "heartbeat relanzado (pid $!)"
fi
