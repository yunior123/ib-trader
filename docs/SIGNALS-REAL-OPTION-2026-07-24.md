# SEÑALES DEL 2026-07-24 RE-PUNTUADAS EN EL VEHÍCULO REAL (la opción comprada)

Compañero de `docs/BACKTEST-SIGNALS-2026-07-24.md` (ese midió el SUBYACENTE). Aquí se
repite el ejercicio comprando la **opción ATM del vencimiento más cercano**, con primas
reales de IBKR, **entrando al ASK y saliendo al BID**. Motivo: `docs/ENGINES-STATE-2026-07-23.md`
ya demostró que el veredicto cambia según el vehículo (confluencia plana ~40% en el
subyacente, monótona C2 54 → C3 56 → C4 59 en la opción). Un backtest de subyacente puede
enterrar señales buenas y salvar malas. Este las vuelve a puntuar donde de verdad se paga.

Scripts: `scripts/option_vehicle_backtest.py` (resolución de contrato + camino de prima) y
`scripts/option_vehicle_report.py` (tablas). Salida cruda: `data/option_vehicle_2026-07-24.json`.

---

## 0. Metodología y ADVERTENCIAS

- **Señales**: `trades.db` tabla `signals`, `date='2026-07-24'` → **776 filas** (las 2.691
  filas WARMUP con timestamp falso ya fueron purgadas; no entran aquí).
- **Primas**: `data/history/2026-07-24/opt_chain_<sym>_HHMM.txt` — foto de cadena cada 5 min
  de 09:20 a 16:15, con `strike right exp bid ask vol oi iv delta gamma` y cabecera con
  epoch + spot. Las filas posteriores a 16:15 salen con **-1** en bid/ask/iv/delta/gamma y
  **se filtran** (no se tratan como 0).
- **Contrato**: `right = C` si la tesis es alcista, `P` si bajista; **strike más cercano al
  spot** de la cabecera; **vencimiento más cercano** del fichero. En la práctica el 100% de
  los 535 contratos resueltos fueron **0DTE (20260724)** — ver §7 la sensibilidad al semanal.
- **Entrada = ASK. Salida = BID.** Esto es la ventaja de este método frente al del
  subyacente: **el spread real está incluido en cada número**, no es un ajuste posterior.
  Un contrato con 10% de spread empieza el trade a −10%.
- **Foto de entrada**: la primera foto con epoch **>=** el instante de la señal (nunca una
  anterior, para no mirar al futuro ni al pasado favorable). Retardo mediano **2,6 min**,
  máximo 8. Es la penalización real de la rejilla de 5 minutos y **abarata** artificialmente
  nada: en un día bajista muchas entradas llegan peor, no mejor.
- **Salidas**: foto más cercana a +15 / +30 / +60 min (tolerancia ±4 min).
- **MFE / TP / bracket** se miden sobre el **bid** de las fotos de 5 min dentro de 60 min.
  Como la rejilla es gruesa, **las tasas de TP son cota INFERIOR** (se pierden picos
  intra-foto) y los stops del bracket son **optimistas** (un stop real salta más veces).
- **SIN comisiones** (IBKR ≈ $0,65/contrato ida y vuelta ≈ 0,9% sobre una prima de $150).
  El spread SÍ está incluido. No hay modelo de slippage adicional ni de rechazo de fill.
- **Victoria** = bid de salida > ask de entrada, es decir **dinero neto en el bolsillo**.
- **Un solo viernes.** Wilson 95% en todo. Cualquier celda con n<20 es **NO CONCLUYENTE**
  aunque el número sea bonito.

### Cobertura (de 776 señales)

| categoría | n | ¿puntuada? |
|---|---:|---|
| Con dirección inferible y contrato resuelto | **605** | SÍ |
| — de ellas, dirección firme (base de todas las tablas) | **535** | SÍ |
| — de ellas, AMBIGUAS (`GIRO A CALLS/PUTS`, supuesto fade) | 70 | aparte (§6) |
| Sin dirección inferible (pin 41, flip 6, watchdog 6, alarmas 5, …) | 75 | NO |
| **Sin cadena de opciones cacheada**: NFLX 27, GLD 22, EWY 16, XLK 16 | **81** | NO |
| Sin foto de cadena tras la señal / sin ATM cotizable / symbol NULL | 15 | NO |

Reglas de dirección: idénticas a las del backtest de subyacente (`eod_backtest.thesis`
ampliada) para que la comparación sea limpia. Única desviación declarada: **`MANADA A
CALLS/PUTS` se puntúa sobre QQQ**, porque el mensaje dice literalmente "rebote del **índice**"
y el `price` guardado es el de QQQ (el `symbol` del registro es un bug del emisor).

**Primer hallazgo, gratis: 81 señales/día (10%) salen sobre tickers de los que la flota ni
siquiera cachea la cadena** (NFLX, GLD, EWY, XLK). No son medibles en opción y, más grave, no
son ejecutables en opción con la información que el propio sistema tiene.

---

## 1. HALLAZGO PRINCIPAL — el 75% de las señales apunta a un contrato que la doctrina
## prohíbe comprar

Gate de la doctrina (regla 4 de `CLAUDE.md`, criterio de `scripts/optgate.py`):
**spread = (ask−bid)/ask ≤ 5%** y **OI > 500**. Presupuesto: **prima ≤ $200** por orden.

| filtro sobre las 535 señales de dirección firme | n | % |
|---|---:|---:|
| Pasan el gate (spread ≤5% **y** OI >500) | **161** | **30%** |
| Falla por spread >5% | 362 | 68% |
| Falla por OI ≤500 | 163 | 30% |
| Falla por ambos | 151 | 28% |
| Prima > $200 (fuera de presupuesto) | **214** | **40%** |
| **Pasan gate Y presupuesto → OPERABLES** | **134** | **25%** |

- Spread mediano del contrato al que apunta la señal: **9,1%** (medio 16,1%).
- Spread medio pagado por las que **fallan** el gate: **22,1%**. Por las que lo pasan: **2,3%**.
- OI mediano 1.433. Prima mediana $159.

**12 de los 26 símbolos con cadena tienen 0% de señales que pasen el gate** — AMD, ASML,
AVGO, DRAM, LRCX, QCOM, SKHY, SMH, STX, TSM, TXN, WDC. Son **206 señales** (38% del total)
que el sistema canta y que **no se pueden ejecutar con opciones jamás**, ningún día, con esa
liquidez. Una señal que no puedes ejecutar no es una señal: es ruido con emoji.

---

## 2. GLOBAL — la opción destroza el número del subyacente… salvo si pasa el gate

Comparación **pareada** (misma señal, mismo instante; subyacente = `backtest_signal_outcomes`
`run_ts=1784941080`):

| subconjunto | H | n pareada | WR subyacente | WR **opción** | Δ |
|---|---|---:|---:|---:|---:|
| todas | +15m | 496 | 46% [42,50] | **31% [27,35]** | **−15pp** |
| todas | +30m | 461 | 48% [43,52] | **34% [30,38]** | −14pp |
| gate OK | +15m | 148 | 48% [40,56] | **40% [32,48]** | −8pp |
| gate OK | +30m | 143 | 52% [44,60] | **48% [40,56]** | −4pp |
| gate + presupuesto | +30m | 121 | 51% [42,60] | 47% [38,56] | −4pp |

Tabla completa en el vehículo (entrada ask, salida bid):

| subconjunto | H | n | WR | Wilson95 | ret medio | ret mediano |
|---|---|---:|---:|---|---:|---:|
| TODAS | +15m | 507 | **31%** | [27,35] | **−13,4%** | −18,9% |
| TODAS | +30m | 472 | 35% | [30,39] | −12,5% | −22,8% |
| TODAS | +60m | 423 | 34% | [29,38] | −1,4% | −21,9% |
| **FALLA el gate** | +15m | 349 | **27%** | [23,32] | **−19,6%** | −26,8% |
| **FALLA el gate** | +60m | 276 | 29% | [24,35] | −16,3% | −31,7% |
| **PASA el gate** | +15m | 158 | **39%** | [32,47] | **+0,2%** | −11,0% |
| **PASA el gate** | +30m | 153 | **48%** | [41,56] | **+6,8%** | −3,0% |
| **PASA el gate** | +60m | 147 | 43% | [35,51] | **+26,5%** | −11,0% |
| gate + presupuesto | +30m | 127 | 48% | [40,57] | +7,3% | −3,0% |

**Descomposición honesta del −15pp: casi todo es el spread, no la señal.** Repitiendo el
mismo ejercicio **mid→mid** (sin pagar el cruce):

| | +15m | +30m | +60m |
|---|---|---|---|
| TODAS ask→bid | 31% / −13,4% | 35% / −12,5% | 34% / −1,4% |
| TODAS mid→mid | **43% / +1,9%** | 43% / +1,8% | 43% / +13,6% |
| GATE OK ask→bid | 39% / +0,2% | 48% / +6,8% | 43% / +26,5% |
| GATE OK mid→mid | 41% / +3,0% | 50% / +9,8% | 44% / +30,2% |

Mid→mid la opción reproduce casi exactamente el subyacente (43% vs 46%). **Es decir: el
sistema no es peor en opciones — es que el 70% de sus señales apunta a contratos cuyo cruce
se come la tesis antes de que el precio se mueva.** En las que pasan el gate el coste del
spread es 2pp, ruido; en las que no, es 12pp, la diferencia entre ganar y perder.

### El daño real: MAE

| subconjunto | MAE medio (≤60m) | MAE mediano | % que toca −50% |
|---|---:|---:|---:|
| TODAS | −45,0% | −46,7% | **47%** |
| GATE OK | −33,8% | −33,3% | 32% |

Casi la mitad de las posiciones habría estado −50% en algún momento dentro de la hora.
**Sin stop server-side esto es una cuenta muerta**, aunque el WR final no lo parezca.

---

## 3. TOMA DE BENEFICIOS: el TP de la casa (+100%) y los realistas

Tasa de toque del TP dentro de 60 min (sobre el bid, cota inferior):

| subconjunto | n | TP +30% | TP +50% | **TP +100% (la casa)** |
|---|---:|---:|---:|---:|
| TODAS | 529 | 39% [35,43] | 30% [26,34] | **14% [11,17]** |
| PASA el gate | 161 | 52% [44,60] | 46% [38,54] | **25% [19,33]** |
| gate + presupuesto | 134 | 51% [43,60] | 44% [36,52] | 26% [19,34] |

Bracket completo (TP contra **SL −30%**, gana el primero que toca; si ninguno, salida al bid
a +60m). Esto sí es una estrategia, no una estadística:

| subconjunto | TP+30/SL−30 | TP+50/SL−30 | TP+100/SL−30 |
|---|---|---|---|
| TODAS | hit 32% · **exp −10,4%/trade** | 29% · −7,0% | 25% · −3,0% |
| **PASA el gate** | 48% · −1,3% | 45% · **+5,2%** | 37% · **+12,7%** |
| gate + presupuesto | 46% · −2,2% | 43% · +3,3% | 36% · **+11,0%** |
| falla el gate | — | — | −9,8% |

**El TP de la casa (+100%) es el que más expectativa deja — pero solo si el contrato pasa el
gate.** La doctrina de "chico y seguro" (+30%) es la PEOR de las tres en la opción: cobra
poco y no compensa el −30% del stop. La asimetría de la prima comprada exige dejar correr.
Con n=161 y un solo día, **+12,7%/trade NO es un edge demostrado**: es la primera evidencia
de que el gate, no la señal, es donde está el dinero.

Bracket TP+30/SL−30 por familia, solo gate OK (expectancy por trade):

| familia | n | hit | exp |
|---|---:|---:|---:|
| MANADA A CALLS | 8 | 75% | **+15,0%** |
| CUSUM TERREMOTO | 4 | 75% | +22,5% |
| FLOW SPIKE CALLS | 12 | 67% | +8,1% |
| ESTRUCTURAL magnet | 24 | 62% | **+7,5%** |
| BB BAND-WALK | 15 | 60% | +4,5% |
| CAPITAN REVIERTE | 7 | 57% | +4,3% |
| BALLENA PUTS | 4 | 50% | −3,5% |
| BB REBOTE 1m | 40 | 40% | −5,5% |
| MANADA A PUTS | 3 | 33% | −10,0% |
| BB RE-ENTRADA 15m | 19 | 32% | −11,1% |
| BALLENA CRECE (calls) | 7 | 29% | −12,9% |
| FLOW SPIKE PUTS | 10 | 20% | **−17,0%** |
| BB REBOTE 1m ⭐ | 3 | 0% | **−30,0%** |

---

## 4. POR FAMILIA — ¿quién cambia de veredicto al medir en la opción?

### 4.1 Comparación pareada @15m (todas, sin filtrar gate)

| familia | n | WR subyacente | WR **opción** | Δ | veredicto |
|---|---:|---:|---:|---:|---|
| BB REBOTE 1m | 187 | 45% [38,52] | **24% [18,30]** | −21pp | **EMPEORA mucho** |
| BB RE-ENTRADA 15m | 84 | 32% [23,43] | 21% [14,31] | −11pp | EMPEORA |
| BB BAND-WALK | 56 | 50% [37,63] | 48% [36,61] | −2pp | igual |
| ESTRUCTURAL magnet | 27 | 70% [52,84] | 59% [41,75] | −11pp | sigue siendo el mejor |
| FLOW SPIKE CALLS | 26 | 69% [50,83] | 38% [22,57] | −31pp | **EMPEORA mucho** |
| FLOW SPIKE PUTS | 21 | 62% [41,79] | 43% [24,63] | −19pp | **VUELCO** (ver abajo) |
| BB REBOTE 1m ⭐ | 19 | 21% [9,43] | 16% [6,38] | −5pp | confirmado desastre |
| BALLENA PUTS | 15 | 27% [11,52] | 20% [7,45] | −7pp | confirmado malo |
| CUSUM TERREMOTO | 13 | 69% [42,87] | 38% [18,64] | −31pp | necesita +60m |
| BALLENA CRECE (calls) | 12 | 33% | 33% | 0pp | igual |
| BB APERTURA FUERA | 12 | 33% [14,61] | 17% [5,45] | −16pp | **EMPEORA** |
| BALLENA CALLS | 9 | 44% | 22% | −22pp | EMPEORA |
| CAPITAN REVIERTE | 7 | 57% | 43% | −14pp | n=7 |

### 4.2 En el vehículo, con horizonte largo y solo lo operable

| familia (GATE OK) | n | WR@15m | WR@30m | WR@60m | ret@60m | TP+100% | %señales operables |
|---|---:|---:|---:|---:|---:|---:|---:|
| **ESTRUCTURAL magnet** | 24 | 58% [39,76] | **67% [47,82]** | **85% [64,95]** | **+74,0%** | 46% | **78%** |
| BB BAND-WALK | 15 | 64% [39,84] | 47% | 47% | +39,7% | 33% | 18% |
| FLOW SPIKE CALLS | 12 | 42% | **67% [39,86]** | 55% | +67,9% | 33% | 42% |
| MANADA A CALLS | 8 | 38% | 62% | 57% | +81,2% | 38% | 62% |
| CUSUM TERREMOTO | 4 | 75% | 50% | **100% [51,100]** | +136,7% | 75% | 23% |
| CAPITAN REVIERTE | 7 | 43% | 57% | 17% | +17,2% | 14% | 86% |
| BB REBOTE 1m | 39 | 33% | 44% | 37% | +23,2% | 15% | 17% |
| BB RE-ENTRADA 15m | 19 | 26% | 44% | 41% | +10,8% | 26% | 21% |
| **FLOW SPIKE PUTS** | 10 | **20% [6,51]** | 25% | **10% [2,40]** | **−38,9%** | 10% | 41% |
| BALLENA CRECE (calls) | 7 | 17% | 29% | 14% | −39,4% | 14% | 31% |
| BALLENA PUTS | 4 | 25% | 25% | **0%** | −34,2% | 0% | 13% |
| **BB REBOTE 1m ⭐** | 3 | **0%** | **0%** | **0%** | **−96,5%** | 0% | 16% |
| BB APERTURA FUERA | 0 | — | — | — | — | 8%(todas) | **0%** |

### Los cinco veredictos que CAMBIAN

1. **`FLOW SPIKE PUTS` — de "mejor candidato a edge" a PERDEDOR.** El backtest de subyacente
   lo coronó (LIFT +6/+27/+22pp, 62–71% WR) y el doc recomendó "mantener y vigilar". En la
   opción: 43% @15m, **25% @30m, 10% @60m** (n=10 gate-OK), ret **−38,9%**, bracket
   **−17,0%/trade**, la peor expectativa de todas las familias con n≥10. Es un LARGO comprado
   dentro de un pánico: entra con IV inflada, el rebote del subyacente es pequeño y la vega se
   desinfla más rápido de lo que sube el delta. **En el subyacente ganaba +0,12%; en la opción
   perdía dinero.** n pequeño → no es sentencia, pero el signo se invierte en los 3 horizontes
   y eso descalifica la recomendación anterior.
2. **`BB REBOTE 1m` — de "moneda" a "trituradora".** 45% → **24%** @15m, ret **−17,2%**, y solo
   el **17%** de sus 209 señales es operable. Es el 39% del volumen de la flota. En el
   subyacente era mediocre; en la opción es una máquina de quemar prima.
3. **`ESTRUCTURAL magnet` — asciende de "prometedor" a lo único serio.** 59/67/**85%** y
   **+74% de retorno medio a +60m**, TP+100% en el 46%, y **el 89% de sus señales pasa el
   gate** (el único detector cuyo contrato es casi siempre líquido, porque apunta a strikes
   con muro de OI). Pierde 11pp respecto al subyacente pero es el único que sobrevive al
   spread **y** al presupuesto. n=27 → prometedor, no probado.
4. **`BB BAND-WALK` sube y `BB REBOTE` baja: dentro de Bollinger, la continuación le gana al
   elástico en el vehículo.** BAND-WALK es la única familia BB que no pierde nada al pasar a
   la opción (50→48%) y gate-OK da 64% @15m. La doctrina del elástico "chico y seguro"
   funciona en el gráfico y no funciona comprando prima.
5. **`CUSUM TERREMOTO` y `FLOW SPIKE CALLS` cambian de HORIZONTE, no de signo.** A +15m
   parecen rotos (38%); a +30/+60m con gate son 100% (n=4) y 55–67%. Un movimiento grande
   necesita tiempo para pagar el spread. Medirlos a 15 minutos era el error.

### Confirmado, y peor de lo que decía el subyacente

- **CELDA ESTRELLA `BB REBOTE ⭐`**: 21% → **16% @15m, 7% @60m**, ret **−63,1%**, mediana
  −89,3%. **De las 19, solo UNA llegó a tocar +50% en toda la hora siguiente (MFE +98%) y
  ninguna a +100%; 16 de 19 nunca estuvieron verdes.** Con
  gate: 3 señales, **0% en los tres horizontes, ret −96,5%**. La señal con voz garantizada es
  la única del sistema cuyo Wilson superior queda muy por debajo de 50 en el vehículo.
- **`BB APERTURA FUERA DE BANDA`**: 17% @15m, 9% @60m, ret −63,6% — y **0 de 12 pasa el
  gate**. Inoperable y perdedora a la vez.
- **Ballenas (ley 11)**: BALLENA PUTS 20/20/**14%** (ret −33,9%), BALLENA CALLS 22/22/**12%**,
  BALLENA CRECE 33/38/38% (ret −17,3%). Y solo el 13–31% de ellas apunta a un contrato
  comprable. La táctica espada-ballena, tal como la ejecuta hoy la flota, **no sobrevivió al
  vehículo** este día. n=37 en total → bandera roja, no sentencia.

---

## 5. LOS GATES DEL PROPIO SISTEMA — el veredicto del subyacente se INVIERTE

El doc del subyacente concluyó que el `bb_context` estaba al revés (las silenciadas ganaban
+11pp) y recomendó quitar el "VETO apertura". **En el vehículo esa conclusión no se sostiene.**

| gate | n | WR@15m | Wilson95 | ret medio | % que pasa optgate |
|---|---:|---:|---|---:|---:|
| SONÓ | 308 | 33% | [28,39] | −11,3% | 34% |
| MUTED p<55 | 131 | 31% | [23,39] | −17,9% | 22% |
| **VETO medido** | 57 | **18%** | [10,29] | −21,4% | 25% |
| MUTED capitán | 6 | 67% | [30,90] | +52,6% | 17% |
| VETADO band-walk | 5 | 0% | [0,43] | −14,6% | 60% |

BB REBOTE apples-to-apples (mismo detector, mismo mix largo/corto):

| grupo | +15m | +30m | +60m |
|---|---|---|---|
| SONÓ normal | 26% [19,34] · −15,4% | 27% [20,35] · −18,0% | 30% [22,39] · −3,2% |
| SONÓ ⭐ estrella | 16% [6,38] · −43,8% | 11% [3,33] · −52,7% | 7% [1,31] · −63,1% |
| **VETO medido** | **18% [10,29]** · −21,4% | 24% [15,38] · −19,6% | 21% [12,36] · −14,1% |

En el subyacente el VETO parecía **+11pp mejor** que lo que sonaba; en la opción es **−8pp
peor** a 15m y peor también a 60m. **El veto `bb_context` estaba haciendo su trabajo; lo que
engañaba era el vehículo de medición.** Ninguna de las dos diferencias alcanza el 95%
(intervalos solapados en ambos casos), así que la acción correcta sigue siendo *instrumentar
y medir 3–5 días* — pero la recomendación §4.3 del doc anterior ("quitar el VETO apertura")
**queda anulada hasta nueva evidencia**. Lo único que se mantiene intacto es degradar la
CELDA ESTRELLA: es peor en los dos vehículos, en los tres horizontes.

---

## 6. HORA DEL DÍA — el vuelco más grande del informe

| hora ET | n | WR@15m (todas) | ret medio | n gate-OK | WR@15m gate-OK | ret gate-OK | % pasa gate | spread mediano |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 09:00 | 87 | **43% [33,53]** | −1,5% | 33 | **48% [33,65]** | **+16,4%** | 38% | 7,0% |
| 10:00 | 100 | 34% [25,44] | −10,8% | 37 | 49% [33,64] | +2,0% | 37% | 6,6% |
| 11:00 | 69 | 20% [12,31] | −18,3% | 25 | 24% [11,43] | −8,4% | 36% | 6,8% |
| 12:00 | 61 | 28% [18,40] | −14,5% | 24 | 42% [24,61] | −0,1% | 40% | 7,2% |
| 13:00 | 26 | 42% [26,61] | +0,2% | 12 | 33% | −4,3% | 37% | 7,2% |
| 14:00 | 87 | 21% [14,30] | −27,3% | 15 | 33% | −7,5% | **17%** | 10,4% |
| 15:00 | 77 | **32% [23,44]** | **−13,9%** | 12 | **25% [9,53]** | **−17,5%** | **13%** | **14,5%** |

**El subyacente dijo que 15:00–15:59 fue el MEJOR bloque del día (66% [56,74], n=105) y que
había que reforzarlo. En el vehículo es el PEOR o casi**: 32% con ret −13,9%, gate-OK 25% con
−17,5%, y **solo el 13% de las señales de esa hora apunta a un contrato comprable** (spread
mediano 14,5%, el doble que por la mañana). Razón mecánica: son 0DTE ATM a menos de una hora
del vencimiento — theta vertical y el market maker abre el cruce. **El movimiento del
subyacente era real; el dinero no estaba ahí.** La regla 7 de la doctrina ("última hora solo
gestión") gana la discusión contra el backtest de subyacente.

Simétricamente, **09:00–09:59, mediocre en el subyacente (51%), es el mejor bloque en la
opción** (48% gate-OK, +16,4% de retorno medio): spread estrecho, prima barata, tiempo por
delante. Y **11:00 y 14:00 se confirman como picadora en los dos vehículos** (20% y 21%).

---

## 7. SENSIBILIDAD: ¿y si en vez de 0DTE se comprara el semanal?

Repitiendo todo con el **segundo vencimiento** (20260727 / 20260731) en lugar del 0DTE:

| bloque | 0DTE @15m (todas) | Semanal @15m (todas) | 0DTE gate-OK | Semanal gate-OK |
|---|---|---|---|---|
| TOTAL | 31% · **−13,4%** | 27% · **−5,5%** | 39% · +0,2% | 38% · −1,4% |
| 15:00 | 32% · −13,9% | 30% · **−2,9%** | 25% · −17,5% | 44% · −2,0% |
| 10:00 | 34% · −10,8% | 19% · −9,3% | 49% · +2,0% | 57% · +3,0% |

El semanal **no mejora el WR** (27% vs 31%) pero **corta la sangría a la mitad** (−5,5% vs
−13,4%) y elimina el desastre de la última hora. Es la traducción numérica de la picardía
"jaula 0DTE → liberación semanal" que ya está en memoria: menos gamma, menos theta, menos
convexidad. **Conclusión: si una señal llega después de las 14:00, el 0DTE es el vehículo
equivocado.**

---

## 8. AMBIGUAS (`GIRO A CALLS/PUTS`, 70 señales) — supuesto fade de doctrina

| familia | +15m | +30m |
|---|---|---|
| GIRO A CALLS (→ PUT) | n=45 · 40% [27,55] · −12,0% | n=44 · 34% [22,49] · −14,6% |
| GIRO A PUTS (→ CALL) | n=22 · **14% [5,33]** · **−39,1%** | n=22 · 23% [10,43] · −39,3% |

En el subyacente GIRO A CALLS daba 65% y GIRO A PUTS 32%. En la opción ambas pierden, y
**GIRO A PUTS es catastrófica** (14%, −39%). Sigue sin poder concluirse nada porque el
mensaje no declara tesis: **la acción sigue siendo que el emisor escriba la dirección**.

---

## 9. QUÉ HACER (por orden de fuerza de la evidencia)

1. **Poner el gate ANTES de la voz, no después.** Hoy la flota canta 535 señales
   direccionales y solo 134 (25%) son ejecutables con opciones bajo su propia doctrina. Toda
   señal debe resolver su contrato ATM y callarse (o cantar "solo acciones/ETF") si
   spread>5%, OI<500 o prima>$200. Esto es lo más rentable del informe: separa 27%/−19,6% de
   39%/+0,2% sin tocar un solo detector.
2. **Apagar la voz de opciones en 12 símbolos**: AMD, ASML, AVGO, DRAM, LRCX, QCOM, SKHY, SMH,
   STX, TSM, TXN, WDC — 206 señales/día, **0%** de contratos operables. Ahí solo acciones o
   ETF apalancado.
3. **Degradar la CELDA ESTRELLA `BB REBOTE ⭐`** — confirmado en los dos vehículos: 16%/7%,
   ret −63%, 1 de 19 tocó +50%. Es la única conclusión que el cambio de vehículo
   refuerza en vez de invertir.
4. **Revertir la recomendación de quitar el `bb_context`**: en la opción el VETO era correcto
   (18% las silenciadas vs 26% las que sonaron). Instrumentar y medir 3–5 días antes de tocar.
5. **Bajar `FLOW SPIKE PUTS` de "candidato a edge" a vigilado-negativo** (−17%/trade con
   bracket, 10% WR @60m) y **subir `ESTRUCTURAL magnet`** al primer puesto (85% @60m, +74%,
   78% operable).
6. **Cambiar el horizonte de medición de 15 a 30–60 min para flow/cusum/magnet**: a 15
   minutos el spread aún no está amortizado y el detector parece roto cuando no lo está.
7. **Después de las 14:00, prohibido 0DTE comprado** (§6, §7): 13% de contratos operables,
   spread 14,5%, ret −17,5%. Si hay señal, semanal o nada.
8. **TP: dejar de vender a +30%.** En la opción el bracket +30/−30 es negativo hasta con gate
   (−1,3%); +100/−30 es el único claramente positivo (+12,7%). La prima comprada se paga con
   la cola, no con el scalp.
9. **Arreglar el emisor**: cachear cadena de NFLX/GLD/EWY/XLK (81 señales/día invisibles),
   escribir la tesis en `GIRO A *` y el `symbol` correcto en `MANADA A *`.

*Todo esto es UN viernes, con 5-minutos de granularidad, sin comisiones y con fills al
ask/bid publicados. Ningún n de este informe supera 209 y casi todas las celdas por familia
están por debajo de 30. **Nada de aquí justifica por sí solo comprar una opción mañana**; lo
que sí justifica es no comprarla cuando el contrato no pasa el gate — eso está medido dos
veces y en la misma dirección.*
