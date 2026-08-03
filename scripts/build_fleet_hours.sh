#!/bin/bash
# build del PORTERO de la flota — flags canonicos (skill cpp23-fleet).
# Mac de 8GB: un solo clang++ a la vez. Si hay otro compilando, esperamos.
set -e
cd "$(dirname "$0")/.."
while [ "$(ps aux | grep -c '[c]lang++')" -gt 0 ]; do
  echo "esperando: hay otro clang++ compilando (Mac 8GB, uno a la vez)..."
  sleep 5
done
echo "== release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bin/fleet_hours scripts/fleet_hours.cpp
echo "OK: ./bin/fleet_hours"
