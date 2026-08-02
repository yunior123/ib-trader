#!/bin/zsh
# shock_snapshot_run.sh — 16:40 ET (lun-vie): recalibra shock+reversion DIARIA -> data/shock_snapshot.json
# Diario, no intradia: la reversion se mide con cierres diarios; un daemon 1m no aporta dato nuevo.
ROOT=${0:A:h}/..
cd "$ROOT" || exit 1
LOG="$PWD/logs/shock_calibrator.log"
mkdir -p "$PWD/logs"

SNAP="$PWD/data/shock_snapshot.json"
BEFORE=0
[[ -f $SNAP ]] && BEFORE=$(stat -f %m "$SNAP")

SYMS=($(<data/provider_syms.txt))
echo "$(date) === shock_calibrator --once (${#SYMS} simbolos) ===" >> $LOG
PYTHONPATH="$PWD/mit" ./venv-mit/bin/python scripts/shock_calibrator.py --once "${SYMS[@]}" >> $LOG 2>&1
RC=$?

AFTER=0
[[ -f $SNAP ]] && AFTER=$(stat -f %m "$SNAP")
# N vacio = json ausente/roto: se trata como 0 y GRITA. Jamas se rellena con un plausible.
N=$(./venv-mit/bin/python -c "import json,sys;d=json.load(open('$SNAP'));print(len(d.get('symbols') or {}))" 2>/dev/null)
[[ -z $N ]] && N=0

if (( RC != 0 )) || (( AFTER == BEFORE )) || (( N == 0 )); then
  echo "$(date) ⚠ shock_snapshot NO actualizado (rc=$RC mtime ${BEFORE}->${AFTER} symbols=$N)" >> $LOG
  osascript -e 'display notification "shock_snapshot NO se actualizo — sin reversion medida" with title "⚠ ib-trader shockcalib"' 2>/dev/null
  exit 1
fi
echo "$(date) shock_snapshot ok: $N simbolos" >> $LOG
