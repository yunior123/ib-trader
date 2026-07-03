#!/usr/bin/env python3
"""Analisis del backtest en el VEHICULO REAL (opcion ATM). Lee el json que produce
option_vehicle_backtest.py y escupe todas las tablas del informe."""
import json, os, sys, sqlite3, statistics as st
from collections import defaultdict
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from eod_backtest import wilson

DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-07-24"
D = json.load(open(os.path.join(REPO, "data", f"option_vehicle_{DAY}.json")))
R = D["recs"]

def agg(rows, H):
    v = [x[f"ret{H}"] for x in rows if x[f"ret{H}"] is not None]
    if not v: return None
    w = sum(1 for r in v if r > 0)
    wr, lo, hi = wilson(w, len(v))
    return dict(n=len(v), wr=wr, lo=lo, hi=hi, mean=sum(v)/len(v), med=st.median(v))

def tp(rows, key):
    v = [x[key] for x in rows if x[key] is not None]
    if not v: return None
    w = sum(v); wr, lo, hi = wilson(w, len(v))
    return dict(n=len(v), wr=wr, lo=lo, hi=hi)

def line(name, rows, H):
    a = agg(rows, H)
    if not a: return f"| {name} | 0 | — | — | — | — |"
    return (f"| {name} | {a['n']} | {a['wr']}% | [{a['lo']},{a['hi']}] | "
            f"{a['mean']:+.1f}% | {a['med']:+.1f}% |")

def sec(title): print("\n" + "="*70 + f"\n{title}\n" + "="*70)

NOAMB = [x for x in R if not x["ambig"]]
GATE  = [x for x in NOAMB if x["gate_ok"]]
GB    = [x for x in NOAMB if x["gate_ok"] and x["budget_ok"]]

sec("0. COBERTURA")
print(f"puntuadas={len(R)}  no-ambiguas={len(NOAMB)}  ambiguas(GIRO)={len(R)-len(NOAMB)}")
print(f"pasan gate (spread<=5% y OI>500): {len(GATE)} de {len(NOAMB)} "
      f"({100*len(GATE)/len(NOAMB):.0f}%)")
print(f"prima > $200 (fuera de presupuesto): {sum(1 for x in NOAMB if not x['budget_ok'])} "
      f"de {len(NOAMB)} ({100*sum(1 for x in NOAMB if not x['budget_ok'])/len(NOAMB):.0f}%)")
print(f"gate Y presupuesto: {len(GB)} ({100*len(GB)/len(NOAMB):.0f}%)")
print(f"spread mediano={st.median([x['spread'] for x in NOAMB]):.1f}%  "
      f"medio={sum(x['spread'] for x in NOAMB)/len(NOAMB):.1f}%")
print(f"OI mediano={st.median([x['oi'] for x in NOAMB]):.0f}   "
      f"prima mediana=${st.median([x['cost'] for x in NOAMB]):.0f}")
print(f"lag de entrada mediano={st.median([x['lag'] for x in NOAMB])/60:.1f} min")
# desglose de por que falla el gate
fs = sum(1 for x in NOAMB if x["spread"] > 5)
fo = sum(1 for x in NOAMB if x["oi"] <= 500)
fb = sum(1 for x in NOAMB if x["spread"] > 5 and x["oi"] <= 500)
print(f"falla por spread: {fs}   falla por OI: {fo}   ambos: {fb}")

for label, rows in (("TODAS (no-ambiguas)", NOAMB), ("SOLO GATE OK", GATE),
                    ("GATE + PRESUPUESTO", GB)):
    sec(f"1. GLOBAL — {label}  (entrada ASK, salida BID)")
    print("| horizonte | n | WR | Wilson95 | ret medio | ret mediano |")
    print("|---|---:|---:|---|---:|---:|")
    for H in (15, 30, 60):
        print(line(f"+{H}m", rows, H))
    for t in (30, 50, 100):
        a = tp(rows, f"tp{t}")
        if a: print(f"| TP +{t}% (<=60m) | {a['n']} | {a['wr']}% | [{a['lo']},{a['hi']}] | | |")
    m = [x["mfe"] for x in rows if x["mfe"] is not None]
    if m: print(f"| MFE medio (bid max <=60m) | {len(m)} | | | {sum(m)/len(m):+.1f}% | {st.median(m):+.1f}% |")

# por familia
for label, rows in (("TODAS", NOAMB), ("GATE OK", GATE)):
    for H in (15, 30, 60):
        sec(f"2. POR FAMILIA — {label} @+{H}m")
        fams = defaultdict(list)
        for x in rows: fams[x["fam"]].append(x)
        print("| familia | n | WR | Wilson95 | ret medio | ret mediano | TP+50% | TP+100% |")
        print("|---|---:|---:|---|---:|---:|---:|---:|")
        for f, rs in sorted(fams.items(), key=lambda x: -len(x[1])):
            a = agg(rs, H)
            if not a: continue
            t50 = tp(rs, "tp50"); t100 = tp(rs, "tp100")
            print(f"| {f} | {a['n']} | {a['wr']}% | [{a['lo']},{a['hi']}] | {a['mean']:+.1f}% | "
                  f"{a['med']:+.1f}% | {t50['wr'] if t50 else '—'}% | {t100['wr'] if t100 else '—'}% |")
        a = agg(rows, H)
        print(f"| **TOTAL** | {a['n']} | {a['wr']}% | [{a['lo']},{a['hi']}] | {a['mean']:+.1f}% | {a['med']:+.1f}% | | |")

# gate del sistema (SONO vs silenciadas)
sec("3. GATES DEL SISTEMA (@+15m, no-ambiguas)")
g = defaultdict(list)
for x in NOAMB: g[x["gate"]].append(x)
print("| gate | n | WR | Wilson95 | ret medio | %pasa optgate |")
print("|---|---:|---:|---|---:|---:|")
for k, rs in sorted(g.items(), key=lambda x: -len(x[1])):
    a = agg(rs, 15)
    if not a: continue
    print(f"| {k} | {a['n']} | {a['wr']}% | [{a['lo']},{a['hi']}] | {a['mean']:+.1f}% | "
          f"{100*sum(y['gate_ok'] for y in rs)/len(rs):.0f}% |")

# BB REBOTE sono vs veto vs estrella
sec("4. BB REBOTE: SONO vs ⭐ vs VETO (@15m/@30m)")
bb = [x for x in NOAMB if x["fam"].startswith("BB REBOTE")]
grp = {"SONO normal": [x for x in bb if x["gate"]=="SONO" and "⭐" not in x["fam"]],
       "SONO ⭐ estrella": [x for x in bb if "⭐" in x["fam"]],
       "VETO medido": [x for x in bb if x["gate"]=="VETO medido"]}
for H in (15,30,60):
    print(f"--- +{H}m")
    print("| grupo | n | WR | Wilson95 | ret medio |")
    print("|---|---:|---:|---|---:|")
    for k, rs in grp.items(): print(line(k, rs, H))

# por lado
sec("5. POR LADO (@15m)")
for lbl, rows in (("TODAS", NOAMB), ("GATE OK", GATE)):
    for d, nm in ((1,"CALL (alcista)"), (-1,"PUT (bajista)")):
        rs = [x for x in rows if x["dir"]==d]
        print(f"{lbl:9s} {nm:16s} " + line("", rs, 15))

# por hora
sec("6. POR HORA ET (@15m, no-ambiguas)")
h = defaultdict(list)
for x in NOAMB: h[x["ts"][:2]].append(x)
print("| hora | n | WR | Wilson95 | ret medio | ret mediano |")
print("|---|---:|---:|---|---:|---:|")
for k in sorted(h): print(line(k+":00", h[k], 15))

# ambiguas
sec("7. AMBIGUAS (GIRO A CALLS/PUTS, supuesto fade)")
amb = [x for x in R if x["ambig"]]
for f in ("GIRO A CALLS", "GIRO A PUTS"):
    rs = [x for x in amb if x["fam"]==f]
    for H in (15,30):
        print(f"{f} @+{H}m  " + line("", rs, H))

# ---- comparacion pareada con el subyacente
sec("8. PAREADO CONTRA EL SUBYACENTE (mismas señales, mismo instante)")
c = sqlite3.connect(os.path.join(REPO, "data", "trades.db"))
u = {}
for ts, sym, hz, ret, win in c.execute(
        "SELECT ts_txt,symbol,horizon,ret,win FROM backtest_signal_outcomes "
        "WHERE date=? AND run_ts=1784941080.160406", (DAY,)):
    u[(ts, sym, hz)] = (ret, win)
c.close()
def paired(rows, H, gate_only=False):
    o = []; s = []
    for x in rows:
        k = (x["ts"], x["sym"], H)
        if k in u and x[f"ret{H}"] is not None:
            o.append(1 if x[f"ret{H}"] > 0 else 0); s.append(u[k][1])
    return o, s
print("| subconjunto | H | n pareada | WR subyacente | WR opcion | delta |")
print("|---|---|---:|---:|---:|---:|")
for lbl, rows in (("todas", NOAMB), ("gate OK", GATE), ("gate+presupuesto", GB)):
    for H in (15, 30):
        o, s = paired(rows, H)
        if not o: continue
        wo = wilson(sum(o), len(o)); ws = wilson(sum(s), len(s))
        print(f"| {lbl} | +{H}m | {len(o)} | {ws[0]}% [{ws[1]},{ws[2]}] | "
              f"{wo[0]}% [{wo[1]},{wo[2]}] | {wo[0]-ws[0]:+d}pp |")
sec("8b. PAREADO POR FAMILIA @15m (todas)")
fams = defaultdict(list)
for x in NOAMB: fams[x["fam"]].append(x)
print("| familia | n par | WR subyacente | WR opcion | delta | veredicto |")
print("|---|---:|---:|---:|---:|---|")
for f, rs in sorted(fams.items(), key=lambda x: -len(x[1])):
    o, s = paired(rs, 15)
    if len(o) < 3: continue
    wo = wilson(sum(o), len(o)); ws = wilson(sum(s), len(s))
    v = "igual"
    if wo[0] - ws[0] >= 8: v = "MEJORA en la opcion"
    if ws[0] - wo[0] >= 8: v = "EMPEORA en la opcion"
    print(f"| {f} | {len(o)} | {ws[0]}% [{ws[1]},{ws[2]}] | {wo[0]}% [{wo[1]},{wo[2]}] | {wo[0]-ws[0]:+d}pp | {v} |")

sec("9. SIMBOLOS: cuantas señales apuntan a contratos inoperables")
sy = defaultdict(list)
for x in NOAMB: sy[x["sym"]].append(x)
print("| sym | n | %gate OK | spread mediano | OI mediano | prima mediana | %>$200 |")
print("|---|---:|---:|---:|---:|---:|---:|")
for s, rs in sorted(sy.items(), key=lambda x: -len(x[1])):
    print(f"| {s} | {len(rs)} | {100*sum(y['gate_ok'] for y in rs)/len(rs):.0f}% | "
          f"{st.median([y['spread'] for y in rs]):.1f}% | {st.median([y['oi'] for y in rs]):.0f} | "
          f"${st.median([y['cost'] for y in rs]):.0f} | "
          f"{100*sum(1 for y in rs if not y['budget_ok'])/len(rs):.0f}% |")
