#!/usr/bin/env python3
"""scorer.py — EL puntuador unico del formato de señales compartido (E1H).

Formato de señal (CSV, una por linea, header opcional):
    epoch,sym,side,kind,ref_px,target_px,stop_px
    side = LONG | SHORT ; ref_px = precio al disparar la señal.

Reglas de puntuacion (fuente de verdad: docs/ENGINE-SCORING-SPEC.md):
  * Entrada  = OPEN de la SIGUIENTE barra 5m tras epoch (barra con start > epoch).
  * Recorre barras 5m desde la barra de entrada (inclusive), horizonte 24 barras.
  * LONG : stop si low <= stop_px ; target si high >= target_px.
    SHORT: stop si high >= stop_px ; target si low <= target_px.
  * Si en una MISMA barra caben stop y target -> cuenta STOP (conservador).
  * GAP HONESTO (2026-07-23): si el OPEN de una barra ya esta mas alla del
    stop/target, el fill real es el OPEN, no el nivel (gap overnight/earnings
    o salto intrabar entre señal y entrada). Antes se puntuaba al nivel:
    un gap-through-stop salia mejor de lo real (mentia a favor).
    Stop-first tambien en el open. Se cuenta cuantas señales cruzaron un
    corte de sesion (>1 h entre barras) dentro de su ventana: overnight_cross.
  * Ni target ni stop en el horizonte -> TIMEOUT (bucket aparte, PnL al cierre
    del horizonte = close de la ultima barra disponible dentro del horizonte).
  * SPREAD: el PnL bruto entra/sale al OPEN sin coste. El reporte global añade
    medianas netas a 2 y 5 bps POR LADO (4/10 bps ida+vuelta) — impacto real
    sobre un target de +-35 bps.
  * WR estricto = wins / (wins + losses). TIMEOUT no entra en el WR.
  * Sin barras tras el epoch -> señal SKIPPED (contada aparte, fuera de n).
  * JAMAS look-ahead: la entrada y todas las barras usadas empiezan tras epoch.

Barras: dir con bars3mo5m_<sym>.csv (5m) o bars30d_<sym>.csv (1m -> se agrega
a 5m: o=primera, h=max, l=min, c=ultima, v=suma, bucket epoch-epoch%300).
Formato de barra: epoch,o,h,l,c,v (header opcional).

Salida: data/backtest/scores_<name>.json + tabla por stdout.

Uso:
    scorer.py --name flow --bars-dir data/backtest señales1.csv [señales2.csv ...]
    (opcional) --horizon 24  --engine "flow_pulse v4 replay"  --out-dir data/backtest
"""

import argparse
import csv
import json
import math
import os
import sys
import time

HORIZON_DEFAULT = 24  # barras 5m (2 horas)
Z95 = 1.959963984540054


def wilson_lo(wins: int, n: int, z: float = Z95) -> float:
    """Cota inferior Wilson 95% de la proporcion wins/n. n = wins+losses."""
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    rad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (center - rad) / denom)


def load_bars_5m(bars_dir: str, sym: str):
    """Devuelve lista ordenada de (epoch,o,h,l,c) en 5m, o None si no hay datos.
    Prioridad: bars3mo5m_<sym>.csv (nativo 5m) -> bars30d_<sym>.csv (1m -> 5m)."""
    cand_5m = [f"bars3mo5m_{sym.lower()}.csv", f"bars3mo5m_{sym}.csv"]
    cand_1m = [f"bars30d_{sym.lower()}.csv", f"bars30d_{sym}.csv"]
    path5 = next((os.path.join(bars_dir, c) for c in cand_5m
                  if os.path.isfile(os.path.join(bars_dir, c))), None)
    path1 = next((os.path.join(bars_dir, c) for c in cand_1m
                  if os.path.isfile(os.path.join(bars_dir, c))), None)
    rows = []
    path = path5 or path1
    if path is None:
        return None
    with open(path) as f:
        for ln in f:
            parts = ln.strip().split(",")
            if len(parts) < 5 or not parts[0].isdigit():
                continue  # header o basura
            try:
                rows.append((int(parts[0]), float(parts[1]), float(parts[2]),
                             float(parts[3]), float(parts[4])))
            except ValueError:
                continue
    if not rows:
        return None
    rows.sort(key=lambda r: r[0])
    if path5:
        return rows
    # agregacion 1m -> 5m
    agg = {}
    for e, o, h, l, c in rows:
        b = e - e % 300
        cur = agg.get(b)
        if cur is None:
            agg[b] = [b, o, h, l, c]
        else:
            cur[2] = max(cur[2], h)
            cur[3] = min(cur[3], l)
            cur[4] = c
    return [tuple(v) for _, v in sorted(agg.items())]


SESSION_GAP_S = 3600  # >1 h entre barras 5m = corte de sesion (overnight/halt)


def score_signal(sig, bars, horizon):
    """Puntua una señal contra sus barras 5m.
    Devuelve (resultado, pnl_bps, cruzo_sesion) con resultado en
    {WIN, LOSS, TIMEOUT, SKIP}. cruzo_sesion = la ventana usada salto un
    corte de sesion (>1 h entre barras) antes de resolver."""
    epoch, side, target, stop = sig["epoch"], sig["side"], sig["target"], sig["stop"]
    # entrada: OPEN de la primera barra con start > epoch (cero look-ahead)
    i0 = None
    for i, b in enumerate(bars):
        if b[0] > epoch:
            i0 = i
            break
    if i0 is None:
        return "SKIP", 0.0, False
    entry = bars[i0][1]
    if entry <= 0:
        return "SKIP", 0.0, False
    window = bars[i0:i0 + horizon]
    sgn = 1.0 if side == "LONG" else -1.0

    def bps(exit_px):
        return sgn * (exit_px - entry) / entry * 1e4

    crossed = False
    prev_e = window[0][0]
    for e, o, h, l, c in window:
        if e - prev_e > SESSION_GAP_S:
            crossed = True
        prev_e = e
        # GAP honesto: open ya mas alla del nivel -> fill al OPEN (stop primero)
        if side == "LONG":
            gap_stop, gap_tgt = o <= stop, o >= target
        else:
            gap_stop, gap_tgt = o >= stop, o <= target
        if gap_stop:
            return "LOSS", bps(o), crossed
        if gap_tgt:
            return "WIN", bps(o), crossed
        if side == "LONG":
            hit_stop, hit_tgt = l <= stop, h >= target
        else:
            hit_stop, hit_tgt = h >= stop, l <= target
        if hit_stop:            # stop y target en la misma barra -> gana el STOP
            return "LOSS", bps(stop), crossed
        if hit_tgt:
            return "WIN", bps(target), crossed
    # timeout: PnL al cierre de la ultima barra disponible dentro del horizonte
    return "TIMEOUT", bps(window[-1][4]), crossed


def read_signals(paths):
    sigs = []
    for p in paths:
        with open(p) as f:
            for row in csv.reader(f):
                if len(row) < 7 or row[0].strip().lower() == "epoch":
                    continue
                try:
                    sigs.append({
                        "epoch": int(float(row[0])), "sym": row[1].strip().upper(),
                        "side": row[2].strip().upper(), "kind": row[3].strip(),
                        "ref": float(row[4]), "target": float(row[5]),
                        "stop": float(row[6]),
                    })
                except ValueError:
                    print(f"[scorer] fila invalida en {p}: {row}", file=sys.stderr)
    bad = [s for s in sigs if s["side"] not in ("LONG", "SHORT")]
    for s in bad:
        print(f"[scorer] side invalido, descartada: {s}", file=sys.stderr)
    return [s for s in sigs if s["side"] in ("LONG", "SHORT")]


def median(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


SPREAD_SIDES_BPS = (2.0, 5.0)  # sensibilidad de spread, bps POR LADO


def bucket_stats(results):
    """results: lista de (resultado, pnl_bps, cruzo_sesion)."""
    wins = sum(1 for r, _, _ in results if r == "WIN")
    losses = sum(1 for r, _, _ in results if r == "LOSS")
    touts = sum(1 for r, _, _ in results if r == "TIMEOUT")
    decided = wins + losses
    pnls = [p for r, p, _ in results if r != "SKIP"]
    return {
        "n": wins + losses + touts,
        "wins": wins, "losses": losses, "timeouts": touts,
        "wr": round(wins / decided, 4) if decided else None,
        "wilson_lo": round(wilson_lo(wins, decided), 4) if decided else None,
        "pnl_bps_median": round(median(pnls), 2) if pnls else None,
        "timeout_pnl_bps_median": round(
            median([p for r, p, _ in results if r == "TIMEOUT"]), 2) if touts else None,
        "overnight_cross": sum(1 for _, _, x in results if x),
    }


def spread_impact(results):
    """Impacto del spread sobre el PnL bruto: resta 2*bps_por_lado a cada
    trade (entrada+salida). No cambia el orden stop/target — cambia el neto."""
    out = {}
    pnls = [p for r, p, _ in results if r != "SKIP"]
    win_pnls = [p for r, p, _ in results if r == "WIN"]
    for side_bps in SPREAD_SIDES_BPS:
        rt = 2 * side_bps
        net = [p - rt for p in pnls]
        out[f"{side_bps:g}bps_side"] = {
            "round_trip_bps": rt,
            "pnl_bps_median_net": round(median(net), 2) if net else None,
            "wins_net_negative": sum(1 for p in win_pnls if p - rt <= 0),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("signals", nargs="+", help="CSV(s) de señales formato compartido")
    ap.add_argument("--name", required=True, help="nombre -> scores_<name>.json")
    ap.add_argument("--bars-dir", default="data/backtest")
    ap.add_argument("--out-dir", default="data/backtest")
    ap.add_argument("--horizon", type=int, default=HORIZON_DEFAULT)
    ap.add_argument("--engine", default=None, help="etiqueta del motor (default=name)")
    args = ap.parse_args()

    sigs = read_signals(args.signals)
    bars_cache, per, skipped = {}, {}, 0
    for s in sigs:
        sym = s["sym"]
        if sym not in bars_cache:
            bars_cache[sym] = load_bars_5m(args.bars_dir, sym)
        bars = bars_cache[sym]
        if bars is None:
            skipped += 1
            print(f"[scorer] sin barras para {sym}, señal SKIPPED", file=sys.stderr)
            continue
        res, pnl, crossed = score_signal(s, bars, args.horizon)
        if res == "SKIP":
            skipped += 1
            continue
        per.setdefault(sym, []).append((res, pnl, crossed))

    por_ticker = {sym: bucket_stats(rs) for sym, rs in sorted(per.items())}
    all_rs = [r for rs in per.values() for r in rs]
    out = {
        "engine": args.engine or args.name,
        "spec": "docs/ENGINE-SCORING-SPEC.md",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "horizon_bars_5m": args.horizon,
        "signals_files": args.signals,
        "skipped_sin_barras": skipped,
        "por_ticker": por_ticker,
        "global": bucket_stats(all_rs),
        "spread_impact_global": spread_impact(all_rs),
    }
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"scores_{args.name}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)

    # tabla legible
    g = out["global"]
    hdr = f"{'ticker':<8}{'n':>4}{'win':>5}{'loss':>5}{'tout':>5}{'WR':>7}{'Wilson':>8}{'PnL med':>9}"
    print(f"\n== scores_{args.name} | motor: {out['engine']} | horizonte {args.horizon}x5m ==")
    print(hdr)
    print("-" * len(hdr))
    fmt = lambda v, pct=False: ("   s/d" if v is None else
                                (f"{v*100:5.1f}%" if pct else f"{v:8.1f}"))
    for sym, st in por_ticker.items():
        print(f"{sym:<8}{st['n']:>4}{st['wins']:>5}{st['losses']:>5}{st['timeouts']:>5}"
              f" {fmt(st['wr'], True)} {fmt(st['wilson_lo'], True)}{fmt(st['pnl_bps_median'])}")
    print("-" * len(hdr))
    print(f"{'GLOBAL':<8}{g['n']:>4}{g['wins']:>5}{g['losses']:>5}{g['timeouts']:>5}"
          f" {fmt(g['wr'], True)} {fmt(g['wilson_lo'], True)}{fmt(g['pnl_bps_median'])}")
    si = out["spread_impact_global"]
    print(f"PnL med bruto {fmt(g['pnl_bps_median'])} bps | "
          f"neto -2bps/lado {fmt(si['2bps_side']['pnl_bps_median_net'])} "
          f"(wins->neg {si['2bps_side']['wins_net_negative']}) | "
          f"neto -5bps/lado {fmt(si['5bps_side']['pnl_bps_median_net'])} "
          f"(wins->neg {si['5bps_side']['wins_net_negative']})")
    print(f"overnight_cross (ventanas que saltaron corte de sesion): {g['overnight_cross']}")
    if skipped:
        print(f"skipped (sin barras/entrada): {skipped}")
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
