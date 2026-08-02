#!/bin/zsh
# Regenera el cubo strike x tiempo del panel TRACE. Lo llama com.ibtrader.tracecube cada 10 min
# en RTH; sin esto el eje de tiempo del terminal se queda congelado en la ultima corrida a mano.
# Simbolos desde data/trace_cube_syms.txt (nada clavado). Senal-solamente.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1
LOG=logs/trace_cube.log
SYMS=$(grep -vE '^\s*(#|$)' data/trace_cube_syms.txt 2>/dev/null | tr '\n' ' ')
[[ -n $SYMS ]] || { echo "$(date) sin data/trace_cube_syms.txt — nada que hacer" >> $LOG; exit 0 }

for SYM in ${=SYMS}; do
  # build_cube LEVANTA si no hay ninguna foto utilizable: se registra y se sigue con el resto,
  # jamas se escribe un cubo vacio que el panel dibujaria como una rejilla de ceros.
  ./venv/bin/python scripts/trace_cube.py "$SYM" >> $LOG 2>&1 \
    || echo "$(date) $SYM sin cubo (ver traza arriba)" >> $LOG
done
