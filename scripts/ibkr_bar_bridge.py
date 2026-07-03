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
import json, os, subprocess, sys, time
from datetime import timezone

# Ruta DERIVADA, nunca hardcodeada (2026-07-25): la mudanza del repo dejo tres scripts en
# crash-loop durante horas — opt_whale_watch, opt_chain_cache y opt_sentinel — con el keepalive
# relanzandolos en silencio y el panel diciendo "armado" sin una sola alarma de ballena.
# Este fichero apuntaba a la ruta nueva ya corregida a mano, pero seguia siendo literal.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ib_insync import IB, Stock, util  # noqa: E402
from ib_mode import get_port  # fuente unica: data/ib_mode.txt (paper/live), no 4002 a ciegas

import os as _os  # portero de banners
_OSA = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "osa_gate")  # respeta data/notify_off

HOST, PORT = "127.0.0.1", get_port()
RETRY_ENTITLEMENT_S = 600
NO_PERM_ERRORS = {420, 10089, 10090, 354}   # variantes "necesita subscripcion"

DAEMON = "--daemon" in sys.argv
LIVE_ONLY = "--live-only" in sys.argv
SYMS = [a for a in sys.argv[1:] if not a.startswith("--")] or ["USO"]
CLIENT_ID = 84 if DAEMON else 83

# CAP DE CINTA MEDIDO 2026-07-27 con docs/probes/hiro_probe_ibkr.py (HIRO_MODE=stk), mercado
# abierto y la flota viva: 5 contratos DISTINTOS tick-by-tick por CUENTA. El 6o contrato nuevo
# da 10190 SIEMPRE, venga de la conexion que venga — 25 pedidos desde 5 conexiones extra
# (clientId 120-124) dieron 25 denegaciones y CERO ficheros escritos.
# TRAMPA que costo dos vueltas: un contrato YA suscrito por otro cliente se concede GRATIS (no
# consume cupo). Por eso 3 clientes simultaneos "recibian 5 cada uno": eran los mismos QQQ SPY
# NVDA TSLA SMH del daemon, duplicados. Mas conexiones NO compran cinta; el cupo es un
# ENTITLEMENT (se sube con Quote Booster packs, no con codigo).
TAPE_MAX = int(os.environ.get("TAPE_MAX", "5"))
BLIND_F = "data/tape_blind.txt"
TAPE = {"granted": set()}

# PRIORIDAD DE CINTA PARA LOS CAPITANES (fix 2026-07-25). Con cupo 5 y 30 simbolos el reparto
# no puede ser justo: se ELIGE. Capitanes primero (regla 12) y el resto por USD/min MEDIDO, no
# por orden de arranque — el 2026-07-25 QQQ iba 13o y SPY 14o y la regla 12 corria ciega.
CAPTAINS_FIRST = ["QQQ", "SPY", "SMH"]


def captains_first(syms):
    """Capitanes al frente, el resto conserva su orden relativo."""
    return ([s for s in CAPTAINS_FIRST if s in syms]
            + [s for s in syms if s not in CAPTAINS_FIRST])


if DAEMON:
    SYMS = captains_first(SYMS)

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
        self.quote_epoch = 0.0        # no clasificar un print contra una quote rancia
        self.whale_day = ""           # truncado diario del whale file
        self.footprint_day = ""       # cinta COMPLETA para Bid x Ask (los 5 con AllLast)
        self.last_trade_px = 0.0       # tick rule: desempata prints dentro del spread
        self.last_trade_dir = 0
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
            # GUARDA ANTI-FANTASMA (2026-07-20): quote cruzada/vieja del feed
            # (NVDA 203.50/203.95 con px real 206.3, spread 0.22% vs 0.02%
            # normal) disparo alarmas falsas. Rechazar ticks cuyo mid salte
            # >0.5% vs el ultimo mid escrito Y vs el ultimo bar 1m — un salto
            # real siempre aparece tambien en bars/el proximo tick coherente.
            mid = (t.bid + t.ask) / 2.0
            lastmid = getattr(st, "nbbo_mid", 0.0)
            lastbar = st.agg[max(st.agg)][3] if getattr(st, "agg", None) else 0.0
            if lastmid > 0 and abs(mid - lastmid) / lastmid > 0.005 and \
               lastbar > 0 and abs(mid - lastbar) / lastbar > 0.005:
                return                        # fantasma: no escribir
            st.nbbo_mid = mid
            st.bid, st.ask = t.bid, t.ask     # siempre fresco para las ballenas
            st.quote_epoch = now
            if now - st.nbbo_last < 0.25:     # 4/s (era 1/s; orden 2026-07-15
                return                        # "blazing fast" — spread gate fresco)
            st.nbbo_last = now
            # ESCRITURA ATOMICA (patron chart_levels.py): 4/s directo sobre el destino
            # dejaba al lector C++ ver un fichero a medias.
            dst = f"data/nbbo_{st.sym.lower()}.txt"
            tmp = dst + f".tmp{os.getpid()}"
            with open(tmp, "w") as f:
                f.write(f"{now:.0f} {t.bid:.4f} {t.ask:.4f}\n")
            os.replace(tmp, dst)
            if st.sym == "QQQ":
                # historia de ticks para el scalper de ballenas (2026-07-21):
                # append-only, rotacion diaria, ~3MB/dia. Degradacion limpia.
                try:
                    day = time.strftime("%Y%m%d", time.localtime(now))
                    with open(f"data/nbbo_hist_qqq_{day}.txt", "a") as f:
                        f.write(f"{now:.3f} {t.bid:.4f} {t.ask:.4f}\n")
                except Exception:
                    pass
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
        footprint = []
        for t in (getattr(ticker, "tickByTicks", None) or []):
            px = float(t.price or 0); sz = float(t.size or 0)
            if px <= 0 or sz <= 0:
                continue
            ep = t.time.timestamp() if getattr(t, "time", None) else time.time()
            # Lee-Ready/quote rule sobre el NBBO vivo; si el print cae exactamente dentro
            # del spread, tick rule con memoria por simbolo. Cero queda CERO (desconocido),
            # nunca se reparte volumen a un lado inventado. El motor publica classification_pct.
            d = 0
            method = "U"
            eps = max(1e-9, px * 1e-10)
            quote_fresh = st.quote_epoch > 0 and abs(ep - st.quote_epoch) <= 2.0
            if quote_fresh and st.ask > 0 and px >= st.ask - eps:
                d = 1
                method = "Q"
            elif quote_fresh and st.bid > 0 and px <= st.bid + eps:
                d = -1
                method = "Q"
            elif quote_fresh and st.bid > 0 and st.ask > st.bid:
                mid = (st.bid + st.ask) * 0.5
                if px > mid + eps:
                    d = 1; method = "Q"
                elif px < mid - eps:
                    d = -1; method = "Q"
            if d == 0 and st.last_trade_px > 0:
                if px > st.last_trade_px + eps:
                    d = 1; method = "T"
                elif px < st.last_trade_px - eps:
                    d = -1; method = "T"
                else:
                    d = st.last_trade_dir
                    if d:
                        method = "T"
            st.last_trade_px = px
            if d:
                st.last_trade_dir = d
            # EPOCH PX SIZE DIR BID ASK METHOD. SIZE son acciones/contratos, NO dolares.
            # Este fichero es el único input válido del footprint; OHLCV nunca lo sustituye.
            footprint.append(f"{ep:.6f} {px:.6f} {sz:.6f} {d} "
                             f"{st.bid if quote_fresh else 0:.6f} "
                             f"{st.ask if quote_fresh else 0:.6f} {method}\n")
            usd = px * sz
            if usd < WHALE_MIN_USD or px <= 0:
                continue
            lines.append(f"{ep:.0f} {px:.4f} {usd:.0f} {d}\n")
        day = time.strftime("%Y%m%d")
        if footprint:
            mode = "a" if st.footprint_day == day else "w"
            st.footprint_day = day
            with open(f"data/footprint_tape_{st.sym.lower()}.txt", mode) as f:
                f.writelines(footprint)
        if lines:
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

def dollar_vol_per_min(sym, nbars=120):
    """USD/min MEDIANO de data/bars_<sym>_ibkr.txt. None si no se puede medir — jamas 0.0:
    un cero plausible manda al simbolo al fondo del reparto como si no cotizara."""
    p = bars_path(sym)
    try:
        size = os.path.getsize(p)
        if size <= 0:
            return None
        with open(p, "rb") as f:
            f.seek(max(0, size - 96 * nbars))
            rows = f.read().decode(errors="ignore").strip().splitlines()[-nbars:]
        v = []
        for r in rows:
            t = r.split()
            if len(t) >= 6:
                v.append(float(t[4]) * float(t[5]))
        if not v:
            return None
        v.sort()
        return v[len(v) // 2]
    except Exception:
        return None


def tape_order(syms):
    """Reparto DELIBERADO: capitanes primero (regla 12), luego por USD/min MEDIDO de los bars.
    Antes lo decidia el ORDEN DE ARRANQUE — el 2026-07-25 QQQ iba 13o y SPY 14o."""
    dv = {s: dollar_vol_per_min(s) for s in syms}
    rest = [s for s in syms if s not in CAPTAINS_FIRST]
    rest.sort(key=lambda s: (dv[s] is None, -(dv[s] or 0.0), s))
    return [s for s in CAPTAINS_FIRST if s in syms] + rest, dv


_BLIND_SAID_F = "data/tape_blind_said.json"


def _load_blind_said():
    """Persistido en disco (Yunior 2026-07-28: "dice que no ve ballenas, fix eso" — el
    dict en memoria se reiniciaba con CADA relanzamiento del puente y re-anunciaba las
    mismas 25/30 simbolos ciegas cada vez, aunque el limite (cupo IBKR, no cambia en el
    dia) ya se hubiera anunciado antes). Solo el DIA importa, no el proceso."""
    try:
        d = json.load(open(_BLIND_SAID_F))
        if d.get("day") == time.strftime("%Y%m%d"):
            return d.get("said", {})
    except Exception:
        pass
    return {}


def _save_blind_said(said):
    try:
        tmp = _BLIND_SAID_F + f".tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"day": time.strftime("%Y%m%d"), "said": said}, f)
        os.replace(tmp, _BLIND_SAID_F)
    except Exception:
        pass


_blind_said = _load_blind_said()   # sym -> dia ya cantado


def declare_blind(syms, why):
    """Un simbolo sin cinta SALE DECLARADO: data/tape_blind.txt + voz + banner + log.
    Un whale_<sym>.txt de 0 bytes es indistinguible de 'no hay ballenas' — el patron
    prohibido de la casa (convertir 'no se' en 'no hay') aplicado al flujo."""
    now = time.time()
    tmp = BLIND_F + f".tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(f"# EPOCH SYM MOTIVO — cinta tick-by-tick AUSENTE "
                f"(cupo IBKR medido: {TAPE_MAX} contratos por CUENTA)\n")
        for s in sorted(syms):
            f.write(f"{now:.0f} {s} {why}\n")
    os.replace(tmp, BLIND_F)
    day = time.strftime("%Y%m%d")
    fresh = sorted(s for s in syms if _blind_said.get(s) != day)
    if not fresh:
        return
    for s in fresh:
        _blind_said[s] = day
    _save_blind_said(_blind_said)
    msg = (f"CINTA CIEGA: {len(fresh)} de la flota sin tape tick-by-tick "
           f"({' '.join(fresh)}) — sus ballenas NO se ven, no es que no haya")
    voz = f"No veo las ballenas de {len(fresh)} acciones."
    print(msg, file=sys.stderr)
    subprocess.Popen([_OSA, "-e",
                      f'display notification "{voz}" with title "🕳 CINTA CIEGA" '
                      f'sound name "ProAlarm"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/bin/bash", "scripts/speak.sh", "DANGER", voz],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import notify_short; notify_short.push("🕳 CINTA CIEGA", voz)
    lt = time.localtime()
    d = os.path.join(ROOT, "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | 🕳 CINTA CIEGA | {msg}\n")


def tape_subscribe(ib, syms, dwell=6.0):
    """Suscribe la cinta de <syms> en UNA conexion; devuelve {sym: Ticker} de los concedidos.
    La denegacion se atribuye por el CONTRATO del error, no por ventana de tiempo: el 10190 de
    la peticion k aterriza dentro de la ventana de k+1 y cancelaba suscripciones SANAS
    (medido 2026-07-27: la ventana daba 6 falsos ON de 25, con CERO bytes escritos)."""
    denied = {}
    def on_err(reqId, code, msg, contract):
        if code in (10190, 322, 102, 200, 354, 420) and contract is not None:
            sym = getattr(contract, "symbol", "")
            if sym:
                denied[sym] = code
    ib.errorEvent += on_err
    asked = {}
    try:
        for s in syms:
            try:
                c = Stock(s, "SMART", "USD")
                ib.qualifyContracts(c)
                if not c.conId:
                    print(f"{s}: sin conId (contrato inexistente) — SIN CINTA", file=sys.stderr)
                    continue
                tbt = ib.reqTickByTickData(c, "AllLast", 0, False)
                tbt.updateEvent += make_on_whale(STATES[s])
                asked[s] = (c, tbt)
                ib.sleep(0.4)
            except Exception as e:
                print(f"{s}: whales sub fallo ({e})", file=sys.stderr)
        ib.sleep(dwell)                  # deja aterrizar los 10190 antes de juzgar
    finally:
        ib.errorEvent -= on_err
    granted = {}
    for s, (c, tbt) in asked.items():
        if s in denied:
            try: ib.cancelTickByTickData(c, "AllLast")
            except Exception: pass
            print(f"{s}: whales tick-by-tick DENEGADO (err {denied[s]} — cap "
                  f"cupo {TAPE_MAX} por CUENTA)", file=sys.stderr)
        else:
            STATES[s].whales_on = True
            TAPE["granted"].add(s)
            granted[s] = tbt
            print(f"{s}: whales tick-by-tick ON (>= {WHALE_MIN_USD:.0f} USD)", file=sys.stderr)
    return granted


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
        # la cinta ya no se pide aqui: va en bloque (tape_subscribe) cuando estan todos
        # los bars/NBBO arriba, para poder atribuir los 10190 por contrato.
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


def prune_footprint(st):
    """Acota la cinta completa a 4 h. El motor C++ conserva 240 minutos y detecta el
    rewrite por tamaño; no necesitamos un fichero diario de millones de prints en data/.
    El histórico profundo exacto pertenece a Databento, no a este ring live."""
    p = f"data/footprint_tape_{st.sym.lower()}.txt"
    try:
        if not os.path.exists(p) or os.path.getsize(p) < 16 * 1024 * 1024:
            return
        cut = time.time() - 4 * 3600
        keep = []
        with open(p) as f:
            for ln in f:
                try:
                    if float(ln.split(" ", 1)[0]) >= cut:
                        keep.append(ln)
                except (ValueError, IndexError):
                    continue
        tmp = p + f".tmp{os.getpid()}"
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
    TAPE["granted"] = set()


def run_daemon():
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=20)
    ib.RequestTimeout = 20   # causa raiz confirmada en caza de bugs 2026-07-28 (opt_whale_watch.py):
                              # RequestTimeout=0 por defecto cuelga qualifyContracts para siempre si TWS no responde
    ib.reqMarketDataType(1)                  # 1 = REALTIME. Delayed PROHIBIDO.
    ib.errorEvent += lambda r, c, m, ct=None, *a: (
        c == 1101 and _resub_all(ib, "Error 1101 data-lost"))
    order, dv = tape_order(SYMS)
    print(f"ibkr fleet daemon: TWS {HOST}:{PORT}, {len(SYMS)} syms "
          f"(bars 5s->1m + NBBO SIP + whales tick-by-tick + overnight)",
          file=sys.stderr)
    print("cinta por USD/min medido: " + "  ".join(
        f"{s}={'sin-medir' if dv[s] is None else format(dv[s], '.0f')}" for s in order),
        file=sys.stderr)
    last_prune = 0.0
    last_resub = 0.0
    while ib.isConnected():
        for st in STATES.values():
            subscribe_sym(ib, st)
        if not TAPE["granted"] and all(st.subs or st.blocked_until for st in STATES.values()):
            for s_, tbt_ in tape_subscribe(ib, order[:TAPE_MAX]).items():
                STATES[s_].subs.append(tbt_)
            declare_blind([s for s in SYMS if s not in TAPE["granted"]],
                          f"cupo_cuenta_{TAPE_MAX}_contratos")
        if time.time() - last_prune > 600:
            last_prune = time.time()
            for st in STATES.values():
                if st.whales_on:
                    prune_whales(st)
                    prune_footprint(st)
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
    ib.RequestTimeout = 20   # ver run_daemon() — causa raiz confirmada en caza de bugs 2026-07-28
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
        if st.subs and not TAPE["granted"]:
            tape_subscribe(ib, [st.sym])
        ib.sleep(15)
    raise ConnectionError("TWS desconectado")

def _main():
    """Bucle de reintento. Con guarda __main__ (2026-07-25) para que el modulo se pueda
    IMPORTAR en tests sin arrancar el daemon: antes un `import` intentaba conectar a TWS y
    se colgaba 15s por vuelta. Nadie importa este modulo en produccion (verificado con grep),
    y los lanzadores lo ejecutan siempre como script, asi que el comportamiento no cambia."""
    while True:
        try:
            run_daemon() if DAEMON else run_single()
        except SystemExit:
            raise
        except Exception as e:
            print(f"ibkr bridge CAIDO: {e} — reintento en 15s (¿TWS en {PORT}?)",
                  file=sys.stderr)
            for st in STATES.values():
                st.subs = []; st.blocked_until = 0; st.whales_on = False
            TAPE["granted"] = set()
            time.sleep(15)


if __name__ == "__main__":
    _main()
