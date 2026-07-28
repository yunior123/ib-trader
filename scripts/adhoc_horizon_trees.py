#!/usr/bin/env python3
"""adhoc_horizon_trees.py — PUNTUAL (Yunior 2026-07-28: "genera nuevos que vayan desde ahora
hasta el final del dia, tambien otros para mañana y el de aqui al viernes, y de aqui dos
semanas"). Reusa tree_sheets.build() (motor GEX/muros ya probado, cutoff arbitrario) con TRES
cortes nuevos -- mañana, viernes, 2 semanas -- y arma un PDF de 1 pagina por (simbolo,
horizonte). El "resto de hoy" ya lo cubre daily_fleet_plans.py (regenerado en vivo hace unos
minutos): esta pieza NO lo repite. SEÑAL-SOLAMENTE."""
import datetime as dt
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import tree_sheets as ts

SYMS = ["QQQ", "SPY", "MU", "DRAM", "SKHY"]
today = dt.date.today()
HORIZONS = [
    ("manana", (today + dt.timedelta(days=1)).isoformat()),
    ("viernes", ts.next_friday(today).isoformat()),
    ("2semanas", (today + dt.timedelta(days=14)).isoformat()),
]
OUTDIR = os.path.join(REPO, "data", "trees_horizonte")
os.makedirs(OUTDIR, exist_ok=True)


def render(sym, label, cutoff, d):
    path = os.path.join(OUTDIR, f"{sym}_{label}.pdf")
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.5, 11))
        fig.text(0.5, 0.96, f"{sym} — horizonte {label} (hasta {cutoff})",
                  ha="center", fontsize=14, weight="bold")
        lines = [
            f"generado {d['generado']}  |  spot {d['spot']:.2f} (edad {int(d['spot_age_s'] or 0)}s, "
            f"fuente {d['spot_source']})",
            f"contratos hasta {cutoff}: {d['n_hasta_viernes']} de {d['n_contratos_cadena']} en cadena",
            "",
            f"REGIMEN: {d['regime']}  net_gex {d['net_gex']:,.0f}" if d['net_gex'] is not None else "REGIMEN: sin dato",
            f"flip {d['flip']} ({d['flip_src']})" if d['flip'] is not None else "flip: sin raiz en banda",
            f"call_wall {d['call_wall']} ({d['call_wall_kind']})",
            f"put_wall {d['put_wall']} ({d['put_wall_kind']})",
            f"abs_wall {d['abs_wall']} ({d['abs_wall_kind']})  |  oi_call_wall {d['oi_call_wall']}  "
            f"oi_put_wall {d['oi_put_wall']}",
            "",
            f"vencimiento del corte ({cutoff}): {d['n_solo_viernes']} contratos, "
            f"P/C OI {d['viernes_pc_oi']}",
        ]
        fig.text(0.06, 0.90, "\n".join(lines), fontsize=10, va="top", family="monospace")

        y = 0.62
        fig.text(0.06, y, "TECHOS (calls, top OI del corte):", fontsize=10, weight="bold")
        for i, r in enumerate(d["viernes_top_calls"][:6]):
            fig.text(0.08, y - 0.03 * (i + 1), f"  {r['strike']:g}C  OI {r['oi']:,.0f}", fontsize=9, family="monospace")
        y2 = y - 0.03 * 7 - 0.02
        fig.text(0.06, y2, "PISOS (puts, top OI del corte):", fontsize=10, weight="bold")
        for i, r in enumerate(d["viernes_top_puts"][:6]):
            fig.text(0.08, y2 - 0.03 * (i + 1), f"  {r['strike']:g}P  OI {r['oi']:,.0f}", fontsize=9, family="monospace")

        y3 = y2 - 0.03 * 7 - 0.03
        fig.text(0.06, y3, "MUROS SUPERVIVIENTES (semana pasada -> hoy):", fontsize=10, weight="bold")
        surv = [s for s in d["supervivientes"] if s["estado"] == "SOBREVIVE"][:6]
        if not surv:
            fig.text(0.08, y3 - 0.028, "  ninguno sobrevive (o sin dato de semana pasada)", fontsize=9)
            y_end = y3 - 0.028
        else:
            for i, s in enumerate(surv):
                fig.text(0.08, y3 - 0.028 * (i + 1),
                          f"  {s['strike']:g}{s['lado']}  {s['dias_semana_pasada']}d  OI antes {s['oi_entonces']}  "
                          f"ahora {s['oi_ahora']} ({s['estado']})", fontsize=8, family="monospace")
            y_end = y3 - 0.028 * len(surv)

        foot_y = min(0.12, y_end - 0.04)
        fig.text(0.06, foot_y,
                  "Cadena archivada de hoy (todos los vencimientos vivos), corte aplicado por fecha.\n"
                  "Polygon = 15min (estructura). Ningun nivel aqui dispara orden: el PRINT confirma via IBKR.\n"
                  "Mientras mas lejos el horizonte, mas cambia el OI antes de llegar -- tratar como mapa, no gatillo.",
                  fontsize=7, style="italic", va="top")
        pdf.savefig(fig)
        plt.close(fig)
    return path


def main():
    cd = ts.latest_chain_dir()
    if not cd:
        print("sin chain_full_* archivada hoy, no puedo construir nada", file=sys.stderr)
        sys.exit(1)
    fri_std = ts.next_friday(today).isoformat()
    lw = ts.week_dates(dt.date.fromisoformat(fri_std))
    for label, cutoff in HORIZONS:
        for sym in SYMS:
            cut = cutoff
            d, err = ts.build(sym, cd, cut, lw)
            if d is None and err.startswith("la cadena no llega"):
                # sin expiry en el corte (DRAM/SKHY no tienen daily): usar el mas cercano
                cp = os.path.join(ts.HIST, cd, f"chain_full_{sym.lower()}.json")
                cs, _, _, _ = ts.gex_snapshot.contracts_from(cp)
                exps = sorted({c["exp"] for c in cs or []})
                if exps:
                    cut = f"{exps[0][:4]}-{exps[0][4:6]}-{exps[0][6:]}"
                    d, err = ts.build(sym, cd, cut, lw)
            if d is None:
                print(f"{sym} {label}: OMITIDO -> {err}")
                continue
            p = render(sym, label, cut, d)
            print(f"{sym} {label}: {p}  spot {d['spot']} {d['regime']} "
                  f"CW {d['call_wall']} PW {d['put_wall']}")


if __name__ == "__main__":
    main()
