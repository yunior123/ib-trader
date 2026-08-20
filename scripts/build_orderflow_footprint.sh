#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
ARCHFLAG="-mcpu=native"
clang++ -std=c++23 -O3 $ARCHFLAG -Wall -Wextra -o bin/orderflow_footprint scripts/orderflow_footprint.cpp
echo "OK: ./bin/orderflow_footprint"
