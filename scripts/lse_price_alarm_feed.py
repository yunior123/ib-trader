#!/usr/bin/env python3
"""London-only BBO bridge for the signal-only price alarm.

The C++ alarm deliberately has no network access.  This small websocket bridge
supplies only fresh ``epoch bid ask`` files for explicitly requested symbols.
It never routes an order and it refuses delayed/replayed quotes (>30 seconds).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import signal
import sys
import time

import websockets

import lse_client


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
STATUS = os.path.join(DATA, "lse_price_alarm_feed_status.json")
# Tope MEDIDO del vault (2026-08-24): el server contesta {"type":"subscribed","max":16} y a
# partir de la 17a manda {"type":"error"}. Con 36 simbolos de flota faltaban 21 en silencio.
MAX_POR_CONEXION = int(os.environ.get("LSE_WS_MAX_SUBS", "16"))


def _epoch(value):
    try:
        value = float(value)
        return value / 1000.0 if value > 10_000_000_000 else value
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _atomic_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%s" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
    os.replace(tmp, path)


_LOTES: dict = {}
_QUOTES: dict = {}      # compartido: cada lote es una conexion, el estado es UNO


def _status(state, symbols, quotes, error=None, lote=0):
    _QUOTES.update(quotes)
    _LOTES[lote] = {"state": state, "symbols": symbols, "n_quotes": len(quotes),
                    "error": str(error)[:240] if error else None}
    payload = {
        "source": "london_strategic_edge_websocket",
        "mode": "signal_only_no_orders",
        "state": state,
        "lotes": _LOTES,
        "symbols": symbols,
        "pid": os.getpid(),
        "updated_at": time.time(),
        "quotes": _QUOTES,
        "error": str(error)[:240] if error else None,
    }
    _atomic_text(STATUS, json.dumps(payload, separators=(",", ":")) + "\n")


async def run(symbols, lote=0):
    quotes = {}
    published = {}
    last_status_at = 0.0
    backoff = 1.0
    while True:
        try:
            _status("CONNECTING", symbols, quotes, lote=lote)
            async with websockets.connect(
                lse_client.WS_URL,
                ping_interval=20,
                ping_timeout=25,
                open_timeout=15,
                close_timeout=5,
                max_size=None,
            ) as ws:
                backoff = 1.0
                _status("CONNECTED", symbols, quotes, lote=lote)
                await ws.recv()  # server hello precedes client authentication
                await ws.send(json.dumps({"action": "auth", "api_key": lse_client.api_key()}))
                _status("AUTHENTICATING", symbols, quotes, lote=lote)
                async for raw in ws:
                    arrival = time.time()
                    msg = json.loads(raw)
                    auth_ok = (
                        msg.get("type") == "authenticated"
                        or (msg.get("type") == "auth" and msg.get("status") == "ok")
                    )
                    if auth_ok:
                        for symbol in symbols:
                            await ws.send(json.dumps({"action": "subscribe", "symbol": symbol}))
                        _status("SUBSCRIBING", symbols, quotes, lote=lote)
                        continue
                    if msg.get("type") == "error":
                        _status("ERROR", symbols, quotes, msg.get("message") or msg, lote=lote)
                        continue
                    if msg.get("type") not in ("tick", "quote", "trade"):
                        continue
                    symbol = str(msg.get("symbol") or "").upper()
                    if symbol not in symbols:
                        continue
                    try:
                        bid, ask = float(msg["bid"]), float(msg["ask"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    exchange_ts = _epoch(msg.get("ts") or msg.get("timestamp"))
                    if exchange_ts is None or abs(arrival - exchange_ts) > 30:
                        continue
                    if not (bid > 0 and ask >= bid):
                        continue
                    quotes[symbol] = {
                        "exchange_ts": exchange_ts,
                        "arrival_ts": arrival,
                        "bid": bid,
                        "ask": ask,
                        "mid": (bid + ask) / 2.0,
                    }
                    # Bound filesystem churn while retaining 20 Hz trigger resolution.
                    if arrival - published.get(symbol, 0.0) < 0.05:
                        continue
                    _atomic_text(
                        os.path.join(DATA, "nbbo_%s.txt" % symbol.lower()),
                        "%.6f %.8f %.8f\n" % (exchange_ts, bid, ask),
                    )
                    published[symbol] = arrival
                    if arrival - last_status_at >= 1.0:
                        _status("LIVE", symbols, quotes, lote=lote)
                        last_status_at = arrival
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _status("RECONNECTING", symbols, quotes, exc, lote=lote)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 20.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="comma-separated US symbols")
    args = parser.parse_args()
    symbols = sorted({item.strip().upper() for item in args.symbols.split(",") if item.strip()})
    if not symbols or any(not item.isalnum() for item in symbols):
        raise SystemExit("invalid --symbols")
    os.chdir(REPO)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, loop.stop)
        except NotImplementedError:
            pass
    lotes = [symbols[i:i + MAX_POR_CONEXION]
             for i in range(0, len(symbols), MAX_POR_CONEXION)]
    tasks = [loop.create_task(run(l, i)) for i, l in enumerate(lotes)]
    try:
        loop.run_forever()
    finally:
        for t in tasks:
            t.cancel()
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    main()
