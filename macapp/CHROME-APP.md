# ib-trader Cockpit — Acceso desde Chrome (otra máquina en la red)

## Escenario

Tienes un Mac (MacBook A) donde corre la app Swift y el backend Python.
Quieres verlo desde Chrome en otro Mac (MacBook B) o en una laptop Linux en la red.

## Solución: 4 pasos

### 1. Identifica la IP de tu Mac origen (MacBook A)

```bash
# En MacBook A:
ifconfig | grep "inet " | grep -v "127.0.0.1"
# Nota la IP local, ej: 192.168.1.42
```

### 2. Arranca chart_bridge en binding 0.0.0.0

El defecto es 127.0.0.1 (solo localhost). Para permitir red:

```bash
# En MacBook A:
python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 8080 --sym QQQ
```

O si usas fleet_up.sh:

```bash
# En MacBook A:
export CHART_HOST=0.0.0.0
zsh scripts/fleet_up.sh --chart --sym QQQ
```

El puerto 8080 se abre a toda la red.

### 3. Abre en Chrome (MacBook B)

```
http://192.168.1.42:8080/
```

Eso es. Sin VPN, sin proxy, sin certificados.

### 4. Configura la app Swift (opcional)

Si quieres que la app Swift se conecte al backend remoto (para que funcione el WKWebView):

```bash
# En MacBook A (donde está la app):
COCKPIT_URL=http://192.168.1.42:8080/ open "ib-trader Cockpit.app"
```

O desde el panel de Configuración → Puerto cockpit: teclea `192.168.1.42:8080`.

---

## Seguridad (importante)

**El servidor chart_bridge NO tiene autenticación**.

Si tu red local no es de confianza (wifi público, compartido):
- Usa SSH tunnel en vez de exposición directa
- O mantén --host 127.0.0.1 y accede desde tu Mac local

### Túnel SSH (más seguro)

**En MacBook B**:
```bash
ssh -L 8080:127.0.0.1:8080 user@192.168.1.42
# Ahora abre: http://127.0.0.1:8080/
```

---

## Archivos de Configuración

### Environment Variables

```bash
export CHART_HOST=0.0.0.0         # binding del servidor
export CHART_PORT=8080            # puerto
export COCKPIT_URL=http://192.168.1.42:8080/  # URL para WKWebView
```

### En la app Swift (Panel de Configuración)

- **Puerto cockpit**: `192.168.1.42:8080` (el host del servidor remoto)

---

## Notas Técnicas

### ¿Dónde está el servidor web?

La app Swift **NO expone un servidor web**. Es solo cliente de WebSocket.

El servidor es `chart_bridge.py` (Python FastAPI). Eso es lo que escucha en 0.0.0.0:8080.

### ¿Se puede servir desde /Applications?

Sí. La .app puede estar en `/Applications` en MacBook A. El servidor Python dentro no tiene restricciones TCC para red.

### ¿Se puede cambiar el puerto en tiempo de ejecución?

Sí:
```bash
python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 9090 --sym QQQ
```

Luego abre: `http://192.168.1.42:9090/`

### ¿Funciona con múltiples símbolos?

chart_bridge.py es **una instancia = un símbolo**.

Para 6 símbolos en paralelo, abre 6 instancias en puertos distintos:

```bash
# MacBook A:
python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 8080 --sym QQQ &
python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 8081 --sym SPY &
python3 scripts/chart_bridge.py --host 0.0.0.0 --http-port 8082 --sym NVDA &
...
```

Luego en Chrome: `http://192.168.1.42:8080/`, `http://192.168.1.42:8081/`, etc.

O usa `fleet_up.sh --chart` que arranca varios:

```bash
CHART_HOST=0.0.0.0 zsh scripts/fleet_up.sh --chart --ports 8080-8085
```

---

## Troubleshooting

### "Connection refused" o timeout

1. Verifica que chart_bridge está arriba: `ps aux | grep chart_bridge`
2. Verifica el puerto: `netstat -an | grep 8080`
3. Verifica la IP: `ifconfig`
4. Prueba desde la misma máquina: `http://127.0.0.1:8080/`

### "No tengo acceso a la red local"

macOS en Ventura+ restringe acceso al puerto 5353 (mDNS) y puertos < 1024 desde apps no firmadas.
- Port 8080 está permitido
- Si necesitas puerto < 1024, firma la app: `codesign -s - ...`

### CORS error en el navegador

Si ves "CORS policy denied":
- El servidor ya tiene CORS permitido (línea ~3150 de chart_bridge.py)
- Verifica que el navegador no tiene extensiones que bloqueen CORS
- Limpia cache: ⌘⇧Delete → "Vaciar caché" → Hard refresh (⌘⇧R)

---

## Resumen

| Scenario | Comando |
|---|---|
| **Local (Mac A)** | `python3 scripts/chart_bridge.py --sym QQQ` — accede desde `http://127.0.0.1:8080/` |
| **Red local (Mac A → Mac B)** | `python3 scripts/chart_bridge.py --host 0.0.0.0 --sym QQQ` — accede desde `http://192.168.1.42:8080/` |
| **Seguro (SSH tunnel)** | SSH-L 8080 → accede desde `http://127.0.0.1:8080/` |
| **6 símbolos en paralelo** | `CHART_HOST=0.0.0.0 zsh scripts/fleet_up.sh --chart --ports 8080-8085` |

