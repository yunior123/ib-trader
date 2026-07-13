#!/usr/bin/env python3
"""korea_bar_bridge.py — realtime KRX market-data daemon (SK Hynix + Samsung).

Descubrimiento 2026-07-12 (verificado en vivo, KRX abierto): el sub waived
"Korea Equities" SI cubre la API de IBKR (a diferencia del US non-consolidated,
que es solo pantalla del TWS). SK Hynix (000660) y Samsung Elec (005930) dan
marketDataType=1 REALTIME con bid/ask + volumen consolidado, GRATIS. Son el
mercado de memoria/DRAM en si; Corea abre ~13h antes que EE.UU. -> indicador
LIDER realtime para los nombres US de memoria (MU, ETF DRAM).

Escribe, en el MISMO formato que la flota (para que un bot C++ lo consuma tal
cual el resto):
  data/bars_<name>.txt   "EPOCH O H L C V"   (5s reqRealTimeBars -> agg 1m)
  data/nbbo_<name>.txt    "EPOCH BID ASK"     (throttle 1/s)
names: skhynix, samsung.

reqMarketDataType(1) fijo — delayed PROHIBIDO (orden #6). Si KRX pierde permiso
(no deberia: sub waived) se marca y reintenta cada 10 min, gritando a stderr.

Python (ib_insync) solo porque el SDK C++ de IB no esta instalado; productor
I/O-bound — la matematica de senal sigue en C++.

Uso: korea_bar_bridge.py [--daemon]   (por defecto daemon)
"""
import os, sys, time
from datetime import timezone

ROOT = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ib_insync import IB, Contract, util  # noqa: E402

HOST, PORT = "127.0.0.1", 7496
CLIENT_ID = 86                               # unico vs fleet(84)/single(83)
RETRY_ENTITLEMENT_S = 600
NO_PERM_ERRORS = {420, 10089, 10090, 354}

# name -> (conId, symbol legible). Contratos KRX verificados en vivo 2026-07-12.
KOREA = {
    "skhynix": (17382246, "000660"),         # SK Hynix
    "samsung": (17382528, "005930"),         # Samsung Electronics
}

class SymState:
    def __init__(self, name):
        self.name = name
        self.agg = {}                         # minute_ep -> [o,h,l,c,v]
        self.last_emitted = 0.0
        self.nbbo_last = 0
        self.blocked_until = 0.0
        self.subs = []

STATES = {n: SymState(n) for n in KOREA}

def emit(st, ep, o, h, l, c, v):
    if ep <= st.last_emitted or c <= 0:
        return
    st.last_emitted = ep
    line = f"{ep:.0f} {o:.4f} {h:.4f} {l:.4f} {c:.4f} {v:.0f}\n"
    with open(f"data/bars_{st.name}.txt", "a") as f:
        f.write(line)

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
        if ep % 60 == 55:                     # el 5s-bar :55 CIERRA el minuto
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
            with open(f"data/nbbo_{st.name}.txt", "w") as f:
                f.write(f"{now:.0f} {t.bid:.4f} {t.ask:.4f}\n")
    return on_tick

def warmup(ib, st):
    """historia 1 dia -> escribe el bars file (truncate, orden ascendente) para
    que el bot C++ prime BB/RSI al instante; live continua en append."""
    conId, sym = KOREA[st.name]
    try:
        c = Contract(conId=conId, exchange="KRX"); ib.qualifyContracts(c)
        hist = ib.reqHistoricalData(c, "", "1 D", "1 min", "TRADES",
                                    useRTH=False, formatDate=2)
    except Exception as e:
        print(f"{st.name}: warmup fallo ({e})", file=sys.stderr); return
    n = 0
    with open(f"data/bars_{st.name}.txt", "w") as f:
        for b in hist:
            if not (b.close and b.close > 0):
                continue
            ep = b.date.timestamp(); m = ep - ep % 60
            v = float(b.volume) if b.volume and b.volume > 0 else 0
            f.write(f"{m:.0f} {b.open:.4f} {b.high:.4f} {b.low:.4f} {b.close:.4f} {v:.0f}\n")
            st.last_emitted = m; n += 1
    print(f"{st.name} ({sym}): warmup {n} bars", file=sys.stderr)

def subscribe_sym(ib, st):
    if time.time() < st.blocked_until or st.subs:
        return
    conId, sym = KOREA[st.name]
    got_err = []
    def on_err(reqId, code, msg, contract):
        if code in NO_PERM_ERRORS:
            got_err.append(code)
    ib.errorEvent += on_err
    try:
        c = Contract(conId=conId, exchange="KRX")
        ib.qualifyContracts(c)
        rtb = ib.reqRealTimeBars(c, 5, "TRADES", useRTH=False)
        rtb.updateEvent += make_on_bar5(st)
        tkr = ib.reqMktData(c, "", False, False)
        tkr.updateEvent += make_on_nbbo(st)
        ib.sleep(3)
        if got_err:
            ib.cancelRealTimeBars(rtb); ib.cancelMktData(c)
            st.blocked_until = time.time() + RETRY_ENTITLEMENT_S
            print(f"{st.name} ({sym}): SIN PERMISOS API (err {got_err[0]}) — "
                  f"reintento en {RETRY_ENTITLEMENT_S//60} min", file=sys.stderr)
            return
        st.subs = [rtb, tkr]
        print(f"{st.name} ({sym}): KRX realtime bars+NBBO suscritos", file=sys.stderr)
    except Exception as e:
        st.blocked_until = time.time() + 120
        print(f"{st.name}: subscribe fallo ({e})", file=sys.stderr)
    finally:
        ib.errorEvent -= on_err

def run():
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=20)
    ib.reqMarketDataType(1)                   # 1 = REALTIME. Delayed PROHIBIDO.
    print(f"korea bridge: TWS {HOST}:{PORT}, {len(KOREA)} KRX syms "
          f"(SK Hynix + Samsung, bars 5s->1m + NBBO)", file=sys.stderr)
    for st in STATES.values():
        warmup(ib, st)
    while ib.isConnected():
        for st in STATES.values():
            subscribe_sym(ib, st)
        ib.sleep(15)
    raise ConnectionError("TWS desconectado")

while True:
    try:
        run()
    except Exception as e:
        print(f"korea bridge CAIDO: {e} — reintento en 15s (¿TWS en {PORT}?)",
              file=sys.stderr)
        for st in STATES.values():
            st.subs = []; st.blocked_until = 0
        time.sleep(15)
