#!/bin/bash
# build de la BRUJULA — flags canonicos de la flota (skill cpp23-fleet).
# SECUENCIAL (Mac 8GB): release primero, ASan despues.
set -e
cd "$(dirname "$0")/.."
mkdir -p bin
echo "== release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bin/compass scripts/compass.cpp
cp bin/compass compass
echo "== asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o compass_asan scripts/compass.cpp
echo "OK: ./compass + ./compass_asan"
