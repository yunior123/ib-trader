#!/bin/zsh
# appfresh.sh — UNA linea: ¿la .app del escritorio es la del ultimo commit?
#   zsh macapp/appfresh.sh
# Compara el sello IBTCommit del bundle contra el ultimo commit que toca algo
# empotrado (macapp/bundled_paths.txt). El mtime NO sirve: un rebuild sin cambios
# lo refresca y parece fresco cuando no lo es.
set -uo pipefail
cd "$(dirname "$0")/.."
APP="${1:-$HOME/Desktop/ib-trader/ib-trader Cockpit.app}"
PL="$APP/Contents/Info.plist"
[ -f "$PL" ] || { echo "🔴 no hay .app en $APP"; exit 1; }

SHA=$(/usr/libexec/PlistBuddy -c "Print :IBTCommit" "$PL" 2>/dev/null || echo "")
BUILT=$(/usr/libexec/PlistBuddy -c "Print :IBTBuildDate" "$PL" 2>/dev/null || echo "?")
[ -n "$SHA" ] || { echo "🔴 .app SIN SELLO (build anterior al sello) — reconstruye: zsh macapp/build.sh"; exit 1; }

PATHS=$(sed 's/#.*//' macapp/bundled_paths.txt | tr -d ' ' | grep -v '^$' | tr '\n' ' ')
LAST=$(git log -1 --format='%h' -- ${=PATHS})
LASTMSG=$(git log -1 --format='%cd %s' --date=format:'%m-%d %H:%M' -- ${=PATHS} | cut -c1-70)

if [ "${SHA%%+*}" = "$LAST" ] || git merge-base --is-ancestor "$LAST" "${SHA%%+*}" 2>/dev/null; then
  echo "✅ AL DIA — .app=$SHA (build $BUILT) · ultimo commit empotrado $LAST"
else
  echo "🔴 RANCIA — .app=$SHA (build $BUILT) · falta $LAST $LASTMSG"
  echo "   arregla:  zsh macapp/build.sh"
  exit 1
fi
