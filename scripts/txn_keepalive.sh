#!/bin/zsh
cd "$(dirname "$0")/.."
# TXN: sweep 90d dio OOS NEGATIVO en todo el grid -> defaults
# raro-limpio (BB3/RSI25, solo panico real). Regla: sin OOS+ no se shippea.
# params por-ticker via env TXN_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
export TXN_STOP=3
export TXN_SKIP_OPEN=5
export TXN_TIME_STOP_MIN=240
# live: gate de spread NBBO + umbral whale (v3)
export TXN_SPREAD_MAX=0.3
export TXN_WHALE_USD=250000
while true; do
  pkill -x txn_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TXN" 2>/dev/null
  sleep 1
  ./txn_signal_bot >> txn_signals.log 2>&1
  echo "$(date) txn_signal_bot salio; relanzando" >> txn_signals.log
  sleep 30
done
