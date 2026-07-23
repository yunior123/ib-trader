# Backtest espada-ballena — 0DTE QQQ primer-OTM (2026-07)

**Criterio pre-registrado**: pasar a shadow-sim en vivo si expectancy neta > 0
en >=1 horizonte Y el limite inferior Wilson 95% del WR > 50%. Si n < 30: DATA-INSUFFICIENT.

- Alertas 🐋 totales: 41 | en IMPACT_SYMS: 25 (descartadas por simbolo: 16) | en ventanas del bot: 17 | con barra y premium valido: 17
- Granularidad: **1 minuto** — la mecanica de segundos NO se mide aqui (se valida en sim).
- Premium sintetico BS (IV por hora {9: 0.28, 10: 0.24, 11: 0.2, 12: 0.18, 13: 0.18, 14: 0.2, 15: 0.26}), costos: spread completo + $1.30 RT.

| hold | spread | n | WR | Wilson 95% | media $ | mediana $ | total $ |
|---|---|---|---|---|---|---|---|
| 1m | 3c | 17 | 24% | [10%, 47%] | -9.42 | -5.66 | -160.21 |
| 1m | 5c | 17 | 12% | [3%, 34%] | -11.42 | -7.66 | -194.21 |
| 2m | 3c | 17 | 47% | [26%, 69%] | -8.20 | -2.55 | -139.44 |
| 2m | 5c | 17 | 47% | [26%, 69%] | -10.20 | -4.55 | -173.44 |
| 5m | 3c | 17 | 59% | [36%, 78%] | +0.82 | +0.36 | +13.97 |
| 5m | 5c | 17 | 47% | [26%, 69%] | -1.18 | -1.64 | -20.03 |

Contexto subyacente: fade a +15m gana 11/17 veces, media +0.285 $QQQ.

## VEREDICTO: **DATA-INSUFFICIENT** (n=17 < 30 o edge no separable de ruido).
Accion: dejar acumular `data/whale_flow_hist.jsonl` + `data/nbbo_hist_qqq_*.txt`
(hooks activos desde 2026-07-21) >=2 semanas y re-correr. Mientras: shadow-sim
diario con `--sim --data data` para validar mecanica, SIN veredicto de edge.

### Detalle por alerta (entrada = close del minuto de la alerta)

| dia | hora | sym | lado | K | prem0 | +1m | +2m | +5m |
|---|---|---|---|---|---|---|---|---|
| 2026-07-20 | 10:12 | NVDA | CALLS | 699P | $1.32 | -20c | -25c | -5c |
| 2026-07-20 | 10:13 | QQQ | PUTS | 701C | $1.43 | +6c | +34c | -3c |
| 2026-07-20 | 10:13 | META | CALLS | 700P | $1.54 | -6c | -32c | +1c |
| 2026-07-20 | 10:19 | AAPL | PUTS | 701C | $1.35 | -28c | -37c | +7c |
| 2026-07-20 | 10:44 | MSFT | CALLS | 700P | $1.48 | -9c | -29c | +45c |
| 2026-07-20 | 10:50 | AVGO | CALLS | 699P | $1.36 | +5c | +21c | +11c |
| 2026-07-20 | 11:15 | GOOGL | CALLS | 700P | $1.17 | -16c | -28c | -22c |
| 2026-07-20 | 14:59 | META | CALLS | 698P | $0.56 | -23c | -20c | +31c |
| 2026-07-20 | 15:05 | MU | PUTS | 698C | $0.43 | +14c | +12c | +33c |
| 2026-07-20 | 15:05 | QQQ | PUTS | 698C | $0.43 | +14c | +12c | +33c |
| 2026-07-20 | 15:05 | MSFT | CALLS | 697P | $0.60 | -15c | -15c | -32c |
| 2026-07-20 | 15:06 | AVGO | CALLS | 697P | $0.45 | +0c | +6c | +5c |
| 2026-07-20 | 15:06 | GOOGL | CALLS | 697P | $0.45 | +0c | +6c | +5c |
| 2026-07-21 | 10:39 | AMZN | CALLS | 706P | $1.59 | +2c | +33c | -24c |
| 2026-07-21 | 11:23 | NVDA | CALLS | 708P | $1.12 | -8c | -15c | -17c |
| 2026-07-21 | 14:07 | MU | CALLS | 709P | $0.47 | -1c | +2c | +7c |
| 2026-07-21 | 14:51 | MU | CALLS | 709P | $0.44 | -1c | +7c | +15c |
