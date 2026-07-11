#!/bin/zsh
cd "$(dirname "$0")/.."
# params por-ticker via env INTC_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
# sweep walk-forward 90d 2026-07-10 (OOS +14.7% 12T/9W) — validado OOS
export INTC_BB_STD=2.5
export INTC_RSI_OS=30
export INTC_VOL_MULT=1.2
export INTC_TARGET=4
export INTC_TRAIL_ATR=3
export INTC_STOP=3
export INTC_SKIP_OPEN=5
export INTC_TIME_STOP_MIN=240
while true; do
  pkill -x intc_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read INTC" 2>/dev/null
  sleep 1
  ./intc_signal_bot >> intc_signals.log 2>&1
  echo "$(date) intc_signal_bot salio; relanzando" >> intc_signals.log
  sleep 30
done
