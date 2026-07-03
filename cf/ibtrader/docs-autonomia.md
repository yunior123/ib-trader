# Que siga funcionando sin nadie delante

Yunior, 2026-08-23: *"if u die tomorrow web ibtrader online should continue to work"*.

## Qué lo mantiene vivo
**Nada de este Mac.** El worker corre en Cloudflare con un **cron cada minuto** que hace, por vuelta:
1. barras de los 6 del cockpit (15m y 1m) desde LSE, de dos en dos (su vault admite 2 a la vez),
2. el mapa de 2 símbolos (uno de los seis en rueda + uno del resto del universo) desde CBOE,
3. el flujo de opciones desde LSE,
4. **poda**: perfiles y bitácora a 7 días, flujo a 14, niveles a 90.

Fuera de 04:00–20:00 ET no recolecta y lo deja escrito en `vueltas`.

## De qué depende, y qué pasa si cae
| pieza | si falla |
|---|---|
| **CBOE** (cadena, sin clave) | no hay muros/flip/GEX nuevos; se sigue sirviendo la última instantánea con su `fuente_ts` |
| **LSE** (`LSE_API_KEY`) | no hay barras ni flujo nuevos; el mapa sigue |
| **OKX** (perps, sin clave) | el modo `perp` da error por símbolo; el modo acciones no se entera |
| **D1** | el panel no pinta. Es el único punto único de fallo |

Una fuente caída **no tumba la vuelta**: cada tarea va en su propio try y lo que falla se escribe en `vueltas` con su motivo.

## Qué NO se sostiene solo
- **`LSE_API_KEY` caduca o se cancela** → barras y flujo se paran. Se ve en `/api/estado` (`cuota_error`) y en la bitácora. Es lo primero que hay que mirar si el panel se queda quieto.
- El **plan gratuito** de Workers: 100k peticiones/día. El cron gasta ~1.440.
- La cuota de LSE: 50 GB/mes. `/api/estado` la publica en cada consulta.

## Cómo comprobar que está vivo, sin saber nada del código
```
curl -s https://ibtrader.quant-academy.workers.dev/api/estado | head -40
```
Mirar: `ventana_abierta`, que `ultimas_vueltas` traiga cosas recientes con `ok: 1`, y `cuota_lse`.

Y las tres suites, que se pueden correr desde cualquier máquina con node:
```
node test.mjs           # 21 · la matemática, sin red
node test-online.mjs    # 44 · la API publicada
node test-6ventanas.mjs # 124 · las seis ventanas y sus muros/flip/GEX
```

## Lo que hay que renovar a mano algún día
`LSE_API_KEY` y `ADMIN_KEY` son secretos del worker (`npx wrangler secret put ...`). No están en el repo ni pueden estarlo.
