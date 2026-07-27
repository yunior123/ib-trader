#!/bin/zsh
# bundle_backend.sh — mete el BACKEND COMPLETO dentro del .app para que sea
# un bundle único y portable: arrastrar y usar, sin instalar nada.
#
# POR QUE UN PYTHON EMPOTRADO Y NO EL DEL SISTEMA:
#   El backend necesita 3.12 (numpy 2.5 exige >=3.11) y macOS trae 3.9.6.
#   Se empotra cpython-3.12.13 de python-build-standalone (astral), que es
#   RELOCATABLE — no lleva rutas absolutas dentro, justo lo que rompió los venv
#   cuando movimos el repo el 2026-07-25.
#
# POR QUE NO PyInstaller: congela rutas y hay que rehacerlo a cada cambio de dep.
# Esto es un Python real: se puede depurar y actualizar in situ.
#
#   zsh macapp/bundle_backend.sh        (se llama solo desde build.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
APP="$REPO/macapp/ib-trader Cockpit.app"
RES="$APP/Contents/Resources"
PYVER="3.12.13"
PYTAG="20260718"
CACHE="$HOME/.cache/ib-trader-python"
TARBALL="$CACHE/cpython-${PYVER}-arm64.tar.gz"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTAG}/cpython-${PYVER}%2B${PYTAG}-aarch64-apple-darwin-install_only_stripped.tar.gz"

[ -d "$APP" ] || { echo "🔴 falta el .app — corre antes: zsh macapp/build.sh"; exit 1; }

# --- 1. Python relocatable (cacheado: solo se baja la primera vez) ---
mkdir -p "$CACHE"
if [ ! -f "$TARBALL" ]; then
  echo "  bajando Python ${PYVER} relocatable (24 MB, una sola vez)…"
  curl -fsSL "$URL" -o "$TARBALL.tmp" && mv "$TARBALL.tmp" "$TARBALL"
fi
rm -rf "$RES/python"
mkdir -p "$RES/python"
tar -xzf "$TARBALL" -C "$RES/python" --strip-components=1
PY="$RES/python/bin/python3.12"
[ -x "$PY" ] || { echo "🔴 el Python empotrado no arrancó"; exit 1; }

# --- 2. dependencias dentro del bundle ---
# --no-compile: los .pyc se generan al vuelo y ahorran ~15 MB de bundle.
echo "  instalando dependencias del cockpit…"
"$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$PY" -m pip install --quiet --no-compile -r macapp/requirements-backend.txt

# pip escribe los console-scripts (uvicorn, fastapi, f2py…) con el shebang APUNTANDO
# A ESTE MAC: "…/Users/<yo>/ib-trader/macapp/…/python3.12". En otro Mac no arrancan.
# Se reescriben al mismo truco relativo que ya usa el propio `pip` del tarball.
for f in "$RES/python/bin/"*; do
  [ -f "$f" ] || continue
  grep -q "^'''exec' \"/" "$f" 2>/dev/null || continue
  perl -0pi -e "s{^'''exec' \"/[^\"]*/python3\.12\"}{'''exec' \"\\\$(dirname -- \"\\\$(realpath -- \"\\\$0\")\")/python3.12\"}m" "$f"
done

# Los .pyc que deja el propio pip al importar la stdlib llevan el co_filename
# absoluto de ESTE Mac. No rompen (solo salen en tracebacks) pero ensucian la
# puerta de portabilidad y pesan ~15 MB. Se borran: se regeneran al vuelo.
find "$RES/python" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

# --- 3. codigo del backend (cierre de dependencias, no el repo entero) ---
rm -rf "$RES/backend"
mkdir -p "$RES/backend/scripts" "$RES/backend/charts" "$RES/backend/data"
# la lista vive en macapp/bundled_paths.txt — la MISMA que usa el hook para decidir
# si hay que reconstruir. Dos listas separadas fue lo que dejo la .app rancia.
sed 's/#.*//' macapp/bundled_paths.txt | tr -d ' ' | grep -v '^$' | while IFS= read -r p; do
  case "$p" in
    scripts/*.py) [ -f "$p" ] && cp "$p" "$RES/backend/scripts/";;
    charts/*)     [ -f "$p" ] && cp "$p" "$RES/backend/charts/";;
    data/*)       [ -f "$p" ] && cp "$p" "$RES/backend/data/";;
  esac
done
for need in chart_bridge.py live.html; do
  find "$RES/backend" -name "$need" | grep -q . || { echo "🔴 falta $need en el bundle"; exit 1; }
done

# --- 4. arranque: usa la config del usuario (Application Support), no la del repo ---
cat > "$RES/backend/run.sh" <<'RUNSH'
#!/bin/zsh
# Lanza el cockpit con el Python empotrado. El .app llama a esto.
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(dirname "$HERE")"
SUPPORT="$HOME/Library/Application Support/ib-trader"
mkdir -p "$SUPPORT/data" "$SUPPORT/charts/data" "$SUPPORT/order_engine"
# el backend escribe en Application Support (SIEMPRE escribible, sin TCC),
# nunca dentro del .app (que puede estar en /Applications, de solo lectura)
cp -n "$HERE/data/"* "$SUPPORT/data/" 2>/dev/null || true
cd "$SUPPORT"
ln -sfn "$HERE/charts" "$SUPPORT/charts_bundled" 2>/dev/null || true
export IBTRADER_CHARTS="$HERE/charts"
export PYTHONPATH="$HERE/scripts"

# --- POR QUE SE LANZA POR UN SYMLINK Y NO DIRECTO DESDE EL BUNDLE ------------
# Todos los modulos del backend deducen su raiz asi:
#   REPO = dirname(dirname(abspath(__file__)))     (chart_bridge.py:48 y 7 mas)
# Lanzandolo como "$HERE/scripts/chart_bridge.py", REPO caia DENTRO del .app
# (…/Resources/backend) — o sea el backend escribia exec_zones_*.json,
# commands.jsonl y data/ dentro del bundle: rompe la firma ad-hoc y falla en seco
# si la .app vive en /Applications (solo lectura). Justo lo contrario de lo que
# prometia el commit 824ffc5. Bug detectado y arreglado el 2026-07-25.
# os.path.abspath NO resuelve symlinks (realpath si), asi que lanzandolo por
# "$SUPPORT/scripts/…" el REPO deducido es $SUPPORT — escribible — mientras el
# CODIGO sigue siendo el del bundle. Cero cambios en el Python.
ln -sfn "$HERE/scripts" "$SUPPORT/scripts"

# --- BRUJULA: la flecha la calcula C++, no el Python -------------------------
# chart_bridge.py solo LEE data/compass_<sym>.json (0.051 ms) — el calculo es
# ./compass (1.09 ms/simbolo). Si nadie la corre, la flecha sale gris/rancia.
# compass lee y escribe RELATIVO al cwd, y el cwd aqui ya es $SUPPORT.
#
# SE LANZA POR RUTA ABSOLUTA A PROPOSITO: scripts/compass_keepalive.sh del repo
# hace `pkill -f "\./compass --loop"`. Si aqui se lanzara como "./compass --loop"
# los dos se matarian mutuamente (bundle vs repo). Con la ruta absoluta el patron
# "\./compass" NO casa, asi que conviven.
#
# HONESTIDAD: la brujula necesita data/bars_<sym>_ibkr.txt, que los produce
# ibkr_bar_bridge.py — ese puente NO va en el bundle (necesita el Gateway y la
# flota). Con la flota del repo arriba la flecha es fresca; con la .app sola, el
# cockpit la marcara RANCIA en gris, que es el fallo ruidoso que queremos.
COMPASS="$RES/engine/compass"
if [ -x "$COMPASS" ]; then
  FLEET=$(cat "$SUPPORT/data/fleet.txt" 2>/dev/null || echo "QQQ SPY")
  "$COMPASS" --loop "${COMPASS_LOOP:-0.25}" ${=FLEET} >> "$SUPPORT/compass.log" 2>&1 &
  COMPASS_PID=$!
  # que no quede huerfana cuando el cockpit se cierre
  trap 'kill $COMPASS_PID 2>/dev/null' EXIT INT TERM
else
  echo "AVISO: sin ./compass en el bundle — el cockpit ira sin flecha" >&2
fi

# sin exec: hay que conservar el trap que mata la brujula al salir
"$RES/python/bin/python3.12" "$SUPPORT/scripts/chart_bridge.py" "$@"
RUNSH
chmod +x "$RES/backend/run.sh"

# --- 5. motor de ordenes (C++), ya generico: la cuenta sale de la config ---
# Enlazado estatico (libTwsSocketClient + libbid), asi que va solo. La proteccion
# vive intacta: doble llave + verificacion de cuenta que FALLA CERRADO.
mkdir -p "$RES/engine"
[ -f order_engine/order_engine ] && cp order_engine/order_engine "$RES/engine/"
# la BRUJULA (C++): sin ella el cockpit empaquetado no tiene flecha
[ -x compass ] && cp compass "$RES/engine/" && echo "  brujula empotrada: $(du -h compass | cut -f1)"
# disarm.sh SI va (borra ARM_LIVE + SIGTERM al motor: funciona desde cualquier sitio,
# es la palanca de emergencia y siempre debe estar a mano).
# arm.sh NO va: deduce el repo de su propia ruta, asi que desde dentro del .app
# escribia en <Resources>/order_engine/ARM_LIVE — carpeta inexistente -> fallaba con
# un error de shell crudo (verificado 2026-07-25: exit 1, sin crear nada). Fallaba
# CERRADO, que es lo correcto, pero era un artefacto roto y engañoso. Armar live se
# hace desde el repo, a conciencia, no desde una .app que se arrastra por ahi.
for f in disarm.sh; do [ -f "order_engine/$f" ] && cp "order_engine/$f" "$RES/engine/"; done
cat > "$RES/engine/LEEME.txt" <<'ENG'
order_engine — coloca ordenes REALES en TWS/IB Gateway.

DOBLE LLAVE, a proposito:
  1) crear el fichero ARM_LIVE con la fecha de hoy   (repo: order_engine/arm.sh)
  2) lanzarlo con --arm-live
Sin AMBAS solo registra lo que colocaria ("DRY colocaria ..."). Borrar ARM_LIVE
lo desarma en el acto: la llave se re-evalua antes de CADA envio.

ARMAR SOLO DESDE EL REPO: arm.sh a proposito NO viene en el .app. Aqui va
disarm.sh, que es la palanca de EMERGENCIA (borra la llave y manda SIGTERM ->
el motor cancela sus ordenes OE: y sale).

CUENTA: sale de tu configuracion (menu de la app -> Configuracion), NO del codigo.
Si no hay cuenta configurada el motor NO opera. Si el broker reporta otra cuenta
distinta a la que declaraste, ABORTA. Es lo que evita ordenar con dinero real
creyendo que es paper.

Empieza SIEMPRE en paper.
ENG

echo "  backend empotrado: $(du -sh "$RES" | cut -f1)"
