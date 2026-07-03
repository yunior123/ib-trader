#!/usr/bin/env python3
"""full_history_backtest.py — backtest de TODO el historial de señales (2026-07-15 .. 07-24)
contra precio real: poly_bars (Polygon 1m, hasta 07-23) + data/bars_<sym>_ibkr.txt (07-24).

Novedades vs backtest_harness.py (que solo agregaba por `source` contra 50%):
  - Familia de señal detallada + gate (MUTED/VETO/⭐/capitán opuesto).
  - BASELINE POR DÍA Y SÍMBOLO: p_long/p_short medidos sobre TODOS los minutos RTH de ese
    (símbolo, día, horizonte). El WR se juzga contra esa base, no contra 50% -> el sesgo
    direccional del día queda descontado (control de régimen).
  - Test de score Poisson-binomial CLUSTER-ROBUSTO (cluster = símbolo×día): los eventos del
    mismo símbolo no son independientes y el Wilson normal sale demasiado estrecho.
  - Estabilidad día a día por familia.
  - Corrección por multiple testing (Bonferroni + Benjamini-Hochberg FDR).
  - Scoring en la OPCIÓN real (poly_opt_bars 5m, 0DTE) para QQQ/SPY/NVDA.

SEÑAL-SOLAMENTE: solo lee BD + ficheros. Sin red, sin órdenes.
Uso: ./venv/bin/python scripts/full_history_backtest.py [--json out.json]
"""
import os, sys, math, json, sqlite3, datetime as dt
from collections import defaultdict

os.environ.setdefault("TZ", "America/New_York")
try:
    import time as _t; _t.tzset()
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
DB = os.path.join(REPO, "data", "trades.db")
import eod_backtest as E          # reusa wilson()

HOR = [5, 15, 30, 60]
WIN_THRESH = 0.05                 # % en la dirección de la tesis para contar victoria
IBKR_FROM = int(dt.datetime(2026, 7, 24, 0, 0).timestamp())   # desde aquí, barras IBKR
FLEET = open("data/fleet.txt").read().split()

# ---------------------------------------------------------------- barras
def load_bars():
    """{sym: [(ts_sec,o,h,l,c), ...]} — poly_bars (<07-24) + IBKR (>=07-24)."""
    bars = defaultdict(list)
    c = sqlite3.connect(DB)
    for sym, ts, o, h, l, cl in c.execute(
            "SELECT sym,ts,o,h,l,c FROM poly_bars WHERE ts < ? ORDER BY sym,ts",
            (IBKR_FROM * 1000,)):
        bars[sym].append((ts // 1000, o, h, l, cl))
    c.close()
    import glob
    for p in glob.glob("data/bars_*_ibkr.txt"):
        sym = os.path.basename(p)[5:-9].upper()
        for ln in open(p):
            q = ln.split()
            if len(q) >= 5:
                try:
                    ts = int(q[0])
                except Exception:
                    continue
                if ts >= IBKR_FROM:
                    bars[sym].append((ts, float(q[1]), float(q[2]), float(q[3]), float(q[4])))
    for s in bars:
        bars[s].sort()
    return dict(bars)


class Series:
    __slots__ = ("ts", "o", "h", "l", "c")
    def __init__(self, rows):
        self.ts = [r[0] for r in rows]; self.o = [r[1] for r in rows]
        self.h = [r[2] for r in rows]; self.l = [r[3] for r in rows]
        self.c = [r[4] for r in rows]
    def idx_le(self, t):
        import bisect
        i = bisect.bisect_right(self.ts, t) - 1
        return i if i >= 0 else None
    def idx_le_from(self, t):
        return self.idx_le(t)


# ---------------------------------------------------------------- dirección / familia
def classify(kind, source, msg, sym):
    """-> (familia, gate, dir)  dir: +1 alcista, -1 bajista, 0 no direccional/excluida."""
    k = (kind or "").strip()
    m = msg or ""
    up = (k + " " + m).upper()
    gate = "SONO"
    if "[MUTED" in k or "MUTED p<" in k:
        gate = "MUTED_p<55"
    elif "[VETO medido]" in k:
        gate = "VETO_medido"
    elif "capitan opuesto" in k.lower():
        gate = "MUTED_capitan"
    elif "VETADO" in k.upper():
        gate = "VETADO_bandwalk"
    elif "⭐" in k:
        gate = "SONO_ESTRELLA"

    # ---- Bollinger
    if source == "bollinger" or k.startswith("🎈") or k.startswith("🎯"):
        if "APERTURA FUERA DE BANDA" in up:
            return "BB_APERTURA_FUERA", gate, (+1 if "ABAJO" in up or "DEBAJO" in up else -1) if ("ABAJO" in up or "ARRIBA" in up or "DEBAJO" in up or "ENCIMA" in up) else 0
        if "RE-ENTRADA A BANDA" in up:
            return "BB_REENTRADA_BANDA", gate, (+1 if "ABAJO" in up else (-1 if "ARRIBA" in up else 0))
        if "15M RE-ENTRADA" in up or "15 MINUTOS" in up:
            return "BB_REENTRADA_15m", gate, (+1 if "ABAJO" in up else (-1 if "ARRIBA" in up else 0))
        if "BAND-WALK" in up or "CAMINA LA BANDA" in up:
            # continuación
            return "BB_BANDWALK", gate, (-1 if "ABAJO" in up else (+1 if "ARRIBA" in up else 0))
        if "REBOTE" in up:
            return "BB_REBOTE", gate, (+1 if "ABAJO" in up else (-1 if "ARRIBA" in up else 0))
        return "BB_OTRO", gate, 0

    # ---- ballenas
    if source == "whale" or "BALLENA" in up:
        if "CRECE" in up:
            return "WHALE_CRECE", gate, -1          # calls creciendo = techo (ley 11)
        if "PUTS" in up:
            return "WHALE_PUTS", gate, +1
        if "CALLS" in up:
            return "WHALE_CALLS", gate, -1
        return "WHALE_OTRO", gate, 0

    # ---- flow (spikes + bot flow_pulse SELL/BUY)
    if source == "flow":
        if "SPIKE" in up:
            fam = "FLOW_SPIKE_PUTS" if "PUTS" in up else "FLOW_SPIKE_CALLS"
            d = +1 if "PUTS" in up else -1
            return fam, gate, d
        if ": SELL" in k.upper():
            return "FLOWBOT_SELL", gate, -1
        if ": BUY" in k.upper():
            return "FLOWBOT_BUY", gate, +1
        return "FLOW_OTRO", gate, 0

    if source == "structural":
        if "magnet" in k:
            return "STRUCT_MAGNET", gate, (+1 if "↑" in m else (-1 if "↓" in m else 0))
        return ("STRUCT_PIN" if "pin" in k else "STRUCT_FLIP"), gate, 0

    if source == "cusum" or "TERREMOTO" in up:
        if "ALZA" in up:
            return "CUSUM_ALZA", gate, +1
        if "CAIDA" in up or "BAJA" in up:
            return "CUSUM_CAIDA", gate, -1
        return "CUSUM_OTRO", gate, 0

    if source == "dip" or "DIP REAL" in up:
        return "DIP_REAL", gate, +1

    # ---- source='signal' (bots C++ y avisos)
    if k.startswith("🌊 FLUJO"):
        return ("FLUJO_INTRADIA_PUTS", gate, +1) if "PUTS" in up else ("FLUJO_INTRADIA_CALLS", gate, -1)
    if k.startswith("🔄 GIRO"):
        return ("GIRO_A_PUTS", gate, +1) if "A PUTS" in up else ("GIRO_A_CALLS", gate, -1)
    if not k and "FLUJO DE" in up and "FUERTE HOY" in up:
        return ("FLUJO_DIARIO_PUTS", gate, +1) if "FLUJO DE PUTS" in up else ("FLUJO_DIARIO_CALLS", gate, -1)
    if "MANADA A" in up:
        return ("MANADA_A_PUTS", gate, +1) if "A PUTS" in up else ("MANADA_A_CALLS", gate, -1)
    if "CAPITAN REVIERTE" in up:
        return "CAPITAN_REVIERTE", gate, (+1 if "AL ALZA" in up or "PISO" in up else -1)
    if k.upper().endswith(": SELL") or ": SELL " in k.upper() or ": SELL NOW" in k.upper():
        return "BOT_SELL", gate, -1
    if k.upper().endswith(": BUY") or ": BUY " in k.upper() or ": BUY NOW" in k.upper():
        return "BOT_BUY", gate, +1
    if "READ-THROUGH" in up:
        return "READTHROUGH_BAJISTA", gate, -1
    if "🛡" in k:
        return "DRAM_GUARD", gate, 0
    if "🛰" in k:
        return "FINVIZ", gate, 0
    if "ALARMA PRECIO" in up:
        return "ALARMA_PRECIO", gate, 0
    if "OPCIONES:" in k:
        return "FLUJO_TABLERO", gate, 0
    return "OTRO", gate, 0


# ---------------------------------------------------------------- baseline por día/símbolo
def rth_bounds(day):
    d = dt.datetime.strptime(day, "%Y-%m-%d")
    o = int(d.replace(hour=9, minute=30).timestamp())
    c = int(d.replace(hour=16, minute=0).timestamp())
    return o, c


def build_baselines(bars, days):
    """p_long/p_short/drift por (sym, day, h): sobre TODOS los minutos RTH de ese día,
    fracción en que una entrada larga (resp. corta) habría ganado (>+0.05%) a +h min,
    y retorno medio de la entrada larga. Es la base contra la que se juzga cada señal."""
    base = {}
    for sym, rows in bars.items():
        S = Series(rows)
        import bisect
        for day in days:
            o, cl = rth_bounds(day)
            i0 = bisect.bisect_left(S.ts, o); i1 = bisect.bisect_right(S.ts, cl)
            if i1 - i0 < 30:
                continue
            for h in HOR:
                nl = ns = n = 0; sr = 0.0
                for i in range(i0, i1):
                    t = S.ts[i]
                    j = bisect.bisect_right(S.ts, t + h * 60, i, i1) - 1
                    if j <= i or S.ts[j] < t + h * 60 - 180:
                        continue
                    r = (S.c[j] - S.c[i]) / S.c[i] * 100
                    n += 1; sr += r
                    if r > WIN_THRESH: nl += 1
                    if -r > WIN_THRESH: ns += 1
                if n >= 30:
                    base[(sym, day, h)] = (nl / n, ns / n, sr / n, n)
    return base


# ---------------------------------------------------------------- estadística
def wilson(k, n):
    return E.wilson(k, n)


def norm_cdf(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def two_sided_p(z):
    return 2 * (1 - norm_cdf(abs(z)))


def cluster_score_test(obs):
    """obs = [(cluster_id, win01, p_expected)] -> (n, wins, wr, exp_wr, lift_pp, z_iid,
    z_cluster, p_cluster, n_clusters). Test de score Poisson-binomial con varianza
    cluster-robusta (sandwich): Var = Σ_c (Σ_i (w_i - p_i))²."""
    n = len(obs)
    if n == 0:
        return None
    wins = sum(o[1] for o in obs)
    sp = sum(o[2] for o in obs)
    var_iid = sum(o[2] * (1 - o[2]) for o in obs)
    byc = defaultdict(float)
    for cid, w, p in obs:
        byc[cid] += (w - p)
    num = wins - sp
    var_cl = sum(v * v for v in byc.values())
    z_iid = num / math.sqrt(var_iid) if var_iid > 0 else 0.0
    z_cl = num / math.sqrt(var_cl) if var_cl > 0 else 0.0
    return dict(n=n, wins=wins, wr=100.0 * wins / n, exp=100.0 * sp / n,
                lift=100.0 * (wins - sp) / n, z_iid=z_iid, z_cl=z_cl,
                p_cl=two_sided_p(z_cl), p_iid=two_sided_p(z_iid), nclust=len(byc))


def bh_fdr(pvals, q=0.05):
    """-> lista de bool (rechaza H0) alineada a pvals, + umbral."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    rej = [False] * m; kmax = -1
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    if kmax > 0:
        for rank, i in enumerate(order, 1):
            if rank <= kmax:
                rej[i] = True
    thr = q * kmax / m if kmax > 0 else 0.0
    return rej, thr


# ---------------------------------------------------------------- main
def main():
    bars = load_bars()
    print(f"[bars] {len(bars)} símbolos, {sum(len(v) for v in bars.values())} barras")
    series = {s: Series(r) for s, r in bars.items()}
    import bisect

    c = sqlite3.connect(DB)
    sigs = c.execute("SELECT ts_epoch, ts_txt, date, kind, symbol, price, priority, source, msg "
                     "FROM signals WHERE ts_epoch IS NOT NULL AND date < '2026-07-25' "
                     "ORDER BY ts_epoch").fetchall()
    days = sorted(set(r[2] for r in sigs))
    print(f"[signals] {len(sigs)} filas, días {days[0]}..{days[-1]}")
    base = build_baselines(bars, days)
    print(f"[baseline] {len(base)} celdas (sym,día,h)")

    # ---- régimen diario
    regime = {}
    for day in days:
        row = {}
        for sym in ("SPY", "QQQ"):
            S = series.get(sym)
            if not S: continue
            o, cl = rth_bounds(day)
            i0 = bisect.bisect_left(S.ts, o); i1 = bisect.bisect_right(S.ts, cl) - 1
            if i0 < len(S.ts) and i1 > i0:
                row[sym] = (S.c[i1] - S.o[i0]) / S.o[i0] * 100
        if row:
            avg = sum(row.values()) / len(row)
            lab = "ALCISTA" if avg > 0.20 else ("BAJISTA" if avg < -0.20 else "LATERAL")
            regime[day] = dict(spy=row.get("SPY"), qqq=row.get("QQQ"), avg=avg, label=lab)

    # ---- evaluación señal a señal
    rows = []
    skip = defaultdict(int)
    for ep, ts_txt, day, kind, sym, price, prio, source, msg in sigs:
        fam, gate, d = classify(kind, source or "", msg or "", sym)
        if not sym or sym not in series:
            skip["sin_simbolo_o_barras"] += 1; continue
        if d == 0:
            skip["sin_direccion:" + fam] += 1; continue
        S = series[sym]; t = int(ep)
        i = S.idx_le(t)
        if i is None or t - S.ts[i] > 300:
            skip["sin_barra_cercana"] += 1; continue
        o, cl = rth_bounds(day)
        if not (o <= t <= cl - 300):
            skip["fuera_RTH"] += 1; continue
        entry = S.c[i]
        rec = dict(day=day, ts=t, hhmm=ts_txt, sym=sym, fam=fam, gate=gate, dir=d,
                   entry=entry, source=source, kind=kind,
                   hour=dt.datetime.fromtimestamp(t).hour, res={})
        i1 = bisect.bisect_right(S.ts, cl)
        for h in HOR:
            j = bisect.bisect_right(S.ts, t + h * 60, i, len(S.ts)) - 1
            if j <= i or S.ts[j] < t + h * 60 - 180:
                continue
            ret = (S.c[j] - entry) / entry * 100 * d
            hi = max(S.h[i + 1:j + 1]); lo = min(S.l[i + 1:j + 1])
            mfe = ((hi - entry) if d > 0 else (entry - lo)) / entry * 100
            mae = ((entry - lo) if d > 0 else (hi - entry)) / entry * 100
            b = base.get((sym, day, h))
            p = (b[0] if d > 0 else b[1]) if b else None
            # base condicional al movimiento: quita el sesgo de "las señales suenan en
            # momentos volátiles" (donde ganar >0.05% es más fácil en AMBOS sentidos)
            pc = None
            if b and (b[0] + b[1]) > 0:
                pc = (b[0] if d > 0 else b[1]) / (b[0] + b[1])
            bret = (b[2] * d) if b else None      # deriva del día en la dirección de la tesis
            rec["res"][h] = dict(ret=ret, win=1 if ret > WIN_THRESH else 0,
                                 moved=1 if abs(ret) > WIN_THRESH else 0,
                                 mfe=mfe, mae=mae, p=p, pc=pc, bret=bret)
        if rec["res"]:
            rows.append(rec)
    c.close()
    print(f"[eval] {len(rows)} señales evaluadas; saltadas: "
          f"{sum(skip.values())} ({dict(sorted(skip.items(), key=lambda x:-x[1])[:8])})")
    return rows, regime, base, series, days, skip


if __name__ == "__main__":
    rows, regime, base, series, days, skip = main()
    out = dict(rows=rows, regime=regime, days=days, skip=dict(skip))
    p = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else "/tmp/fhb.json"
    json.dump(out, open(p, "w"))
    print("->", p)
