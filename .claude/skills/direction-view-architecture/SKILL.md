---
name: direction-view-architecture
description: "Arquitectura de la flecha: la BRUJULA es una maquina de estados (el estado fija el signo), el momentum es COMBUSTIBLE en reversion, y la informacion nueva entra como COEFICIENTE multiplicativo con tope duro (FAMILIES_MAX=6 / VETOES_MAX=8 en compass, 14 factores en direction_view) — una feature nueva DESPLAZA a otra. Usar cuando se quiera añadir, retirar o reponderar cualquier factor de la flecha."
---

# direction-view-architecture — la forma de la flecha, no sus numeros

Motores: **`scripts/compass.cpp`** (C++23, la BRUJULA, 37 tests en `tests/test_compass.py`) y
`scripts/direction_view.py` (la media ponderada legacy + el render de la flecha).
Fichas 11 y 23 de `docs/FEATURES-MINED-2026-07-25.md`.

## 1. Por que la media ponderada NO sirve (el bug de FORMA)

Escenario real, con los pesos reales del fichero: 10am, SPY tocando el Muro put de 740, flujo
masivo de puts, doctrina cantando REBOTE.

| Factor | valor × peso | apunta a |
|---|---|---|
| walls | +0.96 ×1.0 = **+0.96** | donde va a GIRAR |
| captain_flow | +1.00 ×1.2 = **+1.20** | donde va a GIRAR |
| bollinger | +0.67 ×1.15 = **+0.77** | donde va a GIRAR |
| flip | −0.80 ×1.5 = −1.20 | donde ha ESTADO |
| fleet | −1.00 ×1.4 = −1.40 | donde ha ESTADO |
| components | −0.70 ×1.3 = −0.91 | donde ha ESTADO |
| momentum | −1.00 ×1.0 = −1.00 | donde ha ESTADO |
| magnet | −1.00 ×1.1 = −1.10 | donde ha ESTADO |

`score = −2.68/9.65 = −0.278` → **▼ABAJO 61%** en un piso impreso con puts inundando.
Reversion +2.93 contra tendencia −5.61.

**La causa raiz NO es un peso mal puesto.** Una media mezcla los factores de DONDE HA ESTADO
(momentum, lado del flip, amplitud, flota, iman) con los de DONDE VA A GIRAR (Muro, %B extremo,
flujo del capitan, agotamiento). **En TODO extremo real los de tendencia estan maximamente en
contra**, asi que promediar SIEMPRE diluye la reversion. Reponderar solo mueve el punto donde
falla.

## 2. La BRUJULA: el ESTADO fija el signo

Maquina de estados, excluyentes por precedencia. Los factores **solo modulan la confianza DENTRO
del estado** — nunca votan el signo.

| Estado | Condicion | Flecha |
|---|---|---|
`SIN LECTURA` | sin spot / barras no contiguas / libro **THIN** / sin mapa GEX / sin niveles | plana, **y DICE por que** |
`REVERSION EN EXTREMO` | nivel **IMPRESO** + **≥2 familias** + **cero vetos** | **GIRA** hacia el rebote |
`CONTINUACION` | un veto de doctrina activo | NO gira ("no fadear") |
`APROXIMANDO` | va hacia el nivel pero **aun no ha impreso** | hueca, prob −8pp |
`CAJA / PIN` | gamma+ densa entre Muros sin extremo | plana |

Umbrales (`namespace K` en `compass.cpp`): `NEAR_PCT 0.0015` (0.15% = "en el nivel"),
`PRINT_MIN 2` con `PRINT_LOOKBACK 8` barras, `APPROACH_EM 0.35`, `HYST_N 2`, `CALIB_MIN_N 30`,
`FORCE_MAX_AGE 120s`.

**PRINT O NADA**: sin 2 lecturas cruzando el estado es APROXIMANDO, jamas la flecha confiada.
**HISTERESIS**: un estado nuevo necesita **2 computos consecutivos** (regla 3 de la doctrina).

## 3. El momentum es COMBUSTIBLE, no un voto en contra

En reversion la magnitud del movimiento cambia de PAPEL: cuanto mas fuerte cayo hacia un piso
IMPRESO con puts inundando, **mas elastico el latigazo**.

```
base = 72 (≥4 familias) | 68 (3) | 62 (2)
base += clamp(|z6| / FUEL_SAT, 0, 1) · FUEL_MAX      FUEL_SAT=2.5   FUEL_MAX=8.0
```
Es la unica forma honesta de usar el momentum en un extremo: como amplitud esperada del giro, no
como direccion. En `CONTINUACION` el momentum vuelve a ser direccional (`base` 65 con band-walk).

## 4. Los 6 vetos (doctrina existente, ninguno inventado)

| # | Veto | Origen |
|---|---|---|
V1 | band-walk ≥2 TF a favor del movimiento | regla 1 |
V2 | regimen **NEG** sin pin impreso — *"el nivel no es piso, NO fadear en el aire"* | memoria `negative-gamma-whipsaw` |
V3 | spot bajo el **VT congelado** → fadear prohibido | [[flip-and-vol-trigger]] |
V4 | el Muro es **TRAMPILLA**, no pin | `gex_core *_kind`, ver [[book-quality-veto]] |
V5 | **3+ toques** del Muro → exhausto, lado de la ruptura | protocolo imanes |
V6 | dia de **catalizador del lider** → la ballena puede ser continuacion | excepcion de la regla 11 |

## 5. AMPLITUD — cuanto, no solo hacia donde

Minimo de restricciones; **jamas prometer mas de lo que cabe**:

| Restriccion | Que mide |
|---|---|
`room` | siguiente nivel estructural en el sentido del rebote — **JAMAS contar con atravesar un Muro** |
`pull` | distancia a la media de Bollinger (iman a la SMA20) |
`retrace` | 50% de la pata + `ext_medido` (extension mediana MEDIDA de `momentum_decay.json`) |
`em_left` | lo que queda del expected move del dia (ver [[expected-move-envelope]]) |

`amp` = el maximo de los "upside" (`pull`/`retrace`/`ext_medido`) **topado** por los techos
(`room`/`em_left`); `binding` nombra la restriccion que ata.

```
ratio = amp / em_pct
grade = LATIGAZO (≥0.50) | REBOTE (≥0.20) | SCALP (<0.20)
mag   = clamp(ratio/0.6, 0, 1)     ← escala el TAMAÑO de la flecha en el chart
```
**Regla 11 (espada-ballena)**: si el giro lo sostiene SOLO el flujo (sin `bb_mid` ni `leg_pct`),
`LATIGAZO` se degrada a `REBOTE` con `capped_by_rule11` — profit pequeño y seguro, no pedir mas.

## 6. EL TOPE DURO — y por que existe (2026-07-25)

De la mineria salieron 30 features y **8 de ellas querian entrar en la flecha** (book-quality,
flip-honesty, em-envelope, chain-delta, cor-fleet, close-drift, skew-lead, level-react).
Hay **dos** modos de colapso, uno por arquitectura, y cada uno tiene su tope:

### a) La brujula (maquina de estados) — `namespace CAP` en `compass.cpp`
```cpp
constexpr size_t FAMILIES_MAX = 6;   // 4 en uso; margen para 2, y hay que justificarlas
constexpr size_t VETOES_MAX   = 8;   // 6 en uso
enum class FamCat { FLUJO, ESTIRAMIENTO, AGOTAMIENTO, PATRON };
```
- Si las **FAMILIAS** crecen sin limite, "≥2 familias" se vuelve trivial (2 de 12 se cumplen casi
  siempre) → **TODO es reversion** y la brujula deja de discriminar.
- Si los **VETOS** crecen sin limite, casi siempre hay uno activo → **NADA revierte jamas** y la
  brujula es un "no operar" permanente disfrazado de analisis.
- **UNA familia por CATEGORIA.** Dos sabores de lo mismo NO son confirmacion independiente — es
  justo lo que hace creer que hay consenso cuando solo hay una medida repetida. Añadir a una
  categoria ocupada exige **SUSTITUIR** la que estaba, y decirlo.
- **Auditoria**: `COMPASS_AUDIT=1` vuelca `fam_hits`/`veto_hits` sobre `g_calls` al JSON, con
  `fam_cap`/`veto_cap`. **Un veto que dispara SIEMPRE no es un veto: es un interruptor de apagado**,
  y solo se ve contandolo.

### b) `direction_view.py` (media ponderada) — tope de **14 factores**
Hoy hay **11 pesos a mano que suman ~12.35**: `flip 1.5, walls 1.0, gex_accel 0.8, fleet 1.4,
components 1.3, captain_flow 1.2, momentum 1.0, bollinger 1.15, candle 0.6, inflation 0.5,
magnet 1.1`. Las propuestas añadian **+6.4 de peso aditivo correlacionado** → recorta el
apalancamiento de cada factor existente ~**34%** y colapsa la varianza de la flecha hacia una
constante ~**58%**.
- Asercion en runtime: `len(weights) ≤ 14`.
- Un factor **aditivo** nuevo exige (a) veredicto `null-control` ≠ UNPROVEN **y** (b) **nombrar el
  que retira**. Candidatos de retirada: `captain_flow` P/C crudo (1.2), `candle` (0.6),
  `inflation` (0.5).
- Test estadistico de guardia: la varianza de `prob` a lo largo de una sesion **no puede
  encogerse >10%** tras ningun cambio de pesos (detector de colapso de varianza).

> **REGLA UNICA QUE RESUME LAS DOS: una feature nueva DESPLAZA a otra, no se suma.**

## 7. Insercion multiplicativa: la unica forma permitida

**La informacion nueva entra como COEFICIENTE sobre los pesos existentes, jamas como termino.**

| Coeficiente | Sobre | Fuente |
|---|---|---|
`book_quality coef` (0.0–1.0) | flip / walls / magnet | [[book-quality-veto]] |
`captain_coef` (1.25 / 1.0 / 0.75) | fleet / components | `cor_fleet`, ver [[peer-captain-evidence]] |
`name_coef` (0.8 / 1.0 / 1.2) | señal de nombre | idem |
`flip_src='static_no_iv'` → ×0.5 | flip | [[flip-and-vol-trigger]] |

**Todo coeficiente aplicado se IMPRIME en `why[]`**: *"muros ×0.4 libro FINO"*,
*"capitan ×1.25 rho 0.81"*. Una flecha cuyos pesos se mueven con una variable de estado invisible
es **inauditable tras una perdida**.

## 8. Fanout: un solo fichero, y la rancidez se grita

`scripts/features_merge.py` ensambla **`data/features_<sym>.json`** desde cada JSON productor
(levels, book_quality, force, chain_delta, pin, em, vt, cor_fleet, wall_stats, cola de
level_events) con `{value, src_file, ts, stale_sec}` por clave. `direction_view` lee **SOLO ese
fichero** con loader cacheado por `mtime`: **un `stat()` por flecha** en vez de ~12
(retraso = dinero). Todo factor con clave **rancia >120 s se pone a cero Y SE DICE EN VOZ ALTA**.

Test de regresion obligatorio: salida de la flecha **byte-identica** antes/despues del refactor
sobre 200 snapshots replayados.

## 9. Honestidad de la probabilidad

```
prob_source='medido'    solo con celda propia n ≥ 30 (K::CALIB_MIN_N)
prob_source='doctrina'  si no → topada a DOCTRINE_CAP = 78%, y se DICE
```
`prob_retroceso_50` **NO** es la prob de la flecha (condiciona en "hubo un impulso", no en "hubo
NUESTRO setup") — se publica en `amplitude.retrace_prob` como lo que es. Ver
[[measured-probability]].

## 10. Checklist antes de tocar la flecha

1. ¿Es informacion nueva o el mismo dato con otro nombre? Si correlaciona, es un **coeficiente**.
2. Si es aditivo: ¿que factor RETIRA? Sin nombre, el PR se rechaza en review.
3. ¿A que **categoria** de familia pertenece? Si ya esta ocupada, ¿que sustituye?
4. ¿Aparece en `why[]` con su valor?
5. ¿Pasa el test de varianza (no encoger >10%) y el de flecha byte-identica?
6. `COMPASS_AUDIT=1` durante una sesion: ¿la familia nueva dispara entre 5% y 60% de las veces?
   Fuera de esa banda es decoracion o interruptor.

Los pesos elegidos a mano **son probabilidades hardcodeadas con otro sombrero**: con 22 factores
conjuntamente no-ajustados ninguna perdida se puede atribuir a una causa. **El tope es doctrina,
no estilo.**

**SEÑAL-SOLAMENTE**: `compass` y `direction_view` escriben JSON de diagnostico y dibujan una
flecha. Jamas ordenan.
