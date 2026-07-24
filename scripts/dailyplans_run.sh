#!/bin/zsh
# dailyplans_run.sh — 4AM: genera planes flota (PDF + email) y postea TOP-3 en X.
cd /Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader || exit 1
# gexa premarket via Claude headless (skill gexa-terminal); si Chrome no esta, sigue sin el
command -v claude >/dev/null && timeout 300 claude -p "Usa la skill gexa-terminal (Chrome extension). Para QQQ,SPY,NVDA,TSLA,MU,SMH extrae flip (0DTE y ALL-EXP), dealer pressure score, bias y POC del header de gexa.ai/terminal, y escribe el resultado como JSON a /Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader/data/gexa_snapshot.json con formato {\"SYM\":{\"flip\":n,\"flip_all\":n,\"score\":n,\"bias\":\"...\",\"poc\":\"...\"}}. Si la extension no conecta, escribe {} y termina. No hagas nada mas." >> dailyplans.log 2>&1
./venv/bin/python scripts/index_breadth.py >> dailyplans.log 2>&1
./venv/bin/python scripts/options_hunter.py 12 >> dailyplans.log 2>&1
[[ $(date +%H%M) -lt 0500 ]] && ./venv/bin/python scripts/pattern_detect.py --fleet >> dailyplans.log 2>&1
HM=$(date +%H%M)
if [[ $HM -lt 0500 ]]; then MODE=FULL; ARGS=""
elif [[ $HM -lt 0900 ]]; then MODE=REFRESH; ARGS="--tag REFRESH-8AM"
else MODE=APERTURA; ARGS="--tickers QQQ,SPY,NVDA,TSLA,MU,SMH,META,MSFT,AMD,NOK --tag APERTURA-912"
fi
echo "$(date) modo $MODE" >> dailyplans.log
./venv/bin/python scripts/daily_fleet_plans.py $ARGS >> dailyplans.log 2>&1
[[ $MODE == FULL ]] && ./venv/bin/python scripts/calibration_ledger.py record >> dailyplans.log 2>&1
# 4AM: technicals de valuacion (Forward P/E/PEG...) + score de inflacion continuo (orden Yunior 2026-07-24)
[[ $MODE == FULL ]] && FORCE_VALUATION=1 ./venv/bin/python scripts/finviz_valuation.py >> dailyplans.log 2>&1
[[ $MODE == FULL ]] && ./venv/bin/python scripts/inflation_score.py --quiet >> dailyplans.log 2>&1
# gexa verify: si el snapshot no se escribio o quedo vacio, gritar en el log
if [[ $MODE == FULL ]]; then
  if [[ ! -s data/gexa_snapshot.json ]] || grep -q '^{}$' data/gexa_snapshot.json; then
    echo "$(date) ⚠ GEXA NO CONECTO — planes usan GEX estimado propio (revisar Chrome/extension)" >> dailyplans.log
    osascript -e 'display notification "Gexa no conecto: planes con GEX estimado" with title "⚠ ib-trader 4AM"' 2>/dev/null
  fi
  ./venv/bin/python scripts/x_plan_poster.py --top 5 >> dailyplans.log 2>&1
fi
osascript -e 'display notification "📋 Planes flota generados + email + X" with title "ib-trader"'
