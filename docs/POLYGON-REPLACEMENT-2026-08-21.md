# Reemplazo gratuito de Polygon OI — 2026-08-21

## ENMIENDA (Yunior 2026-08-21 tarde): 15 min de retraso VALE para la ESTRUCTURA

> *"polygon is 15 min delayed, so other free ones with 15 minutes is fine"*

Polygon Starter — lo que se está reemplazando — **ya era 15 min delayed**. Una fuente gratuita
con 15 min de retraso no es una degradación para el **libro estructural** (OI de apertura,
estructura de cadena, muros, flip). Sigue siéndolo para el **disparo**: spot, NBBO y el PRINT
que confirma un nivel siguen siendo London realtime, sin excepción.

**El retraso viaja EN EL DATO, no en un comentario.** Todo payload de OI publica ahora:

| campo | significado |
|---|---|
| `realtime` | **siempre `false`** en el carril estructural; `attach_oi` RECHAZA un proveedor que no lo declare |
| `structural_delay_minutes` | minutos MEDIDOS, o `None`. **Jamás 0/0.0/15 "porque suele serlo"** |
| `observed_quote_lag_minutes` | el desfase crudo observado, aunque no sea certificable |
| `structural_delay_basis` | `measured_in_session` · `not_measurable_outside_rth` · `unmeasured_public_delayed_feed` · `exchange_published_start_of_day` · `vendor_documented_starter_15min` |
| `delay_policy` | `structural_only_never_fires_an_order` |

`/health` los expone como `oi_realtime`, `oi_structural_delay_minutes`, `oi_delay_basis` y
`oi_provider_order`, así que ningún consumidor puede tratar estructura delayed como realtime.
Fuera de RTH el retraso **no es medible** (regla ya escrita en CLAUDE.md: *"la latencia SOLO se
mide en sesión"*), así que el número pasa a `None` y el lag crudo queda aparte.

### Orden de la cadena: coste primero, luego fiabilidad

`nasdaq` → `cboe` → `tradier` → `databento`. Override: `IBT_FREE_OI_PROVIDERS` (una lista
desconocida **falla cerrada**, no descarta en silencio). Los dos primeros son keyless y cuestan
$0; Tradier necesita un token de desarrollador gratuito; Databento sigue metered con cotización
previa y tope duro de $0.05. Nasdaq sigue siendo el primario: el trabajo verificado del 21-ago
no se toca.

### CBOE: sonda REAL del 2026-08-21 16:04-16:07 ET (mercado recién cerrado)

`GET https://cdn.cboe.com/api/global/delayed_quotes/options/<SYM>.json`, sin clave, 1 petición
por símbolo, con **OI + IV + griegas** en el mismo payload:

| sym | HTTP | bytes | contratos | OI>0 | IV>0 | último trade | **lag medido** |
|---|---:|---:|---:|---:|---:|---|---:|
| QQQ | 200 | 5.361.090 | 12.020 | 9.062 | 11.104 | 15:49:17 | **16,1 min** |
| NVDA | 200 | 1.671.256 | 3.710 | 3.108 | 3.293 | 15:49:32 | **15,9 min** |
| SMH | 200 | 3.339.338 | 7.570 | 5.512 | 6.907 | 15:49:26 | **16,0 min** |
| SPY | 200 | 6.240.822 | 13.980 | 10.466 | 12.456 | 15:49:29 | **15,9 min** |
| TSLA | 200 | 2.517.779 | 5.608 | 4.349 | 4.946 | 15:49:33 | **15,9 min** |
| SPCX | 200 | 1.626.417 | 3.634 | 3.043 | 3.140 | 15:49:26 | **16,0 min** |

**Esto corrige la tabla vieja de AGENTS.md** ("CBOE delayed y DESIGUAL: QQQ 1,8 h · SPX 4,2 h ·
SPY y SMH 21,5 h"). Medido hoy en los seis a la vez: **15,9–16,1 min, uniforme**. La medición
antigua se tomó fuera de sesión, que es exactamente el caso que CLAUDE.md advierte que no
significa nada. CBOE es, medido, **la misma latencia que pagábamos en Polygon Starter**.

Del payload de CBOE se toma **sólo `open_interest`** (cifra de apertura, que un retraso no puede
cambiar). Su IV y sus griegas, que sí son delayed, se **descartan** (`iv: None` contrato a
contrato): London sigue aportando spot y la IV del mismo vencimiento/strike/lado que reprecia la
gamma. Nunca se mezcla medido delayed con medido realtime.

Verificado en vivo con la cadena real (`IBT_FREE_OI_PROVIDERS=cboe,nasdaq`): QQQ 516 contratos y
SMH 296 en 2 vencimientos, `source=cboe_delayed_chain`, `realtime=false`.

### Tradier: NO conectado — requiere Yunior

Sondas literales del 2026-08-21:

- `GET https://sandbox.tradier.com/v1/markets/options/chains?symbol=QQQ&expiration=2026-08-28&greeks=true`
  → **HTTP 401** `Invalid access token`
- lo mismo contra `https://api.tradier.com/v1/...` → **HTTP 401** `Invalid access token`
- `https://developer.tradier.com/user/sign_up` → HTTP 200 pero es una SPA de 577 bytes; su bundle
  (`/assets/index-DzQ2XyzY.js`) ya sólo enlaza a `https://auth.tradier.com/signup` y a
  `api.tradier.com/v2/applications/agreements?key=fee_schedule|options_agreement`
- el alta real es `POST https://p-be-auth.tradier.com/api/register`, **con `captchaToken` de
  reCAPTCHA v3** (site key `6LeQKdgjAAAAAPgIAuTOtUUIGpG-2YF9G_QWctd2` incrustada en
  `auth.tradier.com/js/app.92de7c1a.js`). POST vacío de sonda → **HTTP 400**
  `{"code":400,"status":"BAD_REQUEST","message":"valid Invalid request parameters"}`

**Resolver un CAPTCHA está prohibido y crear la cuenta pasa por agreements de brokerage**, así que
el alta **requiere Yunior**. El carril está escrito, probado y listo: en cuanto exista
`TRADIER_TOKEN` en `config/feeds.env` entra solo, en tercera posición. Sin token falla en voz alta
(`Tradier lane has no configured TRADIER_TOKEN`) y la cadena pasa al siguiente.

### Negativos remedidos hoy (con clave existente donde la había)

| sonda | resultado literal |
|---|---|
| `api.marketdata.app/v1/options/chain/QQQ/` sin token | **HTTP 401** `{"s":"error","errmsg":"Invalid token header. No credentials provided."}` |
| `data.alpaca.markets/v1beta1/options/snapshots/QQQ` sin token | **HTTP 401** `Authorization Required` (nginx) |
| `finnhub.io/api/v1/stock/option-chain` con `FINNHUB_KEY` real | **HTTP 403** `{"error":"You don't have access to this resource."}` |
| `api.nasdaq.com/.../option-chain` (primario) | **HTTP 200**, `rCode 200`, QQQ 872 filas / NVDA 160 filas. Su `lastTrade` sólo trae FECHA (`"LAST TRADE: $713.44 (AS OF AUG 21, 2026)"`), sin minuto → el retraso **no es medible** desde el payload: `structural_delay_minutes = None`, basis `unmeasured_public_delayed_feed` |

Yahoo/yfinance sigue **prohibido por regla del repo**; no se sondeó ni se cableó.

## Decisión implementada para la semana próxima

Polygon queda **OFF por defecto**. El cockpit no consulta su API ni acepta su caché.
El adaptador `scripts/free_oi.py` usa ahora la cadena pública de Nasdaq, sin clave,
cuenta, tarjeta ni pago. Descarga sólo el rango de expiraciones activo y normaliza OI por
contrato; London conserva spot, IV/Greeks y actividad intradía. El 21-ago se verificó el
camino completo en QQQ, NVDA, SMH, SPY, TSLA y SPCX: los seis publicaron
`oi_source=nasdaq_public_option_chain`, `oi_available=true`, Net GEX y flip.

También queda conectado un segundo camino real: si Nasdaq falla, el adaptador usa la clave
Databento que ya estaba configurada en esta instalación para consultar `OPRA.PILLAR / statistics`.
No descarga cadenas completas: convierte exclusivamente los contratos London visibles a símbolo
OCC, cotiza gratis la solicitud, rechaza el conjunto completo si supera **$0.05**, descarga por
lotes y conserva una sola observación final por contrato. La sonda real de un contrato QQQ
devolvió OI oficial; la cotización de los 647 contratos de la captura QQQ fue $0.00763571.
El camino normal sigue siendo Nasdaq y por tanto hace cero llamadas a Databento.

Databento no se presenta como “gratis para siempre”: la cuenta existente usa créditos promocionales,
que el proveedor aplica antes de cargos y que expiran. El saldo sólo se ve en su portal, no por la
API documentada. Por eso esta ruta es un respaldo medido con tope, no una dependencia gratuita
ilimitada. El límite adicional de gasto mensual debe fijarse en el portal de Databento.

La ruta falla cerrada: OI ausente se conserva como desconocido, una expiración sin calls y
puts suficientes invalida la captura, la caché vence a las 36 h, y se exige IV London del
mismo vencimiento/strike/lado antes de calcular gamma. Polygon sólo conserva un rollback
manual con `IBT_ENABLE_POLYGON_OI=1`; no participa en el arranque normal.

Tradier Lite y Alpaca Basic siguen siendo alternativas gratuitas sin mínimo publicado, pero
ambas necesitan que el usuario cree una cuenta/token. No se fingió que estaban conectadas sin
credenciales. Optionwatch y OptionCharts son interfaces, no feeds públicos documentados.
*(Actualización de la tarde: el carril Tradier YA está escrito y probado; sólo falta la cuenta —
ver la enmienda al principio de este documento.)*

Corrección importante: se probó el CSV keyless de OCC y contiene totales agregados de mercado
por categoría, no OI por símbolo/strike. Sirve como control de totales del mercado, pero **no**
puede alimentar paredes ni flip y queda fuera del camino del cockpit.

## Lo que encontré al revisar las alternativas mencionadas

| Servicio | ¿API gratuita utilizable? | OI por contrato | Veredicto |
|---|---:|---:|---|
| [Nasdaq Option Chain](https://www.nasdaq.com/market-activity/stocks/nvda/option-chain) | Sí, endpoint público keyless | Sí | **Primario; conectado y verificado en los seis símbolos.** Sin SLA/API pública documentada: caché y fail-closed obligatorios. |
| [Databento OPRA](https://databento.com/docs/examples/options/equity-open-interest) | $125 de crédito inicial; después medido | Sí, OI oficial | **Respaldo conectado con la cuenta existente.** Sólo contratos London, cotización previa, tope $0.05 y caché. No confundir crédito con gratuidad permanente. |
| [Alpha Vantage Historical Options](https://www.alphavantage.co/documentation/#historical-options) | La documentación muestra OI, IV y Greeks | Sí | La sonda con la clave existente respondió que el endpoint es premium. No utilizable en el plan actual. |
| [Intrinio Options](https://docs.intrinio.com/documentation/web_api/get_options_chain_eod_v2) | Trial/planes | Sí | Las sondas EOD y realtime con la clave existente devolvieron 401: suscripción activa requerida. |
| [Finnhub](https://finnhub.io/docs/api) | Free general, no esta cadena | Sí en producto autorizado | La sonda real de option-chain con la clave existente devolvió 403. Descartado en el entitlement actual. |
| [Optionwatch.io](https://optionwatch.io/) | No API pública documentada | Visible en UI | Buena interfaz gratuita; no construir un daemon contra HTML privado. |
| [option.watch](https://www.option.watch/) | Es frontend BYOD | Según proveedor | Confirma la ruta: para acciones recomienda conectar Tradier; no es un feed independiente. |
| [OptionCharts](https://optioncharts.io/docs) | No API pública documentada | Visible con 15 min de retraso | UI gratis; su propia página reserva descargas para planes de pago. No usar scraping. |
| [OptionWhales API](https://www.optionwhales.io/developers) | Sólo health en Free | OI es Pro+ | Excelente esquema de snapshots AM/PM, pero no reemplazo gratuito. |
| [HF Market Data](https://www.hfmarketdata.io/) | Sí, keyless | Sí, EOD | Prometedor para historia, no para la semana próxima: la sonda del 21-ago devolvió 07-ago como último día para los seis símbolos. |
| [MarketData.app](https://www.marketdata.app/docs/api/options/chain/) | 100 créditos/día | Sí | Free es 24 h retrasado y las cadenas actuales cobran por contrato; insuficiente para seis libros completos. |
| [ThetaData](https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html) | EOD limitado | OI no está en Free | Rechazado para OI gratuito; la tabla oficial reserva el endpoint OI a Value+. |
| [FlashAlpha](https://flashalpha.com/pricing) | 5 llamadas/día | Cotización completa es Growth | Free sirve para probar GEX/metadata, no para seis cadenas diarias. |
| [OptionData](https://www.optiondata.io/option_chain) | Prueba de 14 días | Sí | Beta y luego $599/mes de lista; no es solución gratuita permanente. |
| [Cboe delayed quotes](https://www.cboe.com/delayed_quotes/API/quote_table/) | ~~No automatizable~~ **Sí: el CDN JSON es keyless** | **Sí, + IV + griegas** | **CORREGIDO la misma tarde y CONECTADO como primer fallback.** El que prohíbe autoextracción es el *quote table* de la web; `cdn.cboe.com/api/global/delayed_quotes/options/<SYM>.json` es el mismo endpoint que este repo ya usa en 5 scripts (`poly_chain_archive.py:287`, `vix_feed.py`, `cboe_nbbo_sidecar.py`, `low_iv_hunter.py`, `daily_fleet_plans.py`). Medido hoy: 15,9–16,1 min en los seis símbolos. |
| [Tradier sandbox](https://docs.tradier.com/docs/market-data) | Token de desarrollador gratuito | Sí, + IV/griegas ORATS | **Carril escrito y testeado, sin conectar: el alta pasa por reCAPTCHA v3 + agreements de brokerage → REQUIERE YUNIOR.** Sondas: 401 sin token, 400 en `/api/register`. |
| [MarketData.app](https://api.marketdata.app/) (resonda 21-ago) | No keyless | Sí | **HTTP 401** `Invalid token header. No credentials provided.` |
| [Alpaca options snapshots](https://data.alpaca.markets/) (resonda 21-ago) | No keyless | Sí | **HTTP 401** `Authorization Required`. Requiere cuenta Alpaca → requiere Yunior. |
| [OCC Daily Open Interest](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest) | Sí, CSV keyless | **No; sólo agregados** | Verificado y descartado para paredes/flip. |

## Contrato mínimo del adaptador

El proveedor nuevo debe normalizar cada fila a:

```json
{
  "expiry": "YYYY-MM-DD",
  "strike": 0.0,
  "right": "call|put",
  "open_interest": 0,
  "oi_date": "YYYY-MM-DD|null",
  "source": "nasdaq_public_option_chain|cboe_delayed_chain|tradier|databento_opra_statistics"
}
```

y la CABECERA del payload debe declarar su retraso, o `attach_oi` lo rechaza:

```json
{
  "realtime": false,
  "structural_delay_minutes": 15.0,
  "observed_quote_lag_minutes": 15.0,
  "structural_delay_basis": "measured_in_session",
  "delay_policy": "structural_only_never_fires_an_order"
}
```

La gamma se reprecifica con spot/IV London; jamás se aceptará un GEX agregado opaco del
proveedor como sustituto de la cadena. El adaptador debe cachear OI una vez por sesión,
publicar edad/cobertura/proveedor y fallar a `DATA`, no a cero.

## Fuentes oficiales

- Databento: [ejemplo oficial de OI OPRA](https://databento.com/docs/examples/options/equity-open-interest),
  [API histórica y cotización](https://databento.com/docs/api-reference-historical),
  [créditos y cobro](https://databento.com/docs/faqs/usage-pricing-and-data-credits) y
  [límites del portal](https://databento.com/docs/portal).
- Tradier: [cadena](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains),
  [campos de quote](https://docs.tradier.com/docs/quotes),
  [tiempo real vs. retrasado](https://docs.tradier.com/docs/market-data),
  [límites](https://docs.tradier.com/docs/rate-limiting) y
  [precio Lite/API](https://production.tradier.com/individuals/pricing).
- Alpaca: [contratos y `open_interest_date`](https://docs.alpaca.markets/us/docs/options-trading)
  y [plan Basic](https://docs.alpaca.markets/us/docs/about-market-data-api).
- OCC: [descarga diaria de OI](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest).

## Comentarios de usuarios revisados (sólo descubrimiento)

Los comentarios de comunidad coinciden con las sondas, pero no se usaron como contrato técnico:
usuarios reportan que Alpha Vantage exige premium para cadenas futuras y que Tradier suele quedar
ligado a una cuenta brokerage para datos útiles. Otros mencionan Yahoo/yfinance como salida gratuita;
esa ruta no se activó porque las reglas de este repositorio prohíben feeds Yahoo/retrasados en el
camino de señales. Referencias: [discusión Alpha Vantage/yfinance](https://www.reddit.com/r/algotrading/comments/1il526e/looking_for_options_data_but_free_does_it_exist/),
[discusión Tradier](https://www.reddit.com/r/options/comments/i61x9h) y
[discusión Databento/Tradier/Alpaca](https://www.reddit.com/r/options/comments/1q2er27/automation_for_0dte/).
