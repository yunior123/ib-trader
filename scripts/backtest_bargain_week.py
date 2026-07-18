#!/usr/bin/env python3
"""backtest_bargain_week.py — backtest de los candidatos del bargain hunter
(data/screener/bargain_log_*.jsonl) contra lo que hizo el precio DESPUÉS.

Objetivo (orden Yunior 2026-07-18): verificar que los filtros no nos meten en
tickers equivocados y proponer mejoras de filtro con evidencia. NO opera nada.

Uso:  ./venv/bin/python scripts/backtest_bargain_week.py [dias_jsonl...]
      (default: todos los data/screener/bargain_log_*.jsonl)

Método: por cada candidato (primer avistamiento del día), retorno forward con
datos diarios de yfinance: close mismo día, +1 día, fin de semana (último día
disponible). Win = forward +1d > 0. Agrupa por lane, score, gain_pct y mcap
para ver QUÉ filtro separa ganadores de perdedores.
"""
import glob, json, sys, statistics
from collections import defaultdict

import yfinance as yf

files = sys.argv[1:] or sorted(glob.glob("data/screener/bargain_log_*.jsonl"))
if not files:
    sys.exit("sin logs bargain_log_*.jsonl")

# 1) primer avistamiento por (día, sym)
first = {}
verdicts = {}
for fp in files:
    day = fp.split("_")[-1].split(".")[0]
    for line in open(fp):
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("kind") == "scan":
            for c in j.get("candidates", []):
                k = (day, c["sym"])
                if k not in first:
                    first[k] = {**c, "day": day, "ts": j["ts"]}
        elif j.get("kind") == "verdict":
            verdicts[(day, j["sym"])] = j.get("ta_action", "?")

syms = sorted({s for _, s in first})
days = sorted({d for d, _ in first})
print(f"candidatos únicos: {len(first)} ({len(syms)} tickers) en {len(days)} días: {days}")

# 2) precios diarios (una sola descarga batch)
d0 = min(days)
start = f"{d0[:4]}-{d0[4:6]}-{int(d0[6:]):02d}"
px = yf.download(syms, start=start, period=None, interval="1d",
                 progress=False, auto_adjust=False, group_by="ticker", threads=True)

def closes(sym):
    try:
        s = px[sym]["Close"].dropna()
        return {i.strftime("%Y%m%d"): float(v) for i, v in s.items()}
    except Exception:
        return {}

rows = []
for (day, sym), c in sorted(first.items()):
    cl = closes(sym)
    dseq = sorted(cl)
    if day not in cl:
        continue
    i = dseq.index(day)
    same = (cl[day] / c["price"] - 1) * 100
    nxt = (cl[dseq[i + 1]] / c["price"] - 1) * 100 if i + 1 < len(dseq) else None
    week = (cl[dseq[-1]] / c["price"] - 1) * 100 if dseq[-1] != day else same
    rows.append({**c, "ret_same": same, "ret_1d": nxt, "ret_week": week,
                 "verdict": verdicts.get((day, sym), "-")})

def stats(sub, key="ret_1d"):
    v = [r[key] for r in sub if r[key] is not None]
    if not v:
        return "n=0"
    wins = sum(1 for x in v if x > 0)
    return (f"n={len(v)} win%={100*wins/len(v):.0f} media={statistics.mean(v):+.2f}% "
            f"mediana={statistics.median(v):+.2f}% peor={min(v):+.1f}% mejor={max(v):+.1f}%")

print(f"\n== GLOBAL (retorno +1 día desde precio de detección) ==\n  {stats(rows)}")
print(f"== GLOBAL (a fin de semana) ==\n  {stats(rows, 'ret_week')}")

print("\n== por LANE ==")
by = defaultdict(list)
for r in rows: by[r["lane"]].append(r)
for k, sub in sorted(by.items()):
    print(f"  {k:<12} {stats(sub)}")

print("\n== por SCORE ==")
for name, lo, hi in [("score<8", 0, 8), ("8-15", 8, 15), ("score>15", 15, 1e9)]:
    print(f"  {name:<12} {stats([r for r in rows if lo <= r['score'] < hi])}")

print("\n== por GAIN% del día (gainer_dip) ==")
for name, lo, hi in [("gain 5-10%", 5, 10), ("10-20%", 10, 20), ("gain>20%", 20, 1e9)]:
    print(f"  {name:<12} {stats([r for r in rows if r['lane']=='gainer_dip' and lo <= r.get('gain_pct',0) < hi])}")

print("\n== por MARKET CAP (M$) ==")
for name, lo, hi in [("micro<2000", 0, 2000), ("2-10k", 2000, 10000), ("large>10k", 10000, 1e12)]:
    print(f"  {name:<12} {stats([r for r in rows if lo <= r.get('market_cap',0) < hi])}")

print("\n== veredicto TA del bot vs realidad ==")
byv = defaultdict(list)
for r in rows: byv[r["verdict"]].append(r)
for k, sub in sorted(byv.items()):
    print(f"  {k:<12} {stats(sub)}")

print("\n== peores 8 (evitar este perfil) ==")
srt = sorted([r for r in rows if r["ret_1d"] is not None], key=lambda r: r["ret_1d"])
for r in srt[:8]:
    print(f"  {r['day']} {r['sym']:<6} {r['lane']:<11} score={r['score']:.1f} "
          f"mcap={r.get('market_cap',0):.0f} 1d={r['ret_1d']:+.1f}% | {r.get('note','')[:46]}")
print("== mejores 8 (perfil a favorecer) ==")
for r in srt[-8:][::-1]:
    print(f"  {r['day']} {r['sym']:<6} {r['lane']:<11} score={r['score']:.1f} "
          f"mcap={r.get('market_cap',0):.0f} 1d={r['ret_1d']:+.1f}% | {r.get('note','')[:46]}")
