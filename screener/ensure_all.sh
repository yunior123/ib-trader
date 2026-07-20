#!/bin/zsh
# ensure_all.sh — supervisor del sistema screener ("working non stop", Yunior
# 2026-07-10). Relanza SOLO los componentes muertos; no toca nada vivo (a
# diferencia de start_all.sh, que hace pkill+restart completo — usar ese solo
# para arranques manuales limpios). launchd lo corre al login y cada 2 min
# (com.ibtrader.screener RunAtLoad + StartInterval). Idempotente via pgrep.
#
# LEY SUPREMA (Yunior 2026-07-16): SEÑAL-SOLAMENTE, SIEMPRE. Sin flags de
# armado, sin SCREENER_LIVE, sin loops de trading, sin watchdog de posiciones —
# ejecutores retirados a backup/execution_retired_2026-07-16/.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
log() { echo "$(date '+%F %T') ensure: $1" >> "$ROOT/screener/ensure.log"; }

if ! pgrep -x screener_alert >/dev/null && ! pgrep -f "screener/alert_bot.py" >/dev/null; then
  if [[ -x "$ROOT/screener/screener_alert" ]]; then
    ALERT_POLL=1 nohup "$ROOT/screener/screener_alert" >>"$ROOT/screener/alert_bot.log" 2>&1 &   # poll 1s (orden 2026-07-15 blazing fast)
  else
    nohup "$PY" "$ROOT/screener/alert_bot.py" >>"$ROOT/screener/alert_bot.log" 2>&1 &
  fi
  log "alert bot relanzado (pid $!)"
fi

# daemon IBKR de flota: SIP bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt.
# Solo lectura de mercado — cero ordenes. 17 syms (CON SKHY).
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup "$ROOT/venv/bin/python" "$ROOT/scripts/"ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO SKHY EWY >>"$ROOT/bridge_ibkr_fleet.log" 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >>"$ROOT/fleet_autostart.log"
fi

# ALPACA RETIRADO (orden Yunior 2026-07-15 "no alpaca, only ibkr"): el daemon
# ws IEX ya no se lanza — flota 100%% IBKR (ibkr_bar_bridge); screener_alert
# usa Finnhub REST para quotes. Revivir: descomentar este bloque.
if false && ! pgrep -f "alpaca_ws_bridge NOK" >/dev/null && [[ -x "$ROOT/alpaca_ws_bridge" ]]; then
  nohup "$ROOT/alpaca_ws_bridge" NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO >>"$ROOT/ws_daemon.log" 2>&1 &
  log "alpaca_ws_bridge daemon relanzado (pid $!)"
fi

# email/telegram ELIMINADOS (Yunior 2026-07-10): solo Mac, fleet_notify.h C++

if ! pgrep -f "screener/heartbeat.sh" >/dev/null; then
  nohup zsh "$ROOT/screener/heartbeat.sh" >/dev/null 2>&1 &
  log "heartbeat relanzado (pid $!)"
fi
