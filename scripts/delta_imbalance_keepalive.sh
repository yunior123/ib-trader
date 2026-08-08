#!/bin/zsh
# VETO de divergencia de delta acumulado: una pasada por minuto, solo dentro de la ventana
# de la flota. SEÑAL-SOLAMENTE, sin voz. Escribe data/delta_imbalance.json.
cd "$(dirname "$0")/.."
LOG=logs/delta_imbalance.log
mkdir -p logs
FAILS=0
while true; do
  if ./bin/fleet_hours >/dev/null 2>&1; then
    ./bin/delta_imbalance --quiet >> $LOG 2>&1
    RC=$?
    if [ $RC -ne 0 ]; then
      FAILS=$((FAILS+1))
      echo "$(date) delta_imbalance rc=$RC (fallo $FAILS)" >> $LOG
      # rc=3 = sin calibracion medida: el veto NO se puede afirmar y hay que decirlo
      if (( FAILS % 10 == 0 )); then
        ./venv/bin/python scripts/notify_short.py "⚠ DELTA IMBALANCE" \
          "el veto de divergencia lleva ${FAILS} fallos (rc=$RC)" 2>/dev/null
      fi
    else
      FAILS=0
    fi
  fi
  sleep 60
done
