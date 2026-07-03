#!/usr/bin/env python3
"""Construye barras 1m con delta firmado desde el tape XNAS.ITCH tbbo de Databento.

Fuente: data/research/databento/<SYM>_<YYYY-MM-DD>_tbbo.csv.zst
Salida: data/research/delta_bars_1m.npz  (escritura atomica)

Convencion de signo VERIFICADA en MANIFEST.json nota_side:
  side='B' -> agresor COMPRADOR (paga el ask) -> +size
  side='A' -> agresor VENDEDOR (pega al bid) -> -size
  side='N' -> sin clasificar (13,7% del volumen)

Se calculan DOS deltas:
  delta      = vol_B - vol_A                (nativo del exchange, primario)
  delta_lr   = delta + Lee-Ready sobre las N (quote rule, luego tick rule)

Fail-loud: una fila malformada aborta. Jamas se rellena con 0.
"""
import io
import json
import os
import sys
import tempfile
from collections import defaultdict

import numpy as np
import zstandard as zstd

REPO = "/Users/yuniorrodriguezosorio/ib-trader"
SRC = os.path.join(REPO, "data/research/databento")
OUT = os.path.join(REPO, "data/research/delta_bars_1m.npz")

# indices de columna del csv tbbo de Databento (cabecera verificada)
I_TS_EVENT, I_ACTION, I_SIDE, I_PRICE, I_SIZE = 1, 5, 6, 8, 9
I_BID, I_ASK = 13, 14
RTH_START_MIN = 13 * 60 + 30
RTH_END_MIN = 20 * 60


def die(msg):
    sys.stderr.write("FATAL: %s\n" % msg)
    sys.exit(1)


def bars_of_file(path):
    """Devuelve dict minuto_del_dia -> acumulador. Streaming, memoria acotada."""
    acc = {}
    dctx = zstd.ZstdDecompressor()
    n_rows = 0
    n_nontrade = 0
    last_px = None          # para tick rule
    prev_diff_px = None
    with open(path, "rb") as fh:
        with dctx.stream_reader(fh) as reader:
            text = io.TextIOWrapper(reader, encoding="utf-8", newline="")
            header = text.readline().rstrip("\n").split(",")
            if header[I_TS_EVENT] != "ts_event" or header[I_SIDE] != "side" or \
               header[I_PRICE] != "price" or header[I_SIZE] != "size" or \
               header[I_BID] != "bid_px_00" or header[I_ASK] != "ask_px_00":
                die("cabecera inesperada en %s: %s" % (path, header))
            for line in text:
                f = line.rstrip("\n").split(",")
                if len(f) < 20:
                    die("fila corta en %s: %r" % (path, line[:120]))
                if f[I_ACTION] != "T":
                    n_nontrade += 1
                    continue
                ts = f[I_TS_EVENT]
                mod = int(ts[11:13]) * 60 + int(ts[14:16])
                # Databento puede incluir un evento de estado inmediatamente anterior
                # al start solicitado (NVDA 2026-07-14 trajo 13:29). El estudio declara
                # RTH 13:30–20:00 UTC: se filtra explícitamente, nunca se deja que una
                # fila pre-open contamine la sesión ni que aborte todo el lote.
                if mod < RTH_START_MIN or mod >= RTH_END_MIN:
                    continue
                px = float(f[I_PRICE])
                sz = int(f[I_SIZE])
                side = f[I_SIDE]
                a = acc.get(mod)
                if a is None:
                    # o, h, l, c, vol, vol_b, vol_a, vol_n, ntr, lr_b, lr_a, lr_unk
                    a = [px, px, px, px, 0, 0, 0, 0, 0, 0, 0, 0]
                    acc[mod] = a
                if px > a[1]:
                    a[1] = px
                if px < a[2]:
                    a[2] = px
                a[3] = px
                a[4] += sz
                a[8] += 1
                if side == "B":
                    a[5] += sz
                    a[9] += sz
                elif side == "A":
                    a[6] += sz
                    a[10] += sz
                else:
                    a[7] += sz
                    # Lee-Ready: quote rule, luego tick rule
                    bid = f[I_BID]
                    ask = f[I_ASK]
                    done = False
                    if bid and ask:
                        b = float(bid)
                        k = float(ask)
                        if k > 0 and px >= k:
                            a[9] += sz
                            done = True
                        elif b > 0 and px <= b:
                            a[10] += sz
                            done = True
                    if not done:
                        if prev_diff_px is not None and px != prev_diff_px:
                            if px > prev_diff_px:
                                a[9] += sz
                            else:
                                a[10] += sz
                        else:
                            a[11] += sz
                if last_px is not None and px != last_px:
                    prev_diff_px = last_px
                last_px = px
                n_rows += 1
    return acc, n_rows, n_nontrade


def main():
    files = sorted(f for f in os.listdir(SRC) if f.endswith("_tbbo.csv.zst"))
    if not files:
        die("no hay ficheros tbbo en %s" % SRC)
    syms, days = [], []
    rows = []
    meta = {"ficheros": [], "n_rows_total": 0, "n_nontrade_total": 0}
    for fn in files:
        sym, day, _ = fn.split("_", 2)
        path = os.path.join(SRC, fn)
        acc, n_rows, n_nt = bars_of_file(path)
        if not acc:
            die("fichero sin barras: %s" % fn)
        if sym not in syms:
            syms.append(sym)
        if day not in days:
            days.append(day)
        si = syms.index(sym)
        for mod in sorted(acc):
            a = acc[mod]
            rows.append([si, days.index(day), mod] + a)
        vol = sum(a[4] for a in acc.values())
        vn = sum(a[7] for a in acc.values())
        meta["ficheros"].append({
            "file": fn, "sym": sym, "day": day, "bars": len(acc),
            "rows": n_rows, "volume": vol, "pct_N": round(100.0 * vn / vol, 3),
        })
        meta["n_rows_total"] += n_rows
        meta["n_nontrade_total"] += n_nt
        sys.stderr.write("  %s  bars=%d rows=%d pctN=%.2f\n"
                         % (fn, len(acc), n_rows, 100.0 * vn / vol))
    days = sorted(days)
    # reindexar dias tras ordenar
    day_of = {d: i for i, d in enumerate(days)}
    arr = np.array(rows, dtype=np.float64)
    # columna 1 traia el indice del orden de aparicion; recalcular
    order_days = []
    for fn in files:
        _, day, _ = fn.split("_", 2)
        if day not in order_days:
            order_days.append(day)
    remap = np.array([day_of[order_days[int(i)]] for i in range(len(order_days))])
    arr[:, 1] = remap[arr[:, 1].astype(int)]

    cols = ["sym", "day", "mod", "o", "h", "l", "c", "vol",
            "vol_b", "vol_a", "vol_n", "ntr", "lr_b", "lr_a", "lr_unk"]
    idx = np.lexsort((arr[:, 2], arr[:, 1], arr[:, 0]))
    arr = arr[idx]

    tmp = tempfile.NamedTemporaryFile(dir=os.path.dirname(OUT), suffix=".tmp",
                                      delete=False)
    tmp.close()
    np.savez_compressed(tmp.name, bars=arr, cols=np.array(cols),
                        syms=np.array(syms), days=np.array(days))
    os.replace(tmp.name + ".npz", OUT)
    meta["n_bars"] = int(arr.shape[0])
    meta["syms"] = syms
    meta["days"] = days
    with open(OUT.replace(".npz", "_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print("OK %d barras -> %s" % (arr.shape[0], OUT))


if __name__ == "__main__":
    main()
