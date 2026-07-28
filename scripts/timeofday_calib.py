#!/usr/bin/env python3
"""timeofday_calib.py — MIDE el edge de cada fuente de señal por HORA DEL DÍA y por SÍMBOLO,
a partir de los outcomes ya backtesteados (trades.db backtest_signal_outcomes). Orden Yunior
2026-07-24: "maybe after 11:30 the signals loss power? setup probability depending on time of
day? search web so we have the math covered".

Base científica (verificada web): la volatilidad intradía es en U (alta 9:30-10:30 y 15-16,
mínimo al mediodía); el lunch-lull 11:30-14:00 tiene menor fiabilidad de mean-reversion/VWAP
(menos participación institucional). NO hardcodeamos la curva: la FORMA la da la literatura,
el FACTOR lo mide nuestra propia data con Wilson + shrinkage bayesiano.

Produce (todo MEDIDO):
  data/timeofday_factors.json  { source: { bucket: {n,wr,ci_low,factor} }, "_meta":{...} }
     factor = p_bucket_shrunk / p_source_overall  (multiplicador sobre la prob base)
  data/signal_enable.json      { "source|SYMBOL": {enabled, n, wr, ci_hi, why} }
     celda MUERTA (Wilson-hi < DEAD_HI con n>=DEAD_N) -> enabled:false  (apagado en duro)
  docs/FALSE-SIGNALS-<fecha>.md  reporte legible

Uso: python3 scripts/timeofday_calib.py [--h 15] [--quiet]
SEÑAL-SOLAMENTE (solo lee; no dispara nada).
"""
import os, sys, json, time, sqlite3
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
from eod_backtest import wilson

DB = os.path.join(REPO, "trades.db")
SHRINK_K = 20        # fuerza del prior bayesiano (= V6Prob en nvda_signal_bot.cpp)
DEAD_HI = 45         # si el Wilson-hi de una celda < esto (con n grande) = muerta
DEAD_N = 15
FACTOR_LO, FACTOR_HI = 0.40, 1.50   # clamp del multiplicador

# buckets de hora del día (minutos ET desde medianoche) — alineados a la doctrina CLAUDE.md
BUCKETS = [
    ("premarket", 0, 570),        # < 9:30  (subasta/backfill — ruido)
    ("auction", 570, 585),        # 9:30-9:45  (jamás operar)
    ("golden", 585, 630),         # 9:45-10:30 (ventana de oro)
    ("mid_am", 630, 690),         # 10:30-11:30
    ("lunch", 690, 840),          # 11:30-14:00 (picadora / lunch-lull)
    ("pm", 840, 900),             # 14:00-15:00
    ("power", 900, 960),          # 15:00-16:00 (power hour)
    ("afterhours", 960, 1440),    # > 16:00
]


def bucket_of(ts_txt):
    try:
        hh, mm = int(ts_txt[:2]), int(ts_txt[3:5])
    except Exception:
        return None
    t = hh * 60 + mm
    for name, lo, hi in BUCKETS:
        if lo <= t < hi:
            return name
    return None


def load_outcomes(h=15):
    c = sqlite3.connect(DB)
    run = c.execute("SELECT MAX(run_ts) FROM backtest_signal_outcomes").fetchone()[0]
    rows = c.execute("SELECT ts_txt, symbol, source, win FROM backtest_signal_outcomes "
                     "WHERE horizon=? AND run_ts=?", (h, run)).fetchall()
    c.close()
    return rows, run


def calibrate(h=15):
    rows, run = load_outcomes(h)
    # agregados
    src_tot = defaultdict(lambda: [0, 0])            # source -> [n, wins]
    src_bkt = defaultdict(lambda: [0, 0])            # (source,bucket) -> [n,wins]
    src_sym = defaultdict(lambda: [0, 0])            # (source,symbol) -> [n,wins]
    for ts_txt, sym, source, win in rows:
        b = bucket_of(ts_txt)
        src_tot[source][0] += 1; src_tot[source][1] += win
        if b:
            src_bkt[(source, b)][0] += 1; src_bkt[(source, b)][1] += win
        if sym:
            src_sym[(source, sym)][0] += 1; src_sym[(source, sym)][1] += win

    # factores por hora del día (shrinkage hacia el WR de la fuente)
    factors = {}
    for source, (n, w) in src_tot.items():
        p_src = w / n if n else 0.5
        factors[source] = {}
        for name, _, _ in BUCKETS:
            bn, bw = src_bkt.get((source, name), [0, 0])
            if bn == 0:
                continue
            p_shrunk = (bw + p_src * SHRINK_K) / (bn + SHRINK_K)
            factor = max(FACTOR_LO, min(FACTOR_HI, (p_shrunk / p_src) if p_src > 0 else 1.0))
            wr, lo, hi = wilson(bw, bn)
            factors[source][name] = dict(n=bn, wr=wr, ci_low=lo, ci_high=hi,
                                         factor=round(factor, 3))
    factors["_meta"] = dict(ts=time.time(), at=time.strftime("%Y-%m-%d %H:%M:%S"),
                            horizon=h, run_ts=run, shrink_k=SHRINK_K,
                            source_overall={s: dict(n=n, wr=wilson(w, n)[0])
                                            for s, (n, w) in src_tot.items()})

    # mapa de apagado en duro: celdas source|SYMBOL medidas-muertas
    enable = {}
    for (source, sym), (n, w) in sorted(src_sym.items(), key=lambda x: -x[1][0]):
        wr, lo, hi = wilson(w, n)
        dead = (n >= DEAD_N and hi < DEAD_HI)
        enable[f"{source}|{sym}"] = dict(enabled=(not dead), n=n, wr=wr, ci_hi=hi,
                                         why=(f"muerta: Wilson-hi {hi}%<{DEAD_HI}% n={n}"
                                              if dead else "viva"))
    return factors, enable, src_tot, src_bkt, src_sym, run


def write_report(factors, enable, src_tot, src_bkt, src_sym):
    at = factors["_meta"]["at"]
    L = []
    L.append(f"# Caza de falsas señales — reporte medido ({at})\n")
    L.append("Backtest sobre `poly_bars`, horizonte 15m, fuente `backtest_signal_outcomes` "
             "(run más reciente). Todo Wilson 95%. SEÑAL-SOLAMENTE.\n")
    L.append("## 1. WR por fuente (el problema de fondo)\n")
    L.append("| fuente | n | WR | Wilson [lo,hi] |")
    L.append("|---|---|---|---|")
    for s, (n, w) in sorted(src_tot.items(), key=lambda x: -x[1][0]):
        wr, lo, hi = wilson(w, n)
        L.append(f"| {s} | {n} | {wr}% | [{lo},{hi}] |")
    L.append("\n> Casi toda fuente es cara-o-cruz o peor (CI-hi < 50). El edge NO está en la "
             "señal cruda sino en la SELECTIVIDAD (hora + símbolo + dirección-flota + valuación).\n")

    L.append("## 2. WR por HORA DEL DÍA (confirma el lunch-lull)\n")
    order = [b[0] for b in BUCKETS]
    for source in sorted(src_tot):
        cells = [(b, src_bkt.get((source, b), [0, 0])) for b in order]
        cells = [(b, nw) for b, nw in cells if nw[0] > 0]
        if not cells:
            continue
        L.append(f"\n**{source}** (overall {wilson(*reversed(src_tot[source]))[0] if False else wilson(src_tot[source][1], src_tot[source][0])[0]}%):\n")
        L.append("| bucket | n | WR | factor |")
        L.append("|---|---|---|---|")
        for b, (n, w) in cells:
            wr, lo, hi = wilson(w, n)
            fac = factors[source].get(b, {}).get("factor", 1.0)
            L.append(f"| {b} | {n} | {wr}% | ×{fac} |")

    L.append("\n## 3. Celdas MUERTAS apagadas en duro (fuente|símbolo)\n")
    L.append("| celda | n | WR | Wilson-hi | acción |")
    L.append("|---|---|---|---|---|")
    dead = [(k, v) for k, v in enable.items() if not v["enabled"]]
    for k, v in sorted(dead, key=lambda x: x[1]["wr"]):
        L.append(f"| {k} | {v['n']} | {v['wr']}% | {v['ci_hi']}% | 🔴 APAGADA |")
    if not dead:
        L.append("| — | | | | (ninguna cruza el umbral de muerte) |")

    L.append("\n## 4. Peores celdas vivas (a vigilar)\n")
    L.append("| celda | n | WR | Wilson [lo,hi] |")
    L.append("|---|---|---|---|")
    alive = [(k, v) for k, v in enable.items() if v["enabled"] and v["n"] >= 10]
    for k, v in sorted(alive, key=lambda x: x[1]["wr"])[:12]:
        wr, lo, hi = wilson(int(round(v["wr"] / 100 * v["n"])), v["n"])
        L.append(f"| {k} | {v['n']} | {v['wr']}% | [{lo},{hi}] |")
    doc = f"docs/FALSE-SIGNALS-{time.strftime('%Y-%m-%d')}.md"
    open(doc, "w").write("\n".join(L) + "\n")
    return doc


def main():
    a = sys.argv[1:]
    h = int(a[a.index("--h") + 1]) if "--h" in a else 15
    quiet = "--quiet" in a
    factors, enable, src_tot, src_bkt, src_sym, run = calibrate(h)
    for path, obj in (("data/timeofday_factors.json", factors), ("data/signal_enable.json", enable)):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)   # signal_conditioning.py lo lee en vivo
    doc = write_report(factors, enable, src_tot, src_bkt, src_sym)
    ndead = sum(1 for v in enable.values() if not v["enabled"])
    print(f"timeofday_calib OK: {len(src_tot)} fuentes, {ndead} celdas apagadas -> "
          f"data/timeofday_factors.json, data/signal_enable.json, {doc}")
    if quiet:
        return
    print("\n=== FACTOR por hora del día (multiplicador sobre prob base) ===")
    for source in sorted(k for k in factors if not k.startswith("_")):
        ov = factors["_meta"]["source_overall"].get(source, {})
        print(f"\n{source} (overall WR {ov.get('wr','?')}%, n={ov.get('n','?')}):")
        for b, _, _ in BUCKETS:
            if b in factors[source]:
                c = factors[source][b]
                print(f"    {b:11s} n={c['n']:<4d} WR {c['wr']:>3d}%  factor ×{c['factor']}")
    print(f"\n=== CELDAS APAGADAS ({ndead}) ===")
    for k, v in sorted(((k, v) for k, v in enable.items() if not v["enabled"]),
                       key=lambda x: x[1]["wr"]):
        print(f"    🔴 {k:22s} {v['why']}")


if __name__ == "__main__":
    main()
