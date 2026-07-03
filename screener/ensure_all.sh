#!/bin/zsh
# ensure_all.sh — supervisor del sistema screener ("working non stop", Yunior
# 2026-07-10). Relanza SOLO los componentes muertos; no toca nada vivo (a
# diferencia de start_all.sh, que hace pkill+restart completo — usar ese solo
# para arranques manuales limpios). launchd lo corre al login y cada 2 min
# (com.ibtrader.screener RunAtLoad + StartInterval). Idempotente via pgrep.
#
# LEY SUPREMA (Yunior 2026-07-16): SEÑAL-SOLAMENTE, SIEMPRE. Sin flags de
# armado, sin SCREENER_LIVE, sin loops de trading, sin watchdog de posiciones —
# ejecutores retirados a backup/execution_retired_2026-07-16/.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
log() { echo "$(date '+%F %T') ensure: $1" >> "$ROOT/screener/ensure.log"; }

# --- PORTERO HORARIO (Yunior 2026-07-25: "de domingo 8pm a viernes 8pm hora de Toronto,
# fuera de ese horario todo muerto, salvo para testing") ---
# launchd corre este supervisor cada 2 min, asi que sin esta guarda RESUCITA la flota que
# `fleet_keepalive_start.sh` acaba de apagar. Medido: eso paso el sabado 2026-07-25 a las
# 16:44:51, 11 s despues del apagado. El calculo vive en C++ (bin/fleet_hours): 0=LIVE 1=DEAD.
# Portero ausente => NO se arranca nada (degradar a "pues arranco" seria el mismo fallo).
# El binario vive en bin/ desde la mudanza; la raiz queda como respaldo. Apuntar solo a la
# raiz dejaba este supervisor en "PORTERO AUSENTE" para siempre: 2.784 de 3.758 lineas de
# screener/ensure.log (74%), o sea que NUNCA relanzo nada desde la mudanza. Mismo precedente
# que ya mato la flota (05:15-06:48) y que rompio fleet_window.py:32.
FLEET_HOURS="$ROOT/bin/fleet_hours"; [[ -x "$FLEET_HOURS" ]] || FLEET_HOURS="$ROOT/fleet_hours"
if [[ -x "$FLEET_HOURS" ]]; then
  if ! "$FLEET_HOURS" >/dev/null 2>&1; then
    log "fuera de ventana horaria -> no relanzo nada ($("$FLEET_HOURS" 2>&1 | head -1))"
    exit 0
  fi
else
  log "PORTERO AUSENTE ($FLEET_HOURS) -> no relanzo nada. Compila con scripts/build_fleet_hours.sh"
  exit 0
fi

if ! pgrep -x screener_alert >/dev/null && ! pgrep -f "screener/alert_bot.py" >/dev/null; then
  if [[ -x "$ROOT/screener/screener_alert" ]]; then
    ALERT_POLL=1 nohup "$ROOT/screener/screener_alert" >>"$ROOT/screener/alert_bot.log" 2>&1 &   # poll 1s (orden 2026-07-15 blazing fast)
  else
    nohup "$PY" "$ROOT/screener/alert_bot.py" >>"$ROOT/screener/alert_bot.log" 2>&1 &
  fi
  log "alert bot relanzado (pid $!)"
fi

# daemon IBKR de flota: SIP bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt.
# Solo lectura de mercado — cero ordenes.
#
# SIMBOLOS DE data/fleet.txt (fuente unica). Aqui habia una lista ESCRITA A MANO de 18
# simbolos, con su comentario "17 syms (CON SKHY)" de cuando la flota tenia ese tamaño:
# **sin SPY, sin SMH y sin MU**, y con SLV/CPER/USO ya retirados. Como este script y
# `fleet_keepalive_start.sh` compiten por lanzar el MISMO daemon (los dos con `pgrep`),
# **el que ganaba la carrera decidia que simbolos tenian barras**. Si ganaba este, los dos
# capitanes del mercado se quedaban sin feed — y la regla 12 (jerarquia de capitanes) es el
# veto mas fuerte del sistema. Medido el 2026-07-25: el screener relanzo el bridge con la
# lista vieja 11 s despues de que el portero horario lo apagara.
#
# PORTERO DE PROVEEDOR (2026-08-03): este era el UNICO lanzador del bridge que no miraba
# data/market_source.txt, y por eso resucitaba IBKR aunque el feed fuera otro
# (fleet_keepalive_start.sh:201-224 y fleet_up.sh:30-36 ya bifurcaban). Medido hoy 07:10:03:
# en cuanto el portero horario volvio a funcionar, este script levanto un
# `ibkr_bar_bridge.py --daemon` de 30 simbolos con market_source=intrinio y el Gateway
# prohibido — el bridge se puso a gritar "CINTA CIEGA" y "TWS desconectado". El camino IBKR
# se CONSERVA entero: vuelve solo con market_source=ibkr.
MARKET_SOURCE="$(cat "$ROOT/data/market_source.txt" 2>/dev/null || echo ibkr)"
if [[ "$MARKET_SOURCE" != "ibkr" ]]; then
  : # feed no-IBKR: lo alimenta provider_bridge, que arranca fleet_keepalive_start.sh
elif ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  FLEET_SYMS="$(cat "$ROOT/data/fleet.txt" 2>/dev/null)"
  if [[ -z "$FLEET_SYMS" ]]; then
    log "data/fleet.txt vacio o ilegible -> NO lanzo el bridge"
  else
    # logs/ desde la reorg 2026-07-29: estos dos apuntaban aun a la raiz del repo.
    nohup "$ROOT/venv/bin/python" "$ROOT/scripts/"ibkr_bar_bridge.py --daemon ${=FLEET_SYMS} >>"$ROOT/logs/bridge_ibkr_fleet.log" 2>&1 &
    echo "$(date) fleet: ibkr fleet daemon lanzado por ensure_all (pid $!) con $(echo $FLEET_SYMS | wc -w | tr -d ' ') simbolos de data/fleet.txt" >>"$ROOT/logs/fleet_autostart.log"
  fi
fi


# email/telegram ELIMINADOS (Yunior 2026-07-10): solo Mac, fleet_notify.h C++

if ! pgrep -f "screener/heartbeat.sh" >/dev/null; then
  nohup zsh "$ROOT/screener/heartbeat.sh" >/dev/null 2>&1 &
  log "heartbeat relanzado (pid $!)"
fi
