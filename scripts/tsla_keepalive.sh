#!/bin/zsh
cd "$(dirname "$0")/.."
while true; do
  pkill -x tsla_signal_bot 2>/dev/null
  pkill -f "ws_bar_bridge.py .* tsla" 2>/dev/null
  sleep 1
  ./tsla_signal_bot >> tsla_signals.log 2>&1
  echo "$(date) tsla_signal_bot salio; relanzando" >> tsla_signals.log
  sleep 30
done
