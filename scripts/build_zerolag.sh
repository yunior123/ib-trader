#!/bin/bash
# build del Zero Lag Trend Signals (MTF). Cero warnings.
set -e
cd "$(dirname "$0")/.."
ARCHFLAG="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCHFLAG="-march=native"
clang++ -std=c++23 -O3 $ARCHFLAG -Wall -Wextra -o bin/zerolag scripts/zerolag.cpp
echo "OK: ./bin/zerolag"
