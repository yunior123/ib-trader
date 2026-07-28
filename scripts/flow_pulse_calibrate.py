#!/usr/bin/env python3
"""flow_pulse_calibrate.py — calibracion EOD de las probabilidades de flow_pulse
(2026-07-22, plan v3 "mejora el algoritmo, para prevenirnos").

Replay del dia con el MISMO algoritmo v3 (spikes 3x + filtros anti-artefacto +
dominancia + contexto band-walk/muro) sobre data/whale_flow_hist.jsonl y las
barras 1m. Por señal mide el REBOTE predicho a +15min:
  - hit: el retorno +15m tiene el signo del rebote (CALLS->baja, PUTS->alza)
  - mfe: excursion favorable maxima >=0.10% en 15min (metrica secundaria)
Acumula por bucket tipo|contexto en data/flow_pulse_probs.json (idempotente por
dia: re-correr el mismo dia sobreescribe su aporte). pct que canta el binario = tasa medida (raw) si n>=5, si no hereda el
agregado del tipo; wilson_lo (95%) queda como referencia de incertidumbre.
Corre desde daily_archive (16:10) o a mano: ./venv/bin/python scripts/flow_pulse_calibrate.py [YYYY-MM-DD]
"""
import json, math, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
SPIKE_X, SPIKE_MIN, EMA_A, WALL_PCT = 3.0, 2000, 0.40, 0.004
CAPT_W = 1200                     # v4: vigencia del spike del capitan (20 min)
PROBS_PATH = "data/flow_pulse_probs.json"

# ---- v4: jerarquia de capitanes (espejo del binario) ----
MEM_TROOP = {"MU", "SKHY", "DRAM", "SNDK", "WDC", "STX", "LRCX"}
def is_market_captain(s): return s in ("SPY", "QQQ")
def is_captain(s): return is_market_captain(s) or s == "SMH"
def captains_of(s):
    if is_market_captain(s): return []
    return (["SMH"] if s in MEM_TROOP else []) + ["SPY", "QQQ"]
def in_troop_of(cap, s):
    if s == cap: return False
    if is_market_captain(cap): return not is_market_captain(s)
    return s in MEM_TROOP

def wilson_lo(ok, n, z=1.96):
    if n == 0: return 0.0
    p = ok / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    e = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - e) / d)

def load_bars(sym):
    try:
        out = []
        for l in open(f"data/bars_{sym.lower()}_ibkr.txt"):
            f = l.split()
            if len(f) >= 5:
                out.append((int(float(f[0])), float(f[4])))
        return out
    except Exception:
        return []

def bands_ctx(bars, ts):
    """band-walk 1m+5m con las barras hasta ts (mismo math del binario)."""
    upto = [(t, c) for t, c in bars if t <= ts][-160:]
    if len(upto) < 25 or ts - upto[-1][0] > 240:
        return None
    def bb(cl):
        m = sum(cl) / len(cl)
        sd = (sum((c - m) ** 2 for c in cl) / len(cl)) ** .5
        return m - 2 * sd, m + 2 * sd
    c1 = [c for t, c in upto[-21:-1]]
    lo1, up1 = bb(c1)
    last = upto[-1][1]
    a5 = {}
    for t, c in upto: a5[t - t % 300] = c
    if len(a5) < 21:
        return {"walk_up": False, "walk_dn": False}
    c5all = [c for k, c in sorted(a5.items())]
    lo5, up5 = bb(c5all[-21:-1])
    last5 = c5all[-1]
    return {"walk_up": last > up1 and last5 > up5,
            "walk_dn": last < lo1 and last5 < lo5}

def wall_ctx(sym, side, spot):
    """muro top-3 OI del lado a <=0.4% — usa la cadena archivada del dia si existe."""
    for base in (f"data/history/{DATE}", "data"):
        p = f"{base}/opt_chain_{sym.lower()}.txt"
        if os.path.exists(p):
            break
    else:
        return False
    try:
        rows = []
        exp0 = None
        for l in open(p):
            if l.startswith("#"): continue
            f = l.split()
            if len(f) < 7: continue
            try: k, r, e, oi = float(f[0]), f[1], f[2], float(f[6])
            except ValueError: continue
            if exp0 is None: exp0 = e
            if e == exp0 and r == side and oi > 0: rows.append((oi, k))
        rows.sort(reverse=True)
        return any(spot > 0 and abs(k - spot) / spot <= WALL_PCT for oi, k in rows[:3])
    except Exception:
        return False

def replay(date):
    day0 = time.mktime(time.strptime(date, "%Y-%m-%d"))
    recs = []
    for src in (f"data/history/{date}/whale_flow_hist.jsonl", "data/whale_flow_hist.jsonl"):
        if os.path.exists(src):
            recs = [json.loads(l) for l in open(src) if l.strip()]
            break
    recs = [r for r in recs if day0 <= r["ts"] < day0 + 86400]
    barscache = {}
    hist = {}
    out = []       # (bucket, hit, mfe_hit)
    cap_last = {}  # v4: capitan -> (dir, ts)
    troop_spk = [] # v4: (ts, sym, dir) spikes recientes (vetados incluidos)
    for r in recs:
        h = hist.setdefault(r["sym"], {"prev": None, "ec": -1, "ep": -1})
        p = h["prev"]
        if p and r["ts"] > p["ts"]:
            mins = (r["ts"] - p["ts"]) / 60
            if 1 <= mins <= 30:
                dc, dp = r["vc"] - p["vc"], r["vp"] - p["vp"]
                if dc >= 0 and dp >= 0:
                    rc, rp = dc / mins, dp / mins
                    sc = h["ec"] > 0 and rc >= SPIKE_X * h["ec"] and dc >= SPIKE_MIN
                    sp = h["ep"] > 0 and rp >= SPIKE_X * h["ep"] and dp >= SPIKE_MIN
                    artifact = (sc and sp) or (h["ec"] > 0 and rc > 50 * h["ec"]) \
                               or (h["ep"] > 0 and rp > 50 * h["ep"])
                    if artifact:
                        h["prev"] = r; continue
                    sig = None
                    if sc and dc >= 2 * dp: sig = ("SPIKE_CALLS", True)
                    elif sp and dp >= 2 * dc: sig = ("SPIKE_PUTS", False)
                    if sig:
                        typ, exp_dn = sig
                        sym = r["sym"]
                        if sym not in barscache: barscache[sym] = load_bars(sym)
                        bars = barscache[sym]
                        bc = bands_ctx(bars, r["ts"])
                        veto = bc and ((typ == "SPIKE_CALLS" and bc["walk_up"]) or
                                       (typ == "SPIKE_PUTS" and bc["walk_dn"]))
                        wall = wall_ctx(sym, "C" if typ == "SPIKE_CALLS" else "P",
                                        r.get("spot", 0))
                        my_dir = "C" if typ == "SPIKE_CALLS" else "P"
                        # v4: override = capitan vigente en direccion opuesta
                        ovr = any(cap_last.get(c) and cap_last[c][0] != my_dir
                                  and r["ts"] - cap_last[c][1] <= CAPT_W
                                  for c in captains_of(sym))
                        ctx = "bandwalk" if veto else \
                              ("override" if ovr else ("muro" if wall else "normal"))
                        win = [(t, c) for t, c in bars if r["ts"] <= t <= r["ts"] + 900]
                        p0 = next((c for t, c in reversed([(t, c) for t, c in bars
                                                          if t <= r["ts"]])), None)
                        if p0 and win:
                            p15 = win[-1][1]
                            r15 = (p15 / p0 - 1) * 100
                            hit = (r15 < 0) == exp_dn
                            mfe = (min(c for t, c in win) / p0 - 1) * 100 if exp_dn \
                                  else (max(c for t, c in win) / p0 - 1) * 100
                            mfe_hit = (mfe <= -0.10) if exp_dn else (mfe >= 0.10)
                            out.append((f"{typ}|{ctx}", hit, mfe_hit))
                            # v4: 🎖 CAPITAN REVIERTE — spike (no vetado) del capitan
                            # tras spikes opuestos de su tropa en <=20 min
                            if not veto and is_captain(sym):
                                troop = [s for t, s, d in troop_spk
                                         if d != my_dir and r["ts"] - t <= CAPT_W
                                         and in_troop_of(sym, s)]
                                if troop:
                                    out.append((f"CAPITAN_REVIERTE|{'alza' if exp_dn is False else 'baja'}",
                                                hit, mfe_hit))
                        # v4: registrar el spike en la jerarquia (vetado o no)
                        if is_captain(sym):
                            cap_last[sym] = (my_dir, r["ts"])
                        troop_spk.append((r["ts"], sym, my_dir))
                        troop_spk = [x for x in troop_spk if r["ts"] - x[0] <= CAPT_W]
                    h["ec"] = rc if h["ec"] < 0 else EMA_A * rc + (1 - EMA_A) * h["ec"]
                    h["ep"] = rp if h["ep"] < 0 else EMA_A * rp + (1 - EMA_A) * h["ep"]
        h["prev"] = r
    return out

def main():
    global DATE
    DATE = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y-%m-%d")
    sigs = replay(DATE)
    day = {}
    for bucket, hit, mfe in sigs:
        d = day.setdefault(bucket, {"n": 0, "ok": 0, "mfe_ok": 0})
        d["n"] += 1; d["ok"] += int(hit); d["mfe_ok"] += int(mfe)
    try:
        store = json.load(open(PROBS_PATH))
    except Exception:
        store = {"days": {}}
    store.setdefault("days", {})[DATE] = day
    # agregado acumulado -> pct (Wilson lower bound, conservador)
    agg = {}
    for dd in store["days"].values():
        for b, d in dd.items():
            a = agg.setdefault(b, {"n": 0, "ok": 0, "mfe_ok": 0})
            for k in ("n", "ok", "mfe_ok"): a[k] += d[k]
    # pct (lo que canta el binario) = tasa medida si n>=5; con n chico hereda
    # el agregado del TIPO; wilson_lo queda como referencia de incertidumbre
    type_tot = {}
    for b, a in agg.items():
        t = b.split("|")[0]
        tt = type_tot.setdefault(t, {"n": 0, "ok": 0})
        tt["n"] += a["n"]; tt["ok"] += a["ok"]
    for b, a in agg.items():
        t = b.split("|")[0]
        a["raw_pct"] = round(a["ok"] / a["n"] * 100) if a["n"] else 0
        a["wilson_lo"] = round(wilson_lo(a["ok"], a["n"]) * 100)
        a["mfe_pct"] = round(a["mfe_ok"] / a["n"] * 100) if a["n"] else 0
        if a["n"] >= 5:
            a["pct"] = a["raw_pct"]
        else:
            tt = type_tot[t]
            a["pct"] = round(tt["ok"] / tt["n"] * 100) if tt["n"] else a["raw_pct"]
        store[b] = a
    tmp = PROBS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=1)
    os.replace(tmp, PROBS_PATH)   # flow_pulse.cpp lo lee en vivo
    print(f"{DATE}: {len(sigs)} señales | buckets acumulados:")
    for b, a in sorted(agg.items()):
        print(f"  {b:22s} n={a['n']:3d} canta={a['pct']}% raw={a['raw_pct']}% wilson_lo={a['wilson_lo']}% mfe={a['mfe_pct']}%")

if __name__ == "__main__":
    main()
