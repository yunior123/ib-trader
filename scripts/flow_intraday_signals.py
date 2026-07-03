#!/usr/bin/env python3
"""flow_intraday_signals.py — señales de spike de flujo INTRADIA sobre la serie
horaria reconstruida (2026-07-23). Replica flow_pulse: ritmo de acumulacion de
contratos/hora, spike >= SPIKE_X x EMA + dominancia 2x, fade (calls->PUT,
puts->CALL), jerarquia de capitanes (capitan opuesto vigente <=3h suprime al
nombre). Entrada = hora siguiente. Salida formato compartido.
"""
import csv, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
SPIKE_X = float(os.environ.get("FI_SPIKE_X", 3.0))
MIN_D = float(os.environ.get("FI_MIN", 2000))   # delta minimo de contratos en la hora
EMA_A = 0.40
CAPT_W = 3 * 3600   # vigencia capitan 3h

MEM = {"mu", "skhy", "dram", "sndk", "wdc", "stx", "lrcx", "nvda", "amd", "tsm"}
def captains_of(sym):
    c = []
    if sym in MEM: c.append("smh")
    c += ["spy", "qqq"]
    return [x for x in c if x != sym]

def load(sym):
    out = []
    try:
        for r in csv.DictReader(open(f"data/backtest/flow_intraday_{sym}.csv")):
            out.append((int(r["epoch"]), float(r["volC"]), float(r["volP"]), float(r["spot"])))
    except Exception:
        return []
    return out

def detect(sym):
    """lista de (epoch, 'CALLS'|'PUTS', spot) de spikes intradia."""
    rows = load(sym)
    ema_c = ema_p = -1
    prev = None
    sigs = []
    for (e, cc, cp, spot) in rows:
        if prev and e > prev[0]:
            day_reset = time.strftime("%Y-%m-%d", time.localtime(e)) != time.strftime("%Y-%m-%d", time.localtime(prev[0]))
            if not day_reset:
                mins = (e - prev[0]) / 60.0
                dc = cc - prev[1]; dp = cp - prev[2]
                if 30 <= mins <= 180 and dc >= 0 and dp >= 0:
                    rc = dc / mins; rp = dp / mins
                    spike_c = ema_c > 0 and rc >= SPIKE_X * ema_c and dc >= MIN_D and dc >= 2 * dp
                    spike_p = ema_p > 0 and rp >= SPIKE_X * ema_p and dp >= MIN_D and dp >= 2 * dc
                    artifact = (spike_c and spike_p) or (ema_c > 0 and rc > 50 * ema_c) or (ema_p > 0 and rp > 50 * ema_p)
                    if not artifact:
                        if spike_c: sigs.append((e, "CALLS", spot))
                        elif spike_p: sigs.append((e, "PUTS", spot))
                    ema_c = rc if ema_c < 0 else EMA_A * rc + (1 - EMA_A) * ema_c
                    ema_p = rp if ema_p < 0 else EMA_A * rp + (1 - EMA_A) * ema_p
            else:
                ema_c = ema_p = -1   # reset diario del ritmo
        prev = (e, cc, cp)
    return sigs

def next_hour_open(sym, e):
    rows = load(sym)
    for (e2, cc, cp, spot) in rows:
        if e2 > e and time.strftime("%Y-%m-%d", time.localtime(e2)) == time.strftime("%Y-%m-%d", time.localtime(e)):
            return e2, spot
    return None, None

def main():
    syms = sys.argv[1:] or ["spy", "qqq", "smh", "nvda", "mu"]
    cap = {c: detect(c) for c in ("spy", "qqq", "smh")}
    def cap_dir_at(c, e):
        d = None
        for (ce, cd, _) in cap.get(c, []):
            if 0 <= e - ce <= CAPT_W:
                d = cd
        return d
    out = [("epoch", "sym", "side", "kind", "ref_px", "target_px", "stop_px")]
    emit = supp = 0
    for sym in syms:
        for (e, direction, spot) in detect(sym):
            if sym not in ("spy", "qqq"):
                opp = False
                for c in captains_of(sym):
                    cd = cap_dir_at(c, e)
                    if cd and cd != direction:
                        opp = True; break
                if opp:
                    supp += 1; continue
            side = "SHORT" if direction == "CALLS" else "LONG"
            ne, nspot = next_hour_open(sym, e)
            if not ne or not spot:
                continue
            out.append((ne, sym.upper(), side, f"FLOWI_{direction}", f"{spot:.2f}", "0", "0"))
            emit += 1
    path = "data/backtest/signals_flowintraday.csv"
    open(path, "w").write("\n".join(",".join(str(x) for x in r) for r in out) + "\n")
    print(f"-> {path} | emitidas {emit}, suprimidas por capitan {supp}")

if __name__ == "__main__":
    main()
