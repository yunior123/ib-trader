#!/bin/zsh
# run.sh — compile and run C++ math tests
# Usage: ./tests/cpp/run.sh

set -e

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASEDIR"

echo "=== Compiling Math Correctness Tests ==="
echo "clang++ -std=c++2c -O2 -Wall -o math_test math_test.cpp"
clang++ -std=c++2c -O2 -Wall -o math_test math_test.cpp || {
    echo "ERROR: Compilation failed"
    exit 1
}

echo ""
echo "=== Compiling Performance Benchmarks ==="
echo "clang++ -std=c++2c -O3 -march=native -Wall -o bench bench.cpp"
clang++ -std=c++2c -O3 -march=native -Wall -o bench bench.cpp || {
    echo "ERROR: Compilation failed"
    exit 1
}

echo ""
echo "=== Running Correctness Tests ==="
./math_test
TEST_RESULT=$?

echo ""
echo "=== Running Performance Benchmarks ==="
./bench
BENCH_RESULT=$?

echo ""
if [ $TEST_RESULT -eq 0 ] && [ $BENCH_RESULT -eq 0 ]; then
    echo "✓ All tests passed"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi
