#!/usr/bin/env bash
# build.sh — order_engine (C++23) contra la API C++ oficial de IBKR TWS.
# Enlace ESTÁTICO (libTwsSocketClient.a + libbid.a) -> sin rpath/DYLD.
# Mac 8GB: compila SECUENCIAL. Se corre desde cualquier sitio (usa BASH_SOURCE).
#
# Prerrequisitos (una vez, ver .claude/skills/ibkr-tws/SKILL.md §"Build macOS"):
#   scalper/vendor/lib/libbid.a               (Intel Decimal FP)
#   scalper/vendor/IBJts/cppclient/client/    (fuentes API TWS vendoreadas)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

CLIENT="scalper/vendor/IBJts/cppclient/client"
LIB="scalper/vendor/lib"
OUT="order_engine/order_engine"

# Apple Silicon: clang usa -mcpu=native (NO -march=native, que rechaza en arm64).
ARCHFLAG="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCHFLAG="-march=native"

[ -f "$LIB/libbid.a" ] || { echo "FALTA $LIB/libbid.a — construir la Intel lib primero (skill ibkr-tws)"; exit 1; }

# --- PASO 1: cliente TWS vendoreado -> libTwsSocketClient.a (static, c++17) ---
# Recompilar también cuando cambió una fuente/header: saltarlo dejaría el nuevo
# campo de protocolo fuera del binario aunque el header compilase.
TWS_STALE=0
if [ ! -f "$LIB/libTwsSocketClient.a" ] || \
   find "$CLIENT" -maxdepth 1 \( -name '*.cpp' -o -name '*.h' \) -newer "$LIB/libTwsSocketClient.a" -print -quit | grep -q .; then
  TWS_STALE=1
fi
if [ "$TWS_STALE" = "1" ]; then
  echo "[1/2] compilando cliente TWS -> libTwsSocketClient.a"
  ( cd "$CLIENT" && clang++ -std=c++17 -O2 -fPIC -pthread -I. -c *.cpp -w \
        && ar rcs "$REPO/$LIB/libTwsSocketClient.a" *.o && rm -f *.o )
else
  echo "[1/2] libTwsSocketClient.a ya existe — salto"
fi

# --- PASO 2: motor (c++23) enlazado estático contra las dos libs ---
echo "[2/2] compilando order_engine (c++23 $ARCHFLAG)"
clang++ -std=c++23 -O3 $ARCHFLAG -pthread -Wall -Wextra -Wno-unused-parameter \
  -I"$CLIENT" \
  order_engine/tws_adapter.cpp order_engine/order_engine.cpp \
  "$LIB/libTwsSocketClient.a" "$LIB/libbid.a" \
  -o "$OUT"

echo "OK -> $OUT"
