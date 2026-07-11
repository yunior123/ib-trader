#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 69T 60W WR87% +37.0% pf1.5 (OOS 84% +15.7%)
export AMD_BB_STD=2.0
export AMD_RSI_OS=30
export AMD_VOL_MULT=1.2
export AMD_TARGET=4
export AMD_TRAIL_ATR=3
export AMD_STOP=8
export AMD_TIME_STOP_MIN=0
export AMD_SKIP_OPEN=5
# LADO CORTO v4 (2026-07-11 'both directions'): cortos FULL26 67T 47W WR70% +16.8% pf1.5 (OOS 69%)
export AMD_SHORTS=1
export AMD_S_TARGET=4
export AMD_S_STOP=2
export AMD_S_TRAIL=3
export AMD_S_TSTOP=0
export AMD_S_FLOOR=0.5
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
