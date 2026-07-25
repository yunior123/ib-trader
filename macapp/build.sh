#!/bin/zsh
# build.sh — compila el cockpit como .app nativa. NO requiere Xcode completo,
# basta con Command Line Tools (verificado 2026-07-25: swiftc 6.3.3, sin xcodebuild).
#
#   zsh macapp/build.sh            -> macapp/ib-trader Cockpit.app
#   open "macapp/ib-trader Cockpit.app"
set -euo pipefail
cd "$(dirname "$0")/.."
APP="macapp/ib-trader Cockpit.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# arm64 nativo; -O porque no cuesta nada y el binario es diminuto igual
swiftc -O -target arm64-apple-macos13 macapp/main.swift -o "$APP/Contents/MacOS/cockpit"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>ib-trader Cockpit</string>
  <key>CFBundleDisplayName</key><string>ib-trader Cockpit</string>
  <key>CFBundleIdentifier</key><string>com.ibtrader.cockpit</string>
  <key>CFBundleExecutable</key><string>cockpit</string>
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

# Firma ad-hoc: suficiente para uso propio y para pasarla a un amigo (el tendra que
# hacer "Abrir de todos modos" la primera vez, o quitar la cuarentena con:
#   xattr -dr com.apple.quarantine "ib-trader Cockpit.app"
codesign --force --sign - "$APP" >/dev/null 2>&1 || echo "  (aviso: firma ad-hoc fallo, la app sigue funcionando en local)"

echo "OK -> $APP  ($(du -sh "$APP" | cut -f1))"
echo "   abrir:  open \"$APP\""
echo "   otro puerto: COCKPIT_URL=http://127.0.0.1:9000/ open -a \"$PWD/$APP\""
