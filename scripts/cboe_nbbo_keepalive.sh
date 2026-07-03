#!/bin/zsh
cd "$(dirname "$0")/.."
# bid/ask de respaldo CBOE para las fichas (delayed, etiquetado; GO exige NBBO vivo).
LOG=logs/cboe_nbbo.log
mkdir -p logs
while true; do
  pkill -f "scripts/cboe_nbbo_sidecar.py" 2>/dev/null
  sleep 1
  ./venv/bin/python -u scripts/cboe_nbbo_sidecar.py >> $LOG 2>&1
  echo "$(date) sidecar salio; relanzando" >> $LOG
  sleep 60
done
