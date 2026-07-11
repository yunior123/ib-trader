#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND FULL26 138T 105W WR76% +36.3% pf2.8 (OOS 72% +15.4%)
export TSLA_MODE=trend
export TSLA_TREND_CUSUM=0.005
export TSLA_TARGET=3.0
export TSLA_STOP=1.2
export TSLA_TRAIL_ATR=3
export TSLA_MAX_DAY=2
export TSLA_FLOOR=0.1
export TSLA_SKIP_OPEN=0
export TSLA_EOD_FORCE=1
export TSLA_TIME_STOP_MIN=120
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP94/DOWN96%, umbral por ticker)
export TSLA_QUAKE_BANNER=1
export TSLA_QUAKE_MIN=0.02
# live: gate de spread NBBO + umbral whale (v3)
export TSLA_SPREAD_MAX=0.3
export TSLA_WHALE_USD=250000
# re-tune FULL-PROFIT 2026-07-11 (coordinate sweep, train+OOS>0, WR>=70)
export TSLA_SHORTS=1
export TSLA_S_STOP=1.6
export TSLA_S_TARGET=1.0
export TSLA_S_TRAIL=3
export TSLA_S_TSTOP=0
# WFO v2 2026-07-11: 90d Alpaca, seleccion solo-train, OOS intacto, velas
export TSLA_S_BB_STD=2.5
export TSLA_S_CANDLE=0
export TSLA_S_FLOOR=0.5
export TSLA_S_MODE=trend
export TSLA_S_RSI_OS=35
export TSLA_S_VOL_MULT=1.0
export TSLA_TREND_VWAP=0
while true; do
  pkill -x tsla_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read TSLA" 2>/dev/null
  sleep 1
  ./tsla_signal_bot >> tsla_signals.log 2>&1
  echo "$(date) tsla_signal_bot salio; relanzando" >> tsla_signals.log
  sleep 30
done
