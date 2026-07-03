#!/bin/zsh
cd "$(dirname "$0")/.."
# Cinta de flujo UW de la FLOTA (sustituto de opt_whale_watch mientras IBKR esta prohibido).
LOG=logs/uw_fleet_flow.log
mkdir -p logs
FAILS=0
while true; do
  pkill -f "scripts/uw_fleet_flow.py" 2>/dev/null
  sleep 1
  ./venv/bin/python -u scripts/uw_fleet_flow.py >> $LOG 2>&1
  RC=$?
  FAILS=$((FAILS+1))
  echo "$(date) uw_fleet_flow salio (rc=$RC); relanzando (fallo $FAILS)" >> $LOG
  if (( FAILS % 3 == 0 )); then
    ./venv/bin/python scripts/notify_short.py "⚠ UW FLOW" \
      "motor caido ${FAILS} veces (rc=$RC) — cinta de flota sin vigilancia" 2>/dev/null
  fi
  sleep 60
done
