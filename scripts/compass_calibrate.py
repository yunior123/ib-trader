#!/usr/bin/env python3
"""Calibrador de la BRUJULA (batch fuera de sesion). SENAL-SOLAMENTE.

Lee data/compass_ledger.jsonl (1 linea por transicion de estado/dir del compass C++),
mide cada flecha up/down contra las barras reales (data/bars_<sym>_ibkr.txt) a +15m y
+30m, y escribe data/compass_calib.json con celdas "ESTADO|fN|REGIMEN" -> {n, wr30, lo}
(lo = Wilson lower bound 95% sobre el acierto a 30m). El compass solo llama "medido" a
una celda con n>=30; hasta entonces sigue en doctrina (etiquetada).

Reglas: barra ausente en la ventana -> fila EXCLUIDA (jamas se fabrica un cierre);
sin datos suficientes -> celda ausente, no un numero plausible.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "compass_ledger.jsonl")
OUT = os.path.join(ROOT, "data", "compass_calib.json")
H15, H30 = 15 * 60, 30 * 60
TOL = 90  # s de tolerancia para casar la barra del horizonte


def wilson_lo(w, n, z=1.96):
    if n == 0:
        return None
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d


def load_bars(sym):
    path = os.path.join(ROOT, "data", f"bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(path):
        path = os.path.join(ROOT, "data", f"bars_{sym.lower()}.txt")
        if not os.path.exists(path):
            return None
    bars = {}
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 5:
                bars[int(p[0])] = float(p[4])
    return bars


def close_at(bars, ts):
    for dt in range(0, TOL + 1, 30):
        for t in (ts + dt, ts - dt):
            # barra 1m: casar al minuto redondeado
            c = bars.get(t - t % 60)
            if c is not None:
                return c
    return None


def main():
    if not os.path.exists(LEDGER):
        print("sin ledger todavia; nada que calibrar", file=sys.stderr)
        return 0
    now = __import__("time").time()
    cells = {}
    rows = exc = 0
    bars_cache = {}
    with open(LEDGER) as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if r.get("dir") not in ("up", "down"):
                continue
            ts, sym, spot = r["ts"], r["sym"], r.get("spot")
            if now - ts < H30 + TOL or not spot:
                continue  # aun sin madurar
            if sym not in bars_cache:
                bars_cache[sym] = load_bars(sym)
            bars = bars_cache[sym]
            if not bars:
                exc += 1
                continue
            c15, c30 = close_at(bars, ts + H15), close_at(bars, ts + H30)
            if c15 is None or c30 is None:
                exc += 1  # hueco de feed: no se fabrica
                continue
            lt = __import__("time").localtime(ts)
            mins = lt.tm_hour * 60 + lt.tm_min
            if not 570 <= mins < 960:
                continue  # solo RTH: la flecha se opera en sesion; overnight el mapa es de ayer
            entry = close_at(bars, ts)  # precio IMPRESO al girar la flecha, no el spot del mapa
            if entry is None:
                exc += 1
                continue
            spot = entry
            sgn = 1 if r["dir"] == "up" else -1
            fam = min(max(int(r.get("fam", 0)), 0), 4)
            key = f"{r['state']}|f{fam}|{r.get('regime') or 'SIN'}"
            c = cells.setdefault(key, {"n": 0, "w15": 0, "w30": 0})
            c["n"] += 1
            c["w15"] += 1 if sgn * (c15 - spot) > 0 else 0
            c["w30"] += 1 if sgn * (c30 - spot) > 0 else 0
            rows += 1
    out = {}
    for k, c in cells.items():
        lo = wilson_lo(c["w30"], c["n"])
        out[k] = {"n": c["n"], "wr15": round(c["w15"] / c["n"], 4),
                  "wr30": round(c["w30"] / c["n"], 4), "lo": round(lo, 4)}
    meta = {"_meta": {"rows": rows, "excluidas": exc, "ts": int(now),
                      "fuente": "compass_ledger.jsonl vs bars IBKR 1m, win=cierre a favor"}}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({**meta, **out}, f, indent=1)
    os.rename(tmp, OUT)
    print(f"celdas {len(out)} | filas medidas {rows} | excluidas {exc} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
