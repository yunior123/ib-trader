#!/usr/bin/env python3
"""yoel_adapted_engine.py — ENGINE YOEL-ADAPTADO (2026-07-23, Mision 3).

Yoel FUSIONADO con lo nuestro para que "todo sea mas fuerte y seguro" (Yunior).
Toma las MISMAS señales geometricas del engine puro (yoel_engine.detect) y las
pasa por NUESTROS filtros de contexto antes de emitirlas:

  1) PRIOR BOLLINGER MEDIDO (data/bollinger_plus.json): solo se acepta la señal
     si la base empirica del ticker es >= 50% (no jugamos donde la casa pierde).
     Ticker sin registro -> se acepta con degradacion limpia (se anota).
  2) VETO BAND-WALK (CLAUDE.md regla 1): un 'iman' (fade) contra una banda que
     CAMINA en 2 TF a favor de la tendencia (15m Y 1H fuera de banda en el sentido
     de la extension) NO es rebote elastico, es continuacion -> se VETA el fade.
  3) CONFIRMACION DE FLUJO (data/backtest/flow_intraday_<sym>.csv, 5 syms:
     spy/qqq/smh/nvda/mu, formato epoch,volC,volP,pc,spot): la señal LONG exige
     que el put/call NO este en su cuartil mas bajista (pc <= p75 del dia hasta t);
     SHORT exige pc >= p25. Sin fichero de flujo -> pasa (degradacion).
  4) GATE DE SPREAD optgate (LIVE-only): en produccion el adaptado llama
     optgate.opt_vehicle(sym) y descarta lo VETADO por spread; el cache de cadena
     es de AHORA, no se puede reproducir en fechas historicas, asi que aqui se
     declara como overlay en vivo (no medido en el backtest) — HONESTO.

Mismo FORMATO COMPARTIDO -> data/backtest/signals_yoel_adapted.csv, para puntuar
con real_option_scorer.py y comparar contra el puro. Señal-solamente, sin
look-ahead (los filtros usan solo flujo/base con epoch <= t).
"""
import csv, glob, json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import yoel_engine as YE  # reusa detect/agg/load/bb_at/sma_dir_at

# ---------------------------------------------------------- prior bollinger
def load_bollinger():
    try:
        return json.load(open("data/bollinger_plus.json"))
    except Exception:
        return {}

BOLL = load_bollinger()
def base_ok(sym):
    """(acepta?, nota). base p>=50 -> ok; sin registro -> ok con nota degradacion."""
    d = BOLL.get(sym.upper())
    if not d:
        return True, "sin_registro_boll"
    p = d.get("base", {}).get("p")
    if p is None:
        return True, "base_sd"
    return (p >= 50.0), f"base_p={p}"

# ---------------------------------------------------------- flujo intradia
def load_flow(sym):
    """lista (epoch, pc) ordenada; [] si no hay fichero."""
    path = f"data/backtest/flow_intraday_{sym.lower()}.csv"
    out = []
    try:
        for r in csv.reader(open(path)):
            if not r or r[0] == "epoch":
                continue
            try:
                out.append((int(r[0]), float(r[3])))
            except Exception:
                continue
    except Exception:
        return []
    return sorted(out)

def pctile(vals, q):
    if not vals:
        return None
    s = sorted(vals); i = q * (len(s) - 1)
    lo = int(i); frac = i - lo
    if lo + 1 < len(s):
        return s[lo] + frac * (s[lo + 1] - s[lo])
    return s[lo]

def flow_confirms(flow, t, side):
    """True si el flujo (put/call) NO contradice la direccion; True si no hay flujo."""
    if not flow:
        return True, "sin_flujo"
    day = t - t % 86400
    hist = [pc for (e, pc) in flow if e <= t and (e - e % 86400) == day]
    if len(hist) < 3:
        hist = [pc for (e, pc) in flow if e <= t]  # cae al historico global del dia si el dia es corto
    if len(hist) < 3:
        return True, "flujo_corto"
    cur = hist[-1]
    if side == "LONG":
        thr = pctile(hist, 0.75)
        return (cur <= thr), f"pc={cur:.2f}<=p75={thr:.2f}" if cur <= thr else f"pc={cur:.2f}>p75={thr:.2f}_VETO"
    else:
        thr = pctile(hist, 0.25)
        return (cur >= thr), f"pc={cur:.2f}>=p25={thr:.2f}" if cur >= thr else f"pc={cur:.2f}<p25={thr:.2f}_VETO"

# ------------------------------------------------------ veto band-walk (iman)
def bandwalk_veto(sym, t, side, kind):
    """veta el fade 'iman' si la banda CAMINA en 2 TF (15m Y 1H) a favor de la
    extension (continuacion, no rebote elastico)."""
    if kind != "iman":
        return False, ""
    R = YE.load(sym)
    if len(R) < 300:
        return False, ""
    M15 = YE.agg(R, 900); H = YE.agg(R, 3600)
    M15c = [b[4] for b in M15]; M15t = [b[0] for b in M15]
    Hc = [b[4] for b in H]; Ht = [b[0] for b in H]
    bb15 = YE.bb_at(M15c, M15t, t); bb1h = YE.bb_at(Hc, Ht, t)
    if not bb15 or not bb1h:
        return False, ""
    _, u15, l15, p15, _ = bb15
    _, u1h, l1h, p1h, _ = bb1h
    if side == "LONG":   # iman compra el suelo -> peligro si banda camina ABAJO en 15m Y 1H
        walk = (p15 <= l15) and (p1h <= l1h)
    else:                # iman vende el techo -> peligro si banda camina ARRIBA
        walk = (p15 >= u15) and (p1h >= u1h)
    return walk, ("band-walk_2TF" if walk else "")

def main():
    syms = sys.argv[1:] or [os.path.basename(f).split("bars3mo5m_")[1][:-4]
                            for f in sorted(glob.glob("data/backtest/bars3mo5m_*.csv"))]
    out = "data/backtest/signals_yoel_adapted.csv"
    n_by = {}; drops = {"base": 0, "flujo": 0, "bandwalk": 0}
    flow_cache = {}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "sym", "side", "kind", "ref_px", "target_px", "stop_px"])
        for sym in syms:
            ok_b, _ = base_ok(sym)
            if sym not in flow_cache:
                flow_cache[sym] = load_flow(sym)
            flow = flow_cache[sym]
            for (t, side, kind, ref) in YE.detect(sym):
                if not ok_b:
                    drops["base"] += 1; continue
                veto, _ = bandwalk_veto(sym, t, side, kind)
                if veto:
                    drops["bandwalk"] += 1; continue
                conf, _ = flow_confirms(flow, t, side)
                if not conf:
                    drops["flujo"] += 1; continue
                w.writerow([t, sym.upper(), side, kind, round(ref, 2), "", ""])
                n_by[kind] = n_by.get(kind, 0) + 1
    total = sum(n_by.values())
    print(f"YOEL ADAPTADO -> {out}  ({total} señales)")
    for k, n in sorted(n_by.items()):
        print(f"  {k:16s} n={n}")
    print(f"  descartadas: base<50={drops['base']}  band-walk={drops['bandwalk']}  flujo-contra={drops['flujo']}")
    print("  NOTA: gate optgate (spread) es overlay EN VIVO, no reproducible en historico -> no medido aqui.")

if __name__ == "__main__":
    main()
