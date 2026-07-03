#!/usr/bin/env bash
# run_tests.sh — suite del order_engine. Release + ASan/UBSan, cero warnings.
# Mac 8GB: SECUENCIAL a proposito (un clang++ a la vez).
# Uso: order_engine/tests/run_tests.sh [--fast]     (--fast salta los sanitizers)
set -euo pipefail
SELF="${BASH_SOURCE[0]:-${(%):-%x}}"   # zsh no tiene BASH_SOURCE y el shell de la casa es zsh
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
cd "$REPO/order_engine"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT

ARCHFLAG="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCHFLAG="-march=native"
SUITES=(guards chain orders chase policy)
FAST=0; [ "${1:-}" = "--fast" ] && FAST=1
rc=0
CLIENT="$REPO/scalper/vendor/IBJts/cppclient/client"
LIB="$REPO/scalper/vendor/lib"

for s in "${SUITES[@]}"; do
  while [ "$(ps aux | grep -c '[c]lang++')" -gt 1 ]; do sleep 2; done
  if [ "$s" = "policy" ]; then
    clang++ -std=c++2c -O3 $ARCHFLAG -Wall -Wextra "tests/test_$s.cpp" \
      -I"$CLIENT" "$LIB/libTwsSocketClient.a" "$LIB/libbid.a" -pthread -o "$OUT/$s"
  else
    clang++ -std=c++2c -O3 $ARCHFLAG -Wall -Wextra "tests/test_$s.cpp" -o "$OUT/$s"
  fi
  "$OUT/$s" || rc=1
done

PYTHON="$REPO/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3
"$PYTHON" tests/test_bridge_order_backend.py || rc=1

if [ "$FAST" = "0" ]; then
  for s in "${SUITES[@]}"; do
    while [ "$(ps aux | grep -c '[c]lang++')" -gt 1 ]; do sleep 2; done
    if [ "$s" = "policy" ]; then
      clang++ -std=c++2c -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
        -Wall -Wextra "tests/test_$s.cpp" -I"$CLIENT" \
        "$LIB/libTwsSocketClient.a" "$LIB/libbid.a" -pthread -o "$OUT/asan_$s"
    else
      clang++ -std=c++2c -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
        -Wall -Wextra "tests/test_$s.cpp" -o "$OUT/asan_$s"
    fi
    echo "--- ASan/UBSan $s"
    "$OUT/asan_$s" >/dev/null || rc=1
  done
  [ "$rc" = "0" ] && echo "ASan/UBSan: limpio en las ${#SUITES[@]} suites"
fi

[ "$rc" = "0" ] && echo "=== SUITE VERDE ===" || echo "=== SUITE ROJA ==="
exit $rc
