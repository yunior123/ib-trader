#!/bin/zsh
# uninstall.sh — limpia TODO lo que la app escribe fuera del bundle.
# Uso: zsh macapp/uninstall.sh
#
# Borra:
#   - ~/Library/Application Support/ib-trader/
#   - ~/Library/Saved Application State/com.ibtrader.cockpit.savedState/
#   - defaults com.ibtrader.cockpit
#
# NO borra la .app en sí (está en macapp/ o donde la copies).

set -euo pipefail

echo "Desinstalación de ib-trader Cockpit — limpia datos del usuario"
echo ""
echo "Se va a BORRAR:"
echo "  - ~/Library/Application Support/ib-trader/"
echo "  - ~/Library/Saved Application State/com.ibtrader.cockpit.savedState/"
echo "  - Preferencias (defaults delete com.ibtrader.cockpit)"
echo ""
read -q "CONFIRM?¿Continuar? (s/n): " || { echo; echo "Cancelado."; exit 0; }
echo ""
echo ""

DIRS=(
  "$HOME/Library/Application Support/ib-trader"
  "$HOME/Library/Saved Application State/com.ibtrader.cockpit.savedState"
)

for d in "${DIRS[@]}"; do
  if [ -e "$d" ]; then
    echo "Borrando: $d"
    rm -rf "$d" && echo "  ✓ borrado"
  fi
done

if defaults read com.ibtrader.cockpit >/dev/null 2>&1; then
  echo "Borrando preferencias (defaults com.ibtrader.cockpit)"
  defaults delete com.ibtrader.cockpit && echo "  ✓ borrado"
fi

echo ""
echo "✓ Desinstalación limpia completada."
echo ""
echo "Nota: la .app en sí (macapp/ib-trader Cockpit.app o donde la tengas)"
echo "se borra manualmente si ya no la necesitas."
