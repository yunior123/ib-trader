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
import os, subprocess, sys, time
from datetime import timezone

ROOT = "/Users/yuniorrodriguezosorio/ib-trader"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ib_insync import IB, Contract, util  # noqa: E402

HOST, PORT = "127.0.0.1", int(__import__("os").environ.get("IBKR_PORT","4002"))
CLIENT_ID = 86                               # unico vs fleet(84)/single(83)
RETRY_ENTITLEMENT_S = 600
NO_PERM_ERRORS = {420, 10089, 10090, 354}

# name -> (conId, symbol legible). Contratos KRX verificados en vivo 2026-07-12.
# El indice KOSPI directo (K200) NO tiene sub API (error 354); usamos KODEX 200
# (069500), ETF que replica el KOSPI200 y ES accion -> sub waived lo cubre RT.
KOREA = {
    "skhynix": (17382246, "000660"),         # SK Hynix
    "samsung": (17382528, "005930"),         # Samsung Electronics
    "kospi":   (76006841, "069500"),         # KODEX 200 ETF = proxy KOSPI200
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
        elif t.last and t.last > 0:
            # KODEX 200 (kospi): IBKR da trades REALTIME (mdt=1) pero CERO book
            # (bid/ask=-1 siempre — probado en vivo 2026-07-20 09:07 KST; las
            # acciones samsung/skhynix si tienen BBO). Fallback honesto: last
            # trade como bid=ask -> mid exacto, spread 0. NO es delayed.
            st.nbbo_last = now
            with open(f"data/nbbo_{st.name}.txt", "w") as f:
                f.write(f"{now:.0f} {t.last:.4f} {t.last:.4f}\n")
    return on_tick

def krx_market():
    """Sesion KRX 09:00-15:30 KST (UTC+9, sin DST), lun-vie coreano.
    Con 5 min de gracia a cada lado para el stall-watchdog."""
    lt = time.gmtime(time.time() + 9 * 3600)
    return lt.tm_wday < 5 and (8, 55) <= (lt.tm_hour, lt.tm_min) <= (15, 35)

_last_banner = 0.0
_last_resub = 0.0

def loud(title, msg, sound="ProAlarm"):
    """Fail LOUD (ley #2): banner Mac + espejo Desktop, throttle 10 min.
    La flota korea no tiene reader C++ que grite por ella — el bridge grita."""
    global _last_banner
    print(f"{title}: {msg}", file=sys.stderr)
    if time.time() - _last_banner < 600:
        return
    _last_banner = time.time()
    esc = lambda s: s.replace("\\", "").replace('"', "'")
    try:
        subprocess.Popen(["/usr/bin/osascript", "-e",
                          f'display notification "{esc(msg)}" with title '
                          f'"{esc(title)}" sound name "{sound}"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lt = time.localtime()
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
        os.makedirs(d, exist_ok=True)
        with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt",
                  "a") as f:
            f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | "
                    f"{title} | {msg}\n")
    except Exception:
        pass

def resub_all(ib, why):
    """Suelta TODO y fuerza resuscripcion (Error 1101 'data lost' / stall:
    tras un flap, TWS reconecta pero las subs NO reviven solas — el daemon NA
    lo cazo en vivo 2026-07-15 17:23; este bridge se quedo CIEGO igual el
    2026-07-16 10:10 KST y perdio la sesion del viernes entera)."""
    print(f"korea RESUB-ALL ({why}): soltando subs y resuscribiendo",
          file=sys.stderr)
    for st in STATES.values():
        for sub in st.subs:
            try:
                if type(sub).__name__ == "RealTimeBarList":
                    ib.cancelRealTimeBars(sub)
                elif hasattr(sub, "contract"):
                    ib.cancelMktData(sub.contract)
            except Exception:
                pass
        st.subs = []
        st.blocked_until = 0

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
    # Error 1101 (data lost tras flap) -> resub inmediato, igual que el daemon NA
    ib.errorEvent += lambda r, c, m, ct=None, *a: (
        c == 1101 and resub_all(ib, "Error 1101 data-lost"))
    print(f"korea bridge: TWS {HOST}:{PORT}, {len(KOREA)} KRX syms "
          f"(SK Hynix + Samsung + KODEX200, bars 5s->1m + NBBO)", file=sys.stderr)
    for st in STATES.values():
        warmup(ib, st)
    while ib.isConnected():
        for st in STATES.values():
            subscribe_sym(ib, st)
        # STALL WATCHDOG (paridad con daemon NA 2026-07-15): en sesion KRX,
        # suscrito pero 5 min sin UN solo bar 1m de 3 nombres liquidos =
        # subs muertas (caso 1100->reconexion sin 1101). Resub + GRITAR.
        # cooldown 5 min entre resubs: sin bars el reloj del stall no avanza
        # hasta el primer bar post-open — sin cooldown esto thrashea cada 15s
        # (visto en vivo 2026-07-19 pre-open KST)
        global _last_resub
        newest = max((st.last_emitted for st in STATES.values()), default=0)
        subscribed = any(st.subs for st in STATES.values())
        if krx_market() and subscribed and newest > 0 \
                and time.time() - newest > 300 \
                and time.time() - _last_resub > 300:
            _last_resub = time.time()
            loud("🇰🇷 KRX BRIDGE CIEGO",
                 f"{time.time() - newest:.0f}s sin bars KRX en sesion — "
                 f"resuscribiendo (skhynix/samsung/kospi)")
            resub_all(ib, f"stall {time.time() - newest:.0f}s sin bars")
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
