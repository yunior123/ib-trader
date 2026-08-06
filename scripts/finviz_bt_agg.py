#!/usr/bin/env python3
"""Agregador multi-sesion sobre backtest_finviz (misma metodologia, solo pooling por fecha)."""
import datetime as dt
import os
import sys

sys.path.insert(0, "/Users/yuniorrodriguezosorio/ib-trader/scripts")
import backtest_finviz as bt

REPO = "/Users/yuniorrodriguezosorio/ib-trader"
DATES = sys.argv[1:] or ["2026-08-03", "2026-08-04", "2026-08-05"]
Q = 0.10


def pool(per_date, key=lambda e: True):
    """Suma k/n por fecha y n_eff por fecha (independencia entre sesiones)."""
    k = n = 0
    ne = 0.0
    na = 0
    clusters = 0
    for d, P in per_date.items():
        items = [e for e in P["labeled"] if key(e)]
        na += len(items)
        kd, nd = bt.rate(items)
        k += kd
        n += nd
        cd = len({e["ticker"] for e in items if e["label"] is not None})
        clusters += cd
        if nd > 0:
            ne += bt.n_effective(nd, cd, P["rho"], cd)
    return k, n, ne, na, clusters


def main():
    per_date = {}
    for d in DATES:
        labeled, excluded = bt.label_events(d)
        evs = [e for e in bt.load_events() if e["date"] == d]
        rho = bt.measured_rho(d, sorted({e["ticker"] for e in evs}))
        if rho is None:
            raise bt.DataMissing(f"rho no medible en {d}")
        nulls = bt.null_sample(d, labeled)
        per_date[d] = {"labeled": labeled, "excluded": excluded, "evs": evs,
                       "rho": rho, "nulls": nulls}

    all_nulls = [x for P in per_date.values() for x in P["nulls"]]
    nk, nn = bt.rate(all_nulls)
    null_p = nk / nn
    null_by_screen = {}
    for s in ("buffett", "squeeze", "momentum"):
        sk, sn = bt.rate([x for x in all_nulls if x["screen"] == s])
        null_by_screen[s] = (sk, sn, sk / sn if sn else None)

    groups = {}
    for P in per_date.values():
        for e in P["labeled"]:
            for dim, val in bt.cuts_for(e):
                groups.setdefault((dim, val), []).append(None)
    keys = sorted(groups) + [("TODO", "todas las alertas")]
    rows, pvals = [], []
    for dim, val in keys:
        if dim == "TODO":
            key = (lambda e: True)
        else:
            key = (lambda e, dim=dim, val=val: (dim, val) in bt.cuts_for(e))
        k, n, ne, na, cl = pool(per_date, key)
        if n == 0:
            rows.append((dim, val, na, n, None, None, None, ne, cl, None))
            pvals.append(1.0)
            continue
        lo, hi = bt.wilson_eff(k, n, ne)
        p = bt.binom_tail_p(k, n, null_p)
        rows.append((dim, val, na, n, k, lo, hi, ne, cl, p))
        pvals.append(p)
    passes = bt.bh_fdr(pvals, Q)

    # sensibilidad k_tp=k_sl pooled
    sens = []
    for kk in (0.5, 0.75, 1.0, 1.5):
        pd_k = {}
        for d in DATES:
            lab, _ = bt.label_events(d, kk, kk)
            pd_k[d] = {"labeled": lab, "rho": per_date[d]["rho"]}
        nl = []
        for d in DATES:
            nl += bt.null_sample(d, pd_k[d]["labeled"], kk, kk)
        nkk, nnn = bt.rate(nl)
        npk = nkk / nnn if nnn else None
        for s in ("buffett", "squeeze", "momentum", "TODOS"):
            key = (lambda e: True) if s == "TODOS" else (lambda e, s=s: e["screen"] == s)
            k, n, ne, na, cl = pool(pd_k, key)
            sens.append((kk, s, n, (k / n if n else None), npk))

    exr = {}
    tot_ex = 0
    for P in per_date.values():
        for e in P["excluded"]:
            exr[e["reason"]] = exr.get(e["reason"], 0) + 1
            tot_ex += 1

    ev06 = [e for e in bt.load_events() if e["date"] == "2026-08-06"]

    out = {
        "per_date": {d: {"rho": P["rho"],
                         "n_events": len(P["evs"]),
                         "labeled": len(P["labeled"]),
                         "rate": bt.rate(P["labeled"]),
                         "null": bt.rate(P["nulls"])}
                     for d, P in per_date.items()},
        "null_p": null_p, "null_n": nn, "null_by_screen": null_by_screen,
        "rows": rows, "passes": passes, "pvals": pvals,
        "sens": sens, "exclusions": exr, "tot_ex": tot_ex,
        "n_ev06": len(ev06),
    }
    md_out = os.environ.get("MD_OUT")
    if md_out:
        bt.atomic_write(md_out, build_md(out, per_date))
        print(f"escrito {md_out}", file=sys.stderr)
    import json
    print(json.dumps(out, default=str, indent=1))


# resumen del informe del 2026-08-04 (docs/BACKTEST-ALERTAS-FINVIZ-2026-08-04.md), para comparar
OLD = {"TODO": (61, 141, 0.517, "UNPROVEN"),
       "buffett": (31, 75, 0.517, "DATA-INSUFICIENTE"),
       "momentum": (23, 49, 0.517, "DATA-INSUFICIENTE"),
       "squeeze": (7, 17, 0.517, "DATA-INSUFICIENTE")}


def casa_verdict(k, n, ne, null_p, fdr_ok):
    if n <= 0 or ne < 30:
        return "DATA-INSUFICIENTE"
    lo, hi = bt.wilson_eff(k, n, ne)
    if lo > null_p and fdr_ok:
        return "MEDIDO-CON-EDGE"
    if hi < null_p:
        return "MEDIDO-SIN-EDGE (KILL: Wilson entero bajo el null)"
    return "MEDIDO-SIN-EDGE (UNPROVEN: no bate al azar)"


def build_md(out, per_date):
    L = []
    dates = sorted(per_date)
    span = f"{dates[0]} → {dates[-1]}"
    null_p = out["null_p"]
    L.append(f"# Backtest honesto — alertas FINVIZ (screeners) · {len(dates)} sesiones {span}")
    L.append("")
    L.append(f"Generado {dt.datetime.now():%Y-%m-%d %H:%M} por `scripts/backtest_finviz.py` "
             "(fetch por sesion) + agregador multi-sesion (pooling por fecha; misma metodologia "
             "y funciones del script — triple barrera 1.0·ATR14(1m), timeout=NULL, Wilson sobre "
             "n_eff, null emparejado, BH-FDR q=0.10). SEÑAL-SOLAMENTE.")
    L.append("Agregacion: k y n se SUMAN entre sesiones; n_eff se calcula POR SESION con el rho "
             "medido de esa sesion y se suma (sesiones independientes). El null se agrupa igual.")
    L.append("")
    L.append("## Por sesion")
    L.append("")
    L.append("| sesion | alertas | etiquetables | hit | null del dia | rho medido |")
    L.append("|---|---|---|---|---|---|")
    for d in dates:
        P = out["per_date"][d]
        k, n = P["rate"]
        nk_, nn_ = P["null"]
        L.append(f"| {d} | {P['n_events']} | {n} | {k}/{n} = {k/n:.1%} | "
                 f"{nk_/nn_:.1%} (n={nn_}) | {P['rho']:.3f} |")
    L.append("")
    L.append(f"Null agrupado (mismo minuto, misma duracion, misma direccion, ticker al azar del "
             f"universo liquido de cada dia): **{null_p:.1%}** sobre n={out['null_n']}.")
    L.append("")
    L.append("## Por screener (agregado 3 sesiones)")
    L.append("")
    L.append("| screener | decididas | hit | Wilson(n_eff) | n_eff | null emparejado del screener "
             "| p (vs null global) | BH-FDR | veredicto |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    idx = {(r[0], r[1]): i for i, r in enumerate(out["rows"])}
    for s in ("buffett", "squeeze", "momentum"):
        i = idx[("screener", s)]
        dim, val, na, n, k, lo, hi, ne, cl, p = out["rows"][i]
        sk, sn, sp = out["null_by_screen"][s]
        v = casa_verdict(k, n, ne, null_p, out["passes"][i])
        L.append(f"| {s} | {n} | {k}/{n} = {k/n:.1%} | [{lo:.1%}, {hi:.1%}] | {ne:.1f} | "
                 f"{sp:.1%} (n={sn}) | {p:.3f} | {'si' if out['passes'][i] else 'no'} | {v} |")
    i = idx[("TODO", "todas las alertas")]
    dim, val, na, n, k, lo, hi, ne, cl, p = out["rows"][i]
    v = casa_verdict(k, n, ne, null_p, out["passes"][i])
    L.append(f"| **TODOS** | {n} | {k}/{n} = {k/n:.1%} | [{lo:.1%}, {hi:.1%}] | {ne:.1f} | "
             f"{null_p:.1%} | {p:.3f} | {'si' if out['passes'][i] else 'no'} | {v} |")
    L.append("")
    L.append("## Todos los cortes (agregado)")
    L.append("")
    L.append("| corte | valor | alertas | decididas | hit | Wilson(n_eff) | n_eff | p | BH-FDR | "
             "veredicto |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r, ok in zip(out["rows"], out["passes"]):
        dim, val, na, n, k, lo, hi, ne, cl, p = r
        if n == 0:
            L.append(f"| {dim} | {val} | {na} | 0 | — | — | — | — | — | DATA-INSUFICIENTE |")
            continue
        v = casa_verdict(k, n, ne, null_p, ok)
        L.append(f"| {dim} | {val} | {na} | {n} | {k/n:.1%} | [{lo:.1%}, {hi:.1%}] | {ne:.1f} | "
                 f"{p:.3f} | {'si' if ok else 'no'} | {v} |")
    L.append("")
    L.append("## Curva de sensibilidad (agregada; si el efecto vive en UN umbral, no es real)")
    L.append("")
    L.append("| k_tp = k_sl (·ATR14 1m) | screener | decididas | hit | null | delta |")
    L.append("|---|---|---|---|---|---|")
    for kk, s, n, hit, npk in out["sens"]:
        if n == 0 or hit is None or npk is None:
            L.append(f"| {kk:.2f} | {s} | 0 | — | — | — |")
            continue
        L.append(f"| {kk:.2f} | {s} | {n} | {hit:.1%} | {npk:.1%} | {(hit-npk)*100:+.1f} pp |")
    L.append("")
    L.append("## Exclusiones (3 sesiones)")
    L.append("")
    L.append("| razon | n |")
    L.append("|---|---|")
    for r_, c in sorted(out["exclusions"].items(), key=lambda x: -x[1]):
        L.append(f"| {r_} | {c} |")
    L.append("")
    L.append("## Comparacion con el informe del 2026-08-04 (1 sesion)")
    L.append("")
    L.append("| corte | 08-04 (1 sesion) | hoy (3 sesiones) | veredicto antes -> ahora |")
    L.append("|---|---|---|---|")
    for s, (ok_, on_, onull, over) in OLD.items():
        key = ("TODO", "todas las alertas") if s == "TODO" else ("screener", s)
        i = idx[key]
        _, _, _, n, k, lo, hi, ne, cl, p = out["rows"][i]
        v = casa_verdict(k, n, ne, null_p, out["passes"][i])
        L.append(f"| {s} | {ok_}/{on_} = {ok_/on_:.1%} vs null {onull:.1%} | "
                 f"{k}/{n} = {k/n:.1%} vs null {null_p:.1%} | {over} -> {v} |")
    L.append("")
    if out["n_ev06"]:
        L.append(f"Nota: {out['n_ev06']} eventos del 2026-08-06 (premarket de hoy) quedan FUERA: "
                 "Polygon (plan delayed) no sirve la sesion en curso. Se etiquetaran cuando "
                 "cierre el dia.")
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
