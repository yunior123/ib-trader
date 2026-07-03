# UW-NOVEDADES — segunda pasada: lo que el recon del 2026-08-04 NO cubrió

**Fecha del sondeo**: 2026-08-04 06:45–07:05 UTC (02:45 ET, **mercado CERRADO**, última sesión
2026-08-03).
**Documento hermano**: `docs/UW-FLOW-RECON-2026-08-04.md` (69 rutas). Este documento **no repite
nada de aquél**: solo mide lo que faltaba y **corrige por escrito cinco afirmaciones suyas**.
**Credencial**: `UW_TOKEN` vía `uw_premium.token()`. **No aparece aquí ni en ningún log.**
**Cuota**: `x-uw-daily-req-count` **566 → 706** ≈ **140 peticiones** de 30.000 (**0,47 %**).
**Fuente del inventario**: el spec OpenAPI oficial `https://api.unusualwhales.com/api/openapi`
(921 KB, **199 rutas**), no la memoria ni el HTML de la doc.

**SEÑAL-SOLAMENTE.** Nada de aquí ordena al broker. Nada de aquí dispara.

---

## 0. Resumen ejecutivo — 3 hallazgos que defiendo, 5 correcciones

1. 🟢 **HAY 90 DÍAS DE MERCADO DE HISTORIA A 1 MINUTO, DESCARGABLES HOY.** La API lo dice con
   todas las letras al pedir una fecha vieja: *«The earliest date currently available to you is
   **2026-03-24 (90 trading days)**»*. Y **el 1m OHLC del mismo proveedor llega igual de atrás**.
   Esto **anula la premisa `forward-only`** sobre la que el recon anterior construyó sus 3
   alertas (§7 de aquel doc: *«el reloj de la muestra empieza el día que se encienda el
   archivador»*). **Es el hallazgo caro.** Detalle y coste en §4.1.
2. 🟢 **`group-flow/{semi|mag7}` es el CAPITÁN medido en premium, y NO es SMH.** Mediana de
   |premium firmado 15 min|: **semi $11.269.360 vs SMH $859.814 (13×)**, ρ = **−0,087**. La regla
   12 usa hoy SMH como *proxy* del sector; UW mide la cesta entera. §4.2.
3. 🟢 **El websocket está cerrado por SCOPE DE TOKEN, y el servidor lo dice en palabras.**
   `wss://api.unusualwhales.com/socket` → **401** con cuerpo *«Your token does not have the
   websocket scope»*. **Retira el TODO de re-probar el martes en RTH**: no es un horario, es un
   permiso. §3.2.

**Las 5 correcciones al recon anterior** (todas con número, §3):

| Afirmación del recon 2026-08-04 | Estado medido hoy |
|---|---|
| «El plan da acceso a TODO. **Cero 401. Cero 403.**» | **FALSO en general**: 8 rutas gated medidas (`advanced_tier_required`, `volatility_scope_required`, `options_pulse_scope_required`). Solo se sostenía porque las 69 rutas probadas esquivaron todas las de pago |
| «`market/sector-tide` **no existe** (usar `{ETF}/etf-tide`)» | **Existe**: la ruta es `/api/market/{sector}/sector-tide`. **391 filas de 1 minuto, 391/391 con dato** |
| «`etf-tide` … es la marea de UN ETF, que es lo que `net-prem-ticks` de XLK ya daría. Colinealidad probable» | **MEDIDO Y FALSO**: ρ(sector-tide, net-prem-ticks XLK) = **0,035**, escala **80.000×** ($215M vs $2.663). Es el flujo de las **PARTICIPACIONES**, no del ETF |
| «`spot-exposures/expiry-strike` … ruta inexistente (404)» | Existe con **otra firma**: `?expirations[]=YYYY-MM-DD` (query, no path) → **200**. La 404 fue de la forma, no de la ruta |
| «la serie intradía de UW **no es recuperable hacia atrás**» | **FALSO desde el 2026-07-02**: 90 días de mercado (§4.1) |

---

## 1. Qué ha lanzado UW recientemente, con fecha y fuente

Fuente: `https://unusualwhales.com/changelog` — **323 entradas parseadas del HTML servido**, con
su `created_at`. Lo relevante de 2026 y todo lo de API:

| Fecha | Título (literal) | Por qué nos importa |
|---|---|---|
| **2026-07-02** | *Updated API limits across all subscriptions* | **Trial Basic (weekly): 30.000 req/día (era 15.000) e histórico 90 días (era 7).** Es exactamente nuestro plan (`x-uw-token-req-limit` = 30000). **El salto de 7→90 días es el hallazgo nº1** |
| 2026-07-24 | *Clicking Market Tide now takes you to that minute in the flow feed* | UI. Confirma que la tide tiene granularidad de minuto en su producto |
| 2026-07-23 | *Added new multi-leg flow feed* | REST equivalente `/api/option-trades/multi-leg` → **403 advanced_tier_required** para nosotros |
| 2026-07-01 | *1 Minute Periscope Available now through Retail Max subscription* | Periscope 1 min = exposición MM por strike/expiry de SPX/VIX/XSP/NANOS. Canal `periscope` del websocket. **Fuera de alcance: websocket + tier** |
| **2026-06-25** | *Recent platform updates - API updates, AI, GEX* | *«Added **'premium' endpoints** to the Advanced subscription»*. **Ésta es la frase que explica los 403 de §3.1** |
| 2026-05-19 | *Added AI chat assistant* (Mr. Whale) | Producto de chat. Irrelevante: mete un LLM en el camino de señal |
| 2026-05-01 | *Market Maps + Dark Pool Updates* | **«Added a new data point that now shows the TRF delay: the time between when the trade executed and when it hit the tape»**. Ojo: es el reconocimiento explícito del proveedor de que el dark pool llega con retraso medible |
| **2026-03-17** | *Added Prediction market data endpoints to the API* | `/api/predictions/*` (9 rutas). **200 para nosotros**. Descartado en §5 |
| **2026-03-12** | *Introducing the Unusual Whales MCP server* | Servidor MCP oficial. Descartado en §5 |
| 2026-02-19 | *API subscriptions: increased historical look back + daily limits* | El escalón anterior (Trial seguía en 7 días). El de julio es el que nos abre la puerta |

**Anteriores, pero nunca inventariadas por la casa** (explican rutas que hoy existen):
`2025-06-02 New API Endpoints` (interpolated-iv, contract volume-profile, contract intraday) ·
`2025-03-31 Spot Gamma by Strike/DTE + new API endpoints` (news/headlines + los 5 de `shorts`) ·
`2024-10-28 Added new endpoints to the API` (**`GroupFlowController.greek_flow` y
`TickerController.greek_flow_expiry`** — o sea, los dos hallazgos 2 y 4 llevan **21 meses**
publicados y a la casa se le pasaron).

> Lección honesta: **ninguna de mis tres joyas es una novedad de 2026.** Lo nuevo de 2026 es el
> *acceso* (90 días) y los *muros* (tiers). Lo demás llevaba dos años ahí sin que lo miráramos.

---

## 2. Endpoints y parámetros NUEVOS probados — status y forma REAL

Inventario completo derivado del OpenAPI: **199 rutas**. El recon anterior probó **69**.
Diff bruto: **130 rutas sin tocar**. De ésas sondeé las **62** con posible valor de señal; las
otras 68 (crypto, forex, private-markets, financials, institution, congress, companies…) quedan
fuera por tesis, no por pereza — se listan en §5.

### 2.1 Las que FUNCIONAN y aportan algo (200)

| Ruta | HTTP | filas | Forma real medida |
|---|---|---|---|
| `/api/stock/{t}/gex-levels` | **200** | 1 | `call_wall · put_wall · gamma_magnet · gamma_flip` (strings). SPY: 760 / 754 / 754 / **764,08** |
| `/api/stock/{t}/greek-flow/{expiry}` | **200** | **405** | 1 fila/min **por vencimiento**: `dir_delta_flow · dir_vega_flow · otm_* · total_* · transactions · volume` |
| `/api/group-flow/{grupo}/greek-flow` | **200** | **405** | 1 fila/min **de la CESTA**. 25 grupos: `semi · mag7 · china · cyber · gold · oil · uranium …`. Añade `net_call_premium/net_put_premium` y el corte OTM, que la versión por ticker NO trae |
| `/api/group-flow/{grupo}/greek-flow/{expiry}` | **200** | 405 | lo mismo × vencimiento |
| `/api/market/{sector}/sector-tide` | **200** | **391** | **1 minuto**: `timestamp · net_call_premium · net_put_premium · net_volume`. 391/391 con dato |
| `/api/net-flow/expiry` | **200** | **390** | **1 minuto, TODO EL MERCADO**, + `underlying_price`. Filtros `moneyness ∈ {all,itm,otm,atm}` · `tide_type ∈ {all,equity_only,etf_only,index_only}` · `expiration ∈ {weekly,zero_dte}` |
| `/api/stock/{t}/nope` | **200** | 390 | 1/min: `nope · nope_fill · call_delta · put_delta · call_fill_delta · put_fill_delta · call_vol · put_vol · stock_vol` |
| `/api/stock/{t}/flow-per-strike-intraday` | **200** | 3.242 | **NO es una rejilla minuto×strike**: 3.218 sellos distintos **con precisión de milisegundo** sobre **solo 8 strikes**. Mediana 1 strike por sello |
| `/api/stock/{t}/spot-exposures/expiry-strike?expirations[]=` | **200** | n | matriz completa `{call,put}_{delta,gamma,vanna,charm}_{oi,vol,ask,bid}` = **32 columnas de griega** |
| `/api/stock/{t}/greeks?expiry=` | **200** | 161 | griegas por strike **medidas por UW**: `call/put_{delta,gamma,vega,theta,rho,charm,vanna,volatility}` |
| `/api/stock/{t}/historical-risk-reversal-skew?expiry=&delta=` | **200** | 27 | `date · delta · risk_reversal` (IV put − IV call a 25Δ/10Δ) |
| `/api/stock/{t}/ohlc/{1m,5m,…,1w}` | **200** | 813/día | `open/high/low/close · start_time/end_time · volume · total_volume · market_time`. **Cubre 08:00→23:59 UTC** (premarket + RTH + AH) |
| `/api/option-trades` | **200** | n | la cinta CRUDA con **~80 filtros** (`min_premium`, `min_dte`, `min_delta`, `is_otm`, `opening`, `exchanges[]`, `min_spread`…). Campos: `nbbo_bid/ask`, **`ewma_nbbo_bid/ask`**, `ask_vol/bid_vol/mid_vol/no_side_vol`, griegas, `flow_alert_id` |
| `/api/lit-flow/{t}` y `/recent` | **200** | n | prints de bolsa con **NBBO en el momento** + `sale_cond_codes` + `market_center` |
| `/api/stock/{t}/volatility/variance-risk-premium` | **200** | 231 | `risk_premium · rank` diario, 231 días |
| `/api/stock/{t}/volatility/{anomaly,character}` | **200** | 1 | `latest` + `history`. `character`: `hurst_rv · half_life_days · entropy_*` |
| `/api/stock/{t}/technical-indicator/{fn}` | **200** | 205 | RSI etc. `interval ∈ {1min…monthly}` |
| `/api/alerts/filters` | **200** | 1 | **28 tipos de alerta configurables server-side**: `gex · market_tide · ticker_interval_flow · option_contract_interval · flow_alerts · trading_state · potus_schedule …` |
| `/api/shorts/{t}/interest-float/v2` · `/volumes-by-exchange` · `/api/short_screener` | **200** | 123/498/50 | `fee_rate · si_float · days_to_cover` con `market_date` |
| `/api/stock/{t}/{expiry-breakdown, option/volume-oi-expiry, options-volume, option-chains, info}` | **200** | 34/35/n/13.958/1 | descriptivos |
| `/api/predictions/{whales,unusual}` · `/api/potus/posts` · `/api/seasonality/*` · `/api/institutions/latest_filings` | **200** | — | ver §5 |

### 2.2 Las que están CERRADAS por plan — con el código de error literal

| Ruta | HTTP | `code` devuelto |
|---|---|---|
| `/api/market/movers` | **403** | `advanced_tier_required` |
| `/api/calendar/ipo` | **403** | `advanced_tier_required` |
| `/api/economy/{indicator}` | **403** | `advanced_tier_required` |
| `/api/option-trades/multi-leg` | **403** | `advanced_tier_required` |
| `/api/volatility/vix-term-structure` | **403** | `volatility_scope_required` (add-on de volatilidad) |
| `/api/options-pulse/{total,sectors,top}` + `/api/stock/{t}/options-pulse` | **403** | `options_pulse_scope_required` (add-on Nasdaq Options Pulse) |
| `/api/option-trades/optionable-tickers` | **422** | *«Missing access … API Advanced subscription»* |
| `/api/option-trades/exchange-breakdown/{date}` | **422** | *«Missing access **for the option tape**»* |
| `wss://api.unusualwhales.com/socket` | **401** | *«Your token does not have the **websocket scope**»* |

### 2.3 Parámetros nuevos probados sobre rutas YA conocidas

| Parámetro | Resultado medido |
|---|---|
| `market-tide?interval_5m=true` vs sin él | **78 filas en AMBOS.** La doc promete *«Per default data are returned in 1 minute intervals»*. **Medido: el parámetro no tiene efecto y siempre son cubos de 5 min.** O el doc miente o el 1m está gated |
| `market-tide?otm_only=true` | 200, 78 filas |
| `net-prem-ticks?date=` a 1/5/20/45/60/75/88 días | **200 con 405-406 filas en todos**; `date` de sábado (2026-06-20) → **200 con 0 filas** (vacío honesto) |
| `net-prem-ticks?date=2026-01-16` | **403 `historic_data_access_missing`** con el mensaje que declara la pared: **2026-03-24, 90 trading days** |
| `ohlc/1m?date=` a 2026-03-20 | **200, 879 filas** — llega **más atrás** que la pared declarada de `net-prem-ticks` |
| `market/oi-change?order=volume` | **422** con la lista de valores válidos (`desc`,`asc`). Errores útiles, no crípticos |
| `/api/stock/{sector}/tickers` | **422** que **enumera los sectores válidos** — útil como descubridor |

---

## 3. Diff explícito contra el recon anterior

### 3.1 «El plan da acceso a TODO» — refutado

El recon concluyó: *«64 de 69 rutas devuelven 200. Los 5 fallos son rutas inexistentes o mal
parametrizadas por mí, no restricciones de plan. **Cero 401. Cero 403.**»*

**Medido hoy: 9 puertas de pago reales** (§2.2), con tres códigos de error distintos y bien
tipados. La conclusión anterior no era falsa sobre *sus* 69 rutas — era falsa **como
generalización**, porque el muestreo esquivó por completo la familia `advanced_tier_required` y
las dos de add-on. **Somos Trial/Basic, no Advanced**: el `code` de error es la prueba, no la
factura.

### 3.2 El websocket: la causa era otra, y ahora está cerrada

El recon probó `wss://…/api/socket?token=` → **101 y EOF a los 0,09 s**, y `wss://…/socket?token=`
→ **401**, y descartó el segundo como «ruta mala». **Es al revés.** El propio spec y la skill
oficial de UW (`https://unusualwhales.com/skills/websocket.md`) declaran el URI:

```
wss://api.unusualwhales.com/socket?token=<TOKEN>
```

Medido hoy con handshake HTTP/1.1 correcto sobre **ese** URI:

```
HTTP/1.1 401 Unauthorized
Your token does not have the websocket scope. To connect to the websocket you need to
upgrade your api subscription. Contact support@unusualwhales.com for more information
```

Y sobre `/api/socket` (la ruta de **documentación**), el mismo handshake da **101** — que es lo
que confundió al recon: es un upgrade que no lleva a ningún canal.

> **Consecuencia: se RETIRA el paso 5 del procedimiento del martes** (`docs/UW-FLOW-RECON-2026-08-04.md`
> §4 y §10, y el TODO correspondiente). Un *scope* de token no cambia con el horario del mercado.
> El canal `flow-alerts` existe y entregaría 6-10M de registros/día — pero no para este token.

### 3.3 La marea sectorial: el recon la mató con una suposición, y la suposición era falsa

El recon mató *«etf-tide por sector para una marea sectorial»* con este argumento:
*«Con el ticker (XLK) sí hay dato — pero entonces es la marea de UN ETF, que es lo que
net-prem-ticks de XLK ya daría. Colinealidad probable: medir antes de construir.»*

**Medido** (SPY/XLK, 2026-08-03, 390 minutos comunes):

```
rho( sector-tide[Technology] , etf-tide[XLK] )                  = 0.982   <- son LA MISMA cosa
rho( sector-tide[Technology] , net-prem-ticks[XLK] )            = 0.035
rho( primeras diferencias de las dos anteriores )               = -0.032
escala mediana |premium firmado|: sector 215.403.017  vs  XLK 2.663   (80.000x)
```

`etf-tide/{XLK}` **no es el flujo del ETF**: es el flujo de sus **PARTICIPACIONES** (el changelog
de 2025-01-03 lo dice: *«Added 'HOLDINGS net flow view' for the SPDR sector ETFs»*). La
colinealidad que el recon temía **no existe**; la que sí existe es entre `sector-tide` y
`etf-tide`, que son duplicados (ρ = 0,982) → **se elige uno y se tira el otro**.

### 3.4 Lo que el recon acertó y aquí se confirma

- `dir_delta_flow` ≡ `net_delta`: **no lo he vuelto a gastar en cuota**. Su medición (406/406,
  ρ = 1,0) es correcta y sigue siendo la razón por la que todo lo de delta está muerto.
- `full-tape/{date}` = ZIP de 1,5 GB: no reprobado, no hace falta.
- `market-tide` a 5 minutos: **confirmado**, y además ahora se sabe que el parámetro que la doc
  ofrece para bajar a 1 min **no funciona en este plan** (§2.3). Pero ver §4.4: existe una ruta
  distinta que sí da 1 minuto a nivel de mercado.

---

## 4. Hallazgos — con las 4 respuestas obligatorias

### 4.1 🟢 HALLAZGO 1 — 90 días de mercado a 1 minuto, y el labelling incluido

**(a) Qué mide exactamente y con qué cadencia real (medida).**
No es una métrica: es **acceso**. Con `?date=YYYY-MM-DD` los endpoints de minuto sirven sesiones
pasadas completas. Medido sobre `/api/stock/SPY/net-prem-ticks`: **200 con 405-406 filas** para
2026-07-30, 07-15, 06-05, 05-21, 05-08, 05-01 y **04-06**; **403 `historic_data_access_missing`**
para 2026-01-16, con el servidor declarando la pared: **«The earliest date currently available to
you is 2026-03-24 (90 trading days)»**. Un sábado devuelve **200 con 0 filas** — vacío honesto,
no un cero plausible. Y `/api/stock/SPY/ohlc/1m?date=` devuelve **813-879 velas** por sesión
(08:00→23:59 UTC, o sea premarket + RTH + after-hours) hasta al menos 2026-03-20.

**(b) ¿La casa ya lo tiene por otra vía? NO, y ésta es la parte que decide.**
`~/CLAUDE.md` fija el estado real de la muestra: `poly_bars` = **21 sesiones** (24-jun→23-jul) y
`poly_opt_bars` **sin columnas iv/griegas/OI**. La skill `measured-probability` §7 lo eleva a ley:
*«Ninguna feature publica una probabilidad cuyo plan de validación reclame ≥60 sesiones hasta que
`data/backfill_report.json` demuestre que esa muestra existe»*, y añade que el backfill *«es SOLO
PRECIOS: la historia de OI/IV no existe a ningún precio en este plan»*.
**UW rompe las dos restricciones a la vez**: 90 sesiones de flujo de opciones por minuto **y** 90
sesiones de barras de 1 minuto para etiquetar, del mismo proveedor y con el mismo reloj. Eso no lo
tiene la casa por ninguna otra vía.

**(c) ¿Pasa la killlist?** No es una feature, así que no tiene celdas, ni z-scores, ni derivadas
de dato congelado. Pero hay que decir en voz alta los **dos peligros que introduce**:
- **Look-ahead silencioso (test 3 de la killlist).** Descargar hoy la sesión del 2026-04-06 sirve
  el estado **final** de esa sesión. Si algún campo se recalcula *a posteriori* (revisiones de
  cinta, trades anulados — UW tiene `canceled` y el changelog 2025-08-07 añadió *«nullified/modified
  trade indicator to historical data»*), lo descargado **no es lo que se veía en vivo**.
  → **Regla dura propuesta: cada fichero archivado lleva en su cabecera `pull_date` y
  `session_date`.** Un backfill y un archivo en vivo **jamás se mezclan sin declararlo**, que es
  literalmente la regla del `oi_source` de `~/CLAUDE.md`.
- **Multiple testing.** 90 sesiones no son licencia para barrer 30 features: sigue rigiendo BH-FDR
  q=0,10 + DSR/MinTRL.

**(d) Qué se podría medir y con qué muestra.** Las **3 alertas del recon anterior**, esta semana,
sin esperar meses. Con la corrección de `n_eff` medida (ρ̄ = 0,412):
- ALERTA 1 `CAPITAN-CONTRA-TROPA`: el recon avisaba de *«2-3 meses en DATA-INSUFFICIENT»*. Con 90
  sesiones × 30 símbolos, topado por clusters `(sym,fecha)` → **≤ 90 clusters-día**, que roza el
  `n_eff ≥ 80` de `level-react`. Sigue siendo justo, pero es **medible ahora**, no en octubre.
- ALERTA 2 `VEGA-AGRESOR`: 90 sesiones × 5 símbolos = **≤ 450 clusters-día**. Sobra.
- Coste de cuota del backfill: `net-prem-ticks` = **1 petición por sym-sesión**. 30 syms × 90
  sesiones = **2.700 peticiones = 9 % de UN día de cupo**. Añadiendo `ohlc/1m` (2.700 más) y
  `greek-flow` (2.700), el backfill entero cabe en **~8.100 peticiones = 27 % de un solo día**.
  **El cupo no es la restricción. Nunca lo fue.**

---

### 4.2 🟢 HALLAZGO 2 — `group-flow/{semi}`: el capitán medido, no el proxy

**(a) Qué mide y cadencia.** Flujo griego agregado de **todos los tickers del grupo**, **1 fila
por minuto**, 405 filas medidas para 2026-08-03. Columnas que la versión por ticker **no tiene**:
`net_call_premium`/`net_put_premium` del grupo **y** el corte OTM completo (`otm_dir_vega_flow`,
`otm_net_*`). 25 grupos; los que nos tocan: **`semi`** y **`mag7`**.

**(b) ¿La casa ya lo tiene?** **No.** La regla 12 (`~/CLAUDE.md`) nombra a SMH capitán de semis y
lo evalúa por su precio y su propio flujo. Medido (2026-08-03, ventanas de 15 min, n = 375):

```
rho( semi , SMH  ) = -0.087       <- NO es SMH
rho( semi , NVDA ) =  0.695
rho( SMH  , NVDA ) =  0.058
|premium firmado 15m| mediana:  semi 11.269.360   SMH 859.814     (13x)
semi dir_vega_flow 15m mediana: 195.070
```

El flujo de opciones **de SMH** es un instrumento distinto del flujo de opciones **de los semis**:
13 veces más pequeño y prácticamente ortogonal. Usar SMH como capitán no es una aproximación
buena — es **otra cosa**.

**(c) ¿Pasa la killlist?**
- **Colinealidad (test 1)**: máx |ρ| = **0,695** contra NVDA. **Sobrevive**, pero **hay que
  decirlo**: la cesta está dominada por los mega-nombres, así que *no* es información
  independiente de NVDA — es NVDA + compañía, con más masa y menos ruido idiosincrático.
- **Celdas (test 2)**: cero. Es una comparación de signo entre dos sumas, como la ALERTA 1.
- **Dato congelado (#16)**: no, es minuto vivo.
- **Ranking transversal (§4)**: **no**, y es justo lo contrario — sustituye un ranking de 30
  nombres correlacionados por **una sola serie agregada**, que es lo que la killlist pide.
- **Veto lavado en señal (#12)**: **cuidado aquí**. La regla 12 dice que el capitán **ANULA** la
  señal del nombre. Si `group-flow` se usa para *fabricar* señal donde SMH no la daba, es
  `borrowed-map` otra vez. → **Sólo se admite en dirección de VETO**, nunca creando señal.

**(d) Qué se mediría.** Sustituir el término `señal_capitan` de la ALERTA 1 del recon por
`semi`/`mag7`, y correr **las dos versiones sobre las mismas 90 sesiones**: ¿la expectancia en ATR
del veto mejora con la cesta frente a SMH? Ésa es una comparación A/B limpia, misma muestra, mismo
etiquetado de triple barrera, y con un **null obligatorio**: barajar la asignación
capitán↔tropa. Coste: **2 peticiones por sesión** (semi + mag7) = **180 para los 90 días**.

---

### 4.3 🟢 HALLAZGO 3 — `greek-flow/{expiry}`: el vega 0DTE es casi ortogonal al agregado

**(a) Qué mide y cadencia.** El mismo flujo griego por minuto, **partido por vencimiento**. 405
filas para SPY/2026-08-03 con `expiry = 2026-08-03` (0DTE).

**(b) ¿La casa ya lo tiene?** No, y **el recon anterior tampoco**: su ALERTA 2 se construyó sobre
el `dir_vega_flow` **agregado**. Medido:

```
rho( dir_vega_flow  agregado , 0DTE ) = 0.089
rho( dir_delta_flow agregado , 0DTE ) = 0.843
|vega 0DTE| / |vega agregado|, mediana = 0.096   (n=405)
```

O sea: **el 0DTE es el 9,6 % del vega agregado y no se mueve con él** (ρ = 0,089). La ALERTA 2 del
recon, tal y como está escrita, mide sobre todo vega **de vencimientos que no son el del día** —
justo el contrario de lo que su propia doctrina (`0dte-only-budget`, presupuesto ≤ $200) quiere
detectar. **No es una mejora cosmética: es que estaba midiendo otra cosa.**

**(c) ¿Pasa la killlist?**
- **Colinealidad**: ρ = 0,089 con el agregado, muy por debajo de 0,9. **Pasa con holgura.** Y su
  primo el delta (ρ = 0,843 con el agregado, que a su vez es ρ = 1,0 con `net_delta`) **sigue
  muerto** — la mitad de delta de este endpoint no se toca.
- **Celdas**: el percentil se calcula **dentro de la sesión** (como ya exigía el recon), así que
  no hay rejilla cruza-día. Pero **partir por vencimiento multiplica ×N las celdas si se abren
  todos los vencimientos** → **regla: sólo 0DTE y el semanal más cercano. Dos, no 35.**
- **Compuesto de z-scores**: no, es una columna.
- **Input muerto (#2)**: no, UW lo mide; no reconstruimos IV.
- **Riesgo declarado (heredado del recon, y sigue vigente)**: `dir_vega_flow` es **lado agresor**,
  **no inventario de dealer**. Esta alerta jamás puede decir «el dealer está corto de vega».

**(d) Qué se mediría.** Triple barrera sobre la ruta 1m posterior, `H ∈ {10,30,60}`, etiquetando
la **reversión**, con el null de entradas aleatorias emparejadas por sym y bucket horario
(N = 2000, bootstrap estacionario sobre la diferencia). Umbral heredado: **null + 4 pp con
`n_eff ≥ 80`**. Coste: **1 petición por sym-sesión-vencimiento**; 5 syms × 90 sesiones × 2
vencimientos = **900 peticiones** para toda la historia disponible.

---

### 4.4 🟡 Dos hallazgos menores que sí anoto (con su pega)

**`gex-levels` como árbitro barato del flip.** 1 petición, 1 fila, 4 números. Contra el mapa de la
casa (`data/gex_snapshot.json`, reescrito hoy a las 02:52, `spot` 758,29 — la misma sesión, así
que la comparación es legítima):

| | UW `gex-levels` | casa `gex_snapshot` |
|---|---|---|
| `call_wall` | **760** | **760,0** ✅ idéntico |
| `put_wall` | **754** | `null` (la casa no lo publica) |
| imán | `gamma_magnet` **754** | `abs_wall`/`poc` **749,0**, `magnets` [749, 760] |
| **flip** | **764,08** | **735,3** (`flip_src: recompute_15pct`) |

El muro de call coincide **exactamente**. El **flip difiere en 28,8 puntos y cae al otro lado del
spot**: UW lo pone por ENCIMA de 758,29 y la casa por DEBAJO → **régimen de dealer opuesto**. Dado
el peso doctrinal de eso (memoria `negative-gamma-whipsaw`: *«gamma NEG = whipsaw, es una caja, no
dirección»*), tener un segundo cómputo por 1 petición/ticker/día es barato.
**Pega honesta**: no es una señal ni puede serlo — es un **detector de discrepancia**. Y la
killlist ya dictaminó que *«los NIVELES de SpotGamma, MenthorQ y TrendSpider son matemática de
commodity»*: el valor está en que **discrepe**, no en creerle. El `parity_ok_pct: 0.0` de nuestro
propio snapshot sugiere que **la que puede estar rota es la nuestra**. → **acción: comparar los 35
del universo durante 5 sesiones y ver si la discrepancia es sistemática o de un solo día.** 35
peticiones/día.

**`/api/net-flow/expiry` = la marea de mercado a 1 MINUTO.** 390 filas (13:30→19:59 UTC), con
`underlying_price` incrustado, y filtrable a `zero_dte` + `otm` + `equity_only`. El recon mató
`market-tide` como disparador porque *«cubos de 5 minutos por construcción»* — lo cual es cierto
**para esa ruta** (confirmado, §2.3) pero **falso para la familia**: aquí hay marea de mercado por
minuto. ρ = 0,817 contra `market-tide` en los 30 minutos que coinciden, con escalas distintas
($18M vs $846M), así que **no son la misma serie** y hay que entender la diferencia antes de usar
ninguna.
**Pega honesta**: no he podido determinar por qué difieren 50× en escala (el `expiration` por
defecto no viene declarado en la respuesta). **No se construye nada encima hasta saberlo.**

---

## 5. Lo que DESCARTO, y por qué

| Idea / ruta | Muerte |
|---|---|
| **`nope` como señal** | Dos golpes. (1) **No es reproducible**: medido, `nope ≠ (call_delta − put_delta)/stock_vol` (ej. 10,03 vs 5,09 — factor ~2 sin documentar). Es un compuesto de vendedor con fórmula cerrada = *«prior inventado disfrazado de medición»*, §2 de la killlist. (2) La ρ que parece salvarlo es **espuria**: ρ(cumsum(net_delta), call_delta−put_delta) = **0,969** es la correlación de dos series integradas, no información; en **primeras diferencias**, que es el test correcto, ρ(net_delta, Δ(cd−pd)) = **0,096**. Ni «es lo mismo» ni «es nuevo»: es **inauditable**. Lo único defendible de la idea —normalizar el delta por volumen de acciones— la casa **ya puede calcularlo** con `net_delta` (que tiene) y el volumen de IBKR |
| **`option-stance`** | `fit_score` **0-5** compuesto de cinco sub-scores nombrados (`iv_regime`, `greeks_fit`, `dte_fit`, `liquidity`, `earnings_timing`) con pesos del vendedor. Es la **regla dura §4 de la killlist literal**: *«prohibido un score compuesto de z-scores con pesos a mano»*. Que los pesos sean de UW y no míos lo empeora, no lo mejora |
| **`volatility/anomaly` + `anomaly/top` + `character/top`** | Misma muerte: la propia doc los llama *«a **composite signal** flagging unusually rich/cheap volatility»*. Y los `/top` son **ranking transversal** sobre una flota 26/30 semis → §4 killlist, prohibido explícitamente. El `character` (Hurst, half-life, entropía) **la casa lo calcula sola** con `stats-trading-core`, sobre sus propios datos y con la fórmula a la vista |
| **`flow-per-strike-intraday` como upgrade de la ALERTA 3** | La doc promete *«one minute intervals»*. **Medido: 3.242 filas, 3.218 sellos distintos con precisión de milisegundo, y sólo 8 strikes** (700…763), mediana 1 strike por sello. **No es la rejilla minuto×strike** que haría falta para ver «el muro que se está construyendo». Queda como **pendiente**, no como hallazgo, hasta explorar el parámetro `filter` (sin enum en el spec) |
| **`market-tide?interval_5m`** | 78 filas con y sin el parámetro. Promesa de la doc no cumplida en este plan. No se construye sobre una promesa |
| **Todo lo de tier Advanced** (`movers`, `ipo`, `economy`, `multi-leg`, `exchange-breakdown`, `optionable-tickers`) y los add-ons (`vix-term-structure`, `options-pulse` ×4) | **403/422 medidos.** Discusión cerrada hasta que alguien pague. Nota: `vix-term-structure` habría sido tentador (el VIX desbloquea la banda de fragilidad, `~/CLAUDE.md`) pero **`cboe-data` ya da la estructura VX gratis** y la killlist #15 ya dictaminó que *«la pendiente del VX de `cboe-data` YA da el régimen»* |
| **Websocket / Kafka / canal `periscope`** | `websocket scope` ausente (§3.2). Sin recurso |
| **Servidor MCP de UW** (2026-03-12) | No añade **ni un dato**: es el mismo REST detrás de un LLM. Mete latencia y no-determinismo en un camino donde `~/CLAUDE.md` dice *«latencia = dinero»* y *«Python es peligroso»*. Para consumo por agente, `curl` al REST es estrictamente superior |
| **`/api/predictions/*`** (9 rutas, novedad 2026-03-17) · **`/api/potus/*`** · **`/api/seasonality/*`** · **`private-markets`** · **`crypto`/`forex`/`commodities`** · **`congress`/`insider`/`institution`** | 200, pero **fuera de la tesis**. El lema de la casa es *«detectar y anticipar MOVIMIENTOS»* intradía; congress/insider ya murió en el recon anterior por desajuste de horizonte (transacción del 07-27 archivada el 08-01). Seasonality y predictions son horizonte de semanas |
| **`lit-flow` y `option-trades` crudos como fuente rutinaria** | No los mato: los **difiero con condición**. `option-trades` con sus ~80 filtros es la herramienta correcta para *reconstruir* una cinta filtrada de los 90 días, pero **son N peticiones por sesión**, no 1. Se abre sólo si una de las 3 alertas sobrevive a su medición y necesita el detalle trade-a-trade |
| **`alerts/filters` + POST `alerts/configuration`** (alertas server-side) | **Difiero con condición.** 28 tipos configurables suena a delegar el sondeo — pero mete la lógica de disparo **en el servidor de un tercero**, fuera del repo, sin tests y sin versionado, y `/api/alerts` ya devolvió `{"data":[]}` en el recon. Se reabre **sólo** si el sondeo REST resulta ser el cuello de botella medido, que hoy no lo es (0,47 % de cupo) |

---

## 6. Lo que NO he podido verificar

1. **Latencia intra-sesión: sigue sin medirse.** Mercado cerrado a las 02:45 ET. Todo lo de §2 es
   forma y acceso, **no latencia**. El procedimiento del martes (`UW-FLOW-RECON` §4) sigue en pie
   **menos su paso 5** (websocket, retirado en §3.2). **Añado a ese procedimiento**:
   `net-flow/expiry`, `group-flow/semi/greek-flow` y `greek-flow/{expiry}` — los tres son de
   minuto y ninguno está en el `RTH_SET` de `scripts/uw_endpoint_probe.py` (que no toco: es de
   otro agente).
2. **Si la pared de 90 días es RODANTE o FIJA.** El mensaje dice «currently available». Si rueda,
   el archivo hay que empezarlo **ya** porque marzo se cae por el borde. Si es fija, no corre
   prisa. **Se resuelve con 1 petición dentro de una semana** (pedir 2026-03-24 y ver si sigue
   dando 200). Mientras no se sepa, **asumir que rueda** es la hipótesis segura.
3. **Por qué `net-flow/expiry` y `market-tide` difieren 50× en escala** (§4.4). Sin esto no se
   construye nada encima.
4. **Qué acepta el parámetro `filter` de `flow-per-strike-intraday`** — sin enum en el OpenAPI.
   Es lo que decide si el hallazgo 4.4-bis vive o muere.
5. **Si los campos históricos se REESCRIBEN** (trades anulados/modificados). Crítico para la
   integridad del backfill (§4.1c). Se comprueba descargando la misma sesión dos veces con una
   semana de separación y difiando byte a byte. **Hasta entonces, todo fichero de backfill lleva
   `pull_date` en cabecera.**
6. **`greek-flow/{expiry}` fuera de SPY**: sólo lo he medido en SPY. Antes de diseñar nada hay que
   ver que QQQ/NVDA/MU tienen las mismas 405 filas y no huecos.
7. **`gex-levels` es un solo día y un solo ticker.** La discrepancia del flip (§4.4) **no está
   establecida como sistemática**. 5 sesiones × 35 tickers antes de afirmar nada.

---

## 7. Cuota

| | |
|---|---|
| `x-uw-daily-req-count` al empezar | **566** (cierre del recon anterior) |
| **al terminar** | **706** |
| Gasto de esta segunda pasada | **~140 peticiones** |
| `x-uw-token-req-limit` | **30.000** |
| **% del cupo diario** | **0,47 %** |
| Coste del backfill completo de 90 días (30 syms × 3 series) | **~8.100 = 27 % de UN día** |

**El cupo no es la restricción. La validación estadística sí — pero por primera vez hay muestra
para intentarla.**

---

**Ficheros de esta entrega**: **sólo este documento.** No se ha tocado ningún otro fichero del
repo (los sondeos corrieron desde el scratchpad de sesión; `scripts/uw_endpoint_probe.py` no se
modificó). Nada se ha cableado a la flota. **Es un mapa, no un motor.**
