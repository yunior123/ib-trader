#!/bin/zsh
cd "$(dirname "$0")/.."
# NVDA: sweep 90d dio OOS NEGATIVO en todo el grid -> defaults
# raro-limpio (BB3/RSI25, solo panico real). Regla: sin OOS+ no se shippea.
# params por-ticker via env NVDA_* (defaults del motor hasta que el sweep
# walk-forward los valide; regla: nada se shippea sin OOS positivo)
export NVDA_STOP=3
export NVDA_SKIP_OPEN=5
export NVDA_TIME_STOP_MIN=240
# MOTOR v3 CONFLUENCE (backtest 2026 completo, v3 OOS may-jul +8.0% 50T pf1.4 (baseline muerto; WR 54%));
# BB 50% (1m+15m) + RSI + VWAP + volumen + whales
export NVDA_SCORE_MIN=0.65
export NVDA_RSI_OS=25
export NVDA_BB_STD=2.0
# live: gate de spread NBBO + umbral whale (v3)
export NVDA_SPREAD_MAX=0.3
export NVDA_WHALE_USD=250000
while true; do
  pkill -x nvda_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read NVDA" 2>/dev/null
  sleep 1
  ./nvda_signal_bot >> nvda_signals.log 2>&1
  echo "$(date) nvda_signal_bot salio; relanzando" >> nvda_signals.log
  sleep 30
done
