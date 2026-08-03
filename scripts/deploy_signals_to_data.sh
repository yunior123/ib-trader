#!/bin/zsh
# deploy_signals_to_data.sh — AL CIERRE: recompila los binarios C++ (ahora escriben a
# data/trading-signals via fleet_notify.h) + reinicia la flota para activar el codigo
# nuevo (Python ya editado). Elimina la dependencia TCC/Desktop de raiz. 2026-07-24.
# Uso: zsh scripts/deploy_signals_to_data.sh   (SOLO con mercado cerrado)
cd "$(dirname "$0")/.." || exit 1
FORCE=0
for a in "$@"; do [ "$a" = "--force" ] && FORCE=1; done
# Portero horario (orden Yunior 2026-07-26): pkill sin guarda mataba la flota EN
# SESION VIVA. ./fleet_hours exit 0 = LIVE -> abortar salvo --force.
if [ -x bin/fleet_hours ]; then
  if bin/fleet_hours >/dev/null 2>&1 && [ "$FORCE" -ne 1 ]; then
    echo "🔴 ventana LIVE ($(bin/fleet_hours --why)) — deploy ABORTADO, no se mata la flota."
    echo "   Forzar con: zsh scripts/deploy_signals_to_data.sh --force"
    exit 1
  fi
else
  echo "🔴 ./fleet_hours no existe/ejecutable — no se puede verificar la ventana. Compila con scripts/build_fleet_hours.sh"
  exit 1
fi
# Doctrina cpp-latest: SIEMPRE el C++ mas nuevo + arquitectura nativa. Antes iba
# con c++20 -O2 SIN -mcpu=native, que es lo mas flojo del repo justo en el codigo
# que mas corre (order_engine y scalper ya usaban -O3 nativo).
STD="-std=c++2c"
ARCH="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCH="-march=native"
# -Wall -Wextra: la ley de la casa pide CERO warnings. Se avisan pero NO se
# convierten en error (-Werror) porque un aviso nuevo de una version de clang no
# puede dejar a la flota sin binarios; el conteo se canta al final del deploy.
WARN="-Wall -Wextra"
FAILED=0
WARNED=0
echo "=== recompilando C++ ($STD -O3 $ARCH $WARN) — secuencial 8GB ==="
# ARRAY, no escalar (fix 2026-07-25): zsh NO hace word-splitting, asi que
# `for src in $BOTS` recibia los 24 nombres como UNA sola cadena, [ -f ] fallaba
# y los saltaba TODOS en silencio. Por eso los binarios seguian siendo del 20-jul
# pese a haber "desplegado". Mismo bug que dailyplans_run.sh (word-splitting).
BOTS=( *_signal_bot.cpp(N) scripts/*_signal_bot.cpp(N) )
for src in scripts/flow_pulse.cpp scripts/qqq_xray.cpp scripts/price_alarm.cpp scripts/korea_watch.cpp scripts/finviz_scout.cpp "${BOTS[@]}"; do
  [ -f "$src" ] || continue
  out=$(basename "$src" .cpp)
  # ESPERA CON CADUCIDAD (2026-08-03). Esto era `while [ -f /tmp/cc.lock ]; do sleep 1; done`
  # sin trap: si el script moria entre el touch (aqui) y el `rm -f` de abajo — Ctrl-C, limite
  # de sesion, timeout — el fichero sobrevivia en /tmp hasta reiniciar el Mac y CUALQUIER
  # despliegue posterior se colgaba aqui para siempre, mudo. Es el mismo patron que dejo
  # `macapp/.rebuild-waiting` rancio desde el 2026-07-29 12:58 y con el la .app sin
  # reconstruir durante dias: un automatismo desactivado en silencio por un marcador huerfano.
  for _ in $(seq 1 600); do
    [ -f /tmp/cc.lock ] || break
    EDAD=$(( $(date +%s) - $(stat -f %m /tmp/cc.lock 2>/dev/null || echo 0) ))
    if [ "$EDAD" -gt 900 ]; then
      echo "  ⚠️  /tmp/cc.lock rancio (${EDAD}s, un clang++ anterior murio a medias) -> lo tomo"
      rm -f /tmp/cc.lock; break
    fi
    sleep 1
  done
  touch /tmp/cc.lock
  trap 'rm -f /tmp/cc.lock' EXIT INT TERM   # muera como muera, el candado no queda armado
  # -lcurl solo donde hace falta (finviz_scout/x_whale_bot hablan HTTP). Sin esto
  # el enlace falla y —desde el fix de abort-on-fail— aborta TODO el despliegue.
  LIBS=""; case "$out" in finviz_scout|x_whale_bot) LIBS="-lcurl";; esac
  if clang++ $STD -O3 $ARCH $WARN -o "$out" "$src" $LIBS 2>/tmp/cc_err; then
    nw=$(grep -c "warning:" /tmp/cc_err)
    if [ "$nw" -gt 0 ]; then echo "  ⚠️  $out ($nw warnings)"; head -3 /tmp/cc_err; WARNED=$((WARNED+1));
    else echo "  ✅ $out"; fi
  else
    echo "  🔴 $out:"; head -5 /tmp/cc_err; FAILED=$((FAILED+1))
  fi
  rm -f /tmp/cc.lock
done
# NO reiniciar con binarios a medias: antes seguia adelante y dejaba la flota con
# una mezcla de binarios viejos y nuevos, que es peor que no desplegar.
if [ "$FAILED" -gt 0 ]; then
  echo "🔴 $FAILED compilacion(es) FALLARON — NO reinicio la flota (quedaria mezclada)."
  echo "   Arregla y repite. La flota sigue corriendo los binarios anteriores."
  exit 1
fi
[ "$WARNED" -gt 0 ] && echo "⚠️  $WARNED binario(s) con warnings — la ley de la casa pide CERO. Revisar."
echo "=== reiniciando la flota (keepalive relanza con binarios+codigo nuevos) ==="
pkill -f '_signal_bot$'; pkill -f 'opt_chain_cache|opt_whale_watch|flow_pulse|bollinger_alarm|band_open|signals_db|notify_relay'
sleep 3
nohup zsh scripts/fleet_keepalive_start.sh >/dev/null 2>&1 &
nohup python3 scripts/signals_db.py --daemon > logs/signals_db.log 2>&1 &
echo "=== verificacion ==="; sleep 20
echo "  señales en data/ tras reinicio: escribir prueba"; echo "$(date +%T) | TEST | deploy /data ok" >> "data/trading-signals/$(date +%F).txt" && tail -1 "data/trading-signals/$(date +%F).txt"
