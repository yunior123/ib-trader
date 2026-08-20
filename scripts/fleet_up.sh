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
  local fleet_live=0
  [[ -x "$ROOT/bin/fleet_hours" ]] && "$ROOT/bin/fleet_hours" >/dev/null 2>&1 && fleet_live=1
  gated_status() {
    local pat="$1" label="$2"
    if alive "$pat"; then ok "$label"
    elif (( fleet_live )); then bad "$label CAÍDO"
    else ok "$label dormido (fuera de ventana, correcto)"; fi
  }
  local n=$(pgrep -f '_signal_bot$' | wc -l | tr -d ' ')
  if [[ $n -gt 0 ]]; then ok "$n bots de señal"
  elif (( fleet_live )); then bad "bots de señal: NINGUNO"
  else ok "bots de señal dormidos (fuera de ventana, correcto)"; fi
  alive "perp_ws_bridge.py" && ok "perpetuos 24/7 WS (OKX + Bybit)" || bad "perpetuos 24/7 WS CAÍDOS"
  alive "perp_stock_keepalive.sh" && ok "respaldo REST de perps (solo si WS cae)" || bad "respaldo REST de perps CAÍDO"
  # Feed de barras/cadena: según market_source (ibkr = puentes IBKR; otro = provider_bridge)
  if [[ "$MARKET_SOURCE" == "ibkr" ]]; then
    gated_status "ibkr_bar_bridge.py" "puente de barras IBKR"
    gated_status "opt_chain_cache.py" "caché de cadenas de opciones (IBKR)"
  else
    gated_status "provider_bridge.py" "provider_bridge ($MARKET_SOURCE): barras+nbbo+cadena"
  fi
  # opt_whale_watch es ib_insync: con market_source != ibkr su salida esta CONGELADA aunque el
  # proceso viva (verde falso cazado por el forense 2026-08-04). El vigia UW es el sustituto.
  if [[ "$MARKET_SOURCE" != "ibkr" ]]; then
    gated_status "uw_fleet_flow.py" "vigía de ballenas UW (flota, sustituto sin IBKR)"
  fi
  gated_status "opt_whale_watch.py" "vigía de ballenas"
  alive "notify_relay.sh" && ok "relé de notificaciones 24/7" || bad "relé de notificaciones 24/7 CAÍDO"
  gated_status "voice_queue.sh" "cola de voz"
  gated_status "price_alarm" "alarma de precio"
  alive "chart_bridge.py" && ok "cockpit del gráfico" || bad "cockpit del gráfico CAÍDO"
  for s in buffett squeeze momentum; do
    gated_status "finviz_screener_watch --screen $s" "Finviz $s"
  done
  # Discord: sin webhooks configurados su ausencia es CORRECTA (aún no se ha hecho bootstrap),
  # pintarla ✗ enseñaría a ignorar los ✗ — misma doctrina anti-crying-wolf que flow_pulse.
  if [[ -s config/discord_webhooks.json ]]; then
    alive "discord_relay.py" && ok "relé de Discord" || bad "relé de Discord"
  else
    ok "Discord sin configurar (correcto: falta scripts/discord_bootstrap.sh)"
  fi
  if alive "options_alert_engine --daemon"; then
    if [[ "${OPTIONS_ALERT_AUTO:-0}" == "1" ]] || grep -q '^export OPTIONS_ALERT_AUTO=1$' scripts/options_alert_engine_keepalive.sh 2>/dev/null; then
      ok "motor C++ de opciones (Discord AUTO)"
    else ok "motor C++ de opciones (shadow; top diario local)"; fi
  else
    (( fleet_live )) && bad "motor C++ de opciones CAÍDO" \
                       || ok "motor C++ de opciones dormido (fuera de ventana, correcto)"
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
