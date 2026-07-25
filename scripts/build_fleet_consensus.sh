#!/bin/bash
# build de la alarma de MANADA — flags canonicos de la flota (skill cpp23-fleet).
# SECUENCIAL (Mac 8GB): release primero, ASan despues.
set -e
cd "$(dirname "$0")/.."
echo "== release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o fleet_consensus scripts/fleet_consensus.cpp
echo "== asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o fleet_consensus_asan scripts/fleet_consensus.cpp
echo "OK: ./fleet_consensus + ./fleet_consensus_asan"
