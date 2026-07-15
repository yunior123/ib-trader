#!/usr/bin/env python3
"""fleet_wfo.py — walk-forward optimization v2, full math (2026-07-11).

Metodologia (refs: vectorbt robustness/WFO, TonyMa1/walk-forward-backtester,
Lopez de Prado CPCV): sobre los 90d reales de Alpaca IEX 1m,
  1. split TEMPORAL 60/40: train = primeros ~54d, OOS = ultimos ~36d INTACTO.
  2. la seleccion de parametros ve SOLO train (WR>=70, PF>=1.2, tot>0).
  3. candidatos ordenados por train-profit se validan EN ORDEN contra OOS
     (primero que pasa gana — sin maximizar sobre OOS = sin leakage).
  4. test de meseta (parameter plateau): vecinos +-1 paso del config elegido
     deben conservar la mayoria del edge en train (pico aislado = overfit).
  5. metricas full-math por lado: WR, total, PF, expectancy/trade, t-stat,
     max drawdown de la curva de trades, max racha perdedora, bag MTM.
Truco de derivacion OOS exacta sin timestamps: el replay es DETERMINISTICO,
el prefijo de trades del run completo == trades del run train-slice, asi que
OOS_trades = full_trades[len(train_trades):].

Lado PUT: obligatorio disparar en los 13 (orden 2026-07-11 "todos tienen que
disparar") — si nada valida OOS se embarca el mejor best-effort (max WR con
tot>0) y se reporta honesto.

Usage: venv/bin/python scripts/fleet_wfo.py [SYM ...]
"""

# ==== GUARDIA NO-ALPACA (orden Yunior 2026-07-15 "no alpaca all over") ====
# Este script de backtest aun trae historia via Alpaca REST. Migracion a
# reqHistoricalData IBKR pendiente (chunks de 30d por pacing). Hasta entonces
# NO corre salvo override explicito.
import os as _os
if _os.environ.get("ALPACA_LEGACY") != "1":
    raise SystemExit(f"{__file__}: usa Alpaca (prohibido 2026-07-15). "
                     "Migrar a IBKR hist o correr con ALPACA_LEGACY=1.")
# ==========================================================================

from __future__ import annotations

import itertools
import math
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from fleet_backtest_audit import SYMS, load_keepalive_env, parse_run  # noqa: E402

TRAIN_FRAC = 0.6
T_MIN_N, T_MIN_WR, T_MIN_PF = 8, 0.70, 1.2      # train gate
O_MIN_N, O_MIN_WR = 3, 0.55                     # OOS gate (muestras cortas)
TOP_K = 10                                       # candidatos validados en orden


def full_math(trades):
    rets = [t["ret"] for t in trades]
    n = len(rets)
    w = sum(1 for r in rets if r > 0)
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    mean = sum(rets) / n if n else 0.0
    var = sum((r - mean) ** 2 for r in rets) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    eq = mdd = peak = 0.0
    streak = worst_streak = 0
    for r in rets:
        eq += r
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        streak = streak + 1 if r <= 0 else 0
        worst_streak = max(worst_streak, streak)
    return {
        "n": n, "wr": w / n if n else 0.0, "tot": sum(rets) * 100,
        "pf": gw / gl if gl > 1e-12 else (99.0 if gw > 0 else 0.0),
        "exp": mean * 100,
        "tstat": mean / (sd / math.sqrt(n)) if n > 1 and sd > 1e-12 else 0.0,
        "mdd": mdd * 100, "streak": worst_streak,
    }


class WFORunner:
    def __init__(self, sym):
        self.sym = sym
        self.low = sym.lower()
        self.bin = os.path.join(ROOT, f"{self.low}_signal_bot")
        self.base = load_keepalive_env(sym)
        lines = [ln for ln in open(os.path.join(ROOT, "data", f"bt_{self.low}.txt")) if ln.strip()]
        t0, t1 = float(lines[0].split()[0]), float(lines[-1].split()[0])
        cutoff = t0 + TRAIN_FRAC * (t1 - t0)
        self.train_bars = "".join(ln for ln in lines if float(ln.split(None, 1)[0]) <= cutoff)
        self.full_bars = "".join(lines)
        self.train_last = float(self.train_bars.rsplit("\n", 2)[-2].split()[4])
        self.full_last = float(lines[-1].split()[4])
        self.cache = {}
        self.runs = 0

    def _replay(self, cfg, bars):
        env = dict(os.environ)
        env.update(self.base)
        env.update({k: str(v) for k, v in cfg.items()})
        with tempfile.TemporaryDirectory(prefix=f"wfo_{self.low}_") as tmp:
            os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
            proc = subprocess.run([self.bin, "--stdin"], input=bars,
                                  capture_output=True, text=True, env=env, cwd=tmp)
        self.runs += 1
        return parse_run(proc.stdout)

    def train(self, cfg):
        key = ("T", tuple(sorted(cfg.items())))
        if key not in self.cache:
            longs, shorts, bag_l, bag_s, _ = self._replay(cfg, self.train_bars)
            r = {"L": full_math(longs), "S": full_math(shorts),
                 "_trades": {"L": longs, "S": shorts}}
            r["L"]["bag"] = (self.train_last / bag_l["entry"] - 1) * 100 if bag_l else 0.0
            r["S"]["bag"] = (bag_s["entry"] / self.train_last - 1) * 100 if bag_s else 0.0
            for s in ("L", "S"):
                r[s]["score"] = r[s]["tot"] + r[s]["bag"]
            self.cache[key] = r
        return self.cache[key]

    def oos(self, cfg):
        """OOS = trades del run completo mas alla del prefijo train (exacto)."""
        key = ("F", tuple(sorted(cfg.items())))
        if key not in self.cache:
            longs, shorts, bag_l, bag_s, _ = self._replay(cfg, self.full_bars)
            tr = self.train(cfg)["_trades"]
            r = {}
            for side, all_t in (("L", longs), ("S", shorts)):
                cut = len(tr[side])
                r[side] = full_math(all_t[cut:])
                r[side]["full"] = full_math(all_t)
            r["L"]["bag"] = (self.full_last / bag_l["entry"] - 1) * 100 if bag_l else 0.0
            r["S"]["bag"] = (bag_s["entry"] / self.full_last - 1) * 100 if bag_s else 0.0
            self.cache[key] = r
        return self.cache[key]


def entry_grids(sym, base, side):
    p = lambda k, d=None: base.get(f"{sym}_{k}", d)
    if side == "L":
        if p("MODE") == "trend":
            return [{f"{sym}_TREND_CUSUM": c, f"{sym}_TREND_VWAP": v}
                    for c in (0.005, 0.01, 0.015, 0.02, 0.03) for v in (0, 1)]
        if float(p("SCORE_MIN", 0) or 0) > 0:
            return [{f"{sym}_SCORE_MIN": s, f"{sym}_RSI_OS": r}
                    for s in (0.60, 0.66, 0.72, 0.78) for r in (25, 30, 35)]
        return [{f"{sym}_BB_STD": b, f"{sym}_RSI_OS": r, f"{sym}_VOL_MULT": v}
                for b, r, v in itertools.product((1.5, 2.0, 2.5, 3.0),
                                                 (20, 25, 30, 35), (1.0, 1.2, 1.5))]
    out = []
    for cu in (0.005, 0.01, 0.015, 0.02, 0.03):
        out.append({f"{sym}_S_MODE": "trend", f"{sym}_S_TREND_CUSUM": cu})
    for b, r, v in itertools.product((1.5, 2.0, 2.5, 3.0), (20, 25, 30, 35), (1.0, 1.2, 1.5)):
        out.append({f"{sym}_S_MODE": "mr", f"{sym}_S_BB_STD": b,
                    f"{sym}_S_RSI_OS": r, f"{sym}_S_VOL_MULT": v})
    return out


def exit_grids(sym, base, side):
    fl = lambda k, d: float(base.get(f"{sym}_{k}", d) or d)
    if side == "L":
        tgt, stp = fl("TARGET", 4), fl("STOP", 3)
        return [(f"{sym}_TARGET", sorted({round(tgt * m, 2) for m in (0.5, 0.75, 1, 1.5, 2)})),
                (f"{sym}_STOP", sorted({round(min(stp * m, 8.0), 2) for m in (0.5, 1, 1.5, 2)})),
                (f"{sym}_TRAIL_ATR", [2, 3, 4, 5]),
                (f"{sym}_TIME_STOP_MIN", [0, 60, 120, 240]),
                (f"{sym}_FLOOR", [0.25, 0.5, 1, 2]),
                (f"{sym}_EOD_FORCE", [0, 1]),
                (f"{sym}_SKIP_OPEN", [0, 5, 15]),
                (f"{sym}_CANDLE", [0, 1])]
    tgt, stp = fl("S_TARGET", fl("TARGET", 4)), fl("S_STOP", fl("STOP", 3))
    return [(f"{sym}_S_TARGET", sorted({round(tgt * m, 2) for m in (0.5, 0.75, 1, 1.5, 2)})),
            (f"{sym}_S_STOP", sorted({round(min(stp * m, 8.0), 2) for m in (0.5, 1, 1.5, 2)})),
            (f"{sym}_S_TRAIL", [2, 3, 4, 5]),
            (f"{sym}_S_TSTOP", [0, 60, 120, 240]),
            (f"{sym}_S_FLOOR", [0.25, 0.5, 1, 2]),
            (f"{sym}_S_CANDLE", [0, 1])]


def train_gate(m):
    return m["n"] >= T_MIN_N and m["wr"] >= T_MIN_WR and m["tot"] > 0 and m["pf"] >= T_MIN_PF


def plateau_ok(rn, cfg, side, ref_tot):
    """Vecinos +-1 paso en train deben conservar >=40% del edge (mediana)."""
    neigh_tots = []
    for param, values in exit_grids(rn.sym, rn.base, side):
        if param not in cfg:
            continue
        vals = [str(v) for v in values]
        cur = str(cfg[param])
        if cur not in vals:
            continue
        i = vals.index(cur)
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                c2 = dict(cfg)
                c2[param] = values[j]
                neigh_tots.append(rn.train(c2)[side]["tot"])
        if len(neigh_tots) >= 6:
            break
    if not neigh_tots:
        return True
    neigh_tots.sort()
    med = neigh_tots[len(neigh_tots) // 2]
    return med >= 0.4 * ref_tot


def optimize_side(rn, side, base_cfg):
    sym = rn.sym
    seen = []
    # etapa 1: entradas coarse, ranking SOLO train
    scored = []
    for e in entry_grids(sym, rn.base, side):
        cfg = dict(base_cfg)
        cfg.update(e)
        if side == "S":
            cfg[f"{sym}_SHORTS"] = 1
        m = rn.train(cfg)[side]
        seen.append((cfg, m))
        if m["n"] >= T_MIN_N:
            scored.append((m["score"], cfg))
    scored.sort(key=lambda x: -x[0])
    # etapa 2: descent de salidas desde top-4 (solo train)
    for _, start in scored[:4]:
        best, bm = dict(start), rn.train(start)[side]
        for _ in range(2):
            improved = False
            for param, values in exit_grids(sym, rn.base, side):
                for v in values:
                    if str(v) == str(best.get(param, rn.base.get(param))):
                        continue
                    c2 = dict(best)
                    c2[param] = v
                    m2 = rn.train(c2)[side]
                    seen.append((c2, m2))
                    better = (min(m2["wr"], T_MIN_WR), m2["score"]) > (min(bm["wr"], T_MIN_WR), bm["score"])
                    if m2["n"] >= T_MIN_N and better:
                        best, bm, improved = c2, m2, True
            if not improved:
                break
        seen.append((best, bm))
    # etapa 3: candidatos train-gated por profit desc -> validar OOS EN ORDEN
    cands, keys = [], set()
    for cfg, m in seen:
        k = tuple(sorted(cfg.items()))
        if k not in keys and train_gate(m):
            keys.add(k)
            cands.append((m["score"], cfg, m))
    cands.sort(key=lambda x: -x[0])
    for _, cfg, mt in cands[:TOP_K]:
        mo = rn.oos(cfg)[side]
        if (mo["n"] >= O_MIN_N and mo["tot"] > 0 and mo["wr"] >= O_MIN_WR
                and plateau_ok(rn, cfg, side, mt["tot"])):
            return cfg, mt, mo, "VALIDATED"
    # best-effort (PUT obligatorio): mejor WR train con tot>0
    be = [(min(m["wr"], T_MIN_WR), m["score"], cfg, m) for cfg, m in seen
          if m["n"] >= T_MIN_N and m["tot"] > 0]
    if be:
        _, _, cfg, mt = max(be, key=lambda x: (x[0], x[1]))
        return cfg, mt, rn.oos(cfg)[side], "BEST-EFFORT"
    return None, None, None, "NONE"


def fmt(m):
    if not m:
        return "-"
    return (f"{m['n']}T WR {m['wr']:.0%} tot {m['tot']:+.2f}% pf {m['pf']:.2f} "
            f"exp {m['exp']:+.3f}% t {m['tstat']:+.1f} dd {m['mdd']:+.1f}% "
            f"racha {m['streak']}")


def main():
    syms = [s.upper() for s in sys.argv[1:]] or SYMS
    t0 = time.time()
    ship = {}
    for sym in syms:
        rn = WFORunner(sym)
        cur = rn.oos({})
        print(f"\n## {sym}  actual L full: {fmt(cur['L'].get('full'))} | "
              f"oos: {fmt(cur['L'])}", flush=True)
        prop = {}
        # LONG
        cfgL, mtL, moL, st = optimize_side(rn, "L", {})
        if st == "VALIDATED" and cfgL:
            curL = cur["L"].get("full", {"tot": -999})
            newL = rn.oos(cfgL)["L"]["full"]
            if newL["tot"] + rn.oos(cfgL)["L"]["bag"] > curL["tot"] + cur["L"]["bag"] + 1.0:
                prop.update(cfgL)
                print(f"   L {st}: train {fmt(mtL)}\n              oos {fmt(moL)}\n     cfg {cfgL}")
            else:
                print(f"   L validado pero no supera al actual — keep")
        else:
            print(f"   L {st} — keep actual")
        # PUT (obligatorio)
        cfgS, mtS, moS, st = optimize_side(rn, "S", dict(prop))
        if cfgS:
            prop.update(cfgS)
            prop[f"{sym}_SHORTS"] = 1
            print(f"   S {st}: train {fmt(mtS)}\n              oos {fmt(moS)}\n     cfg "
                  f"{ {k: v for k, v in cfgS.items() if k.startswith(sym + '_S') or 'SHORTS' in k} }")
        else:
            print(f"   S {st}: ni un config con trades>=8 y tot>0 — PUT queda en radar-only")
        ship[sym] = prop
        print(f"   [{rn.runs} replays, {time.time() - t0:.0f}s total]", flush=True)

    out = os.path.join(ROOT, "data", "fleet_wfo_ship.txt")
    with open(out, "w") as f:
        for sym, prop in ship.items():
            for k, v in sorted(prop.items()):
                f.write(f"{sym} export {k}={v}\n")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
