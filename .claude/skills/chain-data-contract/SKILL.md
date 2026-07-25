---
name: chain-data-contract
description: "Contrato de datos de opciones: la banda ATM de IBKR (2 vencimientos, ±1.45% real, modo narrow silencioso) frente al snapshot completo de Polygon, greeks_ok_pct, la TRAMPA de ?as_of=, inversion de IV solo en RTH, y por que la historia de OI/IV NO se puede rellenar hacia atras. Usar cuando se toque opt_chain_cache, gex_core.from_ibkr_cache, cualquier consumidor de griegas, o se sospeche que un mapa gamma esta truncado."
---

# chain-data-contract — de donde salen las griegas, y donde MIENTEN

Todo numero gamma que publicamos sale de una de dos fuentes con propiedades OPUESTAS. Confundirlas
produce mapas que miden la forma de nuestro fetcher en vez del libro.
Fichas 5, 7, 17 y 19 de `docs/FEATURES-MINED-2026-07-25.md`.

## 1. Las dos fuentes, medidas hoy (2026-07-25, con la key real)

| | **IBKR** `data/opt_chain_<sym>.txt` | **Polygon** `/v3/snapshot/options/{SYM}` |
|---|---|---|
| Cobertura | **2 vencimientos**, banda ATM | **todo strike y todo expiry** |
| Banda real | `PCT_BAND=0.06` anunciado, **±1.45% MEDIDO** (QQQ: 80 filas 680–699 con spot 689.98) | completa |
| Griegas | **NVDA 0/40 filas con IV. SPY 1/80.** Fuera de RTH: nada | **QQQ 854 contratos, 816 con griegas (95.5%), 706 con OI** |
| IV | `modelGreeks.impliedVol` (salida de modelo suavizada, ausente fuera de RTH) | `implied_volatility` por contrato |
| OI | cierre previo, **CONGELADO intradia** | `open_interest` |
| Latencia | vivo, ciclo ~157 s | snapshot |
| Historia | no | **NO — ver seccion 2** |

**Reparto de trabajo, no negociable:**
- **IBKR sirve la banda ATM VIVA** y nada mas.
- **Todo nivel ESTRUCTURAL** (vol-trigger, pin/max-pain, cuotas de expiry, 25Δ RR, mapa del dia
  siguiente, `book_pctile`) se computa **DEL SNAPSHOT DE POLYGON SOLAMENTE**. Con la banda IBKR el
  max pain se sesga hacia el spot **mecanicamente** y `gross` es un artefacto de la ventana.

## 2. `?as_of=` ES UNA TRAMPA (lo mas importante de esta skill)

```
GET /v3/snapshot/options/QQQ?as_of=2026-07-10
→ 200, "status": "OK"   ... y sirve la cadena de HOY. IGNORA la fecha.
```
**No hay error. No hay aviso.** Si se construye historia con eso se obtienen **250 copias del dia
de hoy con fechas distintas**: un backtest que "funciona" y es **ficcion pura**, del peor tipo,
porque el look-ahead es perfecto y silencioso.

Corolarios duros:
- **No existe historia de OI/IV a ningun precio en este plan.** Griegas reales solo **hacia
  adelante**, desde el primer snapshot archivado.
- Los **aggs de opciones NO traen OI ni griegas**: `poly_opt_bars` es `otk,sym,exp,strike,right,
  ts,o,h,l,c,v` — 114.337 filas, 22 dias, **cero IV, cero griegas**.
- Para el PASADO: **invertir IV por biseccion y calcular griegas por Black-Scholes**
  (`gex_core.bs_gamma`/`bs_vanna`/`bs_charm`, skill `option-pricing-pro`), y el OI **no existe** →
  o proxy **marcado como proxy en el propio dato** (`oi_source`), o no se afirma.
- **JAMAS mezclar reconstruido con medido sin decirlo en la cabecera del fichero.**
- `poly_bars` (equity, 1m) SI es backfilleable: hoy **21 sesiones** (24-jun → 23-jul), 493.359
  filas × 30 syms, mientras ~10 features pedian **250 sesiones**. Ver la regla de gobernanza en
  [[measured-probability]].

## 3. `chain_full_snap` — el snapshot nocturno (forward-only)

15:58 y 20:30 ET, 30 syms, paginado `limit=250` siguiendo `next_url`.

1. Guardar por contrato: `ticker, expiry, strike, right, open_interest, day.volume, day.close,
   implied_volatility, last_quote bid/ask`.
2. **ALMACENAR sus griegas pero NUNCA consumirlas** — verificado basura: delta deep-ITM
   `0.99996`, gamma `−1.4e−09`. **RE-DERIVAR** gamma/vanna/charm/delta con `gex_core.bs_*` desde
   **SU** `iv`, nuestro `r=0.045` y `T` de `gex_core._T_of`.
3. **Sonda de entitlement diaria**: no-200 o 0 contratos → **fail loud** (banner + ntfy) y la
   fecha se marca como ausente. `/v3/trades/O:` y `/v3/quotes/O:` son **NOT_AUTHORIZED** (por eso
   HIRO esta fuera de alcance, ver [[dealer-flow-limits]]).
4. Salida: `data/history/<date>/chain_full_<sym>.jsonl.gz` (crudo borrado a 45 dias) +
   `trades.db gex_daily(...)` por-strike para los 3 expiries frontales, agregado mas alla.
5. Si la sonda falla, se reutiliza la estructura de ayer **etiquetada `stale=1`** — nunca en
   silencio.

## 4. `chain-honesty` — matar las degradaciones silenciosas

Todo numero gamma de hoy **puede estar computado desde un `iv=0.3` FABRICADO**, sobre una banda
silenciosamente estrechada, con 0/40 griegas reales.

1. **BORRAR el fallback `iv=0.3`** en `gex_core.from_ibkr_cache`. Un contrato con `iv ≤ 0` queda
   **EXCLUIDO y contado**. (Regla de la casa: un `except` en camino de señal devuelve `None` o
   levanta — **prohibido devolver 0, 0.0, 0.5, 50 o {}**. Un numero plausible convierte "no se"
   en "se, y es cero".)
2. Cabecera obligatoria por fichero de cadena:
   ```
   # sym=X spot=Y ts=EPOCH band=0.06|0.04 max_strikes=20|12 narrow=0|1 exps=E1,E2[,E3] rows=N greeks_ok_pct=NN stale=0|1
   ```
   Campos **append-only**. **Las columnas por fila JAMAS se reordenan**: `scripts/opt_quick.cpp`
   parsea **POSICIONALMENTE** y las lineas `#` deben saltarse. Contrato en `docs/CHAIN-HEADER.md`.
3. **Inversion de IV** (biseccion sobre el mid, 60 iteraciones, tol `1e-6`, forward por paridad
   put-call, `r=0.045`) permitida **SOLO** con `bid>0 y ask>0 y RTH`. Fuera de eso `iv=null` y
   `stale=1`. Razon medida: **a las 16:16 bid/ask son `-1.00`** — una biseccion sobre ESE mid seria
   una mentira mas convincente que el bug que reemplaza.
4. El conjunto **NARROW** ahora es VISIBLE: `opt_chain_cache.py` usa `PCT_BAND=0.06`,
   `NARROW_BAND=0.04`, `MAX_STRIKES=20`, `NARROW_MAX_STRIKES=12`, `CYCLE_S=180`,
   `NARROW={MSFT, AVGO, AMZN, META}`. **Cualquier feature que reclame "±6%" debe leer `band` de la
   cabecera**, no el constante.

## 5. La puerta `greeks_ok_pct` — tabla de decision

| `greeks_ok_pct` | Que se publica | Que se dice |
|---|---|---|
| ≥ 0.5 | claves gamma normales | normal |
| **< 0.5** o `stale=1` | claves gamma **`null`** | *"libro sin griegas"* — **sin voz gamma, sin ticket de muro, sin factores gamma en la flecha** |

Consumidores obligados a leerlo: `chart_levels`, `direction_view`, `daily_fleet_plans`,
`opt_quick.cpp`, `compass`. Estado esperado: **~1.0 en RTH, 0.0 despues de las 16:00.**
Se cruza con el label de [[book-quality-veto]] (`THIN` si `greeks_ok_pct < 0.5`).

## 6. `cube-widening` — ensanchar sin romper el ciclo (solo tras la §4)

Secuencia ESTRICTA:
1. **Medir el techo real de lineas de market-data** de la cuenta viva contra las ~90 que
   `ibkr_bar_bridge` ya sostiene (3/sym) mas la rafaga del fetcher.
2. `exps = sorted(...)[:2]` **+ el monthly del 3er viernes mas cercano**, para **CUATRO syms
   SOLAMENTE (QQQ, SPY, NVDA, MU)**.
3. Strikes: los **14 mas cercanos** MAS **cada 3er strike** hasta el `PCT_BAND=0.06` real →
   **identico conteo de lineas, colas reales**.
4. **ASERCION DURA `cycle ≤ 170 s`** (hoy ~157 s con 17 syms). Si se rompe: **partir en dos
   daemons escalonados**, jamas tirar simbolos en silencio.
5. Flag `artifact=1`: muro presente en 0DTE pero **ausente** en weekly+monthly → se dibuja
   **discontinuo y NUNCA se canta**. Los muros **estructurales** (en todos los expiries traidos)
   pueden servir de nivel de swing. **Descriptivo solamente** hasta `n ≥ 60` expiries.

Fallback honesto si IBKR aprieta: monthly para **QQQ y SPY solamente**.

## 7. `iv_hist logger` — el unico camino a features de skew en 2027

Nocturno desde `chain_full_snap`, por sym × expiry (weekly frontal, weekly siguiente, monthly
frontal). Coste cero, sin voz, sin factor, sin linea de chart.

- `iv_atm` en el strike mas cercano al spot.
- IV a `|delta| = 0.25` **interpolada monotonamente en espacio delta** (lineal en log-moneyness)
  entre los dos contratos que lo bracketean. Si 0.25 cae **FUERA** del rango disponible → `NULL`
  y `extrapolated=1`. **JAMAS extrapolar.**
- `rr = iv_25p − iv_25c` · `smile_slope = (iv_25p − iv_atm)/0.25` · `term = iv_front − iv_next`.
- `iv_rank` = percentil de `iv_atm` en sus propias 252 filas previas → **`NULL` hasta `n ≥ 60`**.
- **`iv_src` siempre registrado** (`'polygon_snapshot'` vs `'ibkr_model'`) y **las dos series
  JAMAS se mezclan en una sola**: la de IBKR es una salida de modelo suavizada y ausente fuera de
  RTH; la de Polygon es del snapshot. Mezclarlas fabrica una serie que no existio nunca.

Sanidad, no calibracion: el `iv_atm` de Polygon dentro de **3 puntos de vol** del modelo IBKR en
RTH sobre strikes solapados.

## 8. Retencion y presupuesto (el Mac de 8 GB manda)

| Dato | Retencion |
|---|---|
`gex_cube` filas crudas por-strike | **30 dias**, luego colapso a `gex_snap` indefinido |
ficheros de texto de cadena | gz tras la carga, borrado a **45 dias** |
`chain_full_<sym>.jsonl.gz` crudo | 45 dias (sin comprimir serian ~4.5 GB/mes) |
`iv_hist` | **indefinido** (~90 filas/noche) |

Aserciones que **fallan en voz alta y ABORTAN el cargador**: `trades.db > 400 MB` (las barras 1m
a un `bars.db` adjunto) o `data/history > 3 GB`. Ver [[sample-integrity]].
Tras la carga, **ninguna feature lee los ficheros de texto planos directamente** — fuente unica.

## 9. Al hablar

- Nunca decir "el mapa gamma de <sym>" sin saber `band`, `exps` y `greeks_ok_pct`. Un mapa de
  ±1.45% con 2 expiries **no es el libro**, es una ventana.
- Toda cabecera de fichero derivado dice su fuente: `polygon_snapshot` / `ibkr_model` /
  `bs_reconstruido` + `oi_source`.
- **SEÑAL-SOLAMENTE**: este contrato mueve bytes y marca honestidad; no ordena nada.
