#!/bin/zsh
cd "$(dirname "$0")/.."
# SPY clonado de QQQ 2026-07-20 (orden "add spy to fleet"): params WR-70 heredados
# del backtest QQQ — PENDIENTE backtest propio (fleet_optimize.py). Whale 400k
# (SPY mas liquido que QQQ: 250k = ruido).
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND FULL26 178T 135W WR76% +14.0% pf2.1 (OOS 76%)
export SPY_MODE=trend
export SPY_TREND_CUSUM=0.004
export SPY_TARGET=0.5
export SPY_STOP=0.8
export SPY_TRAIL_ATR=2
export SPY_MAX_DAY=2
export SPY_FLOOR=0.1
export SPY_SKIP_OPEN=0
export SPY_EOD_FORCE=1
export SPY_TIME_STOP_MIN=240
# LADO CORTO v4 (2026-07-11 'both directions'): cortos FULL26 151T 111W WR74% +15.4% pf2.5 (OOS 76%)
export SPY_SHORTS=1
export SPY_S_TARGET=1.0
export SPY_S_STOP=1.5
export SPY_S_TRAIL=2
export SPY_S_TSTOP=240
export SPY_S_FLOOR=0.1
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP96/DOWN96%, umbral por ticker)
export SPY_QUAKE_BANNER=1
export SPY_QUAKE_MIN=0.01
# live: gate de spread NBBO + umbral whale (v3)
export SPY_SPREAD_MAX=0.3
export SPY_WHALE_USD=400000
# WFO v2 2026-07-11: 90d , seleccion solo-train, OOS intacto, velas
export SPY_S_CANDLE=1
export SPY_S_MODE=trend
export SPY_S_TREND_CUSUM=0.005
while true; do
  pkill -x spy_signal_bot 2>/dev/null
  sleep 1
  bots/spy_signal_bot >> logs/spy_signals.log 2>&1
  echo "$(date) spy_signal_bot salio; relanzando" >> logs/spy_signals.log
  sleep 30
done
