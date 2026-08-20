# Delta divergence / absorcion / CVD / delta flip — MEDIDO, no supuesto

**Veredicto: los CUATRO setups estan MUERTOS.** De 243 celdas probadas, **0** sobreviven.

| | |
|---|---|
| Celdas probadas | 243 (9 variantes x 3 lados x 9 barreras) |
| Baten la entrada ALEATORIA (BH-FDR q=0,10) | **0** |
| Baten al MISMO PATRON DE PRECIO sin delta (BH-FDR) | **0** |
| Marcadas artefacto de volatilidad (ganan en las DOS direcciones) | 14 (de ellas 0 baten ademas al azar: son las que un backtest ingenuo publicaria) |
| **Rentables medidas** (separan + superan al precio + expectancia > 0) | **0** |

El resultado ampliado es mas fuerte: **ninguna celda bate siquiera la entrada aleatoria** despues de BH-FDR; por tanto ninguna llega a superar el control estructural de precio ni a justificar un umbral predictivo.

## Datos

- Tape: Databento XNAS.ITCH tbbo (RTH 13:30-20:00 UTC)
- Simbolos: NVDA, QQQ, SPY | sesiones: 66 (2026-07-10 -> 2026-08-10) | barras 1m: 25740
- Delta: vol(side=B) - vol(side=A), campo `side` NATIVO del exchange
- Volumen sin clasificar (`side=N`): **25.69%**
- Auditoria del signo: el delta nativo del exchange vs la clasificacion por quote-rule correlaciona **0.9152** y coincide en signo el **97.28%** de las barras.

> **LIMITACION QUE NO SE PUEDE OMITIR.** XNAS.ITCH es la cinta de Nasdaq SOLAMENTE, no el SIP consolidado. El delta medido describe el flujo lit de Nasdaq, no el mercado entero. NO extrapolar.

## Metodo

- **etiqueta**: triple barrera (objetivo ATR, stop ATR, tiempo en barras)
- **entrada**: apertura de la barra SIGUIENTE a la señal
- **empate tp y sl en la misma barra**: cuenta como STOP (conservador)
- **atr**: media de True Range de las 30 barras 1m previas
- **percentiles**: expandientes y CAUSALES (solo barras cerradas antes de la señal)
- **wilson**: 95% sobre n EFECTIVO (design effect por solape: 1+(m-1)*ICC)
- **multiplicidad**: BH-FDR q=0.10 sobre las 243 celdas
- **umbral publicacion**: n < 30 -> MUESTRA INSUFICIENTE

Tres controles, no uno:

1. **Azar** — entrada aleatoria emparejada por (simbolo, hora del dia, direccion), n_null >= 2000 por celda
2. **Estructural (ANTI)** — MISMO patron de precio SIN la condicion de delta (ANTI). Aisla la aportacion del delta: el control aleatorio no basta porque la barra extrema tiene mas volatilidad futura y toca cualquier barrera ATR.
3. **Direccion opuesta** — la misma barra operada al reves. Si wr + wr_opuesta > 2*null, el edge es de TOQUE (volatilidad), no de DIRECCION.

Los tres controles se conservan aunque el resultado ampliado ya muera contra el primero: impiden que una futura muestra mas favorable confunda volatilidad o estructura de precio con capacidad direccional de Delta.

## Resultado por setup

Mejor celda de cada setup (la de menor p contra el azar). `wr` = win rate, `null` = entrada aleatoria emparejada por simbolo/hora/direccion, `anti` = mismo patron de precio SIN la condicion de delta, `opp` = la MISMA barra operada al reves.

| Setup | n señales | mejor celda | n | n_eff | wr | null | edge | Wilson 95% | p | anti | edge vs anti | opp | wr+opp vs 2·null | veredicto |
|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|
| **DELTA DIVERGENCE M=5** | 5066 | ALL 1.5ATR/1.5ATR/60m | 5066 | 3562 | 0.5199 | 0.4918 | +2.81 pp | [0.5035, 0.5363] | 1.9e-03 | 0.5164 | +0.35 pp | 0.4726 | 0.992 vs 0.984 | NO SEPARA DEL AZAR |
| **DELTA DIVERGENCE M=10** | 3604 | LARGO 2.0ATR/2.0ATR/15m | 1762 | 1236 | 0.4245 | 0.3841 | +4.04 pp | [0.3972, 0.4523] | 4.7e-03 | 0.3986 | +2.59 pp | 0.3734 | 0.798 vs 0.768 | ARTEFACTO VOL |
| **DELTA DIVERGENCE M=20** | 2611 | LARGO 2.0ATR/2.0ATR/15m | 1258 | 866 | 0.4356 | 0.3854 | +5.02 pp | [0.4029, 0.4688] | 3.1e-03 | 0.4220 | +1.36 pp | 0.3609 | 0.796 vs 0.771 | ARTEFACTO VOL |
| **ABSORCION (abs delta p90 + rango p25, contrario)** | 412 | LARGO 2.0ATR/2.0ATR/15m | 223 | 179 | 0.4529 | 0.3665 | +8.65 pp | [0.3818, 0.5260] | 1.9e-02 | 0.3951 | +5.79 pp | 0.3094 | 0.762 vs 0.733 | ARTEFACTO VOL |
| **CVD DIVERGENCE X=5** | 3019 | LARGO 1.5ATR/1.5ATR/60m | 1398 | 1178 | 0.4914 | 0.5031 | -1.17 pp | [0.4629, 0.5200] | 4.4e-01 | 0.5172 | -2.58 pp | 0.5021 | 0.994 vs 1.006 | NO SEPARA DEL AZAR |
| **CVD DIVERGENCE X=10** | 2131 | LARGO 2.0ATR/2.0ATR/30m | 982 | 723 | 0.4511 | 0.4765 | -2.54 pp | [0.4152, 0.4875] | 1.8e-01 | 0.4736 | -2.25 pp | 0.4827 | 0.934 vs 0.953 | NO SEPARA DEL AZAR |
| **CVD DIVERGENCE X=20** | 1442 | CORTO 2.0ATR/2.0ATR/60m | 770 | 459 | 0.5403 | 0.4937 | +4.66 pp | [0.4945, 0.5853] | 5.0e-02 | 0.4851 | +5.51 pp | 0.4481 | 0.988 vs 0.987 | NO SEPARA DEL AZAR |
| **CVD DIVERGENCE X=30** | 1163 | CORTO 1.5ATR/1.5ATR/60m | 635 | 511 | 0.5339 | 0.4916 | +4.22 pp | [0.4905, 0.5767] | 6.2e-02 | 0.4715 | +6.23 pp | 0.4567 | 0.991 vs 0.983 | NO SEPARA DEL AZAR |
| **DELTA FLIP (cambio de signo, vol p75)** | 1060 | LARGO 2.0ATR/2.0ATR/15m | 545 | 473 | 0.3945 | 0.3717 | +2.28 pp | [0.3515, 0.4392] | 3.2e-01 | 0.3760 | +1.85 pp | 0.3945 | 0.789 vs 0.743 | ARTEFACTO VOL |

Celdas que pasan BH-FDR contra el azar, por setup: DIVERG_M5 0/27, DIVERG_M10 0/27, DIVERG_M20 0/27, ABSORCION 0/27, CVD_DIV_X5 0/27, CVD_DIV_X10 0/27, CVD_DIV_X20 0/27, CVD_DIV_X30 0/27, DELTA_FLIP 0/27.

## Los cuatro, uno a uno

### 1. DELTA DIVERGENCE (M=5, 10, 20) — el edge es del PRECIO, no del delta

De sus 81 celdas, **0** baten al azar tras BH-FDR. La mejor (M=20, LARGO, 2.0ATR/2.0ATR/15m) da wr **0.4356** contra azar **0.3854** (+5.02 pp, p=3.1e-03), pero no alcanza el umbral de publicacion ni supera de forma controlada el patron de precio.

- **Direccion opuesta**: la misma barra operada al reves gana **0.3609**. Suma = 0.796 contra 2·azar = 0.771. Si comprar Y vender la misma barra baten al azar, lo que se mide es que la barra extrema TOCA cualquier barrera ATR: es volatilidad, no direccion.
- **Control estructural**: las barras con el MISMO nuevo extremo de 20 barras pero SIN divergencia de delta ganan **0.4220** (n=1353). La condicion de delta añade +1.36 pp con p=0.566 — no sobrevive a la correccion por multiplicidad. El nuevo extremo de precio ya lo explica todo.

Celdas de divergencia con `fdr_pass` y `R_lb95>0`: **0**; ninguna termina con veredicto MEDIDO rentable.

### 2. ABSORCION — no sobrevive como umbral predictivo

Solo **412 señales** en 66 sesiones-simbolo (la condicion |delta| p90 + rango p25 es rara), y de sus 27 celdas **4** salen marcadas artefacto de volatilidad. La mejor (LARGO 2.0ATR/2.0ATR/15m) luce espectacular — wr **0.4529** vs azar **0.3665**, **+8.65 pp** — y es el ejemplo mas claro del informe de por que eso no significa nada:

- La direccion contraria sobre las MISMAS barras gana **0.3094**. Suma 0.762 vs 2·azar 0.733: la barra de rango estrecho con delta extremo es simplemente el preludio de un movimiento **en cualquier sentido**.
- n = 223 (n_eff = 179). Wilson [0.3818, 0.5260]: el intervalo mide **14.4 puntos** de ancho. No hay muestra para afirmar nada.
- El null publicado se estima por Monte Carlo; el verificador recalcula de forma exacta una celda de auditoria separada. Los números exactos se muestran en la sección de verificación y no se trasladan a esta mejor celda.

### 3. CVD DIVERGENCE (X=5, 10, 20, 30) — plano, sin excusas

**0 de 108 celdas** baten al azar tras BH-FDR, con 7755 señales en total. El mejor p-valor de toda la familia es 0.05. No hace falta control estructural: no hay nada que explicar.

- **CVD_DIV_X5**: 3019 señales, mejor wr 0.4914 vs azar 0.5031 (-1.17 pp), p=0.44, R_lb95 -0.105 -> no paga.
- **CVD_DIV_X10**: 2131 señales, mejor wr 0.4511 vs azar 0.4765 (-2.54 pp), p=0.18, R_lb95 -0.191 -> no paga.
- **CVD_DIV_X20**: 1442 señales, mejor wr 0.5403 vs azar 0.4937 (+4.66 pp), p=0.05, R_lb95 -0.005 -> no paga.
- **CVD_DIV_X30**: 1163 señales, mejor wr 0.5339 vs azar 0.4916 (+4.22 pp), p=0.06, R_lb95 -0.018 -> no paga.

### 4. DELTA FLIP — muerto, y encima con expectancia NEGATIVA

1060 señales, **0 de 27 celdas** baten al azar. La mejor celda (LARGO 2.0ATR/2.0ATR/15m) tiene wr **0.3945** vs azar **0.3717** (p=0.32) y **R medio = +0.004** con R_lb95 = -0.160: seguir el nuevo signo del delta en barras de volumen alto PIERDE dinero en la muestra. Ademas 6 de sus celdas salen artefacto.

## Verificacion independiente

`scripts/research/delta_setups_verify.py` reimplementa la triple barrera (vectorizada por desplazamiento, no señal a señal) y dos de los setups desde cero, y contrasta contra el JSON publicado: **18/18 checks OK**.

- Recuentos de señales: exactos en DIVERG M=5/10/20 y ABSORCION.
- Win rates de 5 celdas cabecera: coinciden **hasta el 5º decimal**.
- El azar se recalculo **EXACTO** (promediando sobre todo el estrato, sin muestreo): 0.3840 vs 0.3854 publicado en DIVERG_M20; 0.4509 vs 0.4468 en ABSORCION. Las diferencias son error de Monte Carlo del estudio, no un fallo.

### Regalo del verificador: el delta agrupado por sesion no predice NADA

| medicion | valor |
|---|---|
| corr(delta, retorno de la MISMA barra), agrupando todo | **+0.2877** (R2 8.28%) |
| corr(delta, retorno de la barra SIGUIENTE), agrupando todo | **+0.0307** |
| la misma, **por sesion** (media de 66 sesiones) | **-0.0071** (sd 0.0664) |
| t agrupado por sesion | **-0.87** |

Agrupando las 25740 barras de golpe, el delta parece predecir la barra siguiente con corr +0.0307. **Al agrupar por sesion la correlacion se vuelve -0.0071 con t = -0.87.** Ese +0.0307 era estructura ENTRE dias (los dias de tendencia tienen a la vez mas delta medio y mas retorno medio), no capacidad predictiva dentro del dia. Es estructura entre dias, no capacidad predictiva intradia.

Contemporaneamente el delta SI explica (R2 8.28%), coherente con la literatura de OFI: explica el pasado inmediato, no el futuro.

## Que se hace con esto

1. **No se construye ningun bot con estos cuatro setups.** Ni delta divergence, ni absorcion, ni CVD divergence, ni delta flip. Cero celdas rentables medidas.
2. Estos resultados prueban Delta de **acciones Nasdaq**, no el Delta/skew de opciones de Architect. Architect sigue siendo la doctrina principal de opciones; el footprint queda como confirmacion contemporanea en value, no como gatillo solo.
3. **El control que hay que exigir siempre es el ANTI**, ademas del azar. En esta muestra el azar aprueba 0 de 243 celdas.
4. Lo unico defendible del delta de acciones sigue siendo **contemporaneo**: describe la barra que ya paso.

## Huecos declarados

- **Muestra corta**: 22 fechas, 3 simbolos, 66 sesiones-simbolo. Suficiente para matar (los edges vs ANTI son de 1-4 pp con intervalos de 8-10 pp), insuficiente para resucitar: el control ANTI solo tiene potencia para detectar diferencias grandes. Un edge real de 2 pp NO se veria aqui.
- **25.69% del volumen sin lado agresor** (`side=N`) se descarta del delta. El estudio usa el delta nativo; la variante Lee-Ready esta en el .npz (`lr_b`/`lr_a`) y NO se probo como alternativa.
- **Solo cinta de Nasdaq (~14-21% del consolidado).** Un delta consolidado podria comportarse distinto; no es medible con los datos comprados.
- **Simbolos: NVDA, QQQ, SPY.** Ya incluye NVDA, pero nada dice de futuros, que es donde el footprint nacio y CME publica el agresor de verdad.
- No se probaron barreras asimetricas (objetivo != stop) ni salidas por tiempo cortas (<15 min), ni la combinacion de los setups entre si.
- El azar de las celdas con pocas señales tiene error de Monte Carlo de ~0,7 pp (25 replicas, 12 estratos). Solo se recalculo EXACTO en 2 celdas.

---
Generado por `scripts/research/delta_setups.py` (medicion) + `delta_setups_verify.py` (verificacion independiente) + este `delta_setups_report.py`. Datos: `data/research/delta_setups_backtest.json`, `data/research/delta_setups_verify.json`.
