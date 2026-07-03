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
names CORE: skhynix, samsung, kodex200. Satelites HBM (2026-07-27, cualificados con
precio mdt=1 en vivo): hanmi, wonikips, hpsp, dbhitek, leeno, solbrain, isc.
Los satelites NO estan en data/fleet.txt: no votan MANADA ni tienen bot.

reqMarketDataType(1) fijo — delayed PROHIBIDO (orden #6). Si KRX pierde permiso
(no deberia: sub waived) se marca y reintenta cada 10 min, gritando a stderr.

Puerto RESUELTO, no adivinado (2026-07-26): resolve_port() sondea env IBKR_PORT y
los puertos de IB GATEWAY (4001 live / 4002 paper), y registra cual eligio. TWS
(7496/7497) queda FUERA del sondeo por orden de Yunior 2026-07-27 "only ib gateway".
Ningun puerto vivo o barras rancias con KRX abierto = voz DANGER, nunca silencio.

Python (ib_insync) solo porque el SDK C++ de IB no esta instalado; productor
I/O-bound — la matematica de senal sigue en C++.

Uso: korea_bar_bridge.py [--daemon]   (por defecto daemon)
"""
import json, os, subprocess, sys, time
from datetime import timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ib_mode  # noqa: E402
import overnight_feed as ovf  # noqa: E402   krx_boundary vive ahi: UNA sola definicion
from ib_insync import IB, Contract, util  # noqa: E402

import os as _os  # portero de banners
_OSA = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "osa_gate")  # respeta data/notify_off

HOST = "127.0.0.1"
CANDIDATE_PORTS = [4001, 4002]   # SOLO IB Gateway (orden Yunior 2026-07-27); TWS 7496/7497 fuera
CLIENT_ID = 86                               # unico vs fleet(84)/single(83)
RETRY_ENTITLEMENT_S = 600
RETRY_S = 15
FAILS_LOUD = 4                               # 4 x RETRY_S = ~60s mudo como techo
STALE_MAX_S = 300                            # mismo umbral que el stall-watchdog de run()
NO_PERM_ERRORS = {101, 420, 10089, 10090, 354}   # 101 = max tickers: retrocede, no revienta

# name -> (conId, symbol legible). Contratos KRX verificados en vivo 2026-07-12.
# El indice KOSPI directo (K200) NO tiene sub API (error 354); IBKR solo puede dar el ETF.
# 2026-08-03: el ETF dejo de llamarse "kospi". NO es el indice — ese dia cerro -8,93% contra
# -5,12% del KOSPI. Los indices reales los sirve korea_naver_bridge como kospi/kospi200.
KOREA = {
    "skhynix": (17382246, "000660"),         # SK Hynix
    "samsung": (17382528, "005930"),         # Samsung Electronics
    "kodex200": (76006841, "069500"),        # KODEX 200 ETF (replica el KOSPI 200, no lo ES)
    # Cadena de suministro HBM/memoria, conIds cualificados con precio mdt=1 en vivo
    # 2026-07-27 12:5x KST. Hanmi (bonders HBM) se mueve ANTES que Hynix/Samsung.
    # NO entran en data/fleet.txt: no votan MANADA, no tienen bot ni keepalive.
    "hanmi":    (44631844,  "042700"),       # Hanmi Semiconductor
    "wonikips": (353068652, "240810"),       # Wonik IPS
    "hpsp":     (616507112, "403870"),       # HPSP
    "dbhitek":  (17382279,  "000990"),       # DB HiTek
    "leeno":    (371878942, "058470"),       # Leeno Industrial
    "solbrain": (489366191, "357780"),       # Solbrain
    "isc":      (611160155, "095340"),       # ISC
}
CORE = ("skhynix", "samsung", "kodex200")    # los que priman si IBKR raciona lineas


def _publish_korea_syms():
    """Fuente unica para chart_bridge.py (orden Yunior 2026-07-27, prohibido hardcodear):
    escribe data/korea_syms.txt con las claves de KOREA. tmp+os.replace, atomico."""
    dst = os.path.join(ROOT, "data", "korea_syms.txt")
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(sorted(n.upper() for n in KOREA)) + "\n")
    os.replace(tmp, dst)
    # ...y los conId, para que el scroll del chart pida historia del KRX correcto
    dst = os.path.join(ROOT, "data", "korea_contracts.txt")
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        for n in sorted(KOREA):
            cid, krx = KOREA[n]
            f.write(f"{n.upper()} {cid} {krx}\n")
    os.replace(tmp, dst)
    # ...y el CORE aparte: overnight_pump_study lo lee en vez de duplicar la tupla
    dst = os.path.join(ROOT, "data", "korea_core.txt")
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(CORE) + "\n")
    os.replace(tmp, dst)


_publish_korea_syms()


class SymState:
    def __init__(self, name):
        self.name = name
        self.agg = {}                         # minute_ep -> [o,h,l,c,v]
        self.last_emitted = 0.0
        self.nbbo_last = 0
        self.blocked_until = 0.0
        self.subs = []

STATES = {n: SymState(n) for n in KOREA}

def bars_path(name):
    return os.path.join(ROOT, "data", f"bars_{name}.txt")

def nbbo_path(name):
    return os.path.join(ROOT, "data", f"nbbo_{name}.txt")

def emit(st, ep, o, h, l, c, v):
    if ep <= st.last_emitted or c <= 0:
        return
    st.last_emitted = ep
    line = f"{ep:.0f} {o:.4f} {h:.4f} {l:.4f} {c:.4f} {v:.0f}\n"
    with open(bars_path(st.name), "a") as f:
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
            with open(nbbo_path(st.name), "w") as f:
                f.write(f"{now:.0f} {t.bid:.4f} {t.ask:.4f}\n")
        elif t.last and t.last > 0:
            # KODEX 200 (kodex200): IBKR da trades REALTIME (mdt=1) pero CERO book
            # (bid/ask=-1 siempre — probado en vivo 2026-07-20 09:07 KST; las
            # acciones samsung/skhynix si tienen BBO). Fallback honesto: last
            # trade como bid=ask -> mid exacto, spread 0. NO es delayed.
            st.nbbo_last = now
            with open(nbbo_path(st.name), "w") as f:
                f.write(f"{now:.0f} {t.last:.4f} {t.last:.4f}\n")
    return on_tick

def krx_market():
    """Sesion KRX (horario de ovf: FUENTE UNICA) KST (UTC+9, sin DST), lun-vie coreano.
    Con 5 min de gracia a cada lado para el stall-watchdog."""
    lt = time.gmtime(time.time() + 9 * 3600)
    mins = lt.tm_hour * 60 + lt.tm_min
    return lt.tm_wday < 5 and \
        ovf.KRX_OPEN_H * 60 + ovf.KRX_OPEN_M - 5 <= mins <= ovf.KRX_CLOSE_H * 60 + ovf.KRX_CLOSE_M + 5

_last_banner = 0.0
_last_resub = 0.0

def loud(title, msg, sound="ProAlarm", prio="DANGER", voz=None):
    """Fail LOUD (ley #2): voz speak.sh + banner Mac + espejo Desktop, throttle 10 min.
    La flota korea no tiene reader C++ que grite por ella — el bridge grita."""
    global _last_banner
    print(f"{title}: {msg}", file=sys.stderr)
    if time.time() - _last_banner < 600:
        return
    _last_banner = time.time()
    esc = lambda s: s.replace("\\", "").replace('"', "'")
    corto = voz or msg
    try:
        subprocess.Popen(["/bin/bash", os.path.join(ROOT, "scripts", "speak.sh"),
                          prio, corto], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen([_OSA, "-e",
                          f'display notification "{esc(corto)}" with title '
                          f'"{esc(title)}" sound name "{sound}"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lt = time.localtime()
        d = os.path.join(ROOT, "data", "trading-signals")
        os.makedirs(d, exist_ok=True)
        with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt",
                  "a") as f:
            f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | "
                    f"{title} | {msg}\n")
        import notify_short; notify_short.push(title, corto)
    except Exception:
        pass

def resolve_port():
    """Primer puerto que ACEPTA TCP. Orden: env IBKR_PORT, los del modo
    (data/ib_mode.txt), y el resto de candidatos. None si ninguno — jamas un
    puerto 'plausible' que solo sirve para volver a fallar."""
    env = os.environ.get("IBKR_PORT") or os.environ.get("IB_PORT")
    env_p = int(env) if env and env.isdigit() else None
    modo = [p for p in ib_mode._ports_for(ib_mode.get_mode()) if p in CANDIDATE_PORTS]
    cands = []
    for p in ([env_p] if env_p else []) + modo + CANDIDATE_PORTS:
        if p not in cands:
            cands.append(p)
    for p in cands:
        if ib_mode._listening(p):
            por = "IBKR_PORT explicito" if p == env_p else \
                  ("gateway del modo " + ib_mode.get_mode() if p in modo else "sondeo de candidatos")
            print(f"korea bridge: puerto {p} ELEGIDO ({por}); probados {cands}",
                  file=sys.stderr)
            return p
    loud("🇰🇷 KRX BRIDGE SIN GATEWAY",
         f"ningun puerto IBKR acepta conexion {cands} — Gateway/TWS caido",
         voz="Puente de Corea sin Gateway.")
    return None

def newest_bar_epoch(names=CORE):
    """Epoch del bar mas reciente entre los ficheros KRX. None si ninguno legible.
    Por defecto solo CORE: los satelites son ilíquidos y su silencio no es averia."""
    best = None
    for name in names:
        try:
            with open(bars_path(name), "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(-min(4096, f.tell()), os.SEEK_END)
                lines = f.read().decode("utf-8", "replace").strip().splitlines()
            ep = float(lines[-1].split()[0])
        except Exception:
            continue
        if best is None or ep > best:
            best = ep
    return best

def archive_bars_before_warmup(name):
    """Archivar a history/<date>/bars/ antes de truncar. Fecha derivada de timestamps.
    Atomicidad: tmp+os.replace. Retorna False si falla (warmup NO trunca entonces)."""
    path = bars_path(name)
    if not os.path.exists(path):
        return True
    try:
        with open(path, "r") as f:
            lines = f.readlines()
        if not lines:
            return True
        try:
            first_epoch = float(lines[0].split()[0])
            session_date = time.strftime("%Y-%m-%d", time.localtime(first_epoch))
        except (IndexError, ValueError):
            print(f"{name}: archive — no puedo extraer epoch, saltando",
                  file=sys.stderr)
            return False
        hist_dir = os.path.join(ROOT, "data", "history", session_date, "bars")
        os.makedirs(hist_dir, exist_ok=True)
        dst = os.path.join(hist_dir, f"{name}_krx.txt")
        tmp = dst + ".tmp"
        with open(tmp, "w") as o:
            o.writelines(lines)
        os.replace(tmp, dst)
        print(f"{name}: {len(lines)} barras archivadas a {session_date}/bars/{name}_krx.txt",
              file=sys.stderr)
        return True
    except Exception as e:
        print(f"{name}: archive FALLO — {e} — NO truncando", file=sys.stderr)
        return False

def prevclose_path():
    return os.path.join(ROOT, "data", ovf.PREVCLOSE_NAME)

def read_bar_rows(path):
    """[(epoch, close)] de un fichero de barras. [] si no existe o no se puede leer."""
    rows = []
    try:
        with open(path) as f:
            for ln in f:
                p = ln.split()
                if len(p) < 5:
                    continue
                try:
                    rows.append((float(p[0]), float(p[4])))
                except ValueError:
                    continue
    except Exception:
        return []
    return rows

def prev_close_from_rows(rows, boundary):
    """(close, epoch) de la ULTIMA barra anterior al boundary KRX. None si no hay ninguna:
    sin barra previa NO hay referencia — jamas el open ni 0.0 (regla #2)."""
    best = None
    for ep, c in rows:
        if ep < boundary and c > 0 and (best is None or ep > best[1]):
            best = (c, ep)
    return best

def update_prev_close(name, rows, boundary, verbose=True):
    """Persiste el cierre de la sesion KRX ANTERIOR en data/korea_prevclose.json (atomico).
    Sin barra utilizable no escribe entrada; nunca retrocede a una barra mas vieja."""
    pc = prev_close_from_rows(rows, boundary)
    if pc is None:
        if verbose:
            print(f"{name}: sin barra pre-boundary — prev_close NO escrito", file=sys.stderr)
        return None
    close, ep = pc
    path = prevclose_path()
    try:
        with open(path) as f:
            cur = json.load(f)
        if not isinstance(cur, dict):
            cur = {}
    except Exception:
        cur = {}
    old = cur.get(name)
    if isinstance(old, dict) and float(old.get("epoch") or 0) >= ep:
        return old
    entry = {"close": round(float(close), 4), "epoch": int(ep),
             "session": ovf.krx_session_date(ep)}
    cur[name] = entry
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f)
    os.replace(tmp, path)
    print(f"{name}: prev_close {entry['close']} ({entry['session']}) persistido",
          file=sys.stderr)
    return entry

_pc_boundary = 0.0
_pc_pending = set()

def maybe_roll_prev_close(names=CORE, now=None):
    """Al cruzar el boundary KRX el fichero vivo aun contiene la sesion anterior: fijar
    ahi el prev_close antes de que warmup lo trunque. Un fallo transitorio (fichero a medio
    escribir -> read_bar_rows []) NO quema el boundary: el nombre queda PENDIENTE y se
    reintenta en cada vuelta hasta que se persiste. True si hubo roll de boundary."""
    global _pc_boundary, _pc_pending
    b = ovf.krx_boundary(now)
    nuevo = b != _pc_boundary
    if nuevo:
        _pc_boundary = b
        _pc_pending = set(names)
    elif not _pc_pending:
        return False
    for name in sorted(_pc_pending.intersection(names)):
        if update_prev_close(name, read_bar_rows(bars_path(name)), b,
                             verbose=nuevo) is not None:
            _pc_pending.discard(name)
    return nuevo

def freshness_guard(now=None):
    """GRITA si KRX esta abierto y el ultimo bar pasa de STALE_MAX_S. True si grito."""
    if not krx_market():
        return False
    now = time.time() if now is None else now
    ep = newest_bar_epoch()
    if ep is not None and now - ep <= STALE_MAX_S:
        return False
    cuanto = "sin ninguna barra" if ep is None else f"{(now - ep) / 60:.0f} min rancias"
    loud("🇰🇷 BARRAS COREA RANCIAS",
         f"KRX abierto y las barras estan {cuanto} — el puente no escribe",
         voz="Barras de Corea rancias.")
    return True

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
    """Archivar barras existentes antes de truncar; luego cargar histórico 1 día."""
    conId, sym = KOREA[st.name]
    boundary = ovf.krx_boundary()
    old_rows = read_bar_rows(bars_path(st.name))   # el fichero VIVO aun tiene la sesion previa
    if not archive_bars_before_warmup(st.name):
        print(f"{st.name}: saltando warmup por fallo en archivado", file=sys.stderr)
        return
    try:
        c = Contract(conId=conId, exchange="KRX"); ib.qualifyContracts(c)
        hist = ib.reqHistoricalData(c, "", "1 D", "1 min", "TRADES",
                                    useRTH=False, formatDate=2)
    except Exception as e:
        print(f"{st.name}: warmup fallo ({e})", file=sys.stderr); return
    n = 0
    rows = list(old_rows)
    with open(bars_path(st.name), "w") as f:
        for b in hist:
            if not (b.close and b.close > 0):
                continue
            ep = b.date.timestamp(); m = ep - ep % 60
            v = float(b.volume) if b.volume and b.volume > 0 else 0
            f.write(f"{m:.0f} {b.open:.4f} {b.high:.4f} {b.low:.4f} {b.close:.4f} {v:.0f}\n")
            st.last_emitted = m; n += 1
            rows.append((m, float(b.close)))
    if update_prev_close(st.name, rows, boundary) is not None:
        _pc_pending.discard(st.name)               # persistido: el reintento del roll ya no insiste
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
    global _fails
    port = resolve_port()
    if port is None:
        raise ConnectionError("ningun puerto IBKR escucha")
    ib = IB()
    ib.connect(HOST, port, clientId=CLIENT_ID, readonly=True, timeout=20)
    ib.RequestTimeout = 20   # causa raiz 2026-07-28 (opt_whale_watch.py): sin esto, qualifyContracts cuelga para siempre si TWS no responde
    _fails = 0
    ib.reqMarketDataType(1)                   # 1 = REALTIME. Delayed PROHIBIDO.
    # Error 1101 (data lost tras flap) -> resub inmediato, igual que el daemon NA
    ib.errorEvent += lambda r, c, m, ct=None, *a: (
        c == 1101 and resub_all(ib, "Error 1101 data-lost"))
    print(f"korea bridge: TWS {HOST}:{port}, {len(KOREA)} KRX syms "
          f"(core {'+'.join(CORE)} + {len(KOREA)-len(CORE)} satelites HBM, "
          f"bars 5s->1m + NBBO)", file=sys.stderr)
    maybe_roll_prev_close()
    for st in STATES.values():
        warmup(ib, st)
    while ib.isConnected():
        maybe_roll_prev_close()
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
                 f"resuscribiendo (skhynix/samsung/kodex200)",
                 voz="Corea sin datos. Reconectando.")
            resub_all(ib, f"stall {time.time() - newest:.0f}s sin bars")
        freshness_guard()   # cubre el hueco del stall-watchdog: conectado y SIN suscribir
        ib.sleep(RETRY_S)
    raise ConnectionError("TWS desconectado")

_fails = 0

def main():
    global _fails
    os.chdir(ROOT)
    while True:
        try:
            run()
        except Exception as e:
            _fails += 1
            print(f"korea bridge CAIDO ({_fails}): {e} — reintento en {RETRY_S}s",
                  file=sys.stderr)
            if _fails >= FAILS_LOUD:
                loud("🇰🇷 KRX BRIDGE CAIDO",
                     f"{_fails} intentos fallidos seguidos ({_fails * RETRY_S}s): {e}",
                     voz="Puente de Corea caído.")
            for st in STATES.values():
                st.subs = []; st.blocked_until = 0
        maybe_roll_prev_close()   # sin Gateway el boundary igual rueda: no perder la referencia
        freshness_guard()
        time.sleep(RETRY_S)

if __name__ == "__main__":
    main()
