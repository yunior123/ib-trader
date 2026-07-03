# BACKTEST DE TODO EL HISTORIAL DE SEÑALES (2026-07-15 → 2026-07-24)

Generado el 2026-07-25. Sustituye y corrige a `docs/BACKTEST-SIGNALS-2026-07-24.md`
(que era un solo viernes). Motor nuevo: `scripts/full_history_backtest.py` (reusa
`eod_backtest.wilson` y el esquema de `backtest_harness.py`).

**Datos**
- Señales: `trades.db.signals`, 3.233 filas → 3.222 con fecha < 07-25 (las 11 del 07-25 no
  tienen barras todavía). Las 2.691 filas `WARMUP` ya estaban purgadas.
- Precio: `poly_bars` (Polygon 1m, 493.359 barras, 30 símbolos, 06-24→07-23) +
  `data/bars_<sym>_ibkr.txt` para el 07-24 (Polygon no publicó ese día).
- Opciones: `poly_opt_bars` 5m. Se bajaron **0DTE reales de cada jornada** (contratos
  expirados, `expired=true`) para QQQ/SPY/NVDA: 07-15…07-24, ±1,2% (índices) / ±3,5% (NVDA).
  Total ahora 937 contratos con barras.

---

## 0. METODOLOGÍA — léela antes de creerte cualquier número

### 0.1 Lo que se mide
Entrada = close de la vela 1m en el instante de la señal. Salida = close a +5/+15/+30/+60 min.
Victoria = el precio se movió **>+0,05% en la dirección de la tesis**. Solo se puntúan señales
dentro de RTH (09:30–15:55) y con barra a menos de 5 min.

### 0.2 El número honesto NO es el WR: es el LIFT contra la base del día
Un WR del 55% no dice nada si ese día el símbolo subió todo el rato. Por eso, para **cada
(símbolo, día, horizonte)** se calcula sobre **todos los minutos RTH** la probabilidad de que
una entrada larga (`p_long`) o corta (`p_short`) en un minuto cualquiera hubiera ganado.
El WR de la señal se compara contra esa base, no contra 50%. **Eso es el control de régimen**,
y es mucho más fino que etiquetar el día "rojo/verde": descuenta la deriva del símbolo
concreto en el día concreto.

### 0.3 Corrección adicional por VOLATILIDAD (crítica)
Las señales suenan en momentos agitados, y en un momento agitado moverse >0,05% es más fácil
**en los dos sentidos**. Medir contra la base incondicional premia a cualquier señal que
simplemente sepa detectar volatilidad, sin saber la dirección.
Por eso la métrica primaria de este informe es el **WR DIRECCIONAL**:

> de las señales cuyo precio SÍ se movió >0,05% en algún sentido, ¿qué fracción se movió
> hacia la tesis? Base = `p_long / (p_long + p_short)` del mismo símbolo-día.

Se reportan las dos (`WRcrudo`/`lift` y `WRdir`/`LIFTdir`). **Cuando discrepan, manda WRdir.**

### 0.4 Los Wilson que verás son DEMASIADO ESTRECHOS
Los eventos del mismo símbolo el mismo día no son independientes (el mismo movimiento de
precio los gana o los pierde a todos a la vez). Los intervalos Wilson de las tablas asumen
independencia y por tanto **mienten a favor**. Para los contrastes se usa un **test de score
Poisson-binomial con varianza cluster-robusta** (cluster = símbolo × día); todos los `z` y `p`
de este informe son cluster-robustos. Se publica también `ncl` = nº de clusters: **ese es el
tamaño de muestra que cuenta de verdad.**

### 0.5 Costes
**Subyacente: SIN comisiones, SIN slippage, SIN spread, fills perfectos al close del minuto.**
Cualquier retorno medio por debajo de ~0,05% es ruido operativo.
**Opciones: el precio de `poly_opt_bars` es real pero es OHLC de barra de 5 minutos, NO
bid/ask. El spread NO está incluido.** Con premiums medianos de $1,04–$1,60 en estos 0DTE,
un spread típico de $0,01–$0,05 es **1–5% del premium por lado, 2–10% ida y vuelta**. Además,
"tocó el TP" se mide contra el HIGH intrabarra: asume una orden límite ya puesta.

### 0.6 Cobertura: de 3.222 señales se puntúan 2.220
| motivo de exclusión | n |
|---|---:|
| **Evaluadas** | **2.220** |
| `FLUJO OPCIONES:` (tablero de estado, sin tesis) | 192 |
| Fuera de RTH (Corea, premarket, after-hours) | 176 |
| `ALARMA PRECIO` (dice explícitamente "mirar, no entrar") | 147 |
| Otros sin dirección inferible (watchdog, X, sentinel…) | 145 |
| Sin `symbol` o sin barras del símbolo | 111 |
| `DRAM GUARD` (comentario de contexto) | 65 |
| `FINVIZ` (gaps informativos) | 53 |
| `ESTRUCTURAL pin` / `flip` (el mensaje dice no direccional) | 49 |
| Sin barra a <5 min | 33 |
| `RE-ENTRADA A BANDA` sin lado en el mensaje | 23 |
| resto | 8 |

Evaluadas por día: 07-15:26 · 07-16:169 · 07-17:283 · 07-20:46 · 07-21:33 · 07-22:661 ·
07-23:315 · 07-24:687. Los días 07-18/07-19 son fin de semana (solo señales de Corea, fuera
de RTH US).

---

## 1. RÉGIMEN DIARIO (09:30 → 16:00)

| día | SPY | QQQ | media | etiqueta |
|---|---:|---:|---:|---|
| 2026-07-15 | +0,03% | −0,83% | −0,40% | BAJISTA |
| 2026-07-16 | −0,29% | −0,85% | −0,57% | BAJISTA |
| 2026-07-17 | +0,08% | +0,46% | +0,27% | ALCISTA |
| 2026-07-20 | −0,58% | −0,76% | −0,67% | BAJISTA |
| 2026-07-21 | +0,25% | +0,29% | +0,27% | ALCISTA |
| 2026-07-22 | +0,20% | +0,37% | +0,29% | ALCISTA |
| 2026-07-23 | −0,07% | −0,18% | −0,12% | LATERAL |
| 2026-07-24 | +0,04% | −0,89% | −0,43% | BAJISTA |

**No hay ningún día francamente alcista en toda la muestra** (el máximo es +0,29%). Cualquier
conclusión de este informe está medida en un mercado plano-a-rojo. En un tramo de subida
sostenida ninguna de estas cifras está validada.

---

## 2. EL HALLAZGO MÁS IMPORTANTE: hay 3× más señales, pero NO 3× más días

El encargo era comprobar estabilidad día a día. La respuesta es incómoda:

| familia | n | **días activos** |
|---|---:|---|
| BB_REBOTE | 785 | **3** (07-22, 23, 24) |
| FLUJO_DIARIO_CALLS | 249 | **2** (07-16, 17) |
| BB_REENTRADA_15m | 178 | **3** (07-22, 23, 24) |
| FLUJO_DIARIO_PUTS | 160 | **2** (07-16, 17) |
| FLUJO_INTRADIA_PUTS | 142 | **1** (07-22) |
| BB_BANDWALK | 129 | **3** (07-22, 23, 24) |
| GIRO_A_CALLS / PUTS | 61 / 52 | 3 |
| WHALE_CALLS | 59 | 5 |
| CUSUM_CAIDA / ALZA | 52 / 37 | 7 |
| FLOW_SPIKE_CALLS | 48 | 3 |
| FLOW_SPIKE_PUTS | 47 | **2** |
| WHALE_PUTS | 39 | 4 |
| BB_APERTURA_FUERA | 38 | **2** |
| WHALE_CRECE | 31 | 3 |
| STRUCT_MAGNET | 29 | **2** |
| BOT_SELL / BOT_BUY | 28 / 25 | 6 |
| MANADA, CAPITÁN, DIP | ≤10 | 1–2 |

La flota se fue desplegando durante la ventana: los detectores grandes (Bollinger, flujo
intradía, spikes) llevan **1–3 sesiones vivos**. El `n` creció porque cada detector grita
muchas veces al día en muchos símbolos, **no porque haya más historia**. Traducido al lenguaje
de la §0.4: el número que importa es `ncl` (símbolo × día), y ahí:

- `FLUJO_DIARIO_CALLS`: n=248 pero **ncl=11**. `FLUJO_DIARIO_PUTS`: n=160, **ncl=15**.
  `FLUJO_INTRADIA_PUTS`: n=142, **ncl=16**. Son *un puñado de días-símbolo repetidos*,
  no 150 observaciones.
- Solo `BB_REBOTE` (ncl=90), `BB_REENTRADA_15m` (ncl=67) y `BB_BANDWALK` (ncl=74) tienen
  un `ncl` respetable — y son las tres peores en lift.

**Ninguna familia tiene todavía un histórico estable de verdad.** Todo lo que sigue hay que
leerlo con eso encima de la mesa.

---

## 3. WR POR FAMILIA — horizontes 5/15/30/60 min

Formato: `WRcrudo (base) lift | WRdir (base) LIFTdir [z_cluster]`.
**Negrita = las 6 familias que superan n=100.**

### +15 min (horizonte principal)

| familia | n | ncl | WRcrudo | base | lift | nMOV | **WRdir** | base | **LIFTdir** | z_cl | p_cl | ret medio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BB_REBOTE** | 773 | 90 | 46% | 42% | +4,3 | 651 | 55% [51,59] | 50% | **+5,3** | +2,74 | 0,006 | +0,033% |
| **FLUJO_DIARIO_CALLS** | 248 | 11 | 48% | 46% | +2,0 | 225 | 53% | 50% | +3,5 | +0,92 | 0,360 | −0,026% |
| **BB_REENTRADA_15m** | 178 | 67 | 40% | 36% | +4,2 | 154 | 47% | 43% | +4,2 | +0,99 | 0,321 | −0,092% |
| **FLUJO_DIARIO_PUTS** | 160 | 15 | 48% | 34% | +14,0 | 140 | 55% | 39% | **+16,4** | +2,67 | 0,008 | +0,350% |
| **FLUJO_INTRADIA_PUTS** | 142 | 16 | 34% | 41% | −7,3 | 114 | 42% | 51% | **−8,7** | −2,63 | 0,009 | −0,029% |
| **BB_BANDWALK** | 128 | 74 | 42% | 48% | −5,5 | 110 | 49% | 56% | −6,6 | −1,45 | 0,147 | +0,043% |
| GIRO_A_CALLS | 60 | 27 | 63% | 54% | +9,7 | 57 | 67% | 59% | +7,4 | +0,98 | 0,327 | +0,226% |
| WHALE_CALLS | 59 | 42 | 42% | 41% | +1,4 | 54 | 46% | 49% | −2,5 | −0,39 | 0,695 | −0,016% |
| CUSUM_CAIDA | 52 | 41 | 48% | 51% | −2,6 | 52 | 48% | 55% | −7,1 | −1,00 | 0,315 | +0,125% |
| GIRO_A_PUTS | 52 | 37 | 38% | 38% | +0,9 | 45 | 44% | 44% | +0,9 | +0,12 | 0,902 | −0,283% |
| FLOW_SPIKE_CALLS | 48 | 24 | 71% | 47% | +23,8 | 39 | **87% [73,94]** | 56% | **+31,2** | +3,34 | 0,001 | +0,158% |
| FLOW_SPIKE_PUTS | 46 | 22 | 57% | 38% | +18,2 | 39 | **67%** | 47% | **+20,1** | +2,53 | 0,011 | +0,136% |
| WHALE_PUTS | 39 | 22 | 33% | 34% | −0,6 | 32 | 41% | 40% | +1,0 | +0,12 | 0,905 | −0,125% |
| BB_APERTURA_FUERA | 38 | 38 | 58% | 40% | +18,0 | 36 | 61% | 48% | +13,4 | +1,70 | 0,089 | +0,121% |
| CUSUM_ALZA | 37 | 30 | 46% | 42% | +3,5 | 37 | 46% | 48% | −1,6 | −0,22 | 0,822 | −0,226% |
| WHALE_CRECE | 30 | 21 | 47% | 44% | +2,9 | 24 | 58% | 52% | +5,9 | +0,68 | 0,497 | +0,130% |
| STRUCT_MAGNET | 29 | **3** | 69% | 41% | +27,5 | 29 | 69% | 49% | +20,2 | +1,54 | 0,124 | +0,097% |
| BOT_SELL | 28 | 26 | 43% | 52% | −9,5 | 26 | 46% | 59% | −12,7 | −1,35 | 0,176 | −0,193% |
| BOT_BUY | 25 | 25 | 60% | 41% | +19,4 | 22 | 68% | 52% | +16,0 | +1,53 | 0,127 | +0,241% |
| MANADA_A_CALLS | 10 | 7 | 80% | 49% | +30,8 | 9 | 89% | 56% | +33,1 | +2,32 | 0,020 | +0,283% |
| CAPITAN_REVIERTE | 9 | 3 | 56% | 38% | +17,1 | 6 | 83% | 55% | +28,3 | +1,35 | 0,176 | +0,039% |
| MANADA_A_PUTS | 7 | 7 | 57% | 36% | +21,2 | 6 | 67% | 40% | +26,2 | +1,16 | 0,248 | +0,206% |
| DIP_REAL | 5 | 5 | 20% | 36% | −16,2 | 3 | 33% | 41% | −7,5 | −0,27 | 0,788 | −0,117% |

### Respuesta directa a "¿cuáles superan n=100?"
**Seis: BB_REBOTE (773), FLUJO_DIARIO_CALLS (248), BB_REENTRADA_15m (178), FLUJO_DIARIO_PUTS
(160), FLUJO_INTRADIA_PUTS (142), BB_BANDWALK (128).**
**Todas las demás siguen siendo anécdota** — incluidas las estrellas del informe del viernes
(FLOW_SPIKE 48+46, STRUCT_MAGNET 29, MANADA 10+7, CAPITÁN 9, DIP 5).
Y de esas seis, tres tienen `ncl` < 20 (FLUJO_DIARIO ×2 y FLUJO_INTRADIA_PUTS): su n=150
esconde 11–16 días-símbolo. **Anécdota disfrazada de muestra.**

### Decaimiento por horizonte (LIFTdir)

| familia | +5m | +15m | +30m | +60m |
|---|---:|---:|---:|---:|
| BB_REBOTE | +3,7 | **+5,3** | +3,0 | +2,7 |
| BB_REENTRADA_15m | −0,6 | +4,2 | +1,3 | +5,5 |
| BB_BANDWALK | −10,5 | −6,6 | −4,7 | **−12,4** (p=0,003) |
| FLOW_SPIKE_CALLS | +17,2 | **+31,2** | +11,1 | −2,0 |
| FLOW_SPIKE_PUTS | +9,4 | **+20,1** | +12,6 | +0,6 |
| FLUJO_INTRADIA_PUTS | −2,1 | −8,7 | −9,0 | −12,3 |
| CUSUM_ALZA | −13,9 | −1,6 | **−18,6** (p=0,006) | −14,2 |
| WHALE_CALLS / PUTS / CRECE | +5,3/+7,6/+22,7 | −2,5/+1,0/+5,9 | −2,0/+11,9/+11,8 | −0,5/+17,0/+9,5 |

**Los spikes de flujo son un scalp de 15 minutos y se apagan a los 60.** Eso encaja
exactamente con la táctica espada-ballena (regla 11): cobrar poco y rápido. Aguantarlos una
hora borra todo el edge.

---

## 4. ESTABILIDAD DÍA A DÍA (LIFTdir @15m) — lo pedido en el punto 2 del encargo

Formato `WRdir/base(n)`.

| familia | global | días lift>0 | detalle |
|---|---:|---:|---|
| **BB_REBOTE** | +5,3 | **3/3** | 07-22: 55/49 (274) · 07-23: 62/50 (146) · 07-24: 51/50 (231) |
| **BB_REENTRADA_15m** | +4,2 | 3/3 | 07-22: 48/45 (54) · 07-23: 73/47 (11) · 07-24: 43/41 (89) |
| **BB_BANDWALK** | −6,6 | **0/3** | 07-22: 49/54 (35) · 07-23: 30/51 (23) · 07-24: 58/58 (52) |
| **FLOW_SPIKE_CALLS** | +31,2 | **3/3** | 07-20: 60/59 (5) · 07-23: 100/52 (8) · 07-24: 88/57 (26) |
| **FLOW_SPIKE_PUTS** | +20,1 | **2/2** | 07-23: 67/47 (18) · 07-24: 67/46 (21) |
| FLUJO_DIARIO_PUTS | +16,4 | 2/2 | 07-16: 49/37 (123) · 07-17: 100/51 (17) |
| FLUJO_DIARIO_CALLS | +3,5 | 1/1 | 07-17: 52/50 (221) |
| FLUJO_INTRADIA_PUTS | −8,7 | 0/1 | 07-22: 42/51 (114) |
| GIRO_A_CALLS | +7,4 | 3/3 | 07-22: 57/46 (7) · 07-23: 60/50 (5) · 07-24: 69/62 (45) |
| WHALE_CALLS | −2,5 | **1/5** | 07-20: 38/54 · 07-21: 37/42 · 07-22: 50/51 · 07-23: 71/53 · 07-24: 50/53 |
| CUSUM_CAIDA | −7,1 | 2/5 | 07-15: 75/50 · 07-16: 55/58 · 07-17: **17/49** · 07-20: 44/64 · 07-24: 67/62 |
| WHALE_PUTS | +1,0 | 1/3 | 07-20: 33/39 · 07-23: 56/43 · 07-24: 33/37 |
| BB_APERTURA_FUERA | +13,4 | **1/2** | 07-22: 82/54 (22) · 07-24: **29/38** (14) |
| WHALE_CRECE | +5,9 | 3/3 | 07-22: 50/46 · 07-23: 71/59 · 07-24: 55/52 |

**Lecturas:**
1. **Se CONFIRMA el flow SPIKE del viernes.** 5/5 días-familia con lift positivo, y el efecto
   es grande (+20 a +31pp). Es lo único del informe anterior que sobrevive a más días.
   Pero son **3 y 2 días respectivamente, n=48 y 46 → sigue por debajo de n=100.**
2. **Se TUMBA `BB_APERTURA_FUERA`** (el "+18pp" del viernes): 82% el 07-22, 29% el 07-24.
   Es un día bueno y un día malo. Ruido.
3. **BB_BANDWALK: 0/3 días.** Negativo de forma consistente, y a +60m con p=0,003. Este sí
   se puede empezar a llamar señal mala (aunque los 3 días son consecutivos).
4. **Las ballenas siguen sin aparecer.** `WHALE_CALLS` 1/5 días con lift positivo, `WHALE_PUTS`
   1/3. La regla 11 (fade de la ballena) **no está respaldada por 5 días de datos**: lift
   −2,5pp con p=0,70. No está refutada tampoco — está *ausente*.
5. `FLUJO_DIARIO_PUTS` (+16,4, p=0,008) tiene 123 de sus 140 observaciones en **un solo día**
   (07-16). Es un día, no una muestra.
6. `CUSUM_CAIDA` alterna 75%/55%/17%/44%/67% en 5 días: varianza pura, lift global −7,1.

---

## 5. CONTROL DE RÉGIMEN — lo pedido en el punto 3

Como se explicó en §0.2, **el control de régimen ya está dentro de cada número**: la base es
la del mismo símbolo el mismo día. El desglose por etiqueta de régimen confirma que el efecto
no es "ganamos porque el día fue rojo":

| familia (@15m) | ALCISTA | LATERAL | BAJISTA |
|---|---|---|---|
| BB_REBOTE | n=274 WRdir 55% lift **+5,4** | n=146 62% **+12,1** | n=231 51% **+0,8** |
| BB_REENTRADA_15m | n=54 48% +3,5 | n=11 73% +26,0 | n=89 43% +1,9 |
| BB_BANDWALK | n=35 49% −5,8 | n=23 30% −21,0 | n=52 58% −0,7 |
| FLOW_SPIKE_CALLS | — | n=8 — | n=31 84% **+26,9** |
| FLOW_SPIKE_PUTS | — | n=18 67% **+19,9** | n=21 67% **+20,3** |
| WHALE_CALLS | n=29 41% −3,4 | — | n=18 44% −9,4 |
| CUSUM_CAIDA | n=14 **14% −34,9** | — | n=38 61% +3,1 |
| FLUJO_INTRADIA_PUTS | n=114 42% −8,7 | — | — |

- **FLOW_SPIKE_PUTS aguanta el control**: +19,9pp en días laterales y +20,3pp en días
  bajistas. No es "largos que ganan por rebote": el efecto es el mismo en los dos regímenes.
  (FLOW_SPIKE_CALLS solo tiene muestra en días bajistas — no se puede separar.)
- **BB_REBOTE pierde casi todo el lift en días bajistas** (+0,8pp) y vive en los laterales
  (+12,1pp). Un elástico solo funciona si el precio no está en tendencia: obvio, pero ahora
  está medido.
- **`CUSUM ALZA` en día alcista: 14% de acierto direccional, lift −34,9pp** (n=14, anécdota,
  pero apunta a que el detector de "terremoto al alza" está comprando el techo).
- La conclusión del viernes ("los cortos ganaron porque el día fue rojo") queda descontada:
  con base por símbolo-día, **CORTOS lift +3,9pp y LARGOS +5,8pp @15m** — el sesgo direccional
  ya no explica nada.

---

## 6. GATES: ¿las silenciadas ganaban más? — lo pedido en el punto 4

**Aviso previo importante:** los gates (`[MUTED p<55]`, `[VETO medido]`, `⭐`, "capitán
opuesto") **solo existen en el 07-23 y el 07-24**. Antes no se escribían en la BD. Así que
"con 2.500 señales" es engañoso: **para esta pregunta la muestra pasó de 1 día a 2 días** y
de 616 a 1.017 señales. No hay 3× de muestra aquí.

### 6.1 Por gate (07-23 + 07-24)

| gate | n | ncl | @15m WRdir | base | LIFTdir | z_cl | @60m LIFTdir |
|---|---:|---:|---:|---:|---:|---:|---:|
| SONO (sonaron, sin ⭐) | 631 | 60 | 60% [56,64] | 51% | **+9,2** | +3,48 | +1,2 |
| MUTED p<55 | 184 | 49 | 47% | 47% | −0,2 | −0,04 | +7,7 |
| VETO medido | 100 | 46 | 57% | 48% | +8,8 | +1,62 | +9,0 |
| **SONO ⭐ (celda estrella)** | 49 | 39 | **32%** | 45% | **−12,3** | −1,58 | **−12,8** |
| MUTED capitán opuesto | 13 | 12 | 77% | 47% | +30,0 | +2,28 | +6,9 |
| VETADO band-walk | 9 | 8 | 50% | 43% | +6,6 | +0,43 | −9,8 |

### 6.2 Apples-to-apples: BB_REBOTE, mismo detector, mismo minuto

| horizonte | SONÓ (lift) | VETO medido (lift) | z(VETO−SONÓ) | p |
|---|---|---|---:|---:|
| +5m | +5,8 | +8,4 | +0,23 | 0,814 |
| +15m | +6,5 | +8,8 | −0,06 | 0,955 |
| +30m | −2,1 | +5,7 | +0,99 | 0,320 |
| +60m | −2,0 | +9,0 | +1,63 | 0,103 |

### VEREDICTO §6 — **el "+11pp a favor de las silenciadas" NO se sostiene**
Con el día extra y, sobre todo, con el control de volatilidad de §0.3, **la diferencia
VETO−SONÓ a +15m es cero (z=−0,06, p=0,96)**. Lo que en el informe del viernes parecía un
gate invertido era en su mayor parte el sesgo de que las señales vetadas caían en momentos
menos volátiles (más fáciles de "ganar" por poco). El signo sigue apuntando a favor de las
silenciadas a +30m y +60m (z=+0,99 y +1,63, p=0,10), pero **no llega a significación ni de
lejos, ni siquiera sin corregir por multiple testing.**

**Conclusión operativa: el gate `bb_context` no aporta y no resta. Es ruido caro.** No hay que
desmontarlo por urgencia, pero tampoco vale nada — y cada veto le cuesta al sistema 100
señales cada dos días.

**`MUTED p<55` sigue sin demostrarse en ningún sentido** (lift −0,2 @15m, +7,7 @60m). Dentro
de `BB_BANDWALK`, las silenciadas quedan igual o mejor que las que sonaron en los 3 horizontes.

**Lo que SÍ hay que actuar: la CELDA ESTRELLA `⭐`.** Es el único grupo con lift negativo en
casi todos los horizontes **y en los dos días por separado**: @5m −20,3 (07-23) y −22,5
(07-24); @15m −6,6 y −17,7; @60m −12,8 global (p=0,037). n=49 y ncl=39 → es la señal de
máxima convicción del sistema y su acierto direccional es **32%** cuando la base es 45%.
Nada aquí sobrevive a Bonferroni, pero la consistencia (2/2 días × 3/4 horizontes) es la más
sólida de todo el bloque de gates.

**`MUTED capitán opuesto` (regla 12): 13 señales, 77% de acierto direccional, lift +30pp.**
Es decir, la jerarquía de capitanes está silenciando señales que ganaban. **n=13 en 2 días =
anécdota**, pero es el segundo informe seguido que apunta en la misma dirección. Instrumentar
y medir, no desmontar.

---

## 7. HORA DEL DÍA (@15m) — y una corrección al informe del viernes

| hora ET | n | ncl | WRdir | base | LIFTdir | z_cl | p_cl |
|---|---:|---:|---:|---:|---:|---:|---:|
| 09:00 | 261 | 115 | 57% | 51% | +6,1 | +1,99 | 0,046 |
| 10:00 | 344 | 106 | 58% | 50% | +8,0 | +2,51 | 0,012 |
| **11:00** | 231 | 84 | **38%** | 49% | **−10,8** | −2,35 | 0,019 |
| 12:00 | 311 | 108 | 47% | 49% | −2,0 | −0,58 | 0,562 |
| 13:00 | 341 | 102 | 59% | 49% | +10,5 | +2,72 | 0,006 |
| 14:00 | 355 | 105 | 49% | 47% | +1,7 | +0,49 | 0,626 |
| **15:00** | 360 | 111 | **63%** | 48% | **+14,5** | +4,29 | **0,00002** |

**Corrección al informe del viernes: el "desastre de las 14:00 (24%)" NO existe en el
histórico.** Con 8 días y control de régimen, la franja 14:00 sale +1,7pp (p=0,63). Era un
artefacto de un solo viernes. La franja mala real es **11:00 (−10,8pp)**.

**El 15:00 es un resultado enorme… y frágil.** Desglose de dónde sale:

- Dentro de `BB_REBOTE`: **15:00 → LIFTdir +22,4pp (n=137, p=0,00002)**; el resto del día
  +0,7pp (n=514, p=0,73). **Todo el edge de BB_REBOTE está en la última hora.**
- Pero por día, el efecto 15:00 solo aparece el **07-23 (+25,1) y el 07-24 (+26,7)**; el
  07-22, con n=105, dio **+1,5**. Y el 07-17 (n=10) y 07-20 (n=7) fueron negativos.
  **2 de 3 días con muestra grande.**

Acción defendible: **subir el peso del bloque 15:00 y bajar el de 11:00 en `timeofday_calib`,
y volver a medir en 5 sesiones más antes de tocar nada estructural.**

---

## 8. LA OPCIÓN REAL (0DTE) — lo pedido en el punto 5

271 señales de QQQ/SPY/NVDA puntuadas sobre el contrato **0DTE ATM real** (strike más cercano
al spot, `call` si la tesis es alcista, `put` si es bajista). Entrada = **open de la barra 5m
siguiente a la señal**. Premium mediano de entrada: QQQ $1,60 · SPY $1,16 · NVDA $1,04.

Se añaden **dos controles sin los cuales estas cifras no significan nada**:
- **base** = misma probabilidad de tocar el TP entrando en una barra 5m cualquiera del **mismo
  contrato, dentro de ±60 min** (un 0DTE ATM se mueve ±30% por gamma sola; sin este control
  cualquier TP parece un edge).
- **OPP** = el contrato del **strike idéntico y el derecho contrario**. Es el control de
  direccionalidad puro: si la señal no sabe la dirección, OPP debe empatar.

| grupo | h | n | TP+30% | base | **OPP** | TP+50% | base | TP+100% | ret medio | **ret mediano** | OPP ret | % con ret>0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TODAS | 15m | 271 | 40% | 35% | 40% | 25% | 22% | 6% | +1,4% | **−5,3%** | +0,1% | 43% |
| TODAS | 30m | 271 | 52% | 45% | 49% | 37% | 31% | 12% | +4,8% | **−8,8%** | +0,7% | 42% |
| TODAS | 60m | 271 | 62% | 53% | 56% | 49% | 39% | 25% | +18,0% | **−18,4%** | −4,4% | 40% |
| QQQ | 30m | 104 | 59% | 47% | 47% | 40% | 32% | 19% | +15,8% | −6,4% | −14,2% | 44% |
| SPY | 30m | 57 | 40% | 42% | 53% | 28% | 28% | 7% | −2,7% | −13,4% | +6,3% | 44% |
| NVDA | 30m | 110 | 52% | 46% | 48% | 37% | 32% | 7% | −1,6% | −13,1% | +11,9% | 38% |
| BB_REBOTE | 30m | 68 | 41% | 40% | 47% | 31% | 25% | 9% | −0,7% | −8,6% | +9,1% | 38% |
| FLUJO_DIARIO_CALLS | 30m | 53 | 64% | 50% | 32% | 40% | 29% | 9% | +12,6% | −5,1% | −8,4% | 45% |
| FLUJO_INTRADIA_PUTS | 30m | 20 | 30% | 21% | 50% | 15% | 8% | 0% | −13,7% | −10,5% | +19,9% | 35% |
| STRUCT_MAGNET | 30m | 16 | 81% | 57% | 25% | 69% | 50% | 12% | +30,1% | +33,8% | −28,1% | 69% |

### Contraste subyacente vs opción — la lectura brutal
1. **El TP+30% "53% de acierto" es casi todo gamma, no señal.** El contrato del derecho
   CONTRARIO lo toca el 49% de las veces. La diferencia real es de ~3pp.
2. **La mediana del retorno de la opción es negativa en TODOS los horizontes** (−5,3% / −8,8%
   / −18,4%) y **solo el 40–43% de las operaciones cierra en verde**. La media positiva sale
   de una cola derecha larga: se gana con pocos billetes grandes y se pierde theta el resto
   del tiempo. Esa es una distribución que aniquila a quien no aguanta rachas.
3. **La prueba pareada contra el contrato opuesto no es significativa en ningún grupo**
   (t cluster-robusto entre −1,7 y +1,7; QQQ el mejor con t=+1,67 a 30m, p≈0,14).
4. **Y todo esto es ANTES del spread**, que en estos 0DTE es 1–5% del premium por lado.
   Con 2–10% de ida y vuelta, el +4,8% de media a 30m se queda en nada y la mediana −8,8%
   empeora.
5. `STRUCT_MAGNET` se ve espectacular (81% TP30 vs 25% del opuesto) pero **ncl=1**: son 16
   señales de NVDA de una sola tarde. **Cero valor probatorio.**
6. Donde el subyacente perdía, la opción pierde el triple: `FLUJO_INTRADIA_PUTS` −13,7% de
   media y el contrato opuesto +19,9%. La señal estaba invertida y el apalancamiento lo
   amplifica.

**Veredicto opciones: no hay evidencia de que comprar el 0DTE en estas señales sea mejor que
lanzar una moneda entre call y put.** El presupuesto ≤$200 limita el daño, pero el edge
medible es cero.

---

## 9. MULTIPLE TESTING — lo pedido en el punto 6

Familia de contrastes pre-especificada: **31 hipótesis @15m** = 19 familias con n≥20 + 4 gates
+ 7 franjas horarias + el total. Todas con `p` cluster-robusto.
Bonferroni α = 0,05/31 = **0,00161**. Benjamini-Hochberg q=0,05 → umbral **p ≤ 0,01613**.

| hipótesis | nMOV | LIFTdir | p_cl | BH | Bonferroni |
|---|---:|---:|---:|:--:|:--:|
| **hora 15:00** | 313 | +14,5 | 0,00002 | **SÍ** | **SÍ** |
| **TOTAL (todas las señales)** | 1910 | +4,8 | 0,00009 | **SÍ** | **SÍ** |
| **gate SONO** | 550 | +9,2 | 0,00049 | **SÍ** | **SÍ** |
| **FLOW_SPIKE_CALLS** | 39 | +31,2 | 0,00083 | **SÍ** | **SÍ** |
| BB_REBOTE | 651 | +5,3 | 0,00610 | SÍ | no |
| hora 13:00 | 286 | +10,5 | 0,00647 | SÍ | no |
| FLUJO_DIARIO_PUTS | 140 | +16,4 | 0,00766 | SÍ | no |
| FLUJO_INTRADIA_PUTS | 114 | **−8,7** | 0,00856 | SÍ | no |
| FLOW_SPIKE_PUTS | 39 | +20,1 | 0,01130 | SÍ | no |
| hora 10:00 | 312 | +8,0 | 0,01223 | SÍ | no |
| hora 11:00 | 208 | −10,8 | 0,01894 | no | no |
| hora 09:00 | 249 | +6,1 | 0,04635 | no | no |
| BB_APERTURA_FUERA | 36 | +13,4 | 0,08923 | no | no |
| VETO_medido | 86 | +8,8 | 0,10574 | no | no |
| SONO_ESTRELLA | 37 | −12,3 | 0,11499 | no | no |
| STRUCT_MAGNET | 29 | +20,2 | 0,12415 | no | no |
| BOT_BUY | 22 | +16,0 | 0,12666 | no | no |
| BB_BANDWALK | 110 | −6,6 | 0,14706 | no | no |
| BOT_SELL · CUSUM_CAIDA · BB_REENTRADA_15m · GIRO_A_CALLS · FLUJO_DIARIO_CALLS · WHALE_CRECE · horas 12/14 · WHALE_CALLS · CUSUM_ALZA · GIRO_A_PUTS · WHALE_PUTS · MUTED_p<55 | 24–278 | −12,7…+7,4 | 0,18–0,97 | no | no |

**Sobreviven a BH-FDR: 10 de 31. Sobreviven a Bonferroni: 4.**

Advertencia sobre estos supervivientes: sobrevivir a la corrección **no arregla el problema de
que la muestra tenga 1–3 días por familia** (§2). Un efecto puede ser estadísticamente sólido
*dentro de esos tres días* y evaporarse el cuarto — el test corrige por multiplicidad, no por
falta de historia. Los cuatro de Bonferroni tienen además parentesco: `TOTAL`, `SONO` y
`15:00` se solapan fuertemente con `BB_REBOTE @15:00`.

---

## 10. QUÉ SOBREVIVE Y QUÉ HAY QUE APAGAR

### Sobrevive (con reservas explícitas)
| qué | evidencia | reserva |
|---|---|---|
| **FLOW SPIKE (calls+puts) a 15 min** | LIFTdir +25,7pp junto, p=0,0004; 5/5 días-familia positivos; aguanta el control de régimen (+20pp en lateral y en bajista) | n=94 (<100), 3 días, ncl=32; a 60m el edge **desaparece** |
| **BB_REBOTE en la franja 15:00** | +22,4pp, p=0,00002, n=137 | 2 de 3 días con muestra; fuera de esa franja BB_REBOTE es **+0,7pp (nada)** |
| **Franjas 10:00 y 13:00** | +8,0 y +10,5pp, sobreviven BH | confundidas con la composición de familias |
| El conjunto global | +4,8pp @15m, p=0,00009 | retorno medio +0,037% — **no paga ni el spread**; sin 15:00 baja a +2,9pp |

### Hay que APAGAR o degradar
| qué | por qué |
|---|---|
| **CELDA ESTRELLA `⭐` de BB_REBOTE** | 32% de acierto direccional vs 45% de base; negativa en **los dos días** y en 3 de 4 horizontes. Es la señal con voz garantizada del sistema y es la peor que tiene. Degradar a INFO YA. |
| **El elástico BB entre 11:00 y 12:00** | −10,8pp (p=0,019, sobrevive por poco a BH); dentro de BB_REBOTE la franja 11:00 da −16,2pp (p=0,007) |
| **BB_BANDWALK** | 0/3 días con lift positivo; −12,4pp a +60m (p=0,003). Como mínimo, quitarle la voz. |
| **FLUJO_INTRADIA_PUTS (`🌊 FLUJO PUTS <SYM>`)** | −8,7pp @15m (p=0,009, sobrevive a BH) y **−13,7% en la opción** mientras el contrato opuesto hace +19,9%. La señal parece estar **invertida**. Solo hay 1 día — no invertirla a ciegas, pero silenciarla hasta medirla. |
| **Comprar la opción 0DTE con estas señales** | mediana −8,8% a 30m, 42% de aciertos, y el contrato del derecho contrario empata en TP. Sin spread incluido. |

### No demostrado en ningún sentido (seguir midiendo, no tocar)
- **Ballenas (reglas 11 y 12)**: `WHALE_CALLS` lift −2,5pp p=0,70 con 5 días; `WHALE_PUTS`
  +1,0pp p=0,91. Cinco días y la ley 11 no aparece ni a favor ni en contra.
- **Gate `bb_context` (VETO medido)** y **`MUTED p<55`**: diferencia nula @15m. El hallazgo
  del viernes queda **descartado**, no confirmado.
- **`MUTED capitán opuesto`**: +30pp con n=13. Segunda vez que apunta a que el capitán silencia
  ganadoras. Instrumentar.
- **Todo lo que tiene n<100**: STRUCT_MAGNET, MANADA, CAPITÁN, DIP, BOT_BUY/SELL, GIRO, CUSUM,
  BB_APERTURA_FUERA. **Ninguno es concluyente.**

### Deuda de medición (arreglar para el próximo backtest)
1. **Registrar el gate y el motivo desde el día 1** (hoy solo existen desde el 07-23: la
   pregunta 4 sigue teniendo 2 días de muestra, no 10).
2. `GIRO A CALLS/PUTS` y `FLUJO OPCIONES:` (192+113 señales) **no declaran tesis en el
   mensaje** — o la escriben, o siguen sin ser medibles.
3. `symbol` NULL en 111 señales (CPER/SLV/USO tienen barras; es un bug del emisor).
4. `ESTRUCTURAL pin/flip` (49): si de verdad no son direccionales, no deberían sonar como
   señal.

---

*Recordatorio final: 8 sesiones, ningún día francamente alcista, la mayoría de detectores con
1–3 días de vida, fills perfectos y sin costes en el subyacente, sin spread en la opción.
Ninguna cifra de este documento justifica por sí sola abrir una posición.*

Reproducir (en orden):
```
./venv/bin/python scripts/full_history_backtest.py --json /tmp/fhb.json   # motor + baselines
./venv/bin/python scripts/full_history_report.py                          # §1..§9 del informe
./venv/bin/python scripts/full_history_optbt.py                           # §8 (opción 0DTE)
```
Descarga de 0DTE expirados (ya hecha, idempotente): contratos `expired=true` con
`expiration_date=<día>` vía `polygon_dl.poly()`, 5m, ±1,2% (QQQ/SPY) y ±3,5% (NVDA).
