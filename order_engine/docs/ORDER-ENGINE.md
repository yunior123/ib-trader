# ORDER-ENGINE — ejecución de opciones vía TWS (C++23)

> **Ley:** AGENTS.md orden #0 (enmendada 2026-07-24). La flota sigue SEÑAL-SOLAMENTE por
> defecto; **este módulo es el ÚNICO autorizado a colocar/modificar/cancelar órdenes**, y solo
> con doble llave, paper primero y disarm-on-exit. Conexión: skill `.claude/skills/ibkr-tws`.

Pedido de Yunior (2026-07-24): *"bot que coloque órdenes a TWS, con cancel/modify/buy/sell, para
TODAS las opciones (no solo 0DTE), C++ preferido. Coloco zonas de compra/venta en el gráfico como
las alarmas; al alcanzar la zona el bot ejecuta under-the-ground. Simple para calls y puts, ver
precios + poder elegir la fecha (expiry). A la derecha del icono buy, la probabilidad de profit
(muros/imanes/GEX/gamma-flip + técnicos + trading-agents + critic). Stop-loss por defecto,
activable/desactivable y arrastrable en el gráfico, para operar seguro."*

---

## 0. Principio rector

**El gráfico es el mando; el motor es invisible.** Yunior pinta una zona (precio + call/put +
expiry) igual que pinta una alarma. El motor la vigila LOCAL y, cuando el precio IMPRIME el nivel
(2 lecturas, PRINT-O-NADA), coloca la orden de la opción en TWS "under the ground". Nada descansa
en el servidor salvo los stops protectivos — y esos SIEMPRE están en el set de cancel-all. Entre
sirena de entrada y de salida, el P&L no se mira (regla #10 de la casa).

## 1. Qué ya existe (reusar, no duplicar)

| Pieza | Estado | Rol en el motor |
|---|---|---|
| `charts/live.html` botón **🎯 Zona** | vivo | UI: clic en precio → elige buy/sell · call/put. **Añadir selector de expiry.** |
| `data/exec_zones_<sym>.json` `[{id,price,side,kind}]` | vivo | **Contrato de datos gráfico→motor.** Añadir `exp`, `exec`, `qty`, `stop`. |
| `scripts/chart_bridge.py` `check_zone_crossings()` | vivo | Detecta cruce de spot; hoy emite FICHA. Sigue mostrando ficha; **ya NO ejecuta**. |
| `scripts/order_ticket.py` `build()` | vivo | Arma contrato+límite+size+spread+OI+prob (GO/CAUTION/NO-GO). Fuente de la ficha y del gate. |
| `scalper/exec_adapter.h` `ExecutionAdapter` + `TwsAdapter` (STUB) | seam listo | **Interfaz de ejecución compartida.** El motor RELLENA el TwsAdapter. |
| `scalper/vendor/IBJts/` (a vendorear) | pendiente | TWS C++ API oficial + `libbid`/`libTwsSocketClient` (skill ibkr-tws). |
| `scripts/cancel_all_bot_orders.py` (7496, clientId 87) | vivo | Referencia del disarm; el motor trae su PROPIO cancel-all C++. |
| `data/opt_chain_<sym>.txt` (opt_chain_cache, clientId 48) | vivo | Cadena ±6% ATM: strikes/bid/ask/oi/iv/delta para elegir contrato y gate. |
| gex_core / `gamma-regime-walls` / `direction_view` / TradingAgents / critic | vivos | Insumos del **overlay de probabilidad** (§5). |

## 2. Arquitectura

```
  ┌──────────────┐   exec_zones_<sym>.json     ┌────────────────────────────┐
  │  chart UI     │  {price,side,kind,exp,      │   order_engine (C++23)      │
  │  live.html    │──  exec,qty,stop} ────────▶ │                            │
  │  🎯 Zona +stop│                             │  zone_watcher ─► gate ─► TwsAdapter ─► TWS
  └──────────────┘                             │        ▲              (EClient/EWrapper) │
        ▲  overlay prob (WS)                    │        │ NBBO (archivos flota, NO por    │
        │                                        │        │ la conexión de órdenes: pacing) │
  ┌──────────────┐  order_status/fills (WS)      │   ledger (jsonl) ─► P&L neto por execId │
  │ chart_bridge  │◀──────────────────────────── │   ARM_LIVE + --arm-live (doble llave)   │
  │ (Python, WS)  │                              │   disarm-on-exit (cancel-all propio)    │
  └──────────────┘                              └────────────────────────────┘
```

- **El motor es headless C++.** No abre sockets al navegador; publica su estado por archivos
  (`order_engine/state/*.jsonl`) que `chart_bridge` relaya al chart por su WS ya existente.
- **NBBO del subyacente** para el trigger sale de los archivos de la flota (`bars_<sym>_ibkr.txt`
  / bridges), NUNCA por la conexión de órdenes — regla de pacing (≤50 msg/s) del skill ibkr-tws.
- **NBBO de la opción** (para el límite marketable) sale de `data/opt_chain_<sym>.txt` (cache, ya
  realtime), no de la conexión de órdenes.

## 3. Contrato de datos — `exec_zones_<sym>.json` (extendido)

```jsonc
[{
  "id": "z_...",          // estable
  "price": 205.0,          // nivel del SUBYACENTE que dispara
  "side": "buy",           // buy | sell   (sell = cerrar/abrir corto de la opción)
  "kind": "call",          // call | put
  "exp":  "20260815",      // expiry ELEGIDA en el chart (no solo 0DTE)   ← NUEVO
  "qty":  1,                // contratos (default por presupuesto ≤$200)  ← NUEVO
  "exec": false,           // false = FICHA-only (señal); true = EJECUTAR  ← NUEVO/CANDADO
  "stop": {"on": true, "px": 201.0, "native": true},  // stop-loss movible  ← NUEVO
  "armed_date": "2026-07-24"   // caduca fin de día salvo re-arme          ← NUEVO
}]
```

**Doble candado de seguridad:** una zona con `exec:true` SOLO ejecuta si además el proceso corre
con `--arm-live` Y existe `order_engine/ARM_LIVE` con la fecha de hoy. Sin eso → DRY (registra la
orden que colocaría). Una zona `exec:false` es idéntica al comportamiento actual (ficha para el
humano). Así "señal-solamente" sigue siendo el default incluso dentro del sistema de zonas.

## 4. Máquina de estados por zona

```
 PLACED ─(spot imprime nivel, 2 lecturas)─► TRIGGERED ─(gate OK)─► SENT ─(orderStatus)─►
        │                                              │(gate NO-GO)     │
        └─ zona movida/borrada ─► PLACED               └─► VETOED(log)   ├─ FILLED ─► (stop nativo armado si stop.on)
                                                                          ├─ CANCELED
                                                                          └─ REJECTED(log, no reintento ciego)
 FILLED ─(stop.px impreso)─► STOP_HIT ─► SELL (cierre)      // stop = watch local + red nativa
```

- **Gate (reusa order_ticket + gex):** spread ≤ 5%, OI > 500, premium ≤ cap ($200 default),
  contrato existe en la cadena, expiry válida, NBBO fresco (<15 min). Falla cualquiera → VETOED.
- **Modify = `placeOrder` con el MISMO orderId** (cancel/replace nativo). **Cancel = `cancelOrder`.**
- **connectionClosed / 1100:** congelar entradas, marcar estado, cancelar locales, reconectar backoff.

## 5. Overlay de probabilidad (a la derecha del icono buy)

`prob_profit(sym, level, side, kind, exp)` — compone (todo ya medido/vivo, degradación limpia):

1. **Estructura gamma** (`gex_core` + skill `gamma-regime-walls`): ¿el nivel va HACIA un imán/oro
   o choca un muro? régimen (POS pin / NEG whipsaw); distancia a call/put wall y a gamma-flip.
2. **Flujo** (`direction_view` + captains spike-flow): flecha compuesta flip+muros+GEX+flota+momentum.
3. **Técnicos** (`signal_conditioning`): prob condicionada hora×flota×inflación×componentes-QQQ.
4. **Trading-agents** (repo TradingAgents) + **critic**: veredicto bull/bear + opinión crítica corta.

Salida: `{ prob: 0..100, verdict: GO|CAUTION|NO-GO, why: [...], regime, magnet, walls }` — mostrado
como chip a la derecha del botón buy. **Honesto:** si el mapa es todo-acelerador NEG sin imán oro,
NO da dirección → "whipsaw, sin lado limpio" (lección post-mortem QQQ 2026-07-24).

## 6. Stop-loss (default-ON, toggle, arrastrable)

- Por defecto se propone un stop (`stop.on:true`) al pintar una zona buy; Yunior lo mueve
  arrastrándolo en el chart (actualiza `stop.px` en el json) o lo apaga (`stop.on:false`).
- **Nativo server-side** (`native:true`, default): sobrevive a un crash del motor = protección real
  aunque el proceso muera. **PERO** todo stop nativo se registra en el ledger y entra SIEMPRE en el
  set de `disarm/cancel-all` → jamás queda huérfano al desarmar (la lección del desastre 2026-07-16).
- Opción `native:false`: stop watch-local (no toca servidor; sin protección si el motor muere).

## 7. Seguridad (no negociable — resumen operativo)

- **Doble llave**: `--arm-live` + `order_engine/ARM_LIVE`(fecha hoy). Falta una → DRY/SIM.
- **Paper primero**: 7497 (DUR197573) hasta probar buy/sell/cancel/modify + cleanup; luego 7496.
- **Disarm-on-exit**: SIGINT/SIGTERM/crash/connectionClosed → cancel-all propio + freeze. Handler
  registrado ANTES de la primera orden. Al arrancar: reconciliar con `reqOpenOrders` y adoptar/cancelar.
- **clientId dedicado** = **92** (libres: 48 chain, 82 whale, 83/84 bars, 87 walls, 90 scalper, 91 ref py).
- **Topes duros**: premium ≤ cap, spread ≤ 5%, OI > 500, band de precio IBKR (~10%, rechazo 202).
- **Ledger** `order_engine/ledger/orders.jsonl`: cada intent/ack/fill/cancel/commission por execId
  → P&L NETO exacto (manda `execDetails`/`commissionReport`, no nuestro reloj).

## 8. Fases (aditivas, cada una compila y corre sola)

- **F0 — vendoring/build** *(task #3)*: TWS C++ API + `libbid` + `libTwsSocketClient` (skill ibkr-tws). 8GB → secuencial.
- **F1 — núcleo paper** *(task #4)*: TwsAdapter real; connect 7497 clientId 92; nextValidId;
  place/cancel/modify de UNA opción; callbacks orderStatus/execDetails/commissionReport/error/
  connectionClosed; doble llave + DRY default + disarm-on-exit; ledger. CLI de prueba manual.
- **F2 — zone watcher** *(task #5)*: leer `exec_zones_<sym>.json` (+`exp`); NBBO flota; PRINT 2-lecturas;
  gate (order_ticket); disparo under-the-ground; expiry selector en el chart; calls y puts.
- **F3 — stop movible + overlay prob** *(task #6)*: stop nativo en cancel-all + arrastrable; chip de
  probabilidad a la derecha del buy (gex/direction_view/trading-agents/critic).
- **F4 — armar LIVE**: tras F1–F3 verdes en paper, `ARM_LIVE`+`--arm-live` sobre 7496 con topes.

## 9. Estado de arranque (checklist antes de cada sesión con órdenes)

1. TWS/IB Gateway arriba, API on, puerto correcto (7497 paper / 7496 live).
2. `order_engine/ARM_LIVE` presente y con fecha de HOY (solo para live).
3. clientId 92 libre (no hay otra conexión viva con él).
4. opt_chain_cache y los bridges de NBBO vivos (el trigger depende de datos frescos).
5. Al salir: confirmar cancel-all (ledger sin órdenes abiertas propias).
