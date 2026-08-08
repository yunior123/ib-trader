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
