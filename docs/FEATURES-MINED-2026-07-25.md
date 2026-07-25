# FEATURES MINADAS — SpotGamma × TrendSpider × MenthorQ (2026-07-25)

**Qué es esto.** Minado sistemático de las tres plataformas de pago (SpotGamma, TrendSpider,
MenthorQ) buscando lo que se puede **implementar en ib-trader** con los datos que ya pagamos.
13 agentes, ~1.6M tokens: 6 dossiers de fuente (en `docs/research/`), 3 diseños por plataforma
(41 candidatos: 13 TrendSpider + 14 MenthorQ + 14 SpotGamma), y una auditoría estadística/operativa
que mató 16 y degradó la mayoría de los supervivientes.

**Resultado: 30 features vivas, 16 muertas con refutación numérica, 13 skills nuevas.**

**Conclusión general del minado** (detalle en `docs/research/README.md`): los NIVELES de las tres
plataformas son **matemática de commodity** — reproducibles desde un snapshot de cadena con OI +
griegas. Lo único genuinamente caro es **HIRO** (cinta OPRA completa con tamaños + NBBO), y está
**fuera de alcance verificado**: `/v3/trades/O:` y `/v3/quotes/O:` devuelven `NOT_AUTHORIZED`.

---

## Cómo leer una ficha

Cada feature trae: **de dónde viene** (plataforma + feature concreta), **el edge en una línea**,
**la matemática en pasos** (implementable sin más investigación), **inputs EXACTOS** de nuestro
stack (fichero/tabla/función real), **output** (forma JSON + dónde se escribe + cómo se
superficia), **decision rule** con los gates que debe pasar, **validación** (diseño del backtest +
umbral keep/kill), **effort / lenguaje / fichero destino / kill-risk / skill / veredicto / ola**.

`KEEP` = el diseño sobrevivió intacto. `DEGRADED` = sobrevive con partes explícitamente amputadas
(y esas amputaciones están escritas en la ficha, no borradas).

**Ley que aplica a las 30**: SEÑAL-SOLAMENTE. Ninguna feature de esta lista ordena al broker.
El único módulo autorizado a ordenar es `order_engine/` (ENMIENDA 2026-07-24), y ninguna de estas
30 lo alimenta con órdenes automáticas — como máximo condiciona un ticket que el humano arma.

---

## LÍMITES DE DATOS MEDIDOS HOY (2026-07-25) — condicionan todo lo de abajo

Cuatro hechos verificados con la key y con el repo. Cualquier plan de validación que los ignore
es astrología:

1. **Polygon da griegas + IV + OI DIRECTAS** en `GET /v3/snapshot/options/{SYM}` — verificado
   200 con `greeks{delta,gamma,theta,vega}`, `implied_volatility`, `open_interest`,
   `day{volume}` para **todo strike y todo expiry**.
2. **`?as_of=` es una TRAMPA**: devuelve `status: OK` e **IGNORA la fecha**, sirviendo la cadena
   de HOY. No hay error, no hay aviso. → **No existe historia de OI/IV a ningún precio en este
   plan.** Griegas reales solo del snapshot **hacia adelante**; para el pasado, BS + inversión
   de IV y OI proxy **marcado como proxy**.
3. **Los aggs de opciones NO traen OI ni griegas** (`poly_opt_bars`: `otk,sym,exp,strike,right,
   ts,o,h,l,c,v` — 71.679 filas, 6 syms, cero IV, cero griegas).
4. **`poly_bars` tiene 21 sesiones** (24-jun → 23-jul) mientras **~10 features pedían 250
   sesiones**, 200 eventos de earnings o retornos forward a 60 días. Esto es exactamente por qué
   la feature #4 existe y por qué es una **regla de gobernanza**, no una feature más.

Corolario duro: **ninguna feature publica una probabilidad cuyo plan de validación reclame ≥60
sesiones hasta que `data/backfill_report.json` demuestre que esa muestra existe** para los syms
implicados.

---

## TABLA MAESTRA (30, en orden de rank)

| # | Feature | Plataforma origen | Efc | Lang | Skill | Veredicto | Ola |
|---|---|---|---|---|---|---|---|
| 1 | barrier-labels | TrendSpider (ML Quant Lab labels) | S | Python | measured-probability | KEEP | 1 |
| 2 | null-control | TrendSpider (Random Control) + MQ #3 | S | Python | measured-probability | KEEP | 1 |
| 3 | book-quality gate | MenthorQ #2/#7 + SG #4 Impact | S | Python | book-quality-veto | KEEP | 1 |
| 4 | poly-aggs-backfill | (forzada por la auditoría) | M | Python | measured-probability | KEEP | 2 |
| 5 | chain-honesty | MQ #13 paso 1 + SG P0b | S | Python | chain-data-contract | DEGRADED | 1 |
| 6 | flip-honesty + freeze 09:35 | MenthorQ #2 + SG #2 | S | Python | flip-and-vol-trigger | DEGRADED | 1 |
| 7 | chain_full_snap | SpotGamma P0a | M | Python | chain-data-contract | DEGRADED | 2 |
| 8 | level-react + level_events | TS #2 + MQ #10 + MQ #3 | M | **C++23** | print-o-nada-levels | DEGRADED | 2 |
| 9 | truth-lock | TrendSpider #6 | S | Python | sample-integrity | DEGRADED | 1 |
| 10 | em-envelope (determinista) | MenthorQ #12 + SG #9 | M | Python | expected-move-envelope | DEGRADED | 1 |
| 11 | features-fanout + tope 14 | (condición transversal) | M | Python | direction-view-architecture | KEEP | 1 |
| 12 | voice-budget governor | (condición transversal) | S | Bash+Py | alert-budget | KEEP | 1 |
| 13 | next-day-map roll-off | MenthorQ #12 | M | Python | pin-and-expiry-mechanics | DEGRADED | 1 |
| 14 | pin-clock (max pain) | SpotGamma #11 | S | Python | pin-and-expiry-mechanics | DEGRADED | 1 |
| 15 | equity-prints archiver | TrendSpider #5 | S | Python | sample-integrity | DEGRADED | 1 |
| 16 | chain-cube archive + retención | MQ #1 + TS #1 | M | Python | sample-integrity | DEGRADED | 1 |
| 17 | iv_hist logger | SG (Compass/IV-Rank, no propuesto) | S | Python | chain-data-contract | KEEP | 1 |
| 18 | levels-5min archive | SpotGamma #7 (solo el enabler) | S | Python | sample-integrity | DEGRADED | 1 |
| 19 | cube-widening (4 syms) | MenthorQ #13 pasos 3-4 | M | Python | chain-data-contract | DEGRADED | 2 |
| 20 | vol-trigger congelado | SpotGamma #2 | M | Python | flip-and-vol-trigger | DEGRADED | 2 |
| 21 | wall-decay ledger | SG #3 + MenthorQ #4 | M | Python | book-quality-veto | DEGRADED | 2 |
| 22 | chain-delta engine | SG #1 + TS #1 + MQ #1 | M | Py→C++ | dealer-flow-limits | DEGRADED | 3 |
| 23 | cor-fleet | SpotGamma #8 (COR1M) | S | Python | peer-captain-evidence | DEGRADED | 2 |
| 24 | close-drift (DEX + charm) | SG #6 + MenthorQ #9 | M | Python | pin-and-expiry-mechanics | DEGRADED | 3 |
| 25 | expiry-unwind | SpotGamma #12 | M | Python | pin-and-expiry-mechanics | DEGRADED | 2 |
| 26 | gap-islands (exportador) | TrendSpider #12 | S | Python | print-o-nada-levels | DEGRADED | 2 |
| 27 | kde-levels | TrendSpider #8 (mitad KDE) | S | Python | print-o-nada-levels | DEGRADED | 2 |
| 28 | skew-lead (25Δ RR) | MenthorQ #5 | S | Python | dealer-flow-limits | DEGRADED | 3 |
| 29 | peer-weights hardening | TS #10 + MQ #6 + MQ #11 | S | Python | peer-captain-evidence | DEGRADED | 2 |
| 30 | finviz-snap + componentes | SpotGamma #14 | S | Python | anti-overfit-killlist | DEGRADED | 2 |

---

# LAS 30 FICHAS

---

## 1. `barrier-labels` — etiquetas de triple barrera + walk-forward purgado

**Origen**: TrendSpider, *ML Quant Lab* — su definición de etiqueta es binaria "¿toca TP antes de
SL en X velas?" con modos `Conservative` (SL nunca tocado) vs `Aggressive`. Es una etiqueta MEJOR
que la nuestra. Su agujero metodológico documentado (no hacen purged CV) **no** lo copiamos.

**Edge (una línea)**: arregla el DENOMINADOR de todas las probabilidades que ya cantamos — las
etiquetas por retorno-a-horizonte cuentan como ganadas señales que fueron **stopeadas en el
camino**, así que nuestros win rates son optimistas por una cantidad no medida.

**Matemática, en pasos**
1. `ATR14(1m)` Wilder por sym desde `poly_bars`.
2. Para cada fila de `trades.db signals(id, ts, sym, source, direction, price)`:
   `TP = entry + k_tp·ATR·dir`, `SL = entry − k_sl·ATR·dir`.
   Barrido: `k_tp ∈ {0.5, 0.75, 1.0, 1.5}`, `k_sl ∈ {0.5, 0.75, 1.0}`, `H ∈ {10, 30, 60, 120}` min.
3. Recorrer la ruta 1m `t+1 … t+H`: `label=1` si TP toca primero, `0` si SL primero,
   **`NULL` en timeout — el timeout NO es una victoria** (esta es la clase de bug que arregla).
   Barra que contiene TP **y** SL = ambigua → se resuelve **SL primero** (conservador) y se
   incrementa un contador publicado como `ambig_pct`.
4. Registrar `MFE` (máxima excursión favorable / ATR), `MAE` (adversa), `t_touch` en minutos.
5. Walk-forward con **purging + embargo**: se descarta toda observación de entrenamiento cuyo
   `[t, t+H]` solape el bloque de test; embargo = `H` barras después de cada bloque de test.
   Alimenta `scripts/fleet_wfo.py`.

**Inputs exactos**: `trades.db signals` (3233 filas / ~972 señales únicas, 8 fechas),
`poly_bars` (1m, 21 sesiones hoy), `data/hist/bars_*_1m_30d.txt` (3 syms),
`data/backtest/bars3mo5m_<sym>.csv` (62 sesiones @5m para variantes de H largo).
Extiende `scripts/calibration_ledger.py` (`wilson`/`record`/`grade`).
**FALTA**: ruta sub-1m → proxy de barra ambigua resuelto SL-primero, con la tasa publicada.

**Output**: `trades.db barrier_outcomes(signal_id, sym, source, k_tp, k_sl, H, mode, label, mfe,
mae, t_touch, ambig)` con retención 365 días; agregado a `data/calibration.json` vía
`calibration_ledger.record()`; la **tabla delta** (WR viejo por horizonte vs WR por barrera, por
fuente) a `docs/EDGE-SCOREBOARD-<fecha>.md`. Se superficia como la `prob` de cada flecha y como
los números del bracket en el PDF diario: *"stop 0.75 ATR, objetivo 1.0 ATR, p=0.41 [0.36–0.47],
n=822"*.

**Decision rule**: ninguna señal se canta con probabilidad si su bucket etiquetado por barrera no
tiene **n ≥ 50 observaciones efectivas**. El `(k_tp, k_sl, H)` elegido por fuente es el que
maximiza el **Wilson-LB de la EXPECTANCIA**, no del win rate; si el CI de expectancia de la mejor
celda incluye 0 → esa fuente es **NO-TRADE**. Los percentiles MFE/MAE se convierten en el bracket
de `order_ticket` ("cobra en el imán" = MFE p60).

**Validación**: *es* el validador. El entregable = el delta de WR contra
`backtest_signal_outcomes` (prior: bollinger h=15 → **0.436 con n=822**, se espera **0.38–0.41**
real; whale h=15 → 0.357 con n=112) más `ambig_pct`. **Kill** solo si el reetiquetado no cambia
el WR de ninguna fuente en >2pp — lo que sería en sí mismo un hallazgo (los stops no se tocaban
nunca en el camino).

**Effort** S · **Lang** Python · **Destino** `scripts/barrier_labels.py` (nuevo) + ediciones a
`scripts/calibration_ledger.py`, `scripts/eod_backtest.py`, `scripts/fleet_wfo.py`
· **Skill** [[measured-probability]] · **Veredicto KEEP** · **Ola 1**

**Kill-risk**: solo 8 fechas de señales y 21 sesiones de 1m, así que casi toda celda
`(source × k × H)` queda DATA-INSUFFICIENT; la salida honesta es "todavía no sabemos" para todo
menos bollinger.

---

## 2. `null-control` — null de entrada aleatoria + null de 16 niveles aleatorios

**Origen**: TrendSpider, *Price Behavior Explorer* → su columna **"Random Control (Mean)"**: el
resultado medio de posiciones abiertas al azar en la misma muestra; una estrategia que no lo bate
no tiene timing. Fusionado con el **null de niveles aleatorios** de MenthorQ #3 (level-calibration).

**Edge**: es la única feature cuya salida es **una resta** — retira fuentes que ya están por
debajo de la moneda (whale 0.357, bollinger h=5 0.402) en vez de añadir otra opinión, y es la
única defensa contra que 30 features nuevas sean una catástrofe de multiple testing.

**Matemática, en pasos**
- **A) Null de entrada aleatoria.** Por fuente (`signal, bollinger, cusum, whale, flow,
  structural, dip`): tomar las entradas realizadas; generar `N=2000` entradas sintéticas
  emparejadas en sym, bucket horario (los buckets de `scripts/timeofday_calib.py`) y distribución
  de holding period, extraídas de días del mismo régimen.
- **B) Null de 16 niveles aleatorios.** Por sesión, extraer 16 pseudo-niveles de la misma rejilla
  de strikes con la misma distribución de `|dist/spot|` que el set real; etiquetarlos con las
  mismas definiciones de evento de `level_react`.
- **C)** Etiquetar ambos con barrera (feature 1); `edge = p_signal − p_random` con **bootstrap
  estacionario sobre la DIFERENCIA** (bloque medio 30 barras, 2000 remuestreos).
- **D) CORRECCIÓN DE MUESTRA EFECTIVA, obligatoria**:
  `n_eff = n / (1 + (k−1)·ρ̄)` donde `k` = syms agrupados y `ρ̄` = correlación media por pares de
  retornos 1m del conjunto. En semis `ρ ≈ 0.7–0.9` → **factor de inflación 3–4×**: los CI de
  Wilson calculados sobre sym-días agrupados son **anticonservadores 3–4×**. Todos los Wilson usan
  `n_eff`.
- **E)** BH-FDR a `q=0.10` sobre `source × sym × bucket`; luego DSR, PSR y MinTRL vía la skill
  `stats-trading-risk`.
- **F)** Escribir automáticamente `data/signal_enable.json` (el mecanismo ya existe en
  `timeofday_calib`).

**Inputs exactos**: `trades.db signals`, `backtest_signal_outcomes`, la nueva `barrier_outcomes`,
`poly_bars`, `data/timeofday_factors.json`, `data/calibration.json`, skill `stats-trading-risk`
(bootstrap / DSR / MinTRL / BH-FDR). **Nada falta.**

**Output**: `data/null_control.json` →
```json
{"bollinger":{"n":822,"n_eff":240,"p":0.41,"p_rand":0.39,"edge":0.02,
  "ci":[-0.03,0.07],"fdr_q":0.31,"dsr":0.08,"mtrl_trades":980,"verdict":"UNPROVEN"}}
```
más `docs/EDGE-SCOREBOARD-<fecha>.md`, una línea en el email diario y
`data/signal_enable.json`.

**Decision rule**: `verdict=UNPROVEN` → la fuente puede imprimir banners pero **JAMÁS canta
SIGNAL y jamás dimensiona un trade**. `verdict=DEAD` (CI del edge entero ≤ 0) → deshabilitada en
`signal_enable.json`. Una feature nueva gana voz **solo celda calibrada a celda calibrada** por
esta puerta. Compromiso previo: los veredictos UNPROVEN se aceptan; **el test no se afloja nunca**.

**Validación**: autovalidante. Puerta de cordura = alimentarlo con una fuente deliberadamente
moneda-al-aire y confirmar `edge ≈ 0` con CI estrecho. Segunda puerta: **afirmar que BH-FDR +
n_eff convierte al menos una fuente hoy-con-voz en UNPROVEN** — si no cambia nada, la corrección
no se está aplicando.

**Effort** S · **Lang** Python · **Destino** `scripts/null_control.py` (nuevo) + extiende
`scripts/conditioned_backtest.py`, `scripts/timeofday_calib.py`
· **Skill** [[measured-probability]] · **Veredicto KEEP** · **Ola 1**

**Kill-risk**: declarará UNPROVEN alarmas queridas con 8 días de datos y la tentación política
será aflojar el umbral; además con `n_eff ~ 40–60` clusters-día casi nada será PROVEN en 2026, así
que el sistema se queda callado.

---

## 3. `book-quality gate` (absorbe el impact-gate) — veto por calidad de libro

**Origen**: MenthorQ #2 (*Total GEX vs Net GEX*: "high total + negative net = trade the levels,
not the regime") y #7 (*book quality*), fusionado con el medidor **Options Impact** de SpotGamma
(SG #4 `impact-gate`).

**Edge**: es un **veto multiplicativo**, no un 12º factor aditivo, y borra confirmaciones falsas
HOY: la cadena de NOK son 4 strikes y DRAM/SPCX/SKHY/EWY son libros de 3 contratos — y cantamos
veredictos gamma sobre ellos como si fueran QQQ.

**Matemática, en pasos** (desde el `profile` de `gex_core`)
1. `gross = Σ|GEX_K|` ; `net = Σ GEX_K` ; `bifurcation = gross/|net|`.
2. `HHI = Σ (|GEX_K|/gross)²` ; `n_strikes_populated` ; `greeks_ok_pct` (cabecera de cadena,
   feature 5).
3. `book_pctile` = percentil de `gross` contra las **propias 20 sesiones previas del ticker**,
   desde `trades.db gex_daily` — **SOLO DEL SNAPSHOT COMPLETO DE POLYGON**: con la banda IBKR,
   `gross` es un artefacto de la ventana del fetcher, no del tamaño del libro.
4. `impact_pctile` = percentil de `gross / (ADV20_shares · price)` — el medidor Impact de SG:
   cuánta gamma nocional hay por dólar de liquidez del subyacente.
5. **`abs_wall_sign` = signo del régimen acumulado en el strike del `abs_wall`**: `+` = **pin**
   (dealers amortiguan) / `−` = **trampilla** (dealers amplifican). Hoy el signo se **DESCARTA**
   → bug vivo, ver la nota del arreglo más abajo.
6. Etiqueta:
   - `THIN` si `book_pctile < 0.20` **o** `n_strikes_populated < 8` **o** `greeks_ok_pct < 0.5`
   - `BIFURCATED` si `net < 0` **y** `bifurcation > 4` **y** `book_pctile > 0.5`
   - `NEAR_FLIP` si `|spot − flip_open|/spot < 0.0015`
   - si no → `STABLE_PIN`
7. Coeficiente: `c = 0.0` si THIN, si no
   `c = clamp(0.35 + 0.65·min(book_pctile, impact_pctile), 0, 1)`.

**Inputs exactos**: `scripts/chart_levels.py gen()` (`profile`, `net_gex`, `abs_wall`,
`call_gex`/`put_gex`, `pressure`), `scripts/gex_core.py build_gex`, la nueva `trades.db gex_daily`
(feature 7), `data/bars_<sym>_ibkr.txt` + `poly_bars` para ADV20, `greeks_ok_pct` de la cabecera
(feature 5). **Sin feed nuevo.**

**Output**: claves ADITIVAS en `charts/data/levels_<sym>.json`: `{gross, net_gex, bifurcation,
hhi, book_pctile, impact_pctile, n_strikes_populated, abs_wall_sign, book_label, coef}`.
Espejo en `data/book_quality.json` para los bots C++. Se superficia como **MULTIPLICADOR** de los
pesos existentes `flip(1.5) / walls(1.0) / magnet(1.1)` en `direction_view`, un badge de color en
`charts/live.html`, y la línea del PDF *"libro FINO — mapa gamma no fiable, operar solo precio"*.

**Decision rule**
- `THIN` → `coef=0`: **toda voz derivada de gamma MUTEADA**, factores wall/flip/magnet a cero,
  banner solamente, operar solo lógica de precio / momentum / capitán.
- `BIFURCATED` → scalps nivel-a-nivel permitidos, trades de dirección-por-régimen **prohibidos**.
- `abs_wall_sign = '−'` a ±1 strike del spot → **VETO DURO sobre 0DTE comprado** (el veto de pin
  existente hoy dispara sobre la mitad EQUIVOCADA de estos casos).
- Esta puerta corre **ANTES** de la regla 12 del capitán y **antes** de `optgate.py`.

**Validación**: partir las 972 señales únicas (2916 filas de outcome, 8 fechas) por `book_label`
y re-correr `conditioned_backtest.py`. H0: la tasa de acierto es independiente de `book_label`.
**Keep** si mutear THIN eleva el Wilson-LB corregido por `n_eff` de la población superviviente en
**≥4pp** eliminando **<25%** de las señales. **Embarca aunque esté subpotenciado**: es una
afirmación de CALIDAD DE DATO (4 strikes no pueden definir un muro), no de edge.

**Effort** S · **Lang** Python · **Destino** `scripts/book_quality.py` (nuevo) + ediciones
aditivas a `scripts/chart_levels.py` y `scripts/gex_core.py` (respaldo en `backup/` primero)
· **Skill** [[book-quality-veto]] · **Veredicto KEEP** · **Ola 1**

**Kill-risk**: `book_pctile` con base de 20 sesiones es débil y mezcla tamaño de libro con
artefactos de ventana del fetcher hasta que aterrice la feature 7; y THIN puede mutear nombres
donde la lógica solo-precio era ya todo lo que usábamos, dejando la puerta como un no-op.

> **ESTADO: el arreglo del signo del Muro YA ESTÁ EN `scripts/gex_core.py` (2026-07-25).**
> `abs_wall/call_wall/put_wall` tiraban todo menos el strike, así que un **pin** (aguanta) y una
> **trampilla** (el precio la atraviesa acelerando) eran el MISMO dato para todos los consumidores,
> incluido el veto 0DTE. Ahora hay `*_net`, `*_regime`, `*_kind`. Y el discriminador **NO** es el
> signo crudo del perfil: con la convención naive (calls +, puts −) un put wall es negativo POR
> CONSTRUCCIÓN y "signo<0 = trampilla" etiquetaría TODO put wall como trampilla. El discriminador
> correcto es el **régimen acumulado en el nivel** — de qué lado del flip cae.
> Lo que queda de la feature 3: `gross/net/HHI/percentiles/coef` y el cableado del coeficiente.

---

## 4. `poly-aggs-backfill` — 2 años × 30 syms de barras 1m

**Origen**: **ningún diseñador la propuso**. La forzó la auditoría de los planes de validación:
`poly_bars` tiene **21 sesiones** mientras ~10 features reclaman 250 sesiones / 200 eventos de
earnings / retornos forward a 60 días.

**Edge**: convierte cobertura del EM, distancia al pin, relleno de huecos, el split de vol
realizada del VT, charm-vs-maxpain y el lado-precio del wall-decay de astrología a **medible** —
incluidas las que va a MATAR, que es exactamente el punto.

**Matemática / procedimiento**
1. Por cada uno de los 30 syms de la flota:
   `GET /v2/aggs/ticker/{sym}/range/1/minute/{from}/{to}?adjusted=false&limit=50000`
   paginado por `next_url` sobre **24 meses**, más `/range/1/day` sobre 5 años.
2. `UPSERT` a `trades.db poly_bars` con `UNIQUE(sym, ts)` e `INSERT OR IGNORE`.
3. Respetar el RPM del plan: token-bucket con sleep, backoff exponencial en 429, **reanudable**
   vía `poly_dl_log(sym, last_ts, status)`.
4. Verificación posterior por sym: nº de sesiones distintas, nº de filas, informe de minutos-RTH
   ausentes, y **reconciliación de 20 sym-días aleatorios** contra las filas de `poly_bars`
   existentes (cierre exacto al tick) y contra el solape con `data/bars_<sym>_ibkr.txt`.

**Inputs exactos**: endpoint de aggs de equity de Polygon (entitled; key en `feeds.env`),
`trades.db poly_bars` (esquema existente), `poly_dl_log`.
**FALTA, sin remedio a ningún precio en este plan**: la historia de OI/IV de opciones (el
snapshot no tiene `as_of` real) → **este backfill es SOLO PRECIOS** y todo bucket condicionado
por gamma queda forward-only.

**Output**: `poly_bars` crece a ~20–25M filas 1m (1m solo para la flota-30; se mueve a un
`bars.db` adjunto si `trades.db` pasa de 400 MB); páginas JSON crudas a
`data/history/aggs/<sym>.jsonl.gz`, borradas tras la verificación.
`data/backfill_report.json` → `{sym:{sessions, rows, gap_minutes, first_ts, last_ts, reconciled}}`.

**Decision rule — REGLA DE GOBERNANZA DURA**: ninguna feature puede publicar una probabilidad
cuyo plan de validación reclame ≥60 sesiones hasta que `backfill_report.json` muestre que esa
muestra existe para los syms implicados. Las features que asumían años de `poly_bars` están
bloqueadas **en esto**, no en su propio código.

**Validación**: el test de reconciliación de arriba (20 sym-días exactos al tick) más
`gap_minutes < 0.5%` de los minutos RTH por sym. Si el plan tapa la historia por debajo de 2 años,
se publica el span REAL y se degradan todos los umbrales keep dependientes en consecuencia.

**Effort** M · **Lang** Python · **Destino** `scripts/poly_backfill.py` (nuevo)
· **Skill** [[measured-probability]] · **Veredicto KEEP** · **Ola 2**

**Kill-risk**: los límites de historia/RPM del plan pueden taparnos muy por debajo de 2 años; y
~2–3 GB de filas nuevas en una caja con 88 MB de páginas libres y 1,14 GB de swap usado ralentizan
toda consulta de `calibration_ledger` a menos que el 1m vaya a una db adjunta separada.

> **ESTADO: EN CURSO.** Otro agente está construyendo este backfill AHORA MISMO (2026-07-25).
> No re-implementar; verificar `data/backfill_report.json` antes de asumir muestra.

---

## 5. `chain-honesty` — matar las degradaciones silenciosas

**Origen**: MenthorQ #13 (cube-widening) **paso 1** + el fallback de inversión de IV de SpotGamma
(P0b). Ambos degradados por la auditoría.

**Edge**: todo número gamma que publicamos hoy puede estar computado desde un `iv=0.3`
**fabricado**, sobre una banda silenciosamente estrechada, con 0/40 griegas reales. Esto hace la
mentira VISIBLE para que los consumidores degraden honestamente en vez de hablar con confianza.

**Matemática / cambios, en pasos**
1. **BORRAR el fallback `iv=0.3`** en `gex_core.from_ibkr_cache`. Un contrato con `iv ≤ 0` queda
   **EXCLUIDO** y contado.
2. `opt_chain_cache.py` escribe una **línea de cabecera** por fichero:
   ```
   # sym=X spot=Y ts=EPOCH band=0.06|0.04 max_strikes=20|12 narrow=0|1 exps=E1,E2[,E3] rows=N greeks_ok_pct=NN stale=0|1
   ```
   Campos **append-only**; las columnas por fila **JAMÁS se reordenan** (`scripts/opt_quick.cpp`
   parsea POSICIONALMENTE, y las líneas `#` deben saltarse).
3. **Inversión de IV** (bisección sobre el mid, 60 iteraciones, tol `1e-6`, forward por paridad
   put-call, `r=0.045`) permitida **SOLO** cuando `bid>0 y ask>0 y RTH`. Fuera de eso `iv=null` y
   `stale=1`. Razón: **a las 16:16 bid/ask son `-1.00`**, así que una bisección sobre ESE mid sería
   una mentira más convincente que el bug que reemplaza.
4. Todo consumidor (`chart_levels`, `direction_view`, `daily_fleet_plans`, `opt_quick.cpp`) lee
   `greeks_ok_pct` y, **por debajo de 0.5**, emite las claves gamma como `null` más el banner
   *"libro sin griegas"*.

**Inputs exactos**: `scripts/opt_chain_cache.py` (verificado: `PCT_BAND=0.06`,
`NARROW_BAND=0.04`, `MAX_STRIKES=20`, `NARROW_MAX_STRIKES=12`, `CYCLE_S=180`,
`NARROW={MSFT, AVGO, AMZN, META}`), `scripts/gex_core.py` `from_ibkr_cache`/`_T_of`, el parser de
`scripts/opt_quick.cpp`, `data/opt_chain_<sym>.txt`.

**Output**: `docs/CHAIN-HEADER.md` (el contrato) + `data/chain_health.json`
`{sym:{greeks_ok_pct, narrow, band, max_strikes, rows, stale, ts}}` + los strings de degradación
para banner/PDF.

**Decision rule**: `greeks_ok_pct < 0.5` **o** `stale=1` → **sin voz gamma, sin ticket de muro,
sin factores gamma en la flecha** para ese sym (fail loud, jamás degradar en silencio). El
conjunto NARROW ahora es VISIBLE: cualquier feature que reclame "±6%" debe leer `band` de la
cabecera.

**Validación**: aserciones deterministas, cero probabilidad. (a) test unitario: un fichero con
`iv=-1` produce gamma `null`, no un número derivado de 0.3; (b) `opt_quick.cpp` sigue parseando;
(c) se publica un histograma de 5 sesiones de `greeks_ok_pct` por sym (se espera ~1.0 en RTH,
0.0 después de las 16:00).

**Effort** S · **Lang** Python · **Destino** `scripts/gex_core.py`, `scripts/opt_chain_cache.py`,
`scripts/opt_quick.cpp`, `docs/CHAIN-HEADER.md`
· **Skill** [[chain-data-contract]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: hacer visible la verdad anula la gamma de muchos syms fuera de RTH y de los libros
finos, y el reflejo será re-añadir un default; `opt_quick.cpp` es posicional, así que un cambio
descuidado de cabecera rompe el lector más rápido de la flota.

---

## 6. `flip-honesty` + congelación a las 09:35

**Origen**: MenthorQ #2 *flip-velocity* (la narrativa de velocidad ELIMINADA) más la idea de
congelación rescatada del *Volatility Trigger* de SpotGamma (#2).

**Edge**: ya pagamos `flip_recompute` y luego lo **descartamos**; reportamos una raíz cuando la
segunda raíz debajo del spot es la **trampilla**; y dejamos que el flip re-oscile intradía — un
nivel que no puede oscilar no puede crying-wolf.

**Matemática, en pasos**
1. Arreglar `from_ibkr_cache` (~línea 298) para que el resultado de `flip_recompute` **GANE**
   durante RTH; emitir `flip_src ∈ {repriced, static_no_iv, none}`.
2. `gex_core._flip` devuelve **TODOS** los cambios de signo de la GEX neta acumulada sobre la
   rejilla ±15% (120 pasos, cada cruce refinado por bisección a `1e-4` del spot), ordenados por
   `|K − spot|` → `roots[]`.
3. **CONGELAR `flip_open`** en el primer snapshot ≥ 09:35 ET dentro de
   `charts/data/levels_<sym>.json` y **no recomputarlo intradía**; publicar `flip_live` aparte
   como diagnóstico.
4. `trapdoor_root` = la raíz más cercana **DEBAJO** del spot dentro de 1× `em`.

**EXPLÍCITAMENTE ELIMINADO**: `eta_min`, la pendiente Theil-Sen `dflip/dt`, la afirmación
`converge='dealer-driven'` y su voz DANGER preventiva. Con OI estático de cierre-previo intradía,
`dflip/dt` es un artefacto de spot/IV y **no puede medir posicionamiento llegando**.

**Inputs exactos**: `scripts/gex_core.py` (`_flip`, `flip_recompute`, `from_ibkr_cache`),
`scripts/chart_levels.py gen()`, `data/opt_chain_<sym>.txt` + la cabecera `greeks_ok_pct`,
`data/nbbo_<sym>.txt` para spot vivo (**nunca** el spot rancio de la cabecera del fichero).

**Output**: `charts/data/levels_<sym>.json` añade `{flip_open, flip_live, flip_src, roots:[...],
trapdoor_root, frozen_at}`; `data/features_<sym>.json` lo espeja.

**Decision rule**: la etiqueta de régimen y el factor `flip` de `direction_view` usan
**`flip_open` SOLAMENTE**. `flip_src='static_no_iv'` → peso del factor flip ×0.5 y `why[]`
imprime *"flip sin griegas"*. `trapdoor_root` presente → **VETO DURO sobre calls 0DTE compradas**
(los dealers amplifican debajo). Clase de voz sin cambios: el cruce del flip sigue siendo SIGNAL,
**nunca** DANGER.

**Validación**: determinista, cero probabilidad. Test unitario: la salida en RTH iguala
`flip_recompute` (hoy iguala silenciosamente `flip_static`). Luego contar sobre 20 sesiones cuántas
veces `|flip_repriced − flip_static| > 0.3%·S` (**ese número es el tamaño del bug**) y cuántas
veces una segunda raíz cae dentro de 1× `em` por debajo del spot.

**Effort** S · **Lang** Python · **Destino** `scripts/gex_core.py`, `scripts/chart_levels.py`
· **Skill** [[flip-and-vol-trigger]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: sobre una banda de ±1,45% las `roots` extra pueden ser bordes de ventana en vez de
cruces reales, así que `roots[]` debe suprimirse salvo `n_strikes_populated ≥ 12` o disponibilidad
del snapshot completo de Polygon.

---

## 7. `chain_full_snap` — snapshot nocturno de cadena completa de Polygon (forward-only)

**Origen**: SpotGamma P0a (*full-chain snapshot*) — reformulado después de que la auditoría
probara que **no existe parámetro `as_of`** funcional.

**Edge**: todo nivel gamma estructural que computamos hoy mide **la forma de nuestro fetcher**
(2 expiries, ±1,45% en QQQ, 0/40 griegas en NVDA). Esto da OI/IV real en **todo strike y todo
expiry**, fuera del camino de señal, por 30 llamadas nocturnas.

**Matemática / procedimiento**
1. A las **15:58** y **20:30 ET**: `GET /v3/snapshot/options/{underlying}` paginado
   (`limit=250`, seguir `next_url`) para los 30 syms de la flota.
2. Guardar por contrato: `ticker, expiry, strike, right, open_interest, day.volume, day.close,
   implied_volatility, last_quote bid/ask`.
3. **ALMACENAR sus griegas pero NUNCA consumirlas** (verificado basura: delta deep-ITM 0.99996,
   gamma −1.4e−09). **RE-DERIVAR** gamma/vanna/charm/delta con `gex_core.bs_gamma`/`bs_vanna`/
   `bs_charm` desde **SU** `iv`, nuestro `r=0.045`, y `T` desde `gex_core._T_of`.
4. Sonda de entitlement diaria: no-200 o 0 contratos → **fail loud** (banner + ntfy) y marcar la
   fecha como ausente.
5. **ACUMULACIÓN FORWARD-ONLY**: no existe historia de OI/IV a ningún precio en este plan, así que
   **todo plan de validación dependiente debe declarar su fecha de inicio**.

**Inputs exactos**: Polygon `/v3/snapshot/options` (verificado 200 con griegas+IV+OI+day en todos
los strikes y expiries; `/v3/trades/O:` y `/v3/quotes/O:` son `NOT_AUTHORIZED`),
`scripts/gex_core.py` `bs_*` + `_T_of`, key en `feeds.env`.

**Output**: `data/history/<date>/chain_full_<sym>.jsonl.gz` (borrado rodante del crudo a 45 días)
+ `trades.db gex_daily(sym, date, exp, dte, strike, right, oi, vol, iv, gamma, gex, dex, charm)`
por-strike para los 3 expiries frontales y agregado más allá +
`data/chain_full_health.json {date, syms_ok, contracts, probe_status}`.

**Decision rule**: los niveles ESTRUCTURALES (vol-trigger, pin, cuotas de expiry, 25Δ RR, mapa del
día siguiente, `book_pctile`) se computan **DE ESTE FICHERO SOLAMENTE**; la cache IBKR sirve
únicamente la banda ATM viva. Si la sonda nocturna falla, se reutiliza la estructura de ayer
**etiquetada `stale=1`** — nunca en silencio.

**Validación**: un log de sonda de 30 días al 100%; cruce de OI contra el OI de cierre-previo de
IBKR en strikes solapados (acuerdo dentro del 1%); afirmar que la gamma ATM re-derivada está
dentro del 5% de la de Polygon mientras su gamma deep-ITM se **rechaza**.

**Effort** M · **Lang** Python · **Destino** `scripts/chain_full_snap.py` (nuevo)
· **Skill** [[chain-data-contract]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: el entitlement podría cambiar en silencio; sin comprimir son ~4,5 GB/mes en una
caja sin holgura de disco (de ahí gz + borrado a 45 días + retención solo-agregada).

---

## 8. `level-react` primitivo + tabla `level_events`

**Origen**: TrendSpider #2 *Dynamic Price Alerts* (Touch/Bounce/BreakThrough con sensibilidad ATR
y **cierre de vela obligatorio**) fusionado con el primitivo C++ de MenthorQ #10 y la taxonomía de
eventos de MenthorQ #3.

**Edge**: es el único ítem que **BORRA código** — ~30 `*_signal_bot.cpp` cargan cada uno su propia
lógica de niveles ad-hoc — y hace **PRINT-O-NADA mecánico** (straddle de dos velas) en vez de 30
gatillos "está cerca" hechos a mano.

**Matemática, en pasos** (C++23: header compartido `level_react.h` + `level_react.cpp`)
1. Cargar el set de niveles del día una vez por sym desde `charts/data/levels_<sym>.json`;
   refrescar al cambiar el `mtime` (esto también mata por construcción el defecto documentado de
   MenthorQ de "las alertas se auto-expiran cada día").
2. **Registro TOPADO DURO a 6 tipos/sym**: `OI_CALL_WALL, OI_PUT_WALL, ABS_WALL, FLIP_OPEN,
   POC_DOM, ROUND`. `GAP_EDGE` y `KDE` solo pueden **DESPLAZAR** un slot de menor prioridad.
3. Buffer `s = max(0.15·ATR14_1m, medio-spread de data/nbbo_<sym>.txt, 1 tick)`.
4. En cada barra 1m **CERRADA**, por nivel `L`:
   - `active(L) = (high > L y low < L)` en la barra **ACTUAL Y LA PREVIA` → **esto ES
     PRINT-O-NADA: dos lecturas cruzando, no proximidad**.
   - `TOUCH` = `low ≤ L+s y high ≥ L−s y close del lado original`
   - `BREAK` = `open` y `close` en lados opuestos de `[L−s, L+s]`
   - `BOUNCE` = `TOUCH` en `t` y **no** `BREAK` en `t+1`
   - `RETEST_REJECT` = `BREAK` en `t`, `TOUCH` desde el lado lejano dentro de 5 barras, sin
     re-ruptura
   - `WICK_REJECT` = `high > L y close < L y |high−close| > |open−close|`
5. `touch_ord` se incrementa **solo tras una excursión ≥ 0.5·ATR** de alejamiento.
6. Arrastrar `is_round`, `dist_atr`, `regime`, bucket horario.

**Inputs exactos**: `data/bars_<sym>_ibkr.txt` (1m, ya es el input de los bots),
`data/nbbo_<sym>.txt`, `charts/data/levels_<sym>.json`, `data/book_quality.json`,
`fleet_notify.h`. **NO necesita dato de opciones en tiempo de señal** (cero riesgo de feed).
Sustrato de backtest: `poly_bars` (los ficheros de barras IBKR son 2 sesiones y **repintan** vía
`warmup_sym`).

**Output**: `trades.db level_events(ts, sym, level_type, level_px, event, is_round, touch_ord,
dist_atr, regime, hour, bar_close_epoch)` con retención 180 días +
`data/level_events.jsonl` (rotado a diario, retención 30 días) + marcadores en `charts/live.html`.
**RSS ~0,7 MB en C++** frente a ~50 MB de un daemon Python.

**Decision rule**: **EMBARCA CON LA VOZ DESHABILITADA PARA TODA FUENTE.** Una celda gana voz solo
después de que `null-control` le dé Wilson-LB ≥ tasa-de-nivel-aleatorio + 4pp con `n_eff ≥ 80`.
Entradas **solo** en `BOUNCE` o `RETEST_REJECT` — **nunca** `TOUCH` (consolidación), nunca un
primer `BREAK` sin retest. Orden de puertas: **book-quality → regla 12 del capitán → Bollinger
(banda estirada en contra = sin trade de reversión) → `optgate.py` para el vehículo.**

**Validación**: replay de `data/hist/bars_*_1m_30d.txt` + `poly_bars` contra niveles
reconstruidos por sesión (POC/PDH/PDL/ROUND/GAP reconstruibles hoy; las celdas de muros OI se
acumulan hacia adelante). Null = **el mismo patrón de vela de reversión a un precio aleatorio sin
nivel** (1000 sets de niveles sintéticos). El prior de **Osler (2000) es 60,8% vs 56,2%** con
~**3,4pp atribuibles a números redondos**, así que la vara es: **el nivel debe añadir ≥6pp sobre
el simple giro de vela**, o es decoración.

**Effort** M · **Lang** **C++23** · **Destino** `scripts/level_react.cpp` + `scripts/level_react.h`
(nuevos), include de una línea en cada `*_signal_bot.cpp` y en `scripts/price_alarm.cpp`
· **Skill** [[print-o-nada-levels]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: el conteo de niveles × syms explota en spam de alarmas y en una máquina de multiple
testing (de ahí el tope de 6 tipos y el default voz-apagada); y el straddle de dos barras puede
ser **estrictamente peor** que los gatillos ad-hoc actuales de los bots.

---

## 9. `truth-lock` — detector de repintado / ajuste de datos

**Origen**: TrendSpider #6 — el *Truth-in-Analysis timestamp* (congelar el análisis para que no
repinte en silencio) + el auto-stop de los *Strategy Bots* ante ajuste de datos históricos.

**Edge**: `warmup_sym()` en `scripts/ibkr_bar_bridge.py` **trunca y REESCRIBE dos días de barras
1m** que la calibración lee después. Nadie sabe hoy qué fracción de nuestro win rate medido se
computó sobre datos que luego cambiaron.

**Matemática, en pasos**
1. En cada emisión de señal, congelar un blob de contexto: `spot`, `nbbo bid/ask`, el set de
   niveles, `force.json`, `regime`, y `bars_sha` = **SHA-1 sobre las últimas 120 barras CERRADAS**
   serializadas `epoch|o|h|l|c|v`.
2. Un watchdog de 30 s recomputa `bars_sha` sobre **la MISMA ventana de epochs**.
3. **FILTRO DE MATERIALIDAD (obligatorio o se vuelve fatiga)**: un cambio cuenta solo si el
   `o/h/l/c` de una barra cerrada difiere en **>1 tick** o su volumen en **>1%**.
4. Ante cambio material: `signals.data_adjusted=1` (`calibration_ledger` **EXCLUYE** esas filas),
   **banner + push ntfy — NO voz DANGER** (un backfill benigno del SIP entrenaría a Yunior a
   ignorarla), y **DESARMAR** cualquier ticket armado de `order_engine` para ese sym (re-armar
   exige doble llave — ganancia neta de seguridad bajo la ley señal-solamente).
5. Todo artefacto (página de PDF, overlay del chart, flecha) lleva `lock_ts`, y el cockpit dibuja
   la **línea vertical de verdad**.

**Inputs exactos**: `data/bars_<sym>_ibkr.txt` (~1690 filas ≈ 2 sesiones, reescrito por
`warmup_sym`), `trades.db signals`, `data/force.json`, `charts/data/levels_<sym>.json`, el
fichero de arm-state de `order_engine`.

**Output**: `trades.db signal_context(signal_id, lock_ts, bars_sha, spot, nbbo_bid, nbbo_ask,
levels_json, regime, force_json)` con retención 90 días +
`data/truth_lock.json {sym:{lock_ts, bars_sha, adjusted, last_check, material_changes_today}}` +
un indicador de candado rojo/azul en `charts/live.html`.

**Decision rule**: `adjusted=1` para un sym → **NO-TRADE en ese sym hasta re-lock** (no-trade es
una posición, regla 6). Todo backtest que toque ventanas ajustadas **debe IMPRIMIR el conteo
excluido**, nunca incluirlas en silencio.

**Validación**: no es una feature de probabilidad. Validar por **INYECCIÓN**: reescribir una barra
en una copia del fichero y afirmar detección dentro de un ciclo de watchdog. Después medir la
incidencia real sobre 30 sesiones. Si la incidencia es 0 tras un mes, degradar a una aserción
barata. El **subproducto** — el % de WR medido computado sobre datos que luego cambiaron —
justifica la construcción incluso con incidencia cero.

**Effort** S · **Lang** Python · **Destino** `scripts/truth_lock.py` (nuevo) + hooks en los
emisores de señal y en `scripts/calibration_ledger.py`
· **Skill** [[sample-integrity]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: las correcciones benignas de backfill del SIP de IBKR en el warmup pueden ser lo
bastante frecuentes para que incluso los cambios materiales disparen a diario, y la exclusión
entonces se come una porción grande de nuestra única muestra.

---

## 10. `em-envelope` — la valla del día (solo la mitad determinista)

**Origen**: MenthorQ #12 *Expected Move* (straddle-mid, cobertura asimétrica — su cobertura
auditada es **87,62% arriba del mínimo vs 85,02% abajo del máximo**), absorbiendo el
target-clamping y la idea de confluencia-con-muro de SpotGamma #9 (`em-measured`).

**Edge**: nuestro `em` es `spot·iv_atm·√T` con un conteo de días que silenciosamente convierte un
nivel de VIERNES en una banda de 1 día en vez de abarcar hasta el LUNES; y `direction_view`
apunta felizmente a niveles fuera de cualquier rango plausible del día.

**Matemática, en pasos**
1. `em_straddle = 0.8 · (call_mid + put_mid)` en el strike más cercano al spot del expiry frontal,
   **capturado a las 15:55 ET o antes** (a las 16:16 bid/ask son `-1.00`, así que esto DEBE
   snapearse mientras existan cotizaciones); si no, `em_src='iv_atm'` con etiqueta.
2. **SPAN CONSCIENTE DEL CALENDARIO**: `span_trading_days` = días de mercado desde el snapshot al
   cierre de la sesión objetivo, y `calendar_days` publicado al lado (viernes→lunes = **1 día de
   mercado, 3 de calendario**) para que el caso del fin de semana sea auditable.
   `em_pct = (em_straddle/S)·√span_trading_days`.
3. `hi = S·exp(+em_pct)` ; `lo = S·exp(−em_pct)`.
4. **Invalidación por earnings**: si la fecha de earnings de Finviz Elite cae dentro del span →
   `invalid_reason='earnings'`.
5. **CLIP**: todo nivel GEX/muro fuera de `[lo, hi]` se **elimina del chart y de
   `direction_view.target`**.
6. Flag de **confluencia** cuando `|hi − call_wall| ≤ 0.0015·S` (o `lo` vs `put_wall`).

**ELIMINADO**: el solve empírico de `k_u`/`k_d` (necesita ≥120 sym-sesiones; tenemos 21) y la
regla de cambio de vehículo por `vrp_ratio` (un ratio no medido cambiando una regla de trading).

**Inputs exactos**: `data/opt_chain_<sym>.txt` bid/ask (**solo RTH**), `scripts/gex_core.py`
(`em`, `iv_atm`), `scripts/chart_levels.py gen()`, fechas de earnings de `scripts/finviz_scan.py`,
`poly_bars` (medición de cobertura post-backfill).

**Output**: `charts/data/levels_<sym>.json` añade `{em_src, em_straddle_pct, em_hi, em_lo,
span_days, calendar_days, invalid_reason, confluence:{side, level, gap_pct}, coverage_hist:null}`.

**Decision rule**: **jamás apuntar más allá de `em_hi`/`em_lo`** (`direction_view.target` se
clampa). Un toque de `em_hi` **POR ENCIMA** del call wall es **agotamiento, no ruptura** → fade o
cobrar beneficios, jamás perseguir; eso más un %B extremo es la confluencia de fade más fuerte
que podemos afirmar. `invalid_reason` puesto → sin trade basado en la valla. Los niveles fuera de
la valla **no son los niveles de hoy** y se quitan del chart (menos líneas = menos confirmaciones
falsas).

**Validación**: post-backfill, tasa de contención del cierre de la sesión siguiente dentro de
`[lo, hi]` por sym con CI de Wilson (objetivo ~76–85%); publicar la cobertura lograda y **NO
ajustar `k_u`/`k_d` hasta `n ≥ 120` sym-sesiones**. Las victorias deterministas (span/calendario,
clipping, invalidación por earnings, straddle-mid) embarcan **independientemente** del resultado
de cobertura.

**Effort** M · **Lang** Python · **Destino** `scripts/gex_core.py` + `scripts/chart_levels.py`
(claves aditivas), `scripts/em_coverage.py` (nuevo, informe offline)
· **Skill** [[expected-move-envelope]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: un straddle de expiry frontal en una tarde 0DTE **no es un movimiento de 1 día en
absoluto** — si la elección de expiry o el conteo de span están mal, la valla se convierte en
silencio en una banda de 3 horas, que es PEOR que el `em` simétrico de hoy.

---

## 11. `features-fanout` + tope duro de 14 factores

**Origen**: TrendSpider — pero en realidad es una **condición transversal** impuesta por las
críticas estadística y operativa de los tres sets: `direction_view` tiene **11 pesos puestos a
mano que suman ~12,35** y las propuestas añadirían ~**+6,4 de peso aditivo correlacionado**.

**Edge**: añadir factores aditivos CORRELACIONADOS a una media ponderada NORMALIZADA **destruye
información**: +6,4 de peso nuevo recorta el apalancamiento de cada factor existente ~**34%** y
colapsa la varianza de la flecha hacia una constante ~**58%**.

**Matemática / arquitectura, en pasos**
1. `scripts/features_merge.py` ensambla `data/features_<sym>.json` desde cada JSON productor
   (levels, book_quality, force, chain_delta, pin, em, vt, cor_fleet, wall_stats, cola de
   level_events) con `{value, src_file, ts, stale_sec}` por clave.
2. `direction_view.py` lee **SOLO ese fichero** por un loader cacheado por `mtime` (**un `stat()`
   por flecha** en vez de ~12).
3. Aserción en runtime: `len(weights) ≤ 14`. Un factor **ADITIVO** nuevo exige (a) veredicto de
   `null-control` ≠ UNPROVEN **y** (b) **nombrar el factor que retira** — candidatos:
   `captain_flow` P/C crudo (1.2), `candle` (0.6), `inflation` (0.5).
4. **La información nueva entra como COEFICIENTE MULTIPLICATIVO** sobre los pesos existentes
   flip/walls/magnet/fleet (`book_quality coef`, `cor_fleet damper`), **jamás como término nuevo**.
5. `why[]` debe imprimir **todo coeficiente aplicado**: p.ej. *"muros ×0.4 libro FINO"*,
   *"capitan ×1.25 rho 0.81"*.
6. Todo factor cuya clave esté **rancia >120 s** se pone a cero **y se dice en voz alta**.

**Inputs exactos**: `scripts/direction_view.py` (factores verificados: `flip 1.5, walls 1.0,
gex_accel 0.8, fleet 1.4, components 1.3, captain_flow 1.2, momentum 1.0, bollinger 1.15,
candle 0.6, inflation 0.5, magnet 1.1`; `score` = media ponderada normalizada mapeada a prob
50–90), todos los JSON productores en `data/`, `scripts/signal_conditioning.py`.

**Output**: `data/features_<sym>.json` (contrato documentado en `docs/FEATURES-CONTRACT.md`) +
`why[]` de `direction_view` con los coeficientes aplicados + un test de CI que afirma el tope.

**Decision rule**: cualquier PR que añada un factor aditivo **sin retirada** se rechaza en review.
Los pesos elegidos a mano **son probabilidades hardcodeadas con otro sombrero**: con 22 factores
conjuntamente no-ajustados ninguna pérdida se puede atribuir a una causa, así que el tope es
**doctrina, no estilo**.

**Validación**: test de regresión — salida de la flecha **byte-idéntica** antes/después del
refactor de fanout sobre 200 snapshots replayados. Test de ops: llamadas a `stat()` por flecha
bajan de ~12 a 1. Test estadístico: la varianza de `prob` a lo largo de una sesión **no puede
encogerse >10%** tras ningún cambio de pesos (detector de colapso de varianza).

**Effort** M · **Lang** Python · **Destino** `scripts/features_merge.py` (nuevo) +
`scripts/direction_view.py`
· **Skill** [[direction-view-architecture]] · **Veredicto KEEP** · **Ola 1**

**Kill-risk**: un único fichero fanout se convierte en un nuevo punto único de fallo y en una
trampa de rancidez — mitigado por `stale_sec` por clave y por poner a cero los factores rancios
**en voz alta**.

---

## 12. `voice-budget governor` — presupuesto de alarmas

**Origen**: TrendSpider (condición transversal de la crítica operativa): `voice_log` tiene **284
locuciones en total** contra **3233 señales**, y el set de propuestas añadía ~14 emisores de voz
nuevos × 30 syms.

**Edge**: la fatiga de alertas es **el único modo de fallo de esta lista sin remedio técnico
posterior** — deshabilita en silencio el sistema entero, y es exactamente a lo que camina de
frente un roster de 30 features.

**Matemática / mecanismo, en pasos**
1. `data/voice_registry.json` lista **cada** emisor: `{id, module, class ∈ DANGER|SIGNAL|INFO,
   calib_cell, enabled}`.
2. `speak.sh` / `voice_queue.sh` imponen:
   - (a) el **conteo de emisores DANGER está CONGELADO** en el conteo de hoy + 1 — un DANGER nuevo
     debe **desplazar** a uno existente;
   - (b) un emisor puede hablar solo si su veredicto de `null_control` es **PROVEN** y su celda
     tiene `n_eff ≥` umbral; si no, banner;
   - (c) cooldown de **10 minutos por sym** más **histéresis** (el gatillo debe re-entrar ±1σ
     antes de re-armarse) — punto 3 de la doctrina;
   - (d) tope duro diario de **40 locuciones** (hoy ~28/sesión); desbordamiento → banner más un
     único digest ntfy;
   - (e) **cada supresión se registra** en `voice_log` con `{emitter, class, reason}`.
   - DANGER nunca es suprimido por el presupuesto, solo SIGNAL/INFO.

**Inputs exactos**: `scripts/speak.sh`, `scripts/voice_queue.sh`, `trades.db voice_log`
(284 filas), `data/signal_enable.json`, `data/null_control.json`.

**Output**: `data/voice_registry.json` + `voice_log` extendido con
`(emitter, class, suppressed_reason)` + una línea de presupuesto semanal de locuciones en el email
diario.

**Decision rule**: **una feature embarca MUDA por defecto y gana voz una celda calibrada a la
vez.** DANGER queda reservado para: **trampilla gamma en el spot, pérdida del VT, y reescritura
material de truth-lock** (banner+ntfy por ahora). **Ningún DANGER nuevo sin una retirada.**

**Validación**: contar locuciones por sesión sobre 10 sesiones antes/después; afirmar que ninguna
sesión pasa de 40 y que el conteo de emisores DANGER es constante; afirmar que **toda** supresión
tiene su fila de motivo (cero descartes silenciosos).

**Effort** S · **Lang** Bash + Python · **Destino** `scripts/voice_queue.sh`, `scripts/speak.sh`,
`data/voice_registry.json`
· **Skill** [[alert-budget]] · **Veredicto KEEP** · **Ola 1**

**Kill-risk**: los topes duros pueden suprimir la locución que importaba; mitigado por prioridad
de clase, el digest ntfy, y registrar cada supresión para que el coste sea visible.

---

## 13. `next-day-map` — arreglo del roll-off de expiry

**Origen**: MenthorQ #12 *Tomorrow's Map Tonight* — **solo la mitad determinista** (la acreción
de OI por κ se elimina).

**Edge**: el plan de las 04:00 mapea la flota entera desde una cache que **todavía contiene
contratos que expiraron ayer**, así que los muros y el flip de la página 1 de 26–30 PDFs se
computan desde OI que está a punto de ser cero. Es un **bug determinado**, no una hipótesis.

**Matemática, en pasos**
1. A las 15:55 ET tomar el último snapshot de cadena **QUE TENGA GRIEGAS** (el fichero de las
   16:05 no las tiene — verificado) más el snapshot completo de Polygon.
2. **Eliminar todo contrato con `expiry == today`.**
3. **Re-timar** los supervivientes `T → T − 1/252` (esto solo ya desplaza la concentración de
   gamma al nuevo expiry frontal).
4. Recomputar el set completo de niveles sobre el libro re-timado: flip (todas las raíces),
   call/put/abs wall, `abs_wall_sign`, `em`, VT.
5. Emitir `delta_vs_today` por nivel con `cause='0DTE roll-off'`.
6. **Auto-puntuación**: `forecast_err_prev` = media `|forecast_level − actual 09:35 level| / em`
   sobre las últimas 5 sesiones por sym.

**ELIMINADO**: `oi_tomorrow = oi + κ·vol` (κ no está disponible — ver feature 22 — y el cambio de
OI overnight está dominado por posicionamiento que no podemos ver).

**Inputs exactos**: `data/history/<date>/opt_chain_<sym>_1555.txt`,
`data/history/<date>/chain_full_<sym>.jsonl.gz`, `scripts/gex_core.py`,
`scripts/chart_levels.py`, `scripts/daily_fleet_plans.py` (consumidor — **RESPALDAR a `backup/`
primero**), `scripts/postmortem_run.sh` (puntuador).

**Output**: `data/next_day_map.json` → `{asof, sym:{today:{...}, tomorrow:{flip, call_wall,
put_wall, abs_wall, abs_wall_sign, vt}, delta:[{level, from, to, cause}], forecast_err_prev}}`,
consumido como el mapa **PRIMARIO** por la corrida de las 04:00 y sobrescrito por el refresh vivo
de las 08:30.

**Decision rule**: las **fichas de orden de la víspera** (regla 10) se construyen desde ESTE mapa,
nunca desde el rancio. Si `forecast_err_prev > 0.5 em` para un sym a lo largo de 5 sesiones, el
mapa nocturno de ese sym **NO se usa** para fichas — esperar el snapshot vivo de las 08:30
(fail loud).

**Validación**: directa y barata. `|forecast − actual 09:35| / em` por nivel por sym frente al
baseline ingenuo *"mañana = el mapa de hoy sin cambios"*. Mantener el **framing de forecast** solo
si el error normalizado mediano bate al ingenuo en **≥20%** con `n ≥ 30` sym-sesiones; **la mitad
de eliminar-expirados embarca sin condiciones** como arreglo de bug.

**Effort** M · **Lang** Python · **Destino** `scripts/next_day_map.py` (nuevo) +
`scripts/daily_fleet_plans.py`
· **Skill** [[pin-and-expiry-mechanics]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: el baseline ingenuo puede simplemente ganar, en cuyo caso la feature se reduce al
arreglo del roll-off — que sigue valiendo la pena por sí solo.

---

## 14. `pin-clock` — max pain estructural

**Origen**: SpotGamma #11 *pin-clock / Max Pain* + el pin de *Absolute Gamma*. Los factores
horarios medidos se **eliminan**.

**Edge**: **no necesita griegas en absoluto**, así que es el único nivel estructural que funciona
en **NOK (4 strikes)**, DRAM, SPCX y SKHY donde toda computación gamma es ruido — y su salida es
una **prohibición que ya creemos**.

**Matemática, en pasos**
1. `pain(K*) = Σ_{K<K*} callOI(K)·(K*−K)·100 + Σ_{K>K*} putOI(K)·(K−K*)·100` sobre **TODOS** los
   expiries hasta el próximo viernes, **desde `chain_full_snap` SOLAMENTE** (la banda IBKR de
   ±1,45% sesga el max pain hacia el spot mecánicamente). `max_pain = argmin pain`.
2. `width` = intervalo modal de strikes.
3. `pin = max_pain` **solo si** `|max_pain − abs_wall| ≤ 1 strike` **Y**
   `Σ(OI dentro de ±2 strikes) ≥ min_oi` (**5000 índice / 1000 nombre individual**); si no
   `pin = null`.
4. `zone = [pin − width/4, pin + width/4]`.
5. `verdict = PIN_DAY` **solo si** `pin ≠ null` **Y** `abs_wall_sign == '+'`
   (**un `abs_wall` '−' es una TRAMPILLA, no un pin**).

**ELIMINADO**: la `p_pin` medida por `hora × régimen` (tenemos 4 viernes de expiry).

**Inputs exactos**: `trades.db gex_daily` / `data/history/<date>/chain_full_<sym>.jsonl.gz`
(OI de expiry completo), `charts/data/levels_<sym>.json` (`abs_wall`, `abs_wall_sign`, `oi_*`),
`poly_bars`, buckets de `scripts/timeofday_calib.py`.

**Output**: `data/pin_<sym>.json` → `{max_pain, abs_wall, pin, width, zone:[lo,hi], oi_in_zone,
verdict: PIN_DAY|NEUTRAL|RELEASE, corr_abs_wall_60d, p_pin: null}` + una zona sombreada en
`charts/live.html` + una rama de escenario en el PDF.

**Decision rule**: `verdict=PIN_DAY` y spot dentro de `zone` → **premium 0DTE comprado PROHIBIDO**
(doctrina existente, ahora con el nivel adjunto); fadear los bordes de la zona hacia el pin; cero
compra direccional. Escape solo con cierre confirmado fuera de la zona **y el capitán de acuerdo**.
Vehículo por `optgate.py` (premium ≤$200, spread ≤5%, OI>500).

**Validación**: **el PRIMER test es COLINEALIDAD, no edge**: correlación rodante de `max_pain` con
el `chart_levels.abs_wall` existente a lo largo de la flota — **si `|ρ| > 0.9` la feature es un
re-etiquetado del `abs_wall` y muere inmediatamente**. Después, post-backfill:
`|close − pin|` vs `|close − open|` vs `|close − strike aleatorio cercano|` en viernes de expiry;
necesita **≥40 viernes**, así que es forward-only, y **jamás se publica una `p_pin` desde 4
observaciones**. Prior de literatura: Ni-Pearson-Poteshman dice que debería ser medible.

**Effort** S · **Lang** Python · **Destino** `scripts/pin_clock.py` (nuevo)
· **Skill** [[pin-and-expiry-mechanics]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: en nombres individuales el OI es lo bastante fino para que `max_pain` salte entre
strikes de un día a otro y el veto dispare al azar — de ahí el suelo `min_oi` y la condición de
acuerdo con el `abs_wall`.

---

## 15. `equity-prints archiver` — la cinta firmada (archivador, sin motor)

**Origen**: TrendSpider #5 *tape-absorb* — **solo la mitad archivadora**.

**Edge**: `data/whale_<sym>.txt` es **la ÚNICA cinta firmada que poseemos** (`EPOCH PX USD DIR`,
`DIR ∈ {+1, 0, −1}`) y la **destruimos cada 15 minutos**; sin el archivo la idea de absorción
**no se puede testear nunca**.

**Matemática / procedimiento**
1. En `scripts/ibkr_bar_bridge.py`, **inmediatamente ANTES** del trim existente `cut = now-900`
   de `data/whale_<sym>.txt`, **append** las líneas que se van a `data/history/prints/<date>/
   prints_<sym>.txt` — un append de fichero plano, **NO un insert sqlite** (un `fsync` dentro del
   tick handler pondría latencia en el daemon más load-bearing del sistema).
2. Un cargador batch separado a las 16:30 parsea esos ficheros a
   `trades.db equity_prints(ts, sym, px, usd, dir)` con retención 180 días, y luego gzipea el día.
3. **Publicar cobertura HONESTA**: `WHALE_MIN_USD=50000` significa que esto es un **perfil de
   BALLENAS, no volume-by-price**; `DIR` se clasifica contra un NBBO cacheado localmente
   (**mala clasificación por rancidez**); `whale_aapl/amd/asml/gld.txt` **son 0 bytes** porque
   tick-by-tick solo corre para los syms de foco.

**Inputs exactos**: tick handler de `scripts/ibkr_bar_bridge.py`, `data/whale_<sym>.txt`,
`data/nbbo_<sym>.txt` (para la nota de rancidez). **FALTA**: cobertura de flota completa (solo
syms de foco) y cualquier historia previa al archivador — reportada por sym, jamás asumida.

**Output**: `data/history/prints/<date>/prints_<sym>.txt` (gz nocturno) +
`trades.db equity_prints` + `data/prints_coverage.json
{sym:{sessions, rows, pct_of_session_covered, zero_byte}}`.

**Decision rule**: **NINGÚN motor de absorción hasta que existan ≥20 sesiones archivadas** para un
sym. Solo entonces se testea `ABS(b) = neg(b) / (|Δprice_in_cell|/ATR + 0.1)` contra un null de
**1000× barajado de signos**. Hasta entonces la cinta sigue alimentando `opt_whale_watch`
exactamente como hoy.

**Validación**: Ops — reconciliación de conteo de filas entre el fichero vivo y el archivo (cero
pérdida) y **cero latencia añadida medible** en el bridge (jitter de llegada de barras sobre 3
sesiones). Estadística: **diferida** — el prior es pobre (whale h=15 WR 0.357, n=112, Wilson
[0.28, 0.45]).

**Effort** S · **Lang** Python · **Destino** `scripts/ibkr_bar_bridge.py` (append de 5 líneas) +
`scripts/prints_loader.py` (nuevo)
· **Skill** [[sample-integrity]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: el filtro de $50k más la clasificación ruidosa de `DIR` pueden hacer la cinta
archivada inservible para absorción; el archivo sigue siendo un seguro barato y el nombrado honesto
previene sobre-afirmar.

---

## 16. `chain-cube archive` + política de retención

**Origen**: el **entregable real** de MenthorQ #1 (*gamma-delta-flow*: "construye el cubo, no los
escalares") fusionado con la nota de archivado de TrendSpider #1.

**Edge**: `data/history/<date>/opt_chain_<sym>_HHMM.txt` (**2140 ficheros, ~171k filas el
2026-07-24**) es el activo más sub-explotado que poseemos **Y su única copia son ficheros planos
de 4 días**; persistirlo es el prerrequisito de todo estudio gamma que se acumule hacia adelante.

**Matemática / procedimiento**
1. Cargador batch a las 16:20 parsea todos los `data/history/<date>/opt_chain_<sym>_HHMM.txt` a
   `trades.db gex_cube(sym_id INT, ts INT, exp INT, strike REAL, right INT, oi INT, vol INT,
   iv REAL, delta REAL, gamma REAL)` con índice en `(sym_id, ts)`.
2. **RETENCIÓN DURA, no negociable**: filas crudas por-strike se guardan **30 días**, luego se
   colapsan en `gex_snap(sym, ts, gross, net, hhi, com, flip, call_wall, put_wall, turn_max,
   vol_hhi)` **indefinidamente**; los ficheros de texto fuente se gzipean tras la carga y se
   borran a los **45 días**.
3. **Aserciones de presupuesto que fallan en voz alta**: `trades.db > 400 MB` (las barras 1m viven
   en un `bars.db` adjunto separado) o `data/history > 3 GB` → ntfy y **abortar** el cargador.
4. Tras esto **NINGUNA feature puede leer los ficheros de texto planos directamente** (fuente
   única de verdad).

**Inputs exactos**: `data/history/<date>/opt_chain_<sym>_HHMM.txt`, `trades.db` (hoy 59 MB;
`data/` 157 MB; `data/history` 32 MB para 4 sesiones = **~1 GB/mes de cubo** si se deja sin límite).

**Output**: `trades.db gex_cube` + `gex_snap` + `data/cube_health.json
{date, files_loaded, rows, db_mb, history_gb, retention_actions}`.

**Decision rule**: **toda tabla nueva propuesta sin política de retención declarada se rechaza en
review.** Toda consulta de calibración que pase de 2 s dispara un **rollup**, no un índice nuevo.

**Validación**: paridad de conteo de filas entre ficheros y tabla; benchmark de tiempos de query
(`calibration_ledger.grade()` debe quedarse **<2 s**); crecimiento de disco medido sobre 10
sesiones comparado con la proyección de 1 GB/mes, con el rollup verificado manteniéndolo plano.

**Effort** M · **Lang** Python · **Destino** `scripts/cube_loader.py` (nuevo)
· **Skill** [[sample-integrity]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: incluso con rollups el cubo puede ralentizar la db lo suficiente para dañar el
cockpit vivo; el cargador debe soportar un `options.db` adjunto separado desde el día uno.

---

## 17. `iv_hist logger` — acumulación de superficie

**Origen**: SpotGamma — la rejilla *Compass / IV-Rank + Risk-Reversal* que se decidió **NO
proponer** como feature; se conserva como el **logger de coste cero** que la auditoría pidió.

**Edge**: no cuesta nada, no es una feature, y es la única forma de que una feature de skew/IV-rank
pueda existir en 2027: **la historia de superficie no existe hoy y no se puede rellenar hacia
atrás**.

**Matemática, en pasos** (nocturno desde `chain_full_snap`, por sym, por expiry: weekly frontal,
weekly siguiente, monthly frontal)
1. `iv_atm` en el strike más cercano al spot.
2. Interpolar IV a `|delta| = 0.25` **monótonamente en espacio delta** entre los dos contratos que
   lo bracketean (lineal en log-moneyness). Si 0.25 cae **fuera** del rango de deltas disponible,
   guardar `NULL` y poner `extrapolated=1` — **jamás extrapolar**.
3. `rr = iv_25p − iv_25c` ; `smile_slope = (iv_25p − iv_atm)/0.25` ; `term = iv_front − iv_next`.
4. `iv_rank` = percentil de `iv_atm` dentro de sus propias 252 filas previas; **`NULL` hasta
   `n ≥ 60`**.
5. `iv_src` siempre registrado (`'polygon_snapshot'` vs `'ibkr_model'`) y **las dos series jamás
   se mezclan** en una sola.

**Inputs exactos**: `data/history/<date>/chain_full_<sym>.jsonl.gz` (IV por contrato verificado
presente), `scripts/gex_core.py` `bs_*` para re-derivar delta.
**FALTA**: cualquier historia previa a la primera noche del logger — declarado explícitamente.

**Output**: `trades.db iv_hist(sym, date, exp, dte, iv_atm, iv_25c, iv_25p, rr, slope, term,
iv_rank, extrapolated, iv_src)` guardada **indefinidamente** (~90 filas/noche) +
`data/iv_hist_health.json {rows, extrapolated_pct por sym}`.

**Decision rule**: **ninguna.** Es un logger sin factor, sin voz, sin línea de chart. Su existencia
es la precondición de cualquier feature futura de skew, IV-rank, VRP o vanna — y esas quedan
**explícitamente diferidas a 2027** en vez de ajustadas sobre 4 días de datos.

**Validación**: solo aserciones — la interpolación es monótona en delta; `extrapolated_pct`
reportado por sym (se espera alto en nombres de precio alto hasta la feature 19); el `iv_atm` de
Polygon dentro de **3 puntos de vol** de la IV del modelo IBKR en RTH sobre strikes solapados
(cordura, no calibración).

**Effort** S · **Lang** Python · **Destino** `scripts/iv_hist_log.py` (nuevo, llamado por
`scripts/chain_full_snap.py`)
· **Skill** [[chain-data-contract]] · **Veredicto KEEP** · **Ola 1**

**Kill-risk**: ninguno material; el único riesgo es que alguien construya una feature sobre 20
filas — la regla de `iv_rank = NULL` hasta `n ≥ 60` es la guarda.

---

## 18. `levels-5min archive` — el enabler de features en tiempo-de-etiqueta

**Origen**: SpotGamma #7 *stability-10* — **solo el enabler**; el modelo en sí está **muerto**
(ver la lista de muertos, #4).

**Edge**: `data/history/<date>/levels.json` es **UN snapshot al día**, y por eso ninguna feature
condicionada por gamma se puede backtestear **en tiempo de etiqueta**; densificarlo a 5 minutos
desbloquea toda la capa de medición.

**Matemática / procedimiento**
1. Dentro del loop ya residente de `scripts/chart_bridge.py`, hacer append cada 5 minutos a
   `data/history/<date>/levels_5m.jsonl`: `{ts, sym, spot, flip_open, flip_live, flip_src, regime,
   net_gex, gross, hhi, call_wall, put_wall, abs_wall, abs_wall_sign, em_hi, em_lo, iv_atm,
   book_label, vt_open}`.
2. **MEDIR PRIMERO**: delta de RSS y latencia por loop sobre 3 sesiones **antes** de mergear —
   `chart_bridge` son 53 MB, la caja está 1,14 GB dentro del swap con ~88 MB de páginas libres.
   **Si el coste pasa de +5 MB RSS o +20 ms/loop, el escritor se mueve a un proceso cron separado
   de 5 minutos** en vez del daemon WS.
3. gz nocturno, retención 90 días, luego colapso en `gex_snap`.

**Inputs exactos**: `scripts/chart_bridge.py` (loop FastAPI + WS `/stream`),
`scripts/chart_levels.py gen()`, `data/book_quality.json`, `charts/data/levels_<sym>.json`.

**Output**: `data/history/<date>/levels_5m.jsonl(.gz)` reemplazando el `levels.json` diario único
+ `data/levels5m_health.json {snapshots_today, rss_delta_mb, loop_ms_p95}`.

**Decision rule**: **ninguna feature puede condicionar sobre estado gamma en tiempo de etiqueta
hasta que este archivo tenga ≥40 sesiones.** Es precisamente por esto que `stability-10` fue
MATADA en vez de degradada: **sus features no existían en tiempo de etiqueta.**

**Validación**: ops primero — RSS/latencia medidos y publicados. Datos: conteo de snapshots por
sesión **≥70** (09:30–16:00 cada 5 min) con **<2% de huecos**.

**Effort** S · **Lang** Python · **Destino** `scripts/chart_bridge.py` (o
`scripts/levels_snap.py` si el test de coste falla)
· **Skill** [[sample-integrity]] · **Veredicto DEGRADED** · **Ola 1**

**Kill-risk**: añadir trabajo al daemon Python **menos prescindible** en una caja de 8 GB que ya
está swapeando; el test de coste es una puerta dura, no una formalidad.

---

## 19. `cube-widening` — 3er expiry + alas dispersas, 4 syms

**Origen**: MenthorQ #13 *Cube Widening* — **solo los pasos 3-4**, y solo después de las banderas
de honestidad (feature 5).

**Edge**: el flip, la interpolación 25Δ y toda computación de "última estantería positiva"
dependen de colas que **no traemos**: las 80 filas de QQQ abarcan **680–699 con spot 689,98 =
±1,45%**, no el ±6% que anuncia `PCT_BAND`.

**SECUENCIA ESTRICTA, solo después de que embarque la feature 5**
1. **Medir el techo real de líneas de market-data de la cuenta viva** contra las ~90 líneas que
   `ibkr_bar_bridge` ya sostiene (3/sym) más la ráfaga del fetcher.
2. `exps = sorted(...)[:2]` **+ el monthly del 3er viernes más cercano**, para **CUATRO syms
   solamente (QQQ, SPY, NVDA, MU)** — no siete.
3. Selección de strikes: los **14 más cercanos** MÁS **cada 3er strike** hasta el `PCT_BAND=0.06`
   real → **idéntico conteo de líneas, colas reales**.
4. La cabecera gana `exps=3` y `exp_kind` por grupo de filas (0DTE/weekly/monthly).
5. **ASERCIÓN DURA `cycle ≤ 170 s`** (hoy ~157 s con 17 syms); si se rompe, **partir en dos
   daemons escalonados** en vez de tirar símbolos.
6. **JAMÁS reordenar las columnas por fila** (`scripts/opt_quick.cpp` parsea posicionalmente).

**ELIMINADO**: la regla de TRADE `multi_exp_divergence` — 4 viernes no pueden validarla.

**Inputs exactos**: `scripts/opt_chain_cache.py` (`FLEET`, `PCT_BAND=0.06`, `MAX_STRIKES=20`,
conjunto `NARROW`, `CYCLE_S=180`, `SLEEP_TICKS`), parser de `scripts/opt_quick.cpp`, el presupuesto
de líneas de IBKR.

**Output**: el mismo contrato de fichero con un 3er expiry para 4 syms +
`data/chain_lines.json {sym:{lines_requested, rows, cycle_s, narrow}}` + un flag de artefacto:
un muro presente en 0DTE pero **ausente** en weekly+monthly recibe `artifact=1` (**SOLO
REGISTRADO**).

**Decision rule**: **descriptivo solamente**. Los muros con `artifact=1` se dibujan **discontinuos
y nunca se cantan**; los muros **estructurales** (presentes en todos los expiries traídos) pueden
servir como niveles de swing. **Ninguna regla de trade adjunta** hasta `n ≥ 60` expiries del
estudio de supervivencia.

**Validación**: tiempo de ciclo antes/después (afirmar ≤170 s); test de parseo de `opt_quick.cpp`;
`greeks_ok_pct` no debe caer; después el estudio de supervivencia de muros (¿persiste el strike
argmax al día siguiente?) — mantener la distinción artefacto/estructural solo si los estructurales
**sobreviven ≥2× más a menudo** con `n ≥ 60`.

**Effort** M · **Lang** Python · **Destino** `scripts/opt_chain_cache.py` (`backup/` primero)
· **Skill** [[chain-data-contract]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: los límites de líneas de market-data de IBKR y un blowup de ciclo en un Mac de
8 GB; el fallback honesto es el expiry monthly para **2 syms solamente (QQQ, SPY)**.

---

## 20. `vol-trigger` congelado a las 09:35 — veto solamente

**Origen**: SpotGamma #2 *Volatility Trigger™ / Hedge Wall* — degradado a una **etiqueta de
régimen congelada sin probabilidad**.

**Edge**: es un **interruptor de LICENCIA-PARA-FADEAR** más que una señal: **por encima del VT la
reversión a la media está permitida, por debajo del VT fadear está PROHIBIDO** — y la congelación
de las 09:35 significa que el nivel **no puede oscilar y no puede crying-wolf**.

**Matemática, en pasos** (desde `chain_full_snap` SOLAMENTE, y solo para syms con **≥40 strikes
poblados**)
1. `net_gex(K)` vía `gex_core.build_gex`, más el perfil continuo `G(S)` sobre la rejilla ±15% vía
   `flip_recompute` (re-gamma en cada spot hipotético, refinado por bisección).
2. `VT = max{ K ≤ spot : net_gex(K) > 0 y net_gex(K) ≥ 0.05·Σ|net_gex| y ambos strikes vecinos
   poblados }` — **la última estantería DENSA de gamma positiva debajo del spot, NO el cruce por
   cero**. Fallback: el strike listado más cercano a la raíz continua de gamma-cero.
3. **CONGELAR `vt_open` a las 09:35 ET**; `vt_live` es diagnóstico solamente.
4. `dist_vt = (spot − vt_open)/em`.
5. **Pre-armar** cuando `dist_vt < 0.35` **Y** la fase de fuerza ∈ {GIRO, AGOTAMIENTO} **Y** el
   put wall cercano **no** está BUILDING.

**Inputs exactos**: `data/history/<date>/chain_full_<sym>.jsonl.gz`, `scripts/gex_core.py`
(`build_gex`, `flip_recompute`), `scripts/chart_levels.py gen()` para spot/em/regime,
`data/force.json`, `data/bars_<sym>_ibkr.txt`, `data/book_quality.json` (puerta de `n_strikes`).

**Output**: `charts/data/vt_<sym>.json` → `{vt_open, vt_live, zero_gamma, dist_vt_em,
regime_vt: ABOVE|BELOW, shelf_gex_pct, n_strikes, source:'polygon_full', frozen_at}` + una línea
horizontal **congelada** en `charts/live.html` + un string en `why[]` + página 1 del PDF.

**Decision rule**
- `spot > vt_open` → **licencia de reversión a la media**: fadear hacia el call wall, mariposas OK,
  venta de premium permitida.
- `spot < vt_open` → **licencia de MOMENTUM: fadear PROHIBIDO**, ampliar stops, sin trades de pin,
  sin venta de premium; **una banda de Bollinger estirada en contra tuya por debajo del VT es
  CONTINUACIÓN, no rebote elástico** (esto refina la regla 1 de la doctrina).
- El cruce exige **2 prints**. Clase de voz **SIGNAL, nunca DANGER**, hasta que el split de RV
  esté medido.

**Validación**: post-backfill, clasificar cada sesión por apertura-vs-`vt_open` y comparar la vol
realizada de 5 minutos y el rango de Parkinson a cada lado (**SpotGamma publica 13% vs 18% de RV a
5 días**); test de dos muestras con block bootstrap y corrección `n_eff`. Registrar todo cruce en
`backtest_signal_outcomes` con `source='vt_cross'` a 15/60/390 min.
**KEEP COMO VETO** si la tasa de acierto de los fades por debajo del VT es **<45%** (Wilson upper
bound) con `n ≥ 60` sesiones; **kill** si los dos lados son indistinguibles.

**Effort** M · **Lang** Python · **Destino** `scripts/vol_trigger.py` (nuevo) + el watcher de
aproximación plegado dentro de `scripts/price_alarm.cpp`
· **Skill** [[flip-and-vol-trigger]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: si la estantería es un artefacto de la escasez de la cadena, el nivel congelado es
arbitrario y la regla de prohibir-fadear hace **daño real**; la puerta de ≥40 strikes y el umbral
de estantería del 5% son las guardas.

---

## 21. `wall-decay ledger` — conteos primero, cero probabilidad

**Origen**: SpotGamma #3 *wall-decay* (sus estadísticas publicadas de brecha: **83%/89% hold**)
fusionado con MenthorQ #4 (la explicación por dGEX **más la curva de sensibilidad de histéresis**).

**Edge**: reemplaza un **"1er toque rebota ~70%, 3+ exhausto" HARDCODEADO** que viola la regla de
la casa y que hoy se canta en **cada alarma de muro**.

**Matemática, en pasos**
1. Congelar `call_wall`/`put_wall`/`abs_wall` a las **09:35** desde `levels_<sym>.json`.
2. Escanear barras 1m: un **toque** es high/low dentro de `0.10%·S` del nivel, **válido solo
   después de una excursión previa ≥ h·ATR14_1m** de alejamiento (histéresis); incrementar
   `touch_idx`.
3. Resultado a +15 min: `REJECT` (se movió ≥`0.4·em` de vuelta adentro), `BREAK` (cerró
   ≥`0.15%·S` más allá durante 2 barras), `CHOP`.
4. Explicar la **salud** con la gamma DESAPARECIENDO de verdad, no con un contador: `dGEX` en ese
   strike desde el toque anterior (feature 22) y `vol_at_strike / median` → `BUILDING | HOLDING |
   WEAKENING`.
5. **SALIDA OBLIGATORIA: la CURVA DE SENSIBILIDAD de histéresis en `h ∈ {0.25, 0.5, 1.0}`** — si
   el gradiente de `touch_idx` existe **en un solo umbral, no es real**. Es el detector de
   overfit más barato del roster.

**Inputs exactos**: `charts/data/levels_<sym>.json`, `data/bars_<sym>_ibkr.txt` + `poly_bars`
(el lado precio ES backfilleable), `trades.db gex_cube` (volumen intradía por strike — el único
sitio donde vive), `data/book_quality.json`.
**FALTA**: OI pasado, así que los NIVELES de muro de sesiones pre-archivo **no se pueden
reconstruir** → acumulación forward-only.

**Output**: `trades.db wall_touches(ts, sym, wall_type, level_px, touch_idx, regime, hour, health,
dgex, outcome)` + `data/wall_stats.json` con clave `'<class>|<type>|<touch_idx>'` y
`{n, reject, sens_curve}` — **SOLO CONTEOS. Sin `p_reject`, sin CI, sin voz, sin puerta de ticket**
hasta que una celda tenga `n ≥ 40` clusters-día INDEPENDIENTES.

**Decision rule**: hasta que una celda califique, los veredictos de muro se cantan **SIN NÚMERO**
(*"muro 690, 2º toque, régimen POS"* y nada más) — **y el 70% hardcodeado SALE de la skill
`gamma-regime-walls` el día que esta tabla exista, diga lo que diga la tabla.** Una vez calificada:
operar el muro solo cuando `p_lo ≥ 0.55` para el `(touch_idx, regime, health)` actual;
`touch_idx ≥ 3` **o** `health=WEAKENING` → **nunca fadear**, voltear al lado de la ruptura tras
retest-y-rechazo.

**Validación**: H0 = tasa de rechazo = 50% e independiente de `touch_idx`. **Keep** si ≥3 celdas
superan Wilson-LB 0.55 con `n ≥ 40` clusters-día **Y** una tendencia monótona en `touch_idx`
sobrevive un test chi-cuadrado **EN LOS TRES umbrales de histéresis**. Test de ticker held-out:
ajustar en QQQ/SPY/NVDA/MU, testear en SMH/AMD/TSM.
**Expectativa honesta: 6–12 meses antes de que alguna celda califique.**

**Effort** M · **Lang** Python · **Destino** `scripts/wall_ledger.py` (nuevo) + extiende
`scripts/calibration_ledger.py`
· **Skill** [[book-quality-veto]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: hambre de `n`: ~1 toque/sym/día repartido entre `type × touch_idx × regime ×
health` = 36+ celdas significa que la respuesta honesta durante un año es *"no hay diferencia
medible entre el 1er y el 3er toque"*.

---

## 22. `chain-delta engine` — volumen ponderado por gamma, turnover, HHI

**Origen**: **el triple duplicado colapsado en un solo motor en sombra**: SpotGamma #1 (*DNF /
HIRO*) + TrendSpider #1 (*gex-drift*) + MenthorQ #1 (*gamma-delta-flow*).

**Edge**: si algo en la cadena de 5 minutos se mueve antes que el precio, es el **VOLUMEN por
strike** (el único campo que realmente cambia intradía), y esta es la única forma honesta de
testearlo **sin afirmar una cinta firmada que no tenemos**.

**Matemática, en pasos** (por par de snapshots consecutivos de 5 min, por strike)
1. `dvol = vol_t − vol_{t−1}` (descartar `≤ 0`).
2. `gwv(K) = gamma_BS(S,K,T,iv) · dvol · 100 · S² · 0.01`, calls menos puts por convención de
   dealer → `gwv_calls` / `gwv_puts`.
3. `dwv(K) = |delta_K| · dvol · 100 · S` (**SIN SIGNO**) — esto también **actualiza
   `scripts/opt_whale_watch.py`** de ponderación por conteo-de-contratos a ponderación por
   `|delta|`, la normalización teóricamente correcta.
4. `turn(K) = vol_t(K)/max(oi(K),1)` y `dturn` sobre 3 snapshots.
5. `vol_hhi = Σ((dvol_K/Σdvol)²)` ; GEX CoM = `Σ K·|GEX_K| / Σ|GEX_K|` ; `hhi_gex`.
6. **CONTROL DE SPOT CONGELADO, OBLIGATORIO**: recomputar CoM y GEX con el spot fijado en
   `spot_0935` vía `chart_levels.gen(sym, spot=spot_0935)` y **publicar solo el residuo**
   `dcom_resid = dcom − dcom_frozen`. **Si `|dcom_resid| < 0.5·|dcom|`, la deriva es PRECIO
   re-etiquetado y el campo publica `NULL`.**
7. z-score de `gwv` contra la propia distribución de 3 días de esa banda de strikes.

**PROHIBIDO: la palabra "firmado"/"signed"**. `/v3/trades/O:` es `NOT_AUTHORIZED`; los cambios de
mid a 5 minutos están **dominados por `vega·dσ`**, así que un firmador por residuo de premium es
una moneda al aire; y `dvol` es volumen **NETO acumulado** sobre cientos de prints bilaterales — no
hay lado por print que recuperar.
`kappa` (OI provisional) **solo se publica** si una regresión semanal del `dOI` de la mañana
siguiente sobre el volumen por strike del día previo da **R² > 0.3** para ese `(sym, dte ≥ 1)`;
si no `kappa = null` y queda el z-score crudo.

**Inputs exactos**: `trades.db gex_cube` (feature 16) + `data/opt_chain_<sym>.txt` vivo,
`data/nbbo_<sym>.txt` (spot vivo), `scripts/gex_core.py bs_gamma`,
`scripts/chart_levels.py gen(spot=...)` para el control, `scripts/opt_whale_watch.py`.
**FALTA**: lado agresor e OI intradía — **no se acepta ningún proxy**; la feature simplemente no
los reclama.

**Output**: `data/chain_delta_<sym>.json` → `{gwv_calls, gwv_puts, gwv_z, dwv_z,
turn_max:{strike, turn, dturn, state}, vol_hhi, com, com_resid, hhi_gex, kappa, kappa_r2,
frozen_spot_ok}` — **5 syms solamente (QQQ SPY SMH NVDA MU), `weight=0` en `direction_view`,
BANNER SOLAMENTE, sin voz.**

**Decision rule**: **NINGUNA mientras esté en sombra.** La hipótesis bajo test es: *"el muro en el
camino está siendo COMIDO (`turn > 1.25` y subiendo) ⇒ el prior de fade en el primer toque queda
SUSPENDIDO y la ruptura está permitida"*. Nada actúa sobre esto, nada habla, y **no puede
reemplazar a `captain_flow`** antes de que `null-control` lo apruebe.

**Validación**: etiquetar eventos de `turn`/`gwv` en el archivo del cubo; retorno forward a
+5/+15/+30 min contra un null de **timestamps barajados dentro del mismo `sym × hora`**; corregido
por `n_eff`; mantener un bucket solo con **Wilson-LB ≥ null + 8pp** y `n ≥ 60` clusters-día.
**PRE-PUERTA DURA: si el test de residuo de spot congelado FALLA (el caso base probable, ya que el
OI intradía es estático) la feature ENTERA se BORRA en vez de mitigarse.**

**Effort** M · **Lang** prototipo Python, C++23 **solo si sobrevive** · **Destino**
`scripts/chain_delta.py` (nuevo); `scripts/dnf_pulse.cpp` solo tras validación;
`scripts/opt_whale_watch.py` (upgrade a peso-delta)
· **Skill** [[dealer-flow-limits]] · **Veredicto DEGRADED** · **Ola 3**

**Kill-risk**: el OI intradía estático convierte la deriva de CoM/GEX en un artefacto de spot, y
el volumen por strike agrega ambos lados, así que el motor entero puede ser **ruido ponderado por
gamma**; la puerta de spot congelado está diseñada para matarlo **rápido y barato**.

---

## 23. `cor-fleet` — amortiguador de correlación realizada para la regla 12

**Origen**: SpotGamma #8 *cor-fleet / COR1M* — **la pata implícita ELIMINADA**.

**Edge**: convierte la jerarquía de capitanes de una regla fija en una **variable de estado**
usando solo barras: cuando la flota se mueve como una, el capitán **debe anular** al nombre; en
dispersión, los niveles de nombre individual **son** el edge.

**Matemática, en pasos**
1. `rho_real` = correlación de Pearson media por pares de retornos de 1 minuto sobre los últimos
   60 minutos, computada **dos veces**: sobre el subconjunto de componentes de QQQ y sobre
   `signal_conditioning.SEMIS`. **Inner-join de epochs** entre `data/bars_*_ibkr.txt` y
   **PUBLICAR la tasa de descarte**; **fail loud por encima del 20%** (los nombres ilíquidos tienen
   agujeros).
2. `pct_60d` = percentil de `rho_real` frente a sus propias 60 sesiones previas (**`NULL` hasta
   que el backfill provea 60 sesiones**; hasta entonces se usa un prior fijo **y se etiqueta**).
3. `regime` = `MACRO` (`pct > 0.7` o `rho_real > 0.75`), `DISPERSION` (`pct < 0.3` o
   `rho_real < 0.45`), si no `MIXED`.
4. `captain_coef = 1.25 / 1.0 / 0.75` y `name_coef = 0.8 / 1.0 / 1.2`.

**ELIMINADO**: `rho_imp` — `iv_atm` está poblado para ~**6 de 30** nombres, así que una versión
implícita sería **un proxy del VIX disfrazado**.

**Inputs exactos**: `data/bars_*_ibkr.txt` (1m, inner-join por epoch), pesos de
`scripts/index_breadth.py`, `scripts/signal_conditioning.py` `SEMIS`/`governing_captain`,
`trades.db peer_weights` (**solo después de que la feature 29 lo endurezca**), `poly_bars` para el
percentil de 60 sesiones.

**Output**: `data/cor_fleet.json` → `{rho_real_qqq, rho_real_smh, pct_60d, regime, captain_coef,
name_coef, join_drop_pct, n_pairs}`.

**Decision rule**: amortiguador **MULTIPLICATIVO** sobre los pesos EXISTENTES `fleet(1.4)` /
`components(1.3)` — **jamás un factor aditivo nuevo**.
`MACRO` → regla 12 a plena fuerza: un capitán opuesto **anula** la señal del nombre (banner, sin
voz). `DISPERSION` → un capitán opuesto solo **degrada DANGER a SIGNAL**.
**El coeficiente aplicado DEBE imprimirse en `why[]`** (*"capitan ×1.25, rho 0.81"*) — una flecha
cuyos pesos se mueven con una variable de estado invisible es **inauditable tras una pérdida**.

**Validación**: re-calificar las 972 señales únicas partiendo las señales de nombre por el tercil
de `rho_real` de ese día; H0 = el override del capitán añade el mismo valor en ambos regímenes.
Mantener el coeficiente dinámico solo si la tasa de acierto de señales de nombre en `DISPERSION`
excede la de `MACRO` en **≥8pp** con intervalos de Wilson corregidos por `n_eff` **no solapados**
y `n ≥ 100` por tercil. Subpotenciado hoy (8 sesiones ≈ 3 días de régimen) → **embarcar con el
prior fijo** y revisar post-backfill.

**Effort** S · **Lang** Python · **Destino** `scripts/cor_fleet.py` (nuevo) + un hook de
coeficiente en `scripts/direction_view.py`
· **Skill** [[peer-captain-evidence]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: en una flota que es 26/30 semis, `rho_real` puede estar por encima de 0.7 **todos
los días**, dejando el amortiguador como una constante — en cuyo caso es **doctrina, no una
variable de estado**, y debe hardcodearse honestamente como tal.

---

## 24. `close-drift` — DEX + charm, **validación PRIMERO**

**Origen**: SpotGamma #6 *charm-clock* fusionado con MenthorQ #9 *close-drift* (el par duplicado).
**Validación antes de cualquier construcción.**

**Edge**: `gex_core.bs_charm` **existe y no lo consume nada**; el charm es el único flujo de hedge
**mecánico y libre de noticias** entre las 14:00 y el cierre, y la **trampa de signo del DEX** que
arregla es un foot-gun vivo y real.

**Matemática, en pasos**
1. `DEX_K = delta_K · OI_K · 100 · S` con el signo de dealer; `net_dex = Σ`.
   **Publicar DOS campos, nunca uno**: `dex_sentiment` (posicionamiento del cliente: positivo =
   alcista) y `dex_flow_impact` (los MMs deben **VENDER** subyacente para quedar neutrales =
   liquidez negativa).
2. `CEX_K = charm_K · OI_K · 100 · S · T` vía `gex_core.bs_charm` /
   `build_exposure(greek='charm')`; evaluar `C(S)` sobre una rejilla ±3%;
   **`drift_target` = la frontera de cambio de signo de `C(S)` más cercana al spot**.
3. `drift_force = Σ|CEX| / ADV20_notional` escalado por `minutes_to_close/390` → **acciones por
   hora: un TAMAÑO, no una sensación**.
4. `T` con suelo de **1 hora**; **NO publicar charm 0DTE después de las 15:00** (la fórmula
   explota).
5. Armado **solo** cuando `regime=POS`, `book_label ≠ THIN` y `abs_wall_sign='+'` (el pinning por
   charm necesita dealers que **amortigüen**).
6. **REPORTAR NIVELES, NO DERIVADAS**: `d(net_dex)/dt` intradía es un artefacto de OI estático.

**Inputs exactos**: `data/opt_chain_<sym>.txt` (delta, RTH) más `chain_full_snap` para todos los
expiries, `scripts/gex_core.py` (`bs_charm`, `build_exposure`), `data/bars_<sym>_ibkr.txt` para
ADV20, `data/book_quality.json`, `poly_bars` para la validación.

**Output**: `data/close_drift.json` → `{net_dex, dex_sentiment, dex_flow_impact, drift_target,
drift_force_sh_hr, pct_adv, armed, valid_until:'15:00'}` → un marcador punteado en el chart y un
párrafo de tarde en el PDF. **SIN voz, SIN factor en `direction_view`, solo QQQ/SPY/NVDA/MU.**

**Decision rule**: **ninguna hasta validar.** Si valida: **13:30–15:15 solamente** (respetando
"última hora solo gestión"), operar **hacia** `drift_target` **DESDE EL LADO CERCANO**, jamás a
través de un muro intermedio (post-mortem 2026-07-20), salir a las 15:45, tamaño pequeño; **cero
trade** si `abs_wall_sign='−'` (trampilla, no pin) o si `drift_target` cae dentro del 0,15% del
flip (niveles apilados = chop).

**Validación**: **HACER LA VALIDACIÓN PRIMERO y no construir nada hasta que pase**:
`|close − drift_target(13:30)|` vs `|close − max_pain|` vs `|close − spot_1330|` sobre sesiones
backfilleadas, **controlando por el retorno de la mañana** para no redescubrir momentum intradía.
**Keep** solo si el error absoluto mediano bate a la persistencia-de-spot en **≥15%** con un CI de
block bootstrap que **excluya 0** con `n ≥ 120` sym-sesiones **Y** bate a max-pain.
**Cero C++ antes de eso.**

**Effort** M · **Lang** Python · **Destino** `scripts/close_drift.py` (nuevo)
· **Skill** [[pin-and-expiry-mechanics]] · **Veredicto DEGRADED** · **Ola 3**

**Kill-risk**: con 20 strikes el charm **colapsa sobre el strike ATM**, así que la "frontera" es
solo el spot redondeado al strike más cercano (**reproduce max pain en secreto**); y el flujo real
de charm queda enanizado por el desequilibrio MOC / rebalanceo de índices que **no podemos ver**.

---

## 25. `expiry-unwind` — DEX + cuotas de expiry, descriptivo

**Origen**: SpotGamma #12 *expiry-unwind / Next Expiry Gamma% and Delta%* (su regla publicada:
>25% = significativo; concentración de expiración >20–30%).

**Edge**: computa **el régimen que existirá DESPUÉS del viernes, antes del viernes**, y **añade
DEX a `gex_core`** — genuinamente ausente hoy y barato.

**Matemática, en pasos**
1. Añadir `build_exposure(greek='delta')` a `gex_core`: `DEX_K = delta_K · OI_K · S`.
2. Desde `chain_full_snap`: `gamma_share_e = Σ|GEX_e| / Σ|GEX|` y
   `delta_share_e = Σ|DEX_e| / Σ|DEX|` por expiry.
3. Marcar `NEXT_EXP_HEAVY` cuando `gamma_share_next > 0.25` **o** `delta_share_next > 0.25`;
   registrar el split calls-vs-puts del delta que expira.
4. Recomputar el perfil post-roll **excluyendo el expiry que expira** y re-timado (`T − 1/252`):
   `flip_ex, vt_ex, call_wall_ex, put_wall_ex`; publicar `level_shift_pct` frente a hoy.

**Inputs exactos**: `data/history/<date>/chain_full_<sym>.jsonl.gz` (**REQUERIDO** — la cache IBKR
de 2 expiries **no puede** computar cuotas), `scripts/gex_core.py`,
`scripts/chart_levels.py gen(all_exp=True)`, `poly_bars` para la validación.

**Output**: `data/expiry_<sym>.json` → `{next_exp, gamma_share, delta_share,
expiring_side: CALLS|PUTS, post_roll:{flip, vt, call_wall, put_wall}, level_shift_pct,
verdict: MAGNET_THEN_RELEASE|NEUTRAL}` → un banner de jueves-PM/viernes-AM y una rama de escenario
en el PDF.

**Decision rule**: **la mitad IMÁN embarca** y es coherente con la doctrina: `gamma_share_next >
0.30` → el viernes es **día imán** (operar hacia el strike dominante que expira, sin trades de
ruptura, sin 0DTE fuera de la lógica de pin).
**La mitad DIRECCIONAL** (*"puts expirando → los dealers cubren → presión al alza la sesión
siguiente"*) es **BANNER SOLAMENTE, sin voz, sin ticket**, hasta `p_lo ≥ 0.56` con `n ≥ 50`
expiries.

**Validación**: para cada expiry en el `poly_bars` backfilleado, testear si la dirección de la
sesión siguiente concuerda con `expiring_side` y si la vol realizada sube tras expiries de
`gamma_share` alto; registrar `setup_type='post_expiry_unwind'` en `calibration_ledger`.
Hoy tenemos ~4 expiries, así que 50 son ~12 meses hacia adelante — **y la deriva post-expiración
es el efecto clásico que decayó después de publicarse.**

**Effort** M · **Lang** Python · **Destino** `scripts/expiry_unwind.py` (nuevo) +
`scripts/gex_core.py` (DEX)
· **Skill** [[pin-and-expiry-mechanics]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: sin OI de grado OCC las cuotas son ruidosas y el efecto está priceado en el gap del
lunes antes de que podamos actuar; la mitad descriptiva **sigue arreglando un hueco real del mapa**.

---

## 26. `gap-islands` — exportador de niveles, **sin probabilidad de relleno**

**Origen**: TrendSpider #12 *Gap Detector / Gap Proximity / Islands*. Nota: **sus dos defaults se
contradicen por diseño (0.5×ATR vs 3×ATR)**, que es exactamente por qué hay que **MEDIR `k`** en
vez de adoptar uno.

**Edge**: los bordes de hueco y los cortes de isla son **solo-barras**, cuestan cero, y **evitan
que dibujemos niveles a través de una discontinuidad**; el folklore de la probabilidad de relleno
**NO se afirma**.

**Matemática, en pasos**
1. **Hueco overnight**: `|open_0930 − close_prev| > k_on · ATR14_daily`.
   **Discontinuidad intradía 1m**: `|open_t − close_{t−1}| > k_id · ATR14_1m`.
2. Registro de huecos sin rellenar por sym: `{gap_lo, gap_hi, size_atr, dir, age_days,
   earnings_gap}` (el flag de earnings desde las fechas de Finviz Elite — **los huecos de earnings
   se comportan distinto y hay que segregarlos**).
3. `gap_proximity = (price − borde_no_rellenado_más_cercano) / ATR14`.
4. Exportar los bordes de hueco como **niveles** al registro de `level_react`, y las fronteras de
   hueco como **CORTES DE ISLA**: **jamás emparejar pivotes ni dibujar un KDE/nivel a través de un
   hueco >3·ATR**.
5. **`p_fill` NO se computa** hasta que exista el backfill y se bata el null de toque simétrico.

**Inputs exactos**: `poly_bars` (1m incluyendo horas extendidas), `data/bars_<sym>_ibkr.txt`,
fechas de earnings de `scripts/finviz_scan.py`, `charts/data/levels_<sym>.json` para el chequeo de
muro-en-medio.

**Output**: `data/gaps.json` → `{sym:{open_gaps:[{lo, hi, size_atr, dir, age_days, earnings_gap}],
proximity_atr, nearest_edge}}` — **SIN campo `p_fill` hasta validar.** Alimenta `level_react` y la
página de PDF de la ventana de oro 09:45–10:30.

**Decision rule**: los bordes de hueco son **OBJETIVOS** (parciales, apretar stops) y niveles de
evento de `level_react` — **nunca entradas por sí solos**. **Cero trade hacia un borde si hay un
muro OI entre el spot y el borde** (prohibición de atravesar el muro). Huecos de earnings =
**NO-TRADE para premium comprado**.

**Validación**: barrer `k_on ∈ [0.3, 3.0]` y elegir el umbral que maximiza la **SEPARACIÓN** entre
las tasas de relleno de aperturas-con-hueco y sin-hueco, **NO el que maximiza la tasa de relleno**.
**Null = la probabilidad de tocar un nivel equidistante en la dirección OPUESTA** (toque
simétrico) — el test que mata el "los huecos son especiales". Publicar `p_fill` solo para buckets
que batan ese null con `n ≥ 60` clusters-día post-backfill; **se espera que el edge desaparezca y
que la feature quede como exportador de niveles.**

**Effort** S · **Lang** Python · **Destino** `scripts/gaps.py` (nuevo)
· **Skill** [[print-o-nada-levels]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: después de condicionar por distancia en ATR, el edge de relleno es exactamente "el
precio toca un nivel cercano", dejando solo los cortes de isla — que **siguen valiendo la pena**.

---

## 27. `kde-levels` — el único rescate del motor de trendlines matado

**Origen**: TrendSpider #8 — el **mapa de calor horizontal de S/R** (KDE, ancho de banda 3×ATR,
ponderado por recencia). **El motor de trendlines O(pivotes²) está MATADO** (ver muertos #8).

**Edge**: una fuente de niveles de **segunda opinión, solo-barras**, que cuesta cero y **se puede
testear contra el null de 16 aleatorios HOY**, sin la máquina de overfit de los pesos de
confluencia ajustados.

**Matemática, en pasos**
1. Por TF (1m, 5m, 15m como agregaciones de las mismas barras) construir un KDE gaussiano sobre
   `log(close)` de las últimas **365 barras**: ancho de banda = `3.0 · ATR14` expresado en espacio
   log; pesos = **rampa lineal de recencia de 0.2 (más viejo) a 1.0 (más nuevo)**.
2. Muestrear **200 puntos** de rejilla; tomar picos con **prominencia ≥ 0.15·max**.
3. Precio del nivel = `exp(x)`; **deduplicar dentro de 0.25·ATR**; **tope de 5 niveles por sym por
   TF**.
4. **Consciente de islas**: una ventana KDE **jamás abarca un hueco >3·ATR** (cortes de la
   feature 26).

**NO SE CONSTRUYE**: enumeración de pivotes, scoring de trendlines, pesos de confluencia ajustados.

**Inputs exactos**: `data/bars_<sym>_ibkr.txt` (agregaciones 1m/5m/15m), `poly_bars` para el
backtest, `data/gaps.json` para los cortes de isla.

**Output**: `data/levels_auto_<sym>.json` → `{tf, lock_ts, kde:[px, ...]}` → puede entrar en el
registro de `level_react` **solo DESPLAZANDO** un slot de menor prioridad (el registro tiene tope
de 6 tipos).

**Decision rule**: un nivel KDE es operable **solo** como evento `BOUNCE` o `RETEST_REJECT` cuya
celda haya pasado el null de nivel aleatorio; **siempre cede** ante los muros OI y ante el capitán,
y **nunca se canta por sí solo**.

**Validación**: tasa de rebote en niveles KDE frente a **1000 niveles aleatorios por sesión** (el
arnés de random-16 de la feature 2). El prior de Osler es **+4 a +5pp**. Mantener solo las celdas
`(tf × regime)` con Wilson-LB por encima de la tasa aleatoria con `n ≥ 80` clusters-día.
**BORRAR la feature si no bate a `POC_DOM` + máximos/mínimos del día previo**, ya que **~90% de
redundancia es el caso esperado**.

**Effort** S · **Lang** Python · **Destino** `scripts/kde_levels.py` (nuevo)
· **Skill** [[print-o-nada-levels]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: casi con certeza redundante con `poc_dom`/`abs_wall`/PDH-PDL; el valor es que la
redundancia se **MIDE una vez** en vez de discutirse, y el tope de 5 niveles mantiene el registro
usable.

---

## 28. `skew-lead` — risk reversal 25Δ diario, **sin voz**

**Origen**: MenthorQ #5 *skew-lead / 25Δ RR* (`RR = IV(25Δ put) − IV(25Δ call)`) + la "pendiente
de la IV" del Option Q-Score (#23) — **degradado a un diagnóstico diario alimentado por snapshot**.

**Edge**: un RR subiendo significa que **están pujando los puts**: es la **corroboración de que un
print de BALLENA-CALLS es un TECHO local** (los dealers comprando downside) en vez de continuación
— hablado como **contexto, jamás como gatillo**.

**Matemática, en pasos**
1. Diario desde `iv_hist` (feature 17): `rr = iv_25p − iv_25c`, `drr_1d`, y `z` frente a sus
   propias 60 sesiones previas (**`NULL` hasta `n ≥ 60`**).
2. `smile_slope` y `term` tal como se registran.
3. **RR intradía SOLO** para los 4 syms ensanchados (feature 19) y **solo cuando el contrato de
   `|delta| = 0.25` está realmente DENTRO de la banda traída**; si no `extrapolated=1` y el valor
   se **suprime**.
4. `iv_src` siempre arrastrado, y **la IV del snapshot de Polygon JAMÁS se mezcla en una serie con
   `modelGreeks.impliedVol` de IBKR** (una salida de modelo suavizada, ausente fuera de RTH).

**Inputs exactos**: `trades.db iv_hist`, `data/opt_chain_<sym>.txt` (solo RTH, syms ensanchados),
`scripts/gex_core.py`, `data/whale_flow_hist.jsonl` para el cruce espada-ballena.
**FALTA**: cualquier historia de superficie previa al logger — `z` es **NULL** las primeras 60
sesiones **y ese NULL se muestra, no se rellena**.

**Output**: `data/skew.json` → `{sym:{rr, drr_1d, z, smile_slope, term, iv_src, extrapolated,
n_hist}}` → una línea en la página 1 del PDF, un banner del cockpit y contexto del narrador.
**SIN voz, SIN factor en `direction_view`.**

**Decision rule**: **contexto solamente**. `z(drr) > 2` con el sym por encima de su call wall
**refuerza** una decisión de fade/cobrar **YA TOMADA sobre precio y gamma**; **nunca inicia**.
`z(drr) < −2` por debajo del put wall refuerza la lectura de suelo del call-scalp espada-ballena.
Si `z` es NULL (`n_hist < 60`) **la línea se OMITE por completo**.

**Validación**: el soporte publicado (**skew de Xing-Zhang-Zhao**, **vol spread de
Cremers-Weinbaum**) es **TRANSVERSAL a horizontes SEMANALES**, no un lead intradía de 10 minutos —
así que el estudio es el retorno forward a 1/3/5 días regresado sobre `z(drr)` con errores **HAC
(Newey-West)** y un null de timestamps barajados, por sym, revisitado en **2027** con un año de
historia de superficie.
**Veredicto HOY: DATA-INSUFFICIENT, y la feature lo dice en voz alta.**

**Effort** S · **Lang** Python · **Destino** `scripts/skew.py` (nuevo, lee `iv_hist`)
· **Skill** [[dealer-flow-limits]] · **Veredicto DEGRADED** · **Ola 3**

**Kill-risk**: `|delta| = 0.25` cae **fuera de nuestra banda** para la mayoría de los nombres y
expiries de la flota, así que la mayoría de las filas serán **solo-Polygon y diarias**; la
afirmación de lead intradía puede no ser testeable nunca con este presupuesto.

---

## 29. `peer-weights hardening` — mata tres features **midiéndolas**

**Origen**: TrendSpider #10 *ratio-tape* / MenthorQ #6 *blind-spots* / MenthorQ #11 *borrowed-map*
— **las tres descansan sobre `trades.db peer_weights`, que tiene 19 FILAS EN TOTAL**.

**Edge**: **anticipar desde un lag espurio es el modo de fallo más caro posible**; esto mide si
alguna relación lead-lag de nuestra flota **sobrevive un null correcto** antes de permitir que algo
actúe sobre ella.

**Matemática, en pasos** (re-ajustar `peer_weights` como se debe)
1. Retornos de 1 minuto **inner-joined por epoch**, con la **tasa de descarte publicada por par**.
2. `corr` con errores estándar **HAC (Newey-West, lag 5)** y t-stats.
3. `lead_min` de la correlación cruzada aceptado **SOLO** si el pico sobrevive **AMBOS**:
   (a) un null de **1000× timestamps barajados**, y
   (b) un **control de factor común**: regresar ambas patas sobre SMH y QQQ primero, y luego
   cross-correlacionar **los RESIDUOS** — las cotizaciones **asíncronas** en activos que
   co-mueven producen picos espurios a lag no-cero **por construcción**.
4. `beta` por OLS sobre retornos residualizados, con `n` y `R²`.
5. **Publicar CUÁNTOS pares sobreviven** (expectativa: **0–2 de 19**).

**Inputs exactos**: `trades.db peer_weights` (19 filas), `scripts/peer_influence.py` (corr/beta/
lead-lag por duckdb), `data/bars_*_ibkr.txt` + `poly_bars` (post-backfill, para muestra real),
`scripts/signal_conditioning.py governing_captain`.

**Output**: `trades.db peer_weights` extendida con `(se, tstat, lead_survives, shuffle_p,
resid_corr, n_eff)` + `data/peer_health.json {pairs_total, pairs_survived, drop_rate}`.

**Decision rule**: **cualquier consumidor** (amortiguador del capitán, niveles prestados, ideas de
ratio) puede usar **SOLO** pares con `lead_survives=1`. **Si CERO pares sobreviven,
`governing_campaign()`… `governing_captain()` sigue siendo una regla de DOCTRINA** (SPY/QQQ =
mercado, SMH = semis) **sin ninguna afirmación de lead medido adjunta — y lo decimos en la skill
en vez de inventar un número.** Esta es también la puerta que **retira formalmente** `ratio-tape`,
`blind-spots` y `borrowed-map`.

**Validación**: **ESTO ES la validación de tres features propuestas.** El entregable = el conteo de
supervivientes con p-values de barajado y la tasa de descarte del join por epoch. **El éxito es un
número creíble, incluido el cero.**

**Effort** S · **Lang** Python · **Destino** `scripts/peer_influence.py` (endurecido) +
`scripts/peer_health.py` (nuevo)
· **Skill** [[peer-captain-evidence]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: con 21 sesiones de barras 1m sobre semis con `ρ ~ 0.8`, **incluso un método
correcto devuelve "no hay lead medible"** — la respuesta útil, pero se sentirá como una pérdida.

---

## 30. `finviz-snap archive` + componentes de squeeze, **sin score compuesto**

**Origen**: SpotGamma #14 *squeeze-scan* — **archivo primero, componentes solamente, compuesto
ELIMINADO**.

**Edge**: sin un archivo nocturno de Finviz, **cualquier backtest de squeeze está contaminado por
look-ahead por construcción** (la historia de short-float **no existe**), así que **el archivo ES
la feature**; los componentes son una **watchlist, no una señal**.

**Matemática, en pasos**
1. Nocturno a las 20:00: archivar el export del screener de Finviz Elite para la flota más el
   universo de extensión a `data/history/finviz/<date>.csv` (`short_float_pct`, `float_shares`,
   `ADV20`, `days_to_cover`, `earnings_date`, `insider`, `price`).
2. **Publicar COMPONENTES, jamás un compuesto**:
   - `otm_call_gamma_per_float = Σ_{K ∈ (S, 1.07S], DTE ≤ 10} gamma(K)·callOI(K)·100 /
     float_shares` (desde `chain_full_snap`)
   - `short_float_pct`
   - `days_to_cover`
   - `opt_vol_ratio = option_volume·100 / ADV20_shares`
   - signo de `net_gex`
3. **Rankear cada componente SEPARADAMENTE y mostrarlos TODOS.**

**ELIMINADO**: `squeeze_score = 0.35z + 0.30z + 0.20z + 0.15flag` (cuatro z-scores transversales
sobre 30 semis que co-mueven es una **máquina de multiple testing que ajustará el rally de memoria
de julio**) y **ELIMINADO** el pre-armado en `price_alarm.cpp`.

**Inputs exactos**: `scripts/finviz_scan.py` / `scripts/finviz_scout.cpp` (Finviz Elite),
`data/history/<date>/chain_full_<sym>.jsonl.gz`, `charts/data/levels_<sym>.json` (`net_gex`),
`data/bars_*_ibkr.txt`.
**FALTA**: historia archivada de short-float — **exactamente lo que esta feature crea,
forward-only**.

**Output**: `data/history/finviz/<date>.csv` (**permanente**) + `data/squeeze_components.json`
(tabla rankeada con **todos** los componentes visibles y **SIN campo de score**) → una sección del
email de pre-apertura y una página de PDF para el top 3.

**Decision rule**: un candidato a squeeze es una **FILA DE WATCHLIST, jamás una entrada y jamás una
alarma pre-armada**, hasta que el compuesto se valide sobre **≥40 días-candidato de datos
ARCHIVADOS** (no reconstruidos). Si un candidato **sí** imprime a través de su cluster de call-OI
de corto plazo, el trade es **CONTINUACIÓN** (el veto de Bollinger **se invierte** aquí, por la
cláusula de band-walk), pero **solo** en un nombre de la flota con `book_quality` VERDE; en nombres
ilíquidos `optgate` dirá **OPCIONES VETADAS → acciones**.

**Validación**: forward-only desde el primer día del archivo:
`P(movimiento al alza ≥5% en 3 días | componente en decil superior)` frente a la tasa base,
registrado como `setup_type='gamma_squeeze'` en `calibration_ledger`;
**keep** con `p_lo ≥ base + 10pp` con `n ≥ 40` días-candidato y **BH-FDR entre componentes**.

**Effort** S · **Lang** Python · **Destino** `scripts/finviz_snap.py` (nuevo) +
`scripts/squeeze_components.py` (nuevo)
· **Skill** [[anti-overfit-killlist]] · **Veredicto DEGRADED** · **Ola 2**

**Kill-risk**: los componentes pueden rankear **los mismos 6 nombres de memoria todos los días**
(MU/SKHY/DRAM/SNDK/WDC/STX), haciendo la watchlist un espejo de la flota — en cuyo caso **solo
sobrevive el archivo, y ese era el punto**.

---

# LOS 16 MUERTOS — con su refutación numérica

**Por qué esta tabla existe**: los muertos valen tanto como los vivos. Sin esta sección, alguien
reinventa `signed-oi` en tres meses y gasta una semana en descubrir de nuevo que
`open_frac ≈ 0.01`.

| # | Propuesta (origen) | La crítica que la mató — con NÚMEROS |
|---|---|---|
| 1 | **SG-5 `signed-oi`** (inventario de dealer por reconciliación de ΔOI) | Refutada numéricamente sobre nuestro propio fichero: **QQQ 685C = vol 238.672 vs OI 2.348**, así que `open_frac = \|ΔOI\|/V_day ≈ 0.01` y la restricción de mínimos cuadrados **no tiene casi apalancamiento** en días 0DTE/índice — los ÚNICOS días para los que se propuso. Construcción **más pesada (L)** con el **menor** apalancamiento; y su regla (anular la etiqueta de régimen cuando los dos flips discrepan >0.3%) **convierte su propio ruido en un veto silencioso a nivel de flota**. |
| 2 | **SG-10 `vanna-ramp`** (predictor de compra forzada por IV crush) | **Dos inputs MUERTOS**: `beta_spotvol` ajustado sobre **4 días** de IV IBKR mayormente ausente, y "IV crush post-earnings medido desde `poly_opt_bars`", una tabla **SIN IV y SIN griegas** (verificado). Su artefacto es una **voz a las 09:45 la mañana después de un print** = un número no validado en el máximo de adrenalina. Solo sobrevive `iv_hist` (feature 17). |
| 3 | **SG-13 `dpi-lite`** (índice de acumulación dark-pool desde FINRA) | `CNMSshvol` de FINRA es alcanzable (200) **pero es volumen CORTO fuera de bolsa, no acumulación en dark pool**; la **réplica bayesiana independiente de SqueezeMetrics pone el edge de DIX en ~0**; horizonte de **60 días** contra un stack intradía; y **no podemos ni testearlo** (necesita 60 días de datos forward). Correr el rechazo una vez como research si hay curiosidad, **cablear nada**, borrar el fetcher. |
| 4 | **SG-7 `stability-10`** (P[movimiento grande en 10 min]) | `p(big move)` a partir de RV/mediana, %B, fuerza y agotamiento es una **recodificación MONÓTONA de lo que `force_meter` + `momentum_calc` ya publican**, y sus features gamma exigen **historia de niveles a 5 minutos que NO EXISTE** (1 snapshot/día, 4 días). **27 celdas con n≥50 sobre 21 sesiones es inconstruible.** Solo sobrevive el enabler (feature 18). Si se quiere un multiplicador de ancho de stop: **vol realizada de 5m sobre su propia mediana de 20 días, una expresión, cero celdas.** |
| 5 | **SG-9 `em-measured`** (EM como cuantil histórico condicionado) | Un percentil 68,3 de `\|retorno 1 día\|` condicionado por **VIX × tercil GEX × VT × earnings** son **~24 celdas contra 21 sesiones** y **~2 nombres efectivamente independientes**; su propia H0 (*no añade nada sobre un cuantil de ATR de 20 días*) es la respuesta probable. El valor determinista se **absorbió en la feature 10**. |
| 6 | **El `squeeze_score` compuesto de SG-14** | **Cuatro z-scores transversales** sobre 30 semis co-movientes **SIN historia archivada de short-float de Finviz** está **contaminado por look-ahead por construcción**. Solo sobreviven el archivador y los componentes visibles (feature 30). |
| 7 | **TS-4 `vw-drops`** (serie OHLC ponderada por volumen, matemática Raindrop) | Con **~5 sub-barras de un minuto por mitad**, `leftVWAP`/`rightVWAP` es **una media de 5 muestras**, colineal (**ρ>0.95**) con el z-score de VWAP y el momentum EMA que `momentum_calc.cpp` ya tiene; **el propio white paper del vendor reporta que los patrones PERDIERON dinero (66 trades, −0.16%)**; y crearía un **segundo par %B/fuerza contradictorio con una regla de desempate no medida DENTRO de nuestro hot path más load-bearing**. |
| 8 | **TS-8 `trendline-engine`** (motor de trendlines automáticas) | **O(pivotes²) × 3 TFs × 30 syms** en una caja con **load 2.4 y 1,14 GB de swap usado**, para niveles que el autor **concede que son ~90% redundantes** con muros/POC/PDH-PDL, con **pesos de confluencia AJUSTADOS sobre 21 días** en 6 términos correlacionados, inyectando **hasta 200 líneas/sym** en el registro. Solo sobrevive la mitad KDE (feature 27). |
| 9 | **TS-9 `avwap-anchors`** (VWAP anclado por eventos) | Intradía **todo ancla converge a la VWAP de sesión ± ruido** (su propio null de ancla aleatoria es el test que la mata); `momentum_calc` **ya** computa el z-score de VWAP; las anclas de cluster de ballena necesitan **historia de cinta que no existe** y solo para syms de foco; y las anclas **forward-looking** son un **foot-gun de look-ahead** cuyo "hard assert" acaba comentado a las 09:40. |
| 10 | **TS-10 `ratio-tape`** (cinta de ratios capitán-vs-tropa) | Descansa sobre `peer_weights`: **19 filas en total**, ajustadas sobre ≤21 días de barras 1m entre activos con **ρ~0.8**. **Los picos de correlación cruzada a lag no-cero entre activos co-movientes cotizados de forma asíncrona son el resultado espurio de libro de texto**, así que `lead_min` probablemente **mide rancidez de cotización**. Reemplazadas por la feature 29, cuyo entregable es el conteo de supervivientes. |
| 11 | **MQ-6 `blind-spots`** (clusters de niveles proyectados de peers) | Igual que #10 (`peer_weights`, 19 filas, ρ~0.8, lag espurio). Además: con una flota 26/30 semis todos muy correlacionados con SMH/QQQ, los clusters pueden **reproducir simplemente los niveles del propio índice**. |
| 12 | **MQ-11 `borrowed-map`** (niveles gamma prestados del padre) | Igual que #10/#11, **y encima LAVA UN VETO CONVIRTIÉNDOLO EN SEÑAL**: **fabrica niveles gamma exactamente para los nombres que `book-quality` MUTEA**, y su decision rule (*"solo cuando el padre está en el nivel del padre"*) **es literalmente la regla 12**. |
| 13 | **TS-13 `fleet-rank`** (TechRank / Relative Performance) | Los dos términos más pesados de TechRank (**slowEMAdist 0.30 + slowROC(125) 0.30 = 60% del score**) son **incomputables desde 21 días** y vendrían de un batch rancio de yfinance, para luego recibir **autoridad de desempate sobre la selección de vehículo**; y un universo de **26 de 30 semis** tiene **dispersión transversal casi nula exactamente en los días risk-on**. `fleet_pulse` **ya** nombra al líder del día. |
| 14 | **TS-11 `expansion-clock`** (estacionalidad de la volatilidad) | 21 sesiones dan **~21 observaciones por bucket de minuto-del-día por sym** ("astrología", palabras del propio autor) y `timeofday_calib` **ya posee la dimensión horaria**; agrupar dentro de SEMIS **lava el reloj por ticker que era el punto**. **Reabrir SOLO** cuando la feature 4 entregue 2 años, y entonces **estrictamente como veto de compresión sin probabilidad**. |
| 15 | **MQ-14 `mechanical-supply`** (proxy vol-control / vol-barometer) | `RV63` necesita **63 cierres diarios (tenemos 21)**; LSVB necesita líneas de market-data de UVXY/VXX/SVIX **contra el único recurso genuinamente escaso**; y es **un efecto macro publicado de 1–5 días** sobre un stack cuyo edge entero es intradía. La pendiente del VX de `cboe-data` **ya** da la lectura de régimen. |
| 16 | **El titular `converge`/`eta_min` de MQ-2 y el overlay "imán móvil" de CoM de TS-1** | **La misma tautología de OI estático**: el OI de IBKR es de **cierre previo y está CONGELADO intradía**, así que `dflip/dt` y `dCoM` miden **el spot moviéndose bajo un libro congelado**. Los arreglos de bug sobreviven (feature 6); el control de spot congelado se convirtió en una **pre-puerta DURA dentro de la feature 22** en vez de una mitigación post-hoc. |

**Matado también como AFIRMACIÓN (la construcción sobrevive renombrada)**: el flujo delta-nocional
**"FIRMADO"** de SG-1. `/v3/trades/O:` y `/v3/quotes/O:` son **NOT_AUTHORIZED** (verificado); el
firmador por residuo de premium **omite el término `vega·dσ` que DOMINA los cambios de mid a 5
minutos**; y `dvol` es volumen **NETO acumulado** sobre cientos de prints bilaterales — **no hay
lado por print que recuperar**. La feature 22 conserva el volumen ponderado por gamma/delta **SIN
signo**, bajo un nombre que no miente.

## DIFERIDAS, no matadas

- **HIRO real** vía IBKR `reqTickByTickData("AllLast")` sobre ±10 strikes de QQQ 0DTE — es un
  **spike P1**, y las líneas deben salir **DE LAS ~90 que el bridge ya sostiene**, no encima.
- **El motor de absorción de ballenas** — tras 20 sesiones de `equity_prints`, contra el null de
  barajado de signos.
- **La rejilla Compass / IV-rank de 25 delta** — **2027**, después de que `iv_hist` tenga un año.
- **`expansion-clock` y el solve de `k_u`/`k_d` del `em`** — después del backfill de aggs.

---

# LAS 3 OLAS

## OLA 1 — barata, alto edge, **cero `n` nueva requerida** (~2–3 semanas)

**Ranks 1, 2, 3, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18** — `barrier-labels`, `null-control`,
`book-quality gate`, `chain-honesty`, `flip-honesty + freeze 09:35`, `truth-lock`,
`em-envelope determinista`, `features-fanout + tope de 14`, `voice-budget governor`,
`next-day-map roll-off`, `pin-clock`, `equity-prints archiver`, `chain-cube archive`,
`iv_hist logger`, `levels-5min archive`.

**Cada ítem es un arreglo de bug determinado, un archivador, un veto de calidad de dato, o la capa
de medición** — ninguno necesita una afirmación de probabilidad, y juntos **hacen honesto todo lo
que venga después**.

**Efecto neto: el sistema se vuelve más CALLADO, más PEQUEÑO y mejor instrumentado.**
**Coste de ops**: ningún daemon Python residente nuevo salvo el watchdog de `truth-lock` (~10 MB)
y el escritor de `levels_5m` (**condicionado a un test medido de RSS/latencia**).

## OLA 2 — necesita los dos desbloqueos de datos (feature 4 + acumulación de la 7), ~4–8 semanas

**Ranks 4, 7, 8, 19, 20, 21, 23, 25, 26, 27, 29, 30** — `poly-aggs-backfill`, `chain_full_snap`,
`level-react + level_events` (C++, **voz apagada**), `cube-widening`, `vol-trigger congelado`,
`wall-decay ledger`, `cor-fleet`, `expiry-unwind`, `gap-islands`, `kde-levels`,
`peer-weights hardening`, `finviz-snap archive`.

Aquí es donde **la lógica de niveles de la flota se CONSOLIDA** (`level_react` retira gatillos
ad-hoc en ~30 signal bots) y donde aparecen **los primeros niveles estructurales reales sobre un
libro no truncado**.
**Ninguna voz nueva se habilita en esta ola**: las celdas ganan voz **de una en una** a través de
`null-control`.

## OLA 3 — pesada, dependiente de `n` forward, **validar-antes-de-construir**

**Ranks 22, 24, 28** — `chain-delta engine` (5 syms, `weight=0`, banner solamente, **BORRADA de
raíz** si el test de residuo de spot congelado falla), `close-drift DEX+charm` (**validación
PRIMERO** contra el baseline de max-pain, **cero C++ hasta que gane**), `skew-lead` (solo diario,
**DATA-INSUFFICIENT publicado honestamente**).

**Todo en la ola 3 embarca MUDO con `weight=0` y debe DESPLAZAR un factor existente para entrar
alguna vez en la flecha.**

---

# TOP 5 MUST-BUILD

1. **`barrier-labels` (#1)** — el único ítem que mejora el **denominador de todas las
   probabilidades que ya cantamos**; nuestros win rates son optimistas por una cantidad no medida
   porque los retornos por horizonte **no pueden ver el stop siendo tocado en el camino**
   (bollinger h=15 **0.436 n=822 → se espera 0.38–0.41**). Cero datos nuevos, cero daemon, y
   entrega las distribuciones MFE/MAE que parametrizan los brackets y alimentan `momentum_decay`.
2. **`null-control` (#2)** — la única feature cuya salida es **una resta**. `whale` está en 0.357 y
   `bollinger h=5` en 0.402 **y ambos siguen hablando**; entradas aleatorias emparejadas por
   tiempo/exposición + BH-FDR + DSR + MinTRL + **la corrección de muestra efectiva** (Wilson sobre
   sym-días de semis agrupados es **anticonservador 3–4×**) es lo que convierte esos números en
   escrituras a `signal_enable.json`, y es **lo único que se interpone entre 30 features nuevas y
   una catástrofe de multiple testing**.
3. **`book-quality gate` (#3)** — la FORMA correcta de una feature: **coeficiente multiplicativo,
   no un 12º factor aditivo; veto, no señal**; justificada por lógica de calidad de dato que se
   sostiene **incluso subpotenciada**; testeable HOY sobre las 972 señales calificadas. La salida
   esperada (**silencio gamma PERMANENTE en DRAM/SPCX/SKHY/EWY/NOK**) vale más que cualquier señal
   nueva, y arregla un bug vivo: `abs_wall` descartaba su signo, así que **un pin y una trampilla
   eran indistinguibles para todo consumidor, incluido el veto 0DTE**.
   → **El arreglo del signo YA ESTÁ EN `gex_core.py` (2026-07-25).**
4. **`poly-aggs-backfill` (#4)** — `poly_bars` tiene **21 sesiones** mientras ~10 features reclaman
   **250 sesiones, 200 eventos de earnings o retornos forward a 60 días**. Un script contra un
   endpoint que **ya pagamos**; convierte cobertura del `em`, distancia al pin, rellenos de hueco,
   el split de vol realizada del VT y charm-vs-maxpain **de astrología a medible — incluidas las
   que va a MATAR**.
   → **EN CURSO ahora mismo por otro agente (2026-07-25).**
5. **`level-react + level_events` (#5 de la lista, rank 8)** — el único ítem que **BORRA código**:
   ~30 `*_signal_bot.cpp` cargan cada uno lógica de niveles ad-hoc, consolidada en **un primitivo
   C++23 (~0,7 MB RSS)** más **una tabla de eventos tipados**. No necesita dato de opciones en
   tiempo de señal (**cero riesgo de feed**), hace **PRINT-O-NADA mecánico como un straddle de dos
   barras** en vez de "está cerca", y es el sustrato al que `wall-decay`, `gap-islands` y
   `kde-levels` se enchufan todos.
   **Condición NO NEGOCIABLE: voz APAGADA para toda fuente al embarcar**, recuperada una celda
   calibrada a la vez.

## Las dos condiciones transversales (son features 11 y 12, y aplican a TODO lo de arriba)

- **El tope de 14 factores de `direction_view` con inserción SOLO multiplicativa.**
- **El presupuesto de voz con el conteo de DANGER congelado.**

**Sin ellas, 30 features significan una flecha cuya varianza de `prob` ha colapsado a una constante
~58% y una sirena que nadie escucha — los dos modos de fallo SIN remedio post-hoc.**

---

## Dónde vive todo esto

- **Dossiers de fuente (los 6)**: `docs/research/` — ver `docs/research/README.md`.
- **Las 13 skills**: `~/.claude/skills/<slug>/SKILL.md` (globales) y
  `~/ib-trader/.claude/skills/<slug>/SKILL.md` (del repo). Índice:
  [[measured-probability]] · [[chain-data-contract]] · [[print-o-nada-levels]] ·
  [[book-quality-veto]] · [[flip-and-vol-trigger]] · [[pin-and-expiry-mechanics]] ·
  [[expected-move-envelope]] · [[dealer-flow-limits]] · [[sample-integrity]] ·
  [[direction-view-architecture]] · [[alert-budget]] · [[peer-captain-evidence]] ·
  [[anti-overfit-killlist]]
- **Contexto de doctrina**: `~/CLAUDE.md`, `AGENTS.md`, `docs/DAILY-SYSTEM.md`,
  `docs/TRADING-RULES.md`.

**SEÑAL-SOLAMENTE.** Ninguna de las 30 ordena al broker.
