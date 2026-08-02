#!/bin/zsh
# 09:35 ET (open+5): regenera arbol + plan + valla del universo data/print_syms_open5.txt con el
# libro fresco y los MANDA AL HP. Yunior 2026-07-30 "print spy again 5 min after market open,
# do the same for apple". Programado por launchd com.ibtrader.printopen5. Senal-solamente.
# El nombre del fichero se mantiene por compatibilidad; el universo ya NO esta en el codigo.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1
exec ./scripts/print_plans.sh --syms-file data/print_syms_open5.txt \
  --market-day --trees --envelope --tag open5 --print
