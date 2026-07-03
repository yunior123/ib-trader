#!/bin/bash
# tests del whale scalper: unit (release + ASan) + escenarios replay.
# SECUENCIAL (Mac 8GB).
set -e
cd "$(dirname "$0")/../.."
echo "== unit release =="
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o /tmp/scalper_test scalper/tests/core_test.cpp
/tmp/scalper_test
echo "== unit asan/ubsan =="
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -o /tmp/scalper_test_asan scalper/tests/core_test.cpp
/tmp/scalper_test_asan
echo "== replay scenarios =="
[ -x scalper/whale_scalper ] || ./scalper/build.sh
mkdir -p /tmp/scalper_replay_ledger
FAIL=0
for s in scalper/tests/scenarios/*.jsonl; do
    rm -f /tmp/scalper_replay_ledger/*.jsonl /tmp/scalper_replay_ledger/*.md
    ./scalper/whale_scalper --replay "$s" --ledger /tmp/scalper_replay_ledger || FAIL=1
done
[ $FAIL = 0 ] && echo "TODOS LOS TESTS OK" || { echo "REPLAYS CON FALLOS"; exit 1; }
