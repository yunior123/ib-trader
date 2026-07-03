# WHALE BACKTEST — 2026-07-24

Backtest de las alertas de OPCIONES/FLUJO del día contra el movimiento REAL del subyacente,
y validación con números de las reglas 11 y 12 de `~/CLAUDE.md`.

**Honestidad primero:** un solo día. n pequeño en casi todos los cortes. Nada de lo que sigue
es concluyente por sí solo; lo que sí es concluyente es que **hay reglas de la casa que hoy
apuntaron en la dirección contraria a lo que dicen**. Sin comisiones ni slippage modelados —
las cifras de scalp son un techo optimista, no un P&L.

---

## 0. Datos y método

| Insumo | Qué es | Cobertura |
|---|---|---|
| `data/bars_<sym>_ibkr.txt` | barras 1m propias (IBKR), `EPOCH O H L C V` separado por espacio | 33 símbolos, 04:00–16:25 ET, ~731 barras/símbolo |
| `data/whale_alerts.jsonl` | cada cruce de umbral del watcher de ballenas | 60 eventos hoy → 42 son señales (17 PUTS, 10 CALLS, 15 CRECE) |
| `trades.db` `signals` | lo que el sistema realmente CANTÓ | 42 ballenas + 55 SPIKE de flow_pulse |
| `data/history/2026-07-24/opt_chain_<sym>_HHMM.txt` | **fotos de cadena cada 5 min** | 26 símbolos × ~82 fotos, 09:19→16:16 |
| `data/flow_pulse_probs.json` | tabla de probabilidades auto-calibradas | comparada contra el resultado real |

**Polygon NO sirve para hoy** (su última barra es 2026-07-23 19:59). Todo se midió con
nuestras propias barras.

**Definición de acierto** (la misma de `scripts/flow_pulse_calibrate.py`): signo del retorno
del subyacente a +5/+15/+30 min desde el cierre de la barra 1m que contiene la alerta.
Tesis de fade: **CALLS → baja**, **PUTS → sube**.

### El control que cambia todo: el base rate del día

Hoy fue un día bajista. Cualquier señal que diga "baja" gana gratis:

```
BASE RATE incondicional (todas las barras 1m RTH, 30 tickers de flota)
  + 5m  P(baja) = 6087/10872 = 56.0%   medRet -0.0285%
  +15m  P(baja) = 6115/10412 = 58.7%   medRet -0.0713%
  +30m  P(baja) = 5685/ 9998 = 56.9%   medRet -0.0942%
Solo capitanes (QQQ SPY SMH): 58.9% / 60.8% / 57.3%
```

Recorrido 09:30→16:00: QQQ **-0.86%**, SPY -0.00%, SMH **-2.24%**, INTC **-7.24%**,
SNDK **-6.51%**, MU -3.81%, STX -2.84%, TSLA -2.46%, AAPL **+2.69%**.

Por eso **todos los aciertos de abajo se comparan contra el base rate del día, no contra 50%**.
Un 60% en una señal "baja" el 2026-07-24 es *peor que tirar una moneda cargada*.

---

## 1. REGLA 11 — Espada-ballena (CALLS = techo, PUTS = piso)

### 1.1 Resultado crudo

| Señal | n | +5m | +15m | +30m |
|---|---|---|---|---|
| 🐋 BALLENA CALLS (tesis: baja) | 10 | 60% [W95 31-83] | 50% [24-76] | 50% [24-76] |
| 🐋 BALLENA PUTS (tesis: sube) | 17 | 41% [22-64] | 47% [26-69] | 31% [14-56] |
| 🐋📈 CRECE CALLS | 10 | 56% [27-81] | 44% [19-73] | 50% [24-76] |
| 🐋📈 CRECE PUTS | 5 | 20% [4-62] | 40% [12-77] | 40% [12-77] |
| **TODAS (42)** | 42 | **46% [32-61]** | **46% [32-61]** | **41% [28-57]** |

### 1.2 Contra el base rate del día (p-valor binomial 1-cola)

```
BALLENA (todas)  + 5m: 19/41 = 46%   base 49.6%   p=0.71
BALLENA (todas)  +15m: 19/41 = 46%   base 49.4%   p=0.71
BALLENA (todas)  +30m: 17/41 = 41%   base 49.8%   p=0.89
BALLENA CALLS    +15m:  5/10 = 50%   base 58.7%   p=0.81   PEOR que la deriva
BALLENA PUTS     +30m:  5/16 = 31%   base 43.1%   p=0.89   PEOR que la deriva
```

**Veredicto regla 11: NO se sostiene con los datos de hoy.** Las ballenas no baten ni siquiera
al azar-con-deriva. El lado de PUTS ("piso local") es el peor: a +30m acierta 31% cuando la
moneda cargada del día daba 43%. Los casos que más duelen son los repetidos: SNDK PUTS 09:45
→ **-2.61%** a +15m; SNDK CRECE PUTS 10:12 → -1.53%; SNDK PUTS 14:19 → -1.49%; SMH PUTS 09:44
→ -1.38%. El "piso" no era piso: era la mitad de la escalera.

n=10 y n=17 ⇒ **NO concluyente**. Con estos tamaños, los IC de Wilson (24-76%) no distinguen
una señal del 50%. Lo que sí se puede decir: **no hay ni rastro de la ventaja que la regla
promete**, y el signo medido es contrario en el lado PUTS.

### 1.3 ¿Y como scalp chico ("profit pequeño y seguro")?

Test de barreras en dirección de la tesis, sobre las 42 ballenas, barras 1m (ambigüedad
intrabar contada como pérdida):

| TP / SL | horizonte | TP | SL | winrate decididos | **control aleatorio** |
|---|---|---|---|---|---|
| 0.10% / 0.20% | 15m | 25 | 12 | 68% [51-80] | **68% [66-70]** |
| 0.15% / 0.25% | 15m | 25 | 11 | 69% [53-82] | **64% [62-67]** |
| 0.15% / 0.25% | 30m | 28 | 12 | 70% [55-82] | **63% [60-65]** |
| 0.20% / 0.20% | 15m | 21 | 17 | 55% [40-70] | **50% [48-53]** |

El control aleatorio son 2000 entradas al azar en los mismos tickers, mismo horario, misma
mezcla de dirección. **El winrate alto es puro artefacto de la asimetría TP/SL, no de la señal.**
E[R] de la mejor celda: **+0.017% por operación**, antes de comisiones y slippage — o sea, cero.
La táctica "entrar en el pico y salir con poquito" hoy no tuvo edge medible.

Único matiz a favor: la **excursión favorable mediana** a +15m fue +0.36% (la ballena sí marca
un punto desde el que *algo* se mueve a favor en algún momento), pero el retorno terminal es
moneda al aire. Marcar extremo ≠ predecir dirección.

---

## 2. REGLA 12 — Jerarquía de capitanes

15 eventos de flujo de capitán hoy (SMH×5, QQQ×6, SPY×4), whale + SPIKE.

### 2.1 (a) "Flujo masivo de PUTS del capitán = rebote del sector SIEMPRE"

| capitán | tesis | horizonte | propio | sector (cesta equiponderada) |
|---|---|---|---|---|
| PUTS (n=7) | sube | +5m | **1/7 = 14%** [3-51] | 1/7 = 14% [3-51] |
| PUTS (n=7) | sube | +15m | **2/7 = 29%** [8-64] | 4/7 = 57% [25-84] |
| PUTS (n=7) | sube | +30m | 3/7 = 43% [16-75] | 3/7 = 43% [16-75] |
| CALLS (n=8) | baja | +5m | 4/8 = 50% [22-78] | 5/8 = 62% [31-86] |
| CALLS (n=8) | baja | +15m | **8/8 = 100%** [68-100] | **8/8 = 100%** [68-100] |
| CALLS (n=8) | baja | +30m | 7/8 = 88% [53-98] | 5/8 = 62% [31-86] |

**El "SIEMPRE" está muerto.** El flujo de PUTS del capitán acertó 2 de 7 a +15m. Ejemplos:
SMH BALLENA PUTS 09:44 → SMH -1.38% y la cesta de semis -1.53% a +15m; SPY SPIKE PUTS 12:35 →
SPY -0.19%, cesta -0.35%.

La asimetría medida es **la contraria**: el capitán con **CALLS** fue el que marcó techo, 8/8
a +15m. Contra el base rate del día (60.8% de barras bajistas en capitanes) el p-valor es
**0.019** — sugerente. Pero: n=8, un solo día, y es una celda entre muchas que probé
(multiplicidad no corregida ⇒ probablemente ruido). No lo conviertas en ley todavía; sí merece
un ledger propio.

### 2.2 (b) "En conflicto capitán-vs-tropa, manda el capitán y la señal del nombre queda ANULADA"

15 conflictos (alerta de un nombre con el capitán en dirección opuesta dentro de 30 min):

```
+ 5m  obedecer NOMBRE  : 10/15 = 67% [W95 42-85]   obedecer CAPITAN: 5/15 = 33% [15-58]
+15m  obedecer NOMBRE  : 10/15 = 67% [W95 42-85]   obedecer CAPITAN: 5/15 = 33% [15-58]
+30m  obedecer NOMBRE  :  5/14 = 36% [W95 16-61]   obedecer CAPITAN: 9/14 = 64% [39-84]
```

| hora | nombre | lado | capitán | lado cap | +5m | +15m | +30m | ganó |
|---|---|---|---|---|---|---|---|---|
| 10:12 | SNDK | PUTS | QQQ | CALLS | -1.88 | -1.53 | -2.61 | capitán |
| 10:17 | INTC | PUTS | QQQ | CALLS | +0.11 | -0.10 | -1.30 | capitán |
| 10:37 | TSLA | PUTS | QQQ | CALLS | -0.48 | +0.19 | -0.15 | nombre |
| 10:57 | MU | CALLS | SMH | PUTS | -0.25 | -0.31 | +0.52 | nombre |
| 11:56 | AMD | CALLS | QQQ | PUTS | -0.24 | +0.19 | +0.21 | capitán |
| 12:03 | AAPL | CALLS | QQQ | PUTS | -0.09 | -0.02 | -0.09 | nombre |
| 13:44 | MU | PUTS | SPY | CALLS | -0.01 | -0.09 | -0.63 | capitán |
| 13:52 | GOOGL | PUTS | QQQ | CALLS | +0.13 | +0.38 | +0.26 | nombre |
| 14:05 | NFLX | PUTS | QQQ | CALLS | +0.03 | +0.19 | +0.54 | nombre |
| 14:19 | SNDK | PUTS | QQQ | CALLS | -0.41 | -1.49 | -1.56 | capitán |
| 15:04 | AMZN | PUTS | QQQ | CALLS | +0.12 | +0.09 | +0.03 | nombre |
| 15:30 | MU | CALLS | QQQ | PUTS | +0.55 | -0.33 | +0.32 | nombre |
| 15:37 | AAPL | PUTS | SPY | CALLS | +0.01 | +0.14 | +0.15 | nombre |
| 15:57 | QCOM | PUTS | SPY | CALLS | +0.54 | +0.06 | -0.10 | nombre |
| 15:58 | STX | PUTS | SPY | CALLS | +0.37 | +0.41 | n/a | nombre |

**Veredicto 12(b): hoy es al revés en el horizonte de scalp.** En 5-15 min mandó el **nombre**
(67%), no el capitán (33%). El capitán solo se impone a +30m (64%). Con n=15 los IC se solapan
completamente (42-85 vs 15-58 a +15m; a +30m 39-84 vs 16-61) ⇒ **no concluyente**, pero la regla
tal como está escrita — "la señal del nombre queda prácticamente ANULADA" — **no tiene apoyo
empírico hoy**, y si algo insinúan los datos es lo contrario dentro de la ventana en la que
operamos.

Matiz utilizable: la única lectura coherente con los 15 casos es **temporal**, no jerárquica —
el nombre manda en los primeros 15 minutos, el capitán en la media hora. Eso encaja con
"scalp corto obedece al nombre, gestión de sesgo obedece al capitán". Hipótesis, no ley.

---

## 3. Muros de OI y GEX intradía (fotos de 5 min)

### 3.1 Lo primero que enseñan las fotos: el OI **no se mueve** intradía

QQQ 690C: OI **7106** a las 09:35, 7106 a las 12:00, 7106 a las 15:00, 7106 a las 16:00.
Lo que sí evoluciona es **volumen** (6.391 → 416.412 contratos), **IV** y **gamma en vivo**.
⇒ "evolución intradía de los muros" = evolución de VOLUMEN y GAMMA, no de OI. Cualquier lógica
que espere que el muro de OI se mueva durante el día está esperando algo que no ocurre.

Dos limitaciones de las fotos, a tener en cuenta antes de sacar conclusiones:
- La **ventana de strikes se desliza con el spot** (~±1.5%, 11-20 strikes). No vemos muros más
  lejos; los muros "aparecen y desaparecen" al moverse el precio.
- Después de las **16:15** salen `bid/ask/iv/delta/gamma = -1` (fuera de ventana). Filtradas.

### 3.2 GEX visible (exp frontal, ventana de la foto) — régimen del día

```
QQQ    09:30 -1.252 M$/1%   13:00 -2.467   14:00 -2.769   15:30 -3.802   (spot 689.75 -> 683.69)
SMH    09:30   -193         10:30   -425   11:30   -332   14:00   -276
INTC   11:00    -10.7       13:00    -16.3 15:30    -23.9
MU     09:30    -13.7       11:00    -96.3 13:00   -136.3 15:30    -97.3
SNDK   10:30    -38.8       12:30    -49.9 15:00   -134.6
```

Corte a las 13:00 en los 26 símbolos: **18 negativos / 8 positivos**. GEX se volvió *más*
negativo a medida que el precio caía = día de gamma negativa clásico (dealers aceleran el
movimiento). Es exactamente el escenario de `negative-gamma-whipsaw`.

### 3.3 ¿Los muros actuaron como imán o rechazo?

Definición del propio `flow_pulse` (top-3 OI por lado del exp frontal), dedupe por strike,
toque = la barra 1m contiene el strike, primer toque cada 10 min, veredicto a +15m
(ROTURA si cierra ≥0.10% al otro lado; REBOTE si vuelve ≥0.15% al lado de origen):

```
TODOS (26 símbolos)   toques 186   REBOTE 86  ROTURA 82  INDECISO 18
                      P(rebote | decidido) = 51% [W95 44-59]
```

**Moneda al aire.** Y por régimen tampoco cambia:

```
GEX+   45 toques   REBOTE 19  ROTURA 18   P(rebote) 51% [36-67]
GEX-  141 toques   REBOTE 67  ROTURA 64   P(rebote) 51% [43-60]
```

**Test del "decaimiento por toques"** (doctrina: 1º rebota ~70%, 3+ exhausto):

```
toque #1   50 toques  REBOTE 22 ROTURA 25  47% [33-61]
toque #2   34 toques  REBOTE 17 ROTURA 14  55% [38-71]
toque #3   26 toques  REBOTE 15 ROTURA  6  71% [50-86]
toque #4+  76 toques  REBOTE 32 ROTURA 37  46% [35-58]
```

El patrón medido es **el inverso del que dice la doctrina**: el primer toque fue el que **menos**
rebotó (47%), y el tercero el que más (71%). Con 4 celdas probadas y n=26 en la mejor, esto es
ruido con toda probabilidad — pero lo que sí queda enterrado es "el 1er toque rebota ~70%":
hoy fue 47% [33-61].

**Efecto imán:** distancia al strike de mayor OI total (C+P), ¿se reduce en 30 min?
**828/1731 = 48% [45-50]**. n grande, IC estrecho: **hoy no hubo efecto imán**. (Coherente:
gamma negativa dominante ⇒ nada pinea.)

**Pin de cierre** (|cierre - strike de mayor OI|): SPY 0.17%, STX 0.20%, QCOM 0.45%, QQQ 0.63%,
META 0.86%, AAPL 0.90% … pero TXN 5.03%, TSM 4.81%, NOK 4.53%, AMD 4.50%. Sin patrón.

**Detalle QQQ** (el caso que el sistema cantó como "MURO 690"): 12 toques dedupe (4 REBOTE,
5 ROTURA, 3 INDECISO = 44%). El precio pasó el día *dentro* de la caja 680-695 **sin tocar
nunca los muros grandes** — 680P con 31.415 de OI y 695C con 10.147 quedaron intactos todo el
día; el "muro 690" que citaban las alertas es un top-3 (7.106 calls / 20.371 puts), no el muro
real. Secuencia de sus toques: ROTURA — REBOTE — REBOTE — INDECISO — ROTURA — REBOTE — REBOTE —
ROTURA — ROTURA — ROTURA — INDECISO — INDECISO. Coin flip.

**Símbolos con más ballenas** (rebotes/roturas): MU 7/9 = 44%, SNDK 6/7 = 46%, NVDA 7/4 = 64%,
INTC 5/5 = 50%, QQQ 4/5 = 44%. Ninguno se sale de la moneda.

---

## 4. Calibración: la prob que el sistema ANUNCIÓ vs el resultado REAL

Esto es lo único que hoy salió **bien**, y sale bien de forma clara.

Las 55 alertas 🚀 SPIKE de `flow_pulse` cantaron su probabilidad en el mensaje
("…rebote a la baja, probabilidad 66"). Medido a +15m con la misma definición del calibrador:

| anunciada | n | real | Wilson 95% | error |
|---|---|---|---|---|
| 44% | 7 | 71% | [36-92] | **+27 pp** |
| 56% | 7 | 86% | [49-97] | **+30 pp** |
| 66% | 23 | 78% | [58-90] | +12 pp |
| 70% | 6 | 67% | [30-90] | -3 pp |
| 73% | 5 | 60% | [23-88] | -13 pp |
| **global** | **48** | **75%** | **[61-85]** | **anunciada media 62.6% ⇒ sesgo +12.4 pp** |

**Brier score 0.2149** (0.25 = anunciar 50% siempre). **El sistema no miente: se queda corto.**
Es conservador, que es el sesgo correcto en el que equivocarse.

Contra el base rate mixto del día (que ya corrige la deriva bajista):

```
SPIKE (55)  + 5m: 36/55 = 65% [52-77]   base 51.2%   p = 0.023
SPIKE (55)  +15m: 39/54 = 72% [59-82]   base 51.9%   p = 0.0019
SPIKE (55)  +30m: 38/54 = 70% [57-81]   base 51.5%   p = 0.0038
  SPIKE_CALLS +15m: 22/29 = 76% [58-88]  vs base 59%  p=0.043
  SPIKE_PUTS  +15m: 14/19 = 74% [51-88]  vs base 41%  p=0.0044
```

Buckets (real de hoy vs la tabla acumulada que usó para cantar):

| bucket | n hoy | real hoy | anunciada | tabla acumulada |
|---|---|---|---|---|
| SPIKE_CALLS\|normal | 23 | 78% [58-90] | 66.0% | 66% (n=53) |
| SPIKE_CALLS\|muro | 6 | 67% [30-90] | 70.0% | 67% (n=18) |
| SPIKE_PUTS\|normal | 10 | 70% [40-89] | 64.5% | 71% (n=21) |
| SPIKE_PUTS\|muro | 9 | 78% [45-94] | 46.7% | 50% (n=28) |
| SPIKE_CALLS\|bandwalk VETADO | 2 | 0% [0-66] | — | 89% (n=9) |
| SPIKE_PUTS\|bandwalk VETADO | 4 | 75% [30-95] | — | 61% (n=2) |

Dos cosas que arreglar:
1. **`SPIKE_PUTS|muro` está mal calibrado a la baja**: canta 44-47% y hoy dio 78% (7/9). Es la
   celda con más margen de mejora.
2. **El ledger no reproduce lo que se cantó en vivo.** `flow_pulse_probs.json` registró para hoy
   `SPIKE_CALLS|normal n=24 ok=16` (67%); midiendo las señales que realmente salieron por la BD
   sale `n=23 ok=18` (78%). El calibrador re-simula desde `whale_flow_hist.jsonl` en vez de
   auditar `signals`; el replay y la realidad divergen. **Recomendación: calibrar contra
   `trades.db signals`, que es lo que el operador realmente vio.**

---

## 5. Contraste final: SPIKE sí, BALLENA no

Misma metodología, mismo día, mismo control de deriva:

```
BALLENA (42 señales)  +15m: 19/41 = 46% [32-61]   base 49.4%   p=0.71   <- sin edge
SPIKE   (55 señales)  +15m: 39/54 = 72% [59-82]   base 51.9%   p=0.0019 <- con edge
```

La diferencia estructural entre las dos familias explica el resultado: la **ballena mide un
NIVEL acumulado** (ratio P/C del día cruzando un umbral) — que a media sesión ya es historia
vieja y sigue disparándose mientras el desequilibrio persiste. El **SPIKE mide ACELERACIÓN**
(tasa de contratos/min ≥3× su EMA) — es un evento puntual, fechado, no un estado.

Aviso de rigor: es **un día**. n=54 en la familia buena, p=0.0019 sin corregir por las ~20
hipótesis que este documento prueba. Corrigiendo Bonferroni (×20) queda p≈0.04: sobrevive por
poco. Necesita 3-5 días más antes de tocar posición.

---

## 6. Qué hacer con esto (propuestas, no cambios)

1. **No armar entradas con 🐋 BALLENA sola.** Degradarla a *contexto* (banner sin voz), como
   ya se hizo con los patrones. Su valor es señalar dónde hay desequilibrio, no cuándo entrar.
2. **🐋📈 CRECE es la peor del lote** (43-47%, siempre bajo el base rate): es literalmente la
   confirmación de que la marea sigue — o sea, continuación disfrazada de reversión. Revisar
   si debe cantarse como fade.
3. **Poner ledger propio al bucket "capitán CALLS → techo" (8/8 hoy)** y al espejo
   "capitán PUTS → piso" (2/7 hoy). Si en 5 días la asimetría aguanta, la regla 12(a) se
   reescribe: el techo del capitán vale, el piso no.
4. **Regla 12(b): probar la versión temporal** — nombre manda ≤15m, capitán manda ≥30m — en vez
   de la anulación total. Hoy la anulación habría costado dinero en 10 de 15 conflictos.
5. **Recalibrar `SPIKE_PUTS|muro`** y migrar el calibrador a leer `trades.db signals`.
6. **Muros: 51% no justifica la confianza doctrinal.** Antes de usar un muro como gatillo hace
   falta medirlo en días de gamma POSITIVA (hoy 18/26 símbolos estaban negativos y no hubo
   diferencia entre regímenes con la n disponible).

---

## Limitaciones

- **Un solo día**, mercado en tendencia bajista. Nada de esto extrapola a un día de rango.
- **Sin comisiones ni slippage.** Las cifras de scalp son un techo.
- **Ambigüedad intrabar** en el test de barreras (barras 1m): contada como pérdida, sesgo conservador.
- **Ventana de strikes limitada** (~±1.5% del spot) en las fotos de cadena: no vemos muros lejanos.
- **GEX es parcial** (solo strikes visibles, exp frontal, convención call+/put−). Sirve para el
  signo del régimen y su evolución, no como cifra absoluta.
- **Multiplicidad no corregida** salvo donde se dice explícitamente. Este documento prueba ~20
  hipótesis sobre el mismo día.
- Los eventos de un mismo símbolo **no son independientes** (SNDK aporta 3 ballenas PUTS en la
  misma caída). Los IC de Wilson asumen independencia ⇒ son **demasiado estrechos**, la
  incertidumbre real es mayor que la reportada.
