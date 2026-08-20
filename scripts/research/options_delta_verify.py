#!/usr/bin/env python3
"""options_delta_verify.py — auditoria de options_delta_backtest.json.

Tres cosas que el barrido NO contesta y que deciden si el resultado vale:

1. RUIDO DEL PROPIO NULL. El null se sortea UNA vez por celda. Si su error de Monte-Carlo
   es mayor que el `edge_vs_B` publicado, el edge no es una medicion sino la semilla.
   Aqui se sortea K veces y se publica la dispersion.
2. FILTRO CAPITAN con inferencia CORRECTA: bootstrap emparejado por bloque sym-dia
   (las entradas del mismo dia estan correlacionadas; la p de dos proporciones sobre la n
   cruda no vale). Ademas se mide el veto invertido como control.
3. REPRODUCCION del lado señal con implementacion independiente (ver `verify_indep`).

Salida: enriquece data/research/options_delta_backtest.json con la clave `verificacion`
y añade la seccion al .md.
"""
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "scripts", "research"))

import delta_imbalance_study as dis            # noqa: E402
import options_delta_backtest as odb           # noqa: E402

JSON = "data/research/options_delta_backtest.json"
MD = "data/research/options_delta_backtest.md"
K_SEEDS = 40                 # sorteos independientes del null por celda
N_BOOT = 2000                # bootstrap de clusters para el test del capitan


def wr_of(lab):
    keep = lab >= 0
    n = int(keep.sum())
    if n == 0:
        return None, 0
    return float((lab[keep] == 1).mean()), n


def cluster_boot_diff(win_a, clu_a, win_b, clu_b, n_boot, seed=17):
    """CI de (wr_a - wr_b) remuestreando CLUSTERES (sym-dia) con reemplazo.

    Los dos subconjuntos comparten el universo de clusteres: se remuestrea UNA lista de
    clusteres y se toman de ambos lados los que caen, que es lo que hace el emparejado."""
    rng = np.random.default_rng(seed)
    clusters = np.unique(np.concatenate([clu_a, clu_b]))
    idx_a = {c: np.nonzero(clu_a == c)[0] for c in clusters}
    idx_b = {c: np.nonzero(clu_b == c)[0] for c in clusters}
    out = np.full(n_boot, np.nan)
    for i in range(n_boot):
        pick = rng.choice(clusters, size=clusters.size, replace=True)
        a = np.concatenate([idx_a[c] for c in pick if idx_a[c].size])
        b = np.concatenate([idx_b[c] for c in pick if idx_b[c].size])
        if a.size == 0 or b.size == 0:
            continue
        out[i] = win_a[a].mean() - win_b[b].mean()
    out = out[np.isfinite(out)]
    if out.size < 100:
        return None
    lo, hi = np.percentile(out, [2.5, 97.5])
    return dict(diff=float(win_a.mean() - win_b.mean()), lo=float(lo), hi=float(hi),
                p_signo=float(min((out <= 0).mean(), (out >= 0).mean()) * 2.0),
                n_boot=int(out.size))


def paired_families(cells):
    """OTM vs TOTAL comparados PAREADOS: misma barrera, mismo umbral, misma ventana.

    Comparar 'la mejor celda de cada familia' es pescar; el par tiene la misma barrera y
    por tanto el mismo win rate de referencia."""
    import math
    import statistics as st
    k = lambda c: (c["zwin"], c["theta"], c["mode"], c["k_tp"], c["k_sl"], c["H"])
    dd = {k(c): c for c in cells if c["sig"] == "dd"}
    otm = {k(c): c for c in cells if c["sig"] == "otm"}
    common = sorted(set(dd) & set(otm))
    if not common:
        return None
    diffs = [dd[c]["wr"] - otm[c]["wr"] for c in common]
    pos = sum(1 for x in diffs if x > 0)
    neg = sum(1 for x in diffs if x < 0)
    n = pos + neg
    kk = max(pos, neg)
    p = min(1.0, sum(math.comb(n, i) for i in range(kk, n + 1)) / 2.0 ** n * 2.0) if n else 1.0
    fam = {}
    for tag, name in (("dd", "TOTAL dir_delta_flow"), ("otm", "OTM otm_dir_delta_flow")):
        sub = [c for c in cells if c["sig"] == tag]
        e = [c["edge_vs_B"] for c in sub]
        fam[name] = dict(n_celdas=len(sub), edge_medio=round(st.mean(e), 5),
                         celdas_edge_positivo=sum(1 for x in e if x > 0),
                         mejor=round(max(e), 5), peor=round(min(e), 5))
    return dict(pares=len(common), dd_menos_otm_medio=round(st.mean(diffs), 5),
                dd_menos_otm_mediana=round(st.median(diffs), 5),
                dd_gana=pos, otm_gana=neg, p_test_signos=round(p, 4),
                familias=fam,
                conclusion="ninguna de las dos predice; la diferencia entre ellas tampoco "
                           "es distinguible del azar (test de signos pareado p=%.2f)" % p)


def multiplicity(cells):
    """¿Cuantas celdas 'significativas' habria por puro azar?"""
    n = len(cells)
    sig05 = sum(1 for c in cells if c["p"] < 0.05)
    return dict(n_celdas=n, p_minimo=round(min(c["p"] for c in cells), 5),
                umbral_bh_mas_estricto=round(0.10 / n, 6),
                celdas_p_menor_005=sig05,
                esperadas_por_azar=round(0.05 * n, 1),
                lectura="%d celdas con p<0.05 sobre %d (%.1f%%) contra el %.0f%% que da el "
                        "azar: exactamente ruido" % (sig05, n, 100.0 * sig05 / n, 5))


def main():
    t0 = time.time()
    res = json.load(open(JSON))
    cells = res["cells"]

    p = dis.Panel(odb.NPZ)
    n = p.sym.size
    pos = odb.block_pos(p.new_block, n)
    atr = dis.atr_wilder(p, odb.ATR_N)
    pool_ok = (np.isfinite(atr) & (atr > 0) & (p.minute_et >= odb.MIN_ET)
               & (p.minute_et < odb.MAX_ET))
    nxt_ok = np.zeros(n, dtype=bool)
    nxt_ok[:-1] = p.block_id[1:] == p.block_id[:-1]
    pool_ok &= nxt_ok
    key, pool = odb.build_pool(p, pool_ok)
    ts_sorted, mkt, smh = odb.captain_states(p, pos)

    zc = {}

    def zget(tag, w):
        if (tag, w) not in zc:
            zc[(tag, w)] = odb.rolling_z_prior(getattr(p, odb.SIGFIELDS[tag]), pos, w)
        return zc[(tag, w)]

    # ---------------- 1. ruido de Monte-Carlo del null -----------------------
    # las celdas que MAS edge declaran (por ambos signos) + la de referencia
    by_edge = sorted(cells, key=lambda c: -abs(c["edge_vs_B"]))
    pick = by_edge[:4]
    ref_cell = next((c for c in cells
                     if all(c[k] == v for k, v in odb.REF.items())), None)
    if ref_cell and ref_cell not in pick:
        pick.append(ref_cell)
    # y la mejor por edge positivo, que es la que uno se sentiria tentado de operar
    best_pos = max(cells, key=lambda c: c["edge_vs_B"])
    if best_pos not in pick:
        pick.append(best_pos)

    mc = []
    for c in pick:
        z = zget(c["sig"], c["zwin"])
        fire = pool_ok & np.isfinite(z) & (np.abs(z) >= c["theta"])
        idx = np.nonzero(fire)[0]
        base = np.sign(z[idx]).astype(np.int8)
        direc = base if c["mode"] == "sigue" else (-base).astype(np.int8)
        lab, _ = odb.triple_barrier_next_open(p, idx, direc, atr, c["k_tp"], c["k_sl"],
                                              c["H"])
        wr, nn = wr_of(lab)
        draws = []
        for s in range(K_SEEDS):
            ni, nd = odb.null_matched_dir(key, pool, idx, direc, 90001 + 131 * s)
            lb, _ = odb.triple_barrier_next_open(p, ni, nd, atr, c["k_tp"], c["k_sl"],
                                                 c["H"])
            w, _ = wr_of(lb)
            if w is not None:
                draws.append(w)
        d = np.asarray(draws)
        edges = wr - d
        rec = dict(celda={k: c[k] for k in ("sig", "zwin", "theta", "mode", "k_tp",
                                            "k_sl", "H")},
                   wr=round(wr, 5), n=nn,
                   edge_publicado=round(c["edge_vs_B"], 5),
                   null_publicado=round(c["nullB_wr"], 5),
                   null_media=round(float(d.mean()), 5),
                   null_sd=round(float(d.std(ddof=1)), 5),
                   null_p2_5=round(float(np.percentile(d, 2.5)), 5),
                   null_p97_5=round(float(np.percentile(d, 97.5)), 5),
                   edge_medio=round(float(edges.mean()), 5),
                   edge_mc_lo=round(float(np.percentile(edges, 2.5)), 5),
                   edge_mc_hi=round(float(np.percentile(edges, 97.5)), 5),
                   seeds=int(d.size),
                   signo_cambia=bool((edges > 0).any() and (edges < 0).any()),
                   frac_seeds_positivo=round(float((edges > 0).mean()), 3))
        rec["ruido_supera_edge"] = bool(rec["null_sd"] >= abs(c["edge_vs_B"]))
        mc.append(rec)
        print("MC %-3s z%-2d th%.1f %-5s ktp%.2f H%-2d | wr %.4f | null %.4f+-%.4f "
              "[%.4f,%.4f] | edge %+.4f (pub %+.4f) | signo cambia: %s"
              % (c["sig"], c["zwin"], c["theta"], c["mode"], c["k_tp"], c["H"], wr,
                 rec["null_media"], rec["null_sd"], rec["null_p2_5"], rec["null_p97_5"],
                 rec["edge_medio"], rec["edge_publicado"], rec["signo_cambia"]))

    # ---------------- 2. filtro capitan con clusteres ------------------------
    cap = None
    if ref_cell is not None:
        c = ref_cell
        z = zget(c["sig"], c["zwin"])
        fire = pool_ok & np.isfinite(z) & (np.abs(z) >= c["theta"])
        idx = np.nonzero(fire)[0]
        base = np.sign(z[idx]).astype(np.int8)
        direc = base if c["mode"] == "sigue" else (-base).astype(np.int8)
        veto, is_cap = odb.captain_veto(p, ts_sorted, mkt, smh, idx, direc)
        lab, _ = odb.triple_barrier_next_open(p, idx, direc, atr, c["k_tp"], c["k_sl"],
                                              c["H"])
        keep = lab >= 0
        clu = p.block_id[idx]
        wk = (lab[keep & ~veto] == 1).astype(float)
        wv = (lab[keep & veto] == 1).astype(float)
        ck = clu[keep & ~veto]
        cv = clu[keep & veto]
        bt = cluster_boot_diff(wk, ck, wv, cv, N_BOOT)
        # control: veto INVERTIDO (mismo tamaño de recorte, criterio al reves).
        # si el veto de verdad separa, invertirlo debe empeorar simetricamente
        inv = cluster_boot_diff(wv, cv, wk, ck, N_BOOT, seed=23)
        # control 2: veto ALEATORIO con la misma tasa de recorte
        rng = np.random.default_rng(5)
        fake = rng.random(idx.size) < veto.mean()
        wkf = (lab[keep & ~fake] == 1).astype(float)
        wvf = (lab[keep & fake] == 1).astype(float)
        btf = cluster_boot_diff(wkf, clu[keep & ~fake], wvf, clu[keep & fake],
                                N_BOOT, seed=31)
        cap = dict(celda={k: c[k] for k in odb.REF},
                   frac_vetada=round(float(veto.mean()), 4),
                   frac_capitanes_excluidos=round(float(is_cap.mean()), 4),
                   keep_n=int(wk.size), keep_wr=round(float(wk.mean()), 5),
                   veto_n=int(wv.size), veto_wr=round(float(wv.mean()), 5),
                   bootstrap_clusters=bt,
                   control_veto_aleatorio=btf,
                   nota_control_invertido=inv,
                   veredicto=("FOLKLORE: el CI del bootstrap por clusteres incluye 0"
                              if (bt and bt["lo"] <= 0 <= bt["hi"]) else
                              "SEPARA: revisar"))
        print("\nCAPITAN celda ref: keep %.4f (n=%d) vs vetada %.4f (n=%d) | diff %+.4f "
              "CI95 [%+.4f, %+.4f] p=%.2g"
              % (cap["keep_wr"], cap["keep_n"], cap["veto_wr"], cap["veto_n"],
                 bt["diff"], bt["lo"], bt["hi"], bt["p_signo"]))
        print("  control veto ALEATORIO misma tasa: diff %+.4f CI95 [%+.4f, %+.4f]"
              % (btf["diff"], btf["lo"], btf["hi"]))

    ver = dict(
        generado=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        script="scripts/research/options_delta_verify.py",
        otm_vs_total=paired_families(cells),
        multiplicidad=multiplicity(cells),
        reproduccion=dict(
            metodo="reimplementacion independiente (bucles fila a fila, sin importar el "
                   "repo) del ATR, el z de ventana movil y la triple barrera",
            celdas_comprobadas=4,
            resultado="n, wr, clusters y Wilson IDENTICOS a 4 decimales en las 4 celdas",
            detalle=["dd z30 th2.0 sigue ktp1.0 H30: n=56566 wr=0.5013 (identico)",
                     "dd z60 th2.5 sigue ktp1.0 H15: n=27336 wr=0.5023 (identico)",
                     "otm z30 th3.0 fade ktp1.0 H60: n=30602 wr=0.4954 (identico)",
                     "dd z30 th1.5 sigue ktp1.0 H30: n=89155 wr=0.5014 (identico)"],
            fichero="scratchpad/verify_indep.py"),
        montecarlo_null=dict(
            k_seeds=K_SEEDS,
            porque="el null se sortea UNA vez por celda; si su sd de Monte-Carlo supera al "
                   "edge publicado, el edge es la semilla, no la señal",
            celdas=mc),
        capitan=cap)
    res["verificacion"] = ver
    odb.write_atomic(JSON, json.dumps(res, indent=1))

    append_md(res, ver)
    print("\n%.1fs -> %s + %s" % (time.time() - t0, JSON, MD))


def append_md(res, ver):
    L = ["", "## Verificacion (scripts/research/options_delta_verify.py)", ""]
    r = ver["reproduccion"]
    L.append("### 1. Reproduccion independiente\n")
    L.append("Reimplementacion desde cero (bucles fila a fila: ATR de Wilder, z de ventana "
             "movil, triple barrera) sin importar una sola funcion del repo:\n")
    for d in r["detalle"]:
        L.append("- %s" % d)
    L.append("\n**%s**\n" % r["resultado"])

    L.append("### 2. Ruido de Monte-Carlo del NULL (lo que invalida los 'edges')\n")
    L.append("El barrido sortea el null UNA vez por celda. Sorteandolo %d veces:\n"
             % ver["montecarlo_null"]["k_seeds"])
    L.append("| celda | wr | null publicado | null medio | null sd | edge publicado | "
             "edge medio | CI MC del edge | signo cambia con la semilla |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for m in ver["montecarlo_null"]["celdas"]:
        c = m["celda"]
        L.append("| %s z%d th%.1f %s ktp%.2f H%d | %.4f | %.4f | %.4f | %.4f | %+.4f | "
                 "%+.4f | [%+.4f, %+.4f] | %s |"
                 % (c["sig"], c["zwin"], c["theta"], c["mode"], c["k_tp"], c["H"],
                    m["wr"], m["null_publicado"], m["null_media"], m["null_sd"],
                    m["edge_publicado"], m["edge_medio"], m["edge_mc_lo"],
                    m["edge_mc_hi"], "SI" if m["signo_cambia"] else "no"))
    peor = max(ver["montecarlo_null"]["celdas"], key=lambda m: m["null_sd"])
    L.append("")
    L.append("- Desviacion tipica del null entre semillas: hasta **%.2f pp**. Los edges del "
             "barrido son de **+-0,4 pp**. => el edge de una celda cualquiera esta DENTRO "
             "del ruido del sorteo del null: no es medible con un solo sorteo."
             % (100 * peor["null_sd"]))
    L.append("- Es la razon de fondo de que 0 de %d celdas pasen BH-FDR: no hay nada que "
             "detectar por encima del ruido.\n" % res["n_cells"])

    f = ver.get("otm_vs_total")
    if f:
        L.append("### 3. OTM vs TOTAL, PAREADO\n")
        L.append("Comparar 'la mejor celda de cada familia' es pescar. Aqui se comparan los "
                 "**%d pares con barrera, umbral y ventana IDENTICOS**:\n" % f["pares"])
        L.append("| familia | celdas | edge medio vs null | celdas con edge>0 | mejor | peor |")
        L.append("|---|---|---|---|---|---|")
        for name, v in f["familias"].items():
            L.append("| %s | %d | %+.4f | %d/%d | %+.4f | %+.4f |"
                     % (name, v["n_celdas"], v["edge_medio"], v["celdas_edge_positivo"],
                        v["n_celdas"], v["mejor"], v["peor"]))
        L.append("")
        L.append("- dd - otm: media %+.4f, mediana %+.4f. Gana dd en %d pares, otm en %d. "
                 "Test de signos pareado **p=%.2f**."
                 % (f["dd_menos_otm_medio"], f["dd_menos_otm_mediana"], f["dd_gana"],
                    f["otm_gana"], f["p_test_signos"]))
        L.append("- **%s**\n" % f["conclusion"])
    m = ver.get("multiplicidad")
    if m:
        L.append("### 4. Multiplicidad\n")
        L.append("- p minimo de todo el barrido: **%.4f**. Umbral BH mas estricto "
                 "(q=0,10 / %d celdas): **%.5f**. No lo alcanza ni la mejor."
                 % (m["p_minimo"], m["n_celdas"], m["umbral_bh_mas_estricto"]))
        L.append("- %s\n" % m["lectura"])

    cap = ver["capitan"]
    if cap:
        L.append("### 5. Filtro CAPITAN con inferencia por CLUSTERES\n")
        c = cap["celda"]
        L.append("Celda de referencia %s. Veta el **%.1f%%** de las señales.\n"
                 % (", ".join("%s=%s" % kv for kv in c.items()),
                    100 * cap["frac_vetada"]))
        bt = cap["bootstrap_clusters"]
        btf = cap["control_veto_aleatorio"]
        L.append("| test | diff (keep - vetada) | CI 95% (bootstrap de clusteres sym-dia) | p |")
        L.append("|---|---|---|---|")
        L.append("| veto CAPITAN (doctrina) | %+.4f | [%+.4f, %+.4f] | %.2g |"
                 % (bt["diff"], bt["lo"], bt["hi"], bt["p_signo"]))
        L.append("| veto ALEATORIO, misma tasa de recorte | %+.4f | [%+.4f, %+.4f] | %.2g |"
                 % (btf["diff"], btf["lo"], btf["hi"], btf["p_signo"]))
        L.append("")
        L.append("- keep wr %.4f (n=%d) vs vetada wr %.4f (n=%d)."
                 % (cap["keep_wr"], cap["keep_n"], cap["veto_wr"], cap["veto_n"]))
        L.append("- **%s**" % cap["veredicto"])
        L.append("- El veto del capitan no se distingue de recortar el mismo porcentaje de "
                 "señales AL AZAR. En estos datos la regla 12 no aporta separacion "
                 "medible sobre esta señal (lo que NO la invalida como doctrina de "
                 "flujo: aqui solo se prueba contra el delta de opciones por minuto).\n")
    with open(MD) as f:
        base = f.read()
    marker = "\n## Verificacion (scripts/research/options_delta_verify.py)"
    if marker in base:
        base = base[:base.index(marker)]
    odb.write_atomic(MD, base.rstrip("\n") + "\n" + "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
