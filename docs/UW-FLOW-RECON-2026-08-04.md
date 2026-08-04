# UW-FLOW-RECON — reconocimiento MEDIDO de la API de Unusual Whales

**Fecha del sondeo**: 2026-08-04 06:19–06:35 UTC (02:19 ET, **mercado CERRADO**, última sesión
2026-08-03).
**Herramienta**: `scripts/uw_endpoint_probe.py` (nueva, reutilizable) + `tests/test_uw_endpoint_probe.py` (13 tests).
**Credencial**: `UW_TOKEN` leído con `uw_premium.token()`. **No aparece en este documento ni en
ningún log.**
**Cuota**: cabeceras `x-uw-daily-req-count` **437 → 566** en toda la campaña ≈ **129 peticiones**,
contra `x-uw-token-req-limit` **30000**. `x-uw-req-per-minute-remaining` = 1000000 (sin límite por
minuto real). Coste del recon: **0,43 % del cupo**.

**SEÑAL-SOLAMENTE.** Nada de lo aquí descrito ordena al broker. Nada de aquí dispara: la doctrina
(`docs/LATENCIA-FUENTES.md`) reserva el disparo a IBKR en tiempo real.

---

## 0. Resumen ejecutivo

1. **El plan da acceso a TODO.** 64 de 69 rutas sondeadas devuelven **200**. Los 5 fallos son rutas
   inexistentes o mal parametrizadas por mí, **no restricciones de plan** (detalle en §2).
2. **El websocket ABRE y se cae en 0,09 s.** `/api/socket` responde **HTTP 101 Switching
   Protocols** con token válido (**401 sin token**), y acto seguido el servidor cierra el TCP
   **sin close-frame y sin enviar un solo byte**, con cualquier formato de `join` e incluso sin
   enviar nada. Veredicto en §5.
3. **`greek-flow` NO es una fuente nueva**: su `dir_delta_flow` es **byte-idéntico** a
   `net_prem_ticks.net_delta` en **406/406 minutos** medidos (§6.1). ρ = 1,0. La casa ya la
   consume desde `uw_premium.py`.
4. **3 alertas defendibles** (§7), **7 ideas propias muertas** (§8) — incluida la que más
   ilusión hacía.

---

## 1. Inventario: lo que la casa YA usa vs lo NUEVO

### Ya cableado (no duplicar)

| Endpoint | Consumidor | fichero:línea |
|---|---|---|
| `/api/stock/{sym}/flow-alerts` | cinta de ballenas, 8 syms, 90 s | `scripts/uw_flow_tape.py:43` |
| `/api/stock/{sym}/net-prem-ticks` | premium neto firmado | `scripts/uw_premium.py:39`, `scripts/uw_net_prem.py:88` |
| `/api/darkpool/{sym}` | widget descriptivo, cero señal | `scripts/uw_darkpool.py:54` |
| `/api/stock/{sym}/greek-exposure/expiry` | GEX por vencimiento (tapa el hueco 08-24…08-31) | `scripts/uw_gex_expiry.py:53` |
| `/api/stock/{sym}/greek-exposure/strike` | árbitro contra nuestro mapa | `scripts/uw_gex_compare.py:170` |
| `/api/stock/{sym}/oi-change` | ¿abría o cerraba? V vs ΔOI | `scripts/uw_oi_delta.py` |
| 11 por símbolo + 3 globales | archivador del trial | `scripts/uw_archive.py:88-103` |
| widgets del cockpit | 3 tarjetas | `charts/uw_widgets.js:170,232,275` |
| sonda de latencia | net-prem-ticks + darkpool + gex/expiry, **solo en sesión** | `scripts/uw_latency_probe.py` |

`scripts/uw_archive.py:88-103` ya archiva 14 rutas. **El recon las respeta y no las reimplementa.**

### NUEVO y con dato utilizable (no lo toca nadie hoy)

| Endpoint | Qué aporta que NO tenemos |
|---|---|
| `/api/option-trades/flow-alerts` | la cinta de ballenas **GLOBAL** (todos los tickers, incl. SPXW/índices) en 1 petición, con `alert_rule` |
| `/api/stock/{sym}/flow-per-strike` | premium del **día por strike**, partido ask-side / bid-side → el muro que se está construyendo HOY |
| `/api/stock/{sym}/flow-per-expiry` | lo mismo por vencimiento (35 filas) |
| `/api/stock/{sym}/flow-recent` | la cinta **cruda** trade a trade con griegas y `tags` (`ask_side`/`bullish`/`sweep`) |
| `/api/stock/{sym}/spot-exposures` | γ/vanna/charm de dealer **por minuto** al spot vivo, con columnas `_oi`, `_vol` y `_dir` |
| `/api/stock/{sym}/option/stock-price-levels` | volumen de opciones **por nivel de precio del subyacente** (5.900 filas) |
| `/api/market/market-tide` | premium neto **de todo el mercado**, cubos de 5 min |
| `/api/market/{ETF}/etf-tide` | lo mismo por ETF sectorial (`XLK` sí; nombre de sector NO, ver §6.2) |
| `/api/market/total-options-volume` | put/call de mercado del día (volumen y premium) |
| `/api/screener/stocks` | 60+ métricas por ticker EOD (`iv_rank`, `bullish/bearish_premium`, `variance_risk_premium`, `cum_dir_vega`) |
| `/api/screener/option-contracts` | contratos rankeados con `ask_side_perc_7_day`, `days_of_oi_increases` |
| `/api/option-trades/full-tape/{date}` | **la cinta ENTERA del día** — ver la trampa de §6.3 |
| `/api/stock/{sym}/volatility/*`, `iv-rank`, `interpolated-iv` | IV/RV con 250 días de historia |
| `/api/shorts/{sym}/data` | `fee_rate` y `short_shares_available` con sello intradía |
| `/api/news/headlines` | titulares con `sentiment`, **vivos 24 h** (medido: 82 s de antigüedad a las 06:17 UTC) |

---

## 2. Tabla maestra: endpoint × status × cadencia × sello más nuevo

Sondeo con `--sym SPY`, 1 petición por ruta, 2026-08-04 06:19 UTC.
Columna «edad» = distancia del sello más nuevo a la hora del sondeo. **El cierre de la sesión
2026-08-03 fue a las 20:00 UTC**, o sea 6 h 19 min antes del sondeo: por eso *todo lo intradía
marca ~6-10 h y eso NO significa que llegue tarde en vivo* (§4).

| # | Endpoint | HTTP | filas | cadencia | sello más nuevo | edad |
|---|---|---|---|---|---|---|
| 1 | `/api/option-trades/flow-alerts` | **200** | 5 (pag. `newer_than`/`older_than`) | evento | `2026-08-03T20:55:32Z` | 9,4 h |
| 2 | `/api/stock/SPY/flow-alerts` | **200** | 200 con `limit` | evento | `2026-08-03T20:13:07Z` | 10,1 h |
| 3 | `/api/option-trades/full-tape/2026-08-03` | **200** | **ZIP 1,54 GB** | diaria | — | 38,2 s de descarga |
| 4 | `/api/stock/SPY/flow-per-strike` | **200** | 440 | día×strike | `2026-08-03T20:15:00Z` | 10,1 h |
| 5 | `/api/stock/SPY/flow-per-expiry` | **200** | 35 | día×expiry | `2026-08-03` | 1 d |
| 6 | `/api/stock/SPY/flow-recent` | **200** | 50 con `limit` | trade a trade | `2026-08-03T20:15:00.000257Z` | 10,1 h |
| 7 | `/api/stock/SPY/option-contracts` | **200** | 5 | EOD | — | — |
| 8 | `/api/stock/SPY/net-prem-ticks` | **200** | **406** | **1 min** 13:30→20:15 UTC | `20:15:00Z` | 10,1 h |
| 9 | `/api/stock/SPY/option/stock-price-levels` | **200** | 5.900 | día | — | — |
| 10 | `/api/stock/SPY/oi-per-strike` | **200** | 489 | EOD | `2026-08-03` | 1 d |
| 11 | `/api/stock/SPY/oi-per-expiry` | **200** | 34 | EOD | `2026-08-03` | 1 d |
| 12 | `/api/stock/SPY/oi-change` | **200** | 50 | **día sobre día** | `curr_date 08-03` vs `last_date 07-31` | 1 d |
| 13 | `/api/stock/SPY/stock-state` | **200** | 1 | tick | `2026-08-03T23:59:42Z` (`market_time: postmarket`) | 6,3 h |
| 14 | `/api/stock/SPY/stock-volume-price-levels` | **200** | 33.448 | día | — | — |
| 15 | `/api/stock/SPY/atm-chains?expirations[]=` | **200** | 2 | EOD | `2026-08-03T21:44:48Z` | 8,6 h |
| 16 | `/api/stock/SPY/greek-exposure` | **200** | **250** | **1 año diario** | `2026-08-03` | 1 d |
| 17 | `/api/stock/SPY/greek-exposure/strike` | **200** | 489 | EOD | `2026-08-03` | 1 d |
| 18 | `/api/stock/SPY/greek-exposure/expiry` | **200** | 35 | EOD | `2026-08-03` | 1 d |
| 19 | `/api/stock/SPY/greek-exposure/strike-expiry?expiry=` | **200** | 163 | EOD | `2026-08-03` | 1 d |
| 20 | `/api/stock/SPY/greek-flow` | **200** | 406 | 1 min | `20:15:00Z` | 10,1 h |
| 21 | `/api/stock/SPY/spot-exposures` | **200** | **530** | **~1 min**, 10:30→20:00 UTC (**incluye premarket**) | `2026-08-03T20:00:48Z` | 10,3 h |
| 22 | `/api/stock/SPY/spot-exposures/strike` | **200** | 50 | snapshot | `2026-08-03T20:14:48Z` | 10,1 h |
| 23 | `/api/stock/SPY/spot-exposures/expiry-strike/{expiry}` | **404** | — | — | — | ruta inexistente |
| 24 | `/api/stock/SPY/max-pain` | **200** | 34 | EOD | `2026-08-03` | 1 d |
| 25 | `/api/stock/SPY/interpolated-iv` | **200** | 9 | EOD | `2026-08-03` | 1 d |
| 26 | `/api/stock/SPY/volatility/term-structure` | **200** | 35 | EOD | `2026-08-03` | 1 d |
| 27 | `/api/stock/SPY/volatility/realized` | **200** | 251 | 1 año diario | `2026-08-03` | 1 d |
| 28 | `/api/stock/SPY/volatility/stats` | **200** | 1 | EOD | `2026-08-03` | 1 d |
| 29 | `/api/stock/SPY/iv-rank` | **200** | 5 | EOD | `2026-08-03T22:35:24Z` | 7,7 h |
| 30 | `/api/market/market-tide` | **200** | **78** | **5 min** 09:30→15:55 ET | `2026-08-03T15:55:00-04:00` | 10,4 h |
| 31 | `/api/market/oi-change` | **200** | 100 | día sobre día | `curr_date 08-03` | 1 d |
| 32 | `/api/market/sector-etfs` | **200** | 12 | EOD | — | 1 d |
| 33 | `/api/market/{ETF}/etf-tide` | **200** | **390** | **1 min** | `2026-08-03T15:59:00-04:00` | 10,3 h |
| 34 | `/api/market/correlations` | **400** sin params / **200** con `?tickers=SPY,QQQ&interval=1m` | 2 | ventana móvil | `max_date 2026-08-03` | 1 d |
| 35 | `/api/market/economic-calendar` | **200** | 34 | futuro | `2026-08-14T14:00:00Z` | −10,3 d |
| 36 | `/api/market/fda-calendar` | **200** | 100 | evento | `2022-10-10` | 3,8 a |
| 37 | `/api/market/spike` y `/api/market/spike/SPY` | **404** | — | — | — | `{"error":"Route not found"}` |
| 38 | `/api/market/total-options-volume` | **200** | 1 | EOD | `2026-08-03` | 1 d |
| 39 | `/api/market/sector-tide` | **404** | — | — | — | no existe (usar `{ETF}/etf-tide`) |
| 40 | `/api/market/top-net-impact` | **200** | 20 | EOD | — | 1 d |
| 41 | `/api/market/insider-buy-sells` | **200** | 500 | diaria | `filing_date 2026-08-03` | 1 d |
| 42 | `/api/darkpool/recent` | **200** | 5 con `limit` | evento | `2026-08-03T23:59:59Z` | 6,3 h |
| 43 | `/api/darkpool/SPY` | **200** | 5 con `limit` | evento | `2026-08-03T23:59:42Z` | 6,3 h |
| 44 | `/api/screener/option-contracts` | **200** | 5 con `limit` | EOD | — | 1 d |
| 45 | `/api/screener/stocks` | **200** | 5 con `limit` | EOD | `2026-08-03` | 1 d |
| 46 | `/api/screener/analysts` | **200** | 5 | evento | `2026-08-03T21:42:29Z` | 8,6 h |
| 47 | `/api/etfs/SPY/exposure` | **200** | 23 | EOD | — | — |
| 48 | `/api/etfs/SPY/holdings` | **200** | 250 | EOD | — | — |
| 49 | `/api/etfs/SPY/in-outflow` | **200** | 749 | diaria | `2026-07-31` | 4 d |
| 50 | `/api/etfs/SPY/info`, `/weights` | **200** | 1 / 1 | EOD | — | — |
| 51 | `/api/earnings/afterhours` | **200** | 50 | diaria | `report_date 2026-08-03` | 1 d |
| 52 | `/api/earnings/premarket` | **200** | 25 | diaria | — | 1 d |
| 53 | `/api/earnings/SPY` | **200** | **`{"data":[]}`** | — | — | SPY no reporta: vacío HONESTO |
| 54 | `/api/insider/transactions` | **200** | 5 con `limit` | filing | `filing_date 2026-08-03` | 1 d |
| 55 | `/api/insider/SPY/ticker-flow` | **200** | `{"data":[]}` | — | — | vacío |
| 56 | `/api/congress/recent-trades` | **200** | 5 | filing | `transaction_date 07-31`, `filed_at 08-01` | días |
| 57 | `/api/congress/late-reports`, `/congress-trader` | **200** | 5 / 5 | filing | — | días |
| 58 | `/api/institutions` | **200** | 5 | trimestral | `2026-03-31` | 126 d |
| 59 | `/api/shorts/SPY/data` | **200** | 1.000 | intradía | `2026-08-03T15:20:41Z` | 15,0 h |
| 60 | `/api/shorts/SPY/ftds` | **200** | 943 | quincenal | `2026-07-14` | 21 d |
| 61 | `/api/news/headlines` | **200** | 5 con `limit` | **evento, 24 h** | `2026-08-04T06:17:55Z` | **82 s** |
| 62 | `/api/alerts` | **200** | `{"data":[]}` | — | — | no hay alertas configuradas |
| 63 | `/api/alerts/configuration` | **200** | 1 | — | `2026-08-02T23:55:38Z` | única regla: `Chat Mentioned` |
| 64 | `/api/socket` (GET normal) | **200** | `{"data":[]}` | — | — | **no anuncia canales** |
| 65 | `/api/docs` | **404** | — | — | — | no existe |

**Los 5 no-200 son míos, no del plan**: 2 rutas inventadas (`spot-exposures/expiry-strike`,
`market/spike`), 1 renombrada por UW (`sector-tide` → `{ETF}/etf-tide`), 1 que exige parámetros
(`correlations`, 400 → 200 con `?tickers=`) y `/api/docs`. **Cero 401. Cero 403.**

### Campos exactos de los que importan

`/api/option-trades/flow-alerts` — 37 campos por fila:
```
id · ticker · type(call|put) · strike · expiry · option_chain · created_at · start_time/end_time (epoch ms)
price · bid · ask · underlying_price · volume · open_interest · volume_oi_ratio · total_size · trade_count
total_premium · total_ask_side_prem · total_bid_side_prem   <-- el LADO se deriva de estos dos
iv_start · iv_end · has_sweep · has_floor · has_multileg · has_singleleg · all_opening_trades
alert_rule · rule_id · expiry_count · sector · marketcap · issue_type · er_time · next_earnings_date · missing_periscope
```
Todo lo numérico-monetario viaja como **`str`**, no como float. `alert_rule` medido en 200 alertas
de SPY: `RepeatedHits` 150 · `RepeatedHitsAscendingFill` 32 · `RepeatedHitsDescendingFill` 18.
**No hay campo `sentiment` ni `side`** (`uw_flow_tape.py` ya lo documenta).

`/api/stock/{sym}/net-prem-ticks` — 13 campos, **1 fila por minuto**:
```
date · tape_time · call_volume · put_volume · call_volume_ask_side · call_volume_bid_side
put_volume_ask_side · put_volume_bid_side · net_call_premium · net_put_premium
net_call_volume · net_put_volume · net_delta
```
> **GOTCHA de la casa, ya documentado en `uw_net_prem.py`**: `signed_premium = net_call_premium −
> net_put_premium`. Vender un put es alcista, por eso el put RESTA.

`/api/stock/{sym}/greek-flow` — 12 campos, 1 fila/minuto:
`timestamp · ticker · transactions · volume · dir_delta_flow · dir_vega_flow ·
otm_dir_delta_flow · otm_dir_vega_flow · otm_total_delta_flow · otm_total_vega_flow ·
total_delta_flow · total_vega_flow`. **Ver §6.1: `dir_delta_flow` ya lo tenemos.**

`/api/stock/{sym}/flow-per-strike` — 24 campos × 440 strikes:
`strike · timestamp · call_volume/put_volume · *_volume_ask_side · *_volume_bid_side ·
call_premium · call_premium_ask_side · call_premium_bid_side · (idem put) · call_trades/put_trades ·
*_otm_premium · *_otm_trades · *_otm_volume`.

`/api/stock/{sym}/spot-exposures` — 15 campos × ~530 minutos:
`time · start_time · ticker · ticker_id · price ·
{charm,gamma,vanna}_per_one_percent_move_{oi,vol,dir}`.

`/api/market/market-tide` — `timestamp · date · net_call_premium · net_put_premium · net_volume`,
78 cubos de **5 minutos** (09:30 → 15:55 ET, etiquetados por inicio).

`/api/stock/{sym}/oi-change` — 25 campos, incluye `days_of_oi_increases`,
`days_of_vol_greater_than_oi`, `oi_diff_plain`, `prev_multi_leg_volume`, `prev_ask_volume`,
`prev_bid_volume`, `percentage_of_total`, `rnk`.

`/api/screener/stocks` — 60+ campos EOD por ticker: `iv_rank`, `implied_move_perc`,
`bullish_premium`, `bearish_premium`, `net_call_premium`, `put_call_ratio`,
`variance_risk_premium`, `cum_dir_vega`, `avg_30_day_put_oi`, `week_52_high/low`…

---

## 3. Lo que SÍ se pudo medir con el mercado cerrado

| Hecho medido | Número |
|---|---|
| Latencia de RED de la API (mediana de 64 llamadas) | **~95 ms** (mín 69, máx 377 salvo `full-tape`) |
| Ninguna ruta intradía se queda corta respecto al cierre | `net-prem-ticks` llega a **20:15 UTC**, 15 min DESPUÉS del cierre de 20:00 |
| `market-tide` cubre la sesión entera | 78 cubos de 5 min, 09:30 → 15:55 ET (el último cubre 15:55-16:00) |
| `spot-exposures` empieza en **premarket** | primera fila 10:30 UTC = **06:30 ET** |
| `flow-alerts` global sigue vivo tras el cierre | alerta de `SPXW` a las **20:55 UTC (16:55 ET)** |
| `darkpool/recent` llega al final del extendido | `23:59:59Z` = 19:59:59 ET |
| `news/headlines` está vivo de madrugada | **82 s** de antigüedad a las 06:17 UTC |
| Cadencia real de `net-prem-ticks` y `greek-flow` | 406 filas = **1 por minuto**, sin huecos |
| Cadencia real de `spot-exposures` | 506 de 529 deltas = **60 s**; 16 de 120 s, 3 de 300 s → hay **huecos** |
| Ritmo de la cinta de alertas | **200 alertas de SPY en 3 h 50 min** = ~52/hora **de un solo símbolo** |

**Lo que esto demuestra**: el feed no se corta antes del cierre y no arrastra días de retraso.
**Lo que NO demuestra**: nada sobre la latencia INTRA-SESIÓN, que es la única que importa.

---

## 4. Latencia: lo NO medible hoy + procedimiento exacto para el martes

### Por qué hoy no se puede

Con el mercado cerrado, «edad del sello más nuevo» = «tiempo desde el cierre». Un endpoint con
retraso de 60 s y otro con retraso de 0 s dan **exactamente la misma lectura** a las 02:19 ET.
`scripts/uw_latency_probe.py` ya implementa esa disciplina y **se niega a correr fuera de sesión**
(`in_session()` → `return 1`, mensaje «FUERA DE SESION … probe NO ejecutado»). **Correcto: no
tocarlo para forzarlo.**

### Procedimiento para el martes 2026-08-05 en RTH

Lo que hay que hacer, en orden, con el mercado abierto:

**Paso 1 — arranque (09:50 ET, ya pasada la subasta).**
```bash
cd ~/ib-trader && ./venv/bin/python scripts/uw_latency_probe.py --all
```
Da `feed_age_s` de `net-prem-ticks` (SPY, QQQ) + darkpool + gex/expiry. Umbral ya codificado:
`REALTIME_BAR_S = 60`. Escribe a `data/uw_latency_probe.jsonl`.

**Paso 2 — barrido de los endpoints NUEVOS** (lo que la sonda actual no cubre). **Ya implementado**
en `uw_endpoint_probe.py --rth-latency`: 6 pasadas cada 5 min sobre los 9 endpoints con sello
intradía (`RTH_SET`), con `feed_age_s` y `cube_lag` por pasada y mediana por endpoint al final.
Un solo comando:
```bash
./venv/bin/python scripts/uw_endpoint_probe.py --rth-latency --sym SPY \
    --minutes 30 --every 300 --out data/uw_rth_probe.json
```
**6 muestras × 9 endpoints = 54 peticiones** (0,18 % del cupo). **Se niega a correr fuera de RTH**
(verificado hoy: sale por stderr «FUERA DE RTH … Sondeo NO ejecutado», exit 1) — misma disciplina
que `uw_latency_probe.py`, para que nadie traiga de madrugada un número que no significa nada.
Los EOD están deliberadamente **excluidos** de `RTH_SET`: su edad se mide en días y falsearía el
veredicto al promediarse con los de minuto.

**Paso 3 — el contraste que decide.** La edad del feed **no basta**: hay que comparar contra IBKR,
que es el reloj de la casa.
- `net-prem-ticks` publica cubos de minuto. El campo `cube_lag` que emite el modo `--rth-latency`
  responde justo a esto: **0** = el cubo del minuto en curso ya está publicado; **1** = va un cubo
  por detrás (lo normal en un feed que consolida por minuto); **≥ 2** = ya no sirve para disparar.
- `stock_state.tape_time` de UW contra el último print de IBKR del mismo símbolo
  (`data/bars_SPY.txt`, que escribe `ibkr_bar_bridge.py`). La **diferencia de sellos** es la
  latencia relativa de UW contra la fuente de disparo. Éste es el número que hay que apuntar en
  `docs/LATENCIA-FUENTES.md`.
- `market-tide` es de **5 minutos por construcción**: aunque llegue con 0 s de retraso, su
  resolución **ya la descalifica para disparar**. Se mide para saber cuándo aparece el cubo, no
  para ascenderla.

**Paso 4 — veredicto y escritura.** Regla de la casa: `< 60 s` → «candidato a tiempo real»,
`≥ 60 s` → **DELAYED, no dispara**. En cualquier caso la fila de UW en
`docs/LATENCIA-FUENTES.md:18` (hoy dice «🟠 mixto (trial, caduca ~2026-08-01)», ya obsoleta: el
token se renovó el 2026-08-03) se sustituye por el número medido, no por una etiqueta.

**Paso 5 — websocket.** Repetir §5 en RTH. Es el único experimento cuyo resultado de hoy podría
cambiar con el mercado abierto.

**Predicción registrada de antemano** (para que no se pueda racionalizar después): espero
`net-prem-ticks` en 30-90 s, porque UW consolida por cubo de minuto y luego lo publica. Si sale
< 30 s, sospechar de la medición antes de celebrarla.

---

## 5. Veredicto del websocket

### Lo medido, con los cuatro casos de control

| Petición | Resultado |
|---|---|
| `GET /api/socket` (HTTP normal, Bearer) | **200**, cuerpo `{"data":[]}` — **no anuncia ningún canal** |
| `wss://api.unusualwhales.com/api/socket?token=<válido>` | **HTTP 101 Switching Protocols**, luego **EOF del servidor a los 0,05-0,09 s**, **0 bytes**, sin close-frame |
| `wss://…/api/socket` **sin** token | **HTTP 401** — no hay handshake |
| `wss://…/api/socket?token=BASURA` | **HTTP 401** — no hay handshake |
| `wss://api.unusualwhales.com/socket?token=<válido>` | **HTTP 401** |
| `wss://…/api/websocket`, `wss://…/socket/websocket` | **HTTP 404** |

Se probaron **4 formatos de mensaje de unión** y **no enviar nada**: `["flow-alerts","join"]`,
`{"channel":…,"msg_type":"join"}`, Phoenix `{"topic":…,"event":"phx_join"}`, y silencio total.
**Los cinco cierran igual, en el mismo tiempo.** También se probó con cabecera `Origin:
https://unusualwhales.com` y User-Agent de navegador: idéntico.

### Veredicto

> **El socket AUTENTICA pero NO ENTREGA.** El token es válido en la capa HTTP (101 con token, 401
> sin él: la discriminación es real), pero la sesión de streaming se corta antes de emitir un solo
> byte. La firma —cierre inmediato, sin close-frame, insensible a lo que se envíe— es la de una
> **puerta de plan**, no la de un error de protocolo nuestro: si el `join` estuviera mal formado,
> el servidor lo diría o ignoraría el mensaje y mantendría la conexión.
>
> **`/api/socket` en GET devuelve `{"data":[]}`: el propio plan declara CERO canales.**
>
> **Consecuencia operativa: no se construye ningún consumidor de websocket.** El motor de flujo
> va por REST con sondeo, y su latencia es la que se mida el martes.
>
> **Falsable**: queda la hipótesis de que UW apague el socket fuera de horario. **Se re-prueba el
> martes en RTH (Paso 5).** Si en RTH el socket entrega mensajes, este veredicto se revoca y el
> socket pasa a ser la vía preferente — latencia = dinero.

---

## 6. Trampas MEDIDAS (esto es lo que se olvida y cuesta un diagnóstico)

### 6.1 `greek-flow.dir_delta_flow` NO es dato nuevo: es `net_prem_ticks.net_delta`

Medido sobre SPY 2026-08-03, los 406 minutos comunes:

```
net_delta == dir_delta_flow  en  406/406 minutos   (idénticos hasta el último decimal)
ej. 15:10 UTC : -34558.278137169387018500  ==  -34558.278137169387018500
greek_flow.volume (43172) == net_prem_ticks.call_volume + put_volume (43172)
```

**ρ = 1,0 exacto.** El primer test de la killlist (§3.1: colinealidad ANTES que edge, `|ρ|>0.9`
muere ya) mata cualquier feature que presente `dir_delta_flow` como fuente nueva. Lo único que
`greek-flow` añade de verdad es la **columna de vega** (`dir_vega_flow`, `total_vega_flow`) y el
**corte OTM**. Ahí sí hay información que no tenemos — y es lo que hay que evaluar, no el delta.

### 6.2 `etf-tide` por NOMBRE DE SECTOR devuelve 200 con 390 filas TODAS NULL

```
/api/market/Technology/etf-tide            -> 200 · 390 filas · 0 con dato
/api/market/Technology/etf-tide?date=…     -> 200 · 390 filas · 0 con dato
/api/market/Consumer%20Cyclical/etf-tide   -> 200 · 390 filas · 0 con dato
/api/market/XLK/etf-tide                   -> 200 · 390 filas · 390 CON DATO
```
El parámetro es el **ticker del ETF**, no el nombre del sector — pero UW **no da 400 ni 404**:
sirve un esqueleto con `timestamp` correcto y todos los valores a `null`. Un consumidor con
`float(x or 0)` fabricaría **una marea sectorial plana de exactamente cero** para todo el día.
Es literalmente el peligro nº 1 de `~/CLAUDE.md` (cero plausible), esta vez servido por el
proveedor. **Cualquier lector de `etf-tide` debe rechazar el payload si `net_call_premium` es
`None`, y levantar.**

### 6.3 `full-tape/{date}` es un ZIP de 1,54 GB, no un JSON

```
bytes = 1.537.500.500 · 38,2 s de descarga · cabecera PK\x03\x04
contiene: 2026-08-03-option_trades.csv
```
No es JSON (`shape: "no-json"`). En un Mac de 8 GB **jamás se carga en memoria**: hay que escribir
a disco por chunks y leer el CSV en streaming. Y es **1,5 GB por día de mercado**: archivar un
año son ~380 GB. Úsese para backtest puntual de un día concreto, no como archivo rutinario.

### 6.4 `spot-exposures`: `_vol` es ACUMULADO desde la apertura; `_oi` sigue congelado

```
gamma_per_one_percent_move_vol  13:38 UTC =  4.772.951.812   ->  20:00 UTC = 213.643.074.559
gamma_per_one_percent_move_oi   13:38 UTC =  3.551.292.777   ->  20:00 UTC =   8.603.993.313
_dir y _vol valen "0" en 153 de 530 filas — todas premarket, ANTES de la apertura
```
Dos consecuencias duras:
- El **nivel** de `_vol` no es comparable entre las 10:00 y las 15:00 (es un acumulado). Lo único
  con sentido es su **primera diferencia** = gamma negociada de ese minuto.
- La columna `_oi` se recalcula al spot vivo **pero con el OI del cierre anterior**. Su derivada
  temporal mide *el spot moviéndose bajo un libro congelado* — exactamente lo que mató a
  `converge`/`eta_min` (killlist #16). **Prohibido `d(gamma_..._oi)/dt`.**
- Los `0` de premarket no son «gamma cero»: son «aún no hay volumen». Rellenarlos o promediarlos
  sobre la sesión los convierte en un cero plausible.

### 6.5 Otros hechos de forma que rompen consumidores

- **Todo el dinero viaja como `str`**, incluidos `total_premium` y `net_call_premium`. Sumar sin
  convertir concatena.
- `net_put_premium` llega con precisión variable dentro de la misma respuesta (`"-98548.00"` y
  `"-840030.0000"`).
- `/api/earnings/SPY` devuelve `{"data":[]}` con 200. Vacío **honesto** (SPY no reporta) — pero
  indistinguible por status de un fallo. Hay que mirar el cuerpo.
- `/api/market/correlations` **400 sin parámetros**, 200 con `?tickers=SPY,QQQ&interval=1m`, y
  devuelve `rows: 21` — la correlación va sobre **21 filas**, no sobre la intradía.
- `congress/recent-trades` trae `ticker: null` en filas donde el activo es un bono o un fondo: el
  campo existe pero está vacío.

---

## 7. Diseño del motor de alertas — las 3 que defiendo

Reglas que gobiernan todo lo que sigue: **regla 11** (flujo extremo = extremo local, se opera la
reversión), **regla 12** (SPY/QQQ capitanes del mercado, SMH de semis; el capitán ANULA la señal
del nombre), **regla 2** (print o nada), **regla 3** (señal marginal ≠ decisiva).
Y la ley de `measured-probability`: hoy **ninguna** de las tres puede publicar un número. Nacen
todas en **`UNPROVEN` → banner, sin voz, sin dimensionar**, hasta que una celda califique.

---

### ALERTA 1 — `CAPITAN-CONTRA-TROPA` (veto, en dólares)

**Qué es.** La regla 12 hoy se aplica a mano y se infiere del PRECIO del capitán. UW permite
medirla en **premium agresor**, para el capitán y para el nombre, **en el mismo reloj de minuto**.

**(a) Gatillo exacto, en números.**
```
señal_nombre    = Σ_{15 min} (net_call_premium − net_put_premium)   de /net-prem-ticks/{sym}
señal_capitan   = Σ_{15 min} (net_call_premium − net_put_premium)   del capitán del sym
                  capitán = SMH si sym ∈ semis; si no SPY para XL*/índices, QQQ para el resto
                  (misma tabla de tropa que ya usa la regla 12; SIN inventar una nueva)
DISPARA VETO si:
  sign(señal_nombre) ≠ sign(señal_capitan)
  Y |señal_capitan| ≥ P80 de |señal_capitan| de las últimas 20 sesiones del PROPIO capitán
  Y |señal_nombre|  ≥ $250.000  (piso de materialidad: por debajo es ruido de un solo lote)
EFECTO: la señal del nombre pasa de SIGNAL a banner. NO genera alerta propia. NO habla.
```
Barrido de sensibilidad obligatorio: `P70 / P80 / P90`. **Si el efecto solo existe en P80, no es
real** (killlist §3.4).

**(b) Con qué se mediría.** Etiquetado de triple barrera sobre las señales que la flota YA emite
(`k_tp × k_sl × H` barridos, timeout = `NULL`), partiendo la muestra en `veto_on` / `veto_off`.
La métrica es la **expectancia en ATR**, no el win rate. Wilson sobre `n_eff` con ρ̄ = 0,412 y
tope por clusters `(sym, fecha)`. Dato necesario: `net-prem-ticks` de los 30 + los 3 capitanes,
archivado por sesión → **3 peticiones extra/minuto o 33 cada 5 min**; `uw_archive.py` ya archiva
`net_prem_ticks`, solo hay que subir la frecuencia. **Forward-only**: la serie intradía de UW no
es recuperable hacia atrás, así que el reloj de la muestra empieza el día que se encienda el
archivador.

**(c) Por qué NO es una trampa de la killlist.**
- **Celdas: CERO.** Es un booleano, no una rejilla `k × n`. Es el fallo que mató a #4, #5 y #14 y
  aquí no aplica.
- **No es compuesto de z-scores** (§4): son dos sumas y una comparación de signo. Sin pesos.
- **No es derivada de dato congelado** (#16): `net-prem-ticks` es de minuto vivo.
- **No es ranking transversal** (#13): compara el nombre con SU capitán, no 30 nombres entre sí.
- **No lava un veto en señal** (#12 `borrowed-map`): va en la dirección segura — convierte una
  señal en veto, nunca al revés.
- **Colinealidad a comprobar ANTES de construir**: ρ contra `fleet_consensus` (que mide manada
  sobre BARRAS, no sobre premium) y contra el `signed_premium` que ya publica `uw_net_prem.py`.
  Si ρ > 0,9 con cualquiera de los dos, **muere aquí**.

**Riesgo honesto**: es la más cara de validar porque solo actúa cuando hay conflicto, y el
conflicto es raro → `n_eff` crecerá despacio. Puede tardar 2-3 meses en salir de
`DATA-INSUFFICIENT`. Se dice ahora para que nadie lo presente como fracaso en septiembre.

---

### ALERTA 2 — `VEGA-AGRESOR EXTREMO` (la espada-ballena, por la única columna que es nueva)

**Qué es.** La regla 11 dice que el flujo extremo marca un extremo local. Hoy se detecta con el
P/C de la cadena IBKR (`opt_whale_watch`). UW aporta lo que la casa **no tiene y no puede
reconstruir**: `dir_vega_flow` y `otm_dir_vega_flow` por minuto — el vega que el AGRESOR compra o
vende. **No el delta**: el delta ya lo tenemos (§6.1, ρ = 1,0) y sería una feature renombrada.

**(a) Gatillo exacto, en números.**
```
v_t = dir_vega_flow del minuto t           de /greek-flow/{sym}
Sea D_t la distribución de |v| de los minutos 09:30 → t de la MISMA sesión, con ≥ 60 minutos
DISPARA si:
  |v_t| ≥ P95(D_t)                       (extremo contra su propia sesión, sin celdas cruza-día)
  Y sign(v_t) = sign(v_{t−1}) = sign(v_{t−2})   (compromiso 3 min — regla 3, nada de titileo)
  Y el spread del vehículo ≤ 5 % del premium  (regla 4; `scripts/optgate.py` ya existe)
  Y NO hay band-walk a favor: %B fuera de [0,05 · 0,95] en 2 de 3 TF (1m/15m) EN LA DIRECCIÓN
    DEL FLUJO ⇒ se ANULA (regla 11, excepción de día de catalizador del líder)
LECTURA: vega agresor comprado en masa = pago por movimiento = extremo local candidato.
         Se opera la REVERSIÓN, scalp corto, stop apretado (regla 11 tal cual).
VETO SUPERIOR: si ALERTA 1 marca conflicto con el capitán, ésta no habla.
```
Barrido: `P90 / P95 / P98` y compromiso de `2 / 3 / 4` minutos.

**(b) Con qué se mediría.** Triple barrera sobre la ruta 1m posterior, `H ∈ {10,30,60}`,
etiquetando la REVERSIÓN (dirección contraria al signo de `v_t`). Null obligatorio: **entradas
aleatorias emparejadas** en `sym` y bucket horario (`timeofday_calib`) de días del mismo régimen,
`N = 2000`, bootstrap estacionario **sobre la diferencia**. Umbral de dominio: la regla 11 es una
táctica de reversión de nivel, así que se le exige lo mismo que a `level-react`: **null + 4 pp**
con `n_eff ≥ 80`. Dato: `greek-flow` de los 8 símbolos de la cinta actual, 1 petición/minuto/sym
en RTH = **3.120 peticiones/día** — **10,4 % del cupo diario**; con los 30 no cabe. Empezar por
SPY, QQQ, SMH, NVDA, MU.

**(c) Por qué NO es una trampa de la killlist.**
- **La colinealidad ya está medida y por eso la feature es de VEGA, no de delta.** Es el único
  motivo por el que sobrevive. Queda un test pendiente: ρ de `dir_vega_flow` contra
  `signed_premium` — si vuelve a salir > 0,9, muere igual.
- **Sin celdas cruza-día**: el percentil se calcula **dentro de la sesión**. Ése fue el fallo
  exacto de `expansion-clock` (#14): 21 observaciones por bucket de minuto-del-día = astrología.
  Aquí no hay bucket de minuto-del-día.
- **No es un score compuesto**: es una condición sobre UNA columna + dos puertas booleanas
  (compromiso, band-walk) que ya son doctrina.
- **Input vivo, no muerto** (#2 `vanna-ramp` murió porque `poly_opt_bars` no tiene IV ni griegas):
  aquí el vega lo publica UW medido, no lo reconstruimos.
- **Riesgo declarado**: `dir_vega_flow` es *lado agresor*, **no inventario de dealer**. La casa ya
  mató como AFIRMACIÓN el «flujo delta-nocional FIRMADO». Esta alerta **no puede** decir «el
  dealer está corto de vega». Solo puede decir lo que UW mide: *el agresor pagó vega*.

---

### ALERTA 3 — `MURO EN CONSTRUCCIÓN` (el nivel que el OI congelado no puede ver)

**Qué es.** Los muros de la casa salen del OI, que **es el cierre de ayer y no se mueve intradía**
(`uw_oi_delta.py` lo documenta; killlist #16). `flow-per-strike` da el premium **de hoy** por
strike, **partido ask-side / bid-side**, actualizado durante la sesión: el muro que se está
levantando ahora mismo y que el mapa congelado no verá hasta mañana.

**(a) Gatillo exacto, en números.**
```
Para cada strike S de /flow-per-strike/{sym}:
  prem_S = put_premium_ask_side(S)      (o call_premium_ask_side(S))
  share  = prem_S / Σ_S' put_premium(S')        <- denominador COMPLETO, sin descartar strikes
DISPARA NIVEL si:
  share ≥ 0,25
  Y prem_S ≥ $2.000.000
  Y |S − spot| / spot ≤ 0,02
  Y S NO coincide (±1 strike) con un muro de OI ya publicado por gex_snapshot  <- anti-duplicado
PUBLICA: una línea en el chart + banner. NI VOZ NI PROBABILIDAD.
SE OPERA: solo con las reglas que ya existen — BOUNCE o RETEST_REJECT impreso
          (`print-o-nada-levels`). Nunca el TOUCH, nunca la primera ruptura.
```
Barrido: `share ∈ {0,15 · 0,25 · 0,40}` y `|S−spot|/spot ∈ {0,01 · 0,02 · 0,03}`.

**(b) Con qué se mediría.** Exactamente el protocolo de `level-react`: etiquetar toques del nivel
con las definiciones tipadas de la casa, contra el **null de nivel aleatorio** (1.000 niveles/
sesión de la misma rejilla de strikes con la misma distribución de `|dist/spot|`) y contra el
**null de toque simétrico** (nivel equidistante al otro lado). Umbral: **null + 4 pp**,
`n_eff ≥ 80` clusters-día. Vara de literatura (Osler 2000): un nivel debe añadir ≥ 6 pp sobre el
simple giro de vela o es decoración. Dato: 1 petición/sym cada 5 min en RTH = 78/día/sym; con 8
símbolos **624/día = 2,1 % del cupo**. Cabe.

**(c) Por qué NO es una trampa de la killlist.**
- **Es la ANTÍTESIS de #16**, no una recaída: el input es premium **negociado hoy**, no OI
  congelado. Ninguna derivada temporal de dato estático.
- **La cláusula anti-duplicado es el test de colinealidad hecho gatillo**: si el strike ya es un
  muro de OI conocido, la alerta **no lo publica**, así que no puede ser un re-etiquetado de
  `abs_wall`. Es la misma disciplina que se le exigió a `pin-clock`.
- **No es un motor de líneas** (#8 `trendline-engine`): son ≤ 2 niveles por símbolo, no 200, y el
  coste es O(strikes) sobre 440 filas ya agregadas por UW.
- **Denominador completo, declarado.** El bug nº 2 de `~/CLAUDE.md` (`fleet_consensus` con
  denominador fabricado, 21/26 = 80,8 % disparando DANGER) fue un símbolo que desapareció del
  denominador. Aquí el denominador es la suma de TODOS los strikes de la respuesta, y si falta
  algún campo la fila **levanta**, no se salta.
- **No habla.** Es un nivel en el gráfico. La voz sigue reservada a lo que ya está probado
  (`alert-budget`: una alerta nueva que habla tiene que decir **qué DANGER retira**; ésta no
  retira ninguno porque no habla).

---

## 8. Lo que MATO de mis propias ideas (y por qué)

| Idea que se me ocurrió | Muerte |
|---|---|
| **HIRO-lite con `greek-flow.dir_delta_flow`** — era la que más ilusión hacía, porque la killlist DIFIRIÓ «HIRO real» por falta de tick-by-tick de opciones en IBKR | **MEDIDO: ρ = 1,0 exacto contra `net_prem_ticks.net_delta`, 406/406 minutos.** Es la misma columna con otro nombre. Test 1 de la killlist (colinealidad ANTES que edge). Sobrevive **solo la mitad de vega** → ALERTA 2 |
| **Dark pool como señal** (`/api/darkpool/recent`, prints de bloque en un nivel = soporte) | Ya muerto: killlist #3 `dpi-lite`. La réplica bayesiana independiente pone el edge de DIX en ~0 y su horizonte son 60 días contra un stack intradía. `uw_darkpool.py` ya hace lo único legítimo: describir |
| **Ranking de flujo con `/api/market/top-net-impact`** (20 tickers por `net_premium`) | §4 killlist: **prohibido el ranking transversal** sobre una flota 26/30 correlacionada. En días risk-on la dispersión es ~nula y el ranking es ruido con autoridad. Además 26 de nuestros 30 son semis |
| **`UW_FLOW_SCORE` compuesto** (z de net premium + z de vega + z de gamma + z de OI-change) | §4 killlist: **prohibido el score compuesto de z-scores con pesos a mano** sobre términos correlacionados. Es el patrón de #6 y #13 literal |
| **`max_pain` como imán operable** | Primer test es colinealidad contra `abs_wall`/`pin-and-expiry-mechanics`, que la casa ya calcula con OI completo. Regla de `pin-clock`: `\|ρ\| > 0,9` = muere ya. **No se construye hasta medir ese ρ** |
| **Congress / insider como gatillo intradía** | Desajuste de horizonte medido en el propio payload: transacción `2026-07-27` **archivada el 2026-08-01**. Un dato con 5 días de retraso no dispara nada intradía. Vale como contexto en el PDF de las 4am, y nada más |
| **`etf-tide` por sector para una «marea sectorial»** | **Medido: 200 con 390 filas TODAS null** (§6.2). Con el ticker (`XLK`) sí hay dato — pero entonces es la marea de UN ETF, que es lo que `net-prem-ticks` de XLK ya daría. Colinealidad probable: **medir antes de construir** |
| **`market-tide` como disparador** | Cubos de **5 minutos por construcción**. Aunque llegara con 0 s de retraso, su resolución la descalifica para disparar. Sirve como el término «capitán» de ALERTA 1 y como contexto, jamás como print |

---

## 9. Cuota y coste operativo del motor propuesto

| Consumidor | Peticiones/día RTH | % de 30.000 |
|---|---|---|
| `uw_flow_tape.py` (ya en marcha, 8 syms / 90 s) | ~2.080 | 6,9 % |
| ALERTA 1: `net-prem-ticks` 30 syms + 3 capitanes cada 5 min | ~2.570 | 8,6 % |
| ALERTA 2: `greek-flow` 5 syms cada minuto | ~1.950 | 6,5 % |
| ALERTA 3: `flow-per-strike` 8 syms cada 5 min | ~624 | 2,1 % |
| Archivo EOD (`uw_archive.py`, 30×11 + 3) | 333 | 1,1 % |
| **Total** | **~7.560** | **25,2 %** |

Cabe con margen ×4. **El cupo NO es la restricción; la validación estadística sí.**

---

## 10. Estado y qué falta

- ✅ 64/69 rutas verificadas con status y forma real. Cero 401, cero 403.
- ✅ Websocket: **101 y cierre en 0,09 s** → no se construye. **Re-probar en RTH el martes.**
- ✅ Colinealidad `dir_delta_flow` ≡ `net_delta` medida y documentada.
- ✅ 3 trampas de forma medidas (nulls de `etf-tide`, ZIP de 1,5 GB, `_vol` acumulado).
- ⏳ **Latencia intra-sesión: NO MEDIBLE HOY.** Procedimiento del martes en §4.
- ⏳ Colinealidades pendientes ANTES de escribir una línea de motor: `dir_vega_flow` vs
  `signed_premium`; `señal_capitan` vs `fleet_consensus`; `max_pain` vs `abs_wall`.
- ⏳ Las 3 alertas nacen **UNPROVEN**: banner, sin voz, sin dimensionar. Ninguna publica un número
  hasta que su celda tenga `n_eff` suficiente y pase el null + BH-FDR.
- ❌ Nada de esto se cablea a la flota en esta sesión. Es un mapa, no un motor.

**Ficheros de esta entrega**: `scripts/uw_endpoint_probe.py` (sondeo + modo `--rth-latency` ya
implementado para el martes), `tests/test_uw_endpoint_probe.py` (**20 tests, pasan**), este
documento. Además, por orden de Yunior del 2026-08-04: hallazgos guardados en
`~/.claude/LEARNED.md` y los 6 TODOs derivados apuntados en `TODOS.md` §8 (latencia RTH,
re-test del websocket, las 3 colinealidades, archivador forward-only, lo bloqueado por muestra,
y lo que exige IBKR vivo).
