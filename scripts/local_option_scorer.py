#!/usr/bin/env python3
"""local_option_scorer.py — puntua CSVs de señales sobre la PRIMA REAL del dia
usando las FOTOS LOCALES de cadena (data/history/<fecha>/opt_chain_<sym>_HHMM.txt),
sin depender de Polygon (que no tiene el dia en curso).

Vehiculo: contrato ATM del vencimiento elegido (0dte = el mas cercano; next = el
siguiente). ENTRADA al ASK, SALIDA al BID -> el spread bid-ask REAL esta incluido.
Sin comisiones (se declara). Sin stop: la prima es la perdida maxima (metodo de
la casa). TP configurable (+30/+50/+100%).

Sin look-ahead: el epoch de una señal es el START de la barra que dispara, asi
que la entrada se busca en la primera foto de cadena con epoch >= señal + duracion
de barra (`--bar-secs`). Las fotos son cada 5 min: ese retraso es real y se declara.

Uso:
  local_option_scorer.py --date 2026-07-24 --bars-tmpl 'data/backtest/fri/bars5m_{sym}.csv' \
      señales.csv:60 otras.csv:900 ...
  (cada CSV con ":<bar_secs>" = duracion de la barra que lo genera)
"""
import csv, glob, json, math, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
os.environ["TZ"] = "America/New_York"; time.tzset()

MIN_ASK = 0.05          # primas < 5c: el +100% es ruido de tick -> fuera
MAX_ENTRY_LAG = 900     # si no hay foto de cadena en 15 min, la señal no se puede operar


# --------------------------------------------------------------- cadenas locales
def load_chains(date, syms=None):
    """sym -> [(epoch, spot, {(strike,right,exp): (bid,ask,vol,oi)})] ordenado."""
    out = {}
    for f in sorted(glob.glob(f"data/history/{date}/opt_chain_*_[0-9][0-9][0-9][0-9].txt")):
        sym = os.path.basename(f).split("_")[2]
        if syms and sym not in syms:
            continue
        try:
            lines = open(f).read().split("\n")
        except Exception:
            continue
        if not lines or not lines[0].startswith("#"):
            continue
        ep = spot = None
        for part in lines[0].split("|"):
            p = part.strip().split()
            if len(p) == 2 and p[0] == "epoch":
                ep = int(p[1])
            elif len(p) == 2 and p[0] == "spot":
                spot = float(p[1])
        if ep is None or spot is None:
            continue
        q = {}
        for ln in lines[2:]:
            p = ln.split()
            if len(p) < 7:
                continue
            try:
                k = float(p[0]); right = p[1]; exp = p[2]
                bid = float(p[3]); ask = float(p[4]); vol = float(p[5]); oi = float(p[6])
            except Exception:
                continue
            if ask <= 0 or bid < 0:      # -1 = fuera de ventana; NO es precio 0
                continue
            q[(k, right, exp)] = (bid, ask, vol, oi)
        if q:
            out.setdefault(sym, []).append((ep, spot, q))
    for s in out:
        out[s].sort(key=lambda x: x[0])
    return out


def pick_contract(snap, right, exp_mode, spot):
    """(strike, exp, bid, ask) del ATM del vencimiento pedido en esta foto."""
    _, snap_spot, q = snap
    exps = sorted({e for (_, r, e) in q if r == right})
    if not exps:
        return None
    exp = exps[0] if exp_mode == "0dte" else (exps[1] if len(exps) > 1 else exps[0])
    cands = [(k, v) for (k, r, e), v in q.items() if r == right and e == exp and v[1] >= MIN_ASK]
    if not cands:
        return None
    k, (bid, ask, vol, oi) = min(cands, key=lambda x: abs(x[0] - snap_spot))
    return (k, exp, bid, ask, oi)


def score_option(rows, chains, bar_secs, tp, exp_mode, max_prem=None):
    """rows: (t, sym, side, kind, ref). Devuelve buckets kind -> [w,n,sum_ret] +
    lista de trades."""
    buckets = {}
    trades = []
    skipped = {"sin_cadena": 0, "sin_foto": 0, "sin_contrato": 0, "caro": 0}
    for (t, sym, side, kind, ref) in rows:
        ch = chains.get(sym.lower())
        if not ch:
            skipped["sin_cadena"] += 1; continue
        t_entry = t + bar_secs
        snap = next((s for s in ch if s[0] >= t_entry), None)
        if snap is None or snap[0] - t_entry > MAX_ENTRY_LAG:
            skipped["sin_foto"] += 1; continue
        right = "C" if side.upper() == "LONG" else "P"
        pick = pick_contract(snap, right, exp_mode, ref)
        if not pick:
            skipped["sin_contrato"] += 1; continue
        k, exp, _, ask, oi = pick
        if max_prem and ask * 100 > max_prem:
            skipped["caro"] += 1; continue
        entry = ask
        key = (k, right, exp)
        path = [(s[0], s[2][key][0]) for s in ch if s[0] > snap[0] and key in s[2]]
        if not path:
            skipped["sin_contrato"] += 1; continue
        ret = None
        for (et, bid) in path:
            if bid >= entry * (1 + tp):
                ret = tp; break
        if ret is None:
            ret = max(path[-1][1] / entry - 1.0, -1.0)
        b = buckets.setdefault(kind or "ALL", [0, 0, 0.0])
        b[0] += int(ret > 0); b[1] += 1; b[2] += ret
        trades.append({"t": t, "sym": sym, "side": side, "kind": kind, "strike": k,
                       "exp": exp, "entry": round(entry, 2), "oi": oi, "ret": round(ret, 3)})
    return buckets, trades, skipped


# ------------------------------------------------------- scorer SUBYACENTE (contraste)
def load_bars(tmpl, sym):
    rows = []
    p = tmpl.format(sym=sym.lower())
    if not os.path.exists(p):
        return rows
    for r in csv.reader(open(p)):
        if not r or r[0] == "epoch":
            continue
        try:
            rows.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
        except Exception:
            continue
    rows.sort()
    return rows


def atr15_at(bars1, t, n=14):
    """ATR(14) sobre bloques de 15m construidos causalmente hasta t."""
    blocks = {}
    for (e, o, h, l, c) in bars1:
        if e > t:
            break
        k = e - e % 900
        b = blocks.get(k)
        if b is None:
            blocks[k] = [o, h, l, c]
        else:
            b[1] = max(b[1], h); b[2] = min(b[2], l); b[3] = c
    ks = sorted(blocks)[-(n + 1):]
    if len(ks) < n + 1:
        return None
    trs = []
    for i in range(1, len(ks)):
        o, h, l, c = blocks[ks[i]]
        pc = blocks[ks[i - 1]][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)


def score_underlying(rows, bars_tmpl, bar_secs, horizon_s=7200, tgt_mult=1.5, stp_mult=1.0):
    """Mismo conjunto, en el SUBYACENTE: target 1.5*ATR15 / stop 1.0*ATR15,
    horizonte 120 min, primer toque gana (stop gana la barra empatada)."""
    buckets = {}
    cache = {}
    for (t, sym, side, kind, ref) in rows:
        s = sym.lower()
        if s not in cache:
            cache[s] = load_bars(bars_tmpl, s)
        bars = cache[s]
        if not bars:
            continue
        t_entry = t + bar_secs
        ent = next(((e, o) for (e, o, h, l, c) in bars if e >= t_entry), None)
        if not ent:
            continue
        e_t, e_px = ent
        atr = atr15_at(bars, t)
        if not atr or atr <= 0:
            continue
        if side.upper() == "LONG":
            tgt = e_px + tgt_mult * atr; stp = e_px - stp_mult * atr
        else:
            tgt = e_px - tgt_mult * atr; stp = e_px + stp_mult * atr
        R = stp_mult * atr
        outcome = None; last_c = e_px
        for (e, o, h, l, c) in bars:
            if e < e_t:
                continue
            if e > e_t + horizon_s:
                break
            last_c = c
            if side.upper() == "LONG":
                if l <= stp: outcome = -1.0; break
                if h >= tgt: outcome = (tgt - e_px) / R; break
            else:
                if h >= stp: outcome = -1.0; break
                if l <= tgt: outcome = (e_px - tgt) / R; break
        if outcome is None:
            outcome = ((last_c - e_px) if side.upper() == "LONG" else (e_px - last_c)) / R
        b = buckets.setdefault(kind or "ALL", [0, 0, 0.0])
        b[0] += int(outcome > 0); b[1] += 1; b[2] += outcome
    return buckets


# ------------------------------------------------------------------------ util
def wilson(w, n, lo=True):
    if n == 0:
        return 0.0
    p = w / n; z = 1.96; d = 1 + z * z / n
    c = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (p + z * z / (2 * n) - c) / d) if lo else min(1.0, (p + z * z / (2 * n) + c) / d)


def read_signals(path, t0=None, t1=None):
    rows = []
    for r in csv.reader(open(path)):
        if not r or r[0] == "epoch":
            continue
        try:
            t = int(r[0]); ref = float(r[4]) if len(r) > 4 and r[4] else 0.0
        except Exception:
            continue
        if t0 and not (t0 <= t < t1):
            continue
        rows.append((t, r[1], r[2], r[3] if len(r) > 3 else "", ref))
    return rows


def show(title, buckets, unit="%", mult=100.0):
    print(f"\n  {title}")
    order = ["BB", "C2", "C3", "C4", "C5+", "ELASTIC", "SQZ_BRK", "BWALK",
             "combo_elastic", "combo_captain", "cambio_tend", "fuera_banda", "iman", "rebote_sma20"]
    keys = [k for k in order if k in buckets] + sorted(k for k in buckets if k not in order)
    tot = [0, 0, 0.0]
    for k in keys:
        w, n, s = buckets[k]
        tot[0] += w; tot[1] += n; tot[2] += s
        if n:
            print(f"    {k:15s} n={n:4d} | WR {w/n*100:5.1f}% | Wilson95 [{wilson(w,n)*100:4.1f},{wilson(w,n,False)*100:5.1f}] | ret/trade {s/n*mult:+6.2f}{unit}")
    if tot[1]:
        w, n, s = tot
        print(f"    {'TOTAL':15s} n={n:4d} | WR {w/n*100:5.1f}% | Wilson95 [{wilson(w,n)*100:4.1f},{wilson(w,n,False)*100:5.1f}] | ret/trade {s/n*mult:+6.2f}{unit}")
    return tot


def bench_day(date, hm0="09:45", hm1="15:55"):
    """BETA DEL DIA: comprar ATM (call y put) en CADA foto de cada simbolo. Es el
    baseline contra el que hay que medir cualquier motor en un dia direccional."""
    ch = load_chains(date)
    t0 = int(time.mktime(time.strptime(f"{date} {hm0}", "%Y-%m-%d %H:%M")))
    t1 = int(time.mktime(time.strptime(f"{date} {hm1}", "%Y-%m-%d %H:%M")))
    out = {}
    for exp_mode in ("0dte", "next"):
        for tp in (0.30, 0.50, 1.00):
            res = {"C": [0, 0, 0.0], "P": [0, 0, 0.0]}
            for sym, snaps in ch.items():
                for i, sn in enumerate(snaps):
                    if not (t0 <= sn[0] <= t1):
                        continue
                    for right in ("C", "P"):
                        pick = pick_contract(sn, right, exp_mode, sn[1])
                        if not pick:
                            continue
                        k, exp, _, ask, _oi = pick
                        key = (k, right, exp); entry = ask
                        path = [(s2[0], s2[2][key][0]) for s2 in snaps[i + 1:] if key in s2[2]]
                        if not path:
                            continue
                        ret = next((tp for (_e, bid) in path if bid >= entry * (1 + tp)), None)
                        if ret is None:
                            ret = max(path[-1][1] / entry - 1.0, -1.0)
                        b = res[right]
                        b[0] += int(ret > 0); b[1] += 1; b[2] += ret
            key = f"{exp_mode}_tp{int(tp*100)}"
            out[key] = res
            print(f"  BENCH {key:11s} " + "  ".join(
                f"{r}: n={v[1]:5d} WR {v[0]/v[1]*100:5.1f}% [{wilson(v[0],v[1])*100:.1f},{wilson(v[0],v[1],False)*100:.1f}] ret {v[2]/v[1]*100:+6.1f}%"
                for r, v in res.items()))
    return out


def main():
    args = sys.argv[1:]
    date = "2026-07-24"; bars_tmpl = "data/backtest/fri/bars5m_{sym}.csv"; files = []; bench_only = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--date": date = args[i + 1]; i += 2
        elif a == "--bars-tmpl": bars_tmpl = args[i + 1]; i += 2
        elif a == "--bench": bench_only = True; i += 1
        else: files.append(a); i += 1
    if bench_only:
        print(f"BETA DEL DIA {date} (ATM en cada foto, entrada ASK / salida BID):")
        bd = bench_day(date)
        json.dump(bd, open(f"data/backtest/fri/bench_{date}.json", "w"), indent=1)
        return
    if not files:
        raise SystemExit(__doc__)

    t0 = int(time.mktime(time.strptime(date + " 00:00", "%Y-%m-%d %H:%M")))
    t1 = t0 + 86400
    chains = load_chains(date)
    print(f"cadenas locales {date}: {len(chains)} simbolos, "
          f"{sum(len(v) for v in chains.values())} fotos")
    bpath = f"data/backtest/fri/bench_{date}.json"
    BENCH = json.load(open(bpath)) if os.path.exists(bpath) else None
    if BENCH:
        bC = BENCH["0dte_tp100"]["C"]; bP = BENCH["0dte_tp100"]["P"]
        print(f"beta del dia (ATM 0DTE TP+100 en cada foto): CALL {bC[0]/bC[1]*100:.1f}% ret {bC[2]/bC[1]*100:+.1f}% | "
              f"PUT {bP[0]/bP[1]*100:.1f}% ret {bP[2]/bP[1]*100:+.1f}%  (n={bC[1]} c/u)")

    out = {}
    for spec in files:
        path, _, bs = spec.partition(":")
        bar_secs = int(bs) if bs else 60
        name = os.path.basename(path).replace(".csv", "")
        rows = read_signals(path, t0, t1)
        print("\n" + "=" * 92)
        print(f"### {name}   n_señales={len(rows)}   (entrada = barra+{bar_secs}s, primera foto >= eso)")
        out[name] = {"n_signals": len(rows), "bar_secs": bar_secs, "opt": {}, "under": {}}
        for exp_mode in ("0dte", "next"):
            for tp in (0.30, 0.50, 1.00):
                b, tr, sk = score_option(rows, chains, bar_secs, tp, exp_mode)
                tot = show(f"OPCION {exp_mode.upper():5s} TP +{int(tp*100)}%  (entrada ASK / salida BID; spread real dentro)", b)
                out[name]["opt"][f"{exp_mode}_tp{int(tp*100)}"] = {
                    "buckets": {k: v for k, v in b.items()},
                    "total": tot, "skipped": sk}
                if tp == 1.00 and exp_mode == "0dte":
                    json.dump(tr, open(f"data/backtest/fri/trades_{name}_0dte.json", "w"), indent=1)
                    sides = {}
                    for x in tr:
                        b2 = sides.setdefault(x["side"], [0, 0, 0.0])
                        b2[0] += int(x["ret"] > 0); b2[1] += 1; b2[2] += x["ret"]
                    for sd, (w2, n2, s2) in sorted(sides.items()):
                        zz = ""
                        if BENCH:
                            bb2 = BENCH["0dte_tp100"]["C" if sd == "LONG" else "P"]
                            p1 = w2 / n2; p2 = bb2[0] / bb2[1]
                            pp = (w2 + bb2[0]) / (n2 + bb2[1])
                            se = math.sqrt(pp * (1 - pp) * (1 / n2 + 1 / bb2[1]))
                            zz = (f"  vs beta {p2*100:4.1f}% ret {bb2[2]/bb2[1]*100:+5.1f}%  "
                                  f"z={((p1-p2)/se if se else 0):+5.2f}")
                        print(f"      por lado {sd:5s} n={n2:4d} WR {w2/n2*100:5.1f}% ret {s2/n2*100:+6.1f}%{zz}")
                    b3, tr3, sk3 = score_option(rows, chains, bar_secs, tp, exp_mode, max_prem=200)
                    t3 = [0, 0, 0.0]
                    for v in b3.values():
                        t3[0] += v[0]; t3[1] += v[1]; t3[2] += v[2]
                    if t3[1]:
                        print(f"      prima<=$200  n={t3[1]:4d} WR {t3[0]/t3[1]*100:5.1f}% "
                              f"Wilson95 [{wilson(t3[0],t3[1])*100:.1f},{wilson(t3[0],t3[1],False)*100:.1f}] ret {t3[2]/t3[1]*100:+6.1f}%")
                        out[name]["opt"]["0dte_tp100_prem200"] = {"total": t3}
        bu = score_underlying(rows, bars_tmpl, bar_secs)
        tot = show("SUBYACENTE scalp (target 1.5*ATR15 / stop 1.0*ATR15, 120 min) — R-multiplo", bu, unit="R", mult=1.0)
        out[name]["under"] = {"buckets": bu, "total": tot}
    json.dump(out, open(f"data/backtest/fri/scores_{date}.json", "w"), indent=1)
    print(f"\n-> data/backtest/fri/scores_{date}.json")


if __name__ == "__main__":
    main()
