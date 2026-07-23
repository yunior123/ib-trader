#!/bin/bash
# build del whale scalper — flags canonicos de la flota (skill cpp23-fleet).
# SECUENCIAL (Mac 8GB): release primero, ASan despues.
set -e
cd "$(dirname "$0")/.."
echo "== release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o scalper/whale_scalper scalper/whale_scalper.cpp
echo "== asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o scalper/whale_scalper_asan scalper/whale_scalper.cpp
echo "OK: scalper/whale_scalper + scalper/whale_scalper_asan"
