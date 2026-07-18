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
#   - Prioridad DANGER > SIGNAL > INFO; voces distintas por tipo para distinción.
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

while true; do
  shopt -s nullglob

  # 1) purgar stale
  now=$(date +%s)
  for f in "$Q"/*.msg; do
    m=$(stat -f %m "$f" 2>/dev/null || echo "$now")
    [ $(( now - m )) -gt "$STALE" ] && rm -f "$f"
  done

  # 2) elegir prioridad más alta presente
  best_prio=""
  for p in DANGER SIGNAL INFO; do
    set -- "$Q"/*_"$p".msg
    if [ -e "${1:-}" ]; then best_prio="$p"; break; fi
  done
  # poll 50ms: imperceptible (humano percibe latencia desde ~100ms) y ~40% menos
  # CPU idle que 30ms (medido 2.8%→~1.7%). Un FIFO daría ~0ms pero es frágil en
  # bash 3.2 sin ganancia perceptible.
  if [ -z "$best_prio" ]; then sleep 0.05; continue; fi

  # 3) de esa prioridad: el más reciente (ls -t) + conteo para coalescing
  newest=$(ls -t "$Q"/*_"$best_prio".msg 2>/dev/null | head -1)
  cnt=$(ls "$Q"/*_"$best_prio".msg 2>/dev/null | wc -l | tr -d ' ')
  msg="$(cat "$newest" 2>/dev/null)"
  rm -f "$Q"/*_"$best_prio".msg           # purga toda esa prioridad (coalesce)
  extra=$(( cnt - 1 ))
  [ "$extra" -gt 0 ] && msg="$msg, y $extra alertas más"

  # 4) hablar SERIALIZADO (sin &, sin killall) → no se pisa. SIN -v = voz Siri
  #    del sistema (la hermosa). Sin -r override para naturalidad neuronal.
  say "$msg" >/dev/null 2>&1
done
