# LSE (London Strategic Edge) — capacidades REST medidas

**Medido**: 2026-08-08 19:06→19:26 UTC (sábado, bolsa US cerrada; cripto 24/7).
**Cómo**: `scripts/research/lse_probe.py` (fase 1 = barrido, `--phase2` = verificación + huecos,
`--phase2b` = dos cierres). Crudo completo en `data/research/lse_probe.json`.
**Llamadas**: 389 (328 OK / 61 fallo). **SDK**: `lse-data` 0.14.0 en `venv-lse/`.
**Cuota**: fase 1 cobró 111,86 MB, fase 2 cobró 11,26 MB → **0,76 % del tope semanal (15 GB)**.
⚠ El contador `/usage` es **por CLAVE, no por proceso**: entre mis fases subió más de lo que yo
bajé (otras sesiones comparten la key). Los bytes que **yo** recibí, medidos en el cliente:
**100,1 MB**.

**Sábado**: nada de lo que sigue prueba latencia en vivo. Toda "frescura" citada es la marca de
tiempo del último dato servido, no un tiempo de propagación.

---

## 1. Veredicto para esta casa (lo que cambia y lo que no)

| Pregunta | Respuesta medida |
|---|---|
| ¿Sustituye a Polygon para historia de barras? | **SÍ, y lo mejora.** 1m real desde **2003** en acciones/ETF/índices, 2004 en FX. La BD de casa tiene 21 días. |
| ¿Sustituye el puente de Naver para Corea? | **Probablemente sí**: `005930.KS` y `000660.KS` con 1m desde **2022-11-11**, sesión KRX completa. |
| ¿Sirve para muros de OI? | **NO. La cadena no trae `open_interest`.** Verificado en 3 llamadas, 18 campos, sin OI. |
| ¿Sirve para el gate de spread (regla 4)? | **NO. La cadena no trae `bid` ni `ask`.** Solo `last_price`. |
| ¿Sirve para disparar una orden? | **NO.** Ni por REST (es archivo) ni por WS (el socket publica la puja, ya cerrado por el orquestador). IBKR sigue siendo el disparo. |
| ¿Aporta algo único? | **SÍ: 1m de opciones con griegas por contrato desde 2026-01-02** (189,2 M filas) y la cinta de prints con griegas al microsegundo. |
| ¿Cubre la flota? | **25 de 30.** Faltan **TSM, XLK, EWY, DRAM, SKHY** (404). Faltan también SPX, XSP, NDX y VIX como símbolos. |

---

## 2. Métodos públicos del SDK (firma real, leída del fuente)

`venv-lse/lib/python3.9/site-packages/lse/client.py` (1251 líneas) y `.../lse/vault.py` (223).

### REST — vault (`client.py`)

| Método | Línea | Firma real |
|---|---|---|
| `candles` | 582 | `(symbol, timeframe="1m", start=None, end=None, limit=5000, order="asc", dataset=None)` |
| `series` | 648 | `(symbol, dataset=None, start=None, end=None, order="asc", limit=5000)` |
| `economic_calendar` | 617 | `(region=None, event=None, start=None, end=None, released_only=False, order="asc", limit=5000)` |
| `insider_trades` | 630 | `(symbol=None, type=None, start=None, end=None, order="desc", limit=5000)` |
| `dividends` | 638 | `(symbol=None, start=None, end=None, order="desc", limit=5000)` |
| `splits` | 643 | `(symbol=None, start=None, end=None, order="desc", limit=5000)` |
| `cot` | 666 | `(symbol=None, start=None, end=None, order="asc", limit=5000)` |
| `financial_reports` | 673 | `(symbol=None, report_type=None, period=None, start=None, end=None, order="desc", limit=5000)` |
| `company_profiles` | 691 | `(symbol=None, limit=5000)` |
| `fundamentals` | 696 | `(symbol=None, limit=5000)` |
| `bond_yields` | 701 | `(symbol=None, start=None, end=None, order="asc", limit=5000)` |
| `options` | 782 | `(underlying, type=None, expiry=None, strike=None, min_dte=None, max_dte=None, limit=5000)` |
| `options_flow` | 823 | `(underlying=None, type=None, min_premium=None, expiry=None, max_dte=None, start=None, end=None, order="desc", limit=5000)` |
| `option_candles` | 858 | `(contract, strike=None, expiry=None, type=None, start=None, end=None, order="asc", limit=5000)` |
| `options_underlyings` | 879 | `()` — local, filtra el catálogo cacheado (**9,1 ms**, 0 bytes) |
| `catalog` | 1012 | `(category=None)` — 1ª llamada baja 9,5 MB; después **2,6 ms** desde caché |
| `get` | 895 | `(table, **filters)` — pasarela legacy PostgREST → vault |

### Vault bulk / discovery (`vault.py`)

| Método | Línea | Firma real |
|---|---|---|
| `vault_meta` | 73 | `()` → forma del vault (datasets, timeframes, `access`) |
| `datasets` | 81 | `(dataset=None)` → catálogo crudo con `ticks/first_tick/last_tick` |
| `reference` | 96 | `()` → filas y rango de cada tabla de referencia |
| `history` | 102 | `(symbol=None, *, dataset=None, timeframe="tick", start=None, end=None, dest=None, dataframe=True, poll_seconds=1.5, timeout=1800.0)` |
| `dataset` | 141 | `(name, *, start=None, end=None, dest=None, dataframe=True, poll_seconds=1.5, timeout=1800.0)` |
| `economics` | 156 | `(symbol=None, start=None, end=None, order="asc", limit=5000)` |

### Streaming (`client.py`) — no re-medido aquí, ya cerrado por el orquestador
`stream` 337 · `connect` 410 · `subscribe` 424 · `unsubscribe` 437 · `subscribe_options` 457 ·
`unsubscribe_options` 482 · `disconnect` 499 · `on` 306 · `stream_async` 1061 · `connect_async` 1098 ·
`disconnect_async` 1103. Propiedades: `symbols` 283, `tier` 288, `authenticated` 293, `subscriptions` 298.
Módulo: `tape()` 143. Clases: `LSEError` 40, `Tick` 56, `OptionTick` 91.

---

## 3. Límites del plan (`/vault/usage`, medido)

```
bytes_cap_week 16.106.127.360 (15 GB)   bytes_cap_month 53.687.091.200 (50 GB)
max_rows_per_request 5000               calls_per_minute 200
vault_concurrency 2                     exports_cap_hour 5
historical_data_months -1 (ILIMITADO)   tier "registered"
```

**`vault_concurrency 2` es un techo DURO**: 4 peticiones idénticas lanzadas a la vez →
2 con 200 y **2 con `429 {"detail":"too many concurrent requests for this key; retry shortly"}`**
(`p2_concurrency`). Cualquier daemon debe serializar a 2 o reintentar.

`max_rows_per_request 5000` no da error al pasarse: `limit=99999` devuelve **5000** filas
en silencio (el SDK hace `min(limit, 5000)` en `client.py:601`). **Un consumidor que no compare
`len(rows)` con 5000 se come una serie truncada sin enterarse.**

**Timeframes válidos** (del mensaje de error real, `candles(SPY,"2m")` → 400):
`1s, 5s, 15s, 30s, 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo`.

---

## 4. Los 18 datasets: qué sirve cada uno

`/meta` declara dos capacidades excluyentes: **`candles`** (7 clases + 3 sintéticas) y **`series`**
(7 clases). Cruzarlas falla siempre, y el error lo dice:

- `series()` sobre un dataset de velas → `400 not a series dataset; valid: ['bond_futures','bonds','corporate_bonds','credit_indices','economics','fx_derivatives','sovereign_yields']` (11/11 pruebas).
- `candles()` sobre un dataset de series → `404 '<sym>' has no candle data; browse /catalog` (14/14 pruebas).

### 4.1 Datasets de VELAS

Muestra = el símbolo con más ticks del dataset. "1ª vela" = `candles(sym, tf, order="asc", limit=1)`.

| dataset | símbolos | muestra | `first_tick` catálogo | **1ª vela 1m real** | huecos intra-sesión (5000 barras 1m) |
|---|---:|---|---|---|---|
| stocks | 3.982 | NVDA | 2003-09-10 | **2003-09-10 12:00** | **0** |
| etf | 25 | SOXL | 2026-04-27 | **2010-03-11 14:56** | **0** |
| etf | — | GLD | 2026-04-27 | **2004-11-18 14:30** | 331 |
| index | 19 | NAS100/USD | 2023-02-15 | **2003-03-21 14:30** | 3 |
| fx | 62 | EUR/JPY | 2009-09-25 | **2003-01-01 20:58** | 4 |
| crypto | 58 | BTC/USD | 2017-08-17 | 2017-08-17 04:00 | **0** (fill 100 %) |
| commodity | 23 | XAU/USD | 2026-04-27 | **2006-03-19 20:29** | 3 |
| futures | 69 | FGBL | 2025-03-11 | 2025-03-11 00:15 | 389 |
| volatility | 1 | VIX/USD | 2026-07-01 | 2026-07-01 13:15 | 10 |
| interest_rates | 4 | USB02Y/USD | 2026-06-30 | 2026-06-30 22:00 | 2.063 |
| currency_index | 1 | DXY/USD | 2026-06-30 | 2026-06-30 21:23 | 111 |

**Hallazgo grande: `first_tick` del catálogo NO es la profundidad de las velas.** El catálogo
describe el archivo de TICKS; las velas vienen de otro archivo mucho más profundo. GLD: catálogo
dice 2026-04-27, la primera vela 1m es de **2004-11-18** (21 años antes). NAS100/USD: catálogo
2023-02-15, primera vela 1m **2003-03-21**. **Fiarse de `first_tick` para planificar un backfill
es subestimar el archivo por más de una década.**

Al revés también pasa: `ZSPC` tiene `last_tick` 2026-04-27 pero sirve velas hasta 2026-05-26.

**Huecos**: en nombres líquidos (NVDA, SOXL, BTC) hay **cero** huecos intra-sesión en 5.000 barras
de 1m. En ilíquidos el minuto sin operación simplemente no existe: LINC 842 huecos, ZSPC 250,
USB30Y/USD 2.825. No es corrupción, es ausencia de print — pero **un consumidor que asuma rejilla
continua se desalinea**.

### 4.2 Datasets de SERIES

Todos devuelven exactamente 3 columnas: **`date`, `symbol`, `value`**. Una observación por día.

| dataset | símbolos | muestra | filas | rango servido | nota |
|---|---:|---|---:|---|---|
| economics | 14.795 | chlinfind | 5.000 (tope) | 1999-02-21 → 2026-08-09 | serie más antigua vista: `mdvtemp` desde **1901-01-01** |
| bonds | 202 | UK5Y | 5.000 (tope) | 1990-01-01 → 2026-07-24 | 31 países |
| sovereign_yields | 88 | IT2YT=RR | 4.226 | 2010-01-04 → 2026-08-03 | |
| corporate_bonds | 192 | ES006083706= | 1.717 | 2020-01-01 → 2026-07-31 | `INIBULPP=` dice 10.149 ticks y **devuelve 1 fila** |
| credit_indices | 79 | .IBBEU003D | 4.278 | 2010-01-04 → 2026-07-31 | |
| fx_derivatives | 63 | SEKSW= | 3.018 | 2015-01-01 → 2026-07-31 | vol ATM y risk-reversals FX |
| bond_futures | 2 | JGBc1 | 4.057 | 2010-01-04 → 2026-08-03 | solo JGB |

⚠ `series()` **sin `dataset=`** resuelve por catálogo y funciona (`series("fdtr")`, `series("US10Y")`),
pero con un ticker de acción da `404 'SPY' is not a series symbol`.

### 4.3 Frescura por dataset (último dato servido, viernes 2026-08-07)

- Velas US (stocks/etf/index): **2026-08-07 23:59 UTC** = 19:59 ET → cubre **pre y post-market completos (04:00–20:00 ET)**.
- Cripto/FX/commodity: hasta **2026-08-08 19:06 UTC** (durante mi propio barrido).
- Series macro/bonos: **2026-07-24 … 2026-08-03** según dataset → **de 5 a 15 días de retraso**.
  `bond_yields(DE10Y)` acaba en **2026-07-01**: 5 semanas rancio.
- `futures/FGBL`: acaba **2026-07-03** (contrato rolado, no es un fallo de la API).

---

## 5. Verificación de la profundidad: ¿las velas de 2010 son reales?

Prueba: bajar el 1m de un día y comprobar que **reconstruye** la vela 1d del mismo día
(`p2_deep_history`). Si el 1m fuese relleno sintético, no cuadraría.

| símbolo | día | barras 1m | O/C/H/L 1d vs 1m | volumen 1d ÷ Σ1m |
|---|---|---:|---|---:|
| NVDA | 2010-05-06 | 390 | O✓ C 0,35/0,355 H 0,37/0,3675 L 0,32/0,326 | **1,0168** |
| NVDA | 2015-08-24 | 419 | **idénticos** | **1,0000** |
| NVDA | 2020-03-16 | 880 | **idénticos** | **1,0000** |
| NVDA | 2026-08-07 | 960 | **idénticos** | **1,0000** |
| SPY | 2010-05-06 | 390 | **idénticos** (L = 105,00 el día del flash crash) | **1,0000** |
| SPY | 2026-08-07 | 925 | **idénticos** | **1,0000** |

**Veredicto: el 1m histórico es real**, no interpolado. Cinco de seis días cuadran al céntimo y al
tick de volumen. El único desajuste (NVDA 2010-05-06) tiene la 1d **más ancha** que la envolvente
1m y un 1,68 % más de volumen → hay prints fuera de la rejilla 1m ese día. Es el día del flash
crash y de NVDA; no se generaliza sin más muestra.

**Dos consecuencias operativas:**

1. **Precios y volúmenes vienen AJUSTADOS por splits hacia atrás.** NVDA cotiza 0,36 en 2010 y 0,53
   en 2015 en este archivo (los 40× de los splits 4:1 de 2021 y 10:1 de 2024 ya están aplicados), y
   el volumen de 2010 sale 965 M (también multiplicado). Para backtests de precio va bien;
   **para cualquier cálculo en dólares del pasado hay que deshacer el ajuste**.
2. **La cobertura de horario extendido crece con los años**: 2010-05-06 = 390 barras (solo RTH,
   13:30–19:59 UTC); 2015-08-24 = 419; 2020-03-16 = 880; 2026-08-07 = 960 (08:00–23:59 UTC).
   **Un backtest de premarket antes de ~2015 no tiene datos que mirar.**

---

## 6. Endpoints de referencia (2 ejemplos cada uno)

| endpoint | ejemplo | filas | ms | rango servido |
|---|---|---:|---:|---|
| `economic_calendar` | `region="US", start=2026-01-01` | 3.726 | 1.011 | 2026-01-02 → **2026-11-06** (futuro) |
| | `region=["EU","GB"], released_only=True, desc` | 500 | 388 | 2025-12-19 → 2026-08-07 |
| `insider_trades` | `"NVDA"` | 500 | 549 | tabla: 11,17 M filas, 2003-12-23 → 2026-08-07 |
| | `type="P-Purchase", start=2026-01-01` | 500 | 507 | |
| `dividends` | `"AAPL"` | **92** | 320 | tabla: 918.886 filas, 1970-01-26 → **2027-04-08** |
| | `start=2026-01-01` | 500 | 532 | |
| `splits` | `"NVDA"` | **6** | 294 | tabla: 46.010 filas → 2026-09-29 |
| | `start=2020-01-01` | 500 | 588 | |
| `series` | `"fdtr"` (Fed funds) | **867** | 350 | **1971-08-04** → 2026-06-17 |
| | `"US10Y"` | 5.000 (tope) | 527 | 1990-01-08 → 2009-08-25 ⚠ |
| `cot` | `order="desc", limit=50` | 50 | 613 | última semana: **2026-08-04** |
| | `"PA"` (paladio) | 605 | 455 | 2015-01-06 → 2026-08-04 |
| `financial_reports` | `"NVDA", report_type="income"` | **19** | 346 | 2018-01-28 → 2026-04-26 |
| | `"AAPL", "balance", period="FY"` | **8** | 322 | 2018-09-29 → 2025-09-27 |
| `company_profiles` | `"NVDA"` | 1 | 312 | tabla completa: **8.304** |
| | `limit=5000` | 5.000 (tope) | 728 | 4,58 MB |
| `fundamentals` | `"NVDA"` | 1 | 550 | tabla completa: **8.304** |
| | `limit=5000` | 5.000 (tope) | 676 | 3,21 MB |
| `bond_yields` | `"US10Y"` | 5.000 (tope) | 495 | 1990-01-08 → 2009-08-25 ⚠ |
| | `"DE10Y", start=2020-01-01` | 1.679 | 434 | 2020-01-02 → **2026-07-01** (rancio) |
| `catalog` | `catalog()` | 22.851 | 1.344 (1ª) / **2,6 (caché)** | 9,5 MB la primera vez |
| | `catalog("crypto")` | 58 | 2,6 | filtro local |
| `options_underlyings` | `()` | **3.186** | 9,1 | filtro local, 0 bytes |

⚠ **Trampa de orden**: `bond_yields` y `series` traen `order="asc"` por defecto, así que con el tope
de 5.000 filas **`US10Y` devuelve 1990–2009 y parece que no hay datos modernos**. Hay que pedir
`order="desc"` o acotar con `start=`.

`/vault/reference` (tamaño real de cada tabla):

| tabla | filas | primero | último |
|---|---:|---|---|
| options_flow_1m | **189.219.740** | 2026-01-02 14:30 | 2026-07-31 20:15 |
| options_flow | **113.156.019** | 2026-06-26 13:30 | 2026-08-07 20:15 |
| insider_trades | 11.170.947 | 2003-12-23 | 2026-08-07 |
| options_chain | 1.122.305 | 2026-06-11 14:53 | 2026-08-07 20:15 |
| dividends | 918.886 | 1970-01-26 | 2027-04-08 |
| bond_yields | 708.808 | 1990-01-01 | 2026-07-24 |
| financial_reports | 204.467 | 2013-04-30 | 2026-07-05 |
| economic_calendar | 137.187 | 2015-01-01 | 2026-11-06 |
| stock_splits | 46.010 | 1970-01-01 | 2026-09-29 |
| cot | 34.006 | 2015-01-06 | 2026-08-04 |
| stock_fundamentals / company_profiles | 8.304 c/u | — | — |

---

## 7. Opciones — lo que da y lo que NO da

### 7.1 `options()` — la cadena. **18 campos, sin OI y sin bid/ask**

```
contract_type, delta, dte, expiry, gamma, iv, last_price, last_trade_at, premium_today,
rho, strike, theta, ticker, underlying, underlying_price, updated_at, vega, volume_today
```

Unión de claves sobre 3 llamadas (SPY completa, SPY dte 0-9, NVDA dte 0-9):
**`has_open_interest = False`, `has_bid = False`, `has_ask = False` en las tres.**

→ **No se pueden construir muros de OI ni el gate de spread ≤5 % con LSE.** Eso sigue siendo IBKR.

**No es una cadena viva, es un REGISTRO DE ÚLTIMO PRINT por contrato**: cada fila lleva el precio,
las griegas y el `underlying_price` **del momento de su último trade**. En una sola llamada de
`expiry=2026-08-21` el `underlying_price` va de **729,36 a 776,29**: cada fila mira a un instante
distinto. **Leer el spot de la cadena es leer un promedio de fechas.**

**Y el `dte` está congelado**: es el DTE del momento de la última actualización, no el de hoy.
Por eso `min_dte`/`max_dte` **no seleccionan los vencimientos actuales**:

| llamada | filas | vencimientos servidos | `updated_at` máx |
|---|---:|---|---|
| `options("SPY")` | 5.000 (**tope**) | 2026-07-02 … 2026-07-28 | 2026-07-27 |
| `options("SPY", min_dte=0, max_dte=9)` | 5.000 (**tope**) | 2026-07-02 … 2026-07-29 | 2026-07-28 |
| `options("SPY", expiry="2026-08-14")` | **327** | 2026-08-14 | **2026-08-07 20:15:02** ✅ |
| `options("SPY", expiry="2026-08-21")` | **467** | 2026-08-21 | **2026-08-07 20:15:02** ✅ |
| `options("NVDA", min_dte=0, max_dte=9)` | 1.999 | hasta 2026-08-14 | **2026-08-07 20:00** ✅ |

**Receta obligatoria**: SPY tiene más de 5.000 contratos y la cadena sale ordenada desde el
vencimiento **más viejo** (incluye ya expirados), así que sin filtro te llevas 5.000 filas muertas.
**Hay que iterar `expiry=` uno a uno.** NVDA cabe entera (1.999 filas) y por eso sí se ve fresca.

Griegas presentes en el **92 %** de las filas (SPY 4.577/5.000; NVDA 1.920/1.999); las que faltan
son contratos profundamente ITM/OTM con `iv` nulo.

### 7.2 `options_flow()` — la cinta de prints. **Lo mejor que tiene LSE**

18 campos: `id, ts, underlying, ticker, strike, expiry, contract_type, last_price, volume,
premium, underlying_price, dte, iv, delta, gamma, theta, vega, rho`. `ts` al **microsegundo**.

- **Profundidad real: 6 semanas**, no "la semana corrida" que dice el docstring
  (`client.py:832`). Print más viejo de SPY: **2026-06-26 13:30:03,283291**.
- **Densidad medida** (ventana de 1 minuto, 2026-08-07 19:00–19:01): **SPY 346 prints/min**,
  **NVDA 285 prints/min**. Con el tope de 5.000 filas → **una llamada ≈ 14 min de cinta de SPY**;
  una sesión completa de SPY ≈ **29 llamadas**.
- **Barrido global sin `underlying`**: `min_premium=250.000` → 5.000 prints en 1,02 días sobre
  **248 subyacentes** (1,92 s). Con `type="put", max_dte=7`: 1.000 prints, **87 subyacentes**.
  Esto sí es un detector de ballenas de mercado entero en una sola llamada.
- Horario servido: **13:30–20:15 UTC** = 09:30–16:15 ET (RTH + prints de liquidación).
- **Sigue sin haber lado agresor** (no hay `bid`/`ask` en el print) → no da delta firmado.

### 7.3 `option_candles()` — 1m por contrato CON griegas

21 campos: OHLC de la prima + `volume`, `premium`, **`print_count`**, `iv_avg`, `delta_avg`,
`gamma_avg`, `theta_avg`, `vega_avg`, `rho_avg`, `underlying_price`, `dte`.
Archivo: **189,2 M filas desde 2026-01-02**; la última semana se pliega en vivo desde `options_flow`.

Medido: `QQQ260810P00722000` → 682 barras (2026-08-04 → 08-07);
`NVDA260821C00242500` → 152 barras; `SPY260925P00780000` → 7 barras (contrato lejano, apenas opera).

**🔴 ROTO: el parámetro `timeframe` se ignora.** `/meta` anuncia
`options_timeframes: [1m,3m,5m,15m,30m,1h,4h,1d,1w,1mo]`, pero el endpoint crudo
`/options/candles?ticker=…&timeframe=1d` y `…&timeframe=1h` devuelven **exactamente las mismas
filas de 1 minuto** que `timeframe=1m` (misma fila `minute: 2026-08-04 13:43:00`, mismo OHLC).
El SDK ni siquiera expone el parámetro (`client.py:874`). **Solo hay 1m; agregar es cosa tuya.**

### 7.4 Nombres ilíquidos: el vacío es MUDO

`NRIM` (53 ticks en catálogo): `options("NRIM")` → **HTTP 200, `[]`, 2 bytes**.
`options("ZZZZNOPE")` (símbolo inexistente) → **HTTP 200, `[]`, 2 bytes**.

**Un símbolo que no existe y uno sin operar son indistinguibles.** Fail-loud obliga a validar
contra el catálogo ANTES de interpretar una lista vacía como "hoy no hubo flujo".

---

## 8. Export a Parquet — el único camino por encima de 5.000 filas

`history()` / `dataset()` lanzan un job async, hacen polling y descargan con reanudación
(`vault.py:102/141`). **5 exports/hora.** Medido de punta a punta:

| export | filas | tamaño | tiempo total | columnas |
|---|---:|---:|---:|---|
| `history("NVDA", timeframe="1d")` | **5.789** | 161 KB | **3,75 s** | ts, symbol, open, high, low, close, volume |
| `history("NVDA", timeframe="1m", 1 día)` | 960 | 25 KB | 1,37 s | idem |
| `history("NVDA", dataset="options", timeframe="1m", 1 día)` | **75.892** | 834 KB | **3,75 s** | ts, underlying, expiry, opt_type, strike, **osi**, open, high, low, close, volume |

- **Rompe el tope de 5.000**: el 1d completo de NVDA son 5.789 filas, **2003-09-10 → 2026-08-07**.
- **Un solo día de opciones de NVDA = 75.892 filas, 2.235 contratos, 24 vencimientos** (0,8 MB).
- **🔴 El export de opciones PIERDE las griegas.** El JSON de `/options/candles` trae
  `iv_avg/delta_avg/gamma_avg/theta_avg/vega_avg/rho_avg/premium/print_count`; el Parquet del
  export trae **solo OHLCV**. Para griegas históricas hay que ir por el endpoint JSON contrato a
  contrato (5.000 filas/llamada), no por el export.
- **El OSI cambia de formato**: el export escribe `O:NVDA260807C00080000` (prefijo `O:`, estilo
  Polygon); el JSON devuelve `NVDA260807C00080000` (sin prefijo). Normalizar al cruzar.
- `dataframe=True` (por defecto) **levanta `LSEError`** si no hay pyarrow: `venv-lse` NO lo tiene,
  el `venv` principal SÍ (pyarrow 21.0.0, pandas 2.3.3, ambos py3.9). El fichero se guarda igual.
  Por eso el probe se corre con `./venv/bin/python` y `dataframe=False`.

---

## 9. Errores y endpoints rotos (documentados)

| sonda | resultado | mensaje exacto |
|---|---|---|
| `candles(SPY,"2m")` | **400** | `invalid timeframe '2m'; valid: 1s, 5s, 15s, 30s, 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo` |
| `candles("ZZZZNOPE","1d")` | **404** | `'ZZZZNOPE' has no candle data; browse /catalog` |
| `candles(SPY,"1d",limit=99999)` | **200** | devuelve 5.000 **sin avisar** del truncado |
| `series("SPY")` | **404** | `'SPY' is not a series symbol; browse /catalog` |
| `series(<símbolo de velas>)` | **400** | `not a series dataset; valid: [7 clases]` (11/11) |
| `candles(<símbolo de series>)` | **404** | `'<sym>' has no candle data` (14/14) |
| `option_candles("NO-ES-OSI")` | **400** (cliente) | `'NO-ES-OSI' is not an option contract; pass an OSI ticker like AAPL260612C00205000…` |
| `option_candles(..., timeframe=1d\|1h)` | **200 ENGAÑOSO** | ignora el timeframe, devuelve 1m |
| `options("ZZZZNOPE")` | **200 `[]`** | sin error para símbolo inexistente |
| 4 peticiones en paralelo | **2×429** | `too many concurrent requests for this key; retry shortly` |
| `get("tabla_muerta")` | **400** (cliente) | `'tabla_muerta' is not served any more; the REST API reads the vault now…` |
| `get("x_options_chain", underlying="eq.SPY")` | **200** | la pasarela legacy **sí** funciona (5 filas) |
| urllib con User-Agent por defecto | **403 CF 1010** | ya cazado por el orquestador: **hay que mandar User-Agent** |

**Vacíos legítimos que no son fallo**: `INIBULPP=` declara 10.149 ticks y `series()` devuelve **1
fila**; `FMEF` (futuro MSCI EM) declara 1 tick y devuelve **1 barra** en los 4 timeframes.

---

## 10. Latencia por endpoint (sábado, desde Toronto)

389 llamadas. Global: **p50 558 ms · p90 966 ms · p99 2.042 ms · máx 3.066 ms**.

| endpoint | n | fallos | p50 ms | p90 ms | máx ms | bytes mediana |
|---|---:|---:|---:|---:|---:|---:|
| `candles` | 264 | 32 | 571,8 | 947,0 | 2.284 | 160 |
| `series` | 70 | 27 | 494,6 | 720,5 | 811 | 195 |
| `options_flow` | 9 | 0 | 721,5 | 1.770,1 | 1.923 | 376.490 |
| `options` (cadena) | 8 | 0 | 711,5 | 1.122,8 | **3.066** | 2.078.229 |
| `option_candles` | 4 | 1 | 1.628,9 | — | 1.979 | 71.102 |
| `/vault/usage` | 5 | 0 | 376,6 | 438,9 | 469 | 261 |
| `catalog` (caché) | 3 | 0 | **2,6** | — | 1.344 | 0 |
| referencia (todos) | 18 | 0 | ~430–730 | — | 1.011 | varía |

Los "fallos" de `candles`/`series` son las sondas de cruce y de símbolo ausente: **eran el
experimento**, no una avería.

**Nada de esto sirve para camino de señal**: medio segundo por llamada, tope de 2 concurrentes.
Es un almacén, no un feed.

---

## 11. Cobertura de los símbolos de esta casa

### Flota (`data/fleet.txt`) — **25 de 30 presentes**

**AUSENTES, con 404 verificado** (`'X' has no candle data; browse /catalog`):
**TSM · XLK · EWY · DRAM · SKHY**. TSM duele (ADR grande y líder de semis); DRAM/SKHY/EWY son
ETF temáticos y KOR; XLK es sectorial.

Presentes con acciones + opciones: QQQ SPY NVDA TSLA MU SMH AMD AAPL MSFT META AMZN GOOGL INTC TXN
QCOM AVGO NFLX GLD SPCX LRCX SNDK WDC STX (+ NOK y ASML **solo acciones, sin cadena de opciones**).
Ojo: QQQ/SPY/SMH/GLD/DIA/IWM viven en el dataset `etf`, no en `stocks`.

### Índices y volatilidad — **NO están como símbolo**

`SPX`, `XSP`, `NDX`, `VIX` → **404** los cuatro. Equivalentes disponibles (contrato CFD, no el
índice oficial): `SPX500/USD`, `NAS100/USD`, `US30/USD`, `US2000/USD`, `SOX/USD`, `NASCOMP/USD`,
y `VIX/USD` en el dataset `volatility` (**solo desde 2026-07-01**). `SOX/USD` y `NASCOMP/USD`
están **congelados desde 2026-06-30**.

### 🇰🇷 Corea — candidato real a sustituir el puente de Naver

| símbolo | 1m desde | último 1m | horario servido (UTC) | huecos intra-sesión |
|---|---|---|---|---|
| `005930.KS` Samsung | **2022-11-11** | 2026-08-07 06:29 | 00:00–06:29 = 09:00–15:29 KST | **1** en 4.999 pasos |
| `000660.KS` SK hynix | **2022-11-11** | 2026-08-07 06:29 | idem | **1** |

Verificado que **no son el mismo dato duplicado**: últimos 5 cierres Samsung
`231500, 231000, 231000, 230500, 231000` vs SK hynix `1419000, 1418000, 1419000, 1418000, 1417000`
(KRW). Sesión KRX completa, sin huecos. **No hay contraste externo de precio contra KRX en esta
medición** — antes de jubilar el puente de Naver, cruzar un día contra la fuente actual.

En total el catálogo trae 18 símbolos `.KS`, 123 `.L`, 42 `.T`, 30 `.HK`, 20 `.NS`, 19 `.AX`, 15 `.TW`.

---

## 12. Cómo reproducir

```bash
set -a; . /Users/yuniorrodriguezosorio/ib-trader/config/feeds.env; set +a
cd /Users/yuniorrodriguezosorio/ib-trader
./venv/bin/python scripts/research/lse_probe.py            # fase 1: barrido (350 llamadas, ~112 MB)
./venv/bin/python scripts/research/lse_probe.py --phase2    # verificación + export (39 llamadas, ~11 MB)
./venv/bin/python scripts/research/lse_probe.py --phase2b   # cadena por expiry + Corea
```

Se usa `./venv/bin/python` (no `venv-lse`) porque necesita **pyarrow** para contar las filas del
Parquet; el script añade `venv-lse/lib/python3.9/site-packages` al `sys.path` para importar `lse`.
Salida cruda: `data/research/lse_probe.json`. Parquets: `data/research/lse_export/`.
