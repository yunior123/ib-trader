#!/bin/bash
# voice_queue.sh — daemon de VOZ SERIALIZADA (Yunior 2026-07-18: "las voces se
# interponen en mi mac y apenas escucho").
#
# PROBLEMA raíz: los 23 signal_bots + price_alarm lanzaban `killall say; say ... &`
# — cada alerta CORTABA a la anterior a media frase → ininteligible en avalanchas.
#
# FIX: un solo consumidor habla. Los productores ENCOLAN (scripts/speak.sh) y este
# daemon reproduce SECUENCIALMENTE (sin &, sin killall) → cada frase se oye entera.
# Extras:
#   - Descarte de STALE: voz de trading >25s vieja = ruido → se tira (no acumula).
#   - Coalescing: en avalancha de misma prioridad, dice el más reciente + "y N más".
#   - Prioridad DANGER > SIGNAL > INFO; UNA sola voz (la del sistema, ver abajo) —
#     la distinción por tipo la da el contenido, no la voz (2026-07-19).
#
# Compatible con bash 3.2 (macOS) — SIN arrays asociativos.
# Señal-solamente (ley #0): solo lee la cola y llama `say`. Cero red, cero órdenes.
# Arráncalo con scripts/voice_queue_keepalive.sh.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
Q="$ROOT/data/voice"
mkdir -p "$Q"
STALE=25
PIDFILE="$ROOT/data/voice_queue.pid"
# INSTANCIA ÚNICA: dos daemons compitiendo por la cola duplican/pierden voces
# (pasó en test 2026-07-18: un daemon viejo sobrevivió a su limpieza). Si ya hay
# uno vivo, este NO arranca.
if [ -f "$PIDFILE" ]; then
  old=$(cat "$PIDFILE" 2>/dev/null)
  [ -n "$old" ] && kill -0 "$old" 2>/dev/null && exit 0
fi
echo $$ > "$PIDFILE"
cleanup() { rm -f "$PIDFILE"; exit 0; }
trap cleanup INT TERM

# VOZ: Yunior 2026-07-18 eligió la voz SIRI del sistema ("la hermosa, no robótica").
# Las Siri NO son accesibles por `say -v <nombre>` (Apple las bloquea → fallback),
# PERO `say` SIN -v usa la voz del sistema, que Yunior fijó a Siri Voice 2 en
# System Settings > Accessibility > Spoken Content > System Voice. Por eso aquí NO
# pasamos -v: una sola voz hermosa para todo. La distinción por tipo la da el
# CONTENIDO del mensaje (el veto ya dice "Veto...") y el ORDEN por prioridad.
# Para cambiar de voz: cambiar la voz del sistema en Ajustes (no tocar código).

# voice_log en trades.db: qué se HABLÓ / DESCARTÓ (para el backtest 4pm y para
# verificar empíricamente "¿hubo voz?"). No bloquea la voz (corre en background).
DBV="$ROOT/trades.db"
log_voice() {  # $1=action(spoke|preempted|notify_only|coalesced|dropped_stale) $2=prio $3=msg
  local e; e="${3//\'/\'\'}"
  # busy_timeout: bajo escritores concurrentes en WAL, esperar el lock en vez de perder la fila.
  ( sqlite3 "$DBV" "PRAGMA busy_timeout=5000; INSERT INTO voice_log(ts_epoch,action,priority,msg) VALUES(strftime('%s','now'),'$1','$2','$e')" 2>/dev/null ) &
}

# POLÍTICA (Yunior 2026-07-23 "voces a tiempo, jamás con retraso — retraso = dinero"):
#  - DANGER (🐋 ballena / ⏰ price_alarm / 🚀 spike / 🩸 dip): voz INMEDIATA y COMPLETA, y
#    PREEMPTA cualquier voz de menor prioridad en curso (la mata y habla YA). Nunca se retrasa.
#  - SIGNAL: se habla (FIFO; coalesce solo en avalancha >FLOOD) PERO es preemptible por DANGER.
#  - INFO (chatter BB muted, p<55): SOLO notificación Mac (el banner osascript ya lo disparó el
#    emisor) — NO se vocaliza, para no congestionar la cola y retrasar lo importante.
# Latencia de una DANGER = ~0 si nada habla, ~50ms si preempta una SIGNAL. Nunca espera a INFO.
FLOOD=4

danger_present() { set -- "$Q"/*_DANGER.msg; [ -e "${1:-}" ]; }

# habla en background y CEDE si llega un DANGER (para prioridades < DANGER).
# devuelve 0 si terminó de hablar, 1 si fue preemptida.
say_preemptible() {  # $1=msg
  say "$1" >/dev/null 2>&1 &
  local spid=$!
  while kill -0 "$spid" 2>/dev/null; do
    if danger_present; then
      kill "$spid" 2>/dev/null; wait "$spid" 2>/dev/null
      return 1
    fi
    sleep 0.03
  done
  return 0
}

while true; do
  shopt -s nullglob

  # --- INFO: NO se vocaliza (solo notificación Mac, ya mostrada). Se descarta de la cola. ---
  for f in "$Q"/*_INFO.msg; do log_voice notify_only INFO "$(cat "$f" 2>/dev/null)"; rm -f "$f"; done

  # --- DANGER: INMEDIATA, completa, jamás preemptida (más vieja primero) ---
  set -- "$Q"/*_DANGER.msg
  if [ -e "${1:-}" ]; then
    oldest=$(ls -tr "$Q"/*_DANGER.msg 2>/dev/null | head -1)
    msg="$(cat "$oldest" 2>/dev/null)"; rm -f "$oldest"
    log_voice spoke DANGER "$msg"
    say "$msg" >/dev/null 2>&1        # DANGER se habla entera, sin ceder
    continue
  fi

  # --- SIGNAL: FIFO completa (coalesce solo en avalancha), PREEMPTIBLE por DANGER ---
  set -- "$Q"/*_SIGNAL.msg
  if [ -e "${1:-}" ]; then
    cnt=$(ls "$Q"/*_SIGNAL.msg 2>/dev/null | wc -l | tr -d ' ')
    if [ "$cnt" -le "$FLOOD" ]; then
      oldest=$(ls -tr "$Q"/*_SIGNAL.msg 2>/dev/null | head -1)
      msg="$(cat "$oldest" 2>/dev/null)"; rm -f "$oldest"
    else
      newest=$(ls -t "$Q"/*_SIGNAL.msg 2>/dev/null | head -1)
      msg="$(cat "$newest" 2>/dev/null)"
      for f in "$Q"/*_SIGNAL.msg; do [ "$f" = "$newest" ] || log_voice coalesced SIGNAL "$(cat "$f" 2>/dev/null)"; done
      rm -f "$Q"/*_SIGNAL.msg
      msg="$msg, y $(( cnt - 1 )) alertas más"
    fi
    if say_preemptible "$msg"; then log_voice spoke SIGNAL "$msg"; else log_voice preempted SIGNAL "$msg"; fi
    continue
  fi

  sleep 0.05
done
