# META — plan 2026-08-03 (lunes, premarket)

**Generado 07:20 ET. SEÑAL-SOLAMENTE. Ninguna orden sale de este fichero.**

Base: `mapa_opciones.json/.md`, `uw_barrido.json/.md`, `kospi_nasdaq_estudio.md` (fase anterior) +
datos nuevos traídos aquí: `raw/uw2_meta.json` (NBBO de opciones, premarket con volumen, gamma por
strike), barras 1m de `data/bars_meta_ibkr.txt`, diarias de yfinance.

---

## 0. VEREDICTO EN CINCO LÍNEAS

| | |
|---|---|
| **Estructura** | CAJA con techo blando en **570,0** (pin/POC/abs_wall) y trampilla en **550,0**. Bisagra: flip **558,35** |
| **Dirección** | P(cierre > apertura) ≈ **56%** [50,4–61,2], n=324 — **medida pero NO probada** (el LB roza el 50) |
| **Lo que sí está medido con margen** | la ENVOLVENTE: excursión mediana ±1,2% desde la apertura, p75 ±2,3%. **Simétrica.** |
| **Vehículo** | **OPCIONES VETADAS** — 0 contratos cumplen a la vez prima ≤$200 y spread ≤5%. **Acciones** |
| **Corea** | canal a META **NULO y MEDIDO**: corr(META,SMH) = **0,034** en 60 sesiones. No se fabrica un párrafo |

**La frase operativa:** hoy no se opera una dirección, se opera un **borde impreso**. Y el borde
de arriba (570) es más rentable de FADEAR que de perseguir, porque por encima está el mayor muro
de calls 0DTE del rango (580 = 2.099 OI) y el premium muere al atravesarlo.

---

## 1. FOTO

### 1.1 Precio (fuente + latencia + hora)

| dato | valor | fuente | latencia | hora |
|---|---|---|---|---|
| **Último print** | **563,20** | Finnhub WS (trade impreso) | **sin retraso de proveedor**; edad del print 11 min (premercado fino) | 07:04:50 ET |
| **Cinta premarket** | close **563,50** · O 563,70 · H **566,00** · L **562,00** | UW `/stock-state` | **VIVA** (`tape_time` 07:11:39 ET) | 07:11:39 ET |
| **Volumen premarket** | **189.759 acc.** | UW `/stock-state` | viva | 07:11:39 ET |
| **Cierre previo** | **556,71** | yfinance diario **y** UW `prev_close` — **coinciden** | EOD viernes 31-jul | — |
| **% premarket** | **+1,22%** (563,50 / 556,71) | calculado | — | — |
| **Rango premarket** | 562,00–566,00 = **4,00 pts (0,71%)** | UW | viva | — |

> ⚠️ **Corrección a un dato de la sesión**: el cierre previo del **QQQ es 687,99**, no 690,57
> (yfinance diario + UW `prev_close`, dos fuentes independientes). Con 690,57 el hueco implícito
> del QQQ parecía −0,59%; con el cierre real y el cash premarket vivo, **QQQ está en +0,27%**.
> El signo del capitán cambia con esa corrección: importa.

### 1.2 De dónde viene META (contexto obligatorio)

| fecha | O | H | L | C | Δ c-c | nota |
|---|---|---|---|---|---|---|
| 2026-07-16 | 677,28 | 681,90 | 660,16 | 664,54 | — | techo de la caída |
| 2026-07-29 | 593,25 | 599,97 | 582,22 | **585,61** | −1,31% | **earnings tras el cierre** |
| 2026-07-30 | 526,00 | 539,88 | 524,49 | **539,03** | **−7,95%** | hueco de apertura **−10,18%** · vol 42,3M |
| 2026-07-31 | 543,60 | 558,33 | 540,22 | **556,71** | **+3,28%** | vol 24,2M · cierra cerca del máximo |
| **2026-08-03** | premarket 563,70 | 566,00 | 562,00 | **563,50** | **+1,22%** | 189.759 acc. |

META viene de **−18,8% en 11 sesiones** (664,54 → 539,03) y lleva **dos sesiones de rebote**
(+3,28% el viernes, +1,22% ahora). El rebote post-crash **es el estado**, no un detalle.

*Observación con salvedad:* las barras 1m dan cierre RTH del viernes **552,84 (15:59)** frente al
cierre consolidado **556,71** → **+0,70% en la subasta de cierre**. Puede ser desequilibrio MOC
comprador o puede ser que el feed de barras no capture el cruce de cierre. **No se puede
distinguir con las fuentes de hoy** → se anota, no se usa como señal.

### 1.3 Bollinger, RSI y fuerza

| TF | BB(20,2) mid / sup / inf | **%B** | ancho | **RSI(14)** | ATR14 |
|---|---|---|---|---|---|
| **1m** | 564,55 / 566,16 / 562,94 | **0,221** | 0,569% | **41,0** | 0,386 |
| **5m** | 563,62 / 565,73 / 561,51 | **0,507** | 0,750% | **53,6** | — |
| **15m** | 560,22 / 568,86 / 551,58 | **0,699** | 3,084% | **66,0** | 1,876 |

**Últimas 8 velas 1m (ET):**

```
06:45  O 564.72  H 564.72  L 564.00  C 564.00
06:46  O 564.00  H 564.14  L 564.00  C 564.14
06:47  O 564.29  H 564.29  L 564.00  C 564.00
06:48  O 564.02  H 564.06  L 563.72  C 563.72
06:49  O 563.76  H 563.76  L 563.76  C 563.76
06:50  O 563.67  H 563.67  L 563.61  C 563.61
06:51  O 563.51  H 563.70  L 563.50  C 563.70
06:53  O 563.65  H 563.65  L 563.65  C 563.65
```

**Últimas 6 velas 15m:** 05:00 C 564,07 · 05:15 C 562,54 · 05:30 C 562,60 · 05:45 C 563,23 ·
06:00 C 563,73 · 06:15 C **565,20** · 06:30 C 564,87 (máx 565,91) · 06:45 C 563,65.

**Lectura Bollinger (doctrina, regla 1):** **NINGUNA banda reventada, ni a favor ni en contra.**
%B 0,22 (1m) / 0,51 (5m) / 0,70 (15m) → no hay band-walk (haría falta banda reventada a favor en
2-3 TF) y no hay rebote elástico (haría falta banda reventada en contra). **Bollinger hoy no da
señal.** No se inventa una.

**Fuerza:** micro-retroceso ordenado desde el máximo premarket 565,91 (06:35) hasta 563,5-564.
Sin impulso ni agotamiento. El 15m sigue en la mitad alta (%B 0,70, RSI 66) = **sesgo intacto**.

**Salvedades que hay que decir:**
- Las barras 1m de hoy son **154 en un tramo de 172 minutos** → faltan 18 minutos. Bollinger sobre
  cinta fina de premercado: es orientativo, no un nivel.
- La columna de volumen de `bars_meta_ibkr.txt` está a **0 en las 1.600 filas** → **no hay
  confirmación de volumen por vela**. El único volumen real es el agregado de UW (189.759).

---

## 2. CADENA DE OPCIONES EN PROFUNDIDAD

### 2.1 Cobertura

11 vencimientos vivos: **0803, 0805, 0807, 0810, 0812, 0814, 0821, 0828, 0904, 0911, 0918**.
El fichero de la flota `data/opt_chain_meta.txt` trae **1 de 11** (recorte `NEAR_EXPS=2` en
`scripts/provider_bridge.py`) → **el mensual 21-ago, donde vive el OI que ancla el mes, no lo ve
ningún consumidor del repo**. Aquí se recupera de la cadena completa de Polygon (1.618 contratos)
y del NBBO de Unusual Whales.

### 2.2 OI y volumen alrededor del spot — **0803 (0DTE)**

Fuente OI/vol: Polygon snapshot (OI = cierre del viernes). Fuente bid/ask/IV: UW `option-contracts`
(**NBBO del cierre del viernes**, no viva).

| strike | call OI | call vol vie | **call bid/ask** | spread | put OI | put vol vie | put IV |
|---:|---:|---:|---|---:|---:|---:|---:|
| 540,0 | 354 | 680 | — | — | **1.083** | 3.009 | 0,306* |
| 545,0 | 155 | 657 | 13,10 / 14,35 | 9,1% | 759 | 3.871 | 0,306 |
| 550,0 | 744 | 3.130 | 9,30 / 10,80 | 14,9% | **854** | 3.765 | 0,305 |
| 555,0 | 760 | 2.712 | 6,70 / 7,20 | **7,2%** | 132 | 213 | 0,304 |
| 557,5 | 230 | 582 | 5,45 / 6,40 | 16,0% | 138 | 95 | 0,311 |
| 560,0 | 814 | 4.949 | 4,55 / 5,00 | 9,4% | 266 | 298 | 0,310 |
| 562,5 | 415 | 419 | 3,65 / 3,95 | **7,9%** | 28 | 9 | 0,317 |
| **565,0** | 677 | 1.747 | 2,68 / 3,20 | 17,7% | 54 | 19 | 0,312 |
| 567,5 | 298 | 783 | 2,29 / 2,54 | 10,4% | 9 | 13 | 0,331 |
| **570,0** | **1.112** | 2.497 | 1,81 / 2,16 | 17,6% | 150 | 23 | 0,308 |
| 575,0 | 599 | 1.225 | 1,02 / 1,18 | 14,5% | 78 | 7 | 0,314 |
| **580,0** | **2.099** | 3.156 | 0,64 / 0,72 | 11,8% | 97 | 51 | 0,344 |
| 582,5 | 1.072 | 596 | 0,52 / 0,58 | 10,9% | 24 | 5 | 0,361 |
| 590,0 | **2.107** | — | — | — | — | — | — |

\* IV del put 540 tomada de UW en el strike 545 (el 540 no aparece en la ventana ±3,5% del NBBO).

**Reparto del OI (0803):** **52,9% por encima del spot / 47,1% por debajo**. Call OI 29.338 vs
put OI 14.526 → **PCR_OI 0,495** (cadena claramente cargada de calls).

| vencimiento | call OI | put OI | PCR_OI | **% OI encima del spot** |
|---|---:|---:|---:|---:|
| 0803 (hoy) | 29.338 | 14.526 | 0,495 | **52,9%** |
| 0807 (vie) | 43.494 | 31.406 | 0,722 | **55,9%** |
| 0821 (mensual) | 99.265 | 99.601 | 1,003 | **63,4%** |

> **Discrepancia declarada:** el OI de Polygon y el de UW no coinciden (0803 570C: **1.112** vs
> **460**; 545P: 759 vs 430; 580C: 2.099 vs 1.873). Polygon consistentemente más alto. Se usa
> **Polygon como primario** (su fichero OCC es el de esta mañana, más final) y UW como
> contraste. **El RANKING de muros es idéntico en ambas** (calls 590>580>570; puts 540>525>550) →
> los niveles se sostienen aunque el número exacto no se pueda reconciliar.

### 2.3 Muros, flip, régimen — dos mediciones independientes que **convergen**

| | casa (`gex_core`, Polygon, todos los vencimientos) | UW (`greek-exposure/strike`, cadena completa, 31-jul) |
|---|---|---|
| **flip** | **558,35** (−0,91% del spot) | cumsum global **750,0** (dominado por LEAPS 750-820 abiertas el viernes) |
| **call wall** | 600 (`pin`) · 570 en 2 vencimientos | 550 (`call_gex` 21.963) |
| **put wall** | **550 (`trampilla`)** | **550 (`put_gex` −45.066)** |
| **abs wall / POC** | **570,0 (`pin`)** | 550,0 (net −23.103) |
| **imanes** | 550 · 570 · 600 | — |
| **régimen** | **INDETERMINADO** (las dos lecturas de paridad discrepan) | net gamma banda ±6% = **−31.127 → NEGATIVO** |
| net DEX | −2,34 B$ (`mm_vende`, bajista) | net delta +4,53 M |

**La verdad operativa está en el perfil strike a strike, no en el titular. Gamma ASIMÉTRICA:**

```
 strike   call_gex    put_gex      NET        lectura
 585,0      3.827     -2.263     +1.564   positivo (amortigua)
 580,0      8.317     -9.785     -1.468   NEGATIVO (muro 2.099 call OI 0DTE)
 575,0      5.422     -3.188     +2.234   positivo
 572,5      1.400       -272     +1.128   positivo
 570,0      8.713     -8.874       -161   ~NEUTRO  <-- el pin: call y put se anulan
 567,5      1.503       -325     +1.178   positivo
 565,0      4.694     -3.352     +1.342   positivo
 562,5      2.202       -401     +1.801   positivo
------------------------------------ spot 563,50 ------------------------------
 560,0      9.178    -14.537     -5.360   NEGATIVO  <-- aquí empieza el acelerador
 557,5      3.258     -4.273     -1.015   NEGATIVO
 555,0     13.042     -8.243     +4.799   POSITIVO  <-- el mayor cojín local
 552,5      3.824     -1.015     +2.809   positivo
 550,0     21.963    -45.066    -23.103   NEGATIVO GRANDE  <-- la trampilla
 545,0      4.963     -9.735     -4.772   NEGATIVO
 540,0     16.896    -22.983     -6.087   NEGATIVO
```

**Traducción:** de **562,5 a 587,5 la gamma es positiva casi en cada strike** (dealers amortiguan
→ movimientos que se apagan, techo blando). **De 560 hacia abajo es negativa y dominante**
(dealers aceleran → trampilla). **550 concentra −23.103, el mayor foco negativo de toda la banda.**

Y la casa lo etiquetó igual sin ver este dato: `put_wall_kind = "trampilla"`, `abs_wall_kind =
"pin"`. **Dos métodos, dos proveedores, mismo veredicto.** Eso es lo que se publica.

**Doctrina gamma-negativa (memoria `negative-gamma-whipsaw`):** por debajo de 560 esto NO es
dirección, es una CAJA que acelera. Se espera **muro + rechazo IMPRESO**. Nunca fadear un %B
extremo en el aire ahí abajo.

### 2.4 Max pain — **CONFLICTO, no se opera con él**

| método | 0803 | 0805 | 0807 | 0821 |
|---|---|---|---|---|
| casa (Polygon, banda ±22%) | **567,5** | 580,0 | — | — |
| UW (cadena completa, 31-jul) | **535,0** | 572,5 | 560,0 | 600,0 |

32,5 puntos de diferencia en el mismo vencimiento. Causa probable: el OI de hoy se construyó
**antes del crash** (META estaba en 585-664), así que el peso del OI vive lejos del precio y el
max pain es hipersensible a la banda de strikes que se incluya. **Veredicto: max pain INUTILIZABLE
hoy.** No entra en el árbol.

### 2.5 IV, skew y la valla del día

**IV ATM 0803 = 31,3%** (UW: 565C 0,313 / 565P 0,312 — **coherentes entre sí**, que es la prueba
de que la cifra sirve).

> **Polygon dio IV ATM 80,95%** — es la media de un call al 30,2% y un **put al 131,7%** en el
> mismo strike. Eso viola la paridad put-call de forma grosera: su IV está calculada sobre último
> precio rancio, no sobre mid. **DESCARTADA.** El expected move del 2,60% de `mapa_opciones.json`
> hereda ese defecto y **no debe usarse**.

**Skew 0803 (UW NBBO, el único skew publicable hoy):**

| strike | 545 | 550 | 555 | 560 | 565 | 570 | 575 | 580 |
|---|---|---|---|---|---|---|---|---|
| IV call | 0,273 | 0,288 | 0,299 | 0,309 | 0,313 | 0,311 | 0,329 | **0,334** |
| IV put | 0,306 | 0,305 | 0,304 | 0,310 | 0,312 | 0,308 | 0,314 | 0,344 |

Es una **sonrisa casi plana, sin skew de put**. El ala de CALLS está pagada un poco más que la de
puts en el borde superior (580C 0,334 vs 545P 0,306). **No hay pánico comprado para hoy.**

**Curva de IV en el tiempo:** 0803 **31,3%** → 0805 **38,7%** → 0807 **40,5%**.
El mercado paga **más por el viernes que por hoy**. *Causa no verificada en este informe; se anota
como hecho de precio, no se le pone una historia.*

**La valla del día (skill `expected-move-envelope`) — tres lecturas, ninguna es el straddle vivo:**

| método | valor | qué es exactamente |
|---|---|---|
| straddle ATM 562,5 (UW NBBO **cierre del viernes**) | 3,80 + 9,75 = **13,55 = 2,41%** | el más cercano a un straddle real; sobrestima algo (aún tenía el fin de semana) |
| term structure UW (viernes, DTE 3) | **±1,89%** (±10,65$ sobre 563,5) | cálculo del proveedor |
| **realizado**: mediana H−L/C 10 sesiones | **2,87%** (20 sesiones: 3,04%) | **MEDIDO**, no implícito |

→ **Valla implícita ≈ ±2,0–2,4% → 552,0 … 577,0.**
→ **Pero el implícito va POR DEBAJO del realizado (2,9%).** Consecuencia operativa: **no recortar
los objetivos al borde del implícito**. META se ha estado moviendo más de lo que hoy cuesta.

⚠️ El straddle capturado antes de las 15:55 que exige la skill **no existe hoy**: IBKR prohibido,
Polygon Starter no sirve `last_quote`. Lo que hay es la NBBO del cierre del viernes.

---

## 3. FLUJO

### 3.1 Prima neta firmada (UW `net-prem-ticks`, viernes 31-jul, 390 ticks)

| | USD |
|---|---:|
| net call premium | **+2.801.821** |
| net put premium | +188.275 |
| **signed premium** (= call − put, *gotcha de la casa*) | **+2.613.546 → ALCISTA** |
| net delta | +832.474 |
| **últimos 30 min** | **+4.138.089** |

El viernes cerró **comprando calls con fuerza en la última media hora**.

### 3.2 La cinta de contratos — quién agredía (UW, volumen por lado)

| vencimiento | calls: ask − bid | puts: ask − bid | lectura |
|---|---:|---:|---|
| **0803** | **−1.374** | **−2.220** | agresores **VENDIENDO** prima en los dos lados |
| 0805 | +689 | −272 | compra leve de calls |
| **0807** | **−2.942** | **+758** | **venta de calls + compra de puts → sesgo BAJISTA** |

Y las 200 alertas de flujo (30-31 jul): calls 45,2 M$ vs puts 39,8 M$, pero **ask−bid negativo en
ambos** (calls −2,14 M$, puts −1,22 M$) → **venta neta de volatilidad** tras el crush de earnings.

**Esto contradice en parte al `signed premium` alcista**: el premium firmado sube porque las calls
valen más, no porque haya un comprador agresivo detrás. Se dice, no se maquilla.

### 3.3 Darkpool (UW, 3 sesiones, umbral 10 M$)

25 prints, **15 limpios** tras filtrar códigos de condición sucios (VWAP / precio de referencia
previa / condicional).

| nivel limpio | tamaño | prima | prints |
|---:|---:|---:|---:|
| **547,24** | 88.479 | 48,4 M$ | 3 |
| **551,13** | 50.000 | 27,5 M$ | 1 |
| **551,69** | 28.125 | 15,5 M$ | 1 |

**0,0% del tamaño limpio está POR ENCIMA del spot.** Toda la size institucional registrada se
cruzó en **547–552**, justo encima de la trampilla de 550.

El mega-print de **551.831 acciones a 538,89 (297 M$)** va marcado **SUCIO**
(`prior_reference_price`, NBBO en ese instante 544,50/544,90) → **no es un nivel**.

*(Uso descriptivo únicamente: dónde se cruzó la size. Cero probabilidad derivada de aquí — la
skill `anti-overfit-killlist` mató `dpi-lite` y esa lección se respeta.)*

### 3.4 oi-change (viernes vs jueves) — **abrían, no cerraban**

**49 APERTURA · 0 CIERRE · 2 CHURN · 9 MIXTO.**

| contrato | Δ OI | prima | lectura |
|---|---:|---:|---|
| 260918 P 460 | +4.592 | 3,91 M$ | cola de protección barata (−18% del spot) |
| 260821 P 425 | +3.471 | 0,18 M$ | cola de crash |
| 260807 C 530 | +3.107 | 6,47 M$ | call semanal profunda ITM |
| 261016 C 600 | +1.638 | 5,03 M$ | call de octubre |
| 270115 C 760/770/780/820 | +1,6-1,7k c/u | ~6,5 M$ | **LEAPS de enero-2027 muy OTM** |

**Lectura: compra de exposición LARGA (LEAPS 2027 + octubre) financiada/acompañada de colas
baratas muy OTM.** Nadie está cerrando. Y esas LEAPS de 750-820 son exactamente las que colocan
el flip global de UW en 750: **son ruido para hoy**.

### 3.5 Espada-ballena (doctrina de la casa, regla 11)

🐋 **La ballena dominante del viernes fue de CALLS** (+4,14 M$ firmados en los últimos 30 minutos).
Doctrina: **ballena de CALLS = techo local cerca** → se opera la reversión con scalp chico.

**Y el premarket ya se ha comido +1,22% de ese impulso.** La zona en la que la doctrina espera el
techo local (**567–570**) es exactamente el pin/POC. Coincidencia útil.

*Etiqueta honesta: **doctrina, no medido**. La fuente `whale` de la casa está en
`DATA-INSUFFICIENT` (n_eff = 18,7 < 50) según `docs/NULL-CONTROL-2026-07-25.md`. Es un prior de la
casa que se respeta, no una probabilidad.*

### 3.6 Jerarquía de capitanes (regla 12) — **NO hay conflicto, pero el capitán no da luz verde**

Premarket vivo (UW `stock-state`, `tape_time` 07:11-07:12 ET):

| sym | cierre previo | premarket | **%** | apertura premkt → ahora | vol premkt |
|---|---:|---:|---:|---|---:|
| **META** | 556,71 | **563,50** | **+1,22%** | 563,70 → 563,50 (**plano**) | 189.759 |
| **QQQ** (capitán mercado) | 687,99 | 689,84 | **+0,27%** | 692,52 → 689,84 (**−0,39%**) | 573.019 |
| **SPY** (capitán mercado) | 747,03 | 750,76 | **+0,50%** | 750,90 → 750,76 | 271.027 |
| **SMH** (capitán semis) | 540,53 | 533,80 | **−1,24%** | 549,72 → 533,80 (**−2,90%**) | 89.318 |
| NVDA | 200,75 | 199,52 | −0,61% | 201,70 → 199,52 | 999.216 |
| MU | 823,03 | 797,00 | **−3,16%** | 833,22 → 797,00 (−4,35%) | 1.386.856 |

**Tres conclusiones, en orden de importancia:**

1. **NO hay conflicto capitán-tropa.** QQQ y SPY están **verdes** y META también. La regla 12
   (*capitán opuesto anula la señal del nombre*) **no se activa hoy**. Se dice explícitamente
   porque el encargo lo pide.
2. **Pero el capitán no da luz verde.** El QQQ está **en su propio flip** (spot 690,10 vs flip
   689,04, `mapa_opciones`) y su régimen es **NEG con bias PUT** → acelerador, no amortiguador. Un
   capitán en gamma negativa sobre su bisagra **no es un permiso alcista, es una caja**.
3. **El capitán y los semis están FADEANDO dentro del premarket**: QQQ −0,39% desde su apertura
   premarket, SMH **−2,90%**, MU −4,35%. **META es la única que no se ha movido** (563,70 →
   563,50). Esa **fortaleza relativa es el dato más limpio del informe**, y es también el primer
   sitio donde mirar si se rompe.

**SMH NO es el capitán de META** — y eso está medido, no supuesto (§4).

---

## 4. CONTAGIO COREANO A META: **NULO Y MEDIDO**

### 4.1 La medición

Correlación y beta de retornos diarios (yfinance, cierres, `auto_adjust=False`):

| par | beta (250 sesiones) | corr (250) | **beta (60)** | **corr (60)** |
|---|---:|---:|---:|---:|
| **META vs SMH** | 0,26 | 0,259 | **0,03** | **0,034** |
| META vs QQQ | 0,84 | 0,424 | 0,36 | 0,205 |
| **SMH vs QQQ** | 1,81 | **0,907** | 2,04 | **0,940** |
| MU vs QQQ | 2,90 | 0,692 | — | — |

**corr(META, SMH) = 0,034 en las últimas 60 sesiones.** Estadísticamente indistinguible de cero.
El canal por el que viaja el shock coreano (Corea → memoria → SMH, corr 0,94 con el índice)
**no toca a META**.

### 4.2 La confirmación de hoy, en vivo

La onda coreana **sí llegó**, y llegó **exactamente donde la doctrina decía**:
**MU −3,16%** (tras −5,90% el viernes) · **SMH −1,24%** · **NVDA −0,61%**.
Y **no llegó** a META (+1,22%), QQQ (+0,27%) ni SPY (+0,50%).

### 4.3 Lo que dice la doctrina y lo que dice el estudio

- Doctrina de la casa (`~/CLAUDE.md`): META está en la lista **"Nulo"** de exposición coreana.
- `kospi_nasdaq_estudio.md` (fase anterior): P(NDX cae ≥2% | KOSPI ≤ −5%) = **28,0%**, n=75 /
  n_eff=49 → *"drásticamente" REFUTADO*. Caso post-rally: P(NDX rojo) 53,8%, **p=0,21**,
  indistinguible del azar. Y **el daño va en el HUECO, no en la sesión**: gap medio del QQQ
  −0,90%, open→close medio **+0,62%**.
- El KOSPI índice cerró **−4,88%** (6.273); nuestro proxy interno **KODEX 200 cayó −8,93%**, casi
  el doble. **Se usa el índice para hablar del mercado y el KODEX solo como proxy del ETF.**

### 4.4 Veredicto

> **El canal Corea → META es NULO.** No hay transmisión medible (corr 0,034), la doctrina lo
> clasifica como nulo, y el mercado de hoy lo está confirmando en vivo símbolo por símbolo.
> **No se construye un párrafo de "META compra HBM, luego..." para justificar una línea.**
>
> El único canal residual es **beta de índice** (META vs QQQ, corr 0,205 en 60 sesiones — débil y
> debilitándose). Si el QQQ se rompe, META lo nota **como cualquier acción**, no como semi.
> Ese riesgo se gestiona en §8, no aquí.

---

## 5. ÁRBOL DE ESCENARIOS

```
                            META  ·  LUNES 2026-08-03
                spot premarket 563,50   (+1,22% vs cierre 556,71)
        valla implícita ±2,0/2,4%  ->  552,0 ........... 577,0
        valla realizada (medida)   ->  rango diario mediano 2,87%
                                     |
                                     |  ventana 09:45-10:30 (nunca 09:30-09:45)
                                     |
        +----------------------------+----------------------------+
        |                                                         |
   RAMA ARRIBA  ^                                            RAMA ABAJO  v
   P ~ 56%  [50,4-61,2]  n=324                              P ~ 44%  [38,8-49,6]
   (medida, NO probada: el LB roza el 50)                   (complemento)
        |                                                         |
        v                                                         v
  [567,5] IMÁN suave                                      [558,35] FLIP  (gamma)
  gamma +1.178 · call OI 298                              -0,91% del spot
  primer freno, no muro                                   bisagra: debajo, el
        |                                                 perfil se vuelve
        |  PRINT: 2 velas 5m cerradas >567,8              acelerador
        v                                                         |
  [570,0] *** PIN / POC / abs_wall ***                            |  PRINT: 2 velas 5m
  call OI 1.112 · gamma NETA -161                                 |  cerradas <558,0
  (8.713 call vs -8.874 put: se ANULAN)                           v
  = techo blando. 1er toque rebota ~70%                   [556,71] CIERRE VIERNES
  (doctrina oi-magnets, no medido)                        = RELLENO DEL HUECO
  excursión MEDIANA del día llega aquí:                   *** P(tocarlo) = 39,8%
  +1,22% desde la apertura                                    [34,6-45,2] n=324
        |                                                     MEDIDO ***
        |  PRINT para seguir: 2 velas 5m                             |
        |  cerradas >570,5 + retest-y-rechazo                        v
        |  (la 1ª ruptura NO se opera)                       [555,0] COJÍN
        v                                                    gamma +4.799 = el
  [575,0] hueco de OI                                        MAYOR positivo local
  call OI 599 · gamma +2.234                                 dealers amortiguan
  = zona de paso, no de parada                               ULTIMA defensa
  p75 de excursión: +2,29% -> 576,4                                  |
        |                                                            | PRINT: 2 velas
        |  *** PROHIBIDO COMPRAR A TRAVÉS ***                        | 5m cerradas <554,5
        v                                                            v
  [580,0] *** MURO MAYOR 0DTE ***                           [550,0] *** TRAMPILLA ***
  call OI 2.099 · gamma -1.468                              put OI 854 · put_wall
  borde superior de la valla implícita                      gamma NETA -23.103
  = OBJETIVO MÁXIMO del día                                 = el MAYOR foco negativo
                                                            de toda la banda
  INVALIDACIÓN de la rama:                                  darkpool limpio 547-552
  perder 558,0 impreso                                      p75 de excursión: -2,36%
                                                            -> 550,2  (¡clava aquí!)
                                                                     |
                                                                     v
                                                            INVALIDACIÓN de la rama:
                                                            recuperar 562,5 impreso
                                                            (vuelve la gamma positiva)
```

### 5.1 Los nodos, tipados

| nivel | tipo | evidencia | distancia desde 563,50 |
|---|---|---|---|
| **580,0** | **MURO** (mayor call OI 0DTE) + borde valla | call OI 2.099 · gamma −1.468 | **+2,93%** |
| 575,0 | zona de paso | call OI 599 · gamma +2.234 | +2,04% |
| **570,0** | **PIN / POC / abs_wall** | call OI 1.112 · gamma neta −161 (se anulan) | **+1,15%** |
| 567,5 | imán suave | call OI 298 · gamma +1.178 | +0,71% |
| — | **spot** | 563,50 | — |
| **558,35** | **FLIP** (gamma) | `gex_core`, todos los vencimientos | **−0,91%** |
| **556,71** | cierre del viernes / **relleno de hueco** | medido: P=39,8% [34,6-45,2] n=324 | **−1,20%** |
| 555,0 | **cojín** (gamma + máxima) | gamma +4.799 · call OI 760 | −1,51% |
| **550,0** | **TRAMPILLA** (put_wall) | put OI 854 · gamma **−23.103** · darkpool 547-552 | **−2,40%** |

**La confluencia que hace este árbol creíble:** las excursiones **medidas** sobre n=473 días de
hueco alcista de META caen **exactamente** sobre los niveles de opciones, sin que nadie las haya
ajustado:

| percentil medido | desplazamiento | precio | nivel de opciones que hay ahí |
|---|---|---|---|
| mediana arriba | +1,22% | **570,4** | **el pin 570,0** |
| p75 arriba | +2,29% | 576,4 | dentro de la valla, antes del muro 580 |
| mediana abajo | −1,24% | **556,5** | **el relleno del hueco 556,71** |
| p75 abajo | −2,36% | **550,2** | **la trampilla 550,0** |

Dos sistemas independientes (estadística de 3.570 sesiones y libro de opciones de hoy) señalando
los mismos cuatro precios. **Ese es el mapa del día.**

---

## 6. PROBABILIDAD DE SUBIR O BAJAR HOY

### 6.1 El número

> **P(cierre > apertura) = 55,9%** · **Wilson 95% [50,4% – 61,2%]** · **n = 324** · **MEDIDA**
>
> **P(cierre < apertura) = 44,1%** · [38,8% – 49,6%]

### 6.2 Cómo se midió, exactamente

- **Datos**: barras diarias de META, yfinance, `auto_adjust=False`, **2012-05-18 → 2026-07-31**,
  **n = 3.570 sesiones**. Descargadas hoy 07:10 ET.
- **Condición**: el cubo de hueco de apertura **[+1,0%, +2,0%)**. El premarket implica
  563,50 / 556,71 = **+1,22%** → cae en ese cubo.
- **Etiqueta**: `Close > Open` de la MISMA sesión. Es una etiqueta a horizonte de sesión, **no
  triple barrera** — la skill `measured-probability` exige triple barrera para señales intradía
  con stop; aquí no hay stop porque la pregunta de Yunior es de dirección de la SESIÓN. **Se
  declara la limitación**: este número **no** es la probabilidad de que un trade con stop gane.
- **Independencia**: una observación por sesión, un solo símbolo → **sin agrupamiento
  transversal**, así que no aplica la corrección `n_eff` por ρ̄ de flota (esa corrección es para
  pooling de 30 semis correlacionados). **n_eff = n = 324.**
- **Wilson** sobre esa n, z = 1,96.

### 6.3 Curva de sensibilidad del umbral (test #4 de `anti-overfit-killlist`) — **y el uso a las 09:30**

**Esta tabla es operativa: a las 09:30 se mira el hueco REAL y se lee la fila que toque.**

| cubo del hueco | n | **P(cierre > apertura)** [Wilson 95%] | **P(rellena el hueco)** [Wilson 95%] |
|---|---:|---|---|
| < −2% | 150 | 0,493 [0,414–0,573] | 0,227 [0,167–0,300] |
| [−2%, −1%) | 282 | 0,532 [0,474–0,589] | 0,511 [0,453–0,568] |
| [−1%, −0,5%) | 387 | 0,527 [0,477–0,576] | 0,654 [0,605–0,699] |
| [−0,5%, +0,5%) | 1.746 | 0,491 [0,467–0,514] | 0,854 [0,837–0,870] |
| [+0,5%, +1%) | 531 | 0,501 [0,459–0,543] | 0,608 [0,566–0,649] |
| **[+1%, +2%) ← hoy** | **324** | **0,559 [0,504–0,612]** | **0,398 [0,346–0,452]** |
| [+2%, +3,5%) | 93 | 0,559 [0,458–0,656] | 0,312 [0,227–0,412] |
| ≥ +3,5% | 56 | 0,464 [0,340–0,593] | 0,054 [0,018–0,146] |

**Lectura crítica y honesta del test de sensibilidad:** el efecto existe en **dos cubos contiguos**
(+1→+2% y +2→+3,5%, ambos 0,559) pero **se INVIERTE en el extremo** (≥+3,5% → 0,464). No es
monótono. Y el **límite inferior de Wilson (50,4%) apenas despega del azar**. → **El edge
direccional NO está probado.** Se publica el número porque se pidió, con su etiqueta puesta.

### 6.4 Referencias base (el contexto que impide engañarse)

| medida | n | P | Wilson 95% |
|---|---:|---:|---|
| BASE, toda la historia: P(cierre > apertura) | 3.569 | 0,507 | [0,491–0,524] |
| BASE, close-to-close verde | 3.569 | 0,521 | [0,505–0,538] |
| **Últimas 250 sesiones** | 250 | **0,480** | [0,419–0,542] |

META es una **moneda al aire** de base, y en el último año ha estado **por debajo** de la moneda.
El +5,9pp del cubo de hoy se mide **contra 50,7%**, no contra cero.

### 6.5 El caso más parecido a hoy: **DATA-INSUFFICIENT**, y aun así es la bandera roja

Condición: `close-to-close(D−2) ≤ −5%` **y** `close-to-close(D−1) ≥ +2,5%` (el patrón exacto de
hoy: −7,95% el jueves, +3,28% el viernes).

**n = 8.** Fechas: 2012-05-24, 2012-08-16, 2018-10-26, 2020-03-05, 2020-03-11, 2020-03-16,
2020-10-30, 2024-07-19.

Crudo: **2 de 8 verdes (25%)**, media open→close **−1,75%**, media close-to-close **−4,38%**.

> **Por la ley de la casa esto NO es una probabilidad** (n=8, muy por debajo del n_eff ≥ 50 de
> `measured-probability`). **No se publica como número.** Se publica como lo que es: **la bandera
> roja de mayor peso del informe**, con su n a la vista. Además 4 de las 8 fechas son marzo-2020 y
> octubre-2018 → la muestra está dominada por dos regímenes de crash, lo que la hace aún menos
> transportable.

### 6.6 Lo que SÍ está medido con margen (y es lo que se opera)

| medida | valor | n | Wilson 95% |
|---|---|---:|---|
| **P(rellena el hueco = toca 556,71)** | **39,8%** | 324 | [34,6–45,2] |
| P(la apertura sea el MÍNIMO del día) | **0,63%** | 473 | [0,2–1,8] |
| P(la apertura sea el MÁXIMO del día) | **0,63%** | 473 | [0,2–1,8] |
| excursión arriba (H−O)/O | p25 0,59% · **mediana 1,22%** · p75 2,29% · p90 3,51% | 473 | — |
| excursión abajo (O−L)/O | p25 0,55% · **mediana 1,24%** · p75 2,36% · p90 3,63% | 473 | — |

**Estas cinco filas valen más que el 55,9%.** Dicen:
1. La excursión es **simétrica** → la dirección no está en el hueco.
2. **Prácticamente nunca (0,63%) la apertura es el extremo del día** → **jamás se persigue la
   apertura**. Siempre hay excursión hacia los dos lados que espera al paciente.
3. El p75 de cada lado clava el muro correspondiente (550 abajo, 576 arriba).

### 6.7 Calibraciones del repo — consultadas y **NO aplicables**

| fichero | qué tiene | ¿sirve hoy? |
|---|---|---|
| `data/compass_calib.json` | 19 celdas de la brújula, `n_eff` 1–52, la mejor `CONTINUACION\|f1\|NEG` wr15 0,578 lo 0,370 | **NO**: mide transiciones de la brújula intradía, no dirección de sesión. Y sus `lo` de Wilson están todos por debajo de 0,41 |
| `data/calibration.json` | `reclaim_wall\|POSITIVO`: rate 0,889, CI [0,719–0,961], **n=27**, `trust: true` | **PARCIAL**: aplicable si hoy se produce un *reclaim* del muro 570 con régimen POSITIVO. Es el único bucket con `trust` en el repo. **n=27** → se cita, no se dimensiona con él |
| `data/calibration_barrier.json` | barrido de triple barrera de bollinger | **NO**: hoy Bollinger no da señal (%B 0,22/0,51/0,70) |
| `timeofday_calib` | — | no localizado como fichero en `data/` |

**Veredicto global de fuente** (`docs/NULL-CONTROL-2026-07-25.md`, citado por la skill):
bollinger = **UNPROVEN** (edge −0,014, 0/117 celdas pasan BH-FDR); whale/flow/structural/cusum =
**DATA-INSUFFICIENT**. **Ninguna fuente de la casa está autorizada a cantar SIGNAL hoy.** Por eso
el número de §6.1 viene de una medición hecha aquí sobre barras diarias, y no de la maquinaria de
señales.

---

## 7. PLAN OPERATIVO

### 7.1 Vehículo: **OPCIONES VETADAS — se opera en ACCIONES**

Gate de la casa (regla 4): **spread ≤ 5% del premium** y **prima ≤ $200 por contrato**.
Medido sobre **286 + 288 + 436 contratos** (0803 / 0805 / 0807) con NBBO de UW:

> **CANDIDATOS que cumplen AMBAS condiciones dentro de ±6% del spot: 0 (CERO).**

| lo barato (≤$200) | mid | **spread** | lo estrecho (≤5%) | mid | coste |
|---|---:|---:|---|---:|---:|
| 0803 570C | $1,99 | **17,6%** | 0807 550P | $9,00 | **$900** |
| 0803 575C | $1,10 | **14,5%** | 0807 565C | $8,80 | **$880** |
| 0803 580C | $0,68 | **11,8%** | 0807 550C | $16,05 | **$1.605** |
| 0803 572,5C | $1,60 | **31,8%** | 0807 570C | $7,10 | **$710** |

Los dos gates fallan **por lados opuestos y a la vez**: lo que cabe en el presupuesto tiene
spreads del **12–32%** (se pierde el 15% al entrar, exactamente el desastre de DRAM del 2026-07-22);
lo que tiene spread sano cuesta **4–8 veces** el presupuesto.

**→ VEHÍCULO: ACCIONES META.** Sin apalancamiento de opciones.

*Salvedad honesta y su regla:* la NBBO usada es la del **cierre del viernes**, siempre la más ancha
del día. **A las 09:45 se reverifica en vivo.** Si algún ATM de 0807 baja de 5% **y** de $200, se
reconsidera — pero con META a 563 un ATM semanal vale $700–1.600, así que el presupuesto de $200 lo
hace **matemáticamente casi imposible**. El veto se levanta sólo con números en pantalla.

**Pin:** el ratio de OI en el strike ATM ±1 frente a la mediana de la banda ±3% es **1,95**, por
debajo del umbral doctrinal de 3× → **NO hay pin en el dinero**. Así que el 0DTE **no** queda
prohibido por pin. Queda prohibido **por spread**, que es peor.

### 7.2 Ventana horaria

| franja | qué se hace |
|---|---|
| **09:30 – 09:45** | **NADA.** Subasta. Prohibido por doctrina, sin excepción |
| **09:45 – 10:30** | **VENTANA DE ORO.** Única ventana de entrada de hoy |
| 10:30 – 11:30 | sólo gestión de lo abierto |
| **11:30 – 14:00** | **PICADORA.** Fuera |
| 14:00 – 15:45 | sólo gestión; arrastre de charm (net charm UW −243 M) |
| 15:45 – 16:00 | cierre / no abrir |

### 7.3 SETUP A — largo desde el borde inferior (**el preferido**)

Hacia el imán, desde el lado cercano. Es el que la doctrina paga.

| | |
|---|---|
| **Disparador** | retroceso a la zona **557,0 – 559,0** (flip 558,35 + cierre del viernes 556,71) **dentro de 09:45–10:30** |
| **PRINT que lo confirma** | **2 velas de 5m CERRADAS por encima de 559,5** tras haber tocado ≤ 558,5. *"Está cerca" no existe* |
| **Entrada** | acciones META en el cierre de la 2ª vela |
| **Invalidación** | **cierre de 5m por debajo de 555,0**. Ahí se pierde el mayor cojín de gamma positiva (+4.799) y el perfil pasa a acelerador |
| **Riesgo** | ~4,5 pts = **0,80%**. ATR14 15m = 1,88 → son 2,4 ATR, holgado |
| **Objetivo 1** | **567,5** (imán suave) — cobrar la mitad |
| **Objetivo 2** | **570,0** (pin / POC / abs_wall) — cobrar el resto. **Aquí se sale, no se pide más** |
| **Extensión** | sólo con **ruptura CONFIRMADA de 570** (2 velas de 5m cerradas > 570,5 **+ retest-y-rechazo**). La 1ª ruptura NO se opera. Entonces 575,0 |
| **Ratio** | 4,5 de riesgo por 8,5–11 pts de objetivo ≈ **1:1,9 / 1:2,4** |

### 7.4 SETUP B — fade del pin (**espada-ballena**)

| | |
|---|---|
| **Disparador** | el precio alcanza **569,0 – 570,5** dentro de **09:45–10:30** y **no lo atraviesa** |
| **PRINT que lo confirma** | **2 velas de 5m CERRADAS por debajo de 569,0** tras haber tocado ≥ 570,0 |
| **Entrada** | corto en acciones (TFSA: no se shortea → entonces **NO-TRADE**, ver 7.6) |
| **Invalidación** | **cierre de 5m por encima de 571,5**. Muro roto = nivel **INVERTIDO**, se sale sin discutir |
| **Objetivo 1** | 563,5 (vuelta al spot) |
| **Objetivo 2** | 560,0 |
| **Extensión** | 556,71 (relleno del hueco, **39,8% medido**) |
| **Base** | 🐋 ballena de CALLS al cierre del viernes (+4,14 M$ en 30 min) = **techo local cerca** — *doctrina, no medido* — + 1er toque de muro rebota ~70% — *doctrina* — + la excursión MEDIANA del día llega justo a 570,4 |

### 7.5 Prohibiciones explícitas para hoy

1. **PROHIBIDO comprar a través del muro de 580.** Si META ya está en 568-572, no se compra nada
   apuntando a 580: hay que atravesar el mayor muro de calls 0DTE del rango (2.099 OI). Es
   literalmente el post-mortem de META 660C del 2026-07-20 repitiéndose.
2. **PROHIBIDO perseguir la apertura.** P(la apertura sea el extremo del día) = **0,63%**, n=473.
   Siempre hay excursión a los dos lados.
3. **PROHIBIDO fadear el %B en el aire por debajo de 560.** Ahí la gamma es negativa (−5.360 en
   560, −23.103 en 550) → acelerador. Sólo **muro + rechazo IMPRESO**.
4. **PROHIBIDO operar la 1ª ruptura** de 570 o de 550. Sólo **BOUNCE** o **RETEST-Y-RECHAZO**
   (skill `print-o-nada-levels`).
5. **PROHIBIDAS las opciones** hasta reverificar spread en vivo a las 09:45 (§7.1).

### 7.6 NO-TRADE también es posición (regla 6)

**El escenario más probable de hoy es que no haya trade.** Las condiciones para no operar:

- El precio abre y se queda **entre 560 y 568** sin tocar ningún borde → **no se hace nada**. Ese
  interior es la caja, y la caja no paga.
- Si el QQQ pierde 689,0 impreso, **el Setup A queda anulado** aunque el precio llegue a 558.
- Si Yunior no puede shortear (TFSA), el **Setup B simplemente no existe**: se anota el nivel, se
  espera al 570 y, si rechaza, **se observa**. No se compra un put — están vetados por spread.
- **3 pérdidas = fin del día.**

---

## 8. LO QUE PODRÍA MATAR ESTA TESIS

### Riesgo 1 — **La onda coreana llega tarde, por el índice**

META no tiene canal directo (corr 0,034 con SMH) **pero sí beta de índice**. Ahora mismo el QQQ
está **en su flip (689,04) con régimen NEG y bias PUT** = acelerador. Y ya está fadeando: abrió el
premarket en 692,52 y va por 689,84. SMH lleva **−2,90% dentro del propio premarket**. Si el QQQ
pierde su bisagra, arrastra a todo, incluida META.

> **Dato que lo delata PRIMERO:** **2 velas de 5m CERRADAS del QQQ por debajo de 689,0**
> (segunda confirmación: SMH por debajo de **530,0**). En ese momento el Setup A queda anulado
> aunque el precio de META esté en la zona de entrada. El capitán manda.

### Riesgo 2 — **El rebote post-earnings se agota en el día 3**

El patrón exacto de hoy (crash ≥5% en D−2 + rebote ≥2,5% en D−1) tiene **n=8** y sale **2/8 verde**
con **−4,38% de media close-to-close**. **n=8 no es una probabilidad** — pero es la única evidencia
directa del patrón que estamos operando, y **apunta en contra**. Por debajo de 560 la gamma pasa a
negativa: el movimiento no se frena, acelera.

> **Dato que lo delata PRIMERO:** **pérdida de 556,71 (cierre del viernes) antes de las 10:30**.
> El relleno del hueco tiene un **39,8% [34,6–45,2] medido** — si ocurre temprano, la rama alcista
> está muerta y el siguiente parón real es **555,0**, y luego el vacío hasta **550,0**.

### Riesgo 3 — **La ballena de calls del viernes era el TECHO, no la gasolina**

+4,14 M$ firmados en los últimos 30 minutos del viernes, y el premarket ya se ha comido **+1,22%**
de ese impulso. Doctrina espada-ballena: 🐋 CALLS = **techo local cerca**. Refuerzo desde la cinta:
en el 0803 los agresores fueron **vendedores netos** de calls (−1.374) y de puts (−2.220), y en el
0807 **vendieron calls (−2.942) y compraron puts (+758)**. Es venta de volatilidad, **no
acumulación direccional**. El `signed premium` alcista sube porque las calls valen más, no porque
las estén persiguiendo.

> **Dato que lo delata PRIMERO:** un **spike de calls en la apertura** en la zona 567–572 que **no
> consolide por encima de 570 en 15 minutos**. *Call-spike de apertura = techo, no gasolina.*
> Y si el precio se pega a 570 sin atravesarlo dos veces, el 1er toque ya rebotó y el 2º es el
> aviso: se pasa al Setup B o a NO-TRADE.

---

## 9. LO QUE ME FALTÓ (y por qué)

| falta | causa | consecuencia |
|---|---|---|
| **NBBO de opciones EN VIVO** | IBKR prohibido esta semana; Polygon Starter no sirve `last_quote`; UW da la NBBO del **cierre del viernes** | el gate de spread se decide **a las 09:45**, no ahora. El veto de §7.1 es conservador |
| **Volumen por vela 1m** | `bars_meta_ibkr.txt` escribe **0** en la columna de volumen en las 1.600 filas | **no hay confirmación de volumen para el PRINT**. Sólo el agregado premarket de UW (189.759 acc.) |
| **Straddle ATM capturado antes de 15:55** | no existe con las fuentes de hoy | la valla es una **estimación de tres lecturas**, no la medición que pide la skill |
| **Catalizador de la fuerza de META** | ninguna de nuestras fuentes lo identifica | **no se inventa uno.** El +1,22% se describe, no se explica |
| **Reconciliación del OI** | Polygon vs UW discrepan (570C 0DTE: 1.112 vs 460) | se publican ambos; el **ranking** de muros coincide y es lo que se usa |
| **18 minutos de barras de hoy** | 154 barras en un tramo de 172 min | Bollinger de premercado es orientativo |
| **`timeofday_calib`** | no localizado como fichero en `data/` | no hay ajuste horario medido para la ventana 09:45-10:30 |

---

## 10. FUENTES Y LATENCIA

| fuente | qué aportó | latencia |
|---|---|---|
| **Finnhub WS** `data/rt_last_META.txt` | último trade impreso 563,20 | **sin retraso de proveedor** (edad del print 11 min, premercado fino) |
| **Unusual Whales** `/stock-state` | premarket O/H/L/C **+ volumen** de META QQQ SPY SMH NVDA MU | **VIVA** (`tape_time` 07:11-07:12 ET) |
| **Unusual Whales** `/option-contracts` | **NBBO bid/ask**, IV coherente, volumen por lado | **cierre del viernes 31-jul** |
| **Unusual Whales** `/greek-exposure/strike` | gamma por strike (297 strikes) | cierre del viernes |
| **Unusual Whales** `/darkpool` `/net-prem-ticks` `/oi-change` `/flow-alerts` | bloques, prima firmada, aperturas | viernes 31-jul |
| **Polygon** `/v3/snapshot/options` | OI y griegas de 1.618 contratos, 11 vencimientos | **15 min** + OI = cierre del viernes |
| **yfinance** diario | 3.570 sesiones de META; cierres de QQQ/SPY/SMH/MU/NVDA/NDX | EOD |
| `data/bars_meta_ibkr.txt` | 1.600 barras 1m (30-jul → hoy 06:53) | viva; **sin volumen** |
| **IBKR / TWS** | — | **NO USADO. Prohibido esta semana.** Cero conexiones a 4001/4002/7496/7497 |

---

**SEÑAL-SOLAMENTE. No es consejo financiero.**
