#!/bin/zsh
# dailyplans_run.sh — 4AM: genera planes flota (PDF + email) y postea TOP-3 en X.
cd /Users/yuniorrodriguezosorio/ib-trader || exit 1
# MAPA GAMMA PROPIO (2026-07-25): aqui vivia el scrape de gexa.ai via Claude headless.
# gexa desaparecio, asi que el mapa se CALCULA en casa desde las cadenas archivadas con
# griegas MEDIDAS de Polygon (gex_snapshot.py -> data/gex_snapshot.json). Cubre 30 simbolos
# en vez de los 16 que se scrapeaban, y es auditable strike por strike.
# ORDEN: las cadenas las archiva com.ibtrader.polychains a las 16:20 y 08:45, asi que a las
# 04:00 el mapa sale del cierre de AYER (el OI correcto para la mañana) y a las 09:12 ya usa
# el de 08:45. gex_snapshot omite el simbolo sin cadena en vez de inventarle un cero.
./venv/bin/python scripts/gex_snapshot.py >> logs/dailyplans.log 2>&1
./venv/bin/python scripts/index_breadth.py >> logs/dailyplans.log 2>&1
./venv/bin/python scripts/options_hunter.py 12 >> logs/dailyplans.log 2>&1
[[ $(date +%H%M) -lt 0500 ]] && ./venv/bin/python scripts/pattern_detect.py --fleet >> logs/dailyplans.log 2>&1
HM=$(date +%H%M)
# ARGS es un ARRAY (fix 2026-07-24): zsh NO hace word-splitting de un escalar, asi
# que `$ARGS` sin comillas llegaba como UN SOLO argv ("--tag REFRESH-8AM") y las
# corridas de 08:30 y 09:12 llevaban >=3 dias muriendo con "unrecognized arguments".
if [[ $HM -lt 0500 ]]; then MODE=FULL; ARGS=()
elif [[ $HM -lt 0900 ]]; then MODE=REFRESH; ARGS=(--tag REFRESH-8AM)
else MODE=APERTURA; ARGS=(--tickers QQQ,SPY,NVDA,TSLA,MU,SMH,META,MSFT,AMD,NOK --tag APERTURA-912)
fi
echo "$(date) modo $MODE" >> logs/dailyplans.log
./venv/bin/python scripts/daily_fleet_plans.py "${ARGS[@]}" >> logs/dailyplans.log 2>&1
[[ $MODE == FULL ]] && ./venv/bin/python scripts/calibration_ledger.py record >> logs/dailyplans.log 2>&1
# 4AM: technicals de valuacion (Forward P/E/PEG...) + score de inflacion continuo (orden Yunior 2026-07-24)
[[ $MODE == FULL ]] && FORCE_VALUATION=1 ./venv/bin/python scripts/finviz_valuation.py >> logs/dailyplans.log 2>&1
[[ $MODE == FULL ]] && ./venv/bin/python scripts/inflation_score.py --quiet >> logs/dailyplans.log 2>&1
# 4AM: calibrar la brujula con el ledger de ayer (celdas Wilson -> compass_calib.json)
[[ $MODE == FULL ]] && ./venv/bin/python scripts/compass_calibrate.py >> logs/dailyplans.log 2>&1
# 4AM: zonas de liquidez (Yunior 2026-07-28) — vpvr.json + levels_auto_*.json; antes eran manuales y rancios
[[ $MODE == FULL ]] && ./bin/volume_profile >> logs/dailyplans.log 2>&1   # vive en bin/ desde la mudanza
[[ $MODE == FULL ]] && ./venv/bin/python scripts/kde_levels.py >> logs/dailyplans.log 2>&1
# 4AM: veredicto TradingAgents de los 5 capitanes (~3m18s c/u medido; lote nocturno, no en vivo)
if [[ $MODE == FULL ]]; then
  for s in QQQ SPY MU SMH NVDA; do
    ./venv/bin/python scripts/ta_view.py "$s" >> logs/dailyplans.log 2>&1
  done
fi
# verify del mapa gamma: si no se escribio, quedo rancio o perdio media flota, gritar
if [[ $MODE == FULL ]]; then
  # FRESCURA Y COBERTURA, no solo existencia (fix 2026-07-24, ampliado 2026-07-25): el
  # snapshot llevaba RANCIO desde el 2026-07-22 y el verify decia "ok" porque el JSON no
  # estaba vacio. Dos dias de planes sin regimen gamma, en silencio.
  # Umbral 36h (no 12h): el mapa sale de la cadena archivada del dia y el finde la del
  # viernes SIGUE VIGENTE — 12h convertia cada sabado en una falsa alarma.
  GEX_AGE=99999
  [[ -f data/gex_snapshot.json ]] && GEX_AGE=$(( $(date +%s) - $(stat -f %m data/gex_snapshot.json) ))
  # simbolos usables segun el propio contrato: load() filtra _meta y devuelve None si el
  # fichero falta o esta roto -> 0 significa "sin mapa", jamas se rellena con un plausible
  GEX_N=$(./venv/bin/python -c "import sys;sys.path.insert(0,'scripts');import gex_snapshot as g;d=g.load(max_age_h=36);print(len(d) if d else 0)" 2>/dev/null)
  [[ -z $GEX_N ]] && GEX_N=0
  FLEET_N=$(tr ' ' '\n' < data/fleet.txt | grep -c '[A-Z]')
  if (( GEX_N == 0 )) || (( GEX_AGE > 129600 )) || (( GEX_N * 2 < FLEET_N )); then
    echo "$(date) ⚠ MAPA GAMMA ausente/rancio/incompleto (${GEX_N}/${FLEET_N} syms, ${GEX_AGE}s) — los planes NO afirman regimen gamma" >> logs/dailyplans.log
    osascript -e 'display notification "Mapa gamma incompleto: planes sin regimen gamma" with title "⚠ ib-trader 4AM"' 2>/dev/null
  else
    echo "$(date) mapa gamma MEDIDO ok: ${GEX_N}/${FLEET_N} syms, ${GEX_AGE}s" >> logs/dailyplans.log
  fi
  ./venv/bin/python scripts/x_plan_poster.py --top 5 >> logs/dailyplans.log 2>&1
fi
osascript -e 'display notification "📋 Planes flota generados + email + X" with title "ib-trader"'
