#!/bin/zsh
# keepalive de la BRUJULA (scripts/compass.cpp -> ./compass). Senal-solamente.
#
# RETRASO = DINERO (Yunior 2026-07-25): "si la flecha apunta con retraso de 2 segundos y
# compramos call en el retroceso cuando esta en su punto maximo, no bueno". Antes la flecha
# la calculaba direction_view.py DENTRO del chart (100-180 ms por simbolo, throttle 2.0 s).
# Ahora la brujula corre aqui en C++ (1.09 ms/simbolo, 32.7 ms los 30 medidos) y el chart solo
# LEE data/compass_<sym>.json (0.051 ms medidos). El retraso lo fija COMPASS_LOOP, no el chart.
#
# GRITA si el hijo muere rapido 3 veces seguidas (leccion del 2026-07-25: los keepalives de
# opt_whale_watch/opt_chain_cache relanzaron en silencio durante horas tras la mudanza del
# repo, y el panel decia "armado" mientras no habia ni una alarma de ballena).
cd "$(dirname "$0")/.."

LOOP="${COMPASS_LOOP:-0.25}"      # segundos entre ciclos (sub-segundo permitido)
LOG=compass.log
FAILS=0

if [[ ! -x bin/compass ]]; then
  ./scripts/build_compass.sh >> "$LOG" 2>&1 || {
    echo "$(date) compass NO COMPILA — brujula caida" >> "$LOG"
    ./scripts/speak.sh DANGER "La brujula no compila. La flecha esta caida." 2>/dev/null
    exit 1
  }
fi

while true; do
  pkill -f "bin/compass --loop" 2>/dev/null
  sleep 1
  START=$(date +%s)
  FLEET=$(cat data/fleet.txt)
  bin/compass --loop "$LOOP" ${=FLEET} >> "$LOG" 2>&1
  END=$(date +%s)
  RAN=$((END - START))
  echo "$(date) compass salio tras ${RAN}s; relanzando" >> "$LOG"
  if (( RAN < 10 )); then
    FAILS=$((FAILS + 1))
    if (( FAILS >= 3 )); then
      echo "$(date) BRUJULA EN CRASH-LOOP (3 muertes en <10s) — no se degrada en silencio" >> "$LOG"
      ./scripts/speak.sh DANGER "Brujula en crash loop. La flecha no es de fiar." 2>/dev/null
      FAILS=0
    fi
  else
    FAILS=0
  fi
  sleep 5
done
