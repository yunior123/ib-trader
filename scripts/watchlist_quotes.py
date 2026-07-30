#!/usr/bin/env python3
"""watchlist_quotes.py — cotizacion de los simbolos AÑADIDOS A MANO (data/watchlist_user.txt)
que NO estan en la flota: el bar_bridge solo suscribe fleet.txt (y ampliarlo quema las
suscripciones tick-by-tick que IBKR capea, err 10190), asi que TQQQ/MSFU/MUU salian con la
fila en blanco aunque el chart si los pintaba (medido 2026-07-30).

SNAPSHOT (no streaming): un reqMktData snapshot por simbolo cada ciclo -> no consume linea
permanente. Escribe data/watchlist_stats.json (tmp+rename) que chart_bridge ya lee.
Puente TONTO: mueve bytes de TWS a disco, cero computo de señal. SEÑAL-SOLAMENTE.

Uso: ./venv/bin/python scripts/watchlist_quotes.py [--once] [--interval 20]
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import ib_mode  # noqa: E402  (fuente unica del puerto paper/live)

OUT = os.path.join(REPO, "data", "watchlist_stats.json")


def _num(x):
    """None si TWS manda nan/-1 (su forma de decir 'no hay dato'). Jamas un 0 plausible."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or v < 0:
        return None
    return v


def extras():
    """Simbolos del usuario sin fichero de barras propio (los de la flota ya lo tienen) y que
    no son coreanos (contrato KRX, otro camino)."""
    try:
        user = [s.upper() for s in open(os.path.join(REPO, "data", "watchlist_user.txt")).read().split()]
    except OSError:
        return []
    try:
        korea = {s.upper() for s in open(os.path.join(REPO, "data", "korea_syms.txt")).read().split()}
    except OSError:
        korea = set()
    out = []
    for s in dict.fromkeys(user):
        if s in korea or s.endswith("USDT") or not s.isalpha():
            continue
        if os.path.exists(os.path.join(REPO, "data", f"bars_{s.lower()}_ibkr.txt")):
            continue
        out.append(s)
    return out


async def cycle(ib, syms):
    from ib_async import Stock
    stats = {}
    for s in syms:
        try:
            (c,) = await asyncio.wait_for(ib.qualifyContractsAsync(Stock(s, "SMART", "USD")), 15)
        except Exception as e:
            print(f"[wlq] {s}: no cualifica ({e})", flush=True)
            continue
        t = ib.reqMktData(c, "", True, False)   # snapshot: se auto-cancela (cancelar da err 300)
        for _ in range(30):
            await asyncio.sleep(0.4)
            if _num(t.last) is not None or _num(t.close) is not None:
                break
        last = _num(t.last) or _num(t.marketPrice()) or _num(t.close)
        prev = _num(t.close)
        vol = _num(t.volume)
        if last is None:
            print(f"[wlq] {s}: TWS sin precio (no invento cero)", flush=True)
            continue
        row = {"last": round(last, 2), "age_s": 0, "ts": int(time.time())}
        # ts POR FILA: chart_bridge exige ts fresco por simbolo para dejar que el
        # feed pise precio/chg (si no, solo pasaba el volumen).
        if prev:
            row["chg"] = round((last - prev) / prev * 100, 2)
        if vol:
            row["vol"] = int(vol)   # ib_async ya devuelve ACCIONES (x100 daba 1,3B en MUU)
        stats[s] = row
    return stats


def write(stats):
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"ts": int(time.time()), "src": "watchlist_quotes.py (TWS snapshot)",
                   "stats": stats}, f)
    os.replace(tmp, OUT)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--client-id", type=int, default=133)
    a = ap.parse_args()
    from ib_async import IB
    ib = IB()
    port = ib_mode.get_port()
    await ib.connectAsync("127.0.0.1", port, clientId=a.client_id, timeout=15, readonly=True)
    ib.RequestTimeout = 15   # sin esto un fallo cuelga para siempre (memoria 2026-07-26)
    print(f"[wlq] conectado TWS 127.0.0.1:{port} clientId={a.client_id}", flush=True)
    try:
        while True:
            syms = extras()
            if syms:
                st = await cycle(ib, syms)
                write(st)
                print(f"[wlq] {len(st)}/{len(syms)} cotizados: {' '.join(st)}", flush=True)
            else:
                write({})
            if a.once:
                return
            await asyncio.sleep(a.interval)
    finally:
        ib.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
