#!/bin/zsh
cd "$(dirname "$0")/.."
# finviz_scout keepalive (2026-07-17). Datos Finviz Elite premarket/RTH
# (short float, gap, rel vol, earnings, target/recom) -> data/finviz_*.txt.
# Señal-solamente. Lanzado por fleet_keepalive_start.sh (respeta fleet_sleep).
while true; do
  pkill -x finviz_scout 2>/dev/null
  sleep 1
  bin/finviz_scout >> logs/finviz_scout.log 2>&1
  echo "$(date) finviz_scout salio; relanzando" >> logs/finviz_scout.log
  sleep 30
done
