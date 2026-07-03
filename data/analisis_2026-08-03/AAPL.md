# AAPL — plan 2026-08-03 (lunes, premarket)

**Generado** 2026-08-03 07:20 ET · **SEÑAL-SOLAMENTE**: nada de este fichero envía una orden.
Base: `mapa_opciones.json/.md`, `uw_barrido.json/.md`, `kospi_nasdaq_estudio.md` (fase anterior) + cadena
completa de 11 vencimientos en `raw/chain_aapl.json` + barras 1m vivas + calibración medida del repo.

---

## CABECERA — lo que hay que saber en 20 segundos

| campo | valor |
|---|---|
| **Spot** | **310,00** (Finnhub WS, último print impreso 07:11:09 ET, edad ~5 min) |
| **Cierre viernes** | 308,67 (nuestras barras 1m, última vela RTH) · 308,91 (referencia UW) |
| **Premarket** | **+0,43 %** vs 308,67 · **+0,35 %** vs 308,91 |
| **Veredicto** | AAPL rebota tras el desplome de resultados y llega a la apertura **clavada en su imán de 310**, con gamma positiva y sin edge direccional medido. **Día de IMÁN + BORDES, no día de tendencia: se operan los bordes, nunca el centro.** |
| **P(subir hoy)** | **≈ 47-49 %** · **P(bajar) ≈ 51-53 %** · IC 95 % [41 %, 53 %] **INCLUYE el 50 % → no hay dirección medida** (procedencia en §6) |
| **Los 3 niveles** | **310,00** imán (pin/POC/max pain/mayor gamma) · **315,00** techo (muro call + borde valla) · **300,00** trampilla (muro put + único strike de gamma NEGATIVA + mínimo del viernes) |
| **Vehículo** | **OPCIONES VETADAS** (spread no verificable: bid/ask = 0 en el 100 % de la cadena). **ACCIONES.** |
| **Ventana** | 09:45–10:30. **Jamás 09:30–09:45.** |

---

## 1. FOTO

### 1.1 Precio y procedencia

| qué | valor | fuente | latencia |
|---|---|---|---|
| Spot | **310,00** | Finnhub WS `data/rt_last_AAPL.txt` | **sin retraso de proveedor**; es el ÚLTIMO PRINT y el premercado es fino → edad ~5 min |
| Barras 1m | último cierre **310,20** (07:00 ET) | Intrinio vía `provider_bridge.py` → `data/bars_aapl_ibkr.txt` | **~16 min medidos** (barra ep 07:00 escrita a las 07:16). El sufijo `_ibkr` del nombre es legado: **no hay IBKR** (prohibido esta semana) |
| NBBO subyacente | 309,99 / 310,20 | Intrinio → `data/nbbo_aapl.txt` | ~18 min (sello 06:58) |
| Cadena de opciones | 140 filas vivas / 840 completas | Polygon | **15 min delayed** y el **OI es del CIERRE DEL VIERNES** |
| bid/ask de opciones | **NO EXISTEN** (0 en el 100 % de las filas) | Polygon Starter no sirve `last_quote` | — |

### 1.2 Rango premarket

| campo | valor |
|---|---|
| Ventana | 04:00 → 07:00 ET, 164 barras 1m |
| Open / High / Low / Last | 309,60 / **310,60** / **307,40** / 310,20 |
| Rango | 3,20 $ = 1,03 % |
| **Volumen premarket** | **SIN DATO** — Intrinio devuelve `volume = 0` en el 100 % de las barras. No se inventa. |

### 1.3 Fuerza: Bollinger(20,2), %B y RSI(14)

| TF | n | BB media | BB sup | BB inf | ancho | **%B** | **RSI(14)** |
|---|---|---|---|---|---|---|---|
| **1m** | 1.605 | 310,158 | 310,721 | 309,595 | 0,363 % | **0,102** | **40,4** |
| **5m** | 341 | 309,075 | 311,005 | 307,144 | 1,250 % | **0,665** | **62,6** |
| **15m** | 117 | 308,085 | 310,038 | 306,133 | 1,268 % | **0,916** | **67,4** |

> **CAVEAT DURO, y sin él estos números engañan.** La ventana de la BB(20) de **15m abarca 07-31 18:00 → hoy 06:45**,
> es decir **after-hours del viernes + premercado de hoy**: cinta fina, sin subasta, sin volumen medible.
> No es la misma banda que verás a las 09:45. **La apertura RESETEA estas bandas.** Se publican porque la
> doctrina exige mirarlas siempre, no porque sean el %B de la sesión.

### 1.4 Las últimas velas (la "fuerza" de la doctrina)

15m, últimas 8:

| hora | O | H | L | C | Δ |
|---|---|---|---|---|---|
| 05:00 | 307,92 | 307,99 | 307,91 | 307,95 | +0,03 |
| 05:15 | 307,95 | 308,00 | 307,90 | 307,92 | −0,03 |
| 05:30 | 307,91 | 308,03 | 307,86 | 307,86 | −0,05 |
| 05:45 | 307,88 | 308,49 | 307,88 | 308,35 | **+0,47** |
| 06:00 | 308,34 | 309,77 | 308,34 | 309,50 | **+1,16** |
| 06:15 | 309,51 | 310,27 | 309,05 | 309,94 | +0,43 |
| 06:30 | 309,79 | 310,59 | 309,79 | 310,41 | +0,62 |
| **06:45** | 310,40 | **310,60** | 309,55 | **309,71** | **−0,69** ← mecha superior, RECHAZO de 310,60 |

**Lectura:** empuje limpio de 05:45 a 06:30 (+2,5 $ en 45 min) y **rechazo en 310,60** en la vela de 06:45,
justo en la banda superior de 15m (310,04). El %B de 15m ha caído de 1,000 a 0,916 en una vela. En 1m el
%B está en **0,102** (pegado a la banda inferior) con RSI 40,4: el impulso premarket está **agotado, no roto**.

**Doctrina Bollinger aplicada:** NO hay band-walk (haría falta la banda reventada a favor en 2-3 TF; aquí
15m 0,92 · 5m 0,67 · 1m 0,10 — divergen). Lo que hay es un **empuje premarket rechazado en el borde**.
Comprar aquí sería comprar contra la banda de 1m. **No se compra en el aire.**

### 1.5 El contexto que lo explica todo: AAPL viene de resultados

| dato | valor | fuente |
|---|---|---|
| Resultados | **30-jul-2026 16:30 ET (AMC)** | `data/earnings_falls.json` (screener Finviz) |
| Caída del día siguiente | **−9,87 %** (gap −8,58 %, −1,40 % adicional desde la apertura) | idem |
| Forma | **CASCADA (perdió la apertura)**, score 82, RVOL 2,32, drop/ATR 3,01 | idem |
| RSI diario al 31-jul | **39,24** | Finviz, vía el mismo fichero |
| Cierre RTH 30-jul → 31-jul | 333,45 → 308,67 = **−7,43 %** | nuestras barras 1m |
| Mínimo del viernes | **300,06** — tocó el 300 y aguantó | nuestras barras 1m |

**Hoy NO hay riesgo de resultados** (ya pasaron). Todo lo que está en el mapa por encima de 325 es
**residuo pre-resultados**, no un imán vivo.

---

## 2. CADENA DE OPCIONES EN PROFUNDIDAD

Fuente: `raw/chain_aapl.json` — **840 contratos, 11 vencimientos vivos** bajados directos de Polygon.
(El fichero que lee la flota, `data/opt_chain_aapl.txt`, solo trae **2 de 11** vencimientos por
`provider_bridge.py NEAR_EXPS = 2`: **no ve el mensual del 21-ago**, que es donde vive el ancla del mes.)

### 2.1 Peso de cada vencimiento

| vencimiento | contratos | OI total | volumen del VIERNES | reparto OI encima del spot |
|---|---|---|---|---|
| 2026-08-03 (**0DTE**) | 94 | 118.756 | 276.052 | 57,3 % |
| 2026-08-05 | 94 | 49.673 | 69.413 | 51,0 % |
| 2026-08-07 | 92 | 202.342 | 278.269 | 63,6 % |
| 2026-08-14 | 90 | 76.459 | 59.008 | 74,9 % |
| **2026-08-21 (mensual)** | 76 | **521.376** | 211.988 | 59,9 % |
| 2026-09-18 | 54 | **415.848** | 191.116 | 46,1 % |
| resto (5 vencs) | 340 | 96.885 | 104.457 | — |
| **TOTAL** | **840** | **1.481.539** | **1.190.303** | **57,2 % encima / 42,8 % debajo** |

**Respuesta cuantificada a "¿cuánto OI está por encima y por debajo del spot?":**
**57,2 % encima (847.777) y 42,8 % debajo (633.762)** sobre los 11 vencimientos.
En el 0DTE: **57,3 % encima / 42,7 % debajo**. El libro está **ligeramente sesgado a calls por encima**,
lo que en gamma positiva significa **techo amortiguado**, no gasolina.

### 2.2 OI y volumen strike a strike alrededor del spot — 0DTE (2026-08-03)

| strike | dist % | call OI | put OI | **OI total** | call vol (vie) | put vol (vie) |
|---|---|---|---|---|---|---|
| 292,50 | −5,60 | 5 | **7.512** | 7.517 | 26 | 9.834 |
| 295,00 | −4,79 | 774 | 2.481 | 3.255 | 1.822 | 9.428 |
| 297,50 | −3,99 | 417 | 3.811 | 4.228 | 1.028 | 8.061 |
| **300,00** | −3,18 | 4.315 | **6.112** | **10.427** | 12.423 | 23.550 |
| 302,50 | −2,37 | 3.826 | 1.816 | 5.642 | 20.216 | 7.406 |
| 305,00 | −1,57 | 3.675 | 1.843 | 5.518 | 32.852 | 5.050 |
| 307,50 | −0,76 | 2.122 | 763 | 2.885 | 14.381 | 1.497 |
| **310,00** | **+0,05** | **6.229** | **5.982** | **12.211** | 27.666 | 6.565 |
| 312,50 | +0,86 | 3.180 | 521 | 3.701 | 9.574 | 803 |
| **315,00** | +1,66 | **4.040** | 1.214 | 5.254 | 13.160 | 1.514 |
| 317,50 | +2,47 | 2.474 | 247 | 2.721 | 7.090 | 270 |
| **320,00** | +3,28 | **3.522** | 1.507 | 5.029 | 10.080 | 1.606 |
| 322,50 | +4,08 | 2.814 | 765 | 3.579 | 4.944 | 295 |
| 325,00 | +4,89 | 2.024 | 1.175 | 3.199 | 3.694 | 1.438 |

**310,00 es el strike más gordo del 0DTE en la banda ±6 % (12.211 de OI) y está a +0,05 % del spot.**

### 2.3 Mensual 21-ago — el ancla que la flota no ve

| strike | dist % | call OI | put OI | total |
|---|---|---|---|---|
| 290,00 | −6,41 | 7.114 | 12.685 | 19.799 |
| **300,00** | −3,18 | 13.923 | **32.431** | **46.354** |
| **310,00** | +0,05 | **25.401** | 8.601 | 34.002 |
| 315,00 | +1,66 | 8.355 | **17.974** | 26.329 |
| **320,00** | +3,28 | **22.456** | 9.177 | 31.633 |
| 325,00 | +4,89 | 17.453 | 7.785 | 25.238 |
| **330,00** | +6,50 | **26.070** | 8.307 | 34.377 |
| **340,00** | +9,73 | **41.378** | 3.273 | 44.651 |

El mensual **repite exactamente los mismos tres pilares**: **300 (put), 310 (call), 320 (call)**.
Que dos vencimientos independientes coloquen los muros en los mismos strikes es la única razón por la
que se publican como niveles y no como ruido.

### 2.4 Muros, flip y régimen

| concepto | valor | método / fuente |
|---|---|---|
| **abs_wall** | **310,00** — tipo **pin** | `gex_core`, 11 vencimientos, banda ±22 % |
| **call wall** | 320,00 (todos los vencs) · 315,00 (solo 2 vencs) | idem |
| **put wall** | **300,00** (en los dos alcances) | idem |
| **POC** | **310,00** | idem |
| **imanes** | 300 / **310** / 320 | idem |
| **gamma flip** | **298,16** (11 vencs) · 304,15 (2 vencs) · 310,00 (cumsum, método UW) | `gex_core` reprecio ±15 % / cumsum |
| **dist. al flip** | **−3,97 %** (11 vencs) · −1,84 % (2 vencs) | — |
| **régimen** | **POSITIVA** (net GEX +0,434 B$/1 %; score casa **+139,9 M$/pt**; bias CALL) | `gex_core`, signo crudo; la paridad no determina (solo 19,3 % de pares coherentes) |
| **net DEX** | +3,77 B$ · `dex_sentiment` alcista · `dex_flow_impact` **mm_compra** | idem |
| **pin_risk_score** | 68,95 (11 vencs) / 78,19 (2 vencs) | idem |
| **¿PIN formal?** | **NO**: ratio OI(310) / mediana banda ±3 % = **2,32×**, umbral doctrina **3×** | `oi-magnets-protocol` (doctrina, no medido) |

**Perfil de gamma por strike (gamma MEDIDA de Polygon, convención dealer call+/put−, $ por 1 %):**

| strike | GEX |
|---|---|
| **300,00** | **−61,4 M$** ← el ÚNICO strike negativo relevante |
| 305,00 | +57,7 M$ |
| 307,50 | +24,9 M$ |
| **310,00** | **+114,9 M$** ← el mayor de toda la cadena |
| 312,50 | +30,2 M$ |
| **320,00** | **+104,1 M$** |
| 325,00 | +46,5 M$ |
| 330,00 | +41,1 M$ |
| 340,00 | +42,7 M$ |

**Esto es el plano del día en una imagen:** un **ancla de gamma positiva enorme en 310** (el dealer
amortigua, revierte a la media) y un **agujero de gamma negativa en 300** (por debajo de ahí el dealer
acelera). Entre 305 y 320 el creador te frena; por debajo de 300 te empuja.

### 2.5 Max pain

| vencimiento | max pain (banda completa) | max pain (banda ±22 %) | dist. vs spot |
|---|---|---|---|
| **2026-08-03 (hoy)** | **310,00** | **310,00** | **−0,05 %** |
| 2026-08-05 | 307,50 | 307,50 | −0,81 % |
| 2026-08-07 | 310,00 | 310,00 | −0,05 % |

> **DISCREPANCIA QUE HAY QUE DECIR EN VOZ ALTA.** El endpoint `/max-pain` de Unusual Whales da
> **332,50** para el vencimiento de hoy (`uw_barrido.md` §9, "+7,6 % por encima"). Recalculado aquí sobre
> el OI completo de Polygon del mismo vencimiento, con banda completa **y** con banda ±22 %, sale **310,00**
> en los dos casos. Y coincide con el max pain del mapa de la fase anterior (310,00, `mapa_opciones.json`).
> **Dos de tres fuentes independientes dicen 310; UW es el atípico.** La causa más probable: el OI
> pre-resultados de los strikes 327,5–340 seguía inflado en la foto de UW del viernes. **Se usa 310,00.**

### 2.6 IV, skew y expected move

| vencimiento | IV ATM call | IV ATM put | IV ATM media | IV 25Δ put | IV 25Δ call | **SKEW put−call** |
|---|---|---|---|---|---|---|
| **2026-08-03** | 0,5685 | 0,8375 | **0,7030** | 0,7345 (K 305) | 0,6446 (K 315) | **+8,99 pts vol** |
| 2026-08-05 | 0,4041 | 0,5104 | 0,4572 | 0,4798 (K 302,5) | 0,4270 (K 317,5) | +5,28 pts vol |
| 2026-08-07 | 0,3644 | 0,4422 | 0,4033 | 0,4350 (K 300) | 0,3798 (K 320) | +5,52 pts vol |

**Skew put fuerte y creciente al acercarse el vencimiento: +8,99 puntos de vol en el 0DTE.** La protección
está cara. Traducción operativa: **comprar puts hoy es pagar el seguro después del incendio** — el
desplome ya ocurrió el viernes.

**Expected move del día — CUATRO métodos, ninguno es un straddle capturado hoy:**

| método | valor | construcción |
|---|---|---|
| Straddle ATM del repo | **±1,746 %** = ±5,38 $ | `data/em_aapl.json`, K 307,5, archivo ≤15:55 del viernes |
| Term structure UW | **±1,761 %** = ±5,46 $ | `uw_barrido.json`, curva del viernes, expiry 03-ago |
| Straddle K=310 (cierre viernes) | ±2,14 % = ±6,63 $ | Polygon `day.close`: 2,78 call + 3,85 put. **Cota superior** (el contrato tenía 1 día más de vida y 310 no era exactamente ATM) |
| IV lognormal 1σ | ±2,26 % (a las 07:00) / **±1,92 % (a las 09:30)** | `S·IV·√T` con T = horas de calendario hasta el cierre / 8760 |

**Los cuatro caen entre 1,75 % y 2,26 %, y los dos independientes de straddle coinciden en 1,75 %.**
Se publica la valla como **±1,8 % ≈ ±5,6 $ desde 310,00 → banda 304,4 – 315,6**, con el aviso de que la
cota superior real es 317,5 si la IV abre más alta.

**Confluencia valla-muro (la que manda, skill `expected-move-envelope`):**
- **borde superior 315,6 ≈ muro call 315,00** → confluencia limpia. Es el techo del día.
- **borde inferior 304,4 ≈ flip de 2 vencimientos 304,15 y strike 25Δ put 305** → confluencia limpia. Es el suelo del día.
- **300,00 queda FUERA de la valla (−3,2 % = 1,8σ).** Llegar ahí hoy no es el caso base.

### 2.7 P/C ratios

| vencimiento | P/C de OI | P/C de VOLUMEN (viernes) |
|---|---|---|
| 2026-08-03 | 0,772 | 0,597 |
| 2026-08-05 | 0,938 | 0,464 |
| 2026-08-07 | 0,624 | 0,663 |
| **TODOS** | **0,608** | **0,575** |

El libro es **estructuralmente call-heavy** (P/C OI 0,61) y el viernes el volumen también fue call-heavy
(0,58) **pese a que el nombre se hundió**. Eso ya se ve en el mapa de calor de strikes de la casa
(`data/strike_heatmap_aapl.json`): dominancia CALLS de 4,9× en 301-310, **6,91× en 310-319** y **7,75× en
319-328**; dominancia PUTS solo por debajo de 301. **La caza del rebote se hizo con calls por encima de 310.**

---

## 3. FLUJO

> **ADVERTENCIA QUE MANDA SOBRE TODA ESTA SECCIÓN.** Ni un dato de Unusual Whales es de hoy: su print más
> reciente tiene **58,87 h** (medido a las 06:51 ET). Es el **posicionamiento de partida del viernes al
> cierre**, jamás el flujo de hoy. La latencia intradía de UW **sigue sin medir** — hay que repetir la
> sonda después de las 09:30.

### 3.1 Premium neto firmado — AAPL fue el extremo bajista de la flota

| campo | valor |
|---|---|
| `net_call_premium` | **−59,2 M$** |
| `net_put_premium` | **+79,5 M$** |
| **`signed_premium` = call − put** | **−138,7 M$** ← el más bajista de los 11 símbolos |
| `net_delta` | **−4.759.110** ← la única mega-cap con delta claramente negativa |
| `net_put_volume` | +115.847 contratos |
| **últimos 30 min** | **+8,9 M$ signed** ← **se dio la vuelta en la campana** |

**La lectura honesta:** el flujo bajista estuvo **cargado al principio del día** y **revirtió a positivo en
la última media hora**. Publicar solo el −138,7 M$ sería contar media película.

### 3.2 Ballenas — `flow-alerts`, ventana 31-jul 13:39 → 19:59 UTC, 200 alertas

| campo | calls | puts |
|---|---|---|
| Premium total | 30,8 M$ | **49,8 M$** |
| ask − bid (agresor) | +2,2 M$ | **+16,0 M$** |

**🐋 BALLENA DE PUTS, y de las claras**: el agresor pagó al ASK **+16,0 M$ netos en puts**. Doctrina de la
casa (táctica espada-ballena): **ballena de PUTS = piso local cerca → call en el fondo, vender en el rebote corto.**

**PERO — y esto es lo que separa el análisis del copiar-pegar — esa señal YA SE COBRÓ.**
AAPL hizo mínimo en **300,06** el viernes y está en 310,00: **+3,31 %**. La ballena de puts del viernes
marcó el suelo del viernes, no el de hoy. **Actuar hoy sobre ella es llegar tarde a una señal ya pagada.**

Las cinco ballenas de AAPL que importan:

| hora UTC | tipo | strike | expiry | premium | lado | V/OI | veredicto |
|---|---|---|---|---|---|---|---|
| 13:40:15 | call | 290 | 18-sep | **6,46 M$** | BID (agresor VENDE) | 0,34 | indeterminado |
| 13:39:13 | put | 330 | 31-jul | 5,03 M$ | MIXTO | 0,40 | expiró el viernes |
| **19:46:10** | **call** | **300** | **03-ago (HOY)** | **2,87 M$** | **ASK (agresor COMPRA)** | **309,13** | **APERTURA pura** |
| 14:17:41 | put | 300 | 07-ago | 1,69 M$ | ASK (compra) | 1,97 | **APERTURA** |
| 18:13:31 | put | 310 | 03-ago (HOY) | 1,61 M$ | **BID (agresor VENDE)** | 1,40 | **APERTURA** |

**Los dos que tocan HOY:**

1. **11.747 calls 300 de HOY compradas al ASK a las 15:46 ET del viernes** (V/OI = 309 → apertura pura),
   con el spot en 306,82 y pagando 7,75. Hoy con el spot en 310,00 valen ~10 de intrínseco: **+29 %**.
   Ese tenedor **tiene que monetizar hoy**. Consecuencia mecánica: el dealer está **corto** esas calls,
   ya cubierto con acciones (delta ≈ 0,9, gamma casi nula a 10 $ ITM). **No es combustible alcista nuevo;
   es oferta latente por encima.**
2. **2.773 puts 310 de HOY VENDIDAS al BID** (agresor vende, apertura) con el spot en 301,59. El dealer
   quedó **largo** esos puts → **largo gamma en 310**. Es exactamente el +114,9 M$/1 % del §2.4 y la razón
   mecánica de que 310 sea un imán y no un trampolín.

### 3.3 Dark pool — descriptivo y nada más

La `anti-overfit-killlist` mata el dark pool como SEÑAL (`dpi-lite`). Va aquí **sin score, sin gatillo, sin voz.**

| campo | valor |
|---|---|
| Prints 3 sesiones / limpios | 81 / **19** |
| Prints del viernes / limpios | 22 / **5** |
| Nivel top con prints LIMPIOS | **302,10** (3 prints, 52,5 % del volumen oculto) |
| Sesgo vs cierre viernes | **0,0 % encima** — todo el bloque limpio quedó por debajo |
| Sesgo vs spot premarket | **0,7 % encima** — el 99,3 % del volumen oculto está por DEBAJO de 310 |
| Bloques 30-jul @ 333,43 | 153.180 + 151.058 + 100.496 acciones — **pre-desplome, ya irrelevantes** |
| Bloque 31-jul 20:34 UTC @ 308,91 | 67.705 acciones, +20,9 M$ — cruce de cierre |

**Traducción:** las manos grandes se colocaron **por debajo** del precio actual (302-309). El precio de hoy
está **por encima** de donde negociaron. Es contexto, **no un muro y no una señal.**

### 3.4 Cambio de OI (Kochuba, viernes vs jueves)

29 APERTURA · **0 CIERRE** · 17 CHURN · 14 MIXTO de 60 contratos examinados. Los tres que más OI ganaron
(`C335 31-jul` +16.387, `C332.5 31-jul` +15.833, `P310 31-jul` +8.134) **expiraron el viernes**: no
existen hoy. **El OI intradía no existe en ningún proveedor; hoy solo se ve viernes contra jueves.**

### 3.5 Griegas de dealer (UW, cierre del viernes) — y el conflicto que no se tapa

| griega | AAPL | día previo |
|---|---|---|
| net gamma | **−25.837** | **+675.479** ← cruzó a NEGATIVA |
| net delta | +38.038.283 | — |
| **net charm** | **−542.187.408** ← el mayor arrastre de charm de la flota | — |
| net vanna | +46.243.449 | — |

> **CONFLICTO DE RÉGIMEN, DECLARADO Y NO RESUELTO.**
> `gex_core` sobre los 11 vencimientos de Polygon dice **gamma POSITIVA** (+0,434 B$/1 %, score +139,9 M$/pt).
> Unusual Whales, con su propio modelo de dealer, dice **gamma NEGATIVA** (−25.837, tras cruzar desde +675 k).
> **Son dos modelos distintos sobre el mismo libro y no tienen por qué coincidir.**
> Mi perfil strike a strike (§2.4) explica cómo pueden ser ciertos los dos a la vez: **+114,9 M$/1 % en 310
> y −61,4 M$/1 % en 300**. La suma es positiva, pero el signo local depende de dónde esté el precio.
> **Regla que se aplica en el plan: entre 305 y 320 se opera como gamma POSITIVA (reversión a 310);
> por debajo de 300 se asume gamma NEGATIVA (caja de whipsaw) y NO SE OPERA.**

**Charm −542 M** significa el mayor arrastre de decaimiento de delta de la tarde de toda la flota: la
presión de recobertura del dealer se concentra **después de las 13:30 ET**, no por la mañana.

### 3.6 JERARQUÍA DE CAPITANES — obligatorio y explícito

| capitán | spot ahora | vs cierre viernes | régimen | nivel del compás | veredicto |
|---|---|---|---|---|---|
| **QQQ** | 690,13 (Finnhub, 07:16) | 687,99 → **+0,31 %** | **NEG** (paridad contradice el signo crudo) | 690,00 "Muro call", **pin, IMPRESO 7 veces**, dist +0,02 % | `state` CONTINUACION, `dir` **FLAT**, `signal_kind` **transition_candidate**, `prob` **null** |
| **SPY** | 751,12 (Finnhub, 07:00) | 747,03 → **+0,55 %** | **INDETERMINADO** (las dos lecturas de paridad discrepan) | pin 750 el 04-ago | sin dirección publicable |
| **SMH** (capitán de semis) | **SIN FICHERO `rt_last_SMH.txt`** | — | NEG | abs_wall 500 | **SIN DATO en premarket** |

**Veredicto de jerarquía, dicho como manda la casa:**
**NINGÚN capitán apunta al revés que AAPL — pero ninguno apunta a nada.** QQQ está **clavado en su muro
de 690** (impreso 7 veces, `dir` FLAT, prob null) y SPY no tiene régimen publicable. **No hay anulación
por capitán y tampoco hay confirmación por capitán: AAPL va sola hoy.**
Consecuencia dura: **cualquier señal de AAPL hoy vale la mitad**, porque le falta el respaldo del capitán
que la doctrina exige. Y el capitán de semis está **mudo** (`data/rt_last_SMH.txt` no existe — hueco
conocido, otro agente lo está arreglando; **no se tapa con el spot delayed de la cabecera de la cadena
para fingir que hay dato**).

### 3.7 La rotación: AAPL es la más FLOJA de las mega-caps que suben

| símbolo | spot (Finnhub, ~07:16) | cierre viernes (UW) | premarket |
|---|---|---|---|
| AMZN | 276,30 | 271,58 | **+1,74 %** |
| GOOGL | 362,06 | 356,13 | **+1,66 %** |
| META | 563,20 | 556,71 | **+1,17 %** |
| **AAPL** | **310,00** | **308,91** | **+0,35 %** ← la más floja |
| QQQ | 690,13 | 687,99 | +0,31 % |
| NVDA | 199,30 | 200,75 | −0,72 % |
| INTC | 88,69 | 90,20 | −1,67 % |
| MU | 794,56 | 823,03 | **−3,46 %** |

Se repite **exactamente** la rotación del viernes (memoria abajo, mega-cap no-semi arriba). **AAPL está en
el lado ganador de la rotación pero es la que menos cobra de él.** Confirmación independiente desde el
compás de QQQ: AAPL aparece en `drivers_skipped` con **z = −0,5** — el motor la descarta por débil.

---

## 4. CONTAGIO COREANO — MEDIDO, no doctrina

La doctrina de la casa dice que AAPL tiene exposición **nula** al lead coreano (solo MU, SMH, INTC, NVDA,
TSM, ASML y demás semis lo tienen). **No me quedo en la doctrina: lo mido.**

**Método:** retornos diarios de cierre a cierre, join por **fecha de calendario local sin desplazamiento**
(Corea cierra 02:30 ET, 7 h antes de la apertura US → `KOSPI[D]` es información ya disponible en `US[D]`;
es la misma alineación validada en `kospi_nasdaq_estudio.md`, incluido su test de cordura). Series:
`^KS11` de `raw/IDX_KS11.csv` y `data/aapl_daily.csv` (2 años, yfinance).

| par | correlación | n |
|---|---|---|
| **KOSPI[D] → AAPL[D]** | **−0,0516** | **468** |
| KOSPI[D] → SOX[D] | +0,1985 | 486 |
| KOSPI[D] → QQQ[D] | +0,1442 | 486 |
| **beta(AAPL ~ KOSPI)** | **−0,042** | 468 |

Con n = 468, el error estándar de r es ≈ 0,046 → **t ≈ −1,11, p ≈ 0,27**. **La correlación de AAPL con
Corea es indistinguible de CERO, y su signo es NEGATIVO.** Sobre la misma ventana, el índice de semis
tiene **4 veces** más acoplamiento.

**Buckets condicionales (para no publicar solo la correlación):**

| condición | n | P(AAPL c/c verde) | P(AAPL open→close verde) | media open→close |
|---|---|---|---|---|
| KOSPI ≤ −3 % | **27** | 0,556 | 0,667 | +0,761 % |
| KOSPI ≤ −4 % | **16** | 0,562 | 0,688 | +1,148 % |
| KOSPI ≤ −5 % | **13** | 0,462 | 0,615 | +1,157 % |

**Los tres buckets tienen n < 30 → n INSUFICIENTE. No se publica probabilidad con ellos.** Se citan como
conteo crudo y punto. (Lo poco que insinúan, además, apunta al ALZA, no a la baja.)

### Veredicto de contagio

> **La exposición de AAPL al desplome coreano de esta madrugada es NULA, y ahora está MEDIDA
> (r = −0,05 sobre n = 468, p ≈ 0,27), no supuesta.** No hay canal de transmisión que fabricar: AAPL no
> compra memoria como insumo dominante ni cotiza el ciclo DRAM. **Ni una línea del plan de hoy debe
> cambiar por el KODEX 200 −8,93 % ni por el KOSPI −5,1 %.**
>
> Lo único coreano que le llega es **de segunda mano y a favor**: la rotación defensiva que saca dinero de
> los semis (MU −3,46 %, INTC −1,67 %) y lo mete en la mega-cap no-semi. **Esa rotación es el único motivo
> por el que AAPL está verde en premarket, y es también su principal fragilidad** (§8, riesgo 3).
>
> Y el estudio de la fase anterior ya cerró la puerta al lado macro: tras KOSPI ≤ −5 % el daño está **en el
> hueco de apertura** (gap medio QQQ −0,90 %) y el open→close medio es **+0,62 %** con P(rojo intradía)
> 46,3 % ≈ base 46,9 %. **A las 09:30 el edge coreano se ha agotado.** Y hoy el NQ está solo −0,61 %.

---

## 5. ÁRBOL DE ESCENARIOS

Probabilidades del árbol: **riesgo-neutral**, derivadas de la **IV MEDIDA por Polygon en cada strike**
(cierre del viernes, delayed 15 min), repreciadas con S = 310,00 y T = horas hasta el cierre / 8760.
`P(termina) = N(d₂)` con la IV del strike OTM correspondiente (puts por debajo, calls por encima —
así se respeta el skew). `P(toca) = 2 × P(termina más allá)` por principio de reflexión, GBM sin deriva:
**eso último es MODELO, no medición.**
**Sesgo conocido y declarado: la probabilidad riesgo-neutral SOBREESTIMA la cola bajista** (prima de
riesgo de varianza + skew put de +8,99 pts). Los números de abajo del imán son un **techo**, no una
expectativa.

```
                          A A P L   —   L U N E S   2 0 2 6 - 0 8 - 0 3
                     spot 310,00  ·  Finnhub WS 07:11 ET  ·  premarket +0,35%
                          regimen GAMMA POSITIVA entre 305 y 320
                          valla del dia +-1,8%  =  304,4  ...  315,6

   ================================ RAMA ARRIBA  ^ ==============================

     320,00  [MURO CALL - todos los vencs]  GEX +104,1 M$/1%
       ^     OI 0DTE call 3.522  ·  OI 21-ago call 22.456     FUERA DE LA VALLA
       |     P(cierra encima) 7,9%   P(toca) 15,8%
       |     >> PROHIBIDO comprar a traves de este muro (regla del muro intermedio)
       |
     317,51  [borde valla - metodo IV]      P(cierra encima) 12,0%
       |
   +---------------------------------------------------------------------------+
   | 315,00  [MURO CALL 2 vencs] + [BORDE SUPERIOR DE LA VALLA 315,6]          |
   |   ^     CONFLUENCIA VALLA+MURO = el mejor fade del dia                    |
   |         OI 0DTE call 4.040 · OI 21-ago put 17.974 (alguien compro 1,67 M$)|
   |         P(cierra encima) 21,0%   P(TOCA) 42,0%                            |
   |         OBJETIVO de la rama alcista. Es TECHO, no trampolin.              |
   |         PRINT que confirma ruptura: 2 velas de 5m CERRADAS > 315,00       |
   |         + retest-y-rechazo. Sin eso, el 1er toque REBOTA (~70%, doctrina). |
   +---------------------------------------------------------------------------+
       |
     312,50  [flip gamma cumsum 0DTE+05-ago]  OI 3.701
       |     P(cierra encima) 33,1%   P(toca) 66,2%
       |     Primer objetivo si el iman se rompe al alza.
       |
  =============================================================================
  ####  310,00   I M A N   ####   abs_wall (pin) · POC · MAX PAIN 0DTE 310,00
  ####  spot     ############     GEX +114,9 M$/1% (el mayor de la cadena)
  ####           ############     OI 0DTE 12.211 (6.229 call + 5.982 put)
  ####           ############     OI 21-ago 34.002 · impreso 8 veces (compass)
  ####           ############     P(cierra encima) 48,6% / debajo 51,3%
  ####           ############     ratio PIN 2,32x < 3x -> NO es pin formal,
  ####           ############     pero pin_risk_score 68,95: aqui la theta MATA.
  =============================================================================
       |
   ================================ RAMA ABAJO  v ===============================
       |
     307,50  [minimo premarket 307,40]  OI 0DTE 2.885 (el mas FINO de la banda)
       v     P(cierra debajo) 38,7%   P(toca) 77,5%
       |     Nivel de paso, NO de decision. No se opera.
       |
   +---------------------------------------------------------------------------+
   | 305,00  [BORDE INFERIOR VALLA 304,4] + [flip 2 vencs 304,15]              |
   |   v     + strike 25-delta put · GEX +57,7 M$/1% (todavia POSITIVO)        |
   |         OI 0DTE 5.518  ·  P(cierra debajo) 25,6%   P(TOCA) 51,1%          |
   |         CONFLUENCIA VALLA+FLIP = el suelo del dia.                        |
   |         PRINT que confirma REBOTE: tocar 305,00 y 2 velas de 1m CERRADAS  |
   |         de vuelta POR ENCIMA de 305,00.  <<< LA UNICA ENTRADA DEL DIA     |
   +---------------------------------------------------------------------------+
       |
     302,10  [nivel dark pool limpio: 3 prints, 52,5% oculto]  DESCRIPTIVO
       v     P(cierra debajo) 16,3%   P(toca) 32,6%
       |     Sirve de STOP, no de tesis (killlist: dark pool no es senal).
       |
   +---------------------------------------------------------------------------+
   | 300,00  [MURO PUT] [TRAMPILLA] [UNICO strike de GAMMA NEGATIVA -61,4 M$]  |
   |   v     OI 0DTE put 6.112 · OI 21-ago put 32.431 (el mayor de +-10%)      |
   |         MINIMO DEL VIERNES 300,06 - el nivel ya se IMPRIMIO y AGUANTO     |
   |         FUERA DE LA VALLA (-3,2% = 1,8 sigma)                             |
   |         P(cierra debajo) 10,0%   P(toca) 19,9%                            |
   |         INVALIDACION TOTAL: 2 velas de 15m CERRADAS < 300,00              |
   |         -> el mapa cambia de signo -> CAJA DE WHIPSAW -> NO-TRADE         |
   +---------------------------------------------------------------------------+
       |
     298,16  [gamma flip - 11 vencimientos, gex_core]      FUERA DE LA VALLA
       v     Por debajo de aqui el dealer ACELERA en vez de frenar.
       |
     292,50  [mayor OI put del 0DTE: 7.512]   cola, no objetivo del dia
       v
```

**Resumen del árbol en una tabla:**

| rama | primer imán | muro a atravesar | flip | objetivo | invalidación | P(toca objetivo) | P(cierra más allá) |
|---|---|---|---|---|---|---|---|
| **ARRIBA ↑** | 310,00 (ya ahí) | **315,00** | 312,50 (cumsum) | **315,00** | perder 307,50 | **42,0 %** | 21,0 % |
| **ABAJO ↓** | 307,50 | **305,00** | 304,15 (2 vencs) | **305,00** | recuperar 312,50 | **51,1 %** | 25,6 % |
| **CENTRO (base)** | — | — | — | **310,00** | 2 velas 15m fuera de 305/315 | — | **P(305 < cierre < 315) = 53,4 %** |

**El escenario base tiene más probabilidad que las dos ramas juntas: 53,4 % de cerrar dentro de 305-315.**
Eso es exactamente lo que significa "día de imán".

---

## 6. PROBABILIDAD DE SUBIR O BAJAR HOY — de dónde sale cada número

**Cuatro fuentes, tres son medición y una es el propio mercado. Ninguna da edge.**

### 6.1 Calibración del repo (la que manda) — `data/compass_aapl.json`

```
state=CONTINUACION  dir=flat  candidate_dir=up
signal_kind = "no_predictive_edge"
prob        = null            prob_source = "sin_edge"
prob_n      = 52              prob_lo     = 0.3689
state_why   = "sin edge predictivo > azar: se observa la tendencia, flecha neutral"
```

Bucket de `data/compass_calib.json` (`_meta`: 6.587 filas, 2.955 excluidas, bloques de mercado **no
solapados** de 30 min, ledger contra barras 1m):

| bucket | n | n_eff | wr15 | wr30 | Wilson lo |
|---|---|---|---|---|---|
| `CONTINUACION\|pool` | **52** | **52** | **0,4423** | 0,5000 | **0,3689** |

**El propio motor de la casa declara que NO hay edge y devuelve `prob = null`.** Cumple la regla de oro:
*prohibido devolver 0, 0,5 o 50 cuando la verdad es "no sé"*. **Ese es el resultado primario.**

### 6.2 Base histórica del ticker — `data/aapl_daily.csv`, 2 años (n = 499, 2024-07-08 → 2026-07-06)

| bucket | n | **P(cierre > apertura)** | Wilson 95 % | media open→close | P(\|o→c\| ≥ 1 %) |
|---|---|---|---|---|---|
| BASE (todos) | 499 | **0,545** | [0,501 – 0,588] | +0,108 % | 0,367 |
| **gap > 0 (EL CASO DE HOY)** | **244** | **0,471** | **[0,410 – 0,534]** | **−0,053 %** | 0,336 |
| gap entre +0,1 % y +1,0 % (el tamaño exacto de hoy) | 158 | 0,462 | [0,386 – 0,540] | −0,002 % | 0,342 |
| gap < 0 | 254 | **0,614** | **[0,553 – 0,672]** ← este SÍ excluye el 50 % | +0,260 % | 0,398 |
| **día siguiente a una caída ≥ 5 %** | **3** | — | — | — | **n INSUFICIENTE** |

**Dos cosas honestas:**
1. El bucket que describe hoy (**gap arriba de +0,35 %**) da **47,1 %**, y su IC **[41,0 – 53,4] incluye el
   50 %** → **no es un edge, es una moneda con un pelo de fade**.
2. El bucket que describiría hoy con MÁS precisión (día siguiente a una caída ≥5 %) tiene **n = 3**.
   **n insuficiente. No se publica.** (Regla `measured-probability`: n_eff ≥ 30 o no sale.)
3. Nota de honestidad sobre el bucket que sí excluye el 50 %: es el de **gap ABAJO** (61,4 %). **Hoy no aplica.**

### 6.3 El propio mercado — riesgo-neutral desde la cadena 0DTE

`P(cierra > 310) = 48,6 %` · `P(cierra < 310) = 51,3 %` (IV medida por Polygon en cada strike, N(d₂)).

### 6.4 Lo que NO se usa

- La **prensa coreana**, el **KODEX 200 −8,93 %** y el **KOSPI −5,1 %**: correlación con AAPL medida en
  **−0,05 sobre n = 468, p ≈ 0,27** → cero (§4).
- El estudio Corea → Nasdaq: sus celdas que describen hoy tienen **n_eff 7-21** y **p 0,16-0,36**, ninguna
  pasa BH-FDR. **Su propio veredicto prohíbe derivar de ahí un P(cae hoy).**
- El **max pain 332,5 de UW**: contradicho por dos recálculos independientes (§2.5).

### VEREDICTO DE PROBABILIDAD

> **P(AAPL cierra por encima de su apertura) ≈ 47 % · P(por debajo) ≈ 53 %.**
> **IC 95 % [41 % – 53 %], que INCLUYE el 50 %.**
> **Dos métodos independientes convergen** — histórico 2 años condicionado a gap arriba (47,1 %, n = 244) y
> riesgo-neutral de la cadena (48,6 %) — **pero convergen en "no lo sé".**
> **Y la calibración propia de la casa lo dice sin rodeos: `no_predictive_edge`, `prob = null`, n = 52,
> Wilson lo = 36,9 %.**
>
> **No se publica dirección hoy en AAPL.** Lo que sí se publica son los **bordes** (§5), que **sí** tienen
> probabilidad con procedencia: P(toca 315) 42,0 % · P(toca 305) 51,1 % · **P(cierre entre 305 y 315) 53,4 %.**
> **El edge de hoy es la SELECTIVIDAD, no la dirección.**

---

## 7. PLAN OPERATIVO

### 7.0 VEHÍCULO — leer antes que nada

> ### 🚫 OPCIONES VETADAS — ACCIONES
>
> **Motivo 1 (bloqueante):** la regla 4 de la casa exige **spread < 5 % del premium ANTES de cantar**.
> Hoy el spread **NO ES CALCULABLE**: `bid = ask = 0` en el **100 %** de las 840 filas de la cadena
> (el plan Polygon no sirve `last_quote`) y **IBKR está prohibido esta semana** (orden 2026-08-02).
> **Sin NBBO de opciones no se aprueba ningún contrato. Punto.**
>
> **Motivo 2 (independiente, y también bloqueante):** el presupuesto es **≤ 200 $ por contrato**, y a
> precios del viernes **el ATM no cabe**: 0DTE 310 call = **278 $**, 0DTE 310 put = **385 $**.
> Lo único que cabría son loterías OTM sobre un nombre clavado en su imán: 312,5C = 187 $, 315C = 114 $,
> 305P = 164 $. **Comprar prima OTM contra un imán de +114,9 M$/1 % de gamma es pagar theta para que el
> dealer te la cobre.**
>
> **Motivo 3 (doctrina):** `pin_risk_score` 68,95 y el mayor OI del 0DTE (12.211) clavado a **+0,05 %** del
> spot. Aunque el test formal de PIN no pase (2,32× < 3×), **comprar 0DTE en 310 es comprar el pin.**
>
> **Alternativa que sí se opera: ACCIONES (AAPL común).** Es un nombre de 4,4 B$ de capitalización con
> spread de céntimos; el gate de spread se cumple trivialmente.
> **Nota TFSA: no se shortea.** La rama bajista **NO tiene vehículo** (los puts están vetados) → **la rama
> bajista es NO-TRADE, solo gestión.** *(La regla 6 de la casa: no entrar ES una posición.)*

### 7.1 La ÚNICA entrada del día — REBOTE en el borde inferior

| campo | valor |
|---|---|
| **Vehículo** | Acciones AAPL |
| **Ventana** | **09:45 – 10:30 ET** (ventana de oro). **Jamás 09:30–09:45** (subasta). Si llega en 11:30–14:00 (picadora), tamaño mitad o nada. |
| **Disparador** | El precio **TOCA 305,00 ± 0,40** y luego imprime **2 velas de 1m CERRADAS por encima de 305,00**. Es un **BOUNCE** de la skill `print-o-nada-levels`, el único evento operable junto al RETEST_REJECT. |
| **NO es entrada** | "está cerca de 305". "Va bajando hacia 305". Un solo cierre por encima. **PRINT O NADA.** |
| **Entrada** | primer cierre de 1m confirmado, ~305,30 |
| **Invalidación (stop)** | **302,00** — por debajo del nivel de dark pool 302,10 y por encima de la trampilla de 300. Riesgo ≈ **3,30 $** |
| **Objetivo 1** | **310,00** — el imán (POC + max pain + mayor gamma). **Cobrar el 70 % aquí.** Recorrido ≈ +4,70 $ |
| **Objetivo 2** | **312,50** — flip cumsum. Solo con el 30 % restante y solo si 310 se rompe con retest-y-rechazo |
| **Objetivo 3 (límite duro)** | **315,00**. **NO SE PASA DE AHÍ.** Es muro call + borde de la valla: la doctrina prohíbe perseguir extensiones fuera de la valla sin confluencia, y aquí la confluencia dice TECHO |
| **R:R** | 4,70 / 3,30 = **1,42 : 1** al objetivo 1; 7,20 / 3,30 = **2,18 : 1** con el tramo a 312,50 |
| **Probabilidad de que el setup ocurra** | **P(toca 305) = 51,1 %** (riesgo-neutral, §5). Es decir: **hay ~1 posibilidad de 2 de que este plan ni se active.** No pasa nada: no activarse es el resultado correcto la mitad de los días. |

### 7.2 Gestión en el borde superior — 315,00 (NO es una entrada)

- **P(toca 315) = 42,0 %** · **P(cierra por encima) = 21,0 %**.
- Si el precio llega a 315 **se VENDE lo comprado en 7.1**. No se compra ahí.
- Doctrina literal: **"call-spike de apertura = techo, no gasolina"**. Si en los primeros 15 minutos el
  volumen de calls 315 + 320 del 0DTE supera su OI (4.040 + 3.522 = 7.562), es **distribución en el techo**.
- **Ruptura de 315**: solo cuenta con **2 velas de 5m CERRADAS por encima + retest-y-rechazo**. La doctrina
  de muros dice que el **primer toque rebota ~70 %** (doctrina, no medido) y que la **primera ruptura NO se
  opera nunca**. Si hay ruptura confirmada, 315 **invierte** y pasa a ser soporte → nuevo mapa, nuevo plan.
- **PROHIBIDO comprar a través de 315 hacia 320** (post-mortem META 660C del 2026-07-20: comprar al otro
  lado de un muro intermedio = premium muerto).

### 7.3 Invalidación de TODA la tesis

**2 velas de 15m CERRADAS por debajo de 300,00.**
Ahí el único strike de gamma negativa (−61,4 M$/1 %) queda por encima del precio, el mapa cambia de signo,
y se entra en **caja de whipsaw** (doctrina `negative-gamma-whipsaw`: la gamma negativa **no es dirección,
es una caja**). En ese estado: **NO-TRADE.** No se fadea, no se persigue. Se espera al mapa nuevo.

### 7.4 Prohibiciones explícitas de hoy

| ❌ | por qué |
|---|---|
| Operar 09:30–09:45 | subasta; regla horaria de la casa |
| Comprar cualquier opción | spread no verificable (bid/ask = 0) **y** ATM fuera de presupuesto |
| Comprar 0DTE clavado en 310 | pin_risk 68,95 + mayor gamma positiva de la cadena = theta te come |
| Comprar a través de 315 hacia 320 | muro intermedio (protocolo de imanes) |
| Perseguir por encima de 315,6 | borde superior de la valla; la skill prohíbe perseguir extensiones |
| Añadir un boleto de QQQ o XLK a esta tesis | **una tesis = un boleto** (AAPL pesa ~9 % del QQQ: sería la misma apuesta dos veces) |
| Corto / put en la rama bajista | TFSA no shortea y los puts están vetados → NO-TRADE |
| Cambiar el plan por Corea | correlación medida −0,05 (p ≈ 0,27) → cero (§4) |

---

## 8. LO QUE PODRÍA MATAR ESTA TESIS

### Riesgo 1 — El OI del mapa es de un día de VENCIMIENTO: el libro abre RECIÉN VACIADO

El viernes 31-jul **era vencimiento**. Todo el OI monstruo de AAPL expiró ese día: `C335` 21.388,
`C332.5` 17.708, `P330` 21.691, `P310` 20.120. El mapa de hoy se apoya en un OI de **12.211 en 310**, que
es un **residuo**, no una posición asentada. Además el `oi-change` del viernes dio **29 aperturas y CERO
cierres de 60 contratos**: el mundo entero abrió riesgo nuevo antes del fin de semana, y ese riesgo se
recoloca hoy. **El imán de 310 podría no existir a las 10:00.**

> **Dato que lo delata primero:** el **volumen de opciones 0DTE en 315 y 320 en los primeros 15 minutos**.
> Si `vol(C315) + vol(C320)` supera su OI heredado (**7.562**) antes de las 10:00, el techo se está
> reconstruyendo más arriba y el objetivo de 315 deja de ser techo. Vigilar en `data/opt_chain_aapl.txt`
> (refresco cada 180 s) y en el heatmap `data/strike_heatmap_aapl.json`.

### Riesgo 2 — El conflicto de régimen no está resuelto: si manda UW, fadear los bordes es suicida

`gex_core` (11 vencimientos, gamma medida de Polygon) dice **POSITIVA +0,434 B$/1 %**.
Unusual Whales, con su modelo de dealer, dice **NEGATIVA −25.837** y además **cruzó** desde +675.479 el
jueves. Todo el plan de §7 asume gamma **positiva** entre 305 y 320 (el dealer amortigua → reversión al
imán). **Si el régimen real es negativo, el precio no revierte: ACELERA**, y comprar el rebote en 305 es
exactamente el error que la doctrina `negative-gamma-whipsaw` prohíbe.

> **Dato que lo delata primero:** el **comportamiento de la primera ruptura** de 307,50 o de 312,50.
> Régimen positivo → la ruptura se devuelve dentro de 2-3 velas de 5m. Régimen negativo → **2 velas de 5m
> CERRADAS al otro lado sin retorno**. Si eso ocurre en cualquiera de los dos niveles: **el mapa es NEG,
> se cancela el plan de rebote y se pasa a NO-TRADE.**

### Riesgo 3 — AAPL no sube por mérito propio: sube porque los semis se hunden

AAPL es la **más floja** de las mega-caps verdes (+0,35 % contra AMZN +1,74 %, GOOGL +1,66 %, META +1,17 %)
y el compás de QQQ la descarta por débil (`drivers_skipped: AAPL z-0,5`). Está verde por **rotación
defensiva** desde la memoria (MU −3,46 %, INTC −1,67 %), no por flujo propio. Y el estudio coreano de la
fase anterior es explícito: tras KOSPI ≤ −5 %, el **open→close medio del Nasdaq es +0,62 %** — el daño se
paga en el hueco y **los semis suelen REBOTAR intradía**. Si eso pasa, el dinero **sale** de AAPL y vuelve
al semi, y AAPL pierde su único motor.

> **Dato que lo delata primero:** **SMH o MU en verde a las 10:00 con AAPL en rojo.**
> Y la señal de capitán que lo anticipa: **flujo masivo de PUTS de SMH o SPY** → doctrina de la casa
> (jerarquía de capitanes, punto a): *"flujo masivo de PUTS del capitán = rebote del sector SIEMPRE"*.
> Si salta esa alarma, la rotación se da la vuelta y esta tesis se queda sin combustible.
> **Bloqueo hoy: `data/rt_last_SMH.txt` NO EXISTE** — el capitán de semis está mudo en premarket, así que
> este riesgo **no se puede vigilar todavía**. Es el primer fichero que hay que tener a las 09:30.

---

## LO QUE ME FALTÓ (declarado, no disimulado)

| falta | consecuencia | cuándo se arregla |
|---|---|---|
| **bid/ask de opciones** (0 en el 100 % de la cadena) | **el gate de spread <5 % no es calculable → OPCIONES VETADAS.** Es la limitación que decide el vehículo del día | requiere IBKR (prohibido esta semana) o un plan Polygon superior |
| **Volumen premarket de AAPL** | Intrinio devuelve `volume = 0`; no se puede medir RVOL ni confirmar el empuje de 06:00-06:30 con volumen | otro agente trabaja en la capa de proveedores |
| **`data/rt_last_SMH.txt`** | el **capitán de semis está mudo**: el riesgo 3 no se puede vigilar en premarket | otro agente lo está arreglando |
| **Latencia intradía de UW** | los 58,87 h medidos son el hueco del fin de semana, **no** su latencia operativa. Todo el §3 es del viernes | repetir la sonda después de las 09:30 |
| **OI intradía** | no existe en ningún proveedor: el mapa de muros es del cierre del viernes durante toda la sesión | limitación estructural |
| **Bucket "día tras caída ≥5 %"** | n = 3 → n insuficiente; es el bucket que mejor describiría hoy | acumular histórico |
| **RSI diario en vivo** | `data/aapl_daily.csv` acaba el 2026-07-06 y `poly_bars` el 2026-07-25. El **39,24 del 31-jul es de Finviz**, no recalculado aquí | backfill de barras diarias |

---

## FUENTES Y LATENCIA

| dato | fuente | latencia |
|---|---|---|
| Spot AAPL, QQQ, SPY, NVDA, MU, META, GOOGL, AMZN, INTC | **Finnhub WS** → `data/rt_last_<SYM>.txt` | **sin retraso de proveedor**; es el último print (premercado fino: edad 0-6 min) |
| Barras 1m, NBBO del subyacente | **Intrinio** vía `scripts/provider_bridge.py` → `data/bars_aapl_ibkr.txt` (nombre legado) | **~16 min medidos** |
| Cadena, OI, IV, griegas (840 contratos, 11 vencs) | **Polygon** `/v3/snapshot/options` → `raw/chain_aapl.json` | **15 min** + **el OI es del cierre del viernes 31-jul** |
| Flujo, ballenas, dark pool, griegas de dealer, max pain UW | **Unusual Whales** REST | **58,87 h** (hueco del fin de semana; latencia intradía SIN MEDIR) |
| KOSPI `^KS11`, SOX, QQQ diarios | **yfinance** → `raw/*.csv` | EOD; la fila coreana de hoy es el cierre ya consumado (02:30 ET) |
| Diario AAPL 2 años | `data/aapl_daily.csv` (yfinance) | EOD, **acaba el 2026-07-06** |
| Mapa gamma, flip, muros | `scripts/gex_core.py` sobre la cadena de Polygon | hereda la de Polygon |
| Calibración de probabilidad | `data/compass_calib.json`, `data/compass_aapl.json` | recalculado hoy 04:00 ET |
| Fecha y forma de resultados | `data/earnings_falls.json` (Finviz) | del 31-jul |
| **IBKR / TWS** | — | **NO USADO. Prohibido esta semana** (orden 2026-08-02). Cero conexiones a 4001/4002/7496/7497 |

---

**SEÑAL-SOLAMENTE. No es consejo financiero.**
