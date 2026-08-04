# STRANGLE SCAN — 2026-08-04 13:20 EDT (sesión viva)

Presupuesto ≤$200 total (call OTM + put OTM comprados), pegado a catalizador.
**Datos**: spot realtime repo (finnhub 13:13-13:17), bid/ask+OI+IV de CBOE delayed_quotes (~15 min delay, ts 13:17-13:20 EDT), OI/IV cruzado con cadenas Polygon del repo. Moves históricos medidos con yfinance (venv). Sin UW.

## Catalizadores VERIFICADOS
- **SPCX (SpaceX)**: primeros earnings como pública **HOY 8/4 AMC** (call 16:30 ET) + **lockup 8/6**: hasta 911,5M acciones (20% insiders) desbloqueadas.
- **AMD**: earnings **HOY 8/4 AMC** (call 17:00 ET). *(El brief decía "AMD reporta hoy" — correcto.)*
- **SNDK + WDC**: ambos **mañana 8/5 AMC** (confirmado Businesswire/Zacks). STX **ya reportó 7/28** (+2.3%) — sin catalizador.
- **CPI**: **miércoles 8/12 8:30 ET** (julio). Entrada martes 8/11 → expiry 8/12 o 8/14.

## Tabla completa (strangle de mayor delta que cabe en $200)

| Cand / exp | Coste | Patas | Spread% | OI | BE req. | EM straddle | Move hist. | Ratio hist/BE | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| SNDK 8/7 (earn 8/5) | 25d=$8.880; NADA cabe | — | — | — | — | 15,9% | med 6,9% (n=5: +8,3 +6,9 +15,3 −4,6 +4,8) | — | **VETADO presupuesto** (spot $1.437; wings 1d = $10 pero BE ±60%+) |
| WDC 8/7 (earn 8/5) | $140 | C820 0,03/0,40 · P360 0,10/1,00 | **172% / 164%** | 82/130 | +49% / −35% | 13,2% | med 8,0% (n=7, máx −10,1/+10,2) | 0,19 | **VETADO spread+ratio** |
| STX 8/7 | no cabe (25d $3.740) | — | — | — | — | 10,6% | med 11,1% (¡pero ya reportó 7/28!) | — | **VETADO** presupuesto + sin catalizador |
| MU 8/7 | $179 | C1170 · P682,5 | 12%/12% | 160/101 | +31% / −24% | 9,3% | earnings ~24-sep (fuera) | — | **VETADO** sin catalizador + spread |
| AMD 8/5 (earn HOY) | $136 | C647,5 0,55/0,71 · P430 0,60/0,65 | 25% / 8% | 12/1.110 | +23,5% / −18,4% | 8,25% | med 6,4% (n=7); extremos +18,6/−17,3 | 0,31 | **VETADO ratio: 0/7 trimestres habría cruzado BE** |
| AMD 8/7 | $178 | C680 · P412,5 | 12%/12% | 253/50 | +29,7% / −21,8% | 9,9% | ídem | 0,29 | **VETADO** |
| SPCX 8/7 (earn HOY + lockup 8/6) | $188 | C162,5 1,62/1,66 · P84 0,21/0,22 | 2% / 5% | 1.745/1.425 | +35% / −32% | **17,1%** | 4d med 8,2%, p90 17,1%; earnings n=0 **DATA-INSUFFICIENT** | ~0,25 | **VETADO presupuesto**: el strangle decente (25d C144/P108) = $790 |
| SPCX 8/7 solo-put sesgo lockup | $182 | P98 1,56/1,59 (+C330 0,23 relleno) | 2% | 3.034 | −20,8% | 17,1% | ídem | ~0,4 | VETADO — $200 no compra BE dentro del EM |
| NOK 8/7 | **$28** | C10,5 0,13/0,15 · P9,5 0,12/0,13 | 14% / 8% (=2¢) | **11.110 / 975** | +8,2% / −7,4% | 6,4% | 4d med 3,9%, **p75 7,7% ≈ BE**, p90 12,8% | 0,49 | **MARGINAL** — sin catalizador discreto (IV 85-91% por régimen post-caída −30% julio); spread% falla el gate pero son céntimos |
| NOK 8/14 | $32 | C11 0,16/0,17 · P9 0,13/0,15 | 6% / 14% | 3.142/5.641 | +13,7% / −12,9% | 9,9% | p90 4d 12,8% | ~0,4 | VETADO ratio |
| AAPL 8/7 | $150 | C320 0,67/0,68 · P300 0,75/0,82 | **1% / 9%** | **17.703 / 15.304** | +3,8% / −3,7% | 2,4% | 4d med 2,2%, **p75 3,8% ≈ BE**, p90 5,7% | **0,60 (mejor medido)** | **MARGINAL** — sin catalizador esta semana |
| TSLA 8/7 | $169 | C350 0,89/0,91 · P305 0,76/0,78 | 2% / 3% | 11.175/6.457 | +7,8% / −7,0% | 4,0% | 4d med 3,7%, p90 8,6% | 0,50 | MARGINAL — sin catalizador |
| INTC 8/7 | $156 | C113 · P90 | 5%/4% | 470/3.842 | +14,1% / −11,9% | 8,1% | sin catalizador | ~0,4 | VETADO |
| **XSP 8/12 (CPI)** | $138 | C795 0,51/0,55 · P752 0,81/0,83 | 8% / 2% | **0 / 79** | +3,0% / −2,9% | 1,5% | **CPI-day SPY 2026 (7 fechas): med 0,15%**, máx −1,58% (jun) | **0,05** | **VETADO — el peor del scan** |
| QQQ 8/12 (CPI) | $154 | C760 · P682 | 5%/3% | **1 / 67** | +5,5% / −5,7% | 2,7% | QQQ 4d med 1,5% | 0,23 | **VETADO OI+ratio** |
| SPY 8/12 (CPI) | $151 | C790 · P749 | 4%/3% | 289/179 | +2,6% / −3,1% | 1,5% | CPI med 0,15% | 0,05 | **VETADO** |
| SPCX 8/21 | 25d=$1.090 | — | 1-3% | 15-25k | −22% / +37% (25d) | 22,5% | 13d med 20,4% | ~0,7 (fuera de budget) | VETADO presupuesto |

## Lo que dicen los NÚMEROS (sin maquillaje)

1. **Ningún strangle con catalizador pasa ratio ≥1.** El mercado cobra 2-3x el movimiento histórico en cada evento conocido de esta quincena. SNDK: IV implica ±15,9% vs mediana real 6,9%. AMD: BE ±20% vs mediana 6,4% — **0 de 7 trimestres habría cruzado el breakeven al expiry** (los extremos +18,6%/−17,3% se quedan justo cortos). Comprar el evento anunciado es pagar el pico de la prima.
2. **IV crush medido por term structure**: SPCX 8/7 IV 2,2-2,6 → 8/14 1,5-1,9 → 8/21 1,3. Post-print de hoy, la pata 8/7 pierde ~40-50% de valor vega de la noche a la mañana si el move < EM. SNDK/WDC igual (8/7 IV ~2,0 vs forward ~1,4). **Ningún strangle corto de earnings sobrevive el move mediano histórico.**
3. **La tesis memoria (SNDK/WDC/STX misma apuesta)**: irrelevante — las tres VETADAS. Spots de 3-4 dígitos ($1.437/$551/$862) hacen que $200 solo compre wings de 1-2 delta con spreads de 3 dígitos.
4. **CPI 8/11→8/12 es la peor idea del scan, medida**: 7 CPIs de 2026, mediana |move| SPY = **0,15%** (solo junio movió −1,58%) vs breakeven ±2,6-3,0%. Ratio 0,05. No entrar el martes 8/11.
5. **SPCX es el catalizador real de la semana** (primeros earnings + lockup 911M acciones el 8/6, EM 17%) pero **no cabe en $200**: el strangle 25d cuesta $790. Con $200 el breakeven queda en ±32%, fuera incluso del p90 realizado. Si algún día sube el presupuesto: SPCX 8/7 25d C144 ($3,60) / P108 ($4,30), spreads 1%, OI 586/2.456, BE +25/−18% vs EM 17% — sigue <1 pero es el único evento donde el ratio se acerca.

## TOP 3 (los menos malos — ninguno es APTO pleno)

**#1 NOK 8/7 — $28 total** *(el único con pérdida máx trivial y BE ≈ p75 realizado)*
- CALL 10,5 exp 2026-08-07: bid 0,13 / ask 0,15 · OI 11.110 · IV 0,91
- PUT 9,5 exp 2026-08-07: bid 0,12 / ask 0,13 · OI 975 · IV 0,85
- Coste $28 · BE +8,2% / −7,4% · spot 9,96
- A favor: p75 semanal 7,7% ≈ BE (~1 de cada 4 semanas llega), p90 12,8% pagaría ~3x, régimen de vol alta (−30% en julio, AI-orders vaivén). En contra: sin catalizador discreto (Nokia ya reportó); spread 8-14% en % (2¢ absolutos — trabajar el mid); no pasa el gate del 5% formalmente.

**#2 AAPL 8/7 — $150 total** *(el mejor ratio medido del scan: 0,60; la mejor estructura)*
- CALL 320 exp 2026-08-07: bid 0,67 / ask 0,68 · OI 17.703 · spread 1%
- PUT 300 exp 2026-08-07: bid 0,75 / ask 0,82 · OI 15.304 · spread 9% (delayed; verificar NBBO vivo)
- Coste $150 · BE +3,8% / −3,7% · spot 309,86
- A favor: p75 de move 4d = 3,8% ≈ BE exacto; liquidez masiva. En contra: cero catalizador antes del expiry (CPI cae el 8/12, DESPUÉS).

**#3 TSLA 8/7 — $169 total** *(ratio 0,50, spreads 2-3%)*
- CALL 350 exp 2026-08-07: bid 0,89 / ask 0,91 · OI 11.175
- PUT 305 exp 2026-08-07: bid 0,76 / ask 0,78 · OI 6.457
- Coste $169 · BE +7,8% / −7,0% · spot 326,20
- p90 4d 8,6% > BE, pero mediana 3,7% muy por debajo. Sin catalizador propio.

## Recomendación honesta
**NO-TRADE = POSICIÓN (regla 6).** Con $200, ningún strangle pegado a los catalizadores verificados (SNDK/WDC 8/5, AMD/SPCX hoy, CPI 8/12) tiene breakeven ≤ move histórico: ratio máximo 0,49 y la mayoría <0,3. Si Yunior quiere sí o sí un boleto de volatilidad, **NOK 8/7 por $28** es el único donde la pérdida máxima es café y el breakeven roza el p75 realizado — pero es lotería de régimen, no de catalizador. La jugada de catalizador correcta esta semana no es comprar el strangle: es esperar el POST-evento (gap SNDK/WDC/SPCX el 8/6 con IV ya aplastada) y operar dirección con las reglas de siempre.

*Fuentes catalizadores: Businesswire (SNDK 8/5), Zacks/Investing (WDC 8/5), CNBC/Yahoo (SPCX 8/4 AMC + lockup 8/6), Benzinga/247WallSt (AMD 8/4 AMC), BLS/usinflationcalculator (CPI 8/12 8:30 ET).*
