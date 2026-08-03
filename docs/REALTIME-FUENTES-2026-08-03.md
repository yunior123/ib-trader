# Tiempo real sin IBKR — auditoría medida en sesión (lunes 2026-08-03)

Petición de Yunior 06:38 ET: *"make sure real time is connected, intrinio is delayed as per the
docs, so finnhub is probably better"*. Todo lo de abajo está **medido con reloj contra el propio
tick**, en sesión viva. Nada viene de la documentación del vendor.

## 1. Qué alimenta cada dato vivo (auditoría de punta a punta)

| dato | fichero | quién lo escribe | proveedor | latencia MEDIDA hoy | quién lo consume |
|---|---|---|---|---|---|
| **PRINT / last** | `data/rt_last_<SYM>.txt` | `scripts/finnhub_ws_bridge.py` | **Finnhub WS** | **0,00–0,04 s** (06:44–06:47 ET) | `provider_bridge.resolve_spot()` → spot de la cadena; antes de hoy: **NADIE** |
| **barras 1m** | `data/bars_<sym>_ibkr.txt` | `scripts/provider_bridge.py:127 append_bars` | Intrinio `equities_edge` | **997–1.657 s** (mediana 1.117 s, 06:51:36) | 21 `bots/*_signal_bot.cpp`, `fleet_consensus`, `compass`, `flow_pulse` |
| **NBBO / bid-ask** | `data/nbbo_<sym>.txt` | `scripts/provider_bridge.py:148 write_nbbo` | Intrinio quote | **1.216–1.279 s** (06:42:07) | gate de spread de los bots (`qqq_signal_bot.cpp:176`) — **falla cerrado**, ver §4 |
| **cadena de opciones** | `data/opt_chain_<sym>.txt` | `scripts/provider_bridge.py write_chain` | Polygon (cabecera `# fuente polygon`) | delayed 15 min; `bidask_ok_pct 0.0000` | `bin/opt_quick`, `gex_snapshot.py` |
| **spot del mapa GEX** | cabecera de `opt_chain_*` | idem | **Finnhub si hay print, si no Intrinio** | declarado en `spot_src` / `spot_age` | `opt_quick`, `gex_snapshot` |

`data/market_source.txt` = `intrinio` y **se queda así** (§3). Es el interruptor que leen
`fleet_up.sh:19`, `fleet_keepalive_start.sh:14`, `fleet_consensus.py:29` y `e2e_smoke.sh:506`.

## 2. Latencia por fuente, medida hoy

| fuente | qué da | latencia medida | evidencia |
|---|---|---|---|
| **Finnhub WS** (`wss://ws.finnhub.io`) | trades US | **0,00 s mediana, 0,04 s máximo** | 26 símbolos, 150 s (06:44:11→06:46:47): QQQ lag_med −0,00 · AAPL 0,03 · GOOGL 0,01 |
| **Intrinio** `/prices/realtime` + `/prices/intervals` | quote + barras 1m | **1.216–1.279 s (quote)**, **997–1.657 s (barras)** | `provider_status.last_exchange_ts` 06:42:07: QQQ 1.268,9 · SPY 1.278,6 · SMH 1.216,3 |
| **Finnhub REST** `/quote` | snapshot US realtime en RTH | **17–26 s de edad observada** | MU 815,04, `t=1785768363` a las 10:46 ET; 60 llamadas/min en el plan actual |
| **Finnhub REST** `/stock/candle` | — | **HTTP 403** | plan gratis sin acceso |
| **Databento Live** | trades/mbp-1 | **no entitlado** | `BentoError: A live data license is required` en DBEQ.BASIC, EQUS.MINI y XNAS.BASIC (la key SÍ vale para histórico: `list_datasets` devuelve 29) |
| **Polygon** | cadena con griegas y OI | delayed 15 min | sin cambios respecto a `LATENCIA-FUENTES.md` |
| **Finviz Elite** | — | **401 Unauthorized** | suscripción **CADUCADA el 2026-08-01** (`data/finviz_auth_health.json`: `dias_restantes -2`, `veredicto CADUCADO`). Las 23 cachés `data/finviz_<sym>.txt` son del 17–31 de julio: **nada de ahí es "realtime"** por mucho que lo diga el comentario de `watchlist_stats.py:141` |
| **Alpha Vantage** | — | **cierre del viernes** | `GLOBAL_QUOTE SPY` → `latest trading day 2026-07-31`, price 747,03. `TIME_SERIES_INTRADAY` topado por rate-limit del plan gratis |

**Conclusión: Finnhub es la única fuente de TIEMPO REAL que tenemos esta semana.** Intrinio va
~20 minutos por detrás; su ventaja es que trae *barras* y *libro*, que Finnhub gratis no da.

## 3. Los tres límites de Finnhub que obligan a mantener Intrinio

1. **No trae libro** → no puede escribir `nbbo_*` (un `bid=ask=last` daría spread 0,00 % y
   colaría el gate: cero plausible prohibido).
2. **No trae barras** → `/stock/candle` da 403.
3. **La cinta es un MUESTREO, no la consolidada**: QQQ **2 trades / 120 acciones en 150 s** de
   premarket. Por eso hay símbolos mudos (§5).

Por eso `market_source.txt` **no pasa a `finnhub`**: el valor se exporta tal cual como
`MIT_MARKET_PROVIDER` (`fleet_keepalive_start.sh:212`) y Finnhub no puede cumplir el contrato
`MarketDataProvider` (bars + quote con bid/ask). Finnhub entra por la capacidad **`print`**, que
es exactamente donde manda.

## 4. Lo que estaba roto y se ha arreglado

| problema medido | arreglo |
|---|---|
| **El print en tiempo real no lo leía NADIE**: `rt_last_*` no aparecía en ningún bot, script ni chart — solo en tests. El dato bueno se escribía y se tiraba. | `provider_bridge.resolve_spot()` lo usa como spot primario y lo publica en la cabecera de la cadena (`spot_src`, `spot_age`) y en `provider_status.latencia`. |
| **Dos puentes Finnhub vivos** (06:49 ET, pids 82516 y 84238). El plan gratis admite **un socket por key**: se expulsaban en bucle y el log acumuló 9 `ConnectionClosedError: no close frame received or sent`. | Lockfile `data/.finnhub_ws.lock` (`fcntl.flock`): la segunda instancia **aborta con motivo**. Verificado. |
| `if caidas == 5: grita(...)` gritaba **una sola vez en toda la vida del proceso**; pasadas las 5 caídas un socket en bucle se quedaba mudo para siempre. Y `caidas`/backoff nunca se reseteaban (en modo daemon `sesion()` solo sale por excepción). | `caidas % 5` + reseteo de backoff y contador tras una sesión sana (≥120 s). |
| **Socket vivo pero mudo**: quedó conectado 131 min sin un trade; hablar cada 10 min no lo recuperaba. | Vigía fail-closed: tras `FINNHUB_WS_MUDO_S` en RTH levanta error y reconecta/resuscribe automáticamente. El reinicio limpio produjo 78 trades/23 s, 17 símbolos activos y MU 816,28. |
| Intrinio `EQUITIES_EDGE` llegaba con timestamps frescos pero precio ~15 min retrasado, y sobrescribía el print Finnhub. | `intrinio_ws_autostart` conserva esos registros para procedencia, pero sólo productos Intrinio declarados realtime pueden escribir `rt_last_*`; el chart acepta únicamente `finnhub` como fallback vivo. |
| El status arrastraba el `error`/`caidas` del proceso muerto (`estado()` fusiona con lo anterior) y hacía pasar por roto un puente sano. | Reset explícito al arrancar (`pid`, `arranque`, `caidas 0`, `error null`). |
| El puente sólo se suscribía a `provider_syms.txt` (26). Los 4 que Intrinio no cubre (DRAM SPCX SKHY EWY) **no tenían ningún precio vivo**, y el socket admite 50 suscripciones. | `fleet.txt` (30) primero. SPCX ya tiene print (07:06). |
| **El hueco de SMH** que el cockpit cantaba como *"SIN LECTURA — barras no contiguas"* sin decir de dónde salía. | `bar_salud()` mide y publica: **SMH 12 huecos en las últimas 30 barras** (QQQ 0). Y **30/30 barras con volumen 0** en premarket, en los dos. |

El gate de spread ya fallaba cerrado y **se ha dejado igual**: `write_nbbo` escribe el epoch de
bolsa, así que con dato delayed `now-ep > 10 s` y el bot rechaza el NBBO (`return -1`, nunca un 0
disfrazado). Correcto: mejor sin spread que con un spread de hace 20 minutos.

## 5. SPY, SMH y NOK

**No es ausencia de cobertura: es escasez de cinta.** Dos medidas del mismo día:

- 06:47:12→06:48:52 ET, conexión exclusiva (puente parado), suscribiendo **solo** esos tres:
  **los tres MUDOS, cero trades en 100 s**. En la misma ventana QQQ/AAPL/GOOGL sí imprimían por
  el mismo socket.
- 07:00:08 ET, **SPY SÍ imprimió**: `rt_last_SPY.txt` = `751.1200`, **44 acciones**. O sea que
  Finnhub sirve SPY; sencillamente pasan **minutos** entre print y print en premarket.

A las 07:06:26 ET, tras subir la suscripción a los 30 de `fleet.txt`: **18 símbolos con print**
y 12 sin él. Sin print a esa hora: SMH, TSM, TXN, QCOM, NOK, GLD, XLK, EWY, DRAM, SKHY, LRCX,
WDC. **SPCX**, que Intrinio no cubre en absoluto, ya tiene su único precio vivo gracias a esta
ampliación (1 trade, 103 acciones).

Estado y respaldo **declarado** (nunca silencioso):

- El spot de un símbolo sin print cae a **Intrinio quote** y se **etiqueta** `spot_src
  intrinio_quote` en la cabecera de la cadena y en `provider_status.latencia[SYM].spot_src`.
- `provider_status.spot_delayed` lista **exactamente** qué símbolos van con precio delayed. A las
  07:06:26: 17 de 26 (AMD AMZN ASML AVGO GLD GOOGL LRCX NFLX NOK QCOM SMH SNDK STX TSM TXN WDC XLK).
- Un print de más de `IBT_PRINT_MAX_AGE_S` (120 s) **deja de mandar** y el símbolo pasa a delayed
  declarado. Un precio vivo caducado no se recicla.

### 5-a. SMH: RESUELTO. Finnhub sí lo sirve

A las 07:32 alguien miró y no había `data/rt_last_SMH.txt` → conclusión falsa "SMH mudo". A las
**07:34:32** el fichero existía: **`533.8900`, 40 acciones, fuente finnhub**. En la misma sesión
de socket (25 min) SMH imprimió **5 veces, 270 acciones**. No es falta de cobertura: es cinta
escasa. A las 07:37:47 SMH tenía print de **43,4 s**.

Ese susto era un fallo del propio status: **`sin_print` se calculaba con el contador de la sesión
del socket**, que vuelve a cero en cada reconexión, así que un símbolo que había impreso hace dos
minutos aparecía como mudo. Arreglado: ahora `sin_print` mira el fichero canónico y se distingue

| campo del status | qué significa | a las 07:37:47 |
|---|---|---|
| `sin_print` | **nunca** ha impreso hoy | DRAM EWY GLD LRCX **NOK** QCOM SKHY TSM TXN WDC XLK (11) |
| `print_rancio` | imprimió, pero hace >120 s | AMD ASML AVGO GOOGL INTC META NFLX NVDA SNDK SPCX **SPY** STX (12) |
| `print_edad_s` | edad exacta por símbolo | QQQ 0,0 · AAPL 11,9 · TSLA 18,1 · MSFT 32,7 · **SMH 43,4** · AMZN 65,9 · MU 76,5 |

**NOK sigue sin un solo print** en toda la mañana. Su cobertura declarada es Intrinio quote
(delayed), y así sale etiquetado en `spot_src`. Repetir la medida tras la apertura.

### 5-b. MANADA: INOPERANTE mientras el feed sea delayed — y ahora lo grita

`fleet_consensus.py:41` exige barras de **≤180 s** para que un símbolo vote; las barras de
Intrinio llegan a **~1.000 s de mediana**. Resultado: **0 de 26 pueden votar**, hacen falta 23.
`fleet_consensus.py:110` ya fallaba cerrado (`cobertura insuficiente`, no un DANGER falso), pero
**en silencio y sin decir que la causa es el FEED y no el mercado**.

No se arregla subiendo la frescura porque no se puede: Intrinio sirve lo que sirve, y reconstruir
barras desde la cinta muestreada de Finnhub daría OHLC y volumen falsos (§3). Así que se
**DECLARA**, que es la otra salida aceptable:

- `provider_status.manada` = `{operativa, votan, need, universo, bar_age_mediana_s, motivo}`.
- El motivo nombra al culpable: *"Es el FEED (intrinio va delayed), no el mercado"*.
- Y en RTH **grita por voz** cada 30 min mientras siga inoperante: una alarma de rebaño apagada
  tiene que doler.
- Los umbrales se leen de **las mismas env** que usa `fleet_consensus` (`FLEET_CONS_MAX_BAR_AGE`,
  `FLEET_CONS_MIN_COVER`) para que el veredicto no se desincronice de su gate.

### 5-c. Mezclar barras y print sin mirar la etiqueta cuesta 1,2 %

Medido en MU: barras (Intrinio, ~17 min) marcaban **804,74 a las 06:59** mientras el print de
Finnhub daba **795,18 a las 07:07** y **796,00 a las 07:16**. Auditado quién puede mezclarlas:

- Consumidores reales de `rt_last`: `provider_bridge`, `gex_core.parse_chain_header`,
  `levels_refresh_daemon`, `intrinio_ws_autostart`. **Ninguno mezcla a ciegas.**
- La única combinación cruzada es **spot vivo × cadena/OI delayed**, que es la doctrina de la casa
  (el nivel se calcula con el libro lento, el print que lo confirma va rápido) y viaja etiquetada:
  `gex_core.parse_chain_header` devuelve `spot_src` y `spot_age` junto al `spot`, así que un
  consumidor **no puede** confundir un spot en tiempo real con uno delayed dentro de la misma
  cadena.
- No hay ningún sitio que calcule un % de variación entre cierre de barra y print vivo.

## 5-bis. Dos problemas de calidad que salieron al medir (Intrinio, no Finnhub)

Medido a las 07:06:26 ET sobre las últimas 30 barras 1m de cada símbolo:

- **16 de 26 símbolos tienen HUECOS**: XLK 25/30 · TXN 23 · GLD 21 · ASML 15 · STX 15 · LRCX 14 ·
  NOK 12 · **SMH 11** · NFLX 10 · AVGO 9 · QCOM 7 · SPY 4 · WDC 4 · TSM 2 · META 1 · QQQ 1.
  Ese es el origen del *"SIN LECTURA — barras no contiguas (hueco de feed)"* que el cockpit canta
  en SMH, y ahora está en `provider_status.bar_huecos`.
- **Volumen 0 en 30/30 barras de TODOS los símbolos** en premarket. No es que no haya volumen:
  es que la fuente lo sirve a cero. Cualquier filtro de volumen de los bots está leyendo un cero
  fabricado. Publicado en `provider_status.latencia[SYM].bar_vol0`; **medir en RTH** antes de
  decidir qué hacer.

## 5-ter. Mentiras de procedencia que quedan vivas (fuera de mis ficheros)

Mismo patrón que el `fuente="ibkr_tws"` que se arregló en `gex_snapshot.py` (commit `62ace993`):

- `scripts/gex_core.py:1058` → `"chain_src": hdr["fuente"] or "ibkr_tws"`. El `or` **inventa**
  procedencia IBKR cuando la cabecera no la trae.
- `scripts/chain_cube_archive.py:132` y `:181` → `"src": "ibkr_tws"` **hardcodeado** al archivar
  cadenas que hoy vienen de Polygon.

No los toco (ficheros de otros agentes en esta sesión), pero el archivo histórico se está
etiquetando como IBKR cuando es Polygon delayed.

## 6. El punto único de decisión de proveedor

Orden de Yunior 07:00 ET: *"code for ibkr stays, do not delete it… put conditionals per data
provider… all generic… preferably just one service file"*.

- **Tabla `PROVEEDORES`** en `scripts/provider_bridge.py` (≈línea 228): cada proveedor declara
  `caps`, `latencia`, `prio`, `activo_si` y `nota`. **Añadir o quitar un proveedor se hace ahí y
  ningún consumidor cambia.**
- **`resolve_spot()`** elige por **frescura medida**, y a igualdad por `prio` (tiempo real antes
  que delayed). La fuente viaja siempre con el número; sin candidatos devuelve
  `(0.0, "ninguna", -1)` — jamás un precio inventado.
- **IBKR sigue entero y declarado** (`caps: bars, nbbo, chain, print`, `latencia: tiempo_real`,
  `prio: 0`). Su código no se ha tocado: `scripts/ibkr_bar_bridge.py`, `scripts/opt_chain_cache.py`,
  `scripts/ib_mode.py`, `scripts/opt_chain_keepalive.sh`, `order_engine/`. Se activa con
  `data/market_source.txt` = `ibkr`, condicional que ya existía en `fleet_up.sh:30` y
  `fleet_keepalive_start.sh:198`. Hay un test que falla si alguien lo borra
  (`tests/test_realtime_routing.py::test_ibkr_sigue_declarado_entero`).

## 7. Lo que sigue abierto

- **Las barras siguen delayed ~18 min** y `fleet_consensus.py` no deja votar a nada con
  `MAX_BAR_AGE = 180 s`: con Intrinio de fuente, la alarma de MANADA está muda por construcción.
  No se ha tocado (fuera del encargo y de los ficheros asignados), pero es la decisión grande.
- **No se reconstruyen barras desde la cinta de Finnhub**: con 120 acciones en 150 s el OHLC y
  sobre todo el volumen saldrían falsos. Antes de construir eso hay que medir la densidad de la
  cinta en RTH.
- **SPY en RTH**: hay que repetir la sonda de §5 después de las 09:30 antes de dar por cerrado
  que Finnhub no sirve al capitán del mercado.
- **Volumen 0 en todas las barras de premarket** de Intrinio: los filtros de volumen de los bots
  ven ceros reales, no ausencia. Medir en RTH si el volumen aparece.
