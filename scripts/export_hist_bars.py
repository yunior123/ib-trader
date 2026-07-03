#!/usr/bin/env python3
"""export_hist_bars.py — vuelca 1m historicas de poly_bars a data/bars_hist_<sym>.txt.

Existe porque los ficheros vivos `bars_<sym>_ibkr.txt` solo guardan 1-2 sesiones y los
indicadores multi-temporalidad (zerolag 60m/240m/1D) necesitan meses. El consumidor lee
PRIMERO el historico y ENCIMA el vivo, asi que el solape se resuelve por epoch.
LOTE FUERA DE SESION.
"""
import os, sqlite3, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(REPO)
DIAS = int(os.environ.get("HIST_DIAS", "400"))
syms = [s.upper() for s in (sys.argv[1:] or open("data/fleet.txt").read().split())]
con = sqlite3.connect("file:data/trades.db?mode=ro", uri=True)
for sym in syms:
    rows = con.execute("select ts,o,h,l,c,v from poly_bars where sym=? order by ts", (sym,)).fetchall()
    if not rows:
        print("  %-6s sin poly_bars" % sym); continue
    corte = rows[-1][0] - DIAS * 86400 * 1000
    rows = [r for r in rows if r[0] >= corte]
    p = "data/bars_hist_%s.txt" % sym.lower()
    with open(p + ".tmp", "w") as f:
        for ts, o, h, l, c, v in rows:
            f.write("%d %.4f %.4f %.4f %.4f %.0f\n" % (ts // 1000, o, h, l, c, v))
    os.replace(p + ".tmp", p)
    print("  %-6s %6d barras -> %s" % (sym, len(rows), p))
