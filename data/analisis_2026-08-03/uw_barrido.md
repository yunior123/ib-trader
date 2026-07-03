# Barrido Unusual Whales — 11 simbolos — lunes 2026-08-03 premarket

**Generado**: 2026-08-03T10:50:15+00:00 UTC (06:50 ET) · **Fuente unica**: API REST `api.unusualwhales.com`, token de `config/feeds.env` · **11/11 simbolos, 0 errores HTTP.**

> ## ADVERTENCIA QUE MANDA SOBRE TODO EL DOCUMENTO
> **Ni un solo dato de este barrido es de hoy.** UW no ha publicado nada del lunes 03-ago.
> Todo lo que sigue es la foto del **viernes 2026-07-31 al cierre**: sirve como **posicionamiento de partida**, jamas como flujo de hoy.

---

## 1. LATENCIA UW MEDIDA (nunca se habia medido en esta casa)

**Metodo**: sonda /api/darkpool/{sym}?limit=1 SIN filtro (el print mas reciente que UW sirve) contra el reloj local, y contra el ultimo tick de Finnhub WS en data/rt_last_<SYM>.txt

**Reloj de la medida**: 2026-08-03T10:51:51+00:00 (06:51 ET)

| sym | ultimo print UW (UTC) | edad UW | ultimo tick Finnhub (UTC) | edad Finnhub | UW va por detras |
|---|---|---:|---|---:|---:|
| AMZN | 2026-07-31T23:59:59Z | **58.86 h** | 2026-08-03T10:24:46+00:00 | 1625 s | 58.4 h |
| META | 2026-07-31T23:56:50Z | **58.92 h** | 2026-08-03T10:40:39+00:00 | 673 s | 58.7 h |
| GOOGL | 2026-07-31T23:58:48Z | **58.88 h** | 2026-08-03T10:51:18+00:00 | 34 s | 58.9 h |
| MU | 2026-07-31T23:59:50Z | **58.87 h** | 2026-08-03T10:40:39+00:00 | 673 s | 58.7 h |
| AAPL | 2026-07-31T23:59:56Z | **58.87 h** | 2026-08-03T10:43:50+00:00 | 483 s | 58.7 h |
| NOK | 2026-07-31T22:28:01Z | **60.4 h** | **SIN FICHERO** | SIN DATO | SIN DATO |
| INTC | 2026-07-31T23:59:25Z | **58.87 h** | 2026-08-03T10:38:29+00:00 | 806 s | 58.7 h |
| QQQ | 2026-07-31T23:59:10Z | **58.88 h** | 2026-08-03T10:51:46+00:00 | 9 s | 58.9 h |
| SPY | 2026-07-31T23:59:40Z | **58.87 h** | **SIN FICHERO** | SIN DATO | SIN DATO |
| SMH | 2026-07-31T23:48:47Z | **59.05 h** | **SIN FICHERO** | SIN DATO | SIN DATO |
| NVDA | 2026-07-31T23:59:42Z | **58.87 h** | 2026-08-03T10:49:13+00:00 | 163 s | 58.8 h |

- **Edad UW: 58.86 h a 60.4 h.** Edad Finnhub en el mismo instante: **9 s a 1625 s.**
- El endpoint **global** `/api/darkpool/recent` (todo el mercado, sin filtro de simbolo) tiene su print mas reciente en **2026-07-31T23:59:59Z** = viernes 19:59:59 ET. No es un hueco de un simbolo: **es toda la API.**
- Sin fichero `rt_last_<SYM>.txt`: NOK, SPY, SMH (hueco conocido, otro agente lo arregla).

### Veredicto de latencia

**UW NO ES UNA FUENTE DE PREMARKET.** A las 06:51 ET del lunes su dato mas fresco tiene **58,9 horas**. La cifra de 58,9 h **no es la latencia intradia de UW**: es el hueco del fin de semana. **La latencia intradia sigue SIN MEDIR** — hay que repetir esta misma sonda despues de las 09:30 ET. Publicar hoy "UW = 58,9 h" como si fuera su latencia operativa seria mentir.

**Consecuencia dura:** ningun nivel de este documento puede disparar una orden por si solo. Confirmar con IBKR es imposible esta semana (prohibido), asi que el PRINT lo da **Finnhub WS**.

---

## 2. SEMANTICA DE LOS ENDPOINTS — dos trampas cazadas hoy

### Trampa 1 — `market-tide` es CUMULATIVO. Sumarlo multiplica el resultado por 90.

- Sumar las 81 barras da signed = **-14,464,555,457 USD** (-14,5 mil millones). **Es basura.**
- Los 11 nombres mas grandes de la flota suman entre todos -29,438,851 USD. Un mercado 500x sus mayores nombres no existe.
- `net_volume` sostenido en +800,559 contratos netos barra tras barra. El volumen TOTAL de opciones US ronda los ~60 M de contratos/dia (*orden de magnitud de conocimiento general, NO medido en esta sesion*) → ~770k por barra de 5 min contando calls y puts. Un **NETO** de ese tamaño repetido 81 veces exigiria que practicamente todo el mercado operase del mismo lado todo el dia: **imposible** por-barra.
- **Regla: se lee la ULTIMA barra. Jamas se suma.**

### Trampa 2 — la mayoria de los prints de dark pool NO son precios ejecutables

`sale_cond_codes` marca `average_price_trade` (VWAP), `prior_reference_price` (precio de referencia anterior) y `contingent_trade` (condicional). **En QQQ son 212 de 250 prints y en SPY 235 de 274.** Construir niveles con ellos **inventa muros que no existen**: el print de AMZN de 415.915 acciones "a 235,50" del viernes esta marcado `average_price_trade` y AMZN cerro a 271,58.

**Todo nivel de dark pool de este documento esta construido SOLO con prints limpios.** Los sucios se publican aparte, etiquetados.

### El resto (medido, no supuesto)

| endpoint | resolucion | trampa |
|---|---|---|
| `net-prem-ticks` | **POR-MINUTO**, no cumulativo | ninguna. La suma del dia SI vale. scripts/uw_premium.py:signed_premium ya suma por ventana: correcto |
| `greek-exposure` | 1 fila/dia, ~250 dias | es exposicion al CIERRE de ese dia |
| `greek-exposure/strike` | 1 fila/strike a la fecha pedida | incluye strikes ajustados (204,78 en QQQ): hay que acotar la banda |
| `oi-change` | cierre de la sesion vs la anterior | **el OI intradia NO existe**: hoy solo se ve viernes vs jueves |
| `darkpool` | print a print, **limit maximo 500** | en QQQ/SPY 500 filas cubren solo ~2 h: hay que filtrar por `min_premium` o se trunca |
| `flow-alerts` | alerta a alerta, **limit maximo 200** | en nombres liquidos cubre parte del dia; en NOK se remonta **al 15-jul** |

`signed_premium = net_call_premium - net_put_premium`. **No es "net call premium".** (gotcha ya cazado por la casa, no repetido aqui.)

UW **no trae campo `side`**. El lado se deriva de `total_ask_side_prem` vs `total_bid_side_prem`: ASK = el agresor compro, BID = el agresor vendio, MIXTO si el desequilibrio es <20%.

---

## 3. LO QUE PASO EL VIERNES — el contexto que cambia la lectura de hoy

*open/close del campo open/close de /max-pain, VALIDADO contra el underlying_price estampado en las flow-alerts de esa misma sesion (dos campos UW independientes). No es un OHLC oficial: es la referencia que usa UW.*

| sym | open | close | open→close | premarket hoy (Finnhub) | pm vs close |
|---|---:|---:|---:|---:|---:|
| **MU** | 919.65 | 823.03 | **-10.51 %** | 802.61 | -2.48 % |
| **INTC** | 96.72 | 90.2 | **-6.74 %** | 89.05 | -1.27 % |
| **SMH** | 557.5 | 540.53 | **-3.04 %** | SIN DATO | SIN DATO |
| **NOK** | 9.42 | 9.14 | **-2.97 %** | SIN DATO | SIN DATO |
| **QQQ** | 692.11 | 687.99 | **-0.60 %** | 690.97 | +0.43 % |
| **SPY** | 744.68 | 747.03 | **+0.32 %** | SIN DATO | SIN DATO |
| **NVDA** | 198.4405 | 200.75 | **+1.16 %** | 200.19 | -0.28 % |
| **AAPL** | 304.81 | 308.91 | **+1.35 %** | 310.5 | +0.51 % |
| **META** | 543.6 | 556.71 | **+2.41 %** | 565.09 | +1.51 % |
| **AMZN** | 265.0 | 271.58 | **+2.48 %** | 276.66 | +1.87 % |
| **GOOGL** | 340.83 | 356.13 | **+4.49 %** | 363.1 | +1.96 % |

**El viernes NO fue un dia plano: fue una ROTACION VIOLENTA dentro del indice.**

- **La memoria se desplomo**: MU **-10,51 %** de apertura a cierre (abrio en 919,65 y cerro en 823,03), INTC **-6,74 %**, SMH **-3,04 %**, NOK -2,97 %.
- **La mega-cap no-semi subio**: GOOGL +4,49 %, AMZN +2,48 %, META +2,41 %, AAPL +1,35 %.
- **Los indices lo taparon**: QQQ -0,60 %, SPY +0,32 %. El indice escondio un desastre sectorial.

Esto **encaja con Corea de hoy** y le quita la sorpresa: el KODEX 200 -8,93 % de hoy no arranca de un maximo intacto — **MU ya habia devuelto -10,5 % el viernes desde su propia apertura**. La distribucion en memoria empezo el viernes en horario US, no esta noche en Seul.

**Discrepancia declarada (no resuelta aqui):** UW da el cierre de QQQ en **687,99**; el orquestador trae **690,57**. Evidencia UW: la ultima flow-alert del viernes (20:16Z) lleva `underlying_price` 687,81 y hay un print limpio de 120.000 acciones a las 20:46Z a 687,83. Contra 687,99 el premarket de QQQ esta **+0,43 %**; contra 690,57, **+0,06 %**. Se publican los dos con su fuente.

---

## 4. TONO DE MERCADO — `market-tide` (viernes al cierre)

| campo | valor |
|---|---:|
| ts (ultima barra) | 2026-07-31T16:10:00-04:00 |
| net_call_premium | **-15.5 M$** |
| net_put_premium | **+144.6 M$** |
| **signed_premium** | **-160.1 M$** |
| net_volume | +800,559 contratos |

- **Apertura 09:30**: signed +72.7 M$ — el dia **empezo alcista**.
- **Pico de compra de puts**: +199.0 M$ a las 11:30.
- **Minimo de net call premium**: -83.5 M$ a las 11:45.
- **Ultima hora** (15:10→16:10): delta signed +14.8 M$.

**Tono: BAJISTA y sostenido.** El mercado abrio comprando calls (+72,7 M$ signed), se dio la vuelta antes de las 10:10 y **paso el dia entero pagando por puts**. Cerro con **-160,1 M$** de premium firmado. El giro fue temprano y **nunca volvio a positivo**.

| hora ET | net_call acum | net_put acum | signed acum | net_volume |
|---|---:|---:|---:|---:|
| 09:30 | +86.7 M$ | +14.0 M$ | +72.7 M$ | +86,118 |
| 10:10 | -62.6 M$ | +131.6 M$ | -194.1 M$ | -599,971 |
| 10:50 | -53.5 M$ | +131.2 M$ | -184.8 M$ | -326,360 |
| 11:30 | -62.1 M$ | +199.0 M$ | -261.1 M$ | -572,373 |
| 12:10 | -77.0 M$ | +176.0 M$ | -253.0 M$ | -579,139 |
| 12:50 | -58.8 M$ | +170.0 M$ | -228.8 M$ | -452,577 |
| 13:30 | -28.7 M$ | +138.1 M$ | -166.8 M$ | -239,256 |
| 14:10 | -50.8 M$ | +146.3 M$ | -197.2 M$ | -313,687 |
| 14:50 | -39.5 M$ | +133.4 M$ | -172.9 M$ | +671,055 |
| 15:30 | -7.0 M$ | +134.5 M$ | -141.5 M$ | +695,786 |
| 16:10 | -15.5 M$ | +144.6 M$ | -160.1 M$ | +800,559 |
| 16:10 | -15.5 M$ | +144.6 M$ | -160.1 M$ | +800,559 |

## 5. SECTORES — `sector-etfs`

**Aviso:** UW solo sirve los **12 ETF sectoriales SPDR** en este endpoint. **SMH y SOXX NO estan.** Los semis se piden aparte (abajo).

| ETF | sector | last | % dia | bull−bear prem | call−put prem | P/C vol | callvol/avg30 | putvol/avg30 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SPY | S&P 500 Index | 747.03 | +0.72 % | +27.5 M$ | -155.7 M$ | 1.277 | 1.17 | 1.28 |
| XLP | Consumer Staples | 85.05 | -0.49 % | +631 k$ | -796 k$ | 1.971 | 0.87 | 1.23 |
| XLK | Technology | 175.35 | -0.22 % | +570 k$ | +302 k$ | 1.518 | 0.87 | 1.04 |
| XLE | Energy | 59.55 | +1.00 % | +459 k$ | +4.4 M$ | 0.5 | 0.56 | 0.44 |
| XLI | Industrials | 179.84 | +0.81 % | +458 k$ | +568 k$ | 1.461 | 0.79 | 0.26 |
| XLC | Communication Services | 108.24 | +1.56 % | +44 k$ | +322 k$ | 0.273 | 0.95 | 0.16 |
| XLV | Health Care | 162.55 | -0.59 % | -2 k$ | +1.4 M$ | 0.772 | 0.37 | 0.53 |
| XLB | Materials | 50.43 | -2.34 % | -17 k$ | -473 k$ | 1.398 | 0.76 | 0.26 |
| XLRE | Real Estate | 45.07 | -0.51 % | -29 k$ | +32 k$ | 1.9 | 0.32 | 1.82 |
| XLY | Consumer Discretionary | 116.09 | +3.29 % | -120 k$ | -740 k$ | 1.175 | 0.74 | 0.34 |
| XLU | Utilities | 44.35 | -0.69 % | -149 k$ | -197 k$ | 1.78 | 0.45 | 1.13 |
| XLF | Financials | 56.94 | -0.11 % | -1.4 M$ | +7.3 M$ | 0.844 | 0.67 | 0.6 |

- **XLY +3,29 % y XLC +1,56 %** mandaron el viernes (AMZN y GOOGL/META estan ahi). **XLK -0,22 %** — la tecnologia se quedo atras. **XLB -2,34 %** el peor.
- **XLK con P/C de volumen 1,52 y put/avg30 1,04**: mas puts que calls en tecnologia el mismo dia que el indice aguanto.
- **XLF es el unico sector con bull−bear claramente negativo** (-1,35 M$) pese a estar plano.

### Semis pedidos aparte (`net-prem-ticks`, suma por-minuto del dia)

| sym | net_call prem | net_put prem | signed |
|---|---:|---:|---:|
| SMH | +1.1 M$ | -3.2 M$ | **+4.3 M$** |
| SOXX | +2.0 M$ | -15.9 M$ | **+17.9 M$** |

**Lectura contraintuitiva y hay que decirla:** SMH y SOXX cierran el viernes con signed **positivo** (+4,3 M$ y +17,9 M$) — el `net_put_premium` es **negativo**, es decir se **VENDIERON** puts netos en semis el dia que los semis se hundieron. Eso es venta de volatilidad / recogida de prima contra la caida, no compra de proteccion. **Contradice** la nueva OI de puts de SMH (seccion 8). Las dos cosas son medidas; la reconciliacion es trabajo del sintetizador, no se fuerza aqui.

---

## 6. PREMIUM NETO POR SIMBOLO — `net-prem-ticks` (dia completo, suma por-minuto)

| sym | net_call prem | net_put prem | **signed** | net_delta | ultimos 30 min | ticks |
|---|---:|---:|---:|---:|---:|---:|
| **AMZN** | +137.3 M$ | -8.7 M$ | **+146.0 M$** | +240,684 | -2.2 M$ | 390 |
| **NVDA** | +42.4 M$ | -8.5 M$ | **+50.8 M$** | +4,857,052 | +7.6 M$ | 390 |
| **QQQ** | -13.0 M$ | -44.1 M$ | **+31.1 M$** | +1,214,006 | +3.9 M$ | 406 |
| **GOOGL** | +34.5 M$ | +7.6 M$ | **+26.9 M$** | +940,534 | +2.8 M$ | 391 |
| **SMH** | +1.1 M$ | -3.2 M$ | **+4.3 M$** | +78,904 | +4.6 M$ | 405 |
| **INTC** | -4.2 M$ | -8.3 M$ | **+4.1 M$** | -33,121 | -3.5 M$ | 391 |
| **META** | +2.8 M$ | +188 k$ | **+2.6 M$** | +832,474 | +4.1 M$ | 390 |
| **NOK** | -221 k$ | -641 k$ | **+419 k$** | +277,722 | -99 k$ | 390 |
| **SPY** | -51.8 M$ | -11.9 M$ | **-40.0 M$** | -3,696,951 | -4.2 M$ | 406 |
| **MU** | -84.5 M$ | +32.5 M$ | **-117.1 M$** | -754,826 | -13.0 M$ | 390 |
| **AAPL** | -59.2 M$ | +79.5 M$ | **-138.7 M$** | -4,759,110 | +8.9 M$ | 392 |

- **AAPL -138,7 M$ y MU -117,1 M$** son los dos extremos bajistas de la flota. En AAPL el `net_put_premium` es **+79,5 M$** (compra de puts) con `net_delta` **-4,76 M**: es la unica mega-cap con delta de dealer claramente negativa.
- **AMZN +146,0 M$** es el extremo alcista, con **+240 k** de net_delta.
- **QQQ +31,1 M$ frente a SPY -40,0 M$**: los dos capitanes **discrepan**. QQQ cierra con puts netos VENDIDOS (-44,1 M$) y SPY con calls netos vendidos (-51,8 M$).
- **MU en los ultimos 30 min: -13,0 M$**, el peor cierre de la flota. Vendieron hasta la campana.

---

## 7. BALLENAS — `flow-alerts` (lado DERIVADO de ask vs bid)

**Truncamiento declarado:** el endpoint topa en **200 alertas**. La ventana real que cubre cada simbolo es distinta y hay que mirarla antes de comparar magnitudes entre nombres.

| sym | n | ventana cubierta | prem calls | prem puts | ask−bid calls | ask−bid puts |
|---|---:|---|---:|---:|---:|---:|
| **AMZN** | 200 | 2026-07-31 14:01 → 2026-07-31 19:59 | +41.7 M$ | +14.4 M$ | +417 k$ | -3.9 M$ |
| **META** | 200 | 2026-07-30 13:44 → 2026-07-31 19:52 | +45.2 M$ | +39.8 M$ | -2.1 M$ | -1.2 M$ |
| **GOOGL** | 200 | 2026-07-27 17:13 → 2026-07-31 19:59 | +48.7 M$ | +11.4 M$ | +12.3 M$ | -2.8 M$ |
| **MU** | 200 | 2026-07-31 13:45 → 2026-07-31 19:59 | +46.7 M$ | +23.9 M$ | -3.1 M$ | +1.1 M$ |
| **AAPL** | 200 | 2026-07-31 13:39 → 2026-07-31 19:59 | +30.8 M$ | +49.8 M$ | +2.2 M$ | +16.0 M$ |
| **NOK** | 200 | 2026-07-15 14:18 → 2026-07-31 19:51 | +19.3 M$ | +7.5 M$ | +4.9 M$ | +2.5 M$ |
| **INTC** | 200 | 2026-07-29 16:44 → 2026-07-31 19:58 | +52.6 M$ | +14.1 M$ | +6.1 M$ | -570 k$ |
| **QQQ** | 200 | 2026-07-31 14:26 → 2026-07-31 20:16 | +25.8 M$ | +33.3 M$ | +1.2 M$ | +2.3 M$ |
| **SPY** | 200 | 2026-07-31 15:15 → 2026-07-31 20:13 | +15.0 M$ | +35.4 M$ | -4.4 M$ | +5.6 M$ |
| **SMH** | 200 | 2026-07-30 15:35 → 2026-07-31 19:59 | +14.0 M$ | +41.1 M$ | -1.1 M$ | -973 k$ |
| **NVDA** | 200 | 2026-07-30 19:06 → 2026-07-31 20:00 | +60.1 M$ | +16.6 M$ | -3.6 M$ | +2.4 M$ |

**NOK se remonta al 15-jul y GOOGL al 27-jul**: sus totales NO son comparables con los de AMZN o MU, que solo cubren el viernes. No se comparan.

### Las 20 mayores ballenas de toda la flota

| # | sym | hora UTC | tipo | strike | expiry | premium | LADO | ask | bid | V/OI | apertura? | sweep |
|---:|---|---|---|---:|---|---:|---|---:|---:|---:|---|---|
| 1 | **INTC** | 15:28:42 | call | 90 | 2026-08-21 | **+6.6 M$** | ASK (agresor compra) | +6.6 M$ | +0 $ | 1.34 | probable APERTURA | - |
| 2 | **AAPL** | 13:40:15 | call | 290 | 2026-09-18 | **+6.5 M$** | BID (agresor vende) | +490 k$ | +3.8 M$ | 0.34 | indeterminado | - |
| 3 | **SMH** | 16:20:21 | put | 575 | 2026-07-31 | **+5.7 M$** | BID (agresor vende) | +36 k$ | +4.1 M$ | 0.60 | indeterminado | - |
| 4 | **QQQ** | 16:54:51 | put | 660 | 2026-08-07 | **+5.6 M$** | ASK (agresor compra) | +5.6 M$ | +222 $ | 0.55 | indeterminado | SI |
| 5 | **INTC** | 19:45:14 | call | 100 | 2026-09-18 | **+5.1 M$** | MIXTO | +2.8 M$ | +2.3 M$ | 0.99 | indeterminado | - |
| 6 | **AAPL** | 13:39:13 | put | 330 | 2026-07-31 | **+5.0 M$** | MIXTO | +757 k$ | +741 k$ | 0.40 | indeterminado | - |
| 7 | **META** | 13:48:31 | put | 557.5 | 2026-07-31 | **+4.6 M$** | ASK (agresor compra) | +4.6 M$ | +0 $ | 7.64 | probable APERTURA | - |
| 8 | **NVDA** | 14:36:32 | call | 210 | 2027-01-15 | **+4.3 M$** | BID (agresor vende) | +11 k$ | +4.3 M$ | 0.06 | indeterminado | - |
| 9 | **MU** | 14:44:17 | call | 740 | 2026-09-18 | **+4.3 M$** | BID (agresor vende) | +265 k$ | +4.1 M$ | 0.15 | indeterminado | SI |
| 10 | **META** | 14:44:36 | put | 560 | 2026-07-31 | **+3.8 M$** | BID (agresor vende) | +0 $ | +3.8 M$ | 1.25 | probable APERTURA | - |
| 11 | **QQQ** | 20:10:52 | put | 650 | 2027-01-15 | **+3.7 M$** | BID (agresor vende) | +268 k$ | +3.4 M$ | 0.25 | indeterminado | - |
| 12 | **NVDA** | 13:40:59 | call | 225 | 2027-12-17 | **+3.7 M$** | MIXTO | +1.4 M$ | +2.1 M$ | 1.32 | probable APERTURA | SI |
| 13 | **NVDA** | 16:46:35 | call | 225 | 2027-03-19 | **+3.3 M$** | BID (agresor vende) | +0 $ | +3.3 M$ | 0.36 | indeterminado | - |
| 14 | **META** | 19:57:14 | call | 600 | 2027-09-17 | **+3.0 M$** | BID (agresor vende) | +438 k$ | +2.3 M$ | 0.92 | indeterminado | - |
| 15 | **AAPL** | 19:46:10 | call | 300 | 2026-08-03 | **+2.9 M$** | ASK (agresor compra) | +2.9 M$ | +0 $ | 309.13 | probable APERTURA | - |
| 16 | **GOOGL** | 13:58:01 | call | 325 | 2027-06-17 | **+2.7 M$** | ASK (agresor compra) | +2.7 M$ | +0 $ | 0.24 | indeterminado | - |
| 17 | **INTC** | 19:45:23 | call | 100 | 2026-09-18 | **+2.6 M$** | ASK (agresor compra) | +2.2 M$ | +0 $ | 1.12 | probable APERTURA | - |
| 18 | **INTC** | 13:57:02 | call | 90 | 2026-08-03 | **+2.6 M$** | ASK (agresor compra) | +2.6 M$ | +0 $ | 4.84 | probable APERTURA | - |
| 19 | **META** | 15:17:42 | put | 550 | 2026-09-18 | **+2.5 M$** | MIXTO | +1.5 M$ | +1.1 M$ | 0.09 | indeterminado | SI |
| 20 | **INTC** | 18:42:18 | call | 120 | 2026-11-20 | **+2.5 M$** | BID (agresor vende) | +0 $ | +1.9 M$ | 0.34 | indeterminado | - |

---

## 8. GRIEGAS DE DEALER — `greek-exposure` (UW, cierre del viernes)

**Unidades**: UW no las documenta en la respuesta. Se publica el numero **crudo**, sin convertir. Comparar magnitudes entre simbolos es valido; leerlas como dolares por 1 % no.

| sym | net gamma | net gamma dia previo | net delta | net charm | net vanna |
|---|---:|---:|---:|---:|---:|
| **AMZN** | +1,684,177 | +412,315 | +110,141,998 | +140,109,808 | +25,849,672 |
| **META** | +79,727 | -51,777 | +4,531,541 | -243,135,932 | +98,839,820 |
| **GOOGL** | +439,968 | +242,338 | +44,319,266 | -15,158,826 | +40,575,579 |
| **MU** | +39,090 | -35,758 | +59,047,374 | +33,055,120 | +37,238,883 |
| **AAPL** | -25,837 | +675,479 | +38,038,283 | -542,187,408 | +46,243,449 |
| **NOK** | +7,104,670 | +8,040,927 | +11,844,402 | -187,818,624 | +125,109,049 |
| **INTC** | +1,036,324 | +272,402 | +114,315,354 | -90,602,362 | +75,344,688 |
| **QQQ** | -297,705 | -968,141 | +4,208,158 | -43,142,568 | +20,861,192 |
| **SPY** | -998,488 | -3,035,791 | +26,838,083 | +355,593,939 | -349,296,609 |
| **SMH** | -379,309 | -650,007 | -6,919,837 | +310,089,421 | +21,685,472 |
| **NVDA** | +2,270,867 | +503,613 | +179,145,881 | -487,509,453 | +208,234,671 |

- **QQQ, SPY, SMH y AAPL cierran con net gamma NEGATIVA.** Doctrina de la casa: gamma negativa **no es direccion, es una caja de whipsaw** — se espera muro + rechazo IMPRESO.
- **SPY y QQQ MEJORARON** su gamma (SPY -3,04 M → -1,00 M; QQQ -0,97 M → -0,30 M): menos negativa que el jueves, la caja se estrecha.
- **AAPL se dio la vuelta**: +675 k el jueves → **-25,8 k** el viernes. Cruzo a negativa.
- **SPY es el unico con net vanna NEGATIVA (-349,3 M)** y charm **+355,6 M**: signo opuesto al resto de la flota en las dos.
- **AAPL charm -542,2 M y NVDA -487,5 M**: el mayor arrastre de charm de la tarde.

### Muros y flip que da UW — `greek-exposure/strike` (viernes)

**Metodo del flip**: cumsum de `call_gex + put_gex` de strike bajo a alto. **NO es el flip por reprecio de spot** que calcula `gex_core.py` en casa. Son dos definiciones distintas y no tienen por que coincidir: la comparacion la hace el sintetizador.

| sym | flip UW (cumsum) | call wall UW | put wall UW | abs wall UW | net GEX total | n strikes |
|---|---:|---:|---:|---:|---:|---:|
| **AMZN** | 250.0 | 260 | 250 | 260 | +1,684,177.5 | 90 |
| **META** | 750.0 | 550 | 550 | 550 | +79,727.2 | 297 |
| **GOOGL** | 342.5 | 340 | 330 | 350 | +439,968.5 | 165 |
| **MU** | 1000.0 | 900 | 800 | 900 | +33,438.4 | 442 |
| **AAPL** | 130.0 | 300 | 300 | 300 | -25,837.1 | 127 |
| **NOK** | 10.5 | 10 | 9 | 10 | +7,104,670.5 | 53 |
| **INTC** | 95.0 | 100 | 100 | 95 | +1,036,324.3 | 156 |
| **QQQ** | **sin cruce** | 700 | 680 | 660 | -297,704.8 | 530 |
| **SPY** | **sin cruce** | 750 | 740 | 743 | -998,487.7 | 489 |
| **SMH** | **sin cruce** | 550 | 520 | 520 | -379,309.0 | 252 |
| **NVDA** | 202.5 | 200 | 200 | 200 | +2,270,866.5 | 272 |

- **QQQ, SPY y SMH no tienen cruce de cumsum**: su perfil de GEX no cambia de signo en ningun strike. Son justo los tres con net gamma negativa. **No se les puede asignar un flip por este metodo — se dice SIN CRUCE, no se inventa un numero.**
- **META flip 750 y MU flip 1000 con banda +-20 %**: strikes muy por encima del spot, artefacto de colas de OI. Tratarlos como ruido, no como nivel.
- **Coincidencias que si valen**: NVDA call wall = put wall = abs wall = **200**, con el spot en 200,75 y premarket 200,19. **OI monstruo a ±1 del spot = PIN → prohibido 0DTE comprado ahi** (doctrina de la casa). Igual en AAPL (**300** triple) y META (**550** triple).

---

## 9. MAX PAIN

| sym | close viernes | 31-jul | 03-ago (HOY) | siguiente | max pain hoy vs close |
|---|---:|---:|---:|---:|---:|
| **AMZN** | 271.58 | 235.0 | **240.0** | 08-05: 255 | -11.6 % |
| **META** | 556.71 | 550.0 | **535.0** | 08-05: 572.5 | -3.9 % |
| **GOOGL** | 356.13 | 330.0 | **330.0** | 08-05: 325 | -7.3 % |
| **MU** | 823.03 | 850.0 | **835.0** | 08-05: 870 | +1.5 % |
| **AAPL** | 308.91 | 327.5 | **332.5** | 08-05: 330 | +7.6 % |
| **NOK** | 9.14 | 9.5 | **sin expiry hoy** | 08-07: 9 | SIN DATO |
| **INTC** | 90.2 | 90.0 | **88.0** | 08-05: 89 | -2.4 % |
| **QQQ** | 687.99 | 690.0 | **679.0** | 08-04: 678 | -1.3 % |
| **SPY** | 747.03 | 740.0 | **740.0** | 08-04: 740 | -0.9 % |
| **SMH** | 540.53 | 550.0 | **540.0** | 08-05: 535 | -0.1 % |
| **NVDA** | 200.75 | 195.0 | **195.0** | 08-05: 195 | -2.9 % |

- **MU max pain de hoy en 835 con el spot en 802,61**: el iman esta **+4,0 % por encima**. Es el desajuste mas grande de la flota.
- **AAPL max pain 332,5 con spot 310,50: +7,3 % por encima.** AMZN 240 con spot 276,66: **-13,3 % por debajo.** Ambos son residuos de la semana de resultados, no imanes limpios.
- **QQQ 679 (spot 690,97, -1,7 %) y SPY 740 (spot ~747, -0,9 %)**: los dos capitanes tienen el max pain **por debajo**. NVDA 195 (-2,6 %), SMH 540 (~0 %), INTC 88 (-1,2 %).
- NOK no tiene expiry hoy (su siguiente es 07-ago).

---

## 10. CAMBIO DE OI — regla Kochuba (viernes vs jueves)

**`V ~ +dOI` = posicion NUEVA · `V ~ -dOI` = SALIDA · `V >> |dOI|` = CHURN.** Umbrales: ratio dOI/V > 0,5 apertura · < -0,5 cierre · |ratio| < 0,25 churn.

| sym | apertura | cierre | churn | mixto |
|---|---:|---:|---:|---:|
| **AMZN** | 27 | 0 | 6 | 27 |
| **META** | 49 | 0 | 2 | 9 |
| **GOOGL** | 31 | 0 | 11 | 18 |
| **MU** | 24 | 0 | 23 | 13 |
| **AAPL** | 29 | 0 | 17 | 14 |
| **NOK** | 42 | 0 | 9 | 9 |
| **INTC** | 31 | 0 | 14 | 15 |
| **QQQ** | 41 | 0 | 7 | 12 |
| **SPY** | 31 | 0 | 24 | 5 |
| **SMH** | 54 | 0 | 1 | 5 |
| **NVDA** | 31 | 0 | 15 | 14 |

**Hallazgo que hay que decir en voz alta: CERO contratos de CIERRE en los 660 examinados (60 por simbolo).** Ni uno solo con dOI negativo suficiente. El viernes **nadie cerro nada: todo el mundo ABRIO**. Eso es apilar riesgo nuevo antes del fin de semana, no reducirlo.

### Los contratos que mas OI ganaron (posicion nueva del viernes)

| sym | contrato | volumen | dOI | ratio | veredicto |
|---|---|---:|---:|---:|---|
| **AMZN** | `AMZN260731C00270000` | 38,237 | **+14,359** | 0.376 | MIXTO |
| **AMZN** | `AMZN260731C00250000` | 50,354 | **+13,783** | 0.274 | MIXTO |
| **AMZN** | `AMZN260731C00260000` | 48,619 | **+13,764** | 0.283 | MIXTO |
| **META** | `META260731C00635000` | 9,902 | **+6,996** | 0.707 | APERTURA |
| **META** | `META260918P00460000` | 7,213 | **+4,592** | 0.637 | APERTURA |
| **META** | `META260731C00540000` | 16,149 | **+4,160** | 0.258 | MIXTO |
| **GOOGL** | `GOOGL260731P00332500` | 15,046 | **+4,940** | 0.328 | MIXTO |
| **GOOGL** | `GOOGL260828P00300000` | 4,730 | **+3,293** | 0.696 | APERTURA |
| **GOOGL** | `GOOGL260731C00332500` | 11,909 | **+2,642** | 0.222 | CHURN |
| **MU** | `MU260807P00500000` | 10,957 | **+8,012** | 0.731 | APERTURA |
| **MU** | `MU260731P00800000` | 20,645 | **+3,673** | 0.178 | CHURN |
| **MU** | `MU260807C00900000` | 8,320 | **+2,569** | 0.309 | MIXTO |
| **AAPL** | `AAPL260731C00335000` | 35,162 | **+16,387** | 0.466 | MIXTO |
| **AAPL** | `AAPL260731C00332500` | 31,168 | **+15,833** | 0.508 | APERTURA |
| **AAPL** | `AAPL260731P00310000` | 22,793 | **+8,134** | 0.357 | MIXTO |
| **NOK** | `NOK260821C00011000` | 25,338 | **+22,162** | 0.875 | APERTURA |
| **NOK** | `NOK260918C00010000` | 15,308 | **+10,354** | 0.676 | APERTURA |
| **NOK** | `NOK260821C00012000` | 16,344 | **+7,025** | 0.43 | MIXTO |
| **INTC** | `INTC260807C00100000` | 12,368 | **+9,380** | 0.758 | APERTURA |
| **INTC** | `INTC260731C00095000` | 35,896 | **+7,342** | 0.205 | CHURN |
| **INTC** | `INTC260731P00071000` | 8,024 | **+6,919** | 0.862 | APERTURA |
| **QQQ** | `QQQ260814P00685000` | 25,555 | **+21,069** | 0.824 | APERTURA |
| **QQQ** | `QQQ260807P00670000` | 29,911 | **+15,475** | 0.517 | APERTURA |
| **QQQ** | `QQQ270319C00715000` | 16,572 | **+14,526** | 0.877 | APERTURA |
| **SPY** | `SPY260731C00742000` | 98,085 | **+23,567** | 0.24 | CHURN |
| **SPY** | `SPY260821P00706000` | 29,858 | **+22,232** | 0.745 | APERTURA |
| **SPY** | `SPY260731C00750000` | 65,809 | **+13,728** | 0.209 | CHURN |
| **SMH** | `SMH260731P00400000` | 19,986 | **+18,871** | 0.944 | APERTURA |
| **SMH** | `SMH260807P00400000` | 11,853 | **+10,334** | 0.872 | APERTURA |
| **SMH** | `SMH260807P00370000` | 10,038 | **+10,020** | 0.998 | APERTURA |
| **NVDA** | `NVDA260807C00197500` | 27,005 | **+17,312** | 0.641 | APERTURA |
| **NVDA** | `NVDA260807C00200000` | 39,108 | **+15,643** | 0.4 | MIXTO |
| **NVDA** | `NVDA260807C00207500` | 23,986 | **+15,579** | 0.65 | APERTURA |

**SMH es el caso mas limpio y mas feo:** **54 de 60** contratos son APERTURA, y los tres mayores son **PUTS**: `SMH260731P00400` +18.871 (ratio 0,944), `SMH260807P00400` +10.334 (0,872), `SMH260807P00370` +10.020 (**0,998** — practicamente todo el volumen se quedo abierto). Strikes 370-400 con SMH en 540,53: **puts a -26 %/-32 %**. Eso es cobertura de cola comprada barata, no una apuesta direccional.

**QQQ**: `P00685` 14-ago +21.069 y `P00670` 07-ago +15.475, ambos apertura limpia. **SPY**: `P00706` 21-ago +22.232 (ratio 0,745). **MU**: `P00500` 07-ago +8.012 (0,731) — puts a -39 % del spot. **La proteccion nueva del viernes es toda de cola.**

**Del otro lado**: **NVDA** abrio **calls** 197,5 / 200 / 207,5 del 07-ago (+17.312, +15.643, +15.579) y **INTC** `C00100` 07-ago +9.380 (0,758), **NOK** `C00011` 21-ago +22.162 (0,875).

---

## 11. DARK POOL — solo prints LIMPIOS

Umbral adaptativo por simbolo (se sube hasta no truncar en 500). En los 11 quedo en **premium ≥ 10 M$**. Ventana: 3 sesiones (31, 30 y 29 de julio).

Un "nivel" solo se publica si lo sostienen **≥3 prints limpios del viernes**. Por debajo se marca **n insuficiente** y no se usa.

| sym | prints 3 ses. | limpios | limpios viernes | nivel top | % vol oculto | sesgo vs cierre | sesgo vs premarket |
|---|---:|---:|---:|---:|---:|---:|---:|
| **AMZN** | 80 | 32 | 12/29 | 271.6 | 21.5 % | 0.0 % encima | 0.0 % encima |
| **META** | 25 | 15 | 5/6 | 547.2361 | 53.11 % | 0.0 % encima | 0.0 % encima |
| **GOOGL** | 43 | 15 | 3/13 | 347.5536 | 34.65 % | 0.0 % encima | 0.0 % encima |
| **MU** | 39 | 23 | 6/16 | 926.698 | 40.51 % | 100.0 % encima | 100.0 % encima |
| **AAPL** | 81 | 19 | 5/22 | 302.1042 | 52.52 % | 0.0 % encima | 0.0 % encima |
| **NOK** | 4 | 2 | **1**/2 | **n insuficiente** | - | n insuf. | n insuf. |
| **INTC** | 28 | 4 | **0**/9 | **n insuficiente** | - | n insuf. | n insuf. |
| **QQQ** | 250 | 24 | 6/58 | 684.56 | 36.18 % | 7.0 % encima | 0.0 % encima |
| **SPY** | 274 | 24 | 13/101 | 746.253 | 63.63 % | 0.0 % encima | SIN DATO |
| **SMH** | 20 | 7 | **1**/5 | **n insuficiente** | - | n insuf. | n insuf. |
| **NVDA** | 75 | 15 | 3/27 | 200.8 | 59.68 % | 0.0 % encima | 59.7 % encima |

- **NOK, INTC, SMH no tienen suficientes prints limpios del viernes para sostener un nivel.** El caso extremo es **INTC: 0 limpios de 9**. Si se hubieran usado los sucios, INTC habria "publicado" un nivel en 90,20 con el 95,85 % del volumen oculto — **un muro entero fabricado a partir de `prior_reference_price`**. Es exactamente el fallo que la seccion 2 previene.
- **El sesgo esta casi todo por DEBAJO del cierre** en AMZN, META, GOOGL, AAPL, QQQ y SPY (0 % encima). **MU es la excepcion: 100 % ENCIMA** — todo el bloque limpio quedo colocado por encima del cierre el dia que se hundio -10,5 %.
- **NVDA es el unico con sesgo mixto util**: 0 % encima del cierre del viernes pero **59,7 % encima del spot premarket** — el premarket ha caido por debajo de donde se coloco el bloque.

### Los 5 prints limpios mas grandes de cada simbolo

| sym | fecha | hora UTC | size | precio | premium | ext hours |
|---|---|---|---:|---:|---:|---|
| **AMZN** | 07-30 | 20:00:04 | 308,000 | 235.5 | +72.5 M$ | SI |
| **AMZN** | 07-30 | 20:00:01 | 210,953 | 235.5 | +49.7 M$ | SI |
| **AMZN** | 07-30 | 20:00:01 | 156,651 | 235.5 | +36.9 M$ | SI |
| **AMZN** | 07-31 | 20:00:00 | 122,409 | 271.58 | +33.2 M$ | SI |
| **AMZN** | 07-30 | 18:08:09 | 134,041 | 237.135 | +31.8 M$ | - |
| **META** | 07-30 | 20:11:27 | 77,460 | 539.03 | +41.8 M$ | SI |
| **META** | 07-31 | 14:50:02 | 50,000 | 550.88 | +27.5 M$ | - |
| **META** | 07-31 | 15:52:13 | 41,861 | 547.2489 | +22.9 M$ | - |
| **META** | 07-29 | 16:19:45 | 34,581 | 586.7 | +20.3 M$ | - |
| **META** | 07-30 | 15:52:20 | 32,480 | 532.82 | +17.3 M$ | - |
| **GOOGL** | 07-29 | 15:09:10 | 77,200 | 335.295 | +25.9 M$ | - |
| **GOOGL** | 07-30 | 14:23:23 | 71,200 | 333.525 | +23.7 M$ | - |
| **GOOGL** | 07-30 | 20:00:00 | 61,164 | 333.66 | +20.4 M$ | SI |
| **GOOGL** | 07-30 | 19:33:03 | 57,010 | 334.205 | +19.1 M$ | - |
| **GOOGL** | 07-29 | 20:00:09 | 50,053 | 336.71 | +16.9 M$ | SI |
| **MU** | 07-31 | 13:33:59 | 64,679 | 926.74 | +59.9 M$ | - |
| **MU** | 07-30 | 13:31:08 | 47,120 | 795.325 | +37.5 M$ | - |
| **MU** | 07-29 | 17:06:02 | 40,127 | 776.345 | +31.2 M$ | - |
| **MU** | 07-30 | 13:30:02 | 38,205 | 792.4 | +30.3 M$ | - |
| **MU** | 07-29 | 13:41:57 | 30,000 | 820.32 | +24.6 M$ | - |
| **AAPL** | 07-30 | 20:00:00 | 153,180 | 333.43 | +51.1 M$ | SI |
| **AAPL** | 07-30 | 20:00:00 | 151,058 | 333.43 | +50.4 M$ | SI |
| **AAPL** | 07-30 | 20:00:00 | 100,496 | 333.43 | +33.5 M$ | SI |
| **AAPL** | 07-29 | 20:00:01 | 67,788 | 338.19 | +22.9 M$ | SI |
| **AAPL** | 07-31 | 20:34:33 | 67,705 | 308.91 | +20.9 M$ | SI |
| **NOK** | 07-31 | 14:24:01 | 2,000,000 | 9.15 | +18.3 M$ | - |
| **NOK** | 07-30 | 20:11:12 | 1,115,343 | 9.09 | +10.1 M$ | SI |
| **INTC** | 07-30 | 19:12:16 | 250,000 | 92.18 | +23.0 M$ | - |
| **INTC** | 07-30 | 15:49:39 | 200,000 | 92.02 | +18.4 M$ | - |
| **INTC** | 07-30 | 15:55:14 | 199,129 | 92.25 | +18.4 M$ | - |
| **INTC** | 07-30 | 15:58:33 | 198,472 | 92.2 | +18.3 M$ | - |
| **QQQ** | 07-31 | 14:30:14 | 149,050 | 684.5 | +102.0 M$ | - |
| **QQQ** | 07-30 | 21:35:54 | 145,000 | 683.69 | +99.1 M$ | SI |
| **QQQ** | 07-30 | 20:00:08 | 125,013 | 683.55 | +85.5 M$ | SI |
| **QQQ** | 07-31 | 20:46:34 | 120,000 | 687.83 | +82.5 M$ | SI |
| **QQQ** | 07-29 | 09:23:36 | 70,000 | 675.05 | +47.3 M$ | SI |
| **SPY** | 07-31 | 20:09:25 | 303,010 | 746.5941 | +226.2 M$ | SI |
| **SPY** | 07-31 | 20:16:31 | 221,300 | 746.5621 | +165.2 M$ | SI |
| **SPY** | 07-31 | 14:34:03 | 136,140 | 741.18 | +100.9 M$ | - |
| **SPY** | 07-31 | 20:47:26 | 135,000 | 746.6 | +100.8 M$ | SI |
| **SPY** | 07-31 | 14:21:15 | 132,355 | 739.28 | +97.8 M$ | - |
| **SMH** | 07-29 | 15:58:50 | 148,339 | 508.08 | +75.4 M$ | - |
| **SMH** | 07-31 | 18:59:46 | 75,382 | 544.56 | +41.1 M$ | - |
| **SMH** | 07-30 | 13:40:11 | 38,012 | 528.95 | +20.1 M$ | - |
| **SMH** | 07-29 | 18:27:18 | 29,728 | 515.46 | +15.3 M$ | - |
| **SMH** | 07-30 | 14:26:07 | 25,079 | 540.86 | +13.6 M$ | - |
| **NVDA** | 07-30 | 14:58:13 | 386,548 | 194.85 | +75.3 M$ | - |
| **NVDA** | 07-29 | 20:00:00 | 316,204 | 190.01 | +60.1 M$ | SI |
| **NVDA** | 07-30 | 20:00:00 | 250,581 | 195.04 | +48.9 M$ | SI |
| **NVDA** | 07-31 | 20:00:01 | 179,098 | 200.75 | +36.0 M$ | SI |
| **NVDA** | 07-29 | 20:00:00 | 98,350 | 190.01 | +18.7 M$ | SI |

**Casi todos los bloques limpios grandes caen a las 20:00-20:01 UTC = 16:00-16:01 ET, el cruce de cierre.** No son informacion direccional: son ejecucion de indexacion en el closing auction. Los que SI dicen algo son los de horario abierto: **QQQ 149.050 @684,50 a las 14:30Z**, **SPY 136.140 @741,18 a las 14:34Z**, **NVDA 386.548 @194,85 el 30-jul a las 14:58Z**, **MU 64.679 @926,74 a las 13:33Z** (3 minutos despues de abrir en 919,65 — alguien coloco 60 M$ **en el techo exacto** del dia).

---

## 12. ESTRUCTURA TEMPORAL DE VOLATILIDAD

| sym | 0DTE / mas cercano | IV | mov. implicito | siguiente | IV | mov. implicito |
|---|---|---:|---:|---|---:|---:|
| **AMZN** | 07-31 (dte 0) | 449.7 % | 0.33 % | 08-03 (dte 3) | 35.9 % | 2.22 % |
| **META** | 07-31 (dte 0) | 289.0 % | 0.22 % | 08-03 (dte 3) | 30.6 % | 1.89 % |
| **GOOGL** | 07-31 (dte 0) | 147.3 % | 0.23 % | 08-03 (dte 3) | 26.4 % | 1.64 % |
| **MU** | 07-31 (dte 0) | 827.4 % | 0.53 % | 08-03 (dte 3) | 77.5 % | 4.76 % |
| **AAPL** | 07-31 (dte 0) | 252.5 % | 0.19 % | 08-03 (dte 3) | 28.7 % | 1.76 % |
| **NOK** | 07-31 (dte 0) | 922.3 % | 1.24 % | 08-07 (dte 7) | 67.1 % | 6.32 % |
| **INTC** | 07-31 (dte 0) | 702.1 % | 0.49 % | 08-03 (dte 3) | 69.1 % | 4.25 % |
| **QQQ** | 07-31 (dte 0) | 24.4 % | 0.12 % | 08-03 (dte 3) | 16.2 % | 1.00 % |
| **SPY** | 07-31 (dte 0) | 24.1 % | 0.10 % | 08-03 (dte 3) | 8.0 % | 0.50 % |
| **SMH** | 07-31 (dte 0) | 117.7 % | 0.44 % | 08-03 (dte 3) | 39.6 % | 2.44 % |
| **NVDA** | 07-31 (dte 0) | 559.1 % | 0.57 % | 08-03 (dte 3) | 28.7 % | 1.82 % |

**La valla de hoy (03-ago)** segun el movimiento implicito del viernes: QQQ **±1,00 %** (±6,89 $ sobre 687,99), y es el numero contra el que hay que medir cualquier objetivo. Doctrina `expected-move-envelope`: recortar objetivos dentro de la valla y no perseguir extensiones fuera de ella sin confluencia muro+valla.

---

## 13. PROBABILIDADES — lo que este documento NO puede afirmar

**Este barrido no publica ni una sola probabilidad.** No hay ninguna medida aqui: son **observaciones de una sola sesion (n=1)**.

Lo que la casa exige para poner un numero (`measured-probability`): etiquetas de triple barrera, Wilson sobre muestra efectiva corregida por correlacion, null de entrada aleatoria, BH-FDR, DSR y MinTRL, y **n minimo antes de publicar**. Nada de eso se puede hacer con una sesion.

Las lecturas doctrinales que aparecen arriba (**pin en NVDA 200 / AAPL 300 / META 550**, **gamma negativa = caja**, **muro de OI = campo de fuerza**) van etiquetadas: **doctrina de la casa, no medicion de este barrido.**

La `anti-overfit-killlist` ademas mata el dark pool como SEÑAL (`dpi-lite`): aqui esta **descriptivo y nada mas** — sin score, sin gatillo, sin voz. Y los 11 nombres estan fuertemente correlacionados: **contarlos como 11 confirmaciones independientes seria exactamente el error que la killlist prohibe.** Es UNA lectura, no once.

---

*JSON completo: `data/analisis_2026-08-03/uw_barrido.json` · 11/11 simbolos, 0 errores HTTP · generado 2026-08-03T10:50:15+00:00*
