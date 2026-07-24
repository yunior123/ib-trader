# order_engine — ejecución de opciones vía TWS (C++23)

Motor headless que ejecuta **under-the-ground** las zonas que Yunior pinta en el
gráfico (`data/exec_zones_<sym>.json`). Único módulo de la flota autorizado a
colocar/cancelar/modificar órdenes (ley `AGENTS.md` #0 enmendada 2026-07-24).
La flota sigue **SEÑAL-SOLAMENTE**; aquí manda la **doble llave**.

Spec completa: `order_engine/docs/ORDER-ENGINE.md`. Recetas TWS: `.claude/skills/ibkr-tws`.

## Archivos
- `tws_adapter.h/.cpp` — `TwsAdapter : DefaultEWrapper`. Conexión, place/cancel/modify, stops nativos, reconciliación, callbacks (orderStatus/execDetails/commissionReport/error/connectionClosed), cola de `ExecReport`.
- `ledger.h` — JSONL append-only en `ledger/orders.jsonl` (intent/ack/fill/cancel/reject/commission). P&L neto por `execId`→commission.
- `safety.h` — doble llave (`--arm-live` + `ARM_LIVE`=hoy) y disarm-on-exit (SIGINT/SIGTERM/crash/atexit → `cancel_all_own` + flush).
- `order_engine.cpp` — main: zone-watcher, gate (spread≤5%, OI>500, prima≤budget, cadena fresca), FSM PLACED→TRIGGERED→SENT→FILLED→STOP_HIT, estado a `state/<sym>.jsonl`.
- `build.sh` — 2 compilaciones secuenciales, **comentadas** (las corre el orquestador; Mac 8GB).

## Build
Prerequisito: `libbid` (Intel Decimal FP) en `scalper/vendor/lib/` — ver skill `ibkr-tws`.
```bash
# desde la raíz del repo (ib-trader/):
bash order_engine/build.sh      # imprime los pasos; descomentar y correr uno a uno
```
Salida: binario `order_engine/order_engine`. Runtime lib fallback:
`export DYLD_LIBRARY_PATH=$PWD/scalper/vendor/lib`.

## Smoke test en PAPER (7497) — DRY por defecto
1. TWS/IB Gateway arriba, **API on**, puerto 7497 (paper `DUR197573`), clientId 92 libre.
2. `opt_chain_cache` y los bridges de barras vivos (`data/opt_chain_<sym>.txt`, `data/bars_<sym>_ibkr.txt` frescos).
3. Correr desde la raíz del repo:
```bash
./order_engine/order_engine --paper --sym QQQ --sym NVDA --budget 200 --repo .
```
Sin `--arm-live` **y** sin `ARM_LIVE` → **DRY**: registra en el ledger la orden que
colocaría (`"mode":"DRY..."`) y NO llama a `placeOrder`. Pinta una zona con
`"exec": true` y `"armed_date"` de hoy; al imprimir el nivel verás el DRY-log.

Para probar el camino de colocación real **en paper** (órdenes reales pero cuenta
de práctica), armar como abajo apuntando a 7497.

## Armar LIVE (7496) — SÓLO tras F1–F3 verdes en paper
Doble llave (ambas obligatorias):
```bash
# 1) archivo con la fecha de HOY (YYYY-MM-DD), sin nada más:
date +%F > order_engine/ARM_LIVE
# 2) flag en la línea de comando + puerto live:
./order_engine/order_engine --live --arm-live --sym QQQ --budget 200 --repo .
```
Sin cualquiera de las dos → DRY. El archivo caduca solo: si su fecha no es hoy,
`armed_live()` devuelve falso. Las zonas también exigen `armed_date == hoy`.

## Desarmar
- **Borrar la llave**: `rm order_engine/ARM_LIVE` → las próximas entradas caen a DRY al instante (se re-evalúa por entrada).
- **Parar el proceso**: `Ctrl-C` (SIGINT) o `kill` (SIGTERM) → `cancel_all_own()` cancela TODAS nuestras órdenes vivas (entries en vuelo + stops nativos, orderRef `OE:`) y flushea el ledger ANTES de morir. En crash (SIGSEGV/ABRT) hay un intento best-effort; la red REAL es que los stops son nativos y las entradas jamás descansan.
- Al arrancar, `reqAllOpenOrders` reconcilia y cancela cualquier huérfana `OE:` de un run previo.

## Contrato de datos (gráfico → motor)
`data/exec_zones_<sym>.json` (ver spec §3):
```json
[{ "id":"z1", "price":205.0, "side":"buy", "kind":"call", "exp":"20260815",
   "qty":1, "exec":true, "stop":{"on":true,"px":201.0,"native":true},
   "armed_date":"2026-07-24" }]
```
- `exec:false` → **ficha-only** (ignorada aquí; la maneja `chart_bridge.py`).
- `stop.native:true` → STP server-side (sobrevive al crash); el nivel del
  subyacente se mapea a precio de la opción vía delta de la cadena (aproximación
  documentada). `native:false` → watch-local: al imprimir `stop.px` en el
  subyacente, cierra marketable.

## Salidas
- `order_engine/ledger/orders.jsonl` — auditoría + P&L neto (broker).
- `order_engine/state/<sym>.jsonl` — estados por zona (PLACED/TRIGGERED/SENT/FILLED/STOP_HIT/VETOED/…) que `chart_bridge.py` relaya al chart.

## Checklist antes de cada sesión con órdenes
1. TWS arriba, API on, puerto correcto (7497 paper / 7496 live).
2. `ARM_LIVE` con fecha de hoy (sólo live).
3. clientId 92 libre.
4. `opt_chain_<sym>.txt` y `bars_<sym>_ibkr.txt` frescos (<15 min).
5. Al salir: ledger sin órdenes propias abiertas (confirmar cancel-all).
