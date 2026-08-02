#!/bin/zsh
# 09:35 ET (open+5): regenera arbol + plan del universo data/print_syms_open5.txt con el
# libro fresco y los MANDA AL HP. Yunior 2026-07-30 "print spy again 5 min after market open,
# do the same for apple". Programado por launchd com.ibtrader.printopen5. Senal-solamente.
# El nombre del fichero se mantiene por compatibilidad; el universo ya NO esta en el codigo.
# SIN --envelope (2026-08-02): la valla la escribe SOLO com.ibtrader.fence (09:12 y 15:56, los 30
# de fleet.txt). A las 09:35 el straddle ATM se toma en los 5 minutos de spread mas ancho e IV mas
# alta del dia, y dejaba SPY/AAPL con valla de procedencia distinta a los otros 28. La doctrina
# (skill expected-move-envelope) captura el straddle <=15:55 y la valla DESCRIBE el dia entero.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1
exec ./scripts/print_plans.sh --syms-file data/print_syms_open5.txt \
  --market-day --trees --tag open5 --print
