#!/bin/bash
# build de la FLECHA PREMARKET — flags canonicos de la flota. SECUENCIAL (Mac 8GB).
set -e
cd "$(dirname "$0")/.."
mkdir -p bin
while [ "$(ps aux | grep -c '[c]lang++')" -gt 0 ]; do echo "esperando a otro clang++..."; sleep 5; done
echo "== release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bin/premarket_arrow scripts/premarket_arrow.cpp
while [ "$(ps aux | grep -c '[c]lang++')" -gt 0 ]; do sleep 5; done
echo "== asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o premarket_arrow_asan scripts/premarket_arrow.cpp
echo "OK: bin/premarket_arrow + ./premarket_arrow_asan"
