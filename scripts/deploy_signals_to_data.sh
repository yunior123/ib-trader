#!/bin/zsh
# deploy_signals_to_data.sh — AL CIERRE: recompila los binarios C++ (ahora escriben a
# data/trading-signals via fleet_notify.h) + reinicia la flota para activar el codigo
# nuevo (Python ya editado). Elimina la dependencia TCC/Desktop de raiz. 2026-07-24.
# Uso: zsh scripts/deploy_signals_to_data.sh   (SOLO con mercado cerrado)
cd "$(dirname "$0")/.." || exit 1
# Doctrina cpp-latest: SIEMPRE el C++ mas nuevo + arquitectura nativa. Antes iba
# con c++20 -O2 SIN -mcpu=native, que es lo mas flojo del repo justo en el codigo
# que mas corre (order_engine y scalper ya usaban -O3 nativo).
STD="-std=c++2c"
ARCH="-mcpu=native"; [ "$(uname -m)" = "x86_64" ] && ARCH="-march=native"
FAILED=0
echo "=== recompilando C++ ($STD -O3 $ARCH) — secuencial 8GB ==="
BOTS=$(ls *_signal_bot.cpp scripts/*_signal_bot.cpp 2>/dev/null)
for src in scripts/flow_pulse.cpp scripts/qqq_xray.cpp scripts/price_alarm.cpp scripts/korea_watch.cpp scripts/finviz_scout.cpp $BOTS; do
  [ -f "$src" ] || continue
  out=$(basename "$src" .cpp)
  while [ -f /tmp/cc.lock ]; do sleep 1; done; touch /tmp/cc.lock
  clang++ $STD -O3 $ARCH -o "$out" "$src" 2>/tmp/cc_err && echo "  ✅ $out" || { echo "  🔴 $out:"; head -5 /tmp/cc_err; FAILED=$((FAILED+1)); }
  rm -f /tmp/cc.lock
done
# NO reiniciar con binarios a medias: antes seguia adelante y dejaba la flota con
# una mezcla de binarios viejos y nuevos, que es peor que no desplegar.
if [ "$FAILED" -gt 0 ]; then
  echo "🔴 $FAILED compilacion(es) FALLARON — NO reinicio la flota (quedaria mezclada)."
  echo "   Arregla y repite. La flota sigue corriendo los binarios anteriores."
  exit 1
fi
echo "=== reiniciando la flota (keepalive relanza con binarios+codigo nuevos) ==="
pkill -f '_signal_bot$'; pkill -f 'opt_chain_cache|opt_whale_watch|flow_pulse|bollinger_alarm|band_open|signals_db|notify_relay'
sleep 3
nohup zsh scripts/fleet_keepalive_start.sh >/dev/null 2>&1 &
nohup python3 scripts/signals_db.py --daemon > signals_db.log 2>&1 &
echo "=== verificacion ==="; sleep 20
echo "  señales en data/ tras reinicio: escribir prueba"; echo "$(date +%T) | TEST | deploy /data ok" >> "data/trading-signals/$(date +%F).txt" && tail -1 "data/trading-signals/$(date +%F).txt"
