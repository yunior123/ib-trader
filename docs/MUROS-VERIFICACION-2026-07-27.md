# Muros: verificación contra 3 referees (2026-07-27)

Cierra `"make sure the walls are ok, no excuses, verify and try in depth… plus explore and call
polygon and others"` (Yunior 2026-07-25) y `"elige ibkr real, polygon only fallback for realtime
market"` (2026-07-27).

**Veredicto: los MUROS sí. El NETO/RÉGIMEN no lo estaba — la gamma de Polygon viola la paridad
put-call — y ahora lleva guardián.** Los dos arreglos anteriores (`cf0baaf` T real, `5a6a34e`
banda adaptativa) siguen en pie, verificados en el DATO.

## 1. Los dos arreglos, medidos en el dato (no en el código)

`band_used` símbolo a símbolo, corrida en vivo el 27 a las 08:2x:

| | resultado |
|---|---|
| `band_fetch` (banda de la cabecera) poblada | **35/35** |
| `band_used == band_fetch` | **35/35** (0,18 · 0,27 · 0,405 · 0,6 según símbolo) |
| `T` real por contrato | 35/35 con `flip_src=repriced` salvo 2 (ver §3) |

El default prohibido `or 0.035` de `gex_core.from_ibkr_cache:908` **sí es alcanzable**: las
cadenas archivadas ANTES de `5a6a34e` no llevan el token `band`, y 19 de 30
`charts/data/levels_*.json` estaban servidas con `band_used=0.035` y spot del 25 porque nadie
regenera los símbolos sin puente. Regenerados los 30 (`chart_levels.py`), band correcta en todos.

## 2. Nuestro vs CBOE vs Polygon vs UW — scope IGUALADO

Scope: `exp <= 2026-08-21` (mensual) **y** `|K−spot| <= banda·spot`. Escala $/1% con NUESTRO spot,
así la única diferencia es Σ±γ·OI.

| SYM | banda | NUESTRO | CBOE match | POLY match | CW n/cb/po | PW n/cb/po | flip n/cb/po |
|---|---|---|---|---|---|---|---|
| QQQ | 0,18 | −5,22 B | −4,69 B | −0,79 B | 700/700/700 | 680/680/680 | 709,97/701,71/695,18 |
| SPY | 0,18 | −9,29 B | −9,84 B | +2,62 B | 750/750/745 | 730/730/730 | 750,16/745,62/744,28 |
| NVDA | 0,405 | +0,18 B | +0,32 B | +0,47 B | 210/210/210 | 200/205/205 | 202,36/204,67/202,67 |
| MU | 0,6 | −0,20 B | −0,22 B | −0,12 B | 1000/1000/1000 | 800/800/800 | 991,28/978,38/974,74 |
| SMH | 0,405 | −0,83 B | −1,23 B | −0,92 B | 600/600/600 | 520/520/520 | 644,54/628,38/654,47 |
| TSLA | 0,6 | −0,006 B | +0,04 B | +0,11 B | 350/330/330 | 300/310/310 | 311,91/311,54/309,22 |
| AAPL | 0,27 | +0,47 B | +0,43 B | +0,49 B | 345/340/335 | 315/330/330 | 304,72/316,38/318,69 |
| SPX | 0,18 | −33,5 B | +9,17 B | sin griegas | 7500/7500/— | 7300/7400/— | 7485,85/7463,66/— |
| XSP | 0,18 | −0,71 B | −0,20 B | sin griegas | 757/745/— | 715/715/— | 760,79/761,55/— |

**Muros: 7/9 call_wall idéntico, 5/9 put_wall idéntico, el resto a 1 strike.** El flip dentro del
1-2% en los 6 primeros.

**La banda ya no trunca:** la corona fuera de nuestra banda aporta **0,03%–3,6%** de la gamma bruta
del referee (QQQ 0,21%, SPY 0,99%, NVDA 0,21%, SMH 0,03%, TSLA 3,6%). El "13×" está muerto.

**Por qué discrepan las magnitudes: AS-OF, no scope.** Nuestro archivo era del viernes 16:20 y el
referee se pidió el lunes tras un gap de +1,2%. Repreciando NUESTRO mismo libro por BS al spot vivo
de IBKR, converge hacia el referee en 4/6 (QQQ −5,22→−3,83 vs CBOE −4,69; NVDA +0,18→+0,25 vs
+0,32; MU −0,20→−0,14 vs −0,12). Prueba definitiva: con el archivo de HOY 08:27, nuestro
`gex_snapshot` reproduce el fetch crudo de Polygon **a 3 decimales** (QQQ −0,82 vs −0,793; SPY +2,29
vs +2,615; NVDA +0,47 vs +0,468). Mismo dato, mismo número.

**CBOE cambia el OI el fin de semana**: 4.343 de 8.512 contratos SPX con OI distinto entre el
viernes 16:20 y el lunes (liquidación OCC). Y sus griegas se actualizan mientras su
`current_price` no: latencia DESIGUAL medida a nivel de campo, no solo de fuente.

### UW como tercer referee (por PATA, scope declarado)
`scripts/uw_gex_compare.py`, 333 ficheros de `data/history/2026-07-26/uw_*.json`:
**30/30 símbolos**, ρ(call_gex) **+0,69…+0,97**, ρ(put_gex) **+0,71…+0,97**. El NETO no se compara
(UW trae el libro entero sin columna de expiry) y el script se niega a publicarlo.
Arreglado: UW manda `null` en la pata inexistente y `float(None)` tumbaba TSLA y GOOGL enteros.

## 3. El test del borde: el recorte ya no fabrica niveles

Distancia del flip al borde de su banda (35 símbolos, `data/gex_snapshot.json`):

```
[  0-  1) pp                       0        antes: 14 de 25 entre 3,7% y 4,6%
[  1-  2) pp                       0        min   13,76 pp
[  2-  5) pp                       0        mediana 39,08 pp
[  5- 10) pp                       0        max   59,55 pp
[ 10- 20) pp  ########             8
[ 20- 40) pp  ##########          10
[ 40-100) pp  #################   17
```

**En el camino VIVO quedaban 2 pegados al borde**: EWY flip 260,0 con spot 163,49 (0,97 pp del
borde) y SNDK 2300,0 con spot 1440,88 (0,38 pp). Causa: `gex_core._flip` devolvía el **extremo del
rango de strikes** cuando el perfil no cruza cero — el techo de nuestro recorte publicado como
"flip", y de ahí los tres `*_kind` = trampilla, que es VETO DURO. `gex_snapshot.honest_flip` ya lo
hacía bien; el original seguía vivo. Arreglado: **sin cruce = `None`**.

## 4. El defecto que no se había visto: la gamma de Polygon viola la paridad put-call

`gamma_call == gamma_put` al mismo (strike, expiry) es una **identidad**, no una convención.
Medido el 27 a las 08:45 sobre las cadenas de HOY:

| fuente | pares dentro del 5% | mediana γC/γP |
|---|---|---|
| Polygon premercado SPY | **2%** de 927 | **0,243** ← una call con 4× menos gamma que su put |
| Polygon premercado QQQ | 2% de 1.155 | 0,890 |
| Polygon viernes 16:20 | 34-36% | ~0,9 |
| **CBOE** | **72-78%** | **1,000** |

Consecuencia con dinero: **SPY publicaba `POSITIVE`** y las dos lecturas legales del mismo libro dan
**NEG** (−6,84 y −4,36 B), y CBOE −10,0 B. El signo crudo era el único positivo. **POS licencia el
fade; NEG lo PROHÍBE.**

Arreglo (`gex_core.regime_by_parity`, **una** definición para el lote y para el vivo): manda la
paridad cuando determina el signo; si las dos lecturas discrepan, `regime = None` + motivo. Hoy
corrigió el signo de **SPY, TSM, ASML y LRCX**, y dejó QCOM/DRAM/WDC sin régimen en vez de con uno
inventado. En libros coherentes (CBOE, Polygon al cierre) reparar no mueve el neto ni un 3%.

## 5. Fuente: IBKR PRIMARIO, Polygon RESPALDO

`gex_snapshot.pick_source()`. IBKR gana solo si su libro **da la talla en las dos cosas** que el mapa
necesita, con constantes YA medidas del repo (no se crea una quinta definición):

- griegas usables ≥ `book_quality.MIN_GREEKS_SRC` (0,50)
- ancho de strikes ≥ `poly_chain_archive.BAND_FLOOR` (0,10) — por debajo está MEDIDO que el flip lo
  fija el recorte (`5a6a34e`)

**El bloqueante, medido: el cache TWS es ±1,3%–7,1% de ancho, 20 strikes, 2 vencimientos**, donde la
gamma necesita ±18%–60%. Aunque sus griegas llegaran al 100%, no puede llevar el régimen sin
reabrir el bug del recorte. Para que "IBKR primario" muerda de verdad hay que ensanchar
`opt_chain_cache.py` (`max_strikes 20` → cubrir la banda adaptativa). La procedencia va DENTRO del
dato: `chain_src` + `source_why`.

## 6. La "contradicción de fuentes" era de SCOPE

`gex_snapshot` daba QQQ `NEGATIVE` y `chart_levels.gen('qqq')` `POS`. No eran dos fuentes: era
**0DTE contra el libro entero**, las dos etiquetadas `regime`. Con el guardián de paridad en los dos
caminos y el scope declarado (`gex_snapshot` publica ahora `scope: "ALL"`), **30/30 de la flota
coinciden a scope igualado**. Sin igualar el scope discrepan 6, y es correcto que discrepen.

## Lo que sigue abierto

- `opt_chain_cache.py` estrecho (§5) — es de otro agente.
- Polygon: paridad al 2% en premercado y 34% al cierre. El guardián salva el signo, no la magnitud.
  Para magnitud fiable la fuente es CBOE.
- SPX `POSITIVE` +7,7 B y XSP `NEGATIVE` −0,22 B el mismo día, los dos de CBOE al 100% de paridad:
  son libros distintos del mismo índice, no un bug, pero conviene no leerlos como uno.
- 21 de 30 `levels_*.json` sólo se refrescan a mano: nadie corre `chart_levels` para los símbolos
  sin puente (`fleet_consensus.cpp:41` ya lo advierte).
