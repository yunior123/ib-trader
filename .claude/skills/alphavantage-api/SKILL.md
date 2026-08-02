---
name: alphavantage-api
description: Alpha Vantage API para la flota ib-trader — SOLO fallback de barras DIARIAS (TIME_SERIES_DAILY funciona en free); el intradía 1m es PREMIUM (inservible para flota 1m). Usar cuando se hable de Alpha Vantage, ALPHAVANTAGE_KEY, un fallback de datos diarios/EOD, o antes de proponerlo para tiempo real (NO sirve). SEÑAL-SOLAMENTE.
---

# alphavantage-api — fallback DIARIO, nunca realtime (2026-08-01)

Fuente única de verdad de latencia: IBKR>Polygon>CBOE ([[data-source-latency]]). Alpha Vantage
entra **por debajo de todo eso**: solo como respaldo de barras **diarias/EOD**. **No dispara nada.**

## Qué sirve y qué NO (MEDIDO 2026-08-01)
- **`TIME_SERIES_DAILY` — SÍ en free tier.** Barras OHLCV diarias. `outputsize=compact` (100
  últimas) en free; `outputsize=full` es PREMIUM.
- **`TIME_SERIES_INTRADAY` (interval=1min) — PREMIUM.** Con key free devuelve un nodo
  `"Information": "...premium endpoint..."` en vez de datos → **cero barras 1m**. Inservible para
  la flota, que exige barras 1m ([[fleet-two-universes]]: sin barras no hay voto). No lo cablees
  como fuente de flota jamás.
- **`GLOBAL_QUOTE` — SÍ en free**, pero es quote **retrasado 15 min** (realtime = premium+
  `entitlement=realtime`). Peor que Polygon; no aporta.
- Free tier: **~25 requests/DÍA, 5/min.** Con 30 tickers un solo refresh diario ya roza el techo.
  Es un balde de una tarea nocturna, no de un daemon.

## Endpoints (verificado en docs oficiales)
Base: `https://www.alphavantage.co/query?function=<F>&...&apikey=<KEY>`
```
TIME_SERIES_DAILY      &symbol=IBM&outputsize=compact&datatype=json   # free
TIME_SERIES_INTRADAY   &symbol=IBM&interval=1min&outputsize=compact   # PREMIUM (free = Information note)
GLOBAL_QUOTE           &symbol=IBM                                     # free, 15-min delayed
```
- Respuesta DAILY: top-level `"Meta Data"` + `"Time Series (Daily)"` (dict fecha→{`1. open`,`2. high`,
  `3. low`,`4. close`,`5. volume`}).
- Entitlement: `entitlement=realtime|delayed` solo aplica a keys premium; en free se ignora.

## GOTCHA — el error de forma que engaña (regla anti-cero-plausible)
Alpha Vantage responde **HTTP 200 con un JSON de "error"** en estos casos, no un status code:
- `"Note"` / `"Information"` = límite diario/minuto agotado, o endpoint premium.
- `"Error Message"` = símbolo inválido o parámetro malo.
Un parser que hace `.get("Time Series (Daily)", {})` sobre eso devuelve `{}` en silencio →
denominador fabricado ([[python-is-dangerous-cpp-default]]). **Si falta la clave de datos, LEVANTA
`ProviderError` con el texto de `Note`/`Information`/`Error Message`. Jamás `{}` ni barras vacías.**

## Adaptador — NO EXISTE aún
Patrón self-registering: soltar UN fichero
`/Users/yuniorrodriguezosorio/ib-trader/mit/backend/app/providers/alphavantage.py` con
`@register("alphavantage")`. El `_discover()` de `providers/registry.py` lo importa solo; no se
toca registry ni config. Copiar la forma de `providers/polygon.py`:
- clase `class AlphaVantageProvider(MarketDataProvider)`, `name = "alphavantage"`,
  `__capabilities__ = {"market"}` (SOLO market; sin options/flow/depth — no los da).
- `httpx.AsyncClient(base_url="https://www.alphavantage.co", timeout=30)`.
- Key desde `feeds.env` → `ALPHAVANTAGE_KEY` (añadir `alphavantage_api_key` a `Settings`, como
  `polygon_api_key`). **Jamás la key en el skill ni hardcoded.** Si falta, `raise ProviderError`.
- `get_bars`: mapear solo `interval in {"1d","d","1day"}` → `TIME_SERIES_DAILY`; para intradía
  levantar `ProviderError("Alpha Vantage intraday es premium — usar IBKR/Polygon")` (fail-loud, no
  intentar y devolver vacío).
- Chequear `Note`/`Information`/`Error Message` ANTES de parsear (ver GOTCHA).

## Veredicto
Es un fallback EOD barato para backfill diario cuando yfinance/Polygon fallan — nada más. **No es
candidato para tiempo real ni para la flota 1m.** Antes de proponerlo para algo vivo: no.
