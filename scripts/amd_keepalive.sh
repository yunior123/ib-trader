#!/bin/zsh
cd "$(dirname "$0")/.."
# params por-ticker via env AMD_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
# sweep walk-forward 90d 2026-07-10 (OOS +7.3% 13T) — validado OOS
export AMD_BB_STD=2.0
export AMD_RSI_OS=25
export AMD_VOL_MULT=1.0
export AMD_TARGET=4
export AMD_TRAIL_ATR=3
export AMD_STOP=3
export AMD_SKIP_OPEN=5
export AMD_TIME_STOP_MIN=240
# live: gate de spread NBBO + umbral whale (v3)
export AMD_SPREAD_MAX=0.3
export AMD_WHALE_USD=250000
while true; do
  pkill -x amd_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read AMD" 2>/dev/null
  sleep 1
  ./amd_signal_bot >> amd_signals.log 2>&1
  echo "$(date) amd_signal_bot salio; relanzando" >> amd_signals.log
  sleep 30
done
