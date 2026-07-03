# GOOGL — plan 2026-08-03

**Generado 2026-08-03 07:17 ET (premercado, apertura US en 2 h 13 min). SEÑAL-SOLAMENTE: nada de este fichero manda una orden.**

Base: `mapa_opciones.json/.md`, `uw_barrido.json/.md` y `kospi_nasdaq_estudio.md` de la fase anterior + medición propia hecha aquí (cadena completa de Polygon, barras 1m vivas, 5.520 sesiones diarias de GOOGL).

---

## CABECERA — lo que hay que saber en 20 segundos

| campo | valor |
|---|---|
| **spot** | **362,75** (Finnhub WS, print real, edad 33 s, 07:17:07 ET) |
| **cierre viernes 31-jul** | **356,13** (yfinance EOD; nuestras barras 1m dan 356,36 en la vela 15:59 — la diferencia es la subasta de cierre) |
| **premercado** | **+1,86%** · rango 357,50 (04:22) – 364,00 (06:23) · volumen **SIN DATO** (las barras del puente llevan volumen 0 en 30/30) |
| **veredicto** | **CAJA. El precio está clavado en su muro (362,50) y el techo implícito que se pagó el viernes ya está consumido por el hueco. No hay operación entre 360 y 365; solo se opera el PRINT fuera de esa caja.** |
| **probabilidad** | **Dirección del cierre: NO MEDIBLE con nuestra n** (63% de cerrar bajo la apertura, pero p=0,070 y muere al corregir por multiplicidad). **Lo único significativo: P(toca 356,13 hoy) = 52,2%** [Wilson 35,6–67,0 sobre n_eff=35], p=0,00054, sobrevive BH-FDR |
| **3 niveles** | **365,00** (PRINT de la rama alta) · **362,50** (abs wall + POC + borde de la valla del viernes = donde vive el precio) · **360,00** (imán mayor, +85,0 M$/1% de gamma; perderlo arma la rama baja hacia 356,13) |
| **vehículo** | **ACCIONES. OPCIONES VETADAS** — sin NBBO de opciones el gate de spread <5% de la regla 4 **no es verificable hoy** |

---

## 1. FOTO

### 1.1 Precio y procedencia

| dato | valor | fuente | latencia |
|---|---|---|---|
| spot | **362,75** | Finnhub WS `data/rt_last_GOOGL.txt` | **tiempo real** (último print, edad 33 s) |
| cierre 31-jul | **356,13** | yfinance EOD diario | EOD, definitivo |
| última vela 1m | 06:58 → C 362,30 | `data/bars_googl_ibkr.txt` (lo escribe `provider_bridge.py`, proveedor **Intrinio**) | **~15 min delayed** (`data/provider_status.json`: `bar_s` 936–1099 s medido) |
| NBBO acciones | 363,00 / 363,11 | `data/nbbo_googl.txt` (Intrinio) | ~15 min delayed |
| cadena de opciones | 150 filas vivas / 936 en la descarga completa | Polygon `/v3/snapshot/options` | **15 min delayed**, y el **OI es el del cierre del VIERNES** |
| IBKR / TWS | — | — | **NO USADO. Prohibido esta semana** (orden 2026-08-02). Cero conexiones a 4001/4002/7496/7497 |

El nombre del fichero `bars_googl_**ibkr**.txt` es un alias histórico (21 bots lo tienen cableado): **hoy lo llena Intrinio, no IBKR** — `scripts/provider_bridge.py:7` lo declara.

### 1.2 Premercado (barras 1m, delayed ~15 min)

| campo | valor |
|---|---|
| primera vela | 04:00 ET, O 361,00 |
| máximo | **364,00** @ 06:23 |
| mínimo | **357,50** @ 04:22 |
| última vela cerrada | 06:58, C 362,30 |
| n velas 1m hoy | 173 |
| **volumen** | **SIN DATO** — el proveedor sirve 0 en el campo de volumen (30/30 de las últimas barras). Sin volumen no hay VWAP ni z-volumen: no se publican |

### 1.3 Bollinger y fuerza — doctrina "Bollinger SIEMPRE"

| TF | BB(20,2) mid | banda alta | banda baja | **%B** | ancho | **RSI(14)** |
|---|---|---|---|---|---|---|
| **1m** | 362,90 | 363,57 | 362,24 | **0,049** | 0,37% | **34,5** |
| **5m** | 362,28 | 364,01 | 360,56 | **0,505** | 0,95% | 59,0 |
| **15m** | 358,20 | 366,02 | 350,38 | **0,762** | 4,37% | **71,8** |
| **diario** | 348,05 | 378,56 | 317,55 | 0,632 | — | 54,3 (+2,32% sobre SMA20) |

**Lectura:** el 1m está pegado a la banda BAJA (%B 0,05, RSI 34,5) dentro de una banda ridículamente estrecha (0,37%) — es ruido de premercado, no señal. El 15m está en %B 0,76 con RSI 71,8: **estirado al alza, sin reventar la banda**. No hay band-walk (haría falta banda reventada a favor en 2-3 TF) y no hay banda reventada en contra. **Doctrina: ninguna de las dos condiciones de la regla 1 está activa → el gráfico no da permiso todavía.**

Últimas 8 velas de 1m (fuerza): 362,71 · 362,60 · 362,60 · 362,65 · 362,72 · 362,40 · 362,33 · **362,30** — siete velas dentro de 42 centavos. **Es un pin, no una tendencia.**

Últimas 8 velas de 15m: 360,48 → 361,40 → 361,29 → 361,95 → 362,70 → 363,00 → 363,44 → **362,67**. Subida ordenada de 05:00 a 06:30 y **primera vela roja** en la de 06:45.

### 1.4 De dónde viene GOOGL (el contexto que cambia todo)

| fecha | cierre | var. |
|---|---:|---:|
| 22-jul (día de resultados, after-close) | 342,09 | −1,46% |
| **23-jul (reacción a resultados)** | **317,69** | **−7,13%** |
| 24-jul | 319,74 | +0,65% |
| 27-jul | 326,56 | +2,13% |
| 28-jul | 333,71 | +2,19% |
| 29-jul | 336,71 | +0,90% |
| 30-jul | 333,66 | −0,91% |
| **31-jul** | **356,13** | **+6,73%** (abrió 340,83, cerró 356,13 = **+4,49% de apertura a cierre**, máximo 358,58) |

GOOGL **se hundió −7,13% el 23-jul** pese a un beat de BPA del +214% (Alphabet reportó el 22-jul), y desde el mínimo de 317,69 lleva **+14,2% en 6 sesiones**. El viernes fue el día grande. **Hoy no hay resultados** (los próximos: 28-oct). Esto importa dos veces: (a) no hay veto de earnings para el plan de hoy; (b) el bucket estadístico correcto excluye los días de reacción a resultados, y así se ha medido.

---

## 2. CADENA DE OPCIONES EN PROFUNDIDAD

**Procedencia:** Polygon `/v3/snapshot/options` descargada hoy 06:50 ET → `data/analisis_2026-08-03/raw/chain_googl.json`, **936 contratos, 11 vencimientos vivos** (el fichero que lee la flota, `data/opt_chain_googl.txt`, solo trae 2 de esos 11: `provider_bridge.py` recorta con `NEAR_EXPS=2`). **OI = cierre del viernes. Bid/ask = 0 en el 100% de las filas** (el plan Polygon no sirve `last_quote`).

### 2.1 OI y volumen por vencimiento

| venc | contratos | call OI | put OI | P/C OI | call vol | put vol | P/C vol |
|---|---:|---:|---:|---:|---:|---:|---:|
| **2026-08-03 (0DTE)** | 106 | 28.349 | 20.436 | **0,72** | 56.382 | 31.132 | 0,55 |
| 2026-08-05 | 104 | 8.746 | 10.743 | 1,23 | 12.286 | 8.415 | 0,68 |
| **2026-08-07** | 94 | **57.846** | 25.147 | **0,43** | 61.823 | 19.512 | 0,32 |
| 2026-08-10 | 96 | 1.858 | 1.035 | 0,56 | 2.178 | 386 | 0,18 |
| 2026-08-12 | 94 | 3.575 | 664 | 0,19 | 3.230 | 712 | 0,22 |
| 2026-08-14 | 92 | 15.912 | 10.731 | 0,67 | 9.606 | 3.721 | 0,39 |
| **2026-08-21 (mensual)** | 94 | **188.459** | **122.117** | 0,65 | 42.240 | 28.772 | 0,68 |
| 2026-08-28 | 64 | 13.044 | 17.394 | 1,33 | 7.675 | 4.008 | 0,52 |
| 2026-09-18 | 64 | 123.180 | 87.767 | 0,71 | 28.214 | 16.266 | 0,58 |

El libro está **inclinado a calls** en todos los vencimientos operativos (P/C OI 0,43–0,72). El 07-ago es el más extremo: **57.846 calls contra 25.147 puts** — es el posicionamiento nuevo que se abrió el viernes durante el rally.

### 2.2 OI por strike alrededor del spot — 0DTE (hoy)

| strike | call OI | put OI | call vol | put vol | dist. |
|---:|---:|---:|---:|---:|---:|
| 347,5 | 810 | **2.130** | 2.820 | 4.273 | −4,2% |
| **350,0** | 1.935 | **4.221** | 10.727 | 6.260 | −3,5% |
| 352,5 | 1.073 | 1.116 | 4.241 | 2.611 | −2,8% |
| 355,0 | 2.044 | 1.607 | 9.384 | 2.593 | −2,1% |
| 357,5 | 1.121 | 99 | 3.490 | 284 | −1,4% |
| 360,0 | **2.703** | 93 | 6.111 | 131 | −0,8% |
| **362,5** | 1.346 | 13 | 3.212 | 84 | **−0,07%** |
| 365,0 | 980 | 2 | 3.000 | 15 | +0,6% |
| 370,0 | 1.187 | 2 | 1.926 | 2 | +2,0% |
| **372,5** | **1.554** | 0 | 2.353 | 1 | +2,7% |
| 375,0 | 448 | 0 | 620 | 1 | +3,4% |

### 2.3 Concentración de OI y de gamma — TODOS los vencimientos

| strike | OI total | net GEX (M$/1%) | qué es |
|---:|---:|---:|---|
| 310,0 | 32.815 | −12,8 | puts de cola |
| 320,0 | 37.946 | −14,3 | puts de cola |
| 330,0 | 28.588 | −14,5 | puts de cola |
| 340,0 | 31.422 | −11,8 | — |
| **350,0** | **57.097** | **+20,1** | **muro PUT (el mayor cúmulo de toda la cadena)** |
| 355,0 | 19.453 | +4,3 | — |
| **360,0** | **48.715** | **+85,0** | **IMÁN — el mayor pico de gamma de la cadena** |
| 362,5 | 4.589 | +54,5 | abs wall del mapa cercano · POC |
| 365,0 | 15.839 | +53,1 | muro call cercano |
| **370,0** | **26.948** | **+51,8** | **muro CALL** |
| 375,0 | 17.415 | +27,5 | — |
| 380,0 | 28.149 | +38,5 | — |
| 400,0 | 39.390 | +30,6 | cola de calls (lejos) |

**Reparto del OI respecto al spot 362,75:**

| ámbito | OI encima | OI debajo |
|---|---:|---:|
| 0DTE (03-ago) | 6.899 (**14,1%**) | 41.886 (**85,9%**) |
| 05-ago | 3.914 (20,1%) | 15.575 (79,9%) |
| 21-ago (mensual) | 125.105 (40,3%) | 185.471 (59,7%) |
| **todos los vencimientos** | 264.714 (**35,4%**) | 482.550 (**64,6%**) |

El 86% del OI del 0DTE está **por debajo** del precio: el libro de hoy se armó con GOOGL en 356 y el hueco lo ha dejado casi todo atrás. Consecuencia mecánica: **casi todo lo que queda vivo por encima son calls compradas que se están volviendo ITM** — eso empuja al creador a comprar acciones (gamma positiva) y es lo que sostiene el suelo de 360.

### 2.4 Muros, flip y régimen — DOS ámbitos, y hay que decir cuál se usa

| | **mapa cercano** (0DTE + 05-ago, = lo que ve la flota) | **mapa completo** (11 vencimientos) |
|---|---|---|
| flip gamma | **360,28** (−0,68% del spot) | **347,15** (−4,3%) |
| régimen | **INDETERMINADO** (crudo POS; paridad no lo confirma: 0% de pares coherentes) | **POSITIVO** (crudo; paridad no determina) |
| call wall | **365,00** (pin) | **370,00** (pin) |
| put wall | **350,00** | **350,00** (pin) |
| **abs wall** | **362,50** (pin) | **360,00** (pin) |
| POC | 362,50 | 360,00 |
| imanes | 350 / 362,50 / 365 | 350 / 360 / 370 |
| net GEX | +29,5 M$/1% | +372,2 M$/1% |
| net DEX | −6,4 M$ (`dex_sentiment` bajista) | +2.397 M$ (alcista) |

Fuentes: `data/gex_snapshot.json` regenerado a las 07:11 (mapa cercano) y `mapa_opciones.json` (los dos ámbitos). **Los dos ámbitos coinciden en 350 como suelo estructural y discrepan en el techo (365 vs 370): el mensual del 21-ago mete el muro de 370 que el fichero vivo no puede ver.**

**El régimen NO es publicable como POSITIVO firme**: `gex_core.regime_by_parity` exige que las dos lecturas de la identidad de paridad coincidan en signo y en GOOGL hay **0% de pares coherentes** (`parity_ok_pct` 0,0 en el mapa cercano, 3,8% en el completo). El signo crudo es POS. Se publica: **POS crudo, no confirmado.**

### 2.5 Max pain — DISCREPANCIA que hay que declarar

| fuente | max pain 0DTE | método |
|---|---:|---|
| **medido aquí** | **345,00** | mínimo del dolor total de los tenedores sobre los 53 strikes de la cadena Polygon (285–440). **Reproducido con un segundo input independiente** (`data/opt_chain_googl.txt`, 38 strikes): también 345,00 |
| `mapa_opciones.json` (fase anterior) | 362,50 | dice "banda ±22%" — pero con esa misma banda el cálculo da 345,00. **Su 362,50 no se reproduce: se marca como sospechoso y NO se usa** |
| Unusual Whales `/max-pain` | 330,00 | su propio OI, universo completo de strikes, foto del viernes |

Curva de dolor medida (M$): 342,5 → 18,1 · **345,0 → 17,6** · 347,5 → 17,9 · 350 → 18,9 · 355 → 24,5 · 360 → 32,9 · 362,5 → 37,9 · 370 → 54,6.

**Los tres cálculos que se reproducen (345 y 330) ponen el max pain MUY POR DEBAJO del precio (−4,8% y −9,0%).** No es un imán operable a un día (el max pain tira en vencimientos, no en la primera hora), pero sí dice de qué lado está el dolor: **el vencimiento de hoy le duele al mercado cuanto más arriba cierre GOOGL.**

### 2.6 IV, skew y expected move

**Aviso duro sobre la IV:** en el mismo strike y vencimiento, la IV de la call y la de la put deben ser casi idénticas (paridad). En GOOGL 0DTE strike 362,5 Polygon da **call 0,120 y put 1,398**. Eso es **imposible** y delata que la IV de las puts ITM está construida sobre cierres del viernes ilíquidos. **Toda IV "ATM" de Polygon en este nombre está contaminada** — y la `IV_atm = 0,759` que usa `mapa_opciones` es precisamente la media de esos dos números.

Skew de 25 delta (put − call), la parte de la superficie que sí es coherente:

| venc | 25d call | IV | 25d put | IV | **RR (put−call)** |
|---|---:|---:|---:|---:|---:|
| 03-ago (0DTE) | K367,5 | 0,332 | K355 | 1,072 | +0,740 (contaminado) |
| 05-ago | K370 | 0,299 | K352,5 | 0,633 | +0,334 |
| 07-ago | K370 | 0,277 | K350 | 0,559 | +0,282 |
| **21-ago** | K380 | 0,280 | K342,5 | 0,415 | **+0,136** |
| 18-sep | K395 | 0,290 | K335 | 0,380 | +0,090 |

**El skew de puts es fuerte y decrece con el plazo** — normal en un nombre que se dejó −7% hace 8 sesiones. En el mensual limpio (21-ago) la referencia sana es **IV ATM ≈ 0,24–0,26** y RR +0,136: hay demanda de protección, no pánico.

**Expected move del día — TRES métodos, ninguno es un straddle capturado hoy** (imposible: bid/ask = 0 y IBKR prohibido):

| método | valor | anclado en |
|---|---:|---|
| UW `volatility/term-structure`, venc. 03-ago (IV 0,2644) | **±1,64%** = ±5,84 $ | cierre viernes 356,13 → **350,3 – 362,0** |
| straddle ATM del viernes, K355 (call 3,97 + put 2,54 = 6,51) | **±1,83%** = ±6,51 $ | cierre viernes 356,13 → **349,6 – 362,6** |
| `mapa_opciones` (IV Polygon 0,759, contaminada) | ±2,44% | 354,25 – 371,95 |

**Los dos métodos limpios coinciden en ±1,6–1,8% y su BORDE SUPERIOR está en 362,0–362,6.** El precio ahora mismo es **362,75**: el hueco de esta madrugada **ya se ha comido la valla entera del día tal como se pagó el viernes**, y el máximo premercado (364,00) la ha superado. Recentrada sobre el premercado, la valla sería 356,8 – 368,7.

Doctrina `expected-move-envelope`: **la confluencia valla+muro es el mejor fade del día.** Aquí coinciden en el mismo punto el borde superior de la valla (362,0–362,6), el **abs wall 362,50**, el **POC 362,50** y el precio. No es una casualidad bonita: es donde el creador quiere que muera el día.

### 2.7 PIN

| test | resultado |
|---|---|
| ratio OI ATM±1 / mediana banda ±3% (0DTE) | 1.359 / 1.116 = **1,22×** — **no** llega al 3× de la doctrina |
| ratio 05-ago | 589 / 230 = 2,56× — tampoco |
| `abs_wall_kind` del mapa cercano | **pin** |
| brújula de la casa (`data/compass_googl.json`, 07:10) | estado **"CAJA / PIN"**, nivel 362,50 "Muro absoluto", **7 prints, printed=true**, dist 0,02% |
| `data/pin_googl.json` (02-ago) | veredicto NEUTRAL, `zero_dte_buy_forbidden: false`, razón: "max_pain lejos del abs_wall (330 vs 350)" |

**Veredicto honesto: el test cuantitativo de PIN NO se dispara (1,22× < 3×), pero el precio lleva 7 prints en 362,50 y el mapa lo llama pin.** No prohíbo el 0DTE por la regla del pin — lo prohíbo por otra razón (§7: no hay gate de spread).

---

## 3. FLUJO

### 3.1 Aviso de latencia que manda sobre toda esta sección

**Unusual Whales no tiene NI UN dato de hoy.** Medido en `uw_barrido.md §1`: el print más reciente de GOOGL en UW es del **2026-07-31T23:58:48Z = 58,88 horas de antigüedad**; el endpoint global `/api/darkpool/recent` está igual de parado. **Todo lo que sigue es posicionamiento de partida del viernes, jamás flujo de hoy.** El único flujo vivo que tenemos hoy es el print de Finnhub WS (precio, sin lado, sin tamaño agregado).

### 3.2 Premium neto firmado — viernes 31-jul (cinta completa, 391 ticks por minuto)

| campo | valor |
|---|---:|
| net call premium | **+34,5 M$** |
| net put premium | **+7,6 M$** |
| **signed premium** (= call − put) | **+26,9 M$** |
| net delta | +940.534 |
| net call volume / net put volume | +34.380 / −1.931 |
| últimos 30 min | **+2,8 M$** (cerró comprando) |

GOOGL fue el **4º signed premium más alcista de los 11 nombres** del barrido (detrás de AMZN +146,0, NVDA +50,8 y QQQ +31,1) y **el mercado entero cerró en −160,1 M$**. El nombre iba a contracorriente del tono general.

### 3.3 Ballenas — `flow-alerts` (ventana 27-jul → 31-jul, 200 alertas, truncado)

| lado | premium total | ask − bid |
|---|---:|---:|
| CALLS | **+48,7 M$** | **+12,3 M$** (agresor COMPRANDO calls) |
| PUTS | +11,4 M$ | −2,8 M$ (agresor VENDIENDO puts) |

Las cuatro mayores:

| hora UTC | tipo | strike | expiry | premium | lado | V/OI |
|---|---|---:|---|---:|---|---:|
| 31-jul 13:58:01 | call | 325 | **2027-06-17** | **+2,73 M$** | ASK (compra) | 0,24 |
| 31-jul 13:58:43 | call | 320 | **2027-06-17** | +2,19 M$ | ASK (compra) | 0,55 |
| 30-jul 14:31:20 | call | 325 | 31-jul | +1,56 M$ | ASK (compra) | 1,14 (apertura) |
| 30-jul 18:38:29 | call | 380 | 2027-06-17 | +1,19 M$ | ASK (compra), sweep | 0,20 |

**Táctica espada-ballena de la casa** (🐋 ballena de CALLS = techo local cerca; 🐋 de PUTS = piso local cerca): el flujo del viernes es **ballena de CALLS agresiva y repetida** → doctrina: **techo local cerca, la reversión se opera con scalp corto y pequeño**. Dos matices honestos que la debilitan:

1. **Las dos mayores son LEAPS de junio-2027 compradas al ask con V/OI 0,24 y 0,55.** Eso no es un 0DTE de momentum: es alguien construyendo exposición direccional larga a un año vista. La regla de la espada-ballena se midió sobre flujo de vencimiento corto; **aplicarla a un LEAP es extrapolar**. Se etiqueta: *doctrina, y además fuera de su dominio de medición*.
2. **La excepción de la propia regla aplica**: en día de catalizador del líder, la ballena de calls puede ser continuación. GOOGL viene de un beat del +214% y una recuperación del −7% de resultados. Aquí el "catalizador" es el post-earnings drift.

### 3.4 Dark pool — solo prints LIMPIOS

| campo | valor |
|---|---:|
| prints 3 sesiones / limpios / limpios del viernes | 43 / 15 / **3** |
| nivel top | **356,10** con 1.160.372 acciones en 8 prints (79,2% del volumen oculto) |
| otros niveles | 353,25 (39.840) · 351,83 (38.705) · **347,55 (41.640)** · 333,67 (184.592) |
| sesgo respecto al spot premercado | **0,0% encima — 1.465.149 acciones, TODAS por debajo** |

**Los tres bloques mayores del nivel 356,10 son de las 20:00:19–20:00:38 UTC = 16:00 ET = la subasta de cierre.** Doctrina del propio barrido (§11): los prints del cruce de cierre son ejecución de indexación, **no información direccional**. Lo que sí vale son los de horario abierto: **347,55 (41.640 acciones) y 351,83 (38.705)** — dos bloques colocados en la zona 347–352, que es exactamente donde están el flip completo (347,15) y el muro de puts (350).

**Traducción operativa:** hay tamaño institucional colocado **por debajo**, en 347–356. Nada por encima. Si el precio vuelve ahí, entra en zona donde alguien ya compró grande.

### 3.5 `oi-change` — ¿abrían o cerraban?

| veredicto Kochuba | contratos (de 60 examinados) |
|---|---:|
| APERTURA (V ≈ +dOI) | **31** |
| CIERRE (V ≈ −dOI) | **0** |
| CHURN | 11 |
| MIXTO | 18 |

**Cero cierres**, igual que en los 11 nombres del barrido. Los mayores aumentos de OI del viernes en GOOGL:

| contrato | volumen | ΔOI | ratio | veredicto |
|---|---:|---:|---:|---|
| `GOOGL260731P00332500` | 15.046 | +4.940 | 0,33 | MIXTO |
| **`GOOGL260828P00300000`** | 4.730 | **+3.293** | 0,70 | **APERTURA** |
| `GOOGL260731C00332500` | 11.909 | +2.642 | 0,22 | CHURN |
| **`GOOGL260911P00295000`** | 2.611 | **+2.607** | **1,00** | **APERTURA** |
| **`GOOGL260821P00295000`** | 2.665 | +2.357 | 0,88 | **APERTURA** |
| `GOOGL260803C00332500` | 3.684 | +2.210 | 0,60 | APERTURA (call 0DTE, hoy muy ITM) |

**Lo nuevo y limpio que se abrió el viernes son PUTS de cola: 295, 300 en agosto y septiembre.** Puts a −18%/−19% del precio. Eso es **cobertura barata, no una apuesta bajista direccional** — el mismo patrón que el barrido midió en SMH (puts a −26%/−32%) y QQQ.

### 3.6 Griegas de dealer (UW, cierre del viernes)

| campo | GOOGL | día previo |
|---|---:|---:|
| net gamma | **+439.968** | +242.338 (**mejoró**) |
| net delta | +44.319.266 | — |
| net charm | −15.158.826 | — |
| net vanna | +40.575.579 | — |
| flip cumsum UW | 342,5 | — |
| call wall / put wall / abs wall UW | 340 / 330 / **350** | — |

GOOGL cierra el viernes con **gamma de dealer POSITIVA y creciendo** (al contrario que QQQ −297.705, SPY −998.488, SMH −379.309 y AAPL −25.837, los cuatro en negativo). Los muros de UW están todos por debajo porque su foto es con GOOGL en 356. **El único nivel que coincide entre UW y nuestro mapa es 350** — y coincide como suelo en ambos. Esa confluencia sí vale.

### 3.7 JERARQUÍA DE CAPITANES — obligatorio antes de operar el nombre

| capitán | spot | vs cierre viernes | régimen del mapa | flip | abs wall | max pain |
|---|---:|---:|---|---:|---:|---:|
| **QQQ** | 690,26 (Finnhub, edad 66 s) | +0,04% vs 690,57 · +0,33% vs 687,99 (UW) | **NEG** (la paridad **contradice** el signo crudo POS) | 689,04 (−0,28%) | 680 (trampilla) · **PIN detectado en 690** | 679 (−1,7%) |
| **SPY** | 751,12 (edad 1.052 s, **rancio**) | +0,55% vs 747,03 (UW) | **INDETERMINADO** (las dos lecturas de paridad discrepan) | 748,82 | 750 (pin) | 740 |
| futuros NQ (06:41, yfinance ~10 min) | 28.498,75 | **−0,613%** | — | — | — | — |

**Veredicto de capitanes: NO HAY CAPITÁN. QQQ está en régimen NEG (caja de whipsaw) y clavado en su propio PIN de 690, con el flip a −0,28% y el max pain −1,7% por debajo. SPY no tiene régimen publicable.** Es decir:

- **El capitán NO contradice a GOOGL** → la señal del nombre **no queda anulada** por la regla 12.
- **El capitán TAMPOCO la respalda** → GOOGL no tiene viento de cola del índice. Una larga en GOOGL hoy es una apuesta *idiosincrática*, y esas se pagan con tamaño pequeño.
- **Y hay una asimetría peligrosa**: si QQQ pierde 689,04 y se va a buscar 680 (su trampilla), la regla 12 se activa **en contra** y la larga de GOOGL queda muerta aunque su propio mapa siga POS. **Ese es el primer dato a vigilar.**

---

## 4. CONTAGIO COREANO — la respuesta corta es NULO, y aquí está el número

La doctrina de la casa (`~/CLAUDE.md`) clasifica a GOOGL como **exposición coreana NULA** junto a AAPL, MSFT, META, AMZN, TSLA, NFLX, NOK, GLD y SPCX. **No voy a fabricar un canal de transmisión para llenar un párrafo.** Pero como hoy Corea es el titular, lo he medido en vez de citarlo:

**Método:** retornos diarios de `^KS11` (KOSPI composite, `raw/IDX_KS11.csv`) contra GOOGL diario, unión por fecha de calendario local (Corea cierra 7 h antes de la apertura US: no hay look-ahead). **n = 5.242 sesiones conjuntas, 2004-08-20 → 2026-07-31.**

| correlación | valor | qué significa |
|---|---:|---|
| corr(KOSPI[D], GOOGL cierre-a-cierre[D]) | **0,128** | débil |
| corr(KOSPI[D], **hueco de apertura** de GOOGL[D]) | **0,220** | Corea aparece en el HUECO |
| corr(KOSPI[D], **apertura→cierre** de GOOGL[D]) | **−0,019** | **CERO. Una vez abierta la sesión US, Corea no mueve a GOOGL** |
| corr(GOOGL[D−1], KOSPI[D]) | **0,214** | Wall Street arrastra a Seúl **más** de lo que Seúl arrastra a GOOGL |

Y el condicional del caso extremo:

| KOSPI ≤ −5% (n=34) | GOOGL |
|---|---:|
| hueco medio de GOOGL | **−1,39%** |
| apertura→cierre medio | **+0,65%** |
| P(apertura→cierre > 0) | **61,8%** |
| cierre-a-cierre medio | −0,77% |

**Traducción:** históricamente, cuando Corea se desploma, GOOGL abre con hueco a la baja y **la sesión lo recupera** (61,8% de las veces cierra por encima de su apertura). **Hoy ni siquiera hay hueco a la baja: GOOGL abre +1,9%.** El canal coreano ya está contradicho por la propia cinta antes de abrir.

Esto es coherente con el estudio de la fase anterior (`kospi_nasdaq_estudio.md`), que mide para el índice: P(NDX rojo | KOSPI ≤ −5%) = 57,3% frente a un 45,1% base, P(caída ≥2%) = 28,0% — y sobre todo, que **el daño está en el hueco y no en la sesión** (tras KOSPI ≤ −5%, el open→close medio de QQQ es **+0,62%** y P(rojo) 46,3% ≈ base 46,9%). Y el caso concreto de hoy (give-back tras un rally récord coreano) sale **p = 0,21, indistinguible del azar**.

**Conclusión: la caída coreana de −4,88% (KOSPI índice) / −8,93% (KODEX 200, nuestro proxy interno, casi el doble) NO es un argumento para operar GOOGL hoy, ni a favor ni en contra. Quien la use está usando ruido.** Además es toma de beneficios tras un +17,91% récord la sesión anterior, no un crash sistémico de origen americano.

---

## 5. ÁRBOL DE ESCENARIOS

```
                    GOOGL — LUNES 2026-08-03   ·   spot 362,75 (Finnhub WS, 07:17 ET)
             cierre viernes 356,13   ·   hueco +1,86%   ·   régimen POS crudo (paridad NO confirma)
        VALLA del día pagada el viernes: 349,6 – 362,6  ·  recentrada en premercado: 356,8 – 368,7

                                     ▲  RAMA ARRIBA   (prob: SIN MEDIR — ver §6)
                                     │
   372,50  ═══ MURO CALL 0DTE (OI 1.554) · BORDE de la valla ·············· objetivo 2 — NO perseguir
      ▲          más allá: aire hasta 375. Sin confluencia muro+valla no se paga.
      │
   370,00  ███ MURO CALL (pin) — 23.151 calls · GEX +51,8 M$/1% ··········· OBJETIVO 1 de la rama alta
      ▲          doctrina: se opera HACIA el imán, JAMÁS a través del muro.
      │          Aquí se VENDE, no se compra.
      │
   365,00  ▓▓▓ muro call cercano (0DTE 980 · 05-ago 515) · GEX +53,1 M$ ···  PRINT DE ENTRADA LARGA
      ▲          ↳ 2 velas de 5m CERRADAS por encima de 365,00. "Está cerca" no existe.
      │
 ══ 362,75 ◄── SPOT AHORA ────────────────────────────────────────────────────────────────────────
   362,50  ███ ABS WALL (pin) + POC + borde SUPERIOR de la valla del viernes
      │          brújula de la casa: 7 prints, estado CAJA / PIN. El precio VIVE aquí.
      │          ⚠ CAJA: entre 360,00 y 365,00 NO HAY OPERACIÓN. NO-TRADE es posición.
      ▼
   360,00  ███ IMÁN MAYOR — GEX +85,0 M$/1% (el mayor pico de la cadena) ···  suelo intradía nº1
      │          OI total 48.715 · FLIP del mapa cercano en 360,28
      │          ↳ 2 velas de 5m CERRADAS por debajo = RAMA BAJA ARMADA
      ▼
   357,50  ░░░ menor (call OI 1.121, put 99)
      ▼
   356,13  ◆◆◆ CIERRE DEL VIERNES = RELLENO DEL HUECO · darkpool 356,10 ····  OBJETIVO 1 rama baja
      │          P(tocarlo hoy) = 52,2%  ← ÚNICO NÚMERO MEDIDO Y SIGNIFICATIVO (§6)
      ▼
   355,00  ░░░ put OI 0DTE 1.607 · GEX +4,3 M$
      ▼
   350,00  ███ MURO PUT (pin) — 57.097 de OI, el mayor cúmulo de TODA la cadena
      │          confluye con el abs_wall de UW (350). Aquí se CUBRE el corto. ····  OBJETIVO 2 rama baja
      ▼
   347,55  ◆   bloque limpio de dark pool (41.640 acciones, horario abierto)
      ▼
   347,15  ⚠⚠⚠ GAMMA FLIP (mapa completo) — POR DEBAJO: gamma NEGATIVA = ACELERADOR
                 345,00 = max pain 0DTE medido aquí. Es COLA, no objetivo.
                 Doctrina negative-gamma-whipsaw: ahí no se fadea nada en el aire.
                                     │
                                     ▼  RAMA ABAJO
```

### Las dos ramas en tabla

| | **RAMA ARRIBA ↑** | **RAMA ABAJO ↓** |
|---|---|---|
| **PRINT que la confirma** | 2 velas de 5m **cerradas** por encima de **365,00** | 2 velas de 5m **cerradas** por debajo de **360,00** |
| primer imán | 370,00 (muro call, pin) | 356,13 (cierre viernes + darkpool 356,10) |
| muro a atravesar | **370,00 — no se atraviesa, se vende ahí** | 356,13 → luego 355,00 |
| objetivo | 370,00 | 356,13, extensión 350,00 |
| dónde está el flip | 360,28 queda **detrás** (soporte) | 347,15 = **frontera de la gamma negativa** |
| invalidación | cierre de 5m por debajo de **362,50** | recuperación de **362,50** con 2 velas cerradas (setup `reclaim_wall`) |
| borde del expected move | 362,6 (valla del viernes) ya superado · 368,7 (valla recentrada) | 356,8 (valla recentrada) · 349,6 (valla del viernes) |
| probabilidad | **SIN MEDIR** — ver §6. Doctrina (no medido): primer toque de muro rebota ~70%, así que 370 es techo, no trampolín | **P(tocar 356,13) = 52,2%** [Wilson 35,6–67,0], medido, significativo tras BH-FDR |

---

## 6. PROBABILIDAD DE SUBIR O BAJAR HOY

### 6.1 Lo que he medido yo, hoy, para este setup exacto

**Muestra:** GOOGL diario 2004-08-19 → 2026-07-31, **n = 5.520 sesiones** (yfinance, `auto_adjust=False`, guardado en `raw/GOOGL_1d.csv`).
**Bucket:** *día previo con cierre-a-cierre ≥ +3% **Y** hueco de apertura ≥ +1%*, **excluidos los días de reacción a resultados** (15 fechas de earnings identificadas y su sesión siguiente eliminada). Hoy encaja: viernes **+6,73%** y hueco premercado **+1,86%**.
**Independencia:** los días que califican llegan en ráfagas, así que **n_eff = episodios separados por >5 sesiones**. Todo Wilson va sobre `n_eff`, nunca sobre `n`.

**n = 46 · n_eff = 35**

| estadístico | valor | Wilson 95% (n_eff) | base | p (una cola, binomial vs base) | ¿sobrevive BH-FDR (m=7)? |
|---|---:|---|---:|---:|---|
| **P(low ≤ cierre previo) = el hueco se RELLENA** | **52,2%** | [35,6 – 67,0] | 24,5% (huecos ≥1,5% **sin** día grande previo) | **0,00054** | **SÍ** (umbral rango 1 = 0,0071) |
| P(cierre < apertura) | 63,0% | [46,3 – 76,8] | 49,0% | 0,070 | **NO** |
| P(cierre > cierre previo) | 69,6% | [52,0 – 81,4] | 52,6% | 0,041 | **NO** (umbral rango 2 = 0,0143) |
| open→close medio | **−0,78%** (mediana −1,02%) | — | +0,02% | — | — |
| máximo medio desde la apertura | +1,63% | — | +1,07% | — | — |
| mínimo medio desde la apertura | **−2,52%** | — | −1,09% | — | — |

**Robustez** (el sesgo no depende de la época ni del umbral exacto):

| variante | n | n_eff | P(cierre < apertura) |
|---|---:|---:|---:|
| bucket base (todo el histórico) | 46 | 35 | **63,0%** |
| solo 2015+ | 18 | 14 | 61,1% |
| solo 2020+ | 16 | 12 | 62,5% |
| día previo ≥ **+5%** + hueco ≥+1% | 16 | 14 | 62,5% |
| **hueco ≥+1,5% SIN día grande previo** | 265 | 163 | **46,8%** ← el sesgo desaparece |

**El último renglón es el que da confianza en que no es sobreajuste: el hueco por sí solo no sesga nada (46,8% ≈ base). El sesgo nace de la COMBINACIÓN día grande + hueco al alza.** Es una variable de condicionamiento, no un patrón pescado.

### 6.2 La respuesta

**No publico una probabilidad direccional del cierre de hoy, porque la medición no la sostiene.** El punto estimado dice 63% de cerrar por debajo de la apertura, pero p = 0,070 y muere al corregir por las 7 hipótesis probadas. Su intervalo Wilson [46,3 – 76,8] **incluye el 50%**. Decir "63% de que baje" sería exactamente el número plausible que convierte "no sé" en "sé, y es cero".

**Lo único que sí publico como probabilidad medida:**

> **P(GOOGL imprime 356,13 en algún momento de la sesión de hoy) = 52,2%** · Wilson 95% [35,6 – 67,0] sobre **n_eff = 35 episodios** (n = 46 sesiones) · null 24,5% · **p = 0,00054** · sobrevive BH-FDR con m = 7.
> Es decir: **más de la mitad de las veces, un hueco alcista como el de hoy tras un día grande acaba visitando el cierre anterior** — el doble de frecuencia que un hueco alcista corriente.

Y la lectura de amplitud del mismo bucket, que es la que dimensiona el árbol: desde la apertura, el día medio extiende **+1,63% arriba y −2,52% abajo**. La cola baja es **1,5 veces** la alta.

### 6.3 Calibraciones de la casa: una se usa, otra se RECHAZA

**Se usa — `data/compass_calib.json` (regenerado hoy 04:01):** la brújula tiene a GOOGL en estado **CAJA / PIN**. La celda medida para ese estado en régimen POS:

| celda | n | n_eff | wr15 | wr30 | Wilson inf. |
|---|---:|---:|---:|---:|---:|
| `CAJA / PIN\|f0\|POS` | 31 | 31 | **32,3%** | 38,7% | 0,237 |
| `CAJA / PIN\|pool` | 32 | 32 | 31,3% | 25,0% | 0,133 |

Método declarado en su `_meta`: 6.587 filas del ledger, 2.955 excluidas, **n_eff = bloques de mercado de 30 min no solapados**, contra las barras 1m reales. **Traducción: apostar dirección estando en CAJA/PIN acierta ~1 de cada 3 veces a 15 minutos.** Es la mejor razón cuantitativa que hay hoy para NO operar dentro de la caja 360–365.

**Se RECHAZA — `data/calibration.json`:** contiene `reclaim_wall|POSITIVO` = **88,9%**, n=27, CI [71,9 – 96,1], `trust: true`. Sería la celda perfecta para el plan de hoy (el setup de la rama alta es literalmente un `reclaim_wall` en régimen POS). **No la uso, y hay que decir por qué:** las **56 filas** de `data/calib_log.jsonl` son **todas del 2026-07-21** — un solo día, 27 tickers de la misma flota, todos correlacionados, todos en la misma dirección. **n_eff = 1 SESIÓN, no 27.** Publicar ese 88,9% sería exactamente el error que la `anti-overfit-killlist` prohíbe (contar nombres correlacionados como confirmaciones independientes). Además `breakdown|POSITIVO` tiene 28 filas y las **28 son `no_entry`**: ese día ni una sola señal bajista llegó a imprimir.

### 6.4 Lo que es doctrina y NO medición

- Primer toque de muro rebota ~70%; 3+ toques lo agotan; ruptura confirmada (retest-y-rechazo) invierte el nivel. **Doctrina `oi-magnets-protocol`, no medido en este documento.**
- Gamma negativa = caja de whipsaw, no dirección. **Doctrina.**
- Ballena de calls = techo local cerca. **Doctrina, y hoy además fuera de su dominio** (las ballenas son LEAPS de 2027).
- PIN = OI ATM±1 ≥ 3× la mediana de la banda ±3%. **Umbral de doctrina, y hoy NO se dispara (1,22×).**

---

## 7. PLAN OPERATIVO

### 7.1 Vehículo — el gate primero

| requisito de la casa | estado hoy |
|---|---|
| spread de opciones < 5% del premium (regla 4) | **NO VERIFICABLE**: `bid/ask = 0` en el **100%** de las 150 filas de `data/opt_chain_googl.txt` (Polygon Starter no sirve `last_quote`) y **IBKR está prohibido esta semana**. Sin NBBO no hay gate |
| presupuesto ≤ 200 $ por contrato | no evaluable sin precio vivo del contrato (los cierres de Polygon son del viernes, con el spot 7 $ más abajo) |
| pin a ±1 strike | test cuantitativo **no** disparado (1,22×), pero `abs_wall_kind = pin` y la brújula dice CAJA/PIN |

> ### 🚫 OPCIONES VETADAS HOY — acciones o nada.
> No por el spread (que puede estar bien): **porque no se puede medir**, y la regla 4 exige verificarlo ANTES de cantar. Si durante la sesión aparece NBBO real de opciones, se reevalúa; hasta entonces el vehículo es **la acción**.
>
> **No propongo ETF apalancado de GOOGL** (existe GGLL, Direxion 2x): la regla 8 exige **verificar que exista y sea líquido antes de recomendarlo**, y hoy no tengo su libro. Sin verificar, no se nombra como vehículo.

### 7.2 Ventana horaria

| franja | qué se hace |
|---|---|
| **09:30 – 09:45** | **NADA. Jamás.** Es subasta y hoy hay hueco: la primera vela va a ser una mentira |
| **09:45 – 10:30** | **ventana de oro.** Aquí y solo aquí se arma la posición, si hay PRINT |
| 10:30 – 11:30 | gestión de lo abierto; entradas nuevas solo con print limpio |
| **11:30 – 14:00** | **picadora.** No se abre nada |
| 14:00 – 15:45 | solo gestión. Arrastre de charm (net charm de GOOGL −15,2 M) |

### 7.3 Las dos fichas

**RAMA ALTA — larga de continuación** *(la que el mapa de gamma favorece; la que la estadística del bucket NO favorece)*

| campo | valor |
|---|---|
| **PRINT de entrada** | **2 velas de 5m CERRADAS por encima de 365,00** (no 364,9x; no "está cerca") |
| entrada | mercado en la apertura de la 3ª vela, ~365,2 |
| **invalidación** | vela de 5m **cerrada** por debajo de **362,50** → fuera, sin discutir |
| objetivo 1 | **370,00** — muro call, pin, 23.151 de OI. **Se vende AHÍ.** Doctrina: no se compra a través de un muro |
| objetivo 2 | 372,50 solo si 370 se rompe con retest-y-rechazo confirmado. **Es el borde de la valla: no se persigue** |
| tamaño | pequeño. Es una apuesta idiosincrática sin capitán a favor (§3.7) |
| veto | si QQQ pierde 689,04 con 2 velas de 5m cerradas → **la ficha se cancela aunque GOOGL haya impreso** (regla 12: manda el capitán) |

**RAMA BAJA — relleno del hueco** *(la que la estadística favorece; la que hoy NO tiene vehículo)*

| campo | valor |
|---|---|
| **PRINT** | 2 velas de 5m **cerradas** por debajo de **360,00** (el imán de +85 M$ y el flip cercano 360,28) |
| objetivo 1 | **356,13** (cierre del viernes + dark pool 356,10) — **P(tocarlo) = 52,2% medido** |
| objetivo 2 | 350,00, el muro de puts de 57.097 de OI. **Ahí se cubre; no se persigue por debajo** |
| invalidación | recuperar **362,50** con 2 velas cerradas |
| **vehículo** | **NO HAY.** En TFSA no se shortea y las opciones están vetadas por falta de gate de spread |
| **cómo se usa entonces** | **como veto de compra**: mientras el precio esté entre 360 y 365 y no haya print, **NO se compra GOOGL**. El valor de esta rama hoy es impedir una entrada mala, no ganar dinero |

### 7.4 La zona muerta

**Entre 360,00 y 365,00 NO HAY OPERACIÓN.** Es la caja: abs wall 362,50 en el centro, brújula en CAJA/PIN, y la celda medida dice que apostar dirección ahí acierta el 32,3% a 15 minutos (n=31). **NO-TRADE es una posición**, y hoy es la posición por defecto hasta que haya print.

Y el recordatorio de la valla: el borde superior de lo que se pagó el viernes es **362,0–362,6**, y el precio ya está encima. Comprar aquí es comprar **fuera de la valla, contra el muro, sin capitán y sin gate de spread**. Cuatro razones para no hacerlo.

---

## 8. LO QUE PODRÍA MATAR ESTA TESIS

**1. El capitán se cae y arrastra al nombre.**
QQQ está en régimen NEG con el flip a −0,28% (689,04), un PIN detectado en 690,00 y el max pain en 679 (−1,7%). Los futuros NQ vienen **−0,613%**. Si QQQ pierde 689 y se va a su trampilla de 680, la regla 12 se activa **en contra**: la larga de GOOGL muere aunque su mapa siga POS y aunque GOOGL esté más fuerte que el índice.
**Dato que lo delata primero:** 2 velas de 5m de QQQ cerradas por debajo de **689,04** — antes de que GOOGL lo note. Vigilar `data/rt_last_QQQ.txt` (edad típica <90 s) contra `data/rt_last_GOOGL.txt`: cuando el índice cae y el nombre aguanta, la divergencia rara vez dura más de 20 minutos.

**2. El relleno ocurre en los primeros 10 minutos y rebota — el 52,2% se cumple y aun así pierdes.**
La estadística mide **si** se toca 356,13, no **cuándo**. Si el hueco se rellena a las 09:35 y ahí hay rechazo (el suelo está bien construido: 360 con +85 M$ de gamma, 350 con 57k de OI, bloques de dark pool en 347–352), la rama baja queda **agotada al primer toque** y el resto del día es alcista. Vender el relleno tarde es comprar el mínimo del día al revés.
**Dato que lo delata primero:** que **356,1x se imprima antes de las 09:45** y que **360,00 se recupere con 2 velas de 5m cerradas**. Si eso pasa, la rama baja está cerrada por hoy y solo queda la ficha alcista.

**3. Los muros son de ayer, y las griegas están medio rotas.**
Todo el mapa (360, 365, 370, 350) está construido con **OI del cierre del viernes** y griegas de Polygon con **15 minutos de retraso**. Y hay una prueba dura de contaminación: en el mismo strike y vencimiento (362,5, 0DTE) la IV de la call es **0,120** y la de la put **1,398** — imposible por paridad. Además `parity_ok_pct = 0,0`: **cero** pares coherentes en el mapa cercano. Si el libro de hoy no se parece al del viernes —y el viernes GOOGL subió +6,73%, con lo que media cadena se re-strikeó— esos muros pueden no existir.
**Dato que lo delata primero:** que el precio cruce **365,00 o 360,00 sin reacción**: sin mecha, sin pausa, en dos velas de 5m limpias. Un muro real siempre deja al menos una mecha y una vela de duda. **Si no hay mecha, no hay muro, y el mapa entero de hoy se tira.**

---

## 9. LO QUE NO TENGO (y no he rellenado con un número)

| falta | por qué | consecuencia |
|---|---|---|
| **NBBO de opciones** | Polygon Starter no sirve `last_quote`; IBKR prohibido | **sin gate de spread → opciones vetadas.** Es la carencia más cara del día |
| **volumen** (acciones y premercado) | el proveedor de barras sirve 0 (`bar_vol0 = 30/30`) | sin VWAP, sin z-volumen, sin medir participación en el hueco |
| **flujo de opciones de HOY** | UW va **58,9 h por detrás** y no publica premercado | todo el §3 es posicionamiento del viernes, no flujo vivo |
| **latencia intradía real de UW** | solo se ha medido el hueco del fin de semana | hay que repetir la sonda **después de las 09:30** antes de fiarse de UW en vivo |
| **barras con más de 3 sesiones** | `bars_googl_ibkr.txt` empieza el 30-jul 10:08 | el BB(20) de 15m abarca 5 h y cruza el hueco nocturno: úsese como orientación, no como nivel |
| **max pain reconciliado** | tres fuentes dan 345 / 362,5 / 330 | publico el mío (345, reproducido con dos inputs) y marco el 362,5 de `mapa_opciones.json` como no reproducible |

---

**Fuentes y latencias**

| fuente | qué aporta aquí | latencia |
|---|---|---|
| **Finnhub WS** (`data/rt_last_*.txt`) | spot de GOOGL, QQQ, AMZN, META, AAPL | **tiempo real** (print, edad 33 s en GOOGL) |
| **Intrinio** vía `provider_bridge` | barras 1m, NBBO de acciones | **~15 min delayed** (medido: `bar_s` 936–1.099 s) |
| **Polygon** `/v3/snapshot/options` | cadena, OI, griegas, IV | **15 min delayed** + **OI = cierre del viernes** |
| **Unusual Whales** REST | premium neto, ballenas, dark pool, griegas de dealer, max pain, term structure | **58,9 h** (hueco de fin de semana; su latencia intradía sigue SIN MEDIR) |
| **yfinance** diario | 5.520 sesiones de GOOGL, KOSPI `^KS11`, futuros | EOD (histórico) · futuros ~10-12 min |
| **Naver** (vía orquestador) | Corea de hoy | delay 0 medido |
| **IBKR / TWS** | — | **NO USADO — prohibido esta semana** |

**SEÑAL-SOLAMENTE. No es consejo financiero.**
