#!/bin/zsh
# start_all.sh — arranque limpio del sistema screener (pkill + relaunch).
# LEY SUPREMA (Yunior 2026-07-16): SEÑAL-SOLAMENTE. Este sistema JAMAS opera
# ordenes — ejecutores retirados a backup/execution_retired_2026-07-16/.
# Componentes (cada uno independiente, restart-safe):
#   screener_alert (C++)   -> señales de breakout del watchlist (banner Mac)
#   ibkr_bar_bridge daemon -> bars 1m + NBBO de la flota (datos, solo lectura)
#   heartbeat.sh           -> beep por minuto (prueba de vida)
# Scanner corre aparte a las 6 AM (launchd) o a demanda.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

echo "== top-gainer system (SEÑAL-SOLAMENTE, ley 2026-07-16) =="

pkill -f "screener/alert_bot.py" 2>/dev/null
pkill -x screener_alert 2>/dev/null
pkill -f "screener/heartbeat.sh" 2>/dev/null
sleep 1

PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
# alert bot: C++ primary (avoid python — Yunior 2026-07-09), python fallback
if [[ -x "$ROOT/screener/screener_alert" ]]; then
  ALERT_POLL=1 nohup "$ROOT/screener/screener_alert" >>"$ROOT/screener/alert_bot.log" 2>&1 &   # poll 1s (orden 2026-07-15 blazing fast)
else
  nohup "$PY" "$ROOT/screener/alert_bot.py" >>"$ROOT/screener/alert_bot.log" 2>&1 &
fi
echo "alert_bot pid $!"

# daemon IBKR de flota: SIP bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt.
# Solo lectura de mercado — cero ordenes. 17 syms (CON SKHY).
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup "$ROOT/venv/bin/python" "$ROOT/scripts/"ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO SKHY EWY >>"$ROOT/bridge_ibkr_fleet.log" 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >>"$ROOT/fleet_autostart.log"
fi


nohup zsh "$ROOT/screener/heartbeat.sh" >/dev/null 2>&1 &
echo "heartbeat pid $! (beeps every minute so you know it's alive)"
echo "up. logs: screener/*.log  | status: $PY screener/state.py status"
