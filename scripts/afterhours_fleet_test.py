#!/usr/bin/env python3
"""afterhours_fleet_test — prueba de flota en after-hours con datos reales
(orden Yunior 2026-07-15: "test the whole fleet in after hours... at least
2 hours... be careful with token consumption").

Deterministico, cero LLM: 26 ciclos x 300s (~2h10m). Por ciclo verifica:
  bots vivos / crash-loops / errores nuevos / frescura de bars por simbolo /
  señales nuevas del espejo Desktop (valida px vs tape al momento).
Al final: resumen compacto + veredicto 30m de cada señal del periodo.
"""
import os
import re
import subprocess
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # regla 7: jamas ruta absoluta
os.chdir(ROOT)
DAY = datetime.now().strftime("%Y-%m-%d")
MIRROR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals", f"{DAY}.txt")
CYCLES, PERIOD = 26, 300
SYMS = ["nok", "spcx", "dram", "tsla", "nvda", "txn", "tsm", "amd", "intc",
        "asml", "aapl", "gld", "qqq", "slv", "cper", "uso", "skhy"]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def bars(sym):
    out = []
    try:
        for ln in open(f"data/bars_{sym}_ibkr.txt"):
            p = ln.split()
            if len(p) == 6:
                out.append((float(p[0]), float(p[4])))
    except FileNotFoundError:
        pass
    return out


def px_at(bs, ep):
    best = None
    for t, c in bs:
        if t <= ep:
            best = c
        else:
            break
    return best


def mirror_lines():
    try:
        return open(MIRROR).read().splitlines()
    except FileNotFoundError:
        return []


start = time.time()
seen = len(mirror_lines())
relanz0 = int(sh("grep -hc relanzando *_signals.log 2>/dev/null | paste -sd+ - | bc") or 0)
signals = []          # señales nuevas del periodo
stall_hist = {}       # sym -> ciclos seguidos sin bar fresco
print(f"== TEST AFTER-HOURS {datetime.now():%H:%M:%S} — {CYCLES}x{PERIOD}s ==", flush=True)

for cyc in range(1, CYCLES + 1):
    time.sleep(PERIOD)
    now = time.time()
    nbots = int(sh("ps aux | grep -c '[_]signal_bot$'") or 0)
    relanz = int(sh("grep -hc relanzando *_signals.log 2>/dev/null | paste -sd+ - | bc") or 0)
    errs = sh("grep -ihE 'error|assert|segv|abort' *_signals.log 2>/dev/null | "
              "grep -viE 'relanzando|SIN DATOS' | wc -l").strip()
    fresh = stale = 0
    stallers = []
    for s in SYMS:
        bs = bars(s)
        age = now - bs[-1][0] - 60 if bs else 9e9
        if age < 180:
            fresh += 1
            stall_hist[s] = 0
        else:
            stale += 1
            stall_hist[s] = stall_hist.get(s, 0) + 1
            stallers.append(f"{s}:{int(age/60)}m")
    # señales nuevas del espejo
    lines = mirror_lines()
    new = lines[seen:]
    seen = len(lines)
    for ln in new:
        parts = [p.strip() for p in ln.split(" | ", 2)]
        if len(parts) < 3 or any(k in parts[1] for k in ("SIN DATOS", "TWS", "TEST", "WARMUP")):
            continue
        m = re.match(r"([A-Z]+)", parts[1])
        pm = re.search(r"px (\d+\.?\d*)|@ (\d+\.?\d*)", parts[2])
        px = float(pm.group(1) or pm.group(2)) if pm else None
        if m:
            sym = m.group(1).lower()
            bs = bars(sym)
            tape = px_at(bs, now) if bs else None
            dev = abs(px - tape) / tape * 100 if (px and tape) else None
            signals.append(dict(t=parts[0], title=parts[1], px=px, ep=now,
                                sym=sym, dev=dev))
            print(f"  SEÑAL {parts[0]} {parts[1]} px={px} tape={tape} "
                  f"dev={f'{dev:.2f}%' if dev is not None else '?'}", flush=True)
    print(f"[{datetime.now():%H:%M}] c{cyc:02d} bots {nbots}/20 "
          f"relanz+{relanz - relanz0} err {errs} bars {fresh}F/{stale}S "
          f"{' '.join(stallers[:4])}", flush=True)

# veredicto 30m de las señales del periodo
print("\n== VEREDICTOS 30m ==", flush=True)
for sg in signals:
    bs = bars(sg["sym"])
    p30 = px_at(bs, sg["ep"] + 1800)
    if sg["px"] and p30:
        print(f"  {sg['t']} {sg['title']}: px {sg['px']} -> 30m {p30} "
              f"({(p30 / sg['px'] - 1) * 100:+.2f}%)", flush=True)
print(f"\n== FIN {datetime.now():%H:%M:%S} — {len(signals)} señales en el periodo ==", flush=True)
