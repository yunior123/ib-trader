#!/bin/zsh
# whale_watch_keepalive.sh — garantiza EXACTAMENTE UN opt_whale_watch vivo (2026-07-21).
# Problema recurrente que arregla: el watcher moria entre healthchecks (3x/dia no basta)
# o se DUPLICABA (dos procesos de dias distintos con datos viejos). Idempotente:
#   - 0 procesos -> lo lanza
#   - 1 proceso  -> no hace nada
#   - 2+         -> mata los VIEJOS, conserva el mas nuevo
# Corre cada 5 min via launchd com.ibtrader.whalewatch. Señal-solamente.
cd "$(dirname "$0")/.." || exit 1
LOG=whale_keepalive.log

# solo en horario de mercado extendido (7:00-16:30 ET, lun-vie)
H=$(date +%H%M); DOW=$(date +%u)
if [ "$DOW" -gt 5 ] || [ "$H" -lt 0700 ] || [ "$H" -gt 1630 ]; then exit 0; fi
# respetar el modo sueño de la flota
[ -f data/fleet_sleep ] && exit 0

PIDS=($(pgrep -f "opt_whale_watch.py" | sort -n))
N=${#PIDS[@]}
if [ "$N" -eq 0 ]; then
  nohup ./venv/bin/python scripts/opt_whale_watch.py >> whale_watch_out.log 2>&1 &
  echo "$(date '+%F %T') relanzado (estaba muerto) pid $!" >> $LOG
  osascript -e 'display notification "opt_whale_watch relanzado (estaba muerto)" with title "🐋 keepalive ballenas" sound name "ProAlert"' 2>/dev/null
elif [ "$N" -gt 1 ]; then
  # matar todos menos el PID mas alto (el mas nuevo)
  KEEP=${PIDS[-1]}
  for P in ${PIDS[@]}; do
    [ "$P" != "$KEEP" ] && kill "$P" 2>/dev/null && echo "$(date '+%F %T') duplicado $P matado (conservo $KEEP)" >> $LOG
  done
fi
exit 0
