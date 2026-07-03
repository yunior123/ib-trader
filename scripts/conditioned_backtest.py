#!/usr/bin/env python3
"""conditioned_backtest.py — demuestra el LIFT de la SELECTIVIDAD: compara el win-rate de
TODAS las señales (RAW) contra el de las que SOBREVIVEN la capa de condicionamiento
(apagado de celdas muertas + ventanas horarias buenas). Orden Yunior 2026-07-24: "backtest
the whole thing... figure out why, attack the wrong ones".

HONESTIDAD (clave): los factores de hora se CALIBRARON sobre esta misma data (in-sample), así
que el lift aquí es un TECHO optimista, no una promesa out-of-sample. Se declara. El apagado
de celdas muertas y el filtro de ventana son descriptivos (qué habría pasado si NO operábamos
las celdas/horas que la data marca malas), no una predicción. La confirmación real llega con
data futura (el EOD recalibra y este mismo script se re-corre).

Compara 3 niveles sobre backtest_signal_outcomes (run más reciente, horizonte 15m):
  RAW           todas las señales
  SIN-MUERTAS   quitando las celdas source|símbolo apagadas (signal_enable.json)
  SELECTIVO     SIN-MUERTAS + solo buckets de hora con factor >= 1.0 (golden/power/…)

Uso: python3 scripts/conditioned_backtest.py
SEÑAL-SOLAMENTE.
"""
import os, sys, json, sqlite3
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
from eod_backtest import wilson
from timeofday_calib import bucket_of

DB = os.path.join(REPO, "data", "trades.db")


def load():
    c = sqlite3.connect(DB)
    run = c.execute("SELECT MAX(run_ts) FROM backtest_signal_outcomes").fetchone()[0]
    rows = c.execute("SELECT ts_txt, symbol, source, win FROM backtest_signal_outcomes "
                     "WHERE horizon=15 AND run_ts=?", (run,)).fetchall()
    c.close()
    enable = json.load(open("data/signal_enable.json"))
    tof = json.load(open("data/timeofday_factors.json"))
    return rows, enable, tof


def wr(rows):
    n = len(rows); w = sum(r[3] for r in rows)
    return n, w, wilson(w, n)


def main():
    rows, enable, tof = load()
    raw = rows
    # nivel 2: quitar celdas muertas
    def alive(r):
        cell = enable.get(f"{r[2]}|{r[1]}")
        return not (cell and not cell.get("enabled", True))
    lvl2 = [r for r in raw if alive(r)]
    # nivel 3: + solo buckets con factor >= 1.0 para esa fuente
    def good_window(r):
        b = bucket_of(r[0])
        f = tof.get(r[2], {}).get(b, {}).get("factor")
        return f is not None and f >= 1.0
    lvl3 = [r for r in lvl2 if good_window(r)]

    print("=== CONDITIONED BACKTEST — lift por selectividad (horizonte 15m) ===")
    print("  (in-sample: los factores de hora se ajustaron sobre esta data -> techo optimista)\n")
    print(f"{'nivel':14s} {'n':>5s} {'wins':>5s} {'WR':>5s} {'Wilson[lo,hi]':>15s}")
    for name, rr in [("RAW (todo)", raw), ("SIN-MUERTAS", lvl2), ("SELECTIVO", lvl3)]:
        n, w, (p, lo, hi) = wr(rr)
        print(f"{name:14s} {n:>5d} {w:>5d} {p:>4d}% {'['+str(lo)+','+str(hi)+']':>15s}")

    # desglose por fuente en SELECTIVO
    print("\n--- SELECTIVO por fuente ---")
    bysrc = defaultdict(list)
    for r in lvl3:
        bysrc[r[2]].append(r)
    for src, rr in sorted(bysrc.items(), key=lambda x: -len(x[1])):
        n, w, (p, lo, hi) = wr(rr)
        base_n = sum(1 for r in raw if r[2] == src)
        print(f"  {src:11s} {n:>4d}/{base_n:<4d} señales  WR {p:>3d}% [{lo},{hi}]")

    n1, _, (p1, _, _) = wr(raw)
    n3, _, (p3, lo3, hi3) = wr(lvl3)
    print(f"\n-> RAW {p1}% (n={n1})  ->  SELECTIVO {p3}% (n={n3}, {100*n3//max(n1,1)}% del volumen).")
    print(f"   El edge está en NO disparar {n1-n3} señales de baja calidad, no en la señal cruda.")
    print("   CAVEAT in-sample declarado; confirmar con data futura (EOD recalibra).")


if __name__ == "__main__":
    main()
