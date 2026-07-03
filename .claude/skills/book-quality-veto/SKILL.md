---
name: book-quality-veto
description: "Veto por calidad de libro: gross/net/HHI, percentil propio del ticker, strikes poblados, pin vs trampilla del abs_wall, y el coeficiente MULTIPLICATIVO que apaga la voz gamma en libros FINOS. Usar antes de cantar cualquier muro, flip o iman, y siempre en DRAM, SPCX, SKHY, EWY y NOK."
---

# book-quality-veto — cuando el mapa gamma es decoracion

El mapa gamma de NOK son **4 strikes**. DRAM/SPCX/SKHY/EWY son libros de **3 contratos**. Y hoy
cantamos veredictos de muro sobre ellos con la misma cara que sobre QQQ. Esta puerta es un
**veto multiplicativo**, no un factor aditivo mas: multiplica los pesos que ya existen y puede
llevarlos a **cero**.

Motor: `scripts/book_quality.py` (feature 3) sobre el `profile` de `scripts/gex_core.py`.
Espejo para los bots C++: `data/book_quality.json`. Claves aditivas en `charts/data/levels_<sym>.json`.

## 1. Orden de chequeo (esta puerta corre PRIMERO)

```
book-quality  →  regla 12 del capitan  →  Bollinger (banda estirada en contra)  →  optgate.py
```
Corre **antes** de la jerarquia de capitanes y **antes** del veto de vehiculo. Si el libro es
FINO no hay nada que jerarquizar: no hay mapa.

## 2. Las metricas, en orden

1. `gross = Σ|GEX_K|` · `net = Σ GEX_K` · `bifurcation = gross/|net|`
2. `HHI = Σ(|GEX_K|/gross)²` · `n_strikes_populated` · `greeks_ok_pct` (cabecera de cadena, ver
   [[chain-data-contract]])
3. `book_pctile` = percentil de `gross` contra las **propias 20 sesiones previas del ticker**
   (`trades.db gex_daily`) — **SOLO desde el snapshot completo de Polygon**. Con la banda IBKR
   (±1.45% real) `gross` mide la ventana del fetcher, no el tamaño del libro.
4. `impact_pctile` = percentil de `gross / (ADV20_shares · price)` — cuanta gamma nocional hay
   por dolar de liquidez del subyacente (el medidor Impact de SpotGamma).
5. `abs_wall_kind` = **pin** o **trampilla** (seccion 4 — el fix ya esta en el codigo).

## 3. Etiqueta → coeficiente → que se permite

| Etiqueta | Condicion | `coef` | Licencia |
|---|---|---|---|
| `THIN` | `book_pctile < 0.20` **o** `n_strikes_populated < 8` **o** `greeks_ok_pct < 0.5` | **0.0** | **toda voz gamma MUTEADA**; wall/flip/magnet a cero; banner solamente; operar solo precio / momentum / capitan |
| `BIFURCATED` | `net < 0` **y** `bifurcation > 4` **y** `book_pctile > 0.5` | ver formula | scalps nivel-a-nivel SI; trades de direccion-por-regimen **PROHIBIDOS** |
| `NEAR_FLIP` | `\|spot − flip_open\|/spot < 0.0015` | ver formula | whipsaw: histeresis obligatoria, 2 lecturas sostenidas |
| `STABLE_PIN` | resto | ver formula | mapa gamma utilizable con normalidad |

```
coef = 0.0 si THIN ; si no  coef = clamp(0.35 + 0.65·min(book_pctile, impact_pctile), 0, 1)
```
El coeficiente **multiplica** los pesos existentes `flip(1.5)` / `walls(1.0)` / `magnet(1.1)` de
`direction_view` — jamas entra como termino nuevo (ver [[direction-view-architecture]]).
Y **se imprime en `why[]`**: *"muros ×0.4 libro FINO"*. Un coeficiente invisible es inauditable
tras una perdida.

En la brujula (`scripts/compass.cpp`) el label THIN o `book_coef == 0` fuerza el estado
**SIN LECTURA** con el motivo *"libro THIN: los niveles gamma son decoracion en este nombre"*.
La flecha se pone plana y DICE por que. Eso es lo correcto.

## 4. PIN vs TRAMPILLA — el fix, y el error que casi se comete

**Estado: YA ESTA EN `scripts/gex_core.py` (2026-07-25).** Antes, `abs_wall`/`call_wall`/`put_wall`
devolvian **solo el strike** (`max(...)[0]`) y se tiraba todo lo demas. Consecuencia: un nivel que
**AGUANTA** y un nivel que el precio **ATRAVIESA acelerando** eran el MISMO dato para todos los
consumidores — incluido el veto de 0DTE, que disparaba sobre la mitad equivocada de los casos.

Ahora hay `*_net` (gamma neta en el strike = fuerza del muro), `*_regime` y `*_kind`.

> **El discriminador NO es el signo crudo del perfil en el strike.** Con la convencion naive
> (calls +, puts −) un put wall tiene gamma neta negativa **POR CONSTRUCCION**, asi que
> "signo<0 = trampilla" etiquetaria **TODO put wall como trampilla** y el veto se dispararia
> siempre. El discriminador correcto es el **REGIMEN ACUMULADO en ese nivel** — de que lado del
> gamma-flip cae:

| `_regime` | `_kind` | Mecanica | Operativa |
|---|---|---|---|
| POS (strike ≥ flip) | **pin** | dealers amortiguan | el nivel **aguanta**: fade del borde hacia el nivel permitido |
| NEG (strike < flip) | **trampilla** | dealers amplifican | el precio lo **atraviesa acelerando**: **fadear PROHIBIDO** |

Consumo aguas abajo:
- `compass.cpp` veto **V4**: `wall_kind == "trampilla"` → estado CONTINUACION, la flecha NO gira,
  motivo impreso *"<nivel> es TRAMPILLA (gamma NEG), no piso"*.
- `compass.cpp` veto **V2**: `regime == "NEG"` y el nivel no es pin → *"el nivel no es piso, NO
  fadear en el aire"* (memoria `negative-gamma-whipsaw`).
- `abs_wall_kind = trampilla` a ±1 strike del spot → **VETO DURO sobre 0DTE comprado**.
- `pin-clock` solo declara `PIN_DAY` si el `abs_wall` es **pin** (ver [[pin-and-expiry-mechanics]]).
- `close-drift` solo se arma con `abs_wall` **pin** — el pinning por charm necesita dealers que
  amortiguen.

## 5. Los muros y su decaimiento: conteos primero, cero probabilidad

`wall-decay ledger` (feature 21) registra `wall_touches(ts, sym, wall_type, level_px, touch_idx,
regime, hour, health, dgex, outcome)` y publica `data/wall_stats.json` con **solo conteos**.

- Un **toque** = high/low dentro de `0.10%·S` del nivel, valido **solo tras una excursion previa
  ≥ h·ATR14_1m** de alejamiento (histeresis).
- Salud del muro por gamma DESAPARECIENDO de verdad, no por un contador:
  `BUILDING | HOLDING | WEAKENING`.
- **Salida obligatoria: la curva de sensibilidad en `h ∈ {0.25, 0.5, 1.0}`.** Si el gradiente de
  `touch_idx` existe en un solo umbral, no es real. Es el detector de overfit mas barato que hay.

Mientras no haya celda con `n ≥ 40` clusters-dia independientes, **los veredictos de muro se
cantan SIN NUMERO**: *"muro 690, 2º toque, regimen POS"* y nada mas.

> **El "1er toque rebota ~70%" HARDCODEADO sale de la skill [[gamma-regime-walls]] el dia que
> esta tabla exista, diga lo que diga la tabla.** Es un numero inventado con sombrero de doctrina.

Una vez calificada la celda: operar el muro solo con `p_lo ≥ 0.55` para el
`(touch_idx, regime, health)` actual; `touch_idx ≥ 3` **o** `health=WEAKENING` → **nunca fadear**,
voltear al lado de la ruptura tras retest-y-rechazo. Expectativa honesta: **6-12 meses** antes de
que alguna celda califique.

## 6. Los cinco nombres a vigilar siempre

**DRAM · SPCX · SKHY · EWY · NOK.** La salida esperada de esta puerta es **silencio gamma
PERMANENTE** en ellos, y eso vale mas que cualquier señal nueva. En esos nombres:
mapa gamma = null, veredicto = precio/momentum/capitan, y `optgate.py` dira casi siempre
**OPCIONES VETADAS → acciones/ETF apalancado** (spread medido 8-20% en DRAM).

Si un dia THIN mutea un nombre donde la logica solo-precio era ya todo lo que usabamos, la puerta
es un no-op ahi — y eso tambien esta bien: es una afirmacion de **calidad de dato** (4 strikes no
pueden definir un muro), no de edge. Embarca aunque este subpotenciada.

## 7. Al hablar

- *"libro FINO — mapa gamma no fiable, operar solo precio"* (PDF y banner). Badge de color en
  `charts/live.html`.
- Nunca decir "muro" sin el `_kind`. Un muro sin tipo es media informacion.
- **SEÑAL-SOLAMENTE**: esta puerta apaga voces y factores; no ordena nada al broker.
