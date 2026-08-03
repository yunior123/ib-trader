#!/bin/bash
# build del GATEWAY FALSO (replay) — flags canonicos de la flota (skill cpp23-fleet).
# SECUENCIAL (Mac 8GB): release primero, ASan despues. -lsqlite3 = lectura RO de trades.db.
set -e
cd "$(dirname "$0")/.."
echo "== release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bin/replay scripts/replay.cpp -lsqlite3
echo "== asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o replay_asan scripts/replay.cpp -lsqlite3
echo "OK: ./bin/replay + ./replay_asan"
