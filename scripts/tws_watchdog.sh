#!/bin/zsh
# tws_watchdog.sh — vigila que TWS este VIVO y logueado (puerto 7496) durante
# las ventanas de mercado (creado 2026-07-15 tras perder 75 min de datos:
# TWS murio 13:09 y el uplink volvio a caer 14:40 — la infraestructura fue
# el eslabon debil del dia, no las señales).
#
# Regla: L-V casi 24h (US ext 04:00-20:00 ET + KRX 20:00-02:30 ET). Si el
# puerto lleva 3 chequeos seguidos (>=3 min) cerrado: mata cualquier launcher
# colgado, relanza TWS, banner+voz LOGIN. No spamea: tras relanzar espera
# 15 min antes de volver a avisar. El login siempre es del humano.
cd "$(dirname "$0")/.." || exit 1
TWS_APP="/Users/yuniorrodriguezosorio/Applications/Trader Workstation/Trader Workstation.app"
MIRROR_DIR="$HOME/Desktop/trading-signals"
fails=0
last_action=0

in_window() {
  local dow=$(date +%u) hm=$(date +%H%M)   # dow 1=lunes
  [[ $dow -ge 6 ]] && return 1             # sabado/domingo fuera
  # hueco muerto 02:30-04:00 ET (KRX cerro, US aun no abre extendido)
  [[ $hm -ge 0230 && $hm -lt 0400 ]] && return 1
  return 0
}

while true; do
  if in_window; then
    if nc -z -w2 127.0.0.1 7496 2>/dev/null; then
      fails=0
    else
      fails=$((fails+1))
      if [[ $fails -ge 3 && $(( $(date +%s) - last_action )) -ge 900 ]]; then
        last_action=$(date +%s)
        # launcher colgado (visto 2026-07-15: 0% CPU, sin ventana) -> matar
        pkill -f "Trader Workstation" 2>/dev/null
        sleep 5
        open -a "$TWS_APP" 2>/dev/null
        osascript -e 'display notification "TWS caido — relanzado, LOGIN + 2FA requerido" with title "🚨 TWS WATCHDOG" sound name "Sosumi"' 2>/dev/null
        say -v Daniel "T W S is down. Login required." >/dev/null 2>&1 &
        mkdir -p "$MIRROR_DIR"
        echo "$(date '+%H:%M:%S') | 🚨 TWS WATCHDOG | puerto 7496 caido ${fails} min — TWS relanzado, login requerido" >> "$MIRROR_DIR/$(date +%Y-%m-%d).txt"
        fails=0
      fi
    fi
  else
    fails=0
  fi
  sleep 60
done
