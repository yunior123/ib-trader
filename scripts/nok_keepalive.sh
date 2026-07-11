#!/bin/zsh
cd "$(dirname "$0")/.."
# params por-ticker (sweep 30d bars reales 2026-07-10: 5 trades 3W +1.5% (baseline +0.2%));
# re-tunear con el sweep del scratchpad tras cambios de regimen
export NOK_TARGET=6
export NOK_TRAIL_ATR=2
export NOK_STOP=3
export NOK_TIME_STOP_MIN=240
# MOTOR v3 CONFLUENCE (backtest 2026 completo, v3 OOS may-jul +2.25% 59T (baseline -7.2%));
# BB 50% (1m+15m) + RSI + VWAP + volumen + whales
export NOK_SCORE_MIN=0.72
export NOK_RSI_OS=25
export NOK_BB_STD=2.5
# live: gate de spread NBBO + umbral whale (v3)
export NOK_SPREAD_MAX=0.3
export NOK_WHALE_USD=150000
while true; do
  pkill -x nok_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read NOK" 2>/dev/null
  sleep 1
  ./nok_signal_bot >> nok_signals.log 2>&1
  echo "$(date) nok_signal_bot salio; relanzando en 30s" >> nok_signals.log
  sleep 30
done
