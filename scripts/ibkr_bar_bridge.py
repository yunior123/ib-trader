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

WHALE_MIN_USD = float(os.environ.get("WHALE_MIN_USD", "50000"))

class SymState:
    def __init__(self, sym):
        self.sym = sym
        self.agg = {}                 # minute_ep -> [o,h,l,c,v]
        self.last_emitted = 0.0
        self.nbbo_last = 0
        self.blocked_until = 0.0      # entitlement backoff por venue
        self.subs = []
        self.warmed = False           # warm-up historico ya escrito
        self.bid = 0.0                # NBBO vivo (para el lado de la ballena)
        self.ask = 0.0
        self.whale_day = ""           # truncado diario del whale file
        self.whales_on = False        # tick-by-tick suscrito (cap IBKR)

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
        if t.bid and t.ask and t.bid > 0 and t.ask > t.bid:
            st.bid, st.ask = t.bid, t.ask     # siempre fresco para las ballenas
            if now - st.nbbo_last < 0.25:     # 4/s (era 1/s; orden 2026-07-15
                return                        # "blazing fast" — spread gate fresco)
            st.nbbo_last = now
            with open(f"data/nbbo_{st.sym.lower()}.txt", "w") as f:
                f.write(f"{now:.0f} {t.bid:.4f} {t.ask:.4f}\n")
    return on_tick


def make_on_whale(st):
    """Prints gordos (>= WHALE_MIN_USD) del tape SIP tick-by-tick -> APPEND
    "EPOCH PX USD DIR" a data/whale_<sym>.txt (formato que whale_score() de
    los bots ya lee; feed alpaca retirado 2026-07-15 era-ibkr-only).
    DIR: +1 agresor comprador (px>=ask), -1 vendedor (px<=bid), 0 indeterminado.
    Truncado diario para que el archivo no crezca sin limite."""
    def on_ticks(ticker):
        # updateEvent emite el Ticker; los ticks nuevos del batch vienen en
        # ticker.tickByTicks (iterar el Ticker directo revienta en silencio
        # dentro del event-loop de ib_insync — bug cazado 2026-07-15 al abrir)
        lines = []
        for t in (getattr(ticker, "tickByTicks", None) or []):
            px = float(t.price or 0); sz = float(t.size or 0)
            usd = px * sz
            if usd < WHALE_MIN_USD or px <= 0:
                continue
            ep = t.time.timestamp() if getattr(t, "time", None) else time.time()
            d = 0
            if st.ask > 0 and px >= st.ask:
                d = 1
            elif st.bid > 0 and px <= st.bid:
                d = -1
            lines.append(f"{ep:.0f} {px:.4f} {usd:.0f} {d}\n")
        if not lines:
            return
        day = time.strftime("%Y%m%d")
        mode = "a" if st.whale_day == day else "w"   # nuevo dia -> truncar
        st.whale_day = day
        with open(f"data/whale_{st.sym.lower()}.txt", mode) as f:
            f.writelines(lines)
    return on_ticks

def warmup_sym(ib, st):
    """Warm-up historico SIP (orden Yunior 2026-07-15 "connect to ibkr only"):
    el archivo de bars queda AUTOSUFICIENTE — 2 dias de 1m TRADES reescritos
    ordenados (truncate) antes de appendear bars vivos, para que el reader C++
    no necesite el backfill REST de alpaca. Solo minutos COMPLETOS (< minuto
    actual); dedupe via last_emitted."""
    if st.warmed:
        return
    # restart rapido (2026-07-15 "blazing fast"): si el archivo ya tiene bars
    # frescos (<30 min) NO re-bajar 2 dias de historia (17 syms ≈ 2 min de
    # resuscripcion que disparaba el banner de outage de los readers) — solo
    # retomar el ultimo epoch y seguir appendeando en vivo.
    try:
        p = bars_path(st.sym)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            with open(p, "rb") as f:
                f.seek(max(0, os.path.getsize(p) - 200))
                last_ep = float(f.read().decode().strip().splitlines()[-1].split()[0])
            if time.time() - last_ep < 1800:
                st.last_emitted = last_ep
                st.warmed = True
                print(f"{st.sym}: warm-up SALTADO (archivo fresco, "
                      f"ultimo bar hace {time.time() - last_ep:.0f}s)", file=sys.stderr)
                return
    except Exception:
        pass
    try:
        smart = Stock(st.sym, "SMART", "USD")
        ib.qualifyContracts(smart)
        hist = ib.reqHistoricalData(smart, "", "2 D", "1 min", "TRADES",
                                    useRTH=False, formatDate=2)
        cur_min = time.time() - time.time() % 60
        n = 0
        with open(bars_path(st.sym), "w") as f:
            for b in hist:
                ep = b.date.timestamp(); ep -= ep % 60
                if ep >= cur_min or b.close <= 0:
                    continue
                v = float(b.volume) if b.volume and b.volume > 0 else 0
                f.write(f"{ep:.0f} {b.open:.4f} {b.high:.4f} "
                        f"{b.low:.4f} {b.close:.4f} {v:.0f}\n")
                st.last_emitted = max(st.last_emitted, ep)
                n += 1
        print(f"{st.sym}: warm-up historico {n} bars 1m (2D SIP)", file=sys.stderr)
        st.warmed = True
    except Exception as e:
        print(f"{st.sym}: warm-up fallo ({e}) — reintento proximo ciclo",
              file=sys.stderr)

def subscribe_sym(ib, st):
    """(re)intenta suscribir un simbolo; deja backoff si no hay permisos."""
    if time.time() < st.blocked_until or st.subs:
        return
    warmup_sym(ib, st)
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
        ib.sleep(1.5)                        # deja aterrizar un posible 420
                                             # (3s->1.5s 2026-07-15: 17 syms
                                             # seriales cruzaban los 120s del
                                             # reader y disparaban outage)
        if got_err:
            ib.cancelRealTimeBars(rtb); ib.cancelMktData(smart)
            st.blocked_until = time.time() + RETRY_ENTITLEMENT_S
            print(f"{st.sym}: SIN PERMISOS API (err {got_err[0]}) — reintento "
                  f"en {RETRY_ENTITLEMENT_S//60} min (activar SIP bundle $10; "
                  f"requiere >= USD 500 equity)", file=sys.stderr)
            return
        st.subs = [rtb, tkr]
        print(f"{st.sym}: SIP bars+NBBO suscritos (premium activo)", file=sys.stderr)
        # ballenas tick-by-tick (2026-07-15, reemplaza el feed alpaca): IBKR
        # capea las suscripciones tick-by-tick por cuenta — best-effort en el
        # orden de la lista de simbolos; sin ballenas el bot solo pierde el 5%
        # del score (gate degradado, no roto). Error tipico al topar: 10190.
        try:
            tbt_err = []
            def on_tbt_err(reqId, code, msg, contract):
                if code in (10190, 322, 102):
                    tbt_err.append(code)
            ib.errorEvent += on_tbt_err
            tbt = ib.reqTickByTickData(smart, "AllLast", 0, False)
            tbt.updateEvent += make_on_whale(st)
            ib.sleep(1)
            ib.errorEvent -= on_tbt_err
            if tbt_err:
                ib.cancelTickByTickData(smart, "AllLast")
                print(f"{st.sym}: whales tick-by-tick DENEGADO (err {tbt_err[0]}"
                      f" — cap de suscripciones)", file=sys.stderr)
            else:
                st.subs.append(tbt)
                st.whales_on = True
                print(f"{st.sym}: whales tick-by-tick ON (>= "
                      f"{WHALE_MIN_USD:.0f} USD)", file=sys.stderr)
        except Exception as e:
            print(f"{st.sym}: whales sub fallo ({e})", file=sys.stderr)
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

def prune_whales(st):
    """Recorta whale_<sym>.txt a los ultimos 15 min: los bots solo puntuan
    prints <=10 min y escanean el archivo ENTERO por barra — en TSLA/NVDA
    ($50k = print normal) creceria a cientos de miles de lineas al dia."""
    p = f"data/whale_{st.sym.lower()}.txt"
    try:
        if not os.path.exists(p) or os.path.getsize(p) < 64 * 1024:
            return
        cut = time.time() - 900
        keep = [ln for ln in open(p)
                if ln.split(" ", 1)[0].isdigit() and float(ln.split(" ", 1)[0]) >= cut]
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            f.writelines(keep)
        os.replace(tmp, p)
    except Exception:
        pass


def _resub_all(ib, why):
    """Suelta TODAS las suscripciones y fuerza resuscripcion (Error 1101
    'data lost' / stall: tras un flap del uplink —hoy causado por ProtonVPN—
    TWS reconecta pero las suscripciones NO reviven solas; el daemon creia
    estar suscrito y se quedaba ciego. Cazado en vivo 2026-07-15 17:23)."""
    print(f"RESUB-ALL ({why}): soltando suscripciones y resuscribiendo",
          file=sys.stderr)
    for st in STATES.values():
        for sub in st.subs:
            try:
                if hasattr(sub, "contract"):
                    ib.cancelMktData(sub.contract)
            except Exception:
                pass
        st.subs = []
        st.blocked_until = 0
        st.whales_on = False


def run_daemon():
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=20)
    ib.reqMarketDataType(1)                  # 1 = REALTIME. Delayed PROHIBIDO.
    ib.errorEvent += lambda r, c, m, ct=None, *a: (
        c == 1101 and _resub_all(ib, "Error 1101 data-lost"))
    print(f"ibkr fleet daemon: TWS {HOST}:{PORT}, {len(SYMS)} syms "
          f"(bars 5s->1m + NBBO SIP + whales tick-by-tick + overnight)",
          file=sys.stderr)
    last_prune = 0.0
    last_resub = 0.0
    while ib.isConnected():
        for st in STATES.values():
            subscribe_sym(ib, st)
        if time.time() - last_prune > 600:
            last_prune = time.time()
            for st in STATES.values():
                if st.whales_on:
                    prune_whales(st)
        # STALL WATCHDOG: conectado + suscrito pero NINGUN bar en 5 min en
        # ventana de mercado (L-V 04:00-20:00 ET o KRX via US overnight) =
        # suscripciones muertas (caso 1100->reconexion sin 1101 explicito).
        # Cooldown 5 min entre resubs (2026-07-19, cazado en el bridge korea):
        # sin bars el reloj del stall no avanza hasta el primer bar post-open
        # — sin cooldown esto thrashea resubs cada 15s en pre-open.
        lt = time.localtime()
        market = lt.tm_wday < 5 and 4 <= lt.tm_hour < 20
        newest = max((st.last_emitted for st in STATES.values()), default=0)
        subscribed = any(st.subs for st in STATES.values())
        if market and subscribed and newest > 0 and time.time() - newest > 300 \
                and time.time() - last_resub > 300:
            last_resub = time.time()
            _resub_all(ib, f"stall {time.time() - newest:.0f}s sin bars")
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
