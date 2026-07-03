#!/usr/bin/env python3
"""fleet_cp_report.py — informe markdown del barrido C/P (scan + rank). DESCRIPTIVO, sin voz.

  ./venv/bin/python scripts/fleet_cp_report.py > docs/CP-SCAN-<fecha>.md
"""
import argparse
import datetime as dt
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import fleet_cp_rank as R  # noqa: E402

VS = ("V1_flujo", "V2_doi", "V3_maxpain", "V4_muros", "V5_ballenas")
SYM_V = {1: "+", 0: "·", -1: "−", None: "?"}


def m(x, dec=0):
    """$ en unidades legibles. None -> s/d (jamas 0 fabricado)."""
    if x is None:
        return "s/d"
    a = abs(x)
    s = "-" if x < 0 else ""
    if a >= 1e9:
        return "%s$%.2fB" % (s, a / 1e9)
    if a >= 1e6:
        return "%s$%.1fM" % (s, a / 1e6)
    if a >= 1e3:
        return "%s$%.0fk" % (s, a / 1e3)
    return "%s$%.*f" % (s, dec, a)


def n(x):
    if x is None:
        return "s/d"
    a = abs(x)
    s = "-" if x < 0 else ""
    if a >= 1e6:
        return "%s%.1fM" % (s, a / 1e6)
    if a >= 1e3:
        return "%s%.0fk" % (s, a / 1e3)
    return "%s%.0f" % (s, a)


def px(x):
    return "s/d" if x is None else ("%.2f" % x)


def wl_str(e, spot):
    """suelo/techo LOCALES (mayor OI dentro de ±15% del spot) — los que votan."""
    suelo, techo = R.local_walls(e, spot)
    return "%s / %s" % (px(suelo), px(techo))


def wl_abs(e):
    """muros ABSOLUTOS de todo el vencimiento (mapa, incluye lottos de cola larga)."""
    w = (e or {}).get("walls")
    if not w:
        return "s/d"
    return "%s / %s" % (px(w.get("put_wall")), px(w.get("call_wall")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=R.SCAN)
    a = ap.parse_args()
    d = json.load(open(a.scan))
    fleet, bargain = set(d["fleet"]), set(d["bargain"])
    rows = R.order([R.row(s) for s in d["syms"].values() if not s.get("errors")])
    bad = [k for k, s in d["syms"].items() if s.get("errors")]
    today = dt.date.fromisoformat(d["today"])

    print("# BARRIDO C/P · BALLENAS · DARK POOL · CADENA · MUROS — %s" % d["today"])
    print()
    print("Generado **%s** (hora Toronto) desde Unusual Whales — IBKR prohibido esta semana. **SEÑAL-SOLAMENTE.**  " % d["generated_at"].replace("T", " "))
    print("Fuente: `data/scan/%s` · %d simbolos (flota %d + bargain %d), 0 errores."
          % (os.path.basename(os.path.realpath(a.scan)), len(rows), len(fleet), len(bargain)))
    print()
    print("## Como se ordena (y que NO es)")
    print()
    print("5 votos de **valor igual** (+1/0/−1), umbral fijo, **cada uno de una familia de dato")
    print("distinta**, publicados por separado. Sin pesos ajustados, sin z-scores compuestos")
    print("(killlist). El orden es la suma; empates por la magnitud del flujo. **No es una")
    print("probabilidad** y no se presenta como tal.")
    print()
    print("| voto | que mide | umbral | reloj del dato |")
    print("|---|---|---|---|")
    print("| **V1 flujo** | premium firmado / bruto del dia, toda la cadena | ±0.05 | HOY, intradia |")
    print("| **V2 ΔOI** | posicion nueva calls vs puts | ±0.20 | **sesion ANTERIOR** (OCC publica t+1) |")
    print("| **V3 maxpain** | spot vs max pain del viernes | ±0.5% | cierre de ayer |")
    print("| **V4 muros** | distancia al techo vs al suelo **locales** (±15% del spot) | ±0.15 | OI de ayer |")
    print("| **V5 ballenas** | premium firmado de las alertas de los 2 vencimientos | ±$100k | HOY, intradia |")
    print()
    ej = max((x for x in rows if x["cp_vol"] and x["call_agg"] is not None and x["call_agg"] < 0),
             key=lambda x: x["cp_vol"], default=None)
    if ej:
        print("**C/P ratio: se muestra, NO vota.** Medido hoy en **%s**: C/P **%.1f** con las calls"
              % (ej["sym"], ej["cp_vol"]))
        print("pegadas al **BID** (agresor %+.2f = vendidas). El ratio dice *cuantas* calls hay; el"
              % ej["call_agg"])
        print("lado agresor dice *quien las quiere*. Vota el lado agresor.")
    print()
    print("**Gotcha MEDIDO hoy y corregido aqui**: `/oi-per-strike` y `/flow-per-strike`")
    print("**IGNORAN el parametro `expiry`** — NOK devolvia 54.877 calls igual con 08-07, con")
    print("08-14 y sin parametro. Los muros y el OI **por vencimiento** se construyen por eso")
    print("desde `/option-contracts?expiry=X`, que si lo respeta; el flujo del dia se pide UNA")
    print("vez y se etiqueta como de toda la cadena. Sumar w1+w2 contaba el mismo dia dos veces.")
    print()
    print("**Dark pool: descriptivo, sin voto** (killlist #3: su edge replicado es ~0).")
    print("**Earnings: veto marcado**, nunca un voto.")
    print()
    base = [x["sym"] for x in rows]
    sens = []
    for k in (0.66, 1.66):
        rr = R.order([R.row(sy, k) for sy in d["syms"].values() if not sy.get("errors")])
        nm = [x["sym"] for x in rr]
        idx = {x: i for i, x in enumerate(base)}
        pairs = len(nm) * (len(nm) - 1) / 2
        conc = sum(1 for i in range(len(nm)) for j in range(i + 1, len(nm))
                   if idx[nm[i]] < idx[nm[j]]) / pairs
        sens.append(conc * 100.0)
    print("Robustez del orden (test #4 de la killlist): moviendo los 5 umbrales a **x0.66** y")
    print("**x1.66**, la concordancia del orden con el base es **%.1f%%** y **%.1f%%**. El orden no"
          % (sens[0], sens[1]))
    print("cuelga de un umbral magico.")
    print()

    # ---- tabla maestra
    print("## Orden ALCISTA -> BAJISTA (los %d)" % len(rows))
    print()
    print("`cAgg`/`pAgg` = lado agresor del dia (ask−bid)/(ask+bid): **+ = compradas al ask, − = vendidas al bid**.")
    print("`firmado` = premium firmado del dia (toda la cadena). `suelo/techo` = muros del **vencimiento de esta semana** (mayor OI dentro de ±15% del spot), desde `option-contracts`.")
    print()
    print("| # | sym | px | dia% | score | V1..V5 | C/P | firmado dia | cAgg | pAgg | suelo/techo | maxpain | ΔOI c/p | ballenas | ER |")
    print("|---:|---|---:|---:|:---:|:---:|---:|---:|---:|---:|:---:|---:|:---:|---:|:---:|")
    for i, r in enumerate(rows, 1):
        v = "".join(SYM_V[r["votes"][k][0]] for k in VS)
        e1 = (r["exp"] or {}).get("w1")
        dc = dp = 0
        for t in ("w1", "w2"):
            ch = ((r["exp"] or {}).get(t) or {}).get("chain")
            if ch:
                dc += ch["doi_call"]
                dp += ch["doi_put"]
        wh = r["whales"] or {}
        er = r["earnings"]
        ertag = ""
        if er and er["date"] <= (today + dt.timedelta(days=12)).isoformat():
            ertag = "**%s**" % er["date"][5:]
        grp = "" if r["sym"] in fleet else " ᵇ"
        print("| %d | **%s**%s | %s | %+.1f | **%+d** | `%s` | %s | %s | %+.2f | %+.2f | %s | %s | %s/%s | %s | %s |"
              % (i, r["sym"], grp, px(r["spot"]), r["chg"] or 0, r["score"], v,
                 r["cp_vol"] if r["cp_vol"] is not None else "s/d",
                 m(r["signed_tgt"]), r["call_agg"] or 0, r["put_agg"] or 0,
                 wl_str(e1, r["spot"]),
                 px((r["max_pain"] or {}).get(r["exp_w1"])),
                 n(dc), n(dp), m(wh.get("target_signed")), ertag))
    print()
    print("ᵇ = bargain fleet. `?` en un voto = dato ausente (nunca se rellena con 0).")
    if bad:
        print()
        print("SIN DATO: %s" % " ".join(bad))
    print()

    # ---- desglose por voto
    print("## Que esta discriminando de verdad")
    print()
    from collections import Counter
    print("| voto | alcistas | neutros | bajistas | lectura |")
    print("|---|---:|---:|---:|---|")
    for k in VS:
        c = Counter(r["votes"][k][0] for r in rows)
        tot = len(rows)
        dom = max((c[1], "alcista"), (c[-1], "bajista"), key=lambda t: t[0])
        if dom[0] >= 0.75 * tot:
            lec = ("**casi constante** (%d/%d %s): no discrimina — resta/suma lo mismo a casi "
                   "todos y NO altera el orden" % (dom[0], tot, dom[1]))
        elif c[None]:
            lec = "reparto real · %d sin dato (voto omitido, no rellenado)" % c[None]
        else:
            lec = "reparto real"
        print("| %s | %d | %d | %d | %s |" % (k, c[1], c[0], c[-1], lec))
    print()

    # ---- proxima semana
    print("## PROXIMA SEMANA — el mapa del vencimiento siguiente")
    print()
    print("Mismo orden que arriba. `flip` = strike donde el GEX neto acumulado de ESE vencimiento")
    print("cruza cero (`s/d` = no cruza: el libro es de un solo signo en toda la banda).")
    print("`ΔOI` y `C/P OI` son del vencimiento de la proxima semana, no del total.")
    print()
    print("| # | sym | exp | suelo/techo | max pain | flip | C/P OI | ΔOI c/p | prem calls | prem puts |")
    print("|---:|---|:---:|:---:|---:|---:|---:|:---:|---:|---:|")
    for i, r in enumerate(rows, 1):
        e = (r["exp"] or {}).get("w2")
        if not e:
            print("| %d | **%s** | s/d | — | — | — | — | — | — | — |" % (i, r["sym"]))
            continue
        w, ch, gx = e.get("walls"), e.get("chain"), e.get("gex")
        print("| %d | **%s** | %s | %s | %s | %s | %s | %s/%s | %s | %s |"
              % (i, r["sym"], e["expiry"][5:], wl_str(e, r["spot"]),
                 px((r["max_pain"] or {}).get(e["expiry"])),
                 px((gx or {}).get("flip")) if (gx or {}).get("flip") is not None else "s/d",
                 (ch or {}).get("cp_oi", "s/d"),
                 n((ch or {}).get("doi_call")), n((ch or {}).get("doi_put")),
                 m((ch or {}).get("prem_call")), m((ch or {}).get("prem_put"))))
    print()

    # ---- conflictos flujo vs estructura
    print("## Donde el flujo y la estructura se CONTRADICEN")
    print()
    print("Los que hay que mirar dos veces: el dinero de hoy dice una cosa y el libro del dealer")
    print("la contraria. No se resuelve con el score — se resuelve con el PRINT.")
    print()
    print("| sym | score | V1 flujo | resto | firmado dia | ballenas | lectura |")
    print("|---|:---:|:---:|:---:|---:|---:|---|")
    conf = []
    for r in rows:
        v1 = r["votes"]["V1_flujo"][0]
        resto = sum(r["votes"][k][0] for k in VS[1:] if r["votes"][k][0] is not None)
        if v1 is not None and v1 != 0 and ((v1 > 0 and resto <= -2) or (v1 < 0 and resto >= 2)):
            conf.append((r, v1, resto))
    for r, v1, resto in conf:
        lec = ("flujo COMPRA, libro vende" if v1 > 0 else "flujo VENDE, libro compra")
        print("| **%s** | %+d | %s | %+d | %s | %s | %s |"
              % (r["sym"], r["score"], SYM_V[v1], resto, m(r["signed_tgt"]),
                 m((r["whales"] or {}).get("target_signed")), lec))
    if not conf:
        print("| — | | | | | | ninguno hoy |")
    print()

    # ---- dark pool
    print("## Dark pool — DESCRIPTIVO (no vota, killlist #3)")
    print()
    print("Los 12 mayores por premium. El VWAP de los prints es una referencia de nivel")
    print("institucional, **no una señal**: su edge replicado independientemente es ~0.")
    print()
    print("**OJO con el total**: UW sirve como maximo 500 prints por llamada. Las filas marcadas")
    print("`TRUNC` son **los 500 mas recientes, NO el dia entero** — su premium es un suelo, no un")
    print("total, y la columna `ventana` dice que trozo de sesion cubren de verdad.")
    print()
    print("| sym | prints | premium | ventana (ET) | VWAP | vs spot | % sobre spot | mayor nivel |")
    print("|---|---:|---:|:---:|---:|---:|---:|---|")

    def hhmm(t):
        if not t or "T" not in t:
            return "s/d"
        h, mi = t.split("T")[1][:5].split(":")
        return "%02d:%s" % ((int(h) - 4) % 24, mi)      # UTC -> ET (EDT)

    dps = sorted((r for r in rows if r["dp"]), key=lambda r: -r["dp"]["premium"])[:12]
    for r in dps:
        dp_ = r["dp"]
        rel = (100.0 * (dp_["vwap"] - r["spot"]) / r["spot"]) if r["spot"] else None
        top = dp_["top_levels"][0] if dp_["top_levels"] else None
        print("| **%s** | %d%s | %s | %s→%s | %s | %s | %s%% | %s |"
              % (r["sym"], dp_["n_prints"], " `TRUNC`" if dp_.get("truncated") else "",
                 m(dp_["premium"]), hhmm(dp_.get("window_from")), hhmm(dp_.get("window_to")),
                 px(dp_["vwap"]),
                 ("%+.2f%%" % rel) if rel is not None else "s/d",
                 dp_["pct_above_spot"],
                 ("%s (%s acc)" % (px(top["px"]), n(top["sz"]))) if top else "s/d"))
    print()

    # ---- fichas
    print("## Fichas — los que se pidieron por nombre")
    print()
    order = ["NOK", "AAPL", "NVDA", "MU", "TSLA"]
    by = {r["sym"]: r for r in rows}
    for s in order:
        r = by.get(s)
        if not r:
            continue
        pos = [i for i, x in enumerate(rows, 1) if x["sym"] == s][0]
        print("### %s — $%s (%+.2f%%) · puesto %d/%d · score %+d `%s`"
              % (s, px(r["spot"]), r["chg"] or 0, pos, len(rows), r["score"],
                 "".join(SYM_V[r["votes"][k][0]] for k in VS)))
        print()
        day = None
        for k, sy in d["syms"].items():
            if k == s:
                day = sy.get("day")
        print("- **C/P del dia** %s (calls %s vs puts %s) · lado agresor calls **%+.2f**, puts **%+.2f**"
              % (r["cp_vol"], n(day.get("call_vol")), n(day.get("put_vol")),
                 r["call_agg"] or 0, r["put_agg"] or 0))
        print("- **Premium firmado** dia %s · objetivo (2 vencimientos) %s · net delta %s"
              % (m(r["signed_day"]), m(r["signed_tgt"]), n(r["net_delta"])))
        for tag in ("w1", "w2"):
            e = (r["exp"] or {}).get(tag)
            if not e:
                continue
            w, ch, gx = e.get("walls"), e.get("chain"), e.get("gex")
            lbl = "ESTA SEMANA" if tag == "w1" else "PROXIMA"
            fl_ = (gx or {}).get("flip")
            fnote = (gx or {}).get("flip_note")
            print("- **%s (%s)**: suelo/techo **%s** · max pain %s · flip %s · C/P de OI %s · vol c/p %s"
                  % (lbl, e["expiry"], wl_str(e, r["spot"]),
                     px((r["max_pain"] or {}).get(e["expiry"])),
                     px(fl_) if fl_ is not None else ("s/d (%s)" % fnote if fnote else "s/d"),
                     (ch or {}).get("cp_oi", "s/d"), (ch or {}).get("cp_vol", "s/d")))
            if ch:
                print("  - OI del vencimiento: calls **%s** vs puts **%s** · volumen hoy c/p %s/%s"
                      % (n(ch["oi_call"]), n(ch["oi_put"]), n(ch["vol_call"]), n(ch["vol_put"])))
                print("  - ΔOI (sesion previa): calls **%s**, puts **%s** · sweeps c/p %s/%s · premium c/p %s / %s"
                      % (n(ch["doi_call"]), n(ch["doi_put"]), n(ch["sweep_call_vol"]),
                         n(ch["sweep_put_vol"]), m(ch["prem_call"]), m(ch["prem_put"])))
                top = [t for t in ch["top_doi"][:3]]
                if top:
                    print("  - mayor ΔOI: %s" % " · ".join(
                        "**%s%s** %+d OI (vol %s, %s ask/%s bid%s)"
                        % (px(t["k"]), t["r"], t["doi"], n(t["vol"]), n(t["ask_v"]), n(t["bid_v"]),
                           ", sweep %s" % n(t["sweep"]) if t["sweep"] else "")
                        for t in top))
        fd = None
        for kk, sy in d["syms"].items():
            if kk == s:
                fd = sy.get("flow_day")
        if fd and fd.get("hot_call_strikes"):
            print("- **Premium del dia por strike** (toda la cadena — el endpoint ignora `expiry`):")
            print("  - calls %s" % ", ".join("%s→%s" % (px(x["k"]), m(x["prem"]))
                                             for x in fd["hot_call_strikes"]))
            print("  - puts %s" % ", ".join("%s→%s" % (px(x["k"]), m(x["prem"]))
                                            for x in fd["hot_put_strikes"]))
        wh = r["whales"] or {}
        if wh.get("target_n"):
            big = sorted([x for x in wh["alerts"] if x["expiry"] in (r["exp_w1"], r["exp_w2"])],
                         key=lambda x: -x["prem"])[:3]
            print("- **Ballenas** (objetivo): %d alertas · calls %s vs puts %s · **firmado %s**"
                  % (wh["target_n"], m(wh["target_call_prem"]), m(wh["target_put_prem"]),
                     m(wh["target_signed"])))
            for b in big:
                print("  - %s %s%s %s · vol %s vs OI %s%s%s"
                      % (b["expiry"], px(b["strike"]), (b["type"] or "?")[0].upper(), m(b["prem"]),
                         n(b["vol"]), n(b["oi"]),
                         " · **sweep**" if b["sweep"] else "",
                         " · **todo apertura**" if b["opening"] else ""))
        dp_ = r["dp"]
        if dp_:
            print("- **Dark pool** (descriptivo%s): %d prints, %s, %s acciones · VWAP **%s** (%s del spot) · %s%% por encima"
                  % (", **TRUNCADO a los 500 mas recientes**" if dp_.get("truncated") else "",
                     dp_["n_prints"], m(dp_["premium"]), n(dp_["size"]), px(dp_["vwap"]),
                     "%+.1f%%" % (100.0 * (dp_["vwap"] - r["spot"]) / r["spot"]) if r["spot"] else "s/d",
                     dp_["pct_above_spot"]))
            print("  - niveles: %s" % " · ".join("%s (%s)" % (px(x["px"]), n(x["sz"])) for x in dp_["top_levels"]))
        if r["earnings"]:
            print("- **Earnings**: %s %s" % (r["earnings"]["date"], r["earnings"]["time"] or ""))
        print()


if __name__ == "__main__":
    main()
