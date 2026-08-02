#!/usr/bin/env python3
"""overnight_feed.py — puente TONTO: NQ/ES (yfinance) + Corea (bars locales) + sentimiento X
-> data/overnight_ctx.json atomico cada 120s, solo fuera de RTH US. Cero computo de senal.
Regla #3: dato que falla = null, jamas 0.0. Uso: [--once] para una sola escritura."""
import glob
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gex_core

TZ = ZoneInfo("America/Toronto")
KST = ZoneInfo("Asia/Seoul")
OUT = os.path.join(REPO, "data", "overnight_ctx.json")
SENT_DIR = os.path.join(REPO, "data", "x_sentiment")
PREVCLOSE_NAME = "korea_prevclose.json"           # lo escribe korea_bar_bridge.update_prev_close
PREVCLOSE = os.path.join(REPO, "data", PREVCLOSE_NAME)
CTX_JSONL = os.path.join(REPO, "data", "history", "overnight_ctx.jsonl")
CTX_MAX_LINES = 20000                             # ~2 meses de noches; el jsonl no rota solo
HOLIDAYS_PATH = os.path.join(REPO, "data", "krx_holidays.txt")
KOREA = {"hynix_pct": "skhynix", "samsung_pct": "samsung", "kospi_pct": "kospi"}
LOOP_S, RTH_NAP_S, SENT_MAX_AGE_S = 120, 300, 7200
# Horario KRX: FUENTE UNICA (la leen korea_bar_bridge.krx_market y overnight_pump_study)
KRX_OPEN_H, KRX_OPEN_M = 9, 0
KRX_CLOSE_H, KRX_CLOSE_M = 15, 30
KRX_GAP_MAX_DAYS = 6       # cierre mas largo del KRX (Seollal/Chuseok + fin de semana)
KRX_HIST_LOOKBACK = 10     # carpetas data/history/<fecha> que se miran hacia atras


def fut_pct(sym):
    try:
        import yfinance as yf
        fi = yf.Ticker(sym).fast_info
        last, prev = fi["last_price"], fi["previous_close"]
        if last and prev:
            return round((last - prev) / prev * 100.0, 4)
        return None
    except Exception:
        return None


def krx_boundary(now=None):
    # apertura KRX mas reciente = 09:00 KST (= 20:00 ET en EDT pero 19:00 en EST: se ancla en KST)
    now = now or datetime.now(TZ)
    k = now.astimezone(KST)
    b = k.replace(hour=KRX_OPEN_H, minute=KRX_OPEN_M, second=0, microsecond=0)
    if b > k:
        b -= timedelta(days=1)
    return b.timestamp()


def krx_session_date(epoch):
    """Fecha KST de la sesion KRX a la que pertenece `epoch` (KRX 09:00-15:30 KST)."""
    return datetime.fromtimestamp(epoch, KST).date().isoformat()


_hol_cache = {"key": None, "days": frozenset()}


def krx_holidays(path=None):
    """Festivos KRX de data/krx_holidays.txt (una fecha ISO por linea). Lunares (Seollal/
    Chuseok) y sustitutos NO son derivables: se tabulan por año, igual que exchange_calendars
    precomputa XKRX. Tabla ausente -> frozenset() y el año queda 'no cubierto' (ver ref_session_ok)."""
    p = path or HOLIDAYS_PATH
    try:
        st = os.stat(p)
    except OSError:
        return frozenset()
    key = (p, st.st_mtime, st.st_size)
    if _hol_cache["key"] != key:
        days = set()
        try:
            with open(p) as f:
                for ln in f:
                    ln = ln.split("#")[0].strip()
                    if len(ln) == 10 and ln[4] == "-" and ln[7] == "-":
                        days.add(ln)
        except OSError:
            return frozenset()
        _hol_cache["key"], _hol_cache["days"] = key, frozenset(days)
    return _hol_cache["days"]


def krx_year_covered(year, path=None):
    """True si la tabla de festivos tiene al menos una fecha de ese año."""
    return any(d.startswith(f"{year:04d}-") for d in krx_holidays(path))


def prev_krx_session_date(boundary, path=None):
    """Fecha KST de la sesion inmediatamente ANTERIOR a la que abre en `boundary`:
    salta fin de semana Y festivos KRX tabulados."""
    hol = krx_holidays(path)
    d = datetime.fromtimestamp(boundary + 3600, KST).date() - timedelta(days=1)
    for _ in range(10):                           # tope: ni Seollal cierra 10 dias seguidos
        if d.weekday() < 5 and d.isoformat() not in hol:
            break
        d -= timedelta(days=1)
    return d.isoformat()


def ref_session_ok(session, boundary, path=None):
    """(aceptable, degradada) para una referencia de la sesion `session`. Se acepta si es la
    sesion KRX anterior mas RECIENTE conocida; si el año del boundary no esta en la tabla de
    festivos, se acepta la mas reciente dentro de KRX_GAP_MAX_DAYS y se marca DEGRADADA
    (etiqueta _gap en el src) — un festivo no tabulado no puede tirar una referencia buena."""
    cur = krx_session_date(boundary + 3600)
    if not session or session >= cur:
        return False, False
    if session >= prev_krx_session_date(boundary, path):
        return True, False
    if krx_year_covered(int(cur[:4]), path):
        return False, False
    dias = (date.fromisoformat(cur) - date.fromisoformat(session)).days
    return (0 < dias <= KRX_GAP_MAX_DAYS), True


def load_prevclose(name, path=None):
    """Entrada de data/korea_prevclose.json para `name`. None si falta o esta corrupta."""
    try:
        with open(path or PREVCLOSE) as f:
            j = json.load(f)
        e = j.get(name)
        if not isinstance(e, dict):
            return None
        c, ep, s = e.get("close"), e.get("epoch"), e.get("session")
        if not c or float(c) <= 0 or ep is None or not s:
            return None
        return {"close": float(c), "epoch": float(ep), "session": str(s)}
    except Exception:
        return None


def hist_ref(name, boundary):
    """(close, epoch, sesion) de la ULTIMA barra archivada anterior al boundary en
    data/history/<fecha>/bars/<name>_krx.txt. Tercera fuente: arranque en frio a mitad de
    sesion (warmup ya trunco bars_*.txt y el proceso nuevo no tiene prev_close). None si nada."""
    pat = os.path.join(REPO, "data", "history", "*", "bars", f"{name}_krx.txt")
    best = None
    # el archivador corta por dia ET y una sesion KRX cae a caballo de dos carpetas (y se
    # solapan): el maximo se busca en TODAS, no en la primera carpeta que tenga algo
    for path in sorted(glob.glob(pat), reverse=True)[:KRX_HIST_LOOKBACK]:
        try:
            with open(path) as f:
                for ln in f:
                    p = ln.split()
                    if len(p) < 5:
                        continue
                    try:
                        t, c = float(p[0]), float(p[4])
                    except ValueError:
                        continue
                    if t < boundary and c > 0 and (best is None or t > best[1]):
                        best = (c, t)
        except OSError:
            continue
    if best is None:
        return None
    return best[0], best[1], krx_session_date(best[1])


def korea_pct(name, boundary):
    """(pct de la sesion KRX en curso, fuente de la referencia). Referencia por orden:
    (1) ultima barra pre-boundary del fichero vivo, (2) prev_close persistido, (3) barra
    archivada en data/history — y solo si pertenece a la sesion KRX anterior mas reciente
    conocida. Sin referencia honesta -> (None, None). Jamas 0.0 (regla #2)."""
    try:
        ref = last = None
        last_t = 0.0
        try:
            with open(os.path.join(REPO, "data", f"bars_{name}.txt")) as f:
                for ln in f:
                    p = ln.split()
                    if len(p) < 5:
                        continue
                    t, c = float(p[0]), float(p[4])
                    if t < boundary:
                        ref = c
                    last, last_t = c, t
        except FileNotFoundError:
            return None, None
        src = "bars" if ref else None
        if not ref:
            pc = load_prevclose(name)
            cands = [("prevclose", lambda: (pc["close"], pc["epoch"], pc["session"]) if pc else None),
                     ("hist", lambda: hist_ref(name, boundary))]   # perezoso: el glob solo si hace falta
            for etiqueta, getter in cands:
                cand = getter()
                if not cand:
                    continue
                c, ep, ses = cand
                if ep >= boundary or not c or c <= 0:
                    continue
                ok, degradada = ref_session_ok(ses, boundary)
                if ok:
                    ref, src = c, etiqueta + ("_gap" if degradada else "")
                    break
        if ref and last is not None and last_t >= boundary:
            return round((last - ref) / ref * 100.0, 4), src
        return None, None
    except Exception:
        return None, None


def sentiment():
    # tally con el clasificador YA existente del repo (x_sentiment.classify); solo para why[]
    try:
        files = [os.path.join(SENT_DIR, f) for f in os.listdir(SENT_DIR) if f.endswith(".json")]
        if not files:
            return None
        newest = max(files, key=os.path.getmtime)
        if time.time() - os.path.getmtime(newest) > SENT_MAX_AGE_S:
            return None
        with open(newest) as f:
            j = json.load(f)
        import x_sentiment as xs
        ko = any("가" <= ch <= "힣" for ch in j.get("query", ""))
        pos_kw, neg_kw = (xs.POS_KO, xs.NEG_KO) if ko else (xs.POS_EN, xs.NEG_EN)
        p, n, _ = xs.classify([t.get("text", "") for t in (j.get("data") or [])], pos_kw, neg_kw)
        return {"tag": os.path.basename(newest).rsplit("_", 2)[0],
                "n": j.get("n"), "pos": p, "neg": n}
    except Exception:
        return None


def archive_ctx(ctx, path=None, max_lines=CTX_MAX_LINES):
    """Append 1 linea/ciclo (unica forma de MEDIR luego el patron de la madrugada), topado a
    max_lines como notify_short.py: nadie rota este jsonl y crece 240 lineas/noche."""
    p = path or CTX_JSONL
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(ctx) + "\n")
        if os.path.getsize(p) > max_lines * 120:   # sonda barata: solo cuenta lineas si puede pasarse
            with open(p) as f:
                lines = f.readlines()
            if len(lines) > max_lines:
                tmp = p + f".tmp{os.getpid()}"
                with open(tmp, "w") as f:
                    f.writelines(lines[-max_lines:])
                os.replace(tmp, p)
        return True
    except Exception as e:
        print(f"overnight_feed: archivo jsonl fallo — {e}", file=sys.stderr)
        return False


def build():
    ctx = {"ts": time.time(), "nq_pct": fut_pct("NQ=F"), "es_pct": fut_pct("ES=F")}
    b = krx_boundary()
    for key, name in KOREA.items():
        pct, src = korea_pct(name, b)
        ctx[key] = pct
        ctx[key.replace("_pct", "_ref_src")] = src   # "bars"|"prevclose"|null: "no se" != "se, y es 0"
    ctx["sent"] = sentiment()
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ctx, f)
    os.replace(tmp, OUT)
    archive_ctx(ctx)
    return ctx


def main():
    once = "--once" in sys.argv
    while True:
        if gex_core.in_rth():
            if once:
                print("RTH: no toca", flush=True)
                return
            time.sleep(RTH_NAP_S)
            continue
        print(json.dumps(build()), flush=True)
        if once:
            return
        time.sleep(LOOP_S)


if __name__ == "__main__":
    main()
