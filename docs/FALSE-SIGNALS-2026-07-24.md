# Caza de falsas señales — reporte medido (2026-07-24 15:36:51)

Backtest sobre `poly_bars`, horizonte 15m, fuente `backtest_signal_outcomes` (run más reciente). Todo Wilson 95%. SEÑAL-SOLAMENTE.

## 1. WR por fuente (el problema de fondo)

| fuente | n | WR | Wilson [lo,hi] |
|---|---|---|---|
| bollinger | 374 | 44% | [39,49] |
| cusum | 349 | 44% | [39,49] |
| whale | 70 | 36% | [26,47] |
| flow | 26 | 46% | [29,65] |
| structural | 5 | 80% | [38,96] |
| dip | 4 | 25% | [5,70] |

> Casi toda fuente es cara-o-cruz o peor (CI-hi < 50). El edge NO está en la señal cruda sino en la SELECTIVIDAD (hora + símbolo + dirección-flota + valuación).

## 2. WR por HORA DEL DÍA (confirma el lunch-lull)


**bollinger** (overall 44%):

| bucket | n | WR | factor |
|---|---|---|---|
| golden | 42 | 50% | ×1.09 |
| mid_am | 50 | 40% | ×0.933 |
| lunch | 136 | 43% | ×0.985 |
| pm | 69 | 39% | ×0.912 |
| power | 77 | 49% | ×1.094 |

**cusum** (overall 44%):

| bucket | n | WR | factor |
|---|---|---|---|
| premarket | 181 | 41% | ×0.939 |
| auction | 9 | 56% | ×1.083 |
| golden | 49 | 53% | ×1.149 |
| mid_am | 1 | 0% | ×0.952 |
| lunch | 3 | 67% | ×1.068 |
| pm | 40 | 48% | ×1.056 |
| power | 5 | 0% | ×0.8 |
| afterhours | 61 | 44% | ×1.007 |

**dip** (overall 25%):

| bucket | n | WR | factor |
|---|---|---|---|
| lunch | 3 | 33% | ×1.043 |
| pm | 1 | 0% | ×0.952 |

**flow** (overall 46%):

| bucket | n | WR | factor |
|---|---|---|---|
| lunch | 11 | 45% | ×0.995 |
| pm | 8 | 50% | ×1.024 |
| power | 7 | 43% | ×0.981 |

**structural** (overall 80%):

| bucket | n | WR | factor |
|---|---|---|---|
| lunch | 4 | 100% | ×1.042 |
| pm | 1 | 0% | ×0.952 |

**whale** (overall 36%):

| bucket | n | WR | factor |
|---|---|---|---|
| auction | 11 | 55% | ×1.187 |
| golden | 15 | 33% | ×0.971 |
| mid_am | 10 | 30% | ×0.947 |
| lunch | 18 | 33% | ×0.968 |
| pm | 3 | 67% | ×1.113 |
| power | 11 | 18% | ×0.826 |
| afterhours | 2 | 50% | ×1.036 |

## 3. Celdas MUERTAS apagadas en duro (fuente|símbolo)

| celda | n | WR | Wilson-hi | acción |
|---|---|---|---|---|
| bollinger|TSLA | 23 | 22% | 42% | 🔴 APAGADA |
| bollinger|QCOM | 22 | 23% | 43% | 🔴 APAGADA |

## 4. Peores celdas vivas (a vigilar)

| celda | n | WR | Wilson [lo,hi] |
|---|---|---|---|
| bollinger|SPY | 22 | 32% | [16,53] |
| bollinger|AVGO | 22 | 36% | [20,57] |
| cusum|QQQ | 30 | 37% | [22,54] |
| bollinger|ASML | 24 | 38% | [21,57] |
| cusum|TSLA | 13 | 38% | [18,64] |
| cusum|MU | 12 | 42% | [19,68] |
| bollinger|AMZN | 23 | 43% | [26,63] |
| cusum|AMD | 113 | 44% | [35,53] |
| bollinger|QQQ | 25 | 44% | [27,63] |
| bollinger|TXN | 25 | 44% | [27,63] |
| bollinger|NVDA | 22 | 45% | [27,65] |
| bollinger|NFLX | 27 | 48% | [31,66] |
