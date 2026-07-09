#!/bin/zsh
cd "$(dirname "$0")/.."
while true; do
  pkill -x nok_signal_bot 2>/dev/null
  pkill -f nok_bar_bridge 2>/dev/null
  sleep 1
  ./nok_signal_bot >> nok_signals.log 2>&1
  echo "$(date) nok_signal_bot salio; relanzando en 30s" >> nok_signals.log
  sleep 30
done
