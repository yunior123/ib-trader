#!/bin/zsh
# fleet_keepalive_start.sh — arranca los 4 keepalives de los signal bots
# (16 bots: dram/nok/spcx/tsla + nvda/txn/tsm/amd/intc/asml/aapl + gld/qqq + slv/cper/uso). Idempotente: si un keepalive ya corre, no lo duplica
# (dos keepalives del mismo bot se matarian el bot mutuamente). launchd lo
# re-ejecuta cada 5 min (StartInterval) = watchdog de los watchdogs.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
# MODO SUEÑO (orden Yunior 2026-07-16 noche "alertas dormidas tambien"):
# si data/fleet_sleep existe, se APAGA todo salvo bridge de datos + tws_watchdog
# y launchd no revive nada. Despertar: rm data/fleet_sleep (+ focus_ticker del dia).
if [[ -f "$ROOT/data/fleet_sleep" ]]; then
  # AUTO-DESPERTAR (sorpresa 2026-07-16): si fleet_sleep contiene "wake: <epoch>"
  # y ya paso la hora, el candado se quita solo y la flota amanece armada.
  WAKE=$(grep -o 'wake: [0-9]*' "$ROOT/data/fleet_sleep" 2>/dev/null | awk '{print $2}')
  if [[ -n "$WAKE" && "$(date +%s)" -ge "$WAKE" ]]; then
    rm -f "$ROOT/data/fleet_sleep"
    echo "$(date) fleet: AUTO-DESPERTAR (wake $WAKE alcanzado)" >> "$ROOT/fleet_autostart.log"
    osascript -e 'display notification "La flota amaneció sola: bots, sirenas y feeds armados. Buen OPEX." with title "🌅 FLOTA DESPIERTA" sound name "ProChord"' 2>/dev/null
  else
    for p in price_alarm_keepalive.sh opt_sentinel_keepalive.sh options_enrich_keepalive.sh opt_chain_keepalive.sh bargain_keepalive.sh sox_keepalive.sh finviz_scout_keepalive.sh notify_relay.sh; do
      pkill -f "scripts/$p" 2>/dev/null
    done
    pkill -f 'scripts/sox_index_feed.py' 2>/dev/null
    pkill -x finviz_scout 2>/dev/null
    pkill -x price_alarm 2>/dev/null
    pkill -f 'scripts/opt_sentinel.py' 2>/dev/null
    pkill -f 'scripts/options_enrich.py' 2>/dev/null
    pkill -f 'scripts/opt_chain_cache.py' 2>/dev/null
    for b in dram nok spcx tsla nvda txn tsm amd intc asml aapl gld qqq slv cper uso skhy skhynix samsung kospi mu smh; do
      pkill -f "scripts/${b}_keepalive.sh" 2>/dev/null
      pkill -x "${b}_signal_bot" 2>/dev/null
    done
    exit 0
  fi
fi
# MODO FOCO (orden Yunior 2026-07-16 "run fleet bot for intc only today"):
# si data/focus_ticker existe, solo los tickers listados ahi corren; el resto
# se APAGA en cada tick de 5 min. Restaurar flota completa: rm data/focus_ticker
FOCUS="$ROOT/data/focus_ticker"
for b in dram nok spcx tsla nvda txn tsm amd intc asml aapl gld qqq slv cper uso skhy skhynix samsung kospi mu smh; do
  if [[ -s "$FOCUS" ]] && ! grep -qix "$b" "$FOCUS"; then
    pkill -f "scripts/${b}_keepalive.sh" 2>/dev/null
    pkill -x "${b}_signal_bot" 2>/dev/null
    continue
  fi
  if ! pgrep -f "scripts/${b}_keepalive.sh" >/dev/null; then
    nohup zsh "$ROOT/scripts/${b}_keepalive.sh" >/dev/null 2>&1 &
    echo "$(date) fleet: ${b}_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
  fi
done

# daemon de VOZ SERIALIZADA (Yunior 2026-07-18: las voces se cortaban entre sí).
# Un solo consumidor habla; price_alarm + bots encolan con speak.sh. Ver
# docs/VOICE-QUEUE.md. Señal-solamente. Arranca antes que los productores.
if ! pgrep -f "voice_queue.sh" >/dev/null; then
  nohup ./scripts/voice_queue_keepalive.sh >> fleet_autostart.log 2>&1 &
  echo "$(date) fleet: voice_queue daemon lanzado (pid $!)" >> fleet_autostart.log
fi

# daemon IBKR de flota — FUENTE UNICA desde 2026-07-15 ("connect to ibkr
# only"; subs NA reales compradas: Cboe One + Network A/B/C, 10089 muerto).
# SIP warm-up historico + bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt.
# Reader C++ en modo IBKR-ONLY (sin alpaca; ALPACA_FALLBACK=1 revive dual).
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup ./venv/bin/python scripts/ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO SKHY MU SMH GOOGL QCOM MSFT AVGO AMZN META XLK >> bridge_ibkr_fleet.log 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >> fleet_autostart.log
fi

# bridge KRX realtime (SK Hynix + Samsung) — sub Korea waived cubre la API
# (verificado 2026-07-12): mercado de memoria/DRAM en vivo y gratis, lider ~13h
# antes que EE.UU. para MU/DRAM. Escribe data/bars_{skhynix,samsung}.txt.
if ! pgrep -f "scripts/korea_bar_bridge.py" >/dev/null; then
  nohup ./venv/bin/python scripts/korea_bar_bridge.py --daemon >> bridge_korea.log 2>&1 &
  echo "$(date) fleet: korea bridge lanzado (pid $!)" >> fleet_autostart.log
fi

# TWS watchdog (2026-07-15, tras 75 min de ceguera): vigila puerto 7496 en
# ventanas de mercado, relanza TWS colgado y GRITA por el login (que siempre
# es del humano). El eslabon debil del dia fue TWS, no las señales.
if ! pgrep -f "scripts/tws_watchdog.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/tws_watchdog.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: tws_watchdog lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# cache de cadenas de opciones (v6.1 2026-07-16 noche): opt_chain_cache.py
# (ib_insync readonly clientId 48) vuelca cada 3 min en RTH la cadena ±6% ATM
# (2 vencimientos, 17 syms) a data/opt_chain_<sym>.txt; lector instantaneo:
# ./opt_quick NVDA [strike C|P]. SEÑAL-SOLAMENTE, cero ordenes.
if [ -f "$ROOT/scripts/opt_chain_cache.py" ] && ! pgrep -f "scripts/opt_chain_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/opt_chain_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: opt_chain_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# bargain bot (2026-07-15): gangas en flota + top gainers + oversold, vetadas
# por TradingAgents — solo BUY notifica. Signal-only, cada 10 min en RTH.
if ! pgrep -f "scripts/bargain_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/bargain_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: bargain_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
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
  echo "$(date) fleet: sox_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# finviz_scout (2026-07-17): datos Finviz Elite que IBKR no da (short float,
# gap, rel vol, earnings, target/recom) -> data/finviz_<sym>.txt cada 60s
# premarket / 180s RTH; banners SOLO en cambios de estado. Señal-solamente,
# token en feeds.env, un request por ciclo. Compilar si falta el binario:
# clang++ -std=c++17 -O2 -o finviz_scout scripts/finviz_scout.cpp -lcurl
if [ -x "$ROOT/finviz_scout" ] && ! pgrep -f "scripts/finviz_scout_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/finviz_scout_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: finviz_scout_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# notify_relay (2026-07-17): espejo Desktop -> ntfy push + Resend email (solo 🚨).
# Anti-ruido: alertas >45s se DESCARTAN (jamas acumular).
if ! pgrep -f "scripts/notify_relay.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/notify_relay.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: notify_relay lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi
