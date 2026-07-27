#!/usr/bin/env python3
"""HIRO probe IBKR — mide el cap REAL de tick-by-tick sobre CONTRATOS DE OPCION.

Correr con TWS/Gateway VIVO y mercado abierto (RTH; en cerrado no llegan prints y
el probe no puede distinguir "sin permiso" de "sin actividad").

    IBKR_PORT=7496 ./venv/bin/python scratchpad/hiro_probe_ibkr.py

READONLY=True, clientId 91 (fuera de los reservados 48/82/83/84/87/90).
NO escribe en el repo. NO ordena nada. Solo mide y escupe una tabla.

Que responde, con numeros:
  1. ¿reqTickByTickData("AllLast") esta PERMITIDO en un contrato de OPCION?
     (err 10190 = cap de suscripciones | 354 = market data no suscrita |
      10197 = no tick-by-tick para este contrato)
  2. ¿Cuantos contratos SIMULTANEOS acepta la cuenta antes del 10190?
  3. ¿Que ritmo de prints llega (prints/min por contrato) y cuantos superan
     un umbral de premium?
  4. ¿Llega el NBBO del PROPIO contrato (tickByTick "BidAsk") para firmar
     Lee-Ready, y a que coste de suscripciones?
"""
import os, sys, time, collections
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from ib_insync import IB, Stock, Option
from ib_mode import get_port

PORT = int(os.environ.get("IBKR_PORT") or get_port())
MODE = os.environ.get("HIRO_MODE", "opt")   # opt | stk (stk = el recurso que pelea el bar bridge)
SYM = os.environ.get("HIRO_SYM", "QQQ")
N_STRIKES = int(os.environ.get("HIRO_STRIKES", "10"))   # +-N/2 alrededor del spot
DWELL = float(os.environ.get("HIRO_DWELL", "60"))       # segundos de escucha
ERRS = collections.Counter()
SEEN = collections.defaultdict(int)
PREM = collections.defaultdict(float)


def next_friday():
    d = date.today()
    return (d + timedelta(days=(4 - d.weekday()) % 7)).strftime("%Y%m%d")


def probe_cap(ib, cons, dwell=20.0):
    """Pide AllLast en TODOS los contratos y mide por TICKS RECIBIDOS quien fue
    aceptado. El break-on-10190 no vale: el error de la peticion k puede llegar
    dentro de la ventana de k+1 y desplaza la cuenta (medido 2026-07-27)."""
    tks = []
    for c in cons:
        tks.append((c, ib.reqTickByTickData(c, "AllLast", 0, False)))
        ib.sleep(0.3)
    got = collections.Counter()
    t0 = time.time()
    while time.time() - t0 < dwell:
        ib.sleep(1.0)
        for c, tk in tks:
            n = len(tk.tickByTicks or [])
            if n:
                got[c.symbol] += n
                tk.tickByTicks.clear()
    print(f"  pedidas {len(tks)}  err10190={ERRS[10190]}  CON TICKS={len(got)}: "
          f"{', '.join(f'{s}:{n}' for s, n in got.most_common())}")
    for c, _ in tks:
        try: ib.cancelTickByTickData(c, "AllLast")
        except Exception: pass
    ib.sleep(1.0)
    return len(got)


def fleet_syms():
    # fleet.txt es UNA linea de 30 palabras: leer por lineas da 1 token (error medido 2026-07-27)
    with open(os.path.join(ROOT, "data", "fleet.txt")) as f:
        return f.read().split()


def main():
    ib = IB()
    ib.connect("127.0.0.1", PORT, clientId=int(os.environ.get("HIRO_CID", "91")),
               readonly=True, timeout=15)
    print(f"conectado {PORT}  server={ib.client.serverVersion()}  "
          f"cuentas={ib.managedAccounts()}")

    def on_err(reqId, code, msg, contract):
        ERRS[code] += 1
        tk = getattr(contract, "localSymbol", "") or getattr(contract, "symbol", "")
        if code in (10190, 354, 10197, 322, 102, 420, 200):
            print(f"  ERR {code} [{tk}] {msg[:90]}")
    ib.errorEvent += on_err

    if MODE == "stk":
        cons = [Stock(s, "SMART", "USD") for s in fleet_syms()]
        ib.qualifyContracts(*cons)
        cons = [c for c in cons if c.conId]
        print(f"MODE=stk  contratos de ACCION cualificados: {len(cons)}")
        probe_cap(ib, cons)
        ib.disconnect()
        return

    # --- spot del subyacente ---
    stk = Stock(SYM, "SMART", "USD")
    ib.qualifyContracts(stk)
    t = ib.reqMktData(stk, "", False, False)
    ib.sleep(2.5)
    spot = t.marketPrice()
    if spot != spot or spot <= 0:
        spot = t.close
    print(f"{SYM} spot={spot}")

    # --- cadena: strikes reales alrededor del spot ---
    params = ib.reqSecDefOptParams(SYM, "", "STK", stk.conId)
    p = next((x for x in params if x.exchange == "SMART"), params[0])
    exp = next_friday()
    if exp not in p.expirations:
        exp = sorted(p.expirations)[0]
    strikes = sorted(p.strikes, key=lambda k: abs(k - spot))[:N_STRIKES]
    print(f"expiry={exp}  strikes={sorted(strikes)}")

    cons = []
    for k in sorted(strikes):
        for r in ("C", "P"):
            cons.append(Option(SYM, exp, k, r, "SMART", tradingClass=SYM))
    ib.qualifyContracts(*cons)
    cons = [c for c in cons if c.conId]
    print(f"contratos cualificados: {len(cons)}")

    # --- PRUEBA 1: un solo contrato, ¿esta permitido? ---
    c0 = min(cons, key=lambda c: abs(c.strike - spot))
    print(f"\n=== PRUEBA 1: AllLast en UN contrato ({c0.localSymbol}) ===")
    before = sum(ERRS.values())
    tb = ib.reqTickByTickData(c0, "AllLast", 0, False)
    ib.sleep(6)
    n0 = len(tb.tickByTicks or [])
    print(f"  ticks en 6s: {n0}   errores nuevos: {sum(ERRS.values()) - before}  {dict(ERRS)}")
    if 10197 in ERRS or 354 in ERRS:
        print("  >>> VEREDICTO: tick-by-tick de OPCIONES NO permitido en esta cuenta.")
        print("      Alternativa: reqMktData con genericTickList '233' (RTVolume) por contrato.")
    ib.cancelTickByTickData(c0, "AllLast")

    # --- PRUEBA 2: escalar hasta el 10190 ---
    print(f"\n=== PRUEBA 2: escalar suscripciones hasta el cap (err 10190) ===")
    live, capped_at = [], None
    for c in cons:
        ERRS[10190] = 0
        tk = ib.reqTickByTickData(c, "AllLast", 0, False)
        ib.sleep(1.0)
        if ERRS[10190]:
            ib.cancelTickByTickData(c, "AllLast")
            capped_at = len(live)
            print(f"  CAP alcanzado en {capped_at} suscripciones simultaneas")
            break
        live.append((c, tk))
    if capped_at is None:
        print(f"  sin cap con {len(live)} suscripciones (no se alcanzo el limite)")

    # --- PRUEBA 3: ritmo de prints y premium ---
    print(f"\n=== PRUEBA 3: escuchando {DWELL:.0f}s en {len(live)} contratos ===")
    t0 = time.time()
    while time.time() - t0 < DWELL:
        ib.sleep(1.0)
        for c, tk in live:
            for x in (tk.tickByTicks or []):
                px, sz = float(x.price or 0), float(x.size or 0)
                if px > 0 and sz > 0:
                    SEEN[c.localSymbol] += 1
                    PREM[c.localSymbol] += px * sz * 100
            tk.tickByTicks.clear()
    mins = (time.time() - t0) / 60
    tot = sum(SEEN.values())
    print(f"  prints totales: {tot}  ({tot/mins:.0f}/min agregado)")
    for k in sorted(SEEN, key=lambda k: -SEEN[k])[:12]:
        print(f"    {k:24s} {SEEN[k]:5d} prints  {PREM[k]/mins:12,.0f} USD-premium/min")

    # --- PRUEBA 4: NBBO del propio contrato para firmar ---
    print(f"\n=== PRUEBA 4: BidAsk tick-by-tick (para firmar Lee-Ready) ===")
    ERRS[10190] = 0
    ba = ib.reqTickByTickData(c0, "BidAsk", 0, True)
    ib.sleep(5)
    nba = len(ba.tickByTicks or [])
    print(f"  BidAsk ticks en 5s: {nba}   err10190={ERRS[10190]}")
    print(f"  >>> coste: 2 suscripciones por contrato si se quiere NBBO al print")
    ib.cancelTickByTickData(c0, "BidAsk")

    for c, _ in live:
        try: ib.cancelTickByTickData(c, "AllLast")
        except Exception: pass
    print(f"\nERRORES ACUMULADOS: {dict(ERRS)}")
    print(f"RESUMEN: cap={capped_at}  prints/min={tot/mins:.0f}  "
          f"contratos_con_actividad={len([k for k in SEEN if SEEN[k]])}/{len(live)}")
    ib.disconnect()


if __name__ == "__main__":
    main()
