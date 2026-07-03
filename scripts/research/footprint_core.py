#!/usr/bin/env python3
"""footprint_core.py — motor de FOOTPRINT (bid x ask por nivel de precio) sobre tape tbbo.

LOTE FUERA DE SESION (Python legitimo, CLAUDE.md).

Entrada : data/research/databento/{SYM}_{YYYY-MM-DD}_tbbo.csv.zst  (XNAS.ITCH, RTH)
          data/research/databento/{SYM}_{YYYY-MM-DD}_ohlcv-1m.csv.zst
Salida  : data/research/footprint_cells.npz   (celdas 1m: minuto x tick x {bid,ask} vol)
          data/research/footprint_class.json  (fracciones de clasificacion del agresor)

Clasificacion del agresor (la que manda la tarea, NO el campo `side` de Databento):
  price >= ask_px_00  -> comprador agresor (ask_vol)
  price <= bid_px_00  -> vendedor agresor (bid_vol)
  dentro del spread / mercado cruzado / sin cotizacion -> TICK RULE, contado APARTE.
El campo nativo `side` se usa SOLO como auditoria (tasa de acuerdo), jamas como fuente.

Imbalance DIAGONAL (Sierra Chart, doc NumbersBars 'Diagonal Comparison'):
  lado ASK (compra) en el nivel P: ask_vol[P]  vs bid_vol[P-1tick]
  lado BID (venta)  en el nivel P: bid_vol[P]  vs ask_vol[P+1tick]
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAPE = os.path.join(REPO, "data", "research", "databento")
OUT_CELLS = os.path.join(REPO, "data", "research", "footprint_cells.npz")
OUT_CLASS = os.path.join(REPO, "data", "research", "footprint_class.json")

RTH_START_MIN = 13 * 60 + 30          # 13:30 UTC = 09:30 ET
RTH_MINUTES = 390
TICK_USD = 0.01                        # SPY/QQQ


def die(msg):
    sys.stderr.write("FATAL footprint_core: %s\n" % msg)
    sys.exit(1)


def atomic_save_npz(path, **arrays):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def read_zst_csv(path, usecols, dtype=None):
    if not os.path.exists(path):
        die("no existe %s" % path)
    p = subprocess.Popen(["zstd", "-dcq", path], stdout=subprocess.PIPE)
    df = pd.read_csv(p.stdout, usecols=usecols, dtype=dtype)
    p.stdout.close()
    if p.wait() != 0:
        die("zstd fallo en %s" % path)
    return df


def tick_rule_sign(price):
    """+1 uptick, -1 downtick, 0 = no decidible (cero-tick antes del primer cambio)."""
    dp = np.empty(price.size)
    dp[0] = 0.0
    dp[1:] = np.diff(price)
    s = np.sign(dp)
    idx = np.where(s != 0, np.arange(s.size), 0)
    np.maximum.accumulate(idx, out=idx)
    return s[idx]


def build_day(sym, day, stats):
    """Devuelve celdas 1m del dia: (minute, tick, ask_q, bid_q, ask_t, bid_t)."""
    path = os.path.join(TAPE, "%s_%s_tbbo.csv.zst" % (sym, day))
    df = read_zst_csv(path,
                      usecols=["ts_recv", "action", "side", "price", "size",
                               "bid_px_00", "ask_px_00"],
                      dtype={"ts_recv": str, "action": str, "side": str})
    if df.empty:
        die("%s %s: tbbo vacio" % (sym, day))
    if (df["action"] != "T").any():
        die("%s %s: filas con action != T (%d)" % (sym, day, int((df["action"] != "T").sum())))

    ts = df["ts_recv"].values.astype("U30")
    # minuto UTC del dia a partir de las posiciones fijas del ISO8601
    hh = np.array([int(s[11:13]) * 60 + int(s[14:16]) for s in ts], dtype=np.int32)
    minute = hh - RTH_START_MIN
    inrth = (minute >= 0) & (minute < RTH_MINUTES)
    if not inrth.all():
        stats["rows_out_of_rth"] += int((~inrth).sum())

    price = df["price"].to_numpy(np.float64)
    size = df["size"].to_numpy(np.float64)
    bid = df["bid_px_00"].to_numpy(np.float64)
    ask = df["ask_px_00"].to_numpy(np.float64)
    nside = df["side"].to_numpy(dtype=object)

    # tick rule sobre TODA la cinta del dia (orden de llegada), antes de filtrar RTH
    tsign = tick_rule_sign(price)

    m = inrth
    price, size, bid, ask, nside, tsign, minute = (
        price[m], size[m], bid[m], ask[m], nside[m], tsign[m], minute[m])

    has_q = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0) & (ask > bid)
    at_ask = has_q & (price >= ask)
    at_bid = has_q & (price <= bid)
    inside = has_q & ~at_ask & ~at_bid
    noq = ~has_q                                   # sin cotizacion o mercado cruzado/bloqueado
    need_tick = inside | noq
    tick_up = need_tick & (tsign > 0)
    tick_dn = need_tick & (tsign < 0)
    unclass = need_tick & (tsign == 0)

    # --- auditoria contra el campo nativo `side` de Databento
    nb = nside == "B"
    na = nside == "A"
    stats["side_native_B_vol"] += float(size[nb].sum())
    stats["side_native_A_vol"] += float(size[na].sum())
    stats["side_native_N_vol"] += float(size[~(nb | na)].sum())
    stats["agree_ask_B_vol"] += float(size[at_ask & nb].sum())
    stats["disagree_ask_A_vol"] += float(size[at_ask & na].sum())
    stats["agree_bid_A_vol"] += float(size[at_bid & na].sum())
    stats["disagree_bid_B_vol"] += float(size[at_bid & nb].sum())

    vol = float(size.sum())
    stats["rows"] += int(size.size)
    stats["vol"] += vol
    stats["vol_at_ask"] += float(size[at_ask].sum())
    stats["vol_at_bid"] += float(size[at_bid].sum())
    stats["vol_inside"] += float(size[inside].sum())
    stats["vol_noquote"] += float(size[noq].sum())
    stats["vol_tick_up"] += float(size[tick_up].sum())
    stats["vol_tick_dn"] += float(size[tick_dn].sum())
    stats["vol_unclass"] += float(size[unclass].sum())
    px100 = price * 100.0
    stats["rows_subpenny"] += int(np.sum(np.abs(px100 - np.rint(px100)) > 1e-6))
    per = stats["per_sym"].setdefault(sym, dict(rows=0, vol=0.0, at_ask=0.0, at_bid=0.0,
                                                inside=0.0, noquote=0.0, unclass=0.0))
    per["rows"] += int(size.size)
    per["vol"] += vol
    per["at_ask"] += float(size[at_ask].sum())
    per["at_bid"] += float(size[at_bid].sum())
    per["inside"] += float(size[inside].sum())
    per["noquote"] += float(size[noq].sum())
    per["unclass"] += float(size[unclass].sum())

    tick = np.rint(px100).astype(np.int64)          # nivel de precio en centavos
    key = minute.astype(np.int64) * 10_000_000 + tick
    uk, inv = np.unique(key, return_inverse=True)
    n = uk.size
    ask_q = np.bincount(inv, weights=size * at_ask, minlength=n)
    bid_q = np.bincount(inv, weights=size * at_bid, minlength=n)
    ask_t = np.bincount(inv, weights=size * tick_up, minlength=n)
    bid_t = np.bincount(inv, weights=size * tick_dn, minlength=n)
    return (uk // 10_000_000).astype(np.int16), (uk % 10_000_000).astype(np.int32), \
        ask_q, bid_q, ask_t, bid_t


def build_bars(sym, day):
    path = os.path.join(TAPE, "%s_%s_ohlcv-1m.csv.zst" % (sym, day))
    df = read_zst_csv(path, usecols=["ts_event", "open", "high", "low", "close", "volume"],
                      dtype={"ts_event": str})
    ts = df["ts_event"].values.astype("U30")
    minute = np.array([int(s[11:13]) * 60 + int(s[14:16]) for s in ts],
                      dtype=np.int32) - RTH_START_MIN
    o = np.full(RTH_MINUTES, np.nan)
    h = np.full(RTH_MINUTES, np.nan)
    l = np.full(RTH_MINUTES, np.nan)
    c = np.full(RTH_MINUTES, np.nan)
    v = np.zeros(RTH_MINUTES)
    ok = (minute >= 0) & (minute < RTH_MINUTES)
    o[minute[ok]] = df["open"].to_numpy()[ok]
    h[minute[ok]] = df["high"].to_numpy()[ok]
    l[minute[ok]] = df["low"].to_numpy()[ok]
    c[minute[ok]] = df["close"].to_numpy()[ok]
    v[minute[ok]] = df["volume"].to_numpy()[ok]
    return o, h, l, c, v


def discover():
    days = {}
    for f in sorted(os.listdir(TAPE)):
        if not f.endswith("_tbbo.csv.zst"):
            continue
        sym, day, _ = f.split("_", 2)
        days.setdefault(sym, []).append(day)
    if not days:
        die("no hay ficheros tbbo en %s" % TAPE)
    return {s: sorted(d) for s, d in days.items()}


def build_all():
    inv = discover()
    syms = sorted(inv)
    stats = dict(rows=0, vol=0.0, vol_at_ask=0.0, vol_at_bid=0.0, vol_inside=0.0,
                 vol_noquote=0.0, vol_tick_up=0.0, vol_tick_dn=0.0, vol_unclass=0.0,
                 rows_out_of_rth=0, rows_subpenny=0, per_sym={},
                 side_native_B_vol=0.0, side_native_A_vol=0.0, side_native_N_vol=0.0,
                 agree_ask_B_vol=0.0, disagree_ask_A_vol=0.0,
                 agree_bid_A_vol=0.0, disagree_bid_B_vol=0.0)

    mins, ticks, aq, bq, at, bt, blk = [], [], [], [], [], [], []
    blocks = []                                   # (sym_idx, day_idx)
    O, H, L, C, V = [], [], [], [], []
    days_all = sorted({d for s in syms for d in inv[s]})
    for si, s in enumerate(syms):
        for d in inv[s]:
            di = days_all.index(d)
            mi, ti, a1, b1, a2, b2 = build_day(s, d, stats)
            bi = len(blocks)
            mins.append(mi); ticks.append(ti)
            aq.append(a1); bq.append(b1); at.append(a2); bt.append(b2)
            blk.append(np.full(mi.size, bi, dtype=np.int32))
            o, h, l, c, v = build_bars(s, d)
            O.append(o); H.append(h); L.append(l); C.append(c); V.append(v)
            blocks.append((si, di))
            print("  %s %s  celdas=%6d  trades=%d" % (s, d, mi.size, stats["rows"]))

    blocks = np.array(blocks, dtype=np.int32)
    atomic_save_npz(
        OUT_CELLS,
        symbols=np.array(syms), days=np.array(days_all),
        block_sym=blocks[:, 0], block_day=blocks[:, 1],
        cell_block=np.concatenate(blk), cell_min=np.concatenate(mins),
        cell_tick=np.concatenate(ticks),
        ask_q=np.concatenate(aq).astype(np.float32),
        bid_q=np.concatenate(bq).astype(np.float32),
        ask_t=np.concatenate(at).astype(np.float32),
        bid_t=np.concatenate(bt).astype(np.float32),
        bar_o=np.array(O), bar_h=np.array(H), bar_l=np.array(L),
        bar_c=np.array(C), bar_v=np.array(V))

    v = stats["vol"]
    frac = dict(
        n_blocks=int(blocks.shape[0]), symbols=syms, n_days=len(days_all),
        trades=stats["rows"], volume=v,
        pct_vol_at_ask=100.0 * stats["vol_at_ask"] / v,
        pct_vol_at_bid=100.0 * stats["vol_at_bid"] / v,
        pct_vol_inside_spread=100.0 * stats["vol_inside"] / v,
        pct_vol_noquote_or_crossed=100.0 * stats["vol_noquote"] / v,
        pct_vol_tickrule_buy=100.0 * stats["vol_tick_up"] / v,
        pct_vol_tickrule_sell=100.0 * stats["vol_tick_dn"] / v,
        pct_vol_unclassifiable=100.0 * stats["vol_unclass"] / v,
        pct_rows_subpenny=100.0 * stats["rows_subpenny"] / max(1, stats["rows"]),
        rows_out_of_rth=stats["rows_out_of_rth"],
        auditoria_side_nativo=dict(
            pct_vol_side_B=100.0 * stats["side_native_B_vol"] / v,
            pct_vol_side_A=100.0 * stats["side_native_A_vol"] / v,
            pct_vol_side_N=100.0 * stats["side_native_N_vol"] / v,
            acuerdo_at_ask_con_B=100.0 * stats["agree_ask_B_vol"] /
            max(1e-9, stats["vol_at_ask"]),
            acuerdo_at_bid_con_A=100.0 * stats["agree_bid_A_vol"] /
            max(1e-9, stats["vol_at_bid"])),
        per_sym={s: {k: (100.0 * x / p["vol"] if k != "rows" and k != "vol" else x)
                     for k, x in p.items()} for s, p in stats["per_sym"].items()})
    atomic_write_json(OUT_CLASS, frac)
    return frac


# ------------------------------------------------------------------ footprint API

class Footprint(object):
    """Celdas agregadas a barras de N minutos, con rejilla densa de ticks por barra."""

    def __init__(self, path=OUT_CELLS):
        z = np.load(path, allow_pickle=False)
        self.symbols = [str(s) for s in z["symbols"]]
        self.days = [str(d) for d in z["days"]]
        self.block_sym = z["block_sym"]
        self.block_day = z["block_day"]
        self.cell_block = z["cell_block"]
        self.cell_min = z["cell_min"].astype(np.int64)
        self.cell_tick = z["cell_tick"].astype(np.int64)
        self.ask_q = z["ask_q"].astype(np.float64)
        self.bid_q = z["bid_q"].astype(np.float64)
        self.ask_t = z["ask_t"].astype(np.float64)
        self.bid_t = z["bid_t"].astype(np.float64)
        self.bar_o, self.bar_h = z["bar_o"], z["bar_h"]
        self.bar_l, self.bar_c, self.bar_v = z["bar_l"], z["bar_c"], z["bar_v"]
        self.n_blocks = self.block_sym.size

    def bars(self, nmin, include_tick_rule=True):
        """Lista de barras: (block, bar_idx, last_minute, tick0, ask_dense, bid_dense)."""
        ask = self.ask_q + (self.ask_t if include_tick_rule else 0.0)
        bid = self.bid_q + (self.bid_t if include_tick_rule else 0.0)
        bar = self.cell_min // nmin
        key = self.cell_block.astype(np.int64) * 100000 + bar
        order = np.lexsort((self.cell_tick, key))
        key_s, tick_s = key[order], self.cell_tick[order]
        ask_s, bid_s = ask[order], bid[order]
        # agregar celdas del mismo (bloque, barra, tick)
        k2 = key_s * 10_000_000 + tick_s
        uk, inv = np.unique(k2, return_inverse=True)
        a = np.bincount(inv, weights=ask_s, minlength=uk.size)
        b = np.bincount(inv, weights=bid_s, minlength=uk.size)
        gk = uk // 10_000_000
        gt = uk % 10_000_000
        out = []
        starts = np.nonzero(np.concatenate(([True], gk[1:] != gk[:-1])))[0]
        ends = np.append(starts[1:], gk.size)
        for s, e in zip(starts, ends):
            blk = int(gk[s] // 100000)
            bidx = int(gk[s] % 100000)
            t = gt[s:e]
            t0, t1 = int(t[0]), int(t[-1])
            w = t1 - t0 + 1
            if w > 5000:
                die("barra con %d niveles: rejilla absurda (bloque %d barra %d)" % (w, blk, bidx))
            ad = np.zeros(w)
            bd = np.zeros(w)
            ad[t - t0] = a[s:e]
            bd[t - t0] = b[s:e]
            out.append((blk, bidx, (bidx + 1) * nmin - 1, t0, ad, bd))
        return out


def diagonal_imbalance(ask, bid, ratio, min_vol, zero_as_one=True):
    """Sierra Chart diagonal. Devuelve (buy_imb, sell_imb) booleanos por nivel.

    buy  (lado ask) en P: ask[P] vs bid[P-1]
    sell (lado bid) en P: bid[P] vs ask[P+1]
    """
    n = ask.size
    den_buy = np.empty(n)
    den_buy[0] = 0.0
    den_buy[1:] = bid[:-1]
    den_sell = np.empty(n)
    den_sell[-1] = 0.0
    den_sell[:-1] = ask[1:]
    if zero_as_one:
        db = np.where(den_buy <= 0, 1.0, den_buy)
        ds = np.where(den_sell <= 0, 1.0, den_sell)
        ok_b = np.ones(n, dtype=bool)
        ok_s = np.ones(n, dtype=bool)
    else:
        db, ds = den_buy, den_sell
        ok_b = den_buy > 0
        ok_s = den_sell > 0
    buy = ok_b & (ask >= ratio * db) & (ask >= min_vol)
    sell = ok_s & (bid >= ratio * ds) & (bid >= min_vol)
    return buy, sell


def stacks(flags, K):
    """Devuelve lista de (start, length) de rachas contiguas de longitud >= K."""
    if flags.size == 0:
        return []
    idx = np.nonzero(flags)[0]
    if idx.size == 0:
        return []
    brk = np.nonzero(np.diff(idx) != 1)[0]
    starts = np.concatenate(([0], brk + 1))
    ends = np.concatenate((brk, [idx.size - 1]))
    out = []
    for s, e in zip(starts, ends):
        ln = int(e - s + 1)
        if ln >= K:
            out.append((int(idx[s]), ln))
    return out


def main():
    ap = argparse.ArgumentParser(description="motor de footprint sobre tape tbbo")
    ap.add_argument("--build", action="store_true", help="reconstruye la cache de celdas")
    a = ap.parse_args()
    if a.build:
        f = build_all()
        print(json.dumps({k: v for k, v in f.items() if k != "per_sym"}, indent=1))
        print("-> %s\n-> %s" % (OUT_CELLS, OUT_CLASS))
    else:
        fp = Footprint()
        print("bloques=%d syms=%s dias=%d celdas=%d"
              % (fp.n_blocks, fp.symbols, len(fp.days), fp.cell_min.size))


if __name__ == "__main__":
    main()
