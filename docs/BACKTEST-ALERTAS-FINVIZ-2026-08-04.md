# Backtest honesto — alertas FINVIZ (screeners) · 2026-08-03

Generado 2026-08-04 02:58 por `scripts/backtest_finviz.py` · SEÑAL-SOLAMENTE, ninguna conclusion ordena nada.
Verdad de terreno: **Polygon aggs 1m + grouped daily** (sin IBKR; orden vigente prohibe TWS/Gateway). Barrera triple k_tp=1.00·ATR14(1m), k_sl=1.00·ATR14(1m), horizonte = hasta el cierre 16:00 ET del mismo dia. Timeout = NULL, no victoria.

## VEREDICTO EN 6 LINEAS

1. El 2026-08-03 los 3 screeners emitieron **184 alertas de ticker** en **116 banners**, cada uno con voz + push al telefono.
2. De las 141 etiquetables, ganaron **61 (43.3%)**. Entradas ALEATORIAS emparejadas por minuto y duracion ganaron **51.7%**. El screener va **-8.4 pp** contra el azar.
3. El signo negativo se mantiene en 3 de los 4 umbrales de barrera barridos (seccion 3b) -> no es un artefacto de un umbral.
4. Ningun corte sobrevive BH-FDR q=0.10. Con una sola sesion de muestra, **casi todo es DATA-INSUFICIENTE** y no se publica probabilidad.
5. Los pesos del `score N/6` y `N/7` estan **INVENTADOS**, y uno de los componentes declarados (SMA20) **no existe** en el CSV que llega (seccion 1).
6. Lo unico que apunta a algo es el **RVOL alto** — y con n de dos digitos bajos: es una pista para medir, no para operar.

## 0. Advertencias (leelas antes de creerte un numero)

- **SIN comisiones, SIN slippage, SIN spread.** Entrada al close de la vela 1m del minuto de la alerta, con el tape de Polygon (no con el precio que canto Finviz).
- **Horizonte unico: intradia**. Ver seccion 5 — +1d/+2d/+5d NO se pueden medir hoy.
- El **timeout no es victoria**: las alertas cuya barrera no se toca antes del cierre salen del denominador (`label = NULL`).
- **Ningun ticker se rellena**: el que no tiene barras en Polygon se EXCLUYE y se cuenta en la tabla de exclusiones.
- Wilson se evalua sobre **n_eff**, no sobre n cruda. Un solo dia de mercado es casi una sola observacion.

## 1. Inventario de los 3 screeners

Motor unico `scripts/finviz_screener_watch.cpp`, 3 instancias (`--screen buffett|squeeze|momentum`). Filtros leidos del propio .cpp:

| screener | linea | filtro enviado a Finviz | signal `s=` | sondeo RTH |
|---|---|---|---|---|
| BUFFETT | `finviz_screener_watch.cpp:135` | `fa_debteq_u0.5,fa_eps5years_pos,fa_netmargin_pos,fa_pe_u20,fa_roe_o15,sh_avgvol_o500,sh_price_o5` | — | 600 s |
| SHORT SQUEEZE | `finviz_screener_watch.cpp:139` | `sh_avgvol_o500,sh_float_u50,sh_price_o5,sh_relvol_o1.5,sh_short_o15` | — | 120 s |
| MOMENTUM BREAKOUT | `finviz_screener_watch.cpp:142` | `sh_avgvol_o500,sh_price_o5,sh_relvol_o1.5,ta_sma20_pa,ta_sma50_pa,ta_sma200_pa` | `ta_newhigh` | 60 s |

URL: `finviz_screener_watch.cpp:342-344` — `v=152`, `o=-relativevolume`, `c=1,2,6,30,31,53,54,55,59,60,61,63,64,65,66,67`.

### Como se calcula el score (`score()`, lineas 176-197)

| linea | componente | regla | peso |
|---|---|---|---|
| 177 | cambio del dia | `>+0.3%` -> +1, `<-0.3%` -> -1, si no 0 | ±1 |
| 178 | cambio desde apertura | `>+0.2%` -> +1, `<-0.2%` -> -1 | ±1 |
| 179-183 | RSI(14) | `[50,75]` -> +1; `<42` o `>82` -> -1 | ±1 |
| 184 | SMA20 | signo de la distancia | ±1 |
| 185 | SMA50 | signo de la distancia | ±1 |
| 186 | SMA200 | signo de la distancia | ±1 |
| 187 | RVOL | `>=1.5` -> +1, si no 0 | +1/0 |
| 190-191 | squeeze: short+impulso | `short_float>=20 && change>0` -> +1 | +1/0 |
| 192-194 | momentum: breakout sostiene | `change>0 && from_open>0` -> +1, si no -1 | ±1 |
| 195-196 | umbral | `max(2, ceil(possible*0.45))`; BUY si `score>=u`, SELL si `<=-u` | — |

### ¿Los pesos estan MEDIDOS o INVENTADOS?

**INVENTADOS.** Los cinco hechos, cada uno verificable:

1. **No existe fichero de calibracion del score.** El repo tiene `data/calibration.json`, `data/calibration_barrier.json`, `data/compass_calib.json` y `data/timeofday_calib*`; **ninguno** contiene los pesos de este motor, y el .cpp no lee ningun fichero de calibracion. Todos los umbrales (`0.3`, `0.2`, `50/75`, `42/82`, `1.5`, `20`, `0.45`) son literales en el codigo.
2. **Un componente declarado NO EXISTE.** El .cpp pide `c=...53,54,55...` y comenta (lineas 340-341) que son SMA20/50/200. El header REAL del export es `"50-Day Simple Moving Average","200-Day Simple Moving Average","50-Day High"` — **no hay columna de SMA20**. Como el parser busca por NOMBRE, `r.sma20` es siempre NaN: el voto SMA20 nunca suma y nunca incrementa `possible`. Evidencia cruzada: `sma20_pct` esta vacio en el 100% de las filas de los 3 CSV, y BUFFETT reporta `possible = 6` (no 7).
3. **El filtro se auto-vota.** MOMENTUM filtra por `ta_sma50_pa`, `ta_sma200_pa` y `sh_relvol_o1.5`; esos mismos tres son votos del score. Medido: RVOL>=1.5 en **56/56** de sus alertas, y en el snapshot SMA50>0 y SMA200>0 en el 100% de las filas. Son **3 puntos de 7 REGALADOS** antes de mirar nada. El umbral BUY es 4 -> **basta 1 punto mas** para cantar BUY.
4. **Y un voto muerto en el otro sentido.** BUFFETT no filtra por RVOL: el voto vale 0 en **96/100** de sus alertas. Su score util es de 5 componentes, no de 6.
5. **Terminos colineales con pesos a mano.** SMA50 y SMA200 comparten signo en el 78.5% de las filas BUFFETT, el **100%** de MOMENTUM y el 75% de SQUEEZE: es UNA tesis de tendencia contada dos o tres veces. La `anti-overfit-killlist` prohibe exactamente esto ("compuesto de z-scores con pesos elegidos a mano sobre terminos correlacionados", muertos #6, #8, #13).

Ademas `possible` **no es el maximo alcanzable**: `add(r, 0, ...)` (linea 172-174) incrementa `possible` aunque el voto sea 0. Un "score 3/6" NO significa "3 de 6 puntos posibles"; es una suma con signo sobre 6 componentes evaluados donde los ceros inflan el denominador. **El numero que se canta por voz no se puede leer como una fraccion.**

> Veredicto `anti-overfit-killlist`: **prior inventado disfrazado de medicion**, con dos de los seis disfraces del catalogo presentes a la vez — *input muerto* (SMA20) y *compuesto de terminos colineales con pesos a mano*.

## 2. Volumen de alertas (la medida del ruido)

| hora ET | buffett | squeeze | momentum | total |
|---|---|---|---|---|
| 08:00 | 7 | 1 | 0 | 8 |
| 09:00 | 33 | 11 | 15 | 59 |
| 10:00 | 12 | 3 | 12 | 27 |
| 11:00 | 12 | 4 | 7 | 23 |
| 12:00 | 8 | 3 | 10 | 21 |
| 13:00 | 4 | 3 | 6 | 13 |
| 14:00 | 9 | 0 | 0 | 9 |
| 15:00 | 13 | 0 | 2 | 15 |
| 16:00 | 2 | 3 | 4 | 9 |
| **TOTAL** | 100 | 28 | 56 | **184** |

Cada banner = 1 notificacion de voz/urgente + 1 push al telefono (`finviz_screener_watch.cpp:316-317`). Ritmo de interrupcion medido:

| screener | banners | ciclos posibles | % de sondeos que interrumpen | mediana entre banners |
|---|---|---|---|---|
| buffett | 40 | ~77 | 52% | 10 min |
| squeeze | 25 | ~309 | 8% | 8 min |
| momentum | 51 | ~580 | 9% | 3 min |
| **TOTAL** | **116** | | | |

(Contraste independiente: `grep -c "FINVIZ (BUFFETT|MOMENTUM|SHORT)" data/trading-signals/2026-08-03.txt` = 116 lineas, mas 1 linea `FINVIZ ROTO` de las 04:02.)

**Churn dentro del dia**: 95 tickers distintos generaron 184 alertas; **38** tickers alertaron mas de una vez. Top repetidores: `NEOG` x12, `DRH` x8, `PCRX` x6, `SFD` x5, `PGR` x4, `STNG` x4.

La causa esta en el codigo: `finviz_screener_watch.cpp:378-381` NO alerta `BUY -> WATCH`, pero SI alerta `WATCH -> BUY`. Un ticker que oscila alrededor del umbral produce una interrupcion NUEVA en cada cruce hacia arriba. El churn no es un efecto del mercado: es la regla de notificacion.

## 3. Muestra efectiva (rho MEDIDO, no prior)

- eventos direccionales etiquetables: **141** de 184
- excluidos: **43** (razones abajo)
- clusters (ticker, fecha): **74** — todo cae en **1 sola sesion**
- rho medio por pares de retornos 1m del 2026-08-03, medido sobre los propios tickers alertados: **0.037**
- **n_eff = 38.1**

| razon de exclusion | n |
|---|---|
| sin ATR14 1m previo (menos de 14 barras) | 27 |
| WATCH (sin direccion) | 7 |
| emitida despues del cierre (16:00 ET) | 7 |
| sin camino restante hasta el cierre | 1 |
| alerta fuera del rango de barras del dia | 1 |

## 3b. Follow-through por corte

Null emparejado (mismo minuto, misma duracion, misma direccion, ticker al azar del mismo universo liquido): **51.7%** sobre n=414 entradas sinteticas.

| corte | valor | alertas | decididas | hit | Wilson(n_eff) | n_eff | p | BH-FDR | veredicto |
|---|---|---|---|---|---|---|---|---|---|
| TODO | todas las alertas | 141 | 141 | 43.3% | [27.9%, 57.8%] | 38.1 | 0.982 | no | UNPROVEN |
| hora | 09:30-10:30 oro | 45 | 45 | 48.9% | [27.3%, 68.3%] | 18.7 | 0.700 | no | DATA-INSUFICIENTE |
| hora | 10:30-11:30 | 26 | 26 | 42.3% | [19.8%, 64.3%] | 15.3 | 0.876 | no | DATA-INSUFICIENTE |
| hora | 11:30-14:00 picadora | 38 | 38 | 36.8% | [17.3%, 58.7%] | 17.0 | 0.977 | no | DATA-INSUFICIENTE |
| hora | 14:00-16:00 | 22 | 22 | 40.9% | [21.4%, 67.4%] | 14.1 | 0.890 | no | DATA-INSUFICIENTE |
| hora | premarket <09:30 | 10 | 10 | 50.0% | [25.0%, 84.2%] | 7.5 | 0.664 | no | DATA-INSUFICIENTE |
| rvol | RVOL 1.0-1.5 | 5 | 5 | 60.0% | [9.5%, 90.5%] | 2.0 | 0.532 | no | DATA-INSUFICIENTE |
| rvol | RVOL 1.5-2.5 | 59 | 59 | 39.0% | [23.6%, 57.6%] | 28.4 | 0.982 | no | DATA-INSUFICIENTE |
| rvol | RVOL <1.0 | 66 | 66 | 37.9% | [23.6%, 57.6%] | 27.8 | 0.991 | no | DATA-INSUFICIENTE |
| rvol | RVOL >=2.5 | 11 | 11 | 90.9% | [43.6%, 97.0%] | 6.0 | 0.008 | no | DATA-INSUFICIENTE |
| score | abs(score) < possible-1 | 111 | 111 | 39.6% | [25.6%, 55.3%] | 37.9 | 0.996 | no | UNPROVEN |
| score | abs(score) = maximo | 14 | 14 | 64.3% | [35.4%, 87.9%] | 9.4 | 0.251 | no | DATA-INSUFICIENTE |
| score | abs(score) >= possible-1 | 16 | 16 | 50.0% | [28.0%, 78.7%] | 11.0 | 0.650 | no | DATA-INSUFICIENTE |
| screener | buffett | 75 | 75 | 41.3% | [24.6%, 57.7%] | 29.8 | 0.972 | no | DATA-INSUFICIENTE |
| screener | momentum | 49 | 49 | 46.9% | [30.0%, 66.5%] | 25.0 | 0.791 | no | DATA-INSUFICIENTE |
| screener | squeeze | 17 | 17 | 41.2% | [13.7%, 69.4%] | 8.0 | 0.867 | no | DATA-INSUFICIENTE |
| tipo | new_match | 29 | 29 | 48.3% | [26.8%, 73.2%] | 14.5 | 0.710 | no | DATA-INSUFICIENTE |
| tipo | weather_change | 112 | 112 | 42.0% | [27.9%, 57.8%] | 38.3 | 0.984 | no | UNPROVEN |
| weather | BUY | 116 | 116 | 44.0% | [28.7%, 59.1%] | 36.8 | 0.961 | no | UNPROVEN |
| weather | SELL | 25 | 25 | 40.0% | [19.8%, 64.3%] | 15.0 | 0.915 | no | DATA-INSUFICIENTE |

Total decidido: 61/141 = 43.3% vs null 51.7%.

### Descriptivo: retorno alerta -> cierre (no es la etiqueta, es contexto)

| screener | n | mediana % | media % | > 0 |
|---|---|---|---|---|
| buffett | 75 | -0.44 | -0.49 | 26/75 |
| squeeze | 17 | +1.82 | +9.16 | 10/17 |
| momentum | 49 | -1.58 | -1.60 | 16/49 |
| **null aleatorio** | 422 | +0.17 | +0.64 | 244/422 |

### Curva de sensibilidad (si el efecto vive en UN solo umbral, no es real)

| k_tp = k_sl (·ATR14 1m) | screener | decididas | hit | null | delta |
|---|---|---|---|---|---|
| 0.50 | buffett | 75 | 52.0% | 47.2% | +4.8 pp |
| 0.50 | squeeze | 17 | 47.1% | 47.2% | -0.1 pp |
| 0.50 | momentum | 49 | 40.8% | 47.2% | -6.3 pp |
| 0.50 | TODOS | 141 | 47.5% | 47.2% | +0.4 pp |
| 0.75 | buffett | 75 | 44.0% | 50.8% | -6.8 pp |
| 0.75 | squeeze | 17 | 47.1% | 50.8% | -3.8 pp |
| 0.75 | momentum | 49 | 49.0% | 50.8% | -1.9 pp |
| 0.75 | TODOS | 141 | 46.1% | 50.8% | -4.7 pp |
| 1.00 | buffett | 75 | 41.3% | 51.7% | -10.4 pp |
| 1.00 | squeeze | 17 | 41.2% | 51.7% | -10.5 pp |
| 1.00 | momentum | 49 | 46.9% | 51.7% | -4.8 pp |
| 1.00 | TODOS | 141 | 43.3% | 51.7% | -8.4 pp |
| 1.50 | buffett | 75 | 42.7% | 51.3% | -8.7 pp |
| 1.50 | squeeze | 17 | 35.3% | 51.3% | -16.1 pp |
| 1.50 | momentum | 48 | 41.7% | 51.3% | -9.7 pp |
| 1.50 | TODOS | 140 | 41.4% | 51.3% | -9.9 pp |

## 4. Propuesta de filtros (simulada sobre el propio dia)

Ganadoras de referencia (barrera=1 con k=1.00/1.00 ATR): **61** sobre 184 alertas.

Tasa base: **33%** de las alertas del dia acaban en ganadora. Un filtro util tiene que SUBIR esa concentracion; si la deja igual, esta matando señal y ruido en la misma proporcion.

| filtro | deja | mata | % ruido matado | ganadoras conservadas | concentracion | vs base |
|---|---|---|---|---|---|---|
| solo NUEVOS (mata weather_change) | 44 | 140 | 76% | 14/61 | 32% | -1.3 pp |
| solo BUY/SELL (mata WATCH) | 177 | 7 | 4% | 61/61 | 34% | +1.3 pp |
| abs(score) == possible | 19 | 165 | 90% | 9/61 | 47% | +14.2 pp |
| abs(score) >= possible-1 | 40 | 144 | 78% | 17/61 | 42% | +9.3 pp |
| RVOL >= 1.5 | 88 | 96 | 52% | 33/61 | 38% | +4.3 pp |
| RVOL >= 2.0 | 19 | 165 | 90% | 11/61 | 58% | +24.7 pp |
| ventana 09:45-15:30 | 111 | 73 | 40% | 44/61 | 40% | +6.5 pp |
| mata post-cierre (>=16:00) | 175 | 9 | 5% | 61/61 | 35% | +1.7 pp |
| mata premarket (<09:30) | 166 | 18 | 10% | 56/61 | 34% | +0.6 pp |
| 1 alerta por ticker y dia | 95 | 89 | 48% | 32/61 | 34% | +0.5 pp |

Combos, con dedupe de 1 alerta por ticker y dia en todos:

| combo | alertas | ruido matado | ganadoras | concentracion | vs base | alertas matadas por ganadora perdida |
|---|---|---|---|---|---|---|
| A · minimo higienico | 87 | 97 (53%) | 32/61 | 37% | +3.6 pp | 3.3 |
| B · A + RVOL>=1.5 | 38 | 146 (79%) | 17/61 | 45% | +11.6 pp | 3.3 |
| C · B + ventana 09:45-15:30 | 26 | 158 (86%) | 11/61 | 42% | +9.2 pp | 3.2 |
| D · C + score>=possible-1 | 16 | 168 (91%) | 8/61 | 50% | +16.8 pp | 3.2 |
| E · solo NUEVOS + RVOL>=2.0 | 6 | 178 (97%) | 3/61 | 50% | +16.8 pp | 3.1 |

**Lo que dice esta tabla, y lo que NO.** El filtro que mas concentra es `RVOL >= 2.0`: 58% de ganadoras frente a una base de 33% (**+24.7 pp**). Pero deja **n = 19** alertas, n_eff = 11.4 -> **DATA-INSUFICIENTE**: es una PISTA, no un resultado. Coincide con el corte de menor p de la seccion 3b (`rvol = RVOL >=2.5`, 90.9%, p=0.008, que NO sobrevive a BH-FDR). Si algo hay aqui, esta en el VOLUMEN RELATIVO — no en el score.

**Recomendacion (exquisita): D · C + score>=possible-1** — deja **16** interrupciones de 184 (**-91%**), concentracion 50% (+16.8 pp sobre la base), conservando 8/61 ganadoras. Reglas: solo BUY/SELL (mata WATCH), mata post-cierre (>=16:00), RVOL >= 1.5, ventana 09:45-15:30, abs(score) >= possible-1, mas 1 alerta por ticker y dia.

Si 16 alertas/dia parece demasiado poco, el escalon anterior es **B · A + RVOL>=1.5**: 38 alertas, concentracion 45%, 17/61 ganadoras.

Ademas, y con independencia del filtro elegido, dos cambios que el propio codigo justifica: (a) **quitar la voz** a los 3 screeners mientras el veredicto sea UNPROVEN (`fleet_notify_urgent` -> banner; regla de `measured-probability`: UNPROVEN no habla), y (b) **no re-alertar el mismo ticker el mismo dia** aunque vuelva a cruzar el umbral (`finviz_screener_watch.cpp:378-381`).

Las 16 alertas que habrian sobrevivido el 2026-08-03:

| ticker | screener | hora | weather | score | RVOL |
|---|---|---|---|---|---|
| CDNA | momentum | 09:47 | BUY | 6/7 | 3.99 |
| GSAT | momentum | 09:53 | BUY | 7/7 | 1.97 |
| CNK | momentum | 09:54 | BUY | 6/7 | 1.54 |
| ESTA | momentum | 10:00 | BUY | 7/7 | 1.55 |
| FOSL | momentum | 10:01 | BUY | 6/7 | 3.12 |
| IMAX | momentum | 10:04 | BUY | 6/7 | 1.6 |
| TFX | momentum | 10:05 | BUY | 7/7 | 1.5 |
| JACK | squeeze | 10:06 | BUY | 7/7 | 1.53 |
| CFFN | momentum | 10:11 | BUY | 7/7 | 1.5 |
| BVS | momentum | 10:13 | BUY | 7/7 | 1.55 |
| DRH | momentum | 10:16 | BUY | 6/7 | 1.61 |
| EAT | momentum | 10:24 | BUY | 6/7 | 1.56 |
| ELVN | momentum | 10:55 | BUY | 7/7 | 1.56 |
| VVX | momentum | 11:14 | BUY | 7/7 | 1.56 |
| NEOG | momentum | 12:17 | BUY | 6/7 | 1.57 |
| BBVA | momentum | 12:20 | BUY | 6/7 | 1.6 |

## 5. Lo que NO se puede afirmar

- **Un solo dia.** El unico dia con eventos de screener archivados es 2026-08-03 (`data/finviz_screener_events.jsonl`). El agregado llega a n_eff = 38.1 y por eso se le pone veredicto (UNPROVEN); **casi todos los cortes por screener/score/hora caen por debajo de 30 y son DATA-INSUFICIENTE**. Un dia no distingue "el screener no sirve" de "el 3 de agosto fue malo".
- **rho medido = 0.037**, mucho mas bajo que el 0.412 de la flota de 30 semis: el universo del screener es sectorialmente diverso (mineras de oro, aseguradoras, biotech, restaurantes), asi que la muestra NO se hunde por correlacion — se hunde por ser un solo dia.
- **Horizontes +1d/+2d/+5d NO medidos**: Polygon (plan sin realtime) no sirve el dia en curso hasta despues del cierre; el dia siguiente al ultimo alertado no existe todavia. Solo hay horizonte intradia alerta->cierre.
- **Churn entre dias NO medible**: `data/finviz_*_state.txt` guarda un solo dia (`date=` + `alerted|`) y se reinicia; no hay historico de membresia.
- **Sin look-ahead, pero sin archivo**: los eventos se etiquetan con el precio y el RVOL que el motor grabo EN EL INSTANTE de la alerta; nada se re-lee del snapshot de hoy. A cambio, el snapshot CSV (`data/finviz_*_signals.csv`) se sobrescribe cada ciclo: no sirve para reconstruir el pasado.
- La probabilidad de cada corte no se publica; se publica el intervalo y el veredicto DATA-INSUFICIENTE donde toca.
- **El null es una sola sesion tambien.** 45 tickers del universo liquido, 3 entradas sinteticas por alerta. Basta para decir "no bate al azar"; no basta para poner un numero al edge.

### Que falta, en orden

1. **Acumular sesiones.** El fichero de eventos ya existe y es append-only: con 20-30 sesiones los cortes por screener y por RVOL pasan el umbral de n. Nada mas hay que construir para eso — solo esperar y no borrar el jsonl.
2. **Archivar la membresia diaria** (los `alerted|` del state) para poder medir el churn entre dias, que hoy es literalmente inobservable.
3. **Horizontes multidia**: con un `grouped daily` por sesion (1 peticion Polygon por dia) se etiquetan +1d/+2d/+5d de todo el universo de golpe. Barato; solo necesita que el dia haya cerrado.
4. **Arreglar el componente SMA20** o quitarlo del score y del texto que se canta: hoy el numero que se dice por voz miente sobre lo que mide.
5. **Probar la hipotesis RVOL** aislada (sin score), que es la unica que dio señal de vida, con el barrido de umbrales {1.5, 2.0, 2.5, 3.0} y n suficiente.

