#!/bin/zsh
# build del PERFIL DE VOLUMEN — flags canonicos de la flota (skill cpp23-fleet).
# Un solo clang++ a la vez en el Mac de 8 GB.
cd "$(dirname "$0")/.." || exit 1
while [ "$(ps aux | grep -c '[c]lang++')" -gt 0 ]; do sleep 2; done
set -e
clang++ -std=c++23 -O3 -mcpu=native -Wall -Wextra -o bin/volume_profile scripts/volume_profile.cpp -lsqlite3
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -Wall -Wextra \
    -o volume_profile_asan scripts/volume_profile.cpp -lsqlite3
echo "OK: ./bin/volume_profile + ./volume_profile_asan"
