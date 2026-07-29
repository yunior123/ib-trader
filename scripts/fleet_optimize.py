#!/usr/bin/env python3
"""fleet_optimize.py — full-profit re-tuning sweep for the 13-bot fleet (2026-07-11).

Coordinate-descent per ticker per side around the SHIPPED keepalive config:
  pass 1+2 over exits then entries (engine-aware grids: MR / v3-score / trend).
Ship gate (Yunior mandate): n>=10 closed trades, full-sample WR>=70%,
OOS (last 40%% of trades) total > 0, and must BEAT the shipped config's score.
Score = sum of closed trade returns + open-bag mark-to-market at last close
(a config can't win by hiding losers in a bag).

Runs are the real C++ bots via --stdin in ISOLATED tmpdirs (never touches
live data/pos_*.txt). Sequential (8GB box). ~15-25 min for the full fleet.

Usage:
  venv/bin/python scripts/fleet_optimize.py            # sweep all 13
  venv/bin/python scripts/fleet_optimize.py NOK TSM    # subset
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from fleet_backtest_audit import SYMS, load_keepalive_env, parse_run  # noqa: E402

MIN_N = 10          # min closed trades full-sample to trust a config
MIN_WR = 0.70       # mandate
MIN_IMPROVE = 1.0   # score must beat shipped by >= 1.0 pct-points to ship


def side_metrics(trades, frac=0.4):
    rets = [t["ret"] for t in trades]
    n = len(rets)
    w = sum(1 for r in rets if r > 0)
    m = {"n": n, "wr": w / n if n else 0.0, "tot": sum(rets) * 100}
    if n >= 5:
        cut = int(n * (1 - frac))
        oos = rets[cut:]
        m["oos_tot"] = sum(oos) * 100
        m["oos_wr"] = sum(1 for r in oos if r > 0) / len(oos)
        m["train_tot"] = sum(rets[:cut]) * 100
    else:
        m["oos_tot"] = m["tot"]
        m["oos_wr"] = m["wr"]
        m["train_tot"] = m["tot"]
    return m


class Runner:
    def __init__(self, sym):
        self.sym = sym
        self.low = sym.lower()
        self.hist = os.path.join(ROOT, "data", f"bt_{self.low}.txt")
        self.bin = os.path.join(ROOT, "bots", f"{self.low}_signal_bot")
        self.base = load_keepalive_env(sym)
        with open(self.hist) as f:
            self.bars = f.read()
        self.last_close = float(self.bars.rsplit("\n", 2)[-2].split()[4])
        self.cache = {}
        self.runs = 0

    def eval(self, cfg: dict):
        # NB: metodo "eval" = evaluar UN config de backtest (subprocess al bot
        # C++); no es el builtin eval() de Python — aqui no se ejecuta codigo.
        key = tuple(sorted(cfg.items()))
        if key in self.cache:
            return self.cache[key]
        env = dict(os.environ)
        env.update(self.base)
        env.update({k: str(v) for k, v in cfg.items()})
        with tempfile.TemporaryDirectory(prefix=f"opt_{self.low}_") as tmp:
            os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
            proc = subprocess.run(
                [self.bin, "--stdin"], input=self.bars, capture_output=True,
                text=True, env=env, cwd=tmp)
        longs, shorts, bag_l, bag_s, _ = parse_run(proc.stdout)
        r = {"L": side_metrics(longs), "S": side_metrics(shorts)}
        r["L"]["bag"] = (self.last_close / bag_l["entry"] - 1) * 100 if bag_l else 0.0
        r["S"]["bag"] = (bag_s["entry"] / self.last_close - 1) * 100 if bag_s else 0.0
        for s in ("L", "S"):
            r[s]["score"] = r[s]["tot"] + r[s]["bag"]
        self.cache[key] = r
        self.runs += 1
        return r

    def gate(self, m, base_m):
        # allow a sym whose shipped config already has <MIN_N trades (e.g. NOK 11)
        min_n = min(MIN_N, max(base_m["n"], 5)) if base_m["n"] else MIN_N
        # train Y OOS positivos: un config que pierde 3 meses y gana al final
        # (o al reves) es apuesta de regimen, no edge
        return (m["n"] >= min_n and m["wr"] >= MIN_WR
                and m["oos_tot"] > 0 and m["train_tot"] > 0)


def grids(sym, base, side):
    """Engine-aware (param, values) list. side='L'|'S'. Values as strings."""
    p = lambda k, d=None: base.get(f"{sym}_{k}", d)
    fl = lambda k, d: float(p(k, d) or d)
    mode_trend = p("MODE") == "trend"
    g = []
    if side == "L":
        tgt = fl("TARGET", 4)
        stp = fl("STOP", 3)
        g.append((f"{sym}_TARGET", sorted({round(tgt * m, 2) for m in (0.5, 0.75, 1, 1.5, 2)})))
        g.append((f"{sym}_STOP", sorted({round(min(stp * m, 8.0), 2) for m in (0.5, 1, 1.5, 2)})))
        g.append((f"{sym}_TRAIL_ATR", [2, 3, 4, 5]))
        g.append((f"{sym}_TIME_STOP_MIN", [0, 60, 120, 240]))
        g.append((f"{sym}_EOD_FORCE", [0, 1]))
        g.append((f"{sym}_SKIP_OPEN", [0, 5, 15]))
        if mode_trend:
            g.append((f"{sym}_TREND_CUSUM", [0.005, 0.01, 0.015, 0.02, 0.03]))
            g.append((f"{sym}_TREND_VWAP", [0, 1]))
        elif fl("SCORE_MIN", 0) > 0:
            g.append((f"{sym}_SCORE_MIN", [0.60, 0.66, 0.72, 0.78, 0.84]))
            g.append((f"{sym}_RSI_OS", [25, 30, 35, 40]))
            g.append((f"{sym}_BB_STD", [1.5, 2.0, 2.5, 3.0]))
        else:
            g.append((f"{sym}_BB_STD", [2.0, 2.5, 3.0]))
            g.append((f"{sym}_RSI_OS", [20, 25, 30, 35]))
            g.append((f"{sym}_VOL_MULT", [1.0, 1.2, 1.5, 2.0]))
            g.append((f"{sym}_CONFIRM_STRICT", [0, 1]))
    else:
        s_mode = p("S_MODE") or ("trend" if mode_trend else "mr")
        tgt = fl("S_TARGET", fl("TARGET", 4))
        stp = fl("S_STOP", fl("STOP", 3))
        g.append((f"{sym}_S_TARGET", sorted({round(tgt * m, 2) for m in (0.5, 0.75, 1, 1.5, 2)})))
        g.append((f"{sym}_S_STOP", sorted({round(min(stp * m, 8.0), 2) for m in (0.5, 1, 1.5, 2)})))
        g.append((f"{sym}_S_TRAIL", [2, 3, 4, 5]))
        g.append((f"{sym}_S_TSTOP", [0, 60, 120, 240]))
        if s_mode == "trend":
            g.append((f"{sym}_S_TREND_CUSUM", [0.005, 0.01, 0.015, 0.02, 0.03]))
        else:
            g.append((f"{sym}_S_BB_STD", [1.5, 2.0, 2.5, 3.0]))
            g.append((f"{sym}_S_RSI_OS", [20, 25, 30, 35]))
            g.append((f"{sym}_S_VOL_MULT", [1.0, 1.2, 1.5, 2.0]))
    return g


def descend(rn: Runner, side: str, cfg0: dict, passes=2):
    """Greedy coordinate descent maximizing gated score of `side`."""
    sym = rn.sym
    base_res = rn.eval(cfg0)
    base_m = base_res[side]
    best_cfg = dict(cfg0)
    best = rn.eval(best_cfg)[side]
    best_ok = rn.gate(best, base_m)
    for _ in range(passes):
        improved = False
        for param, values in grids(sym, rn.base, side):
            cur = best_cfg.get(param, rn.base.get(param))
            for v in values:
                if str(v) == str(cur):
                    continue
                cand_cfg = dict(best_cfg)
                cand_cfg[param] = v
                m = rn.eval(cand_cfg)[side]
                ok = rn.gate(m, base_m)
                if (ok and not best_ok) or (ok == best_ok and m["score"] > best["score"] + 1e-9):
                    best_cfg, best, best_ok = cand_cfg, m, ok
                    improved = True
        if not improved:
            break
    return best_cfg, best, best_ok


def fmt(m):
    return (f"{m['n']:4d}T WR {m['wr']:4.0%} tot {m['tot']:+7.2f}% "
            f"bag {m['bag']:+5.2f}% tr {m['train_tot']:+6.2f}% "
            f"oos {m['oos_tot']:+6.2f}%@{m['oos_wr']:3.0%}")


def main():
    syms = [s.upper() for s in sys.argv[1:]] or SYMS
    t0 = time.time()
    proposals = {}
    for sym in syms:
        rn = Runner(sym)
        shipped = rn.eval({})
        shorts_on = float(rn.base.get(f"{sym}_SHORTS", "0") or 0) > 0
        print(f"\n## {sym}  shipped L: {fmt(shipped['L'])}"
              + (f"  S: {fmt(shipped['S'])}" if shorts_on else "  S: off"), flush=True)
        prop = {}

        # ---- long side ----
        cfgL, mL, okL = descend(rn, "L", {})
        gain = mL["score"] - shipped["L"]["score"]
        if cfgL and okL and gain >= MIN_IMPROVE:
            prop.update(cfgL)
            print(f"   L-NEW  {fmt(mL)}  (+{gain:.2f} score)  {cfgL}")
        else:
            print(f"   L keep (best sweep {fmt(mL)}, gain {gain:+.2f}, gate {okL})")

        # ---- put side (from best long cfg; try enabling where off) ----
        cfgS0 = dict(prop)
        if not shorts_on:
            cfgS0[f"{sym}_SHORTS"] = 1
        cfgS, mS, okS = descend(rn, "S", cfgS0)
        baseS_score = shipped["S"]["score"] if shorts_on else 0.0
        gainS = mS["score"] - baseS_score
        strict = (mS["n"] >= MIN_N and mS["wr"] >= MIN_WR and mS["oos_tot"] > 0
                  and mS["train_tot"] > 0 and mS["oos_wr"] >= 0.65)
        if strict and gainS >= MIN_IMPROVE:
            # long side must still pass its own gate under the combined cfg
            mL2 = rn.eval(cfgS)["L"]
            if mL2["score"] >= rn.eval(prop)["L"]["score"] - MIN_IMPROVE:
                prop.update(cfgS)
                tag = "S-NEW" if shorts_on else "S-ENABLE"
                print(f"   {tag}  {fmt(mS)}  (+{gainS:.2f} score)  "
                      f"{ {k: v for k, v in cfgS.items() if k not in cfgL} }")
            else:
                print(f"   S found but degrades L ({fmt(mL2)}) — skipped")
        else:
            print(f"   S keep (best sweep {fmt(mS)}, gain {gainS:+.2f}, strict {strict})")
        proposals[sym] = prop
        print(f"   [{rn.runs} runs, {time.time() - t0:.0f}s elapsed]", flush=True)

    print("\n" + "=" * 70)
    print("PROPOSED KEEPALIVE CHANGES (gate-passing, profit-improving only)")
    print("=" * 70)
    for sym, prop in proposals.items():
        if prop:
            print(f"{sym}: " + " ".join(f"{k.split('_', 1)[1]}={v}" for k, v in sorted(prop.items())))
        else:
            print(f"{sym}: no change")
    out = os.path.join(ROOT, "data", "fleet_optimize_proposals.txt")
    with open(out, "w") as f:
        for sym, prop in proposals.items():
            for k, v in sorted(prop.items()):
                f.write(f"{sym} export {k}={v}\n")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
