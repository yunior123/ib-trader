#!/bin/zsh
cd "$(dirname "$0")/.."
# QQQ = TREND MODE (sweep walk-forward 90d 2026-07-10: OOS 30d +1.61% 33T/25W, stop 0.4% (vs MR wide +1.8% con stop 3%)).
# Reversion 1m en instrumentos calmados/eficientes no paga o paga con
# riesgo 7x mayor; trend monta el movimiento con stop chico y EOD plano.
export QQQ_MODE=trend
export QQQ_TREND_CUSUM=0.002
export QQQ_TARGET=1.0
export QQQ_STOP=0.4
export QQQ_TRAIL_ATR=2
export QQQ_MAX_DAY=2
export QQQ_FLOOR=0.1
export QQQ_SKIP_OPEN=15
export QQQ_EOD_FORCE=1
export QQQ_TIME_STOP_MIN=0
# live: gate de spread NBBO + umbral whale (v3)
export QQQ_SPREAD_MAX=0.3
export QQQ_WHALE_USD=250000
while true; do
  pkill -x qqq_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read QQQ" 2>/dev/null
  sleep 1
  ./qqq_signal_bot >> qqq_signals.log 2>&1
  echo "$(date) qqq_signal_bot salio; relanzando" >> qqq_signals.log
  sleep 30
done
