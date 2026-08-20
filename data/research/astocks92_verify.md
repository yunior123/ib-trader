# @astocks92 — verificacion contra precio real

Generado 2026-08-08T19:01:21Z · **102 llamadas** extraidas de sus posts (2025-08-06 → 2026-08-07).

## Veredicto

**No separa del azar: lo separa POR DEBAJO.** Sobre las 45 llamadas direccionales resueltas y comparables,
acierta **42.2%**; entradas ALEATORIAS con la misma direccion, la misma geometria de barreras (en ATR),
el mismo ticker y la misma hora del dia aciertan **58.5%** (2243 muestras).
p-valor de 'mejor que el azar' = **0.9941** (o sea: no). p-valor de 'peor que el azar' = **0.0141**
(Monte Carlo remuestreando por POST, que es la unidad independiente: **0.0157**).

Expectancia medida: **-0.179 R** por llamada frente a **0.158 R** del azar con esas mismas barreras.

Muestra: 52 llamadas resueltas en 43 posts distintos. Pasa de 30, pero es JUSTO:
el intervalo de confianza va de 32.7% a 59.6% (bootstrap por cluster de post). Con esa anchura,
cualquier afirmacion del tipo '13/15' o '6-0' que el publica es indistinguible de suerte con esta muestra.

## Metodo (fijado ANTES de mirar resultados)
- **datos**: Polygon aggs 5m (acciones/ETF/BTC/oro) + Yahoo chart (SPX/VIX/ES_F, 5m si <52 dias, si no 1h)
- **etiqueta**: triple barrera; objetivo/stop del post si existen; si falta uno se refleja simetrico; si faltan los dos, +-1.0xATR(14) de la barra usada
- **relleno**: entrada en la apertura de la primera barra RTH tras el post; llamadas condicionales exigen que el gatillo se toque (si no: NO_ACTIVADO)
- **horizonte**: S=sesion de entrada (si entra en la ultima hora se extiende a la sesion siguiente); S+N=N sesiones; D:fecha; FY=hasta 2026-08-07 (en curso)
- **conservador**: si una vela toca objetivo y stop, se cuenta STOP
- **control**: 60 entradas aleatorias por llamada, mismo ticker, misma hora del dia +-45min, MISMA geometria en unidades de ATR y mismo numero de barras, MISMA direccion

## Por bucket

| bucket | n | aciertos | fallos | resueltas | sin resolver | gatillo nunca tocado | win rate | Wilson 95% |
|---|---|---|---|---|---|---|---|---|
| direccional (triple barrera) | 76 | 24 | 28 | 52 | 9 | 12 | 46.2% | [33.3%, 59.5%] |
| rango / pin / dia flat | 12 | 5 | 7 | 12 | 0 | 0 | 41.7% | [19.3%, 68.0%] |
| no evaluable | 3 | 0 | 0 | 0 | 0 | 0 | - | - |
| techo o 'no toca X' | 6 | 4 | 2 | 6 | 0 | 0 | 66.7% | [30.0%, 90.3%] |
| prediccion anual | 1 | 0 | 0 | 0 | 0 | 0 | - | - |
| idea de contrato | 3 | 0 | 0 | 0 | 0 | 0 | - | - |
| dia rojo/verde | 1 | 1 | 0 | 1 | 0 | 0 | 100.0% | [20.6%, 100.0%] |

## Control aleatorio

| | n | win rate | IC 95% |
|---|---|---|---|
| llamadas REALES comparables | 45 | 42.2% | Wilson [29.0%, 56.7%] · bootstrap-cluster [28.9%, 56.4%] |
| entradas ALEATORIAS misma geometria | 2243 | 58.5% | Wilson [56.4%, 60.5%] |


| direccion | n | acierta | azar (misma geometria) |
|---|---|---|---|
| long | 23 | 43.5% [25.6%, 63.2%] | 61.0% (n=1265) |
| short | 22 | 40.9% [23.3%, 61.3%] | 55.1% (n=978) |

Los DOS lados rinden por debajo de su propio azar: no es 'estuvo corto en un mercado alcista'.

Payoff medio de las 52 direccionales resueltas: **-0.11 R** (RR medio de las barreras 1.035).

## Ideas de CONTRATO — prima real (Polygon, 5m)

| id | contrato | prima ref | max | final | max % | veredicto |
|---|---|---|---|---|---|---|
| 61 | `O:META260320C00650000` | 22.6 | 38.65 | 38.35 | 71.0 | ACIERTO |
| 96 | `O:AMD251031C00270000` | 2.88 | 5.72 | 0.01 | 98.6 | MEDIDO |
| 4 | `O:AAPL260828C00315000` | 3.98 | 9 | 6.55 | 126.1 | MEDIDO |
| 35 | `O:SPY260522P00730000` | 3.17 | 4.32 | 0.01 | 36.3 | MEDIDO |
| 50 | `O:NOW260417C00120000` | 3.6 | 12.4 | 0.03 | 244.4 | MEDIDO |
| 57 | `O:SLV260417C00130000` | 7 | 14.88 | 0.01 | 112.6 | MEDIDO |
| 76 | `O:CCL260130P00032000` | 1.8 | 4 | 2.32 | 122.2 | MEDIDO |
| 74 | `O:OXY260618C00045000` | 1.8 | 5 | 4 | None | DEGENERADO |
| 99 | `O:AMKR260618C00036000` | 3.1 | 22.24 | 12.69 | 617.4 | MEDIDO |

Sin control aleatorio de opciones -> **no es puntuable como edge**, es descripcion. El patron medido: casi todas las ideas
dieron un pico de prima explotable en algun momento, y la mayoria expiraron sin valor si se aguantaban.

## Detalle por llamada

| id | fecha UTC | ticker | tipo | dir | estado | barrera/criterio | numeros | azar |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-08-07 20:29 | QQQ | dir |  | EN_CURSO | post posterior a la ultima barra disponible (2026-08-07 cierre); aun s |  |  |
| 2 | 2026-08-07 20:29 | SPY | dir |  | EN_CURSO | post posterior a la ultima barra disponible (2026-08-07 cierre); aun s |  |  |
| 3 | 2026-08-05 19:39 | TSLA | dir | short | ACIERTO | objetivo | entrada=322.34 objetivo=321.7457 stop=322.9343 | 0.65 (n=60) |
| 4 | 2026-08-04 14:31 | AAPL | dir | long | ACIERTO | objetivo | entrada=306.28 objetivo=307.5268 stop=305.0332 | 0.50 (n=60) |
| 5 | 2026-08-03 20:51 | PLTR | dir | long | ACIERTO | objetivo | entrada=142.5 objetivo=151.75 stop=133.25 | 0.00 (n=2) |
| 6 | 2026-07-29 17:48 | QCOM | rango |  | FALLO | cierre dentro del rango | cierre=151.58 max=154.1595 min=146 |  |
| 7 | 2026-07-24 13:20 | SPY | rango |  | ACIERTO | cierre dentro del rango | cierre=738.85 max=743.72 min=737.29 |  |
| 8 | 2026-07-24 13:20 | QQQ | dir | short | ACIERTO | objetivo | entrada=690.41 objetivo=683.4 stop=697.42 | 0.62 (n=26) |
| 9 | 2026-07-23 13:08 | SPY | dir | short | FALLO | stop | entrada=736.03 objetivo=733.63 stop=738.43 | 0.57 (n=21) |
| 10 | 2026-07-23 13:08 | QQQ | dir | short | ACIERTO | objetivo | entrada=693.03 objetivo=688.71 stop=697.35 | 0.67 (n=18) |
| 11 | 2026-07-23 13:08 | SPY | dir | long | SIN_RESOLVER | tiempo | entrada=739.37 objetivo=744.27 stop=734.47 | 0.14 (n=14) |
| 12 | 2026-07-21 16:56 | SPX | dir |  | NO_ACTIVADO | gatillo 7516.0 above nunca tocado |  |  |
| 13 | 2026-07-17 13:18 | VIX | no_evaluable |  | NO_EVALUABLE | 'PIVOT 17.15 LONG BELOW, T2 19.17': direccion y objetivo se contradice |  |  |
| 14 | 2026-07-07 13:03 | SPY | rango |  | ACIERTO | cierre dentro del rango | cierre=747.66 max=750.96 min=745.21 |  |
| 15 | 2026-06-30 13:28 | SPY | techo |  | FALLO | no superar el techo en el horizonte |  |  |
| 16 | 2026-06-30 13:28 | QQQ | techo |  | FALLO | no superar el techo en el horizonte |  |  |
| 17 | 2026-06-26 23:14 | MSTR | dir | short | SIN_RESOLVER | tiempo | entrada=85.67 objetivo=50.0 stop=121.34 | 0.43 (n=14) |
| 18 | 2026-06-26 15:13 | SPY | rango |  | FALLO | cierre dentro del rango | cierre=729.09 max=736.53 min=716.58 |  |
| 19 | 2026-06-26 15:13 | QQQ | rango |  | FALLO | cierre dentro del rango | cierre=705.84 max=715.555 min=705.1 |  |
| 20 | 2026-06-26 13:04 | MU | dir | long | YA_CUMPLIDO_AL_POSTEAR | el objetivo ya estaba alcanzado cuando se publico el post | entrada=1139.075 objetivo=600.0 |  |
| 21 | 2026-06-26 13:04 | MSTR | dir | short | SIN_RESOLVER | tiempo | entrada=83.23 objetivo=50.0 stop=116.46 | 0.72 (n=18) |
| 22 | 2026-06-26 13:04 | NVDA | no_toca |  | ACIERTO | no alcanzar el nivel antes de la fecha | extremo=224.76 |  |
| 23 | 2026-06-26 13:04 | SPY | ytd |  | EN_CURSO | +6-8% a cierre de 2026 (no vence hasta 2026-12-31) | ytd_pct=13.4 |  |
| 24 | 2026-06-23 14:09 | SPX | dir | long | FALLO | stop | entrada=7411.77 objetivo=7430.3364 stop=7393.2036 | 0.52 (n=60) |
| 25 | 2026-06-23 14:09 | SPY | dir | long | FALLO | stop | entrada=738.41 objetivo=742.0 stop=734.82 | 0.54 (n=59) |
| 26 | 2026-06-23 14:09 | QQQ | dir | long | ACIERTO | objetivo | entrada=721.81 objetivo=723.0 stop=720.62 | 0.37 (n=60) |
| 27 | 2026-06-22 17:22 | SPX | rango |  | FALLO | cierre dentro del rango | cierre=7475.46 max=7485.8101 min=7460.0098 |  |
| 28 | 2026-06-22 17:22 | SPY | rango |  | ACIERTO | cierre dentro del rango | cierre=744.37 max=745.74 min=743.13 |  |
| 29 | 2026-06-22 17:22 | QQQ | dir | long | FALLO | stop | entrada=738.0 objetivo=738.9067 stop=737.0933 | 0.55 (n=60) |
| 30 | 2026-06-18 17:33 | SPX | rango |  | FALLO | cierre dentro del rango | cierre=7497.8599 max=7510.1699 min=7482.3901 |  |
| 31 | 2026-06-18 17:33 | QQQ | cierre_cerca |  | FALLO | cierre a +-0.25% | objetivo=742.0 cierre=739.66 |  |
| 32 | 2026-06-12 13:08 | SPY | dir | short | FALLO | stop | entrada=735.85 objetivo=730.4 stop=741.3 | 0.56 (n=32) |
| 33 | 2026-05-19 14:49 | SPX | dir | short | FALLO | stop | entrada=7341.1001 objetivo=7320.0 stop=7362.2002 | 0.61 (n=54) |
| 34 | 2026-05-19 14:49 | SPY | dir | short | ACIERTO | objetivo | entrada=733.0 objetivo=732.0 stop=734.0 | 0.40 (n=60) |
| 35 | 2026-05-19 14:10 | SPY | dir | short | ACIERTO | objetivo | entrada=733.36 objetivo=731.7331 stop=734.9869 | 0.58 (n=60) |
| 36 | 2026-05-18 13:20 | QQQ | dir |  | NO_ACTIVADO | gatillo 713.68 above nunca tocado |  |  |
| 37 | 2026-05-18 13:20 | QQQ | dir | short | ACIERTO | objetivo | entrada=711.06 objetivo=705.06 stop=717.06 | 0.69 (n=35) |
| 38 | 2026-05-08 12:56 | SPY | dir |  | NO_ACTIVADO | gatillo 730.02 below nunca tocado |  |  |
| 39 | 2026-05-07 12:44 | SPY | dir | long | SIN_RESOLVER | tiempo | entrada=730.02 objetivo=735.96 stop=724.08 | 0.17 (n=6) |
| 40 | 2026-05-07 12:44 | SPY | dir |  | NO_ACTIVADO | gatillo 729.43 below nunca tocado |  |  |
| 41 | 2026-04-17 20:33 | SPY | no_evaluable |  | NO_EVALUABLE | post retrospectivo tras el cierre ('where did we cross?'), no es llama |  |  |
| 42 | 2026-04-12 22:11 | SPY | dir | short | FALLO | stop | entrada=677.41 objetivo=671.57 stop=683.25 | 0.55 (n=53) |
| 43 | 2026-04-09 12:15 | TSLA | dir |  | NO_ACTIVADO | gatillo 320.0 below nunca tocado |  |  |
| 44 | 2026-04-07 13:18 | SPY | dir | short | FALLO | stop | entrada=653.3 objetivo=649.04 stop=657.56 | 0.50 (n=4) |
| 45 | 2026-04-07 13:18 | SPY | dir | long | FALLO | stop | entrada=656.8 objetivo=660.96 stop=652.64 | 0.44 (n=9) |
| 46 | 2026-03-24 14:44 | SPX | dir | long | FALLO | stop | entrada=6586.2202 objetivo=6600.0 stop=6572.4404 | 0.57 (n=60) |
| 47 | 2026-03-23 00:56 | BTC | dir |  | NO_ACTIVADO | gatillo 60000.0 below nunca tocado |  |  |
| 48 | 2026-03-22 22:31 | SPX | dir |  | NO_ACTIVADO | gatillo 6475.0 below nunca tocado |  |  |
| 49 | 2026-03-22 22:31 | SPX | dir |  | NO_ACTIVADO | gatillo 6460.0 below nunca tocado |  |  |
| 50 | 2026-02-26 14:59 | NOW | dir | long | FALLO | stop | entrada=109.495 objetivo=110.4089 stop=108.5811 | 0.42 (n=60) |
| 51 | 2026-02-16 13:29 | NFLX | dir | short | FALLO | stop | entrada=76.92 objetivo=72.0 stop=81.84 | 0.78 (n=41) |
| 52 | 2026-01-31 18:53 | BTC | dir | short | SIN_RESOLVER | tiempo | entrada=65000.0 objetivo=48750.0 stop=81250.0 | 0.64 (n=33) |
| 53 | 2026-01-30 12:15 | MSTR | dir | short | FALLO | stop | entrada=139.995 objetivo=130.0 stop=149.99 | 0.57 (n=58) |
| 54 | 2026-01-26 17:53 | BTC | dir |  | NO_ACTIVADO | gatillo 90970.0 above nunca tocado |  |  |
| 55 | 2026-01-26 17:49 | GOLD | dir | long | ACIERTO | objetivo | entrada=5100.63 objetivo=5250.0 stop=4951.26 | 0.77 (n=57) |
| 56 | 2026-01-26 17:49 | SLV | dir | long | FALLO | stop | entrada=105.38 objetivo=130.0 stop=80.76 | 0.90 (n=58) |
| 57 | 2026-01-26 15:15 | SLV | dir | long | FALLO | stop | entrada=101.53 objetivo=102.513 stop=100.547 | 0.47 (n=60) |
| 58 | 2026-01-21 16:17 | MU | dir | long | ACIERTO | objetivo | entrada=391.45 objetivo=500.0 stop=282.9 | 1.00 (n=60) |
| 59 | 2026-01-20 01:44 | ES_F | dir | short | ACIERTO | objetivo | entrada=6964.0 objetivo=6865.56 stop=7062.44 | 1.00 (n=2) |
| 60 | 2026-01-20 01:44 | ES_F | dir |  | NO_ACTIVADO | gatillo 6914.0 above nunca tocado |  |  |
| 61 | 2026-01-19 23:01 | META | premium |  | PENDIENTE_PRIMA |  |  |  |
| 62 | 2026-01-18 21:30 | AAPL | dir | long | ACIERTO | objetivo | entrada=252.73 objetivo=273.4 stop=232.06 | 0.56 (n=9) |
| 63 | 2026-01-14 15:09 | NFLX | dir | short | ACIERTO | objetivo | entrada=89.24 objetivo=88.6451 stop=89.8349 | 0.45 (n=60) |
| 64 | 2026-01-13 19:41 | MU | dir | long | ACIERTO | objetivo | entrada=338.67 objetivo=500.0 stop=177.34 | 1.00 (n=60) |
| 65 | 2026-01-11 23:34 | AVGO | dir | short | FALLO | stop | entrada=336.8 objetivo=330.37 stop=343.23 | 0.38 (n=26) |
| 66 | 2026-01-11 23:34 | AVGO | dir | long | FALLO | stop | entrada=350.65 objetivo=353.39 stop=347.91 | 0.34 (n=59) |
| 67 | 2026-01-11 23:22 | AA | dir | long | ACIERTO | objetivo | entrada=64.155 objetivo=65.03 stop=55.0 | 1.00 (n=36) |
| 68 | 2026-01-11 18:20 | TSM | dir | long | ACIERTO | objetivo | entrada=322.1 objetivo=322.6147 stop=321.5853 | 0.52 (n=60) |
| 69 | 2026-01-11 18:06 | TSLA | dir | long | SIN_RESOLVER | tiempo | entrada=441.225 objetivo=474.63 stop=432.96 | 0.07 (n=30) |
| 70 | 2026-01-02 22:40 | NVDA | no_toca |  | ACIERTO | no alcanzar el nivel antes de la fecha | extremo=171.03 |  |
| 71 | 2026-01-02 22:40 | MU | no_toca |  | ACIERTO | no alcanzar el nivel antes de la fecha | extremo=309.55 |  |
| 72 | 2026-01-02 22:40 | QQQ | no_toca |  | ACIERTO | no alcanzar el nivel antes de la fecha | extremo=593.34 |  |
| 73 | 2025-12-31 15:31 | SPY | dir | long | FALLO | stop | entrada=685.39 objetivo=685.68 stop=685.1 | 0.43 (n=60) |
| 74 | 2025-12-30 16:16 | OXY | premium |  | PENDIENTE_PRIMA |  |  |  |
| 75 | 2025-12-28 21:59 | MSTR | dir | short | FALLO | stop | entrada=157.945 objetivo=130.0 stop=185.89 | 0.50 (n=10) |
| 76 | 2025-12-22 16:18 | CCL | dir | short | FALLO | stop | entrada=32.07 objetivo=31.9535 stop=32.1865 | 0.53 (n=60) |
| 77 | 2025-12-15 14:12 | VIX | dir | short | FALLO | stop | entrada=16.09 objetivo=14.06 stop=17.2 | 0.27 (n=60) |
| 78 | 2025-12-15 14:12 | NQ_F | no_evaluable |  | NO_EVALUABLE | mapa de niveles sin direccion (pivote + T arriba + T abajo) |  |  |
| 79 | 2025-12-10 21:28 | ORCL | dir | short | FALLO | stop | entrada=190.62 objetivo=180.0 stop=201.24 | 0.57 (n=58) |
| 80 | 2025-12-10 21:28 | MU | dir | long | FALLO | stop | entrada=261.53 objetivo=283.0 stop=240.06 | 0.74 (n=54) |
| 81 | 2025-12-03 01:39 | MU | dir | long | ACIERTO | objetivo | entrada=223.92 objetivo=235.2 stop=212.64 | 0.60 (n=5) |
| 82 | 2025-12-02 04:01 | TSLA | dia_color |  | ACIERTO | dia rojo = cierre < cierre previo | cierre=429.01 |  |
| 83 | 2025-11-20 13:54 | VIX | dir | short | FALLO | stop | entrada=20.11 objetivo=18.0 stop=22.22 | 0.57 (n=60) |
| 84 | 2025-11-19 13:42 | BTC | dir | short | SIN_RESOLVER | tiempo | entrada=85000.0 objetivo=52000.0 stop=118000.0 | 0.43 (n=7) |
| 85 | 2025-11-07 18:04 | BMNR | dir | short | FALLO | stop | entrada=38.37 objetivo=35.0 stop=41.74 | 0.62 (n=60) |
| 86 | 2025-11-06 20:55 | IREN | dir |  | NO_ACTIVADO | gatillo 76.0 above nunca tocado |  |  |
| 87 | 2025-11-06 20:55 | ABNB | rango |  | ACIERTO | cierre dentro del rango | cierre=120.88 max=125.76 min=117.1473 |  |
| 88 | 2025-11-06 20:55 | MP | dia_flat |  | FALLO | flat = |cambio| <= 2.0% | cambio_pct=12.94 |  |
| 89 | 2025-11-05 19:58 | QCOM | rango |  | ACIERTO | cierre dentro del rango | cierre=173.21 max=178.51 min=170.06 |  |
| 90 | 2025-11-05 19:58 | BROS | dir | long | FALLO | stop | entrada=56.305 objetivo=67.0 stop=50.0 | 0.37 (n=46) |
| 91 | 2025-11-02 19:33 | SPOT | bidir | short | SIN_RESOLVER | tiempo | entrada=620.0 objetivo=600.0 stop=690.0 | 1.00 (n=27) |
| 92 | 2025-11-02 19:33 | UBER | bidir |  | NO_ACTIVADO | ningun gatillo del mapa |  |  |
| 93 | 2025-11-02 19:33 | HIMS | bidir | short | ACIERTO | objetivo | entrada=46.0 objetivo=40.0 stop=53.0 | 0.30 (n=10) |
| 94 | 2025-11-02 19:33 | PLTR | bidir | short | ACIERTO | objetivo | entrada=180.0 objetivo=170.0 stop=211.0 | 1.00 (n=7) |
| 95 | 2025-10-28 23:31 | NBIS | dir | long | FALLO | stop | entrada=124.28 objetivo=160.0 stop=88.56 | 0.92 (n=36) |
| 96 | 2025-10-24 14:42 | AMD | premium |  | PENDIENTE_PRIMA |  |  |  |
| 97 | 2025-10-21 17:13 | BMNR | bidir | short | ACIERTO | objetivo | entrada=51.0 objetivo=47.0 stop=55.0 | 0.62 (n=56) |
| 98 | 2025-10-17 20:59 | GOLD | dir | long | FALLO | stop | entrada=4247.81 objetivo=5000.0 stop=3495.62 | 0.82 (n=51) |
| 99 | 2025-09-22 14:35 | AMKR | dir | long | ACIERTO | objetivo | entrada=29.31 objetivo=29.501 stop=29.1189 | 0.39 (n=59) |
| 100 | 2025-09-15 14:57 | VIX | dir | long | ACIERTO | objetivo | entrada=15.16 objetivo=15.4 stop=14.92 | 0.62 (n=60) |
| 101 | 2025-09-01 16:17 | VIX | dir | short | SIN_RESOLVER | tiempo | entrada=18.56 objetivo=12.75 stop=24.37 | 0.00 (n=19) |
| 102 | 2025-08-06 12:13 | MCD | dir | long | ACIERTO | objetivo | entrada=307 objetivo=318.0 stop=296.0 | 0.53 (n=30) |

## Lo que NO se pudo verificar
- SPX, VIX y ES_F no estan en el plan de Polygon (I:SPX / I:VIX -> HTTP 401 NOT_AUTHORIZED): se midieron con Yahoo Finance chart API, 5m si la llamada cae dentro de los ultimos 52 dias y 1h si es mas antigua. Resolucion 1h = barreras menos precisas (ids 33, 46, 48, 49, 59, 60, 77, 83, 100, 101).
- 3 llamadas no son evaluables por el propio texto: VIX 2026-07-17 ('PIVOT 17.15 LONG BELOW' con T2 19.17 - direccion y objetivo se contradicen), SPY 2026-04-17 (post retrospectivo tras el cierre), NQ_F 2025-12-15 (mapa de niveles sin direccion).
- 12 llamadas condicionales nunca se activaron (el gatillo no se toco): no son ni acierto ni fallo y se excluyen del win rate.
- 9 llamadas siguen abiertas al final de su horizonte (SIN_RESOLVER) y 3 vencen despues del 2026-08-07 (QQQ 888, SPY 850, SPY +6-8% anual): EN_CURSO.
- El TSLA 307.5P del 2026-08-05 no lleva expiracion en el post: no se puede identificar el contrato, se midio solo el subyacente.
- La 'IV crush' que anuncia en las previas de earnings NO se verifico: haria falta serie historica de IV por strike, que Polygon no da con ?as_of (devuelve el presente). Solo se verifico el RANGO de precio que acompana a esas previas.
- Las primas de contrato se miden con el maximo del alto de barras de 5m: no garantiza que hubiera tamano ejecutable en ese precio.
- No hay control aleatorio para las ideas de contrato (haria falta un null de compra de opciones equivalente).
- El win rate agrupa horizontes muy distintos (intradia, semana, FY26); dentro de cada horizonte n es demasiado pequeno para publicar tasas por separado.

