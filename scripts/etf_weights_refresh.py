#!/usr/bin/env python3
"""etf_weights_refresh.py — pesos REALES de los holdings de los ETF -> data/etf_weights.json

Fuente unica de verdad de los pesos de indice, que consume ./compass (C++) para nombrar
QUE acciones arrastran o empujan a QQQ/SPY/SMH/XLK.

POR QUE ES PYTHON Y ESTA BIEN QUE LO SEA (regla ~/CLAUDE.md 2026-07-25: "Python es
peligroso, solo para casos especificos"): esto es un LOTE OFFLINE de las 4am que baja unos
pesos de referencia que cambian lento. No es camino de senal, no calcula ninguna senal, y
538 ms de import de yfinance a las 4am no cuestan nada. Lo que consume estos pesos EN VIVO
es C++ y no toca la red. Prohibido llamar a esto desde cualquier cosa intradia.

POR QUE NO SE HARDCODEAN: el WEIGHTS de scripts/index_breadth.py:22 estaba EQUIVOCADO —
decia MSFT 8.0 en QQQ cuando el real es 4.34, y NVDA 9.0 cuando es 7.58. Un peso mal puesto
reordena la lista de culpables y hace que la flecha acuse al ticker equivocado.

LIMITE HONESTO: yfinance solo da el TOP-10 de holdings, asi que la cobertura es ~35-50% del
indice. Eso se escribe en el JSON (`w_listed_sum`) y ./compass lo REPORTA en vez de fingir
que mide el indice completo.

Uso: ./venv/bin/python scripts/etf_weights_refresh.py [--indices QQQ,SPY,SMH,XLK]
Cron: en scripts/dailyplans_run.sh, antes de index_breadth.py.
SENAL-SOLAMENTE.
"""
import argparse
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

OUT = "data/etf_weights.json"
DEFAULT = ["QQQ", "SPY", "SMH", "XLK"]


def fleet():
    try:
        return set(open("data/fleet.txt").read().split())
    except Exception:
        return set()


def holdings(sym):
    """-> {ticker: peso_pct} del top-10, o {} si no se puede. Falla RUIDOSO, nunca en silencio."""
    import yfinance as yf
    th = yf.Ticker(sym).funds_data.top_holdings
    if th is None or len(th) == 0:
        raise RuntimeError("top_holdings vacio")
    col = "Holding Percent"
    if col not in th.columns:
        raise RuntimeError(f"sin columna '{col}' (columnas: {list(th.columns)})")
    out = {}
    for tk, pct in th[col].items():
        t = str(tk).upper().strip()
        v = float(pct) * 100.0          # yfinance da fraccion (0.0758), no porcentaje
        if t and v > 0:
            out[t] = round(v, 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indices", default=",".join(DEFAULT))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    fl = fleet()
    idx = [s.strip().upper() for s in a.indices.split(",") if s.strip()]

    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "source": "yfinance funds_data.top_holdings (top-10)",
           "note": ("cobertura parcial por diseno: yfinance solo expone el top-10. "
                    "compass reporta `coverage`, no finge medir el indice completo."),
           "indices": {}}
    failed = []
    for s in idx:
        try:
            w = holdings(s)
        except Exception as e:
            failed.append(f"{s}: {type(e).__name__}: {e}")
            continue
        # cuantos de esos holdings tenemos en la flota (los unicos con barras locales)
        have = {k: v for k, v in w.items() if k in fl}
        out["indices"][s] = {
            "asof": time.strftime("%Y-%m-%d"),
            "n_listed": len(w),
            "w_listed_sum": round(sum(w.values()), 3),
            "n_in_fleet": len(have),
            "w_in_fleet_sum": round(sum(have.values()), 3),
            "not_in_fleet": sorted(set(w) - set(have)),
            "weights": w,
        }

    if not out["indices"]:
        # fail-loud: no se escribe un fichero vacio que luego parezca "medido"
        print("ERROR: no se obtuvo NINGUN indice; no se escribe el fichero", file=sys.stderr)
        for f in failed:
            print("  " + f, file=sys.stderr)
        return 1
    if failed:
        print("AVISO (indices que fallaron, el resto SI se escribe):", file=sys.stderr)
        for f in failed:
            print("  " + f, file=sys.stderr)
    out["failed"] = failed

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, OUT)      # atomico: otros procesos lo leen a la vez

    if a.json:
        print(json.dumps(out, indent=1))
        return 0
    for s, d in out["indices"].items():
        print(f"{s}: {d['n_listed']} holdings, suma {d['w_listed_sum']:.1f}% | "
              f"en la flota {d['n_in_fleet']} ({d['w_in_fleet_sum']:.1f}%) | "
              f"fuera: {','.join(d['not_in_fleet']) or '-'}")
        top = sorted(d["weights"].items(), key=lambda x: -x[1])[:6]
        print("   " + "  ".join(f"{k} {v:.2f}%" for k, v in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
