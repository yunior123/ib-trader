#!/bin/bash
# fleet_consensus_keepalive.sh — mantiene vivo el daemon de MANADA.
# Era el unico daemon de senal sin keepalive: si moria a media sesion, nadie lo
# relanzaba y la flota se quedaba sin denominador (2026-07-27).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
while true; do
  if ! pgrep -f "scripts/fleet_consensus.py --daemon" >/dev/null 2>&1; then
    nohup ./venv/bin/python -u scripts/fleet_consensus.py --daemon \
      >> "$ROOT/logs/fleet_consensus_py.log" 2>&1 &
    echo "$(date) fleet_consensus.py relanzado" >> "$ROOT/logs/fleet_consensus_py.log"
  fi
  sleep 15
done
