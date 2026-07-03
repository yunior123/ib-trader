#!/bin/zsh
# 09:20 ET (premarket): arboles + plan del universo. NO a las 09:12: ahi corre el APERTURA de
# com.ibtrader.dailyplans sobre el MISMO daily_fleet_plans.py y se pisarian. Yunior 2026-07-30
# "send tree for aapl too, before market open and 5 min after open". launchd: com.ibtrader.printpremarket.
# Senal-solamente.
ROOT=${0:A:h:h}
cd "$ROOT" || exit 1
# sin --envelope: com.ibtrader.fence ya corre em_envelope --all a las 09:12 (misma escritura)
exec ./scripts/print_plans.sh --syms-file data/print_syms_premarket.txt \
  --market-day --trees --tag premarket --print
