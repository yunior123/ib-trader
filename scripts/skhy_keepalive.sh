#!/bin/zsh
cd "$(dirname "$0")/.."
# SKHY (NASDAQ, proxy US de SK Hynix) — TERREMOTO / deteccion-only
# (creado 2026-07-15, orden "u can create earthquake bot for skhy as well").
# Datos: ibkr_bar_bridge.py daemon (subs NA reales compradas 2026-07-15,
# Cboe One + Network A/B/C — 10089 muerto, verificado). El reader sigue
# data/bars_skhy_ibkr.txt en modo IBKR-ONLY. Motor de ENTRADAS APAGADO hasta
# pasar WR-70 + OOS (regla ship, orden #7); banner AMBAS direcciones.
export SKHY_QUAKE_BANNER=1
# umbral PROVISIONAL (sin backtest aun; ETF joven/fino) — calibrar con historial:
export SKHY_QUAKE_MIN=0.02
# entradas OFF: score imposible (max real 1.0) => nunca arma compra; shorts 0
export SKHY_SCORE_MIN=9
# gate spread NBBO del subyacente: p95 medido 0.17% (n=30 after-hours); 0.4 deja margen RTH + ADR fino
export SKHY_SPREAD_MAX=0.4
while true; do
  pkill -x skhy_signal_bot 2>/dev/null
  sleep 1
  ./skhy_signal_bot >> skhy_signals.log 2>&1
  echo "$(date) skhy_signal_bot salio; relanzando" >> skhy_signals.log
  sleep 30
done
