#!/bin/zsh
cd "$(dirname "$0")/.."
# AAPL: sweep 90d dio OOS NEGATIVO en todo el grid -> defaults
# raro-limpio (BB3/RSI25, solo panico real). Regla: sin OOS+ no se shippea.
# params por-ticker via env AAPL_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
export AAPL_STOP=3
export AAPL_SKIP_OPEN=5
export AAPL_TIME_STOP_MIN=240
while true; do
  pkill -x aapl_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read AAPL" 2>/dev/null
  sleep 1
  ./aapl_signal_bot >> aapl_signals.log 2>&1
  echo "$(date) aapl_signal_bot salio; relanzando" >> aapl_signals.log
  sleep 30
done
