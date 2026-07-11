#!/bin/zsh
cd "$(dirname "$0")/.."
# params por-ticker via env ASML_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
# sweep walk-forward 90d 2026-07-10 (OOS +3.5% 20T) — validado OOS
export ASML_BB_STD=2.0
export ASML_RSI_OS=30
export ASML_VOL_MULT=1.2
export ASML_TARGET=4
export ASML_TRAIL_ATR=3
export ASML_STOP=3
export ASML_SKIP_OPEN=5
export ASML_TIME_STOP_MIN=240
# live: gate de spread NBBO + umbral whale (v3)
export ASML_SPREAD_MAX=0.3
export ASML_WHALE_USD=250000
while true; do
  pkill -x asml_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read ASML" 2>/dev/null
  sleep 1
  ./asml_signal_bot >> asml_signals.log 2>&1
  echo "$(date) asml_signal_bot salio; relanzando" >> asml_signals.log
  sleep 30
done
