# Backtest honesto — alertas FINVIZ (screeners) · 3 sesiones 2026-08-03 → 2026-08-05

Generado 2026-08-06 11:27 por `scripts/backtest_finviz.py` (fetch por sesion) + agregador multi-sesion (pooling por fecha; misma metodologia y funciones del script — triple barrera 1.0·ATR14(1m), timeout=NULL, Wilson sobre n_eff, null emparejado, BH-FDR q=0.10). SEÑAL-SOLAMENTE.
Agregacion: k y n se SUMAN entre sesiones; n_eff se calcula POR SESION con el rho medido de esa sesion y se suma (sesiones independientes). El null se agrupa igual.

## Por sesion

| sesion | alertas | etiquetables | hit | null del dia | rho medido |
|---|---|---|---|---|---|
| 2026-08-03 | 184 | 141 | 61/141 = 43.3% | 51.7% (n=414) | 0.037 |
| 2026-08-04 | 225 | 106 | 59/106 = 55.7% | 54.1% (n=316) | 0.024 |
| 2026-08-05 | 296 | 192 | 113/192 = 58.9% | 48.9% (n=575) | 0.036 |

Null agrupado (mismo minuto, misma duracion, misma direccion, ticker al azar del universo liquido de cada dia): **51.0%** sobre n=1305.

## Por screener (agregado 3 sesiones)

| screener | decididas | hit | Wilson(n_eff) | n_eff | null emparejado del screener | p (vs null global) | BH-FDR | veredicto |
|---|---|---|---|---|---|---|---|---|
| buffett | 222 | 116/222 = 52.3% | [42.2%, 61.8%] | 96.0 | 53.0% (n=657) | 0.384 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| squeeze | 68 | 35/68 = 51.5% | [37.0%, 68.0%] | 36.0 | 47.0% (n=198) | 0.520 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| momentum | 149 | 82/149 = 55.0% | [44.1%, 65.9%] | 75.9 | 50.0% (n=450) | 0.186 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| **TODOS** | 439 | 233/439 = 53.1% | [44.5%, 61.8%] | 123.8 | 51.0% | 0.210 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |

## Todos los cortes (agregado)

| corte | valor | alertas | decididas | hit | Wilson(n_eff) | n_eff | p | BH-FDR | veredicto |
|---|---|---|---|---|---|---|---|---|---|
| hora | 09:30-10:30 oro | 176 | 175 | 55.4% | [43.4%, 66.2%] | 69.0 | 0.138 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| hora | 10:30-11:30 | 79 | 79 | 49.4% | [35.6%, 62.5%] | 48.7 | 0.659 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| hora | 11:30-14:00 picadora | 97 | 97 | 47.4% | [33.7%, 60.6%] | 49.0 | 0.792 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| hora | 14:00-16:00 | 64 | 63 | 55.6% | [39.9%, 68.8%] | 41.9 | 0.277 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| hora | premarket <09:30 | 25 | 25 | 64.0% | [43.7%, 83.7%] | 18.5 | 0.136 | no | DATA-INSUFICIENTE |
| rvol | RVOL 1.0-1.5 | 18 | 18 | 72.2% | [39.1%, 86.2%] | 11.6 | 0.058 | no | DATA-INSUFICIENTE |
| rvol | RVOL 1.5-2.5 | 164 | 163 | 52.8% | [41.7%, 63.1%] | 80.3 | 0.359 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| rvol | RVOL <1.0 | 186 | 186 | 48.9% | [38.6%, 59.2%] | 85.8 | 0.742 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| rvol | RVOL >=2.5 | 73 | 72 | 59.7% | [43.6%, 74.4%] | 34.6 | 0.087 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| score | abs(score) < possible-1 | 329 | 329 | 51.7% | [42.3%, 60.2%] | 116.9 | 0.430 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| score | abs(score) = maximo | 64 | 63 | 57.1% | [41.0%, 70.7%] | 39.2 | 0.200 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| score | abs(score) >= possible-1 | 48 | 47 | 57.4% | [39.3%, 71.8%] | 32.1 | 0.232 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| screener | buffett | 222 | 222 | 52.3% | [42.2%, 61.8%] | 96.0 | 0.384 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| screener | momentum | 151 | 149 | 55.0% | [44.1%, 65.9%] | 75.9 | 0.186 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| screener | squeeze | 68 | 68 | 51.5% | [37.0%, 68.0%] | 36.0 | 0.520 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| tipo | new_match | 99 | 98 | 54.1% | [40.4%, 67.0%] | 49.8 | 0.308 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| tipo | preopen_match | 2 | 1 | 0.0% | [0.0%, 79.3%] | 1.0 | 1.000 | no | DATA-INSUFICIENTE |
| tipo | weather_change | 340 | 340 | 52.9% | [43.7%, 61.1%] | 121.7 | 0.258 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| weather | BUY | 373 | 371 | 55.0% | [46.1%, 63.8%] | 118.1 | 0.071 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| weather | SELL | 68 | 68 | 42.6% | [28.7%, 59.1%] | 37.0 | 0.934 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| TODO | todas las alertas | 441 | 439 | 53.1% | [44.5%, 61.8%] | 123.8 | 0.210 | no | MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |

## Curva de sensibilidad (agregada; si el efecto vive en UN umbral, no es real)

| k_tp = k_sl (·ATR14 1m) | screener | decididas | hit | null | delta |
|---|---|---|---|---|---|
| 0.50 | buffett | 222 | 53.2% | 47.0% | +6.2 pp |
| 0.50 | squeeze | 68 | 52.9% | 47.0% | +6.0 pp |
| 0.50 | momentum | 151 | 47.0% | 47.0% | +0.1 pp |
| 0.50 | TODOS | 441 | 51.0% | 47.0% | +4.1 pp |
| 0.75 | buffett | 222 | 50.0% | 48.6% | +1.4 pp |
| 0.75 | squeeze | 68 | 55.9% | 48.6% | +7.3 pp |
| 0.75 | momentum | 150 | 52.7% | 48.6% | +4.0 pp |
| 0.75 | TODOS | 440 | 51.8% | 48.6% | +3.2 pp |
| 1.00 | buffett | 222 | 52.3% | 51.0% | +1.2 pp |
| 1.00 | squeeze | 68 | 51.5% | 51.0% | +0.4 pp |
| 1.00 | momentum | 149 | 55.0% | 51.0% | +4.0 pp |
| 1.00 | TODOS | 439 | 53.1% | 51.0% | +2.0 pp |
| 1.50 | buffett | 222 | 50.9% | 51.4% | -0.5 pp |
| 1.50 | squeeze | 67 | 47.8% | 51.4% | -3.6 pp |
| 1.50 | momentum | 146 | 51.4% | 51.4% | -0.0 pp |
| 1.50 | TODOS | 435 | 50.6% | 51.4% | -0.8 pp |

## Exclusiones (3 sesiones)

| razon | n |
|---|---|
| sin ATR14 1m previo (menos de 14 barras) | 153 |
| WATCH (sin direccion) | 80 |
| emitida despues del cierre (16:00 ET) | 27 |
| sin camino restante hasta el cierre | 2 |
| alerta fuera del rango de barras del dia | 2 |

## Comparacion con el informe del 2026-08-04 (1 sesion)

| corte | 08-04 (1 sesion) | hoy (3 sesiones) | veredicto antes -> ahora |
|---|---|---|---|
| TODO | 61/141 = 43.3% vs null 51.7% | 233/439 = 53.1% vs null 51.0% | UNPROVEN -> MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| buffett | 31/75 = 41.3% vs null 51.7% | 116/222 = 52.3% vs null 51.0% | DATA-INSUFICIENTE -> MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| momentum | 23/49 = 46.9% vs null 51.7% | 82/149 = 55.0% vs null 51.0% | DATA-INSUFICIENTE -> MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |
| squeeze | 7/17 = 41.2% vs null 51.7% | 35/68 = 51.5% vs null 51.0% | DATA-INSUFICIENTE -> MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar) |

Nota: 201 eventos del 2026-08-06 (premarket de hoy) quedan FUERA: Polygon (plan delayed) no sirve la sesion en curso. Se etiquetaran cuando cierre el dia.

