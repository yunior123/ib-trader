#!/bin/zsh
# Un punto de control nocturno. Lo ARMA data/night_monitor_until.txt (una fecha ISO local):
# sin ese fichero no corre nada, y el propio control final lo borra. Asi el plist puede vivir
# cargado para siempre sin disparar noches que nadie pidio.
# El control de la ventana 09:20-09:35 es el FINAL: publica el post de X y desarma.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1
UNTIL_F="data/night_monitor_until.txt"
[[ -f "$UNTIL_F" ]] || exit 0
UNTIL=$(tr -d '[:space:]' < "$UNTIL_F")
[[ -n "$UNTIL" ]] || exit 0

SYM=${NIGHT_MONITOR_SYM:-SPY}
H=$(date +%H%M)
FINAL=()
if [[ "$H" -ge 0920 && "$H" -le 0935 ]]; then FINAL=(--final); fi

./venv/bin/python -u scripts/night_monitor.py --sym "$SYM" --deadline "$UNTIL" "${FINAL[@]}"
rc=$?

# desarme: tras el control final, o si ya pasamos la fecha limite
if [[ ${#FINAL} -gt 0 ]] || [[ "$(date +%Y-%m-%dT%H:%M)" > "$UNTIL" ]]; then
  rm -f "$UNTIL_F"
  echo "$(date) night_monitor DESARMADO (limite $UNTIL)"
fi
exit $rc
