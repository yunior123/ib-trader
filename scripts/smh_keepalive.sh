#!/bin/zsh
cd "$(dirname "$0")/.."
# SMH bot (2026-07-16, flota semis). Tuning dia-de-gap-bajista (espejo INTC
# WR-70 cortos-trend); el backtest v6 semanal recalibrara con historia propia.
export SMH_BB_STD=3.0
export SMH_RSI_OS=35
export SMH_VOL_MULT=1.2
export SMH_SHORTS=1
export SMH_S_MODE=trend
export SMH_S_TREND_CUSUM=0.015
export SMH_S_TARGET=1.5
export SMH_S_STOP=4
export SMH_S_TRAIL=2
export SMH_S_TSTOP=120
export SMH_S_FLOOR=0.25
export SMH_QUAKE_BANNER=1
export SMH_QUAKE_MIN=0.05
export SMH_SPREAD_MAX=0.3
export SMH_WHALE_USD=250000
while true; do
  pkill -x smh_signal_bot 2>/dev/null
  sleep 1
  ./smh_signal_bot >> smh_signals.log 2>&1
  echo "$(date) smh_signal_bot salio; relanzando" >> smh_signals.log
  sleep 30
done
