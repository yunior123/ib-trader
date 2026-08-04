#!/usr/bin/env python3
"""backtest_alertas_flota.py — backtest honesto de las alertas de la flota.

LOTE FUERA DE SESION (no es camino de señal): mide, no dispara. SEÑAL-SOLAMENTE.
Python 3.9 (./venv/bin/python). Escritura atomica tmp + os.replace.

Metodo (skills measured-probability / walk-forward-validation / anti-overfit-killlist):
  1. VERDAD DE TERRENO PRIMERO. Un sym-dia solo entra si tiene >= MIN_RTH de las 390
     barras 1m RTH ARCHIVADAS. Si no, se EXCLUYE y se reporta con nombre y nº de barras.
     Prohibido rellenar, interpolar o devolver 0/0.5/50.
  2. Etiquetado TRIPLE BARRERA (TP/SL = k*ATR14_1m). Timeout = None, NUNCA victoria.
     Barra que contiene TP y SL = ambigua -> se resuelve SL (conservador) y se publica.
  3. Wilson 95% sobre muestra EFECTIVA corregida por correlacion MEDIDA (no hardcodeada)
     y TOPADA por el nº de clusters (fecha, ventana de 5 min): una rafaga multi-simbolo
     del mismo minuto es ~1 observacion, no 26.
  4. Null de entrada aleatoria emparejado en (sym, hora del dia), misma direccion, mismo H.
     Bootstrap por bloques sobre la DIFERENCIA.
  5. BH-FDR q=0.10 sobre todos los tests a la vez.
  6. n_eff < MIN_NEFF -> DATA-INSUFICIENTE. No se publica probabilidad.

Uso:
  ./venv/bin/python scripts/backtest_alertas_flota.py --days 2026-07-21..2026-08-03
  ./venv/bin/python scripts/backtest_alertas_flota.py --day 2026-08-03 --json out.json
  ./venv/bin/python scripts/backtest_alertas_flota.py --days ... --cuts --sweep
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import random
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGDIR = os.path.join(REPO, "data", "trading-signals")
HISTDIR = os.path.join(REPO, "data", "history")
DATADIR = os.path.join(REPO, "data")

MIN_RTH = 380            # de 390 barras RTH. Por debajo el sym-dia se EXCLUYE.
MIN_NEFF = 30.0          # por debajo: DATA-INSUFICIENTE
WARMUP_HOUR = 8          # las barras 08:00-09:29 solo sirven de calentamiento del ATR
RTH_OPEN = (9, 30)
RTH_CLOSE = (16, 0)
RTH_BARS = 390
HORIZONS = [5, 15, 30, 60, RTH_BARS]     # el ultimo = "hasta el cierre"
K_GRID = [0.5, 0.75, 1.0, 1.5]           # curva de sensibilidad (anti-overfit test #4)
K_DEFAULT = 1.0
NULL_DRAWS = 20
BOOT_N = 2000
FDR_Q = 0.10
KEEP_FLOOR = 0.50        # un KEEP tiene que ser operable, no solo batir al null
CONFLICT_TOL = 0.005     # archivo vs buffer vivo: >50 bp de diferencia = pasado reescrito


# ----------------------------------------------------------------- barras

def read_bars(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, errors="replace") as fh:
        for line in fh:
            p = line.split()
            if len(p) < 5:
                continue
            try:
                out[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]), float(p[4]))
            except ValueError:
                continue
    return out


def day_bounds(date):
    y, m, d = [int(x) for x in date.split("-")]
    warm = int(dt.datetime(y, m, d, WARMUP_HOUR, 0).timestamp())
    op = int(dt.datetime(y, m, d, RTH_OPEN[0], RTH_OPEN[1]).timestamp())
    cl = int(dt.datetime(y, m, d, RTH_CLOSE[0], RTH_CLOSE[1]).timestamp())
    return warm, op, cl


def load_symbol_day(sym, date):
    """OHLC 08:00-16:00 de un sym-dia. Union archivo diario + buffer vivo.
    Cuando ambos tienen la misma barra: manda el ARCHIVO (se escribio el mismo dia,
    del mismo feed que leyeron los bots). Si difieren mas de CONFLICT_TOL la barra se
    DESCARTA: ahi no sabemos cual pasado es el bueno y no se elige ganador
    (las alertas TRUTH-LOCK del feed prueban que el pasado se reescribia)."""
    warm, _op, cl = day_bounds(date)
    hist = read_bars(os.path.join(HISTDIR, date, "bars", "%s.txt" % sym.lower()))
    live = read_bars(os.path.join(DATADIR, "bars_%s_ibkr.txt" % sym.lower()))
    out = {}
    conflicts = 0
    for ep in range(warm, cl, 60):
        a = hist.get(ep)
        b = live.get(ep)
        if a is not None and b is not None and a != b:
            rel = max(abs(x - y) / abs(y) if y else 1.0 for x, y in zip(a, b))
            if rel > CONFLICT_TOL:
                conflicts += 1
                continue
        v = a if a is not None else b
        if v is not None:
            out[ep] = v
    return out, conflicts


def audit_bars(dates, fleet):
    """Verdad de terreno. Devuelve (admitidos, excluidos). No rellena nada."""
    admitted = {}
    excluded = []
    for date in dates:
        _warm, op, cl = day_bounds(date)
        for sym in fleet:
            bars, conflicts = load_symbol_day(sym, date)
            n_rth = sum(1 for ep in bars if op <= ep < cl)
            if n_rth < MIN_RTH:
                excluded.append({"date": date, "sym": sym, "rth_bars": n_rth,
                                 "missing": RTH_BARS - n_rth, "conflicts": conflicts})
                continue
            admitted[(date, sym)] = bars
    return admitted, excluded


# ----------------------------------------------------------------- alertas

def classify(kind, msg):
    """(tipo, direccion). Verificado contra el productor; ver el doc para fichero:linea.
    direccion: +1 = se espera que suba, -1 = baje, 0 = no direccional (PIN)."""
    k = kind.strip()
    up = (k + " " + msg).upper()
    if "WARMUP" in up:
        return None
    if k.startswith("\U0001F388 BB REBOTE"):        # 🎈
        d = 1 if " ABAJO " in up else (-1 if " ARRIBA " in up else 0)
        if "[VETO" in k:
            t = "BB_REBOTE_VETO"
        elif "degradada" in k:
            t = "BB_REBOTE_STAR"
        else:
            t = "BB_REBOTE"
        return t, d
    if k.startswith("\U0001F388 BB 15m RE-ENTRADA"):
        d = -1 if " ARRIBA " in up else (1 if " ABAJO " in up else 0)
        return ("BB15_REENTRADA_MUTED" if "MUTED" in k else "BB15_REENTRADA"), d
    if k.startswith("\U0001F388 BB BAND-WALK"):
        d = 1 if " ARRIBA " in up else (-1 if " ABAJO " in up else 0)
        return ("BB_BANDWALK_MUTED" if "MUTED" in k else "BB_BANDWALK"), d
    if "APERTURA FUERA DE BANDA" in k:
        d = -1 if "ARRIBA DE LA BANDA" in up else (1 if "ABAJO DE LA BANDA" in up else 0)
        return "APERTURA_FUERA_BANDA", d
    if "TERREMOTO ALZA" in k:
        return "CUSUM_TERREMOTO", 1
    if "TERREMOTO CAIDA" in k:
        return "CUSUM_TERREMOTO", -1
    if k.startswith("\U0001F9F2 ESTRUCTURAL magnet"):   # 🧲
        d = 1 if "↑" in msg else (-1 if "↓" in msg else 0)
        return "ESTRUCTURAL_MAGNET", d
    if k.startswith("\U0001F9F2 ESTRUCTURAL pin"):
        return "ESTRUCTURAL_PIN", 0
    if "BALLENA CALLS" in k:
        return "BALLENA_CALLS", -1      # espada-ballena: calls masivas = techo local
    if "BALLENA PUTS" in k:
        return "BALLENA_PUTS", 1
    if "BALLENA CRECE" in k:
        return "BALLENA_CRECE", -1 if "calls" in msg.lower() else 1
    if "SPIKE CALLS" in k:
        return "SPIKE_CALLS", -1
    if "SPIKE PUTS" in k:
        return "SPIKE_PUTS", 1
    if "MANADA A CALLS" in k:
        return "MANADA_CALLS", -1
    if "MANADA A PUTS" in k:
        return "MANADA_PUTS", 1
    if "DIP REAL" in k:
        return "DIP_REAL", 1
    return None


TOK_RE = re.compile(r"\b[A-Z]{2,5}\b")
PX_RE = re.compile(r"(?:px|en|precio|@)\s+\$?(\d{1,6}\.\d{1,4})", re.I)
MAGNET_RE = re.compile(r"im[aá]n\s+(\d{1,6}(?:\.\d+)?)", re.I)


def extract_symbol(kind, msg, fleet_set):
    for tok in TOK_RE.findall(kind):
        if tok in fleet_set:
            return tok
    for tok in TOK_RE.findall(msg):
        if tok in fleet_set:
            return tok
    return None


def extract_msg_price(msg):
    m = PX_RE.search(msg)
    if m:
        return float(m.group(1))
    m = re.search(r"\b(\d{1,6}\.\d{2})\b", msg)
    return float(m.group(1)) if m else None


def parse_day(date, fleet_set):
    path = os.path.join(SIGDIR, "%s.txt" % date)
    if not os.path.exists(path):
        return []
    y, mo, d = [int(x) for x in date.split("-")]
    out = []
    with open(path, errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            parts = line.rstrip("\n").split(" | ")
            if len(parts) < 3:
                continue
            ts_txt = parts[0].strip()
            if not re.match(r"^\d{2}:\d{2}:\d{2}$", ts_txt):
                continue
            kind = parts[1].strip()
            msg = " | ".join(parts[2:]).strip()
            c = classify(kind, msg)
            if c is None:
                continue
            typ, direction = c
            if typ.startswith("MANADA"):
                sym = "QQQ"                 # la manada habla del INDICE, no del nombre
            else:
                sym = extract_symbol(kind, msg, fleet_set)
            if not sym:
                continue
            hh, mm, ss = [int(x) for x in ts_txt.split(":")]
            ts = int(dt.datetime(y, mo, d, hh, mm, ss).timestamp())
            mg = MAGNET_RE.search(msg)
            out.append({"date": date, "ts": ts, "ts_txt": ts_txt, "type": typ,
                        "dir": direction, "sym": sym, "kind": kind, "msg": msg,
                        "msg_price": extract_msg_price(msg),
                        "magnet": float(mg.group(1)) if mg else None,
                        "line": lineno})
    return out


# ----------------------------------------------------------------- etiquetado

def atr14(bars, i):
    """ATR14 con las 14 barras ESTRICTAMENTE anteriores a i, exigiendo contigüidad
    (una barra ausente invalida el ATR: no se rellena, se devuelve None)."""
    if i < 15:
        return None
    trs = []
    for j in range(i - 14, i):
        if bars[j][0] + 60 != bars[j + 1][0] or bars[j - 1][0] + 60 != bars[j][0]:
            return None
        _o, h, l, _c = bars[j][1]
        pc = bars[j - 1][1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else None


def triple_barrier(bars, i, direction, k_tp, k_sl, horizon):
    """1 = TP primero, 0 = SL primero, None = timeout (NO es victoria)."""
    a = atr14(bars, i)
    if a is None or a <= 0:
        return None, None, None, False, None
    entry = bars[i][1][3]
    tp = entry + k_tp * a * direction
    sl = entry - k_sl * a * direction
    mfe = 0.0
    mae = 0.0
    end = min(i + horizon, len(bars) - 1)
    for j in range(i + 1, end + 1):
        _o, h, l, _c = bars[j][1]
        mfe = max(mfe, (h - entry) * direction / a, (l - entry) * direction / a)
        mae = min(mae, (h - entry) * direction / a, (l - entry) * direction / a)
        hit_tp = (h >= tp) if direction > 0 else (l <= tp)
        hit_sl = (l <= sl) if direction > 0 else (h >= sl)
        if hit_tp and hit_sl:
            return 0, mfe, mae, True, a
        if hit_tp:
            return 1, mfe, mae, False, a
        if hit_sl:
            return 0, mfe, mae, False, a
    return None, mfe, mae, False, a


def containment(bars, i, k, horizon, center=None):
    """PIN: 1 si el precio NO sale de center +- k*ATR14 en el horizonte."""
    a = atr14(bars, i)
    if a is None or a <= 0:
        return None
    c0 = bars[i][1][3] if center is None else center
    end = min(i + horizon, len(bars) - 1)
    for j in range(i + 1, end + 1):
        _o, h, l, _c = bars[j][1]
        if h > c0 + k * a or l < c0 - k * a:
            return 0
    return 1


def entry_index(bars, ts, open_ep):
    """Primera barra RTH que CIERRA en o despues del segundo de la alerta.
    Cero look-ahead: se entra al cierre de la barra que contiene la alerta."""
    for i, (ep, _v) in enumerate(bars):
        if ep < open_ep:
            continue
        if ep + 60 >= ts:
            return i
    return None


# ----------------------------------------------------------------- estadistica

def wilson(k, n, z=1.96):
    if n is None or n <= 0:
        return None, None, None
    p = float(k) / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n))
    lo = min(1.0, max(0.0, (c - r) / d))
    hi = min(1.0, max(0.0, (c + r) / d))
    return p, lo, hi


def _corr(x, y):
    n = len(x)
    if n < 30:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx <= 0 or sy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def mean_pairwise_corr(admitted, dates, fleet, agg=5):
    """rho_bar MEDIDO sobre retornos de `agg` minutos de los sym-dias admitidos.
    A 1m las barras MIDPOINT de IBKR estan dominadas por microestructura y rho sale
    artificialmente baja -> se mide tambien a 5m y se usa la MAYOR (conservador:
    sobre-corregir n_eff es el error seguro)."""
    per_day = {}
    for date in dates:
        _warm, op, cl = day_bounds(date)
        for sym in fleet:
            b = admitted.get((date, sym))
            if not b:
                continue
            eps = sorted(ep for ep in b if op <= ep < cl)
            closes = [(ep, b[ep][3]) for ep in eps]
            sampled = closes[::agg]
            rets = {}
            for i in range(1, len(sampled)):
                p0 = sampled[i - 1][1]
                if p0 > 0:
                    rets[sampled[i][0]] = sampled[i][1] / p0 - 1.0
            if len(rets) >= 30:
                per_day.setdefault(date, {})[sym] = rets
    vals = []
    for date, per in per_day.items():
        syms = sorted(per)
        for i in range(len(syms)):
            for j in range(i + 1, len(syms)):
                a = per[syms[i]]
                b = per[syms[j]]
                common = sorted(set(a) & set(b))
                if len(common) < 30:
                    continue
                c = _corr([a[e] for e in common], [b[e] for e in common])
                if c is not None:
                    vals.append(c)
    return (sum(vals) / len(vals)) if vals else None


def n_effective(rows, rho):
    """n_eff = n/(1+(k-1)*rho) topado por el nº de clusters (fecha, ventana 5 min)."""
    n = len(rows)
    if n == 0:
        return 0.0, 0
    clusters = set((r["date"], r["ts"] // 300) for r in rows)
    nc = len(clusters)
    if rho is None:
        return float(nc), nc          # sin rho medido se topa a clusters (conservador)
    k = float(n) / nc
    neff = n / (1.0 + (k - 1.0) * rho)
    return min(neff, float(nc)), nc


def bh_fdr(pvals, q=FDR_Q):
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    kmax = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    passed = [False] * m
    for rank, i in enumerate(order, 1):
        if rank <= kmax:
            passed[i] = True
    return passed


def norm_sf(x):
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def boot_diff(labels, p_null, rng, n_boot=BOOT_N):
    """Bootstrap estacionario por bloques sobre la DIFERENCIA p_signal - p_null."""
    vals = [v for v in labels if v is not None]
    n = len(vals)
    if n < 8 or p_null is None:
        return None, None
    block = max(1, min(30, n // 5))
    diffs = []
    for _ in range(n_boot):
        s = []
        while len(s) < n:
            start = rng.randrange(n)
            ln = min(block, n - len(s))
            for j in range(ln):
                s.append(vals[(start + j) % n])
        diffs.append(float(sum(s)) / len(s) - p_null)
    diffs.sort()
    return diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot)]


# ----------------------------------------------------------------- motor

def build_index(admitted, dates):
    idx = {}
    opens = {}
    for date in dates:
        _w, op, _cl = day_bounds(date)
        opens[date] = op
    for key, b in admitted.items():
        idx[key] = sorted(b.items())
    return idx, opens


def label_alerts(alerts, index, opens, k_tp, k_sl, horizon):
    out = []
    skipped_no_atr = 0
    for a in alerts:
        key = (a["date"], a["sym"])
        bars = index.get(key)
        if bars is None:
            continue
        i = entry_index(bars, a["ts"], opens[a["date"]])
        if i is None or i >= len(bars) - 2:
            continue
        rec = dict(a)
        rec["entry_px"] = bars[i][1][3]
        rec["entry_ep"] = bars[i][0]
        if a["type"] == "ESTRUCTURAL_PIN":
            # centro = ENTRADA (no el iman) para que el null aleatorio sea comparable;
            # la distancia entrada-iman se publica aparte en ATR.
            atr = atr14(bars, i)
            if atr is None:
                skipped_no_atr += 1
                continue
            rec["label"] = containment(bars, i, k_tp, horizon)
            rec["mfe"] = None
            rec["mae"] = None
            rec["ambig"] = False
            rec["atr"] = atr
            if a.get("magnet"):
                rec["magnet_dist_atr"] = abs(rec["entry_px"] - a["magnet"]) / atr
        else:
            if a["dir"] == 0:
                continue
            lab, mfe, mae, amb, atr = triple_barrier(bars, i, a["dir"], k_tp, k_sl, horizon)
            rec["label"] = lab
            rec["mfe"] = mfe
            rec["mae"] = mae
            rec["ambig"] = amb
            rec["atr"] = atr
            if atr is None:
                skipped_no_atr += 1
                continue
        out.append(rec)
    return out, skipped_no_atr


def _null_pool(index, opens):
    pool = {}
    for (date, sym), bars in index.items():
        op = opens[date]
        for i, (ep, _v) in enumerate(bars):
            if ep < op or i < 15 or i >= len(bars) - 2:
                continue
            hh = dt.datetime.fromtimestamp(ep).hour
            pool.setdefault((sym, hh), []).append(((date, sym), i))
    return pool


def null_for(alerts, index, pool, k_tp, k_sl, horizon, rng, draws=NULL_DRAWS):
    wins = 0
    tot = 0
    for a in alerts:
        hh = dt.datetime.fromtimestamp(a["ts"]).hour
        cand = pool.get((a["sym"], hh))
        if not cand:
            continue
        d = a["dir"]
        for _ in range(draws):
            key, i = cand[rng.randrange(len(cand))]
            bars = index[key]
            if a["type"] == "ESTRUCTURAL_PIN":
                lab = containment(bars, i, k_tp, horizon)
            else:
                lab = triple_barrier(bars, i, d, k_tp, k_sl, horizon)[0]
            if lab is None:
                continue
            tot += 1
            wins += lab
    return ((float(wins) / tot) if tot else None), tot


def verdict(n_eff, hit, lo_eff, p_null, fdr_ok, edge_lo):
    if n_eff < MIN_NEFF:
        return "DATA-INSUFICIENTE"
    if p_null is None or edge_lo is None or hit is None or lo_eff is None:
        return "DATA-INSUFICIENTE"
    if edge_lo > 0 and fdr_ok and lo_eff > KEEP_FLOOR:
        return "KEEP"
    return "KILL"


def evaluate(sub, index, opens, pool, rho, rng, k_tp, k_sl, horizons=None):
    rows = []
    for H in (horizons or HORIZONS):
        lab, no_atr = label_alerts(sub, index, opens, k_tp, k_sl, H)
        res = [x for x in lab if x["label"] is not None]
        n = len(res)
        wins = sum(x["label"] for x in res)
        hit, lo, hi = wilson(wins, n)
        neff, nc = n_effective(res, rho)
        if neff >= 1 and hit is not None:
            _p, lo_e, hi_e = wilson(int(round(hit * neff)), neff)
        else:
            lo_e = hi_e = None
        p_null, n_null = null_for(sub, index, pool, k_tp, k_sl, H, rng)
        elo, ehi = boot_diff([x["label"] for x in res], p_null, rng)
        pval = None
        if hit is not None and p_null is not None and neff >= 1:
            se = math.sqrt(max(p_null * (1 - p_null) / neff, 1e-12))
            pval = norm_sf((hit - p_null) / se)
        mfes = [x["mfe"] for x in res if x["mfe"] is not None]
        maes = [x["mae"] for x in res if x["mae"] is not None]
        mdist = [x["magnet_dist_atr"] for x in res if x.get("magnet_dist_atr") is not None]
        rows.append({
            "H": H, "n_signals": len(sub), "n_labeled": len(lab), "n_resolved": n,
            "timeout": len(lab) - n, "no_atr": no_atr,
            "n_eff": round(neff, 1), "clusters": nc,
            "hit": hit, "wilson_raw": [lo, hi], "wilson_eff": [lo_e, hi_e],
            "null": p_null, "n_null": n_null,
            "edge": (hit - p_null) if (hit is not None and p_null is not None) else None,
            "edge_ci": [elo, ehi], "pval": pval,
            "ambig": sum(1 for x in res if x["ambig"]),
            "mfe_p60": _pct(mfes, 0.60), "mae_p20": _pct(maes, 0.20),
            "magnet_dist_atr_med": _pct(mdist, 0.50),
        })
    return rows


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(q * len(s)))], 3)


def price_drift(alerts, index, opens):
    """Divergencia entre el precio que la alerta CANTO y la barra archivada de ese
    minuto. Mide el retraso del feed: si el precio cantado coincide mejor con una
    barra de hace N minutos, el feed iba N minutos tarde."""
    out = {"n": 0, "abs_bp": [], "best_lag_min": {}}
    for a in alerts:
        if a["msg_price"] is None:
            continue
        bars = index.get((a["date"], a["sym"]))
        if not bars:
            continue
        i = entry_index(bars, a["ts"], opens[a["date"]])
        if i is None or i < 20:
            continue
        px = a["msg_price"]
        ref = bars[i][1][3]
        if ref <= 0 or abs(px / ref - 1.0) > 0.05:
            continue                      # precio del mensaje que no es de este simbolo
        out["n"] += 1
        out["abs_bp"].append(abs(px / ref - 1.0) * 1e4)
        best = None
        for lag in range(0, 21):
            j = i - lag
            if j < 0:
                break
            lo = bars[j][1][2]
            hi = bars[j][1][1]
            dist = 0.0 if lo <= px <= hi else min(abs(px - lo), abs(px - hi))
            if best is None or dist < best[1]:
                best = (lag, dist)
        out["best_lag_min"][best[0]] = out["best_lag_min"].get(best[0], 0) + 1
    if out["abs_bp"]:
        s = sorted(out["abs_bp"])
        out["median_abs_bp"] = round(s[len(s) // 2], 2)
    else:
        out["median_abs_bp"] = None
    del out["abs_bp"]
    return out


def load_regimes(dates):
    """regime gamma por (fecha, sym) desde data/history/<fecha>/gex_snapshot.json."""
    reg = {}
    for date in dates:
        p = os.path.join(HISTDIR, date, "gex_snapshot.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as fh:
                blob = json.load(fh)
        except ValueError:
            continue
        if not isinstance(blob, dict):
            continue
        for sym, v in blob.items():
            if isinstance(v, dict) and v.get("regime"):
                reg[(date, sym.upper())] = v["regime"]
    return reg


def confluence(alerts, window=180):
    """Alertas del mismo sym con >=2 TIPOS distintos dentro de `window` segundos."""
    by = {}
    for a in alerts:
        by.setdefault((a["date"], a["sym"]), []).append(a)
    solo, conf = [], []
    for _k, rows in by.items():
        rows.sort(key=lambda r: r["ts"])
        for i, a in enumerate(rows):
            types = set()
            for b in rows:
                if abs(b["ts"] - a["ts"]) <= window:
                    types.add(b["type"])
            (conf if len(types) >= 2 else solo).append(a)
    return solo, conf


def run(dates, fleet, seed=7, k_tp=K_DEFAULT, k_sl=K_DEFAULT, cuts=False, sweep=False):
    fleet_set = set(fleet)
    admitted, excluded = audit_bars(dates, fleet)
    index, opens = build_index(admitted, dates)
    rho1 = mean_pairwise_corr(admitted, dates, fleet, agg=1)
    rho5 = mean_pairwise_corr(admitted, dates, fleet, agg=5)
    rho = max([r for r in (rho1, rho5) if r is not None] or [None])
    pool = _null_pool(index, opens)

    alerts = []
    for d in dates:
        alerts.extend(parse_day(d, fleet_set))
    usable = [a for a in alerts if (a["date"], a["sym"]) in index]
    dropped = [a for a in alerts if (a["date"], a["sym"]) not in index]

    rng = random.Random(seed)
    results = []
    for typ in sorted(set(a["type"] for a in usable)):
        sub = [a for a in usable if a["type"] == typ]
        for row in evaluate(sub, index, opens, pool, rho, rng, k_tp, k_sl):
            row["type"] = typ
            results.append(row)

    pv = [r["pval"] if r["pval"] is not None else 1.0 for r in results]
    for r, ok in zip(results, bh_fdr(pv)):
        r["fdr_ok"] = bool(ok) and r["pval"] is not None
        r["verdict"] = verdict(r["n_eff"], r["hit"], r["wilson_eff"][0], r["null"],
                               r["fdr_ok"], r["edge_ci"][0])

    out = {
        "dates": dates, "rho_1m": rho1, "rho_5m": rho5, "rho_used": rho,
        "k_tp": k_tp, "k_sl": k_sl,
        "min_rth": MIN_RTH, "min_neff": MIN_NEFF, "keep_floor": KEEP_FLOOR,
        "excluded_sym_days": excluded,
        "n_alerts": len(alerts), "n_usable": len(usable),
        "n_dropped_no_bars": len(dropped),
        "dropped_by_sym": _count(dropped, "sym"),
        "by_type": _count(usable, "type"),
        "price_drift": price_drift(usable, index, opens),
        "results": results,
    }

    if cuts:
        out["cuts"] = build_cuts(usable, index, opens, pool, rho, rng, k_tp, k_sl, dates)
    if sweep:
        out["sweep"] = build_sweep(usable, index, opens, pool, rho, seed)
    return out


def build_cuts(usable, index, opens, pool, rho, rng, k_tp, k_sl, dates):
    cuts = {}
    H = 30
    # por HORA
    hour = {}
    for a in usable:
        hh = dt.datetime.fromtimestamp(a["ts"]).hour
        hour.setdefault(hh, []).append(a)
    cuts["hour"] = {}
    for hh, sub in sorted(hour.items()):
        sub = [a for a in sub if a["type"] != "ESTRUCTURAL_PIN"]
        if not sub:
            continue
        cuts["hour"][str(hh)] = evaluate(sub, index, opens, pool, rho, rng, k_tp, k_sl, [H])[0]
    # por SIMBOLO
    sym = {}
    for a in usable:
        if a["type"] != "ESTRUCTURAL_PIN":
            sym.setdefault(a["sym"], []).append(a)
    cuts["symbol"] = {}
    for s, sub in sorted(sym.items()):
        cuts["symbol"][s] = evaluate(sub, index, opens, pool, rho, rng, k_tp, k_sl, [H])[0]
    # por REGIMEN gamma
    reg = load_regimes(dates)
    byreg = {}
    for a in usable:
        if a["type"] == "ESTRUCTURAL_PIN":
            continue
        r = reg.get((a["date"], a["sym"]))
        if r:
            byreg.setdefault(r, []).append(a)
    cuts["regime"] = {}
    for r, sub in sorted(byreg.items()):
        cuts["regime"][r] = evaluate(sub, index, opens, pool, rho, rng, k_tp, k_sl, [H])[0]
    cuts["regime_coverage"] = {"with_regime": sum(len(v) for v in byreg.values()),
                               "total": len([a for a in usable if a["type"] != "ESTRUCTURAL_PIN"])}
    # CONFLUENCIA
    solo, conf = confluence([a for a in usable if a["type"] != "ESTRUCTURAL_PIN"])
    cuts["confluence"] = {
        "solo": evaluate(solo, index, opens, pool, rho, rng, k_tp, k_sl, [H])[0],
        "confluent": evaluate(conf, index, opens, pool, rho, rng, k_tp, k_sl, [H])[0],
    }
    # BB con y sin MUTED (¿el mute esta calibrado?)
    fam = {
        "BB_REBOTE_all": ["BB_REBOTE", "BB_REBOTE_VETO", "BB_REBOTE_STAR"],
        "BB15_all": ["BB15_REENTRADA", "BB15_REENTRADA_MUTED"],
        "BANDWALK_all": ["BB_BANDWALK", "BB_BANDWALK_MUTED"],
        "FLUJO_all": ["BALLENA_CALLS", "BALLENA_PUTS", "BALLENA_CRECE",
                      "SPIKE_CALLS", "SPIKE_PUTS", "MANADA_CALLS", "MANADA_PUTS"],
    }
    cuts["family"] = {}
    for name, types in fam.items():
        sub = [a for a in usable if a["type"] in types]
        if sub:
            cuts["family"][name] = evaluate(sub, index, opens, pool, rho, rng, k_tp, k_sl, [H])[0]
    return cuts


def build_sweep(usable, index, opens, pool, rho, seed):
    """Curva de sensibilidad: si el efecto vive en un solo k, no es real."""
    out = {}
    for typ in sorted(set(a["type"] for a in usable)):
        sub = [a for a in usable if a["type"] == typ]
        row = {}
        for k in K_GRID:
            rng = random.Random(seed)
            r = evaluate(sub, index, opens, pool, rho, rng, k, k, [30])[0]
            row["k=%s" % k] = {"n": r["n_resolved"], "hit": r["hit"],
                               "null": r["null"], "edge": r["edge"]}
        out[typ] = row
    return out


def _count(rows, field):
    out = {}
    for r in rows:
        out[r[field]] = out.get(r[field], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def atomic_write(path, text):
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def expand_days(spec):
    if ".." in spec:
        a, b = spec.split("..")
        out = []
        for p in sorted(glob.glob(os.path.join(SIGDIR, "*.txt"))):
            d = os.path.basename(p)[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", d) and a <= d <= b:
                out.append(d)
        return out
    return [x for x in spec.split(",") if x]


def fmt(v, w=6, nd=3):
    if v is None:
        return " " * (w - 3) + "n/a"
    return ("%%%d.%df" % (w, nd)) % v


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="2026-07-21..2026-08-03")
    ap.add_argument("--day")
    ap.add_argument("--json")
    ap.add_argument("--k", type=float, default=K_DEFAULT)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--cuts", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args(argv)
    dates = [a.day] if a.day else expand_days(a.days)
    with open(os.path.join(REPO, "data", "fleet.txt")) as fh:
        fleet = fh.read().split()
    out = run(dates, fleet, seed=a.seed, k_tp=a.k, k_sl=a.k, cuts=a.cuts, sweep=a.sweep)
    if a.json:
        atomic_write(a.json, json.dumps(out, indent=1, default=str))
    print("dias=%d  rho_1m=%s rho_5m=%s (usada %s)" %
          (len(dates), fmt(out["rho_1m"]), fmt(out["rho_5m"]), fmt(out["rho_used"])))
    print("alertas=%d usables=%d sin_barras=%d  sym-dias EXCLUIDOS=%d" %
          (out["n_alerts"], out["n_usable"], out["n_dropped_no_bars"],
           len(out["excluded_sym_days"])))
    pd = out["price_drift"]
    print("precio cantado vs barra archivada: n=%s mediana=%s bp  lag modal=%s min" %
          (pd["n"], pd["median_abs_bp"],
           max(pd["best_lag_min"].items(), key=lambda kv: kv[1])[0] if pd["best_lag_min"] else "n/a"))
    print("%-22s %4s %5s %5s %6s %6s %6s %14s %6s %7s %16s %3s %s" %
          ("tipo", "H", "n", "t/o", "noATR", "neff", "hit", "CI(n_eff)", "null", "edge",
           "edge CI95", "FDR", "veredicto"))
    for r in out["results"]:
        ci = r["wilson_eff"]
        ec = r["edge_ci"]
        print("%-22s %4d %5d %5d %6d %6.1f %s [%s,%s] %s %s [%s,%s] %3s %s" %
              (r["type"], r["H"], r["n_resolved"], r["timeout"], r["no_atr"], r["n_eff"],
               fmt(r["hit"]), fmt(ci[0], 5), fmt(ci[1], 5), fmt(r["null"]),
               fmt(r["edge"], 7), fmt(ec[0], 6), fmt(ec[1], 6),
               "Y" if r["fdr_ok"] else "n", r["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
