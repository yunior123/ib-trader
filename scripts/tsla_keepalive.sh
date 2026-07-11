#!/bin/zsh
cd "$(dirname "$0")/.."
# params por-ticker (sweep 30d bars reales 2026-07-10: 1 trade 1W +1.5% (baseline 0 trades));
# re-tunear con el sweep del scratchpad tras cambios de regimen
export TSLA_BB_STD=3.0
export TSLA_RSI_OS=25
export TSLA_VOL_MULT=1.0
export TSLA_TARGET=4
export TSLA_TRAIL_ATR=3
export TSLA_STOP=1.5
export TSLA_SKIP_OPEN=5
# live: gate de spread NBBO + umbral whale (v3)
export TSLA_SPREAD_MAX=0.3
export TSLA_WHALE_USD=250000
while true; do
  pkill -x tsla_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TSLA" 2>/dev/null
  sleep 1
  ./tsla_signal_bot >> tsla_signals.log 2>&1
  echo "$(date) tsla_signal_bot salio; relanzando" >> tsla_signals.log
  sleep 30
done
