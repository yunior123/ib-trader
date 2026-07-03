#!/bin/zsh
# Build reproducible del selector y backtest de alertas de opciones dinámicas.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p bin

echo "== options alert engine =="
clang++ -std=c++17 -O2 -Wall -Wextra \
  -o bin/options_alert_engine scripts/options_alert_engine.cpp

echo "== options alert backtest =="
clang++ -std=c++17 -O2 -Wall -Wextra \
  -o bin/options_alert_backtest scripts/options_alert_backtest.cpp -lsqlite3

echo "== options alert unit test =="
TEST_BIN="${TMPDIR:-/tmp}/ibtrader-options-alert-test.$$"
trap 'rm -f "$TEST_BIN"' EXIT INT TERM
clang++ -std=c++17 -O2 -Wall -Wextra \
  -o "$TEST_BIN" tests/test_options_alert_engine.cpp
"$TEST_BIN"
echo "OK: bin/options_alert_engine + bin/options_alert_backtest"
