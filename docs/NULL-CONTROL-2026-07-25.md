# NULL CONTROL — 2026-07-25 09:58:10

La única salida de todo el roster que es una **RESTA**. `edge = p_señal − p_random`, con entradas aleatorias EMPAREJADAS en símbolo, bucket horario y régimen de sesión, sacadas de sesiones distintas.

- Celda de barrera **pre-comprometida**: `k_tp=1.0, k_sl=1.0, H=30 min` (no se elige a posteriori).
- Ambas ramas pasan por el **mismo** cargador de barras y la **misma** regla de ATR14 Wilder. Un null asimétrico mide el cargador, no el edge.
- `N` intentos sintéticos por fuente: 2000 · bootstrap estacionario 2000 remuestreos, bloque medio 30.
- `n_eff = n/(1+(k-1)*rho_bar), topado por n_clusters (sym,fecha)`. Régimen = `session_range_over_avg_price` (proxy declarado), terciles por símbolo sobre sus propias sesiones.
- Fechas con señales: 2026-07-15, 2026-07-16, 2026-07-17, 2026-07-18, 2026-07-19, 2026-07-20, 2026-07-21, 2026-07-22, 2026-07-23, 2026-07-24, 2026-07-25

## Veredictos por fuente

| fuente | n | n_clusters | k syms | ρ̄ | **n_eff** | p señal | p random | **edge** | CI 95% del edge | p boot | BH-FDR (celdas ok/tot) | DSR | PSR | MinTRL | **veredicto** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bollinger | 1154 | 90 | 30 | 0.412 | **89.2** | 0.482 | 0.496 | **-0.014** | [-0.048, +0.019] | 0.365 | 0/117 | 0.003 | 0.108 | — | **UNPROVEN** |
| cusum | 146 | 77 | 16 | 0.418 | **20.1** | 0.479 | 0.491 | **-0.011** | [-0.067, +0.043] | 0.710 | 0/5 | 0.006 | 0.311 | — | **DATA-INSUFFICIENT** |
| dip | 5 | 5 | 5 | 0.169 | **3.0** | — | — | **—** | — | — | 0/0 | — | — | — | **DATA-INSUFFICIENT** |
| flow | 89 | 26 | 18 | 0.303 | **14.5** | 0.573 | 0.489 | **0.084** | [+0.001, +0.158] | 0.050 | 0/2 | 0.219 | 0.911 | 133 | **DATA-INSUFFICIENT** |
| structural | 81 | 4 | 3 | 0.271 | **4.0** | 0.642 | 0.503 | **0.139** | [+0.063, +0.220] | 0.001 | 0/6 | 0.899 | 0.992 | 38 | **DATA-INSUFFICIENT** |
| whale | 133 | 64 | 21 | 0.306 | **18.7** | 0.556 | 0.495 | **0.061** | [-0.033, +0.151] | 0.195 | 0/1 | 0.313 | 0.900 | 219 | **DATA-INSUFFICIENT** |

Motivo de cada veredicto:

- **bollinger** → `UNPROVEN`: el CI del edge cruza 0; no pasa BH-FDR q=0.10; DSR 0.003 <= 0.95
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

### Segunda puerta de cordura: ¿muerde la corrección?

La ficha exige demostrar que `n_eff` + BH-FDR **cambia** veredictos. Si no cambiara nada, la corrección no se estaría aplicando.

| fuente | veredicto SIN corrección (n cruda, sin FDR/DSR) | veredicto CON corrección | cambió |
|---|---|---|---|
| bollinger | UNPROVEN | **UNPROVEN** | no |
| cusum | UNPROVEN | **DATA-INSUFFICIENT** | SÍ |
| dip | DATA-INSUFFICIENT | **DATA-INSUFFICIENT** | no |
| flow | PROBADO | **DATA-INSUFFICIENT** | SÍ |
| structural | PROBADO | **DATA-INSUFFICIENT** | SÍ |
| whale | UNPROVEN | **DATA-INSUFFICIENT** | SÍ |

**4 de 6 fuentes cambian de veredicto** al aplicar la muestra efectiva y el multiple testing. La puerta está activa.

## Celdas fuente × símbolo × bucket que SOBREVIVEN BH-FDR q=0.10

> **NINGUNA.** Cero celdas de 131 baten a la entrada aleatoria tras corregir el multiple testing. Con 11 fechas de señales ése es el resultado esperable y es el resultado que se publica.

## Qué se APAGARÍA (propuesta, NO aplicada)

- **DEAD (propone apagar en `signal_enable.json`)**: ninguna
- **UNPROVEN (banner solamente: jamás voz, jamás dimensiona)**: `bollinger`
- **DATA-INSUFFICIENT (se dice 'todavía no sabemos', en voz alta)**: `cusum`, `dip`, `flow`, `structural`, `whale`

> La propuesta está en `data/signal_enable.PROPUESTO.json`. **`data/signal_enable.json` NO se ha tocado**: silenciar una alarma en vivo lo decide Yunior. Compromiso previo de la ficha: los veredictos UNPROVEN se aceptan; el test no se afloja nunca.

