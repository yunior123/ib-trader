# Skill: macOS App Creation (ib-trader Cockpit)

## Descripción

Cómo construir y empaquetar **ib-trader Cockpit.app** desde cero en macOS 13+. La app es un bundle nativo Swift + backend Python + binarios C++ con firma ad-hoc, entregable en Desktop sin instalador.

## Requisitos

```bash
# Swift + Command Line Tools (sin necesidad de Xcode completo)
xcode-select --install

# Verificar:
swiftc --version   # ≥6.3
python3 --version  # ≥3.12
clang++ --version  # ≥14

# En el Mac: 8GB RAM mínimo. Compilar compass (C++) es secuencial (1 clang++ a la vez).
```

## Estructura del Bundle

```
ib-trader Cockpit.app/
├── Contents/
│   ├── MacOS/
│   │   └── cockpit                  # binario Swift compilado
│   ├── Resources/
│   │   ├── AppIcon.icns             # icono (10 tamaños requeridos)
│   │   ├── python/                  # Python 3.12 relocatable (cpython-build-standalone)
│   │   │   ├── bin/python3.12
│   │   │   ├── lib/python3.12/site-packages/  # pip install -r requirements
│   │   │   └── ...
│   │   ├── backend/
│   │   │   ├── scripts/speak.sh, voice_queue.sh, chart_bridge.py, ...
│   │   │   ├── charts/              # HTML/JS del frontend
│   │   │   ├── data/                # datos iniciales (fleet.txt, compass.json, ...)
│   │   │   └── run.sh               # script que lanza chart_bridge.py con Python empotrado
│   │   └── engine/
│   │       ├── compass              # binario C++ de cálculo de brújula
│   │       ├── order_engine         # motor de órdenes (opcional)
│   │       └── disarm.sh            # herramienta de emergencia
│   └── Info.plist                   # metadatos del bundle
└── (sin sello: es ad-hoc del fabricante)
```

## Proceso de Construcción (macapp/build.sh)

### 1. Compilar el binario Swift

```bash
swiftc -O -target arm64-apple-macos13 macapp/main.swift macapp/Settings.swift \
  -o "$APP/Contents/MacOS/cockpit"
```

- `-O`: optimización
- `-target arm64-apple-macos13`: nativo para Apple Silicon, compatible macOS 13+
- Resultado: ~8 MB ejecutable sin dependencias externas

### 2. Compilar la Brújula (C++, secuencial)

```bash
# Esperar a que NO haya otro clang++ en curso (Mac 8GB: evitar swap)
ps aux | grep -c '[c]lang++'

# Compilar
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bin/compass scripts/compass.cpp
```

- Necesita `data/bars_<sym>_ibkr.txt` (produce: `data/compass_<sym>.json`)
- La copia en el bundle lee estos JSONs en tiempo real (~51 microseg por símbolo)
- Si falta, el cockpit marca la flecha "RANCIA" (gris, sin errores ruidosos)

### 3. Crear Metadatos (Info.plist)

```xml
<key>CFBundleIdentifier</key><string>com.ibtrader.cockpit</string>
<key>CFBundleExecutable</key><string>cockpit</string>
<key>CFBundleVersion</key><string>1</string>
<key>NSAppTransportSecurity</key><dict>
  <key>NSAllowsLocalNetworking</key><true/>  <!-- permite http://127.0.0.1 -->
</dict>
```

El sello de versión va AQUÍ (antes de codesign):

```bash
GIT_SHA=$(git rev-parse --short HEAD)
/usr/libexec/PlistBuddy -c "Add :IBTCommit string $GIT_SHA" Contents/Info.plist
```

### 4. Icono (AppIcon.icns, 10 tamaños requeridos)

```bash
# Si falta o el arte es más nuevo, generar con PIL:
python3 macapp/icon/make_icon.py
# Produce: macapp/icon/AppIcon.icns

# Verificar tamaños (Finder necesita los 10):
python3 -c "import struct; ... (check 10 tamaños: ic04 ic05 ic07 ic08 ic09 ic10 ic11 ic12 ic13 ic14)"

cp macapp/icon/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
```

Si falta 1 tamaño, Finder muestra el icono placeholder (círculo prohibitorio).

### 5. Backend Empotrado (bundle_backend.sh)

#### 5a. Python Relocatable

```bash
# Descargar cpython-build-standalone (24 MB, cached, solo 1ª vez)
# URL: https://github.com/astral-sh/python-build-standalone/releases/download/20260718/cpython-3.12.13%2B20260718-aarch64-apple-darwin-install_only_stripped.tar.gz

tar -xzf cpython-3.12.13+20260718-aarch64-apple-darwin-install_only_stripped.tar.gz \
  -C "$APP/Contents/Resources/python" --strip-components=1

# Verificar:
"$APP/Contents/Resources/python/bin/python3.12" --version
```

**¿Por qué relocatable?** Cuando pip instala paquetes, escribe shebang con la ruta absoluta de ESTE Mac:

```bash
#!/Users/yunior/ib-trader/macapp/ib-trader Cockpit.app/Contents/Resources/python/bin/python3.12
```

En otro Mac, eso falla. El tarball de astral usa rutas relativas:

```bash
# Con reemplazo Perl:
perl -0pi -e 's{^\'\'\'exec\' "/[^"]*\/python3\.12"}{\'\'\'exec\' "$(dirname -- "$(realpath -- "$0")")/python3.12"}m' "$f"
```

Resultado portátil: la ruta se deduce del lugar donde vive el script, no hardcodeada.

#### 5b. Dependencias (pip install)

```bash
"$PYTHON" -m pip install --quiet --no-compile -r macapp/requirements-backend.txt
```

`--no-compile`: evita generar `.pyc` con rutas absolutas. Se generan al vuelo.

#### 5c. Código del Backend

```bash
# Copiar solo los scripts necesarios (la lista vive en macapp/bundled_paths.txt)
sed 's/#.*//' macapp/bundled_paths.txt | grep -v '^$' | while read p; do
  case "$p" in
    scripts/*.py) cp "$p" "$BACKEND/scripts/" ;;
    charts/*)     cp "$p" "$BACKEND/charts/"  ;;
    data/*)       cp "$p" "$BACKEND/data/"    ;;
  esac
done

# Verificar que existen los archivos críticos:
find "$BACKEND" -name "chart_bridge.py" | grep -q . || exit 1
find "$BACKEND" -name "live.html" | grep -q . || exit 1
```

La lista de bundled_paths.txt es CRÍTICA: si un fichero necesario falta, la app sale sin pantalla.

#### 5d. Script de Arranque (run.sh del backend)

Genera: `$APP/Contents/Resources/backend/run.sh`

```bash
#!/bin/zsh
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(dirname "$HERE")"
SUPPORT="$HOME/Library/Application Support/ib-trader"

# Crear directorios en Application Support (siempre escribible)
mkdir -p "$SUPPORT/data" "$SUPPORT/charts/data"

# Lanzar MEDIANTE SYMLINK (no directo desde el bundle)
ln -sfn "$HERE/scripts" "$SUPPORT/scripts"
export PYTHONPATH="$HERE/scripts"

# Ejecutar el backend
"$RES/python/bin/python3.12" "$SUPPORT/scripts/chart_bridge.py" "$@"
```

**¿Por qué symlink?** El backend deduce su raiz así:

```python
REPO = dirname(dirname(abspath(__file__)))
```

Si se ejecuta desde dentro del bundle, `REPO` cae dentro del .app (de solo lectura). Con symlink, `REPO` cae en Application Support (escribible).

#### 5e. Binarios C++ (compass, order_engine)

```bash
# Compass (brújula)
if [ -x "$REPO/bin/compass" ]; then
  cp "$REPO/bin/compass" "$APP/Contents/Resources/engine/"
fi

# order_engine (motor, opcional)
[ -f "order_engine/order_engine" ] && cp "order_engine/order_engine" "$APP/Contents/Resources/engine/"

# Herramientas
cp "order_engine/disarm.sh" "$APP/Contents/Resources/engine/"
```

### 6. Firma Ad-Hoc

```bash
# ORDEN CRÍTICO: firmar DESPUÉS de empoquetar el backend
# Si firmas antes, codesign --verify lista "5000 files added" al mover el backend después.
codesign --force --deep --sign - "$APP"

# Verificar:
codesign --verify "$APP"  # exit 0 = OK
```

Sin notarización (solo ad-hoc), Gatekeeper bloqueará en otro Mac hasta que el usuario ejecute:

```bash
xattr -dr com.apple.quarantine "$APP"
```

### 7. Portabilidad (cero rutas absolutas)

```bash
# Buscar rutas de este Mac dentro del bundle
if BAD=$(grep -rl "$HOME" "$APP" 2>/dev/null); then
  echo "❌ PORTABILIDAD ROTA: $(echo "$BAD" | head -3)"
  exit 1
fi
```

Culpables comunes:
- Shebangs en `python/bin/*` (fix: `perl -0pi`)
- `.pyc` con `co_filename` absoluto (fix: `--no-compile` y `rm -rf __pycache__`)
- Rutas en config.json (fix: guardar en Application Support, no en el bundle)

### 8. Entrega a Desktop

```bash
# Usar ditto (no cp -R): preserva xattrs, ACLs, sello
DESK="$HOME/Desktop/ib-trader"
STAGE="$DESK/.ib-trader Cockpit.app.new"
ditto "$APP" "$STAGE"
xattr -dr com.apple.quarantine "$STAGE"  # quitar cuarentena
mv "$STAGE" "$DESK/ib-trader Cockpit.app"
```

**¿Por qué ditto y staging?** Entre `rm` y `cp`, si falla, Desktop queda sin app. Staging + move es atómico en comparación.

### 9. LaunchServices (limpiar fantasmas)

Después de mover a Desktop, LaunchServices puede tener registros duplicados o stale:

```bash
LSR=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

# Dumpar y buscar el mismo CFBundleIdentifier
"$LSR" -dump | awk '/identifier: com.ibtrader.cockpit/ { print $2 }'

# Si hay fantasmas (path muerto), purgarlos:
"$LSR" -u "$DEAD_PATH"

# Re-registrar el vivo:
"$LSR" -f -R -trusted "$DESK_APP"
```

Esto evita que el icono salga con el "prohibitorio" (círculo blanco + barra).

## Troubleshooting

### codesign: invalid argument (code or signature have become invalid)

**Causa**: se firmó ANTES de empoquetar backend; luego se movió el backend, rompiendo el sello.

**Fix**: limpiar y reconstruir en orden correcto (build.sh hace esto automático).

### "can't open input file" — Gatekeeper bloquea

**Causa**: app sin notarización, TCC en otro Mac.

**Fix temporal**:
```bash
xattr -dr com.apple.quarantine "$APP"
open "$APP"
```

### Python no arranca ("dyld: Library not loaded")

**Causa**: rutas hardcodeadas en shebang.

**Fix**: verificar `$APP/Contents/Resources/python/bin/*` con `head -1` — debe ser relativo.

### Backend escribe dentro del bundle ("a sealed resource is missing")

**Causa**: `REPO` deducido cayó dentro del .app en vez de Application Support.

**Fix**: asegurar que `chart_bridge.py` se lanza mediante symlink desde `$SUPPORT/scripts/chart_bridge.py`.

## Voz Española Portable

Ver `macapp/VOICE-PORTABILITY.md`. La app detecta voces españolas disponibles al arranque:

```bash
macapp/voice_detect.sh  # devuelve la mejor: Mónica > Paulina > Enhanced > Estándar > nada
```

Si no hay voz detectada, fallback a voz de sistema (puede ser inglés/robótica).

## Uninstall

```bash
# Borrar la app del Desktop
rm -rf ~/Desktop/ib-trader

# Borrar datos en Application Support
rm -rf ~/Library/Application\ Support/ib-trader

# Limpiar cache de voces
rm -f ~/.cache/ib-trader-voice
```

## Referencias (GitHub Skills)

1. **astral-sh/python-build-standalone**: Python relocatable para macOS
   - URL: https://github.com/astral-sh/python-build-standalone/releases
   - Usado en: bundle_backend.sh línea 16

2. **Apple: Creating a macOS App Bundle**
   - Referencia: https://developer.apple.com/documentation/bundleresources/placing_content_in_a_bundle
   - Structure: Contents/MacOS, Contents/Resources, Info.plist

3. **Swift for macOS Command-Line Tools**
   - swiftc manual: https://www.swift.org/documentation/
   - Nuestro: macapp/main.swift + Settings.swift

4. **Creating Relocatable Python Installations**
   - Problema: pip shebangs hardcodeados
   - Fix: perl one-liner para rewrite relativo (bundle_backend.sh línea 66)

## Keywords

`macos` `app-bundling` `swift` `python-relocatable` `codesign` `ad-hoc` `app-store` `swift-ui` `menubar-app` `code-signing`

## Versión

Skill creado: 2026-07-29
Versión de app: 1.0 (ib-trader Cockpit, Swift nativo)
Compatible: macOS 13+ (arm64)
