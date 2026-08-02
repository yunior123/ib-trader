---
name: dealer-flow-limits
description: "Que se puede y que NO se puede medir del flujo de opciones sin cinta OPRA: volumen ponderado por gamma y por delta, turnover vol/oi, HHI y el control obligatorio de spot congelado, con prohibicion explicita de decir flujo FIRMADO porque la cinta de opciones no esta autorizada y el mid de 5 minutos lo domina vega. Usar cuando alguien proponga HIRO, DNF, OI firmado, deriva del centro de masa gamma o cualquier flujo de opciones."
---

# dealer-flow-limits — la frontera entre medir y fabricar

Esta skill existe para decir NO con numeros. Tres plataformas venden "flujo de dealers"; lo unico
genuinamente caro que tienen es **HIRO**, y esta **fuera de alcance verificado**. Todo lo demas se
puede reproducir — pero no todo lo que se puede computar se puede AFIRMAR.
Fichas 22 y 28 + los muertos #1 y #16 de `docs/FEATURES-MINED-2026-07-25.md`.

## 1. La frontera, medida (no de memoria)

| Endpoint | Estado |
|---|---|
`/v3/snapshot/options/{SYM}` | **200** — greeks + IV + OI + `day.volume` por strike/expiry |
`/v3/snapshot?ticker=O:<contrato>` | 200 — greeks/IV/OI/session, **sin bid/ask ni last_trade** |
`/v3/trades/O:<contrato>` · `/v3/quotes/O:<contrato>` | **403 NOT_AUTHORIZED** |
`/v2/last/trade/O:` · `/v2/last/nbbo/O:` | **403** |
**`/v3/trades/AAPL` · `/v3/quotes/AAPL`** (acciones) | **403 — el MISMO error** |
`/v3/snapshot/indices?ticker=I:SPX` | **403** |
`/v2/aggs/ticker/O:<contrato>` | 200 pero **sin OI y sin griegas** |

> **El 403 NO es de opciones** (medido 2026-07-25): las acciones y los índices dan el mismo
> `NOT_AUTHORIZED`. El plan **no tiene carril de CINTA en absoluto** — es agregados + snapshots.
> No hay endpoint escondido ni variante delayed. Sin cinta no hay lado agresor, y sin lado agresor
> **no hay flujo FIRMADO por Polygon**. Punto.

**Pero eso NO cierra HIRO** — ver §6: la cinta firmada ya la pagamos en IBKR.

## 2. PROHIBIDO: la palabra "firmado" / "signed"

Tres razones independientes, cada una suficiente:

1. **La cinta no esta autorizada** (arriba).
2. **El firmador por residuo de premium no funciona**: los cambios de mid a 5 minutos estan
   **DOMINADOS por `vega·dσ`**. Un firmador que omite ese termino es una moneda al aire con
   pretensiones.
3. **`dvol` es volumen NETO ACUMULADO** sobre cientos de prints bilaterales. **No hay lado por
   print que recuperar** — la informacion ya se perdio en la agregacion.

Lo que SI se conserva: volumen ponderado por gamma y por delta, **SIN SIGNO**, bajo un nombre que
no miente. Renombrar es la mitad del trabajo honesto.

## 3. `signed-oi` esta MUERTO, con el numero que lo mato

La idea era reconstruir el inventario del dealer reconciliando ΔOI con volumen. Sobre nuestro
propio fichero:

```
QQQ 685C:  vol_day = 238.672     OI = 2.348
open_frac = |ΔOI| / V_day  ≈  0.01
```
La restriccion de minimos cuadrados **no tiene casi apalancamiento** en dias 0DTE/indice — que son
los UNICOS dias para los que se propuso. Construccion mas pesada del roster con el MENOR
apalancamiento. Y su regla (anular la etiqueta de regimen cuando dos flips discrepan >0.3%)
**convertia su propio ruido en un veto silencioso a nivel de flota**.

Si alguien lo reinventa en tres meses: `open_frac ≈ 0.01`. Ese es el numero.

## 4. Lo que SI se mide: `chain-delta engine` (en SOMBRA)

Por par de snapshots consecutivos de 5 min, por strike:

```
dvol   = vol_t − vol_{t−1}                                   (descartar ≤ 0)
gwv(K) = gamma_BS(S,K,T,iv) · dvol · 100 · S² · 0.01          → gwv_calls / gwv_puts
dwv(K) = |delta_K| · dvol · 100 · S                           SIN SIGNO
turn(K) = vol_t(K) / max(oi(K), 1)     y  dturn sobre 3 snapshots
vol_hhi = Σ((dvol_K/Σdvol)²)      CoM = Σ K·|GEX_K| / Σ|GEX_K|      hhi_gex
z de gwv contra su propia distribucion de 3 dias en esa banda de strikes
```

**Beneficio colateral inmediato**: `dwv` actualiza `scripts/opt_whale_watch.py` de ponderacion por
**conteo de contratos** a ponderacion por **`|delta|`** — la normalizacion teoricamente correcta.
10.000 contratos de delta 0.02 no son 10.000 contratos de delta 0.60.

### El CONTROL DE SPOT CONGELADO es una PRE-PUERTA DURA
```
recomputar CoM y GEX con el spot fijado en spot_0935  →  chart_levels.gen(sym, spot=spot_0935)
publicar SOLO el residuo:  dcom_resid = dcom − dcom_frozen
si |dcom_resid| < 0.5·|dcom|  →  la deriva es PRECIO RE-ETIQUETADO  →  el campo publica NULL
```
> **Si el test de residuo FALLA — que es el caso base probable, porque el OI intradia es ESTATICO —
> la feature ENTERA se BORRA en vez de mitigarse.**

Misma tautologia que mato el "iman movil" de CoM y el `dflip/dt`: **el OI de IBKR es de cierre
previo y esta CONGELADO intradia**, asi que cualquier derivada temporal mide **el spot moviendose
bajo un libro congelado**.

### `kappa` (OI provisional) solo con R² > 0.3
Se publica **solo** si una regresion semanal del `dOI` de la mañana siguiente sobre el volumen por
strike del dia previo da **R² > 0.3** para ese `(sym, dte ≥ 1)`. Si no, `kappa = null` y queda el
z-score crudo. Nunca un `kappa` de conveniencia.

### Estado operativo
**5 syms (QQQ SPY SMH NVDA MU), `weight=0` en `direction_view`, BANNER SOLAMENTE, sin voz.**
Hipotesis bajo test: *"el muro en el camino esta siendo COMIDO (`turn > 1.25` y subiendo) ⇒ el
prior de fade en el primer toque queda SUSPENDIDO y la ruptura esta permitida."*
Nada actua sobre esto, nada habla, y **no puede reemplazar a `captain_flow`** antes de que
`null-control` lo apruebe (ver [[measured-probability]]).

## 5. `skew-lead` — contexto diario, jamas gatillo

```
rr = iv_25p − iv_25c      drr_1d      z contra sus propias 60 sesiones previas
```
`z` es **NULL hasta `n ≥ 60`**, y ese NULL **se muestra, no se rellena**. Si `z` es NULL, la linea
se **OMITE por completo**.

RR intradia **SOLO** para los 4 syms ensanchados y **solo cuando el contrato de `|delta| = 0.25`
esta realmente DENTRO de la banda traida**; si no `extrapolated=1` y el valor se **suprime**.
Y la IV del snapshot de Polygon **JAMAS se mezcla en una serie con `modelGreeks.impliedVol` de
IBKR** (ver [[chain-data-contract]]).

| Lectura | Que refuerza (nunca inicia) |
|---|---|
`z(drr) > 2` con el sym **encima de su call wall** | una decision de **fade / cobrar** YA TOMADA sobre precio y gamma. Los puts se estan pujando → la ballena-CALLS es TECHO local, no continuacion (regla 11) |
`z(drr) < −2` **debajo del put wall** | la lectura de **suelo** del call-scalp espada-ballena |

**SIN voz, SIN factor en `direction_view`.** El soporte publicado (skew de Xing-Zhang-Zhao, vol
spread de Cremers-Weinbaum) es **TRANSVERSAL a horizontes SEMANALES**, no un lead intradia de 10
minutos. Veredicto HOY: **DATA-INSUFFICIENT, y la feature lo dice en voz alta.** Revisita en 2027
con un año de `iv_hist`.

## 6. HIRO: NO es un problema de autorizacion (resuelto en diagnostico 2026-07-25)

Spec completa: **`docs/HIRO-2026-07-25.md`**. Resumen operativo:

**El 403 se RODEA, no se arregla.** Subir a Options Advanced (~$199/mes) es **gasto duplicado**:
ya pagamos IBKR por los mismos prints de OPRA, y REST paginado seria **mas lento** que el socket
local de TWS que ya esta conectado (retraso = dinero).

**La cinta firmada YA CORRE en esta cuenta, para acciones** — `scripts/ibkr_bar_bridge.py:250`:
```python
tbt = ib.reqTickByTickData(smart, "AllLast", 0, False)   # y make_on_whale() la firma:
#   px >= ask -> +1 (cliente compra) | px <= bid -> -1 (cliente vende) | en medio -> 0, descartado
```
`ib_insync` acepta `'Last'|'AllLast'|'BidAsk'|'MidPoint'` sobre **cualquier `Contract`**, incluido
`Option`. **HIRO = ese motor apuntado a contratos de opcion, ponderado por delta.**
Nota: `opt_whale_watch.py` **no** hace esto — lee VOLUMEN acumulado con `reqMktData` (ratio P/C,
agregado bilateral).

> ### ⛔ ACTUALIZACIÓN 2026-07-28 — ESTA VÍA ESTÁ MUERTA, YA SE INTENTÓ Y SE MIDIÓ
> `reqTickByTickData(..., "AllLast")` sobre contratos de OPCIÓN devuelve **error 10189 en 20/20
> contratos de QQQ** ("tick-by-tick requests are not supported for this contract"). Evidencia:
> `Done.md:437` y `docs/HIRO-2026-07-25.md:215`. **HIRO no es construible aquí**: ni por Polygon
> (403 en `/v3/trades` y `/v3/quotes` de opciones) ni por IBKR (10189). No vuelvas a diseñarlo.
> Lo que SÍ da flujo firmado son las **flow-alerts de Unusual Whales** (`Done.md:759`: "hiro_pulse
> SUPERADO por la cinta UW"). El párrafo de arriba se conserva porque el ÁLGEBRA del hedge_flow
> sigue siendo correcta — lo que no existe es la fuente de prints firmados de opciones.

### Del print firmado al flujo de cobertura
```
hedge_flow = aggr · leg · |delta| · size · 100 · spot        aggr=±1   leg=+1 CALL / −1 PUT
```
| Print del cliente | Dealer queda | Cubre | Signo |
|---|---|---|---|
compra CALL | corto call | **COMPRA** subyacente | **+** |
vende PUT | largo put | **COMPRA** | **+** |
vende CALL / compra PUT | — | VENDE | **−** |

Delta **al print**: `bs_delta` con nuestra IV + el spot vivo de `nbbo_<sym>.txt` (4/s), **jamas** el
delta de la cadena de hace 180 s.

### El recurso escaso es el CAP, y hoy esta MAL REPARTIDO (bug vivo)
IBKR capea las suscripciones tick-by-tick (**err 10190**) y el bridge las reparte *por orden de la
lista*. Medido en `data/whale_*.txt`: **`whale_qqq.txt` y `whale_spy.txt` son 0 BYTES** — los dos
capitanes sin cinta firmada, junto a aapl/amd/asml/gld/intc/tsm/txn (**8 de 14 vacios**), mientras
DRAM y SPCX si la tienen. **La regla 12 corre sin su input firmado.** Arreglo: prioridad
QQQ→SPY→SMH + cobertura publicada. HIRO competiria por **ese mismo cap**.

### Las tres pre-puertas duras (cualquiera mata la feature antes de escribir C++)
1. `unsigned_pct > 35%` → son prints de **combo** (verticales/condores/rollos se reportan por patas
   dentro del NBBO y no son direccionales). **KILL.**
2. Cap medido **< 10** contratos simultaneos → la banda es demasiado fina para ser un indice. **KILL.**
3. `|ρ| > 0.9` con el `dvol` ponderado por gamma **sin signo** de §4 → la cinta no añade nada sobre
   el volumen. **KILL** (colinealidad primero, no edge — [[anti-overfit-killlist]]).

### Lo que sigue prohibido decir aunque funcione
- **Apertura vs cierre es invisible** → se afirma *"flujo agresor ponderado por delta"*, **nunca
  "posicionamiento de dealers"**. SpotGamma tiene el mismo agujero.
- Con ±5 strikes de un expiry el agregado **no es** el HIRO del ticker: es `hiro_band`, con la banda
  en la cabecera, y **jamas se compara entre dias con bandas distintas**.
- Embarca **mudo, `weight=0`, banner** (ver [[alert-budget]]).

**Siguiente paso bloqueante**: correr el probe con TWS vivo y mercado abierto (mide si `AllLast`
sobre opcion esta permitido, **el cap real**, prints/min y el coste del `BidAsk`).
Sin ese numero, todo lo demas es especulacion.

## 7. Que se puede decir en voz alta hoy

| Se PUEDE decir | **NO se puede decir** |
|---|---|
"volumen ponderado por gamma z=+2.1 en la banda 690-695" | "entraron $40M de delta comprado" |
"turnover 1.4× el OI en el strike del muro" | "los dealers estan cortos gamma ahi" |
"el flujo del capitan es puts-dominante 3× su EMA" ([[flow-captains]]) | "flujo FIRMADO de puts" |
"RR subiendo z=2.3: los puts se estan pujando" | "los institucionales compran proteccion" |
"OI congelado de cierre previo — el mapa es de ayer" | "el posicionamiento esta llegando" |

La columna derecha es el catalogo completo de lo que suena profesional y es inventado.
Ver [[anti-overfit-killlist]].

**SEÑAL-SOLAMENTE.**
