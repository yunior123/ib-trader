---
name: yoel-sardinas
description: El metodo del libro de Yoel Sardinas (caps X-XII, pp.116-177) destilado a herramienta operativa para la flota ib-trader — solo 4 armas (Bollinger 20/2sigma, SMAs simples 20/40/100/200, VOLUMEN con MA50, velas+trendlines), proceso top-down 15m->1H->1D, tendencia por direccion de la SMA20, LAS 8 ESTRATEGIAS en tabla accionable (cambio de tendencia, rebote de punto medio, fuera-de-Bollinger en apertura, efecto iman a la SMA20), el filtro DURO volumen>MA50 en la vela gatillo, sizing 8-12% y take-profit +100% auto. Usar cuando Yunior pida "metodo Yoel", "el libro", "estrategia del punto medio", "efecto iman", "fuera de banda en apertura", "cambio de tendencia con trendline", o cuando se quiera cruzar el sistema del libro con nuestra evidencia medida. SEÑAL-SOLAMENTE.
---

# yoel-sardinas — el metodo del libro

Sistema completo de Yoel Sardinas (caps X-XII, pp.116-177). Compra de **prima**
(opciones), venc. **semanal**, strikes **ATM/OTM cercanos**. Solo 4 herramientas —
sin RSI, sin MACD, sin Supertrend, **sin stop-loss** (el riesgo ES la prima).
Doctrina de la casa: las probabilidades del libro (">80%") son **afirmaciones del
autor, NO medidas** — nosotros las medimos (ver `## vs nuestra evidencia medida`).

## 1. Config exacta (las 4 armas)

| arma | parametros | panel |
|---|---|---|
| Bollinger | SMA20 central, **2 sigma** (pop std) | precio |
| Medias simples | **20 / 40 / 100 / 200** (SMA, no EMA) | precio |
| Volumen | barras + **media movil 50** | subpanel |
| Velas + trendlines | manual sobre techos/suelos | precio |

Timeframes: **15m, 1H (1H), 1D (diario)**. Regla 88%/80% (pp.~120): el precio vive
dentro de 2sigma el **88%** del tiempo; el autor afirma estrategias >80% fiables
(NO medido). Ciclo de volatilidad: bandas **se abren** (vol sube) y **se cierran**
(squeeze), es ciclico — squeeze precede expansion.

## 2. Proceso TOP-DOWN (obligatorio, en este orden)

Empezar **SIEMPRE en 15m** -> anticipa la **1H** -> anticipa el **1D**. Pero la
**TENDENCIA se define en 1H y 1D**; el 15m solo dispara/confirma la entrada.

**Tendencia = direccion de la SMA20:**
- **Alcista**: precio > SMA20 + SMA20 y bandas **ascendentes**. Cruce confirmador:
  **SMA20 > SMA40** y ambas ascendentes.
- **Bajista**: espejo (precio < SMA20, SMA20/bandas descendentes, SMA20 < SMA40).
- **Fin de tendencia**: precio cruza SMA20 **y** SMA40 y los **promedios se cruzan**
  entre si. Sin el cruce de promedios = solo pullback, no cambio.

## 3. LAS 8 ESTRATEGIAS (tabla accionable)

Vol✓ = la vela gatillo exige **volumen que CRUCE por encima de la MA50** del subpanel.

| # | setup | TF señal | dir | gatillo | filtro-vol |
|---|---|---|---|---|---|
| 1 | Cambio tendencia AL ALZA | 1H | **call** | trendline sobre techos bajistas **ROTA** + precio cruza SMA20 + en 15m SMA20 alcista + vela alcista confirma | — |
| 2 | Cambio tendencia A LA BAJA | 1H | **put** | trendline sobre suelos **ROTA** por vela bajista + vela cruza SMA20 y cierra debajo + en 15m SMA20 bajista | — |
| 3 | Rebote punto medio ALCISTA | 1D | **call** | SMA20-dia sigue alcista + precio **TOCA** SMA20 y **NO** la cruza -> rebota + en 1H vela alcista cruza SMA20 y cierra alcista | — |
| 4 | Rebote punto medio BAJISTA | 1D | **put** | SMA20-dia bajista/lateral + precio sube, toca SMA20 y rebota abajo + en 1H vela cruza SMA20 y cierra debajo | — |
| 5 | Fuera de Bollinger APERTURA (sobrecompra) | 15m | **put** | lateral + gap premarket + al abrir precio **TOTALMENTE fuera** de banda superior + esperar retraccion | **Vol✓** |
| 6 | Fuera de Bollinger APERTURA (sobreventa) | 15m | **call** | espejo de 5: 1ers 15min + precio **fuera** de banda inferior | **Vol✓** |
| 7 | Efecto IMAN BAJISTA (rebote) | 1H+15m | **call** | tend. bajista + precio **MUY** alejado de SMA20 + caida se debilita, vela verde + en 15m precio salio de banda y vela cierra verde | **Vol✓** (vela verde cruza MA50) |
| 8 | Efecto IMAN ALCISTA (correccion) | 1H+15m | **put** | tend. alcista + varios dias subiendo, lo mas lejos de SMA20 + fatiga + velas bajistas + en 15m vela bajista fuera/tocando banda superior | **Vol✓** (vela bajista cruza MA50) |

Estrategias **1-4**: la confirmacion es el **cruce de SMA20** con cierre; el volumen
ayuda pero no es gate formal en el libro. Estrategias **5-8**: el filtro de volumen
es **DURO** (siguiente seccion).

## 4. El filtro volumen>MA50 — la confirmacion DURA (est. 5-8)

**Lo nuevo y testeable del libro.** En 5-8 la vela gatillo **solo vale si su barra de
volumen cruza por encima de la media 50** del subpanel de volumen. Sin ese cruce
**NO hay entrada** — el precio puede estar fuera de banda, pero sin empuje de
volumen es ruido, no reversion. Es un filtro transversal: convierte "toco la banda"
(coin flip) en "toco la banda **con participacion**". Este es exactamente el eje
que nuestra flota ya mide como RVOL — ver `## vs nuestra evidencia medida`.

## 5. El corazon — rebote de punto medio / efecto iman a la SMA20

La **SMA20 es el iman**. Todo el sistema opera el regreso del precio a su media:
- **Rebote de punto medio (3-4)**: en una tendencia SANA, el precio que retrocede
  **hasta** la SMA20 y **la respeta** (toca y no cruza) rebota en direccion de la
  tendencia. Entrada = confirmacion en 1H del rebote (vela que cruza SMA20 con
  cierre a favor). Es continuacion, no reversion de tendencia.
- **Efecto iman (7-8)**: cuando el precio se **estira demasiado lejos** de la SMA20
  (banda reventada, fatiga), la media lo **jala de vuelta**. 7 = tras caida, call
  que vuela a la SMA20/40; 8 = tras subida, put que regresa a la SMA20/40. Aqui SI
  es mean-reversion contra-tendencia de corto plazo, y por eso el **volumen es
  obligatorio** (sin volumen, el band-walk continua y te arrolla).

Distincion clave: **respetar la SMA20** (3-4, continuacion) vs **estar lejisimos de
la SMA20** (7-8, reversion). No confundir un pullback sano con un estiramiento.

## 6. Riesgo, sizing y ADVERTENCIAS

- **Sizing**: 8-12% de la cuenta por trade. **Take-profit +100% automatico** (o mas
  si gapea a favor). No reinvertir toda la ganancia.
- **Earnings**: operar **DESPUES** del reporte, en la apertura siguiente — nunca
  antes (el libro lo dice y coincide con la regla de la casa).
- ⚠️ **SIN STOP**: el libro NO define stop; asume que el riesgo maximo es la prima
  pagada. **Si esto se automatiza HAY que añadir un stop** (la casa es SEÑAL-SOLAMENTE
  y jamas aguanta un print comprado en dia de earnings del ticker). 8-12% sin stop
  es agresivo — degradar el sizing o poner stop de premium.
- ⚠️ **El ">80%" es del AUTOR, NO medido.** Jamas cantar esos numeros como propios.
  Reportar SIEMPRE lo que medimos abajo, con Wilson CI, neto de spread.

## 7. vs nuestra evidencia medida

Cruce honesto de cada bloque del libro con lo que la flota YA midio
(ver [[bollinger-mastery]] para n, Wilson CI y la tabla de filtros completa):

| bloque del libro | afirma | MEDIDO (flota) |
|---|---|---|
| toque/reventon de banda solo | reversion fiable | **~50%** — coin flip; la banda sola no predice |
| fuera-de-banda + reversion (base est. 5-8) | >80% | base flota **65.8%** [64.4, 67.1], pero MFE30≈MAE30 → expectativa ≈0 sin filtro |
| est. 5-6 fuera-de-banda en APERTURA | alta fiabilidad | **CONTRA nuestra medida**: apertura 9:45-10:30 = **58.1%, −7.7 uplift = VETO** (peor hora, MAE −0.9%) |
| filtro VOLUMEN>MA50 (5-8) | confirma la entrada | **CONFIRMADO parcial**: RVOL≥1.5 = 68.5% (+2.7 flota, pero por-ticker vuela: NVDA +22, TXN +19). El volumen SI importa, mas por nombre que global |
| efecto iman / rebote punto medio (7-8) | vuelo a la SMA20 | mean-reversion **56-60%** de base; sube a **76.8%** con squeeze y **85.1%** en la celda estrella squeeze+tarde (14:00-15:30) |
| toque ligero que respeta SMA20 (3-4) | rebote continuacion | consistente con nuestro **toque-ligero ~60%** y band-walk = fuerza (no vender el toque superior en tendencia) |

**Traduccion operativa para la flota:**
1. El metodo Yoel es solido en la ESTRUCTURA (top-down, SMA20 como iman, volumen
   como gate) pero sus horarios estan al reves de nuestra data: **la apertura es la
   PEOR hora**, no la mejor (est. 5-6). Preferir el **efecto iman por la TARDE**.
2. La **celda estrella** (est. 7-8 + squeeze + tarde) = **85.1%** medido — ahi si
   el efecto iman del libro tiene numeros reales. Es la mejor version del metodo.
3. Nunca vender vetos: **z-VWAP≥1.5 (54.8%), RSI2 extremo (53%), apertura (58%)**
   hunden cualquier setup del libro por bonito que se vea el fuera-de-banda.

**Cross-links**: [[bollinger-mastery]] (numeros duros BB/%B/squeeze) ·
[[mean-reversion]] (Hurst, half-life, OU — la mecanica del iman) ·
[[flow-captains]] (el volumen/flujo que confirma o veta la vela gatillo).

## VEREDICTO DE BACKTEST (2026-07-22, medido — NO conectar)
**TEST FIEL 2026-07-23** (confluencia 3-TF + SIN stop + pago de opción semanal ATM Black-Scholes, como Yoel opera): el **rebote-punto-medio (corazón del método) es POSITIVO** — +14% retorno medio/trade, 56% aciertos, Wilson 51%, SOLO con el filtro volumen>MA50 (sin él: 0%). El efecto imán contra-tendencia sale negativo en opción sintética (posible fallo de replicar su timing discrecional). Los tests crudos v1/v2 (con stop, un solo TF, subyacente) fueron INJUSTOS y quedan superados.
- `rebote_sma20` (est 3-4): **49.8%** (n=2076) < toque-ligero 60% → NO CONECTAR.
- `bandopen` fuera-de-banda apertura (est 5-6): **38.9%** (n=1523) << band-open 56% → NO CONECTAR.
- `iman` lejos de SMA20 (est 7-8): **47.7%** (n=3279) < elastic 58% → NO CONECTAR.
- **Filtro volumen>MA50** (la pieza "nueva" del libro): **CORRECCIÓN 2026-07-23 — SÍ añade edge** cuando el target es la SMA20 (no ±0.35%): +5pp en alcanzar la media, **+10pp (37%→47%) en movimiento ≥1.5 ATR a favor**, consistente en ~29/30 tickers. El v1 lo descartó por un target equivocado. CONECTABLE como filtro de confirmación (no señal aislada). Yoel tenía razón sobre el volumen.
- Excepciones por ticker sin poder estadístico: META rebote 71% (n=75), EWY/STX ~60% — color, no señal.
**Matiz honesto**: el instrumento del libro es la OPCIÓN comprada con TP +100% y sin stop; medirlo sobre el subyacente con ±0.35% NO es su método exacto. El test dice que el SUBYACENTE no se anticipa mejor con estas reglas — la skill queda como REFERENCIA doctrinal, no como fuente de señales de la flota. Detalle: `docs/YOEL-BACKTEST-2026-07.md`.
