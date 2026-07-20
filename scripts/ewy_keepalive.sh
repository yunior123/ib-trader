#!/bin/zsh
cd "$(dirname "$0")/.."
# EWY bot (2026-07-16, flota semis). Tuning dia-de-gap-bajista (espejo INTC
# WR-70 cortos-trend); el backtest v6 semanal recalibrara con historia propia.
export EWY_BB_STD=3.0
export EWY_RSI_OS=35
export EWY_VOL_MULT=1.2
export EWY_SHORTS=1
export EWY_S_MODE=trend
export EWY_S_TREND_CUSUM=0.015
export EWY_S_TARGET=1.5
export EWY_S_STOP=4
export EWY_S_TRAIL=2
export EWY_S_TSTOP=120
export EWY_S_FLOOR=0.25
export EWY_QUAKE_BANNER=1
export EWY_QUAKE_MIN=0.05
export EWY_SPREAD_MAX=0.3
export EWY_WHALE_USD=250000
while true; do
  pkill -x ewy_signal_bot 2>/dev/null
  sleep 1
  ./ewy_signal_bot >> ewy_signals.log 2>&1
  echo "$(date) ewy_signal_bot salio; relanzando" >> ewy_signals.log
  sleep 30
done
