#!/bin/zsh
cd "$(dirname "$0")/.."
while true; do
  pkill -x spcx_signal_bot 2>/dev/null
  pkill -f "ws_bar_bridge.py .* spcx" 2>/dev/null
  sleep 1
  ./spcx_signal_bot >> spcx_signals.log 2>&1
  echo "$(date) spcx_signal_bot salio; relanzando" >> spcx_signals.log
  sleep 30
done
