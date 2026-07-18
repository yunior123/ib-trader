#!/bin/zsh
cd "$(dirname "$0")/.."
# opt_sentinel keepalive (2026-07-16). SEÑAL-SOLAMENTE.
while true; do
  pkill -f "scripts/opt_sentinel.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/opt_sentinel.py >> opt_sentinel.log 2>&1
  echo "$(date) opt_sentinel salio; relanzando" >> opt_sentinel.log
  sleep 20
done
