#!/bin/zsh
# print_plans.sh — genera e imprime el plan (3 pags: muros/griegas, arbol, plan picaro) de los
# tickers que se pasen. Uso: ./scripts/print_plans.sh SPY,AAPL [--print]
# Sin --print (ni IBT_ALLOW_PRINT=1) solo genera: orden Yunior 2026-07-27.
cd /Users/yuniorrodriguezosorio/ib-trader || exit 1
SYMS=${1:?uso: print_plans.sh SYM[,SYM...] [--print]}
LOG=printplans.log
DAY=$(date +%Y-%m-%d)
HOY=${IBT_DESKTOP_HOY:-$HOME/Desktop/ib-trader/hoy}
mkdir -p "$HOY"
DEST=$HOY/planes-$DAY
PRINTER=HP_OfficeJet_Pro_9120e_Series
ALLOW_PRINT=${IBT_ALLOW_PRINT:-0}
[[ "$2" == "--print" ]] && ALLOW_PRINT=1

echo "$(date) === print_plans $SYMS (imprimir=$ALLOW_PRINT) ===" >> $LOG
./venv/bin/python scripts/daily_fleet_plans.py --tickers "$SYMS" --no-email --outdir "$DEST" >> $LOG 2>&1
RC=$?
for SYM in ${(s:,:)SYMS}; do
  PDF=$DEST/${SYM}_plan.pdf
  if [[ ! -s $PDF ]]; then
    echo "$(date) FALTA $PDF (rc=$RC)" | tee -a $LOG
  elif [[ "$ALLOW_PRINT" == "1" ]]; then
    lpr -P $PRINTER "$PDF" && echo "$(date) IMPRESO $SYM -> $PRINTER" | tee -a $LOG
  else
    echo "$(date) generado $SYM (NO impreso)" | tee -a $LOG
  fi
done
