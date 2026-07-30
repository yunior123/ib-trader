#!/bin/zsh
# fleet_keepalive_start.sh — UNICO punto de entrada de la flota (lo relanza
# com.ibtrader.fleet cada 300 s, RunAtLoad). Arranca los keepalives de los signal
# bots (21 syms en FLEET_SYMS) + infraestructura. Idempotente: si un keepalive ya corre, no lo duplica
# (dos keepalives del mismo bot se matarian el bot mutuamente). launchd lo
# re-ejecuta cada 5 min (StartInterval) = watchdog de los watchdogs.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

# --- MUTEX contra arranques concurrentes (2026-07-26) -------------------------
# El dedup de abajo es "pgrep ¿ya corre? -> si no, lanza": entre el pgrep y el nohup
# hay una ventana. Si DOS instancias de este script corren a la vez (launchd cada
# 300s solapado con un run manual, o esta corrida tardando por el finviz_valuation.py
# sincrono) ambas pueden pasar el pgrep antes de que ninguna haya lanzado nada ->
# DOS nvda_keepalive.sh para el mismo simbolo, cada uno con `pkill -x` en su loop ->
# se matan el bot mutuamente cada ciclo (TODOS.md: "bot asesinado cada 31 s").
# mkdir es atomico (macOS no trae flock, patron ya usado en speak.sh). Si el lock
# esta viejo (>120s, instancia anterior murio a medias) se roba.
mkdir -p "$ROOT/logs"   # los logs viven en logs/ desde la reorg 2026-07-29
LOCKDIR="$ROOT/data/.fleet_keepalive_start.lockd"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCKDIR" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt 120 ]; then
    echo "$(date) fleet: OTRA instancia activa (lock ${AGE}s) -> salgo sin tocar nada (evita doble keepalive)" >> "$ROOT/logs/fleet_autostart.log"
    exit 0
  fi
  echo "$(date) fleet: lock viejo (${AGE}s) -> instancia anterior murio a medias, lo tomo" >> "$ROOT/logs/fleet_autostart.log"
  rmdir "$LOCKDIR" 2>/dev/null
  mkdir "$LOCKDIR" 2>/dev/null
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

# --- AUTO-CHEQUEO DE PERMISO (Yunior 2026-07-24 "los bots siempre con permiso") ---
# Si el contexto de arranque (p.ej. launchd SIN Full Disk Access) no puede escribir el
# HUD del Desktop, los bots correrian MUDOS y las señales se perderian en silencio.
# Fallar RUIDOSO: voz + notificacion + bandera data/PERM_DENIED (la ve el healthcheck).

# --- LISTA UNICA DE APAGADO (extraida 2026-07-25) -----------------------------
# Antes esta lista vivia SOLO dentro del MODO SUEÑO. Ahora la comparten el sueño
# manual y el portero horario, porque dos listas divergentes = keepalives que
# sobreviven al apagado (el bug de hoy: sabado con 30 keepalives arriba).
# slv/cper/uso BORRADOS: no son de la flota de 30, ya se mataron sus huerfanos.
FLEET_SYMS=(dram nok spcx tsla nvda txn tsm amd intc asml aapl gld qqq spy
            skhy skhynix samsung kospi mu smh ewy)

fleet_stop_all() {
  # keepalives de infraestructura
  for p in price_alarm_keepalive.sh opt_sentinel_keepalive.sh options_enrich_keepalive.sh \
           opt_chain_keepalive.sh bargain_keepalive.sh sox_keepalive.sh \
           finviz_scout_keepalive.sh notify_relay.sh x_signal_keepalive.sh \
           opt_whale_keepalive.sh uw_flow_tape_keepalive.sh overnight_feed_keepalive.sh voice_queue_keepalive.sh compass_keepalive.sh \
           perp_stock_keepalive.sh perp_nbbo_bridge_keepalive.sh \
           fleet_consensus_keepalive.sh levels_refresh_keepalive.sh; do
    pkill -f "scripts/$p" 2>/dev/null
  done
  pkill -f 'scripts/perp_nbbo_bridge.py' 2>/dev/null
  pkill -f 'scripts/fleet_consensus.py --daemon' 2>/dev/null
  # daemons python de señal (el arnes ib_async/ib_insync)
  for p in x_signal_poster.py sox_index_feed.py opt_sentinel.py options_enrich.py \
           opt_chain_cache.py band_open_watch.py bollinger_alarm.py dip_alert.py \
           earnings_fall_scout.py; do
    pkill -f "scripts/$p" 2>/dev/null
  done
  # binarios de señal C++
  pkill -x finviz_scout 2>/dev/null
  pkill -x price_alarm 2>/dev/null
  pkill -x flow_pulse 2>/dev/null
  pkill -x fleet_consensus 2>/dev/null
  pkill -f 'ib-trader/compass --loop' 2>/dev/null
  pkill -f 'scripts/voice_queue.sh' 2>/dev/null
  # HUERFANOS: notify_relay lanza 'timeout N tail -n0 -F .../trading-signals/<hoy>.txt'.
  # Al matar al padre el tail SOBREVIVE (medido 2026-07-25: quedaba vivo tras el
  # apagado). Un hijo que sobrevive al apagado ES el bug que estamos arreglando.
  pkill -f 'tail -n0 -F .*trading-signals' 2>/dev/null
  pkill -f 'timeout .* tail -n0 -F' 2>/dev/null
  # screener (lo arranca com.ibtrader.screener, pero fuera de ventana tambien calla)
  pkill -f 'screener/heartbeat.sh' 2>/dev/null
  pkill -x screener_alert 2>/dev/null
  # bots de la flota + sus keepalives
  for b in "${FLEET_SYMS[@]}"; do
    pkill -f "scripts/${b}_keepalive.sh" 2>/dev/null
    pkill -x "${b}_signal_bot" 2>/dev/null
  done
}

# Los bridges de datos SOBREVIVEN al sueño manual (asi estaba diseñado: el sueño
# calla las alertas pero conserva el tape). FUERA DE VENTANA no: el mercado esta
# cerrado, no hay tape que puentear, y un bridge vivo mantiene TWS/Gateway ocupado.
fleet_stop_bridges() {
  pkill -f 'scripts/ibkr_bar_bridge.py' 2>/dev/null
  pkill -f 'scripts/korea_bar_bridge.py' 2>/dev/null
  pkill -f 'scripts/chart_bridge.py' 2>/dev/null
}

SIGDIR="$ROOT/data/trading-signals"
mkdir -p "$SIGDIR" 2>/dev/null
if ! ( : > "$SIGDIR/.perm_check" ) 2>/dev/null; then
  echo "$(date) fleet: SIN PERMISO de escritura en $SIGDIR (TCC/Full Disk Access)" >> "$ROOT/logs/fleet_autostart.log"
  touch "$ROOT/data/PERM_DENIED" 2>/dev/null
  "$ROOT/scripts/speak.sh" DANGER "Atención: los bots no tienen permiso de escritura. Activar Full Disk Access. Las señales no se están guardando." 2>/dev/null
  osascript -e 'display notification "Bots SIN permiso (TCC). Activa Full Disk Access al runner." with title "🔴 PERMISO DENEGADO" sound name "Sosumi"' 2>/dev/null
else
  rm -f "$SIGDIR/.perm_check" "$ROOT/data/PERM_DENIED" 2>/dev/null
fi
# --- PORTERO HORARIO (orden Yunior 2026-07-25) --------------------------------
# "los horarios de la flota son de domingo 8pm a viernes 8 pm hora de toronto,
#  fuera de ese horario todo muerto, salvo para testing, backtesting, fixes."
# El 2026-07-25 (sabado) la flota entera estaba arriba porque NADIE miraba el reloj.
# El calculo vive en C++ (./fleet_hours): exit 0 = LIVE, exit 1 = DEAD.
# Escape de testing: FLEET_FORCE=1 o data/FLEET_FORCE (el binario lo ANUNCIA).
# bin/ primero (mudanza de binarios 2026-07-29); raiz como fallback legado
FLEET_HOURS="$ROOT/bin/fleet_hours"
[[ -x "$FLEET_HOURS" ]] || FLEET_HOURS="$ROOT/fleet_hours"
if [[ ! -x "$FLEET_HOURS" ]]; then
  # FAIL-LOUD: sin portero NO se arranca. Degradar a "pues arranco" es exactamente
  # el fallo que estamos arreglando (un LIVE plausible sin haberlo comprobado).
  echo "$(date) fleet: PORTERO AUSENTE ($FLEET_HOURS no existe o no es ejecutable) -> NO se arranca nada. Compila con ./scripts/build_fleet_hours.sh" >> "$ROOT/logs/fleet_autostart.log"
  if [[ ! -f "$ROOT/data/FLEET_HOURS_MISSING" ]]; then
    touch "$ROOT/data/FLEET_HOURS_MISSING" 2>/dev/null
    osascript -e 'display notification "Falta ./fleet_hours: la flota NO arranca. Corre scripts/build_fleet_hours.sh" with title "🔴 PORTERO AUSENTE" sound name "Sosumi"' 2>/dev/null
  fi
  fleet_stop_all
  exit 0
fi
rm -f "$ROOT/data/FLEET_HOURS_MISSING" 2>/dev/null
FH_OUT="$("$FLEET_HOURS" 2>&1)"; FH_RC=$?
if [[ $FH_RC -ne 0 ]]; then
  # FUERA DE VENTANA. Idempotente y SILENCIOSO: sin voz y sin notificacion, porque
  # el fin de semana esto es lo NORMAL, no una alarma. Solo deja rastro en el log.
  fleet_stop_all
  fleet_stop_bridges
  echo "$(date) fleet: fuera de ventana -> todo apagado | $FH_OUT" >> "$ROOT/logs/fleet_autostart.log"
  exit 0
fi

# MODO SUEÑO (orden Yunior 2026-07-16 noche "alertas dormidas tambien"):
# si data/fleet_sleep existe, se APAGA todo salvo bridge de datos + tws_watchdog
# y launchd no revive nada. Despertar: rm data/fleet_sleep (+ focus_ticker del dia).
if [[ -f "$ROOT/data/fleet_sleep" ]]; then
  # AUTO-DESPERTAR (sorpresa 2026-07-16): si fleet_sleep contiene "wake: <epoch>"
  # y ya paso la hora, el candado se quita solo y la flota amanece armada.
  WAKE=$(grep -o 'wake: [0-9]*' "$ROOT/data/fleet_sleep" 2>/dev/null | awk '{print $2}')
  if [[ -n "$WAKE" && "$(date +%s)" -ge "$WAKE" ]]; then
    rm -f "$ROOT/data/fleet_sleep"
    echo "$(date) fleet: AUTO-DESPERTAR (wake $WAKE alcanzado)" >> "$ROOT/logs/fleet_autostart.log"
    osascript -e 'display notification "La flota amaneció sola: bots, sirenas y feeds armados. Buen OPEX." with title "🌅 FLOTA DESPIERTA" sound name "ProChord"' 2>/dev/null
  else
    # MISMA lista que el portero horario (fleet_stop_all). Los bridges de datos
    # sobreviven al sueño a proposito: el sueño calla alertas, no el tape.
    fleet_stop_all
    exit 0
  fi
fi
# MODO FOCO (orden Yunior 2026-07-16 "run fleet bot for intc only today"):
# si data/focus_ticker existe, solo los tickers listados ahi corren; el resto
# se APAGA en cada tick de 5 min. Restaurar flota completa: rm data/focus_ticker
FOCUS="$ROOT/data/focus_ticker"
for b in "${FLEET_SYMS[@]}"; do
  if [[ -s "$FOCUS" ]] && ! grep -qix "$b" "$FOCUS"; then
    pkill -f "scripts/${b}_keepalive.sh" 2>/dev/null
    pkill -x "${b}_signal_bot" 2>/dev/null
    continue
  fi
  if ! pgrep -f "scripts/${b}_keepalive.sh" >/dev/null; then
    nohup zsh "$ROOT/scripts/${b}_keepalive.sh" >/dev/null 2>&1 &
    echo "$(date) fleet: ${b}_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
  fi
done

# daemon de VOZ SERIALIZADA (Yunior 2026-07-18: las voces se cortaban entre sí).
# Un solo consumidor habla; price_alarm + bots encolan con speak.sh. Ver
# docs/VOICE-QUEUE.md. Señal-solamente. Arranca antes que los productores.
if ! pgrep -f "voice_queue.sh" >/dev/null; then
  nohup ./scripts/voice_queue_keepalive.sh >> logs/fleet_autostart.log 2>&1 &
  echo "$(date) fleet: voice_queue daemon lanzado (pid $!)" >> logs/fleet_autostart.log
fi

# daemon IBKR de flota — FUENTE UNICA desde 2026-07-15 ("connect to ibkr
# only"; subs NA reales compradas: Cboe One + Network A/B/C, 10089 muerto).
# SIP warm-up historico + bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt.
# Bots leen data/bars_<sym>_ibkr.txt directo via tail -F (reader retirado 2026-07-20).
# SIMBOLOS: de data/fleet.txt, la FUENTE UNICA (Yunior). La lista iba escrita a mano aqui
# y habia DERIVADO: pedia 33 simbolos = los 30 de la flota + SLV, CPER y USO, tres retirados
# cuyos keepalives se mataron el 2026-07-25. Tres suscripciones tick-by-tick gastadas en
# nombres que ya nadie mira, y IBKR capea esas suscripciones por cuenta (err 10190).
# `${=...}` es la division en palabras de zsh: sin el `=` la flota entera va como UN argumento.
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  FLEET_SYMS="$(cat "$ROOT/data/fleet.txt" 2>/dev/null)"
  if [[ -z "$FLEET_SYMS" ]]; then
    echo "$(date) fleet: data/fleet.txt vacio o ilegible -> NO lanzo el bridge (sin flota no hay feed que valga)" >> logs/fleet_autostart.log
  else
    nohup ./venv/bin/python scripts/ibkr_bar_bridge.py --daemon ${=FLEET_SYMS} >> logs/bridge_ibkr_fleet.log 2>&1 &
    echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!) con $(echo $FLEET_SYMS | wc -w | tr -d ' ') simbolos de data/fleet.txt" >> logs/fleet_autostart.log
  fi
fi

# cotizacion de la watchlist del usuario (TQQQ/MSFU/MUU...): el bar_bridge solo cubre
# fleet.txt y ampliarlo quema suscripciones (err 10190) -> snapshots a watchlist_stats.json.
if ! pgrep -f "scripts/watchlist_quotes.py" >/dev/null; then
  nohup ./venv-chart/bin/python scripts/watchlist_quotes.py >> logs/watchlist_quotes.log 2>&1 &
  echo "$(date) fleet: watchlist_quotes lanzado (pid $!)" >> logs/fleet_autostart.log
fi

# bridge KRX realtime (SK Hynix + Samsung) — sub Korea waived cubre la API
# (verificado 2026-07-12): mercado de memoria/DRAM en vivo y gratis, lider ~13h
# antes que EE.UU. para MU/DRAM. Escribe data/bars_{skhynix,samsung}.txt.
if ! pgrep -f "scripts/korea_bar_bridge.py" >/dev/null; then
  nohup ./venv/bin/python scripts/korea_bar_bridge.py --daemon >> logs/bridge_korea.log 2>&1 &
  echo "$(date) fleet: korea bridge lanzado (pid $!)" >> logs/fleet_autostart.log
fi

# TWS watchdog (2026-07-15, tras 75 min de ceguera): vigila puerto 7496 en
# ventanas de mercado, relanza TWS colgado y GRITA por el login (que siempre
# es del humano). El eslabon debil del dia fue TWS, no las señales.
# DESACTIVADO 2026-07-24 (Yunior: "no tws anymore, gateway is better"). El order_engine
# y los lectores usan IB GATEWAY (4002/4001) con auto-detección; ya NO relanzamos TWS.
# Reactivar: quitar el 'false &&'. (Gateway trae su propio auto-restart en su config.)
if false && ! pgrep -f "scripts/tws_watchdog.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/tws_watchdog.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: tws_watchdog lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# cache de cadenas de opciones (v6.1 2026-07-16 noche): opt_chain_cache.py
# (ib_insync readonly clientId 48) vuelca cada 3 min en RTH la cadena ±6% ATM
# (2 vencimientos, 17 syms) a data/opt_chain_<sym>.txt; lector instantaneo:
# ./opt_quick NVDA [strike C|P]. SEÑAL-SOLAMENTE, cero ordenes.
if [ -f "$ROOT/scripts/opt_chain_cache.py" ] && ! pgrep -f "scripts/opt_chain_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/opt_chain_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: opt_chain_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# bargain bot (2026-07-15): gangas en flota + top gainers + oversold, vetadas
# por TradingAgents — solo BUY notifica. Signal-only, cada 10 min en RTH.
if ! pgrep -f "scripts/bargain_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/bargain_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: bargain_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# EJECUTOR ELIMINADO 2026-07-15 (orden Yunior: "borra todo lo que ejecute
# operaciones en tws, los bots son un peligro, solo señales"). El executor
# ADOPTABA posiciones manuales via reconcile y les colocaba stop+GTC REALES
# aun DESARMADO (vendio RAM 13:45 e INTW 15:31 contra su voluntad, y
# re-coloco las ordenes tras un global-cancel). Archivado en
# backup/executors_retired_2026-07-15/. LA FLOTA ES 100% SEÑALES, 24/5.

# feed del indice SOX (2026-07-16: niveles del indice para sirenas; sin bot —
# es indice, sin volumen). Escribe data/nbbo_sox.txt en RTH.
if ! pgrep -f "scripts/sox_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/sox_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: sox_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# finviz_scout (2026-07-17): datos Finviz Elite que IBKR no da (short float,
# gap, rel vol, earnings, target/recom) -> data/finviz_<sym>.txt cada 60s
# premarket / 180s RTH; banners SOLO en cambios de estado. Señal-solamente,
# token en feeds.env, un request por ciclo. Compilar si falta el binario:
# clang++ -std=c++17 -O2 -o finviz_scout scripts/finviz_scout.cpp -lcurl
if { [ -x "$ROOT/bin/finviz_scout" ] || [ -x "$ROOT/finviz_scout" ]; } && ! pgrep -f "scripts/finviz_scout_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/finviz_scout_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: finviz_scout_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# notify_relay (2026-07-17): espejo Desktop -> ntfy push + Resend email (solo 🚨).
# Anti-ruido: alertas >45s se DESCARTAN (jamas acumular).
if ! pgrep -f "scripts/notify_relay.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/notify_relay.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: notify_relay lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# vigia de BALLENAS de opciones (2026-07-20 "activa alarm fleet for whale puts
# and calls"): flujo P/C ±3% ATM cada 5 min, expiry semanal auto, alerta
# voz+banner en cruces (P/C>=2 puts / <=0.35 calls, ley #13). clientId 82.
# patron de Yunior 2026-07-22: apertura fuera de banda 15m RTH -> re-entrada
# (probs medidas en data/band_snap_stats.json). Corre solo 9:29-10:35 y muere.
if ! pgrep -f "scripts/band_open_watch.py" >/dev/null; then
  nohup ./venv/bin/python -u scripts/band_open_watch.py >> logs/band_open_watch.log 2>&1 &
  echo "$(date) fleet: band_open_watch lanzado (pid $!)" >> logs/fleet_autostart.log
fi

# vigia Bollinger INTRADIA (Yunior 2026-07-22: "rectifica bollinger alarms"):
# pierce+re-entrada = rebote elastico; 1m+5m mismo lado = band-walk (no fade).
# portero RTH (fix 2026-07-28): de noche entraba en boot-loop banner "arriba/fuera" cada 5 min
BA_HM=$(( $(date +%-H) * 100 + $(date +%-M) ))
BA_DOW=$(date +%u)
if (( BA_DOW <= 5 && BA_HM >= 930 && BA_HM < 1556 )) && ! pgrep -f "scripts/bollinger_alarm.py" >/dev/null; then
  nohup ./venv/bin/python -u scripts/bollinger_alarm.py >> logs/bollinger_alarm.log 2>&1 &
  echo "$(date) fleet: bollinger_alarm lanzado (pid $!)" >> logs/fleet_autostart.log
fi

# flow_pulse (2026-07-22, Yunior): vigia de flujo MENOS estricto en C++ —
# P/C 0.50/1.40, giros de ratio y surges de volumen; tail 1s de
# whale_flow_hist.jsonl. Complementa (no reemplaza) la ballena DANGER.
# solo en RTH (935-1555 como su rth_open): de noche entraba en boot-loop banner+exit cada 5 min
FP_HM=$(( $(date +%-H) * 100 + $(date +%-M) ))
FP_DOW=$(date +%u)
if (( FP_DOW <= 5 && FP_HM >= 930 && FP_HM < 1556 )) && ! pgrep -x "flow_pulse" >/dev/null; then
  FP_BIN="$ROOT/bin/flow_pulse"; [ -x "$FP_BIN" ] || FP_BIN="$ROOT/flow_pulse"
  nohup "$FP_BIN" >> "$ROOT/logs/flow_pulse.log" 2>&1 &
  echo "$(date) fleet: flow_pulse lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# aviso hablado "posicion expira HOY" (hueco del opt_sentinel retirado; posiciones REALES, readonly)
if (( FP_DOW <= 5 && FP_HM >= 930 && FP_HM < 1600 )) \
   && ! pgrep -f "scripts/position_close_reminder.py" >/dev/null; then
  mkdir -p "$ROOT/logs"
  nohup "$ROOT/venv/bin/python" -u "$ROOT/scripts/position_close_reminder.py" >> "$ROOT/logs/position_close_reminder.log" 2>&1 &
  echo "$(date) fleet: position_close_reminder lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# scout de caidas post-earnings (2026-07-28): pasadas 8:20/9:50/12:30, muere 13:00
if (( FP_DOW <= 5 && FP_HM >= 815 && FP_HM < 1300 )) \
   && ! pgrep -f "scripts/earnings_fall_scout.py" >/dev/null; then
  mkdir -p "$ROOT/logs"
  nohup "$ROOT/venv/bin/python" -u "$ROOT/scripts/earnings_fall_scout.py" >> "$ROOT/logs/earnings_fall_scout.log" 2>&1 &
  echo "$(date) fleet: earnings_fall_scout lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

if ! pgrep -f "scripts/opt_whale_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/opt_whale_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: opt_whale_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# cinta de ballenas UW (2026-07-28 "spot whales like tradingflow, usa UW"): flow-alerts
# capitanes+foco cada 90s/sym -> data/uw_flow_tape.json (widget wgt-flow del cockpit).
if ! pgrep -f "scripts/uw_flow_tape_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/uw_flow_tape_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: uw_flow_tape_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# BRUJULA (compass C++): escribe data/compass_<sym>.json que lee el cockpit. Estaba en
# fleet_stop_all pero NADIE la lanzaba (cazado 2026-07-29: flecha rancia 9h con flota "arriba").
if ! pgrep -f "scripts/compass_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/compass_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: compass_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# factor overnight de la flecha (2026-07-28 "night compass has as weight the NQ"): NQ/ES +
# Corea + sentimiento X -> data/overnight_ctx.json (overnight_structure en direction_view).
if ! pgrep -f "scripts/overnight_feed_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/overnight_feed_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: overnight_feed_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"

# refresca levels_<sym>.json para los 24+ simbolos sin chart_bridge vivo.
# SECUENCIAL (Mac 8GB): ciclo completo ~120s en RTH, duerme 300s fuera de RTH.
if ! pgrep -f "scripts/levels_refresh_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/levels_refresh_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: levels_refresh_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi
fi

# price_alarm estaba en la lista de APAGADO (linea 47 y 60) pero NUNCA en la de
# arranque: el watcher de alarmas de precio no lo levantaba nadie (medido 2026-07-27).
if ! pgrep -f "scripts/price_alarm_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/price_alarm_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: price_alarm_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# Perpetuos: perp_stock_fetch.py era one-shot y su JSON llego a 5h46m rancio; el
# puente vuelca data/perp_stocks.json -> data/nbbo_<sym>usdt.txt para price_alarm.
if ! pgrep -f "scripts/perp_stock_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/perp_stock_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: perp_stock_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi
if ! pgrep -f "scripts/perp_nbbo_bridge_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/perp_nbbo_bridge_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: perp_nbbo_bridge_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# MANADA: era el unico daemon de senal sin keepalive (el denominador de la flota).
if ! pgrep -f "scripts/fleet_consensus_keepalive.sh" >/dev/null; then
  nohup bash "$ROOT/scripts/fleet_consensus_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: fleet_consensus_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# x_signal_poster (2026-07-21): postea en X las señales FUERTES de la flota
# (prob>=70, ballenas >=3:1, retest-ok/reclaim/ruptura) + combos multi-ticker
# de data/x_combo_triggers.txt. SEÑAL-SOLAMENTE; ledger compartido
# data/x_plan_budget.json (10 posts/dia, $4/mes) con x_plan_poster/postmortem.
if ! pgrep -f "scripts/x_signal_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/x_signal_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: x_signal_keepalive lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi

# ---- dip alert (mision B5 2026-07-22): valuacion 1x/dia + vigia de dips RTH ----
# finviz_valuation idempotente (<24h no re-baja). dip_alert muere solo 15:30.
"$ROOT/venv/bin/python" "$ROOT/scripts/finviz_valuation.py" >> "$ROOT/logs/dip_alert.log" 2>&1
HHMM=$(date +%H%M); DOW=$(date +%u)
if [ "$DOW" -le 5 ] && [ "$HHMM" -ge 0930 ] && [ "$HHMM" -lt 1530 ] \
   && ! pgrep -f "scripts/dip_alert.py" >/dev/null; then
  nohup "$ROOT/venv/bin/python" -u "$ROOT/scripts/dip_alert.py" >> "$ROOT/logs/dip_alert.log" 2>&1 &
  echo "$(date) fleet: dip_alert lanzado (pid $!)" >> "$ROOT/logs/fleet_autostart.log"
fi
