#!/usr/bin/env python3
"""flow_daily_signals.py — genera señales de FLUJO desde el flujo diario
reconstruido (2026-07-23), con la jerarquía de capitanes, para backtest sobre
3 meses de datos reales.

Lógica (versión diaria del flow_pulse): por ticker, EMA del volumen call y put
diario; un SPIKE = volumen de un lado ≥ SPIKE_X × su EMA y ≥ MIN, con dominancia
2×. SPIKE_CALLS → fade → PUT (SHORT) al día siguiente; SPIKE_PUTS → CALL (LONG).
Jerarquía: si un NOMBRE spikea con un capitán (SPY/QQQ mercado, SMH memoria)
spikeando OPUESTO el mismo día, el capitán PREVALECE y el nombre se suprime
(regla 12). Entrada = apertura del día siguiente; ref_px = spot de cierre.
Salida: data/backtest/signals_flowdaily.csv (formato compartido).
"""
import csv, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
SPIKE_X = float(os.environ.get("FD_SPIKE_X", 2.5))
MIN_VOL = float(os.environ.get("FD_MIN", 3000))
EMA_A = 0.40

CAPS_MKT = {"spy", "qqq"}
MEM = {"mu", "skhy", "dram", "sndk", "wdc", "stx", "lrcx", "nvda", "amd", "tsm", "smh"}
def captains_of(sym):
    c = []
    if sym in MEM and sym != "smh": c.append("smh")
    c += ["spy", "qqq"]
    return [x for x in c if x != sym]

def load(sym):
    out = []
    try:
        for r in csv.DictReader(open(f"data/backtest/flow_daily_{sym}.csv")):
            out.append((r["date"], float(r["volC"]), float(r["volP"]), float(r["spot"])))
    except Exception:
        return []
    return out

def detect(sym):
    """dia -> ('CALLS'|'PUTS', spot) del spike de ese ticker."""
    rows = load(sym)
    ema_c = ema_p = -1
    sig = {}
    for (d, vc, vp, spot) in rows:
        if ema_c > 0 and vc >= SPIKE_X * ema_c and vc >= MIN_VOL and vc >= 2 * vp:
            sig[d] = ("CALLS", spot)
        elif ema_p > 0 and vp >= SPIKE_X * ema_p and vp >= MIN_VOL and vp >= 2 * vc:
            sig[d] = ("PUTS", spot)
        ema_c = vc if ema_c < 0 else EMA_A * vc + (1 - EMA_A) * ema_c
        ema_p = vp if ema_p < 0 else EMA_A * vp + (1 - EMA_A) * ema_p
    return sig, {d: s for d, (s, _) in sig.items()}

def next_day_open_epoch(sym, date):
    """epoch de la apertura (9:30 ET aprox) del siguiente dia de trading con barras."""
    try:
        days = sorted({time.strftime("%Y-%m-%d", time.localtime(int(r[0])))
                       for r in csv.reader(open(f"data/backtest/bars3mo5m_{sym}.csv")) if r and r[0][0].isdigit()})
    except Exception:
        return None
    for d in days:
        if d > date:
            # primer epoch de ese dia
            for r in csv.reader(open(f"data/backtest/bars3mo5m_{sym}.csv")):
                if r and r[0][0].isdigit() and time.strftime("%Y-%m-%d", time.localtime(int(r[0]))) == d:
                    return int(r[0])
    return None

def main():
    syms = sys.argv[1:] or ["spy", "qqq", "smh", "nvda", "mu"]
    # precomputar spikes por dia de los capitanes disponibles
    cap_sig = {}
    for c in ("spy", "qqq", "smh"):
        _, cs = detect(c)
        cap_sig[c] = cs
    out = [("epoch", "sym", "side", "kind", "ref_px", "target_px", "stop_px")]
    stats = {"emitidas": 0, "suprimidas_capitan": 0}
    for sym in syms:
        full, day_dir = detect(sym)
        for d, (direction, spot) in full.items():
            # jerarquía: capitán opuesto vigente ese día suprime al nombre
            suppressed = False
            if sym not in CAPS_MKT:
                for c in captains_of(sym):
                    cd = cap_sig.get(c, {}).get(d)
                    if cd and cd != direction:   # capitán spikea opuesto
                        suppressed = True; break
            if suppressed:
                stats["suprimidas_capitan"] += 1
                continue
            side = "SHORT" if direction == "CALLS" else "LONG"   # fade: calls->PUT, puts->CALL
            ep = next_day_open_epoch(sym, d)
            if not ep:
                continue
            kind = f"FLOWD_{direction}"
            out.append((ep, sym.upper(), side, kind, f"{spot:.2f}", "0", "0"))
            stats["emitidas"] += 1
    path = "data/backtest/signals_flowdaily.csv"
    with open(path, "w") as f:
        for row in out:
            f.write(",".join(str(x) for x in row) + "\n")
    print(f"-> {path}  | emitidas {stats['emitidas']}, suprimidas por capitán {stats['suprimidas_capitan']}")

if __name__ == "__main__":
    main()
