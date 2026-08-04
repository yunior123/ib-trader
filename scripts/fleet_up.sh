#!/bin/zsh
# fleet_up.sh — UN SOLO COMANDO para levantar TODO. Idempotente: si algo ya corre,
# no lo duplica. Pensado para que Yunior lo use sin copiloto.
#
#   zsh scripts/fleet_up.sh              # levanta la flota (SEÑAL-SOLAMENTE)
#   zsh scripts/fleet_up.sh --chart      # + cockpit del gráfico en el navegador
#   zsh scripts/fleet_up.sh --status     # sólo informa qué está vivo, no toca nada
#
# PASAR A LIVE (lo único que hace un humano):
#   1) IB Gateway/TWS: entrar con la cuenta LIVE (puerto 7496 TWS / 4001 Gateway)
#   2) zsh scripts/ib_mode.sh live
#   3) volver a lanzar este script
# El motor de órdenes NO se arma solo: exige order_engine/arm.sh + --arm-live.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
MODE="$(cat data/ib_mode.txt 2>/dev/null || echo paper)"
MARKET_SOURCE="$(cat data/market_source.txt 2>/dev/null || echo ibkr)"

alive() { pgrep -f "$1" >/dev/null 2>&1; }
ok()    { print -P "  %F{green}✓%f $1"; }
bad()   { print -P "  %F{red}✗%f $1"; }
warn()  { print -P "  %F{yellow}!%f $1"; }

status() {
  print -P "%F{cyan}=== estado de la flota ===%f  modo=$MODE"
  local n=$(pgrep -f '_signal_bot$' | wc -l | tr -d ' ')
  [[ $n -gt 0 ]] && ok "$n bots de señal" || bad "bots de señal: NINGUNO"
  # Feed de barras/cadena: según market_source (ibkr = puentes IBKR; otro = provider_bridge)
  if [[ "$MARKET_SOURCE" == "ibkr" ]]; then
    alive "ibkr_bar_bridge.py" && ok "puente de barras IBKR" || bad "puente de barras IBKR"
    alive "opt_chain_cache.py" && ok "caché de cadenas de opciones (IBKR)" || bad "caché de cadenas (IBKR)"
  else
    alive "provider_bridge.py" && ok "provider_bridge ($MARKET_SOURCE): barras+nbbo+cadena" || bad "provider_bridge ($MARKET_SOURCE) CAÍDO"
  fi
  for p in opt_whale_watch.py:"vigía de ballenas" \
           notify_relay.sh:"relé de notificaciones" \
           voice_queue.sh:"cola de voz" \
           price_alarm:"alarma de precio" \
           chart_bridge.py:"cockpit del gráfico"; do
    alive "${p%%:*}" && ok "${p#*:}" || bad "${p#*:}"
  done
  for s in buffett squeeze momentum; do
    alive "finviz_screener_watch --screen $s" && ok "Finviz $s" || bad "Finviz $s"
  done
  # Discord: sin webhooks configurados su ausencia es CORRECTA (aún no se ha hecho bootstrap),
  # pintarla ✗ enseñaría a ignorar los ✗ — misma doctrina anti-crying-wolf que flow_pulse.
  if [[ -s config/discord_webhooks.json ]]; then
    alive "discord_relay.py" && ok "relé de Discord" || bad "relé de Discord"
  else
    ok "Discord sin configurar (correcto: falta scripts/discord_bootstrap.sh)"
  fi
  # flow_pulse solo vive lun-vie 09:30-15:56 (fleet_keepalive_start.sh:358). Fuera de ahí
  # su ausencia es CORRECTA: pintarla ✗ enseña a ignorar los ✗ (doctrina anti-crying-wolf).
  local fp_hm=$(date +%H%M) fp_dow=$(date +%u)
  if alive flow_pulse; then ok "pulso de flujo"
  elif (( fp_dow <= 5 && 10#$fp_hm >= 930 && 10#$fp_hm < 1556 )); then bad "pulso de flujo"
  else ok "pulso de flujo dormido (fuera de su ventana 09:30-15:56, correcto)"; fi
  # TWS/Gateway: puerto según modo. Con market_source != ibkr el feed NO es IBKR y su
  # ausencia es lo ESPERADO (solo haría falta para órdenes): decirlo en rojo es ruido.
  local port=4002; [[ "$MODE" == "live" ]] && port=4001
  if nc -z 127.0.0.1 $port 2>/dev/null; then ok "IB Gateway vivo (puerto $port, $MODE)"
  elif nc -z 127.0.0.1 7497 2>/dev/null; then ok "TWS vivo (7497, paper)"
  elif nc -z 127.0.0.1 7496 2>/dev/null; then ok "TWS vivo (7496, LIVE)"
  elif [[ "$MARKET_SOURCE" != "ibkr" ]]; then
    ok "sin TWS/Gateway (correcto: market_source=$MARKET_SOURCE; solo haría falta para órdenes)"
  else bad "NO hay TWS ni Gateway escuchando — ábrelo y entra"; fi
  [[ -f order_engine/ARM_LIVE ]] && warn "order_engine ARMADO ($(cat order_engine/ARM_LIVE))" \
                                  || ok "order_engine desarmado (señal-solamente)"
}

if [[ "${1:-}" == "--status" ]]; then status; exit 0; fi

print -P "%F{cyan}=== levantando la flota ===%f  modo=$MODE  $(date '+%F %H:%M')"

# 0) TWS/Gateway tiene que estar arriba: sin él no hay datos ni órdenes.
#    EXCEPCION (Yunior 2026-08-01): con market_source != ibkr, el feed viene de
#    provider_bridge (intrinio+polygon) y NO se necesita Gateway para market data.
#    Gateway sigue haciendo falta para order_engine si se opera en vivo.
port=4002; [[ "$MODE" == "live" ]] && port=4001
if [[ "$MARKET_SOURCE" == "ibkr" ]]; then
  if ! nc -z 127.0.0.1 $port 2>/dev/null && ! nc -z 127.0.0.1 7497 2>/dev/null \
     && ! nc -z 127.0.0.1 7496 2>/dev/null; then
    bad "NO hay TWS/Gateway escuchando. Ábrelo, entra con la cuenta $MODE, y repite."
    exit 1
  fi
else
  warn "market_source=$MARKET_SOURCE -> IBKR OFF para market data (feed via provider_bridge). Gateway solo hace falta para ordenes."
fi

# 1) permisos de escritura: si falla, las señales se pierden EN SILENCIO (lección 2026-07-24)
if ! touch data/trading-signals/.probe 2>/dev/null; then
  bad "no puedo escribir en data/trading-signals — revisa permisos ANTES de operar"
  exit 1
fi
rm -f data/trading-signals/.probe

# 2) la flota entera (bots + puentes + alarmas + voz). El script ya es idempotente.
if alive 'fleet_keepalive_start.sh'; then
  ok "keepalive de la flota ya vivo — no lo duplico"
else
  nohup zsh scripts/fleet_keepalive_start.sh >/dev/null 2>&1 &
  ok "keepalive de la flota lanzado"
fi

# 3) base de datos de señales (alimenta el backtest EOD) — via keepalive + log (2026-07-28)
alive 'signals_db_keepalive.sh' && ok "signals_db keepalive ya vivo" || {
  nohup bash scripts/signals_db_keepalive.sh >/dev/null 2>&1 & ok "signals_db keepalive lanzado"; }

# 4) cockpit del gráfico (opcional)
if [[ "${1:-}" == "--chart" ]]; then
  if alive 'chart_bridge.py'; then ok "cockpit ya vivo"
  else nohup ./venv-chart/bin/python scripts/chart_bridge.py >/dev/null 2>&1 &
       sleep 3; ok "cockpit lanzado"; fi
  open "http://127.0.0.1:8765/live.html" 2>/dev/null || true
fi

sleep 8
print ""
status
print ""
print -P "%F{cyan}Recordatorio:%f la flota es SEÑAL-SOLAMENTE. Para ejecutar órdenes:"
print "  order_engine/arm.sh && order_engine/run.sh --arm-live --sym QQQ"
print "  desarmar: order_engine/disarm.sh"
