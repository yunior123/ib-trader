#!/usr/bin/env python3
"""overnight_pump_study.py — MEDIR el patron "~12:30 AM ET se bombea" (Yunior), no afirmarlo.
Lote FUERA de sesion. Unica fuente que cubre 20:00-03:59 ET: las barras KRX archivadas en
data/history/<fecha>/bars/{kospi,samsung,skhynix}_krx.txt (poly_bars solo tiene 04:00-19:59 ET,
histograma comprobado 2026-08-02 -> el pump de las 00:30 NO es medible con trades.db).
Retorno por franja de 30 min desde la apertura KRX (09:00 KST = 20:00 ET) + Wilson.
Se NIEGA a publicar probabilidad con n < 30 (doctrina measured-probability).
Salida atomica a data/overnight_pump_study.json.\nModo --us: mide el overnight US con los futuros NQ/ES de overnight_feed (la fuente que\nSI cubre las 00:30 ET) -> data/overnight_pump_us.json.\nUso: [--us [--campo nq_pct|es_pct]] [--min-n N] [--print]"""
import glob
import json
import math
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

KST = ZoneInfo("Asia/Seoul")
TZ = ZoneInfo("America/Toronto")
HISTORY = os.path.join(REPO, "data", "history")
OUT = os.path.join(REPO, "data", "overnight_pump_study.json")
SYMS = ("kospi", "samsung", "skhynix")
MIN_N = 30                      # por debajo de esto no se publica probabilidad
BUCKET_S = 1800                 # 30 min
OPEN_H, OPEN_M, N_BUCKETS = 9, 0, 13     # KRX 09:00-15:30 KST = 13 franjas de 30 min
Z = 1.96


def wilson(ups, n, z=Z):
    """Intervalo de Wilson al 95%. None si n<=0 — jamas un 0.5 plausible."""
    if n <= 0:
        return None
    p = ups / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def read_rows(path):
    """[(epoch, close)] del formato de la flota `epoch o h l c v`. [] si ilegible."""
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


def load_sessions(sym, history_root):
    """{fecha KST: {epoch: close}} juntando TODOS los archivos del simbolo. La carpeta
    <fecha> viene del primer epoch del fichero vivo (puede ser un trozo de sesion tras un
    reinicio), asi que la sesion se deriva del propio epoch, no del nombre de la carpeta."""
    sessions = {}
    for path in sorted(glob.glob(os.path.join(history_root, "*", "bars", f"{sym}_krx.txt"))):
        for ep, c in read_rows(path):
            if c <= 0:
                continue
            d = datetime.fromtimestamp(ep, KST)
            sessions.setdefault(d.date().isoformat(), {})[ep] = c
    return sessions


def session_open_epoch(day_iso):
    return datetime.fromisoformat(day_iso).replace(
        hour=OPEN_H, minute=OPEN_M, tzinfo=KST).timestamp()


def bucket_returns(bars, day_iso):
    """{bucket: retorno %} de una sesion. Franja anclada a las 09:00 KST (no a la primera
    barra) para que las franjas sean comparables entre sesiones incompletas."""
    o = session_open_epoch(day_iso)
    grouped = {}
    for ep in sorted(bars):
        i = int((ep - o) // BUCKET_S)
        if 0 <= i < N_BUCKETS:
            grouped.setdefault(i, []).append(bars[ep])
    out = {}
    for i, closes in grouped.items():
        if len(closes) < 2 or closes[0] <= 0:
            continue
        out[i] = (closes[-1] - closes[0]) / closes[0] * 100.0
    return out


def bucket_labels(day_iso):
    o = session_open_epoch(day_iso)
    return [{"kst": datetime.fromtimestamp(o + i * BUCKET_S, KST).strftime("%H:%M"),
             "et": datetime.fromtimestamp(o + i * BUCKET_S, TZ).strftime("%H:%M")}
            for i in range(N_BUCKETS)]


def study(history_root=None, min_n=MIN_N):
    """-> dict con status DATA-INSUFFICIENT (n<min_n) o MEASURED. Nunca un % con n chico."""
    history_root = history_root or HISTORY
    syms, n_max = {}, 0
    for sym in SYMS:
        sessions = load_sessions(sym, history_root)
        days = sorted(sessions)
        labels = bucket_labels(days[-1]) if days else bucket_labels(
            datetime.now(KST).date().isoformat())
        agg = {i: {"n": 0, "ups": 0, "sum_ret": 0.0} for i in range(N_BUCKETS)}
        for day in days:
            for i, r in bucket_returns(sessions[day], day).items():
                a = agg[i]
                a["n"] += 1
                a["ups"] += 1 if r > 0 else 0
                a["sum_ret"] += r
        buckets = []
        for i in range(N_BUCKETS):
            a = agg[i]
            b = {"bucket": i, "kst": labels[i]["kst"], "et": labels[i]["et"],
                 "n": a["n"], "ups": a["ups"],
                 "mean_ret_pct": round(a["sum_ret"] / a["n"], 4) if a["n"] else None}
            if a["n"] >= min_n:
                lo, hi = wilson(a["ups"], a["n"])
                b.update({"status": "MEASURED", "p_up": round(a["ups"] / a["n"], 4),
                          "wilson_lo": lo, "wilson_hi": hi})
            else:
                b.update({"status": "DATA-INSUFFICIENT", "p_up": None,
                          "wilson_lo": None, "wilson_hi": None})
            buckets.append(b)
        n_sym = max((b["n"] for b in buckets), default=0)
        n_max = max(n_max, n_sym)
        syms[sym] = {"n": n_sym, "sessions": days,
                     "status": "MEASURED" if n_sym >= min_n else "DATA-INSUFFICIENT",
                     "buckets": buckets}
    return {"ts": time.time(), "min_n": min_n, "n": n_max,
            "status": "MEASURED" if n_max >= min_n else "DATA-INSUFFICIENT",
            "source": "data/history/<fecha>/bars/*_krx.txt", "symbols": syms}


# --- Modo US: el patron que preguntó Yunior es del overnight US, NO del agotamiento KRX ------
# "overnight pump US = AMZN/semis (catalizador nuevo), distinto del agotamiento KRX" (TODOS.md:77).
# poly_bars no cubre 00:30 ET, pero los futuros NQ/ES que ya registra overnight_feed SI.
CTX = os.path.join(REPO, "data", "history", "overnight_ctx.jsonl")
FEED_LOG = os.path.join(REPO, "logs", "overnight_feed.log")
US_OUT = os.path.join(REPO, "data", "overnight_pump_us.json")
US_START_H, US_N_BUCKETS = 20, 16      # 20:00 -> 04:00 ET, franjas de 30 min


def load_futures_rows(ctx=None, feed_log=None):
    """Filas {ts, nq_pct, es_pct} de ambas fuentes, deduplicadas por ts. Una fila sin ts o sin
    ningun futuro NO se cuenta: no se rellena con 0."""
    vistos, filas = set(), []
    for path in (ctx or CTX, feed_log or FEED_LOG):
        try:
            texto = open(path).read()
        except OSError:
            continue
        for ln in texto.splitlines():
            ln = ln.strip()
            if not ln.startswith("{"):
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            ts = d.get("ts")
            if not ts or ts in vistos:
                continue
            if d.get("nq_pct") is None and d.get("es_pct") is None:
                continue
            vistos.add(ts)
            filas.append({"ts": ts, "nq_pct": d.get("nq_pct"), "es_pct": d.get("es_pct")})
    filas.sort(key=lambda r: r["ts"])
    return filas


def _noche(ts):
    """Etiqueta de noche: de 18:00 ET a 09:29 ET del dia siguiente cuenta como la MISMA noche."""
    dt = datetime.fromtimestamp(ts, TZ)
    if dt.hour < 18:
        dt = dt.fromordinal(dt.toordinal() - 1).replace(tzinfo=TZ)
    return dt.date().isoformat()


def us_bucket(ts):
    """Franja de 30 min desde las 20:00 ET, o None si el tick cae fuera de 20:00-04:00."""
    dt = datetime.fromtimestamp(ts, TZ)
    h = dt.hour + (24 if dt.hour < US_START_H else 0)
    i = int(((h - US_START_H) * 60 + dt.minute) // 30)
    return i if 0 <= i < US_N_BUCKETS else None


def study_us(campo="nq_pct", min_n=MIN_N, ctx=None, feed_log=None):
    """Retorno del futuro dentro de cada franja de 30 min. DATA-INSUFFICIENT por debajo de min_n
    NOCHES: con 3 noches cualquier 'patron de las 00:30' es ruido."""
    filas = [f for f in load_futures_rows(ctx, feed_log) if f.get(campo) is not None]
    noches = {}
    for f in filas:
        i = us_bucket(f["ts"])
        if i is None:
            continue
        noches.setdefault(_noche(f["ts"]), {}).setdefault(i, []).append((f["ts"], f[campo]))

    agg = {i: {"n": 0, "ups": 0, "sum_ret": 0.0} for i in range(US_N_BUCKETS)}
    for franjas in noches.values():
        for i, pts in franjas.items():
            if len(pts) < 2:          # una sola lectura no define un retorno
                continue
            pts.sort()
            r = pts[-1][1] - pts[0][1]
            a = agg[i]
            a["n"] += 1
            a["ups"] += 1 if r > 0 else 0
            a["sum_ret"] += r

    buckets = []
    for i in range(US_N_BUCKETS):
        a = agg[i]
        h, m = divmod(US_START_H * 60 + i * 30, 60)
        b = {"bucket": i, "et": f"{h % 24:02d}:{m:02d}", "n": a["n"], "ups": a["ups"],
             "mean_ret_pct": round(a["sum_ret"] / a["n"], 4) if a["n"] else None}
        if a["n"] >= min_n:
            lo, hi = wilson(a["ups"], a["n"])
            b.update({"status": "MEASURED", "p_up": round(a["ups"] / a["n"], 4),
                      "wilson_lo": lo, "wilson_hi": hi})
        else:
            b.update({"status": "DATA-INSUFFICIENT", "p_up": None,
                      "wilson_lo": None, "wilson_hi": None})
        buckets.append(b)

    n_noches = len(noches)
    return {"ts": time.time(), "campo": campo, "min_n": min_n,
            "n_noches": n_noches, "noches": sorted(noches),
            "faltan_noches": max(0, min_n - n_noches),
            "status": "MEASURED" if n_noches >= min_n else "DATA-INSUFFICIENT",
            "source": "data/history/overnight_ctx.jsonl + logs/overnight_feed.log (futuros NQ/ES)",
            "buckets": buckets}


def write(res, out=None):
    out = out or OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, out)
    return out


def main():
    min_n = MIN_N
    if "--min-n" in sys.argv:
        min_n = int(sys.argv[sys.argv.index("--min-n") + 1])
    if "--us" in sys.argv:
        campo = sys.argv[sys.argv.index("--campo") + 1] if "--campo" in sys.argv else "nq_pct"
        res = study_us(campo=campo, min_n=min_n)
        write(res, US_OUT)
        if "--print" in sys.argv:
            print(json.dumps(res, indent=1))
        else:
            print(f"{res['status']} noches={res['n_noches']} "
                  f"(faltan {res['faltan_noches']} para min {min_n}) -> {US_OUT}")
        return
    res = study(min_n=min_n)
    write(res)
    if "--print" in sys.argv:
        print(json.dumps(res, indent=1))
    else:
        print(f"{res['status']} n={res['n']} (min {min_n}) -> {OUT}")


if __name__ == "__main__":
    main()
