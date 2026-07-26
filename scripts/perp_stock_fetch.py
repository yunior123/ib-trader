#!/usr/bin/env python3
"""perp_stock_fetch.py -- puente tonto: precio/volumen/OI/funding/spread de los perps de
acciones tokenizadas en Bybit para los tickers de fleet.txt. Cero computo de senal.

Verificado 2026-07-26 (Yunior: "we should be able to see DRAM and some others like MU in
perpetuals"): Bitunix lista 26/30 pero el libro de fin de semana esta casi muerto (MU
$4,257 en 48h sab+dom); Bybit lista 29/30 (todo salvo GLD) con turnover real de fin de
semana (MU ~$150-300k/hora, ~$13M en 48h) y OI publico. Bybit es la fuente.

Exclusion dura: STXUSDT es el token cripto Stacks, NO Seagate (Bybit $0.146 vs cierre
real IBKR STX $853.25 el mismo dia) -- colision de ticker, se descarta siempre.
GLD no tiene perp en Bybit -- se omite.

Lead-lag medido (scripts/lead_lag_bybit.py ad-hoc, no incluido: correlacion movimiento
fin-de-semana-perp vs gap real lunes, n=6-10 por ticker, null de 2000 barajados):
MU corr=0.94 p=0.009 firma=8/8; INTC corr=0.83 p=0.003 firma=8/10; DRAM corr=0.97
p=0.002 firma=6/6. Sobrevive el null (a diferencia de peer_influence.py 0/19) porque es
el MISMO activo en otro venue, no un peer distinto -- no es prediccion independiente.

SOLO LECTURA. Uso: python3 scripts/perp_stock_fetch.py [SYM ...]
Sin args: fleet.txt completo -> data/perp_stocks.json
"""
import os, sys, json, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

EXCLUDE = {"GLD", "STX"}  # GLD: sin perp en Bybit. STX: colision con cripto Stacks.
BASE = "https://api.bybit.com/v5/market/tickers"
UA = {"User-Agent": "Mozilla/5.0"}


def fetch_ticker(sym):
    url = f"{BASE}?category=linear&symbol={sym}USDT"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.load(r)
    if d.get("retCode") != 0:
        raise RuntimeError(f"{sym}: bybit retCode={d.get('retCode')} {d.get('retMsg')}")
    lst = d.get("result", {}).get("list", [])
    if not lst:
        raise RuntimeError(f"{sym}: sin ticker en bybit")
    return lst[0]


def one(sym):
    t = fetch_ticker(sym)
    bid = float(t["bid1Price"]); ask = float(t["ask1Price"])
    mid = (bid + ask) / 2
    return {
        "sym": sym,
        "px": float(t["lastPrice"]),
        "mark_px": float(t["markPrice"]),
        "index_px": float(t["indexPrice"]),
        "bid": bid, "ask": ask,
        "spread_pct": round((ask - bid) / mid * 100, 4) if mid else None,
        "vol24h_usd": float(t["turnover24h"]),
        "oi_usd": float(t["openInterestValue"]),
        "funding_rate": float(t["fundingRate"]),
        "src": "bybit",
        "feed_ts": time.time(),
        "feed_age_s": 0.0,
    }


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
    out = {}
    for s in syms:
        if s in EXCLUDE:
            print(f"[skip] {s}: excluido (ver EXCLUDE)", file=sys.stderr)
            continue
        try:
            out[s] = one(s)
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
