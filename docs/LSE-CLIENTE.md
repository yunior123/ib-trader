# `scripts/lse_client.py` — contrato del cliente de London Strategic Edge

> Escrito el **2026-08-08 (sábado, bolsa US cerrada)**. Todo lo de aquí está **medido contra la
> key real** de `config/feeds.env`; cada afirmación lleva el comando que la produjo. Lo que no
> se pudo medir en sábado está marcado **SIN MEDIR EN VIVO** y no se afirma.

Cargar la key: `set -a; . config/feeds.env; set +a`

| | |
|---|---|
| REST | `https://api.londonstrategicedge.com/vault` |
| WS | `wss://ws.londonstrategicedge.com` (endpoint oficial observado 2026-08-12; ver §6) |
| Auth | cabecera **`X-API-Key`**. `Bearer` y `?api_key=` → **401** `{"detail":"missing x-api-key"}` |
| Tests | `./venv/bin/python -m pytest tests/test_lse_client.py -q` (46 sin red + 1 con red opt-in) |

---

## 1. Qué devuelve cada función

Todas devuelven **`list[dict]` tal cual lo sirve el vault** o **levantan `LSEError`**. Nunca
devuelven `0`, `0.0`, `{}` ni una lista vacía fabricada: `[]` sólo aparece cuando el servidor
respondió `[]` de verdad (eso **es** la medición: no hubo filas).

| función | endpoint | campos medidos en la respuesta |
|---|---|---|
| `candles(symbol, timeframe, start, end, limit, order, dataset)` | `/candles` | `ts symbol open high low close volume` |
| `series(symbol, dataset, start, end, limit, order)` | `/series` | `symbol date value` |
| `options_chain(underlying, kind, expiry, strike, min_dte, max_dte, limit, allow_expired)` | `/options/chain` | `ticker underlying strike expiry contract_type last_price volume_today premium_today underlying_price dte iv delta gamma theta vega rho last_trade_at updated_at` |
| `options_flow(underlying, kind, min_premium, expiry, max_dte, start, end, limit, order)` | `/options/flow` | `id ts underlying ticker strike expiry contract_type last_price volume premium underlying_price dte iv delta gamma theta vega rho` |
| `option_candles(ticker_osi, start, end, limit, order)` | `/options/candles` | `ticker underlying strike expiry contract_type minute dte open high low close volume premium print_count iv_avg delta_avg gamma_avg theta_avg vega_avg rho_avg underlying_price` |
| `catalog(dataset)` / `datasets()` | `/catalog` | `dataset symbol name ticks first_tick last_tick years last_value change_pct country_name live` |
| `usage()` | `/usage` | **dict**, único que no es lista |
| `osi(underlying, strike, expiry, kind)` | — | arma el ticker OSI **local**, 0 peticiones |
| `stale_seconds(row, field)` | — | antigüedad real en segundos, **levanta** si el campo no está |

Normalización (lo único que se toca del cable, y se puede desactivar con `raw=True`):
- horas UTC `"YYYY-MM-DD hh:mm:ss[.ffffff]"` → ISO-8601 con `Z`;
- ruido binario de flotantes redondeado (`strike: 484.99999999999994` → `485.0`).

**`ts` NO se renombra.** El SDK oficial (`venv-lse/.../lse/client.py:606`) lo renombra a
`timestamp`; aquí se deja el nombre de cable para que el fichero diga lo que dijo el servidor.

**No se fabrica `volume`.** El SDK hace `r.setdefault("volume", 0.0)` para FX
(`client.py:608`): eso es el **cero plausible prohibido** por la casa — *"sin volumen
consolidado"* no es *"volumen cero"*. Aquí el campo simplemente no aparece.

---

## 2. Lo que este cliente NO garantiza (leer antes de construir nada encima)

### 2.1 La "cadena viva" sin filtro es una MENTIRA — medido

```
curl -s -H "X-API-Key: $LSE_API_KEY" \
  "https://api.londonstrategicedge.com/vault/options/chain?underlying=SPY&limit=5000"
→ rows 5000 | expiry min 2026-07-02 max 2026-07-28 | expirados (< hoy 2026-08-08): 5000
  last_trade_at max 2026-07-27 20:15:12
```

**5000 de 5000 contratos EXPIRADOS.** El techo de 5000 filas corta antes de llegar al presente.
Por eso `options_chain()` **levanta** en dos casos:
1. sin `expiry=` y tocando el techo → `"cadena truncada … llama con expiry="`;
2. si ninguna fila vence hoy o después → `"la cadena servida está ENTERA EXPIRADA"`
   (se puede pedir a propósito con `allow_expired=True`).

Con filtro sí sirve: `expiry=2026-08-14` → 327 filas, `last_trade_at` máx `2026-08-07 20:15:01`.

### 2.2 Las filas de cadena son fotos del ÚLTIMO TRADE, no una cadena sincronizada

Misma expiración `2026-08-14`, medido el 2026-08-08:

| campo | valor observado | qué significa |
|---|---|---|
| `dte` | **7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 21, 35** en la *misma* expiración | el `dte` va congelado a `last_trade_at`, no es el de hoy |
| `underlying_price` | **731,04 … 776,31** | cada fila lleva el spot del momento de *su* último trade |
| `last_trade_at` | `2026-07-10` … `2026-08-07` | contratos ilíquidos con datos de hace un mes |

Consecuencias duras:
- **`min_dte` / `max_dte` filtran por ese `dte` rancio** → devuelven contratos ya expirados
  (medido: `max_dte=7&limit=200` sobre SPY → **200/200 filas con `expiry 2026-07-02`**, todas
  vencidas). **Filtra por `expiry=`.** El remedio funciona: `expiry=2026-08-14` → 327 filas,
  327 vivas.
- `iv`, `delta`, `gamma`, `theta`, `vega`, `rho` son **de `last_trade_at`**, no de ahora.
- Antes de usar una fila para cualquier cosa que valga dinero: `stale_seconds(row)`.
- **No hay `bid`/`ask` en ninguna respuesta REST** → de aquí **no** sale gate de spread.
  El gate de spread sigue siendo de IBKR (`AGENTS.md`, regla de tiempo real).

### 2.3 `options_flow` NO trae lado agresor — medido

Unión de campos sobre **2000 filas** del barrido global:

```
id ts underlying ticker strike expiry contract_type last_price volume premium
underlying_price dte iv delta gamma theta vega rho
```

**Ni `side`, ni `bid`, ni `ask`, ni `exchange`.** Por tanto: **de LSE no sale delta firmado, ni
CVD, ni footprint.** Para lado agresor sellado por el exchange sigue mandando Databento
(`side=B` ejecuta al ask 98,7 %, `side=A` al bid 98,2 %, medido sobre 80k trades), y para el
disparo, IBKR. El test vivo `test_vivo_contra_el_vault` **falla a propósito** si algún día
aparece `side`/`bid`/`ask`, para que este documento se actualice en vez de quedar obsoleto.

Densidad de la cinta (medida): **2000 filas del barrido global = 53 segundos** de tape
(`20:14:08` → `20:15:01`). El techo de 5000 filas ≈ 2 minutos → **una sesión entera exige
paginar con `start`/`end`**, no subir el `limit`.

### 2.4 El WebSocket publica la PUJA en el campo `price` — SIN RE-VERIFICAR EN VIVO

Hallazgo del orquestador (sábado 2026-08-08, mercado cerrado): en **980 de 980** ticks con
`bid < ask`, el campo `price` era **exactamente igual a `bid`**. Si eso se mantiene en sesión,
la *quote rule* daría 100 % vendedor agresor y **el socket no sirve para delta ni footprint**.

Estado: **DECLARADO, NO CONSTRUIDO.** Este cliente **no toca el WebSocket** a propósito. Hay que
re-medirlo el lunes con la bolsa abierta antes de fiarse en ningún sentido; en sábado el socket
sólo devuelve un tick de snapshot (salvo cripto, que tiquea 24/7).

### 2.5 Frescura: no la garantiza nadie
En sábado todo es del viernes. **La latencia sólo se mide en sesión** (regla de la casa). Este
cliente no afirma frescura en ningún sitio: expone `stale_seconds()` para que el llamante la
mida, y esa función **levanta** si el campo de tiempo no está — jamás devuelve `0.0`.
Ejemplo medido de dato rancio en un sitio inesperado: `series("US10Y")` tenía como última
observación **2026-07-01**, cinco semanas atrás, un sábado de agosto.

### 2.6 Techo de filas: truncamiento silencioso
`limit=9999` → **200 OK con 5000 filas** (`2026-08-07` … `2006-09-29`). El servidor **no avisa**
de que recortó. `candles()` y `option_candles()` **levantan** cuando se pidió un rango cerrado
(`start` *y* `end`) y la respuesta tocó el techo: un rango truncado que parece completo es
exactamente el bug caro. Sin rango cerrado el techo es normal y no levanta; `capped(rows, limit)`
lo dice.

---

## 3. Cuota, ritmo y concurrencia — medido

`/vault/usage` (2026-08-08):

```json
{"bytes_cap_month":53687091200,"bytes_cap_week":16106127360,"exports_cap_hour":5,
 "historical_data_months":-1,"calls_per_minute":200,"max_rows_per_request":5000,
 "vault_concurrency":2}
```

- **200 req/min** → `RateLimiter` con ventana deslizante de **190/62 s**, estado en
  `data/lse_rate_state.json` con `flock`: dos procesos comparten la MISMA cuota (patrón copiado
  de `scripts/poly_client.py:66`).
- **`vault_concurrency: 2`** → medido con 5 `curl` en paralelo: **2 × 429 en 0,40 s**, y el 429
  trae `retry-after: 1`. Por eso hay **huecos de concurrencia en disco** (`data/lse_slots/`,
  `flock` no bloqueante): el cliente espera su turno en local en vez de comerse un 429.
- **Los GB muerden antes que las peticiones.** Cada `200` trae `x-data-bytes` = tamaño del
  cuerpo (5000 velas 1m de SPY = **601.717 bytes**). A ese ritmo, 15 GB/semana ≈ **26.000**
  peticiones grandes. `stats["bytes"]` lo acumula y `report()` lo imprime.
  ⚠️ `x-data-bytes` **no vino siempre** (una repetición idéntica llegó sin él) → `stats["bytes"]`
  es una **cota inferior**; la autoridad del gasto es `/vault/usage`.
- Reintentos **sólo** para `429` (respetando `retry-after`), `5xx` y fallo de red.
  **`400`/`401`/`403`/`404` levantan al primer intento**: reintentarlos quema cuota sin arreglar
  nada. El detalle anidado (`{"detail":"{\"detail\":\"…\"}"}`) se desenvuelve antes de mostrarlo,
  y la key se tapa con `redact()`.
- El catálogo se cachea en `data/lse_catalog.json` con escritura atómica `tmp + os.replace`,
  TTL 24 h (`LSE_CATALOG_TTL_S`). Cache corrupta o caducada → se rebaja a la red; catálogo
  vacío → **levanta** (nunca está vacío de verdad). Medido: `/catalog` **ignora `limit`** y
  devuelve las **22.851 filas** enteras → **9,5 MB** de fichero y de cuota por refresco
  (`economics 14.795 · stocks 3.982 · options 3.186 · bonds 202 · corporate_bonds 192`).
  Sus `first_tick`/`last_tick` **no** se normalizan a ISO-Z: salen como los sirve el vault.

Validación local antes de gastar una petición: `timeframe` contra la lista que sirve el propio
vault en su `400` (`1s 5s 15s 30s 1m 3m 5m 15m 30m 1h 4h 1d 1w 1mo`), `order` ∈ {asc, desc},
`limit ≥ 1`, `type` ∈ {call, put}, y el OSI contra `^[A-Z][A-Z0-9.]{0,9}\d{6}[CP]\d{8}$`.

---

## 4. CLI de diagnóstico

```bash
./venv/bin/python scripts/lse_client.py --probe                       # usage + 3 velas SPY
./venv/bin/python scripts/lse_client.py --candles SPY --tf 1d --limit 5
./venv/bin/python scripts/lse_client.py --series US10Y --limit 5
./venv/bin/python scripts/lse_client.py --chain SPY --expiry 2026-08-14 --limit 50
./venv/bin/python scripts/lse_client.py --flow SPY --min-premium 250000 --limit 20
./venv/bin/python scripts/lse_client.py --optcandles SPY260925P00780000 --limit 10
./venv/bin/python scripts/lse_client.py --catalog options
./venv/bin/python scripts/lse_client.py --usage
```

Salida real del `--probe` (2026-08-08):

```
usage: {"bytes_used_month": 136567481, ... "calls_per_minute": 200, "vault_concurrency": 2}
probe SPY 1d:
  {"ts": "2026-08-07T00:00:00.000000Z", "symbol": "SPY", "open": 769.24, ..., "close": 773.4}
  lse: 2 peticiones (2 ok, 0 429, 0 5xx, 0 red), 0.0 MB de cuota, espera 0.0 s
```

Y la guardia de la cadena, en vivo (`rc=2`, nada de datos falsos):

```
$ ./venv/bin/python scripts/lse_client.py --chain SPY --limit 5000
LSEError(200): cadena de SPY truncada en 5000 filas sin filtro de expiry: MEDIDO que el
recorte devuelve contratos EXPIRADOS (SPY 2026-08-08: 5000/5000). Llama con expiry= o una
ventana de strike
```

---

## 5. Tests

```
./venv/bin/python -m pytest tests/test_lse_client.py -q
46 passed, 1 skipped in 0.64s
```

Cero red por defecto: la única salida del módulo es `_http_get`, y los tests la sustituyen. El
limitador de ritmo y los huecos de concurrencia **sí son los reales** (ficheros en `tmp_path`).

El test que toca la red está marcado y se salta salvo opt-in:

```
IBT_LSE_LIVE=1 ./venv/bin/python -m pytest tests/test_lse_client.py -q -k vivo
1 passed, 46 deselected in 1.89s
```

Comprueba el contrato mínimo contra el servidor real (usage, 3 velas, un `404` de verdad) y
**vigila el hallazgo de §2.3**: falla si `options_flow` empieza a traer `side`/`bid`/`ask`.

---

## 6. Dónde encaja LSE en la casa

**Es HISTORIA, no disparo.** La regla dura no cambia (`AGENTS.md`): *ningún nivel que dispare
una orden puede venir de fuente delayed*, y la frescura de LSE **no está medida en sesión**.
Para qué sí sirve, medido: historia de opciones por contrato con griegas (`option_candles`),
cinta de prints de la semana corrida (`options_flow`), OHLCV largo (SPY 1d llega a **2006**),
series macro y de bonos, y un catálogo de 22.851 símbolos en 18 datasets.

Pendiente del lunes (mercado abierto), y hasta entonces **no se construye nada encima**:
1. re-medir el WebSocket: ¿sigue `price == bid` en acciones? (§2.4);
2. medir la latencia real de `options_flow` contra la cinta de IBKR;
3. medir cada cuánto se refresca una fila de `/options/chain` de un contrato líquido.
