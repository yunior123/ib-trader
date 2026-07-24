#!/bin/bash
# ib_mode.sh — cambia paper<->live en un solo lugar (data/ib_mode.txt) y avisa qué reiniciar.
# Uso: scripts/ib_mode.sh [paper|live]   (sin arg = muestra estado)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
if [ $# -eq 0 ]; then
  python3 "$REPO/scripts/ib_mode.py"; exit 0
fi
python3 "$REPO/scripts/ib_mode.py" "$1"
echo "→ reinicia los lectores TWS para tomar el puerto nuevo:"
echo "   pkill -f opt_chain_cache.py   # la cadena reconecta al puerto del modo"
echo "   (el order_engine toma el modo en su arranque: --paper/--live o data/ib_mode.txt)"
