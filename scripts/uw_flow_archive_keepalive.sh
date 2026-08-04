#!/bin/zsh
cd "$(dirname "$0")/.."
# Archivador forward-only de las series intradia de UW. Cada dia sin archivar es un dia que
# las alertas de flujo NO podran validar nunca: UW no sirve la serie intradia hacia atras.
LOG=logs/uw_flow_archive.log
mkdir -p logs
FAILS=0
while true; do
  pkill -f "scripts/uw_flow_archive.py" 2>/dev/null
  sleep 1
  ./venv/bin/python -u scripts/uw_flow_archive.py >> $LOG 2>&1
  RC=$?
  FAILS=$((FAILS+1))
  echo "$(date) uw_flow_archive salio (rc=$RC); relanzando (fallo $FAILS)" >> $LOG
  if (( FAILS % 3 == 0 )); then
    ./venv/bin/python scripts/notify_short.py "⚠ ARCHIVO UW" \
      "caido ${FAILS} veces (rc=$RC) — la sesion de hoy no se esta archivando" 2>/dev/null
  fi
  sleep 60
done
