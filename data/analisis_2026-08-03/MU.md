# MU — plan 2026-08-03

**Corte de datos: 07:20 ET, lunes 3-ago-2026, premarket.** SEÑAL-SOLAMENTE: nada de aquí dispara una orden.
IBKR **no se ha tocado** (prohibido esta semana): cero conexiones a 4001/4002/7496/7497.

---

## CABECERA — lo que hay que saber en 20 segundos

| | |
|---|---|
| **Spot** | **796,00 USD** — Finnhub WS (trade impreso, **TIEMPO REAL**, edad 19 s), 07:16:03 ET |
| **Cierre viernes** | **823,03** (yfinance EOD y UW `max-pain.close` coinciden; nuestras barras 1m dicen 824,25) |
| **Premarket** | **−3,28%** · rango 04:00→06:59: **835,13 / 792,00** · volumen **SIN DATO** (columna vol = 0 en las 1.605 barras) |
| **Régimen gamma** | **NEGATIVO** — net GEX **−57,8 M$/1%** (2 venc cercanos, repreciado al spot de ahora) · **−255,4 M$/1%** todos los venc |
| **Veredicto (1 línea)** | **CAJA, no dirección.** MU perdió el viernes su flip de gamma y ha abierto hueco por debajo: dealer corto de gamma → amplificación en los dos sentidos. Sin edge direccional medible desde la apertura. |
| **Probabilidad** | **Cierre a cierre: 64,6% rojo** (MEDIDO, n=127 / n_eff=89) — **pero el hueco ya se pagó**. **Desde la apertura: NO SÉ** (4 celdas publicables de 47,9% a 60,4%, todas contienen la base 51,4%) |
| **Los 3 niveles** | **800,00** put wall / trampilla (+0,50%) · **824,77** GAMMA FLIP = techo de la caja (+3,62%) · **750,00** imán + borde inferior del expected move (−5,78%) |
| **Vehículo** | **OPCIONES VETADAS** (spread NO VERIFICABLE: bid/ask = 0 en el 100% de las filas; e IV 0DTE al 205%). Con presupuesto de 200 $ **MU no es operable hoy**: 1 acción = 796 $ |

---

## 1. FOTO

### 1.1 Precio y fuentes (cada número con su latencia)

| Dato | Valor | Fuente | Latencia | Hora |
|---|---|---|---|---|
| Spot | **796,00** | Finnhub WS (`data/rt_last_MU.txt`) | **TIEMPO REAL** (trade impreso) | 07:16:03 ET |
| Cierre viernes 31-jul | **823,03** | yfinance EOD + UW `/max-pain.close` (dos fuentes independientes) | EOD | 16:00 ET viernes |
| Apertura viernes | 919,65 | UW `/max-pain.open`, validado con `underlying_price` de las flow-alerts | EOD | — |
| Barras 1m | ver §1.2 | `data/bars_mu_ibkr.txt`, escritas por `provider_bridge.py --daemon` (`data/market_source.txt` = **intrinio**) | **RETRASO MEDIDO 15-17 min** (última barra 06:59, reloj 07:16 → 1.043 s) | 06:59 ET |
| Cadena de opciones | 1.780 contratos, 11 venc | Polygon `/v3/snapshot/options` (`raw/chain_mu.json`) | **15 min**; OI = **cierre del VIERNES, congelado** | fetch 06:50 ET |
| Flujo UW | viernes al cierre | Unusual Whales REST | **58,9 h** — UW **no publica en premarket** (medido) | 19:59 ET viernes |

> **DIVERGENCIA MEDIDA entre las dos fuentes de precio, y no la escondo.** Las barras (Intrinio, retraso 17 min) marcan 804,74 a las 06:59; Finnhub (tiempo real) marca 795,18 a las 07:07 y 796,00 a las 07:16. El tramo 06:59→07:07 es una caída de −1,2% que las barras **todavía no muestran**. Todo lo que necesita el precio de AHORA usa Finnhub; todo lo que necesita una serie usa las barras y va etiquetado con su retraso.

### 1.2 Bollinger, %B y RSI — con la advertencia que toca

BB(20,2) y RSI(14) sobre las barras 1m de `provider_bridge` (retraso 15-17 min), agregadas a 5m y 15m.

| TF | n barras | BB inferior | BB media | BB superior | **%B** | **RSI(14)** | Ancho |
|---|---|---|---|---|---|---|---|
| 1m | 1.605 | 799,19 | 802,07 | 804,94 | **0,402** | **50,2** | 0,72% |
| 5m | 332 | 792,40 | 805,59 | 818,77 | **0,345** | **42,9** | 3,27% |
| 15m | 115 | 797,94 | 812,11 | 826,27 | **0,126** | **38,6** | 3,49% |
| **Diario** | 10.623 | **775,15** | **911,69** | 1.048,22 | **0,076** (con spot 796) | **43,6** | 30,0% |

**Últimas 8 velas 1m (la "fuerza", 06:52→06:59 ET, retraso 17 min):**

```
06:52  O 801,70  H 801,83  L 800,53  C 801,80
06:53  O 801,04  H 802,10  L 801,04  C 801,92
06:54  O 803,00  H 803,80  L 802,88  C 803,30
06:55  O 803,73  H 804,93  L 803,73  C 804,56
06:56  O 804,50  H 805,71  L 804,39  C 805,51
06:57  O 805,50  H 806,20  L 805,24  C 805,99
06:58  O 805,92  H 805,92  L 805,92  C 805,92
06:59  O 804,84  H 805,42  L 804,54  C 804,74
```

**Lectura honesta de la fuerza:** esas 8 velas son un rebote de +0,5% desde 801 — pero son de hace 17 minutos y Finnhub ya las ha desmentido (796,00). **La fuerza real de ahora: SIN DATO fiable hasta que las barras alcancen.** Lo único firme: entre las 06:00 y las 06:20 hubo un tramo de 812,90 → 792,00 (−2,6% en 20 min) y desde ahí el precio lleva dos horas oscilando en 792-806.

**Caveats obligatorios:** (1) BB sobre barras de PREMARKET (cinta fina, huecos) no es lo mismo que BB de sesión; el BB(20,2) de RTH no existirá hasta ~09:50. (2) El campo volumen vale 0 en **1.605 de 1.605** barras → **volumen premarket SIN DATO**, no puedo validar ningún nivel con volumen. (3) Ninguna banda está **reventada**: %B 1m 0,40 y 15m 0,13 son "bajo", no "fuera". **Hoy todavía NO hay setup elástico** en el sentido de la casa (que exige perforación + re-entrada).

**Contexto diario (yfinance, cierre del viernes):**

| | |
|---|---|
| SMA20 / SMA50 / SMA200 | 911,69 / 964,85 / 518,10 → precio **−12,7%** bajo la SMA20 y **+53,6%** sobre la SMA200 |
| ATR(14) diario | **72,28 USD = 8,78%** del precio → **un día de ±8% es NORMAL en MU ahora** |
| Máx/mín 52 s. | 1.255,00 / 103,38 → MU está **−36,6%** desde su máximo, tras multiplicar por 12 en un año |
| Últimas 4 sesiones | 28-jul **−8,85%** · 29-jul **−9,94%** (open→close **−11,28%**) · 30-jul **+18,36%** · 31-jul **−5,90%** (open→close **−10,51%**) |

El viernes MU abrió con hueco de **+5,14%** (919,65) y cerró en 823,03: **open→close −10,51%**, con mínimo en 818,00. Eso es un **día de agotamiento / vela de reversión** en el techo de una parábola, no una corrección ordenada.

---

## 2. CADENA DE OPCIONES EN PROFUNDIDAD

Fuente: Polygon `/v3/snapshot/options`, 1.780 contratos, 11 vencimientos (03-ago → 18-sep). **Griegas e IV MEDIDAS por Polygon** (no reconstruidas). **OI = cierre del viernes y CONGELADO** — no existe OI intradía (medido, `oi-change` de UW solo da cierre vs cierre). **Bid/ask NO EXISTEN**: 0 en el 100% de las filas (Polygon Starter no sirve `last_quote`).

### 2.1 Vencimientos relevantes

| Venc | DTE | OI calls | OI puts | P/C OI | IV ATM | Max pain | Expected move 1σ |
|---|---|---|---|---|---|---|---|
| **2026-08-03 (0DTE)** | hoy 16:00 | 27.510 | 46.195 | **1,68** | **2,056 (205,6%)** | 835 (UW) / 800 (banda ±22%) / 845 (banda snapshot) | **±5,89% = ±46,9 → [749,1 · 842,9]** |
| 2026-08-05 | 2 d | 9.142 | 11.830 | 1,29 | 1,436 | 850 / 870 (UW) | ±11,5% |
| 2026-08-07 | 4 d | 29.639 | 60.760 | **2,05** | 1,353 | 890 (UW) | ±14,8% |
| 2026-08-21 (mensual) | 18 d | 34.574 | 84.798 | **2,45** | 1,024 | 900 (UW) | ±23,0% |
| **TODOS (11 venc)** | — | **156.318** | **299.662** | **1,92** | — | — | — |

**Expected move: APROXIMADO, no es el straddle.** `S·IV_atm·√T` con IV medida por Polygon (delayed 15 min). La skill `expected-move-envelope` pide el **straddle capturado antes de las 15:55** y hoy **no se puede**: bid/ask no existen en este plan. Referencia de cota: el straddle 805 del 0DTE **cerró el viernes** en 36,16 + 14,69 = **50,85 USD = 6,34%** — consistente con el ±5,89% calculado.

**Tres max pain distintos y digo por qué:** 835 es el de UW sobre la cadena completa; 800 sale de la banda ±22% del informe hermano; 845 de la banda del snapshot. Los tres están **POR ENCIMA** del spot (+4,9% / +0,5% / +6,2%). Con el precio 5% por debajo y gamma negativa, **el max pain hoy NO manda**: no es imán a esa distancia.

### 2.2 OI por strike alrededor del spot — 0DTE (2026-08-03)

| Strike | dist | call OI | put OI | GEX (M$/1%) | qué es |
|---|---|---|---|---|---|
| 825,00 | +3,64% | 286 | 359 | −1,67 | |
| 820,00 | +3,02% | 321 | 745 | −4,79 | |
| 815,00 | +2,39% | 189 | 283 | −1,61 | |
| 810,00 | +1,76% | 148 | 438 | −2,86 | |
| 805,00 | +1,13% | 102 | 280 | −1,72 | ATM±1 (ratio pin 0,46× → **NO hay pin**) |
| **800,00** | **+0,50%** | **595** | **1.706** | **−10,00** | **PUT WALL / trampilla · nodo de gamma más negativo** |
| 795,00 | −0,13% | 128 | 700 | −4,11 | |
| **790,00** | **−0,75%** | 247 | **1.219** | **−6,60** | **POC + abs_wall (2 venc)** |
| 785,00 | −1,38% | 95 | 212 | −0,91 | |
| 780,00 | −2,01% | 224 | 617 | −2,55 | |
| 775,00 | −2,64% | 103 | 571 | −2,36 | ≈ banda inferior BB diaria (775,15) |
| 770,00 | −3,27% | 154 | 450 | −1,51 | |
| 765,00 | −3,89% | 68 | 305 | −0,99 | |

**Top OI 0DTE:** calls 900 (3.647) · 960 (2.440) · 950 (1.959) · 835 (1.940) · 850 (1.767). Puts 700 (4.994) · 747,5 (1.981) · 720 (1.935) · 710 (1.780) · 800 (1.706).

### 2.3 Los muros de verdad — OI agregado de los 11 vencimientos

| Strike | dist | call OI | put OI | **total** | GEX (M$/1%) | tipo |
|---|---|---|---|---|---|---|
| **800,00** | **+0,50%** | 10.278 | **32.618** | **42.896** | **−59,64** | **el muro. Puts 3,2:1** |
| 900,00 | +13,07% | **21.717** | 10.659 | 32.376 | +17,23 | call wall |
| **700,00** | **−12,06%** | 4.502 | **25.732** | **30.234** | −23,23 | imán inferior mayor |
| 850,00 | +6,78% | 7.398 | 10.951 | 18.349 | −5,37 | imán superior 1º |
| **750,00** | **−5,78%** | 2.715 | **15.577** | **18.292** | **−21,96** | **imán inferior 1º = borde EM** |
| 650,00 | −18,34% | 1.783 | 15.502 | 17.285 | −9,61 | |
| 950,00 | +19,35% | 11.943 | 5.037 | 16.980 | +7,89 | |
| 830,00 | +4,27% | 2.769 | 6.608 | 9.377 | −5,74 | |
| 820,00 | +3,02% | 3.142 | 5.724 | 8.866 | −9,83 | |
| 780,00 | −2,01% | 2.724 | 5.662 | 8.386 | −7,50 | |

### 2.4 ¿Cuánto OI hay arriba y cuánto abajo del spot?

| Ámbito | OI por ENCIMA | OI por DEBAJO |
|---|---|---|
| 0DTE (03-ago) | 37.826 (**51,3%**) | 35.879 (48,7%) |
| 05-ago | 13.412 (64,0%) | 7.560 (36,0%) |
| 07-ago | 56.365 (62,4%) | 34.034 (37,6%) |
| 21-ago | 68.770 (57,6%) | 50.602 (42,4%) |
| **Todos (11 venc)** | **259.275 (56,9%)** | **196.705 (43,1%)** |

El 0DTE está **repartido casi 50/50** — otra pieza de "caja, no dirección". El OI de vencimientos posteriores sí pesa arriba (57-64%), pero eso es el legado del rally, no una predicción de hoy.

### 2.5 El gamma flip — y el cambio de régimen que ocurrió el viernes

Repreciando la gamma de cada contrato por Black-Scholes con la **IV medida de Polygon** (mismo método que `gex_core`, verificado contra el informe hermano: mi flip da 824,6 y `mapa_opciones.json` da **824,77** — dos cálculos independientes que coinciden):

| Spot | net GEX 0803+0805 | net GEX todos venc |
|---|---|---|
| 700 | **−110,2 M$** | −283,2 M$ |
| 750 | −108,9 M$ | −305,4 M$ |
| **795,81 (ahora)** | **−57,8 M$** | **−255,4 M$** |
| 800 | −51,1 M$ | −247,8 M$ |
| **823,03 (cierre viernes)** | **−4,0 M$ ≈ CERO** | −192,2 M$ |
| **824,77** | **0 → FLIP** | — |
| 850 | +62,2 M$ | −109,8 M$ |
| 900 | +118,6 M$ | −9,3 M$ |
| ~908 | — | **0 → FLIP** |

> **El hallazgo estructural del día: MU cerró el viernes EXACTAMENTE encima de su gamma flip (823,03 vs 824,77) y ha abierto hueco POR DEBAJO.** Ese cruce es el cambio de régimen: por encima de 824,77 los dealers están largos de gamma (amortiguan, pinean); por debajo están **cortos de gamma** (venden en las caídas y compran en los rebotes = **amplifican los dos sentidos**). Y **el libro se hace más negativo cuanto más baja**: −57,8 M$ aquí, −108,9 M$ en 750, −110,2 M$ en 700. **No hay colchón de gamma por abajo.**
>
> Esto además **reconcilia** la aparente contradicción con Unusual Whales, que publica `net_gamma` **+39.090 (POSITIVO)** para el viernes: UW lo calcula al spot del **viernes** (823, justo en el flip); nosotros al spot de **hoy** (796, ya debajo). **Ninguno de los dos miente — es que el régimen cambió al cruzar el nivel.**

Régimen declarado por el informe hermano (`gex_core`, 2 venc): **NEGATIVE**, bias **PUT**, `call_wall` 900 (pin), `put_wall` 800 (**trampilla**), `abs_wall`/`poc` **790** (trampilla), `pin_risk_score` 30,3, `fortress_pin` **false**, `net_dex` −57,1 M$ (**mm_vende**).

### 2.6 Skew — el dato que va CONTRA la lectura bajista fácil

Risk reversal 25-delta (IV call25 − IV put25). **Positivo = las calls están MÁS caras que las puts.**

| Venc | call 25Δ | put 25Δ | **RR** |
|---|---|---|---|
| 03-ago (0DTE) | K 855 · IV 2,309 | K 775 · IV 1,431 | **+0,878** |
| 05-ago | K 885 · IV 1,571 | K 755 · IV 1,176 | **+0,394** |
| 07-ago | K 905 · IV 1,467 | K 742,5 · IV 1,168 | **+0,299** |
| 21-ago | K 975 · IV 1,069 | K 710 · IV 0,936 | **+0,132** |
| 18-sep | K 970 · IV 0,961 | K 690 · IV 0,862 | **+0,098** |

**Skew de CALL en los cinco vencimientos.** Lo normal en una acción que se derrumba es skew de PUT (las puts se encarecen). Aquí pasa lo contrario: el mercado sigue pagando **más** por la cola ALCISTA que por la bajista, y el efecto es mayor cuanto más corto el plazo. Traducción operativa: **las puts están relativamente BARATAS** y **lo que el mercado teme de verdad es quedarse fuera de un squeeze**. Es la firma de una manía que aún no ha capitulado. Va explícitamente en contra de cargar corto aquí.

---

## 3. FLUJO — Unusual Whales

> **ADVERTENCIA que vale para toda esta sección: UW NO PUBLICA EN PREMARKET.** Medido a las 06:51 ET: el print más reciente de toda la API (incluido `/darkpool/recent` global) es del viernes 23:59:50Z. **Edad 58,9 h.** Esto es **POSICIONAMIENTO DE PARTIDA**, no el flujo de hoy. En el mismo instante Finnhub servía ticks de 9 a 1.625 s.

### 3.1 Premium neto firmado (cinta del viernes, 390 minutos)

| | USD |
|---|---|
| net call premium | **−84.521.522** |
| net put premium | **+32.544.308** |
| **signed premium** (= net_call − net_put, el gotcha de la casa) | **−117.065.830** |
| net delta | **−754.826** |
| últimos 30 min | **−13.018.193** (siguió bajista hasta la campana) |
| net call volume / net put volume | −53.136 / +22.977 |

**Tono del viernes: BAJISTA y sostenido hasta el cierre.**

### 3.2 Ballenas (200 flow-alerts, 09:45→15:59 ET viernes)

| | USD |
|---|---|
| premium total calls | 46.655.931 |
| premium total puts | 23.870.656 |
| **ask − bid en CALLS** | **−3.118.899** → el agresor **VENDIÓ** calls |
| **ask − bid en PUTS** | **+1.090.407** → el agresor **COMPRÓ** puts |

Las 4 alertas que importan:

| Hora ET | Tipo | Strike | Venc | Premium | Lado | Vol/OI | Lectura |
|---|---|---|---|---|---|---|---|
| 10:44 | CALL | 740 | 18-sep | **4,32 M$** | **BID (vende)** | 266 / 1.746 | deshace una call ITM con spot en 843,4 — toma de beneficios |
| 11:31 | CALL | 830 | 31-jul | 1,06 M$ | BID (vende) | 5.497 / 2.611 → **APERTURA** | vende calls 0DTE contra el rebote |
| **15:56** | CALL | 900 | 07-ago | **1,26 M$** | **ASK (compra)** | 4.869 / 4.055 → **APERTURA** | **cola alcista comprada en la campana** |
| **15:57** | PUT | 792,5 | 07-ago | **1,05 M$** | **ASK (compra)** | 415 / **11** → **APERTURA** | **cola bajista comprada en la campana, sweep** |

**Táctica espada-ballena de la casa aplicada:** el flujo dominante del viernes fue **venta de calls + compra de puts** → 🐋 sesgo de BALLENA-PUTS = **piso local cerca**, que en la doctrina se opera comprando EN el fondo y soltando en el rebote corto, no persiguiendo abajo. **Pero** en los últimos 4 minutos compraron **las dos colas** (900C y 792,5P, ambas aperturas frescas). Eso **no es una apuesta direccional: es una apuesta a AMPLITUD**. Coincide exactamente con lo que dice la medición histórica (§6) y con el régimen de gamma negativa (§2.5).

### 3.3 oi-change (cierre viernes vs jueves — **no existe OI intradía**)

| Contrato | Volumen | ΔOI | ratio | Veredicto Kochuba | Premium | Precio medio |
|---|---|---|---|---|---|---|
| **MU 07-ago PUT 500** | 10.957 | **+8.012** | 0,731 | **APERTURA** | 551.843 $ | 0,50 $ |
| MU 31-jul PUT 800 | 20.645 | +3.673 | 0,178 | **CHURN** | 18,30 M$ | 8,86 $ |
| MU 07-ago CALL 900 | 8.320 | +2.569 | 0,309 | MIXTO | 24,20 M$ | 29,09 $ |
| MU 31-jul PUT 850 | 16.849 | +2.137 | 0,127 | CHURN | 37,03 M$ | 21,98 $ |
| **MU 21-ago PUT 720** | 2.687 | **+1.892** | 0,704 | **APERTURA** | 7,79 M$ | 28,98 $ |

**Se abrieron las DOS colas con dinero de verdad:** 9.237 puts de strike 500 a 4 días (seguro de catástrofe a −37%) y 24,2 M$ en calls 900. Otra vez: **amplitud, no dirección**.

### 3.4 Darkpool — se reporta, **NO se usa como señal**

39 prints ≥10 M$ en 3 sesiones; tras descartar los `sale_cond_codes` sucios (`prior_reference_price` 13, `average_price_trade` 3) quedan **23 limpios**. Niveles limpios por volumen: **926,70** (64.679 acc. / 59,94 M$, viernes 09:33 ET) · 849,34 · 902,01 · 850,98 · 847,69. **El 100% del volumen limpio está POR ENCIMA del spot de hoy.**

> **Etiqueta obligatoria: esto NO es una señal.** El dark-pool está en la kill-list de la casa (`anti-overfit-killlist` #3 `dpi-lite`): *"la réplica bayesiana independiente pone el edge de DIX en ~0"*. Se cita como **descriptivo** — dónde se cruzó papel grande el viernes — y punto. Nadie construye un nivel operable con esto.

### 3.5 JERARQUÍA DE CAPITANES — el veto explícito

Premarket, mismo instante (barras con retraso 17 min salvo donde se indica TIEMPO REAL):

| Símbolo | Cierre viernes | Premarket | Δ | fuente |
|---|---|---|---|---|
| **SPY** (capitán mercado) | 748,27 | 751,12 | **+0,38%** | Finnhub 06:46 (edad 30 min) |
| **QQQ** (capitán mercado) | 690,57 | 690,15 | **−0,06%** | **Finnhub TIEMPO REAL 07:16** |
| **SMH** (capitán semis) | 542,41 | 536,99 | **−1,00%** | barras 06:57 (**sin `rt_last_SMH.txt`** — hueco conocido) |
| AVGO | 389,54 | 389,72 | +0,05% | barras |
| NVDA | 201,44 | 199,30 | **−1,06%** | Finnhub 07:08 |
| INTC | 90,21 | 88,69 | −1,69% | Finnhub 07:11 |
| AMD | 477,58 | 473,86 | −0,78% | barras |
| TSM | 404,34 | 401,21 | −0,77% | barras |
| LRCX | 293,31 | 289,71 | −1,23% | barras |
| WDC | 544,45 | 536,54 | −1,45% | barras |
| STX | 858,05 | 842,65 | −1,79% | barras |
| **SNDK** | 1.228,05 | 1.193,78 | **−2,79%** | barras |
| **MU** | 823,03 | **796,00** | **−3,28%** | **Finnhub TIEMPO REAL 07:16** |

**Dos conclusiones, y son opuestas entre sí:**

1. **El capitán de MERCADO NO acompaña.** QQQ está plano (−0,06%) y **con un PIN medido en 690** (OI ATM±1 = 9.214 = 3,46× la mediana de la banda ±3%, `mapa_opciones.md §6`); SPY está **verde**. Por la doctrina de la casa (*conflicto capitán vs tropa → gana el capitán, la señal del nombre queda prácticamente ANULADA*): **cualquier tesis bajista de MU que se apoye en "el mercado se cae" está ANULADA hoy. El mercado no se está cayendo.**
2. **El sub-complejo de MEMORIA sí acompaña, y ordenado por pureza:** SNDK −2,79% · MU −3,28% · STX −1,79% · WDC −1,45% · LRCX −1,23% · SMH −1,00%, frente a AVGO +0,05% y QQQ ≈0%. **Cuanto más memoria, más rojo.** Eso es exactamente la firma del canal coreano (§4) y es lo único que sostiene la debilidad de MU.

**Traducción operativa: la señal de hoy en MU es de SECTOR-MEMORIA, no de mercado. Vive o muere con SMH.** Si SMH recupera su cierre del viernes, MU se queda sin quien le empuje.

---

## 4. CONTAGIO COREANO — cuánto de esto es Corea, medido

**Exposición estructural: la más alta de toda la flota.** MU es uno de los **tres** fabricantes de DRAM del mundo junto a Samsung y SK Hynix. Cuando Samsung cae −8,76% y SK Hynix −8,79% en la misma sesión, eso **es** el mercado de memoria repreciándose. Esto es cualitativo y así queda etiquetado: **no es una medición**.

**Lo que SÍ está medido** (yfinance EOD, 7.068 sesiones conjuntas MU × KOSPI, 1996-12-12 → 2026-07-31, unión por fecha de calendario **sin desplazamiento** — Corea cierra 7-8 h antes de la apertura US, no hay look-ahead):

| Correlación | Valor | n |
|---|---|---|
| corr(KOSPI[D], MU[D]) — muestra completa | **0,135** | 7.068 |
| corr(KOSPI[D], MU[D]) — desde 2020 | **0,210** | 1.560 |
| **corr(KOSPI[D], MU[D]) — 2026** | **0,286** | 138 |
| corr(NDX[D−1], KOSPI[D]) — control de cordura | **0,310** | 7.068 |

**Corea explica ~8,2% de la varianza diaria de MU en 2026 (R² = 0,286²).** Real, medible, y **pequeño**. Y el control de cordura confirma lo del informe hermano: **Wall Street arrastra a Seúl (0,310) más del doble de lo que Seúl arrastra a Wall Street (0,130 sobre el NDX)**. La flecha causal apunta mayoritariamente al revés de lo que sugiere el titular.

**Qué es exactamente lo de hoy** (verificado por el orquestador, fuente Naver `delayTime` 0, cierre 02:30 ET):

- KOSPI índice **−4,88%** en 6.273 (prensa) / **−5,12%** en 6.257,45 (yfinance, provisional). **Uso el ÍNDICE.**
- **NO uso el KODEX 200 (−8,93%) para los buckets**: es nuestro proxy interno y hoy cayó **casi el doble** que el índice. Mezclarlos metería el caso de hoy en una celda que no le corresponde.
- **No es un crash sistémico americano**: es **toma de beneficios tras un rally RÉCORD de +17,91%** la sesión anterior, más un **catalizador regulatorio local** (Corea propone bajar el apalancamiento de los ETF de 2x a 1,5x/1x). Es un **desapalancamiento LOCAL**.
- **El NDX subió el viernes (+0,60%)** → hoy **no** es "Corea replicando a Wall Street". Es Corea moviéndose por lo suyo. Por eso la celda que aplica es la **AC ("no es eco")** en §6.

**Honestidad sobre el resto de la flota:** para AAPL, AMZN, META, GOOGL y NOK el canal coreano directo es **NULO** por doctrina de la casa. No lo fabrico para rellenar un párrafo. Con MU es al revés: es el nombre **más** expuesto que existe en la flota, y aun así el número medido es 8% de varianza. Las dos cosas son verdad a la vez.

---

## 5. ÁRBOL DE ESCENARIOS

```
                                MU — 796,00  (Finnhub, tiempo real, 07:16 ET)
                                cierre viernes 823,03   premarket −3,28%
                                RÉGIMEN: GAMMA NEGATIVA (−57,8 M$/1%) = CAJA, NO DIRECCIÓN
                                                 |
        +----------------------------------------+----------------------------------------+
        |                                                                                 |
     RAMA ARRIBA ↑                                                                   RAMA ABAJO ↓
     "el hueco ya se pagó"                                                    "la trampilla se abre"
     PRINT: 2 velas 1m CERRADAS > 800,00                                PRINT: 2 velas 1m CERRADAS < 790,00
     prob 48,6%  (= complemento de la base; SIN edge medible)           prob 51,4%  (= base; SIN edge medible)
        |                                                                                 |
        v                                                                                 v
  [800,00]  MURO PUT / TRAMPILLA   +0,50%                                  [792,00]  mínimo premarket    −0,50%
  42.896 OI totales (32.618 puts)                                           bisagra de las últimas 2 h
  nodo de gamma MÁS negativo (−59,6 M$)                                                   |
  1er toque desde abajo rebota ~70% (doctrina)                                            v
        |                                                                    [790,00]  POC + abs_wall  −0,75%
        v                                                                    trampilla · GEX −17,4 M$
  [810 - 820]  zona de OI medio (8.866 en 820)   +1,8/+3,0%                              |
        |                                                                                 v
        v                                                                    [775,15]  BANDA INFERIOR BB   −2,62%
  [823,03]  cierre del viernes  +3,40%                                       DIARIA (20,2) · %B = 0,076
        |                                                                                 |
        v                                                                                 v
  ###[824,77]  GAMMA FLIP  +3,62%  ###                                   ###[750,00]  IMÁN + BORDE EM  −5,78%###
  ### TECHO DE LA CAJA            ###                                    ### 18.292 OI (15.577 puts)     ###
  ### encima, dealer LARGO gamma  ###                                    ### confluencia MURO + VALLA:   ###
  ### = amortigua y pinea         ###                                    ### el mejor fade del día       ###
        |                                                                ### GEX −108,9 M$ = fondo del   ###
        v                                                                ### acelerador                  ###
  [835,00]  max pain UW  +4,90%                                                           |
  [842,90]  BORDE SUPERIOR EM 1σ  +5,89%                                                  v
        |                                                                    [749,10]  BORDE INFERIOR EM 1σ −5,89%
        v                                                                                 |
  [850,00]  IMÁN 18.349 OI  +6,78%                                                        v
     OBJETIVO RAMA ARRIBA                                                    [720,00]  8.841 OI    −9,55%
        |                                                                                 |
        v                                                                                 v
  [900,00]  CALL WALL 21.717 calls +13,07%                                   [700,00]  IMÁN MAYOR  −12,06%
     (fuera del EM: NO es objetivo de hoy)                                   30.234 OI (25.732 puts)
                                                                                OBJETIVO RAMA ABAJO
                                                                             (fuera del EM: solo día de pánico)

  INVALIDACIÓN RAMA ARRIBA:  2 velas 1m cerradas < 790,00  →  la trampilla manda
  INVALIDACIÓN RAMA ABAJO :  2 velas 1m cerradas > 800,00  →  el muro aguantó, objetivo pasa a 824,77

  LEYENDA:  ### = nivel decisivo   ·   MURO = OI que defiende   ·   IMÁN = OI que atrae
            FLIP = frontera de régimen gamma   ·   POC = punto de control   ·   EM = borde expected move
```

**Cómo se lee este árbol (doctrina de la casa, `print-o-nada-levels`):**

- **Solo se operan BOUNCE o RETEST_REJECT.** Nunca el TOUCH y **nunca la primera ruptura**.
- **PRINT = 2 velas 1m CERRADAS al otro lado del nivel.** "Está cerca" no existe. "Lo tocó" no existe.
- **Muros de OI:** 1er toque rebota ~70%, 3+ toques = exhausto, ruptura confirmada (retest-y-rechazo) **INVIERTE** el nivel (doctrina `oi-magnets-protocol`, **no medido**).
- **JAMÁS comprar a través de un muro intermedio.** Desde 796 comprar un objetivo en 850 significa atravesar el muro de 800 **y** el flip de 824,77: eso es premium muerto (precedente META 660C tras muro 650).
- **Gamma NEGATIVA:** el árbol dibuja una **caja**, no una flecha. Los dos bordes se visitan.

---

## 6. PROBABILIDAD DE SUBIR O BAJAR HOY

**Medición hecha para este informe.** Método idéntico al del estudio hermano `kospi_nasdaq_estudio.md` para que los números sean comparables: yfinance EOD, unión por fecha de calendario sin desplazamiento, **7.068 sesiones conjuntas MU × KOSPI (1996-12-12 → 2026-07-31)**, `n_eff` = **episodios independientes** (grupos separados por >5 sesiones), Wilson 95% **sobre `n_eff`**, umbral de publicación **`n_eff` ≥ 30**. La pregunta es de **cierre a cierre**, así que el retorno a horizonte **es** la etiqueta correcta y no aplica triple barrera (que es para señales intradía con stop).

**Bases:** P(MU día rojo) = **49,1%** [47,9 – 50,2] · P(MU open→close rojo) = **51,4%** [50,2 – 52,6] (Wilson sobre n=7.068).

**Condiciones de hoy:** NDX[D−1] = **+0,60%** (viernes) → grupo **AC "no es eco"** (NDX[D−1] > −1%). KOSPI[D] = **−4,88%** → bucket **≤ −3%** (con yfinance, −5,12%, rozaría el ≤ −5%; uso el bucket robusto). MU[D−1] = **−5,90%**. Hueco implícito de hoy: **−3,28%**.

### 6.1 Día completo (cierre de hoy vs cierre del viernes)

| Celda | n | n_eff | P(rojo) | Wilson 95% | media | mediana | z 1 cola | ¿publicable? |
|---|---|---|---|---|---|---|---|---|
| BASE | 7.068 | 7.068 | 49,1% | [47,9–50,2] | +0,11% | +0,00% | — | — |
| KOSPI ≤ −3% | 275 | 141 | 58,9% | [50,6–66,6] | −1,18% | −1,43% | — | sí |
| **AC & KOSPI ≤ −3%** ← **HOY** | **127** | **89** | **64,6%** | **[53,7–73,2]** | **−1,76%** | **−2,14%** | **+2,93** | **SÍ** |
| AC & KOSPI ≤ −3% & MU[D−1] ≤ −5% | 15 | 15 | 66,7% | [41,7–84,8] | −4,07% | −5,16% | +1,36 | **n INSUFICIENTE** |

**→ P(MU cierra hoy por debajo de 823,03) = 64,6%, MEDIDO, n=127 / n_eff=89, Wilson [53,7–73,2], z=+2,93.**

**PERO — y esto es la mitad de la respuesta: el hueco ya está hecho.** Ese 64,6% incluye un hueco de apertura que hoy **ya ha ocurrido**. Medido en esa misma celda: el hueco medio es −1,41% y la mediana −0,46%. **El hueco de hoy (−3,28%) es más profundo que el 81,1% de los casos de la celda** (y más profundo que el 92,6% de los casos "MU[D−1] ≤ −5%"). **La mayor parte de ese 64,6% ya está cobrada antes de que abra la bolsa.**

### 6.2 Desde la APERTURA — lo único operable a partir de las 09:45

| Celda | n | n_eff | P(open→close rojo) | Wilson 95% | mediana | z vs base 51,4% | ¿publicable? |
|---|---|---|---|---|---|---|---|
| AC & KOSPI ≤ −3% | 127 | 89 | 59,1% | [49,2–69,1] | −1,12% | **+1,44** (p≈0,075) | sí |
| hueco ≤ −3% & KOSPI ≤ −3% | 53 | 36 | 60,4% | [44,9–75,2] | −1,46% | +1,08 | sí |
| **MU[D−1] ≤ −5% & hueco ≤ −3%** | 37 | 33 | **54,1%** | [38,0–70,2] | −0,47% | +0,30 | sí |
| **MU[D−1] ≤ −5% & hueco ≤ −2%** ← la que mejor describe hoy | **71** | **59** | **47,9%** | [35,3–60,0] | **+0,21%** | **−0,54** | sí |

> **VEREDICTO DE PROBABILIDAD DIRECCIONAL INTRADÍA: NO SÉ, y lo digo así.**
> Las cuatro celdas publicables van de **47,9% a 60,4%** y **las cuatro contienen la base (51,4%)** dentro de su intervalo. Ninguna pasa un contraste de una cola. La celda que **mecánicamente** describe mejor la situación de hoy (MU ya se dejó ≥5% ayer **y** abre con hueco ≤ −2%) da **47,9%** con mediana **positiva**. **No hay edge direccional publicable desde la apertura. Publicar un número aquí sería inventarlo.**

### 6.3 Lo que SÍ está medido y es grande: la AMPLITUD

| Celda | n | rango H/L medio | **mediana** | p75 | p90 |
|---|---|---|---|---|---|
| BASE | 7.068 | 4,54% | **3,74%** | 5,54% | 7,97% |
| KOSPI ≤ −3% | 275 | 7,96% | 6,96% | 9,93% | 13,97% |
| AC & KOSPI ≤ −3% | 127 | 7,31% | 6,47% | 8,48% | 12,95% |
| **MU[D−1] ≤ −5% & hueco ≤ −2%** | **71** | **8,82%** | **7,55%** | **10,47%** | **13,60%** |
| MU 2026 (todo el año) | 138 | 6,54% | 5,67% | 7,86% | 11,31% |

Y desde la **apertura**, en esa misma celda (n=71):

| Métrica | Valor |
|---|---|
| Máximo mediano por encima de la apertura | **+3,60%** (p75 +6,72%) |
| Mínimo mediano por debajo de la apertura | **−2,96%** (p25 −5,20%) |
| **P(el día toca −2% desde la apertura)** | **60,6%** |
| **P(el día toca +2% desde la apertura)** | **64,8%** |

> **Los DOS lados se tocan el mismo día en ~6 de cada 10 casos.** Eso es la caja de gamma negativa, **medida** — y coincide con el ±5,89% del expected move implícito y con el ATR(14) diario de 8,78%. **El edge de hoy es de AMPLITUD y de BORDE, no de dirección.**

### 6.4 Números del propio repo que apuntan a lo mismo

| Fuente | Celda | Número | Etiqueta |
|---|---|---|---|
| `data/bollinger_probs.json` → **MU** | `elastic` | **P(vuelve a la media en 30 min) = 64,9%**, n=202, **Wilson LB 58,0%**, P(recorre la mitad) 78,7%, `enabled: true` | **MEDIDO**. El único número propio con n decente aplicable hoy |
| `data/bollinger_probs.json` → MU | `bandwalk` | n=16, `enabled: false` | **n INSUFICIENTE** |
| `data/compass_calib.json` | `CONTINUACION\|f0\|NEG` | wr15 = **44,2%**, n=52 | **MEDIDO**: en gamma negativa la flecha de continuación **no le gana a una moneda a 15 min**. Confirma "caja, no dirección" |
| `data/flow_pulse_probs.json` | `SPIKE_PUTS\|muro` | 55%, n=44, Wilson LB 40% | MEDIDO pero flojo (LB por debajo de la moneda) |
| `data/inflation_score.json` → MU | valoración | score −0,858 · fPE 5,81 · PEG 0,03 · "BARATA/creciendo", `inflada: false` | contexto, **no es señal intradía** |

---

## 7. PLAN OPERATIVO

### 7.1 VEHÍCULO — se decide primero, porque hoy es lo que corta el plan

| Comprobación | Resultado |
|---|---|
| Spread < 5% del premium | **NO SE PUEDE VERIFICAR.** Bid/ask = 0 en el **100%** de las 1.780 filas (Polygon Starter no sirve `last_quote`), e IBKR está **prohibido** esta semana. En esta casa "no verificado" **≠** "aprobado" |
| Presupuesto ≤ 200 $/contrato | El straddle ATM 805 **cerró el viernes** en 50,85 $ = **5.085 $/contrato**. Lo único que cabe en 200 $ son **alas**: 900C hoy cerró a 2,82 (282 $), 950C a 0,62 (62 $), 500P del 07-ago se cruzó a 0,50 (50 $) |
| IV de esas alas | **205,6%** en el 0DTE, con **8,7 h** de vida. Comprar 205% de IV a ocho horas del vencimiento es pagar el pico de la vela por un billete de lotería |
| Pin a ±1 strike | **NO hay pin** en MU (ATM±1 = 805, OI 382 = **0,46×** la mediana de la banda ±3%; el umbral de doctrina es 3×). No aplica la prohibición por pin |

> ### **OPCIONES VETADAS — spread no verificable + presupuesto.**
> **Alternativa: ACCIONES.** Y aquí llega el otro corte: **MU cotiza a 796 $ → una sola acción se come casi 4× el presupuesto de 200 $.**
>
> ### **Conclusión de vehículo: con presupuesto de 200 $, MU HOY NO ES OPERABLE. Es VIGILANCIA, no posición.**
> Se vigila el nivel, no la cartera. **NO-TRADE es posición** (regla 6 de la casa). Si el presupuesto real para acciones es mayor que 200 $, sirve el plan de §7.2 con tamaño mínimo. La expresión barata del **mismo** canal es SMH o INTC (88,69 $) — pero eso es **otra tesis y otro boleto**, y no lo mezclo aquí (regla 4: una tesis = un boleto).

### 7.2 Si hay tamaño: los dos bordes de la caja (y solo los bordes)

Gamma negativa = **caja de whipsaw**. No se opera dirección; se opera **borde con print**. Solo **BOUNCE** o **RETEST_REJECT**.

**A) BORDE BAJO — 750,00 · el mejor fade del día**

| | |
|---|---|
| Por qué | **Confluencia MURO + VALLA**: imán de 18.292 OI (15.577 puts) **exactamente** sobre el borde inferior del expected move (749,10). La skill `expected-move-envelope` marca esta confluencia como el mejor fade del día |
| Entrada | **LARGO solo con BOUNCE IMPRESO**: el precio perfora 750 y luego **2 velas 1m CERRADAS por encima de 752** |
| Invalidación | 2 velas 1m cerradas **por debajo de 745** → el imán no aguantó, siguiente parada 720 |
| Objetivos | 775,15 (banda inferior BB diaria) → **790 (POC)**. **Nada más allá**: 800 es un muro y no se compra a través de un muro |
| Riesgo real | El GEX en 750 es **−108,9 M$**, el fondo del acelerador. Si falla, falla rápido |

**B) BORDE ALTO — 824,77 · el gamma flip**

| | |
|---|---|
| Por qué | Frontera de régimen. Por debajo dealer **corto** de gamma (amplifica); por encima **largo** (amortigua) → el fade solo tiene sentido **por debajo** |
| Entrada | **CORTO solo con RETEST_REJECT IMPRESO**: toca 823-826 y **2 velas 1m CERRADAS de vuelta por debajo de 820** |
| Invalidación | **2 velas 1m cerradas por encima de 827** → el libro pasa a gamma positiva, el fade muere. **Fuera sin discutir** |
| Objetivos | 800 (muro) → 790 (POC). Nada más abajo en la primera visita |
| Contra-argumento honesto | El **skew de CALL** (§2.6, RR +0,878 en el 0DTE) dice que el mercado paga más por la cola alcista. Cargarse corto contra eso es ir contra el precio del riesgo |

**C) El nivel 800,00 — la bisagra, se lee, no se opera**

- **2 velas 1m cerradas POR ENCIMA de 800** → el muro aguantó desde abajo (1er toque rebota ~70%, doctrina). Corto muerto hasta 824,77.
- **2 velas 1m cerradas POR DEBAJO de 790** (POC/abs_wall) → la **trampilla** se abre: 775 → 750.
- Entre 790 y 800 **no hay operación**: es ruido dentro de la caja.

### 7.3 Ventana horaria — con los vetos MEDIDOS del repo

| Franja | Qué se hace | Por qué |
|---|---|---|
| **09:30 – 09:45** | **JAMÁS.** Ni mirar el P&L | subasta (regla 7) |
| **09:45 – 10:30** | **VETADO para el fade de borde** | `scripts/bollinger_alarm.py:137` → *"VETO apertura: peor hora del elástico, 58 por ciento"* (mins 585-630). Es la ventana de oro del **momentum**, y la peor del **fade** — y hoy la tesis operable es de fade |
| **10:30 – 11:30** | **Ventana buena para el borde.** Aquí se busca el print | fuera del veto, con el rango del día ya formado |
| **11:30 – 14:00** | picadora: tamaño mínimo o nada | regla 7 |
| **14:00 – 15:30** | La mejor si además hay **squeeze de banda** | `bollinger_alarm.py:135` → *"CELDA ESTRELLA tarde+squeeze, 85 por ciento medido"*. **Hoy hay que recomprobarlo en vivo**: el squeeze exige percentil de bandwidth ≤20 y ahora mismo no lo está |
| **15:30 – 16:00** | solo gestión | — |

**Vetos vivos que apagan el fade (medidos, mismo fichero):**
- **RSI(2) < 10 o > 90** → *"impulso en curso, 53 por ciento"*. **Fuera.**
- **|z-VWAP| ≥ 1,5** → *"día de tendencia, 55 por ciento"*. **Fuera** (y hoy, con hueco de −3,3%, es perfectamente posible que el z-VWAP se pase de 1,5 toda la mañana).

### 7.4 Gestión

- **3 pérdidas = fin del día** (regla 6). Con ATR diario del 8,78%, dos errores de tamaño normal se comen la semana.
- **Entre sirena de entrada y de salida el P&L no se mira** (regla 10).
- **Verde temprano = proteger, no exprimir.**
- **Bracket del lado bajo**: la mediana de excursión adversa desde la apertura en esta celda es **−2,96%**; un stop más apretado que eso será barrido por el ruido normal del día. Si el stop que exige el nivel no cabe en el tamaño, **no hay operación**.

---

## 8. LO QUE PODRÍA MATAR ESTA TESIS

**RIESGO 1 — El capitán de semis gira y el canal se apaga.**
Toda la debilidad de MU hoy es de **sector memoria**, no de mercado: QQQ está plano y **pineado en 690** (PIN medido 3,46×) y SPY está verde. Si SMH recupera su cierre del viernes, MU se queda sin motor y el fade en el borde alto se convierte en **band-walk** contra ti.
**Dato que lo delata primero:** SMH imprimiendo **por encima de 542,41** con 2 velas 1m cerradas, y QQQ cerrando 2 velas por encima de **691**.
**Punto ciego que hay que decir:** **no existe `data/rt_last_SMH.txt`** (hueco conocido, lo está arreglando otro agente) → hasta que aparezca, **SMH llega con 17 minutos de retraso**, justo el capitán que más importa hoy. Es el peor sitio posible para tener el retraso.

**RIESGO 2 — El hueco ya está pagado y esto rebota, no cae.**
El hueco de hoy (−3,28%) es **más profundo que el 81% de los casos** de la celda que aplica; el estudio hermano ya midió que en el índice *"para las 09:30 ya no queda edge corto"*; y la celda que mejor describe a MU (ya cayó ≥5% ayer + abre con hueco ≤ −2%) mide **47,9% de rojo desde la apertura, con mediana POSITIVA (+0,21%)** y un máximo mediano de **+3,60%** sobre la apertura. Añade el **skew de CALL** (§2.6): el mercado paga más por el squeeze que por la caída. **Un corto en el borde bajo es exactamente el trade equivocado.**
**Dato que lo delata primero:** 2 velas 1m cerradas **por encima de 800,00** (el muro aguantó) con %B 1m subiendo de 0,5 y RSI(2) saliendo de la zona <10. En cuanto eso imprima, la trampilla se cierra y el objetivo pasa a 824,77.

**RIESGO 3 — El muro de 800 puede que ya no exista, y todo el árbol se apoya en él.**
El OI que usa este informe es del **cierre del viernes y está CONGELADO** (medido: no hay OI intradía en ninguna de nuestras fuentes; el propio `oi-change` de UW solo compara cierre contra cierre). Y hay una pista fea: el put 800 del 31-jul rotó **20.645 contratos** con solo **+3.673 de ΔOI** → veredicto **CHURN**, o sea que ahí se estuvo **cerrando** tanto como abriendo. Si el muro de 32.618 puts se deshizo el viernes por la tarde, **800 no es un muro**, 790 no es un POC, y el árbol entero se descuelga. Añádele que la IV viene con 15 min de retraso y que **bid/ask no existen**: no puedo ver el libro, solo el inventario de ayer.
**Dato que lo delata primero:** los **primeros 15 minutos de cinta en 800**. Si el precio atraviesa 800 en cualquier sentido **sin reacción**, el muro no está. Y no habrá confirmación por OI: a las 09:30 el `oi-change` del lunes **no existirá**.

---

## LO QUE ME FALTÓ (y por qué importa)

| Falta | Impacto |
|---|---|
| **Bid/ask de opciones** (0 en el 100% de las filas; Polygon Starter no sirve `last_quote`, IBKR prohibido) | Sin esto **no hay gate de spread** → opciones vetadas por defecto, y el expected move es aproximado (lognormal) en vez del straddle que pide la doctrina |
| **Volumen** en las barras 1m (0 en 1.605/1.605) | No puedo validar **ningún** nivel con volumen, ni calcular z-VWAP (que es uno de los vetos medidos del fade) |
| **`data/rt_last_SMH.txt`** | El capitán de semis, que hoy es **el** capitán que manda sobre MU, llega con 17 min de retraso |
| **Flujo de UW de hoy** (no publica en premarket; edad 58,9 h) | Todo §3 es posicionamiento del viernes, no flujo de hoy. Hay que repetir la sonda **en sesión abierta** |
| **OI intradía** (no existe en ninguna fuente) | El muro de 800 es del cierre del viernes y ya mostró CHURN — riesgo 3 |
| **Earnings de MU no verificados con fuente primaria** | MU no aparece en el screen de earnings de la próxima semana (`data/finviz_earn_nextweek_*.csv`, 31-jul), pero eso **no es** una confirmación. Con IV del 205% conviene verificarlo antes de aguantar nada |

---

### FUENTES Y LATENCIAS

| Fuente | Qué aportó | Latencia |
|---|---|---|
| **Finnhub WS** (`data/rt_last_*.txt`) | spot MU/QQQ/NVDA/SPY/INTC | 🟢 **TIEMPO REAL** (trade impreso, edad 19-30 s) |
| **provider_bridge / Intrinio** (`data/bars_*_ibkr.txt`) | barras 1m, BB, RSI, rango premarket | 🟠 **15-17 min (MEDIDO hoy: 1.043 s)** |
| **Polygon** `/v3/snapshot/options` | cadena, OI, griegas e IV **medidas**, GEX, flip | 🔴 **15 min**; OI = **cierre del viernes, congelado** |
| **Unusual Whales** REST | premium firmado, ballenas, oi-change, greek exposure, max pain, darkpool | 🔴 **58,9 h — no publica en premarket (medido hoy)** |
| **yfinance EOD** | series diarias MU/KOSPI/NDX para las probabilidades, BB diario, ATR | EOD (la sesión US de hoy no existe todavía) |
| **Naver** (vía orquestador) | cierre coreano | 🟢 **delay 0 medido** |
| **IBKR / TWS** | **NADA. PROHIBIDO esta semana** — cero conexiones a 4001/4002/7496/7497 | — |

**Doctrina aplicada:** `gamma-regime-walls` · `oi-magnets-protocol` · `print-o-nada-levels` · `expected-move-envelope` · `measured-probability` (n_eff, Wilson, umbral n_eff≥30) · `anti-overfit-killlist` (#3 dark-pool, #16 OI congelado) · `bollinger-always-check` · jerarquía de capitanes · una tesis = un boleto.

**SEÑAL-SOLAMENTE. No es consejo financiero.**
