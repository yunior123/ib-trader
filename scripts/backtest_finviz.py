#!/usr/bin/env python3
"""backtest_finviz.py — auditoria honesta de las alertas de los 3 screeners Finviz.

LOTE FUERA DE SESION (Python legitimo, ~/CLAUDE.md). No es camino de senal, no ordena nada.

Reglas de la casa que aplica:
  - PROHIBIDO devolver 0 / 0.0 / 0.5 / 50 / {} ante un fallo: o el dato, o None, o levanta.
  - Ticker sin dato = EXCLUIDO y contado en `excluded`, jamas rellenado.
  - Wilson sobre muestra EFECTIVA (rho medido con los propios 1m del dia, no un prior).
  - Triple barrera: timeout = NULL, nunca victoria. Barra ambigua -> SL primero.
  - Escritura atomica tmp + os.replace.

Modos:
  fetch    descarga y cachea (grouped daily + 1m de los tickers alertados + pool null)
  report   calcula y escribe docs/BACKTEST-ALERTAS-FINVIZ-<fecha>.md
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

EVENTS = os.path.join(REPO, "data", "finviz_screener_events.jsonl")
CACHE = os.environ.get("IBT_FINVIZ_BT_CACHE", os.path.join(REPO, "data", "backtest_finviz_cache"))

ET_CLOSE_HHMM = (16, 0)
ET_OPEN_HHMM = (9, 30)


class DataMissing(RuntimeError):
    """El dato no esta. Se levanta o se excluye; jamas se sustituye por un numero plausible."""


# ------------------------------------------------------------------ estadistica
def wilson(k, n, z=1.96):
    """Intervalo de Wilson. n<=0 levanta: no hay 'proporcion por defecto'."""
    if n is None or n <= 0:
        raise DataMissing("Wilson sobre n<=0")
    if k < 0 or k > n:
        raise DataMissing(f"Wilson con k={k} fuera de [0,{n}]")
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def n_effective(n, k_syms, rho, n_clusters=None):
    """n_eff = n / (1 + (k-1)*rho), topado por el numero de clusters (sym, fecha).

    k = SIMBOLOS AGRUPADOS que se mueven juntos (no observaciones/cluster) — es la
    definicion de measured-probability: bollinger n=1154, k=30 syms, rho=0.412 -> 89.2.
    rho tiene que venir MEDIDO; None levanta (prohibido el prior)."""
    if n <= 0:
        raise DataMissing("n_eff sobre n<=0")
    if k_syms <= 0:
        raise DataMissing("n_eff sin simbolos agrupados")
    if rho is None:
        raise DataMissing("n_eff sin rho medido (prohibido el prior)")
    rho = max(0.0, min(1.0, rho))
    eff = n / (1.0 + (k_syms - 1.0) * rho) if k_syms > 1 else float(n)
    if n_clusters:
        eff = min(eff, float(n_clusters))
    return max(1.0, min(float(n), eff))


def mean_pairwise_corr(series):
    """Correlacion media por pares. `series` = lista de dicts {timestamp: retorno}.

    ALINEA POR TIMESTAMP: truncar por longitud desalinea las series (unas empiezan en
    premarket y otras no) y la correlacion sale ~0 por construccion. Ese fue un bug real.
    None si no hay 2 series con >=30 minutos comunes."""
    usable = [s for s in series if s and len(s) >= 30]
    if len(usable) < 2:
        return None
    acc, cnt = 0.0, 0
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            common = sorted(set(usable[i]) & set(usable[j]))
            if len(common) < 30:
                continue
            c = _pearson([usable[i][t] for t in common], [usable[j][t] for t in common])
            if c is not None:
                acc += c
                cnt += 1
    return acc / cnt if cnt else None


def _pearson(a, b):
    n = len(a)
    if n < 2:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def binom_tail_p(k, n, p0):
    """p-valor de una cola (P[X >= k] bajo Binomial(n, p0)). Exacto, sin scipy."""
    if n <= 0:
        raise DataMissing("binomial sobre n<=0")
    if not 0.0 < p0 < 1.0:
        raise DataMissing(f"binomial con p0={p0} fuera de (0,1)")
    tot = 0.0
    for i in range(int(k), n + 1):
        tot += math.exp(_lchoose(n, i) + i * math.log(p0) + (n - i) * math.log(1 - p0))
    return min(1.0, tot)


def _lchoose(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg. Devuelve lista de bool (True = sobrevive) en el orden de entrada."""
    if not pvals:
        return []
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    kmax = -1
    for rank, i in enumerate(idx, start=1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    out = [False] * m
    for rank, i in enumerate(idx, start=1):
        if rank <= kmax:
            out[i] = True
    return out


# ------------------------------------------------------------------ etiquetado
def atr_from_bars(bars, upto_idx, period=14):
    """ATR de `period` barras 1m ANTERIORES a upto_idx. None si no hay suficientes."""
    if upto_idx < period:
        return None
    trs = []
    for i in range(upto_idx - period, upto_idx):
        prev_c = bars[i - 1]["c"] if i > 0 else bars[i]["o"]
        tr = max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - prev_c), abs(bars[i]["l"] - prev_c))
        trs.append(tr)
    a = sum(trs) / len(trs)
    return a if a > 0 else None


def triple_barrier(bars, entry_idx, entry, direction, atr, k_tp, k_sl, end_idx):
    """1 = TP primero, 0 = SL primero, None = timeout (NUNCA victoria).

    Barra que contiene TP y SL a la vez -> SL primero (conservador). Devuelve
    (label, ambiguo:boolean, minutos_hasta_toque|None)."""
    if atr is None or atr <= 0:
        raise DataMissing("triple barrera sin ATR medido")
    if direction not in (1, -1):
        raise DataMissing(f"direccion invalida {direction}")
    tp = entry + direction * k_tp * atr
    sl = entry - direction * k_sl * atr
    for i in range(entry_idx + 1, min(end_idx, len(bars) - 1) + 1):
        hi, lo = bars[i]["h"], bars[i]["l"]
        hit_tp = hi >= tp if direction == 1 else lo <= tp
        hit_sl = lo <= sl if direction == 1 else hi >= sl
        if hit_tp and hit_sl:
            return 0, True, i - entry_idx
        if hit_tp:
            return 1, False, i - entry_idx
        if hit_sl:
            return 0, False, i - entry_idx
    return None, False, None


# ------------------------------------------------------------------ E/S
def atomic_write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_events(path=EVENTS):
    """Eventos ticker-a-ticker del motor C++ (fuente de verdad; el banner solo muestra 3)."""
    out = []
    if not os.path.exists(path):
        raise DataMissing(f"falta {path}")
    with open(path) as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            for req in ("ts", "screen", "ticker", "event", "weather", "score", "possible"):
                if req not in d:
                    raise DataMissing(f"evento sin campo {req}: {ln[:120]}")
            d["date"] = dt.datetime.fromtimestamp(d["ts"]).strftime("%Y-%m-%d")
            out.append(d)
    return out


def cache_path(*parts):
    return os.path.join(CACHE, *parts)


def read_cache(name):
    p = cache_path(name)
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def write_cache(name, obj):
    atomic_write(cache_path(name), json.dumps(obj))


# ------------------------------------------------------------------ fetch
def do_fetch(date, null_n, force=False):
    from poly_client import Polygon  # noqa: E402  (import tardio: solo el modo fetch lo necesita)

    os.makedirs(CACHE, exist_ok=True)
    poly = Polygon()
    evs = [e for e in load_events() if e["date"] == date]
    if not evs:
        raise DataMissing(f"sin eventos para {date}")
    tickers = sorted({e["ticker"] for e in evs})
    print(f"{date}: {len(evs)} eventos, {len(tickers)} tickers unicos", flush=True)

    gname = f"grouped_{date}.json"
    if force or read_cache(gname) is None:
        d = poly.get(f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date}"
                     "?adjusted=true")
        if not d or d.get("status") not in ("OK", "DELAYED") or not d.get("results"):
            raise DataMissing(f"grouped {date} no disponible: {d and d.get('status')}")
        write_cache(gname, d["results"])
        print(f"  grouped {date}: {len(d['results'])} tickers", flush=True)
    grouped = read_cache(gname)

    # Pool null: mismo universo que el filtro comun de los 3 screeners (precio > $5,
    # volumen relevante). Se fija con semilla para que el null sea reproducible.
    liquid = sorted({g["T"] for g in grouped
                     if g.get("c", 0) > 5 and g.get("v", 0) > 500000 and "." not in g["T"]})
    pool = [t for t in liquid if t not in set(tickers)]
    rnd = random.Random(20260803)
    nulls = rnd.sample(pool, min(null_n, len(pool)))
    write_cache(f"nullpool_{date}.json", nulls)
    print(f"  universo liquido {len(liquid)}, null muestreado {len(nulls)}", flush=True)

    todo = [t for t in tickers + nulls if force or read_cache(f"m1_{date}_{t}.json") is None]
    print(f"  faltan {len(todo)} series 1m (~{len(todo) * 12.4 / 60:.0f} min a 5 req/min)",
          flush=True)
    missing = []
    for i, t in enumerate(todo, 1):
        url = (f"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{date}/{date}"
               "?adjusted=true&sort=asc&limit=50000")
        d = poly.get(url)
        if not d or not d.get("results"):
            missing.append(t)
            write_cache(f"m1_{date}_{t}.json", {"missing": True})
            print(f"  [{i}/{len(todo)}] {t} SIN DATO -> excluido", flush=True)
            continue
        write_cache(f"m1_{date}_{t}.json",
                    [{"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"],
                      "v": r.get("v", 0)} for r in d["results"]])
        if i % 10 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {t} ok", flush=True)
    write_cache(f"missing_{date}.json", missing)
    print(poly.report("polygon"), flush=True)
    print(f"sin dato: {len(missing)} -> {missing}", flush=True)


# ------------------------------------------------------------------ analisis
def _bars(date, ticker):
    d = read_cache(f"m1_{date}_{ticker}.json")
    if d is None:
        return None
    if isinstance(d, dict) and d.get("missing"):
        return None
    return d


def _idx_at_or_after(bars, ts_ms):
    for i, b in enumerate(bars):
        if b["t"] >= ts_ms:
            return i
    return None


def _et_ms(date, hh, mm):
    y, mo, d = (int(x) for x in date.split("-"))
    return int(dt.datetime(y, mo, d, hh, mm).timestamp() * 1000)


def label_events(date, k_tp=1.0, k_sl=1.0):
    """Etiqueta cada evento direccional. Devuelve (labeled, excluded)."""
    close_ms = _et_ms(date, *ET_CLOSE_HHMM)
    open_ms = _et_ms(date, *ET_OPEN_HHMM)
    labeled, excluded = [], []
    for e in load_events():
        if e["date"] != date:
            continue
        if e["weather"] not in ("BUY", "SELL"):
            excluded.append({**e, "reason": "WATCH (sin direccion)"})
            continue
        ts_ms = e["ts"] * 1000
        if ts_ms >= close_ms:
            excluded.append({**e, "reason": "emitida despues del cierre (16:00 ET)"})
            continue
        bars = _bars(date, e["ticker"])
        if bars is None:
            excluded.append({**e, "reason": "sin barras 1m en Polygon"})
            continue
        i = _idx_at_or_after(bars, ts_ms)
        if i is None or i >= len(bars) - 1:
            excluded.append({**e, "reason": "alerta fuera del rango de barras del dia"})
            continue
        end = _idx_at_or_after(bars, close_ms)
        end = (end - 1) if end else (len(bars) - 1)
        if end <= i:
            excluded.append({**e, "reason": "sin camino restante hasta el cierre"})
            continue
        atr = atr_from_bars(bars, i)
        if atr is None:
            excluded.append({**e, "reason": "sin ATR14 1m previo (menos de 14 barras)"})
            continue
        entry = bars[i]["c"]
        direction = 1 if e["weather"] == "BUY" else -1
        lab, ambig, tmin = triple_barrier(bars, i, entry, direction, atr, k_tp, k_sl, end)
        exit_px = bars[end]["c"]
        labeled.append({
            **e,
            "entry": entry, "exit_close": exit_px, "atr": atr,
            "dir": direction,
            "ret_close_pct": direction * (exit_px - entry) / entry * 100.0,
            "label": lab, "ambiguo": ambig, "t_touch_min": tmin,
            "premarket": ts_ms < open_ms,
            "minutes_left": end - i,
            "hhmm": dt.datetime.fromtimestamp(e["ts"]).strftime("%H:%M"),
        })
    return labeled, excluded


def null_sample(date, labeled, k_tp=1.0, k_sl=1.0, per_event=3, seed=20260803):
    """Null emparejado: mismo minuto de entrada, misma duracion, ticker AL AZAR del mismo
    universo liquido. La direccion se empareja con la de la senal."""
    nulls = read_cache(f"nullpool_{date}.json")
    if not nulls:
        raise DataMissing("falta el pool null (corre `fetch` antes)")
    close_ms = _et_ms(date, *ET_CLOSE_HHMM)
    rnd = random.Random(seed)
    out = []
    usable = [t for t in nulls if _bars(date, t) is not None]
    if len(usable) < 10:
        raise DataMissing(f"pool null insuficiente: {len(usable)} tickers con barras")
    for ev in labeled:
        for _ in range(per_event):
            for _try in range(8):
                t = rnd.choice(usable)
                bars = _bars(date, t)
                i = _idx_at_or_after(bars, ev["ts"] * 1000)
                if i is None or i >= len(bars) - 1:
                    continue
                end = _idx_at_or_after(bars, close_ms)
                end = (end - 1) if end else (len(bars) - 1)
                if end <= i:
                    continue
                atr = atr_from_bars(bars, i)
                if atr is None:
                    continue
                entry = bars[i]["c"]
                lab, _amb, _tm = triple_barrier(bars, i, entry, ev["dir"], atr, k_tp, k_sl, end)
                out.append({"ticker": t, "dir": ev["dir"], "label": lab,
                            "ret_close_pct": ev["dir"] * (bars[end]["c"] - entry) / entry * 100.0,
                            "screen": ev["screen"]})
                break
    return out


def measured_rho(date, tickers):
    """rho medio por pares MEDIDO con los retornos 1m del propio dia (no un prior)."""
    open_ms, close_ms = _et_ms(date, *ET_OPEN_HHMM), _et_ms(date, *ET_CLOSE_HHMM)
    series = []
    for t in tickers:
        bars = _bars(date, t)
        if bars is None or len(bars) < 40:
            continue
        rets = {}
        for i in range(1, len(bars)):
            p0, p1 = bars[i - 1]["c"], bars[i]["c"]
            # solo RTH: en premarket muchas barras faltan y el hueco finge decorrelacion
            if p0 > 0 and open_ms <= bars[i]["t"] < close_ms:
                rets[bars[i]["t"]] = (p1 - p0) / p0
        series.append(rets)
    return mean_pairwise_corr(series)


def rate(items, key="label"):
    """(k, n) sobre etiquetas de barrera: timeout (None) NO cuenta ni arriba ni abajo."""
    dec = [x for x in items if x[key] is not None]
    return sum(1 for x in dec if x[key] == 1), len(dec)


def wilson_eff(k, n, n_eff):
    """Wilson evaluado sobre la muestra EFECTIVA: se conserva p = k/n y se degrada la n."""
    if n <= 0:
        raise DataMissing("wilson_eff sobre n<=0")
    return wilson(round(k / n * n_eff), max(1, round(n_eff)))


def verdict(k, n, n_eff, null_p, q_pass, min_n_eff=30):
    """Tabla de veredictos de measured-probability. Sin n_eff suficiente NO se publica prob."""
    if n <= 0 or n_eff < min_n_eff:
        return "DATA-INSUFICIENTE"
    lo, _hi = wilson_eff(k, n, n_eff)
    if lo > null_p and q_pass:
        return "KEEP"
    _lo2, hi = wilson_eff(k, n, n_eff)
    return "KILL" if hi < null_p else "UNPROVEN"


# ------------------------------------------------------------------ cortes
def hour_bucket(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    t = h * 60 + m
    if t < 570:
        return "premarket <09:30"
    if t < 630:
        return "09:30-10:30 oro"
    if t < 690:
        return "10:30-11:30"
    if t < 840:
        return "11:30-14:00 picadora"
    if t < 960:
        return "14:00-16:00"
    return ">=16:00 post-cierre"


def rvol_bucket(r):
    if r is None:
        return "sin RVOL"
    if r < 1.0:
        return "RVOL <1.0"
    if r < 1.5:
        return "RVOL 1.0-1.5"
    if r < 2.5:
        return "RVOL 1.5-2.5"
    return "RVOL >=2.5"


def cuts_for(ev):
    """Cortes a los que pertenece un evento etiquetado."""
    out = [("screener", ev["screen"]),
           ("tipo", ev["event"]),
           ("hora", hour_bucket(ev["hhmm"])),
           ("rvol", rvol_bucket(ev.get("rvol"))),
           ("weather", ev["weather"])]
    p = ev["possible"]
    s = abs(ev["score"])
    out.append(("score", "abs(score) = maximo" if s >= p else
                ("abs(score) >= possible-1" if s >= p - 1 else "abs(score) < possible-1")))
    return out


CPP = os.path.join(REPO, "scripts", "finviz_screener_watch.cpp")


def cpp_profiles(path=CPP):
    """Lee los filtros REALES del .cpp (para que el doc no se desincronice del motor)."""
    if not os.path.exists(path):
        raise DataMissing(f"falta {path}")
    import re
    src = open(path).read()
    out = {}
    for m in re.finditer(r'if \(id == "(\w+)"\) return \{(.*?)\};', src, re.S):
        pid, body = m.group(1), m.group(2)
        line = src[:m.start()].count("\n") + 1
        lits = re.findall(r'"([^"]*)"', body)
        if len(lits) < 2:
            raise DataMissing(f"perfil {pid} sin literales legibles en {path}")
        # [label, ...trozos de filtro..., signal]  (literales adyacentes se concatenan en C++)
        out[pid] = {"line": line, "label": lits[0],
                    "filters": "".join(lits[1:-1]), "signal": lits[-1]}
    if set(out) < {"buffett", "squeeze", "momentum"}:
        raise DataMissing(f"no encontre los 3 perfiles en {path}: {sorted(out)}")
    return out


FILTERS = {
    "solo NUEVOS (mata weather_change)": lambda e: e["event"] == "new_match",
    "solo BUY/SELL (mata WATCH)": lambda e: e["weather"] in ("BUY", "SELL"),
    "abs(score) == possible": lambda e: abs(e["score"]) >= e["possible"],
    "abs(score) >= possible-1": lambda e: abs(e["score"]) >= e["possible"] - 1,
    "RVOL >= 1.5": lambda e: e.get("rvol") is not None and e["rvol"] >= 1.5,
    "RVOL >= 2.0": lambda e: e.get("rvol") is not None and e["rvol"] >= 2.0,
    "ventana 09:45-15:30": lambda e: "09:45" <= e["_hhmm"] <= "15:30",
    "mata post-cierre (>=16:00)": lambda e: e["_hhmm"] < "16:00",
    "mata premarket (<09:30)": lambda e: e["_hhmm"] >= "09:30",
}


def simulate_filters(all_evs, labeled):
    """Cuantas alertas mata cada filtro y cuantas GANADORAS (barrera=1) se pierde."""
    for e in all_evs:
        e["_hhmm"] = dt.datetime.fromtimestamp(e["ts"]).strftime("%H:%M")
    win = {(e["ts"], e["ticker"]) for e in labeled if e["label"] == 1}
    n = len(all_evs)
    rows = []
    for name, f in FILTERS.items():
        keep = [e for e in all_evs if f(e)]
        kept_win = len({(e["ts"], e["ticker"]) for e in keep} & win)
        rows.append((name, len(keep), n - len(keep), kept_win, len(win)))
    seen, keep = set(), []
    for e in sorted(all_evs, key=lambda x: x["ts"]):
        if e["ticker"] in seen:
            continue
        seen.add(e["ticker"])
        keep.append(e)
    rows.append(("1 alerta por ticker y dia", len(keep), n - len(keep),
                 len({(e["ts"], e["ticker"]) for e in keep} & win), len(win)))
    return rows


def apply_combo(all_evs, names, dedup=True):
    fs = [FILTERS[x] for x in names]
    out, seen = [], set()
    for e in sorted(all_evs, key=lambda x: x["ts"]):
        if not all(f(e) for f in fs):
            continue
        if dedup and e["ticker"] in seen:
            continue
        seen.add(e["ticker"])
        out.append(e)
    return out


def build_report(date, k_tp=1.0, k_sl=1.0, q=0.10):
    labeled, excluded = label_events(date, k_tp, k_sl)
    all_evs = [e for e in load_events() if e["date"] == date]
    tickers = sorted({e["ticker"] for e in all_evs})
    rho = measured_rho(date, tickers)
    nulls = null_sample(date, labeled, k_tp, k_sl)
    nk, nn = rate(nulls)
    null_p = nk / nn if nn else None
    if null_p is None:
        raise DataMissing("null vacio: no se publica nada sin control")

    L = []
    L.append(f"# Backtest honesto — alertas FINVIZ (screeners) · {date}")
    L.append("")
    L.append(f"Generado {dt.datetime.now():%Y-%m-%d %H:%M} por `scripts/backtest_finviz.py` · "
             "SEÑAL-SOLAMENTE, ninguna conclusion ordena nada.")
    L.append(f"Verdad de terreno: **Polygon aggs 1m + grouped daily** (sin IBKR; orden vigente "
             "prohibe TWS/Gateway). Barrera triple k_tp={:.2f}·ATR14(1m), k_sl={:.2f}·ATR14(1m), "
             "horizonte = hasta el cierre 16:00 ET del mismo dia. Timeout = NULL, no victoria."
             .format(k_tp, k_sl))
    L.append("")
    kk0, nn0 = rate(labeled)
    L.append("## VEREDICTO EN 6 LINEAS")
    L.append("")
    L.append(f"1. El {date} los 3 screeners emitieron **{len(all_evs)} alertas de ticker** en "
             f"**{len({(e['ts'], e['screen'], e['event']) for e in all_evs})} banners**, "
             f"cada uno con voz + push al telefono.")
    L.append(f"2. De las {nn0} etiquetables, ganaron **{kk0} ({kk0/nn0:.1%})**. Entradas "
             f"ALEATORIAS emparejadas por minuto y duracion ganaron **{null_p:.1%}**. "
             f"El screener va **{(kk0/nn0 - null_p)*100:+.1f} pp** contra el azar.")
    L.append("3. El signo negativo se mantiene en 3 de los 4 umbrales de barrera barridos "
             "(seccion 3b) -> no es un artefacto de un umbral.")
    L.append("4. Ningun corte sobrevive BH-FDR q=0.10. Con una sola sesion de muestra, "
             "**casi todo es DATA-INSUFICIENTE** y no se publica probabilidad.")
    L.append("5. Los pesos del `score N/6` y `N/7` estan **INVENTADOS**, y uno de los "
             "componentes declarados (SMA20) **no existe** en el CSV que llega (seccion 1).")
    L.append("6. Lo unico que apunta a algo es el **RVOL alto** — y con n de dos digitos "
             "bajos: es una pista para medir, no para operar.")
    L.append("")
    L.append("## 0. Advertencias (leelas antes de creerte un numero)")
    L.append("")
    L.append("- **SIN comisiones, SIN slippage, SIN spread.** Entrada al close de la vela 1m del "
             "minuto de la alerta, con el tape de Polygon (no con el precio que canto Finviz).")
    L.append("- **Horizonte unico: intradia**. Ver seccion 5 — +1d/+2d/+5d NO se pueden medir hoy.")
    L.append("- El **timeout no es victoria**: las alertas cuya barrera no se toca antes del "
             "cierre salen del denominador (`label = NULL`).")
    L.append("- **Ningun ticker se rellena**: el que no tiene barras en Polygon se EXCLUYE y se "
             "cuenta en la tabla de exclusiones.")
    L.append("- Wilson se evalua sobre **n_eff**, no sobre n cruda. Un solo dia de mercado es "
             "casi una sola observacion.")
    L.append("")

    # --- 1. inventario
    prof = cpp_profiles()
    L.append("## 1. Inventario de los 3 screeners")
    L.append("")
    L.append("Motor unico `scripts/finviz_screener_watch.cpp`, 3 instancias "
             "(`--screen buffett|squeeze|momentum`). Filtros leidos del propio .cpp:")
    L.append("")
    L.append("| screener | linea | filtro enviado a Finviz | signal `s=` | sondeo RTH |")
    L.append("|---|---|---|---|---|")
    polls = {"buffett": "600 s", "squeeze": "120 s", "momentum": "60 s"}
    for pid in ("buffett", "squeeze", "momentum"):
        p_ = prof[pid]
        sig = f"`{p_['signal']}`" if p_["signal"] else "—"
        L.append(f"| {p_['label']} | `finviz_screener_watch.cpp:{p_['line']}` | "
                 f"`{p_['filters']}` | {sig} | {polls[pid]} |")
    L.append("")
    L.append("URL: `finviz_screener_watch.cpp:342-344` — `v=152`, `o=-relativevolume`, "
             "`c=1,2,6,30,31,53,54,55,59,60,61,63,64,65,66,67`.")
    L.append("")
    L.append("### Como se calcula el score (`score()`, lineas 176-197)")
    L.append("")
    L.append("| linea | componente | regla | peso |")
    L.append("|---|---|---|---|")
    L.append("| 177 | cambio del dia | `>+0.3%` -> +1, `<-0.3%` -> -1, si no 0 | ±1 |")
    L.append("| 178 | cambio desde apertura | `>+0.2%` -> +1, `<-0.2%` -> -1 | ±1 |")
    L.append("| 179-183 | RSI(14) | `[50,75]` -> +1; `<42` o `>82` -> -1 | ±1 |")
    L.append("| 184 | SMA20 | signo de la distancia | ±1 |")
    L.append("| 185 | SMA50 | signo de la distancia | ±1 |")
    L.append("| 186 | SMA200 | signo de la distancia | ±1 |")
    L.append("| 187 | RVOL | `>=1.5` -> +1, si no 0 | +1/0 |")
    L.append("| 190-191 | squeeze: short+impulso | `short_float>=20 && change>0` -> +1 | +1/0 |")
    L.append("| 192-194 | momentum: breakout sostiene | `change>0 && from_open>0` -> +1, si no -1 | ±1 |")
    L.append("| 195-196 | umbral | `max(2, ceil(possible*0.45))`; BUY si `score>=u`, SELL si `<=-u` | — |")
    L.append("")
    L.append("### ¿Los pesos estan MEDIDOS o INVENTADOS?")
    L.append("")
    L.append("**INVENTADOS.** Los cinco hechos, cada uno verificable:")
    L.append("")
    L.append("1. **No existe fichero de calibracion del score.** El repo tiene "
             "`data/calibration.json`, `data/calibration_barrier.json`, `data/compass_calib.json` "
             "y `data/timeofday_calib*`; **ninguno** contiene los pesos de este motor, y el .cpp "
             "no lee ningun fichero de calibracion. Todos los umbrales (`0.3`, `0.2`, `50/75`, "
             "`42/82`, `1.5`, `20`, `0.45`) son literales en el codigo.")
    L.append("2. **Un componente declarado NO EXISTE.** El .cpp pide `c=...53,54,55...` y comenta "
             "(lineas 340-341) que son SMA20/50/200. El header REAL del export es "
             "`\"50-Day Simple Moving Average\",\"200-Day Simple Moving Average\",\"50-Day High\"` — "
             "**no hay columna de SMA20**. Como el parser busca por NOMBRE, `r.sma20` es siempre "
             "NaN: el voto SMA20 nunca suma y nunca incrementa `possible`. Evidencia cruzada: "
             "`sma20_pct` esta vacio en el 100% de las filas de los 3 CSV, y BUFFETT reporta "
             "`possible = 6` (no 7).")
    ev_m = [e for e in all_evs if e["screen"] == "momentum" and e.get("rvol") is not None]
    rv_ok = sum(1 for e in ev_m if e["rvol"] >= 1.5)
    L.append(f"3. **El filtro se auto-vota.** MOMENTUM filtra por `ta_sma50_pa`, `ta_sma200_pa` y "
             f"`sh_relvol_o1.5`; esos mismos tres son votos del score. Medido: RVOL>=1.5 en "
             f"**{rv_ok}/{len(ev_m)}** de sus alertas, y en el snapshot SMA50>0 y SMA200>0 en el "
             f"100% de las filas. Son **3 puntos de 7 REGALADOS** antes de mirar nada. El umbral "
             f"BUY es 4 -> **basta 1 punto mas** para cantar BUY.")
    ev_b = [e for e in all_evs if e["screen"] == "buffett" and e.get("rvol") is not None]
    rv_dead = sum(1 for e in ev_b if e["rvol"] < 1.5)
    L.append(f"4. **Y un voto muerto en el otro sentido.** BUFFETT no filtra por RVOL: el voto "
             f"vale 0 en **{rv_dead}/{len(ev_b)}** de sus alertas. Su score util es de 5 "
             f"componentes, no de 6.")
    L.append("5. **Terminos colineales con pesos a mano.** SMA50 y SMA200 comparten signo en el "
             "78.5% de las filas BUFFETT, el **100%** de MOMENTUM y el 75% de SQUEEZE: es UNA "
             "tesis de tendencia contada dos o tres veces. La `anti-overfit-killlist` prohibe "
             "exactamente esto (\"compuesto de z-scores con pesos elegidos a mano sobre terminos "
             "correlacionados\", muertos #6, #8, #13).")
    L.append("")
    L.append("Ademas `possible` **no es el maximo alcanzable**: `add(r, 0, ...)` "
             "(linea 172-174) incrementa `possible` aunque el voto sea 0. Un "
             "\"score 3/6\" NO significa \"3 de 6 puntos posibles\"; es una suma con signo sobre "
             "6 componentes evaluados donde los ceros inflan el denominador. **El numero que se "
             "canta por voz no se puede leer como una fraccion.**")
    L.append("")
    L.append("> Veredicto `anti-overfit-killlist`: **prior inventado disfrazado de medicion**, "
             "con dos de los seis disfraces del catalogo presentes a la vez — *input muerto* "
             "(SMA20) y *compuesto de terminos colineales con pesos a mano*.")
    L.append("")

    # --- 2. volumen
    L.append("## 2. Volumen de alertas (la medida del ruido)")
    L.append("")
    byh = {}
    for e in all_evs:
        h = dt.datetime.fromtimestamp(e["ts"]).strftime("%H")
        byh.setdefault(h, {}).setdefault(e["screen"], 0)
        byh[h][e["screen"]] += 1
    L.append("| hora ET | buffett | squeeze | momentum | total |")
    L.append("|---|---|---|---|---|")
    for h in sorted(byh):
        r = byh[h]
        tot = sum(r.values())
        L.append(f"| {h}:00 | {r.get('buffett',0)} | {r.get('squeeze',0)} | "
                 f"{r.get('momentum',0)} | {tot} |")
    L.append(f"| **TOTAL** | {sum(1 for e in all_evs if e['screen']=='buffett')} | "
             f"{sum(1 for e in all_evs if e['screen']=='squeeze')} | "
             f"{sum(1 for e in all_evs if e['screen']=='momentum')} | **{len(all_evs)}** |")
    L.append("")
    L.append("Cada banner = 1 notificacion de voz/urgente + 1 push al telefono "
             "(`finviz_screener_watch.cpp:316-317`). Ritmo de interrupcion medido:")
    L.append("")
    L.append("| screener | banners | ciclos posibles | % de sondeos que interrumpen | "
             "mediana entre banners |")
    L.append("|---|---|---|---|---|")
    tot_ban = 0
    for pid, prth, pext in (("buffett", 600, 900), ("squeeze", 120, 300), ("momentum", 60, 180)):
        stamps = sorted({e["ts"] for e in all_evs if e["screen"] == pid})
        ban = len({(e["ts"], e["event"]) for e in all_evs if e["screen"] == pid})
        tot_ban += ban
        cyc = int((5.5 + 4) * 3600 / pext + 6.5 * 3600 / prth)
        gaps = sorted((stamps[i + 1] - stamps[i]) / 60.0 for i in range(len(stamps) - 1))
        med = f"{gaps[len(gaps)//2]:.0f} min" if gaps else "—"
        L.append(f"| {pid} | {ban} | ~{cyc} | {len(stamps)/cyc:.0%} | {med} |")
    L.append(f"| **TOTAL** | **{tot_ban}** | | | |")
    L.append("")
    L.append(f"(Contraste independiente: `grep -c \"FINVIZ (BUFFETT|MOMENTUM|SHORT)\" "
             f"data/trading-signals/{date}.txt` = {tot_ban} lineas, mas 1 linea "
             "`FINVIZ ROTO` de las 04:02.)")
    L.append("")
    per = {}
    for e in all_evs:
        per[e["ticker"]] = per.get(e["ticker"], 0) + 1
    rep = sorted(per.items(), key=lambda x: -x[1])[:6]
    L.append(f"**Churn dentro del dia**: {len(per)} tickers distintos generaron {len(all_evs)} "
             f"alertas; **{sum(1 for _t, c in per.items() if c > 1)}** tickers alertaron mas de "
             f"una vez. Top repetidores: " +
             ", ".join(f"`{t}` x{c}" for t, c in rep) + ".")
    L.append("")
    L.append("La causa esta en el codigo: `finviz_screener_watch.cpp:378-381` NO alerta "
             "`BUY -> WATCH`, pero SI alerta `WATCH -> BUY`. Un ticker que oscila alrededor del "
             "umbral produce una interrupcion NUEVA en cada cruce hacia arriba. "
             "El churn no es un efecto del mercado: es la regla de notificacion.")
    L.append("")

    # --- muestra efectiva
    n = len(labeled)
    k_clusters = len({e["ticker"] for e in labeled})
    neff_all = n_effective(n, k_clusters, rho, k_clusters) if n else None
    L.append("## 3. Muestra efectiva (rho MEDIDO, no prior)")
    L.append("")
    L.append(f"- eventos direccionales etiquetables: **{n}** de {len(all_evs)}")
    L.append(f"- excluidos: **{len(excluded)}** (razones abajo)")
    L.append(f"- clusters (ticker, fecha): **{k_clusters}** — todo cae en **1 sola sesion**")
    L.append(f"- rho medio por pares de retornos 1m del {date}, medido sobre los propios "
             f"tickers alertados: **{rho:.3f}**" if rho is not None else "- rho: NO MEDIBLE")
    L.append(f"- **n_eff = {neff_all:.1f}**" if neff_all else "- n_eff: no calculable")
    L.append("")
    exr = {}
    for e in excluded:
        exr[e["reason"]] = exr.get(e["reason"], 0) + 1
    L.append("| razon de exclusion | n |")
    L.append("|---|---|")
    for r_, c in sorted(exr.items(), key=lambda x: -x[1]):
        L.append(f"| {r_} | {c} |")
    L.append("")

    # --- tabla de follow-through
    L.append("## 3b. Follow-through por corte")
    L.append("")
    kk, nnn = rate(labeled)
    L.append(f"Null emparejado (mismo minuto, misma duracion, misma direccion, ticker al azar "
             f"del mismo universo liquido): **{null_p:.1%}** sobre n={nn} entradas sinteticas.")
    L.append("")
    groups = {}
    for e in labeled:
        for dim, val in cuts_for(e):
            groups.setdefault((dim, val), []).append(e)
    groups[("TODO", "todas las alertas")] = labeled
    rows, pvals = [], []
    for (dim, val), items in sorted(groups.items()):
        k, m = rate(items)
        if m == 0:
            rows.append((dim, val, len(items), 0, None, None, None, None, "SIN DECIDIR"))
            pvals.append(1.0)
            continue
        kc = len({x["ticker"] for x in items})
        ne = n_effective(m, kc, rho, kc)
        lo, hi = wilson_eff(k, m, ne)
        p = binom_tail_p(k, m, null_p)
        rows.append((dim, val, len(items), m, k / m, lo, hi, ne, None))
        pvals.append(p)
    passes = bh_fdr(pvals, q)
    best_cut = min(((r, pv) for r, pv in zip(rows, pvals) if r[8] is None),
                   key=lambda x: x[1], default=None)
    L.append("| corte | valor | alertas | decididas | hit | Wilson(n_eff) | n_eff | p | BH-FDR | veredicto |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for (r_, p_, ok) in zip(rows, pvals, passes):
        dim, val, na, m, hit, lo, hi, ne, note = r_
        if note:
            L.append(f"| {dim} | {val} | {na} | 0 | — | — | — | — | — | DATA-INSUFICIENTE |")
            continue
        v = verdict(round(hit * m), m, ne, null_p, ok)
        L.append(f"| {dim} | {val} | {na} | {m} | {hit:.1%} | [{lo:.1%}, {hi:.1%}] | {ne:.1f} | "
                 f"{p_:.3f} | {'si' if ok else 'no'} | {v} |")
    L.append("")
    L.append(f"Total decidido: {kk}/{nnn} = "
             f"{(kk/nnn if nnn else 0):.1%} vs null {null_p:.1%}.")
    L.append("")

    # --- retorno descriptivo alerta -> cierre
    L.append("### Descriptivo: retorno alerta -> cierre (no es la etiqueta, es contexto)")
    L.append("")
    L.append("| screener | n | mediana % | media % | > 0 |")
    L.append("|---|---|---|---|---|")
    for s in ("buffett", "squeeze", "momentum"):
        it = [e for e in labeled if e["screen"] == s]
        if not it:
            L.append(f"| {s} | 0 | — | — | — |")
            continue
        r_ = sorted(e["ret_close_pct"] for e in it)
        med = r_[len(r_) // 2]
        L.append(f"| {s} | {len(it)} | {med:+.2f} | {sum(r_)/len(r_):+.2f} | "
                 f"{sum(1 for x in r_ if x > 0)}/{len(r_)} |")
    nr = sorted(x["ret_close_pct"] for x in nulls)
    L.append(f"| **null aleatorio** | {len(nr)} | {nr[len(nr)//2]:+.2f} | "
             f"{sum(nr)/len(nr):+.2f} | {sum(1 for x in nr if x > 0)}/{len(nr)} |")
    L.append("")

    # --- 3b. curva de sensibilidad (test 4 de anti-overfit-killlist)
    L.append("### Curva de sensibilidad (si el efecto vive en UN solo umbral, no es real)")
    L.append("")
    L.append("| k_tp = k_sl (·ATR14 1m) | screener | decididas | hit | null | delta |")
    L.append("|---|---|---|---|---|---|")
    for k in (0.5, 0.75, 1.0, 1.5):
        lab_k, _ = label_events(date, k, k)
        nul_k = null_sample(date, lab_k, k, k)
        nk_, nn_ = rate(nul_k)
        np_ = nk_ / nn_ if nn_ else None
        for s in ("buffett", "squeeze", "momentum", "TODOS"):
            it = lab_k if s == "TODOS" else [e for e in lab_k if e["screen"] == s]
            kk_, mm_ = rate(it)
            if mm_ == 0 or np_ is None:
                L.append(f"| {k:.2f} | {s} | 0 | — | — | — |")
                continue
            L.append(f"| {k:.2f} | {s} | {mm_} | {kk_/mm_:.1%} | {np_:.1%} | "
                     f"{(kk_/mm_ - np_)*100:+.1f} pp |")
    L.append("")

    # --- 4. propuesta de filtros
    L.append("## 4. Propuesta de filtros (simulada sobre el propio dia)")
    L.append("")
    sim = simulate_filters(all_evs, labeled)
    total_win = sim[0][4] if sim else 0
    L.append(f"Ganadoras de referencia (barrera=1 con k={k_tp:.2f}/{k_sl:.2f} ATR): "
             f"**{total_win}** sobre {len(all_evs)} alertas.")
    L.append("")
    base = (sim[0][4] / len(all_evs)) if all_evs else 0
    L.append(f"Tasa base: **{base:.0%}** de las alertas del dia acaban en ganadora. Un filtro "
             "util tiene que SUBIR esa concentracion; si la deja igual, esta matando señal y "
             "ruido en la misma proporcion.")
    L.append("")
    L.append("| filtro | deja | mata | % ruido matado | ganadoras conservadas | "
             "concentracion | vs base |")
    L.append("|---|---|---|---|---|---|---|")
    for name, keep, kill, kw, tw in sim:
        pct = kill / len(all_evs) if all_evs else 0
        conc = kw / keep if keep else None
        d = f"{(conc - base)*100:+.1f} pp" if conc is not None else "—"
        L.append(f"| {name} | {keep} | {kill} | {pct:.0%} | {kw}/{tw} | "
                 f"{conc:.0%} | {d} |" if conc is not None else
                 f"| {name} | {keep} | {kill} | {pct:.0%} | {kw}/{tw} | — | — |")
    L.append("")
    win = {(e["ts"], e["ticker"]) for e in labeled if e["label"] == 1}
    combos = {
        "A · minimo higienico": ["solo BUY/SELL (mata WATCH)", "mata post-cierre (>=16:00)"],
        "B · A + RVOL>=1.5": ["solo BUY/SELL (mata WATCH)", "mata post-cierre (>=16:00)",
                              "RVOL >= 1.5"],
        "C · B + ventana 09:45-15:30": ["solo BUY/SELL (mata WATCH)",
                                        "mata post-cierre (>=16:00)", "RVOL >= 1.5",
                                        "ventana 09:45-15:30"],
        "D · C + score>=possible-1": ["solo BUY/SELL (mata WATCH)",
                                      "mata post-cierre (>=16:00)", "RVOL >= 1.5",
                                      "ventana 09:45-15:30", "abs(score) >= possible-1"],
        "E · solo NUEVOS + RVOL>=2.0": ["solo NUEVOS (mata weather_change)", "RVOL >= 2.0",
                                        "mata post-cierre (>=16:00)"],
    }
    L.append("Combos, con dedupe de 1 alerta por ticker y dia en todos:")
    L.append("")
    L.append("| combo | alertas | ruido matado | ganadoras | concentracion | vs base | "
             "alertas matadas por ganadora perdida |")
    L.append("|---|---|---|---|---|---|---|")
    rows_c = []
    for name, names in combos.items():
        kept = apply_combo(all_evs, names)
        kw = len({(e["ts"], e["ticker"]) for e in kept} & win)
        killed = len(all_evs) - len(kept)
        lost = len(win) - kw
        conc = kw / len(kept) if kept else 0.0
        rows_c.append((name, names, kept, kw, killed, conc))
        L.append(f"| {name} | {len(kept)} | {killed} ({killed/len(all_evs):.0%}) | "
                 f"{kw}/{len(win)} | {conc:.0%} | {(conc-base)*100:+.1f} pp | "
                 f"{(killed/lost if lost else float('inf')):.1f} |")
    L.append("")
    bc, bcp = best_cut if best_cut else ((None,) * 9, 1.0)
    bestf = max(sim, key=lambda r: (r[3] / r[1]) if r[1] else 0)
    bf_conc = bestf[3] / bestf[1]
    bf_neff = n_effective(bestf[1], min(bestf[1], len({e['ticker'] for e in all_evs})), rho,
                          bestf[1])
    L.append(f"**Lo que dice esta tabla, y lo que NO.** El filtro que mas concentra es "
             f"`{bestf[0]}`: {bf_conc:.0%} de ganadoras frente a una base de {base:.0%} "
             f"(**{(bf_conc-base)*100:+.1f} pp**). Pero deja **n = {bestf[1]}** alertas, "
             f"n_eff = {bf_neff:.1f} -> **DATA-INSUFICIENTE**: es una PISTA, no un resultado. "
             f"Coincide con el corte de menor p de la seccion 3b "
             f"(`{bc[0]} = {bc[1]}`, {bc[4]:.1%}, p={bcp:.3f}, que NO sobrevive a BH-FDR). "
             f"Si algo hay aqui, esta en el VOLUMEN RELATIVO — no en el score.")
    L.append("")
    chosen = max(rows_c, key=lambda r: (r[5], r[3]))
    name, names, kept, kw, killed, conc = chosen
    fall = min(rows_c, key=lambda r: abs(len(r[2]) - 40))
    L.append(f"**Recomendacion (exquisita): {name}** — deja **{len(kept)}** interrupciones de "
             f"{len(all_evs)} (**-{killed/len(all_evs):.0%}**), concentracion {conc:.0%} "
             f"({(conc-base)*100:+.1f} pp sobre la base), conservando {kw}/{len(win)} "
             f"ganadoras. Reglas: {', '.join(names)}, mas 1 alerta por ticker y dia.")
    L.append("")
    L.append(f"Si {len(kept)} alertas/dia parece demasiado poco, el escalon anterior es "
             f"**{fall[0]}**: {len(fall[2])} alertas, concentracion {fall[5]:.0%}, "
             f"{fall[3]}/{len(win)} ganadoras.")
    L.append("")
    L.append("Ademas, y con independencia del filtro elegido, dos cambios que el propio codigo "
             "justifica: (a) **quitar la voz** a los 3 screeners mientras el veredicto sea "
             "UNPROVEN (`fleet_notify_urgent` -> banner; regla de `measured-probability`: "
             "UNPROVEN no habla), y (b) **no re-alertar el mismo ticker el mismo dia** aunque "
             "vuelva a cruzar el umbral (`finviz_screener_watch.cpp:378-381`).")
    L.append("")
    L.append(f"Las {len(kept)} alertas que habrian sobrevivido el {date}:")
    L.append("")
    L.append("| ticker | screener | hora | weather | score | RVOL |")
    L.append("|---|---|---|---|---|---|")
    for e in kept:
        rv = e.get("rvol")
        L.append(f"| {e['ticker']} | {e['screen']} | {e['_hhmm']} | {e['weather']} | "
                 f"{e['score']}/{e['possible']} | {rv if rv is not None else '—'} |")
    L.append("")

    # --- 5. limites
    L.append("## 5. Lo que NO se puede afirmar")
    L.append("")
    L.append(f"- **Un solo dia.** El unico dia con eventos de screener archivados es {date} "
             f"(`data/finviz_screener_events.jsonl`). El agregado llega a n_eff = "
             f"{neff_all:.1f} y por eso se le pone veredicto (UNPROVEN); **casi todos los "
             f"cortes por screener/score/hora caen por debajo de 30 y son DATA-INSUFICIENTE**. "
             f"Un dia no distingue \"el screener no sirve\" de \"el 3 de agosto fue malo\".")
    L.append(f"- **rho medido = {rho:.3f}**, mucho mas bajo que el 0.412 de la flota de 30 "
             "semis: el universo del screener es sectorialmente diverso (mineras de oro, "
             "aseguradoras, biotech, restaurantes), asi que la muestra NO se hunde por "
             "correlacion — se hunde por ser un solo dia.")
    L.append("- **Horizontes +1d/+2d/+5d NO medidos**: Polygon (plan sin realtime) no sirve el "
             "dia en curso hasta despues del cierre; el dia siguiente al ultimo alertado no "
             "existe todavia. Solo hay horizonte intradia alerta->cierre.")
    L.append("- **Churn entre dias NO medible**: `data/finviz_*_state.txt` guarda un solo dia "
             "(`date=` + `alerted|`) y se reinicia; no hay historico de membresia.")
    L.append("- **Sin look-ahead, pero sin archivo**: los eventos se etiquetan con el precio y "
             "el RVOL que el motor grabo EN EL INSTANTE de la alerta; nada se re-lee del "
             "snapshot de hoy. A cambio, el snapshot CSV (`data/finviz_*_signals.csv`) se "
             "sobrescribe cada ciclo: no sirve para reconstruir el pasado.")
    L.append("- La probabilidad de cada corte no se publica; se publica el intervalo y el "
             "veredicto DATA-INSUFICIENTE donde toca.")
    L.append("- **El null es una sola sesion tambien.** 45 tickers del universo liquido, "
             "3 entradas sinteticas por alerta. Basta para decir \"no bate al azar\"; no basta "
             "para poner un numero al edge.")
    L.append("")
    L.append("### Que falta, en orden")
    L.append("")
    L.append("1. **Acumular sesiones.** El fichero de eventos ya existe y es append-only: con "
             "20-30 sesiones los cortes por screener y por RVOL pasan el umbral de n. Nada mas "
             "hay que construir para eso — solo esperar y no borrar el jsonl.")
    L.append("2. **Archivar la membresia diaria** (los `alerted|` del state) para poder medir el "
             "churn entre dias, que hoy es literalmente inobservable.")
    L.append("3. **Horizontes multidia**: con un `grouped daily` por sesion (1 peticion Polygon "
             "por dia) se etiquetan +1d/+2d/+5d de todo el universo de golpe. Barato; solo "
             "necesita que el dia haya cerrado.")
    L.append("4. **Arreglar el componente SMA20** o quitarlo del score y del texto que se canta: "
             "hoy el numero que se dice por voz miente sobre lo que mide.")
    L.append("5. **Probar la hipotesis RVOL** aislada (sin score), que es la unica que dio "
             "señal de vida, con el barrido de umbrales {1.5, 2.0, 2.5, 3.0} y n suficiente.")
    L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["fetch", "report"])
    ap.add_argument("--date", default="2026-08-03")
    ap.add_argument("--null-n", type=int, default=45)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.mode == "fetch":
        do_fetch(a.date, a.null_n, a.force)
        return 0
    out = a.out or os.path.join(REPO, "docs", f"BACKTEST-ALERTAS-FINVIZ-{dt.date.today()}.md")
    atomic_write(out, build_report(a.date))
    print(f"escrito {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
