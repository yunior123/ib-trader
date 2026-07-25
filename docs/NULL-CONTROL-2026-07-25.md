# NULL CONTROL — 2026-07-25 09:56:59

La única salida de todo el roster que es una **RESTA**. `edge = p_señal − p_random`, con entradas aleatorias EMPAREJADAS en símbolo, bucket horario y régimen de sesión, sacadas de sesiones distintas.

- Celda de barrera **pre-comprometida**: `k_tp=1.0, k_sl=1.0, H=30 min` (no se elige a posteriori).
- Ambas ramas pasan por el **mismo** cargador de barras y la **misma** regla de ATR14 Wilder. Un null asimétrico mide el cargador, no el edge.
- `N` intentos sintéticos por fuente: 200 · bootstrap estacionario 2000 remuestreos, bloque medio 30.
- `n_eff = n/(1+(k-1)*rho_bar), topado por n_clusters (sym,fecha)`. Régimen = `session_range_over_avg_price` (proxy declarado), terciles por símbolo sobre sus propias sesiones.
- Fechas con señales: 2026-07-15, 2026-07-16, 2026-07-17, 2026-07-18, 2026-07-19, 2026-07-20, 2026-07-21, 2026-07-22, 2026-07-23, 2026-07-24, 2026-07-25

## Veredictos por fuente

| fuente | n | n_clusters | k syms | ρ̄ | **n_eff** | p señal | p random | **edge** | CI 95% del edge | p boot | BH-FDR (celdas ok/tot) | DSR | PSR | MinTRL | **veredicto** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bollinger | 1154 | 90 | 30 | 0.412 | **89.2** | 0.482 | 0.553 | **-0.071** | [-0.137, -0.010] | 0.027 | 0/2 | 0.003 | 0.108 | — | **DEAD** |
| cusum | 146 | 77 | 16 | 0.418 | **20.1** | 0.479 | 0.460 | **0.020** | [-0.067, +0.104] | 0.630 | 0/4 | 0.006 | 0.311 | — | **DATA-INSUFFICIENT** |
| dip | 5 | 5 | 5 | 0.169 | **3.0** | — | — | **—** | — | — | 0/0 | — | — | — | **DATA-INSUFFICIENT** |
| flow | 89 | 26 | 18 | 0.303 | **14.5** | 0.573 | 0.500 | **0.073** | [-0.020, +0.166] | 0.120 | 1/2 | 0.219 | 0.911 | 133 | **DATA-INSUFFICIENT** |
| structural | 81 | 4 | 3 | 0.271 | **4.0** | 0.642 | 0.387 | **0.255** | [+0.165, +0.353] | 0.001 | 1/6 | 0.899 | 0.992 | 38 | **DATA-INSUFFICIENT** |
| whale | 133 | 64 | 21 | 0.306 | **18.7** | 0.556 | 0.553 | **0.004** | [-0.097, +0.104] | 0.932 | 0/1 | 0.313 | 0.900 | 219 | **DATA-INSUFFICIENT** |

Motivo de cada veredicto:

- **bollinger** → `DEAD`: CI del edge entero <= 0 (peor que entrada aleatoria)
- **cusum** → `DATA-INSUFFICIENT`: n_eff 20.1 < 50
- **dip** → `DATA-INSUFFICIENT`: sin muestra suficiente para el bootstrap
- **flow** → `DATA-INSUFFICIENT`: n_eff 14.5 < 50
- **structural** → `DATA-INSUFFICIENT`: n_eff 4.0 < 50
- **whale** → `DATA-INSUFFICIENT`: n_eff 18.7 < 50

## Efecto de la corrección de muestra efectiva

| fuente | n cruda | n_eff | factor de inflación del CI que se estaba aplicando |
|---|---|---|---|
| bollinger | 1154 | 89.2 | **×3.6** |
| cusum | 146 | 20.1 | **×2.7** |
| dip | 5 | 3.0 | **×1.3** |
| flow | 89 | 14.5 | **×2.5** |
| structural | 81 | 4.0 | **×4.5** |
| whale | 133 | 18.7 | **×2.7** |

El factor es cuánto se estaba ESTRECHANDO cada intervalo de confianza por tratar símbolos correlacionados como muestras independientes.

## Celdas fuente × símbolo × bucket que SOBREVIVEN BH-FDR q=0.10

| fuente | sym | bucket | n | p | p random | q BH |
|---|---|---|---|---|---|---|
| structural | AAPL | golden | 7 | 1.000 | 0.318 | 0.0250 |
| flow | AMZN | lunch | 5 | 1.000 | 0.300 | 0.0781 |

## Qué se APAGARÍA (propuesta, NO aplicada)

- **DEAD (propone apagar en `signal_enable.json`)**: `bollinger`
- **UNPROVEN (banner solamente: jamás voz, jamás dimensiona)**: ninguna
- **DATA-INSUFFICIENT (se dice 'todavía no sabemos', en voz alta)**: `cusum`, `dip`, `flow`, `structural`, `whale`

> La propuesta está en `data/signal_enable.PROPUESTO.json`. **`data/signal_enable.json` NO se ha tocado**: silenciar una alarma en vivo lo decide Yunior. Compromiso previo de la ficha: los veredictos UNPROVEN se aceptan; el test no se afloja nunca.

