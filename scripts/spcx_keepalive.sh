#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND vida 20T 19W WR95% +19.2% pf12.2
export SPCX_MODE=trend
export SPCX_TREND_CUSUM=0.002
export SPCX_TARGET=2.0
export SPCX_STOP=1.5
export SPCX_TRAIL_ATR=3
export SPCX_MAX_DAY=2
export SPCX_FLOOR=0.1
export SPCX_SKIP_OPEN=15
export SPCX_EOD_FORCE=1
export SPCX_TIME_STOP_MIN=0
# live: gate de spread NBBO + umbral whale (v3)
export SPCX_SPREAD_MAX=0.3
export SPCX_WHALE_USD=100000
while true; do
  pkill -x spcx_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read SPCX" 2>/dev/null
  sleep 1
  ./spcx_signal_bot >> spcx_signals.log 2>&1
  echo "$(date) spcx_signal_bot salio; relanzando" >> spcx_signals.log
  sleep 30
done
