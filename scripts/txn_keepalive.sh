#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND FULL26 166T 117W WR70% +10.5% pf1.4 (OOS 70%)
export TXN_MODE=trend
export TXN_TREND_CUSUM=0.004
export TXN_TARGET=0.5
export TXN_STOP=0.8
export TXN_TRAIL_ATR=3
export TXN_MAX_DAY=2
export TXN_FLOOR=0.1
export TXN_SKIP_OPEN=15
export TXN_EOD_FORCE=1
export TXN_TIME_STOP_MIN=0
# live: gate de spread NBBO + umbral whale (v3)
export TXN_SPREAD_MAX=0.3
export TXN_WHALE_USD=250000
while true; do
  pkill -x txn_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TXN" 2>/dev/null
  sleep 1
  ./txn_signal_bot >> txn_signals.log 2>&1
  echo "$(date) txn_signal_bot salio; relanzando" >> txn_signals.log
  sleep 30
done
