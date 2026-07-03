# FLOW-SCALP backtest — MISION 1 (spike de flujo = scalp rapido)

Generado: 2026-07-23 08:12  |  detector: spike>= 3.0x EMA(a=0.4), dom 2.0x, anti-artefacto 50.0x/bilateral

Fuentes de flujo por simbolo:
  - spy: flow_5min_spy.csv  | spikes crudos=95 | tras filtro-capitan=95
  - qqq: flow_5min_qqq.csv  | spikes crudos=93 | tras filtro-capitan=93
  - smh: flow_5min_smh.csv  | spikes crudos=646 | tras filtro-capitan=646
  - nvda: flow_5min_nvda.csv  | spikes crudos=94 | tras filtro-capitan=1
  - mu: flow_5min_mu.csv  | spikes crudos=100 | tras filtro-capitan=4

## Curva de reversion (MFE favorable al FADE, subyacente) — n total spikes=839

| horizonte | min | n | MFE medio | MFE mediana | adverso medio | edge (MFE-adv) |
|---|---|---|---|---|---|---|
| 1 barra | 5 | 839 | +0.16% | +0.10% | +0.15% | +0.01% |
| 2 barra | 10 | 839 | +0.23% | +0.15% | +0.24% | -0.01% |
| 3 barra | 15 | 839 | +0.29% | +0.19% | +0.31% | -0.02% |
| 6 barra | 30 | 839 | +0.45% | +0.25% | +0.47% | -0.02% |
| 12 barra | 60 | 839 | +0.64% | +0.34% | +0.70% | -0.06% |

## Scalp subyacente (TP a favor del fade / stop -0.3% / 12 barras)

| TP | n | WR | Wilson95 | 
|---|---|---|---|
| +0.3% | 839 | 52% | [49%, 55%] |
| +0.5% | 839 | 41% | [38%, 45%] |

### Por simbolo (WR al TP +0.3%)

| sym | n | WR+0.3% | Wilson95 | ret medio 12b (fade) |
|---|---|---|---|---|
| spy | 95 | 51% | [41%, 60%] | -0.01% |
| qqq | 93 | 60% | [50%, 70%] | -0.03% |
| smh | 646 | 51% | [47%, 55%] | -0.06% |
| nvda | 1 | 100% | [21%, 100%] | -0.21% |
| mu | 4 | 75% | [30%, 95%] | -4.56% |

## Scalp OPCION ATM real (Polygon) — pico de prima en ~30 min

| sym | n | WR>=+20% prima | pico medio | pico mediana |
|---|---|---|---|---|
| spy | 95 | 23% | +14.14% | +8.04% |
| qqq | 93 | 16% | +14.57% | +5.34% |
| smh | 636 | 25% | +21.73% | +6.82% |
| nvda | 1 | 100% | +21.54% | +21.54% |
| mu | 4 | 75% | +25.13% | +33.24% |
| GLOBAL | 829 | 24% [21%,27%] | | |

## VEREDICTO

Edge del scalp (TP+0.3%): WR 52%, Wilson95 [49%,55%]. ¿Batir 50% con confianza? NO.

## Conclusión maestra (2026-07-23, sobre 5-min REAL)
Con la granularidad correcta (5-min real, n=839), el spike de flujo **NO tiene edge como
fade rápido** — la reversión es simétrica a todos los horizontes. Cierra la tesis flow-fade
con muestra grande (los 76%/n=17 previos eran suerte). Defecto a recalibrar: SMH dispara 646
spikes en 5-min (detector demasiado sensible) y el filtro-capitán 3h suprime casi todos los
nombres (NVDA 94→1). El edge medido de la casa está en el filtro SELECTIVO (confluencia C4
59%/+19%; Yoel cambio_tend 64%/+31%), no en el gatillo de flujo.
