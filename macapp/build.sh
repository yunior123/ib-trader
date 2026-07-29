#!/bin/zsh
# build.sh — compila el cockpit como .app nativa. NO requiere Xcode completo,
# basta con Command Line Tools (verificado 2026-07-25: swiftc 6.3.3, sin xcodebuild).
#
#   zsh macapp/build.sh            -> macapp/ib-trader Cockpit.app
#   open "macapp/ib-trader Cockpit.app"
set -euo pipefail
cd "$(dirname "$0")/.."
APP="macapp/ib-trader Cockpit.app"

# --- MUTEX: un solo build a la vez -------------------------------------------
# Sin esto, dos builds solapados (post-commit de dos agentes, o post-commit +
# pre-push) se pisan: el segundo hace `rm -rf "$APP"` sobre lo que el primero esta
# escribiendo y en Desktop queda un bundle a medias o firmado roto.
# mkdir es atomico (macOS no trae flock) — mismo patron que fleet_keepalive_start.sh.
LOCKDIR="macapp/.build.lockd"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCKDIR" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt 1800 ]; then
    echo "🔒 otro build activo (lock ${AGE}s) — salgo sin tocar el bundle"
    exit 0
  fi
  echo "🔒 lock viejo (${AGE}s) — build anterior murio a medias, lo tomo"
  rmdir "$LOCKDIR" 2>/dev/null || true
  mkdir "$LOCKDIR"
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT INT TERM

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# arm64 nativo; -O porque no cuesta nada y el binario es diminuto igual
swiftc -O -target arm64-apple-macos13 macapp/main.swift macapp/Settings.swift -o "$APP/Contents/MacOS/cockpit"

# --- BRUJULA (C++): la flecha del cockpit ------------------------------------
# chart_bridge.py ya NO computa la direccion, solo LEE data/compass_<sym>.json. Si
# la .app no lleva bin/compass, el cockpit empaquetado sale sin flecha (o gris/rancia).
# SECUENCIAL a proposito (Mac 8GB): un solo clang++ a la vez, nunca en paralelo.
if [ ! -x bin/compass ] || [ scripts/compass.cpp -nt bin/compass ]; then
  # esperar a que no haya OTRO clang++ vivo: en el Mac de 8 GB dos a la vez = swap
  for _ in $(seq 1 120); do
    [ "$(ps aux | grep -c '[c]lang++')" -eq 0 ] && break
    sleep 5
  done
  echo "  compilando la BRUJULA (secuencial, un solo clang++)…"
  clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bin/compass scripts/compass.cpp
  cp bin/compass compass
fi

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>ib-trader Cockpit</string>
  <key>CFBundleDisplayName</key><string>ib-trader Cockpit</string>
  <key>CFBundleIdentifier</key><string>com.ibtrader.cockpit</string>
  <key>CFBundleExecutable</key><string>cockpit</string>
  <!-- SIN extension: Finder busca Resources/AppIcon.icns -->
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <!-- el cockpit es http://127.0.0.1 -> hay que permitir texto plano LOCAL -->
  <key>NSAppTransportSecurity</key><dict>
    <key>NSAllowsLocalNetworking</key><true/>
  </dict>
</dict></plist>
PLIST

# --- SELLO DE BUILD — que commit lleva dentro, VISIBLE ----------------------
# Sin esto no habia forma de saber si la .app del escritorio era la del ultimo
# commit: se miraba el mtime, que miente (un rebuild sin cambios lo refresca).
# Va ANTES de codesign; despues romperia el sello.
PL="$APP/Contents/Info.plist"
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "sin-git")
GIT_DATE=$(git log -1 --format=%cd --date=format:'%Y-%m-%d %H:%M' 2>/dev/null || echo "?")
DIRTY=""
git diff --quiet -- $(sed 's/#.*//' macapp/bundled_paths.txt | tr -d ' ' | grep -v '^$' | tr '\n' ' ') 2>/dev/null || DIRTY="+sucio"
/usr/libexec/PlistBuddy -c "Add :IBTCommit string $GIT_SHA$DIRTY" "$PL" >/dev/null
/usr/libexec/PlistBuddy -c "Add :IBTCommitDate string $GIT_DATE" "$PL" >/dev/null
/usr/libexec/PlistBuddy -c "Add :IBTBuildDate string $(date '+%Y-%m-%d %H:%M:%S')" "$PL" >/dev/null
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $GIT_SHA$DIRTY" "$PL" >/dev/null
echo "  sello: commit $GIT_SHA$DIRTY ($GIT_DATE)"

# --- ICONO (brujula) — SIEMPRE ANTES DE FIRMAR ------------------------------
# Lo GENERA el pipeline: si falta el .icns o el arte fuente es mas nuevo, se
# re-dibuja aqui. Solo si no hay Python con PIL se cae al .icns versionado.
# Ojo al ORDEN, misma trampa que el backend: si el icono entra DESPUES de
# codesign, el sello queda roto ("a sealed resource is missing or invalid").
if [ ! -f macapp/icon/AppIcon.icns ] || [ macapp/icon/make_icon.py -nt macapp/icon/AppIcon.icns ]; then
  for PY in ./venv/bin/python ./venv-chart/bin/python python3; do
    command -v "$PY" >/dev/null 2>&1 || [ -x "$PY" ] || continue
    "$PY" -c 'import PIL' 2>/dev/null || continue
    echo "  regenerando el icono con $PY…"
    "$PY" macapp/icon/make_icon.py >/dev/null && break
  done
fi
[ -f macapp/icon/AppIcon.icns ] || { echo "🔴 sin macapp/icon/AppIcon.icns y sin PIL para generarlo"; exit 1; }
cp macapp/icon/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
# Un .icns al que le falte un tamaño da el placeholder de Finder: se exigen los 10.
ICN_N=$(python3 - "$APP/Contents/Resources/AppIcon.icns" <<'PY'
import struct,sys
d=open(sys.argv[1],'rb').read(); o=8; t=[]
while o<len(d):
    k=d[o:o+4].decode('latin1'); l=struct.unpack('>I',d[o+4:o+8])[0]; t.append(k); o+=l
need={'ic04','ic05','ic07','ic08','ic09','ic10','ic11','ic12','ic13','ic14'}
print(len(need & set(t)))
PY
)
[ "$ICN_N" = "10" ] || { echo "🔴 AppIcon.icns incompleto ($ICN_N/10 tamaños) — Finder pintaria el placeholder"; exit 1; }
echo "  icono: AppIcon.icns empotrado (10/10 tamaños)"

# --- BACKEND EMPOTRADO (bundle unico y portable) ---
# SKIP_BACKEND=1 para iterar rapido en la UI sin re-empaquetar los ~200 MB.
if [ "${SKIP_BACKEND:-0}" != "1" ]; then
  zsh macapp/bundle_backend.sh
else
  echo "  (SKIP_BACKEND=1 — bundle SIN backend, solo para iterar la UI)"
fi

# --- FIRMA AD-HOC — SIEMPRE AL FINAL -----------------------------------------
# Ojo al ORDEN: firmar ANTES de empotrar el backend deja el sello ROTO ("a sealed
# resource is missing or invalid"), porque los ~150 MB de python/ + backend/ +
# engine/ entran DESPUES de sellar. Bug real detectado el 2026-07-25 en la .app
# entregada: `codesign --verify` listaba 5000 "file added". En local arranca igual,
# pero al pasarla a otro Mac Gatekeeper la mata. Por eso: empotrar -> firmar.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "  (aviso: firma ad-hoc fallo, la app sigue funcionando en local)"
if codesign --verify "$APP" >/dev/null 2>&1; then
  echo "  firma ad-hoc: sello VALIDO"
else
  echo "  🔴 AVISO: el sello de la firma NO valida — revisar antes de pasarla a otro Mac"
fi

# --- PORTABILIDAD: cero rutas absolutas de esta maquina ----------------------
# El fallo clasico: los wrappers que pip escribe en Resources/python/bin llevan el
# shebang con la ruta del .app en ESTE Mac -> en otro Mac no arrancan.
if BAD=$(grep -rl "$HOME" "$APP" 2>/dev/null); then
  echo "🔴 PORTABILIDAD ROTA — estos ficheros del bundle llevan la ruta de este Mac:"
  echo "$BAD" | sed 's/^/     /'
  exit 1
fi
echo "  portabilidad: 0 rutas absolutas de este Mac dentro del bundle"

# --- ENTREGA A DESKTOP (pipeline automatico) -------------------------------
# Desktop esta bajo TCC: desde una shell interactiva se escribe bien, pero si esto
# llegara a correr bajo launchd fallaria igual que el repo antes de la mudanza.
# CI=1 (GitHub Actions) no tiene Desktop de nadie: se salta la entrega.
# Yunior 2026-07-26: el escritorio va LIMPIO, una sola carpeta ~/Desktop/ib-trader.
DESK="$HOME/Desktop/ib-trader"
DESK_APP="$DESK/ib-trader Cockpit.app"
if [ "${CI:-}" = "true" ] || [ "${CI:-0}" = "1" ]; then
  echo "  (CI — sin entrega a Desktop)"
elif mkdir -p "$DESK" 2>/dev/null && [ -w "$DESK" ]; then
  # una copia suelta en la raiz = 2 registros del mismo bundle id = el fantasma vuelve
  rm -rf "$HOME/Desktop/ib-trader Cockpit.app"
  # ditto (no cp -R): preserva xattrs, ACLs y el sello. Y se entrega por STAGING +
  # swap: entre el rm y el cp habia una ventana en la que el Desktop se quedaba sin
  # app — si el cp fallaba (disco, Ctrl-C) desaparecia y no volvia. Eso es lo que
  # Yunior veia como "sometimes disappear the one in desktop".
  STAGE="$DESK/.ib-trader Cockpit.app.new"
  rm -rf "$STAGE"
  ditto "$APP" "$STAGE"
  xattr -dr com.apple.quarantine "$STAGE" 2>/dev/null || true
  rm -rf "$DESK_APP"
  mv "$STAGE" "$DESK_APP"
  echo "  -> entregada en Desktop: $DESK_APP"
else
  echo "  AVISO: no puedo escribir en $DESK (TCC?) — la .app queda solo en macapp/"
fi

# --- LAUNCHSERVICES: la causa REAL del icono roto ----------------------------
# MEDIDO 2026-07-26: habia 4 registros del MISMO CFBundleIdentifier
# com.ibtrader.cockpit. El que resolvia LaunchServices era un FANTASMA en
# /private/tmp/apptest/ib-trader Cockpit.app, borrado hace dias
# ("Bundle node not found on disk: fnfErr") y con iconDict VACIO. Resultado en el
# escritorio: el badge prohibitorio (circulo blanco con barra) encima del icono.
# Sobrevive a los rebuilds porque vive en la base de datos de LS, no en el bundle.
# Por eso cada build purga los registros cuyo path ya no existe y re-registra los
# vivos. Sin esto, el icono se vuelve a romper al siguiente experimento.
LSR=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
if [ -x "$LSR" ]; then
  BID=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$APP/Contents/Info.plist")
  "$LSR" -dump 2>/dev/null \
    | awk -v bid="$BID" '$1=="path:"       {p=""; for(i=2;i<=NF;i++){if($i ~ /^\(0x/)break; p=(p==""?$i:p" "$i)}}
                         $1=="identifier:" && $2==bid && p!="" {print p; p=""}' \
    | while IFS= read -r ghost; do
        # fantasma = path muerto; la Papelera existe en disco pero compite por el mismo bundle id
        case "$ghost" in
          "$HOME/.Trash/"*) "$LSR" -u "$ghost" 2>/dev/null; echo "  LS: purgado de la Papelera $ghost"; continue;;
        esac
        [ -n "$ghost" ] && [ ! -d "$ghost" ] && { "$LSR" -u "$ghost" 2>/dev/null; echo "  LS: purgado fantasma $ghost"; }
      done
  "$LSR" -f -R -trusted "$APP" 2>/dev/null || true
  [ -d "$DESK_APP" ] && { "$LSR" -f -R -trusted "$DESK_APP" 2>/dev/null || true; touch "$DESK_APP"; }
  echo "  LS: bundles re-registrados ($BID)"
fi

echo "OK -> $APP  ($(du -sh "$APP" | cut -f1))"
echo "   1 ventana:  open \"$APP\""
echo "   6 simbolos: open \"$APP\" --args --windows 6      (puertos 8080..8085, uno por bridge)"
echo "   a la carta: open \"$APP\" --args --ports 8080,8083,8085"
