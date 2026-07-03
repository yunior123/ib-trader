# CUCHILLOS-0DTE — martes 2026-08-04, medido 10:40–10:45 ET (agente)

Complementa TODOS.md §17 (losers Finviz ya vetados: BRKR/APTV/NRG/HUT spreads 18-188%, CIFR
rebotado — no se repiten aquí). Fuentes: UW screener/net-prem-ticks/flow-alerts/flow-per-strike
(sellos 14:41-14:44Z) + cadenas CBOE delayed (spread = estructura, no disparo). Mercado FUERTE:
SPY 765,73 (+1,1%), pegado al máximo (hi 765,77); INTC +9,1%, AMD +6,3%, MRVL +10,2%.
SEÑAL-SOLAMENTE. No es consejo financiero.

## Veredicto en una línea
**Hay 2 cuchillos reales (CAT, VST) y los dos están VETADOS por spread (regla 4). 0DTE de índice:
flujo SPX bajista gordo pero precio no confirma. Sin boleto operable a las 10:45. TA caído
(DeepSeek 402 sin saldo).**

## Candidatos (todos los números medidos hoy)

| # | Sym | Evidencia flujo (a) | Precio (b) | Spread/OI (c) | TA | Entrada condicional |
|---|---|---|---|---|---|---|
| 1 | **CAT** | P/C 1,52 · bear $28,0M vs bull $23,9M · net_put +$3,9M · signed −$4,05M día PERO desacelera (13:30-14:00 −3,57M → 14:20-14:45 **+0,56M**) · puts K920 ITM $2,75M ask-side | Earnings HOY premarket: abrió 922 (gap +11% vs 830,03) y CAE −5,7% desde apertura; 869,75 a 0,3% del low 866,85 | **VETADO**: ATM 870P 08-08 bid 15,05/ask 16,90 = **11,6%** OI 89 (CBOE). Presupuesto $200 → K805 (−7,4%) spread **61,6%** — impagable | **pendiente** (DeepSeek 402) | Solo si pierde 866,85 con 2 lecturas Y el spread ATM comprime ≤5% — hoy no existe vehículo de opción pagable; el fade se mira, no se compra |
| 2 | **VST** | P/C 1,29 · bear $5,5M vs bull $2,9M (1,9×) · signed NEGATIVO las 3 ventanas (−0,57/−1,68/−0,37 = −$2,63M) · puts COMPRADAS: K115 **$1,24M ask-side** (−21%, delante de earnings 08-07 premarket), K140 $0,39M ask | −6,5% en línea recta desde apertura (155,75→145,75), a 0,9% del low 144,50 | **VETADO**: ATM 146P 08-08 = **15,0%** OI 48; K140 (~$190/contrato) = **17,9%** OI 369 | **pendiente** (DeepSeek 402) | NINGUNA con premium comprado: el vencimiento más cercano (vie 08-08) contiene earnings 08-07 premarket → doctrina prohíbe aguantar. Cuchillo para mirar, no para pagar |
| 3 | SPX/XSP (0DTE puro de HOY) | SPX net_call **−$171,7M** + net_put +$65,5M; SPXW net_call −$42,6M — cobertura bajista masiva de índice | **NO confirma**: SPY 765,73 pegado al máximo de sesión (hi 765,77, low 760,52) | XSP = único vehículo ≤$200 de índice | no aplica | Solo si SPY imprime 2 lecturas bajo 760,52 (low del día) — mientras esté en máximos ese flujo es hedge, no dirección |

## Descartados (tan valioso como lo elegido)

| Sym | Por qué NO |
|---|---|
| USO | −4,05% día (OPEP+) y signed −$4,68M, PERO todo el flujo fue 13:30-14:00 (−4,61M) y está PLANO desde apertura (+0,35%): el cuchillo ya cayó overnight, sin print fresco (regla 2). Único con venc. 08-05 (1DTE); ATM 117P spread 8,8% > 5% → vetado igual |
| INTC | Ballena 98P 08-05 $1,25M ask-side a las 14:41Z, pero px +9,1% y premium alcista ACELERANDO (+6,3/+8,3/+9,2M por ventana): es cobertura del rally, no cuchillo |
| AMD | 515P 10-ago $5,8M ask-side ATM con px +6,3%; última ventana −4,2M. Huele a techo local (regla 11, espada-ballena) — territorio del motor de flota, no cuchillo confirmado |
| IWM | P/C 1,27 y net_put +$5,0M pero px +0,96% cerca de máximos: hedge de small-caps, sin print |
| CVX | P/C 2,02 pero premiums minúsculos ($2,9M bear) y precio EN el máximo de sesión (190,59/190,61) |
| ARKK / VIXW / ETHA | P/C 2,61 / 2,30 / 1,93 con premium <$2M: ruido de lotes, sin materialidad |
| NBIS, BE, FCX, MRVL, AAOI, CAT-alcistas etc. | Verdes fuertes (MRVL +10,2%, AAOI +16,5%, BE +7,4%): su flujo put es cobertura de ganancias |
| VIX complejo | net_call −$5,0M (calls de VIX vendidas) = confirma mercado tranquilo, anti-cuchillo |

## Hallazgos operativos
1. **TradingAgents CAÍDO**: `ta_view.py` CAT y VST → **402 Insufficient Balance** de DeepSeek en
   el primer analista. `data/ta_view_cat.json` / `ta_view_vst.json` guardan el error (fail-loud
   OK). **Recargar saldo DeepSeek o TA no opina esta semana.**
2. El patrón del §17 se repite fuera de la flota: los cuchillos de verdad (CAT 11,6%, VST 15%)
   tienen opciones impagables al momento del cuchillo. El spread ES el precio del pánico.
3. Screener UW intradía: `close/high/low` vienen **null** en sesión (solo `prev_close`); el precio
   vivo hay que pedirlo a `stock-state` por símbolo.

Cuota UW gastada por este agente: **~26 requests** (contador global 12.200→12.452 compartido con
otro agente en paralelo).
