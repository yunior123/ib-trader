#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): calm-MR: OOS WR79% +3.3%; full-year 61% — UNICO bajo 70 (ningun motor lo alcanzo)
export GLD_BB_STD=2.0
export GLD_RSI_OS=25
export GLD_VOL_MULT=1.0
export GLD_TARGET=1.2
export GLD_FLOOR=0.25
export GLD_TRAIL_ATR=3
export GLD_STOP=0.75
export GLD_TIME_STOP_MIN=120
export GLD_EOD_FORCE=1
export GLD_SKIP_OPEN=5
# LADO CORTO optimizado (sweep independiente 2026-07-11): cortos trend FULL26 190T 142W WR75% +32.0% pf4.3 (antes +2.4%)
export GLD_SHORTS=1
export GLD_S_MODE=trend
export GLD_S_TREND_CUSUM=0.008
export GLD_S_TARGET=1.0
export GLD_S_STOP=0.8
export GLD_S_TRAIL=2
export GLD_S_TSTOP=120
export GLD_S_FLOOR=0.1
# live: gate de spread NBBO + umbral whale (v3)
export GLD_SPREAD_MAX=0.3
export GLD_WHALE_USD=250000
while true; do
  pkill -x gld_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read GLD" 2>/dev/null
  sleep 1
  ./gld_signal_bot >> gld_signals.log 2>&1
  echo "$(date) gld_signal_bot salio; relanzando" >> gld_signals.log
  sleep 30
done
