---
name: databento-api
description: API de Databento (historico + live streaming) para la flota ib-trader — barras OHLCV, quotes NBBO (mbp-1), profundidad L2 (mbp-10), cadenas de opciones (OPRA), con el detalle que muerde (precios fixed-point x1e9, ts_event en ns, datasets/schemas por entitlement, coste medido). Usar cuando se hable de Databento, db-* key, timeseries.get_range, db.Live, EQUS.MINI, XNAS.ITCH, OPRA.PILLAR, mbp-1/mbp-10/ohlcv, order book L2, o al tocar los adapters providers/databento*.py. SEÑAL-SOLAMENTE — jamás órdenes al broker.
---

# databento-api — datos de mercado medidos (historico + live)

Proveedor de datos de mercado **pago y medido por uso** (cada byte descargado cuesta). No es
tiempo-real gratis como TWS; es la fuente para PROFUNDIDAD L2 y barras/quotes limpias cuando
IBKR no llega. Ley de la casa: **nada delayed dispara una orden** — Databento live es realtime
(con entitlement), el historico es historia. Cross-links: [[data-source-latency]] · [[chain-data-contract]].

Adapters de la casa (única puerta):
- **`mit/backend/app/providers/databento.py`** — `DatabentoProvider` (historico + fusión con live).
- **`mit/backend/app/providers/databento_live.py`** — `DatabentoLiveHub` (cache de streams por símbolo/schema).
- Key en `feeds.env` → `DATABENTO_API_KEY` (**prefijo `db-` es PARTE de la key**, no se recorta).
- Requiere el paquete opcional: `pip install databento` (extra `.[databento]`). Sin él, el
  provider levanta `ProviderError` fail-loud (nunca devuelve datos falsos).

## 1. Autenticación y bases (verificado en docs oficiales)
- Key: 32 chars con prefijo `db-` (portal Databento). Env `DATABENTO_API_KEY`.
- **Historico** — HTTP base `https://hist.databento.com/v0/`, endpoint `v0/timeseries.get_range`.
  Auth = **HTTP Basic**: la KEY es el usuario, password VACÍO (`-u "db-xxxx:"` en curl).
- **Live** — no es REST: cliente `db.Live(key)` sobre stream binario DBN (TCP/gateway).
- SDK: `import databento as db` → `db.Historical(key)` y `db.Live(key)`.

## 2. Historico — `timeseries.get_range` (el 90% del uso)
```python
store = hist.timeseries.get_range(
    dataset="EQUS.MINI", schema="ohlcv-1m", symbols=["AAPL"],
    stype_in="raw_symbol", start=start, end=end)   # encoding="json" en HTTP crudo
df = store.to_df()          # DataFrame; store.replay(cb) para event-driven
```
- `stype_in="raw_symbol"` = símbolo tal cual (AAPL). Otros: `parent` (ES.FUT), `continuous`.
- HTTP crudo: `GET .../v0/timeseries.get_range?dataset=&symbols=&schema=&stype_in=raw_symbol&start=&end=&encoding=json`.
  `encoding` ∈ {`dbn`(binario, default SDK), `csv`, `json`}. El SDK usa DBN y decodifica.
- **Es un DOWNLOAD facturado**: rango grande = factura grande. En `databento.py` el span se
  acota (`get_bars` pide `limit*paso*3`, mínimo 5 días) para no bajar años por una barra.

## 3. Datasets y schemas (por entitlement — verificar antes de fiarse)
| dataset | qué | schemas usados | nota |
|---|---|---|---|
| **EQUS.MINI** | equities US consolidado barato | `ohlcv-1m` `ohlcv-1h` `ohlcv-1d`, `mbp-1` (NBBO/quote), `tbbo`, `trades`, `bbo` | **NO tiene `mbp-10`** (medido en docs) → L2 profunda va por XNAS.ITCH |
| **XNAS.ITCH** | Nasdaq TotalView L2 | `mbp-10` (10 niveles bid/ask) | profundidad real; solo nombres Nasdaq-listed |
| **OPRA.PILLAR** | opciones US (todas las bolsas) | cadenas/quotes de opciones | volumen ENORME → filtrar símbolos o quema cuota |

- En los adapters: `databento_market_dataset` (default EQUS.MINI) para bars/quote;
  `databento_depth_dataset` + `databento_depth_schema` (XNAS.ITCH / mbp-10) para el order book.
- `get_bars("...", "5m")` NO existe como schema: se pide `ohlcv-1m` y se agrega x5 en casa
  (`_aggregate`). Solo `1m`/`1h`/`1d` son nativos.

## 4. GOTCHA que muerde: precios fixed-point x1e9 + ts en ns
- **Precios DBN son enteros fixed-point ×1e9**: `744680000000` = **744.68**. Nunca uses el crudo
  como dólar. Los adapters lo resuelven con `_scaled`/`_price` (divide /1e9 si `abs > 1e7`) —
  tolera que `to_df()` a veces ya devuelva float. **Al leer campos DBN a mano, divide siempre.**
- **`ts_event` en NANOSEGUNDOS** desde epoch: `datetime.fromtimestamp(ns/1e9, UTC)` (`_timestamp`).
  `ts_recv` = llegada al gateway (fallback). No confundir con segundos → fechas en 1970.
- Campos de libro: `bid_px_00..09`, `bid_sz_00..09`, `bid_ct_00..09` (y `ask_*`) en mbp-10;
  `bid_px_00`/`ask_px_00` en mbp-1. `_int_or_none` para los counts.

## 5. Live streaming — `db.Live` (realtime, un cliente por par)
```python
c = db.Live(key)
c.subscribe(dataset="EQUS.MINI", schema="mbp-1", stype_in="raw_symbol", symbols=["AAPL"])
c.add_callback(cb); c.start()      # start() bloquea → hilo daemon
```
- **Regla dura: UN cliente por (dataset, schema)** — `DatabentoLiveHub` cachea por
  `(dataset,schema,symbol)` y lanza un hilo daemon por stream; `ensure_quote/ensure_bars/ensure_depth`
  abren bajo demanda. No abras un `Live` por llamada (fuga de conexiones + coste).
- Callbacks reciben objetos DBN genéricos (subclases de mensaje) → el hub usa `getattr` tolerante
  y aplica `_price` (÷1e9). El warmup (`databento_live_warmup_seconds`) da tiempo al primer tick
  antes de leer el cache; si no hay tick, cae al historico (`mbp-1` últimos 15 min).
- `close()` llama `client.stop()` de cada stream al apagar el provider.

## 6. Coste y límites (honestidad)
- **Metered/pago por uso** (bytes descargados + entitlement por dataset). No hay "ilimitado":
  cada `get_range` factura. Antes de un backfill grande, estimar con `metadata.get_cost` /
  `get_billable_size` del SDK. El historico crudo por HTTP con rango abierto es la forma más
  fácil de quemar dinero — acotar `start/end` SIEMPRE.
- L2 (mbp-10) y OPRA son los schemas caros (mucho mensaje). Filtrar símbolos, no barrer la flota.
- Entitlement: un dataset sin plan devuelve error/vacío — el provider levanta `ProviderError`
  ("verify dataset entitlement"), no inventa libro. Verificar el plan en el portal, no asumir.
