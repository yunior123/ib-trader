#!/bin/bash
# build del GATE de opciones — flags canonicos de la flota (skill cpp23-fleet).
# SECUENCIAL (Mac 8GB): release primero, ASan despues. Cero warnings.
set -e
cd "$(dirname "$0")/.."
# Apple Silicon: clang rechaza -march=native en arm64 -> -mcpu=native.
ARCHFLAG="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCHFLAG="-march=native"
echo "== release =="
clang++ -std=c++23 -O3 $ARCHFLAG -Wall -Wextra -o gate scripts/gate.cpp
echo "== asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o gate_asan scripts/gate.cpp
echo "OK: ./gate + ./gate_asan"
