#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND FULL26 138T 105W WR76% +36.3% pf2.8 (OOS 72% +15.4%)
export TSLA_MODE=trend
export TSLA_TREND_CUSUM=0.008
export TSLA_TARGET=2.0
export TSLA_STOP=0.8
export TSLA_TRAIL_ATR=3
export TSLA_MAX_DAY=2
export TSLA_FLOOR=0.1
export TSLA_SKIP_OPEN=15
export TSLA_EOD_FORCE=1
export TSLA_TIME_STOP_MIN=0
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
