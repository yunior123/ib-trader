#!/usr/bin/env python3
"""smoke_paper.py — prueba que la cuenta PAPER permite place/cancel de OPCIONES vía API.

Independiente del motor C++: usa ib_insync para (1) conectar a 7497, (2) verificar
que es la cuenta paper DUR197573, (3) cualificar una opción líquida, (4) colocar un
LÍMITE lejos-del-dinero a $0.01 (JAMÁS llena), (5) confirmar que aparece, (6)
CANCELARLO, (7) confirmar cancelado. Si todo pasa -> la vía de órdenes de opciones
funciona en paper y el order_engine C++ puede operar igual.

SEGURIDAD: se NIEGA a correr si el puerto no es 7497 o la cuenta no es la paper.
Nunca toca live. La orden es no-marketable (no llena) y se cancela enseguida.

Uso:  venv/bin/python order_engine/smoke_paper.py [--sym QQQ]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from ib_insync import IB, Option, Stock, LimitOrder  # noqa: E402
import ib_mode                        # fuente única: puerto del modo (gateway/tws auto)

PAPER_ACCT = "DUR197573"
CLIENT_ID = 96                      # dedicado al smoke (no choca con 92 del motor)


def die(msg, code=1):
    print(f"❌ {msg}"); sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="QQQ")
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args()

    port = a.port or ib_mode.get_port()     # auto: gateway 4002 / tws 7497
    if port not in ib_mode.PAPER_PORTS:
        die(f"puerto {port} no es de PAPER ({ib_mode.PAPER_PORTS}) — este smoke SOLO corre en paper. Aborto.")

    ib = IB()
    try:
        ib.connect("127.0.0.1", port, clientId=CLIENT_ID, timeout=15)  # NO readonly: vamos a ordenar
    except Exception as e:
        die(f"no conecta a paper puerto {port} ({e}). ¿Gateway/TWS paper arriba? ¿API socket habilitado?")

    accts = ib.managedAccounts()
    if PAPER_ACCT not in accts:
        ib.disconnect()
        die(f"cuenta conectada {accts} NO es la paper {PAPER_ACCT}. Aborto (jamás live).")
    print(f"✓ conectado paper puerto {port}, cuenta {accts}")

    stk = Stock(a.sym, "SMART", "USD")
    ib.qualifyContracts(stk)
    # Spot desde NUESTRO archivo de la flota (evita la suscripción de market data
    # del API; place/cancel NO necesita market data). Fallback: delayed.
    spot = None
    barf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", f"bars_{a.sym.lower()}_ibkr.txt")
    try:
        last = [l for l in open(barf) if l.strip()][-1]
        spot = float(last.split()[4])          # epoch o h l C v
        print(f"✓ {a.sym} spot ~{spot:.2f} (archivo flota)")
    except Exception:
        ib.reqMarketDataType(3)                # delayed SOLO para elegir strike de un test
        [t] = ib.reqTickers(stk)
        spot = t.marketPrice() or t.close or t.last
        print(f"✓ {a.sym} spot ~{spot} (delayed, solo para el strike)")
    if not spot or spot != spot:
        ib.disconnect(); die(f"sin spot de {a.sym}")

    params = ib.reqSecDefOptParams(a.sym, "", "STK", stk.conId)
    if not params:
        ib.disconnect(); die("sin parámetros de opciones")
    p = params[0]
    # strike ATM (existe seguro) + PUT. $0.01 no es marketable en NINGÚN strike real,
    # así que no hace falta OTM. Probar expiries hasta que el contrato CUALIFIQUE.
    strike = min(p.strikes, key=lambda k: abs(k - spot))
    opt = None
    for exp in sorted(p.expirations)[:5]:
        cand = Option(a.sym, exp, strike, "P", "SMART", tradingClass=a.sym)
        try:
            ib.qualifyContracts(cand)
        except Exception:
            pass
        if cand.conId:
            opt = cand; break
    if not opt or not opt.conId:
        ib.disconnect(); die(f"no cualifica ninguna opción ATM de {a.sym} (strike {strike})")
    print(f"✓ contrato: {a.sym} {opt.lastTradeDateOrContractMonth} {strike}P conId={opt.conId}")

    # límite $0.01 (no-marketable: NO llena). BUY 1.
    order = LimitOrder("BUY", 1, 0.01)
    order.orderRef = "OE:SMOKE"
    tr = ib.placeOrder(opt, order)
    ib.sleep(3)
    st = tr.orderStatus.status
    print(f"✓ orden colocada id={tr.order.orderId} status={st}")
    if st not in ("Submitted", "PreSubmitted", "PendingSubmit", "ApiPending"):
        print(f"⚠ status inesperado: {st} (¿permisos de opciones en la cuenta?)")

    ib.cancelOrder(tr.order)
    ib.sleep(2)
    st2 = tr.orderStatus.status
    print(f"✓ cancelada -> status={st2}")

    ib.disconnect()
    ok = st in ("Submitted", "PreSubmitted", "PendingSubmit", "ApiPending") and \
        st2 in ("Cancelled", "ApiCancelled", "PendingCancel")
    if ok:
        print("\n✅ SMOKE PASA: place + cancel de opciones funciona en paper. "
              "El order_engine C++ puede operar igual (misma API).")
        sys.exit(0)
    print("\n⚠ SMOKE PARCIAL: revisa los status arriba (permisos/market-data de la cuenta).")
    sys.exit(2)


if __name__ == "__main__":
    main()
