#!/bin/zsh
cd "$(dirname "$0")/.."
# cinta de ballenas UW -> data/uw_flow_tape.json (cockpit wgt-flow). Señal-solamente.
while true; do
  pkill -f "scripts/uw_flow_tape.py" 2>/dev/null
  sleep 1
  ./venv/bin/python -u scripts/uw_flow_tape.py >> uw_flow_tape.log 2>&1
  echo "$(date) uw_flow_tape salio; relanzando" >> uw_flow_tape.log
  sleep 60
done
