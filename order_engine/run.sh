#!/usr/bin/env bash
# run.sh — arranca el order_engine. PAPER por default (data/ib_mode.txt).
# Uso: order_engine/run.sh NVDA QQQ            (paper, DRY)
#      order_engine/run.sh --arm-live NVDA     (live SOLO si ARM_LIVE tiene la fecha de hoy)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$REPO"
[ -x order_engine/order_engine ] || bash order_engine/build.sh
MODE="$(cat data/ib_mode.txt 2>/dev/null || echo paper)"
PORTFLAG="--paper"; [ "$MODE" = "live" ] && PORTFLAG="--live"
ARM=""; SYMS=()
for a in "$@"; do case "$a" in
  --arm-live) ARM="--arm-live";; --live) PORTFLAG="--live";; --paper) PORTFLAG="--paper";;
  *) SYMS+=("--sym" "$a");; esac; done
[ ${#SYMS[@]} -gt 0 ] || { echo "uso: run.sh [--arm-live] SYM [SYM...]"; exit 2; }
echo "order_engine $PORTFLAG $ARM (modo $MODE)"
exec order_engine/order_engine $PORTFLAG $ARM "${SYMS[@]}"
