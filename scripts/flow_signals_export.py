#!/usr/bin/env python3
"""flow_signals_export.py — replay historico del motor de flujo (flow_pulse v3/v4)
sobre data/whale_flow_hist.jsonl -> señales en el FORMATO COMPARTIDO
(docs/ENGINE-SCORING-SPEC.md) para el scorer unico.

Replica EXACTA del nucleo de spikes de scripts/flow_pulse.cpp:
  * ritmo por lado: dc=vc-prev.vc, dp=vp-prev.vp sobre mins=(ts-prev.ts)/60,
    solo si 1.0 <= mins <= 30.0 y dc>=0 y dp>=0.
  * EMA alfa 0.40 por lado (contratos/min); primer valor = seed.
  * SPIKE: ritmo >= 3.0x su EMA  Y  delta >= 2000 contratos.
  * dominancia 2x: calls solo si dc >= 2*dp; puts solo si dp >= 2*dc.
  * anti-artefacto: spike bilateral (ambos lados a la vez) o ritmo > 50x EMA
    -> mudo y SIN tocar la EMA (relleno del feed tras hueco).
  * cooldown 600 s por sym+lado (se consume aunque la señal quede vetada,
    igual que el cpp).
  * RTH: lunes-viernes 09:35-15:54 ET (hm >= 935 && hm < 1555).
  * VETO band-walk BB(20,2) 1m+5m con barras historicas (bars30d_<sym>.csv):
    ultima barra 1m COMPLETADA a <= 240 s del registro; cierre > banda sup en
    1m Y 5m = band-walk alcista -> veta el fade de SPIKE_CALLS; espejo abajo
    para SPIKE_PUTS. Sin barras suficientes -> sin veto (degradacion limpia).
    CERO look-ahead: solo barras con epoch+60 <= ts (1m) / epoch+300 <= ts (5m).

Señal emitida (tesis de reversion, tactica espada-ballena):
  SPIKE_PUTS  (panico vendedor) -> LONG  target +0.35%  stop -0.35%
  SPIKE_CALLS (climax comprador)-> SHORT target -0.35%  stop +0.35%
  ref_px = spot del registro (registros sin spot valido se descartan y cuentan).

Uso:
  flow_signals_export.py [--hist data/whale_flow_hist.jsonl]
      [--bars-dir data/backtest] [--out data/backtest/flow_signals.csv]
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SPIKE_X, SPIKE_MIN, EMA_A, COOLDOWN_S = 3.0, 2000.0, 0.40, 600
MOVE = 0.0035  # +-0.35%

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rth_open(ts: int) -> bool:
    lt = time.localtime(ts)  # replica localtime del cpp; Toronto == ET
    hm = lt.tm_hour * 100 + lt.tm_min
    return lt.tm_wday < 5 and 935 <= hm < 1555  # tm_wday: lunes=0 .. viernes=4


def load_1m(bars_dir: str, sym: str):
    for cand in (f"bars30d_{sym.lower()}.csv", f"bars30d_{sym}.csv"):
        p = os.path.join(bars_dir, cand)
        if os.path.isfile(p):
            rows = []
            with open(p) as f:
                for ln in f:
                    parts = ln.strip().split(",")
                    if len(parts) >= 5 and parts[0].isdigit():
                        rows.append((int(parts[0]), float(parts[4])))  # (epoch, close)
            rows.sort()
            return rows
    return None


def bb(closes):
    m = sum(closes) / len(closes)
    sd = math.sqrt(sum((c - m) ** 2 for c in closes) / len(closes))  # poblacional, como el cpp
    return m - 2 * sd, m + 2 * sd


class BandChecker:
    """Veto band-walk BB(20,2) 1m+5m — math de flow_pulse.cpp bands_of(),
    con barras historicas y cero look-ahead (solo barras cerradas <= ts)."""

    def __init__(self, bars_dir):
        self.bars_dir = bars_dir
        self.cache = {}

    def bands(self, sym, ts):
        """-> (ok, walk_up, walk_dn)"""
        if sym not in self.cache:
            self.cache[sym] = load_1m(self.bars_dir, sym)
        bars = self.cache[sym]
        if not bars:
            return False, False, False              # sin barras: sin veto
        # barras 1m COMPLETADAS al momento ts, ventana movil de 160 como el cpp
        done = [b for b in bars if b[0] + 60 <= ts][-160:]
        if len(done) < 25 or ts - done[-1][0] > 240:
            return False, False, False              # viejas/pocas: sin veto
        c1 = [c for _, c in done[-21:-1]]
        lo1, up1 = bb(c1)
        last = done[-1][1]
        a5 = {}                                     # 5m: cierre = ultimo del bucket
        for t, c in done:
            a5[t - t % 300] = c
        if len(a5) < 21:
            return True, False, False               # sin 5m suficiente: sin veto
        c5 = [a5[k] for k in sorted(a5)]
        last5 = c5[-1]
        lo5, up5 = bb(c5[-21:-1])
        return True, (last > up1 and last5 > up5), (last < lo1 and last5 < lo5)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hist", default=os.path.join(REPO, "data/whale_flow_hist.jsonl"))
    ap.add_argument("--bars-dir", default=os.path.join(REPO, "data/backtest"))
    ap.add_argument("--out", default=os.path.join(REPO, "data/backtest/flow_signals.csv"))
    args = ap.parse_args()

    checker = BandChecker(args.bars_dir)
    hist = {}       # sym -> {prev, ema_c, ema_p}
    cool = {}       # "SYM|SC"/"SYM|SP" -> ultimo disparo (ts del registro)
    sigs, stats = [], {"recs": 0, "spikes_c": 0, "spikes_p": 0, "vetoed": 0,
                       "artifacts": 0, "no_spot": 0, "cooldown": 0, "fuera_rth": 0}
    ts_min = ts_max = None

    def cooled(key, ts):
        if ts - cool.get(key, -10**12) < COOLDOWN_S:
            return False
        cool[key] = ts
        return True

    with open(args.hist) as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            ts, sym = int(r["ts"]), r["sym"]
            vc, vp = float(r["vc"]), float(r["vp"])
            spot = float(r.get("spot") or 0)
            stats["recs"] += 1
            ts_min = ts if ts_min is None else min(ts_min, ts)
            ts_max = ts if ts_max is None else max(ts_max, ts)
            h = hist.setdefault(sym, {"prev": None, "ema_c": -1.0, "ema_p": -1.0})
            prev = h["prev"]
            if prev is not None and ts > prev["ts"]:
                mins = (ts - prev["ts"]) / 60.0
                if 1.0 <= mins <= 30.0:
                    dc, dp = vc - prev["vc"], vp - prev["vp"]
                    if dc >= 0 and dp >= 0:
                        rc, rp = dc / mins, dp / mins
                        spike_c = h["ema_c"] > 0 and rc >= SPIKE_X * h["ema_c"] and dc >= SPIKE_MIN
                        spike_p = h["ema_p"] > 0 and rp >= SPIKE_X * h["ema_p"] and dp >= SPIKE_MIN
                        artifact = (spike_c and spike_p) or \
                                   (h["ema_c"] > 0 and rc > 50 * h["ema_c"]) or \
                                   (h["ema_p"] > 0 and rp > 50 * h["ema_p"])
                        if artifact:
                            stats["artifacts"] += 1
                            h["prev"] = {"ts": ts, "vc": vc, "vp": vp}
                            continue                 # mudo, EMA intacta (como el cpp)

                        def emit(kind, side):
                            if not (spot > 0 and math.isfinite(spot)):
                                stats["no_spot"] += 1
                                return
                            tgt = spot * (1 + MOVE) if side == "LONG" else spot * (1 - MOVE)
                            stp = spot * (1 - MOVE) if side == "LONG" else spot * (1 + MOVE)
                            sigs.append([ts, sym, side, kind,
                                         f"{spot:.4f}", f"{tgt:.4f}", f"{stp:.4f}"])

                        # SPIKE CALLS: climax comprador -> fade SHORT, salvo band-walk arriba
                        if spike_c and dc >= 2 * dp:
                            if not rth_open(ts):
                                stats["fuera_rth"] += 1
                            elif not cooled(sym + "|SC", ts):
                                stats["cooldown"] += 1
                            else:
                                stats["spikes_c"] += 1
                                ok, walk_up, _ = checker.bands(sym, ts)
                                if ok and walk_up:
                                    stats["vetoed"] += 1
                                else:
                                    emit("SPIKE_CALLS", "SHORT")
                        # SPIKE PUTS: panico vendedor -> rebote LONG, salvo band-walk abajo
                        if spike_p and dp >= 2 * dc:
                            if not rth_open(ts):
                                stats["fuera_rth"] += 1
                            elif not cooled(sym + "|SP", ts):
                                stats["cooldown"] += 1
                            else:
                                stats["spikes_p"] += 1
                                ok, _, walk_dn = checker.bands(sym, ts)
                                if ok and walk_dn:
                                    stats["vetoed"] += 1
                                else:
                                    emit("SPIKE_PUTS", "LONG")
                        h["ema_c"] = rc if h["ema_c"] < 0 else EMA_A * rc + (1 - EMA_A) * h["ema_c"]
                        h["ema_p"] = rp if h["ema_p"] < 0 else EMA_A * rp + (1 - EMA_A) * h["ema_p"]
            h["prev"] = {"ts": ts, "vc": vc, "vp": vp}

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "sym", "side", "kind", "ref_px", "target_px", "stop_px"])
        w.writerows(sigs)

    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M ET", time.localtime(t)) if t else "s/d"
    print(f"flujo: {stats['recs']} registros, ventana {fmt(ts_min)} .. {fmt(ts_max)}")
    print("DECLARADO: whale_flow_hist.jsonl existe SOLO desde 2026-07-21 — "
          "3 meses de flujo NO EXISTEN; n minusculo por diseño.")
    print(f"spikes calls={stats['spikes_c']} puts={stats['spikes_p']} | "
          f"vetados band-walk={stats['vetoed']} artefactos={stats['artifacts']} "
          f"cooldown={stats['cooldown']} fuera_rth={stats['fuera_rth']} "
          f"sin_spot={stats['no_spot']}")
    print(f"señales exportadas: {len(sigs)} -> {args.out}")


if __name__ == "__main__":
    main()
