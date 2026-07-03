#!/bin/zsh
cd "$(dirname "$0")/.."
# NQ/ES + Corea + sentimiento X -> data/overnight_ctx.json (factor overnight de la flecha). Señal-solamente.
while true; do
  pkill -f "scripts/overnight_feed.py" 2>/dev/null
  sleep 1
  ./venv/bin/python -u scripts/overnight_feed.py >> logs/overnight_feed.log 2>&1
  echo "$(date) overnight_feed salio; relanzando" >> logs/overnight_feed.log
  sleep 60
done
