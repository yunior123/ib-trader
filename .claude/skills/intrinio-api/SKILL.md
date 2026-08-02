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

**MEDIDO 2026-08-02**: con nuestras 2 keys, los auth de equities-edge/options-edge/opra/realtime-mx
CONECTAN (TCP/TLS) pero devuelven **Empty reply / cierran sin HTTP** = key SIN entitlement realtime
(una entitled devuelve un token). O sea: el mecanismo es correcto, pero el feed realtime hay que
ACTIVARLO en la cuenta/key. Diagnóstico: `curl https://equities-edge.intrinio.com/auth?api_key=K`
→ "Empty reply from server" = no entitled; → token JSON = entitled.
Cuando se active: construir `providers/intrinio_realtime.py` (un fichero, @register) que corra el
WS EQUITIES_EDGE/OPTIONS_EDGE y alimente los ficheros de la flota — reemplaza al puente REST delayed.

## EL SOURCE CORRECTO ES `equities_edge` (medido 2026-08-02) + por qué el WS cae
FIX medido: el REST realtime FMV funciona con **`source=equities_edge`** (NO iex/intrinio_mx, que
degradan a cboe_one_delayed). HTTP 200, `src=equities_edge`, sin downgrade, en `/prices/realtime`,
`/quote` y `/prices/intervals`. Entonces **EquitiesEdge FMV SÍ está entitled** en la key. Config:
`MIT_INTRINIO_STOCK_SOURCE=equities_edge` + `MIT_INTRINIO_INTERVAL_SOURCE=equities_edge`.
WebSocket (más rápido): `equities-edge.intrinio.com/auth` completa TLS, recibe el GET y **cierra
sin respuesta HTTP** desde Toronto Y desde VPN US de **datacenter (Datacamp)**. Eso NO es
entitlement (sería 403 con cuerpo; y el REST equities_edge da 200) → es **IP de datacenter
bloqueada por el edge del exchange** o **host de streaming no provisionado**. Para el WS: IP US
**RESIDENCIAL** (no datacenter/VPN) o pedir a Intrinio que provisione/whiteliste el host de
streaming. Opciones FMV: `/options/snapshots` (bulk 5min, 200) sí; `/options/chain` por símbolo = 403.
