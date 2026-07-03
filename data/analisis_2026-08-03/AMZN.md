# AMZN — plan 2026-08-03

**Generado** 2026-08-03 07:40 ET (premarket, lunes) · **SEÑAL-SOLAMENTE. No es consejo financiero.**
Base: `mapa_opciones.json`, `uw_barrido.json`, `kospi_nasdaq_estudio.md` (fase anterior), **recalculados y verificados uno a uno** contra `raw/chain_amzn.json` (Polygon, 710 contratos), `data/gex_snapshot.json` (regenerado **07:31:56 ET**), barras vivas y `data/rt_last_*.txt`.

---

## RESUMEN EN UNA PANTALLA

| | |
|---|---|
| **Spot** | **276,22** (Finnhub WS, tick 07:31:38 ET) |
| **Cierre RTH viernes** | 271,35 (`bars_amzn_ibkr.txt`, barra 15:59) |
| **Premarket** | **+1,80 %** · rango 273,77–276,66 · volumen **SIN DATO** |
| **Régimen gamma** | **POSITIVO** (net GEX casa +45,7 M, +126,1 M $/1 %) |
| **VEREDICTO** | **CAJA de gamma positiva 270–280 con el spot PEGADO al PIN de 275. No hay dirección: hay bordes. La señal alcista del nombre está ANULADA por el capitán.** |
| **P(sube hoy)** | **NO EXISTE — sin medición publicable.** Lo que sí está medido (n_eff=31) dice que seguir la flecha en este estado **acierta el 32,3 %** → no operar la dirección |
| **Los 3 niveles** | **280,00** muro call (pin) · **275,00** ★ **abs_wall tipo PIN + POC — el spot está encima** · **270,00** gamma flip + muro put (**trampilla**) |
| **Vehículo** | 🚫 **OPCIONES VETADAS** — `bidask_ok_pct = 0,0000`, el spread NO es medible. Acciones o no-trade |
| **Corea** | **exposición directa NULA** (doctrina de la casa). No se fabrica canal |

### ⚠️ CORRECCIÓN sobre la fase anterior (verificada, no opinión)

El mapa gamma se **recomputó a las 07:31:56 ET** y dos etiquetas cambiaron respecto a lo publicado antes:

| campo | valor publicado antes | **valor vivo 07:31:56** | consecuencia |
|---|---|---|---|
| `abs_wall` | 280,00 (pin) | **275,00 tipo `pin`** | el pin está **donde cotiza el spot** (−0,44 %), no arriba |
| `put_wall_kind` | (no publicado) | **`trampilla`** en 270,00 | perder 270 **acelera**, no amortigua |
| `flip` | 269,72 | **270,03** | irrelevante (mismo nivel), pero se cita el vivo |

**Consecuencia dura e inmediata:** OI monstruo a ±1 strike del spot = **PIN** → **prohibido 0DTE COMPRADO en la zona 275** (doctrina `oi-magnets-protocol`). Y la etiqueta `trampilla` del 270 cambia la Ficha B: debajo de 270 no se promedia, se sale.

---

## 0. Procedencia y latencia de cada número

| dato | fuente | latencia | **medida hoy** |
|---|---|---|---|
| **spot 276,22** | Finnhub WS → `data/rt_last_AMZN.txt` | **tiempo real** | tick 07:31:38 ET |
| **barras 1m/5m/15m** | Intrinio vía `provider_bridge` → `data/bars_amzn_ibkr.txt` | **~16 min de retraso — MEDIDO** | última barra **07:19**, reloj 07:35 → **15,9 min**. No es premercado fino: es el feed |
| **cadena** (OI, gamma, delta, IV) | Polygon `/v3/snapshot/options` → `raw/chain_amzn.json` (bajada 06:50 ET) | 15 min **+ el OI es el del CIERRE DEL VIERNES** | 710 contratos, 11 vencimientos |
| **bid/ask de opciones** | — | — | **NO EXISTEN.** `data/opt_chain_amzn.txt` cabecera 07:34:54: `bidask_ok_pct 0.0000`. **Sin esto no hay gate de spread** |
| **mapa gamma** | `data/gex_snapshot.json` | recomputado **07:31:56 ET** sobre cadenas Polygon | flip 270,03 · abs_wall 275 pin |
| **flujo / darkpool / griegas de dealer** | Unusual Whales | **~59 h** (hueco de fin de semana; latencia intradía SIN MEDIR) | **nada de UW es de hoy** |
| **futuros NQ/ES** | yfinance (dato del orquestador, 06:41 ET) | **~10-12 min declarados** | NQ −0,613 % · ES −0,033 % |
| **Corea** | Naver | **delay 0 medido** | KODEX 200 −8,93 % · KOSPI índice −4,88 % |
| **IBKR / TWS** | — | — | **NO USADO — prohibido esta semana** (orden 2026-08-02). Cero conexiones a 4001/4002/7496/7497 |

**Lo que hoy NO se puede publicar:** straddle ATM capturado, spread de opciones, volumen premercado, y cualquier probabilidad direccional medida (§6).

---

## 1. FOTO

### 1.1 Precio

| campo | valor | fuente |
|---|---|---|
| **spot** | **276,22** | Finnhub WS, tick 07:31:38 ET |
| cierre RTH viernes | **271,3457** (barra 15:59) | `bars_amzn_ibkr.txt` |
| cierre extendido viernes (19:59) | 270,29 | mismas barras |
| cierre viernes según UW | 271,58 | UW `/max-pain` `close` |
| **premarket %** | **+1,80 %** vs RTH · +1,71 % vs UW | — |
| apertura premarket | 274,05 (04:00 ET) | barras |
| **rango premarket** | **273,77 – 276,66** (2,89 = **1,05 %**) | barras 04:00–07:19 |
| **volumen premarket** | **SIN DATO** | la columna volumen es **0 en las 1.608 filas**. No se inventa un cero |

**El contexto que lo explica todo: AMZN presentó resultados el 30-jul a las 16:30 ET** (`data/finviz_amzn.txt`: `earnings_date=7/30/2026 4:30:00 PM`). El viernes 31-jul abrió con hueco **+12,52 %** y cerró **+15,51 %** con volumen **113,2 M contra 48,2 M de media (rel. volumen 2,37)**. **Toda la cadena que se lee hoy se construyó ANTES de ese salto: el libro está descolocado y hay que leerlo sabiéndolo.**

### 1.2 Bollinger + RSI (doctrina: obligatorio antes de cualquier orden)

⚠️ Valores calculados sobre la última barra **07:19** — llevan **15,9 min medidos** de retraso. La serie de 15m encadena premercado con sesión regular, así que **el RSI de 15m está inflado por el hueco de resultados**: no es comparable con un RSI de sesión limpia.

| TF | BB(20,2) media | banda sup | banda inf | **%B** | ancho | **RSI(14)** | ATR(14) | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **1m** | 276,01 | 276,53 | 275,48 | **0,698** | 0,38 % | **55,3** | 0,197 | 1.608 |
| **5m** | 275,91 | 276,75 | 275,07 | **0,681** | 0,61 % | **58,6** | 0,439 | 338 |
| **15m** | 274,00 | 278,91 | 269,09 | **0,726** | 3,58 % | **73,6** | 0,802 | 117 |

**Lectura:**
- **Ninguna banda reventada** (%B < 1 en los tres marcos) → **no hay band-walk** y **no hay veto de rebote elástico en contra**.
- Los tres %B están en **0,68–0,73**: el precio está en el tercio alto de su banda en todos los marcos **pero sin tocarla**. Eso no es fuerza, es **deriva dentro del rango**.
- El 15m con **RSI 73,6** y banda de **3,58 % de ancho** dice lo único relevante: **el movimiento grande YA OCURRIÓ el viernes.** Perseguir el largo aquí es comprar en el techo del rango premercado.
- **Buffer mínimo de stop** = 1 ATR de 15m = **0,80 $**; si se confirma en 5m, 0,44 $.

### 1.3 Fuerza — últimas 8 velas

**1m (07:12 → 07:19):** 276,30 · 276,00 · 275,86 · 275,89 · 275,85 · 275,93 · 275,94 · 276,22
→ rango de **45 centavos en 8 minutos**. Bajó a 275,85, recuperó. **El precio está PARADO.**

**5m (06:40 → 07:15):** 276,27 · 276,05 · 276,00 · 276,13 · 275,78 · 276,25 · 275,86 · 276,22
→ ocho velas dentro de **49 centavos**. Cero impulso, cero dirección.

**15m (05:30 → 07:15):** 275,36 · 275,38 · 275,87 · 275,93 · 276,27 · 276,13 · 275,86 · 276,22
→ **+0,86 en 1h45**: escalera lenta, sin aceleración.

**El máximo del premercado (276,66) se marcó y NO se ha vuelto a superar.** Rechazo suave, no giro.

> **VEREDICTO DE FUERZA: NEUTRA — deriva alcista sin impulso, con el techo premercado intacto.** El precio lleva más de una hora dentro de 50 centavos alrededor del strike 275. **Eso no es indecisión: es un PIN funcionando** (§2.4).

---

## 2. CADENA DE OPCIONES EN PROFUNDIDAD

Fuente: `raw/chain_amzn.json` — 710 contratos, **11 vencimientos vivos**: 03/05/07/10/12/14/21/28-ago + 04/11/18-sep. OI = **cierre del viernes**. Volumen = **sesión del viernes**.

> ⚠️ **AVISO DE COBERTURA:** el fichero que lee la flota (`data/opt_chain_amzn.txt`) trae **2 de los 11 vencimientos** (`provider_bridge.py`, `NEAR_EXPS=2`). El mensual del **21-ago, donde vive el 34 % de todo el OI de calls de AMZN**, no lo ve ningún consumidor de la flota. Este informe lo recupera.

### 2.1 OI y volumen por strike — vencimiento de HOY (0DTE 03-ago)

| strike | dist % | call OI | call VOL (vie) | put OI | put VOL (vie) | net OI |
|---:|---:|---:|---:|---:|---:|---:|
| 262,50 | −4,97 % | 383 | 621 | 999 | 3.085 | −616 |
| 265,00 | −4,06 % | 4.897 | 8.258 | 2.457 | 11.368 | +2.440 |
| 267,50 | −3,16 % | 2.480 | 6.997 | 1.794 | 7.769 | +686 |
| **270,00** | **−2,25 %** | **6.981** | **26.184** | 2.082 | 16.532 | +4.899 |
| 272,50 | −1,35 % | 6.464 | 19.329 | 899 | 4.328 | +5.565 |
| **275,00 ★PIN** | **−0,44 %** | **4.911** | **17.244** | 695 | 2.165 | +4.216 |
| 277,50 | +0,46 % | 4.923 | 9.565 | 346 | 1.332 | +4.577 |
| **280,00** | **+1,37 %** | **7.631** | **21.449** | 497 | 1.037 | **+7.134** |
| 282,50 | +2,27 % | 2.779 | 4.129 | 423 | 1.562 | +2.356 |
| 285,00 | +3,18 % | 1.489 | 2.901 | 340 | 3.946 | +1.149 |
| 287,50 | +4,08 % | 870 | 1.822 | 141 | 3.500 | +729 |
| 290,00 | +4,99 % | 948 | 1.726 | 1.035 | 501 | −87 |

**El net OI es positivo (calls > puts) en 10 de 12 strikes.** El corredor **272,5–280 acumula 26.366 contratos** — un **cinturón**, no un muro único.

**Vencimiento 05-ago (miércoles), mismo tramo:** el único strike con OI de call relevante es **280 con 4.105** (y 6.067 de volumen el viernes). Confirma el 280 como el borde alto también fuera del 0DTE.

### 2.2 Reparto del OI respecto al spot — la cifra que pide el encargo

| alcance | OI total | **encima del spot** | de eso calls / puts | **debajo del spot** | de eso calls / puts |
|---|---:|---:|---|---:|---|
| **0DTE 03-ago** | 94.512 | **26.960 (28,5 %)** | 23.363 C / 3.597 P | **67.552 (71,5 %)** | 38.438 C / 29.114 P |
| 05-ago | 37.608 | 11.372 (30,2 %) | 8.395 C / 2.977 P | 26.236 (69,8 %) | 10.965 C / 15.271 P |
| todo agosto | 998.103 | 358.688 (35,9 %) | 341.016 C / 17.672 P | 639.415 (64,1 %) | 364.837 C / 274.578 P |
| **TODOS (11 vencs)** | **1.341.688** | **482.071 (35,9 %)** | 461.580 C / 20.491 P | **859.617 (64,1 %)** | 498.959 C / 360.658 P |

**Cómo se lee y cómo NO:**
- **71,5 % del OI de hoy está DEBAJO del spot. Eso NO es bajista.** De esos 67.552, **38.438 son CALLS ya dentro del dinero** — residuo del hueco de resultados, compradas cuando AMZN valía 235–271, hoy casi delta-1.
- Lo informativo de verdad: **por encima del spot solo hay 3.597 puts en todo el 0DTE frente a 23.363 calls.** Por arriba **no hay protección vendida que el creador tenga que defender**: el techo lo pone la gamma, no un muro de puts.
- **Ratio P/C de OI:** 0DTE **0,529** · 05-ago 0,943 · 07-ago 0,730 · 10-ago 0,507 · **21-ago 0,294** · 28-ago 0,262 · 18-sep 0,344. **El libro de AMZN es estructuralmente de calls.**

### 2.3 El mensual del 21-ago — el ancla del mes (invisible para la flota)

451.494 calls contra 132.890 puts (**P/C 0,294**):

| strike | dist % | call OI | put OI | qué es |
|---:|---:|---:|---:|---|
| 320,00 | +15,8 % | **45.640** | 0 | **la apuesta viva del mes** |
| 310,00 | +12,2 % | 30.598 | 10 | apuesta viva |
| 295,00 | +6,8 % | 32.872 | 326 | apuesta viva |
| **280,00** | **+1,4 %** | **35.567** | 2.151 | refuerza el muro de hoy |
| 270,00 | −2,3 % | 43.929 | 4.467 | ITM heredada |
| 260,00 | −5,9 % | 44.747 | 7.704 | ITM heredada |
| 250,00 | −9,5 % | 38.804 | 15.791 | ITM heredada |
| 230,00 | −16,8 % | 3.183 | **20.204** | cobertura de cola |
| 220,00 | −20,4 % | 3.551 | **27.691** | cobertura de cola |

Las calls de 250–270 son ITM heredadas. **Lo vivo y direccional son las 45.640 calls del 320 y las 30.598 del 310.** Los puts vivos están a **−17 %/−20 %**: **cobertura de cola, no una apuesta a que AMZN caiga hoy.**

### 2.4 Muros, PIN y gamma flip

**Perfil GEX $/1 % por strike** (todos los vencimientos, gamma **MEDIDA** de Polygon, spot 276,22; call +, put −):

| strike | GEX $/1 % | acumulado |
|---:|---:|---:|
| 250,00 | −22,5 M | — |
| 260,00 | −10,1 M | — |
| 262,50 | −4,4 M | — |
| 265,00 | +7,8 M | — |
| **267,50** | **−7,4 M** | último negativo |
| **270,00** | **+103,1 M** | **← CRUCE DE SIGNO** |
| 272,50 | +41,3 M | |
| **275,00 ★** | **+157,3 M** | 2º mayor |
| 277,50 | +44,4 M | |
| **280,00 ★★** | **+194,4 M** | **el mayor del libro** |
| 282,50 | +22,9 M | |
| 285,00 | +72,9 M | |
| 290,00 | +59,5 M | |
| 295,00 | +47,5 M | |
| 300,00 | +45,6 M | |

**Suma de todos los strikes = +750,5 M $/1 %** — reproduce exactamente `mapa_todos_venc.net_gex_dollar1pct` = 750,8 M. **Régimen POSITIVO confirmado por reconstrucción independiente.**

**El gamma flip: tres métodos independientes lo ponen en 270.**

| método | fichero / cálculo | flip |
|---|---|---:|
| reprecio de spot (gex_core) | `data/gex_snapshot.json` **07:31:56** | **270,03** |
| cumsum de GEX por strike | este informe, cadena completa Polygon | **270,00** |
| reprecio, 2 vencimientos cercanos | `mapa_opciones.json` → `mapa_2venc.flip` | **270,01** |
| reprecio, TODOS los vencimientos | `mapa_opciones.json` → `mapa_todos_venc.flip` | 256,19 ← *descartado: arrastra la cola de strikes lejanos* |
| cumsum sobre `greek-exposure/strike` de UW | `uw_barrido.json` | 250,00 ← *otra definición, otra fecha* |

→ **FLIP PUBLICADO = 270,00**, a **−2,25 %** del spot.

**Los niveles del día (coinciden `gex_snapshot.json` 07:31:56 y este informe):**

| nivel | qué es | etiqueta del motor | evidencia |
|---|---|---|---|
| **280,00** | **muro call + mayor GEX del libro** | `call_wall`, kind **`pin`** | +194,4 M · 7.631 callOI 0DTE · 4.105 el 05-ago · 35.567 el 21-ago |
| **275,00** | **★ `abs_wall` tipo PIN + POC — el spot está encima** | `abs_wall`=275, kind **`pin`**; `poc`=275 | +157,3 M · el spot lleva >1 h dentro de ±50 c |
| **270,00** | **gamma flip + muro put** | `put_wall`, kind **`trampilla`** | +103,1 M y el cruce de signo; 26.184 calls de volumen el viernes |
| 285 / 290 | imanes secundarios arriba | `magnets` | +72,9 M / +59,5 M |
| 267,50 | **1er strike de gamma NEGATIVA** | — | −7,4 M: debajo se ACELERA |
| 260 / 250 | pozos de gamma negativa | — | −10,1 M / −22,5 M |

**Test del PIN, hecho con dos criterios y publicados los dos (honestidad obligada):**
- **Criterio de OI (cociente):** OI del ATM±1 ≥ 3× la mediana de la banda ±3 % → da **1,06×** en el 275. **NO pasa.**
- **Criterio del motor de la casa:** `gex_core` clasifica `abs_wall 275,00 kind = "pin"`, `pin_risk_score = 175,16`, `fortress_pin = false`. Y `compass_amzn.json` (07:33) fija el nivel activo en **275,00 "Muro absoluto", `wall_kind: pin`, dist 0,44 %**.

> **Conclusión honesta: no hay pin de fortaleza (`fortress_pin=false`), pero sí hay PIN operativo en 275,00**, y el spot está encima. **Consecuencia dura: 0DTE COMPRADO en la zona 275 está PROHIBIDO** — se paga theta contra la mayor concentración de gamma del entorno. Lo mismo, con más razón, en el 280 (mayor GEX del libro). *(doctrina `oi-magnets-protocol` / `pin-and-expiry-mechanics`)*

### 2.5 Max pain — cuatro números y por qué difieren

| fuente | método | max pain 0DTE | vs spot |
|---|---|---:|---:|
| **este informe** | dolor sobre los **39 strikes** del 0DTE, OI del viernes | **262,50** | **−4,97 %** |
| `data/opt_chain_amzn.txt` (lo que ve la flota) | mismo cálculo, fichero recortado | 265,00 | −4,06 % |
| Unusual Whales | su propio `/max-pain` | 240,00 | −13,1 % |
| `mapa_opciones.json` | banda ±22 % | 275,00 | −0,44 % |

**Mi número es 262,50 y es ROBUSTO**: idéntico con banda ±10 %, ±22 % y sin banda (dolor mínimo 34,86 M$). **Tres de las cuatro fuentes ponen el max pain claramente por DEBAJO del spot.**

**Pero es el max pain de un libro PRE-RESULTADOS:** 262,5 era donde menos dolía cuando AMZN cotizaba a 235. **NO es un imán limpio para hoy y NO se opera hacia él.**

### 2.6 IV, skew y expected move

**IV por vencimiento** (Polygon, precios del cierre del viernes). Skew medido como **IV(put a −5 %) − IV(call a +5 %)**:

| venc | IV call ATM (K=275) | IV put ATM (K=275) | IV put −5 % (262,5) | IV call +5 % (290) | **skew** |
|---|---:|---:|---:|---:|---:|
| **03-ago (0DTE)** | 0,308 | **1,485** | 1,121 | 0,723 | **+0,398** ⚠️ |
| 05-ago | 0,261 | 0,802 | 0,677 | 0,420 | +0,258 |
| **07-ago** | 0,271 | 0,676 | 0,581 | 0,372 | **+0,209** |
| 10-ago | 0,235 | 0,540 | 0,501 | 0,316 | +0,185 |
| 12-ago | 0,228 | 0,503 | 0,461 | 0,306 | +0,154 |

⚠️ **La asimetría call/put al MISMO strike ATM (0,308 vs 1,485) es un ARTEFACTO, no una señal.** Polygon calcula la IV con el cierre del viernes y el subyacente de ese momento (271,58): el put del 275 cerró ITM y el call OTM. **El skew del 0DTE (+0,398) no vale.** El que vale es el de los vencimientos limpios: **+0,15 a +0,26, decreciente y estable.**

**Comparación transversal en el MISMO vencimiento (07-ago), sobre las 11 cadenas del directorio** *(cifras de la fase anterior, coherentes con mi método)*:

| GOOGL | **AMZN** | META | QQQ / SPY | AAPL | NVDA / SMH | INTC | NOK | MU |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| +0,282 | **+0,209** | +0,196 | +0,112 | +0,055 | −0,018 / −0,014 | −0,162 | −0,212 | −0,299 |

**AMZN tiene el 2º skew de puts más caro de la flota, solo por detrás de GOOGL.** Los semis (MU, INTC, NOK) tienen skew **INVERTIDO**: sus calls valen más que sus puts. **Es la rotación del viernes vista desde la volatilidad: se paga por PROTEGER las megacaps que subieron y por PERSEGUIR los semis que se hundieron.**

**Expected move de HOY — dos métodos limpios y uno descartado:**

| método | fuente | EM 1σ | rango sobre 276,22 |
|---|---|---:|---|
| **IV ATM 05-ago (0,3733) escalada a 1 sesión** (√(1/252)) | UW term-structure (cierre viernes) | **±2,35 % = ±6,50 $** | **269,72 – 282,72** |
| movimiento implícito del 03-ago (dte 3) | UW term-structure | ±2,22 % = ±6,13 $ | 270,09 – 282,35 |
| IV ATM 0DTE Polygon (1,02) | `mapa_opciones.json` | ±3,29 % | ← **descartado**: la IV de un 0DTE al cierre de la víspera se dispara por convexidad; no es la valla del día |

**VALLA PUBLICADA: 269,72 – 282,72 (±2,35 %).** Los dos métodos limpios coinciden dentro de 0,13 pp.

> **CONFLUENCIA QUE MANDA EL DÍA** (skill `expected-move-envelope`): el **borde inferior 269,72 cae ENCIMA del gamma flip y del muro put (270,00)** y el **borde superior 282,72 cae justo por encima del muro call (280,00)**. Cuando el borde de la valla y un muro coinciden, **ese es el mejor fade del día. AMZN tiene las dos confluencias, una a cada lado.**

---

## 3. FLUJO

> **⚠️ NADA DE ESTA SECCIÓN ES DE HOY.** UW no ha publicado un solo dato del lunes: su print más reciente tiene **~59 h** (`uw_barrido.json` → `latencia.VEREDICTO`: *"UW NO PUBLICA EN PREMARKET"*). Todo lo que sigue es **posicionamiento de partida del viernes 31-jul**, jamás flujo de hoy.

### 3.1 Premium neto firmado — AMZN fue el extremo alcista de toda la flota

| campo | AMZN | puesto entre los 11 nombres |
|---|---:|---|
| net call premium | **+137,3 M$** | 1º |
| net put premium | −8,7 M$ | puts netos **VENDIDOS** |
| **signed premium** (= call − put, *gotcha de la casa*) | **+146,0 M$** | **1º, el mayor de los 11** |
| net delta | +240.684 | — |
| net call vol / net put vol | +34.073 / −22.072 | — |
| **últimos 30 min** | **−2,2 M$** | **se giró en la campana** |

Contexto: NVDA +50,8 M$ · QQQ +31,1 M$ · SMH +4,3 M$ · **SPY −40,0 M$** · MU −117,1 M$ · AAPL −138,7 M$.

### 3.2 Ballenas — 200 alertas, ventana 31-jul 14:01→19:59 UTC

Premium: **calls 41,7 M$ · puts 14,4 M$**. Lado derivado (ask − bid): **calls +417 k$** (compra tenue) · **puts −3,9 M$** (puts **VENDIDOS**).

| hora UTC | tipo | strike | expiry | premium | **LADO** | v/OI | spot |
|---|---|---:|---|---:|---|---:|---:|
| 19:27:39 | call | 275 | **2026-11-20** | 1.776 k$ | **ASK (compra)** | 0,15 | 272,18 |
| 17:21:08 | call | 250 | 2028-12-15 | 1.290 k$ | MIXTO | 0,10 | 270,62 |
| 14:31:55 | call | 235 | 2027-03-19 | 1.254 k$ | **ASK (compra)** | 0,51 | 271,14 |
| 16:35:25 | call | 267,5 | 31-jul (0DTE) | 1.162 k$ | **BID (vende)** | 7,79 | 271,24 |
| 14:01:30 | call | 250 | **21-ago** | 1.147 k$ | **BID (vende)** ·sweep | 0,38 | 270,24 |
| 14:01:46 | call | 250 | **21-ago** | 1.127 k$ | **BID (vende)** | 0,38 | 270,54 |
| 14:02:44 | call | 250 | **21-ago** | 1.122 k$ | **BID (vende)** | 0,40 | 269,94 |
| 15:25:22 | call | 265 | 31-jul (0DTE) | 1.084 k$ | **BID (vende)** | 1,57 | 269,49 |
| 19:40:28 | call | 255 | 2026-12-18 | 996 k$ | **BID (vende)** ·sweep | 0,21 | 271,16 |
| 14:51:04 | call | 267,5 | 31-jul (0DTE) | 881 k$ | **BID (vende)** | 5,23 | 271,09 |
| 14:31:47 | call | 267,5 | 31-jul (0DTE) | 795 k$ | ASK (compra) | 4,65 | 270,39 |
| 14:18:22 | **put** | 272,5 | 07-ago | 714 k$ | **BID (vende)** ·sweep | **27,97** | 268,90 |

*(El campo `volumen` de UW es el volumen del CONTRATO en el día, no el tamaño de la alerta.)*

**Lectura: el viernes en AMZN se VENDIERON calls cercanas y se COMPRARON calls lejanas.** Los cuatro mayores prints de vencimiento corto (267,5 · 265 · 250-ago) son todos del **lado BID = el agresor VENDE**: recogida de beneficio y venta cubierta contra el hueco. Las compras de verdad están en **nov-2026, mar-2027 y dic-2028**: **tesis a largo, no combustible para hoy.** Y el put del 272,5 del 07-ago con **v/OI 27,97 también se vendió** → alguien cobró prima apostando a que AMZN **no baja de 272,5 esta semana**.

### 3.3 🗡️ ESPADA-BALLENA + JERARQUÍA DE CAPITANES — el punto que decide el sesgo

**Táctica de la casa, regla 11, literal:** 🐋 **BALLENA DE CALLS = TECHO LOCAL CERCA.** AMZN cerró el viernes con **+146,0 M$ de premium firmado, el mayor de los 11 nombres**, y con las mayores ballenas de calls cortas **vendidas**. Por la táctica, ese extremo de flujo de calls marca un **extremo local** y lo que se opera es la **reversión con scalp pequeño y seguro**, no la continuación. **Traducción: no se compra fuerza aquí.**

**Regla 12 — capitanes. Estado medido AHORA (Finnhub WS, ticks de 07:17–07:35 ET) contra cierre RTH del viernes de nuestras barras:**

| capitán | cierre RTH vie | **spot ahora** | **% premkt** | mapa gamma vivo (07:31:56) |
|---|---:|---:|---:|---|
| **QQQ** | 688,03 | **690,50** (07:35) | **+0,36 %** | régimen **POSITIVO** · POC/`abs_wall` **690,00 tipo pin** · `call_wall` 695 · flip 674,85 (−2,24 %) |
| **SPY** | 746,57 | **750,97** (07:21) | **+0,59 %** | régimen **POSITIVO** · `abs_wall` **751,00 pin** · `call_wall` 752 · **flip 748,99 → a solo −0,28 %** |
| **SMH** (capitán de semis) | 540,92 | **533,89** (07:34) | **−1,30 %** | régimen **NEGATIVO** · `abs_wall` **530,00 tipo TRAMPILLA** · flip 551,06 (+3,21 %) |

**Y el flujo del viernes de los capitanes:** tono de mercado (`market-tide`, última barra 16:10) **signed −160,1 M$** con net put premium **+144,6 M$** — abrió comprando calls (+72,7 M$ a las 09:30), se dio la vuelta antes de las 10:10 y **nunca volvió a positivo**. SPY signed **−40,0 M$**. QQQ signed **+31,1 M$**.

> ### VEREDICTO EXPLÍCITO: **la señal alcista de AMZN queda PRÁCTICAMENTE ANULADA.**
> El tono de mercado del viernes cerró en **−160,1 M$** y SPY en **−40,0 M$**. Regla 12: *"conflicto capitán vs tropa → el capitán PREVALECE y la señal del nombre queda prácticamente anulada; señal de nombre con capitán opuesto vigente = banner sin voz."*
> **En AMZN hoy NO hay voz alcista. Los +146 M$ del viernes son contexto, no gatillo.**
>
> **Matiz obligado (y es el dato más importante de la mañana):** los capitanes **no hablan con una sola voz**. QQQ signed +31,1 M$ contra SPY −40,0 M$; y ahora mismo **QQQ +0,36 % y SPY +0,59 % en premercado, mientras SMH cae −1,30 %**. Los tres están en caja: QQQ **pinneado en 690**, SPY **pinneado en 751 y a 0,28 % de su flip**, SMH **en gamma negativa sobre una trampilla**. Cuando los capitanes discrepan, **la única lectura firme es "sin dirección"** — que es exactamente lo que dice el mapa de AMZN.
>
> **El aviso que hay que vigilar: SPY está a −0,28 % de su gamma flip (748,99).** Es el nivel más frágil del mercado esta mañana. **Si SPY imprime debajo de 748,99, todo el mercado pasa a gamma negativa y la caja de AMZN deja de proteger.**

### 3.4 Dark pool — dónde están los bloques respecto al spot

Umbral 10 M$ · 80 prints en 3 sesiones. **Los prints "sucios"** (con `average_price_trade` / `prior_reference_price`) **no son precios ejecutables** — el print de 1.304.179 acciones "a 235,50" del 30-jul tenía el NBBO en **252,75/252,80**: es un fuera-de-secuencia y se descarta.

| precio | acciones | premium | n prints |
|---:|---:|---:|---:|
| **271,60** | 1.938.076 | 526,3 M$ | 12 |
| 267,25 | 1.000.000 | 267,4 M$ | 2 |
| ~~235,48~~ | ~~667.596~~ | ~~157,2 M$~~ | 3 | ← **descartado, fuera de secuencia** |
| 271,06 | 244.433 | 66,2 M$ | 4 |
| 270,79 | 168.000 | 45,5 M$ | 1 |
| 268,34 | 160.222 | 43,0 M$ | 2 |

**Sesgo medido por UW: `pct_encima = 0,0 %`** — ni una acción del volumen oculto por encima del cierre del viernes ni por encima del spot premercado. **Todo el bloque institucional se colocó entre 267,25 y 271,60**, es decir **debajo de donde cotiza AMZN ahora y encima del flip**.

**Lectura:** es un **suelo de referencia** que se solapa con la zona flip/muro-put (270), **no una resistencia**. Refuerza la Ficha B.

### 3.5 Cambio de OI — ¿abrían o cerraban?

Regla Kochuba sobre 60 contratos de AMZN: **27 apertura · 0 cierre · 6 churn · 27 mixto.** **Cero contratos de cierre** — igual que en los 660 contratos de los 11 símbolos del barrido: **el viernes NADIE cerró nada.** Los tres que más OI ganaron (`C 270`, `C 250`, `C 260` del 31-jul) son **calls ITM de un vencimiento que YA EXPIRÓ**: OI que hoy no existe. **No aportan nada al libro de hoy** — pero sí avisan de que **el reajuste del libro está pendiente** (§8, Riesgo 1).

### 3.6 Griegas de dealer (UW, cierre del viernes)

| net gamma | día previo | net delta | net charm | net vanna |
|---:|---:|---:|---:|---:|
| **+1.684.177** | +412.315 | +110.141.998 | +140.109.808 | +25.849.672 |

**AMZN cuadruplicó su gamma neta positiva el viernes** (+412 k → +1,68 M) y es, con NVDA, uno de los dos únicos nombres del barrido con gamma claramente positiva y creciente. **Confirma el régimen desde una fuente independiente.** *(UW no documenta la unidad: se compara entre símbolos, no se lee como dólares.)*

---

## 4. CONTAGIO COREANO — **NULO. Y lo digo sin fabricar un canal.**

**Doctrina de la casa (`~/CLAUDE.md`), literal:**
- Corea **DIRECTO**: MU SKHY DRAM SMH NVDA TSM ASML AMD INTC AVGO TXN QCOM EWY LRCX SNDK WDC STX
- Corea **INDIRECTO** (engranaje de índice): QQQ SPY XLK
- Corea **NULO**: AAPL MSFT META **AMZN** GOOGL TSLA NFLX NOK GLD SPCX

**AMZN está en la lista de exposición NULA. No hay canal directo y no voy a inventar uno.**

Lo único real, dicho con su tamaño:

1. **Canal mecánico de índice.** AMZN pesa en QQQ y SPY: si el índice se vende, los indexados venden AMZN. **Ese canal es QQQ, no Corea.** Y hoy apunta **al revés de la intuición**: con Corea −8,93 % (KODEX 200) / −4,88 % (índice KOSPI), **QQQ cotiza +0,36 % y SPY +0,59 % en premercado**, y **AMZN +1,80 %**. **El daño está CONTENIDO EN SEMIS** — el único capitán rojo es SMH (−1,30 %). AMZN está **restando** presión al índice, no recibiéndola.
2. **La narrativa AWS-memoria** (Amazon compra DRAM/HBM para sus centros de datos → memoria más cara = capex más caro) existe como relato fundamental. **No hay ninguna transmisión intradía medida en este repo.** Etiqueta: **narrativa, NO medida.** No entra en el plan y no se le asigna número.
3. **El estudio ya cerró la puerta general** (`kospi_nasdaq_estudio.md`): P(NDX cae ≥2 %) con KOSPI ≤ −5 % = **28,0 %** (en el 72 % de esos días NO hubo caída drástica); el open→close medio tras esos días es **+0,62 %** con P(rojo intradía) **46,3 % ≈ base 46,9 %**. **Todo el daño está en el HUECO: a las 09:30 el edge coreano se ha agotado.** Y para el perfil exacto de hoy (give-back tras rally récord, Wall Street sana): **NO DEMOSTRADO — n_eff 7-21, p 0,16-0,36, ninguna celda pasa BH-FDR.**

> **Lo único que Corea aporta hoy a AMZN es VOLATILIDAD DE MERCADO, y eso SÍ está medido:** P(|movimiento| ≥ 1 %) del índice pasa de **42 % a 71 %**, y la desviación típica sube **+56 %**.
> **Traducción operativa: día de RANGO ANCHO. Stops más anchos (mínimo 1 ATR de 15m = 0,80 $) y objetivos DENTRO de la valla.** Ni una palabra más sobre Corea en AMZN.

---

## 5. ÁRBOL DE ESCENARIOS

```
                        A M Z N   —   L U N E S   0 3 - A G O - 2 0 2 6
                spot 276,22  (Finnhub WS, tick 07:31:38 ET)  ·  premarket +1,80%
              regimen GAMMA POSITIVA  ·  net GEX +45,7M ($/1%: +126,1M)  ·  bias CALL
                    VALLA DEL DIA (EM 1s): 269,72 ────────────── 282,72   (+-2,35%)
                                             │
       ══════════════════════════════════════╪══════════════════════════════════════
            ↑  R A M A   A R R I B A         │        R A M A   A B A J O  ↓
       ══════════════════════════════════════╪══════════════════════════════════════
                                             │
  ┌──────────────────────────────────────────┴──────────────────────────────────────┐
  ↑                                                                                 ↓

277,50 [IMAN menor] 4.923 callOI · GEX +44,4M              275,00 ★★ abs_wall tipo PIN + POC ★★
  │   El spot ya esta encima: es peaje, no nivel.            │   GEX +157,3M (2o mayor del libro)
  │   PRINT: irrelevante, no se opera.                       │   EL SPOT ESTA PEGADO (-0,44%).
  ↑                                                          │   >>> 0DTE COMPRADO AQUI: PROHIBIDO <<<
280,00 ★★★ MURO CALL (kind pin) — MAYOR GEX ★★★             │   PRINT: 2 velas 5m CERRADAS < 275,00
  │   GEX +194,4M · 7.631 callOI 0DTE                        ↓       = primera senal real del dia
  │   4.105 el 05-ago · 35.567 el 21-ago                  272,50 [muro menor] 6.464 callOI · GEX +41,3M
  │   P(cierre>280) = 27,8%  ·  P(TOCAR) = 55,6%             │   Amortiguador. 1er toque suele rebotar
  │   ── 1er TOQUE: doctrina dice REBOTA (~70%, NO medido) ──│   (doctrina ~70%, NO medido)
  │   ── AQUI NO SE COMPRA. AQUI SE FADEA. ──                ↓
  │   >>> PROHIBIDO 0DTE COMPRADO <<<                     271,60 / 267,25 [DARKPOOL LIMPIO]
  │   PRINT p/ romper: 2 velas 15m CERRADAS > 280,00         │   ~2,9M acciones y ~790M$ colocados
  ↑                                                          │   el 0,0% del volumen oculto esta ARRIBA
282,72 [BORDE VALLA +1s]  <<< CONFLUENCIA con muro 280 >>>   ↓   => es SUELO de referencia, no techo
  │   El mejor fade del dia (expected-move-envelope)      270,00 ★★★ GAMMA FLIP + MURO PUT ★★★
  │   P(cierre>282,5) = 16,7%                                │   kind = TRAMPILLA (no amortigua: acelera)
  ↑                                                          │   270,03 gex_snapshot 07:31 / 270,00 cumsum
285,00 [IMAN]  GEX +72,9M · 1.489 callOI 0DTE                │   / 270,01 mapa 2vencs — 3 metodos coinciden
  │   ◄── OBJETIVO DE LA RAMA ARRIBA                         │   GEX +103,1M · debajo el perfil es NEGATIVO
  │   P(cierre>285) = 9,0%  ·  P(TOCAR) = 18,0%              │   P(cierre<270) = 16,9% · P(TOCAR) = 33,8%
  ↑                                                          │   <<< CONFLUENCIA con borde valla 269,72 >>>
290,00 [iman lejano] GEX +59,5M — FUERA de la valla          │   PRINT: 2 velas 15m CERRADAS < 270,00
       P(cierre>290) = 1,9%.  NO SE PERSIGUE.                ↓
                                                          267,50 [1er strike GAMMA NEGATIVA] GEX -7,4M
  INVALIDACION RAMA ARRIBA:                                  │   Cruzado esto YA NO AMORTIGUAN: se ACELERA
  2 velas de 15m CERRADAS por debajo de 275,00               ↓
                                                          265,00 2.457 putOI 0DTE
                                                             │   ◄── OBJETIVO DE LA RAMA ABAJO
                                                             │   P(cierre<265) = 4,0% · P(TOCAR) = 8,0%
                                                             ↓
                                                          262,50 [MAX PAIN 0DTE] robusto a toda banda
                                                                 PERO es max pain de un libro PRE-RESULTADOS
                                                                 (era el minimo con AMZN a 235).
                                                                 NO ES IMAN LIMPIO — no se opera hacia el.

                                                          INVALIDACION RAMA ABAJO:
                                                          recuperar 272,50 con 2 velas de 15m CERRADAS encima

  ════════════════ EL ESCENARIO CENTRAL, Y ES EL MAS PROBABLE ════════════════
      C A J A   2 7 0  ───  2 8 0      P(cerrar dentro) = 55,3%
      (40,8% si se usa la IV alta del call 280 del 0DTE, s=0,535 — se publican las dos)
      Gamma positiva = el creador VENDE los repuntes y COMPRA las caidas: COMPRIME el rango.
      Sin PRINT en un borde, la posicion correcta es NO-TRADE (regla 6 de la casa).
```

### De dónde salen exactamente las probabilidades del árbol

Todas las `P(...)` son **probabilidades RISK-NEUTRAL de la propia cadena**, calculadas aquí con Black-Scholes: `S = 276,22` (Finnhub vivo), **`σ = 0,3733`** (IV ATM del 05-ago de la term-structure de UW, la más limpia disponible), `T = 1/252` (una sesión), `P(cierre > K) = N(d₂)`. `P(TOCAR)` usa el principio de reflexión sin deriva, `≈ 2 × P(cerrar más allá)`.

- **Son reproducibles y son la opinión del MERCADO**, no inventadas.
- **NO son una medición direccional:** por construcción risk-neutral no hay deriva. Es la opinión del libro sobre la **DISPERSIÓN**, no sobre el rumbo.
- La elección de σ mueve el resultado **15 puntos** (caja 55,3 % con σ=0,3733 vs 40,8 % con σ=0,535). **Se publican las dos porque ocultarlo sería maquillar.**

---

## 6. PROBABILIDAD DE SUBIR O BAJAR HOY

### **P(AMZN sube hoy) = NO EXISTE. No hay ninguna medición direccional publicable para AMZN hoy.**

Y **no la relleno con un 50 %**. Esto es lo que hay, con su origen:

**(a) El propio motor de la casa se declara SIN LECTURA.** `data/compass_amzn.json`, escrito a las **07:33:49 ET**:

```
state = "CAJA / PIN"        dir = "flat"       prob = null
prob_source = "sin_lectura"   prob_n = 31      prob_lo = 0.2373
state_why  = ["gamma+ entre Muros, sin extremo: caja"]
level      = { price: 275.00, kind: "Muro absoluto", wall_kind: "pin", dist_pct: 0.44, printed: false }
overnight  = { score: -0.646, nq: -0.646, korea: null }
vix        = { vix: 15.97, band: "CALM", live: false }
```

**La brújula RECHAZA dar una probabilidad.** Es el comportamiento correcto (fail-loud) y es el dato más honesto del día. *(Ojo: `korea: null` — la brújula no está ingiriendo Corea; el contexto coreano de este informe entra a mano.)*

**(b) Lo que SÍ está medido, y dice "no operes la dirección".**
`data/compass_calib.json` (recalibrado hoy 04:01. `_meta`: 6.587 filas, 2.955 excluidas, **n_eff = bloques de mercado NO SOLAPADOS de 30 min con voto mayoritario de flota** → **ya corregido por correlación**, que es el requisito de la skill `measured-probability`). La celda que corresponde **exactamente** al estado de AMZN ahora (`CAJA / PIN` × 0 familias × gamma POS):

| celda | **n_eff** | n crudo | **WR a +15 min** | WR a +30 min | Wilson inferior |
|---|---:|---:|---:|---:|---:|
| **`CAJA / PIN\|f0\|POS`** | **31** | 107 | **32,3 %** | 38,7 % | **23,7 %** |
| `CAJA / PIN\|pool` | 32 | 144 | 31,3 % | 25,0 % | 13,3 % |
| `CAJA / PIN\|f1\|POS` | 15 | 30 | 46,7 % | 33,3 % | 15,2 % ← n_eff<30, no publicable |

**Interpretación literal: en este estado, seguir la flecha ACIERTA el 32,3 % de las veces a 15 minutos.** No es "no sabemos": es **"medido, y perder es lo probable"**. Con **n_eff = 31 supera el mínimo de la casa (n ≥ 30)** y el Wilson inferior (23,7 %) está **muy por debajo del 50 %**. **Es una probabilidad MEDIDA — y es una probabilidad de NO OPERAR.**

**(c) La cadena tampoco tiene opinión direccional.** `P(cerrar por encima del spot) ≈ 49,6 %` con σ=0,3733 — pero eso es **la definición de un modelo risk-neutral sin deriva**, no una medición. Publicarlo como "probabilidad de subir" sería **exactamente el 50 % de relleno que la casa prohíbe**. Lo digo y lo descarto.

**(d) La única probabilidad alta del repo está PODRIDA y la mato aquí.**
`data/calibration.json` contiene:
```
reclaim_wall|POSITIVO :  rate 0.889 · ci_low 0.719 · n 27 · wins 24 · trust TRUE
```
Sería la cifra perfecta para hoy (AMZN en régimen POSITIVO y el plan es un reclaim). **NO se puede usar.** Auditoría del ledger, hecha ahora:
```
data/calib_log.jsonl : 56 filas · 26 símbolos distintos
fechas = Counter({'2026-07-21': 56})        ← LAS 56 SON DEL MISMO DÍA
```
**Las 27 "muestras" son símbolos correlacionados de UNA SOLA SESIÓN: n_eff ≈ 1 día, no 27.** El flag `trust: true` es falso — `scripts/calibration_ledger.py` lo pone con `raw_n >= MIN_N`, contando **filas**, no muestra efectiva. Es el error exacto que la skill `measured-probability` prohíbe. **El 88,9 % NO se publica, NO se usa, y queda reportado como defecto del repo.**

**(e) Contexto macro: tampoco hay número.** `kospi_nasdaq_estudio.md` para el perfil de hoy: *"3 celdas, todas con n_eff 7-21, ninguna pasa BH-FDR; la central da 50,0 % de rojo y media −0,005 %"* → **NO DEMOSTRADO, n insuficiente.** Lo único medido es volatilidad: P(|mov| ≥ 1 %) 42 % → **71 %**, sd **+56 %**.

**(f) Franja horaria** (`data/timeofday_factors.json`): ventana dorada 09:45-10:30 → familia bollinger **WR 50 % (n=42, CI 36-64)**, familia cusum **WR 53 % (n=49, CI 39-66)**. **Ambos intervalos contienen el 50 %: la hora NO aporta edge direccional medible.** Sí es la mejor franja relativa de la sesión.

### Lo que sí se puede afirmar hoy, ordenado por solidez

| afirmación | estado | número |
|---|---|---|
| Día de RANGO ANCHO | **MEDIDO** | P(\|mov\| ≥1 %) 42 % → **71 %**, sd **+56 %** |
| Seguir la flecha en este estado PIERDE | **MEDIDO, n_eff = 31** | WR **32,3 %** a +15 min (Wilson lo 23,7 %) |
| AMZN cierra dentro de 270–280 | **RISK-NEUTRAL de la cadena** (no es medición) | **55,3 %** (σ=0,3733) · 40,8 % (σ=0,535) |
| **AMZN sube o baja hoy** | **SIN MEDICIÓN — NO EXISTE** | **—** |
| Corea empuja a AMZN | **NULO por doctrina** | — |
| Rebote en el 1er toque de muro | **DOCTRINA, NO MEDIDO** | ~70 % (etiquetado, no publicable como medición) |

---

## 7. PLAN OPERATIVO

### 7.0 VEHÍCULO — el gate se ejecuta ANTES de cantar nada

| chequeo | resultado |
|---|---|
| **Spread ≤ 5 % del premium** (regla 4) | 🚫 **NO VERIFICABLE.** `data/opt_chain_amzn.txt` cabecera 07:34:54: **`bidask_ok_pct 0.0000`**. Bid/ask = 0 en el 100 % de las 710 filas de Polygon. IBKR (que sí daría NBBO) está **prohibido esta semana** |
| **Presupuesto ≤ 200 $/contrato** | orientativo con **cierres del VIERNES** (obsoletos: AMZN ha subido +1,8 % desde entonces): 0DTE **280C 0,94 → 94 $** · 05-ago **280C 1,83 → 183 $** · 07-ago **285C 1,40 → 140 $** · 07-ago 280C 2,48 → 248 $ (fuera) · 0DTE 275C 2,04 → **204 $ (fuera)** · 0DTE 270P 2,84 → **284 $ (fuera)** |
| **Pin / gamma** | `abs_wall 275,00 kind pin` con el spot a **−0,44 %**, y el 280 es el mayor GEX del libro → **0DTE COMPRADO EN 275 Y EN 280: PROHIBIDO** |

> ## 🚫 OPCIONES VETADAS — acciones o nada.
> **No por el precio: por el SPREAD, que hoy no es medible.** La regla 4 no admite excepciones y sin NBBO no hay forma de saber si se paga un 3 % o un 20 %. Precedente de la casa: **DRAM con 8-20 % de spread = −15 % en el instante de entrar.**
> **Si durante la sesión aparece una fuente de NBBO de opciones**, el único candidato que pasaría presupuesto y evitaría los dos pines sería el **07-ago o 14-ago FUERA de 275/280** (p.ej. 07-ago 285C, 140 $) — **jamás un 0DTE en 275 o 280**.
> **Alternativa hoy: acciones al contado.** En TFSA no se shortea → **la rama bajista se gestiona NO ESTANDO DENTRO**, no vendiéndola.

### 7.1 Ventana horaria

| franja | qué se hace |
|---|---|
| **09:30 – 09:45** | **JAMÁS.** Subasta. Y hoy con más razón: valla ±2,35 % y sd medida **+56 %** |
| **09:45 – 10:30** | **Ventana de oro.** Es donde se busca el PRINT en un borde |
| 10:30 – 11:30 | válida si el print llegó tarde |
| **11:30 – 14:00** | **picadora.** Nada nuevo. Solo gestión |
| 14:00 – 15:45 | segunda oportunidad si la caja aguantó la mañana |
| 15:45 – 16:00 | cierre. Nada |

### 7.2 Las tres únicas fichas del día

**No hay ninguna entrada válida ahora mismo.** Las tres exigen **PRINT — 2 velas CERRADAS cruzando**. *"Está cerca" no existe.*

#### 🔴 FICHA A — fade del muro 280 (la de mayor confluencia)
- **Disparo:** el precio **toca 280,00 y RECHAZA**. Válido solo si es el **1er o 2º toque del día** y hay **2 velas de 5m cerradas de vuelta por debajo de 279,50**.
- **Por qué:** confluencia de **muro call (kind pin) + mayor GEX del libro (+194,4 M) + 7.631 callOI 0DTE + 35.567 en el mensual + borde superior de la valla (282,72)**. `expected-move-envelope` marca la confluencia valla+muro como **el mejor fade del día**.
- **Invalidación:** 2 velas de **15m cerradas por encima de 280,00** → el muro se rompió; se espera el **retest-y-rechazo** y el nivel **se invierte a soporte**. **La primera ruptura NO se opera.**
- **Objetivo:** 277,50 → **275,00** (el pin). Segundo, 272,50.
- **Vehículo:** acciones. **Sin opciones** (§7.0). Si no se puede vender en corto: **esta ficha es solo una razón para NO COMPRAR ARRIBA.**
- **Probabilidad:** P(TOCAR 280) = **55,6 %** (risk-neutral). Del rebote en el 1er toque **no hay medición: doctrina ~70 %, NO medido.**

#### 🟢 FICHA B — reclaim del flip 270 (la de mejor relación riesgo/premio)
- **Disparo:** AMZN **pierde 270,00 y lo RECUPERA** con **2 velas de 15m cerradas por encima**.
- **Por qué:** **flip (270,03 / 270,00 / 270,01, tres métodos) + muro put + GEX +103,1 M + borde inferior de la valla (269,72) + la zona de darkpool 267,25–271,60 donde se colocaron ~2,9 M de acciones el viernes, con el 0,0 % por encima.** Cinco confluencias.
- **Invalidación:** 2 velas de 15m cerradas **por debajo de 267,50** (1er strike de gamma negativa). ⚠️ **El motor etiqueta el put_wall 270 como `trampilla`**: debajo **NO amortigua, ACELERA**. Se sale y **NO SE PROMEDIA**.
- **Objetivo:** 272,50 → **275,00**. **NO se pide el 280**: habría que atravesar el muro intermedio y la doctrina lo prohíbe (post-mortem META 660C, 20-jul).
- **Probabilidad:** P(TOCAR 270) = **33,8 %**. **Del reclaim NO hay probabilidad publicable** — el 88,9 % de `calibration.json` está muerto por n_eff ≈ 1 (§6d).

#### ⚪ FICHA C — NO-TRADE (la más probable, y es una POSICIÓN)
- **Condición:** el precio se pasa la sesión entre **272,50 y 280,00** sin imprimir ningún borde.
- **Probabilidad del escenario: 55,3 %** (risk-neutral, σ=0,3733) — **es la rama más probable del árbol.**
- **Acción: NADA.** Gamma positiva = el creador vende repuntes y compra caídas: el rango se comprime y **se cobra decaimiento a quien persigue**. Regla 6: **en whipsaw, no entrar es la mejor decisión.** Y el motor de la casa **mide** que seguir la flecha en este estado gana el **32,3 %** (n_eff=31).

### 7.3 Reglas que aplican hoy sí o sí

1. **Gamma POSITIVA** → esto **NO** es la caja de whipsaw de gamma negativa; es una **caja de amortiguación**: los bordes **tienden a aguantar**, no a estallar. **Se fadea, no se persigue.** *(La caja frágil hoy es SMH: régimen NEGATIVO con trampilla en 530.)*
2. **PIN en 275 con el spot encima** → **prohibido 0DTE comprado ahí** (y en 280).
3. **Una tesis = un boleto.** AMZN largo + QQQ largo + XLY largo es la misma apuesta tres veces.
4. **Nunca comprar a través de un muro intermedio.** Desde 276,22, comprar "hacia el 285" pasa por el 280: **premium muerto**.
5. **Sin volumen premercado publicado** (columna a 0 en las 1.608 barras) → **no se puede confirmar nada con volumen**. Es un agujero declarado, no un cero.
6. **El PRINT se toma del tick de Finnhub, no de la vela**, mientras las barras lleven 15,9 min de retraso (§8, Riesgo 2).

---

## 8. LO QUE PODRÍA MATAR ESTA TESIS

### RIESGO 1 — El libro que estoy leyendo ya no existe
**Qué es:** todo el mapa (pin 275, muros 270/280, flip, max pain) se calcula con el **OI del cierre del viernes**, y el viernes AMZN se movió **+15,51 %** con volumen **2,37× la media**. Un libro construido con AMZN entre 235 y 271 puede **reordenarse entero en la primera hora**. Además `oi-change` mide **27 aperturas y 0 cierres**: nadie descargó nada, **el reajuste está pendiente**.
**Qué lo delata primero:** el **volumen de opciones por strike en la primera media hora**. Si el **285/290 empieza a operar múltiplos de su OI (v/OI > 2)** mientras el 280 no se mueve, el muro se está desplazando arriba y **la Ficha A caduca**. Segundo aviso: `data/gex_snapshot.json` recomputado tras la apertura — **si `abs_wall` deja de ser 275 o `call_wall` deja de ser 280, el árbol entero se reescribe.**

### RIESGO 2 — Los 15,9 min de retraso de las barras hacen llegar tarde el PRINT
**Qué es:** el PRINT es la **definición mecánica** de entrada en esta casa (2 velas CERRADAS) y las velas del repo vienen de Intrinio con **15,9 min medidos de retraso** — uniforme en toda la flota, no un artefacto del premercado. **Una confirmación de 2 velas de 15m puede llegar 45 minutos después del hecho.** Con una valla de ±2,35 %, en 45 min AMZN recorre la caja entera. Es el peligro nº 3 de la doctrina: **latencia = dinero.**
**Qué lo delata primero:** comparar `data/rt_last_AMZN.txt` (Finnhub, tiempo real) contra el cierre de la última barra. **Si divergen más de 1 ATR de 5m (0,44 $), las velas ya no describen el precio.** Mitigación: **confirmar en 5m (ATR 0,44) en vez de 15m**, asumiendo más ruido, y **tomar el nivel del tick, no de la vela**.

### RIESGO 3 — El capitán arrastra a AMZN aunque AMZN no tenga nada que ver
**Qué es:** el mapa de AMZN describe a AMZN **aislado**. Pero el tono de mercado del viernes cerró en **−160,1 M$**, SPY en **−40,0 M$**, y Corea cae **−8,8 %** en memoria. Si el índice se vende de verdad, los productos indexados **venden AMZN mecánicamente**: la gamma positiva **amortigua pero no sostiene**, y el 270 se pierde **sin que ninguna ballena de AMZN haya hecho nada**. Es literalmente la regla 12.
**Qué lo delata primero — y hoy tiene nombre y número:** **SPY está a solo −0,28 % de su gamma flip (748,99), con el spot en 750,97.** Es **el nivel más frágil del mercado esta mañana**. **Si SPY imprime debajo de 748,99, todo el mercado pasa a gamma negativa, la caja de AMZN deja de proteger y la Ficha B se CANCELA** — no se compra el reclaim de un nombre con el capitán rompiendo. Avisos secundarios: **QQQ perdiendo su pin de 690,00**, y **SMH (ya en gamma NEGATIVA) perdiendo la trampilla de 530,00**.

---

## FUENTES Y LATENCIAS

| fuente | qué aporta | latencia |
|---|---|---|
| **Finnhub WS** (`data/rt_last_*.txt`) | spot AMZN 276,22 · QQQ 690,50 · SPY 750,97 · SMH 533,89 | **TIEMPO REAL** (ticks 07:17–07:35 ET) |
| **Intrinio** vía `provider_bridge` (`data/bars_amzn_ibkr.txt`) | barras 1m, BB, %B, RSI, ATR, rango premercado | **~15,9 min MEDIDOS HOY** (uniforme en la flota) |
| **Polygon** `/v3/snapshot/options` (`raw/chain_amzn.json`) | OI, gamma, delta, IV — 710 contratos, 11 vencimientos | **15 min · OI = cierre del viernes · SIN bid/ask** |
| **`data/gex_snapshot.json`** (07:31:56 ET) | flip 270,03 · abs_wall 275 pin · call_wall 280 · put_wall 270 trampilla · régimen | recomputado hoy sobre cadenas Polygon |
| **`data/opt_chain_amzn.txt`** (07:34:54) | verificación del gate de spread | `bidask_ok_pct = 0.0000` |
| **Unusual Whales** | flujo, darkpool, griegas de dealer, max pain, term-structure | **~59 h** (hueco de fin de semana; **latencia intradía SIN MEDIR**) |
| **`data/compass_amzn.json`** (07:33:49) · **`compass_calib.json`** (04:01) | estado CAJA/PIN · WR medido n_eff=31 | vivo |
| **`data/finviz_amzn.txt`** | fecha de resultados, hueco +12,52 %, rel. volumen 2,37 | 31-jul 15:57 |
| **Naver** (vía orquestador) | Corea: KODEX 200 −8,93 %, KOSPI índice −4,88 % | **delay 0 medido** |
| **yfinance futuros** (vía orquestador, 06:41) | NQ −0,613 % · ES −0,033 % | ~10-12 min declarados |
| **`kospi_nasdaq_estudio.md`** | veredicto Corea→Nasdaq | hoy 07:00 |
| **IBKR / TWS** | — | **NO USADO — PROHIBIDO esta semana** (orden 2026-08-02) |

**SEÑAL-SOLAMENTE. No es consejo financiero.**
