#!/bin/zsh
# print_mon_plans.sh — lunes 9:25AM: regenera e imprime el plan (tree + muros + picaro) de QQQ, DRAM y SPY.
# Programado por launchd com.ibtrader.printplans. SEÑAL-SOLAMENTE.
cd /Users/yuniorrodriguezosorio/ib-trader || exit 1

LOG=printplans.log
DAY=$(date +%Y-%m-%d)
HOY=${IBT_DESKTOP_HOY:-$HOME/Desktop/ib-trader/hoy}   # ruta derivada, ver daily_archive.py
mkdir -p "$HOY"
DEST=$HOY/planes-$DAY
PRINTER=HP_OfficeJet_Pro_9120e_Series

# Yunior 2026-07-27: "no imprimas de nuevo, a menos q te diga". GENERAR sí, MANDAR A PAPEL solo
# con IBT_ALLOW_PRINT=1 (o --print). Default: se generan los PDF y NO se imprime.
ALLOW_PRINT=${IBT_ALLOW_PRINT:-0}
[[ "$1" == "--print" ]] && ALLOW_PRINT=1

echo "$(date) === print_mon_plans QQQ,DRAM,SPY (imprimir=$ALLOW_PRINT) ===" >> $LOG
./venv/bin/python scripts/daily_fleet_plans.py --tickers QQQ,DRAM,SPY --no-email --outdir "$DEST" >> $LOG 2>&1

for SYM in QQQ DRAM SPY; do
  PDF=$DEST/${SYM}_plan.pdf
  if [[ ! -s $PDF ]]; then
    echo "$(date) ⚠ falta $PDF" >> $LOG
  elif [[ "$ALLOW_PRINT" == "1" ]]; then
    lpr -P $PRINTER "$PDF" && echo "$(date) impreso $SYM" >> $LOG
  else
    echo "$(date) generado $SYM (NO impreso: IBT_ALLOW_PRINT=0)" >> $LOG
  fi
done

MSG=$([[ "$ALLOW_PRINT" == "1" ]] && echo "🖨 Impreso" || echo "📄 Generado (sin imprimir)")
osascript -e "display notification \"$MSG QQQ + DRAM + SPY (tree)\" with title \"ib-trader lunes 9:25AM\"" 2>/dev/null
