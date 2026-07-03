#!/bin/zsh
cd "$(dirname "$0")/.."
# vigia de ballenas de opciones (P/C flujo flota, 2026-07-20). Señal-solamente.
while true; do
  pkill -f "scripts/opt_whale_watch.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/opt_whale_watch.py >> logs/opt_whale.log 2>&1
  echo "$(date) opt_whale_watch salio; relanzando" >> logs/opt_whale.log
  sleep 60
done
