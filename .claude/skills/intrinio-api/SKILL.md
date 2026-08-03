---
name: intrinio-api
description: Intrinio API v2 para el proyecto mit — auth, endpoints de barras 1m (/prices/intervals), quote realtime, histórico diario y opciones, con los entitlements/gotchas MEDIDOS de nuestra key (2026-08-01). Usar al tocar el provider Intrinio, depurar un 400/403, elegir source (iex vs intrinio_mx), o cablear barras/quotes/cadena de opciones desde Intrinio.
---

# intrinio-api — data feed del proyecto mit (medido 2026-08-01)

Base `https://api-v2.intrinio.com`. Adapter único: `mit/backend/app/providers/intrinio.py`.
Key en `config/feeds.env` → `INTRINIO_API_KEY` (config: `mit/backend/app/config.py:73`).
SDKs oficiales de referencia: `github.com/intrinio/python-sdk` (docs `SecurityApi.md`,
`OptionsApi.md`). **SEÑAL-SOLAMENTE** — Intrinio no ordena, solo alimenta datos.

## 1. Auth (MEDIDO)
- `api_key` = **el string base64 COMPLETO** tal cual (verificado HTTP 200). NO decodificar:
  el hex decodificado da `API Key formatted invalidly`.
- Dos formas equivalentes:
  - **Query param**: `?api_key=<base64>` (lo que usa el adapter, `_get`).
  - **Basic-auth**: usuario `:` + password `<hex>` (la variante hex sí vale en basic, no en query).
- Nunca poner la key en el skill ni en código; siempre desde `feeds.env`.

## 2. Barras intradía — `/prices/intervals` (el bueno)
```
GET /securities/{sym}/prices/intervals?source=iex&interval_size=1m&page_size<=1000
```
- **El endpoint viejo `/prices/intraday` devuelve 400 "no longer supported"** (deprecado, medido).
  Usar SIEMPRE `/prices/intervals`.
- `interval_size`: `1m 5m 10m 15m 30m 60m 1h` (oficial).
- `page_size` **≤ 1000** en /intervals (10000 → 400). Paginación por `next_page`.
- `source` aquí: `iex` o `cboe_one_delayed` (o sin source). **`intrinio_mx` NO es válido aquí**
  (solo sirve en /realtime; ponerlo en /intervals falla).
- Respuesta: `{"intervals":[{time,open,high,low,close,volume,average,change,...}], "next_page":...}`
  **newest-first** → el adapter ordena ascendente (`get_bars`, la flota necesita ascendente).

## 3. Quote realtime — `/prices/realtime`
```
GET /securities/{sym}/prices/realtime?source=intrinio_mx
```
- Da last/bid/ask (según entitlement). `intrinio_mx` = fuente de cotización realtime.
- Adapter `get_quote`: **no fabrica bid/ask desde last** (un bid≈last daría spread falso que
  pasaría el gate) — si faltan quedan 0 y el puente rechaza el NBBO fail-loud.

## 4. Histórico diario — `/prices?frequency=daily` (funciona)
```
GET /securities/{sym}/prices?frequency=daily&page_size<=10000
```
Devuelve `stock_prices[]` EOD. Adapter `get_daily_bars` lo lee (soporta `price` anidado o plano).

## 5. Opciones — entitlement bloqueado en NUESTRA key (MEDIDO)
| endpoint | resultado en nuestra key |
|---|---|
| `GET /options/chain/{sym}/{exp}/realtime` | **HTTP 403** (no provisionado) |
| `GET /options/expirations/{sym}` | **HTTP 403** |
| `GET /options/snapshots` (bulk) | **200**, gzip, mercado completo — es el producto **FMV OptionsEdge** |
- La cadena por-strike (`get_option_chain`/`_nearest_expiration` en el adapter) da 403 en este
  plan; el camino que SÍ responde es el **bulk `/options/snapshots`** (FMV, gzipeado).

## 6. Entitlement real de esta cuenta (MEDIDO)
- Equities: sirve **`cboe_one_delayed`** (delayed). El plan FMV realtime **NO está provisionado a
  la key** — es tema de dashboard/soporte de Intrinio, **no del código**. Verificar en cuenta antes
  de culpar al adapter.
- Consecuencia de latencia (regla de la casa): Intrinio delayed **jamás dispara una orden**. El
  PRINT que confirma un nivel es IBKR/TWS realtime; Intrinio vale para historia/estructura/relleno.
  (Ver `~/CLAUDE.md` tabla LATENCIA-FUENTES.)

## 7. Gotchas rápidos
- `/prices/intraday` = 400 deprecado → usar `/intervals`.
- `intrinio_mx` solo en `/realtime`, nunca en `/intervals`.
- key = base64 completo, no hex, no decodificar.
- opciones por-strike = 403 en esta key; usar `/options/snapshots` bulk gzip.
- page_size /intervals tope 1000; /prices diario tope 10000.
- Sources del provider en config: `MIT_INTRINIO_STOCK_SOURCE`, `MIT_INTRINIO_INTERVAL_SOURCE`
  (default `iex`), `MIT_INTRINIO_OPTIONS_SOURCE` (default `delayed`), `MIT_INTRINIO_BASE_URL`.

## REALTIME (FMV) = WebSocket, NO el REST (investigado + medido 2026-08-02)
El REST `/prices/realtime` y `/prices/intervals` SIEMPRE dan delayed (`cboe_one_delayed`) por
diseño. El **realtime FMV que se paga (EquitiesEdge/OptionsEdge)** vive en el **WebSocket** del
SDK `intriniorealtime` (`pip install intriniorealtime`), NO en REST.

- Equities: `IntrinioRealtimeEquitiesClient({"api_key":K,"provider":EQUITIES_EDGE}, on_trade, on_quote)`;
  `.connect()` → auth `https://equities-edge.intrinio.com/auth?api_key=` → token → `wss://equities-edge.intrinio.com/socket/websocket`; `.join(["SPY",...])` o `.join("lobby")` (firehose).
  Providers equities: `IEX|DELAYED_SIP|NASDAQ_BASIC|CBOE_ONE|EQUITIES_EDGE`.
- Options: `IntrinioRealtimeOptionsClient(Config(api_key=K, provider=Providers.OPTIONS_EDGE, symbols=[...]), on_trade, on_quote)`;
  auth `https://options-edge.intrinio.com/auth`; providers: `OPRA|OPTIONS_EDGE`; `OPRA_FIREHOSE` para todo.

**MEDIDO 2026-08-02**: los auth de equities-edge/options-edge/opra/realtime-mx CONECTAN (TCP/TLS)
pero devuelven **Empty reply / cierran sin HTTP**.
~~= key SIN entitlement realtime~~ ❌ **ESA LECTURA ERA FALSA** — ver la corrección de más abajo:
un fallo de entitlement daría 401/403 **con cuerpo**, y `/securities/replay?subsource=equities_edge`
responde **200**, o sea que EquitiesEdge SÍ está contratado. La causa más probable es que Intrinio
**apaga el cluster de streaming fuera de horario de mercado**.
El provider ya existe: `mit/backend/app/providers/intrinio_realtime.py` (@register
`intrinio_realtime`), con pre-chequeo de auth ACOTADO — obligatorio, porque
`equities_client.py:262` hace `requests.get` **sin timeout** y su `connect()` reintenta en bucle
infinito: arrancar el SDK con el socket apagado deja un hilo girando para siempre.

## EL SOURCE CORRECTO ES `equities_edge` (medido 2026-08-02) + por qué el WS cae
FIX medido: el REST realtime FMV funciona con **`source=equities_edge`** (NO iex/intrinio_mx, que
degradan a cboe_one_delayed). HTTP 200, `src=equities_edge`, sin downgrade, en `/prices/realtime`,
`/quote` y `/prices/intervals`. Entonces **EquitiesEdge FMV SÍ está entitled** en la key. Config:
`MIT_INTRINIO_STOCK_SOURCE=equities_edge` + `MIT_INTRINIO_INTERVAL_SOURCE=equities_edge`.
WebSocket (más rápido): `equities-edge.intrinio.com/auth` completa TLS, recibe el GET y **cierra
sin respuesta HTTP**. Opciones FMV: `/options/snapshots` (bulk 5min, 200) sí; `/options/chain` por
símbolo = 403.

### ⚠️ CORRECCIÓN 2026-08-02 02:30 ET — NO es la IP ni el entitlement (medido, la nota vieja era falsa)
La hipótesis anterior ("IP de datacenter bloqueada / whitelist") queda **REFUTADA** por medición:
- **check-host.net, 20 nodos** (BR CA CH DE×2 ES FI HU IN IR IT JP PT RU SE TR UA US×2 VN): los
  **20 fallan con `Broken pipe` a 5,1-6,9 s** contra 52.71.202.77, **sin enviar api_key**. El
  control `api-v2.intrinio.com` da **OK en los 20**. Un bloqueo por IP no puede fallar en 20 países
  a la vez; y sin key enviada, el entitlement no puede intervenir.
- **Los 7 hosts del SDK fallan idéntico** (`realtime-mx`, `realtime-delayed-sip`,
  `realtime-nasdaq-basic`, `cboe-one`, `equities-edge`, `realtime-options`, `options-edge`),
  cada uno en su IP. Incluye `cboe-one`/`realtime-delayed-sip`, que sirven datos **delayed que SÍ
  tenemos** — si fuera entitlement darían 401/403 **con cuerpo**.
- **El servidor nunca lee la petición**: cierra a los ~5,14 s **aunque no se envíe un solo byte**
  tras el handshake (`api-v2` en cambio aguanta >30 s ocioso). ~5000 ms es el `request_timeout`
  por defecto de Cowboy (Erlang/Phoenix). Patrón de **balanceador vivo con backend ausente**.
- **Control de "mercado cerrado"**: Polygon `wss://socket.polygon.io/stocks` el mismo domingo
  conecta en 0,27 s y responde al auth **con cuerpo**. O sea: que el mercado esté cerrado no tumba
  por sí solo un endpoint de streaming — pero Intrinio **puede** apagar su cluster fuera de horario.

### CAUSA MÁS PROBABLE (~70%, NO cerrada): apagado del cluster fuera de horario
Lo **cerrado y medido** es el diagnóstico técnico: *edge TLS de AWS vivo + app Phoenix/Cowboy detrás
ausente*. Lo que falta por cerrar es el PORQUÉ de negocio. No lo afirmes como certeza hasta el lunes.

Citas verificadas a mano en la fuente primaria (2026-08-02):
- **La buena** — `intrinio-realtime-csharp-sdk/README.md:500` (repo con push el 2026-07-29), une los
  dos términos sin inferir nada:
  > "…especially useful for testing **when the markets are closed and the websocket servers are
  > off for the night**."
- `intrinio.com/how-to/stream-stock-trades-and-quotes` → Prerequisites: **"Testing the code during
  market hours"**.
- El SDK de equities documenta el **ReplayClient** con caso de uso declarado *"while the servers are down"*.
- "…and **when then servers turn on every morning**" aparece en `java-sdk:356`, `go-sdk:382`,
  `options-python-sdk:377`, `options-java-sdk:332`. ⚠️ **Es un párrafo boilerplate copiado entre
  repos: cuenta como UNA fuente, no como cuatro.**

**INVESTIGACIÓN EXTERNA (GitHub/web, 2026-08-02) — dos hallazgos que cambian el cuadro:**
- 🔴 **`intrinio-realtime-options-python-sdk` issue #7, ABIERTO desde 2024-02-23**: *"Client drops
  connection and fails to reconnect"* — la conexión cae **alrededor de medianoche**, la reconexión
  falla en silencio y **el cliente sigue desconectado cuando el mercado abre**, días seguidos.
  Es el patrón del apagado nocturno, confirmado por un tercero, Y la prueba de que **el SDK oficial
  no se recupera solo**. Consecuencia para nosotros: cachear un fallo de conexión sin caducidad deja
  el provider muerto justo el día que hace falta → `intrinio_realtime.py` usa `ERROR_TTL_S` (60 s).
  Ver también #13 *"improve reconnection logic"* (abierto).
- 🟡 **Contradice el apagado**: `docs.intrinio.com/documentation/websocket_iex` dice *"Upon
  connecting, the system will send you the last recorded IEX bid/ask/last quotes, **even during
  off-hours**"* → al menos el feed IEX **espera aceptar conexiones fuera de horario**. Por eso la
  hipótesis del apagado NO sube del ~70%.
- Nadie ha reportado nuestro síntoma exacto (`Empty reply` / `RemoteDisconnected` en `/auth`) en
  ninguno de los 7 repos de SDK. Ausencia de evidencia, no evidencia de ausencia.

**Lo que NO sostiene la hipótesis** (no lo uses como prueba):
- `status.intrinio.com` = *All Systems Operational* **NO prueba que no haya outage**: su
  `components.json` solo cubre APIv1/APIv2/Web APIs — **no hay componente de streaming**, así que una
  caída del socket es INVISIBLE ahí. Además, de 50 incidentes históricos: 0 en sábado, 1 en domingo,
  48/50 creados entre 09:00 y 17:36 ET → una caída de viernes noche no se publicaría hasta el lunes.
- La doc dice "night"/"every morning"/"during market hours", **jamás menciona fin de semana ni una
  hora numérica**. `docs.intrinio.com/documentation/websocket_*` da HTTP 500 y
  `/websocket/getting_started` da 404.
- Un servidor "apagado" no completa un TLS 1.3 con cert válido: lo medido es *backend muerto*,
  compatible con escalado a cero pero **inferencia nuestra, no texto del vendor**.

Ranking honesto: **A (apagado programado) 70% · B (outage en curso) 17% · D (provisioning aparte) 3%
como causa del síntoma · C (hosts migrados) 3%**. C queda **REFUTADA**: 6.3.0 es el último en PyPI y
los SDK de C#/Go/Java apuntan en HEAD a los MISMOS 7 hosts. A y B no son excluyentes.

`/auth` y el socket **viven en el mismo host y la misma app Phoenix** (`equities_client.py:179-196`
vs `:206-224`), así que apagar el cluster de streaming tumba `/auth` por construcción — eso explica
exactamente el síntoma (TLS del balanceador OK + Cowboy ausente + cierre a los 5 s).

**Lo que NO está documentado**: la ventana horaria numérica. Dicen "every morning" / "off for the
night", nunca "04:00 ET". Si enciende sábados/domingos tampoco consta. Eso lo mide la sonda.

**FMV EquitiesEdge está entitled, probado por otra vía**:
`GET /securities/replay?subsource=equities_edge&date=<YYYY-MM-DD>` → **200** con URL S3 firmada
(`EQUITIES_EDGE_20260731.bin`, 3,25 GB/día). `iex` y `cboe_one` dan **403** en ese mismo endpoint.
El fichero es autodelimitado y se puede leer **por rangos HTTP** sin bajar los 3 GB:
`[tipo(1)][len(1)][msg(len-2)][time_received(8, <Q)]` repetido. Con esto se valida el camino
completo con el mercado cerrado — es el "replay client" que ellos mismos recomiendan.
⚠️ **Medido: el replay de EQUITIES_EDGE trae SOLO trades, cero quotes** (216.265 msgs de premarket
y 108.718 de RTH, 100% tipo 0). La doc del SDK **sí** describe mensajes Quote con `EQUITIES_EDGE`
como subprovider y da requisitos aparte para "Trades and Quotes", así que lo más probable es que sea
una limitación del *fichero de replay*, no del socket. **Confirmar en vivo el lunes**: sin quotes no
hay NBBO de Intrinio y el gate de spread se queda ciego (el provider deja bid/ask en 0 y el puente
rechaza — falla cerrado, que es lo correcto, pero deja la flota sin gate por esa fuente).

**MEDIDO EL DOMINGO ENTERO (2026-08-02)**: 97 mediciones de 02:16 a 18:44 ET, **las 97 con el
socket abajo**. Cubre toda la "mañana" del domingo → el *"turn on every morning"* de los README
**NO se cumple en fin de semana**: el cluster sigue el CALENDARIO DE MERCADO, no un ciclo diario
literal. Eso es consistente con el apagado programado y hace la hipótesis de outage menos probable
(un outage de 16 h en fin de semana sin incidencia publicada sería raro, aunque su status page es
ciega al streaming). Sigue sin poder cerrarse hasta medirlo en sesión.

**Estado honesto**: el WS **nunca se ha medido con el mercado abierto**. Todas las medidas (2026-08-01
noche y 2026-08-02 madrugada) son fuera de sesión. La sonda `scripts/intrinio_ws_probe.py`
(job `com.ibtrader.intrinioprobe`, cada 10 min, sin portero horario) escribe
`data/intrinio_ws_probe.jsonl` con cada fila etiquetada por fase de sesión: si revive justo al abrir
premarket el lunes, la causa es horaria; si sigue muerto en RTH, es outage/provisioning y toca soporte.
Provider listo para entrar solo: `mit/backend/app/providers/intrinio_realtime.py` (@register
`intrinio_realtime`) — levanta fail-loud si el socket no está, jamás sirve precio rancio como vivo.

## WEBSOCKET: TODO LO PROBADO EL 2026-08-02 21:00 ET (para no repetirlo)

Antes de volver a tocar esto, lee la tabla. **Ninguna de estas vias conecta**, y la conclusion
importante es que **el SDK OFICIAL sin modificar falla igual** — o sea que no es un error de
integracion nuestro.

| prueba | resultado |
|---|---|
| SDK oficial `intriniorealtime` 6.3.0 (**la ultima de PyPI**) tal cual, `EQUITIES_EDGE` | `Cannot connect: RemoteDisconnected` a los 5,1 s, en bucle |
| hosts de HEAD en los SDK de **Python, Node y Java** | los MISMOS 5 + options-edge/opra: no hay host nuevo al que migrar |
| `curl --http1.1` / `--http2-prior-knowledge` / `--tlsv1.2` | los tres: cierre a 5,13 s, `http=000` |
| `openssl s_client` + GET crudo con Host y SNI correctos | el server lee y cierra: **`DONE`**, cero bytes de respuesta |
| upgrade WebSocket directo a `/socket/websocket` en los 5 hosts | `InvalidMessage: did not receive a valid HTTP response` (5,14-5,24 s) |
| modo *public key* (`Authorization: Public <key>`, sin api_key en la query) | igual, 5,13 s |
| mTLS (¿pide cert de cliente?) | **NO**: `No client certificate CA names sent` |
| ALPN | `No ALPN negotiated` incluso ofreciendo solo `http/1.1` (normal en Cowboy pelado) |
| DNS local vs Google (8.8.8.8) vs Cloudflare (1.1.1.1) | **identico** en los 6 hosts; y cada host tiene **IP propia** (no es un edge compartido caido) |
| desde OTRA red (infra de fetch de Anthropic, ruta distinta a la nuestra) | `socket hang up` |
| 20 nodos de check-host.net en 4 continentes | los 20 fallan; el control `api-v2` responde OK en los 20 |
| **misma key** contra `api-v2.intrinio.com` | **200** — `/prices/realtime?source=equities_edge` devuelve `last_price` y `/securities/replay` sirve el fichero |

**Los 5,13 s no son casualidad**: es el `request_timeout` por defecto de Cowboy (5000 ms) + el RTT
a us-east-1 (~130 ms). El proceso que termina el TLS esta vivo y sirve el cert `*.intrinio.com`
valido, pero nunca da por completa la peticion.

**Lo que NO se puede decidir desde fuera**: "cluster apagado" y "el WAF descarta en silencio a
quien no esta autorizado" producen exactamente la misma observacion. Lo unico que queda para
distinguirlas es preguntar a `success@intrinio.com`.

**Mientras tanto**: `scripts/intrinio_ws_autostart.py` sondea `/auth` cada 20 s y abre el socket
en el instante en que responda, con voz. No hay que vigilarlo a mano.

## CUANTAS KEYS HAY, Y QUE ENTITLEMENT TIENEN (medido 2026-08-02 21:15)

**UNA sola key** en este Mac: `config/feeds.env:INTRINIO_API_KEY`. El `feeds.env` de la raiz del
repo es un **symlink** al mismo fichero (`lrwxr-xr-x feeds.env -> config/feeds.env`), asi que no
son dos. Buscado ademas en el keychain (`security find-generic-password -s intrinio` -> no existe),
en el entorno y en los `.env`: no hay segunda key. Si aparece una (Intrinio da **Sandbox** y
**Production** en el panel), probarla cuesta 30 s — pero hoy no hay ninguna otra guardada.

**La propia API declara el entitlement.** Pidiendo cada `source` a
`/securities/AAPL/prices/realtime` y leyendo el campo `messages`:

| `source=` | lo que responde Intrinio |
|---|---|
| `iex` | **"Realtime sources have been adjusted to `cboe_one_delayed` based on your access."** |
| `intrinio_mx` | "…adjusted to `iex` based on your access." |
| `delayed_sip` | "…adjusted to `delayed_sip,utp_delayed,cta_a_delayed,cta_b_delayed,otc_delayed`…" |
| `cboe_one` / `nasdaq_basic` / `equities_edge` | **sin mensaje de ajuste** (los acepta tal cual) |

O sea: **el plan es de tier DELAYED y lo dice el vendor**, no nosotros. Eso encaja con que el
socket de streaming nos rechace, y es una explicacion distinta de "cluster apagado" — aunque
ninguna de las dos se puede confirmar desde fuera (ver la tabla de arriba: el mismo cierre a
5,13 s le pasa a una peticion SIN key desde otra red).

**Cosa util que SI tenemos**: `/securities/{sym}/prices/realtime?source=equities_edge` responde
con `last_price` + `last_time` reales para toda la flota (probado AAPL SNDK NOK LRCX WDC SPY),
y `/securities/replay` sirve los ficheros de ticks. Delayed, pero medido y honesto.
