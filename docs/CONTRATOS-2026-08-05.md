# CONTRATOS Y ANÁLISIS — 2026-08-05 premarket (~08:40 ET)

Datos: UW (dark pool paginado, GEX per-strike por expiry, flow-alerts, ΔOI, max pain, calendario de earnings) +
Polygon (RV20 diaria) + BD local `poly_bars`. NBBO de premarket: **re-verificar con `scripts/optgate.py` antes de pagar**.
Vencimientos reales: **08-07 (viernes)** y **08-14 (viernes próximo)**. 08-08 y 08-15 son sábados.

## Método (por qué estos y no otros)
1. **IV invertida por bisección** del mid de cada contrato (Black-Scholes) → IV real que se paga, no la del vendor.
2. **IV/RV20**: IV pagada contra volatilidad realizada medida. <0.85 = premium barato de verdad; >1.25 = caro.
3. **Sigmas hasta break-even**: `(strike+prima−spot)/spot ÷ (1σ implícito)`. Cuántas desviaciones típicas
   necesita el precio SOLO para empatar. <0.40 = el movimiento normal ya basta. Es el criterio que manda.
4. **Gates duros**: spread NBBO ≤6.5%, OI ≥500, y **veto si hay earnings antes del vencimiento**.

## VETOS POR EARNINGS (medido en el calendario de UW, no supuesto)
Reportan **antes del 08-14** → premium comprado que cruce el print está PROHIBIDO:
**QBTS 08-06 · DKNG 08-06 · ACHR 08-10 · RKLB 08-10 · CRWV 08-11 · LUNR 08-13 · ONDS 08-13**
Limpios en la ventana: HOOD PLTR MSTR COIN NOK NVDA MSFT AAPL AMD SOFI SOUN OPEN GME DJT SNAP ZETA PATH POET BBAI RGTI CLSK RDW NVTS RUN USAR.

## LOS CONTRATOS (ordenados por sigmas-a-break-even, el criterio limpio)

| # | contrato | $ prem | spr | OI | IV | IV/RV | P(ITM) | σ→BE | ROI si +1σ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **NVDA C215 08-14** | 425 | 3.6% | 7.181 | 27% | **0.77** | 53% | 0.40 | +133% |
| 2 | **NVDA C215 08-07** | 203 | **1.5%** | 29.221 | 26% | **0.74** | 57% | 0.32 | +145% |
| 3 | **NVDA C210 08-14** (ITM) | 670 | 2.3% | 7.861 | 20% | **0.57** | 80% | **0.16** | +85% |
| 4 | **SOFI C18 08-14** | 107 | 4.8% | 6.296 | 57% | s/d | 64% | 0.26 | +115% |
| 5 | **HOOD C95 08-14** | 395 | 3.9% | 1.108 | 73% | 1.18 | 44% | 0.46 | +146% |
| 6 | **PLTR C160 08-14** | 800 | 3.2% | 1.765 | 68% | **0.65** | 53% | 0.36 | +135% |
| 7 | **MSTR C95 08-14** | 645 | 6.4% | 678 | 80% | s/d | 56% | 0.32 | +127% |
| — | ~~CRWV C90 08-14~~ | 980 | 4.2% | 1.797 | 161% | 1.24 | 47% | 0.39 | +141% | **VETADO: earnings 08-11** |

### 1. NVDA C215 08-14 — máxima convicción, $425
La única de la lista donde **coinciden las tres cosas**: premium barato (IV 27% contra RV 35%), estructura y ballena.
- **Ballena confirmada**: sweep de **$2,30M comprado en ASK** en ESTE contrato exacto (vol 18.070 vs OI 7.181 = ABRE posición). Ya está ITM.
- ΔOI semanal: C215 +16.192 (9 días seguidos subiendo) y C217.5 +13.522 → imán 215-217.5.
- Rompió 210 ayer; el mapa de dealers (muros 210, max pain 197-200) va POR DETRÁS del precio = ruptura real, no rebote.
- Sin earnings hasta **26-ago**: ningún print que cruzar.
- Break-even 219.25 = **+1,7%** cuando el movimiento típico a 9 días es **±4,3%**.
- **Invalida**: pierde 210 impreso (vuelve a la caja y el contagio de AMD ganó).

### 2. NVDA C215 08-07 — el mismo caballo esta semana, $203
Spread **1,5%** y OI 29.221: el contrato más líquido de todo el barrido. P(ITM) 57%, break-even +1,4%.
Es el boleto si se quiere cobrar el imán 217.5 ya el viernes en lugar de esperar.

### 3. SOFI C18 08-14 — el barato con probabilidad, $107
P(ITM) 64% y solo 0,26σ para empatar; puts vendidos por −$1,53M (alcista). Reportó el 07-29, sin print pendiente.
Cabe de sobra en el presupuesto de $200. Menos espectacular, mucho más probable.

### 4. HOOD C95 08-14 — el que replica el patrón NOK, $395
La estructura ES la de Nokia la semana pasada: **el mapa de dealers rueda arriba** — max pain 89 → 95, call wall 92 → 100 —
con puts vendidos por −$9,7M y ΔOI creciendo 7-9 sesiones seguidas en C100 y P80.
**Pero el premium es caro**: IV 73% contra RV 62%. Consecuencia medida: si HOOD solo llega al imán 95 el día 12,
el contrato **pierde −48%** por theta. Necesita ~99-100 para ganar de verdad. Es apuesta a ruptura, no a pin.

### 5. PLTR C160 08-14 — el premium más barato del universo, $800
IV 68% contra RV 104% (**0,65** = el ratio más bajo medido), call volume **4,20× su media** y
**+$109,5M de prima neta en calls**, la mayor de los 42 símbolos. Reportó el 03-ago (doble beat), sin print pendiente.
**Matiz honesto**: (a) el RV 104% incluye el gap de earnings del lunes, así que "barato" está algo sobrestimado;
(b) las ballenas grandes **venden** calls ITM (146 y 152.5, ~$11M en bid) — huele a covered call o pata de spread;
(c) su mapa está muy por detrás (max pain 123 contra spot 162): no hay imán que empuje arriba. Premium alto en $.

## LA PREGUNTA DE AAPL: ¿sube o baja por el dark pool?
**Sesgo ARRIBA, pero es un soporte, no un motor — y ahora mismo se está probando.**
- Honestidad primero: **un print de dark pool no lleva lado**. No se sabe si fue compra o venta agresiva; sirve como NIVEL, no como flecha.
- Lo que sí es medible: los **$1.049B se ejecutaron todos a 309,38** (5 prints, 16:00-16:52). AAPL abrió el premarket
  en 311,41 y **ahora está en 309,80**: ha bajado a tocar ese nivel exacto. Está en la línea en este momento.
- Lo que inclina la balanza arriba es el **flujo de opciones, que sí lleva lado**: C/P 3,26, prima neta de calls
  **+$10,2M**, puts **vendidos** (−$1,9M), y las cuatro ballenas del día compradas **en ask abriendo posición**
  (C307.5 08-10 $1,77M · C310 08-07 $0,96M · C305 y C310 0DTE). ΔOI: C305 +8.905, C310 08-07 +8.337.
- Y la estructura acompaña: **max pain sube de 307,5 (08-07) a 310 (08-14)** y el call wall está en 310 ambas semanas.
- **Traducción**: mientras 309,38 aguante, el camino es 310-312, con techo pegajoso en el muro 310 (los dealers venden ahí).
  **Print sostenido por debajo de 309,38 invalida todo** y abre 305 (call wall 0DTE) y 303,75 (flip).
- Contrapeso que no se oculta: alguien compró **P300 de diciembre por $17,2M** (ΔOI +5.812). Es cobertura a meses, no una apuesta a hoy.

## BARGAIN FLEET — esta semana y la próxima
Criterio "rueda arriba" = el max pain del 08-14 está por encima del de 08-07: los dealers desplazan la gravedad hacia arriba (el patrón NOK).

| SYM | spot | C/P | vol/med | prima neta calls | max pain 07→14 | call wall 07→14 | veredicto |
|---|---|---|---|---|---|---|---|
| **ZETA** | 24.37 | 6.76 | **4.89×** | +$2.21M | 20.5→21.5 ↑ | 25→23 | el flujo más fuerte del grupo |
| **USAR** | 17.61 | 5.29 | 1.77× | +$0.92M | 15→16 ↑ | 16→**20** | mucho espacio hasta el muro |
| **RGTI** | 17.24 | 2.55 | 1.41× | +$1.70M | 14→15.5 ↑ | 16→17 | estructura sube limpia |
| **SOFI** | 18.65 | 2.07 | 1.16× | +$0.45M | 17→17 | 18→18.5 | puts vendidos −$1.53M |
| **POET** | 8.44 | 8.00 | 1.61× | +$1.15M | 7→7 | 8→9.5 | C/P alto, muro lejos |
| **DJT** | 10.09 | **12.99** | 3.07× | +$0.32M | 9.5→9 ↓ | 10→10 | C/P engañoso: gravedad baja |
| **BBAI** | 3.15 | **15.38** | 2.79× | +$0.15M | 3→3 | 3→3 | C/P máximo pero todo clavado en 3 |
| **OPEN** | 3.78 | 5.41 | 1.74× | +$1.22M | 4→3.5 ↓ | 4.5→5 | **−8,3% hoy**, cayendo |
| GME | 19.25 | 3.10 | 1.30× | **−$1.11M** | 19.5→20 ↑ | 19→20 | prima NEGATIVA: no |
| PATH / RUN / SNAP | — | 7.19/10.53/5.46 | — | negativas | — | — | C/P alto con prima negativa = ruido |
| QBTS · ACHR · ONDS · LUNR | — | — | — | — | — | — | **VETADOS: earnings antes del 08-14** |

**Lectura**: de los 20, solo **ZETA, USAR, RGTI y SOFI** combinan flujo de calls positivo con estructura que sube.
Los C/P espectaculares de BBAI (15.4) y DJT (13.0) **no valen**: su prima neta es casi nula y su mapa está clavado o bajando —
un ratio alto con $150k de prima es un puñado de lotes baratos, no una ballena.

## LOS NUEVOS DE LA FLOTA (tipo HOOD, "queridos por la comunidad")
Añadidos y con barras 1m verificadas en vivo: **PLTR · MSTR · COIN · CRWV · RKLB** (+ HOOD).
`fleet.txt` 36 · `universe_gamma.txt` 41 · `provider_syms.txt` 32.

| SYM | C/P | prima neta C / P | max pain 07→14 | call wall 07→14 | nota |
|---|---|---|---|---|---|
| **PLTR** | 2.10 | **+$109.5M** / −$46.3M | 123→125 | 150→155 | flujo monstruoso, IV la más barata |
| **MSTR** | 2.26 | +$4.7M / −$3.0M | 93→**100** ↑ | 93→**100** ↑ | replica el patrón HOOD exacto |
| **COIN** | 2.60 | +$0.1M / −$1.3M | 146→**155** ↑ | 155→**170** ↑ | mapa rueda arriba, volumen flojo |
| CRWV | 1.81 | +$19.0M / −$12.8M | 80→76 | 100→100 | ΔOI +51.7k en C110 sep. **Earnings 08-11: sin premium comprado** |
| RKLB | 2.62 | +$6.9M / −$1.7M | 67→67.5 | 70→75 | ballenas VENDEN el muro 70. **Earnings 08-10** |

## REGLAS QUE SIGUEN VIGENTES
- Entrar solo con el nivel **impreso** (dos velas cerradas), jamás "está cerca".
- 9:30-9:45 no se opera. Ventana de oro 9:45-10:30. Hoy además: **ADP 8:15 e ISM Services 10:00**.
- AMD sigue **vetado para premium comprado**: IV 190% contra RV 76% (ratio 2,48) tras el −8,7%. Spreads o nada.
- Una tesis = un boleto: NVDA 08-07 y NVDA 08-14 son la MISMA apuesta. Se elige una.
