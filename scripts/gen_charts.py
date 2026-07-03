#!/usr/bin/env python3
"""gen_charts.py — genera charts/data/<sym>.json para el visor localhost.

Por simbolo: velas 1m de 90d (data/bt_<sym>.txt) + TODAS las operaciones del
replay con la config de produccion (keepalive env) marcadas con su epoch t=
(los bots imprimen t= en cada senal desde 2026-07-11). Visor: charts/index.html
(TradingView lightweight-charts, servido local con http.server).

Usage: venv/bin/python scripts/gen_charts.py [SYM ...]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from fleet_backtest_audit import SYMS, load_keepalive_env  # noqa: E402

ET_SHIFT = -4 * 3600   # epochs UTC -> mostrar hora ET en el chart (EDT)

RX = {
    "BUY": re.compile(r"\*\*\* \w+: COMPRAR \*\*\* ~([\d.]+) \(.*?\) t=(\d+)"),
    "SELL": re.compile(r"\*\*\* \w+: VENDER \*\*\* ~([\d.]+) \((.+?), entrada [\d.]+\) t=(\d+)"),
    "PUT": re.compile(r"\*\*\* \w+: PUT \*\*\* ~([\d.]+) \(.*?\) t=(\d+)"),
    "SELLPUT": re.compile(r"\*\*\* \w+: VENDER PUT \*\*\* ~([\d.]+) \((.+?), entrada [\d.]+\) t=(\d+)"),
}


def gen(sym: str):
    low = sym.lower()
    hist = os.path.join(ROOT, "data", f"bt_{low}.txt")
    candles, volume = [], []
    for ln in open(hist):
        p = ln.split()
        if len(p) != 6:
            continue
        t = int(float(p[0])) + ET_SHIFT
        o, h, l, c, v = map(float, p[1:])
        candles.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        volume.append({"time": t, "value": v,
                       "color": "rgba(38,166,154,0.4)" if c >= o else "rgba(239,83,80,0.4)"})

    env = dict(os.environ)
    env.update(load_keepalive_env(sym))
    with tempfile.TemporaryDirectory(prefix=f"ch_{low}_") as tmp:
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        out = subprocess.run([os.path.join(ROOT, f"{low}_signal_bot"), "--stdin"],
                             stdin=open(hist), capture_output=True, text=True,
                             env=env, cwd=tmp).stdout

    markers = []
    for line in out.splitlines():
        m = RX["BUY"].search(line)
        if m:
            markers.append({"time": int(m.group(2)) + ET_SHIFT, "position": "belowBar",
                            "color": "#26a69a", "shape": "arrowUp",
                            "text": f"BUY {float(m.group(1)):g}"})
            continue
        m = RX["SELL"].search(line)
        if m:
            stop = "STOP" in m.group(2).upper()
            markers.append({"time": int(m.group(3)) + ET_SHIFT, "position": "aboveBar",
                            "color": "#ef5350" if stop else "#ff9800", "shape": "arrowDown",
                            "text": f"SELL {float(m.group(1)):g} ({m.group(2)})"})
            continue
        m = RX["SELLPUT"].search(line)   # antes que PUT: 'VENDER PUT' contiene 'PUT'
        if m:
            stop = "STOP" in m.group(2).upper()
            markers.append({"time": int(m.group(3)) + ET_SHIFT, "position": "belowBar",
                            "color": "#ef5350" if stop else "#29b6f6", "shape": "arrowUp",
                            "text": f"SELL PUT {float(m.group(1)):g} ({m.group(2)})"})
            continue
        m = RX["PUT"].search(line)
        if m:
            markers.append({"time": int(m.group(2)) + ET_SHIFT, "position": "aboveBar",
                            "color": "#ab47bc", "shape": "arrowDown",
                            "text": f"BUY PUT {float(m.group(1)):g}"})

    markers.sort(key=lambda x: x["time"])
    os.makedirs(os.path.join(ROOT, "charts", "data"), exist_ok=True)
    with open(os.path.join(ROOT, "charts", "data", f"{low}.json"), "w") as f:
        json.dump({"symbol": sym, "candles": candles, "volume": volume,
                   "markers": markers}, f)
    print(f"{sym}: {len(candles)} velas, {len(markers)} marcas")


def main():
    syms = [s.upper() for s in sys.argv[1:]] or SYMS
    for sym in syms:
        gen(sym)
    with open(os.path.join(ROOT, "charts", "symbols.json"), "w") as f:
        json.dump(SYMS, f)


if __name__ == "__main__":
    main()
