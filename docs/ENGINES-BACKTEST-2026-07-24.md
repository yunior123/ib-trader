# Backtest de los ENGINES sobre el VIERNES 2026-07-24 — puntuado en la OPCIÓN REAL

Continuación de `ENGINES-STATE-2026-07-23.md`. Objetivo: confirmar o refutar con el viernes
que **BB solo pierde** y que los tres selectivos (Yoel cambio-de-tendencia, Yoel
fuera-de-banda, Confluencia C4) **pagan**. Señal-solamente. Ningún bot fue tocado.

---

## 0. DECLARACIÓN DE DATOS (leer antes que los números)

| qué | fuente | límite honesto |
|---|---|---|
| Barras 1m del viernes | `data/history/2026-07-24/bars/<sym>.txt` (IBKR, 33 símbolos, 23.824 barras) | filtradas a RTH 09:30–15:59 para ser homogéneas con el histórico yfinance |
| Contexto histórico (SMA20 diaria/1H que los detectores exigen) | `bars3mo5m_*` (5m, ~3 meses, hasta 7/22) + 7/23 + 7/24 de IBKR | compuesto por `scripts/fri_bars_prep.py` → `data/backtest/fri/bars{5m,1m}_<sym>.csv` |
| **Primas reales del viernes** | `data/history/2026-07-24/opt_chain_<sym>_HHMM.txt` — 26 símbolos × ~80 fotos, cada 5 min de 09:15 a 16:15 (**1.956 fotos**) | resolución temporal 5 min; filas con `-1` (fuera de ventana, ≥16:15) descartadas, **no** tratadas como precio 0 |
| Polygon | **NO tiene el 2026-07-24** (última barra 2026-07-23 19:59) | no se usó; el scorer local lo sustituye |
| Flujo de ballenas | `data/whale_flow_hist.jsonl` tiene 7/24 (1.505 registros, 25 símbolos) | combo_engine sí pudo correr con contexto real |

**Universo**: 26 símbolos con barras Y cadena (aapl amd amzn asml avgo dram googl intc lrcx
meta msft mu nok nvda qcom qqq skhy smh sndk spcx spy stx tsla tsm txn wdc).

**Verificado**: 0 procesos de `yoel_*`, `confluence_engine`, `bb_engine` o `combo_engine`
corriendo (`ps aux`). Los tres motores con edge del 7/23 siguen **apagados**.

---

## 1. MÉTODO DE PUNTUACIÓN EN EL VEHÍCULO REAL

`scripts/local_option_scorer.py` (nuevo). Para cada señal:

1. **Sin look-ahead**: el epoch de una señal es el START de la barra que dispara
   (`bb_core.h` línea 194). La entrada se busca en la **primera foto de cadena con
   epoch ≥ señal + duración de barra** (60 s para bb/combo que corren en 1m; 900 s para
   Yoel/confluencia que disparan en 15m). Esto corrige de paso un look-ahead del
   `yoel_engine.py` original, que entraba en el open del 5m *siguiente* — dentro todavía
   de la vela 15m que dispara.
2. **Contrato**: ATM (strike más cercano al spot de esa foto) del vencimiento pedido.
   Se reporta **0DTE** (`20260724`) y **NEXT** (el siguiente listado: `20260727` lunes en
   los líquidos, `20260731` en NOK/DRAM/etc.).
3. **ENTRADA AL ASK, SALIDA AL BID.** → **el spread bid-ask real está DENTRO de todos los
   números de este documento.** Es la ventaja del método sobre cualquier síntesis
   Black-Scholes o sobre agregados OHLC de opción.
4. **Sin stop** (la prima es la pérdida máxima, método de la casa). TP: se reporta
   **+30% / +50% / +100%**, porque +100% intradía en un solo día es raro.
   Sin TP alcanzado → se liquida al **último bid válido** del día (≈16:00).
5. Primas < $0.05 descartadas (el +100% ahí es ruido de tick).
6. **SIN COMISIONES.** Declarado. IBKR ≈ $0.65/contrato ida y vuelta ≈ 1,3% sobre una
   prima de $100 — no cambia ninguna conclusión de abajo, pero no está descontado.

**Contraste obligatorio**: el MISMO conjunto puntuado en el SUBYACENTE con scalp
uniforme (target 1,5·ATR15 / stop 1,0·ATR15, horizonte 120 min, stop gana la barra
empatada), en R-múltiplos.

---

## 2. EL VIERNES FUE UN DÍA DE UNA SOLA DIRECCIÓN — esto domina todo

Movimiento 09:30 → 15:59: **mediana −1,75%, 25 de 30 símbolos en rojo.**
Masacre de memoria/semis: INTC −8,0%, SNDK −7,5%, SKHY −5,6%, NOK −5,3%, AMD −4,6%,
DRAM −4,4%, MU −4,1%. AAPL +3,5% fue la única excepción grande.

Por eso el número central de este documento no es ningún motor, sino la **BETA DEL DÍA**:
comprar el ATM en **cada foto de cada símbolo** (09:45–15:55), mismo método (ask→bid).

| vehículo | TP | CALL n=1839 | PUT n=1839 |
|---|---|---|---|
| 0DTE | +30% | 33,2% WR, **−48,5%**/trade | 71,7% WR, +0,4% |
| 0DTE | +50% | 27,1% WR, −50,3% | 66,2% WR, +8,3% |
| **0DTE** | **+100%** | **17,6% WR, −57,0%** | **56,9% WR, +20,9%** |
| NEXT | +100% | 14,3% WR, −23,2% | 59,9% WR, +13,4% |

**Traducción brutal: el viernes, tirar un dardo y comprar un PUT 0DTE pagaba 56,9% y
+20,9% por trade. Cualquier motor que no supere eso no aportó NADA.**
`data/backtest/fri/bench_2026-07-24.json`.

---

## 3. RESULTADOS — TODOS LOS MOTORES (0DTE, TP +100%, Wilson 95%)

| motor / señal | n | WR | Wilson 95% | ret/trade | subyacente (mismo set) |
|---|---|---|---|---|---|
| **BB solo 15m** (baseline confluencia) | 160 | **25,0%** | [18,9 – 32,2] | **−42,0%** | 41,2% WR, −0,06R |
| bb_engine ELASTIC (1m) | 254 | 34,3% | [28,7 – 40,3] | −22,7% | 41,7% WR, −0,05R |
| bb_engine SQZ_BRK | 25 | 72,0% | [52,4 – 85,7] | +39,8% | 76,0% WR, +0,82R |
| **bb_engine TOTAL** | **280** | **37,9%** | [32,4 – 43,7] | **−16,7%** | 44,6% WR, +0,02R |
| combo_engine combo_elastic | 156 | 44,9% | [37,3 – 52,7] | −6,7% | 40,3% WR, −0,08R |
| combo_engine combo_captain | 40 | 35,0% | [22,1 – 50,5] | −19,3% | 27,5% WR, −0,18R |
| **combo_engine TOTAL** | **196** | **42,9%** | [36,1 – 49,9] | **−9,3%** | 37,7% WR, −0,10R |
| Confluencia C2 | 91 | 29,7% | [21,3 – 39,7] | −29,7% | 48,9% WR, +0,11R |
| Confluencia C3 | 22 | 36,4% | [19,7 – 57,0] | −26,8% | 31,8% WR, −0,18R |
| Confluencia C4 | **3** | 33,3% | [6,1 – 79,2] | −43,9% | 33,3% WR, −0,17R |
| **Confluencia TOTAL** | **116** | **31,0%** | [23,3 – 39,9] | **−29,5%** | 45,3% WR, +0,05R |
| Yoel puro TOTAL | 12 | 50,0% | [25,4 – 74,6] | −5,2% | 25,0% WR, −0,38R |
| **Yoel ADAPTADO TOTAL** | **6** | **83,3%** | [43,6 – 97,0] | **+52,5%** | 50,0% WR, +0,25R |
| — Yoel adaptado `cambio_tend` | 4 | 100% | [51,0 – 100] | +78,7% | 50,0% WR |
| — Yoel adaptado `fuera_banda` | 2 | 50% | [9,5 – 90,5] | +0,2% | 50,0% WR |

Con TP realista **+30%** el orden no cambia: BB solo 39,4% / −39,3%; bb_engine 48,6% / −28,2%;
combo 52,0% / −26,8%; confluencia 44,8% / −30,9%; Yoel adaptado **83,3% / +8,4%**.

Con vencimiento **NEXT** (menos theta) todo mejora en retorno pero el ranking se mantiene:
BB solo 15,6% / −14,4%; bb_engine 41,4% / −0,8%; combo 44,9% / **+0,5%**; confluencia
19,8% / −10,3%; Yoel adaptado 66,7% / +7,1%.

Variante presupuesto de la casa (**prima ≤ $200**): bb_engine n=182 36,3% / −19,6%;
combo n=120 41,7% / −11,1%; confluencia n=45 26,7% / −36,8%; BB solo n=78 29,5% / −33,9%;
Yoel adaptado n=3 100% / +100%. No salva a nadie.

---

## 4. LO QUE DE VERDAD IMPORTA: EXCESO SOBRE LA BETA DEL DÍA

Mismo TP +100% 0DTE, partido por lado, contra el benchmark de la sección 2 (z de dos
proporciones):

| motor | lado | n | WR | ret | beta | z |
|---|---|---|---|---|---|---|
| bb_engine ELASTIC | LONG | 143 | 18,2% | −55,1% | 17,6% / −57,0% | +0,18 |
| bb_engine ELASTIC | SHORT | 111 | 55,0% | +19,2% | 56,9% / +20,9% | −0,40 |
| bb_engine SQZ_BRK | SHORT | 21 | 81,0% | +57,6% | 56,9% | **+2,21** |
| combo_elastic | SHORT | 87 | 69,0% | +41,8% | 56,9% | **+2,22** |
| combo_elastic | LONG | 69 | 14,5% | −67,9% | 17,6% | −0,67 |
| combo_captain | SHORT | 20 | 50,0% | +15,7% | 56,9% | −0,62 |
| Confluencia C2 | LONG | 69 | 24,6% | −37,6% | 17,6% | +1,50 |
| Confluencia C3 | LONG | 10 | 0,0% | −99,3% | 17,6% | −1,46 |
| Confluencia TOTAL | SHORT | 36 | 52,8% | +7,1% | 56,9% | −0,49 |
| BB solo | LONG | 135 | 20,0% | −50,4% | 17,6% | +0,70 |
| BB solo | SHORT | 25 | 52,0% | +3,2% | 56,9% | −0,49 |
| Yoel adaptado | LONG | 3 | 66,7% | +33,4% | 17,6% | +2,23 |
| Yoel adaptado | SHORT | 3 | 100% | +71,6% | 56,9% | +1,51 |

**Solo dos celdas pasan de |z|>2 con n usable: `combo_elastic` SHORT (z=+2,22, n=87) y
`SQZ_BRK` SHORT (z=+2,21, n=21).** Se probaron ~20 celdas: con Bonferroni el umbral es
z≈2,9. **Ninguna sobrevive la corrección por comparaciones múltiples.** Son pistas, no
hallazgos.

---

## 5. RESPUESTAS A LAS PREGUNTAS DEL ENCARGO

### ¿Se sostiene "BB solo pierde"? — **SÍ, ROTUNDO.**
El 7/23 midió 45% WR / −8%/trade (n=1937, opción real Polygon). El viernes, con primas
locales y spread dentro: **BB solo 25,0% WR / −42,0%** (0DTE) y **15,6% / −14,4%** (NEXT),
n=160. El bb_engine completo (elastic 1m, el diseño live) tampoco: 37,9% / −16,7%.
Y lo peor: **su exceso sobre la beta es cero en ambos lados** (z +0,70 y −0,49). BB solo no
solo pierde: no distingue nada que la dirección del día no diera gratis.
Como BB es ~73% del volumen de señales de la flota, esto sigue siendo el agujero #1.

### ¿Se sostiene "Confluencia C4 paga"? — **NO CONCLUYENTE, y el viernes NO pagó.**
- En la OPCIÓN 0DTE la escalera **no es monótona**: C2 29,7% → C3 36,4% → C4 33,3%, y
  **C4 tiene n=3** (Wilson [6,1 – 79,2] — inútil).
- En el SUBYACENTE tampoco: C2 48,9% → C3 31,8% → C4 33,3%.
- Retorno C4 en opción: **−43,9%**.
**Un solo día no puede juzgar C4** (3 señales). Lo que sí se puede decir es que la
monotonía C2→C3→C4 del 7/23 **no se reprodujo** el viernes, en ninguno de los dos vehículos.

### ¿Se sostiene "Yoel cambio-de-tendencia / fuera-de-banda pagan"? — **CONSISTENTE, pero n=6.**
Yoel adaptado emitió **6 señales** en todo el viernes en 26 símbolos. 5 ganaron:

```
09:30 ASML  SHORT cambio_tend  K1787.5 0DTE  $15.30  -> +100%
09:30 DRAM  SHORT cambio_tend  K55.0   0DTE  $ 1.00  -> +100%
09:30 GOOGL LONG  fuera_banda  K320.0  0DTE  $ 1.90  -> +100%
09:30 TSLA  LONG  fuera_banda  K317.5  0DTE  $ 3.15  -> -100%
09:45 LRCX  SHORT cambio_tend  K312.5  0DTE  $ 6.10  ->  +15%
10:00 NVDA  LONG  cambio_tend  K207.5  0DTE  $ 1.19  -> +100%
```

`cambio_tend` 4/4 (+78,7%/trade). **Wilson [43,6 – 97,0] con n=6 NO es prueba de nada** —
es exactamente lo que el 7/23 avisó sobre los n chicos. Pero es consistente con el 64%/n=226
de Polygon, y viene con la firma correcta: **el motor selectivo dispara poquísimo y sus
entradas fueron LONG rentables en un día en que el LONG genérico perdía 57%** (z=+2,23,
n=3 — anecdótico, no estadístico).

### El VETO band-walk del adaptado funcionó (evidencia limpia del día)
Yoel puro emitió 12 señales, el adaptado 6. Los 6 podados fueron los `iman` (fade contra
banda que camina). Sus resultados reales: WDC −100%, DRAM −98%, SNDK −99%, STX −97%,
SMH −83% y MU +100%. **El veto cortó 5 desastres y sacrificó 1 acierto.** El `iman` en
conjunto: 16,7% WR / −62,9%/trade (n=6) — sigue siendo la peor señal medida, igual que el
47%/+1% del 7/23 pero peor en un día de tendencia. La regla 1 de CLAUDE.md (band-walk =
continuación, no rebote) queda respaldada otra vez.

### ¿Cambia el veredicto según el vehículo? — **SÍ, y de forma dramática.**
| conjunto | subyacente | opción 0DTE TP+100 |
|---|---|---|
| BB solo | 41,2% WR, −0,06R → "mediocre" | **25,0% WR, −42,0%** → "catastrófico" |
| Confluencia TOTAL | 45,3% WR, +0,05R → "breakeven" | **31,0% WR, −29,5%** → "sangría" |
| bb_engine TOTAL | 44,6% WR, +0,02R | 37,9% WR, −16,7% |
| Yoel puro TOTAL | 25,0% WR, −0,38R → "malo" | 50,0% WR, −5,2% → "casi neutro" |
| Yoel adaptado | 50,0% WR, +0,25R | **83,3% WR, +52,5%** |

**Confirmado: puntuar en el subyacente MIENTE.** Pero atención al matiz — el 7/23 concluyó
que la opción era más *generosa* con la confluencia (C2 54 → C4 59 vs ~40% plano en
subyacente). El viernes ocurre lo **contrario**: la opción es mucho más *dura* con las
señales de reversión (theta 0DTE + comprar calls contra una caída) y más *generosa* con las
selectivas direccionales. La afirmación correcta y general es: **el vehículo cambia el
veredicto**; la dirección del cambio depende del régimen del día, no es una constante.

---

## 6. RANKING DEL VIERNES (qué pagó y qué no)

1. 🥇 **Yoel ADAPTADO** — único motor con retorno positivo grande (+52,5%/trade, 83,3% WR).
   **n=6: prometedor, NO concluyente.**
2. 🥈 **combo_engine** (BB + flujo con jerarquía de capitanes) — el menos malo de los de
   volumen: −9,3% vs −16,7% del bb solo. Su `combo_elastic` SHORT (69,0%, z=+2,22, n=87)
   es la señal de n usable más interesante del día, **pero no sobrevive Bonferroni**.
   Nota: el gating de flujo mejoró bb_engine en 5 puntos de WR con casi 100 señales menos.
3. 🥉 **SQZ_BRK** — 72% / +39,8% (n=25). Inversión total frente a los 3 meses
   (27,8%, "pierde"). Es exactamente lo esperable: un breakout de squeeze **paga en día de
   tendencia y muere en día de rango**. No re-habilitarlo por este día; sí anotar que su
   fallo del 7/23 puede ser dependencia de régimen, no un fallo de diseño.
4. ❌ **Confluencia** — 31,0% / −29,5%. Sin monotonía, sin exceso sobre la beta.
5. ❌❌ **BB solo** — 25,0% / −42,0%. El peor. Confirma el 7/23 y lo empeora.
6. ❌❌ **Yoel `iman`** — 16,7% / −62,9%. El fade ingenuo es el enemigo.

---

## 7. LÍMITES HONESTOS

- **n de UN día.** Todo lo de Yoel (n=6/12) y C4 (n=3) es **no concluyente**. Wilson
  publicado en todo para que se vea.
- **Un régimen único**: día de tendencia bajista fuerte (mediana −1,75%, 25/30 rojos).
  Cualquier motor que compre reversión LONG estaba condenado; cualquiera que se pusiera
  corto cobraba gratis. Por eso la sección 4 (exceso sobre beta) es la única lectura
  válida del "skill", y ahí casi nadie gana.
- **~20 comparaciones** → riesgo de falso positivo alto. Bonferroni z≈2,9: nadie pasa.
- **Resolución 5 min** en la cadena: la entrada real puede llegar hasta 5 min después del
  cierre de la barra que dispara. Es slippage real y está **dentro** de los números
  (perjudica, no favorece), pero un motor de 1m operado con fills de 5m está infra-medido.
- **Sin comisiones.**
- **Contexto histórico híbrido**: yfinance 5m/1m hasta 7/22 + IBKR 7/23–7/24. Fuentes
  distintas para las SMA/BB largas; el efecto es pequeño (RTH en ambas) pero existe.
- **`combo_captain`** (n=40) fue el peor sub-bucket del combo (35,0%, −19,3%). Primera vez
  que tiene n; contradice la intuición del "refuerzo". Vigilar, no cablear.
- **GEX / `gex_gate.py` sigue sin medirse** — overlay en vivo, igual que el 7/23.

---

## 8. QUÉ HACER CON ESTO

1. **BB solo NO debe ser el 73% del volumen de señales de la flota.** Dos días de datos
   independientes (Polygon 3 meses y viernes local) dicen lo mismo. Es la corrección de
   mayor impacto disponible.
2. **Encender Yoel-adaptado en modo señal-solo y acumular histórico diario** con este mismo
   scorer local. Con 6 señales/día en 26 símbolos, hacen falta ~5 semanas para n≈150.
   Es barato y no rompe nada.
3. **Añadir la BETA DEL DÍA como línea base obligatoria** en todo backtest de un día: sin
   ella, un 65% de WR en día de tendencia parece edge y no lo es.
4. **No re-habilitar SQZ_BRK** por este día, pero medir su WR condicionado a régimen
   (tendencia vs rango) — es la hipótesis más concreta que salió del viernes.
5. **El veto band-walk del adaptado va a todos los motores de fade** (cortó 5/6 desastres).

---

## 9. REPRODUCIR

```bash
cd ~/Documents/GitHub/ib-trader
./venv/bin/python scripts/fri_bars_prep.py                       # barras compuestas
for s in $(cat data/backtest/fri/syms.txt); do
  ./engines/bb_engine    --backtest data/backtest/fri/bars5m_$s.csv --sym ${s:u} \
      --csv1m data/backtest/fri/bars1m_$s.csv --out data/backtest/fri/sig/bb_$s.csv
  ./engines/combo_engine --backtest data/backtest/fri/bars5m_$s.csv --sym ${s:u} \
      --flow data/whale_flow_hist.jsonl --csv1m data/backtest/fri/bars1m_$s.csv \
      --out data/backtest/fri/sig/combo_$s.csv
done
export BARS5M_TMPL='data/backtest/fri/bars5m_{sym}.csv'          # override añadido
./venv/bin/python scripts/yoel_engine.py $SYMS
./venv/bin/python scripts/yoel_adapted_engine.py $SYMS
./venv/bin/python scripts/confluence_engine.py $SYMS
# beta del dia + puntuacion en opcion real
./venv/bin/python scripts/local_option_scorer.py --date 2026-07-24 --bench
./venv/bin/python scripts/local_option_scorer.py --date 2026-07-24 \
    data/backtest/fri/sig/FRI_bb_engine.csv:60 data/backtest/fri/sig/FRI_combo_engine.csv:60 \
    data/backtest/fri/sig/FRI_yoel_pure.csv:900 data/backtest/fri/sig/FRI_yoel_adapted.csv:900 \
    data/backtest/fri/sig/FRI_confluence.csv:900 data/backtest/fri/sig/FRI_bb_baseline.csv:900
```

**Artefactos**: `data/backtest/fri/scores_2026-07-24.json`, `bench_2026-07-24.json`,
`trades_FRI_*_0dte.json`, `sig/FRI_*.csv`.
**Nuevos**: `scripts/local_option_scorer.py` (scorer de opción real sin Polygon, reusable
cualquier día que existan fotos de cadena), `scripts/fri_bars_prep.py`.
**Modificados (aditivo, degradación limpia)**: `scripts/yoel_engine.py` y
`scripts/confluence_engine.py` aceptan `BARS5M_TMPL` para apuntar a otras barras; sin la
variable se comportan exactamente igual que antes.
