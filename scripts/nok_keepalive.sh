#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 13T 13W WR100% +25.4% (perfil stop-ancho: perdidas pueden quedar en bag)
export NOK_BB_STD=2.0
export NOK_RSI_OS=35
export NOK_VOL_MULT=1.0
export NOK_TARGET=8.0
export NOK_TRAIL_ATR=2
export NOK_STOP=4.0
export NOK_TIME_STOP_MIN=240
export NOK_SKIP_OPEN=5
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP98/DOWN93%, umbral por ticker)
export NOK_QUAKE_BANNER=1
export NOK_QUAKE_MIN=0.03
# live: gate de spread NBBO + umbral whale (v3)
export NOK_SPREAD_MAX=0.3
export NOK_WHALE_USD=150000
# WFO v2 2026-07-11: 90d , seleccion solo-train, OOS intacto, velas
export NOK_SHORTS=1
export NOK_S_MODE=trend
export NOK_S_TARGET=3.0
export NOK_S_TRAIL=3
export NOK_S_TREND_CUSUM=0.005
while true; do
  pkill -x nok_signal_bot 2>/dev/null
  sleep 1
  bots/nok_signal_bot >> logs/nok_signals.log 2>&1
  echo "$(date) nok_signal_bot salio; relanzando" >> logs/nok_signals.log
  sleep 30
done
