#!/bin/zsh
# dram_signal_bot (C++) 24/5 — instancia UNICA, limpia huerfanos en cada ciclo
cd "$(dirname "$0")/.."
# params por-ticker (sweep 30d bars reales 2026-07-10: 20 trades 16W +15.7% (baseline: 1 trade -3.1%));
# re-tunear con el sweep del scratchpad tras cambios de regimen
export DRAM_BB_STD=2.5
export DRAM_RSI_OS=35
export DRAM_VOL_MULT=1.2
export DRAM_TARGET=6
export DRAM_TRAIL_ATR=3
export DRAM_STOP=3
export DRAM_TIME_STOP_MIN=240
# live: gate de spread NBBO + umbral whale (v3)
export DRAM_SPREAD_MAX=0.5
export DRAM_WHALE_USD=100000
while true; do
  pkill -x dram_signal_bot 2>/dev/null      # nunca dos motores
  pkill -f "alpaca_ws_bridge read DRAM" 2>/dev/null      # nunca bridges huerfanos
  sleep 1
  ./dram_signal_bot >> dram_signals.log 2>&1
  echo "$(date) dram_signal_bot salio; relanzando en 30s" >> dram_signals.log
  sleep 30
done
