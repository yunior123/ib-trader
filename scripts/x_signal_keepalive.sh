#!/bin/zsh
cd "$(dirname "$0")/.."
# x_signal_poster keepalive (2026-07-21): postea en X señales fuertes de la
# flota + combos multi-ticker. SEÑAL-SOLAMENTE, ledger compartido 30/dia $4/mes.
while true; do
  pkill -f "scripts/x_signal_poster.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/x_signal_poster.py >> logs/x_signal_poster.log 2>&1
  echo "$(date) x_signal_poster salio; relanzando" >> logs/x_signal_poster.log
  sleep 60
done
