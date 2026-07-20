#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND vida 20T 19W WR95% +19.2% pf12.2
export SPCX_MODE=trend
export SPCX_TREND_CUSUM=0.002
export SPCX_TARGET=3.0
export SPCX_STOP=0.75
export SPCX_TRAIL_ATR=5
export SPCX_MAX_DAY=2
export SPCX_FLOOR=0.1
export SPCX_SKIP_OPEN=15
export SPCX_EOD_FORCE=1
export SPCX_TIME_STOP_MIN=0
# LADO CORTO v4 (2026-07-11 'both directions'): cortos vida 26T 22W WR85% +17.2% pf8.3
export SPCX_SHORTS=1
export SPCX_S_TARGET=6.0
export SPCX_S_STOP=4
export SPCX_S_TRAIL=5
export SPCX_S_TSTOP=0
export SPCX_S_FLOOR=0.5
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP96/DOWN91%, umbral por ticker)
export SPCX_QUAKE_BANNER=1
export SPCX_QUAKE_MIN=0.013   # 0.006->0.013 2026-07-15: falso ALZA +1.27% en apertura (retrace), TRUE del dia -2.01% se mantiene; revisar con mas dias
# live: gate de spread NBBO + umbral whale (v3)
export SPCX_SPREAD_MAX=0.3
export SPCX_WHALE_USD=100000
# re-tune FULL-PROFIT 2026-07-11 (coordinate sweep, train+OOS>0, WR>=70)
export SPCX_S_TREND_CUSUM=0.005
# WFO v2 2026-07-11: 90d , seleccion solo-train, OOS intacto, velas
export SPCX_S_CANDLE=1
export SPCX_S_MODE=trend
while true; do
  pkill -x spcx_signal_bot 2>/dev/null
  sleep 1
  ./spcx_signal_bot >> spcx_signals.log 2>&1
  echo "$(date) spcx_signal_bot salio; relanzando" >> spcx_signals.log
  sleep 30
done
