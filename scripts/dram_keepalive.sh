#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 59T 43W WR73% +33.8% pf1.8 (config 07-10 conservado: gana en dinero y cumple 70)
export DRAM_BB_STD=2.0
export DRAM_RSI_OS=35
export DRAM_VOL_MULT=1.0
export DRAM_TARGET=9.0
export DRAM_TRAIL_ATR=2
export DRAM_STOP=6.0
export DRAM_TIME_STOP_MIN=0
export DRAM_SKIP_OPEN=0
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP95/DOWN88%, umbral por ticker)
export DRAM_QUAKE_BANNER=1
export DRAM_QUAKE_MIN=0.015
# live: gate de spread NBBO + umbral whale (v3)
export DRAM_SPREAD_MAX=0.5
export DRAM_WHALE_USD=100000
# re-tune FULL-PROFIT 2026-07-11 (coordinate sweep, train+OOS>0, WR>=70)
export DRAM_CONFIRM_STRICT=0
# WFO v2 2026-07-11: 90d , seleccion solo-train, OOS intacto, velas
export DRAM_SHORTS=1
export DRAM_S_FLOOR=2
export DRAM_S_MODE=trend
export DRAM_S_TRAIL=2
export DRAM_S_TREND_CUSUM=0.015
export DRAM_S_TSTOP=60
while true; do
  pkill -x dram_signal_bot 2>/dev/null
  sleep 1
  bots/dram_signal_bot >> logs/dram_signals.log 2>&1
  echo "$(date) dram_signal_bot salio; relanzando" >> logs/dram_signals.log
  sleep 30
done
