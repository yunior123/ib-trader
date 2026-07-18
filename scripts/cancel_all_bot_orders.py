#!/usr/bin/env python3
"""cancel_all_bot_orders.py — orden Yunior 2026-07-16: SOLO SEÑALES.
Cancela TODAS las ordenes abiertas (GTC de recuperacion, stops OCA) que los
ejecutores retirados dejaron vivas en el servidor IBKR. Lista antes de cancelar
para que cada orden quede documentada y re-colocable a mano si alguna era humana.
"""
import sys
from ib_insync import IB, util

ib = IB()
try:
    ib.connect("127.0.0.1", 7496, clientId=87, timeout=15)
except Exception as e:
    print(f"ERROR: no conecta a TWS 7496: {e}")
    sys.exit(1)

acct = ib.managedAccounts()
print(f"cuenta(s): {acct}")

trades = ib.reqAllOpenOrders()
ib.sleep(2)
open_trades = [t for t in ib.openTrades()]
if not open_trades:
    print("SIN ORDENES ABIERTAS — el broker esta limpio.")
    ib.disconnect()
    sys.exit(0)

print(f"{len(open_trades)} orden(es) abiertas ANTES de cancelar:")
for t in open_trades:
    o, c = t.order, t.contract
    print(f"  #{o.orderId} {o.action} {o.totalQuantity} {c.symbol} "
          f"{o.orderType} lmt={o.lmtPrice} aux={o.auxPrice} tif={o.tif} "
          f"oca={o.ocaGroup!r} ref={o.orderRef!r} status={t.orderStatus.status}")

for t in open_trades:
    ib.cancelOrder(t.order)
ib.sleep(3)

remaining = [t for t in ib.openTrades()
             if t.orderStatus.status not in ("Cancelled", "ApiCancelled", "Inactive")]
if remaining:
    print(f"ATENCION: {len(remaining)} orden(es) siguen vivas tras cancelar:")
    for t in remaining:
        print(f"  #{t.order.orderId} {t.contract.symbol} status={t.orderStatus.status}")
else:
    print("TODAS CANCELADAS — cero ordenes bot en el broker.")
ib.disconnect()
