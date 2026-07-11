#!/usr/bin/env python3
"""ibkr_bar_bridge.py — TWS market-data daemon for the C++ signal fleet.

Orden Yunior 2026-07-11: "leave the bots ready for ibkr and use alpaca as
fallback ... premium ibkr next week ... super pro fast precise".

Modo flota (el normal):
    ibkr_bar_bridge.py --daemon SYM1 SYM2 ...
  - por simbolo: reqRealTimeBars 5s (TRADES, useRTH=0) -> agg 1m -> APPEND
    "EPOCH O H L C V" a data/bars_<sym>_ibkr.txt (el reader C++ del bot
    prefiere este archivo cuando esta vivo; alpaca = fallback caliente)
  - por simbolo: reqMktData NBBO SIP -> data/nbbo_<sym>.txt "EPOCH BID ASK"
    (throttle 1/s; los 16 nombres — el cap de 30 de alpaca no aplica aqui)
  - venue OVERNIGHT (IBEOS) ademas de SMART: bars 24/5 donde exista
  - ENTITLEMENT PROBE: si un sub da error 420/10089 (sin subscripcion) se
    marca y se reintenta cada 10 min — cuando Yunior active el SIP bundle
    ($10/mo, requiere >= USD 500 equity) la flota se auto-actualiza sin
    tocar nada. Se grita a stderr; JAMAS delayed (reqMarketDataType 1 fijo).

Modo legacy (un simbolo, stdout): ibkr_bar_bridge.py SYM [--live-only]

Python (ib_insync) solo porque el SDK C++ de IB no esta instalado; es un
productor de archivos I/O-bound — bots, readers y matematica siguen en C++.
"""
import os, sys, time
from datetime import timezone

ROOT = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ib_insync import IB, Stock, util  # noqa: E402

HOST, PORT = "127.0.0.1", 7496
RETRY_ENTITLEMENT_S = 600
NO_PERM_ERRORS = {420, 10089, 10090, 354}   # variantes "necesita subscripcion"

DAEMON = "--daemon" in sys.argv
LIVE_ONLY = "--live-only" in sys.argv
SYMS = [a for a in sys.argv[1:] if not a.startswith("--")] or ["USO"]
CLIENT_ID = 84 if DAEMON else 83

class SymState:
    def __init__(self, sym):
        self.sym = sym
        self.agg = {}                 # minute_ep -> [o,h,l,c,v]
        self.last_emitted = 0.0
        self.nbbo_last = 0
        self.blocked_until = 0.0      # entitlement backoff por venue
        self.subs = []

STATES = {s: SymState(s) for s in SYMS}

def bars_path(sym):
    return f"data/bars_{sym.lower()}_ibkr.txt"

def emit(st, ep, o, h, l, c, v):
    if ep <= st.last_emitted or c <= 0:
        return
    st.last_emitted = ep
    line = f"{ep:.0f} {o:.4f} {h:.4f} {l:.4f} {c:.4f} {v:.0f}\n"
    if DAEMON:
        with open(bars_path(st.sym), "a") as f:
            f.write(line)
    else:
        sys.stdout.write(line); sys.stdout.flush()

def make_on_bar5(st):
    def on_bar5(bars, hasNewBar):
        if not hasNewBar or not bars:
            return
        b = bars[-1]
        ep = b.time.replace(tzinfo=b.time.tzinfo or timezone.utc).timestamp()
        m = ep - ep % 60
        a = st.agg.get(m)
        if a is None:
            for pm in sorted(k for k in st.agg if k < m):   # minuto previo -> fuera
                o, h, l, c, v = st.agg.pop(pm)
                emit(st, pm, o, h, l, c, v)
            st.agg[m] = [b.open_, b.high, b.low, b.close, b.volume]
        else:
            a[1] = max(a[1], b.high); a[2] = min(a[2], b.low)
            a[3] = b.close; a[4] += b.volume
        if ep % 60 == 55:                # el 5s-bar :55 CIERRA el minuto -> ~300ms
            o, h, l, c, v = st.agg.pop(m)
            emit(st, m, o, h, l, c, v)
    return on_bar5

def make_on_nbbo(st):
    def on_tick(t):
        now = time.time()
        if now - st.nbbo_last < 1.0:
            return
        if t.bid and t.ask and t.bid > 0 and t.ask > t.bid:
            st.nbbo_last = now
            with open(f"data/nbbo_{st.sym.lower()}.txt", "w") as f:
                f.write(f"{now:.0f} {t.bid:.4f} {t.ask:.4f}\n")
    return on_tick

def subscribe_sym(ib, st):
    """(re)intenta suscribir un simbolo; deja backoff si no hay permisos."""
    if time.time() < st.blocked_until or st.subs:
        return
    got_err = []
    def on_err(reqId, code, msg, contract):
        if code in NO_PERM_ERRORS:
            got_err.append(code)
    ib.errorEvent += on_err
    try:
        smart = Stock(st.sym, "SMART", "USD")
        ib.qualifyContracts(smart)
        rtb = ib.reqRealTimeBars(smart, 5, "TRADES", useRTH=False)
        rtb.updateEvent += make_on_bar5(st)
        tkr = ib.reqMktData(smart, "", False, False)
        tkr.updateEvent += make_on_nbbo(st)
        ib.sleep(3)                          # deja aterrizar un posible 420
        if got_err:
            ib.cancelRealTimeBars(rtb); ib.cancelMktData(smart)
            st.blocked_until = time.time() + RETRY_ENTITLEMENT_S
            print(f"{st.sym}: SIN PERMISOS API (err {got_err[0]}) — reintento "
                  f"en {RETRY_ENTITLEMENT_S//60} min (activar SIP bundle $10; "
                  f"requiere >= USD 500 equity)", file=sys.stderr)
            return
        st.subs = [rtb, tkr]
        print(f"{st.sym}: SIP bars+NBBO suscritos (premium activo)", file=sys.stderr)
        try:                                  # venue overnight best-effort
            onc = Stock(st.sym, "OVERNIGHT", "USD")
            ib.qualifyContracts(onc)
            r2 = ib.reqRealTimeBars(onc, 5, "TRADES", useRTH=False)
            r2.updateEvent += make_on_bar5(st)
            st.subs.append(r2)
        except Exception:
            pass
    except Exception as e:
        st.blocked_until = time.time() + 120
        print(f"{st.sym}: subscribe fallo ({e})", file=sys.stderr)
    finally:
        ib.errorEvent -= on_err

def run_daemon():
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=20)
    ib.reqMarketDataType(1)                  # 1 = REALTIME. Delayed PROHIBIDO.
    print(f"ibkr fleet daemon: TWS {HOST}:{PORT}, {len(SYMS)} syms "
          f"(bars 5s->1m + NBBO SIP + overnight)", file=sys.stderr)
    while ib.isConnected():
        for st in STATES.values():
            subscribe_sym(ib, st)
        ib.sleep(15)
    raise ConnectionError("TWS desconectado")

def run_single():
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=20)
    ib.reqMarketDataType(1)
    st = STATES[SYMS[0]]
    if not LIVE_ONLY:
        smart = Stock(st.sym, "SMART", "USD")
        ib.qualifyContracts(smart)
        hist = ib.reqHistoricalData(smart, "", "3 D", "1 min", "TRADES",
                                    useRTH=False, formatDate=2)
        for b in hist:
            ep = b.date.timestamp()
            emit(st, ep - ep % 60, b.open, b.high, b.low, b.close,
                 float(b.volume) if b.volume and b.volume > 0 else 0)
        print(f"{st.sym}: warm-up {len(hist)} bars", file=sys.stderr)
    while ib.isConnected():
        subscribe_sym(ib, st)
        ib.sleep(15)
    raise ConnectionError("TWS desconectado")

while True:
    try:
        run_daemon() if DAEMON else run_single()
    except Exception as e:
        print(f"ibkr bridge CAIDO: {e} — reintento en 15s (¿TWS en {PORT}?)",
              file=sys.stderr)
        for st in STATES.values():
            st.subs = []; st.blocked_until = 0
        time.sleep(15)
