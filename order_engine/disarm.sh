#!/usr/bin/env bash
# disarm.sh — desarma YA: borra ARM_LIVE (el motor cae a DRY en la próxima evaluación)
# y si está corriendo lo termina limpio (SIGTERM -> disarm-on-exit cancela sus OE:).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -f "$REPO/order_engine/ARM_LIVE" && echo "ARM_LIVE borrado -> motor en DRY."
if pgrep -f "order_engine/order_engine" >/dev/null; then
  pkill -TERM -f "order_engine/order_engine" && echo "SIGTERM al motor -> cancela sus órdenes y sale."
else echo "(motor no estaba corriendo)"; fi
