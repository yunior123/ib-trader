#!/bin/zsh
cd "$(dirname "$0")/.."
# SPCX = TREND MODE (estudio 30d 2026-07-10): el dip-engine confirmo 0% en
# SPCX (waterfalls sin reclaim, follow-through negativo); trend +17.2% 16/18W
# in-sample CON stops reales. OOS corto (ticker joven) -> rieles duros y
# scorecard semanal; revisar en 2 semanas.
export SPCX_MODE=trend
export SPCX_TRAIL_ATR=2
export SPCX_STOP=2
export SPCX_TARGET=6
export SPCX_FLOOR=0.5
export SPCX_EOD_FORCE=1
export SPCX_MAX_DAY=2
export SPCX_SKIP_OPEN=15
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
