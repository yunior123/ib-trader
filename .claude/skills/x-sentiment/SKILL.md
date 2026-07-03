---
name: x-sentiment
description: Capturar sentimiento de x.com con la cuenta de Yunior via API (search/recent, OAuth1 de x.env) — presets Corea (SK하이닉스/삼성전자/KOSPI) y tickers de la flota. Usar cuando Yunior pida "sentiment", leer X sobre un ticker, o en noches de earnings coreanos. Cada llamada es una lectura PAGADA — una por pregunta, jamás en loop sin orden.
---

# x-sentiment — sentimiento vía x.com API (medido 2026-07-28)

**Herramienta:** `./venv/bin/python scripts/x_sentiment.py --preset skhynix|samsung|kospi|<SYM>`
(o `--query "..."` libre). Guarda el crudo en `data/x_sentiment/<tag>_<ts>.json` (atómico)
e imprime tally pos/neg/neutro + top-8 por engagement.

## Lo medido (no doctrina)
- **OAuth1 user de `x.env` funciona** para `GET /2/tweets/search/recent` (200, 100 tuits).
  El `X_BEARER_TOKEN` da **401** — no usarlo para search.
- Nitter: muerto (anti-bot Anubis en todas las instancias vivas). Prohibido saltárselo.
- Chrome extension: vale cuando está conectada; la API no depende de eso.
- Probado en vivo 28-jul 20:05 ET: 98 tuits coreanos sobre SK하이닉스 capturados
  **minutos** después del earnings 2Q — utilizable como lectura de reacción inmediata.

## Reglas duras
1. **Cada search = lectura pagada.** Una llamada por pregunta concreta. Jamás en loop/daemon
   sin orden explícita de Yunior con presupuesto acordado. El ledger de posts ($4-5/mes,
   `x_post_common.py`) NO cuenta lecturas — apuntar usos gordos en TODOS.md.
2. **El tally por keywords es un TERMÓMETRO, no una señal.** La lectura de verdad la hace
   Claude leyendo los top tuits (el script los imprime). Sarcasmo/contexto no lo pilla un grep.
3. **Sentimiento = contexto, jamás gatillo.** No dispara órdenes ni alarmas por sí solo
   (SEÑAL-SOLAMENTE + regla "print o nada"). Sirve para: reacción post-earnings, confirmar
   capitulación/manada, y color en planes diarios.
4. Extremos se leen contrarian (ley espada-ballena): euforia unánime = techo local probable;
   pánico unánime + short covering visible = piso probable.

## Recetas de query
- Corea earnings-night: preset `skhynix` / `samsung` / `kospi` (lang:ko, -is:retweet).
- Ticker US: `--preset NVDA` → `($NVDA OR NVDA) lang:en -is:retweet`.
- Afinar: añadir `min_faves:10` para solo tuits con tracción; `since_id` para deltas.

## Cuándo usarla
- Noche de earnings KRX (SK Hynix/Samsung): capturar a los ~5-20 min del release y otra vez
  tras el conference call. Cruzar con `data/bars_skhynix.txt` (puente vivo) — el par
  (sentimiento, precio) es la lectura: miss+verde = ya estaba en precio.
- Yunior pide "sentiment de X sobre <ticker>".
- Confirmación de capitulación (liquidaciones forzadas, margin calls en los tuits = fase final).
