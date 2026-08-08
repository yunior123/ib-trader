# Desequilibrio de delta — lo que se midió y lo único que sobrevive (2026-08-07)

Orden: *"try to setup delta imbalance alert and whether to enter or exit a trade based on that
plus the target price, search github for best skills for delta imbalances, take a look at these
expert posts, backtest them with real data, see what are the patterns he is using."*

## Muestra
85 sesiones × 30 símbolos = **939.784 minutos** con las dos series alineadas al mismo minuto:

| serie | fuente | qué aporta |
|---|---|---|
| `dir_delta_flow`, `total_delta_flow`, `otm_dir_delta_flow` | `data/history/<día>/uw_greek_flow_<sym>.json` (UW, 1 fila/minuto) | delta de opciones firmado por agresor |
| `o/h/l/c/v` 1m | `poly_bars` de `data/trades.db` | precio y ATR14 |

Solape real 2026‑03‑24 → 2026‑07‑24 (`poly_bars` acaba el 07‑24; los 9 días posteriores del
archivo UW quedan fuera y se cuentan: 195 pares sym‑día sin barras, 951 minutos descartados).
Preparación: `scripts/delta_imbalance_prep.py`.

## Qué se probó (y de dónde sale cada patrón)

La literatura de order flow tiene dos familias y se probaron las dos. La rigurosa es **OFI**
(Cont, Kukanov & Stoikov, *The Price Impact of Order Book Events*), y la de calle es el
footprint: **absorción, delta, imbalances apiladas**. GitHub no tiene nada empaquetado y maduro
para esto: lo que hay son reimplementaciones de OFI de 2‑3 estrellas, no una "skill".

| patrón | definición medida | resultado |
|---|---|---|
| delta crudo, seguir | z de la suma de 1/5/15 min ≥ θ, se opera CON el delta | edge **+0,3…+0,8 pp**, CI cruza 0 |
| delta crudo, fadear | igual, contra el delta | ídem, espejo |
| APILADO (*stacked imbalance*) | 3 minutos seguidos del mismo signo sobre θ | +1,0 pp, CI cruza 0 |
| ABSORCIÓN (*delta divergence* por minuto) | delta fuerte y el precio no acompaña → contra el delta | no llega ni al top‑32 |
| CONVICCIÓN | delta por contrato en el quintil alto del símbolo | +0,0…+1,0 pp, CI cruza 0 |
| RELEVANCIA | \|delta\| grande frente al volumen de acciones | +0,1…+1,4 pp, CI cruza 0 |
| ORO / PICADORA | mismo gatillo por franja horaria | **la picadora puntúa igual que el resto** |

**0 de 128 celdas pasan BH‑FDR q=0,10.** Y el control negativo (11:30‑14:00, la franja donde la
doctrina dice que no hay nada) marca +1,35 pp, tanto como los patrones "buenos": eso es la firma
del ruido, no de una señal. `scripts/delta_imbalance_patterns.py`.

## Lo único que sobrevive: divergencia sobre el delta ACUMULADO

El error de bulto de la primera tanda fue medir la divergencia sobre el **incremento** por
minuto. La literatura la define sobre la **línea acumulada** (CVD / HIRO): el precio hace
extremo nuevo de *w* minutos y el delta acumulado **no** lo acompaña.

```
DIVERG_BAJISTA_w15   n=73.111  2.407 clusters   wr 0,510 vs null 0,498
                     edge +1,11 pp   CI bootstrap [+0,52, +1,70] pp   p < 1e-4   BH-FDR: pasa
```

Y el contraste directo, misma población y mismo horario (`scripts/delta_imbalance_veto.py`):

| | dentro de la divergencia | fuera | Δ | CI 95% | p |
|---|---|---|---|---|---|
| **LARGO** en divergencia bajista | 48,69% | 49,72% | **−1,02 pp** | [−1,58, −0,50] | 1,2e‑7 |
| CORTO en divergencia bajista | 50,96% | 50,03% | +0,93 pp | [+0,41, +1,49] | 1,4e‑6 |
| CORTO en divergencia alcista | 49,56% | 50,15% | −0,60 pp | [−1,13, −0,06] | 2,8e‑3 |
| LARGO en divergencia alcista | 50,14% | 49,58% | +0,56 pp | [+0,01, +1,09] | 5,2e‑3 |

Asimétrico a propósito: **la divergencia bajista pesa el doble que la alcista** — coherente con
la doctrina de la casa de que el pico de calls marca techo y el suelo no es su espejo.

## El veredicto, sin maquillar

**Un punto porcentual NO es una entrada.** Con barrera simétrica y `n_eff` topada por clusters,
el Wilson‑LB de la expectancia sigue **negativo**: comprar por esto pierde después de costes.
Lo que sí es un punto porcentual es un **VETO**, exactamente como `vol-trigger`:

- **ENTRAR** por desequilibrio de delta: **no**, en ninguna de sus formas. Medido.
- **NO AGUANTAR** un largo dentro de una divergencia bajista viva: **sí** (−1,02 pp, p=1,2e‑7).
- **OBJETIVO y STOP**: de los percentiles de la propia muestra, no de una opinión —
  **MFE p60 = 1,08 ATR** (objetivo) y **MAE p75 = 1,29 ATR** (el stop de 1,0 ATR está DENTRO del
  ruido: un cuarto de los ganadores lo pierde antes). Toque mediano a los **3 minutos**.

## Motor

`scripts/delta_imbalance.cpp` → `bin/delta_imbalance` (C++23, `-O3 -Wall -Wextra`, cero
warnings). Lee las barras vivas + el archivo UW del día + `data/research/delta_imbalance_veto.json`
(**sin la calibración medida sale con rc=3 y no afirma nada**), y publica
`data/delta_imbalance.json` con estado, veto, objetivo y stop. **Sin voz.**
`scripts/delta_imbalance_keepalive.sh` lo corre cada 60 s dentro de la ventana de la flota.

Verificación del port: `./bin/delta_imbalance --dump SPY` frente a la réplica en Python sobre
los mismos dos ficheros — **576/576 minutos idénticos**, 22 BAJISTA y 17 ALCISTA en ambos.

## Lo que falta para poder subir de VETO a SEÑAL

1. Condicionar por régimen de gamma (el archivo de cadenas es *forward-only* desde julio).
2. Divergencia **en un nivel** (muro/flip), no en el aire — es como la usa el footprint.
3. Repetir con `poly_bars` extendido más allá del 2026‑07‑24 para recuperar las 9 sesiones.

---

# CORRECCIÓN: lo que @astocks92 llama "delta imbalance" NO es lo que yo medí

Yunior mandó mirar la cuenta. Es **@astocks92 ("The Architect", 35.298 seguidores)**, y su bio
lo dice entero: *"enjoy analyzing data | GAMMA, delta, vanna charm analysis | ... NEVER CHART
AGAIN"*. Leída por la API de X con las credenciales del repo (`config/x.env`, OAuth1; el bearer
da 401), 304 posts de 2026‑06‑24 a 2026‑08‑07.

El post que importa: **2026‑08‑04 14:31 — "$AAPL 8/28 $315C · Playing the delta imbalance ·
Lotto sized"**. Y el 08‑03: *"S/O a todos los que siguieron el delta & skew"*.

**Su "delta imbalance" es el desequilibrio del SKEW por strike, no el flujo de delta por minuto.**
Su propia definición, en sus palabras:

| fecha | post |
|---|---|
| 07‑07 | *"Remember: **SKEW is pricing in inventory**"* |
| 06‑26 | *"**Dealer inventory** Monday $QQQ y $SPY: Call side 3‑6%. Put side 12‑15%"* |
| 06‑30 | *"$SPY >$750 is 28%+ Call side Skew | Put side to $740 is 7%"* |
| 07‑14 | *"$QQQ: Call skew runs 19% a 25%+ para $1‑$6+ | Put skew 4% a 6%"* |
| 07‑12 | *"$QCOM: **85th Percentile CALL SKEW 25 Delta**"* |
| 07‑21 | *"Gamma = cuánto cambia delta; **Speed** = cuánto cambia la propia gamma... Delta puts subiendo + IV bajando + **charm support**"* |

O sea: una medida **transversal sobre la cadena** (IV por strike frente a la ATM, por lado, a
$1..$6 del spot) y percentilada contra su propia historia. Nada que ver con la serie temporal de
`dir_delta_flow` que medí arriba. **Mi estudio midió otra cosa** — sigue siendo válido para lo
que mide, y su veredicto (VETO, no entrada) no cambia. Pero no era su métrica.

## Su métrica, reproducida — `scripts/skew_imbalance.py`

Sale de `chain_full_<sym>.json`, que ya archivamos con IV y griegas MEDIDAS de Polygon:

```
SPY 2026-08-07  spot 772.88   venc 08-10
   call skew $1..$6:  -5 -4 -6 -5 -6 -5   media -5.0%
   put  skew $1..$6:  +2 +6 +6 +9 +12 +14 media +8.3%
   IMBALANCE -13.3% -> lado PUT mas caro  |  RR25 -1.08 vol pts
```

Formato idéntico al suyo. Añade además el **risk reversal 25Δ**, que es lo que permite el
percentil del que él habla.

## La lectura que se deduce de su operación: **compra el lado BARATO**

El 04‑ago AAPL tenía el **put** claramente más caro (imbalance −13,1% a 1 día, −7,0% a 3 días;
RR25 −4,0 vol pts) — y él compró **calls** (315C, +1,8% OTM). No sigue el skew: lo **fadea**. Si
"skew = inventario del dealer", el inventario estaba cargado de puts y la convexidad barata
estaba en las calls.

Resultado de esa operación con nuestros propios datos: AAPL 309,44 (04‑ago) → máximo **315,66**
el 06‑ago → 313,33 el 07‑ago. Él publicó +17% al día siguiente. **n=1: es una anécdota, no
evidencia.** La serie de SPY es coherente con la misma lectura (31‑jul imbalance −30,9%, el más
extremo del archivo → SPY 747,49 → 771,12 en dos sesiones), pero eso también es n=1.

## Estado honesto y qué falta

`chain_full` solo tiene **13 sesiones archivadas** (25‑jul → 7‑ago). El percentil del que él vive
exige ≥30 y un keep/kill honesto ~60. Por eso `skew_imbalance.py` **dice "sin percentil: 13
sesiones archivadas, hacen falta 30"** en vez de inventar uno. El archivo crece solo (ya
archivamos las cadenas a diario), así que el reloj corre desde hoy.

Hipótesis registrada para graduar cuando haya muestra, con la misma vara que todo lo demás
(triple barrera, null emparejado, n_eff, BH‑FDR): **comprar el lado con el skew más barato
cuando el imbalance está en el decil extremo de su propia historia**.

---

# TEST del skew con un año de datos — y el confound que se lo come (2026-08-08)

Orden de Yunior: *"no dejes todo eso, nowwww, search the data u need then testssssss"* y
*"read all his x posts and see"*.

## Los datos que faltaban, conseguidos

`chain_full` solo tenía 13 sesiones. La historia estaba en un endpoint de UW que no usábamos:
**`/api/stock/{t}/historical-risk-reversal-skew`** — serie DIARIA del risk reversal 25Δ por
vencimiento, **hasta 2025‑08‑11** (un año). `scripts/skew_rr_fetch.py` monta la escalera de
vencimientos mensuales y la archiva: **36 símbolos × ~250 días**.

Cruzado con `poly_bars` 1m → **4.982 observaciones** con percentil expandido (sin mirar el
futuro, ≥60 días propios antes de percentilar), 29 símbolos con serie usable.
Serie de **madurez constante**: cada día se toma el vencimiento con DTE más cercano a 30.

## El resultado que parecía bueno

`scripts/skew_rr_study.py`, triple barrera sobre el camino 1m real, entrada a la APERTURA del
día siguiente (el RR es de cierre: cero look‑ahead):

```
cola 10 · FADE (comprar el lado barato) · TP=SL=1 ATR · H=1 día
n=514   clusters-día=126   wr 0,547 vs null 0,473
edge +7,39 pp   CI bootstrap [+1,96, +12,94]   p=0,018   ÚNICA celda positiva que pasa BH-FDR
```

Siete veces el efecto del flujo de delta, en la dirección exacta que dedujimos de su operación
de AAPL, y sólo a **1 día** (a 3 y 5 días desaparece) y sólo en el **decil** extremo.

## El confound: era la deriva, no el skew

El null usaba dirección ALEATORIA. Pero las entradas no están balanceadas: **el 64% son cortos**
(la cola alta manda). En ese periodo el lado corto pagaba solo:

| control (mismas fechas, mismos símbolos) | win rate |
|---|---|
| señal cola10 fade | **54,67%** |
| **SIEMPRE CORTO** | **54,47%** ← casi idéntico |
| SIEMPRE LARGO | 45,53% |
| desglose: cola alta → corto | 57,14% (n=329) |
| desglose: cola baja → largo | 50,27% (n=185) |

Contra el null HONESTO —**mismos días, mismos símbolos, misma mezcla long/short, pero con el
skew NO extremo**— el edge cae de +7,39 pp a:

```
+4,25 pp   CI [-0,86, +8,58]   p=0,129   ->  NO SIGNIFICATIVO
```

**Veredicto: UNPROVEN.** El +7,4 pp era en su mayor parte la deriva bajista del periodo. Lo que
queda atribuible al skew son ~2,6 pp en el lado corto, con el intervalo cruzando el cero.
No está muerto —el punto estimado sigue siendo positivo y es lo mejor medido hasta ahora—
pero no pasa la vara, y por poco no publico un número que era beta disfrazada.

## Lo que falta para volver a intentarlo

1. Más muestra: 126 clusters‑día es poco. La serie crece sola (el fetch es reanudable).
2. Neutralizar el mercado: la prueba correcta es **long/short contra el sector o contra SPY**,
   no direccional — así la deriva no puede colarse por la puerta de atrás.
3. Condicionar por régimen de VIX (ver abajo): él nunca mira el skew solo.

---

# El método completo de @astocks92, leído en sus 610 posts (2026‑05‑09 → 08‑07)

El skew es una pieza de siete. Ordenadas por cuánto las repite:

| pieza | qué es | ¿lo tenemos? |
|---|---|---|
| **$VIX PIVOT** (~50 posts) | un número diario + T1/T2/T3 arriba/abajo. VIX **encima** = los índices "mienten" (bajista); **debajo** = alcista. "VIX crush de T2 a pivot es sano". Retó a 150+ seguidores a adivinarlo: **0 aciertos** → fórmula propia. Afirma que el HOD/LOD del VIX cae a **$0,01‑0,04** del pivote casi a diario | **NO.** Es su pieza central y no la tenemos |
| **Niveles con % de ODDS** | líneas amarilla/azul/roja = strikes a probabilidad fija. *"$SPY 13% y 7% odds a +$11; 6% a $7 abajo"*, *"MM hedged hasta $722,28 — not offsides"*, y la frase clave: ***"d spot delta diff both sides — this drives skew"*** | **Casi.** Es delta‑como‑probabilidad sobre la cadena: trivial desde `chain_full` |
| **PIVOT/CEILING/FLOOR semanal** | fijados el lunes, **no se cambian** en toda la semana | NO |
| **MAPS / incentivo del dealer** | *"$SPY: burn upside calls >$734/735 + burn $730P; $QQQ: burn shorts <709, demasiadas calls >711 → CHOP"* | **SÍ** = nuestro mapa gamma + pin/max‑pain, con otro nombre |
| **SKEW = inventario** | call/put side % a $1..$6 + percentil 25Δ | **SÍ** (`skew_imbalance.py` + `skew_rr_fetch.py`) |
| **IV vs RV para earnings** | *"$TXN: IV 43% por encima de su RV normal"*, objetivos de expansión de IV e "IV crush" | Parcial (`event-premium-discipline`) |
| **Curva VIX** contango/backwardation + VIX9D + VVIX | *"know when LONG vs Short"* | Parcial (`cboe-data` trae VX) |

Dos frases suyas que resumen la doctrina y que coinciden con la de esta casa:
*"SKEW is pricing in inventory"* y *"Prediction = delivery = boring"*.

**La pieza que más rendimiento daría copiar es el VIX PIVOT**, no el skew: es lo que usa como
portero de TODO lo demás ("who is lying?"), y es una afirmación **falsable con los datos que ya
tenemos** (VIX diario + intradía) — si un candidato de fórmula reproduce el HOD/LOD del VIX a
±$0,04 con la frecuencia que él publica, eso se mide y se cierra en una tarde.
