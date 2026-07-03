#!/bin/zsh
# run.sh — tests de matematica C++ (correccion + ASan + benchmark)
# Uso: ./tests/cpp/run.sh     (desde cualquier sitio)
#
# 2026-07-24: math_test ahora incluye engines/bb_core.h (CODIGO REAL del repo),
# asi que se compila desde la RAIZ con -I. y no desde tests/cpp.
# Doble build OBLIGATORIO por doctrina (skill cpp23-testing): un test que solo
# pasa en release esta roto. Mac 8GB -> secuencial, una compilacion a la vez.

set -e

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

STD="-std=c++2c"
ARCH="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCH="-march=native"

echo "=== 1/3 correccion (release) ==="
clang++ $STD -O3 $ARCH -Wall -Wextra -I. -o /tmp/math_test tests/cpp/math_test.cpp
/tmp/math_test
REL=$?

echo ""
echo "=== 2/3 correccion (ASan + UBSan) ==="
clang++ $STD -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
        -Wall -Wextra -I. -o /tmp/math_test_asan tests/cpp/math_test.cpp
/tmp/math_test_asan
ASAN=$?

echo ""
echo "=== 3/3 benchmark ==="
clang++ $STD -O3 $ARCH -Wall -I. -o /tmp/bench tests/cpp/bench.cpp
/tmp/bench
BENCH=$?

echo ""
if [ $REL -eq 0 ] && [ $ASAN -eq 0 ] && [ $BENCH -eq 0 ]; then
    echo "✓ release + ASan + bench OK"
    echo "  (recuerda: las copias inline de los 24 bots NO estan cubiertas)"
    exit 0
else
    echo "✗ fallos: release=$REL asan=$ASAN bench=$BENCH"
    exit 1
fi
