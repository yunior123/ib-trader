#!/bin/zsh
# print_mon_plans.sh — lunes 9:25AM: regenera e imprime el plan (tree + muros + picaro) de QQQ, DRAM y SPY.
# Programado por launchd com.ibtrader.printplans. SEÑAL-SOLAMENTE.
cd /Users/yuniorrodriguezosorio/ib-trader || exit 1

LOG=printplans.log
DAY=$(date +%Y-%m-%d)
DEST=$HOME/Desktop/planes-$DAY
PRINTER=HP_OfficeJet_Pro_9120e_Series

echo "$(date) === print_mon_plans QQQ,DRAM,SPY ===" >> $LOG
./venv/bin/python scripts/daily_fleet_plans.py --tickers QQQ,DRAM,SPY --no-email >> $LOG 2>&1

for SYM in QQQ DRAM SPY; do
  PDF=$DEST/${SYM}_plan.pdf
  if [[ -s $PDF ]]; then
    lpr -P $PRINTER "$PDF" && echo "$(date) impreso $SYM" >> $LOG
  else
    echo "$(date) ⚠ falta $PDF — no impreso" >> $LOG
  fi
done

osascript -e 'display notification "🖨 Impreso QQQ + DRAM + SPY (tree)" with title "ib-trader lunes 9:25AM"' 2>/dev/null
