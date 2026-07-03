#!/usr/bin/env python3
"""gaps.py — ficha 26 `gap-islands`: EXPORTADOR DE NIVELES + CORTES DE ISLA.

Lo que este fichero SI hace:
  * detecta huecos overnight   |open_0930 - close_prev| > k_on * ATR14_diario
  * detecta discontinuidades intradia 1m |open_t - close_{t-1}| > k_id * ATR14_1m
  * mantiene el registro de huecos SIN RELLENAR por sym
  * publica `gap_proximity` y el borde no rellenado mas cercano
  * publica los CORTES DE ISLA (huecos > 3*ATR): ningun nivel/KDE puede cruzarlos

Lo que este fichero JAMAS hace:
  * `p_fill` NO SE COMPUTA. La clave NO EXISTE en el JSON. El folklore de "los huecos
    se rellenan el X%" no se afirma en esta casa. El null que lo mata (toque simetrico)
    se corre con `--validate` y su resultado se publica en docs/GAPS-KDE-2026-07-25.md.
  * ordenes. SEÑAL-SOLAMENTE.

`earnings_gap` sale `None` mientras no exista una fuente fiable de fechas de earnings.
NUNCA `False`: `False` seria afirmar "este hueco no es de earnings" sin haberlo medido.

Uso:
  python3 scripts/gaps.py                 # escribe data/gaps.json
  python3 scripts/gaps.py --validate      # barrido de k_on + null de toque simetrico
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import sys
import tempfile
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "trades.db")
OUT = os.path.join(REPO, "data", "gaps.json")
FLEET = os.path.join(REPO, "data", "fleet.txt")

ET = ZoneInfo("America/New_York")

# `K_ON` MEDIDO con --validate el 2026-07-25 sobre 28 syms x ~501 sesiones (poly_bars).
#   - la SEPARACION cruda (hueco vs sin-hueco a la misma distancia) crece hasta k=3.0,
#     pero alli n_dias=53 y el null de TOQUE SIMETRICO ya no se bate: esa "separacion"
#     es volatilidad del dia de hueco, no direccionalidad del hueco.
#   - el maximo de la separacion CONSERVADORA (Wilson LB-UB) esta en k=1.5 (+12.8pp).
#   - k=1.0 es el unico tramo donde ademas se bate el null simetrico con LB positivo
#     (+3.1pp) y con la evidencia pareada mas fuerte (McNemar chi2=16.5, n_dias=312).
# Se elige 1.0: separacion grande Y superviviente del null. Detalle en
# docs/GAPS-KDE-2026-07-25.md. `K_ID` NO esta medido -> SOSPECHADO.
K_ON = 1.0
K_ID = 4.0
ISLAND_MULT = 3.0        # hueco > 3*ATR = corte de isla (ficha 26 punto 4)

RTH_OPEN_MIN = 9 * 60 + 30
RTH_CLOSE_MIN = 15 * 60 + 59


# --------------------------------------------------------------------------- ATR
def atr14(bars, n=14):
    """ATR de Wilder sobre `bars` = [(o,h,l,c), ...]. Devuelve None si no hay barras
    suficientes. NUNCA devuelve 0.0 por falta de datos: eso convertiria "no se" en
    "se, y no hay rango"."""
    if bars is None or len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l = bars[i][1], bars[i][2]
        pc = bars[i - 1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    if not (a > 0) or not math.isfinite(a):
        return None       # rango nulo = dato roto, no un cero legitimo
    return a


def atr14_series(bars, n=14):
    """ATR14 alineado a `bars`: out[i] es el ATR con informacion hasta bars[i-1]
    INCLUSIVE (sin look-ahead sobre la barra i). None donde no alcanza la historia."""
    out = [None] * len(bars)
    for i in range(len(bars)):
        out[i] = atr14(bars[max(0, i - 60):i], n)
    return out


# ------------------------------------------------------------------- deteccion
def detect_overnight_gaps(daily, k_on=K_ON, atrs=None):
    """`daily` = [{date, o,h,l,c}, ...] cronologico. Devuelve los huecos overnight.

    Un hueco es la banda ENTRE el cierre previo y la apertura:
      gap-up   : lo = close_prev, hi = open      (dir = +1)
      gap-down : lo = open,       hi = close_prev(dir = -1)
    El borde LEJANO (el que hay que alcanzar para rellenarlo) es siempre `close_prev`.
    """
    if atrs is None:
        atrs = atr14_series([(b["o"], b["h"], b["l"], b["c"]) for b in daily])
    gaps = []
    for i in range(1, len(daily)):
        atr = atrs[i]
        if atr is None:
            continue
        prev_c = daily[i - 1]["c"]
        op = daily[i]["o"]
        d = op - prev_c
        if abs(d) <= k_on * atr:
            continue
        gaps.append({
            "date": daily[i]["date"],
            "idx": i,
            "lo": round(min(prev_c, op), 4),
            "hi": round(max(prev_c, op), 4),
            "far_edge": round(prev_c, 4),      # el borde que hay que tocar para rellenar
            "near_edge": round(op, 4),
            "size_atr": round(abs(d) / atr, 3),
            "dir": 1 if d > 0 else -1,
            "atr_at_open": round(atr, 4),
            "earnings_gap": None,              # sin fuente de fechas -> None, jamas False
        })
    return gaps


def detect_intraday_discontinuities(bars1m, k_id=K_ID, atr_1m=None):
    """Discontinuidades DENTRO de la sesion: |open_t - close_{t-1}| > k_id * ATR14_1m.
    `bars1m` = [(ts,o,h,l,c), ...] de una sola sesion, cronologico."""
    if atr_1m is None:
        atr_1m = atr14([(b[1], b[2], b[3], b[4]) for b in bars1m])
    if atr_1m is None:
        return None            # sin ATR no se afirma nada
    out = []
    for i in range(1, len(bars1m)):
        d = bars1m[i][1] - bars1m[i - 1][4]
        if abs(d) > k_id * atr_1m:
            out.append({
                "ts": bars1m[i][0],
                "lo": round(min(bars1m[i - 1][4], bars1m[i][1]), 4),
                "hi": round(max(bars1m[i - 1][4], bars1m[i][1]), 4),
                "size_atr": round(abs(d) / atr_1m, 3),
                "dir": 1 if d > 0 else -1,
            })
    return out


def open_gap_registry(daily, k_on=K_ON, atrs=None):
    """Huecos overnight AUN SIN RELLENAR al final de `daily`.

    Cierre del registro: un hueco se cierra cuando cualquier sesion POSTERIOR alcanza
    su borde LEJANO (gap-up -> low <= close_prev; gap-down -> high >= close_prev).
    """
    gaps = detect_overnight_gaps(daily, k_on, atrs)
    last = len(daily) - 1
    live = []
    for g in gaps:
        filled = False
        for j in range(g["idx"], len(daily)):
            b = daily[j]
            if g["dir"] > 0 and b["l"] <= g["far_edge"]:
                filled = True
                break
            if g["dir"] < 0 and b["h"] >= g["far_edge"]:
                filled = True
                break
        if filled:
            continue
        live.append({
            "date": g["date"],
            "lo": g["lo"],
            "hi": g["hi"],
            "far_edge": g["far_edge"],
            "size_atr": g["size_atr"],
            "dir": g["dir"],
            "age_days": last - g["idx"],
            "earnings_gap": g["earnings_gap"],
        })
    return live


def island_cuts(gaps, mult=ISLAND_MULT):
    """CORTES DE ISLA: los huecos > `mult`*ATR. Ningun nivel (KDE incluido) puede
    trazarse a traves de uno de estos."""
    return [{"lo": g["lo"], "hi": g["hi"], "size_atr": g["size_atr"],
             "date": g.get("date")} for g in gaps if g["size_atr"] > mult]


def gap_proximity(price, open_gaps, atr):
    """(distancia con signo al borde no rellenado mas cercano) / ATR, y ese borde.
    Devuelve (None, None) si no hay huecos vivos o no hay ATR — nunca 0.0."""
    if atr is None or not open_gaps:
        return None, None
    edges = []
    for g in open_gaps:
        edges.append(g["lo"])
        edges.append(g["hi"])
    nearest = min(edges, key=lambda e: abs(price - e))
    return round((price - nearest) / atr, 3), round(nearest, 4)


def crosses_island(lo, hi, cuts):
    """True si el intervalo de precio [lo,hi] atraviesa un corte de isla."""
    a, b = (lo, hi) if lo <= hi else (hi, lo)
    for c in cuts:
        if a < c["hi"] and b > c["lo"]:
            return True
    return False


# ------------------------------------------------------------------------ datos
def _ro(db=DB):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def fleet():
    with open(FLEET) as f:
        return [s.strip().upper() for s in f.read().split() if s.strip()]


def load_daily(conn, sym, rth_only=True):
    """Agrega poly_bars 1m -> sesiones diarias RTH (09:30-15:59 ET).

    TRAMPA MEDIDA 2026-07-25: `ts` esta en MILISEGUNDOS. `date(ts,'unixepoch')`
    devuelve NULL sobre las 540 sesiones. Aqui se divide entre 1000 SIEMPRE.
    """
    rows = conn.execute(
        "SELECT ts,o,h,l,c,v FROM poly_bars WHERE sym=? ORDER BY ts", (sym,)).fetchall()
    if not rows:
        return []
    days = {}
    for ts, o, h, l, c, v in rows:
        d = dt.datetime.fromtimestamp(ts / 1000, ET)
        mins = d.hour * 60 + d.minute
        if rth_only and not (RTH_OPEN_MIN <= mins <= RTH_CLOSE_MIN):
            continue
        key = d.strftime("%Y-%m-%d")
        s = days.get(key)
        if s is None:
            days[key] = {"date": key, "o": o, "h": h, "l": l, "c": c,
                         "v": v or 0.0, "first": mins}
        else:
            s["h"] = max(s["h"], h)
            s["l"] = min(s["l"], l)
            s["c"] = c
            s["v"] += (v or 0.0)
    return [days[k] for k in sorted(days)]


def load_session_1m(conn, sym, day, rth_only=True):
    """Barras 1m de UNA sesion ET."""
    start = dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=ET)
    a = int(start.timestamp() * 1000)
    b = a + 24 * 3600 * 1000
    out = []
    for ts, o, h, l, c, v in conn.execute(
            "SELECT ts,o,h,l,c,v FROM poly_bars WHERE sym=? AND ts>=? AND ts<? ORDER BY ts",
            (sym, a, b)):
        d = dt.datetime.fromtimestamp(ts / 1000, ET)
        mins = d.hour * 60 + d.minute
        if rth_only and not (RTH_OPEN_MIN <= mins <= RTH_CLOSE_MIN):
            continue
        out.append((ts, o, h, l, c, v))
    return out


def atomic_write(path, obj):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".gaps.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ------------------------------------------------------------------------ build
def build(syms=None, k_on=K_ON, k_id=K_ID, db=DB, out=OUT):
    conn = _ro(db)
    syms = syms or fleet()
    res = {"_meta": {
        "generated": int(dt.datetime.now(dt.timezone.utc).timestamp()),
        "k_on": k_on, "k_id": k_id, "island_mult": ISLAND_MULT,
        "src": "poly_bars (ts en ms) RTH 09:30-15:59 ET",
        "probabilidad_de_relleno": "NO SE COMPUTA — ver docs/GAPS-KDE-2026-07-25.md",
        "earnings_gap": "None en toda la flota: no hay fuente de fechas de earnings",
    }}
    for sym in syms:
        daily = load_daily(conn, sym)
        if len(daily) < 30:
            res[sym] = {"open_gaps": None, "island_cuts": None, "proximity_atr": None,
                        "nearest_edge": None, "n_sessions": len(daily),
                        "why": "historia insuficiente (<30 sesiones)"}
            continue
        bars = [(b["o"], b["h"], b["l"], b["c"]) for b in daily]
        atrs = atr14_series(bars)
        atr_now = atr14(bars[-60:])
        og = open_gap_registry(daily, k_on, atrs)
        allg = detect_overnight_gaps(daily, k_on, atrs)
        price = daily[-1]["c"]
        prox, edge = gap_proximity(price, og, atr_now)
        res[sym] = {
            "n_sessions": len(daily),
            "last_date": daily[-1]["date"],
            "price": round(price, 4),
            "atr14": round(atr_now, 4) if atr_now is not None else None,
            "open_gaps": og,
            "island_cuts": island_cuts(allg),
            "proximity_atr": prox,
            "nearest_edge": edge,
        }
    conn.close()
    atomic_write(out, res)
    return res


# ------------------------------------------------------------------- validacion
def _session_touch(bars, level, side):
    """side=+1: se toca si algun high >= level. side=-1: si algun low <= level."""
    if side > 0:
        return any(b[2] >= level for b in bars)
    return any(b[3] <= level for b in bars)


def _wilson(k, n, z=1.96):
    if n == 0:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def validate(syms=None, db=DB, ks=None, min_sessions=200):
    """Barrido de k_on. Se eligen umbrales por SEPARACION, no por tasa de relleno.

    Tres tasas, TODAS a la MISMA distancia `k_on*ATR14` desde la apertura (asi la
    comparacion no esta confundida por la distancia, que es el vicio del folklore):

      RETRO_GAP  : dias CON hueco  — se toca open - dir*k*ATR (retroceso, "relleno")
      RETRO_FLAT : dias SIN hueco  — mismo nivel, misma direccion nominal
      SIM_GAP    : dias CON hueco  — se toca open + dir*k*ATR (TOQUE SIMETRICO = el null)

    separacion  = RETRO_GAP - RETRO_FLAT   (¿el hueco cambia algo?)
    delta_null  = RETRO_GAP - SIM_GAP      (¿el hueco es DIRECCIONAL, o solo volatil?)
    """
    conn = _ro(db)
    syms = syms or fleet()
    ks = ks or [round(0.3 + 0.1 * i, 1) for i in range(28)]     # 0.3 .. 3.0
    per_sym = {}
    for sym in syms:
        daily = load_daily(conn, sym)
        if len(daily) < min_sessions:
            per_sym[sym] = {"n_sessions": len(daily), "why": "n < %d" % min_sessions}
            continue
        bars = [(b["o"], b["h"], b["l"], b["c"]) for b in daily]
        atrs = atr14_series(bars)
        rows = []
        for i in range(1, len(daily)):
            if atrs[i] is None:
                continue
            d = daily[i]["o"] - daily[i - 1]["c"]
            if d == 0:
                continue
            rows.append((abs(d) / atrs[i], 1 if d > 0 else -1, daily[i]["date"],
                         daily[i]["o"], daily[i]["h"], daily[i]["l"], atrs[i]))
        out = {}
        for k in ks:
            g_r = g_n = f_r = f_n = s_r = s_n = 0
            b_ret = b_sym = 0          # discordantes de McNemar (par retro/simetrico)
            days = set()
            for size, dirn, day, op, hi, lo, atr in rows:
                dist = k * atr
                retro = op - dirn * dist          # contra el hueco (hacia el cierre previo)
                sym_lv = op + dirn * dist         # simetrico, al otro lado
                hit_retro = (lo <= retro) if dirn > 0 else (hi >= retro)
                hit_sym = (hi >= sym_lv) if dirn > 0 else (lo <= sym_lv)
                if size > k:
                    g_n += 1
                    g_r += hit_retro
                    s_n += 1
                    s_r += hit_sym
                    days.add(day)
                    if hit_retro and not hit_sym:
                        b_ret += 1
                    elif hit_sym and not hit_retro:
                        b_sym += 1
                else:
                    f_n += 1
                    f_r += hit_retro
            out[k] = {"gap_k": g_r, "gap_n": g_n, "flat_k": f_r, "flat_n": f_n,
                      "sym_k": s_r, "sym_n": s_n, "mcn_b": b_ret, "mcn_c": b_sym,
                      "days": days}
        per_sym[sym] = {"n_sessions": len(daily), "sweep": out}
    conn.close()

    # pool sobre los syms con historia; se reporta n por sym aparte (cobertura desigual).
    # `n_dias` = fechas DISTINTAS con hueco: en una flota 26/30 semis el sym-dia NO es
    # una observacion independiente (todos abren con hueco el mismo dia). El n honesto
    # para cualquier intervalo esta mas cerca de `n_dias` que de `gap_n`.
    pooled = {}
    for k in ks:
        g_r = g_n = f_r = f_n = s_r = s_n = b = c = 0
        alldays = set()
        for sym, d in per_sym.items():
            if "sweep" not in d:
                continue
            q = d["sweep"][k]
            g_r += q["gap_k"]; g_n += q["gap_n"]
            f_r += q["flat_k"]; f_n += q["flat_n"]
            s_r += q["sym_k"]; s_n += q["sym_n"]
            b += q["mcn_b"]; c += q["mcn_c"]
            alldays |= q["days"]
        if g_n < 60 or f_n < 60:
            pooled[k] = {"gap_n": g_n, "flat_n": f_n, "separacion": None,
                         "why": "n < 60 en alguna rama"}
            continue
        pg, plo, phi = _wilson(g_r, g_n)
        pf, flo, fhi = _wilson(f_r, f_n)
        ps, slo, shi = _wilson(s_r, s_n)
        # McNemar (pareado retro vs simetrico, mismos dias): chi2 con correccion de
        # continuidad. NO corrige el clustering entre syms -> es un LIMITE OPTIMISTA.
        mcn = ((abs(b - c) - 1) ** 2 / (b + c)) if (b + c) > 0 else None
        pooled[k] = {
            "gap_n": g_n, "flat_n": f_n, "sym_n": s_n, "n_dias": len(alldays),
            "p_retro_gap": round(pg, 4), "p_retro_gap_lb": round(plo, 4),
            "p_retro_flat": round(pf, 4), "p_retro_flat_lb": round(flo, 4),
            "p_sym_gap": round(ps, 4),
            "separacion": round(pg - pf, 4),
            "delta_null": round(pg - ps, 4),
            "sep_lb": round(plo - fhi, 4),          # separacion conservadora (LB - UB)
            "null_lb": round(plo - shi, 4),         # idem contra el toque simetrico
            "mcnemar_b": b, "mcnemar_c": c,
            "mcnemar_chi2": round(mcn, 2) if mcn is not None else None,
        }
    return {"per_sym": {s: d.get("n_sessions") for s, d in per_sym.items()},
            "pooled": pooled}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--k-on", type=float, default=K_ON)
    ap.add_argument("--k-id", type=float, default=K_ID)
    a = ap.parse_args(argv)
    syms = [s.upper() for s in a.syms] or None
    if a.validate:
        r = validate(syms)
        print(json.dumps(r, indent=1))
        return 0
    res = build(syms, a.k_on, a.k_id)
    n_live = sum(len(v["open_gaps"]) for k, v in res.items()
                 if k != "_meta" and v.get("open_gaps"))
    n_cut = sum(len(v["island_cuts"]) for k, v in res.items()
                if k != "_meta" and v.get("island_cuts"))
    print(f"gaps.json: {len(res)-1} syms · {n_live} huecos vivos · {n_cut} cortes de isla "
          f"· k_on={a.k_on} · p_fill NO COMPUTADO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
