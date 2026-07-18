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
awaiting_login=0   # tras relanzar, NO volver a matar hasta ver el puerto vivo
                   # (el puerto solo abre POST-login; matar TWS mientras Yunior
                   # esta en el 2FA seria sabotaje — race cazada 17:32)

in_window() {
  local dow=$(date +%u) hm=$(date +%H%M)   # dow 1=lunes
  [[ $dow -ge 6 ]] && return 1             # sabado/domingo fuera
  # hueco muerto 02:30-04:00 ET (KRX cerro, US aun no abre extendido)
  [[ $hm -ge 0230 && $hm -lt 0400 ]] && return 1
  return 0
}

newest_bar_age() {
  # edad (s) del bar mas nuevo de toda la flota — proxy de salud END-TO-END
  local newest=0 ep
  for f in data/bars_*_ibkr.txt; do
    [[ -f $f ]] || continue
    ep=$(tail -1 "$f" 2>/dev/null | awk '{print $1}')
    [[ -n $ep && $ep -gt $newest ]] && newest=$ep
  done
  [[ $newest -eq 0 ]] && { echo 999999; return; }
  echo $(( $(date +%s) - newest - 60 ))
}

while true; do
  if in_window; then
    if nc -z -w2 127.0.0.1 7496 2>/dev/null; then
      awaiting_login=0
      # ZOMBIE check (cazado 2026-07-15 17:29: puerto vivo, API muerta tras
      # flap de ProtonVPN): puerto abierto pero CERO bars nuevos en 12 min
      # con el daemon vivo = TWS wedged -> cuenta como fallo igual.
      if pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null && \
         [[ $(newest_bar_age) -gt 720 ]]; then
        fails=$((fails+1))
      else
        fails=0
      fi
    else
      fails=$((fails+1))
      if [[ $awaiting_login -eq 1 ]]; then
        # TWS ya relanzado y esperando login humano: solo recordatorio suave
        # cada 15 min, JAMAS pkill (el puerto abre despues del login)
        if [[ $(( $(date +%s) - last_action )) -ge 900 ]]; then
          last_action=$(date +%s)
          osascript -e 'display notification "TWS sigue esperando tu LOGIN + 2FA" with title "🔑 LOGIN TWS PENDIENTE" sound name "ProChord"' 2>/dev/null
        fi
        fails=0
      elif [[ $fails -ge 3 && $(( $(date +%s) - last_action )) -ge 900 ]]; then
        last_action=$(date +%s)
        # launcher colgado (visto 2026-07-15: 0% CPU, sin ventana) -> matar
        pkill -f "Trader Workstation" 2>/dev/null
        sleep 5
        open -a "$TWS_APP" 2>/dev/null
        osascript -e 'display notification "TWS caido — relanzado, LOGIN + 2FA requerido" with title "🚨 TWS WATCHDOG" sound name "ProAlarm"' 2>/dev/null
        say -v Daniel "T W S is down. Login required." >/dev/null 2>&1 &
        mkdir -p "$MIRROR_DIR"
        echo "$(date '+%H:%M:%S') | 🚨 TWS WATCHDOG | puerto 7496 caido ${fails} min — TWS relanzado, login requerido" >> "$MIRROR_DIR/$(date +%Y-%m-%d).txt"
        fails=0
        awaiting_login=1
      fi
    fi
  else
    fails=0
  fi
  sleep 60
done
