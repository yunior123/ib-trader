#!/bin/zsh
cd "$(dirname "$0")/.."
# USO — TERREMOTO bot (orden Yunior 2026-07-11: "add new bots for uso ... a
# terremoto bot ... should be 24/7"). Solo deteccion banner-grade AMBAS
# direcciones; motor de entradas APAGADO hasta pasar WR-70 + OOS (regla ship).
# Datos: daemon alpaca ws (RTH 9:30-16 = websockets, orden 2026-07-11) +
# poll overnight del daemon (Dom20->Vie04 ET). IBKR TWS: RT API bloqueado por
# subscripcion (error 420 2026-07-11) — el bridge ibkr corre en modo
# suplemento (venue OVERNIGHT best-effort; upgrade path al activar SIP $10).
export USO_QUAKE_BANNER=1
# umbral 90d, metrica OFICIAL flota (no-retrace>50% en 30min, item 18):
# precision 95% (n=112), 8.7 alertas/sem <=10; control GLD@0.01 = 95%
export USO_QUAKE_MIN=0.02
# entradas OFF: score imposible (max real = 1.0) => nunca arma compra;
# shorts default 0. Terremoto puro.
export USO_SCORE_MIN=9
while true; do
  pkill -x uso_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read USO" 2>/dev/null
  sleep 1
  ./uso_signal_bot >> uso_signals.log 2>&1
  echo "$(date) uso_signal_bot salio; relanzando" >> uso_signals.log
  sleep 30
done
