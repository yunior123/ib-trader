---
name: ibkr-order-execution
description: Cómo colocar/modificar/cancelar órdenes REALES de opciones y acciones en la cuenta de Yunior vía IB Gateway (no el MCP), con todos los errores y gotchas medidos en vivo. Usar cuando Yunior pida comprar/vender/poner stop/take-profit/bracket en su cuenta.
---

# Ejecución de órdenes IBKR (aprendido en vivo 2026-07-31)

## Conexión — SIEMPRE por Gateway, NUNCA por el MCP
- El MCP `mcp__claude_ai_Interactive_Brokers_IBKR__*` apunta a la cuenta **VACÍA U26642820 ($15)**. Sirve solo para DATOS de mercado (precios/cadena). **JAMÁS ejecuta en la cuenta real.**
- Cuenta REAL de Yunior = **U26942420** (TFSA). Se opera por **IB Gateway local puerto 4001** (live). Ver [[read-real-account-via-gateway]].
- `~/ib-trader/venv/bin/python` tiene `ib_insync`. Conectar: `IB().connect("127.0.0.1",4001,clientId=<alto único>,readonly=False,timeout=20)`. `readonly=True` para leer; quitar solo para ejecutar. clientId alto no usado (la flota usa 41-91).

## GOTCHAS medidos (cada uno costó un rechazo real)
1. **Error 10311 / 10329 — ruteo directo bloqueado.** Rutear a un exchange concreto (NASDAQ, OVERNIGHT) da "direct routed order" + cancela. **Usar `exchange="SMART"` siempre** (crea `Stock("MUD","SMART","USD")` fresco; el contrato de la posición viene con `primaryExchange=NASDAQ` y hay que forzar SMART).
2. **Error 103 — ID de orden duplicado.** No se puede MODIFICAR una orden desde un `clientId` distinto al que la puso. Para cambiar precio/nivel: `reqGlobalCancel()` (si esas son las únicas abiertas) → esperar 3s → verificar `openOrders()` vacío → re-colocar. Reconectar con el mismo clientId también sirve.
3. **Error 201 — cash insuficiente.** Verificar BuyingPower ANTES: `{a.tag:a.value for a in ib.accountSummary() if a.account==ACCT}`. Opciones USD contra cuenta CAD → dividir CAD/~1.42 para USD. Un lote de opción = ask×100.
4. **Sesión OVERNIGHT (8pm-4am ET):** SMART solo rutea 4am-8pm (ver `tradingHours` del contrato). El venue OVERNIGHT (Blue Ocean) es **solo LIMIT (no stops)** Y el direct-route está bloqueado → **NO se puede poner un stop activo overnight vía API.** Un stop nativo re-armado dispara en la APERTURA SMART de las 4am. Overnight MUD igual cotiza (bid/ask a veces vacío en snapshot pero el volumen/last se actualizan).
5. **reqGlobalCancel tiene lag:** tras cancelar, `openOrders()` puede mostrar las viejas unos segundos. SIEMPRE re-verificar con un clientId nuevo antes de asumir que se limpiaron (una vez vi 4 órdenes = riesgo de oversell; era snapshot a mitad de cancelación).

## Recetas
- **Compra/venta marketable (fill inmediato):** `LimitOrder("BUY",qty, round(ask+0.03,2))` / `SELL` a `round(bid-0.03,2)`. MKT puede rechazarse en extended hours; el limit marketable no.
- **Bracket OCO (TP + stop):** dos órdenes con mismo `ocaGroup` + `ocaType=1` (una llena → cancela la otra). Verificar que queden SOLO 2 (qty total ≤ posición). `outsideRth=True`, `tif="GTC"`.
- **Stop-limit ancho para fill garantizado en gap:** `StopLimitOrder("SELL",qty, lmt_muy_bajo, stop_trigger)` — el límite ancho (ej. stop 11.34 / lmt 10.80) asegura fill aunque abra con hueco.
- **Verificar SIEMPRE tras colocar:** `reqPositions()` + `openOrders()` + `ib.fills()` para el precio real de ejecución.

## Reglas de la casa al ejecutar
- Dinero real → verificar posición exacta antes (safety check: abortar si la qty no es la esperada). Ver [[order-engine-execution]] (doble llave) y [[never-revert-codex]].
- Strikes: AAPL/megacaps van en incrementos de 2.5 cerca de $300 (300/302.5/305, NO 301/302); SPY/QQQ tienen $1. Verificar strikes válidos (Error 200 = no existe).
- Confirmar niveles/números con Yunior antes de disparar cuando cambie la premisa; nunca fabricar un fill (leer `ib.fills()`).
