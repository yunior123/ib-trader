#!/bin/zsh
cd "$(dirname "$0")/.."
# MU bot (2026-07-16, flota semis). Tuning dia-de-gap-bajista (espejo INTC
# WR-70 cortos-trend); el backtest v6 semanal recalibrara con historia propia.
export MU_BB_STD=3.0
export MU_RSI_OS=35
export MU_VOL_MULT=1.2
export MU_SHORTS=1
export MU_S_MODE=trend
export MU_S_TREND_CUSUM=0.015
export MU_S_TARGET=1.5
export MU_S_STOP=4
export MU_S_TRAIL=2
export MU_S_TSTOP=120
export MU_S_FLOOR=0.25
export MU_QUAKE_BANNER=1
export MU_QUAKE_MIN=0.05
export MU_SPREAD_MAX=0.3
export MU_WHALE_USD=250000
while true; do
  pkill -x mu_signal_bot 2>/dev/null
  sleep 1
  bots/mu_signal_bot >> logs/mu_signals.log 2>&1
  echo "$(date) mu_signal_bot salio; relanzando" >> logs/mu_signals.log
  sleep 30
done
