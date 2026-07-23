#!/usr/bin/env python3
"""bollinger_complements.py — MISION B6: complementos de Bollinger, ticker por
ticker, con evidencia (2026-07-22).

Replica EXACTA de la deteccion elastic-1m de scripts/bollinger_alarm.py:
  - BB(20,2) 1m, std POBLACIONAL (/N), banda calculada sobre los 20 cierres
    ANTERIORES a la vela actual (bars[-21:-1] en el alarm).
  - PIERCE: high>banda_sup o low<banda_inf. Si el cierre queda FUERA -> arma.
  - RE-ENTRADA: vela posterior (<=10 min) que sigue perforando pero CIERRA
    dentro -> FIRE. Cooldown 30 min por simbolo+lado.
  - Si el cierre 5m actual tambien esta fuera de su BB(20,2) 5m -> BAND-WALK
    (el alarm NO canta elastico; aqui se tabula aparte y queda FUERA de la base).
  - RTH only; señales 9:50-15:30 ET (>=20 barras de la sesion para que la BB
    sea 100% intradia; <=15:30 para tener 30 min de outcome).

Outcomes (ventana 30 barras 1m, misma sesion):
  - hit_mid30: toca la MEDIA BB20-1m congelada al fire (dn: high>=mid; up: low<=mid).
  - hit_half30: avanza >=50% del gap |mid-close_fire|.
  - mfe/mae 15 y 30 min en % del cierre de entrada (a favor de la reversion).

Filtros F1-F8 (grid completo, sin cherry-picking) + combos de a 2.
Resultados incrementales: data/backtest/bcomp_results.json (no se pierde nada
si muere a mitad). Analisis: --analyze -> data/bollinger_plus.json + grid md.

SEÑAL-SOLAMENTE. Aditivo. Sin daemons.
"""
import csv, json, math, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data", "backtest")
RESULTS = os.path.join(DATA, "bcomp_results.json")
ET = ZoneInfo("America/New_York")
COOLDOWN_S = 1800
ARM_EXPIRE_S = 600
OUT_BARS = 30


# ---------------------------------------------------------------- utilidades
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - hw), min(1.0, c + hw))


def bb_pop(closes, k=2.0):
    m = sum(closes) / len(closes)
    sd = math.sqrt(sum((c - m) ** 2 for c in closes) / len(closes))
    return m - k * sd, m, m + k * sd


def load_bars(sym):
    """[(epoch, o,h,l,c,v, date_str, et_min)] solo RTH 9:30-16:00, ordenado."""
    path = os.path.join(DATA, f"bars30d_{sym}.csv")
    out = []
    with open(path) as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if len(row) < 6:
                continue
            t = int(float(row[0]))
            dt = datetime.fromtimestamp(t, ET)
            mins = dt.hour * 60 + dt.minute
            if not (570 <= mins < 960):        # 9:30 <= t < 16:00
                continue
            out.append((t, float(row[1]), float(row[2]), float(row[3]),
                        float(row[4]), float(row[5]), dt.strftime("%Y-%m-%d"), mins))
    out.sort(key=lambda x: x[0])
    return out


class Wilder:
    """RSI(n) de Wilder incremental."""
    def __init__(self, n):
        self.n = n; self.prev = None; self.ag = None; self.al = None; self.seed = []

    def update(self, c):
        if self.prev is None:
            self.prev = c; return None
        ch = c - self.prev; self.prev = c
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if self.ag is None:
            self.seed.append((g, l))
            if len(self.seed) < self.n:
                return None
            self.ag = sum(x for x, _ in self.seed) / self.n
            self.al = sum(y for _, y in self.seed) / self.n
        else:
            self.ag = (self.ag * (self.n - 1) + g) / self.n
            self.al = (self.al * (self.n - 1) + l) / self.n
        if self.ag + self.al == 0:
            return 50.0
        if self.al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + self.ag / self.al)


class ADX:
    """ADX(14) de Wilder, alimentado con barras COMPLETAS (5m)."""
    def __init__(self, n=14):
        self.n = n; self.prev = None
        self.atr = None; self.pdm = None; self.ndm = None
        self.seed = []; self.dx_seed = []; self.adx = None

    def update(self, h, l, c):
        if self.prev is None:
            self.prev = (h, l, c); return self.adx
        ph, pl, pc = self.prev; self.prev = (h, l, c)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        pdm = up if (up > dn and up > 0) else 0.0
        ndm = dn if (dn > up and dn > 0) else 0.0
        if self.atr is None:
            self.seed.append((tr, pdm, ndm))
            if len(self.seed) < self.n:
                return self.adx
            self.atr = sum(x[0] for x in self.seed)
            self.pdm = sum(x[1] for x in self.seed)
            self.ndm = sum(x[2] for x in self.seed)
        else:
            self.atr = self.atr - self.atr / self.n + tr
            self.pdm = self.pdm - self.pdm / self.n + pdm
            self.ndm = self.ndm - self.ndm / self.n + ndm
        if self.atr == 0:
            return self.adx
        pdi = 100.0 * self.pdm / self.atr
        ndi = 100.0 * self.ndm / self.atr
        s = pdi + ndi
        dx = 100.0 * abs(pdi - ndi) / s if s > 0 else 0.0
        if self.adx is None:
            self.dx_seed.append(dx)
            if len(self.dx_seed) >= self.n:
                self.adx = sum(self.dx_seed) / self.n
        else:
            self.adx = (self.adx * (self.n - 1) + dx) / self.n
        return self.adx


# ---------------------------------------------------------------- deteccion
def run_ticker(sym):
    bars = load_bars(sym)
    if len(bars) < 200:
        return {"error": f"solo {len(bars)} barras", "signals": [], "n_bars": len(bars)}
    signals, walks = [], 0

    rsi2 = Wilder(2)
    adx5 = ADX(14)
    bw_hist = []                       # bandwidth 1m
    b5, b15 = [], []                   # buckets [key,o,h,l,c] cross-sesion RTH
    cur_date = None
    sess_start_i = 0
    vwap_pv = vwap_v = 0.0
    dev_s = dev_s2 = dev_n = 0
    armed = {"up": None, "dn": None}   # (idx, epoch, max_depth)
    last_fire = {"up": 0.0, "dn": 0.0}
    dates = sorted({b[6] for b in bars})

    for i, (t, o, h, l, c, v, d, mins) in enumerate(bars):
        if d != cur_date:
            cur_date = d
            sess_start_i = i
            vwap_pv = vwap_v = 0.0
            dev_s = dev_s2 = dev_n = 0
            armed = {"up": None, "dn": None}   # sin arrastre nocturno
        sess_idx = i - sess_start_i

        # --- buckets 5m / 15m (incluyen la barra actual; el anterior completa)
        for blist, secs, adx in ((b5, 300, adx5), (b15, 900, None)):
            k = t - t % secs
            if not blist or blist[-1][0] != k:
                if blist and secs == 300:
                    _, po, ph, pl, pc = blist[-1]
                    adx5.update(ph, pl, pc)    # bucket 5m completado
                blist.append([k, o, h, l, c])
            else:
                bk = blist[-1]
                bk[2] = max(bk[2], h); bk[3] = min(bk[3], l); bk[4] = c

        # --- rsi2 / vwap (antes de decidir: todo al cierre de la barra i)
        r2 = rsi2.update(c)
        tp = (h + l + c) / 3.0
        vwap_pv += tp * v; vwap_v += v
        vwap = vwap_pv / vwap_v if vwap_v > 0 else c
        dev = c - vwap
        dev_s += dev; dev_s2 += dev * dev; dev_n += 1
        zv = None
        if dev_n >= 20:
            mu = dev_s / dev_n
            var = dev_s2 / dev_n - mu * mu
            sd = math.sqrt(var) if var > 1e-12 else 0.0
            zv = (dev - mu) / sd if sd > 0 else 0.0

        if sess_idx < 20:
            continue
        closes20 = [b[4] for b in bars[i - 20:i]]
        lo, mid, up = bb_pop(closes20)
        width = up - lo
        bw = width / mid if mid else 0.0
        bw_hist.append(bw)
        bw_pct = None
        if len(bw_hist) >= 100:
            window = bw_hist[-125:]
            bw_pct = 100.0 * sum(1 for x in window if x <= bw) / len(window)

        vol20 = [b[5] for b in bars[i - 20:i]]
        vsma = sum(vol20) / 20.0
        rvol = v / vsma if vsma > 0 else None

        # walk 5m/15m (BB sobre los 20 buckets ANTERIORES al actual)
        def tf_state(blist):
            if len(blist) < 21:
                return None, None
            cl = [b[4] for b in blist[-21:-1]]
            tlo, tmid, tup = bb_pop(cl)
            cc = blist[-1][4]
            return ("up" if cc > tup else "dn" if cc < tlo else "in"), (tlo, tmid, tup)
        w5, _ = tf_state(b5)
        w15, _ = tf_state(b15)

        # --- deteccion por lado (estructura del alarm)
        for side in ("up", "dn"):
            pierced = h > up if side == "up" else l < lo
            depth = ((h - up) if side == "up" else (lo - l)) / width if width > 0 else 0.0
            if pierced:
                back = c < up if side == "up" else c > lo
                if not back:
                    prev = armed[side]
                    armed[side] = (i, t, max(depth, prev[2] if prev else 0.0))
                elif armed[side] and t - last_fire[side] > COOLDOWN_S:
                    ai, at, adep = armed[side]
                    armed[side] = None
                    if t - at > ARM_EXPIRE_S:
                        continue
                    last_fire[side] = t
                    walk = (w5 == side)
                    if walk:
                        walks += 1
                        continue                    # el alarm canta BAND-WALK, no elastico
                    if mins > 930:                  # <=15:30 para outcome completo
                        continue
                    # outcomes: 30 barras, misma sesion
                    fut = [b for b in bars[i + 1:i + 1 + OUT_BARS] if b[6] == d]
                    if len(fut) < OUT_BARS:
                        continue
                    gap = abs(mid - c)
                    if side == "dn":                # fade LONG hacia la media
                        hit_mid = any(fb[2] >= mid for fb in fut)
                        hit_half = any(fb[2] >= c + 0.5 * gap for fb in fut)
                        mfe15 = (max(fb[2] for fb in fut[:15]) - c) / c * 100
                        mae15 = (c - min(fb[3] for fb in fut[:15])) / c * 100
                        mfe30 = (max(fb[2] for fb in fut) - c) / c * 100
                        mae30 = (c - min(fb[3] for fb in fut)) / c * 100
                    else:                           # fade SHORT hacia la media
                        hit_mid = any(fb[3] <= mid for fb in fut)
                        hit_half = any(fb[3] <= c - 0.5 * gap for fb in fut)
                        mfe15 = (c - min(fb[3] for fb in fut[:15])) / c * 100
                        mae15 = (max(fb[2] for fb in fut[:15]) - c) / c * 100
                        mfe30 = (c - min(fb[3] for fb in fut)) / c * 100
                        mae30 = (max(fb[2] for fb in fut) - c) / c * 100
                    hb = ("0945_1030" if 585 <= mins < 630 else
                          "1030_1130" if 630 <= mins < 690 else
                          "1130_1400" if 690 <= mins < 840 else
                          "1400_1530" if 840 <= mins <= 930 else "otras")
                    signals.append({
                        "date": d, "et": f"{mins // 60:02d}:{mins % 60:02d}",
                        "side": side, "close": round(c, 4), "mid": round(mid, 4),
                        "gap_pct": round(gap / c * 100, 3),
                        "rvol": round(rvol, 2) if rvol is not None else None,
                        "rsi2": round(r2, 1) if r2 is not None else None,
                        "depth": round(max(adep, depth), 3),
                        "zvwap": round(zv, 2) if zv is not None else None,
                        "bw_pct": round(bw_pct, 1) if bw_pct is not None else None,
                        "hour": hb,
                        "f7_in15": (w15 == "in") if w15 is not None else None,
                        "adx5": round(adx5.adx, 1) if adx5.adx is not None else None,
                        "hit_mid30": hit_mid, "hit_half30": hit_half,
                        "mfe15": round(mfe15, 3), "mae15": round(mae15, 3),
                        "mfe30": round(mfe30, 3), "mae30": round(mae30, 3),
                    })
            elif armed[side] and (t - armed[side][1]) > ARM_EXPIRE_S:
                armed[side] = None

    return {"n_bars": len(bars), "n_days": len(dates), "band_walks_5m": walks,
            "signals": signals}


# ---------------------------------------------------------------- filtros
def fdefs():
    """nombre -> (descripcion, predicado(sig)->bool|None)."""
    def side_rsi(s):
        if s["rsi2"] is None:
            return None
        return s["rsi2"] < 10 if s["side"] == "dn" else s["rsi2"] > 90

    def side_z(s):
        if s["zvwap"] is None:
            return None
        return s["zvwap"] <= -1.5 if s["side"] == "dn" else s["zvwap"] >= 1.5

    F = {
        "F1_rvol15":   ("RVOL vela fire >= 1.5", lambda s: None if s["rvol"] is None else s["rvol"] >= 1.5),
        "F2_rsi2_ext": ("RSI(2) extremo (dn<10 / up>90)", side_rsi),
        "F3a_depth05": ("pierce depth > 0.05 del ancho", lambda s: s["depth"] > 0.05),
        "F3b_depth15": ("pierce depth > 0.15 del ancho", lambda s: s["depth"] > 0.15),
        "F4_zvwap15":  ("z-VWAP >= |1.5| contra el lado", side_z),
        "F5_squeeze":  ("bandwidth 1m pctile <= 20 (post-squeeze)", lambda s: None if s["bw_pct"] is None else s["bw_pct"] <= 20),
        "F6_0945":     ("hora 9:50-10:30", lambda s: s["hour"] == "0945_1030"),
        "F6_1030":     ("hora 10:30-11:30", lambda s: s["hour"] == "1030_1130"),
        "F6_1130":     ("picadora 11:30-14:00", lambda s: s["hour"] == "1130_1400"),
        "F6_1400":     ("hora 14:00-15:30", lambda s: s["hour"] == "1400_1530"),
        "F7_15m_in":   ("cierre 15m DENTRO de su banda", lambda s: s["f7_in15"]),
        "F8a_adx_lt20": ("ADX(14) 5m < 20 (rango)", lambda s: None if s["adx5"] is None else s["adx5"] < 20),
        "F8b_adx_ge25": ("ADX(14) 5m >= 25 (tendencia)", lambda s: None if s["adx5"] is None else s["adx5"] >= 25),
    }
    return F


def cell(sigs, key="hit_mid30"):
    n = len(sigs)
    k = sum(1 for s in sigs if s[key])
    p, lo, hi = wilson(k, n)
    return {"n": n, "k": k, "p": round(p * 100, 1),
            "wilson_lo": round(lo * 100, 1), "wilson_hi": round(hi * 100, 1)}


def avg(sigs, key):
    xs = [s[key] for s in sigs if s.get(key) is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def analyze(results):
    F = fdefs()
    grid = {}          # ticker -> {base:..., filters:{fname:cell}}
    pooled = []
    for sym, res in sorted(results.items()):
        sigs = res.get("signals", [])
        pooled.extend(sigs)
        base = cell(sigs)
        base.update({"p_half": cell(sigs, "hit_half30")["p"],
                     "mfe15": avg(sigs, "mfe15"), "mae15": avg(sigs, "mae15"),
                     "mfe30": avg(sigs, "mfe30"), "mae30": avg(sigs, "mae30"),
                     "n_days": res.get("n_days"), "band_walks_5m": res.get("band_walks_5m")})
        filts = {}
        for fname, (desc, pred) in F.items():
            sub = [s for s in sigs if pred(s) is True]
            cc = cell(sub)
            cc["uplift"] = round(cc["p"] - base["p"], 1) if cc["n"] else None
            cc["p_half"] = cell(sub, "hit_half30")["p"] if cc["n"] else None
            filts[fname] = cc
        grid[sym] = {"base": base, "filters": filts,
                     "by_side": {sd: cell([s for s in sigs if s["side"] == sd])
                                 for sd in ("up", "dn")}}

    fleet_base = cell(pooled)
    fleet = {"base": fleet_base, "filters": {}, "by_side": {
        sd: cell([s for s in pooled if s["side"] == sd]) for sd in ("up", "dn")}}
    for fname, (desc, pred) in F.items():
        sub = [s for s in pooled if pred(s) is True]
        cc = cell(sub)
        cc["uplift"] = round(cc["p"] - fleet_base["p"], 1) if cc["n"] else None
        cc["desc"] = desc
        fleet["filters"][fname] = cc

    # combos: filtros con uplift flota >= 5 y n>=15, pares, max 6
    elig = [f for f, c in fleet["filters"].items()
            if c["n"] >= 15 and c["uplift"] is not None and c["uplift"] >= 5.0]
    elig.sort(key=lambda f: -fleet["filters"][f]["uplift"])
    combos = {}
    import itertools
    for a, b in itertools.combinations(elig, 2):
        if len(combos) >= 6:
            break
        pa, pb = F[a][1], F[b][1]
        sub = [s for s in pooled if pa(s) is True and pb(s) is True]
        cc = cell(sub)
        cc["uplift"] = round(cc["p"] - fleet_base["p"], 1) if cc["n"] else None
        combos[f"{a}+{b}"] = cc
    fleet["combos"] = combos
    return grid, fleet, pooled


def write_outputs(grid, fleet):
    plus = {}
    for sym, g in grid.items():
        base = g["base"]
        best, veto = [], []
        for fname, c in g["filters"].items():
            if c["n"] >= 15 and c["uplift"] is not None and abs(c["uplift"]) >= 5.0:
                item = {"filtro": fname, "n": c["n"], "p": c["p"], "uplift": c["uplift"],
                        "wilson": [c["wilson_lo"], c["wilson_hi"]]}
                (best if c["uplift"] > 0 else veto).append(item)
        best.sort(key=lambda x: -x["uplift"]); veto.sort(key=lambda x: x["uplift"])
        plus[sym.upper()] = {"base": {"n": base["n"], "p": base["p"],
                                      "wilson": [base["wilson_lo"], base["wilson_hi"]]},
                             "best_filters": best, "veto_filters": veto}
    plus["_meta"] = {"generado": datetime.now(ET).strftime("%Y-%m-%d %H:%M ET"),
                     "outcome": "P(toca media BB20-1m congelada, 30min)",
                     "criterio": "n>=15 y |uplift|>=5pts vs base del ticker",
                     "fleet_base": fleet["base"], "fleet_filters": fleet["filters"],
                     "fleet_combos": fleet["combos"]}
    out = os.path.join(REPO, "data", "bollinger_plus.json")
    json.dump(plus, open(out, "w"), indent=1)
    print(f"escrito {out}")


def emit_grid_md(grid, fleet):
    F = fdefs()
    lines = []
    fn = list(F.keys())
    hdr = "| ticker | base n | base P% | " + " | ".join(f.split('_')[0] + "_" + "_".join(f.split('_')[1:]) for f in fn) + " |"
    lines.append("Celdas: `P% (n) [uplift]` — outcome = toca la media BB20-1m en 30 min.")
    lines.append("")
    lines.append(hdr)
    lines.append("|" + "---|" * (3 + len(fn)))
    for sym, g in sorted(grid.items()):
        b = g["base"]
        row = [sym.upper(), str(b["n"]), f"{b['p']}"]
        for f in fn:
            c = g["filters"][f]
            row.append(f"{c['p']} ({c['n']}) [{c['uplift']:+.0f}]" if c["n"] else "—")
        lines.append("| " + " | ".join(row) + " |")
    fb = fleet["base"]
    row = ["**FLOTA**", str(fb["n"]), f"{fb['p']}"]
    for f in fn:
        c = fleet["filters"][f]
        row.append(f"{c['p']} ({c['n']}) [{c['uplift']:+.1f}]" if c["n"] else "—")
    lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main():
    fleet_syms = [s.lower() for s in
                  open(os.path.join(REPO, "data", "fleet.txt")).read().split()]
    results = {}
    if os.path.exists(RESULTS):
        results = json.load(open(RESULTS))

    if "--analyze" in sys.argv:
        results = {k: v for k, v in results.items() if not v.get("error")}
        grid, fleet, pooled = analyze(results)
        write_outputs(grid, fleet)
        print(emit_grid_md(grid, fleet))
        json.dump({"grid": grid, "fleet": fleet},
                  open(os.path.join(DATA, "bcomp_grid.json"), "w"), indent=1)
        return

    todo = [s for s in fleet_syms if s not in results or "--force" in sys.argv]
    for sym in todo:
        path = os.path.join(DATA, f"bars30d_{sym}.csv")
        if not os.path.exists(path):
            print(f"{sym}: sin datos ({path}) — pendiente")
            continue
        try:
            res = run_ticker(sym)
        except Exception as e:
            res = {"error": str(e), "signals": []}
        results[sym] = res
        json.dump(results, open(RESULTS, "w"))
        ns = len(res.get("signals", []))
        print(f"{sym}: {ns} señales elastic | {res.get('band_walks_5m', '?')} band-walks | "
              f"{res.get('n_days', '?')} dias | {res.get('error', '')}")


if __name__ == "__main__":
    main()
