#!/usr/bin/env python3
"""Backtest en la OPCION real (0DTE) para QQQ/SPY/NVDA a partir de poly_opt_bars (5m).
Entrada = open de la barra 5m siguiente a la señal; TP +30/+50/+100% contra el HIGH."""
import os, sys, json, sqlite3, math, bisect, datetime as dt
from collections import defaultdict
os.environ.setdefault("TZ", "America/New_York")
import time as _t; _t.tzset()
sys.path.insert(0, "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader/scripts")
os.chdir("/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader")
from full_history_backtest import wilson, cluster_score_test

SP = "/tmp"
D = json.load(open(SP + "/fhb.json"))
rows = [r for r in D["rows"] if r["sym"] in ("QQQ", "SPY", "NVDA")]
print(f"señales QQQ/SPY/NVDA con dirección: {len(rows)}")

c = sqlite3.connect("trades.db")
# indice de contratos 0DTE: (sym, exp, right) -> [(strike, otk)]
cons = defaultdict(list)
for sym, exp, right, strike, otk in c.execute(
        "SELECT DISTINCT sym,exp,right,strike,otk FROM poly_opt_bars"):
    cons[(sym, exp, right)].append((strike, otk))
bars = defaultdict(list)
for otk, ts, o, h, l, cl, v in c.execute("SELECT otk,ts,o,h,l,c,v FROM poly_opt_bars ORDER BY otk,ts"):
    bars[otk].append((ts // 1000, o, h, l, cl, v))
c.close()
print(f"contratos con barras: {len(bars)}  · claves 0DTE: {len(cons)}")

HOR = [15, 30, 60]
TPS = [0.30, 0.50, 1.00]

# ---- BASELINE de la opcion: probabilidad de que un contrato 0DTE cualquiera suba +X%
# desde el open de una barra 5m cualquiera de ese mismo dia. Sin esto, "53% TP30" no
# significa nada: el 0DTE ATM se mueve +30% por gamma sola.
# Ojo: se restringe a barras dentro de +-60min del instante de la señal, porque el
# premium 0DTE decae durante el dia y un +30% es mucho mas facil a las 15:30 que a las 10:00.
def opt_baseline(otk, t0, h):
    b = bars.get(otk)
    if not b:
        return None
    k = h // 5
    cnt = defaultdict(int); n = 0
    for i in range(len(b)):
        if abs(b[i][0] - t0) > 3600 or b[i][1] <= 0.02 or b[i][5] <= 0:
            continue
        seg = b[i:i + k]
        if len(seg) < k:
            continue
        hi = max(x[2] for x in seg)
        n += 1
        for t in TPS:
            if hi >= b[i][1] * (1 + t):
                cnt[t] += 1
    if n < 6:
        return None
    return {t: cnt[t] / n for t in TPS}

out = []
skip = defaultdict(int)
for r in rows:
    right = "call" if r["dir"] > 0 else "put"
    key = (r["sym"], r["day"], right)
    lst = cons.get(key)
    if not lst:
        skip["sin_contrato_0DTE"] += 1; continue
    strike, otk = min(lst, key=lambda x: abs(x[0] - r["entry"]))
    b = bars.get(otk)
    if not b:
        skip["sin_barras"] += 1; continue
    ts = [x[0] for x in b]
    i = bisect.bisect_right(ts, r["ts"])       # primera barra que EMPIEZA despues de la señal
    if i >= len(b) or ts[i] - r["ts"] > 600:
        skip["sin_barra_siguiente"] += 1; continue
    e = b[i]
    if e[1] <= 0.02 or e[5] <= 0:
        skip["premium_o_vol_nulo"] += 1; continue
    entry = e[1]
    rec = dict(sym=r["sym"], day=r["day"], fam=r["fam"], gate=r["gate"], dir=r["dir"],
               otk=otk, strike=strike, entry=entry, spot=r["entry"],
               moneyness=(strike - r["entry"]) / r["entry"] * 100 * (1 if right == "call" else -1),
               res={}, und=r["res"])
    # contrato OPUESTO (mismo strike, otro derecho) = control de direccionalidad puro
    opp_right = "put" if right == "call" else "call"
    opp = None
    for st, ot in cons.get((r["sym"], r["day"], opp_right), []):
        if abs(st - strike) < 1e-6:
            opp = ot
    ob = bars.get(opp) if opp else None
    for h in HOR:
        end = r["ts"] + h * 60
        j = i
        hi = -1e9; last = None
        while j < len(b) and b[j][0] < end:
            hi = max(hi, b[j][2]); last = b[j][4]; j += 1
        if last is None:
            continue
        d = dict(ret=(last - entry) / entry * 100,
                 mfe=(hi - entry) / entry * 100,
                 **{f"tp{int(t*100)}": 1 if hi >= entry * (1 + t) else 0 for t in TPS})
        bb_ = opt_baseline(otk, r["ts"], h)
        if bb_:
            d.update({f"b{int(t*100)}": bb_[t] for t in TPS})
        if ob:
            ots = [x[0] for x in ob]
            oi = bisect.bisect_right(ots, r["ts"])
            if oi < len(ob) and ots[oi] - r["ts"] <= 600 and ob[oi][1] > 0.02:
                oe = ob[oi][1]; ohi = -1e9; olast = None; jj = oi
                while jj < len(ob) and ob[jj][0] < end:
                    ohi = max(ohi, ob[jj][2]); olast = ob[jj][4]; jj += 1
                if olast is not None:
                    d["opp_ret"] = (olast - oe) / oe * 100
                    d.update({f"opp_tp{int(t*100)}": 1 if ohi >= oe * (1 + t) else 0 for t in TPS})
        rec["res"][h] = d
    if rec["res"]:
        out.append(rec)
print(f"evaluadas en opción: {len(out)} · saltadas {dict(skip)}")

json.dump(out, open(SP + "/opt_bt.json", "w"))

def agg(rs, h, key):
    v = [x["res"][h][key] for x in rs if h in x["res"]]
    return v

print("\n=== OPCION 0DTE vs SUBYACENTE (mismas señales) ===")
print("  TP*  = % de señales que tocaron ese TP contra el HIGH de barras 5m (sin stop)")
print("  base = misma prob. entrando en un minuto CUALQUIERA del mismo contrato/dia")
print("  OPP  = mismo strike, derecho CONTRARIO (control de direccionalidad puro)")
print(f"{'grupo':22s} {'h':>3s} {'n':>4s} {'TP30':>6s}{'base':>6s}{'OPP':>5s} {'TP50':>6s}{'base':>6s} "
      f"{'TP100':>6s} {'retOPC':>8s} {'OPPret':>8s} | {'WRsub':>6s} {'retSub':>7s}")
groups = {"TODAS": out}
for f in sorted(set(x["fam"] for x in out)):
    g = [x for x in out if x["fam"] == f]
    if len(g) >= 15:
        groups[f] = g
for s in ("QQQ", "SPY", "NVDA"):
    groups["sym:" + s] = [x for x in out if x["sym"] == s]
for name, rs in groups.items():
    for h in HOR:
        v = [x for x in rs if h in x["res"]]
        if len(v) < 5: continue
        n = len(v)
        f = lambda k: sum(x["res"][h].get(k, 0) for x in v) / n * 100
        g = lambda k: ([x["res"][h][k] for x in v if k in x["res"][h]])
        t30, t50, t100 = f("tp30"), f("tp50"), f("tp100")
        b30 = (sum(g("b30")) / len(g("b30")) * 100) if g("b30") else float("nan")
        b50 = (sum(g("b50")) / len(g("b50")) * 100) if g("b50") else float("nan")
        o30 = (sum(g("opp_tp30")) / len(g("opp_tp30")) * 100) if g("opp_tp30") else float("nan")
        oret = (sum(g("opp_ret")) / len(g("opp_ret"))) if g("opp_ret") else float("nan")
        ro = sum(x["res"][h]["ret"] for x in v) / n
        us = [x["und"].get(str(h)) or x["und"].get(h) for x in v]
        us = [u for u in us if u]
        wr = sum(u["win"] for u in us) / len(us) * 100 if us else 0
        rs_ = sum(u["ret"] for u in us) / len(us) if us else 0
        print(f"{name:22s} {h:>3d} {n:>4d} {t30:>5.0f}%{b30:>5.0f}%{o30:>4.0f}% {t50:>5.0f}%{b50:>5.0f}% "
              f"{t100:>5.0f}% {ro:>+7.1f}% {oret:>+7.1f}% | {wr:>5.0f}% {rs_:>+6.3f}%")

print("\n=== distribucion de moneyness (%) y premium de entrada ===")
for s in ("QQQ", "SPY", "NVDA"):
    v = [x for x in out if x["sym"] == s]
    if not v: continue
    mn = sorted(x["moneyness"] for x in v); pr = sorted(x["entry"] for x in v)
    print(f"  {s}: n={len(v)} moneyness p10/50/90 = {mn[len(mn)//10]:+.2f}/{mn[len(mn)//2]:+.2f}/{mn[-len(mn)//10]:+.2f}%"
          f"  premium p10/50/90 = ${pr[len(pr)//10]:.2f}/${pr[len(pr)//2]:.2f}/${pr[-len(pr)//10]:.2f}")

print("\n=== por hora (opcion, h=30) ===")
byh = defaultdict(list)
for x in out:
    hh = dt.datetime.strptime(x["day"], "%Y-%m-%d")
    byh[x["fam"]].append(x)
print("\n=== TP30 por dia ===")
bd = defaultdict(list)
for x in out: bd[x["day"]].append(x)
for d in sorted(bd):
    v = [x for x in bd[d] if 30 in x["res"]]
    if not v: continue
    print(f"  {d} n={len(v):>3d} TP30 {sum(x['res'][30]['tp30'] for x in v)/len(v)*100:>3.0f}% "
          f"TP50 {sum(x['res'][30]['tp50'] for x in v)/len(v)*100:>3.0f}% "
          f"retOPC {sum(x['res'][30]['ret'] for x in v)/len(v):+.1f}%")
