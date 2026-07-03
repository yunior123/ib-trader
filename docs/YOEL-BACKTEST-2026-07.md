# YOEL-BACKTEST-2026-07 — Backtest honesto de la doctrina Yoel Sardinas

**Fecha:** 2026-07-23 · **Generador:** `scripts/yoel_backtest.py` · **Scorer:** `scripts/scorer.py` (unico)
**Datos:** `data/backtest/bars3mo5m_<sym>.csv` — 5m nativo CON volumen, RTH 9:30-15:55 ET.
62 dias (2026-04-23 → 07-22) para la flota; **SPCX 27d, SKHY 9d = series cortas (marcadas)**.
**Horizonte scorer:** 24 barras 5m (2h). **Target/stop:** ±0.35% (35 bps), entrada al OPEN de la
barra siguiente, stop gana empate, spread neto 5 bps/lado. Sin look-ahead.

La condicion de Yunior: *"test antes de conectar; si da resultados, conectar."* Esto es el test.
Doctrina de la casa: **probabilidades MEDIDAS, no las afirmaciones del autor.** El libro dice
">80% fiable" y "88% dentro de 2σ" — aqui **no se asume; se mide.**

---

## 1. Qué se midió y qué se aproximó (honestidad primero)

El libro solo usa 4 herramientas (BB 20/2, medias simples 20/40/100/200, VOLUMEN con MA50,
velas+trendlines), top-down 15m→1H→1D, y opera **opciones semanales con TP +100% de la prima y
SIN stop.** Nada de eso es medible 1:1 sobre el subyacente. Lo medible:

| # | Estrategia libro | Codificación medible | Estado |
|---|---|---|---|
| 3-4 | Rebote punto medio SMA20 (1D) | SMA20 sobre ~1H (bucket epoch%3600); precio en tendencia que TOCA la SMA20 (low≤SMA20≤high o \|c−SMA20\|≤0.2·ATR) sin cerrar del otro lado → LONG/SHORT espejo | `rebote_sma20` |
| 5-6 | Fuera de banda en apertura + VOL>MA50 | Primeras 2 barras RTH; barra ENTERA fuera de BB(20,2) 5m → fade a la media. **A/B: CON y SIN filtro vol>MA50** | `bandopen` / `bandopen_novol` |
| 7-8 | Imán lejos de SMA20 + VOL>MA50 | \|precio−SMA20_1H\| ≥ 2·ATR + vela de reversión → regreso a SMA20. **A/B: CON y SIN filtro vol** | `iman` / `iman_novol` |
| 1-2 | Cambio de tendencia por trendline-break | **APROX**: ruptura del max/min de 12 barras + cruce de SMA20_1H | `trendbreak_aprox` |

**Aproximaciones declaradas:**
- **"1D SMA20" → SMA20 sobre ~1H.** 62 días no dan una SMA20 diaria útil; el 1H captura el mismo
  concepto "toca la media y rebota" a resolución medible. Es el TF que el libro usa para confirmar.
- **Barras 1H por bucket de reloj** (9:30 cae en el bucket 9:00, parcial). El libro dibuja velas 1H
  alineadas a sesión. Aproximación declarada.
- **Target/stop = ±0.35%.** El TP del libro (+100% de prima, sin stop) NO se mide en el subyacente.
  Se usa la convención de scalp de la casa (la misma de flow 62.5% y band-open) para que el WR sea
  **directamente comparable** a los baselines y el A/B de volumen quede limpio.
- **Trendline-break es la pieza más débil** — una recta sobre pivotes no se codifica 1:1; se
  aproxima con ruptura N-barras. Marcado `APROX`; tratarlo como orientativo, no como el patrón del libro.

**Filtro transversal (est 5-8) — la pregunta central de Yunior:** ¿el volumen>MA50 AÑADE edge sobre
el band-open que ya medimos (56%)? Se mide CON y SIN, mismo universo, difieren SOLO en el filtro
(cada bucket con su propio cooldown de 30 min).

---

## 2. Resultados globales vs baselines de la casa

Baselines de la casa: **elastic-1m 58% · band-open 56% · combo 69% · toque-ligero 60%.**

| Estrategia | n | win | loss | tout | **WR** | Wilson lo | PnL med (bps) | neto −5bps/lado | vs baseline |
|---|---|---|---|---|---|---|---|---|---|
| `rebote_sma20` (est 3-4) | 2076 | 993 | 1001 | 82 | **49.8%** | 47.6% | −0.0 | −10.0 | vs toque 60% → **NO** |
| `iman` CON vol (est 7-8) | 3279 | 1525 | 1675 | 79 | **47.7%** | 45.9% | −24.2 | −34.2 | vs elastic 58% → **NO** |
| `iman_novol` SIN vol | 6903 | 3162 | 3415 | 326 | **48.1%** | 46.9% | −14.5 | −24.5 | — |
| `bandopen` CON vol (est 5-6) | 1509 | 577 | 905 | 27 | **38.9%** | 36.5% | −31.8 | −41.8 | vs band-open 56% → **NO** |
| `bandopen_novol` SIN vol | 1523 | 585 | 910 | 28 | **39.1%** | 36.7% | −31.8 | −41.8 | — |
| `trendbreak_aprox` (est 1-2) | 695 | 299 | 374 | 22 | **44.4%** | 40.7% | −27.4 | −37.4 | APROX → **NO** |

**Ninguna estrategia supera su baseline. Todas por debajo del 50% de WR, con Wilson inferior por
debajo del baseline en todos los casos.** El PnL mediano neto de spread es negativo en las cinco.

---

## 3. VEREDICTO CON-vs-SIN volumen (la pregunta de Yunior)

| Estrategia | SIN filtro vol | CON filtro vol>MA50 | Δ WR |
|---|---|---|---|
| Band-open (est 5-6) | **39.1%** (n=1523) | **38.9%** (n=1509) | **−0.2 pp** |
| Imán (est 7-8) | **48.1%** (n=6903) | **47.7%** (n=3279) | **−0.4 pp** |

**Veredicto: el filtro de volumen>MA50 NO añade edge.** En ambas familias el WR con el filtro es
IGUAL o levemente PEOR que sin él, y en ninguna se acerca al band-open medido del 56%. La pieza
"nueva y testeable" del libro (el cruce de volumen sobre su MA50 como gatillo) **no se sostiene en
los datos**: filtra el número de señales a la mitad sin mejorar la calidad. La afirmación del autor
de que el cruce de volumen valida la entrada no se refleja en el WR forward del subyacente.

---

## 4. Detalle por ticker (color, no cambia el veredicto)

Individuos con señal por encima del baseline (n≥15), útiles solo como pistas para estudio futuro,
NO como permiso de conexión (Wilson roza o queda bajo el baseline):

- **`rebote_sma20`**: META 71% (Wilson 60%, n=75) destaca; EWY 60%, STX 60%. Cola: MU 38%, SPCX 35%.
- **`iman`**: SPCX 63% (n=35, serie corta), SPY 57%, AMZN 56%. Cola: NOK 40%, SNDK 36% (n=129).
- **`bandopen`**: NFLX 63% (n=30), GOOGL 57%, AMZN 56%. Cola: STX 16%, SPCX 12% (n=16, serie corta).
- **`trendbreak_aprox`**: NFLX 73% (Wilson 54%, n=27), GLD 67%, NVDA 59%. Cola: XLK 23%, LRCX 22%.

La dispersión es enorme y las colas destruyen el agregado. Ningún ticker con n decente tiene Wilson
que lo separe limpiamente del baseline. **SPCX/SKHY marcados como series cortas** (27d/9d) — sus
números son ruido (SKHY apenas produjo 1-5 señales por estrategia).

---

## 5. VEREDICTO DE CONEXIÓN por estrategia

| Estrategia | Veredicto | Razón |
|---|---|---|
| `rebote_sma20` (est 3-4) | **NO CONECTAR** | WR 49.8% < toque-ligero 60%; moneda al aire, PnL neto negativo. |
| `bandopen` (est 5-6) | **NO CONECTAR** | WR 38.9% << band-open 56%; el fade del gap de apertura con stop apretado pierde. |
| `iman` (est 7-8) | **NO CONECTAR** | WR 47.7% < elastic 58%; el filtro de volumen no ayuda. |
| `trendbreak_aprox` (est 1-2) | **NO CONECTAR** | 44.4%, y además es APROX (no es el patrón real del libro). |
| **Filtro volumen>MA50** | **NO ADOPTAR** | No añade edge (Δ ≤ 0.4 pp, en contra) sobre band-open ni imán. |

**Conclusión.** Bajo nuestra convención de scalp ±0.35% en el subyacente, y con 62 días de 5m, la
doctrina Yoel Sardinas **NO reproduce las tasas que el autor afirma y NO supera ninguno de nuestros
baselines.** La pregunta de Yunior tiene respuesta clara: **el filtro de volumen no aporta.**

**Matiz honesto (no cambia el veredicto):** el instrumento del libro es la OPCIÓN comprada con TP
+100% y sin stop — asimetría convexa que un test de ±0.35% simétrico sobre el subyacente NO captura.
Es posible que la doctrina "funcione" en el P&L de opciones por la cola derecha (pocos aciertos
grandes) aunque el WR direccional del subyacente sea <50%. Eso requeriría un backtest de PRIMAS
(pricing de opciones semanales ATM con decaimiento real), no de barras del subyacente — fuera del
alcance del scorer actual. Con lo medible hoy: **no conectar nada.**

---

## 6. Artefactos

- `scripts/yoel_backtest.py` — generador (ast.parse OK, señal-solamente, degradación limpia).
- `data/backtest/scores_yoel.json` — agregado por estrategia + por ticker + spread.
- `data/backtest/scores_yoel_<estr>.json` — detalle por estrategia (via scorer.py).
- `data/backtest/signals_yoel_<estr>.csv` — señales crudas en formato compartido.
- `data/yoel_probs.json` — WR por estrategia × ticker (para gateo futuro; hoy NINGÚN gate se abre).

---
## ADDENDUM v2 (2026-07-23) — CORRECCIÓN: el target estaba mal, el volumen SÍ aporta

Tras releer el libro (caps X-XII verbatim), el backtest v1 tenía un **desajuste de fondo**: usó target fijo ±0.35% para el efecto imán, pero la tesis LITERAL de Yoel es *"el precio regresa a su media (SMA20)"* — el target del imán es la SMA20, que a ≥2 ATR está 1-3% lejos. Con 0.35% el ruido tocaba el target con o sin volumen, ENMASCARANDO el filtro.

**Re-test fiel (target = SMA20, stop = extremo + 0.5 ATR, horizonte 4h, A/B volumen):**
| Métrica | CON vol>MA50 | SIN vol | Δ |
|---|---|---|---|
| Alcanza la SMA20 completa | 32.1% (n=2698) | 26.8% (n=1651) | **+5.3pp** |
| **Movimiento ≥1.5 ATR a favor en 4h** (≈ +100% en opción ATM) | **47%** | 37% | **+10pp** |
| Expectancy subyacente (R) | −0.12R | −0.15R | — |

**Veredicto corregido:**
1. **El filtro volumen>MA50 SÍ tiene edge** — consistente en ~29/30 tickers, +5pp en alcanzar la media y +10pp en el movimiento favorable. Yoel tenía razón; el v1 fue injusto. **CONECTABLE como filtro de confirmación** (no como señal aislada).
2. **El imán-hasta-la-SMA20-completa sobre el SUBYACENTE es expectancy negativa** (−0.12R) — la media está demasiado lejos para un scalp con stop. NO operar el subyacente así.
3. **El método real de Yoel es la OPCIÓN** (TP +100%, sin stop, prima = pérdida máxima). El 47% de movimiento ≥1.5 ATR a favor CON volumen es un número honestamente favorable para un comprador de opción ATM semanal, pero NO se puede confirmar sin datos históricos de cadena de opciones (pendiente: la grabadora de cadenas acumula desde 2026-07-21).

**Acción**: el filtro volumen>MA50 se propone como gate de confirmación OPCIONAL y aditivo para band_open_watch / señales de imán — mejora medida, degradación limpia. NO se conecta ninguna estrategia como generador de señal standalone (subyacente negativo). Las est. 5-6 (fuera-de-banda apertura) siguen sin poder medirse fielmente: requieren GAP PREMARKET y nuestros datos son RTH-only.

---
## ADDENDUM v3 (2026-07-23) — TEST FIEL: confluencia 3-TF + SIN stop + pago de OPCIÓN

Autor VERIFICADO (Investep Academy, "8 estrategias que generan millones"). Yunior corrigió: hay que juzgar el MÉTODO, no un muñeco de paja. Este test replica su geometría real: tendencia definida en **1H y 1D** (SMA20), gatillo en 5m/15m, **SIN STOP**, aguantando la opción semanal ATM (Black-Scholes, IV = vol realizada) hasta **+100% (su TP)** o vencimiento del viernes. `scripts/yoel_faithful_backtest.py`.

| Estrategia | vol>MA50 | n | P(gana) | Retorno medio/trade | Wilson⌊ |
|---|---|---|---|---|---|
| **rebote_sma20** (corazón, est 3-4) | **CON** | 448 | **56%** | **+14% de la prima** | **51%** |
| rebote_sma20 | SIN | 1503 | 49% | −0% | 47% |
| iman (est 7-8, contra-tendencia) | CON | 2267 | 44% | −8% | 42% |
| iman | SIN | 1158 | 44% | −10% | 41% |

**VEREDICTO CORREGIDO (el justo):**
1. **El rebote-punto-medio — el corazón del libro — es POSITIVO** con la confluencia 3-TF + volumen: **+14% de retorno medio por trade, 56% de aciertos, Wilson 51%** (sobre la moneda al aire). Cuando se prueba como Yoel lo opera, SÍ funciona. Los backtests v1/v2 lo condenaron injustamente (stop que él no usa, un solo TF, subyacente).
2. **El filtro volumen>MA50 es DECISIVO** — convierte 0% en +14%. Tercer test independiente, tercera vindicación.
3. **El efecto imán (contra-tendencia, est 7-8) sale negativo** en opción semanal ATM sintética: el rebote rápido no llega a +100% antes de que el theta se coma la prima. MATIZ: Yoel lo opera con precisión discrecional (aguanta 5 min en el pico exacto, TSLA +$16.700 en 5 min); nuestra versión sistemática no replica ese timing — puede ser fallo nuestro, no del método.

**CAVEATS honestos:** IV sintética (vol realizada, sin skew/term/earnings); el +14% es en múltiplos de prima ANTES del spread bid/ask de la opción (que puede ser ancho — lección DRAM); test con cadena de opciones REAL pendiente en ~3 semanas (grabadora desde 7/21). Fuentes de datos históricos de opción: todas de pago (Polygon $29/mes 15-min delay, ORATS); gratis solo la síntesis BS + nuestra grabadora.

---
## ADDENDUM v4 (2026-07-23) — CON LA BANDA DE BOLLINGER REAL (respuesta a Yunior: "¿tuviste en cuenta Bollinger?")
El v3 aproximó "lejos de la media" con ≥2 ATR — atajo. El libro (cap X) exige la BANDA 2σ real: est 7-8 = "precio COMPLETAMENTE fuera de Bollinger en 15m". v4 usa BB(20,2) poblacional en 15m como gatillo.
| Estrategia (gatillo BB 2σ real 15m) | vol | n | P(gana) | Ret/trade | Wilson⌊ |
|---|---|---|---|---|---|
| **rebote_sma20** (toca banda media + confl. 1H+1D) | CON | 111 | 58% | **+16%** | 48% |
| rebote_sma20 | sin | 594 | 46% | −5% | 42% |
| iman_BB (fuera de banda 2σ + reversión + tendencia) | con | 1849 | 47% | −3% | 45% |
| iman_BB | sin | 811 | 51% | +5% | 48% |
**Refinamiento:** (1) el REBOTE (corazón) sigue positivo con volumen (+16%, robusto vs el +14% del ATR-proxy) — el hallazgo aguanta con la banda real. (2) El IMÁN fuera-de-banda es marginal (~breakeven) y ahí el volumen NO ayuda (incluso resta). (3) El edge del volumen es CONTEXTO-DEPENDIENTE: firme en el regreso a la media (rebote), ambiguo en el fuera-de-banda puro. El cableado en band_open_watch gatea la RE-ENTRADA (regreso a la media = familia rebote) → defendible. Caveats de IV sintética y spread de opción siguen vigentes; test con cadena real pendiente ~3 semanas.

---
## ADDENDUM v6 (2026-07-23) — PRIMAS REALES de Polygon (el test definitivo)
Yunior compró el paquete de opciones de Polygon. `scripts/yoel_real_options_backtest.py` resuelve el contrato ATM semanal REAL de cada señal de rebote fiel (v5: día=tendencia, hora=corrección, toque SMA20 diaria) y baja su camino de prima a 5m — theta y spread reales incluidos.

| Métrica | vol | n | P(gana) | Ret/trade | Wilson⌊ |
|---|---|---|---|---|---|
| Optimista (TP al tocar +100% intradía = auto-sell Yoel) | con | 12 | 67% | +37% | 39% |
| Optimista | sin | 10 | 60% | +22% | 31% |
| **Conservador (TP solo por CIERRE 5m real)** | con | 12 | 50% | **+4%** | 25% |
| Conservador | sin | 10 | 60% | +22% | 31% |

**VERDAD CON DATOS REALES:** (1) La síntesis BS (v3-v5, +38%) era DEMASIADO optimista — con primas reales el rebote es de breakeven a modestamente positivo. El BS no capturaba el theta real ni que muchas semanales van a cero. (2) Ganadores reales +100% (AMD/AVGO/GOOGL/MSFT-put/NVDA/QQQ/TXN) pero perdedores −100% completos (GOOGL/SPY/TSLA calls) — la asimetría sin-stop. (3) El filtro de volumen se vuelve AMBIGUO con data real (conservador 50% con vs 60% sin) — no sostenible en esta muestra. (4) n=22, no concluyente. (5) El edge real de Yoel probablemente vive en su timing/selección discrecional (1-3 a mano/tendencia) que un escaneo no replica. **Pipeline de datos reales queda listo** (`yoel_real_options_backtest.py`) para re-correr con más historia. Nota: revisar el cableado del filtro de volumen en band_open_watch — con data real de opción su edge no se confirma (con data de subyacente sí daba +10pp; la discrepancia importa).
