#!/usr/bin/env python3
"""option_vehicle_backtest.py — re-puntua las señales de un dia en el VEHICULO REAL
(la opcion ATM del vencimiento mas cercano), no en el subyacente.

Entrada al ASK, salida al BID -> el spread real esta INCLUIDO en cada numero.
Fuente de primas: data/history/<day>/opt_chain_<sym>_HHMM.txt (foto cada 5 min).

Uso: ./venv/bin/python scripts/option_vehicle_backtest.py [YYYY-MM-DD]
"""
import os, sys, glob, math, sqlite3, json
import datetime as dt
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from eod_backtest import wilson  # reuso

DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-07-24"
HIST = os.path.join(REPO, "data", "history", DAY)
ENTRY_MAX_LAG_S = 8 * 60      # foto de entrada: primera >= señal, max 8 min despues
EXIT_TOL_S = 4 * 60           # foto de salida: la mas cercana a +H, tolerancia +-4 min
HORIZONS = (15, 30, 60)
TPS = (0.30, 0.50, 1.00)

# ---------------------------------------------------------------- cadenas
def load_chains():
    """sym -> lista ordenada de snapshots {epoch, spot, quotes{(k,right,exp)->dict}}"""
    chains = defaultdict(list)
    for path in glob.glob(os.path.join(HIST, "opt_chain_*_[0-9][0-9][0-9][0-9].txt")):
        sym = os.path.basename(path).split("opt_chain_")[1].rsplit("_", 1)[0].upper()
        epoch = spot = None
        quotes = {}
        exps = set()
        for ln in open(path):
            if ln.startswith("#"):
                if "epoch " in ln:
                    try:
                        epoch = int(ln.split("epoch ")[1].split(" |")[0])
                        spot = float(ln.split("spot ")[1].split(" |")[0].split()[0])
                    except Exception:
                        pass
                continue
            f = ln.split()
            if len(f) < 10:
                continue
            try:
                k = float(f[0]); right = f[1]; exp = f[2]
                bid, ask = float(f[3]), float(f[4])
                vol, oi = float(f[5]), float(f[6])
                iv, delta = float(f[7]), float(f[8])
            except ValueError:
                continue
            quotes[(k, right, exp)] = dict(bid=bid, ask=ask, vol=vol, oi=oi,
                                           iv=iv, delta=delta)
            exps.add(exp)
        if epoch and spot and quotes:
            chains[sym].append(dict(epoch=epoch, spot=spot, q=quotes,
                                    exp0=min(exps), path=os.path.basename(path)))
    for s in chains:
        chains[s].sort(key=lambda x: x["epoch"])
    return chains

CH = load_chains()

def snap_at_or_after(sym, ep):
    for s in CH.get(sym, []):
        if s["epoch"] >= ep:
            return s if s["epoch"] - ep <= ENTRY_MAX_LAG_S else None
    return None

def snap_near(sym, ep):
    best = None
    for s in CH.get(sym, []):
        d = abs(s["epoch"] - ep)
        if best is None or d < best[0]:
            best = (d, s)
    if best and best[0] <= EXIT_TOL_S:
        return best[1]
    return None

def atm_key(snap, right):
    """strike mas cercano al spot, vencimiento mas cercano, con cotizacion viva."""
    exp = snap["exp0"]
    cands = [(abs(k - snap["spot"]), k) for (k, r, e) in snap["q"]
             if r == right and e == exp]
    if not cands:
        return None
    for _, k in sorted(cands):
        q = snap["q"][(k, right, exp)]
        if q["ask"] > 0 and q["bid"] >= 0:      # -1 = sin dato (post 16:15)
            return (k, right, exp)
    return None

def quote(snap, key):
    q = snap["q"].get(key)
    if not q or q["bid"] < 0 or q["ask"] < 0:
        return None
    return q

# ---------------------------------------------------------------- direccion
EXCLUDE_KIND = ("WATCHDOG", "SCALPER HALT", "FLOW PULSE", "BOLLINGER VIGIA",
                "FINVIZ", "TICKER CIEGO", "ALARMA PRECIO", "ZONA ",
                "RE-ENTRADA A BANDA", "ESTRUCTURAL pin", "ESTRUCTURAL flip",
                "MANADA BAJISTA")

def direction(kind, source, msg):
    """(+1 alcista/CALL, -1 bajista/PUT, 0 excluida), familia, grupo_gate, ambigua"""
    k = kind or ""; m = msg or ""; up = (k + " " + m).upper()
    for x in EXCLUDE_KIND:
        if x.upper() in up.upper() and x.upper() in (k.upper() + " " + m.upper()):
            if x in ("MANADA BAJISTA",) and "MANADA BAJISTA" not in k:
                continue
            return 0, "excluida", "", False
    gate = ""
    if "[VETO medido" in k: gate = "VETO medido"
    elif "[MUTED p<55]" in k: gate = "MUTED p<55"
    elif "capitan opuesto" in k: gate = "MUTED capitan"
    elif "(VETADO)" in k: gate = "VETADO band-walk"
    else: gate = "SONO"

    # --- bots de estrategia  "SYM: BUY/SELL"
    if k.endswith(": BUY"):  return +1, "BOT BUY", gate, False
    if k.endswith(": SELL"): return -1, "BOT SELL", gate, False
    # --- CUSUM
    if "TERREMOTO" in k:
        return (+1, "CUSUM TERREMOTO", gate, False) if "ALZA" in up else (-1, "CUSUM TERREMOTO", gate, False)
    # --- manada / capitan
    if "MANADA A CALLS" in k: return -1, "MANADA A CALLS", gate, False
    if "MANADA A PUTS" in k:  return +1, "MANADA A PUTS", gate, False
    if "CAPITAN REVIERTE" in k:
        return (+1, "CAPITAN REVIERTE", gate, False) if "rebote al alza" in m else (-1, "CAPITAN REVIERTE", gate, False)
    # --- giro (AMBIGUAS: supuesto de doctrina fade)
    if "GIRO A CALLS" in k: return -1, "GIRO A CALLS", gate, True
    if "GIRO A PUTS" in k:  return +1, "GIRO A PUTS", gate, True
    # --- flow spikes
    if "SPIKE" in k:
        if "(VETADO)" in k:   # el veto invierte: continuacion
            return (-1, "FLOW SPIKE PUTS", gate, False) if "PUTS" in k else (+1, "FLOW SPIKE CALLS", gate, False)
        if "PUTS" in k:  return +1, "FLOW SPIKE PUTS", gate, False
        if "CALLS" in k: return -1, "FLOW SPIKE CALLS", gate, False
    # --- ballenas
    if "BALLENA PUTS" in k:  return +1, "BALLENA PUTS", gate, False
    if "BALLENA CALLS" in k: return -1, "BALLENA CALLS", gate, False
    if "BALLENA CRECE" in k: return -1, "BALLENA CRECE (calls)", gate, False
    # --- bollinger
    if "APERTURA FUERA DE BANDA" in k:
        return (+1, "BB APERTURA FUERA", gate, False) if " abajo de la banda" in m else (-1, "BB APERTURA FUERA", gate, False)
    if "BB REBOTE" in k:
        fam = "BB REBOTE 1m ⭐" if "⭐" in k else "BB REBOTE 1m"
        return (+1, fam, gate, False) if "ABAJO" in up else (-1, fam, gate, False)
    if "RE-ENTRADA" in k:
        return (+1, "BB RE-ENTRADA 15m", gate, False) if "ABAJO" in up else (-1, "BB RE-ENTRADA 15m", gate, False)
    if "BAND-WALK" in k:
        return (-1, "BB BAND-WALK", gate, False) if "ABAJO" in up else (+1, "BB BAND-WALK", gate, False)
    # --- estructural magnet
    if "ESTRUCTURAL magnet" in k:
        return (+1, "ESTRUCTURAL magnet", gate, False) if "↑" in m else (-1, "ESTRUCTURAL magnet", gate, False)
    return 0, "excluida", "", False

# ---------------------------------------------------------------- run
def main():
    c = sqlite3.connect(os.path.join(REPO, "trades.db"))
    rows = c.execute("SELECT ts_epoch, ts_txt, kind, source, symbol, msg FROM signals "
                     "WHERE date=? ORDER BY ts_epoch", (DAY,)).fetchall()
    c.close()

    recs = []
    excl = defaultdict(int)
    for ep, ts_txt, kind, source, sym, msg in rows:
        if not ep:
            excl["sin ts_epoch"] += 1; continue
        d, fam, gate, ambig = direction(kind, source, msg)
        if d == 0:
            excl["sin direccion inferible"] += 1; continue
        # MANADA: el mensaje habla del INDICE (price = QQQ), no del ticker nombrado
        if fam.startswith("MANADA A"):
            sym = "QQQ"
        if not sym:
            excl["symbol NULL"] += 1; continue
        sym = sym.upper()
        if sym not in CH:
            excl[f"sin cadena de opciones ({sym})"] += 1; continue
        right = "C" if d > 0 else "P"
        s0 = snap_at_or_after(sym, int(ep))
        if not s0:
            excl["sin foto de cadena tras la señal"] += 1; continue
        key = atm_key(s0, right)
        if not key:
            excl["sin ATM cotizable"] += 1; continue
        q0 = quote(s0, key)
        if not q0 or q0["ask"] <= 0:
            excl["ask invalido"] += 1; continue
        entry = q0["ask"]
        spread_pct = (q0["ask"] - q0["bid"]) / q0["ask"] * 100 if q0["ask"] > 0 else 999
        rec = dict(ts=ts_txt, sym=sym, kind=kind, source=source, fam=fam, gate=gate,
                   ambig=ambig, dir=d, right=right, strike=key[0], exp=key[2],
                   entry=entry, bid0=q0["bid"], spread=spread_pct, oi=q0["oi"],
                   iv=q0["iv"], delta=q0["delta"], spot=s0["spot"],
                   lag=s0["epoch"] - int(ep), ep0=s0["epoch"],
                   cost=entry * 100)
        rec["gate_ok"] = (spread_pct <= 5.0) and (q0["oi"] > 500)
        rec["budget_ok"] = rec["cost"] <= 200.0
        # salidas
        for H in HORIZONS:
            sx = snap_near(sym, s0["epoch"] + H * 60)
            r = None
            if sx and sx["epoch"] > s0["epoch"]:
                qx = quote(sx, key)
                if qx and qx["bid"] >= 0:
                    r = (qx["bid"] - entry) / entry * 100
            rec[f"ret{H}"] = r
            rec[f"win{H}"] = (None if r is None else (1 if r > 0 else 0))
        # camino de bids dentro de 60 min
        path = []
        for s in CH[sym]:
            if s0["epoch"] < s["epoch"] <= s0["epoch"] + 60 * 60:
                qx = quote(s, key)
                if qx and qx["bid"] >= 0:
                    path.append((s["epoch"], qx["bid"], (qx["bid"]+qx["ask"])/2))
        mx = max([p[1] for p in path], default=None)
        mn = min([p[1] for p in path], default=None)
        rec["mfe"] = None if mx is None else (mx - entry) / entry * 100
        rec["mae"] = None if mn is None else (mn - entry) / entry * 100
        for tp in TPS:
            rec[f"tp{int(tp*100)}"] = (None if mx is None
                                       else (1 if mx >= entry * (1 + tp) else 0))
        # bracket: primera foto que toca TP o SL (-30%), sino salida al bid a +60m/ultima
        for tp in TPS:
            res = None
            for _, b, _m in path:
                if b >= entry * (1 + tp): res = tp * 100; break
                if b <= entry * 0.70:     res = -30.0;    break
            if res is None and path:
                res = (path[-1][1] - entry) / entry * 100
            rec[f"br{int(tp*100)}"] = res
        # mid->mid (sin coste de spread) para aislar cuanto pesa el spread
        mid0 = (q0["bid"] + q0["ask"]) / 2
        for H in HORIZONS:
            sx = snap_near(sym, s0["epoch"] + H * 60)
            r = None
            if sx and sx["epoch"] > s0["epoch"]:
                qx = quote(sx, key)
                if qx and qx["bid"] >= 0 and mid0 > 0:
                    r = ((qx["bid"] + qx["ask"]) / 2 - mid0) / mid0 * 100
            rec[f"mid{H}"] = r
        recs.append(rec)

    out = os.path.join(HIST, "..", "..", "..", "scratch_option_vehicle.json")
    json.dump(dict(recs=recs, excl=excl), open(
        os.path.join(REPO, "data", f"option_vehicle_{DAY}.json"), "w"), indent=1)
    print(f"señales totales={len(rows)}  puntuadas={len(recs)}")
    for k, v in sorted(excl.items(), key=lambda x: -x[1]):
        print(f"  excluida: {k:45s} {v}")
    return recs, excl

if __name__ == "__main__":
    main()
