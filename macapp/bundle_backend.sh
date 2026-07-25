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

# --- 3. codigo del backend (cierre de dependencias, no el repo entero) ---
rm -rf "$RES/backend"
mkdir -p "$RES/backend/scripts" "$RES/backend/charts" "$RES/backend/data"
for m in chart_bridge chart_levels confluence_engine direction_view ib_mode \
         narrator order_ticket gex_core optgate; do
  [ -f "scripts/$m.py" ] && cp "scripts/$m.py" "$RES/backend/scripts/"
done
cp charts/live.html charts/*.js "$RES/backend/charts/" 2>/dev/null || true
cp data/fleet.txt "$RES/backend/data/" 2>/dev/null || true

# --- 4. arranque: usa la config del usuario (Application Support), no la del repo ---
cat > "$RES/backend/run.sh" <<'RUNSH'
#!/bin/zsh
# Lanza el cockpit con el Python empotrado. El .app llama a esto.
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(dirname "$HERE")"
SUPPORT="$HOME/Library/Application Support/ib-trader"
mkdir -p "$SUPPORT/data" "$SUPPORT/charts"
# el backend escribe en Application Support (SIEMPRE escribible, sin TCC),
# nunca dentro del .app (que puede estar en /Applications, de solo lectura)
cp -n "$HERE/data/"* "$SUPPORT/data/" 2>/dev/null || true
cd "$SUPPORT"
ln -sfn "$HERE/charts" "$SUPPORT/charts_bundled" 2>/dev/null || true
export IBTRADER_CHARTS="$HERE/charts"
export PYTHONPATH="$HERE/scripts"
exec "$RES/python/bin/python3.12" "$HERE/scripts/chart_bridge.py" "$@"
RUNSH
chmod +x "$RES/backend/run.sh"

echo "  backend empotrado: $(du -sh "$RES" | cut -f1)"
