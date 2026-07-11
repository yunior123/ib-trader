#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND FULL26 166T 117W WR70% +10.5% pf1.4 (OOS 70%)
export TXN_MODE=trend
export TXN_TREND_CUSUM=0.005
export TXN_TARGET=1.0
export TXN_STOP=2.4
export TXN_TRAIL_ATR=5
export TXN_MAX_DAY=2
export TXN_FLOOR=0.25
export TXN_SKIP_OPEN=0
export TXN_EOD_FORCE=0
export TXN_TIME_STOP_MIN=0
# LADO CORTO v4 (2026-07-11 'both directions'): cortos FULL26 158T 127W WR80% +28.0% pf3.3 (OOS 91%)
export TXN_SHORTS=1
export TXN_S_TARGET=0.5
export TXN_S_STOP=0.75
export TXN_S_TRAIL=2
export TXN_S_TSTOP=60
export TXN_S_FLOOR=0.1
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP96/DOWN94%, umbral por ticker)
export TXN_QUAKE_BANNER=1
export TXN_QUAKE_MIN=0.02
# live: gate de spread NBBO + umbral whale (v3)
export TXN_SPREAD_MAX=0.3
export TXN_WHALE_USD=250000
export TXN_S_TREND_CUSUM=0.005
# WFO v2 2026-07-11: 90d Alpaca, seleccion solo-train, OOS intacto, velas
export TXN_CANDLE=1
export TXN_S_MODE=trend
export TXN_TREND_VWAP=0
while true; do
  pkill -x txn_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TXN" 2>/dev/null
  sleep 1
  ./txn_signal_bot >> txn_signals.log 2>&1
  echo "$(date) txn_signal_bot salio; relanzando" >> txn_signals.log
  sleep 30
done
