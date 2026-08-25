#!/bin/zsh
# Sube cada minuto a D1 las barras 1m que el WebSocket construye en el Mac. Sin esto, el
# chart online depende del REST del vault y con la cuota agotada pinta el ultimo dia bueno
# y el tick vivo con un hueco de horas en medio (medido 2026-08-24 en las seis ventanas).
cd "$(dirname "$0")/.."
LOG=logs/bars_push.log
FAILS=0
N=0
while true; do
  # Cada 30 vueltas se reenvia la ventana entera: el warmup del vault mete barras anteriores
  # a la ultima subida y el push incremental no las alcanzaria.
  if (( N % 30 == 0 )); then ARG=--completo; else ARG=; fi
  N=$((N + 1))
  if ./venv/bin/python scripts/bars_push.py $ARG >> "$LOG" 2>&1; then
    FAILS=0
  else
    FAILS=$((FAILS + 1))
    if (( FAILS == 3 )); then
      echo "$(date) bars_push falla 3 veces seguidas — el chart online se queda sin historia" >> "$LOG"
    fi
  fi
  sleep 60
done
