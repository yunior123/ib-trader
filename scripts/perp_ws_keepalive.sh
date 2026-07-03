#!/bin/zsh
# Perpetuos 24/7: el socket es primario y se relanza tras cualquier corte del venue.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
while true; do
  ./venv/bin/python scripts/perp_ws_bridge.py >> logs/perp_ws_bridge.log 2>&1
  RC=$?
  echo "$(date) perp_ws_bridge terminó rc=$RC; reconecto en 5s" >> logs/perp_ws_bridge.log
  sleep 5
done
