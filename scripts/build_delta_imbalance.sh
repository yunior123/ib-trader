#!/bin/bash
# build del VETO de divergencia de delta — flags canonicos de la flota. Cero warnings.
set -e
cd "$(dirname "$0")/.."
ARCHFLAG="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCHFLAG="-march=native"
echo "== release =="
clang++ -std=c++23 -O3 $ARCHFLAG -Wall -Wextra -o bin/delta_imbalance scripts/delta_imbalance.cpp
echo "OK: ./bin/delta_imbalance"
