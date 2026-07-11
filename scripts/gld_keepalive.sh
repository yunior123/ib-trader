#!/bin/zsh
cd "$(dirname "$0")/.."
# GLD = TREND MODE (sweep walk-forward 90d 2026-07-10: OOS 30d +1.87% 25T/19W (vs MR +0.93%)).
# Reversion 1m en instrumentos calmados/eficientes no paga o paga con
# riesgo 7x mayor; trend monta el movimiento con stop chico y EOD plano.
export GLD_MODE=trend
export GLD_TREND_CUSUM=0.002
export GLD_TARGET=0.5
export GLD_STOP=0.4
export GLD_TRAIL_ATR=2
export GLD_MAX_DAY=2
export GLD_FLOOR=0.1
export GLD_SKIP_OPEN=15
export GLD_EOD_FORCE=1
export GLD_TIME_STOP_MIN=0
while true; do
  pkill -x gld_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read GLD" 2>/dev/null
  sleep 1
  ./gld_signal_bot >> gld_signals.log 2>&1
  echo "$(date) gld_signal_bot salio; relanzando" >> gld_signals.log
  sleep 30
done
