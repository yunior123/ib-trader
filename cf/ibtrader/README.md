# ib-trader en Cloudflare

Mapa de posicionamiento **señal-solamente** que corre entero en el borde de Cloudflare: sin Mac,
sin IBKR y sin ninguna API de pago. https://ibtrader.quant-academy.workers.dev

## Por qué existe
Las suscripciones cayeron a la vez (UW 401, Intrinio 401, Polygon-opciones 403, Finviz Elite 401)
y la flota local dependía de ellas. Estas dos fuentes sobreviven y **Cloudflare las alcanza**
(medido el 2026-08-23; algunas responden mejor desde el borde que desde casa — Yahoo daba 429 en el
Mac y 200 aquí):

| fuente | qué da | clave |
|---|---|---|
| **CBOE** `delayed_quotes` | cadena completa con **gamma, delta, IV y OI por contrato** | no |
| **LSE** vault | barras 1m y **flujo de opciones con prima y griegas** | `X-API-Key` |

CBOE sirve 5 MB por ETF y 12,5 MB en SPX, y el Worker del plan gratuito los parsea sin romper el
límite de CPU (medido).

## Qué calcula
- **Muros** de OI (call wall / put wall).
- **GEX por strike y total**, en $ por cada 1 % de movimiento. Convención declarada: dealer largo
  de calls, corto de puts. **El lado real del OI no se observa**: es un supuesto, no una medición.
- **Flip**: todas las raíces del GEX acumulado, y se publica **la más cercana al spot** con su
  distancia. Alineado con `gex_core._flip_roots` del repo — quedarse con la primera raíz esconde la
  trampilla. Sin cruce ⇒ `null`, nunca el borde del recorte.
- **Max pain** y **Bollinger(20,2)** con %B; menos de 20 cierres devuelve `null`, no un 0,5 plausible.

## Rutas
| ruta | qué |
|---|---|
| `/` | panel |
| `/api/niveles` | última instantánea de cada símbolo |
| `/api/perfil?sym=QQQ` | perfil por strike (top 40 por \|GEX\|) |
| `/api/flujo?min_prima=100000` | flujo de opciones por prima |
| `/api/barras?sym=QQQ` | barras 1m + Bollinger |
| `/api/quotes` | **precio vivo de TODA la flota** (o `?syms=A,B`): barrido rotativo Finnhub con D1 como almacén compartido; `age_s` declara la edad de cada precio. Barrido completo ~1 min de demanda |
| `/api/estado` | recuentos, cuota de LSE y últimas vueltas |
| `/stream?sym=…&modo=perp` | **WebSocket realtime** del worker: history + ticks (~5 s) + niveles (~1 min). Con `modo=perp` (o `perp=…`) sirve el perpetuo OKX 24/7; sin él, snapshot de D1 declarado sin ticks. Habla un subconjunto del protocolo del puente local — el cockpit de seis ventanas funciona en el borde sin el Mac |
| `/tarea/vuelta?key=…` | fuerza una vuelta (requiere `ADMIN_KEY`) |
| `/tarea/mapa?sym=…&key=…` | recolecta un símbolo |

## Cómo corre
Cron cada minuto, **ventana 24/5** (Yunior 2026-08-23: "sunday to friday") — del domingo al
viernes se recolecta continuo y solo el sabado reposa. Cada vuelta hace **un símbolo del mapa**
(41), **un símbolo de barras** de la flota (36) y el flujo: 5 MB de cadena no caben todos en una
invocación, así que van en rueda. El precio VIVO de las ventanas no depende del cron: lo sirve
`/stream` (Finnhub realtime en cash, perpetuo OKX en modo=perp).

## Lo que NO hace
No coloca órdenes ni las sugiere, y **no notifica** — ver `data/notify_off` en el repo. Es un mapa.

## Lo que la fuente NO da (medido, no supuesto)
- LSE **no publica griegas de los contratos que vencen ese mismo día** (4 de 100 en la muestra).
  Llegan como `null`, nunca como 0: un cero plausible es peor que un hueco declarado.
- CBOE es **diferida y desigual entre símbolos**. Su `last_trade_time` viaja con cada fila y es lo
  primero que hay que mirar; la hora nuestra no dice nada sobre la edad del dato.
- 7 de 41 símbolos no tienen flip hoy (QQQ, SPY, SMH, IWM, QCOM, SPCX, WDC): el acumulado nunca
  cruza cero. Eso es una lectura, no un fallo — y el panel dice «sin cruce» en vez de inventar uno.

## Desarrollo
```
node test.mjs                                   # 21 pruebas de las funciones puras
node test-online.mjs                            # 44 pruebas contra el worker PUBLICADO
npx wrangler deploy
npx wrangler d1 execute ibtrader --remote --command="SELECT COUNT(*) FROM niveles"
```
Secretos: `LSE_API_KEY` y `ADMIN_KEY` (`npx wrangler secret put …`).
