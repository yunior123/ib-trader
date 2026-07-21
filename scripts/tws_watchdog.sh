#!/bin/zsh
# tws_watchdog.sh — vigila que TWS este VIVO y logueado (puerto 7496) durante
# las ventanas de mercado (creado 2026-07-15 tras perder 75 min de datos:
# TWS murio 13:09 y el uplink volvio a caer 14:40 — la infraestructura fue
# el eslabon debil del dia, no las señales).
#
# Regla: L-V casi 24h (US ext 04:00-20:00 ET + KRX 20:00-02:30 ET) MAS
# domingo desde 19:45 ET (la sesion KRX del lunes abre 20:00 ET domingo —
# hueco cazado 2026-07-19 preparando la flota korea; viernes >=20:00 fuera:
# KRX no abre sabado KST). Si el puerto lleva 3 chequeos seguidos (>=3 min)
# cerrado: mata cualquier launcher colgado, relanza TWS, banner+voz LOGIN.
# No spamea: tras relanzar espera 15 min antes de volver a avisar. El login
# siempre es del humano. ZOMBIE (puerto vivo + 0 bars con daemon vivo) ahora
# SI relanza TWS (2026-07-19: el contador subia pero la rama puerto-abierto
# jamas actuaba — la deteccion de 446360c era ciega).
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
  [[ $dow -eq 6 ]] && return 1             # sabado fuera
  if [[ $dow -eq 7 ]]; then                # domingo: solo pre-open+sesion KRX
    [[ $hm -ge 1945 ]] && return 0 || return 1
  fi
  [[ $dow -eq 5 && $hm -ge 2000 ]] && return 1  # viernes noche: KRX no abre sabado
  # hueco muerto 02:30-04:00 ET (KRX cerro, US aun no abre extendido)
  [[ $hm -ge 0230 && $hm -lt 0400 ]] && return 1
  return 0
}

newest_bar_epoch() {
  # bar mas nuevo de TODA la flota (NA daemon + bridge korea) — proxy de
  # salud END-TO-END. Korea incluido 2026-07-19: en la ventana KRX
  # (20:00-02:30 ET) los unicos bars frescos posibles son los coreanos.
  local newest=0 ep
  for f in data/bars_*_ibkr.txt data/bars_skhynix.txt data/bars_samsung.txt data/bars_kospi.txt; do
    [[ -f $f ]] || continue
    ep=$(tail -1 "$f" 2>/dev/null | awk '{print $1}')
    [[ -n $ep && $ep -gt $newest ]] && newest=$ep
  done
  echo $newest
}

tws_alive() { pgrep -f "Trader Workstation.app" >/dev/null }

launch_tws() {
  # open puede fallar en silencio (cazado 2026-07-20 14:44: relanzo, a los
  # 5 min cero procesos TWS) -> verificar que el proceso EXISTA y reintentar
  open -a "$TWS_APP" 2>/dev/null
  sleep 10
  tws_alive && return 0
  open -a "$TWS_APP" 2>/dev/null
  sleep 10
  tws_alive
}

session_open_epoch() {
  # apertura de la ventana ACTUAL: 04:00 ET (dia US) o 20:00 ET (noche KRX).
  # Da la gracia anti-falso-positivo: al abrir sesion los bars de ayer son
  # viejos por definicion — zombie solo si NO llegan bars NUEVOS post-open.
  local dow=$(date +%u) hm=$(date +%H%M) today=$(date +%Y-%m-%d)
  if [[ $hm -ge 2000 || $dow -eq 7 ]]; then
    date -j -f "%Y-%m-%d %H:%M" "$today 20:00" +%s
  elif [[ $hm -lt 0230 ]]; then
    echo $(( $(date -j -f "%Y-%m-%d %H:%M" "$today 20:00" +%s) - 86400 ))
  else
    date -j -f "%Y-%m-%d %H:%M" "$today 04:00" +%s
  fi
}

is_zombie() {
  # puerto vivo pero feed muerto: daemon(s) de datos vivos + sesion abierta
  # hace >=15 min + ningun bar en los ultimos 13 min. pgrep "bar_bridge.py"
  # cubre ibkr_bar_bridge Y korea_bar_bridge.
  pgrep -f "bar_bridge.py" >/dev/null || return 1
  local now=$(date +%s) open=$(session_open_epoch) newest=$(newest_bar_epoch)
  [[ $(( now - open )) -ge 900 ]] || return 1     # gracia 15 min post-open
  [[ $newest -lt $(( now - 780 )) ]] && return 0  # 13 min sin bar alguno
  return 1
}

while true; do
  if in_window; then
    if nc -z -w2 127.0.0.1 7496 2>/dev/null; then
      awaiting_login=0
      # ZOMBIE check (cazado 2026-07-15 17:29: puerto vivo, API muerta tras
      # flap de ProtonVPN). FIX 2026-07-19: antes solo contaba fallos y esta
      # rama jamas actuaba — ahora a los 3 zombies seguidos RELANZA TWS.
      # Gracia 15 min post-open dentro de is_zombie: sin falsos positivos al
      # abrir sesion (04:00 ET dia / 20:00 ET noche KRX).
      if is_zombie; then
        fails=$((fails+1))
        if [[ $fails -ge 3 && $(( $(date +%s) - last_action )) -ge 900 ]]; then
          last_action=$(date +%s)
          pkill -f "Trader Workstation" 2>/dev/null
          sleep 5
          launch_tws
          osascript -e 'display notification "TWS ZOMBIE (puerto vivo, 0 bars 13 min) — relanzado, LOGIN + 2FA requerido" with title "🧟 TWS WATCHDOG" sound name "ProAlarm"' 2>/dev/null
          bash scripts/speak.sh DANGER "T W S is a zombie. Restarted. Login required." >/dev/null 2>&1
          mkdir -p "$MIRROR_DIR"
          echo "$(date '+%H:%M:%S') | 🧟 TWS WATCHDOG | zombie: puerto vivo, 0 bars — TWS relanzado, login requerido" >> "$MIRROR_DIR/$(date +%Y-%m-%d).txt"
          fails=0
          awaiting_login=1
        fi
      else
        fails=0
      fi
    else
      fails=$((fails+1))
      if [[ $awaiting_login -eq 1 ]]; then
        # TWS ya relanzado y esperando login humano: recordatorio suave cada
        # 15 min, JAMAS pkill (el puerto abre despues del login). PERO si el
        # proceso MURIO esperando login (cazado 2026-07-20: relanzo 14:44 y a
        # las 14:49 cero procesos -> TWS quedo muerto el resto de la sesion
        # porque esta rama jamas relanzaba) -> relanzar otra vez, cooldown 3 min.
        if ! tws_alive && [[ $(( $(date +%s) - last_action )) -ge 180 ]]; then
          last_action=$(date +%s)
          launch_tws
          osascript -e 'display notification "TWS murio esperando login — relanzado OTRA VEZ, LOGIN + 2FA requerido" with title "🚨 TWS WATCHDOG" sound name "ProAlarm"' 2>/dev/null
          bash scripts/speak.sh DANGER "T W S died again. Restarted. Login required." >/dev/null 2>&1
          mkdir -p "$MIRROR_DIR"
          echo "$(date '+%H:%M:%S') | 🚨 TWS WATCHDOG | proceso TWS murio esperando login — relanzado de nuevo" >> "$MIRROR_DIR/$(date +%Y-%m-%d).txt"
        elif tws_alive && [[ $(( $(date +%s) - last_action )) -ge 900 ]]; then
          last_action=$(date +%s)
          osascript -e 'display notification "TWS sigue esperando tu LOGIN + 2FA" with title "🔑 LOGIN TWS PENDIENTE" sound name "ProChord"' 2>/dev/null
        fi
        fails=0
      elif [[ $fails -ge 3 && $(( $(date +%s) - last_action )) -ge 900 ]]; then
        last_action=$(date +%s)
        # launcher colgado (visto 2026-07-15: 0% CPU, sin ventana) -> matar
        pkill -f "Trader Workstation" 2>/dev/null
        sleep 5
        launch_tws
        osascript -e 'display notification "TWS caido — relanzado, LOGIN + 2FA requerido" with title "🚨 TWS WATCHDOG" sound name "ProAlarm"' 2>/dev/null
        # voz via cola serializada (Siri del sistema, orden 2026-07-18) — jamas -v Daniel
        bash scripts/speak.sh DANGER "T W S is down. Login required." >/dev/null 2>&1
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
