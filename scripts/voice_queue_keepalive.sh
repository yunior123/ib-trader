#!/bin/bash
# voice_queue_keepalive.sh — mantiene vivo el daemon de voz serializada.
# Mismo patrón que los demás keepalives de la flota. Arráncalo al reencender.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
while true; do
  if ! pgrep -f "voice_queue.sh" >/dev/null 2>&1; then
    "$ROOT/scripts/voice_queue.sh" >/dev/null 2>&1 &
  fi
  sleep 10
done
