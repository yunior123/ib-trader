# BACKTEST DE LAS SEÑALES DEL 2026-07-24 (viernes) — datos reales, sin maquillaje

Generado el 2026-07-24 por la noche. Fuente de señales: `trades.db` tabla `signals`
(852 filas con `date='2026-07-24'`, 30 símbolos). Resultados escritos en
`backtest_signal_outcomes` (2.088 filas, `run_ts=1784941080`).

## 0. Metodología y ADVERTENCIAS (léelas antes de creerte un número)

- **Barras**: `data/bars_<sym>_ibkr.txt` (1m, epoch = inicio de vela, 23.824 barras de hoy,
  33 símbolos, 04:15→16:25 ET). **Polygon NO tiene el 24/07** (su última barra es
  2026-07-23 19:59), así que `poly_bars` no sirvió para hoy: el harness de Polygon se
  envolvió para leer las barras IBKR. Se reusaron `eod_backtest.wilson`, `load_bars` y
  `price_at`; el esquema de salida es el de `backtest_harness.py`.
- **Entrada**: close de la vela de 1m en el instante de la señal. **Salida**: close a
  +5/+15/+30 min. **Victoria** = retorno en la dirección de la tesis > +0.05%.
- **SIN comisiones, SIN slippage, SIN spread, SIN retardo de ejecución.** Fills perfectos al
  close del minuto. En opciones (spread real 1–27% hoy) estos números serían bastante
  peores. Cualquier "edge" menor a ~0.10% de retorno medio es ruido operativo: no paga ni el
  spread.
- **Un solo día**. n global 616. Todo lo que tenga n<20 se marca NO CONCLUYENTE aunque el WR
  se vea bonito.
- Ninguna ventana quedó truncada por el fin de los datos (las barras llegan a 16:25 ET).

### Cobertura y exclusiones (de 852 señales)

| categoría | n | ¿backtesteable? |
|---|---:|---|
| Dirección de alta confianza | **620** (616 con resultado) | SÍ — es la base de todas las tablas |
| Dirección AMBIGUA (`GIRO A CALLS/PUTS`) | 80 | Aparte, con supuesto explícito |
| `WARMUP *` | 76 | **NO** — ver §7 |
| `symbol` NULL | 16 | **NO** — ver §6 |
| Sin dirección inferible | 64 | NO (pin 41, flip 6, ALARMA PRECIO 5, ZONA 2, FINVIZ 2, TICKER CIEGO 2, RE-ENTRADA+VOL 4, otros) |

Reglas de dirección usadas (regla 11 de `CLAUDE.md`): BALLENA PUTS/SPIKE PUTS = alcista;
BALLENA CALLS/CRECE/SPIKE CALLS = bajista; BB REBOTE/RE-ENTRADA ABAJO = alcista, ARRIBA =
bajista; BAND-WALK ABAJO = bajista (continuación), ARRIBA = alcista; SPIKE `(VETADO)` =
continuación (invierte el fade); magnet por la flecha ↑/↓; CUSUM ALZA/CAIDA; bot `: BUY/SELL`.
**`ESTRUCTURAL pin` y `ESTRUCTURAL flip` se EXCLUYEN**: el propio mensaje dice "no
direccional"/"TRANSICIÓN" — no se inventa un lado. `RE-ENTRADA A BANDA +VOL` (4) se excluye
porque el mensaje no dice el lado.

---

## 1. HALLAZGO PRINCIPAL: el conjunto de señales NO le ganó a "shortear a ciegas"

El día fue bajista (09:30→15:55: QQQ −0.75%, SMH −2.02%, MU −3.01%, META −1.33%, SPY +0.01%).

| horizonte | TODAS las señales (n=616) | baseline: SIEMPRE CORTO en el mismo instante | baseline: SIEMPRE LARGO |
|---|---|---|---|
| +5m | WR **43%** [39,47] · ret +0.016% | WR 45% [41,49] · ret +0.045% | WR 34% · ret −0.045% |
| +15m | WR **48%** [44,52] · ret +0.048% | WR 50% [47,54] · ret +0.119% | WR 37% · ret −0.119% |
| +30m | WR **48%** [44,52] · ret +0.006% | WR 51% [47,55] · ret +0.154% | WR 40% · ret −0.154% |

Un mono que shorteara el subyacente en cada timestamp de señal habría sacado **más retorno
medio** que el conjunto de nuestras señales. El Wilson global cruza el 50% en los tres
horizontes (techo 47–52%): **no hay edge agregado demostrable hoy**.

Desglose por lado (alta confianza): **LARGOS n=324 → WR 41% [36,47], ret −0.068%** ·
**CORTOS n=292 → WR 55% [49,60], ret +0.176%** (@15m). Casi todo lo que "funcionó" hoy
funcionó porque era corto en un día rojo. Por eso las tablas siguientes incluyen **LIFT** =
WR real − WR esperado dado el mix largo/corto de esa familia. **El LIFT es el número honesto.**

---

## 2. WR por FAMILIA de señal (Wilson 95%)

### +5 min
| familia | n | WR | Wilson95 | ret medio | MFE | MAE | LIFT |
|---|---:|---:|---|---:|---:|---:|---:|
| BB REBOTE 1m | 269 | 42% | [36,48] | +0.029% | +0.22 | +0.19 | −2pp |
| BB RE-ENTRADA 15m | 102 | 37% | [28,47] | −0.063% | +0.22 | +0.30 | −2pp |
| BB BAND-WALK | 63 | 41% | [30,54] | +0.028% | +0.31 | +0.25 | −6pp |
| FLOW SPIKE CALLS | 31 | 58% | [41,74] | +0.042% | +0.19 | +0.19 | +9pp |
| ESTRUCTURAL magnet | 30 | 50% | [33,67] | +0.060% | +0.23 | +0.14 | +11pp |
| FLOW SPIKE PUTS | 24 | 46% | [28,65] | +0.032% | +0.19 | +0.14 | +6pp |
| BALLENA PUTS | 17 | 41% | [22,64] | −0.043% | +0.43 | +0.43 | +4pp |
| BALLENA CRECE (calls) | 15 | 40% | [20,64] | −0.074% | +0.26 | +0.27 | −6pp |
| CUSUM TERREMOTO | 14 | 57% | [33,79] | +0.081% | +0.59 | +0.44 | +12pp |
| BB APERTURA FUERA | 14 | 29% | [12,55] | −0.077% | +1.16 | +0.52 | −12pp |
| BALLENA CALLS | 10 | 60% | [31,83] | −0.043% | +0.25 | +0.32 | +10pp |
| MANADA A CALLS | 8 | 75% | [41,93] | +0.355% | +0.46 | +0.15 | +25pp |
| BOT SELL | 7 | 71% | [36,92] | +0.396% | +0.56 | +0.29 | +22pp |
| CAPITAN REVIERTE | 7 | 43% | [16,75] | +0.044% | +0.11 | +0.07 | −3pp |
| MANADA A PUTS | 4 | 25% | [5,70] | −0.123% | +0.17 | +0.24 | −12pp |
| BOT BUY | 1 | — | — | — | — | — | — |
| **TOTAL** | **616** | **43%** | **[39,47]** | +0.016% | | | |

### +15 min
| familia | n | WR | Wilson95 | ret medio | MFE | MAE | LIFT |
|---|---:|---:|---|---:|---:|---:|---:|
| BB REBOTE 1m | 269 | 45% | [39,51] | +0.013% | +0.34 | +0.34 | −3pp |
| BB RE-ENTRADA 15m | 102 | 37% | [28,47] | −0.146% | +0.35 | +0.48 | −6pp |
| BB BAND-WALK | 63 | 48% | [36,60] | +0.244% | +0.63 | +0.36 | −4pp |
| FLOW SPIKE CALLS | 31 | 65% | [47,79] | +0.140% | +0.38 | +0.23 | +11pp |
| ESTRUCTURAL magnet | 30 | 67% | [49,81] | +0.164% | +0.39 | +0.22 | +23pp |
| FLOW SPIKE PUTS | 24 | 71% | [51,85] | +0.123% | +0.38 | +0.25 | +27pp |
| BALLENA PUTS | 17 | 35% | [17,59] | −0.145% | +0.65 | +0.81 | −6pp |
| BALLENA CRECE (calls) | 15 | 27% | [11,52] | −0.048% | +0.45 | +0.39 | −24pp |
| CUSUM TERREMOTO | 14 | 64% | [39,84] | +0.619% | +1.12 | +0.62 | +14pp |
| BB APERTURA FUERA | 14 | 29% | [12,55] | −0.313% | +1.34 | +1.03 | −17pp |
| BALLENA CALLS | 10 | 50% | [24,76] | +0.016% | +0.43 | +0.50 | −5pp |
| MANADA A CALLS | 8 | 88% | [53,98] | +0.357% | +0.70 | +0.17 | +33pp |
| BOT SELL | 7 | 86% | [49,97] | +1.033% | +1.15 | +0.31 | +31pp |
| CAPITAN REVIERTE | 7 | 57% | [25,84] | +0.042% | +0.16 | +0.10 | +6pp |
| MANADA A PUTS | 4 | 50% | [15,85] | +0.276% | +0.52 | +0.37 | +9pp |
| BOT BUY | 1 | — | — | — | — | — | — |
| **TOTAL** | **616** | **48%** | **[44,52]** | +0.048% | | | |

### +30 min
| familia | n | WR | Wilson95 | ret medio | LIFT |
|---|---:|---:|---|---:|---:|
| BB REBOTE 1m | 269 | 43% | [37,49] | −0.057% | −6pp |
| BB RE-ENTRADA 15m | 102 | 40% | [31,50] | −0.092% | −5pp |
| BB BAND-WALK | 63 | 63% | [51,74] | +0.297% | +12pp |
| FLOW SPIKE CALLS | 31 | 52% | [35,68] | +0.124% | −1pp |
| ESTRUCTURAL magnet | 30 | 70% | [52,83] | +0.285% | +25pp |
| FLOW SPIKE PUTS | 24 | 67% | [47,82] | +0.063% | +22pp |
| BALLENA PUTS | 17 | 35% | [17,59] | −0.473% | −8pp |
| BALLENA CRECE (calls) | 15 | 47% | [25,70] | −0.198% | −3pp |
| CUSUM TERREMOTO | 14 | 64% | [39,84] | +0.822% | +15pp |
| BB APERTURA FUERA | 14 | 21% | [8,48] | −1.179% | −25pp |
| BALLENA CALLS | 10 | 40% | [17,69] | +0.007% | −13pp |
| MANADA A CALLS | 8 | 75% | [41,93] | +0.402% | +22pp |
| BOT SELL | 7 | 86% | [49,97] | +0.902% | +32pp |
| **TOTAL** | **616** | **48%** | **[44,52]** | +0.006% | |

**Lectura honesta:**
- Lo único con n decente y LIFT positivo consistente en los 3 horizontes: **FLOW SPIKE PUTS**
  (n=24, +6/+27/+22pp) y **ESTRUCTURAL magnet** (n=30, +11/+23/+25pp). Ambos con n<35 → **NO
  concluyente**, pero son los dos candidatos serios. Ojo: SPIKE PUTS son LARGOS que ganaron en
  un día rojo — eso es lo que le da valor a su lift.
- **Las ballenas fallaron hoy**: fuente `whale` global @15m 36% [23,51] (n=42), ret −0.072%.
  `BALLENA CRECE` (fade de calls) 27% [11,52] con LIFT −24pp. La ley 11 no funcionó este día
  concreto; con n=42 no se puede declarar rota, pero es una bandera roja.
- **Bollinger es el 73% del volumen de señales y es el que hunde el promedio**: 448 señales,
  WR 43% [39,48] @15m, ret −0.001%, LIFT negativo en todas las familias BB salvo band-walk a
  +30m. **Estamos gritando 448 veces al día algo que es peor que una moneda.**
- `MANADA A CALLS` (n=8, 88%) y `BOT SELL` (n=7, 86%) se ven espectaculares: **n<10, NO se
  vende ese número**. Wilson baja hasta 53% y 49%.

---

## 3. WR por FUENTE (@15m)

| fuente | n | WR | Wilson95 | ret medio |
|---|---:|---:|---|---:|
| bollinger | 448 | 43% | [39,48] | −0.001% |
| flow | 55 | 67% | [54,78] | +0.133% |
| whale | 42 | 36% | [23,51] | −0.072% |
| structural (solo magnet) | 30 | 67% | [49,81] | +0.164% |
| signal | 27 | 74% | [55,87] | +0.441% |
| cusum | 14 | 64% | [39,84] | +0.619% |

`flow` es la única fuente con n>50 cuyo Wilson **no toca el 50%** (54–78). Es el mejor
candidato a edge real del día.

---

## 4. CRÍTICO — las MUTED / VETADAS contra las que SONARON

### 4.1 Global por gate (@15m)

| gate | n | WR | Wilson95 | ret | % largo |
|---|---:|---:|---|---:|---:|
| SONO (sonaron) | 374 | 49% | [44,54] | +0.060% | 50% |
| VETO medido (silenciadas) | 74 | **53%** | [41,64] | +0.048% | 50% |
| MUTED p<55 (silenciadas) | 155 | 41% | [34,49] | +0.008% | 59% |
| MUTED capitán opuesto | 7 | 86% | [49,97] | +0.442% | — |
| VETADO band-walk (flow) | 6 | 50% | [19,81] | −0.174% | — |

### 4.2 Comparación apples-to-apples (mismo detector, mismo mix largo/corto)

**BB REBOTE 1m — SONÓ (n=195) vs [VETO medido] (n=74)**, ambos exactamente 50% largo / 50%
corto, mismo código, mismo minuto de detección; la única diferencia es el gate `bb_context`:

| horizonte | SONÓ | VETO medido | diferencia | z |
|---|---|---|---:|---:|
| +5m | 41% | 45% | **+4pp a favor de las silenciadas** | 0.60 |
| +15m | 42% [35,49] | 53% [41,64] | **+11pp a favor de las silenciadas** | 1.57 |
| +30m | 40% | 50% | **+10pp a favor de las silenciadas** | 1.47 |

**El signo está INVERTIDO en los tres horizontes: lo que el gate calló ganó más que lo que
dejó hablar.** Con z=1.57 (p≈0.12) **NO alcanza el 95%** — no se puede decretar todavía, pero
la consistencia en 5/15/30m dice que el `bb_context` de `bollinger_alarm.py` hoy no aportó
nada, y probablemente resta. Necesita 2–3 días más para pasar de "sospechoso" a "probado".

**Desglose del VETO por motivo (BB REBOTE, @15m):**

| grupo | n | WR | Wilson95 | ret medio |
|---|---:|---:|---|---:|
| SONÓ (normal) | 175 | 45% | [37,52] | +0.035% |
| **SONÓ ⭐ (CELDA ESTRELLA, "85% medido")** | **20** | **20%** | **[8,42]** | **−0.312%** |
| VETO: apertura 9:45-10:30 | 21 | 62% | [41,79] | +0.145% |
| VETO: z-VWAP estirado | 30 | 53% | [36,70] | +0.098% |
| VETO: RSI2 extremo | 30 | 43% | [27,61] | −0.079% |

Dos cosas graves:
1. **La CELDA ESTRELLA —la señal de máxima convicción, con voz siempre— fue la PEOR del día:
   20% [8,42], ret −0.31%.** Su Wilson superior (42%) queda por debajo de 50%: es el único
   grupo del día del que se puede decir con 95% que **no** llega a moneda. n=20, un día.
2. El **"VETO apertura 9:45-10:30"** silencia exactamente la ventana de oro de la doctrina
   (regla 7) y esas señales fueron las mejores del bloque BB (62%, n=21). Ese veto es el más
   sospechoso de estar al revés.
   El único veto que se salva es **RSI2 extremo** (43%, por debajo de las que sonaron): ese sí
   parece estar filtrando basura.

**BB BAND-WALK — SONÓ (n=10) vs [MUTED p<55] (n=53)**: 40% vs 49% @15m; 30% vs **70%** @30m.
Mismo signo invertido, pero n=10 del lado que sonó → **no concluyente, solo dirección**.

**MUTED p<55 (n=155)**: es el único gate que sale "bien" a 5 y 15m (41% vs 49%), pero está
**confundido**: se compone 100% de `BB RE-ENTRADA 15m` (102) + `BB BAND-WALK` (53), y la
familia RE-ENTRADA 15m no tiene contraparte que suene, así que el 41% mide la familia, no el
gate. Y a +30m se da la vuelta (MUTED 50% vs SONÓ 46%). **Ese gate no está demostrado en
ningún sentido.**

**MUTED "capitán opuesto" (7 señales de flow, regla 12)**: 86% @15m, ret +0.44%. Es decir, las
señales que la jerarquía de capitanes anuló habrían ganado. **n=7: anécdota, no evidencia** —
pero apunta en la misma dirección que todo lo demás: hoy la capa de condicionamiento silenció
mejores señales de las que dejó pasar.

### Veredicto §4
Con la evidencia de UN día: **la capa de condicionamiento no demostró aportar valor y el signo
del veto `bb_context` (y del veto de capitán) apunta al revés**. Ninguna comparación llega a
significación 95%. Acción correcta: **NO desmontarla a ciegas — instrumentarla**: registrar
cada gate con su motivo y medir a 3–5 días. Lo que sí se puede hacer YA es degradar la CELDA
ESTRELLA (20% con Wilson<50) y desactivar el "VETO apertura".

---

## 5. WR por SÍMBOLO (@15m, alta confianza)

| símbolo | n | WR | Wilson95 | ret | | símbolo | n | WR | Wilson95 | ret |
|---|---:|---:|---|---:|---|---|---:|---:|---|---:|
| NVDA | 48 | 46% | [33,60] | +0.000% | | GLD | 19 | 42% | [23,64] | −0.015% |
| AAPL | 32 | 56% | [39,72] | +0.090% | | QCOM | 19 | 79% | [57,91] | +0.285% |
| INTC | 25 | 56% | [37,73] | +0.263% | | ASML | 18 | 44% | [25,66] | +0.003% |
| MU | 25 | 56% | [37,73] | +0.232% | | SPCX | 17 | 41% | [22,64] | +0.023% |
| NFLX | 25 | 44% | [27,63] | −0.046% | | NOK | 17 | 53% | [31,74] | −0.086% |
| SPY | 25 | 32% | [17,52] | −0.022% | | SKHY | 17 | 41% | [22,64] | +0.165% |
| AMD | 24 | 50% | [31,69] | +0.263% | | SNDK | 17 | 41% | [22,64] | −0.186% |
| QQQ | 24 | 46% | [28,65] | +0.082% | | STX | 17 | 29% | [13,53] | −0.182% |
| TSM | 23 | 52% | [33,71] | +0.127% | | DRAM | 16 | 50% | [28,72] | +0.108% |
| AMZN | 22 | 45% | [27,65] | −0.001% | | EWY | 16 | 62% | [39,82] | +0.196% |
| GOOGL | 22 | 64% | [43,80] | +0.096% | | LRCX | 16 | 38% | [18,61] | −0.211% |
| MSFT | 21 | 38% | [21,59] | +0.028% | | TSLA | 16 | 56% | [33,77] | +0.110% |
| SMH | 20 | 55% | [34,74] | +0.074% | | AVGO | 16 | 50% | [28,72] | +0.049% |
| META | 19 | **21%** | [9,43] | −0.077% | | TXN | 15 | 40% | [20,64] | −0.072% |
| | | | | | | WDC | 13 | 46% | [23,71] | −0.179% |
| | | | | | | XLK | 12 | 50% | [25,75] | +0.043% |

Todos los símbolos tienen n<50 → **ningún WR por símbolo es concluyente**. Solo dos tienen el
Wilson superior por debajo de 50%: **META 21% [9,43] (n=19)** y **STX 29% [13,53]** (roza). Con
n=19 no se apaga una celda por un día; se vigila. QCOM 79% [57,91] (n=19) es el inverso: bonito
pero indemostrable. Nótese que `bollinger|TSLA` y `bollinger|QCOM` ya estaban apagadas del run
anterior (`docs/FALSE-SIGNALS-2026-07-24.md`) — QCOM aparece aquí vía otras fuentes.

---

## 6. WR por HORA (ET, @15m, alta confianza)

| hora | n | WR | Wilson95 | ret medio |
|---|---:|---:|---|---:|
| 09:00 | 98 | 51% | [41,61] | +0.193% |
| 10:00 | 113 | 55% | [46,64] | +0.050% |
| 11:00 | 79 | **33%** | [24,44] | −0.064% |
| 12:00 | 72 | 44% | [34,56] | +0.013% |
| 13:00 | 50 | 62% | [48,74] | +0.133% |
| 14:00 | 98 | **24%** | [17,34] | −0.181% |
| 15:00 | 105 | **66%** | [56,74] | +0.189% |
| 16:00 | 1 | — | — | — |

**Esto sí es concluyente al 95%** (los Wilson no cruzan 50%):
- **14:00–14:59 es un desastre: 24% [17,34] con n=98.** Composición: BB REBOTE 1m 44 señales
  al 23%, BB RE-ENTRADA 15m 18 al 6%. La picadora de la doctrina (regla 7: 11:30–14:00)
  medida en carne propia, y se extiende hasta las 15:00.
- **11:00 también negativo: 33% [24,44], n=79** (BB REBOTE 16%).
- **15:00 excelente: 66% [56,74], n=105** (BB REBOTE 63% n=57, RE-ENTRADA 15m 67% n=24, flow
  spikes 10/11).
  La última hora fue donde el elástico funcionó — al revés de la intuición de "última hora solo
  gestión".

Acción directa: **el elástico BB no debe hablar entre 11:00 y 15:00**, y el `timeofday_calib`
debería reflejar el bloque 15:00 como el mejor del día para BB.

---

## 7. Señales inservibles para backtest

- **`symbol` NULL: 16 señales** — `🚨/🧟 TWS WATCHDOG` (6), `🐘 MANADA BAJISTA` (2),
  `🎈 BOLLINGER VIGIA` (2), `🌊 FLOW PULSE v4` (1), `🛑 SCALPER HALT` (1), y 4 de tickers fuera
  de flota (`SLV: BUY`, `USO: SELL`, `CPER: SELL`, `CPER TERREMOTO CAIDA`).
  **Sí, son inservibles tal cual**: sin símbolo no hay precio de entrada. Matices: (a) las de
  watchdog/vigía/halt son de estado, nunca serán backtesteables ni deberían serlo; (b) las de
  CPER/SLV/USO **sí tendrían barras** (`data/bars_cper_ibkr.txt` existe) — el bug es que el bot
  no rellena `symbol`; arreglarlo recupera 4 señales/día; (c) `MANADA BAJISTA` es direccional
  y de mercado: se podría backtestear contra QQQ si se le pusiera `symbol='QQQ'`.
- **`WARMUP *`: 76 señales — EXCLUIDAS y hay que arreglarlo.** Todas llevan `ts_epoch` de
  09:18:23–09:18:55 (el arranque de los bots), pero son eventos históricos re-emitidos (p.ej.
  3 `WARMUP DRAM TERREMOTO ALZA` con precios 56.59 / 57.22 / 57.40 en el mismo segundo).
  Backtestearlas contra el precio de las 09:18 daría basura. **Recomendación: no escribirlas en
  `signals`, o escribirlas con el `ts_epoch` del evento original y una marca `warmup=1`.**
- **Sin dirección inferible: 64** — el grueso es `ESTRUCTURAL pin` (41) y `flip` (6), que por
  definición son neutrales; no se les inventó lado. `ALARMA PRECIO` (5) dice explícitamente
  "MIRAR el print, no entrar aun". `ZONA NVDA` (2) son fichas de orden con veredicto NO-GO.

---

## 8. Señales de dirección AMBIGUA: `GIRO A CALLS/PUTS` (80)

El mensaje solo dice "X girando a calls: ratio 1.00 desde 2.00" — no declara tesis. **No se
puede inferir la dirección con confianza**, así que van aparte. Bajo el supuesto de doctrina
(giro a calls = techo → corto; giro a puts = piso → largo):

| familia | horizonte | n | WR | Wilson95 | ret |
|---|---|---:|---:|---|---:|
| GIRO A CALLS (→ corto) | +15m | 49 | 65% | [51,77] | +0.248% |
| GIRO A PUTS (→ largo) | +15m | 31 | 32% | [19,50] | −0.430% |
| GIRO A CALLS | +30m | 49 | 49% | [36,63] | +0.187% |
| GIRO A PUTS | +30m | 31 | 42% | [26,59] | −0.277% |

La asimetría es exactamente la del sesgo del día (cortos ganan, largos pierden), así que **no
demuestra que el fade sea correcto**: demuestra que el 24/07 fue rojo. **Acción: que el emisor
escriba la tesis en el mensaje**, o estas 80 señales/día seguirán siendo no medibles.

---

## 9. Qué hacer (por orden de evidencia)

1. **Callar el elástico BB entre 11:00 y 15:00 ET** (24% y 33% con n=98/79, significativo).
2. **Degradar la CELDA ESTRELLA** de BB REBOTE: 20% [8,42] con ret −0.31%. Hoy fue la peor
   señal del sistema y es la que tiene voz garantizada.
3. **Quitar el "VETO apertura 9:45-10:30"** de `bb_context` (62% las silenciadas) y dejar el
   veto RSI2 (43%, sí filtra).
4. **Instrumentar la capa de condicionamiento** (guardar gate+motivo+prob en la BD) y medirla
   3–5 días antes de tocar nada más: el signo apunta invertido (+11pp para las silenciadas)
   pero z=1.57 no es prueba.
5. **Arreglar WARMUP y `symbol` NULL** para no perder 92 señales/día de la medición.
6. Mantener y vigilar lo único con lift positivo consistente: **flow spikes** y **magnets**
   (n=24 y n=30 — prometedores, no probados).

*Recordatorio final: todo lo anterior es un solo viernes, con fills perfectos y sin costes.
Ninguna de estas cifras justifica por sí sola comprar una opción.*
