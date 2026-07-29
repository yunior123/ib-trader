#!/bin/zsh
cd "$(dirname "$0")/.."
# SOX index feed keepalive (2026-07-16). Nivel del indice para sirenas.
while true; do
  pkill -f "scripts/sox_index_feed.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/sox_index_feed.py >> logs/sox_feed.log 2>&1
  echo "$(date) sox_feed salio; relanzando" >> logs/sox_feed.log
  sleep 30
done
