#!/usr/bin/env python3
"""lse_validate.py — valida London Strategic Edge contra las fuentes ya auditadas.

LOTE OFFLINE (no camino de senal): Polygon va a 5 req/min y la key LSE admite 2
consultas concurrentes, asi que esto no puede vivir en vivo. Fail-loud en todo: si una
fuente no responde la seccion queda con su error; JAMAS se rellena con 0 / 0.5 / {}.

Secciones (--secciones bars,relleno,volume,options,greeks,history,korea,all):
  bars     LSE 1m/1d vs Polygon FRESCO, 5 simbolos x 10 sesiones, campo a campo
  relleno  el gran sospechoso: extremos de 1 centimo. Polygon como CONTROL + el
           ruido de revision del propio Polygon como suelo de comparacion
  volume   volumen diario y RTH, LSE / Polygon consolidado
  options  cadena LSE vs Unusual Whales vs cadena Polygon archivada
  greeks   griegas LSE contra el Black-Scholes de la casa (gex_core) + r/q implicitos
  history  5 fechas profundas (2003/2008/2015/2020/2024) contra Yahoo
  korea    005930.KS / 000660.KS contra los CSV de la casa y el puente Naver

  set -a; . config/feeds.env; set +a
  ./venv-lse/bin/python scripts/research/lse_validate.py --secciones all
Salida: data/research/lse_validacion.json (escritura atomica tmp+os.replace).
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics as st
import subprocess
import sys
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core  # noqa: E402  (BS de la casa: fuente unica de griegas propias)

OUT_JSON = os.path.join(REPO, "data", "research", "lse_validacion.json")
CACHE_DIR = os.environ.get("LSE_VAL_CACHE") or os.path.join(tempfile.gettempdir(),
                                                            "lse_validate_cache")
DB = os.path.join(REPO, "data", "trades.db")

SYMS = ["SPY", "QQQ", "NVDA", "MU", "AAPL"]
SESIONES = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
            "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
# ventana profunda: la que ya esta en poly_bars (2 anios en local, coste API cero)
SESIONES_DB = ["2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17",
               "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"]
RTH_INI, RTH_FIN = 13 * 60 + 30, 20 * 60      # 09:30-16:00 ET en minutos UTC (EDT)
OPT_SYM = "SPY"
OPT_FECHA = "2026-08-07"                       # ultima sesion cerrada (viernes)
OPT_EXPS = ["2026-08-07", "2026-08-10", "2026-08-14", "2026-08-21"]
VENTANAS_HIST = [("2003-09-10", "2003-09-19"), ("2008-10-06", "2008-10-16"),
                 ("2015-08-21", "2015-08-29"), ("2020-03-12", "2020-03-21"),
                 ("2024-08-02", "2024-08-09")]
KOREA = [("005930.KS", "data/005930_ks_1m_30d.csv", 100),
         ("000660.KS", "data/000660_ks_1m_30d.csv", 1000)]


class ValidationError(RuntimeError):
    """Fallo que el llamante DEBE ver: nunca se convierte en un numero."""


# ------------------------------------------------------------------ utilidades
def atomic_write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def cache_get(name):
    p = os.path.join(CACHE_DIR, name)
    if os.path.exists(p):
        with open(p) as fh:
            return json.load(fh)
    return None


def cache_put(name, obj):
    os.makedirs(CACHE_DIR, exist_ok=True)
    atomic_write(os.path.join(CACHE_DIR, name), json.dumps(obj))


def env_key(nombre):
    """Key de config/feeds.env o del entorno. Levanta si falta: sin key no hay medida."""
    v = os.environ.get(nombre)
    if v:
        return v
    p = os.path.join(REPO, "config", "feeds.env")
    if os.path.exists(p):
        with open(p) as fh:
            for ln in fh:
                if ln.split("=", 1)[0].strip() == nombre:
                    v = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        return v
    raise ValidationError(f"falta {nombre} en config/feeds.env ni en el entorno")


def epoch_ms(iso):
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def utc_min(ms):
    d = dt.datetime.utcfromtimestamp(ms / 1000.0)
    return d.hour * 60 + d.minute


def utc_dia(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000.0).date().isoformat()


def cents(x):
    return int(round(x * 100))


def resumen_abs(errs):
    """Estadistica de un vector de errores. None si esta vacio (no se inventa un 0)."""
    if not errs:
        return None
    a = sorted(abs(x) for x in errs)
    return {"n": len(a), "media_abs": st.mean(a), "mediana_abs": st.median(a),
            "p95_abs": a[min(len(a) - 1, int(0.95 * len(a)))], "max_abs": a[-1],
            "sesgo": st.mean(errs)}


def pct(a, b):
    return (100.0 * a / b) if b else None


# ------------------------------------------------------------------ clientes
_ULTIMA_LSE = [0.0]
LSE_GAP = 0.40      # la key admite 2 conexiones; en serie con holgura no hay 429


def lse_client():
    from lse import LSE
    return LSE(api_key=env_key("LSE_API_KEY"), timeout=120)


def lse_retry(fn, *a, **k):
    """429 = concurrencia, no cuota. Se espacia y se reintenta; si se agota, levanta."""
    from lse import LSEError
    ultimo = None
    for i in range(8):
        gap = LSE_GAP - (time.time() - _ULTIMA_LSE[0])
        if gap > 0:
            time.sleep(gap)
        _ULTIMA_LSE[0] = time.time()
        try:
            return fn(*a, **k)
        except LSEError as e:
            ultimo = e
            if e.status in (429, 0, 500, 502, 503, 504):
                time.sleep(2 + 4 * i)
                continue
            raise
        except urllib.error.URLError as e:
            ultimo = e
            time.sleep(2 + 4 * i)
    raise ValidationError(f"LSE agotado tras reintentos: {ultimo}")


def lse_1m_rango(c, sym, ini, fin, paso_dias=1):
    """1m de [ini,fin) troceado (tope 5000 filas/peticion), cacheado en disco."""
    k = f"lse1m_{sym.replace('.', '_')}_{ini}_{fin}.json"
    got = cache_get(k)
    if got is not None:
        return {int(a): b for a, b in got.items()}
    out = {}
    cur, end = dt.date.fromisoformat(ini), dt.date.fromisoformat(fin)
    while cur < end:
        nx = min(cur + dt.timedelta(days=paso_dias), end)
        rows = lse_retry(c.candles, sym, "1m", start=cur.isoformat(),
                         end=nx.isoformat(), limit=5000)
        if len(rows) >= 5000:
            raise ValidationError(f"{sym} {cur}: 5000 filas = tope, el trozo tapa datos")
        for x in rows:
            out[epoch_ms(x["timestamp"])] = x
        cur = nx
    cache_put(k, {str(a): b for a, b in out.items()})
    return out


def poly_client():
    from poly_client import Polygon
    return Polygon(verbose=True)


def poly_aggs(p, sym, tf, ini, fin):
    """Agregados Polygon FRESCOS (adjusted=false), una peticion por rango."""
    k = f"polyapi_{sym}_{tf}_{ini}_{fin}.json"
    got = cache_get(k)
    if got is not None:
        return got
    url = (f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/{tf}/"
           f"{ini}/{fin}?adjusted=false&sort=asc&limit=50000")
    r = p.get(url)
    if r is None or r.get("status") not in ("OK", "DELAYED") or "results" not in r:
        raise ValidationError(f"Polygon {tf} {sym} {ini}..{fin}: {r.get('status') if r else 'sin respuesta'}")
    cache_put(k, r)
    return r


def poly_db(sym, dias):
    """poly_bars local (2 anios ya descargados): control gratis y con mucha n."""
    if not os.path.exists(DB):
        raise ValidationError(f"falta {DB}")
    cx = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {}
    for d in dias:
        t0 = int(dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp() * 1000)
        for ts, o, h, l, c_, v in cx.execute(
                "select ts,o,h,l,c,v from poly_bars where sym=? and ts>=? and ts<?",
                (sym, t0, t0 + 86400000)):
            out[ts] = {"o": o, "h": h, "l": l, "c": c_, "v": v}
    cx.close()
    if not out:
        raise ValidationError(f"poly_bars sin filas para {sym} en {dias[0]}..{dias[-1]}")
    return out


def uw_get(path, **q):
    tok = env_key("UW_TOKEN")
    u = "https://api.unusualwhales.com" + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(u, headers={"Authorization": "Bearer " + tok,
                                             "Accept": "application/json",
                                             "User-Agent": "ib-trader/1.0 (lse validation)"})
    ultimo = None
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read()).get("data")
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            if e.code in (403, 429, 500, 502, 503):
                time.sleep((5, 15, 40, 60)[i])
                continue
            raise ValidationError(f"UW {path}: {ultimo}")
        except OSError as e:
            ultimo = repr(e)
            time.sleep(3 + 3 * i)
    raise ValidationError(f"UW {path} agotado: {ultimo}")


def yahoo_daily(sym, ini, fin):
    """Diarias de Yahoo via yfinance de ta_venv (subproceso: aqui corre venv-lse)."""
    py = os.path.join(REPO, "ta_venv", "bin", "python")
    if not os.path.exists(py):
        raise ValidationError(f"falta {py}: sin el no hay tercera fuente")
    prog = (
        "import json,sys,yfinance as yf\n"
        f"h=yf.Ticker({sym!r}).history(start={ini!r},end={fin!r},auto_adjust=False)\n"
        "o=[{'d':str(i.date()),'o':float(r.Open),'h':float(r.High),'l':float(r.Low),"
        "'c':float(r.Close),'v':float(r.Volume)} for i,r in h.iterrows()]\n"
        "sys.stdout.write(json.dumps(o))\n")
    p = subprocess.run([py, "-c", prog], capture_output=True, text=True, timeout=240)
    if p.returncode != 0 or not p.stdout.strip():
        raise ValidationError(f"yfinance {sym} {ini}..{fin} fallo: {p.stderr.strip()[:300]}")
    return json.loads(p.stdout)


# ------------------------------------------------------------------ descarga barras
def bajar_barras(c, p):
    datos = {}
    for s in SYMS:
        d = cache_get(f"lse_{s}_1d.json")
        if d is None:
            d = lse_retry(c.candles, s, "1d", start=SESIONES[0], end="2026-08-08", limit=100)
            cache_put(f"lse_{s}_1d.json", d)
        fin = (dt.date.fromisoformat(SESIONES[-1]) + dt.timedelta(days=1)).isoformat()
        m = lse_1m_rango(c, s, SESIONES[0], fin)
        pd_ = poly_aggs(p, s, "day", SESIONES[0], SESIONES[-1])
        pm = poly_aggs(p, s, "minute", SESIONES[0], SESIONES[-1])
        datos[s] = {"lse_1d": d, "lse_1m": m, "poly_1d": pd_, "poly_1m": pm}
        print(f"  [{s}] lse1m={len(m)} poly1m={len(pm['results'])}", flush=True)
    return datos


# ------------------------------------------------------------------ 1) BARRAS
def _campo_stats(L, P, ks):
    campos = (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"))
    blk = {}
    ident4 = 0
    for k in ks:
        if all(cents(L[k][a]) == cents(P[k][b]) for a, b in campos):
            ident4 += 1
    blk["barras"] = len(ks)
    blk["ohlc_4de4_identico"] = ident4
    blk["pct_ohlc_4de4"] = pct(ident4, len(ks))
    for a, b in campos:
        e = [L[k][a] - P[k][b] for k in ks]
        ig = sum(1 for k in ks if cents(L[k][a]) == cents(P[k][b]))
        blk[a] = {"identicos_al_centimo": ig, "pct_identicos": pct(ig, len(ks)),
                  "error": resumen_abs(e)}
    return blk


def seccion_bars(datos):
    out = {"ventana": [SESIONES[0], SESIONES[-1]], "por_simbolo": {}, "global": {},
           "convencion": {}}
    tot = {"rth": [0, 0], "ext": [0, 0]}
    eg = {"open": [], "high": [], "low": [], "close": []}
    for s in SYMS:
        L = datos[s]["lse_1m"]
        P = {r["t"]: r for r in datos[s]["poly_1m"]["results"]}
        com = sorted(set(L) & set(P))
        if not com:
            raise ValidationError(f"{s}: cero minutos comunes LSE/Polygon")
        rth = [k for k in com if RTH_INI <= utc_min(k) < RTH_FIN]
        ext = [k for k in com if not (RTH_INI <= utc_min(k) < RTH_FIN)]
        res = {"rth": _campo_stats(L, P, rth), "ext": _campo_stats(L, P, ext)}
        for a, b in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c")):
            eg[a].extend(L[k][a] - P[k][b] for k in rth)
        tot["rth"][0] += len(rth); tot["rth"][1] += res["rth"]["ohlc_4de4_identico"]
        tot["ext"][0] += len(ext); tot["ext"][1] += res["ext"]["ohlc_4de4_identico"]
        solo_l = sorted(set(L) - set(P))
        solo_p = sorted(set(P) - set(L))
        res["cobertura"] = {
            "lse_barras": len(L), "poly_barras": len(P), "comunes": len(com),
            "solo_lse": len(solo_l), "solo_poly": len(solo_p),
            "solo_lse_en_rth": sum(1 for k in solo_l if RTH_INI <= utc_min(k) < RTH_FIN),
            "solo_lse_volumen_cero": sum(1 for k in solo_l if (L[k].get("volume") or 0) == 0),
            "solo_poly_en_rth": sum(1 for k in solo_p if RTH_INI <= utc_min(k) < RTH_FIN)}
        # rejilla de cotizacion: quien publica sub-centimo y quien redondea
        n_l = sum(1 for k in rth for f in ("open", "high", "low", "close")
                  if abs(L[k][f] * 100 - round(L[k][f] * 100)) > 1e-6)
        n_p = sum(1 for k in rth for f in ("o", "h", "l", "c")
                  if abs(P[k][f] * 100 - round(P[k][f] * 100)) > 1e-6)
        res["fuera_de_rejilla_centimo"] = {"lse": n_l, "poly": n_p, "de_valores": 4 * len(rth)}
        # desplazamiento temporal: si el maximo no esta en 0, la barra esta corrida
        sh = {}
        for d_ in (-2, -1, 0, 1, 2):
            n = e = 0
            for k in rth:
                k2 = k + d_ * 60000
                if k2 in P:
                    n += 1
                    e += cents(L[k]["close"]) == cents(P[k2]["c"])
            sh[d_] = pct(e, n)
        res["desplazamiento_close_pct"] = sh
        out["por_simbolo"][s] = res
        print(f"  [bars {s}] rth={len(rth)} 4de4={res['rth']['pct_ohlc_4de4']:.1f}% "
              f"close={res['rth']['close']['pct_identicos']:.1f}%", flush=True)
    out["global"] = {
        "rth": {"barras": tot["rth"][0], "ohlc_4de4": tot["rth"][1],
                "pct": pct(tot["rth"][1], tot["rth"][0])},
        "ext": {"barras": tot["ext"][0], "ohlc_4de4": tot["ext"][1],
                "pct": pct(tot["ext"][1], tot["ext"][0])},
        "error_rth": {k: resumen_abs(v) for k, v in eg.items()}}
    # convencion del bar diario (sesion RTH o 24h) contra el 1m de cada fuente
    conv = {}
    for s in SYMS:
        f = SESIONES[-1]
        ld = [r for r in datos[s]["lse_1d"] if r["timestamp"][:10] == f]
        pdd = [r for r in datos[s]["poly_1d"]["results"] if utc_dia(r["t"]) == f]
        lm = sorted([k for k in datos[s]["lse_1m"] if utc_dia(k) == f])
        pmk = sorted([r["t"] for r in datos[s]["poly_1m"]["results"] if utc_dia(r["t"]) == f])
        P = {r["t"]: r for r in datos[s]["poly_1m"]["results"]}
        lr = [k for k in lm if RTH_INI <= utc_min(k) < RTH_FIN]
        pr = [k for k in pmk if RTH_INI <= utc_min(k) < RTH_FIN]
        if not (ld and pdd and lr and pr):
            raise ValidationError(f"faltan barras de {s} el {f} para fijar la convencion")
        conv[s] = {"lse_1d_o": ld[0]["open"], "lse_1d_c": ld[0]["close"],
                   "lse_1m_rth_open": datos[s]["lse_1m"][lr[0]]["open"],
                   "lse_1m_rth_close": datos[s]["lse_1m"][lr[-1]]["close"],
                   "lse_1m_ext_open": datos[s]["lse_1m"][lm[0]]["open"],
                   "poly_1d_o": pdd[0]["o"], "poly_1d_c": pdd[0]["c"],
                   "poly_1m_rth_open": P[pr[0]]["o"], "poly_1m_rth_close": P[pr[-1]]["c"]}
    out["convencion"] = {"fecha": SESIONES[-1], "detalle": conv,
                         "lectura": "si lse_1d_o == lse_1m_rth_open la barra diaria es de sesion RTH"}
    return out


# ------------------------------------------------------------------ 2) RELLENO
def _dist_extremos(L, P, ks):
    """El sospechoso: high==open+1c y low==open-1c. Polygon es el CONTROL."""
    l_h = sum(1 for k in ks if cents(L[k]["high"]) - cents(L[k]["open"]) == 1)
    l_l = sum(1 for k in ks if cents(L[k]["open"]) - cents(L[k]["low"]) == 1)
    l_u = sum(1 for k in ks if cents(L[k]["high"]) - cents(L[k]["open"]) == 1
              or cents(L[k]["open"]) - cents(L[k]["low"]) == 1)
    p_h = sum(1 for k in ks if cents(P[k]["h"]) - cents(P[k]["o"]) == 1)
    p_l = sum(1 for k in ks if cents(P[k]["o"]) - cents(P[k]["l"]) == 1)
    p_u = sum(1 for k in ks if cents(P[k]["h"]) - cents(P[k]["o"]) == 1
              or cents(P[k]["o"]) - cents(P[k]["l"]) == 1)
    l_plano = sum(1 for k in ks if cents(L[k]["high"]) == cents(L[k]["low"]))
    p_plano = sum(1 for k in ks if cents(P[k]["h"]) == cents(P[k]["l"]))
    rl = [L[k]["high"] - L[k]["low"] for k in ks]
    rp = [P[k]["h"] - P[k]["l"] for k in ks]
    return {
        "barras": len(ks),
        "lse_high_eq_open_mas_1c_pct": pct(l_h, len(ks)),
        "poly_high_eq_open_mas_1c_pct": pct(p_h, len(ks)),
        "lse_low_eq_open_menos_1c_pct": pct(l_l, len(ks)),
        "poly_low_eq_open_menos_1c_pct": pct(p_l, len(ks)),
        "lse_union_pct": pct(l_u, len(ks)), "poly_union_pct": pct(p_u, len(ks)),
        "lse_barra_plana_pct": pct(l_plano, len(ks)),
        "poly_barra_plana_pct": pct(p_plano, len(ks)),
        "rango_medio_lse": st.mean(rl), "rango_medio_poly": st.mean(rp),
        "rango_ratio_medio": st.mean(rl) / st.mean(rp) if st.mean(rp) else None,
        "rango_mediana_lse": st.median(rl), "rango_mediana_poly": st.median(rp),
        "lse_high_mayor_que_poly_pct": pct(sum(1 for k in ks if L[k]["high"] > P[k]["h"] + 1e-9), len(ks)),
        "lse_high_menor_que_poly_pct": pct(sum(1 for k in ks if L[k]["high"] < P[k]["h"] - 1e-9), len(ks)),
        "lse_low_menor_que_poly_pct": pct(sum(1 for k in ks if L[k]["low"] < P[k]["l"] - 1e-9), len(ks)),
        "lse_low_mayor_que_poly_pct": pct(sum(1 for k in ks if L[k]["low"] > P[k]["l"] + 1e-9), len(ks)),
    }


def _atr(bars, n=14):
    """ATR de Wilder sobre 1m; bars = lista (h,l,c) en orden temporal."""
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, _ = bars[i]
        pc = bars[i - 1][2]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = st.mean(trs[:n])
    for x in trs[n:]:
        a = (a * (n - 1) + x) / n
    return a


def seccion_relleno(datos, c):
    """Responde: los extremos de 1 centimo son relleno fabricado o microestructura real."""
    out = {"pregunta": ("en el 1m de LSE, high==open+0.01 / low==open-0.01 son minutos "
                        "sin actividad con extremos RELLENADOS, o son reales?"),
           "metodo": "Polygon como CONTROL sobre los MISMOS minutos; si LSE no excede a "
                     "Polygon no hay relleno que atribuir a LSE",
           "por_simbolo": {}, "ventana_profunda": {}, "ruido_propio_de_polygon": {}}
    for s in SYMS:
        L = datos[s]["lse_1m"]
        P = {r["t"]: r for r in datos[s]["poly_1m"]["results"]}
        com = sorted(set(L) & set(P))
        rth = [k for k in com if RTH_INI <= utc_min(k) < RTH_FIN]
        ext = [k for k in com if not (RTH_INI <= utc_min(k) < RTH_FIN)]
        e = {"rth": _dist_extremos(L, P, rth), "ext": _dist_extremos(L, P, ext)}
        # ATR(14) sobre 1m RTH: la pregunta practica es si el ATR queda contaminado
        atrs = {}
        for d in SESIONES:
            ks = [k for k in rth if utc_dia(k) == d]
            if len(ks) < 30:
                continue
            al = _atr([(L[k]["high"], L[k]["low"], L[k]["close"]) for k in ks])
            ap = _atr([(P[k]["h"], P[k]["l"], P[k]["c"]) for k in ks])
            if al and ap:
                atrs[d] = {"lse": al, "poly": ap, "ratio": al / ap}
        if not atrs:
            raise ValidationError(f"{s}: sin dias con suficientes barras para ATR")
        e["atr14_1m_por_dia"] = atrs
        e["atr14_ratio"] = {"media": st.mean([v["ratio"] for v in atrs.values()]),
                            "min": min(v["ratio"] for v in atrs.values()),
                            "max": max(v["ratio"] for v in atrs.values()),
                            "n_dias": len(atrs)}
        out["por_simbolo"][s] = e
        print(f"  [relleno {s}] RTH union LSE {e['rth']['lse_union_pct']:.2f}% vs POLY "
              f"{e['rth']['poly_union_pct']:.2f}% | ATR ratio {e['atr14_ratio']['media']:.4f}",
              flush=True)
    # ventana profunda con poly_bars local (coste API cero, n grande)
    fin = (dt.date.fromisoformat(SESIONES_DB[-1]) + dt.timedelta(days=1)).isoformat()
    for s in ("SPY", "QQQ"):
        L = lse_1m_rango(c, s, SESIONES_DB[0], fin)
        P = poly_db(s, SESIONES_DB)
        com = sorted(set(L) & set(P))
        rth = [k for k in com if RTH_INI <= utc_min(k) < RTH_FIN]
        out["ventana_profunda"][s] = {"sesiones": [SESIONES_DB[0], SESIONES_DB[-1]],
                                      "fuente_poly": "poly_bars local",
                                      "rth": _dist_extremos(L, P, rth)}
    # suelo de comparacion: Polygon contra SI MISMO (descarga vieja vs API de hoy)
    P_db = poly_db("SPY", [SESIONES_DB[-1]])
    P_api = cache_get(f"polyapi_SPY_minute_{SESIONES_DB[-1]}_{SESIONES_DB[-1]}.json")
    if P_api is None:
        p = poly_client()
        P_api = poly_aggs(p, "SPY", "minute", SESIONES_DB[-1], SESIONES_DB[-1])
    A = {r["t"]: r for r in P_api["results"]}
    com = sorted(set(P_db) & set(A))
    dif = [k for k in com if any(abs(P_db[k][a] - A[k][a]) > 1e-9 for a in ("o", "h", "l", "c"))]
    dif_c = [k for k in com if cents(P_db[k]["c"]) != cents(A[k]["c"])]
    out["ruido_propio_de_polygon"] = {
        "dia": SESIONES_DB[-1], "simbolo": "SPY", "barras": len(com),
        "barras_revisadas": len(dif), "pct_revisadas": pct(len(dif), len(com)),
        "close_revisado_al_centimo": len(dif_c), "pct_close_revisado": pct(len(dif_c), len(com)),
        "lectura": ("Polygon REVISA sus propias agregadas: este es el suelo de desacuerdo "
                    "que ni siquiera una fuente consigo misma baja de el")}
    return out


# ------------------------------------------------------------------ 3) VOLUMEN
def seccion_volume(datos):
    out = {"por_simbolo": {}, "nota": "ratio = volumen LSE / volumen Polygon consolidado"}
    todos_d, todos_r = [], []
    for s in SYMS:
        L1d = {r["timestamp"][:10]: r for r in datos[s]["lse_1d"]}
        P1d = {utc_dia(r["t"]): r for r in datos[s]["poly_1d"]["results"]}
        L = datos[s]["lse_1m"]
        P = {r["t"]: r for r in datos[s]["poly_1m"]["results"]}
        filas, rd, rr = [], [], []
        for d in SESIONES:
            if d not in L1d or d not in P1d:
                raise ValidationError(f"volumen: falta el dia {d} de {s} en una de las fuentes")
            lv, pv = L1d[d]["volume"], P1d[d]["v"]
            lr = sum(L[k]["volume"] for k in L
                     if utc_dia(k) == d and RTH_INI <= utc_min(k) < RTH_FIN)
            pr = sum(P[k]["v"] for k in P
                     if utc_dia(k) == d and RTH_INI <= utc_min(k) < RTH_FIN)
            if pv <= 0 or pr <= 0:
                raise ValidationError(f"volumen Polygon no positivo {s} {d}")
            filas.append({"dia": d, "lse_1d": lv, "poly_1d": pv, "ratio_1d": lv / pv,
                          "lse_rth_1m": lr, "poly_rth_1m": pr, "ratio_rth": lr / pr})
            rd.append(lv / pv); rr.append(lr / pr)
        todos_d.extend(rd); todos_r.extend(rr)
        out["por_simbolo"][s] = {"dias": filas, "ratio_1d_medio": st.mean(rd),
                                 "ratio_rth_medio": st.mean(rr),
                                 "ratio_rth_min": min(rr), "ratio_rth_max": max(rr)}
    out["ratio_1d_global"] = {"media": st.mean(todos_d), "mediana": st.median(todos_d),
                              "min": min(todos_d), "max": max(todos_d), "n": len(todos_d)}
    out["ratio_rth_global"] = {"media": st.mean(todos_r), "mediana": st.median(todos_r),
                               "min": min(todos_r), "max": max(todos_r), "n": len(todos_r)}
    return out


# ------------------------------------------------------------------ 4) OPCIONES
def bajar_opciones(c):
    lse_ch = cache_get("lse_chain_spy.json")
    if lse_ch is None:
        lse_ch = {}
        for e in OPT_EXPS:
            lse_ch[e] = lse_retry(c.options, OPT_SYM, expiry=e, limit=5000)
        lse_ch["_sin_filtro"] = lse_retry(c.options, OPT_SYM, limit=5000)
        cache_put("lse_chain_spy.json", lse_ch)
    uw = cache_get("uw_chain_spy.json")
    if uw is None:
        uw = []
        for e in OPT_EXPS:
            pag = uw_get(f"/api/stock/{OPT_SYM}/option-contracts", expiry=e, limit=500)
            if pag is None:
                raise ValidationError(f"UW option-contracts {e}: data=null")
            uw.extend(pag)
            time.sleep(0.8)
        cache_put("uw_chain_spy.json", uw)
    arch = os.path.join(REPO, "data", "history", OPT_FECHA, f"chain_full_{OPT_SYM.lower()}.json")
    if not os.path.exists(arch):
        raise ValidationError(f"falta la cadena Polygon archivada {arch}")
    with open(arch) as fh:
        poly = json.load(fh)
    return lse_ch, uw, poly


def seccion_options(c):
    lse_ch, uw, poly = bajar_opciones(c)
    out = {"fecha_referencia": OPT_FECHA, "subyacente": OPT_SYM}
    campos_lse = sorted(lse_ch[OPT_EXPS[-1]][0].keys()) if lse_ch[OPT_EXPS[-1]] else []
    out["campos_lse"] = campos_lse
    out["ausencias_criticas"] = {
        "open_interest": "open_interest" not in campos_lse,
        "bid_ask": not any(k in campos_lse for k in ("bid", "ask", "nbbo_bid"))}

    # -- trampa 1: options() sin filtro devuelve lo MAS VIEJO y todo vencido
    sf = lse_ch["_sin_filtro"]
    exps_sf = sorted({r["expiry"] for r in sf})
    out["trampa_sin_filtro"] = {
        "filas": len(sf), "tope_5000": len(sf) >= 5000,
        "expiries": exps_sf[:4] + ["..."] + exps_sf[-3:],
        "ya_vencidos": sum(1 for r in sf if r["expiry"] < OPT_FECHA),
        "pct_vencidos": pct(sum(1 for r in sf if r["expiry"] < OPT_FECHA), len(sf)),
        "underlying_price_distintos": len({r.get("underlying_price") for r in sf}),
        "lectura": ("options(sym) sin expiry devuelve las filas MAS ANTIGUAS hasta el tope; "
                    "parece una cadena y son contratos ya vencidos")}

    # -- trampa 2: cada fila esta congelada en SU PROPIA ultima operacion
    congel = {}
    for e in OPT_EXPS:
        rows = lse_ch[e]
        if not rows:
            raise ValidationError(f"LSE options expiry={e}: cero filas")
        ups = sorted({r["underlying_price"] for r in rows if r.get("underlying_price")})
        dias = sorted({(r.get("last_trade_at") or "")[:10] for r in rows})
        congel[e] = {
            "filas": len(rows),
            "con_griegas": sum(1 for r in rows if r.get("delta") is not None),
            "underlying_price_distintos": len(ups),
            "underlying_price_min": ups[0] if ups else None,
            "underlying_price_max": ups[-1] if ups else None,
            "dispersion_spot_pct": (100.0 * (ups[-1] - ups[0]) / ups[0]) if len(ups) > 1 else None,
            "last_trade_dias_distintos": len(dias), "last_trade_mas_viejo": dias[0],
            "last_trade_mas_nuevo": dias[-1],
            "filas_del_ultimo_dia": sum(1 for r in rows
                                        if (r.get("last_trade_at") or "")[:10] == OPT_FECHA),
            "pct_del_ultimo_dia": pct(sum(1 for r in rows if (r.get("last_trade_at") or "")[:10] == OPT_FECHA), len(rows))}
    out["congelado_por_contrato"] = {
        "por_expiry": congel,
        "lectura": ("cada fila trae SU underlying_price, SU dte y SUS griegas del instante de "
                    "su ultima operacion. Sumar gamma entre strikes = sumar spots distintos")}

    # -- cruce strike a strike contra UW
    U = {r["option_symbol"]: r for r in uw}
    L = {}
    for e in OPT_EXPS:
        for r in lse_ch[e]:
            L[r["ticker"]] = r
    com = sorted(set(L) & set(U))
    campos = [("last_price", "last_price"), ("volume_today", "volume"),
              ("iv", "implied_volatility"), ("delta", "delta"), ("gamma", "gamma")]
    err = {k: [] for k, _ in campos}
    rel = {k: [] for k, _ in campos}
    err_f = {k: [] for k, _ in campos}
    put_ok = put_n = 0
    for t in com:
        a, b = L[t], U[t]
        fresco = (a.get("last_trade_at") or "")[:10] == OPT_FECHA
        if a["contract_type"] == "put" and a.get("delta") is not None:
            put_n += 1
            put_ok += a["delta"] <= 0
        for kl, ku in campos:
            va, vb = a.get(kl), b.get(ku)
            if va is None or vb is None:
                continue
            try:
                vb = float(vb)
            except (TypeError, ValueError):
                continue
            d = float(va) - vb
            err[kl].append(d)
            if abs(vb) > 1e-9:
                rel[kl].append(d / abs(vb))
            if fresco:
                err_f[kl].append(d)
    out["cruce_lse_uw"] = {
        "contratos_lse": len(L), "contratos_uw": len(U), "comunes": len(com),
        "solo_lse": len(set(L) - set(U)), "solo_uw": len(set(U) - set(L)),
        "error_absoluto": {k: resumen_abs(v) for k, v in err.items()},
        "error_relativo": {k: resumen_abs(v) for k, v in rel.items()},
        "error_solo_filas_del_dia": {k: resumen_abs(v) for k, v in err_f.items()},
        "delta_put_negativo": {"ok": put_ok, "de": put_n,
                               "convencion": "LSE usa delta de put NEGATIVO" if put_n and put_ok == put_n else "REVISAR"}}

    # -- cruce contra la cadena Polygon archivada (foto de las 15:34 ET)
    P = {}
    for r in poly["results"]:
        P[r["details"]["ticker"].replace("O:", "")] = r
    com_p = sorted(set(L) & set(P))
    ep = {"iv": [], "delta": [], "gamma": [], "last_price": []}
    n_g = 0
    for t in com_p:
        a, b = L[t], P[t]
        g = b.get("greeks") or {}
        if g:
            n_g += 1
        if a.get("iv") is not None and b.get("implied_volatility") is not None:
            ep["iv"].append(a["iv"] - b["implied_volatility"])
        if a.get("delta") is not None and g.get("delta") is not None:
            ep["delta"].append(a["delta"] - g["delta"])
        if a.get("gamma") is not None and g.get("gamma") is not None:
            ep["gamma"].append(a["gamma"] - g["gamma"])
        if a.get("last_price") is not None and (b.get("day") or {}).get("close"):
            ep["last_price"].append(a["last_price"] - b["day"]["close"])
    out["cruce_lse_polygon_archivo"] = {
        "snapshot_polygon": poly["meta"].get("snapshot_local"),
        "spot_polygon": poly["meta"].get("spot"),
        "contratos_polygon": len(P), "comunes": len(com_p),
        "polygon_con_griegas": n_g,
        "error_absoluto": {k: resumen_abs(v) for k, v in ep.items()},
        "aviso": "el archivo Polygon es de las 15:34 ET; parte del error es TIEMPO"}
    vl = sum(L[t].get("volume_today") or 0 for t in com)
    vu = sum(float(U[t].get("volume") or 0) for t in com)
    out["volumen_opciones"] = {"lse": vl, "uw": vu, "ratio": (vl / vu) if vu else None,
                               "contratos": len(com),
                               "aviso": "volume_today de LSE es el volumen del DIA DE SU ULTIMA "
                                        "OPERACION, no el de hoy"}
    return out, L


# ------------------------------------------------------------------ 5) GRIEGAS
def _t_anios(last_trade_at, expiry):
    t0 = dt.datetime.fromisoformat(last_trade_at.replace("Z", "+00:00"))
    t1 = dt.datetime.fromisoformat(f"{expiry}T20:00:00+00:00")   # 16:00 ET = 20:00 UTC (EDT)
    return (t1 - t0).total_seconds() / (365.0 * 24 * 3600.0)


def _bs_set(S, K, T, iv, cp, r, q):
    """delta, gamma, vega(1%), theta(dia), rho(1%) con dividendo continuo q."""
    if min(S, K, T, iv) <= 0:
        return None
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + iv * iv / 2.0) * T) / sq
    d2 = d1 - sq
    pdf = math.exp(-d1 * d1 / 2.0) / math.sqrt(2 * math.pi)
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    n1, n2 = gex_core._ncdf(d1), gex_core._ncdf(d2)
    if cp == "call":
        delta = dq * n1
        theta = (-S * dq * pdf * iv / (2 * math.sqrt(T)) - r * K * dr * n2 + q * S * dq * n1) / 365.0
        rho = K * T * dr * n2 / 100.0
    else:
        delta = dq * (n1 - 1.0)
        theta = (-S * dq * pdf * iv / (2 * math.sqrt(T)) + r * K * dr * (1 - n2)
                 - q * S * dq * (1 - n1)) / 365.0
        rho = -K * T * dr * (1 - n2) / 100.0
    return {"delta": delta, "gamma": dq * pdf / (S * sq), "vega": S * dq * pdf * math.sqrt(T) / 100.0,
            "theta": theta, "rho": rho}


def seccion_greeks(L):
    cand = [r for r in L.values()
            if r.get("iv") and r.get("delta") is not None and r.get("gamma")
            and r.get("underlying_price") and r.get("last_trade_at")
            and _t_anios(r["last_trade_at"], r["expiry"]) > 0]
    if len(cand) < 20:
        raise ValidationError(f"solo {len(cand)} contratos LSE con griegas utilizables: n<20")
    cand.sort(key=lambda r: (r["expiry"], abs(r["strike"] - r["underlying_price"])))
    sel, vistos = [], set()
    for r in cand:
        k = (r["expiry"], r["contract_type"], round(abs(r["strike"] - r["underlying_price"]) / 5))
        if k in vistos:
            continue
        vistos.add(k)
        sel.append(r)
        if len(sel) >= 20:
            break
    mejor = None
    for i in range(0, 33):
        for j in range(0, 13):
            r_, q_ = i * 0.0025, j * 0.0025
            e = []
            for c in sel:
                bs = _bs_set(c["underlying_price"], c["strike"],
                             _t_anios(c["last_trade_at"], c["expiry"]), c["iv"],
                             c["contract_type"], r_, q_)
                if bs is None:
                    continue
                for k in ("delta", "gamma", "vega", "theta"):
                    v = c.get(k)
                    if v is None or abs(v) < 1e-6:
                        continue
                    e.append((bs[k] - v) / abs(v))
            if e:
                sse = sum(x * x for x in e)
                if mejor is None or sse < mejor[0]:
                    mejor = (sse, r_, q_)
    if mejor is None:
        raise ValidationError("no se pudo ajustar r/q: ningun contrato produjo residuos")
    _, rb, qb = mejor
    err = {k: [] for k in ("delta", "gamma", "vega", "theta", "rho")}
    relv = {k: [] for k in err}
    filas = []
    for c in sel:
        T = _t_anios(c["last_trade_at"], c["expiry"])
        bs = _bs_set(c["underlying_price"], c["strike"], T, c["iv"], c["contract_type"], rb, qb)
        f = {"ticker": c["ticker"], "S": c["underlying_price"], "K": c["strike"],
             "T_anios": round(T, 6), "iv": c["iv"], "tipo": c["contract_type"]}
        for k in err:
            v, w = c.get(k), bs[k]
            f[f"lse_{k}"] = v
            f[f"bs_{k}"] = round(w, 6)
            if v is None:
                continue
            err[k].append(w - v)
            if abs(v) > 1e-6:
                relv[k].append((w - v) / abs(v))
        filas.append(f)
    return {"r_ajustado": rb, "q_ajustado": qb, "contratos": len(sel),
            "error_absoluto": {k: resumen_abs(v) for k, v in err.items()},
            "error_relativo": {k: resumen_abs(v) for k, v in relv.items()},
            "detalle": filas,
            "convenciones": {"vega": "por punto de vol (1%)", "theta": "por dia (anual/365)",
                             "rho": "por punto de tipo (1%)",
                             "T": "desde last_trade_at de la fila hasta 16:00 ET del vencimiento"}}


# ------------------------------------------------------------------ 6) HISTORIA
def seccion_history(c):
    out = {"catalogo": {}, "ventanas": []}
    cat = cache_get("lse_catalog_syms.json")
    if cat is None:
        todos = lse_retry(c.datasets)
        cat = [x for x in todos if x.get("symbol") in SYMS + [k for k, _, _ in KOREA]]
        cache_put("lse_catalog_syms.json", cat)
    for x in cat:
        out["catalogo"][f"{x['symbol']}/{x.get('dataset')}"] = {
            "primer_tick": x.get("first_tick"), "ultimo_tick": x.get("last_tick"),
            "ticks": x.get("ticks")}
    for ini, fin in VENTANAS_HIST:
        blob = cache_get(f"hist_{ini}.json")
        if blob is None:
            blob = {"lse": lse_retry(c.candles, "SPY", "1d", start=ini, end=fin, limit=50),
                    "yahoo": yahoo_daily("SPY", ini, fin)}
            cache_put(f"hist_{ini}.json", blob)
        Ld = {r["timestamp"][:10]: r for r in blob["lse"]}
        Yd = {r["d"]: r for r in blob["yahoo"]}
        com = sorted(set(Ld) & set(Yd))
        if not com:
            raise ValidationError(f"historia {ini}: cero dias comunes LSE/Yahoo")
        filas, errs, vr = [], {"o": [], "h": [], "l": [], "c": []}, []
        for d in com:
            a, b = Ld[d], Yd[d]
            filas.append({"dia": d, "lse": [a["open"], a["high"], a["low"], a["close"], a["volume"]],
                          "yahoo": [round(b["o"], 4), round(b["h"], 4), round(b["l"], 4),
                                    round(b["c"], 4), b["v"]]})
            for kk, la, yb in (("o", "open", "o"), ("h", "high", "h"),
                               ("l", "low", "l"), ("c", "close", "c")):
                errs[kk].append((a[la] - b[yb]) / b[yb] * 10000.0)   # puntos basicos
            if b["v"]:
                vr.append(a["volume"] / b["v"])
        # relleno sintetico se delata con dias repetidos o rangos identicos
        cl = [Ld[d]["close"] for d in com]
        out["ventanas"].append({
            "ventana": [ini, fin], "dias_lse": len(Ld), "dias_yahoo": len(Yd),
            "dias_comunes": len(com),
            "error_bp": {k: resumen_abs(v) for k, v in errs.items()},
            "cierres_distintos": len(set(cl)), "de_dias": len(cl),
            "ratio_volumen": {"media": st.mean(vr), "min": min(vr), "max": max(vr)} if vr else None,
            "detalle": filas})
    return out


# ------------------------------------------------------------------ 7) COREA
def _csv_bars(path):
    out = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.fromisoformat(r["date"])
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            out[int(t.timestamp() * 1000)] = {k: float(r[k]) for k in
                                              ("open", "high", "low", "close", "volume")}
    if not out:
        raise ValidationError(f"{path} sin filas")
    return out


def seccion_korea(c):
    out = {"por_simbolo": {}, "puente_naver": {}}
    for sym, rel, tick in KOREA:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            raise ValidationError(f"falta {path}")
        R = _csv_bars(path)
        ks = sorted(R)
        ini = dt.datetime.utcfromtimestamp(ks[0] / 1000).date().isoformat()
        fin = (dt.datetime.utcfromtimestamp(ks[-1] / 1000).date() + dt.timedelta(days=1)).isoformat()
        prof = {}
        for tf in ("1m", "1d"):
            a = lse_retry(c.candles, sym, tf, order="asc", limit=1)
            b = lse_retry(c.candles, sym, tf, order="desc", limit=1)
            if not a or not b:
                raise ValidationError(f"{sym} {tf}: LSE devolvio vacio")
            prof[tf] = {"primero": a[0]["timestamp"], "ultimo": b[0]["timestamp"]}
        L = lse_1m_rango(c, sym, ini, fin, paso_dias=3)
        com = sorted(set(L) & set(R))
        if not com:
            raise ValidationError(f"{sym}: cero minutos comunes LSE/CSV")
        vpos = [k for k in com if R[k]["volume"] > 0]
        ident = sum(1 for k in com if all(abs(L[k][f] - R[k][f]) < 1e-6
                                          for f in ("open", "high", "low", "close")))
        ident_v = sum(1 for k in vpos if all(abs(L[k][f] - R[k][f]) < 1e-6
                                             for f in ("open", "high", "low", "close")))
        vol_ig = sum(1 for k in vpos if abs(L[k]["volume"] - R[k]["volume"]) < 1e-6)
        ce = [L[k]["close"] - R[k]["close"] for k in vpos]
        vr = [L[k]["volume"] / R[k]["volume"] for k in vpos]
        # KRX cotiza en WON ENTEROS: cualquier decimal es corrupcion, no precio
        off_l = sum(1 for k in com for f in ("open", "high", "low", "close")
                    if abs(L[k][f] - round(L[k][f])) > 1e-9)
        off_r = sum(1 for k in com for f in ("open", "high", "low", "close")
                    if abs(R[k][f] - round(R[k][f])) > 1e-9)
        # y el precio debe caer en la rejilla de tick del tramo
        offtick_l = sum(1 for k in com for f in ("open", "high", "low", "close")
                        if abs(L[k][f] - round(L[k][f] / tick) * tick) > 1e-6)
        offtick_r = sum(1 for k in com for f in ("open", "high", "low", "close")
                        if abs(R[k][f] - round(R[k][f] / tick) * tick) > 1e-6)
        sh = {}
        for d_ in (-2, -1, 0, 1, 2):
            n = e = 0
            for k in vpos:
                k2 = k + d_ * 60000
                if k2 in R:
                    n += 1
                    e += abs(L[k]["close"] - R[k2]["close"]) < 1e-6
            sh[d_] = pct(e, n)
        out["por_simbolo"][sym] = {
            "profundidad_lse": prof,
            "csv_casa": {"fichero": rel, "n": len(R),
                         "primero": dt.datetime.utcfromtimestamp(ks[0] / 1000).isoformat() + "Z",
                         "ultimo": dt.datetime.utcfromtimestamp(ks[-1] / 1000).isoformat() + "Z"},
            "cobertura": {"lse_en_rango": len(L), "comunes": len(com),
                          "solo_lse": len(set(L) - set(R)), "solo_csv": len(set(R) - set(L)),
                          "minutos_volumen_cero_en_csv": len(com) - len(vpos)},
            "ohlc_4de4_identico": ident, "pct_ohlc_4de4": pct(ident, len(com)),
            "ohlc_4de4_solo_volumen_positivo": ident_v, "pct_4de4_vol_pos": pct(ident_v, len(vpos)),
            "volumen_exactamente_igual": vol_ig, "pct_volumen_igual": pct(vol_ig, len(vpos)),
            "error_close": resumen_abs(ce),
            "error_close_pct_del_precio": (resumen_abs(ce)["mediana_abs"] /
                                           st.median([R[k]["close"] for k in vpos]) * 100.0),
            "ratio_volumen": {"mediana": st.median(vr), "media": st.mean(vr)},
            "tick_krx_won": tick,
            "valores_no_enteros": {"lse": off_l, "csv": off_r, "de_valores": 4 * len(com)},
            "fuera_de_rejilla_de_tick": {"lse": offtick_l, "csv": offtick_r,
                                         "de_valores": 4 * len(com)},
            "desplazamiento_close_pct": sh}
        print(f"  [korea {sym}] 4de4={pct(ident, len(com)):.2f}% volIgual="
              f"{pct(vol_ig, len(vpos)):.2f}% noEnteros={off_l}", flush=True)
    # que produce hoy el puente Naver (contrato de fichero de la casa)
    nb = {}
    for name in ("samsung", "skhynix", "kospi", "kospi200", "kodex200"):
        p = os.path.join(REPO, "data", f"bars_{name}.txt")
        if os.path.exists(p):
            with open(p) as fh:
                ln = fh.read().strip().splitlines()
            nb[name] = {"fichero": f"data/bars_{name}.txt", "lineas": len(ln),
                        "ultima": ln[-1] if ln else None,
                        "mtime": dt.datetime.utcfromtimestamp(os.path.getmtime(p)).isoformat() + "Z"}
        else:
            nb[name] = {"fichero": f"data/bars_{name}.txt", "existe": False}
    out["puente_naver"] = {"ficheros": nb,
                           "nota": "korea_naver_bridge NO escribe nbbo (el endpoint de libro da 404)"}
    return out


# ------------------------------------------------------------------ MAIN
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secciones", default="all")
    ap.add_argument("--salida", default=OUT_JSON)
    a = ap.parse_args()
    todas = ["bars", "relleno", "volume", "options", "greeks", "history", "korea"]
    quiere = set(todas) if a.secciones == "all" else set(a.secciones.split(","))
    mal = quiere - set(todas)
    if mal:
        raise SystemExit(f"secciones desconocidas: {sorted(mal)}")

    res = {"generado": dt.datetime.now(dt.timezone.utc).isoformat(),
           "fuente_lse": "https://api.londonstrategicedge.com/vault (sdk lse-data 0.14.0)",
           "simbolos": SYMS, "sesiones": SESIONES, "secciones": sorted(quiere),
           "cache": CACHE_DIR, "errores": {}}
    c = lse_client()

    def corre(nombre, fn, *args):
        if nombre not in quiere:
            return None
        try:
            v = fn(*args)
            res[nombre] = v
            print(f"[{nombre}] ok", flush=True)
            return v
        except Exception as e:            # se REGISTRA el fallo, no se disfraza de dato
            res["errores"][nombre] = f"{type(e).__name__}: {e}"
            print(f"[{nombre}] FALLO: {type(e).__name__}: {e}", flush=True)
            return None

    datos = None
    if quiere & {"bars", "relleno", "volume"}:
        p = poly_client()
        datos = bajar_barras(c, p)
        res["polygon_ritmo"] = p.report()
    if datos is not None:
        corre("bars", seccion_bars, datos)
        corre("relleno", seccion_relleno, datos, c)
        corre("volume", seccion_volume, datos)

    L_chain = None
    if quiere & {"options", "greeks"}:
        try:
            opt, L_chain = seccion_options(c)
            if "options" in quiere:
                res["options"] = opt
                print("[options] ok", flush=True)
        except Exception as e:
            res["errores"]["options"] = f"{type(e).__name__}: {e}"
            print(f"[options] FALLO: {e}", flush=True)
    if L_chain is not None:
        corre("greeks", seccion_greeks, L_chain)
    corre("history", seccion_history, c)
    corre("korea", seccion_korea, c)

    atomic_write(a.salida, json.dumps(res, indent=1, default=str))
    print(f"escrito {a.salida}  (secciones ok: {sorted(set(quiere) - set(res['errores']))})")
    return 1 if res["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
