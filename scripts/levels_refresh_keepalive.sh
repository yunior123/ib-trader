#!/bin/zsh
cd "$(dirname "$0")/.."
while true; do
  pkill -f "scripts/levels_refresh_daemon.py" 2>/dev/null
  sleep 1
  ./venv/bin/python -u scripts/levels_refresh_daemon.py >> logs/levels_refresh.log 2>&1
  echo "$(date) levels_refresh_daemon salio; relanzando" >> logs/levels_refresh.log
  sleep 60
done
