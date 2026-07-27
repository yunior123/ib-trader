#!/usr/bin/env python3
"""perp_stock_fetch.py -- puente tonto: precio/volumen/OI/spread de los perps de acciones
tokenizadas en OKX (instType SWAP) para los tickers de fleet.txt. Cero computo de senal.

MIGRADO a OKX 2026-07-27 (orden Yunior: "dramusdt from okx perpetuals, the same for the
others"). Bybit queda como fallback SOLO para el simbolo que no exista en OKX; el campo
'src' de cada fila dice la fuente real, nunca mezclado en silencio.

Verificado en vivo 2026-07-27 contra GET /public/instruments?instType=SWAP (430 filas):
existen en OKX 26/28 no-excluidos de fleet.txt. NO existen en OKX (fallback Bybit, ambos
confirmados ahi): TXN, XLK. GLD: sin perp en OKX ni en Bybit -> excluido siempre.
STX-USDT-SWAP EXISTE en OKX pero es el mismo choque que en Bybit: precio ~0.14 = token
cripto Stacks, no Seagate (IBKR STX ~$853) -- excluido igual.

SOLO LECTURA. Uso: python3 scripts/perp_stock_fetch.py [SYM ...]
Sin args: fleet.txt completo -> data/perp_stocks.json
"""
import os, sys, json, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

EXCLUDE = {"GLD", "STX"}  # GLD: sin perp en ningun venue medido. STX: choque cripto Stacks.
OKX_BASE = "https://www.okx.com/api/v5"
BYBIT_BASE = "https://api.bybit.com/v5/market/tickers"
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def okx_valid_bases():
    d = _get(f"{OKX_BASE}/public/instruments?instType=SWAP")
    if d.get("code") != "0":
        raise RuntimeError(f"okx instruments: code={d.get('code')} {d.get('msg')}")
    return {row["instId"].split("-")[0] for row in d.get("data", [])
             if row.get("instId", "").endswith("-USDT-SWAP")}


def fetch_okx(sym):
    inst = f"{sym}-USDT-SWAP"
    t = _get(f"{OKX_BASE}/market/ticker?instId={inst}")
    if t.get("code") != "0" or not t.get("data"):
        raise RuntimeError(f"{sym}: okx ticker code={t.get('code')} {t.get('msg')}")
    tk = t["data"][0]
    b = _get(f"{OKX_BASE}/market/books?instId={inst}&sz=1")
    bk = (b.get("data") or [None])[0]
    if b.get("code") != "0" or not bk or not bk.get("bids") or not bk.get("asks"):
        raise RuntimeError(f"{sym}: okx books vacio/invalido")
    bid, ask = float(bk["bids"][0][0]), float(bk["asks"][0][0])
    if bid <= 0 or ask < bid:
        raise RuntimeError(f"{sym}: okx book cruzado bid={bid} ask={ask}")
    oi_usd = None
    o = _get(f"{OKX_BASE}/public/open-interest?instType=SWAP&instId={inst}")
    if o.get("code") == "0" and o.get("data"):
        oi_usd = float(o["data"][0]["oiUsd"])
    mid = (bid + ask) / 2
    return {
        "sym": sym,
        "px": float(tk["last"]),
        "bid": bid, "ask": ask,
        "spread_pct": round((ask - bid) / mid * 100, 4) if mid else None,
        "vol24h_usd": float(tk["volCcy24h"]),
        "oi_usd": oi_usd,
        "src": "okx",
        "feed_ts": time.time(),
        "feed_age_s": 0.0,
    }


def fetch_bybit(sym):
    d = _get(f"{BYBIT_BASE}?category=linear&symbol={sym}USDT")
    if d.get("retCode") != 0:
        raise RuntimeError(f"{sym}: bybit retCode={d.get('retCode')} {d.get('retMsg')}")
    lst = d.get("result", {}).get("list", [])
    if not lst:
        raise RuntimeError(f"{sym}: sin ticker en bybit")
    t = lst[0]
    bid, ask = float(t["bid1Price"]), float(t["ask1Price"])
    if bid <= 0 or ask < bid:
        raise RuntimeError(f"{sym}: bybit book cruzado bid={bid} ask={ask}")
    mid = (bid + ask) / 2
    return {
        "sym": sym,
        "px": float(t["lastPrice"]),
        "bid": bid, "ask": ask,
        "spread_pct": round((ask - bid) / mid * 100, 4) if mid else None,
        "vol24h_usd": float(t["turnover24h"]),
        "oi_usd": float(t["openInterestValue"]),
        "src": "bybit",  # fallback: sym no existe como *-USDT-SWAP en OKX
        "feed_ts": time.time(),
        "feed_age_s": 0.0,
    }


def one(sym, okx_bases):
    if sym in okx_bases:
        try:
            return fetch_okx(sym)
        except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as e:
            print(f"[warn] {sym}: okx fallo ({e}) -> probando bybit", file=sys.stderr)
    return fetch_bybit(sym)


def atomic_write_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    args = sys.argv[1:]
    syms = [s.upper() for s in args] if args else \
        [s for s in open("data/fleet.txt").read().split() if s not in EXCLUDE]
    try:
        okx_bases = okx_valid_bases()
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"[warn] okx instruments: {e} -> todo via bybit esta pasada", file=sys.stderr)
        okx_bases = set()
    out = {}
    for s in syms:
        if s in EXCLUDE:
            print(f"[skip] {s}: excluido (ver EXCLUDE)", file=sys.stderr)
            continue
        try:
            out[s] = one(s, okx_bases)
        except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as e:
            print(f"[warn] {s}: {e}", file=sys.stderr)
    if args:
        json.dump(out, sys.stdout, indent=1, sort_keys=True)
        print()
    else:
        atomic_write_json("data/perp_stocks.json", out)
        print(f"{len(out)}/{len(syms)} symbols -> data/perp_stocks.json", file=sys.stderr)


if __name__ == "__main__":
    main()
