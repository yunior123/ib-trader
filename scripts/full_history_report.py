#!/usr/bin/env python3
"""Analisis del backtest full-history. Metrica primaria = WR CONDICIONAL AL MOVIMIENTO
(quita el sesgo de volatilidad) contra la base del mismo simbolo/dia/horizonte."""
import os, sys, json, math
from collections import defaultdict
sys.path.insert(0, "/Users/yuniorrodriguezosorio/ib-trader/scripts")
os.chdir("/Users/yuniorrodriguezosorio/ib-trader")
from full_history_backtest import wilson, cluster_score_test, bh_fdr, two_sided_p

SP = "/tmp"
D = json.load(open(SP + "/fhb.json"))
rows, regime, days = D["rows"], D["regime"], D["days"]
HOR = [5, 15, 30, 60]
ALLTESTS = []          # (nombre, dict test)  para multiple testing


def cell(r, h):
    return r["res"].get(str(h)) or r["res"].get(h)


def obs_raw(rs, h):
    """(cluster, win, p_incondicional)"""
    return [((r["sym"], r["day"]), e["win"], e["p"])
            for r in rs if (e := cell(r, h)) and e.get("p") is not None]


def obs_cond(rs, h):
    """solo señales cuyo precio SI se movio >0.05% en algun sentido; base condicional."""
    o = []
    for r in rs:
        e = cell(r, h)
        if e and e.get("pc") is not None and e.get("moved"):
            o.append(((r["sym"], r["day"]), e["win"], e["pc"]))
    return o


def alpha(rs, h):
    """retorno medio - deriva media del dia en esa direccion (pp)."""
    a = [(e["ret"], e["bret"]) for r in rs if (e := cell(r, h)) and e.get("bret") is not None]
    if not a:
        return 0.0, 0.0
    return sum(x[0] for x in a) / len(a), sum(x[0] - x[1] for x in a) / len(a)


def mfe_mae(rs, h):
    a = [cell(r, h) for r in rs]
    a = [x for x in a if x and x.get("mfe") is not None]
    if not a:
        return 0, 0
    return sum(x["mfe"] for x in a) / len(a), sum(x["mae"] for x in a) / len(a)


def report(name, rs, h, register=False, indent="  "):
    oc = obs_cond(rs, h); orw = obs_raw(rs, h)
    if len(oc) < 3:
        return None
    tc = cluster_score_test(oc); tr = cluster_score_test(orw)
    w, lo, hi = wilson(tc["wins"], tc["n"])
    ret, alp = alpha(rs, h)
    line = (f"{indent}{name:24s} n={tr['n']:>4d} ncl={tr['nclust']:>3d} | WRcrudo {tr['wr']:>3.0f}%"
            f" base {tr['exp']:>3.0f}% lift {tr['lift']:>+5.1f} | nMOV={tc['n']:>4d}"
            f" WRdir {w:>3d}% [{lo:>2d},{hi:>3d}] base {tc['exp']:>3.0f}%"
            f" LIFTdir {tc['lift']:>+5.1f} z {tc['z_cl']:>+5.2f} p {tc['p_cl']:>6.3f}"
            f" | ret {ret:>+6.3f}% alpha {alp:>+6.3f}%")
    print(line)
    if register:
        ALLTESTS.append((name + f"@{h}m", tc))
    return tc


print("=== 0. REGIMEN DIARIO (SPY/QQQ 09:30->16:00) ===")
for d in sorted(regime):
    r = regime[d]
    print(f"  {d}  SPY {r['spy']:+.2f}%  QQQ {r['qqq']:+.2f}%  media {r['avg']:+.2f}%  {r['label']}")

print("\n=== 0b. COBERTURA ===")
print("  saltadas:", json.dumps(D["skip"], ensure_ascii=False))
byday = defaultdict(int)
for r in rows:
    byday[r["day"]] += 1
print("  evaluadas/dia:", dict(sorted(byday.items())))

fams = defaultdict(list)
for r in rows:
    fams[r["fam"]].append(r)

print("\n  familia -> dias activos:")
for fam, rs in sorted(fams.items(), key=lambda x: -len(x[1])):
    dd = sorted(set(r["day"] for r in rs))
    print(f"    {fam:24s} n={len(rs):>4d}  {len(dd)} dias: {' '.join(d[5:] for d in dd)}")

print("\n=== 1. WR POR FAMILIA ===")
for h in HOR:
    print(f"\n--- +{h}min ---")
    for fam, rs in sorted(fams.items(), key=lambda x: -len(x[1])):
        report(fam, rs, h, register=(h == 15 and len(rs) >= 20))

print("\n=== 2. ESTABILIDAD DIA A DIA (LIFTdir @15m) ===")
for fam, rs in sorted(fams.items(), key=lambda x: -len(x[1])):
    if len(rs) < 30:
        continue
    parts, pos, tot = [], 0, 0
    for d in days:
        sub = [r for r in rs if r["day"] == d]
        o = obs_cond(sub, 15)
        if len(o) < 5:
            continue
        t = cluster_score_test(o)
        parts.append(f"{d[5:]}:{t['wr']:>3.0f}/{t['exp']:>3.0f}(n{t['n']})")
        tot += 1; pos += 1 if t["lift"] > 0 else 0
    T = cluster_score_test(obs_cond(rs, 15))
    print(f"\n  {fam}  global nMOV={T['n']} WRdir {T['wr']:.0f}% base {T['exp']:.0f}% "
          f"lift {T['lift']:+.1f}pp · dias con lift>0: {pos}/{tot}")
    print("     " + "   ".join(parts) if parts else "     (ningun dia con n>=5)")

print("\n=== 3. GATES (solo 07-23 y 07-24: antes no existian) ===")
g = defaultdict(list)
for r in rows:
    if r["day"] >= "2026-07-23":
        g[r["gate"]].append(r)
for h in HOR:
    print(f"\n--- +{h}min ---")
    for k, rs in sorted(g.items(), key=lambda x: -len(x[1])):
        report(k, rs, h, register=(h == 15 and len(rs) >= 20))

print("\n=== 3b. BB_REBOTE apples-to-apples (mismo detector, mismo minuto) ===")
for h in HOR:
    parts = {}
    for k in ("SONO", "VETO_medido", "SONO_ESTRELLA"):
        rs = [r for r in rows if r["fam"] == "BB_REBOTE" and r["gate"] == k and r["day"] >= "2026-07-23"]
        o = obs_cond(rs, h)
        if o:
            parts[k] = cluster_score_test(o)
    s, v = parts.get("SONO"), parts.get("VETO_medido")
    line = f"  +{h:>2d}m  " + "  ".join(
        f"{k}: nMOV={t['n']} WRdir {t['wr']:.0f}% base {t['exp']:.0f}% lift {t['lift']:+.1f}"
        for k, t in parts.items())
    if s and v:
        p1, n1 = s["wins"] / s["n"], s["n"]; p2, n2 = v["wins"] / v["n"], v["n"]
        pp = (s["wins"] + v["wins"]) / (n1 + n2)
        se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
        z = (p2 - p1) / se if se > 0 else 0
        line += f"  | z(VETO-SONO)={z:+.2f} p={two_sided_p(z):.3f}"
    print(line)

print("\n=== 3c. MUTED p<55 vs SONO dentro de cada familia BB ===")
for fam in ("BB_REENTRADA_15m", "BB_BANDWALK"):
    for h in (15, 30, 60):
        parts = {}
        for k in ("SONO", "MUTED_p<55"):
            rs = [r for r in rows if r["fam"] == fam and r["gate"] == k and r["day"] >= "2026-07-23"]
            o = obs_cond(rs, h)
            if o:
                parts[k] = cluster_score_test(o)
        if len(parts) == 2:
            print(f"  {fam:18s} +{h:>2d}m: " + "  ".join(
                f"{k} nMOV={t['n']} WRdir {t['wr']:.0f}% base {t['exp']:.0f}% lift {t['lift']:+.1f}"
                for k, t in parts.items()))

print("\n=== 4. POR FUENTE ===")
srcs = defaultdict(list)
for r in rows:
    srcs[r["source"]].append(r)
for h in (5, 15, 30, 60):
    print(f"--- +{h}m ---")
    for s, rs in sorted(srcs.items(), key=lambda x: -len(x[1])):
        report(s, rs, h)

print("\n=== 5. GLOBAL + por direccion ===")
for h in HOR:
    report("TOTAL", rows, h, register=(h == 15))
    report("  LARGOS", [r for r in rows if r["dir"] > 0], h)
    report("  CORTOS", [r for r in rows if r["dir"] < 0], h)

print("\n=== 6. POR HORA ET (@15m) ===")
hh = defaultdict(list)
for r in rows:
    hh[r["hour"]].append(r)
for k in sorted(hh):
    if len(hh[k]) >= 20:
        report(f"{k:02d}:00", hh[k], 15, register=True)

print("\n=== 6b. hora x BB_REBOTE (control de composicion) ===")
for k in sorted(hh):
    sub = [r for r in hh[k] if r["fam"] == "BB_REBOTE"]
    if len(sub) >= 20:
        report(f"{k:02d}:00 BB_REBOTE", sub, 15)

print("\n=== 7. POR REGIMEN (@15m) ===")
for fam, rs in sorted(fams.items(), key=lambda x: -len(x[1])):
    if len(rs) < 40:
        continue
    parts = []
    for lab in ("ALCISTA", "LATERAL", "BAJISTA"):
        sub = [r for r in rs if regime.get(r["day"], {}).get("label") == lab]
        o = obs_cond(sub, 15)
        if len(o) < 10:
            parts.append(f"{lab[:3]} n={len(o)} —"); continue
        t = cluster_score_test(o)
        parts.append(f"{lab[:3]} n={t['n']} WRdir {t['wr']:.0f}% lift {t['lift']:+.1f}")
    print(f"  {fam:24s} " + " | ".join(parts))

print("\n=== 8. MULTIPLE TESTING (todas las hipotesis @15m, p cluster-robusto) ===")
pv = [t[1]["p_cl"] for t in ALLTESTS]
rej, thr = bh_fdr(pv, 0.05)
bon = 0.05 / len(pv)
order = sorted(range(len(pv)), key=lambda i: pv[i])
print(f"  m={len(pv)} hipotesis · Bonferroni alpha={bon:.5f} · BH(q=0.05) umbral p<={thr:.5f}")
print(f"  {'hipotesis':30s} {'nMOV':>5s} {'LIFTdir':>8s} {'p_cl':>9s} {'BH':>4s} {'Bonf':>5s}")
for i in order:
    name, t = ALLTESTS[i]
    print(f"  {name:30s} {t['n']:>5d} {t['lift']:>+7.1f} {t['p_cl']:>9.5f} "
          f"{'SI' if rej[i] else 'no':>4s} {'SI' if pv[i] < bon else 'no':>5s}")

print("\n=== 9. POR SIMBOLO (@15m, exploratorio, SIN correccion) ===")
sy = defaultdict(list)
for r in rows:
    sy[r["sym"]].append(r)
for s, rs in sorted(sy.items(), key=lambda x: -len(x[1])):
    if len(rs) >= 40:
        report(s, rs, 15)
