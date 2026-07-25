# CHAIN-HEADER — contrato de la cabecera de `data/opt_chain_<sym>.txt`

Feature minada **#5 `chain-honesty`** (2026-07-25). Este fichero es el CONTRATO: quien lo
rompa rompe `scripts/opt_quick.cpp` (el lector mas rapido de la flota, parseo POSICIONAL) y
`scripts/gex_core.py:parse_chain_header`.

## Formato

```
# opt_chain NVDA | epoch 1784298180 | 2026-07-17 10:03:00 | spot 208.35 | exps 20260717 20260724
# fuente ibkr_tws | band 0.0600 | max_strikes 20 | narrow 0 | vencimientos 2 | rows 80 | greeks_ok_pct 1.0000 | bidask_ok_pct 1.0000
# strike right exp bid ask vol oi iv delta gamma
207.50 C 20260717 1.23 1.27 15234 8211 0.4310 0.5512 0.0410
```

- **Linea 1** (histórica, `opt_chain_cache.py` / `poly_chain_archive.py`): `epoch`, sello
  local, `spot`, `exps`.
- **Linea 2** (nueva): procedencia y forma del fetcher. La escribe `opt_chain_cache.py`;
  `poly_chain_archive.py` escribe su propia version con `fuente polygon_snapshot_v3`.
- **Linea 3**: nombres de columna. **Las columnas por fila JAMAS se reordenan.**
- Filas: 10 campos separados por espacios. `-1` = **no lo se** (nunca 0).

## Reglas duras

1. **Append-only.** Se AÑADEN campos al final de una linea `#`; no se renombran ni se quitan.
2. **La linea 1 no se toca.** `opt_quick.cpp` busca `"epoch "`, `"spot "` y `"exps "` por
   SUBSTRING en *cualquier* linea `#`. Por eso ningun campo nuevo puede contener esos
   substrings: el primer intento uso `n_exps 2` y `opt_quick` empezo a imprimir
   `exps 2` en vez de los vencimientos (cazado en test, 2026-07-25). Se llama
   `vencimientos`, no `n_exps`.
3. Toda linea que empiece por `#` se salta al parsear filas.
4. `greeks_ok_pct` y `bidask_ok_pct` son **fracciones 0..1** sobre las filas escritas.

## Campos de la linea 2

| campo | significado |
|---|---|
| `fuente` | `ibkr_tws` \| `polygon_snapshot_v3` — de donde salieron las griegas |
| `band` | banda de strikes REAL usada por el fetcher (±fraccion del spot) |
| `max_strikes` | tope de strikes por vencimiento |
| `narrow` | 1 si el simbolo va en modo recortado (`NARROW` = MSFT, AVGO, AMZN, META) |
| `vencimientos` | cuantos vencimientos trae el fichero |
| `rows` | filas escritas |
| `greeks_ok_pct` | fraccion de filas con `iv > 0` |
| `bidask_ok_pct` | fraccion de filas con `bid > 0 y ask > 0` |

## Por que existe (medido, no supuesto)

`data/history/2026-07-24`, cache TWS:

| hora | QQQ filas | `iv>0` | `bid/ask>0` |
|---|---|---|---|
| 10:00 | 80 | **100%** | 100% |
| 12:00 | 80 | **100%** | 100% |
| 14:00 | 80 | **100%** | 100% |
| 15:30 | 80 | **100%** | 96% |
| 16:10 | 80 | **100%** | 82% |
| **16:16** (ultimo ciclo) | 80 | **0%** | **0%** |

En RTH las griegas estan completas. Tras el cierre TODA la flota queda a `iv=-1 delta=-1
gamma=-1` y `bid=-1 ask=-1`, y ese es el fichero que leen **los planes de las 04:00** y todo
lo que corra el fin de semana. Antes de esta feature ese caso caia en un `iv=0.3` de relleno
dentro de `gex_core.from_ibkr_cache` y se publicaban muros, flip, regimen y presion como si
fueran medidos.

## Que hace ahora el consumidor (`gex_core.from_ibkr_cache`)

1. `iv <= 0` **y** `gamma <= 0` → se intenta **invertir la IV** del mid por biseccion
   (60 iteraciones, tol 1e-6, forward implicito por paridad put-call, `r=0.045`).
   **Solo si `bid > 0` y `ask > 0` y estamos en RTH**: a las 16:16 el mid vale -1 y una
   biseccion sobre ESE mid seria una mentira mas convincente que el bug que reemplaza.
2. Lo que no se pueda invertir se **EXCLUYE y se CUENTA**. No existe ningun default de IV.
3. `greeks_ok_pct < 0.5` (o cache TWS de mas de 45 min **en RTH** = daemon muerto) →
   `gamma_ok = false` y **todas** las claves gamma a `null`:
   `net_gex, regime, flip, call_wall, put_wall, abs_wall, pressure, em, iv_atm,
   gross_gex, hhi, bifurcation`. **Nunca 0.**
4. Los **muros por OI puro** (`oi_call_wall`, `oi_put_wall`) SI se publican: el OI es dato
   real y no necesita griegas. Es lo unico que tienen NOK, DRAM, SPCX y SKHY.
5. Fuera de RTH no hay cadena mas fresca posible, asi que el libro del cierre anterior **no
   es "rancio"**: se declara `quotes_ok=false` / `session=fuera_de_rth` y quien decide si hay
   voz gamma es `greeks_ok_pct`, que es medible, no el reloj.

## Respaldo con griegas MEDIDAS

`scripts/chart_levels.py` reintenta con `data/history/<hoy>/poly_chain_<sym>_<HHMM>.txt`
(snapshot `/v3/snapshot/options` de Polygon) cuando el cache TWS no tiene griegas usables.
Verificado 2026-07-25: QQQ 854 contratos, 816 con griegas (95.5%), 706 con OI. Solo se acepta
el respaldo si resulta MEJOR — nunca se cambia una fuente buena por otra.
