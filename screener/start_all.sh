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

# --- PORTERO HORARIO (Yunior 2026-07-25) ---
# Ventana de la flota: domingo 20:00 -> viernes 20:00 hora de Toronto. Fuera de ahi, muerto.
# Este arranque es MANUAL, asi que el escape de testing es explicito y se anuncia solo:
#   FLEET_FORCE=1 zsh screener/start_all.sh
# bin/ primero, raiz como respaldo (ver ensure_all.sh: apuntar solo a la raiz dejaba el
# portero "AUSENTE" para siempre tras la mudanza de binarios).
FLEET_HOURS="$ROOT/bin/fleet_hours"; [[ -x "$FLEET_HOURS" ]] || FLEET_HOURS="$ROOT/fleet_hours"
if [[ -x "$FLEET_HOURS" ]]; then
  if ! "$FLEET_HOURS" >/dev/null 2>&1; then
    "$FLEET_HOURS" --why 2>&1 | head -3
    echo "NO arranco nada. Para probar fuera de horario: FLEET_FORCE=1 zsh screener/start_all.sh"
    exit 0
  fi
else
  echo "🔴 PORTERO AUSENTE ($FLEET_HOURS). Compila con scripts/build_fleet_hours.sh — no arranco nada."
  exit 1
fi

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
# Solo lectura de mercado — cero ordenes.
# SIMBOLOS DE data/fleet.txt (fuente unica). Aqui habia la MISMA lista escrita a mano de 18
# simbolos que en ensure_all.sh — sin SPY, sin SMH, sin MU, y con SLV/CPER/USO retirados.
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  FLEET_SYMS="$(cat "$ROOT/data/fleet.txt" 2>/dev/null)"
  if [[ -z "$FLEET_SYMS" ]]; then
    echo "🔴 data/fleet.txt vacio o ilegible -> NO lanzo el bridge"
  else
    nohup "$ROOT/venv/bin/python" "$ROOT/scripts/"ibkr_bar_bridge.py --daemon ${=FLEET_SYMS} >>"$ROOT/bridge_ibkr_fleet.log" 2>&1 &
    echo "$(date) fleet: ibkr fleet daemon lanzado por start_all (pid $!) con $(echo $FLEET_SYMS | wc -w | tr -d ' ') simbolos de data/fleet.txt" >>"$ROOT/fleet_autostart.log"
  fi
fi


nohup zsh "$ROOT/screener/heartbeat.sh" >/dev/null 2>&1 &
echo "heartbeat pid $! (beeps every minute so you know it's alive)"
echo "up. logs: screener/*.log  | status: $PY screener/state.py status"
