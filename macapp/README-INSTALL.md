# ib-trader Cockpit — Instalación & Desinstalación

## Resumen de Portabilidad

La app **funciona completamente independiente** del repo, usuario, Homebrew y MacOS pasado.
No hay rutas absolutas dentro del bundle. Python está empaquetado (relocatable, cpython-3.12 de astral).
Firma ad-hoc + gatekeeper: en otro Mac, click derecho → Abrir.

---

## 1. Instalación en Otro Mac (5 pasos)

### Paso 1: Obtener la .app

Copia `macapp/ib-trader Cockpit.app` a tu Mac destino. Puedes:
- **Arrastrar desde este repo** (si tienes git/repo acceso)
- **Email/Drive/USB**: funciona igual — es un bundle autónomo
- **CI/CD**: el build.sh entrega a `~/Desktop/ib-trader/` automáticamente

### Paso 2: Primer arranque — Gatekeeper

En el Mac destino, abre Finder:
1. Navega a donde copiaste la .app
2. Haz **click derecho** → **Abrir** (no solo hacer doble-clic)
3. Gatekeeper pregunta "¿Ejecutar software no verificado?" → **Abre**
4. La app arranca y pide **Configuración** (primer arranque)

### Paso 3: Configurar sin el repo

La app se auto-precarga desde **cualquier fuente**:
- **Env vars** (CI/tests): `IBTRADER_ACCOUNT_PAPER`, `IBTRADER_ACCOUNT_LIVE`, `COCKPIT_URL`
- **Fichero del repo** (si existe): `~/ib-trader/data/account.txt` y `~/ib-trader/config/feeds.env`
- **Panel de la app**: `~/Library/Application Support/ib-trader/config.json`
- **Vacío**: si nada de lo anterior existe

**Escenario típico** (tu amigo en otro Mac):
1. Abre la app → panel de Configuración
2. Teclea solo cuenta paper (la LIVE es opcional)
3. Teclea puerto IB Gateway (por defecto 4002 paper / 4001 live) si no es el default
4. Clic en **Guardar**
5. La config vive en `~/Library/Application Support/ib-trader/` — NO en el repo

### Paso 4: Arrancar el backend

La app necesita que corran los puentes (chart_bridge.py) en la MISMA red.
Tienes dos opciones:

**Opción A: App solita (sin repo, sin puentes)**
- La app arranque y muestra "El backend del cockpit no responde"
- El compass (si lo tiene) saldrá gris
- Puedes verlo como demo, pero sin datos vivos

**Opción B: Con puentes (necesita repo en otro Mac)**
- En OTRA máquina con ~/ib-trader repo arranca: `zsh scripts/fleet_up.sh --chart`
- En el panel de Configuración, cambia "Puerto cockpit" al host de esa máquina
- O env var: `COCKPIT_URL=http://192.168.1.42:8080/ open "path/to/ib-trader Cockpit.app"`

### Paso 5: Desinstalación limpia

Cuando ya no la necesites:

```bash
# 1. Borra la .app (arrastra a la Papelera o)
rm -rf "/Applications/ib-trader Cockpit.app"
# o donde sea que la tengas

# 2. Limpia la config y datos (OPCIONAL — guralos si quieres preservar la cuenta)
rm -rf ~/Library/Application\ Support/ib-trader
```

La app **NO toca LaunchAgents, no se instala en el sistema**. Solo escribe en:
- `~/Library/Application Support/ib-trader/` (config y datos del usuario)
- `~/Library/Saved Application State/com.ibtrader.cockpit.savedState` (marco de la ventana)
- `~/Library/Preferences/com.ibtrader.cockpit.plist` (zoom, si se cambia)

---

## 2. Versionado

Cada versión se sella con el commit:

```bash
$ open "ib-trader Cockpit.app" --args --windows 1
# La ventana muestra: "cockpit :8080 · 5ff62ea9"
#                                 ↑ commit SHA (corto)
```

El panel de menú también enseña el sello:
- Click en 📈 → "build 5ff62ea9 · 2026-07-29 03:59:57"

**Dos versiones pueden coexistir sin pisarse** — usa puertos distintos:
```bash
COCKPIT_URL=http://127.0.0.1:8080/ open "v1/ib-trader Cockpit.app"
COCKPIT_URL=http://127.0.0.1:8081/ open "v2/ib-trader Cockpit.app"
```

El zoom y la geometría se guardan POR PUERTO en Preferences, no por versión.

---

## 3. Configuración Avanzada

### Host/Binding (red local o localhost)

Por defecto, la app escucha en `127.0.0.1` (solo esta máquina).

Para permitir acceso desde otros Mac en la red:

1. **Arranca chart_bridge en binding 0.0.0.0**:
   ```bash
   CHART_HOST=0.0.0.0 python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 8080
   ```

2. **Configura la app para que busque el binding correcto**:
   ```bash
   COCKPIT_URL=http://192.168.1.42:8080/ open "ib-trader Cockpit.app"
   ```

O ajusta en el panel: Configuración → Puerto cockpit (aquí va el host:puerto del bridge).

### Chrome Web App

Si ejecutas la app en Mac A y quieres verla desde Chrome en Mac B:

1. **Asegúrate que chart_bridge escucha en 0.0.0.0**:
   ```bash
   python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 8080
   ```

2. **Abre en Chrome (Mac B)**:
   ```
   http://192.168.1.42:8080/
   ```

3. **CORS ya está activo** en chart_bridge.py (línea ~3150).

**Nota**: La app Swift WKWebView NO sube un servidor web externo. Es solo cliente de WebSocket.
El servidor que sirve http://127.0.0.1:8080 es `chart_bridge.py` corriendo en Python.
Si la .app está sola sin puentes, no hay servidor — eso es lo que se ve en el error "El backend del cockpit no responde".

---

## 4. Solución de Problemas

### "El backend del cockpit no responde"

- **Causa**: chart_bridge.py no está corriendo
- **Solución**:
  ```bash
  cd ~/ib-trader  # en la máquina que lo arranca
  zsh scripts/fleet_up.sh --chart --sym QQQ  # o el símbolo que quieras
  ```
  Luego recarga la app (⌘R) o cierra y vuelve a abrir.

### Gatekeeper rechaza la app

- **Causa**: Fue firmada en otro Mac o no tiene firma completa
- **Solución**:
  ```bash
  sudo xattr -rd com.apple.quarantine /Applications/"ib-trader Cockpit.app"
  codesign --verify /Applications/"ib-trader Cockpit.app"
  ```

### La app desaparece del escritorio

- **Causa**: LaunchServices cambió el bundle id o hay duplicados (puede pasar si reciclaste .app)
- **Solución**: Lanza una sola copia, desde una ruta fija

### El zoom no se guarda entre sesiones

- Lo guarda automáticamente en `~/Library/Preferences/com.ibtrader.cockpit.plist`
- Si lo borra: `defaults delete com.ibtrader.cockpit` (vuelve al 100%)

---

## 5. Mantenimiento: Actualizar de Versión

Cuando hay una .app nueva:

1. **Opción A (reemplazo limpio)**:
   ```bash
   rm -rf ~/Desktop/ib-trader/"ib-trader Cockpit.app"
   cp ./macapp/"ib-trader Cockpit.app" ~/Desktop/ib-trader/
   ```

2. **Opción B (dos versiones lado a lado)**:
   ```bash
   cp ./macapp/"ib-trader Cockpit.app" ~/Desktop/ib-trader-v2/
   COCKPIT_URL=http://127.0.0.1:8081/ open ~/Desktop/ib-trader-v2/"ib-trader Cockpit.app"
   ```

La config se preserva en `~/Library/Application Support/ib-trader/` — no hay que reconfigurable.

---

## 6. Inventario de Ficheros Escritos Fuera del Bundle

Por defecto, la app **solamente** escribe aquí (nunca en el repo, nunca rutas absolutas):

```
~/Library/Application Support/ib-trader/
  ├── config.json                   ← cuentas, puertos, keys de API
  ├── account.txt                   ← espejo para compatibilidad
  ├── config/feeds.env              ← keys de API (si se teclearon)
  ├── data/                         ← archivos copiados del bundle
  ├── charts/                       ← simbólicos apuntando al bundle
  ├── order_engine/                 ← socket del motor de órdenes (si arranca)
  └── compass.log                   ← log de la brújula (si arranca)

~/Library/Saved Application State/com.ibtrader.cockpit.savedState/
  └── windows.plist                 ← marco y geometría de cada ventana

~/Library/Preferences/
  └── com.ibtrader.cockpit.plist    ← zoom, timestamps
```

**Para borrar TODO** (limpieza completa):
```bash
rm -rf ~/Library/Application\ Support/ib-trader
rm -rf ~/Library/Saved\ Application\ State/com.ibtrader.cockpit.savedState
defaults delete com.ibtrader.cockpit
```

O usa el script de desinstalación:
```bash
zsh macapp/uninstall.sh
```

---

## 7. Desarrollo: Rebuild Rápido

Si cambias la UI (main.swift / Settings.swift):

```bash
# Rebuild solo la UI (sin empaquetar los 150 MB de Python)
SKIP_BACKEND=1 zsh macapp/build.sh
```

Si cambias scripts de Python que ya está empaquetados:

```bash
# Rebuild del backend + UI (más lento)
zsh macapp/build.sh
```

Verifica que el sello cambió:
```bash
/usr/libexec/PlistBuddy -c "Print :IBTCommit" "macapp/ib-trader Cockpit.app/Contents/Info.plist"
```

---

**Resumen**: app totalmente portable, sin dependencias de sistema. Config en un solo lugar (`~/Library/Application Support/ib-trader`). Desinstalación limpia con un solo comando.
