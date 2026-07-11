#!/bin/zsh
cd "$(dirname "$0")/.."
# TSM: sweep 90d dio OOS NEGATIVO en todo el grid -> defaults
# raro-limpio (BB3/RSI25, solo panico real). Regla: sin OOS+ no se shippea.
# params por-ticker via env TSM_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
export TSM_STOP=3
export TSM_SKIP_OPEN=5
export TSM_TIME_STOP_MIN=240
# MOTOR v3 CONFLUENCE (backtest 2026 completo, v3 OOS may-jul +10.9% 48T pf1.3 (baseline +0.4%));
# BB 50% (1m+15m) + RSI + VWAP + volumen + whales
export TSM_SCORE_MIN=0.72
export TSM_RSI_OS=35
export TSM_BB_STD=2.0
# live: gate de spread NBBO + umbral whale (v3)
export TSM_SPREAD_MAX=0.3
export TSM_WHALE_USD=250000
while true; do
  pkill -x tsm_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TSM" 2>/dev/null
  sleep 1
  ./tsm_signal_bot >> tsm_signals.log 2>&1
  echo "$(date) tsm_signal_bot salio; relanzando" >> tsm_signals.log
  sleep 30
done
