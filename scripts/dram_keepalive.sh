#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 59T 43W WR73% +33.8% pf1.8 (config 07-10 conservado: gana en dinero y cumple 70)
export DRAM_BB_STD=2.5
export DRAM_RSI_OS=35
export DRAM_VOL_MULT=1.2
export DRAM_TARGET=6
export DRAM_TRAIL_ATR=3
export DRAM_STOP=3
export DRAM_TIME_STOP_MIN=240
export DRAM_SKIP_OPEN=0
# live: gate de spread NBBO + umbral whale (v3)
export DRAM_SPREAD_MAX=0.5
export DRAM_WHALE_USD=100000
while true; do
  pkill -x dram_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read DRAM" 2>/dev/null
  sleep 1
  ./dram_signal_bot >> dram_signals.log 2>&1
  echo "$(date) dram_signal_bot salio; relanzando" >> dram_signals.log
  sleep 30
done
