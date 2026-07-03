# Order Flow Footprint — Bid × Ask realtime

Implementación de las referencias `~/Desktop/delta0.png`, `delta1.png`, `delta3.png` y
`delta5.png`. Es **señal-solamente** y no comparte semántica con
`data/delta_imbalance.json`, que mide delta de opciones de Unusual Whales.

## Dos instrumentos, dos cintas

El selector del cockpit separa físicamente **ACCIONES** y **PERP 24/7**. Nunca combina
ambas cintas ni presenta un perpetuo tokenizado como si fuera la acción US.

| modo | instrumento | fuente | lado agresor | estado actual |
|---|---|---|---|---|
| ACCIONES | acción/ETF US | Massive SIP trades + NBBO | inferido: quote rule ≤2 s, luego tick rule | preparado, fail-closed: la key actual no incluye WebSocket realtime |
| PERP 24/7 | perpetuo tokenizado `SYMUSDT` | OKX/Bybit | nativo del venue | activo; proxy descriptivo, **no es la acción** |
| IBKR | acción/ETF US | AllLast + NBBO | inferido y auditable | implementación conservada, apagada hasta que Yunior rehabilite IBKR |

OHLCV, Finnhub sin NBBO, Intrinio delayed y snapshots REST no se transforman en una
footprint plausible. Sin trades+quotes realtime, ACCIONES publica `NO_TAPE` con la causa.

## Contrato normalizado

`scripts/equity_footprint_ws.py` normaliza Massive a:

```text
data/equity_footprint_tape/footprint_tape_<sym>.txt
EPOCH PRICE SIZE DIR BID ASK METHOD
```

`DIR=+1` es compra agresiva, `-1` venta agresiva y `0` indeterminada. `METHOD=Q/T/U`
permite auditar quote rule, tick rule y desconocido; un desconocido nunca se reparte entre
Bid y Ask. Trades delayed (>10 s), quotes posteriores al trade, duplicados y quotes con más
de 2 s se rechazan o quedan desconocidos.

`scripts/perp_ws_bridge.py` guarda la cinta cruda firmada por el venue en
`data/perp_tape/YYYY-MM-DD/<sym>.txt`. El motor la ingiere con `--format perp`, conserva
`side_provenance=NATIVE` y publica `instrument_kind=TOKENIZED_STOCK_PERPETUAL` más
`proxy_for=<SYM>`.

## Motor C++

`scripts/orderflow_footprint.cpp` se compila C++23/O3 y acepta dos formatos:

```bash
zsh scripts/build_orderflow_footprint.sh

# Acción US: cinta normalizada trade+NBBO
bin/orderflow_footprint --format normalized \
  --dir data/equity_footprint_tape --out-dir data --loop 250 \
  --source "Massive consolidated SIP trades+NBBO realtime" \
  --quality FULL_SIP_INFERRED_SIDE

# Perpetuo tokenizado: lado nativo del venue
bin/orderflow_footprint --format perp --dir data/perp_tape --out-dir data \
  --sym-suffix USDT --instrument-kind TOKENIZED_STOCK_PERPETUAL \
  --source "OKX/Bybit tokenized-stock perpetual signed tape" \
  --quality VENUE_NATIVE_SIDE_THIN_PERP --loop 250
```

La salida atómica `data/footprint_<sym>.json` contiene 1m/5m/15m/30m, celdas por
precio, Bid, Ask, volumen desconocido, delta, CVD diario, POC, procedencia del lado y
porcentajes native/quote/tick/unknown. Al rotar el día, el lector de perps toma el fichero
fechado más nuevo sin perder las barras que ya mantiene en memoria.

## Patrones delta0 / delta1 / delta3 / delta5

- **Absorption (`delta0`)**: Bid y Ask de la misma celda superan percentiles adaptativos,
  el total es anómalo, aparece en el extremo y el precio deja de progresar.
- **Delta flip/divergence (`delta1`)**: vela alcista con delta negativo o vela bajista con
  delta positivo; también compara cambio de precio y cambio de delta a tres footprints.
- **Stacked imbalance (`delta3`)**: comparación diagonal 300%; Ask[p] contra Bid[p−tick]
  o Bid[p] contra Ask[p+tick], con piso adaptativo y al menos tres filas adyacentes.
- **Multiple HVN (`delta5`)**: POC alineado en dos footprints cerradas = Double HVN; en
  tres = Triple HVN.

Todo patrón mutable lleva `FORMING`; al cerrar la footprint cambia a `BAR_CLOSED`.
`evidence_score` describe la fuerza visual de la evidencia, **no probabilidad de ganar**.
La doctrina sigue siendo `DESCRIPTIVE_UNPROVEN_SIGNAL_ONLY` hasta validación OOS.

## UI y estados operativos

En **ƒ Indicadores → Order Flow · Bid × Ask** hay selector ACCIONES/PERP 24/7,
temporalidad independiente, vista HUELLA o DIVIDIR, Bid/Ask legible, POC/HVN, geometría de
patrones, inspector, tooltips y control de densidad con Ctrl/Cmd + rueda.

La cabecera muestra proveedor, instrumento, procedencia del lado, edad y clasificación.
En PERP siempre añade `PROXY ≠ ACCIÓN`. Estados `NO_TAPE`, `STALE`, `QUIET`, `BROKEN` y
`LOW_CLASSIFICATION` son visibles; `QUIET` significa socket PERP vivo sin una impresión
reciente, no caída del feed.

## Activación de ACCIONES (cuando exista entitlement)

La implementación está lista, pero no debe habilitarse con el plan Massive actual: la sonda
real devolvió `Your plan doesn't include websocket access`. Tras adquirir un feed realtime
consolidado trades+NBBO y verificarlo:

```bash
echo massive > data/footprint_equity_source.txt
zsh scripts/fleet_keepalive_start.sh
```

Para apagarlo: eliminar el fichero o escribir `off`. No se compra ni cambia un plan desde el
software. Databento queda soportado por el contrato normalizado, pero la key actual tampoco
tiene licencia live; Intrinio/Finnhub no cumplen la cinta necesaria.

## Verificación

```bash
zsh scripts/build_orderflow_footprint.sh
./venv/bin/python -m pytest tests/test_orderflow_footprint.py \
  tests/test_orderflow_frame.py tests/test_equity_footprint_ws.py \
  tests/test_whale_tape.py tests/test_indicator_menu.py -q
node --check charts/orderflow_panel.js
./venv-chart/bin/python scripts/chart_bridge.py --selftest --sym qqq
```

Las reglas se contrastaron con las referencias de Trader Dale: 300% diagonal, stack de tres,
POC/HVN y agregación por tick. La implementación conserva sus parámetros como reglas
descriptivas; no atribuye un win rate que no se haya medido.
