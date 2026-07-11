#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): v3 FULL26 30T 26W WR87% +17.1% pf1.5 (OOS 86%)
export TSM_SCORE_MIN=0.72
export TSM_RSI_OS=35
export TSM_BB_STD=2.0
export TSM_TARGET=4
export TSM_TRAIL_ATR=3
export TSM_STOP=8
export TSM_TIME_STOP_MIN=0
export TSM_SKIP_OPEN=5
# live: gate de spread NBBO + umbral whale (v3)
export TSM_SPREAD_MAX=0.3
export TSM_WHALE_USD=250000
while true; do
  pkill -x tsm_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TSM" 2>/dev/null
  sleep 1
  ./tsm_signal_bot >> tsm_signals.log 2>&1
  echo "$(date) tsm_signal_bot salio; relanzando" >> tsm_signals.log
  sleep 30
done
