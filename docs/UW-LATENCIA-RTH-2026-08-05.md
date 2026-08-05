# UW — latencia en sesion y colinealidades (2026-08-05)

TODOS 8a (latencia RTH) + 8b (websocket en RTH) + 8c (las 3 colinealidades).

## Estado a las 07:2x ET — 8a y 8b quedan **MEDIDO-PENDIENTE** hasta la apertura

**No se midio la latencia esta manana y no es un olvido: a las 07:20 ET el mercado esta en
PREMARKET.** La doctrina de la casa (`~/CLAUDE.md`, "la latencia SOLO se mide en sesion") lo
prohibe porque fuera de RTH la edad del sello es el tiempo desde el cierre, identica para un
endpoint con 0 s de retraso y para uno con 60 min.

Lo unico que se midio ahora, y que **fija la hora con el propio dato en vez de con una suposicion**
(1 peticion):

```
GET /api/stock/SPY/stock-state  ->  200 en 149,1 ms
  market_time : "premarket"
  tape_time   : 2026-08-05T11:19:28Z   (= 07:19:28 ET)
  reloj local : 2026-08-05T11:20:21Z
  cupo UW     : 2.417 / 30.000 usadas hoy
```

La medicion real queda **programada sola** para las **09:35 ET** (5 min tras la apertura, ya con
cinta consolidada y fuera de la subasta):

- `scripts/uw_latency_probe.py --rth-measure` — tope duro **10 peticiones UW/corrida**
- `scripts/com.ibtrader.uwlatency.plist` — `StartCalendarInterval` 09:35, una vez al dia
- **El portero de RTH vive DENTRO del script y aborta fail-loud** (verificado: al invocarlo en
  premarket dijo `FUERA DE SESION ... Probe NO ejecutado` y gasto **0 peticiones**). Un festivo
  no puede producir un numero mal etiquetado.
- Salida: `data/uw_latency.json` + reescritura de este mismo documento con los numeros medidos.

Que medira, y contra que:

| medida | contra que |
|---|---|
| `stock-state.tape_time` vs reloj | edad del feed |
| `net-prem-ticks.tape_time` vs reloj + `cube_lag` | edad del cubo de minuto |
| **UW − print de finnhub** (`data/rt_last_<SYM>.txt`) | **desfase contra el disparador** |

Sin IBKR esta semana (orden vigente), el proxy del disparador es finnhub. **El contraste
definitivo contra `data/bars_<SYM>.txt` sigue abierto en TODOS 8f.**

**Prediccion registrada de antemano (TODOS 8a): 30-90 s.** Si sale < 30 s, sospechar de la
medicion antes de celebrarla.

---

## 8c — las 3 colinealidades (killlist test 1: rho antes que edge, |rho| > 0,9 = muere ya)

Medido con `scripts/uw_colinealidad.py` sobre lo ya archivado. **Cero peticiones UW**: todo sale
de `data/history/`. Numeros crudos en `data/uw_colinealidad.json`.

### Control de metodo (antes de creerse nada)

El recon del 2026-08-04 encontro que `greek-flow.dir_delta_flow` era **byte-identico** a
`net_prem_ticks.net_delta` en 406/406 minutos. Ese mismo control, ahora sobre **1.013.120
minutos** (92 sesiones x 30 syms):

```
rho(dir_delta_flow, net_delta) = 0,9999992
byte-identicos                 = 1.013.079 / 1.013.120  (99,996 %)
```

**El precedente se reproduce a escala de un millon de minutos.** La tuberia mide bien; lo que
sigue se puede leer.

### (1) `dir_vega_flow` vs `signed_premium` — **SOBREVIVE**

| | valor |
|---|---|
| rho agrupado | **0,0706** (n = 1.013.120 minutos, 92 dias, 30 syms) |
| rho por simbolo: min / mediana / max | **−0,242 / 0,193 / 0,544** |
| mas altos | NOK 0,544 · DRAM 0,501 · XLK 0,417 · NVDA 0,402 · MSFT 0,386 |
| mas bajos | SMH −0,242 · SNDK −0,111 · ASML −0,086 |

**Muy lejos de 0,9: vega NO es un re-etiquetado del premium firmado.** Sobrevive el test 1, que
es exactamente lo que la mitad de delta no hizo. Consistente con el recon ("sobrevive solo la
mitad de vega").

**Aviso honesto de inestabilidad**: SPY agrupado en 92 dias da **−0,082**, pero SPY el 8/4 solo
da **+0,327** (verificado a mano, 391 pares). La relacion **cambia de signo entre dias**. Eso
refuerza que no es la misma columna, pero tambien avisa de que cualquier motor que use vega
tendra que condicionar por regimen, no asumir un signo fijo.

### (2) `senal_capitan` vs manada sobre BARRAS — **SOBREVIVE**

`signed_premium` 15 m del capitan contra la amplitud (`ret15` de la flota) en rejilla de 5 min,
mismo minimo de cobertura que `fleet_consensus` (27/30 votando, si no es FEED y no direccion):

| capitan | rho | n buckets | acuerdo de signo |
|---|---|---|---|
| SPY | **0,420** | 678 | 68,1 % |
| QQQ | **0,506** | 678 | 72,2 % |
| SMH | **0,123** | 678 | 56,6 % |

**Ninguno pasa de 0,51: el premium del capitan NO es la manada de barras con otro nombre.** Miden
cosas distintas (dolares agresivos en opciones vs. cuantos nombres suben), que es justo lo que la
regla 12 de la casa afirma sin haberlo medido hasta hoy.

**Aviso de muestra**: `n = 678` son buckets **solapados** (ventanas de 15 min sobre rejilla de
5 min) de solo **9 sesiones** (2026-07-21 → 07-31, las que tienen `bars/` archivadas). El `n_eff`
real es **mucho menor** que 678. Sirve para descartar colinealidad (que es lo que pedia 8c); **no
sirve para publicar una probabilidad** — eso sigue bloqueado en 8e.

### (3) `max_pain` (UW/OI) vs `abs_wall` (gex) — **SOBREVIVE**

| | valor |
|---|---|
| rho de (nivel−spot)/spot | **−0,0196** (n = 185 sym-dias, 7 sesiones) |
| strike identico | **8,6 %** |
| mediana \|max_pain − abs_wall\| / spot | **5,14 %** |

Filas reales del 8/4 que explican el rho≈0:

```
SMH   spot 576,86   max_pain 585,00   abs_wall 530,00   |d| 9,53 %
NVDA  spot 212,44   max_pain 200,00   abs_wall 210,00   |d| 4,71 %
MU    spot 889,80   max_pain 940,00   abs_wall 800,00   |d| 15,73 %
MSFT  spot 495,30   max_pain 440,00   abs_wall 500,00   |d| 12,11 %
SKHY  spot 142,93   max_pain 143,00   abs_wall 145,00   |d|  1,40 %
AMZN  spot 277,51   max_pain 250,00   abs_wall 280,00   |d| 10,81 %
```

**No son el mismo iman: coinciden en menos de 1 de cada 10 sym-dias y de media estan a 5 % del
spot el uno del otro.** `max_pain` sobrevive el test de colinealidad — pero que sea *distinto* de
`abs_wall` no lo convierte en *operable*: eso exige su propia medicion de edge contra el null de
nivel aleatorio, y sigue bloqueado en 8e.

**Bug de higiene cazado durante esta medicion**: la primera pasada metia `2026-07-25` (sabado),
`07-26` y `08-02` (domingos) porque existe un `levels.json` rancio en esas carpetas — 77 sym-dias
duplicados del viernes anterior inflando la muestra. Corregido con un filtro de dia de mercado
(`uw_colinealidad.dias_de_mercado`); n bajo de 262 a 185 y el rho de −0,025 a −0,0196.

### Veredicto de 8c

**Las tres sobreviven el test 1 de la killlist (ninguna con |rho| > 0,9).** Ninguna muere hoy, y
ninguna nace probada: pasar de "no es colineal" a "tiene edge" exige el null de entrada aleatoria,
BH-FDR y `n_eff` suficiente — TODOS 8e, que sigue **BLOQUEADO por muestra**.

---

## Estado de los TODOS 8

| todo | estado |
|---|---|
| 8a latencia RTH | **MEDIDO-PENDIENTE** — programado 09:35 ET hoy (launchd) |
| 8b websocket RTH | **MEDIDO-PENDIENTE** — en la misma corrida de las 09:35 |
| 8c colinealidades | **HECHO** — las 3 sobreviven, numeros arriba |
| 8d archivador forward-only | **HECHO** — `uw_netprem_archive.py` + launchd 16:10 |
| 8e alertas con probabilidad | **BLOQUEADO** por muestra (n_eff), a proposito |
| 8f contraste contra IBKR | **BLOQUEADO** — sin TWS/Gateway esta semana |
