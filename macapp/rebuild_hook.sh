#!/bin/zsh
# rebuild_hook.sh — lo llama .git/hooks/post-commit en background. Decide si el
# commit toca algo que va DENTRO del .app y, si toca, reconstruye UNA sola vez
# aunque lleguen 10 commits seguidos.
#
# Por que existe (medido 2026-07-26): el post-commit viejo solo miraba '^macapp/'.
# En 24 h hubo 21 commits que cambiaban charts/live.html, scripts/chart_bridge.py,
# gex_core, direction_view, order_engine... — todos DENTRO del bundle — y ninguno
# disparo rebuild. La .app del escritorio solo se refrescaba de casualidad.
# Y con 5 agentes commiteando a la vez, disparar un build por commit son varios
# clang++/swiftc simultaneos en un Mac de 8 GB (el que congelo Chrome con 121.958
# pageouts). De ahi la ventana de silencio + coalescencia.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 0
[ -f macapp/build.sh ] || exit 0

QUIET=${IBT_REBUILD_QUIET:-90}      # s de silencio: absorbe rafagas de commits
PENDING=macapp/.rebuild-pending
LOG=macapp/build.log

# --- toca el commit algo empotrado? ---
CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD)
[ -n "$CHANGED" ] || exit 0
HIT=0
while IFS= read -r pat; do
  case "$pat" in ""|"#"*) continue;; esac
  case "$pat" in
    */) echo "$CHANGED" | grep -q "^$pat" && HIT=1;;
    *)  echo "$CHANGED" | grep -qx "$pat" && HIT=1;;
  esac
  [ $HIT -eq 1 ] && break
done < <(sed 's/#.*//' macapp/bundled_paths.txt | tr -d ' ')
[ $HIT -eq 1 ] || exit 0

date '+%F %T' > "$PENDING"

# Si ya hay un build (o una espera) en curso, basta con haber marcado PENDING:
# el que corre lo vera y volvera a construir al terminar.
if [ -d macapp/.build.lockd ] || [ -f macapp/.rebuild-waiting ]; then
  echo "[rebuild] ya hay build/espera en curso — marcado pendiente" >> "$LOG"
  exit 0
fi

: > macapp/.rebuild-waiting
trap 'rm -f macapp/.rebuild-waiting' EXIT INT TERM
sleep "$QUIET"
rm -f macapp/.rebuild-waiting

# hasta 3 pasadas: si entran commits MIENTRAS se construye, se reconstruye otra vez
for _ in 1 2 3; do
  [ -f "$PENDING" ] || break
  rm -f "$PENDING"
  { echo "===== $(date '+%F %T') rebuild ($(git rev-parse --short HEAD)) ====="; zsh macapp/build.sh; } >> "$LOG" 2>&1
done
