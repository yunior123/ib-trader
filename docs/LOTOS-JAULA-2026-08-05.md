# LOTOS $10-30 Y JAULA QUE EXPIRA — 2026-08-05 14:40-15:05 ET

Fuente: UW en vivo (`option-contracts?expiry=X` NBBO+OI+ΔOI+lado agresor, `greek-exposure/expiry`,
`max-pain`, `ohlc/1d`, `stock-state`). Script: `scripts/cage_lotto_scan.py` →
`data/scan/cage_lotto_2026-08-05.json`. 21 símbolos con spot ≤ $45 (bargain fleet + flota).
Filtro de entrada: **ASK entre $0.10 y $0.30** (lo que se paga de verdad), OI ≥300, vol ≥50, spread ≤35%.

**GOTCHA MEDIDO HOY**: `/max-pain` ignora `?expiry` pero devuelve **una fila por vencimiento** —
coger `[0]` da siempre el 08-07. Se filtra por el campo `expiry` de la fila. Control cruzado: max pain
recalculado en casa desde el OI por strike de cada vencimiento **coincide 21/21** con el de UW.

## EL HALLAZGO: la jaula de todo el grupo muere este viernes

Fracción de la gamma TOTAL de la cadena que vence el 08-07, contra la que queda para el 08-14:

| SYM | spot | gamma 08-07 | gamma 08-14 | ratio muere/queda | %OI que expira el vie | r5/ATR (compresión) | pin 08-07 (dist) |
|---|---|---|---|---|---|---|---|
| **DJT** | 10.22 | 25.1% | **1.8%** | **13.9×** | **89.9%** | **1.24** (el más preso) | 10.0 (−2.0%) |
| **ZETA** | 27.27 | **38.2%** | 3.6% | 10.6× | 85.4% | 4.91 | 27.0 (−0.8%) |
| GME | 19.20 | 24.0% | 4.4% | 5.5× | 76.5% | 5.66 | 22.0 (+14.6%) |
| SNAP | 5.33 | 26.6% | 4.9% | 5.4× | 84.5% | 4.57 | 5.0 (−6.3%) |
| NVTS | 12.37 | 24.3% | 4.6% | 5.3× | 77.1% | 2.15 | 15.0 (+21.4%) |
| ACHR | 5.20 | 30.3% | 6.5% | 4.7× | 73.5% | 2.25 | 5.0 (−3.7%) |
| OPEN | 3.79 | 26.1% | 8.5% | 3.1% | 71.0% | 2.08 | 4.5 (+18.9%) |
| SOFI | 18.39 | 19.6% | 6.9% | 2.8× | 69.6% | 4.04 | 17.5 (−4.8%) |
| **NOK** | 9.68 | **11.6%** | 5.5% | 2.1× | 63.6% | 2.37 | 9.0 (−6.9%) |

**Consecuencia dura**: el 60-90% del OI abierto de estos nombres muere el viernes y lo que queda para
la semana siguiente es una fracción. La liberación es REAL, pero **se cobra a partir del lunes**, no
antes: el contrato 08-07 expira con los barrotes, no después de ellos.

**NOK es la excepción y hay que decirlo**: solo el 11,6% de su gamma vence el viernes; el 82,9% vive
en el **mensual 08-21**. NOK NO sale de la jaula esta semana — sigue cosido entre el muro de puts 9,0
(15.456) y el de calls 10,0 (17.524).

## TAPE DE HOY (verificado antes de opinar, 14:50 ET)

Día rojo generalizado en el grupo especulativo, casi todos **en la parte baja del rango del día**:
OPEN −7,9% (posdía 0,27) · SNAP −7,9% (0,24) · BBAI −4,0% (0,26) · POET −4,0% · NVTS −2,6% ·
NOK −2,5% (0,13) · SOFI −1,7% (**0,07 = en el mínimo**) · ACHR −2,1% · DJT −1,1% · GME 0,0%.
Única verde: **ZETA +12,4%** post-earnings (reportó 08-04).

## VETOS POR EARNINGS (medidos en UW hoy)

- Cruzan el 08-07: **RDW y RUN y SOUN (hoy postmarket) · CLSK y QBTS y RGTI (08-06)** → prohibido premium comprado.
- Cruzan el 08-14: los anteriores **+ ACHR y POET y USAR (08-10) · LUNR y ONDS (08-13)**.
- Limpios ambas semanas: BBAI · DJT · GME (09-08) · NOK (10-22) · NVTS · OPEN · PATH (09-03) · SNAP · SOFI · ZETA.

## LOS CONTRATOS ($10-30, 08-07, limpios, con mercado real)

`x1ATR` = cuánto vale el contrato mañana si el subyacente se mueve 1 ATR a favor (Black-Scholes, IV constante);
`xcrush` = lo mismo con IV −20%.

| # | contrato | $ | spr | OI | ΔOI hoy | vol | agresor | P(ITM) | P(prof) | x1ATR | xcrush |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **OPEN P4.00 08-07** | 26 | 8% | 5.931 | **+1.641** | 3.326 | +202 | **0,82** | 0,44 | 1,94 | 1,94 |
| 2 | **SNAP P5.50 08-07** | 24 | 8% | 3.215 | **+2.134** | 8.029 | +633 | **0,73** | 0,41 | 1,83 | 1,83 |
| 3 | **SOFI P18.00 08-07** | 16 | 6% | 8.436 | **+5.240** | 7.104 | −514 | 0,32 | 0,25 | **3,50** | 3,36 |
| 4 | **NOK P9.50 08-07** | 14 | 7% | 1.674 | +699 | 1.217 | +312 | 0,39 | 0,29 | **3,16** | 3,06 |
| 5 | **BBAI C3.00 08-07** | **10** | 10% | 9.381 | −865 | 1.924 | +197 | 0,54 | 0,36 | 2,30 | 2,27 |
| 6 | **NOK C10.00 08-07** | 11 | 10% | **17.524** | **+3.205** | 7.882 | **+3.344** | 0,27 | 0,21 | 3,01 | 2,78 |
| 7 | **GME C19.50 08-07** | 12 | 9% | 5.018 | +1.293 | 3.287 | −90 | 0,32 | 0,26 | **3,24** | 3,01 |

1-4 van **a favor del tape** (todo el grupo en mínimos del día). 5-7 son alcistas: solo con el print,
no "porque está cerca".

Detalle de por qué cada uno:
- **OPEN P4.00** — el de mayor probabilidad medida del barrido. Ya ITM ($0,21 intrínseco de $0,26 pagados:
  solo 5 centavos de valor temporal). Encaja con la estructura: max pain baja de 4,0 (08-07) a **3,5** (08-14),
  y los **61.100 calls de 4,5 y 5,0** que sostienen el mapa mueren sin valor si OPEN no sube +19%.
  Break-even 3,74 = −1,2% desde 3,79. Charm 08-07 −22,6M, el mayor sangrado de delta del grupo.
- **SNAP P5.50** — ITM ($0,17 de $0,24). ΔOI +2.134 **hoy** y agresor +633 = se está comprando en ask.
  Suelo real lejos: el muro de puts está en 4,0 (23.800). Max pain 5,0 = hay 6% de recorrido hasta el imán.
- **SOFI P18.00** — el mayor multiplicador de la lista (x3,5) y **ΔOI +5.240 hoy**. Spot en el **mínimo
  del día** (posdía 0,07). Max pain 17,0 ambas semanas, con muros de calls apilados en 18,5/19/19,5 que
  actúan de techo. Contra: 268.494 de OI en el 08-07 = pin denso, puede quedarse clavado en 18,4.
- **NOK P9.50** — ITM de un centavo. NOK no se libera esta semana; dentro de la caja 9-10 el borde
  bajo paga x3,16. Break-even 9,36.
- **BBAI C3.00** — **el boleto de $10**. Casi ATM (spot 3,02, strike 3,00), max pain 3,0 = **el imán
  está exactamente en el strike**, con 9.400 calls en 3,0 y 8.400 en 3,5 encima. Sin earnings hasta
  noviembre. Riesgo total $10 por contrato.
- **NOK C10.00** — el contrato **más comprado de todo el barrido**: OI 17.524, ΔOI **+3.205**, y el
  agresor +3.344 dice que se paga en **ask**. Es el muro: si NOK imprime 10,00 sostenido, el squeeze
  de gamma está justo ahí. Hoy va en contra (9,68, posdía 0,13).
- **GME C19.50** — ATR 3,2% (el más tranquilo del grupo) y el precio clavado en su max pain 19,5.
  La gravedad rueda arriba para la semana que viene: **max pain 19,5 → 20,0 y call wall 22 → 24**.

## LA JAULA MÁS PURA: DJT — mirar, no pagar

**89,9% de su OI muere el viernes** y para el 08-14 quedan 3.244 contratos en total (1,8% de la gamma).
Rango de 5 días = **1,24 ATR**: es el ticker más comprimido del universo barato. Estructura 08-07:
calls 9,5 (4.900) y 10,0 (6.800) encima, puts 9,0 (2.800) debajo; spot 10,22, ya sobre el call wall.
Traducción: el viernes se le quitan TODOS los barrotes y no se le ponen otros.

**Pero el vehículo para cobrarlo no existe**: los contratos del 08-14 cotizan 0,14/0,25 (spread 56%) con
OI de 200-300. Pagar eso es regalar el 30% en la entrada. Lo operable en DJT es el 08-07: **P10,00 $21**
(x2,54 si −1 ATR) o **C10,50 $23** si rompe 10,55 impreso. Alarma puesta en 10,55 arriba / 10,08 abajo.

## LO QUE NO SE COMPRA Y POR QUÉ

- **ZETA**: 38,2% de gamma muriendo y el precio clavado a −0,8% del pin 27, pero hoy hay alguien
  **vendiendo 6.148 contratos nuevos del C30 en bid** (agresor −3.439): ese es el techo declarado.
  Y su 08-14 no tiene mercado (P21,5 $10 con volumen 5).
- **NVTS**: su call wall **colapsa de 15 a 10** para el 08-14 y el max pain de 11,5 a 10,0. La estructura
  de la semana que viene está ABAJO, no arriba. Si algo, es put — pero con IV 139% no es barato.
- Todos los vetados por earnings arriba: el mercado cobra 2-3× el movimiento histórico en un evento
  con fecha (skill `event-premium-discipline`).

## LA REGLA QUE SE DERIVA DE ESTE BARRIDO

La gamma que enjaula a este grupo vence el **viernes 08-07**. Un contrato **08-07 no cobra la
liberación** — expira con ella. Quien quiera la ruptura post-vencimiento tiene que estar en el
**08-14**, y en la mayoría de estos nombres el 08-14 está tan vacío que el spread se come la ventaja.
Los dos únicos 08-14 con mercado real y $10-30: **GME P18,00 $12** (OI 1.696) y **GME C20,00 $18**
(OI 1.901, vol 1.869).
