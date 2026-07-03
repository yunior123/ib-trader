#!/usr/bin/env python3
"""mag7_view.py — tracking del grupo MAG7 (fuente unica data/mag7.txt).

Amplitud del grupo al estilo fleet_consensus: voto por simbolo = lado del flip
(estructural, chart_levels) confirmado por momentum 5m; sin flip degrada a
momentum-solo (etiquetado). Score ponderado por peso NDX (patron index_breadth).
Escribe data/mag7_view.json atomico. SEÑAL-SOLAMENTE, aditivo: nadie lo requiere.

Uso: ./venv/bin/python scripts/mag7_view.py [--json] [--daemon]
"""
import json, os, sys, time, statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
import chart_levels

MAG7 = open(os.path.join(REPO, "data", "mag7.txt")).read().split()
# Pesos NDX aprox (publicos, cambian lento) — patron index_breadth.WEIGHTS.
WEIGHTS = {"NVDA": 9.0, "MSFT": 8.0, "AAPL": 7.5, "AMZN": 5.5,
           "META": 4.5, "GOOGL": 5.0, "TSLA": 3.0}
MAX_BAR_AGE = float(os.environ.get("MAG7_MAX_BAR_AGE", "180"))
MIN_COVER = float(os.environ.get("MAG7_MIN_COVER", "0.71"))   # 5 de 7
OUT = os.path.join(REPO, "data", "mag7_view.json")


def _pb(c, n=20):
    # None cuando no hay muestra: jamas un 0.5 fabricado (regla de la casa).
    if len(c) < n:
        return None
    w = c[-n:]; m = st.mean(w); sd = st.pstdev(w); up = m + 2 * sd; lo = m - 2 * sd
    return (c[-1] - lo) / (up - lo) if up > lo else None


def member_view(sym, now):
    """Devuelve dict del miembro o levanta; el caller registra el motivo en skipped."""
    p = os.path.join(REPO, "data", f"bars_{sym.lower()}_ibkr.txt")
    age = now - os.path.getmtime(p)
    if age > MAX_BAR_AGE:
        raise RuntimeError(f"barras rancias ({age/60:.0f}min)")
    c = [float(l.split()[4]) for l in open(p) if l.strip()]
    if len(c) < 7:
        raise RuntimeError("menos de 7 barras")
    spot = c[-1]
    mom = 100 * (c[-1] - c[-6]) / c[-6]
    flip = None
    try:
        lv = chart_levels.gen(sym, spot=spot, write=False)
        flip = lv.get("flip") if lv else None
    except Exception:
        flip = None   # sin mapa GEX: degrada a momentum-solo, etiquetado abajo
    if flip is not None:
        side = 1 if spot >= flip else -1
        basis = "flip"
    elif abs(mom) > 0.03:
        side = 1 if mom > 0 else -1
        basis = "mom"
    else:
        side = 0
        basis = "plano"
    return dict(spot=round(spot, 2), mom=round(mom, 3), flip=flip, side=side,
                basis=basis, pb=(lambda v: round(v, 2) if v is not None else None)(_pb(c)))


def snapshot():
    now = time.time()
    members = {}; skipped = {}
    for s in MAG7:
        try:
            members[s] = member_view(s, now)
        except Exception as e:
            skipped[s] = f"{type(e).__name__}: {e}"
    up = sum(1 for m in members.values() if m["side"] > 0)
    dn = sum(1 for m in members.values() if m["side"] < 0)
    n = len(members)
    wt = sum(WEIGHTS[s] for s in members)
    score = round(sum(WEIGHTS[s] * m["side"] for s, m in members.items()) / wt, 3) if wt else None
    need = int(len(MAG7) * MIN_COVER) + 1
    if n < need:
        verdict = None
        why = f"cobertura insuficiente {n}/{len(MAG7)} (min {need}) — esto es FEED, no direccion"
    elif score is not None and score >= 0.5 and up >= 5:
        verdict = "UP"; why = f"{up}/{len(MAG7)} arriba, score ponderado {score:+.2f}"
    elif score is not None and score <= -0.5 and dn >= 5:
        verdict = "DN"; why = f"{dn}/{len(MAG7)} abajo, score ponderado {score:+.2f}"
    else:
        verdict = "MIXTO"; why = f"{up}↑/{dn}↓ de {len(MAG7)}, score {score:+.2f}" if score is not None else "sin datos"
    return dict(ts=int(now), group="MAG7", up=up, dn=dn, n=n, total=len(MAG7),
                score=score, verdict=verdict, why=why, members=members, skipped=skipped)


def write_atomic(snap):
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snap, f, indent=1)
    os.replace(tmp, OUT)


def report(snap):
    v = snap["verdict"] or "SIN VEREDICTO"
    print(f"[mag7] {time.strftime('%H:%M:%S', time.localtime(snap['ts']))} "
          f"{v}: {snap['why']} (n={snap['n']}/{snap['total']})")
    for s, m in sorted(snap["members"].items(), key=lambda x: -WEIGHTS[x[0]]):
        arrow = "↑" if m["side"] > 0 else "↓" if m["side"] < 0 else "·"
        fl = f"{m['flip']:.2f}" if m["flip"] is not None else "s/flip"
        pb = f"{m['pb']:.2f}" if m["pb"] is not None else " s/d"
        print(f"  {s:5} w{WEIGHTS[s]:>4} {arrow} spot {m['spot']:>8.2f} flip {fl:>8} "
              f"mom {m['mom']:+.2f}% %B {pb} [{m['basis']}]")
    for s, r in snap["skipped"].items():
        print(f"  {s:5} SIN VOTO: {r}")


def main():
    daemon = "--daemon" in sys.argv
    while True:
        snap = snapshot()
        write_atomic(snap)
        if "--json" in sys.argv:
            print(json.dumps(snap, indent=1))
        else:
            report(snap)
        if not daemon:
            break
        time.sleep(60)


if __name__ == "__main__":
    main()
