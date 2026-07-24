#!/usr/bin/env bash
# arm.sh — arma la ejecución LIVE por HOY (escribe ARM_LIVE con la fecha).
# Segunda llave: además hay que lanzar el motor con --arm-live. Caduca fin del día.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
date +%F > "$REPO/order_engine/ARM_LIVE"
echo "ARM_LIVE = $(cat "$REPO/order_engine/ARM_LIVE") (válido SOLO hoy)."
echo "Lanza el motor con --arm-live. Desarmar: order_engine/disarm.sh"
