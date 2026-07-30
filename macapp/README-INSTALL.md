# ib-trader Cockpit.app — Guía de Instalación

## Para empezar

1. **Abre la app**: `open ~/Desktop/ib-trader/ib-trader\ Cockpit.app`
   - O: busca "ib-trader Cockpit" en Spotlight (Cmd+Space)

2. **Configura tu cuenta IBKR**: en el panel de la app, ingresa:
   - Cuenta PAPER (comienza aquí): `DU1234567`
   - Cuenta LIVE (después): `U1234567`
   - Puertos: paper 4002 (gateway) o 7497 (TWS); live 4001 (gateway) o 7496 (TWS)

3. **Conecta el Gateway/TWS**: desde la app, abre IB Gateway o TWS y autentica

## Voz en español

La app lleva dentro el banco canónico Matilda: 114 clips pregrabados. No requiere
descargar voces de macOS, configurar Accesibilidad, conectarse a una API ni instalar
nada adicional.

El menú de la barra muestra `Voz Matilda · 114/114 clips offline` cuando el banco
está íntegro. Si falta o se corrompe un clip, la voz se desactiva completa y aparece
un aviso visual. La app nunca sustituye Matilda por una voz de prueba o del sistema.

QA silencioso (no reproduce una muestra):

```bash
python3 "macapp/ib-trader Cockpit.app/Contents/Resources/backend/voice_player.py" --check
```

## Troubleshooting

### La app no arranca

**Si ves:** `Exit 1` o `can't find ...`

**Checklist**:
1. ¿Existe `~/Library/Application Support/ib-trader/`?
   - Si no, crea: `mkdir -p ~/Library/Application\ Support/ib-trader`
2. ¿Está el Gateway/TWS conectado en el puerto configurado?
3. ¿Hay espacio en disco? (la app necesita ~500 MB)

**Logs**:
```bash
tail -50 ~/Library/Application\ Support/ib-trader/chart_bridge.log
tail -50 ~/Library/Application\ Support/ib-trader/compass.log
```

### Gatekeeper bloquea la app ("No se puede abrir porque viene de desarrollador sin verificar")

**Solución temporal** (segura, la firma es ad-hoc de tu Mac):
```bash
xattr -dr com.apple.quarantine ~/Desktop/ib-trader/ib-trader\ Cockpit.app
open ~/Desktop/ib-trader/ib-trader\ Cockpit.app
```

Esto es normal para apps sin notarización de Apple. La app está completamente segura (Swift nativo + binarios C++, compilada en tu Mac).

### Python no arranca ("command not found")

**Causa**: el Python 3.12 empotrado en el bundle no se encontró.

**Fix**:
```bash
# Verificar que el bundle tiene python
ls -la ~/Desktop/ib-trader/ib-trader\ Cockpit.app/Contents/Resources/python/bin/python3.12

# Si falta, reconstruir:
cd ~/ib-trader && zsh macapp/build.sh
```

## Panel de Configuración

El panel de la app precarga valores desde (en orden):
1. Variables de entorno (`IBTRADER_ACCOUNT_PAPER`, `IBTRADER_ACCOUNT_LIVE`)
2. Config guardada (`~/Library/Application Support/ib-trader/config.json`)
3. Fichero del repo (`~/ib-trader/data/account.txt`)
4. Vacío (para teclear a mano)

**IMPORTANTE**: Precargar la cuenta LIVE NO arma nada. La doble llave del motor sigue intacta:
- Para operar: `scripts/ib_mode.sh live` + `order_engine/arm.sh`
- Para parar: `order_engine/disarm.sh`

## Datos: Bundle vs Application Support

- **Bundle** (`~/Desktop/ib-trader/ib-trader Cockpit.app`): código, recursos (de solo lectura)
- **Application Support** (`~/Library/Application Support/ib-trader`): datos en vivo, logs, config guardada

La app escribe SIEMPRE en Application Support, jamás en el bundle.

## Actualizar la App

Reconstruir y entregar a Desktop:

```bash
cd ~/ib-trader
zsh macapp/build.sh
```

Tarda ~30 segundos. La vieja se reemplaza sin perder configuración.

## Más ayuda

- **Portabilidad de voces**: `~/ib-trader/macapp/VOICE-PORTABILITY.md`
- **Docs del repo**: `~/ib-trader/docs/`
- **Daily system**: `~/ib-trader/docs/DAILY-SYSTEM.md`
