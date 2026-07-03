#!/bin/zsh
# run_dedupe.sh — el warm-up del bridge no puede envenenar los indicadores vivos.
# Compila UN bot real (nvda por defecto) + el test, y conduce el binario por --stdin.
# Uso: zsh tests/cpp/run_dedupe.sh [sym]      (desde cualquier sitio)
#
# Mac 8GB: UNA compilacion a la vez (doctrina). Se espera si hay otro clang++ vivo.
# Doble build del TEST (release + ASan/UBSan) por doctrina cpp23-testing; el BOT se
# compila una sola vez y con los flags de produccion (deploy_signals_to_data.sh),
# porque lo que se prueba es el binario que corre en la flota.

set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
SYM="${1:-nvda}"

STD="-std=c++2c"
ARCH="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCH="-march=native"

espera_clang() {   # pgrep, NO `ps | grep`: el grep se caza a si mismo por la linea de
  # comando y espera para siempre. El patron va escapado: pgrep lo trata como regex
  # y `clang++` crudo es "repetition-operator operand invalid" (fallaba en silencio).
  local n=0
  while [ "$(pgrep -x 'clang\+\+' | wc -l | tr -d ' ')" -gt 0 ] && [ $n -lt 120 ]; do
    sleep 2; n=$((n+1))
  done
}

echo "=== 1/3 bot real ${SYM}_signal_bot (flags de produccion) ==="
espera_clang
clang++ $STD -O3 $ARCH -Wall -Wextra -o /tmp/${SYM}_signal_bot_test ${SYM}_signal_bot.cpp

echo "=== 2/3 test (release) ==="
espera_clang
clang++ $STD -O3 $ARCH -Wall -Wextra -o /tmp/bar_dedupe_test tests/cpp/bar_dedupe_test.cpp
/tmp/bar_dedupe_test /tmp/${SYM}_signal_bot_test data/bars_${SYM}_ibkr.txt
REL=$?

echo ""
echo "=== 3/3 test (ASan + UBSan) ==="
espera_clang
clang++ $STD -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
        -Wall -Wextra -o /tmp/bar_dedupe_test_asan tests/cpp/bar_dedupe_test.cpp
/tmp/bar_dedupe_test_asan /tmp/${SYM}_signal_bot_test data/bars_${SYM}_ibkr.txt
ASAN=$?

echo ""
if [ $REL -eq 0 ] && [ $ASAN -eq 0 ]; then
  echo "✓ dedupe por epoch OK en ${SYM} (release + ASan)"
  echo "  (el parche es IDENTICO en los 24 bots: ver git show del commit)"
  exit 0
else
  echo "✗ fallos: release=$REL asan=$ASAN"
  exit 1
fi
