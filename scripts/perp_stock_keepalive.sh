#!/bin/zsh
# perp_stock_keepalive.sh -- perp_stock_fetch.py es one-shot; este loop lo
# respaldo REST solamente si el WS deja de latir. El WS ya entrega precio, BBO, volumen y OI;
# dos escritores concurrentes hacian que REST delayed pisara un snapshot WebSocket fresco.
cd "$(dirname "$0")/.." || exit 1
while true; do
  if ./venv/bin/python - <<'PY' >/dev/null 2>&1
import json,time
d=json.load(open("data/perp_ws_state.json"))
raise SystemExit(0 if time.time()-float(d["latido"]) <= 20 else 1)
PY
  then
    sleep 10
  else
    echo "$(date) WS perpetuos rancio/caido -> una pasada REST de respaldo" >> logs/perp_stock_fetch.log
    ./venv/bin/python scripts/perp_stock_fetch.py >> logs/perp_stock_fetch.log 2>&1
    sleep 30
  fi
done
