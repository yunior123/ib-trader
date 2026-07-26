#!/usr/bin/env python3
"""Ledger de decaimiento de muros: la curva REAL de aguante por numero de toque.

La casa opera con "1er toque rebota ~70%, 3+ = exhausto" y compass.cpp veta con
TOUCH_EXHAUST=3. Eso nunca se midio. Esto lo mide o dice que no se puede.
"""
import json, os, sqlite3, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "trades.db")
OUT = os.path.join(ROOT, "data", "wall_decay.json")

RHO_FLOTA = 0.41        # medida, docs/NULL-CONTROL-2026-07-25.md; no es un prior
Z = 1.96
N_EFF_MIN = 30          # por debajo de esto la celda no publica numero
DOCTRINA_TOQUE1 = 0.70
DOCTRINA_EXHAUST = 3

AGUANTA = ("BOUNCE", "RETEST_REJECT")   # resolucion a favor del nivel
FALLA = ("BREAK",)
AMBIGUO = ("WICK_REJECT",)              # una mecha no es un rebote: se cuenta aparte


def wilson(k, n, z=Z):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - m), min(1.0, c + m))


def n_effective(n, n_clusters):
    """Kish: n/(1+(m-1)rho). Los eventos de un mismo sym-sesion no son independientes."""
    if not n or not n_clusters:
        return None
    m = n / n_clusters
    return n / (1.0 + (m - 1.0) * RHO_FLOTA)


def rows(con, printed_only=True):
    q = ("select sym, date(ts,'unixepoch','localtime') d, level_type, regime, touch_ord, event, "
         "printed, tradeable from level_events where event in (?,?,?,?)")
    args = list(AGUANTA + FALLA + AMBIGUO)
    if printed_only:
        q += " and printed=1"
    return con.execute(q, args).fetchall()


def bucket(t):
    t = int(t)
    return "1" if t <= 1 else ("2" if t == 2 else ("3" if t == 3 else "4+"))


def tally(rs, keyfn):
    acc = {}
    for r in rs:
        k = keyfn(r)
        if k is None:
            continue
        a = acc.setdefault(k, {"aguanta": 0, "falla": 0, "mecha": 0, "clusters": set()})
        ev = r[5]
        if ev in AGUANTA:
            a["aguanta"] += 1
        elif ev in FALLA:
            a["falla"] += 1
        else:
            a["mecha"] += 1
        a["clusters"].add((r[0], r[1]))
    return acc


def cell(a):
    k, n = a["aguanta"], a["aguanta"] + a["falla"]
    ne = n_effective(n, len(a["clusters"]))
    lo, hi = wilson(k, n)
    lo_e, hi_e = wilson(round(k * (ne / n)) if (ne and n) else 0, round(ne) if ne else 0)
    suf = bool(ne and ne >= N_EFF_MIN)
    return {
        "aguanta": k, "falla": a["falla"], "mecha_ambigua": a["mecha"],
        "n": n, "n_clusters": len(a["clusters"]),
        "n_eff": None if ne is None else round(ne, 1),
        "pct_aguanta": None if not suf else round(100.0 * k / n, 1),
        "wilson_nominal": None if lo is None else [round(lo, 3), round(hi, 3)],
        "wilson_efectivo": None if (lo_e is None or not suf) else [round(lo_e, 3), round(hi_e, 3)],
        "suficiente": suf,
        "motivo": None if suf else f"n_eff {'' if ne is None else round(ne,1)} < {N_EFF_MIN}",
    }


def build(printed_only=True):
    if not os.path.exists(DB):
        raise FileNotFoundError(DB)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rs = rows(con, printed_only)
        span = con.execute("select count(distinct date(ts,'unixepoch','localtime')),"
                           " count(distinct sym), min(date(ts,'unixepoch','localtime')),"
                           " max(date(ts,'unixepoch','localtime')) from level_events").fetchone()
    finally:
        con.close()
    if not rs:
        raise RuntimeError("level_events no tiene eventos de resolucion con printed=1")

    por_toque = {k: cell(v) for k, v in tally(rs, lambda r: bucket(r[4])).items()}
    por_toque_reg = {f"{bucket(r[4])}|{r[3]}": None for r in rs if r[3]}
    por_toque_reg = {k: cell(v) for k, v in
                     tally([r for r in rs if r[3]], lambda r: f"{bucket(r[4])}|{r[3]}").items()}
    por_tipo = {k: cell(v) for k, v in
                tally(rs, lambda r: f"{bucket(r[4])}|{r[2]}").items()}

    t1 = por_toque.get("1")
    sop = None
    if t1 and t1["suficiente"] and t1["wilson_efectivo"]:
        lo, hi = t1["wilson_efectivo"]
        sop = ("CONFIRMA" if lo <= DOCTRINA_TOQUE1 <= hi else
               ("REFUTA_POR_ALTO" if lo > DOCTRINA_TOQUE1 else "REFUTA_POR_BAJO"))

    ordenados = [k for k in ("1", "2", "3", "4+") if k in por_toque and por_toque[k]["suficiente"]]
    decae = None
    if len(ordenados) >= 2:
        ps = [por_toque[k]["pct_aguanta"] for k in ordenados]
        decae = all(ps[i] >= ps[i + 1] for i in range(len(ps) - 1))

    exhaust = None
    if decae:
        for k in ordenados:
            c = por_toque[k]
            if c["wilson_efectivo"] and c["wilson_efectivo"][1] < 0.5:
                exhaust = int(k.rstrip("+"))
                break

    return {
        "generado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base": "printed=1" if printed_only else "todos los eventos",
        "definiciones": {
            "aguanta": list(AGUANTA), "falla": list(FALLA),
            "ambiguo_no_cuenta": list(AMBIGUO),
            "nota": "WICK_REJECT NO cuenta como aguante: una mecha no es un rebote.",
        },
        "muestra": {"sesiones": span[0], "syms": span[1], "desde": span[2], "hasta": span[3],
                    "eventos_resolutorios": len(rs), "rho_flota": RHO_FLOTA,
                    "n_eff_min": N_EFF_MIN},
        "por_toque": por_toque,
        "por_toque_y_regimen": por_toque_reg,
        "por_toque_y_tipo": por_tipo,
        "doctrina": {
            "afirma_toque1": DOCTRINA_TOQUE1,
            "afirma_touch_exhaust": DOCTRINA_EXHAUST,
            "soporte_toque1": sop,
            "la_curva_decae": decae,
            "touch_exhaust_medido": exhaust,
            "veredicto": (
                "DATOS INSUFICIENTES: ninguna celda alcanza n_eff minimo, no se afirma ni se niega "
                "la doctrina" if not ordenados else
                ("la curva NO decae con el numero de toque: la doctrina no tiene soporte en esta "
                 "muestra" if decae is False else
                 "la curva decae; TOUCH_EXHAUST medido en el campo touch_exhaust_medido")),
        },
    }


def main():
    d = build(printed_only="--todos" not in sys.argv)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, OUT)
    m = d["muestra"]
    print(f"{OUT}: {m['eventos_resolutorios']} eventos, {m['sesiones']} sesiones, "
          f"{m['syms']} syms ({m['desde']}..{m['hasta']})")
    for k in ("1", "2", "3", "4+"):
        c = d["por_toque"].get(k)
        if not c:
            continue
        pct = "—" if c["pct_aguanta"] is None else f"{c['pct_aguanta']:.1f}%"
        print(f"  toque {k:<2} aguanta {c['aguanta']:>4} falla {c['falla']:>4} "
              f"mecha {c['mecha_ambigua']:>4} | n {c['n']:>4} n_eff {c['n_eff']} -> {pct} "
              f"{'' if c['suficiente'] else '[INSUFICIENTE]'}")
    print("  doctrina:", d["doctrina"]["veredicto"])


if __name__ == "__main__":
    main()
