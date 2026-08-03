#!/bin/zsh
set -e
cd "$(dirname "$0")/.." || exit 1
mkdir -p bin
clang++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  -o bin/finviz_screener_watch scripts/finviz_screener_watch.cpp -lcurl
bin/finviz_screener_watch --selftest
echo "✅ bin/finviz_screener_watch"
