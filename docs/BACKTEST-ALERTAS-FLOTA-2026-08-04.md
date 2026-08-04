# BACKTEST ALERTAS FLOTA — lunes 2026-08-03 + 9 sesiones previas

Medido 2026-08-04. **Solo lectura**: nada de este documento toca código de producción.
Motor: `scripts/backtest_alertas_flota.py` (48 tests en `tests/test_backtest_alertas_flota.py`).
Reproducir:

```bash
./venv/bin/python scripts/backtest_alertas_flota.py --days 2026-07-21..2026-08-03 --cuts --sweep --json /tmp/bt.json
./venv/bin/python -m pytest tests/test_backtest_alertas_flota.py -q     # 48 passed
```

Método, sin atajos: **triple barrera** (TP/SL = k·ATR14 de 1m, timeout = `None` y NUNCA victoria,
barra ambigua resuelta contra nosotros), **Wilson 95 % sobre `n_eff`** corregido por correlación
**medida** y topado por clusters `(fecha, ventana de 5 min)`, **null de entrada aleatoria**
emparejado en `(sym, hora)` con la misma dirección (20 sorteos por alerta), **bootstrap por bloques
sobre la diferencia**, **BH-FDR q = 0,10** sobre los 95 tests a la vez, y **`n_eff < 30` ⇒
DATA-INSUFICIENTE** (no se publica probabilidad).

**Correlación medida en esta muestra**: `ρ̄(1 m) = 0,323`, `ρ̄(5 m) = 0,351` → se usa la mayor.
Con eso, 1.200 alertas BB REBOTE valen **`n_eff` = 366**, no 1.200.

---

## Titular

> **Ni una sola familia de alertas pasa BH-FDR. Cero KEEP de 95 tests.**
> La flota emitió **5.366 alertas de ticker en 10 sesiones** (390 el 08-03) y la que más volumen
> tiene —BB REBOTE, 1.200 etiquetadas— acierta **48,8 %** contra un null de **49,4 %**: es una
> moneda cara. Cuatro familias son **peores que el azar con CI que excluye el 0**, es decir
> **anti-señales**: CUSUM TERREMOTO, BB 15m RE-ENTRADA hablada, APERTURA FUERA DE BANDA y
> BALLENA PUTS. Un solo símbolo, **TSLA**, pasa BH-FDR él solo — por malo (edge −0,190, p = 0,0001).

---

## 1. Inventario de productores (fichero:línea) y volumen del 08-03

Cada string se verificó con `grep` contra su emisor; nada aquí está supuesto.

| tipo (clave interna) | productor `fichero:línea` | string exacto verificado | 08-03 | 10 sesiones |
|---|---|---|--:|--:|
| `ESTRUCTURAL_PIN` | `scripts/chart_bridge.py:3739` (BD) y `:3754` (feed) | `🧲 ESTRUCTURAL pin QQQ \| QQQ en su imán 690.0 — pin · prob 76%` | **179** | 570 |
| `ESTRUCTURAL_MAGNET` | `scripts/chart_bridge.py:3754` | `🧲 ESTRUCTURAL magnet MU \| MU se dirige a su imán 835.0 ↑` | **52** | 261 |
| `BB_REBOTE` / `_VETO` / `_STAR` | `scripts/bollinger_alarm.py:267` + `:283-291` | `X reventó la banda ABAJO y re-entró en …` | 49 / 11 / 2 | 1.734 / 489 / 108 |
| `BB15_REENTRADA(_MUTED)` | `scripts/bollinger_alarm.py:196` | `X reventó la banda 15 minutos ARRIBA y re-entró en …` | 0 / **47** | 65 / 644 |
| `BB_BANDWALK(_MUTED)` | `scripts/bollinger_alarm.py:253` | `X camina la banda ARRIBA tambien en 5 minutos` | 6 / 15 | 116 / 365 |
| `APERTURA_FUERA_BANDA` | `scripts/band_open_watch.py:120` | `🎯 APERTURA FUERA DE BANDA \| MSFT abrio 474.15 arriba de la banda 15m` | 20 | 145 |
| `CUSUM_TERREMOTO` | `bots/<sym>_signal_bot.cpp:1539` (ALZA) / `:1545` (CAIDA), 21 bots | `MU TERREMOTO CAIDA \| CUSUM: cayendo fuerte -5.20% px 780.12` | 9 | 164 |
| `BALLENA_CALLS/PUTS` | `scripts/opt_whale_watch.py:652` | `🐋 ALERTA BALLENA CALLS \| … strike dominante 310` | **0** | 117 / 96 |
| `BALLENA_CRECE` | `scripts/opt_whale_watch.py:614` | `🐋📈 ALERTA BALLENA CRECE` | **0** | 93 |
| `SPIKE_CALLS/PUTS` | `scripts/flow_pulse.cpp:529/548` | `🚀 SPIKE PUTS AVGO \| SPIKE de puts en AVGO: 3 mil contratos, 13 veces su ritmo` | 0 | 178 / 109 |
| `MANADA_CALLS/PUTS` (🐺, opciones) | `scripts/flow_pulse.cpp:411/418` | `🐺 MANADA A PUTS \| … 3 tickers en 12 minutos` | **0** | 34 / 23 |
| MANADA 🐘 (precio, la voz DANGER) | `scripts/fleet_consensus.py:139` | `🐘 MANADA ALCISTA ↑: n/30 de la flota` | 0 | **4** |
| `DIP_REAL` | `scripts/dip_alert.py:283` | `🩸 DIP REAL \| DIP REAL en MU: -19.8% desde el high de 5 dias` | 1 | 55 |

Los totales de la última columna son alertas **emitidas**; la tabla §2 mide sólo las que caen sobre
un sym-día con barras admitidas (3.907 de 5.366 — ver §3.4).
| — (ruido de infraestructura, no señal) | `scripts/truth_lock.py:344`, `scripts/ibkr_bar_bridge.py:329`, `scripts/flow_pulse.cpp:491/639`, `screener/*` | `🔒 TRUTH-LOCK INFO`, `🕳 CINTA CIEGA`, `🌊 FLOW PULSE v4`, `FINVIZ …` | 252 | — |

**El 08-03 en una línea: 642 líneas en el feed, 390 son alertas de ticker de la flota, y de esas
231 (59 %) son `🧲 ESTRUCTURAL`.** De los 179 PIN sólo **82 son textos distintos** (`QQQ en su imán
690.0 — pin · prob 76%` aparece **13 veces**); de los 52 MAGNET, **31** distintos.

**La cinta de opciones estuvo MUERTA el 08-03**: cero BALLENA, cero SPIKE, cero MANADA en toda la
sesión (`🕳 CINTA CIEGA` 14 veces en el feed). La espada de Napoleón estuvo envainada el lunes;
todo lo que se mide de flujo en este documento viene de las 9 sesiones previas.

---

## 2. Resultados: tipo × horizonte

`n` = alertas resueltas por barrera · `t/o` = timeouts (no cuentan) · `n_eff` = muestra efectiva ·
`hit` contra `null` de entrada aleatoria emparejada · `edge CI95` = bootstrap por bloques sobre la
diferencia · FDR = BH q = 0,10 sobre los 95 tests.
`k_tp = k_sl = 1,0·ATR14`. Horizontes 5 y 60 min en el JSON; aquí 15/30/cierre.

| tipo | H | n | t/o | n_eff | hit | Wilson95 (n_eff) | null | edge | edge CI95 | FDR | veredicto |
|---|--:|--:|--:|--:|--:|---|--:|--:|---|:-:|---|
| APERTURA_FUERA_BANDA | 15 | 75 | 2 | 7 | 0.347 | [0.082, 0.641] | 0.501 | −0.154 | [−0.274, −0.047] | no | DATA-INSUFICIENTE |
| APERTURA_FUERA_BANDA | 30 | 77 | 0 | 7 | 0.338 | [0.082, 0.641] | 0.489 | −0.152 | [−0.268, −0.035] | no | DATA-INSUFICIENTE |
| APERTURA_FUERA_BANDA | cierre | 77 | 0 | 7 | 0.338 | [0.082, 0.641] | 0.487 | −0.150 | [−0.267, −0.033] | no | DATA-INSUFICIENTE |
| BALLENA_CALLS | 15 | 81 | 1 | 63 | 0.543 | [0.418, 0.657] | 0.501 | +0.042 | [−0.019, 0.116] | no | KILL |
| BALLENA_CALLS | 30 | 81 | 1 | 63 | 0.543 | [0.418, 0.657] | 0.504 | +0.040 | [−0.022, 0.114] | no | KILL |
| BALLENA_CALLS | cierre | 82 | 0 | 63 | 0.537 | [0.418, 0.657] | 0.480 | +0.057 | [−0.016, 0.142] | no | KILL |
| BALLENA_CRECE | 15 | 57 | 1 | 40 | 0.509 | [0.352, 0.648] | 0.495 | +0.014 | [−0.091, 0.119] | no | KILL |
| BALLENA_CRECE | 30 | 58 | 0 | 40 | 0.500 | [0.352, 0.648] | 0.492 | +0.008 | [−0.096, 0.128] | no | KILL |
| BALLENA_CRECE | cierre | 58 | 0 | 40 | 0.500 | [0.352, 0.648] | 0.509 | −0.009 | [−0.130, 0.095] | no | KILL |
| **BALLENA_PUTS** | 15 | 57 | 0 | 43 | 0.404 | [0.264, 0.544] | 0.476 | −0.072 | [−0.160, 0.033] | no | **KILL** |
| **BALLENA_PUTS** | 30 | 57 | 0 | 43 | 0.404 | [0.264, 0.544] | 0.493 | −0.090 | [−0.177, 0.016] | no | **KILL** |
| **BALLENA_PUTS** | cierre | 57 | 0 | 43 | 0.404 | [0.264, 0.544] | 0.495 | −0.091 | [−0.179, 0.014] | no | **KILL** |
| **BB15_REENTRADA** (hablada) | 15 | 65 | 0 | 35 | 0.369 | [0.232, 0.537] | 0.471 | −0.102 | [−0.194, 0.021] | no | **KILL** |
| **BB15_REENTRADA** (hablada) | 30 | 65 | 0 | 35 | 0.369 | [0.232, 0.537] | 0.499 | −0.130 | [−0.238, **−0.007**] | no | **KILL** |
| **BB15_REENTRADA** (hablada) | cierre | 65 | 0 | 35 | 0.369 | [0.232, 0.537] | 0.489 | −0.119 | [−0.227, 0.004] | no | **KILL** |
| BB15_REENTRADA_MUTED | 15 | 400 | 10 | 184 | 0.472 | [0.402, 0.545] | 0.498 | −0.026 | [−0.088, 0.039] | no | KILL |
| BB15_REENTRADA_MUTED | 30 | 405 | 5 | 184 | 0.469 | [0.397, 0.539] | 0.508 | −0.039 | [−0.101, 0.030] | no | KILL |
| BB15_REENTRADA_MUTED | cierre | 410 | 0 | 185 | 0.466 | [0.394, 0.537] | 0.509 | −0.043 | [−0.104, 0.023] | no | KILL |
| BB_BANDWALK (hablada) | 15 | 95 | 0 | 78 | 0.442 | [0.331, 0.546] | 0.500 | −0.058 | [−0.153, 0.037] | no | KILL |
| BB_BANDWALK (hablada) | 30 | 95 | 0 | 78 | 0.442 | [0.331, 0.546] | 0.522 | −0.080 | [−0.175, 0.015] | no | KILL |
| BB_BANDWALK (hablada) | cierre | 95 | 0 | 78 | 0.442 | [0.331, 0.546] | 0.507 | −0.065 | [−0.159, 0.030] | no | KILL |
| **BB_BANDWALK_MUTED** | 15 | 235 | 2 | 116 | 0.540 | [0.453, 0.631] | 0.490 | +0.051 | [−0.038, 0.140] | no | KILL |
| **BB_BANDWALK_MUTED** | 30 | 236 | 1 | 116 | 0.542 | [0.453, 0.631] | 0.477 | **+0.065** | [−0.020, 0.150] | no | KILL |
| **BB_BANDWALK_MUTED** | cierre | 237 | 0 | 116 | 0.544 | [0.453, 0.631] | 0.496 | +0.049 | [−0.036, 0.137] | no | KILL |
| BB_REBOTE | 15 | 1194 | 7 | 364 | 0.487 | [0.435, 0.537] | 0.498 | −0.011 | [−0.049, 0.030] | no | KILL |
| BB_REBOTE | 30 | 1200 | 1 | 366 | 0.488 | [0.438, 0.540] | 0.494 | −0.006 | [−0.045, 0.034] | no | KILL |
| BB_REBOTE | cierre | 1200 | 1 | 366 | 0.488 | [0.438, 0.540] | 0.500 | −0.011 | [−0.051, 0.026] | no | KILL |
| BB_REBOTE_STAR ⭐ | 15 | 77 | 0 | 37 | 0.584 | [0.435, 0.737] | 0.484 | +0.101 | [−0.016, 0.205] | no | KILL |
| BB_REBOTE_STAR ⭐ | 30 | 77 | 0 | 37 | 0.584 | [0.435, 0.737] | 0.491 | +0.094 | [−0.023, 0.197] | no | KILL |
| BB_REBOTE_STAR ⭐ | cierre | 77 | 0 | 37 | 0.584 | [0.435, 0.737] | 0.481 | **+0.103** | [−0.013, 0.207] | no | KILL |
| BB_REBOTE_VETO | 15 | 313 | 1 | 181 | 0.470 | [0.398, 0.542] | 0.496 | −0.026 | [−0.093, 0.044] | no | KILL |
| BB_REBOTE_VETO | 30 | 314 | 0 | 181 | 0.471 | [0.398, 0.542] | 0.495 | −0.024 | [−0.094, 0.049] | no | KILL |
| BB_REBOTE_VETO | cierre | 314 | 0 | 181 | 0.471 | [0.398, 0.542] | 0.489 | −0.018 | [−0.084, 0.059] | no | KILL |
| **CUSUM_TERREMOTO** | 15 | 125 | 2 | 92 | 0.320 | [0.229, 0.416] | 0.498 | **−0.178** | [−0.282, **−0.058**] | no | **KILL** |
| **CUSUM_TERREMOTO** | 30 | 127 | 0 | 93 | 0.323 | [0.236, 0.423] | 0.493 | **−0.171** | [−0.281, **−0.045**] | no | **KILL** |
| **CUSUM_TERREMOTO** | cierre | 127 | 0 | 93 | 0.323 | [0.236, 0.423] | 0.475 | **−0.152** | [−0.254, **−0.026**] | no | **KILL** |
| DIP_REAL | 15 | 50 | 1 | 25 | 0.460 | [0.300, 0.665] | 0.512 | −0.052 | [−0.212, 0.128] | no | DATA-INSUFICIENTE |
| DIP_REAL | 30 | 51 | 0 | 25 | 0.471 | [0.300, 0.665] | 0.486 | −0.016 | [−0.192, 0.161] | no | DATA-INSUFICIENTE |
| DIP_REAL | cierre | 51 | 0 | 25 | 0.471 | [0.300, 0.665] | 0.480 | −0.009 | [−0.166, 0.187] | no | DATA-INSUFICIENTE |
| ESTRUCTURAL_MAGNET | 15 | 209 | 11 | 122 | 0.488 | [0.405, 0.579] | 0.497 | −0.009 | [−0.057, 0.044] | no | KILL |
| ESTRUCTURAL_MAGNET | 30 | 220 | 0 | 123 | 0.468 | [0.386, 0.559] | 0.503 | −0.035 | [−0.098, 0.020] | no | KILL |
| ESTRUCTURAL_MAGNET | cierre | 220 | 0 | 123 | 0.468 | [0.386, 0.559] | 0.498 | −0.030 | [−0.084, 0.029] | no | KILL |
| **ESTRUCTURAL_PIN** | 15 | 492 | 0 | 185 | **0.041** | [0.022, 0.083] | 0.021 | +0.020 | [−0.004, 0.054] | no | **KILL** |
| **ESTRUCTURAL_PIN** | 30 | 492 | 0 | 185 | **0.010** | [0.003, 0.039] | 0.007 | +0.003 | [−0.005, 0.015] | no | **KILL** |
| **ESTRUCTURAL_PIN** | cierre | 492 | 0 | 185 | **0.004** | [0.001, 0.030] | 0.003 | +0.001 | [−0.003, 0.008] | no | **KILL** |
| MANADA_CALLS 🐺 | 30 | 19 | 0 | 19 | 0.421 | [0.231, 0.637] | 0.521 | −0.100 | [−0.310, 0.111] | no | DATA-INSUFICIENTE |
| MANADA_PUTS 🐺 | 30 | 15 | 0 | 15 | 0.400 | [0.198, 0.643] | 0.545 | −0.145 | [−0.279, −0.012] | no | DATA-INSUFICIENTE |
| SPIKE_CALLS | 30 | 95 | 0 | 66 | 0.474 | [0.354, 0.588] | 0.487 | −0.013 | [−0.087, 0.071] | no | KILL |
| SPIKE_CALLS | cierre | 95 | 0 | 66 | 0.474 | [0.354, 0.588] | 0.499 | −0.025 | [−0.099, 0.049] | no | KILL |
| SPIKE_PUTS | 30 | 69 | 0 | 59 | 0.522 | [0.400, 0.647] | 0.488 | +0.034 | [−0.125, 0.179] | no | KILL |
| SPIKE_PUTS | cierre | 69 | 0 | 59 | 0.522 | [0.400, 0.647] | 0.497 | +0.025 | [−0.135, 0.170] | no | KILL |

### 2.1 Lectura honesta de la tabla

- **CUSUM TERREMOTO es la peor: acierta 32 % donde el azar da 49 %.** Y el signo aguanta en los
  **cuatro** umbrales de la curva de sensibilidad (edge −0,204 / −0,191 / −0,154 / −0,085 para
  k = 0,5 / 0,75 / 1,0 / 1,5). Un efecto que sobrevive a todo el barrido no es artefacto de
  umbral: **la alarma de terremoto está apuntando al revés**. (En el selloff del 07-27 acertó
  —doc `BACKTEST-ALARMAS-2026-07-27.md`— pero eso fueron 7 disparos de apertura de un día; sobre
  10 sesiones el continuar-la-vela pierde.)
- **El MUTE de Bollinger está INVERTIDO.** BAND-WALK hablada: 0,442 (edge −0,080). BAND-WALK
  *silenciada por p<55*: 0,542 (edge **+0,065**), y positiva en 3 de 4 umbrales. **La flota calla
  a las buenas y grita a las malas.** Mismo patrón con BB REBOTE ⭐ "degradada" (0,584, el hit más
  alto de todo el estudio) que perdió la voz el 2026-07-25 por un n = 20.
- **ESTRUCTURAL PIN canta "prob 74-76 %" y el precio se queda quieto el 1,0 % de las veces a
  30 min.** El número no está mal calibrado: mide **otra cosa** que el texto que canta. Y ni
  siquiera bate el null de contención (+0,003 [−0,005, +0,015]). Es el 46 % del feed del 08-03.
- **BB REBOTE (1.200 etiquetas, la fuente con más muestra de la casa) es una moneda**: 48,8 %
  contra 49,4 %. Coincide exactamente con la medición del 2026-07-25 (`0,482` vs null `0,496`,
  UNPROVEN). Un año de trabajo y sigue sin batir a entrar al azar a la misma hora en el mismo
  nombre.
- **Lo único que apunta hacia arriba y aguanta el barrido de k**: `BALLENA_CALLS` fadeada
  (edge +0,047/+0,045/+0,054/+0,110 en los 4 k, hit 0,543, n_eff = 63) y `BB_REBOTE_STAR`
  (+0,016/+0,071/+0,078/+0,064, hit 0,584, n_eff = 37). Ninguna pasa FDR. **Son candidatas, no
  señales.** La táctica espada-ballena (calls masivas = techo local) es lo que mejor pinta de todo
  el sistema y ni siquiera eso está probado.

### 2.2 Cortes pedidos

**Por hora** (H = 30, todas las alertas direccionales juntas): sólo **las 14:00-14:59 salen en
positivo** (hit 0,543 vs null 0,499, edge +0,044 [−0,001, +0,089], n_eff = 92) y **las 15:00-15:59
en negativo** (0,445 vs 0,494, edge −0,048 [−0,100, −0,000], n_eff = 81). Las 09:00 (apertura,
n = 402) dan −0,023. **Ninguna hora pasa BH-FDR sobre los 7 tests horarios.** La "ventana de oro"
09:45-10:30 de la doctrina **no aparece en los datos**: la hora 10 da −0,011.

**Por símbolo** (30 tests, BH-FDR q = 0,10): **pasa exactamente uno, TSLA, y por malo** —
hit 0,323 vs null 0,513, **edge −0,190, n = 117, n_eff = 108, p = 0,0001**. Le siguen sin pasar
GOOGL (−0,085, p = 0,085), EWY (−0,078), DRAM (−0,076), MU (−0,080). **Ningún símbolo tiene edge
positivo significativo.**

**Por régimen gamma** (`data/history/<fecha>/gex_snapshot.json`, cobertura 2.438 de 3.383 alertas —
sólo hay snapshot desde el 07-27): NEGATIVE −0,020 [−0,059, +0,019] · POSITIVE −0,024
[−0,051, +0,004]. **El régimen no separa nada.** Con 6 sesiones no se puede afirmar lo contrario
tampoco.

**Por confluencia** (≥2 tipos distintos sobre el mismo símbolo en ±3 min): **la confluencia es
PEOR que la alerta suelta.** Sola: 0,478 vs null 0,494 (edge −0,017, n = 2.703). Confluente: 0,461
vs 0,496 (edge −0,035, n = 558). **Dos alertas a la vez no baten a una: la correlación entre
detectores no aporta información, aporta simultaneidad.** Es exactamente lo que predice la
`anti-overfit-killlist` sobre rankings/compuestos en una flota 26/30 semis.

---

## 3. Los huecos de datos — lo que NO se pudo medir y por qué

Verdad de terreno primero, y sale cara.

### 3.1 Símbolos sin barras el 2026-08-03 → EXCLUIDOS (4 de 30)

| símbolo | barras RTH 08-03 | faltan | motivo |
|---|--:|--:|---|
| **EWY** | 0 | 390 | `data/bars_ewy_ibkr.txt` termina el **2026-07-31 16:44**; sin `data/history/2026-08-03/bars/ewy.txt` |
| **DRAM** | 0 | 390 | ídem |
| **SPCX** | 0 | 390 | ídem |
| **SKHY** | 0 | 390 | ídem |

Los 26 restantes tienen **390/390 barras RTH** y el archivo diario coincide **bit a bit** con el
buffer vivo (0 conflictos). Ese cuarteto no emitió ninguna alerta el 08-03, así que la exclusión no
pierde ninguna medición del lunes — pero **si hubieran hablado, la flota habría cantado sobre un
símbolo del que no tenemos ni un solo precio**. Y en el denominador de MANADA sí cuentan.

### 3.2 El premarket del 08-03 está roto → 20 alertas del lunes son inmedibles

Barras disponibles en la ventana **09:00-09:29** (necesarias para el ATR14 de una alerta de 09:31):

| fecha | símbolos completos (30/30 barras) | media de barras |
|---|--:|--:|
| 2026-07-27 | 30 de 30 | 30,0 |
| 2026-07-30 | 30 de 30 | 30,0 |
| 2026-07-31 | 30 de 30 | 30,0 |
| **2026-08-03** | **1 de 26** | **9,0** |

Consecuencia directa: las **20 `🎯 APERTURA FUERA DE BANDA` del 08-03 (09:31-09:32) no se pueden
etiquetar**: el ATR14 exige 14 barras 1m **contiguas** previas y no existen. El script las cuenta
en `no_atr` (21 en las 10 sesiones) y **no las rellena**. `APERTURA_FUERA_BANDA` acaba con
`n_eff = 7` sobre las 10 sesiones → **DATA-INSUFICIENTE**, pese a que su edge es −0,15 en los
cuatro umbrales de k. Es la sospecha más fuerte del estudio que no se puede publicar como número.

### 3.3 El pasado se reescribió: 07-30 y 07-31

El archivo diario (`data/history/<fecha>/bars/`) y el buffer vivo (`data/bars_<sym>_ibkr.txt`)
**discrepan en ~89 % de las barras RTH** de esos dos días (medido sobre QQQ SPY NVDA MU XLK:
1.727 de 1.950 barras el 07-30, 1.950 de 1.950 el 07-31), con **diferencia relativa mediana de
1,9-4,6 pb y máximo de 5,7 %**. El 08-03: **cero discrepancias**. Es la huella de las 98
`🔒 TRUTH-LOCK INFO` del feed ("PASADO reescrito, N barras materiales").

Decisión tomada y declarada: **manda el archivo diario** (se escribió a las 16:10 del mismo día,
del mismo feed que leyeron los bots) **salvo que la diferencia supere 50 pb, en cuyo caso la barra
se DESCARTA** — ahí no sabemos qué pasado es el bueno y no se elige ganador.

**Sensibilidad a esa decisión, medida.** Con el criterio estricto (descartar *cualquier*
discrepancia) se pierden **21 sym-días más** (217 excluidos en vez de 196) y 397 alertas medibles.
Los veredictos **no cambian de signo** en 18 de las 19 familias — CUSUM_TERREMOTO −0,153 → −0,171,
BB_REBOTE −0,012 → −0,006, PIN +0,004 → +0,003. **La excepción es `BALLENA_CALLS`, que pasa de
−0,030 a +0,040 al añadir muestra**: es la prueba directa de que su signo todavía no está fijado y
de por qué es *candidata* y no señal.

### 3.4 Sesiones que no existen

De las 14 fechas del rango, **10 tienen barras**: 07-21, 07-22, 07-23, 07-24, 07-27, 07-28, 07-29,
07-30, 07-31, 08-03. **07-25, 07-26, 08-01 y 08-02 son fin de semana** (0 barras, 0 sym-días
admitidos). El 07-24 tiene **374 barras RTH de media** (por debajo del mínimo de 380) → **los 30
sym-días de ese viernes están excluidos**. Total: **196 sym-días excluidos** y **1.510 alertas
descartadas por no tener barras del símbolo** (de 5.417 → 3.907 medibles).

### 3.5 Volumen = 0 en todas las barras

Las 390 barras RTH de los 26 símbolos del 08-03 traen **volumen 0** (son barras MIDPOINT del
bridge IBKR). **Ningún corte por volumen/RVOL es computable** con estos datos, ni el 08-03 ni
ningún otro día. Todo lo que en las alertas dice "RVOL" o "veces su ritmo" viene de la cadena de
opciones, no de estas barras.

### 3.6 El retraso de 16 min NO se ve en el precio cantado

Contraste medido: para 2.768 alertas se comparó el precio del mensaje con la barra archivada de ese
minuto. **Mediana de desviación 6,6 pb**, y el lag que mejor explica el precio cantado es **0
minutos en 2.098 casos** (76 %), 1 minuto en 217, y sólo 22 casos caen en 16 minutos. **El precio
que la alerta canta es el del minuto en que la canta.** El "delayed ~16 min" apuntado en `TODOS.md`
no aparece en el precio de las alertas del feed; si existió, fue en otra ruta (el mapa/cadena, o el
premarket). No se afirma más porque no se midió esa ruta.

### 3.7 Lo que se midió con la cinta ciega

El 08-03 **no hubo ni una alerta de flujo** (`opt_whale_watch` + `flow_pulse` mudos). Todo lo que
dice este documento sobre BALLENA / SPIKE / MANADA viene de las 9 sesiones previas, y de la 🐘
MANADA de `fleet_consensus.py` —la que tiene voz DANGER— **sólo hay 4 disparos en 10 sesiones**:
**imposible de medir, ni a favor ni en contra.**

---

## 4. Propuesta de filtros — cada uno con su número

"Buenas" = alertas de las 3 familias con edge positivo en ≥3 de los 4 umbrales de k
(`BB_BANDWALK_MUTED`, `BB_REBOTE_STAR`, `BALLENA_CALLS`): **17 el 08-03, 590 en 10 sesiones**.
Nada de esto se aplica solo: es propuesta, `data/signal_enable.json` no se toca sin Yunior.

| # | filtro | justificación numérica | mata el 08-03 | de ellas buenas | mata en 10 sesiones | de ellas buenas |
|---|---|---|--:|--:|--:|--:|
| **F1** | **`🧲 ESTRUCTURAL pin` fuera del feed** (a BD, para seguir midiendo) | contención real **1,0 %** a 30 min contra el `prob 74-76 %` que canta; edge +0,003 [−0,005, +0,015]; **97 de 179 son texto repetido** | **179 (45,9 %)** | **0** | 570 (10,6 %) | 0 |
| **F2** | **dedupe: mismo `sym`+texto exacto, cooldown 15 min** (`🧲` PIN y MAGNET) | 179 PIN → 82 textos únicos; 52 MAGNET → 31. `QQQ en su imán 690.0` se repite **13 veces** | **118 (30,3 %)** | **0** | 440 (8,2 %) | 0 |
| **F3** | **`🎈 BB 15m RE-ENTRADA` fuera (las dos variantes)** | hablada: hit 0,369 vs null 0,499, **edge −0,130 [−0,238, −0,007]**, negativa en 3 de 4 k. MUTED: −0,039. **Ni la que habla ni la que calla aportan** | 47 (12,1 %) | **0** | **709 (13,2 %)** | 0 |
| **F4** | **`TERREMOTO` deja de ser direccional** → banner sin dirección, o **se invierte** | hit 0,323 vs null 0,493, **edge −0,171 [−0,281, −0,045]**, negativa en **los 4** umbrales de k (−0,204/−0,191/−0,154/−0,085) | 9 (2,3 %) | **0** | 164 (3,1 %) | 0 |
| **F5** | **`🎯 APERTURA FUERA DE BANDA` fuera hasta poder medirla** | edge −0,15 en los 4 k, pero **`n_eff` = 7** por el premarket roto → **no se puede afirmar**; mientras tanto no debe competir por la atención | 20 (5,1 %) | **0** | 145 (2,7 %) | 0 |
| **F6** | **TSLA fuera del universo de alertas** (o a banner mudo) | **único símbolo que pasa BH-FDR de 30**: hit 0,323 vs null 0,513, **edge −0,190, n_eff = 108, p = 0,0001** | 11 (2,8 %) | 1 | 161 (3,0 %) | 18 |
| **F7** | **`🎈 BB REBOTE` normal y `[VETO]` fuera; se queda la ⭐** | REBOTE 0,488 vs 0,494 (n_eff = 366, edge −0,006: **moneda**); VETO 0,471 vs 0,495 (**el veto no separa**); ⭐ 0,584 (+0,103) | 60 (15,4 %) | **0** | **2.223 (41,4 %)** | 0 |
| **F8** | **invertir el mute p<55 en BAND-WALK** (que hable la MUTED, calle la otra) | hablada 0,442 (−0,080) vs silenciada 0,542 (**+0,065**): **10 pp de diferencia a favor de la que calla**. No mata alertas: reasigna la voz | 0 | 0 | 0 | 0 |
| **F9** | **ventana horaria 09:45-11:30 + 14:00-15:00** | h14 es la única positiva (+0,044 [−0,001, +0,089]); h15 la única negativa con CI que excluye 0 (−0,048 [−0,100, −0,000]) | 141 (36,2 %) | 6 | 3.029 (56,4 %) | 271 |
| — | **STACK F1+F2+F3+F4+F5+F6** | — | **312 (80,0 %)** | **1** | 1.971 (36,7 %) | 18 |
| — | **STACK + F7** | — | **368 (94,4 %)** | **1** | 4.126 (76,9 %) | 18 |

### Los tres de mejor relación ruido-eliminado / señal-conservada

1. **F1 — matar `🧲 ESTRUCTURAL pin` del feed.** Elimina **179 de 390 alertas del 08-03 (45,9 %) y
   NI UNA buena**. Ratio ruido/señal ≈ ∞. Es la mitad del feed del lunes a coste cero.
2. **F7 — matar `BB REBOTE` normal y `[VETO]`, dejar sólo la ⭐.** Elimina **2.223 alertas en 10
   sesiones (41,4 %), 60 el 08-03, y ninguna buena** — la ⭐ (edge +0,103, el mejor hit del
   estudio) se conserva entera. Es el mayor recorte absoluto del sistema.
3. **F2 — dedupe por texto exacto con cooldown.** Elimina **118 del 08-03 (30,3 %) sin perder ni un
   nivel distinto**: es puramente antirrepetición, no descarta información. Y es el único filtro
   que se puede aplicar sin decidir nada sobre la calidad de la fuente.

Detrás, **F4** (terremoto) y **F6** (TSLA) matan poco volumen pero son los dos con la evidencia
estadística más fuerte del documento: son los únicos números que sobreviven a BH-FDR o al barrido
completo de k.

---

## 5. Lo que NO se puede afirmar todavía

1. **Que alguna alerta tenga edge.** Cero de 95 tests pasan BH-FDR q = 0,10. Lo único que se puede
   decir de `BALLENA_CALLS` (+0,057 al cierre, positivo en los 4 k) y `BB_REBOTE_STAR` (+0,103) es
   **"candidata"**. Para probarlas hacen falta `n_eff ≥ 100` en su propia celda: al ritmo actual son
   **~25 sesiones más** para la ballena y **~35** para la ⭐.
2. **Que la manada funcione o no.** 🐺 (opciones): `n_eff` 19 y 15. 🐘 (`fleet_consensus`, la voz
   DANGER): **4 disparos en 10 sesiones**. **No hay muestra para tener opinión**, y la voz DANGER es
   precisamente la que más autoridad tiene sobre Yunior.
3. **Que la ventana de oro 09:45-10:30 exista.** La hora 10 da edge −0,011. Pero ninguna hora pasa
   FDR, así que tampoco se puede afirmar que NO exista. Hace falta partir por hora **dentro de cada
   tipo**, y eso exige 3-4× la muestra actual.
4. **Que el régimen gamma condicione algo.** Sólo hay `gex_snapshot.json` desde el **2026-07-27** (6
   de 10 sesiones), y POSITIVE vs NEGATIVE dan −0,024 y −0,020: indistinguibles. **Es forward-only**:
   la serie empieza el 07-27 y punto.
5. **Que `APERTURA FUERA DE BANDA` sea mala** (aunque lo parezca en los 4 umbrales de k): `n_eff` = 7
   por el premarket roto. **Arreglar el premarket es lo que desbloquea esta medición**, no más días.
6. **Nada sobre la ejecución real en opciones.** Todo esto se mide sobre el subyacente. Con spreads
   medianos del 9,1 % medidos el 2026-07-24 (`docs/SIGNALS-REAL-OPTION`), un edge de +0,05 en el
   subyacente puede ser negativo en la prima. **Un KEEP aquí no autorizaría una orden.**
7. **Nada sobre el 08-03 en flujo**: la cinta de opciones estuvo ciega toda la sesión.

### Qué haría falta medir, en orden de rentabilidad

1. **Arreglar el archivo de premarket 09:00-09:29** (1 de 26 símbolos completo el 08-03) →
   desbloquea `APERTURA_FUERA_BANDA` y todo lo que dispara antes de las 09:45.
2. **Archivar los 4 símbolos huérfanos** (EWY DRAM SPCX SKHY): sin barras no votan, y el precedente
   del denominador de MANADA (21/26 = 80,8 % disparó DANGER cuando 21/30 = 70 % no debía) está
   documentado en `~/CLAUDE.md`.
3. **20 sesiones más de cinta de opciones viva** para decidir sobre BALLENA_CALLS, que es la mejor
   candidata del sistema.
4. **Etiquetar sobre la PRIMA, no sobre el subyacente**, para las familias que sobrevivan.
5. **Congelar `gex_snapshot.json` a diario sin fallos** para que el corte por régimen sea posible
   en 2027 con 250 sesiones.

---

## Apéndice — reproducibilidad

- Motor: `scripts/backtest_alertas_flota.py` · Tests: `tests/test_backtest_alertas_flota.py` (48).
- Fuentes de alertas: `data/trading-signals/2026-07-21..2026-08-03.txt`.
- Verdad de terreno: `data/history/<fecha>/bars/<sym>.txt` ∪ `data/bars_<sym>_ibkr.txt`
  (archivo manda, tolerancia 50 pb, resto descartado).
- Régimen: `data/history/<fecha>/gex_snapshot.json`.
- Parámetros: `MIN_RTH=380`, `MIN_NEFF=30`, `KEEP_FLOOR=0.50`, `NULL_DRAWS=20`, `BOOT_N=2000`,
  `FDR_Q=0.10`, `K_GRID=[0.5, 0.75, 1.0, 1.5]`, `seed=7`.
- `data/notify_push.txt` **no se usó**: 676 líneas sin campo de fecha que cubren ~4 días
  (3 saltos hacia atrás en el reloj) → no se puede atribuir a una sesión sin inventar.

**SEÑAL-SOLAMENTE.** Ninguna cifra de este documento ordena nada al bróker, y ningún fichero de
producción fue modificado para producirlo.
