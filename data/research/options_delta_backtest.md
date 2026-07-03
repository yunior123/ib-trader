# Delta imbalance de OPCIONES (UW) — medicion

Generado 2026-08-08T15:13:35-0400 · `scripts/research/options_delta_backtest.py`

## Muestra

- 939784 minutos, 30 simbolos, **85 sesiones** (2026-03-24 -> 2026-07-24), 2407 bloques sym-dia.
- 85 sesiones >= 30 => el resultado ES medido, no indicativo.
- Lo que NO entra y por que: el archivo UW tiene 2607 ficheros en 94 dias (2026-03-24 -> 2026-08-07), pero `poly_bars` se queda en la barra del 2026-07-24. Se pierden **195 ficheros de 9 sesiones** (07-25 -> 08-07) por falta de barras 1m, no por falta de flujo. De los 2412 ficheros con dia utilizable entran 2407 bloques: solo 5 se caen. Refrescar `poly_bars` añadiria ~11% de muestra.

## Metodo

- **entrada**: open del minuto t+1 (señal en la barra cerrada t)
- **barrera**: triple: TP=k_tp*ATR14(1m), SL=k_sl*ATR, tiempo=H min; timeout=NULL fuera del denominador
- **z**: ventana movil intrasesion: mu,sd de los W minutos ANTERIORES del mismo sym-dia
- **nullA**: entradas al azar, mismo (sym, bucket 30min), direccion 50/50
- **nullB**: entradas al azar, mismo (sym, bucket 30min) y MISMA direccion (controla la deriva del periodo)
- **wilson**: 95% sobre n_eff = n/(1+(k-1)rho), rho=0.412, topada por clusters
- **fdr**: BH q=0.10 sobre las 192 celdas, p contra NULL B
- **horario**: 09:45-15:40 ET

## Resultado

- Celdas barridas: **192**. Pasan BH-FDR q=0.10 contra el null de misma direccion: **0**.
- Celdas PROVEN (FDR + Wilson-LB de expectancia > 0 + edge_lo > 0): **0**.

### Top 15 por Wilson-LB de la expectancia

| sig | zwin | theta | modo | ktp/ksl | H | n | n_eff | clu | wr | wr_lo | nullA | nullB | edge vs B | p | veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| otm | 60 | 3.0 | sigue | 1.50/1.00 | 60 | 20992 | 2406 | 2406 | 0.4061 | 0.3866 | 0.4051 | 0.4090 | -0.0030 | 0.54 | UNPROVEN |
| otm | 60 | 3.0 | sigue | 1.50/1.00 | 30 | 20949 | 2406 | 2406 | 0.4055 | 0.3861 | 0.4046 | 0.4088 | -0.0033 | 0.49 | UNPROVEN |
| dd | 60 | 2.5 | sigue | 1.00/1.00 | 15 | 27336 | 2407 | 2407 | 0.5023 | 0.4823 | 0.4989 | 0.4999 | +0.0024 | 0.57 | UNPROVEN |
| dd | 30 | 2.5 | sigue | 1.00/1.00 | 15 | 38758 | 2407 | 2407 | 0.5022 | 0.4822 | 0.5001 | 0.5010 | +0.0011 | 0.75 | UNPROVEN |
| dd | 60 | 2.5 | sigue | 1.00/1.00 | 30 | 27465 | 2407 | 2407 | 0.5022 | 0.4822 | 0.4987 | 0.4997 | +0.0025 | 0.56 | UNPROVEN |
| dd | 60 | 2.5 | sigue | 1.00/1.00 | 60 | 27471 | 2407 | 2407 | 0.5022 | 0.4822 | 0.4987 | 0.4997 | +0.0025 | 0.56 | UNPROVEN |
| dd | 30 | 2.5 | sigue | 1.00/1.00 | 60 | 38977 | 2407 | 2407 | 0.5018 | 0.4819 | 0.5005 | 0.5014 | +0.0005 | 0.89 | UNPROVEN |
| dd | 30 | 2.5 | sigue | 1.00/1.00 | 30 | 38966 | 2407 | 2407 | 0.5018 | 0.4819 | 0.5006 | 0.5013 | +0.0005 | 0.89 | UNPROVEN |
| dd | 30 | 2.5 | sigue | 1.50/1.00 | 60 | 38975 | 2407 | 2407 | 0.4048 | 0.3854 | 0.4033 | 0.4048 | -0.0000 | 1 | UNPROVEN |
| dd | 30 | 1.5 | sigue | 1.00/1.00 | 15 | 88634 | 2407 | 2407 | 0.5016 | 0.4816 | 0.4989 | 0.4975 | +0.0040 | 0.089 | UNPROVEN |
| dd | 30 | 2.0 | sigue | 1.00/1.00 | 15 | 56232 | 2407 | 2407 | 0.5015 | 0.4815 | 0.4981 | 0.5029 | -0.0015 | 0.62 | UNPROVEN |
| dd | 30 | 1.5 | sigue | 1.00/1.00 | 30 | 89155 | 2407 | 2407 | 0.5014 | 0.4814 | 0.4990 | 0.4974 | +0.0040 | 0.09 | UNPROVEN |
| dd | 30 | 1.5 | sigue | 1.00/1.00 | 60 | 89175 | 2407 | 2407 | 0.5014 | 0.4814 | 0.4990 | 0.4974 | +0.0040 | 0.093 | UNPROVEN |
| dd | 30 | 2.5 | sigue | 1.50/1.00 | 30 | 38893 | 2407 | 2407 | 0.4045 | 0.3851 | 0.4032 | 0.4045 | +0.0000 | 0.99 | UNPROVEN |
| otm | 60 | 1.5 | sigue | 1.00/1.00 | 60 | 60388 | 2406 | 2406 | 0.5013 | 0.4813 | 0.4954 | 0.4989 | +0.0024 | 0.41 | UNPROVEN |

### OTM vs TOTAL (mejor celda de cada familia por edge vs null B)

| familia | sig | zwin | theta | modo | H | n | wr | nullB | edge vs B | p |
|---|---|---|---|---|---|---|---|---|---|---|
| TOTAL dir_delta_flow | dd | 60 | 3.0 | sigue | 60 | 19759 | 0.4994 | 0.4930 | +0.0064 | 0.2 |
| OTM otm_dir_delta_flow | otm | 30 | 3.0 | fade | 60 | 30600 | 0.3982 | 0.3930 | +0.0052 | 0.19 |

### Filtro CAPITAN (CLAUDE.md regla 12)

**Celda de referencia** (sig=dd, zwin=30, theta=2.0, mode=sigue, k_tp=1.0, k_sl=1.0, H=30, la unica lectura con n independiente):

| subconjunto | n | n_eff | wr | Wilson 95% (n_eff) |
|---|---|---|---|---|
| señal NO vetada | 44482 | 2407 | 0.5004 | [0.4804, 0.5203] |
| señal VETADA por capitan | 12084 | 2135 | 0.5046 | [0.4834, 0.5257] |

- Diferencia -0.42 pp, p=0.41. p de dos proporciones sobre la n CRUDA; con n_eff (clusters sym-dia) el intervalo es el de arriba y se solapan

- Consistencia del signo: el filtro MEJORA en 83 celdas y EMPEORA en 109 de 192.

- agregado sobre celdas SOLAPADAS (mismas entradas con distintas barreras): la n de aqui NO es independiente, sirve para el SIGNO y el orden de magnitud, no para el intervalo

- Señales **NO vetadas** por el capitan: wr 0.4488 (n=6753852).
- Señales **VETADAS** (capitan opuesto vigente): wr 0.4495 (n=1912911).
- Diferencia: **-0.07 pp** (p naive 0.093).

| theta | wr sin veto | n | wr vetadas | n | delta pp |
|---|---|---|---|---|---|
| 1.5 | 0.4490 | 2806398 | 0.4492 | 763023 | -0.02 |
| 2.0 | 0.4489 | 1792565 | 0.4493 | 507585 | -0.04 |
| 2.5 | 0.4486 | 1240719 | 0.4500 | 364990 | -0.14 |
| 3.0 | 0.4484 | 914170 | 0.4501 | 277313 | -0.17 |

## Verificacion (scripts/research/options_delta_verify.py)

### 1. Reproduccion independiente

Reimplementacion desde cero (bucles fila a fila: ATR de Wilder, z de ventana movil, triple barrera) sin importar una sola funcion del repo:

- dd z30 th2.0 sigue ktp1.0 H30: n=56566 wr=0.5013 (identico)
- dd z60 th2.5 sigue ktp1.0 H15: n=27336 wr=0.5023 (identico)
- otm z30 th3.0 fade ktp1.0 H60: n=30602 wr=0.4954 (identico)
- dd z30 th1.5 sigue ktp1.0 H30: n=89155 wr=0.5014 (identico)

**n, wr, clusters y Wilson IDENTICOS a 4 decimales en las 4 celdas**

### 2. Ruido de Monte-Carlo del NULL (lo que invalida los 'edges')

El barrido sortea el null UNA vez por celda. Sorteandolo 40 veces:

| celda | wr | null publicado | null medio | null sd | edge publicado | edge medio | CI MC del edge | signo cambia con la semilla |
|---|---|---|---|---|---|---|---|---|
| otm z60 th2.5 fade ktp1.50 H60 | 0.3997 | 0.4086 | 0.4022 | 0.0031 | -0.0089 | -0.0025 | [-0.0077, +0.0023] | SI |
| otm z60 th2.5 fade ktp1.50 H30 | 0.3996 | 0.4083 | 0.4021 | 0.0031 | -0.0087 | -0.0025 | [-0.0078, +0.0024] | SI |
| dd z30 th2.5 fade ktp1.00 H15 | 0.4933 | 0.5020 | 0.4986 | 0.0023 | -0.0087 | -0.0053 | [-0.0086, -0.0003] | no |
| otm z60 th1.5 fade ktp1.50 H60 | 0.3983 | 0.4066 | 0.4008 | 0.0015 | -0.0083 | -0.0026 | [-0.0051, +0.0001] | SI |
| dd z30 th2.0 sigue ktp1.00 H30 | 0.5013 | 0.5029 | 0.4985 | 0.0024 | -0.0017 | +0.0027 | [-0.0026, +0.0075] | SI |
| dd z60 th3.0 sigue ktp1.00 H60 | 0.4994 | 0.4930 | 0.4981 | 0.0037 | +0.0064 | +0.0012 | [-0.0048, +0.0089] | SI |

- Desviacion tipica del null entre semillas: hasta **0.37 pp**. Los edges del barrido son de **+-0,4 pp**. => el edge de una celda cualquiera esta DENTRO del ruido del sorteo del null: no es medible con un solo sorteo.
- Es la razon de fondo de que 0 de 192 celdas pasen BH-FDR: no hay nada que detectar por encima del ruido.

### 3. OTM vs TOTAL, PAREADO

Comparar 'la mejor celda de cada familia' es pescar. Aqui se comparan los **96 pares con barrera, umbral y ventana IDENTICOS**:

| familia | celdas | edge medio vs null | celdas con edge>0 | mejor | peor |
|---|---|---|---|---|---|
| TOTAL dir_delta_flow | 96 | -0.0011 | 33/96 | +0.0064 | -0.0087 |
| OTM otm_dir_delta_flow | 96 | -0.0010 | 37/96 | +0.0052 | -0.0089 |

- dd - otm: media -0.0006, mediana -0.0005. Gana dd en 42 pares, otm en 54. Test de signos pareado **p=0.26**.
- **ninguna de las dos predice; la diferencia entre ellas tampoco es distinguible del azar (test de signos pareado p=0.26)**

### 4. Multiplicidad

- p minimo de todo el barrido: **0.0032**. Umbral BH mas estricto (q=0,10 / 192 celdas): **0.00052**. No lo alcanza ni la mejor.
- 12 celdas con p<0.05 sobre 192 (6.2%) contra el 5% que da el azar: exactamente ruido

### 5. Filtro CAPITAN con inferencia por CLUSTERES

Celda de referencia sig=dd, zwin=30, theta=2.0, mode=sigue, k_tp=1.0, k_sl=1.0, H=30. Veta el **21.4%** de las señales.

| test | diff (keep - vetada) | CI 95% (bootstrap de clusteres sym-dia) | p |
|---|---|---|---|
| veto CAPITAN (doctrina) | -0.0042 | [-0.0141, +0.0055] | 0.42 |
| veto ALEATORIO, misma tasa de recorte | +0.0004 | [-0.0096, +0.0104] | 0.96 |

- keep wr 0.5004 (n=44482) vs vetada wr 0.5046 (n=12084).
- **FOLKLORE: el CI del bootstrap por clusteres incluye 0**
- El veto del capitan no se distingue de recortar el mismo porcentaje de señales AL AZAR. En estos datos la regla 12 no aporta separacion medible sobre esta señal (lo que NO la invalida como doctrina de flujo: aqui solo se prueba contra el delta de opciones por minuto).

