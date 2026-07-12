#!/usr/bin/env python3
"""backtest_replay.py — harness de re-tuning de la flota (persistido 2026-07-11).

Los bots C++ son el motor de backtest: replay deterministico via --stdin
(~5us/bar). Este script trae bars reales de Alpaca, corre un config y parsea
los trades de AMBOS lados. Metodologia completa: memoria signal-engine-playbook
+ AGENTS.md (train/OOS, WR>=70, regresion bit a bit tras tocar el master).

Uso:
  venv/bin/python scripts/backtest_replay.py fetch NOK 180        # dias -> data/bt_nok.txt
  venv/bin/python scripts/backtest_replay.py run NOK data/bt_nok.txt NOK_BB_STD=2.5 NOK_SHORTS=1 ...
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "screener"))
from price import _load_alpaca_keys  # noqa: E402


def fetch(sym, days):
    key, sec = _load_alpaca_keys()
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bars, tok = [], None
    while True:
        url = (f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min"
               f"&feed=iex&limit=10000&start={start}" + (f"&page_token={tok}" if tok else ""))
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key,
                                                   "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.load(r)
        bars += d.get("bars") or []
        tok = d.get("next_page_token")
        if not tok:
            break
        time.sleep(0.3)
    out = os.path.join(ROOT, "data", f"bt_{sym.lower()}.txt")
    with open(out, "w") as f:
        for b in bars:
            ep = int(datetime.strptime(b["t"][:19], "%Y-%m-%dT%H:%M:%S")
                     .replace(tzinfo=timezone.utc).timestamp())
            f.write(f"{ep} {b['o']} {b['h']} {b['l']} {b['c']} {b['v']}\n")
    print(f"{sym}: {len(bars)} bars -> {out}")


def run(sym, hist, env_pairs):
    low = sym.lower()
    env = dict(os.environ)
    env.update(dict(p.split("=", 1) for p in env_pairs))
    # cwd AISLADO (fix 2026-07-11): correr en ROOT pisaba data/pos_*.txt
    # VIVOS de la flota y ensuciaba los ops logs con historia de replay.
    import tempfile
    with tempfile.TemporaryDirectory(prefix=f"rp_{low}_") as tmp:
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        out = subprocess.run([os.path.join(ROOT, f"{low}_signal_bot"), "--stdin"],
                             stdin=open(hist), capture_output=True, text=True,
                             env=env, cwd=tmp).stdout
    sides = {"L": [], "S": []}
    le = se = None
    for line in out.splitlines():
        m = re.search(r": COMPRAR \*\*\* ~([\d.]+)", line)
        if m:
            le = float(m.group(1)); continue
        m = re.search(r": VENDER \*\*\* ~([\d.]+)", line)
        if m and le:
            sides["L"].append(float(m.group(1)) / le - 1); le = None; continue
        m = re.search(r": PUT \*\*\* ~([\d.]+)", line)
        if m:
            se = float(m.group(1)); continue
        m = re.search(r"VENDER PUT \*\*\* ~([\d.]+)", line)
        if m and se:
            sides["S"].append(se / float(m.group(1)) - 1); se = None
    for name, lbl in (("L", "LONGS "), ("S", "SHORTS")):
        t = sides[name]
        n, w = len(t), sum(1 for x in t if x > 0)
        gw = sum(x for x in t if x > 0)
        gl = -sum(x for x in t if x <= 0)
        pf = gw / gl if gl > 1e-9 else (99 if gw > 0 else 0)
        print(f"  {lbl} {n:4d}T {w:4d}W WR {w / n if n else 0:5.0%} "
              f"tot {sum(t) * 100:+7.2f}%  pf {pf:4.1f}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fetch":
        fetch(sys.argv[2].upper(), int(sys.argv[3]) if len(sys.argv) > 3 else 90)
    elif len(sys.argv) >= 4 and sys.argv[1] == "run":
        run(sys.argv[2].upper(), sys.argv[3], sys.argv[4:])
    else:
        print(__doc__)
