#!/bin/zsh
# shock_snapshot_run.sh — 16:40 ET (lun-vie): recalibra shock+reversion DIARIA -> data/shock_snapshot.json
# Diario, no intradia: la reversion se mide con cierres diarios; un daemon 1m no aporta dato nuevo.
ROOT=${0:A:h}/..
cd "$ROOT" || exit 1
LOG="$PWD/logs/shock_calibrator.log"
mkdir -p "$PWD/logs"

SNAP="$PWD/data/shock_snapshot.json"
PY="./venv-mit/bin/python"
BEFORE=0
[[ -f $SNAP ]] && BEFORE=$(stat -f %m "$SNAP")

grita() {  # log + notificacion; el runner NUNCA se calla un snapshot incompleto
  echo "$(date) ⚠ $1" >> $LOG
  osascript -e "display notification \"$1\" with title \"⚠ ib-trader shockcalib\"" 2>/dev/null
}

# Universo: MISMA resolucion que shock_calibrator._syms() (provider_syms -> fleet). No se duplica.
PYSYMS='import sys;sys.path.insert(0,sys.argv[1]);import shock_calibrator as sc;print(" ".join(sc._syms()))'
SYMS=($(IBT_DATA_DIR="$PWD/data" $PY -c "$PYSYMS" "$PWD/scripts" 2>>$LOG))
WANT=${#SYMS}
if (( WANT == 0 )); then
  grita "shock_snapshot ABORTADO: universo no resuelto (shock_calibrator._syms vacio)"
  exit 1
fi

echo "$(date) === shock_calibrator --once (${WANT} simbolos) ===" >> $LOG
PYTHONPATH="$PWD/mit" $PY scripts/shock_calibrator.py --once "${SYMS[@]}" >> $LOG 2>&1
RC=$?

AFTER=0
[[ -f $SNAP ]] && AFTER=$(stat -f %m "$SNAP")

# Cobertura: N contra el universo PEDIDO. Un snapshot truncado NO es "ok" (json roto -> 0 ALL).
PYCOV='import json,sys
try:
    got=set(json.load(open(sys.argv[1])).get("symbols") or {})
except Exception:
    print("0 ALL"); raise SystemExit(0)
miss=sorted(set(sys.argv[2:])-got)
print(len(got), ",".join(miss) or "-")'
COV=$($PY -c "$PYCOV" "$SNAP" "${SYMS[@]}" 2>/dev/null)
N=${COV%% *}; MISS=${COV#* }
[[ -z $COV ]] && { N=0; MISS=ALL; }

if (( RC != 0 )) || (( AFTER == BEFORE )) || (( N < WANT )); then
  grita "shock_snapshot NO actualizado (rc=$RC mtime ${BEFORE}->${AFTER} symbols=$N/$WANT faltan: $MISS)"
  exit 1
fi
echo "$(date) shock_snapshot ok: $N/$WANT simbolos" >> $LOG
