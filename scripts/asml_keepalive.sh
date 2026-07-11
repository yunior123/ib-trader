#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 17T 14W WR82% +15.1% pf2.1 (OOS 73%)
export ASML_BB_STD=2.5
export ASML_RSI_OS=25
export ASML_VOL_MULT=1.2
export ASML_TARGET=4
export ASML_TRAIL_ATR=2
export ASML_STOP=4
export ASML_TIME_STOP_MIN=0
export ASML_SKIP_OPEN=5
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
