#!/usr/bin/env python3
"""perp_ws_bridge.py — puente TONTO por WebSocket a perps de acciones tokenizadas.
Mueve bytes a disco: cero computo de señal (CLAUDE.md).

POR QUE EXISTE (Yunior 2026-08-08: "todo websockets" + "keep it dynamic so that we can select
any ticker"): perp_stock_fetch.py resondea REST cada 15 s. Esto es un socket vivo.

LO QUE APORTA Y NADIE MAS NOS DA — el LADO AGRESOR. Medido el 2026-08-08 en
wss://ws.okx.com:8443/ws/v5/public canal `trades`: cada print trae side (buy/sell), tradeId
UNICO, px, sz y ts en ms. Es la unica cinta firmada a la que llegamos hoy: Databento no tiene
licencia live, el WS de London Strategic Edge publica la PUJA en el campo price (1.110/1.110
ticks price==bid), Finnhub muestrea y no trae lado, e IBKR esta apagado.

CAVEAT QUE VA EN LA CABECERA DEL PROPIO DATO (data/perp_tape/<dia>/<sym>.txt): esto es el
PERPETUO, no la cinta US, y es FINISIMO — volumen 24 h medido: SPY $988, QQQ $4.562,
DRAM $37.016. Que su delta anticipe al subyacente es una pregunta EMPIRICA sin medir.
Se archiva para poder medirla; no se usa como señal hasta que alguien la mida.

tradeId en cada linea = la cinta es deduplicable de verdad, al reves que data/prints/
(89,1% de duplicados medidos y ya IRREPARABLES por no llevar identificador).

SALIDA:
  data/perp_tape/<YYYY-MM-DD>/<sym>.txt  append "TS_MS TRADE_ID PX SZ SIDE"
  data/nbbo_<sym>usdt.txt                "BID ASK TS" (mismo contrato que perp_nbbo_bridge)
  data/perp_ws_state.json                latido + contadores por simbolo (atomico)

Uso: perp_ws_bridge.py [SYM ...] [--seconds N] [--no-tape]
Sin simbolos: los de data/fleet.txt; OKX primario y Bybit WS para sus huecos.
"""
import argparse
import asyncio
import fcntl
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
INSTRUMENTS = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
BYBIT_TICKERS = "https://api.bybit.com/v5/market/tickers?category=linear&symbol="
BYBIT_WS = "wss://stream.bybit.com/v5/public/linear"
UA = {"User-Agent": "Mozilla/5.0"}
LOCK = "data/.perp_ws.lock"
STATE = "data/perp_ws_state.json"
PERP_STATE = "data/perp_stocks.json"
REQUESTS = "data/perp_requests.txt"       # append desde cualquier chart_bridge
REQUEST_STATUS = "data/perp_request_status.json"
TAPE_DIR = "data/perp_tape"
# perp_stock_fetch.py excluye los mismos por la misma razon medida: GLD no tiene perp en
# ningun venue, y STX-USDT-SWAP es el token Stacks (~$0,14), no Seagate (~$853).
EXCLUDE = {"GLD", "STX"}
STATE_EVERY_S = 5


def tomar_lock():
    """Un solo puente vivo: dos sockets escribiendo el mismo tape es corrupcion silenciosa."""
    f = open(LOCK, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[perp-ws] ya hay otro puente vivo (lock) -> salgo", file=sys.stderr)
        sys.exit(1)
    f.write(str(os.getpid()))
    f.flush()
    return f


def perps_disponibles():
    """Bases con -USDT-SWAP en OKX. Levanta si la API no responde: sin esto no se sabe que
    pedir, y suscribirse a un contrato inexistente devuelve error por cada simbolo."""
    req = urllib.request.Request(INSTRUMENTS, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.load(r)
    if d.get("code") != "0":
        raise RuntimeError("okx instruments: code=%s %s" % (d.get("code"), d.get("msg")))
    return {row["instId"].split("-")[0] for row in d.get("data", [])
            if row.get("instId", "").endswith("-USDT-SWAP")}


def disponible_bybit(sym):
    req = urllib.request.Request(BYBIT_TICKERS + urllib.parse.quote(sym + "USDT"), headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.load(r)
    return d.get("retCode") == 0 and bool(d.get("result", {}).get("list"))


def pedidos_dinamicos():
    """Requests are intentionally append-only: multiple chart processes cannot lose updates."""
    try:
        rows = open(REQUESTS).read().split()
    except OSError:
        rows = []
    return {re.sub(r"USDT$", "", s.upper()) for s in rows
            if re.fullmatch(r"[A-Z0-9.]{1,20}(?:USDT)?", s.upper())}


def simbolos(args_syms):
    pedidos = [s.upper() for s in args_syms] if args_syms else \
        [s.upper() for s in open("data/fleet.txt").read().split()]
    pedidos = list(dict.fromkeys(pedidos + sorted(pedidos_dinamicos())))
    disp = perps_disponibles()
    okx, bybit, sin = [], [], []
    for s in pedidos:
        if s in EXCLUDE:
            continue
        if s in disp:
            okx.append(s)
        else:
            try:
                (bybit if disponible_bybit(s) else sin).append(s)
            except (urllib.error.URLError, ValueError, KeyError):
                sin.append(s)
    if sin:
        print("[perp-ws] sin perp en OKX/Bybit (se DECLARAN, no se rellenan): %s" % " ".join(sin),
              file=sys.stderr)
    if not okx and not bybit:
        raise RuntimeError("ningun simbolo pedido tiene perp en OKX/Bybit")
    return okx, bybit


def escribe_atomico(path, texto):
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Tape:
    """Append por simbolo y dia. El dia sale del ts de CADA trade, no del reloj del proceso."""

    def __init__(self, activo=True):
        self.activo = activo
        self._fh = {}

    def escribe(self, sym, ts_ms, trade_id, px, sz, side):
        if not self.activo:
            return
        dia = time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000.0))
        clave = (sym, dia)
        fh = self._fh.get(clave)
        if fh is None:
            d = os.path.join(TAPE_DIR, dia)
            os.makedirs(d, exist_ok=True)
            fh = open(os.path.join(d, "%s.txt" % sym.lower()), "a")
            self._fh[clave] = fh
        fh.write("%d %s %s %s %s\n" % (ts_ms, trade_id, px, sz, side))

    def flush(self):
        for fh in self._fh.values():
            fh.flush()

    def close(self):
        for fh in self._fh.values():
            try:
                fh.close()
            except OSError:
                pass


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def snapshot_stats(stats, now=None):
    """Contrato existente de perp_stocks.json, ahora alimentado por WS."""
    now = now or time.time()
    out = {}
    for sym, r in stats.items():
        px, bid, ask = r.get("px"), r.get("bid"), r.get("ask")
        if not (px and bid and ask and bid > 0 and ask >= bid):
            continue
        mid = (bid + ask) / 2.0
        out[sym] = {
            "sym": sym, "px": px, "bid": bid, "ask": ask,
            "spread_pct": round((ask - bid) / mid * 100, 4),
            "vol24h_usd": r.get("vol24h_usd"), "oi_usd": r.get("oi_usd"),
            "src": r.get("src"), "transport": "websocket",
            "feed_ts": r.get("feed_ts"),
            "feed_age_s": round(max(0.0, now - r.get("feed_ts", now)), 3),
        }
    return out


def _okx_args(syms):
    args = []
    for s in syms:
        inst = "%s-USDT-SWAP" % s
        args.extend({"channel": channel, "instId": inst}
                    for channel in ("trades", "bbo-tbt", "tickers", "open-interest"))
    return args


async def _okx_dynamic_subscriber(ws, queue):
    while True:
        sym = await queue.get()
        await ws.send(json.dumps({"op": "subscribe", "args": _okx_args([sym])}))


async def corre_okx(syms, tape, trades, quotes, ultimo, stats, dynamic_queue=None):
    import websockets
    args = _okx_args(syms)

    async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": args}))
        subscriber = asyncio.create_task(_okx_dynamic_subscriber(ws, dynamic_queue)) \
            if dynamic_queue is not None else None
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    continue  # el ping_interval mantiene vivo el socket; silencio != caida
                m = json.loads(raw)
                if m.get("event") == "error":
                    print("[perp-ws] error del vendor: %s" % raw[:200], file=sys.stderr)
                    continue
                if m.get("event"):
                    continue
                arg = m.get("arg") or {}
                canal = arg.get("channel")
                sym = (arg.get("instId") or "").split("-")[0]
                for d in m.get("data", []):
                    if canal == "trades":
                        try:
                            ts_ms = int(d["ts"])
                            tape.escribe(sym, ts_ms, d["tradeId"], d["px"], d["sz"], d["side"])
                        except (KeyError, ValueError):
                            continue  # trade malformado se SALTA; jamas se inventa el lado
                        trades[sym] = trades.get(sym, 0) + 1
                        ultimo[sym] = time.time()
                        stats[sym].update(px=float(d["px"]), feed_ts=ts_ms / 1000.0)
                    elif canal == "bbo-tbt":
                        bids, asks = d.get("bids") or [], d.get("asks") or []
                        if not bids or not asks:
                            continue  # medio libro no es un NBBO: no se escribe
                        try:
                            bid, ask = float(bids[0][0]), float(asks[0][0])
                        except (IndexError, ValueError):
                            continue
                        if not (bid > 0 and ask > 0 and ask >= bid):
                            continue
                        escribe_atomico("data/nbbo_%susdt.txt" % sym.lower(),
                                        "%.6f %.6f %.3f\n" % (bid, ask, time.time()))
                        quotes[sym] = quotes.get(sym, 0) + 1
                        ultimo[sym] = time.time()
                        stats[sym].update(
                            bid=bid, ask=ask,
                            feed_ts=_num(d.get("ts")) / 1000.0 if _num(d.get("ts")) else time.time())
                    elif canal == "tickers":
                        px = _num(d.get("last")); bid = _num(d.get("bidPx")); ask = _num(d.get("askPx"))
                        if px: stats[sym]["px"] = px
                        if bid: stats[sym]["bid"] = bid
                        if ask: stats[sym]["ask"] = ask
                        vol_base = _num(d.get("volCcy24h"))
                        if vol_base is not None and px:
                            stats[sym]["vol24h_usd"] = vol_base * px
                        ts = _num(d.get("ts"))
                        stats[sym]["feed_ts"] = ts / 1000.0 if ts else time.time()
                        ultimo[sym] = time.time()
                    elif canal == "open-interest":
                        oi = _num(d.get("oiUsd"))
                        if oi is not None: stats[sym]["oi_usd"] = oi
                        ts = _num(d.get("ts"))
                        if ts: stats[sym]["feed_ts"] = ts / 1000.0
                        ultimo[sym] = time.time()
        finally:
            if subscriber:
                subscriber.cancel()


async def ping_bybit(ws):
    while True:
        await asyncio.sleep(20)
        await ws.send(json.dumps({"op": "ping"}))


async def _bybit_dynamic_subscriber(ws, queue):
    while True:
        s = await queue.get()
        topics = ["publicTrade.%sUSDT" % s, "orderbook.1.%sUSDT" % s,
                  "tickers.%sUSDT" % s]
        await ws.send(json.dumps({"op": "subscribe", "args": topics}))


async def corre_bybit(syms, tape, trades, quotes, ultimo, stats, dynamic_queue=None):
    import websockets
    topics = []
    for s in syms:
        topics.extend(["publicTrade.%sUSDT" % s, "orderbook.1.%sUSDT" % s,
                       "tickers.%sUSDT" % s])
    async with websockets.connect(BYBIT_WS, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": topics}))
        ping = asyncio.create_task(ping_bybit(ws))
        subscriber = asyncio.create_task(_bybit_dynamic_subscriber(ws, dynamic_queue)) \
            if dynamic_queue is not None else None
        try:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("success") is False:
                    raise RuntimeError("bybit subscribe: %s" % str(m)[:240])
                topic = m.get("topic") or ""
                if topic.startswith("publicTrade."):
                    sym = topic.split(".", 1)[1][:-4]
                    for d in m.get("data") or []:
                        try:
                            ts_ms = int(d["T"])
                            side = str(d["S"]).lower()
                            if side not in ("buy", "sell"):
                                continue
                            tape.escribe(sym, ts_ms, d["i"], d["p"], d["v"], side)
                        except (KeyError, TypeError, ValueError):
                            continue
                        trades[sym] = trades.get(sym, 0) + 1
                        ultimo[sym] = time.time()
                        stats[sym].update(px=float(d["p"]), feed_ts=ts_ms / 1000.0)
                elif topic.startswith("orderbook.1."):
                    sym = topic.split(".", 2)[2][:-4]
                    d = m.get("data") or {}
                    bids, asks = d.get("b") or [], d.get("a") or []
                    try:
                        bid, ask = float(bids[0][0]), float(asks[0][0])
                    except (IndexError, TypeError, ValueError):
                        continue
                    if not (bid > 0 and ask >= bid):
                        continue
                    escribe_atomico("data/nbbo_%susdt.txt" % sym.lower(),
                                    "%.6f %.6f %.3f\n" % (bid, ask, time.time()))
                    quotes[sym] = quotes.get(sym, 0) + 1
                    ultimo[sym] = time.time()
                    stats[sym].update(bid=bid, ask=ask,
                                      feed_ts=float(m.get("ts") or time.time() * 1000) / 1000.0)
                elif topic.startswith("tickers."):
                    sym = topic.split(".", 1)[1][:-4]
                    d = m.get("data") or {}
                    mapping = {"lastPrice": "px", "bid1Price": "bid", "ask1Price": "ask",
                               "turnover24h": "vol24h_usd", "openInterestValue": "oi_usd"}
                    for src, dst in mapping.items():
                        v = _num(d.get(src))
                        if v is not None: stats[sym][dst] = v
                    stats[sym]["feed_ts"] = float(m.get("ts") or time.time() * 1000) / 1000.0
                    ultimo[sym] = time.time()
        finally:
            ping.cancel()
            if subscriber:
                subscriber.cancel()


async def corre(okx_syms, bybit_syms, segundos, tape):
    syms = okx_syms + bybit_syms
    trades = {s: 0 for s in syms}
    quotes = {s: 0 for s in syms}
    ultimo = {s: 0.0 for s in syms}
    arranque = time.time()
    fuentes = {s: "okx-ws" for s in okx_syms}
    fuentes.update({s: "bybit-ws" for s in bybit_syms})
    stats = {s: {"src": fuentes[s], "feed_ts": 0.0} for s in syms}
    resolved_requests = set(syms)
    request_status = {s: {"ok": True, "src": fuentes[s], "ts": time.time()} for s in syms}
    okx_dynamic, bybit_dynamic = asyncio.Queue(), asyncio.Queue()

    def start_socket_tasks():
        out = []
        if okx_syms:
            out.append(asyncio.create_task(corre_okx(okx_syms, tape, trades, quotes, ultimo,
                                                     stats, okx_dynamic)))
        if bybit_syms:
            out.append(asyncio.create_task(corre_bybit(bybit_syms, tape, trades, quotes, ultimo,
                                                       stats, bybit_dynamic)))
        return out

    tasks = start_socket_tasks()
    try:
        while True:
            if segundos and time.time() - arranque >= segundos:
                break
            await asyncio.sleep(min(STATE_EVERY_S, segundos or STATE_EVERY_S))
            ahora = time.time()
            # Dynamic universe: a chart can request ANY base. Resolve only new requests,
            # declare rejects, then reconnect the vendor sockets with the expanded set.
            # The process/heartbeat remains alive and existing stats are preserved.
            pending = sorted(pedidos_dinamicos() - resolved_requests)
            if pending:
                try:
                    okx_catalog = await asyncio.to_thread(perps_disponibles)
                except Exception as e:
                    okx_catalog = set()
                    print("[perp-ws] catálogo OKX dinámico falló: %s" % e, file=sys.stderr)
                changed = False
                for s in pending:
                    resolved_requests.add(s)
                    if s in EXCLUDE:
                        request_status[s] = {"ok": False, "why": "símbolo excluido/colisión", "ts": ahora}
                        continue
                    if s in okx_catalog:
                        okx_syms.append(s); src = "okx-ws"; await okx_dynamic.put(s)
                    else:
                        try:
                            if not await asyncio.to_thread(disponible_bybit, s):
                                request_status[s] = {"ok": False,
                                                     "why": "no existe en OKX ni Bybit", "ts": ahora}
                                continue
                        except Exception as e:
                            request_status[s] = {"ok": False, "why": "validación falló: %s" % e,
                                                 "ts": ahora}
                            continue
                        bybit_syms.append(s); src = "bybit-ws"; await bybit_dynamic.put(s)
                    syms.append(s); fuentes[s] = src
                    trades[s] = quotes[s] = 0; ultimo[s] = 0.0
                    stats[s] = {"src": src, "feed_ts": 0.0}
                    request_status[s] = {"ok": True, "src": src, "ts": ahora}
                    changed = True
                    print("[perp-ws] suscripción DINÁMICA %sUSDT via %s" % (s, src),
                          file=sys.stderr, flush=True)
                escribe_atomico(REQUEST_STATUS, json.dumps(request_status, indent=1, sort_keys=True))
                # No reconnect: subscriber tasks send a small additional subscribe frame.
            tape.flush()
            snap = snapshot_stats(stats, ahora)
            if snap:
                escribe_atomico(PERP_STATE, json.dumps(snap, indent=1, sort_keys=True))
            escribe_atomico(STATE, json.dumps({
                "ts": int(ahora), "latido": int(ahora), "pid": os.getpid(),
                "vivo_s": int(ahora - arranque), "fuente": "perp-ws",
                "fuentes": fuentes, "simbolos": len(syms), "snapshot_ws": len(snap),
                "trades": trades, "quotes": quotes,
                "mudos": sorted(s for s in syms
                                if not ultimo[s] or ahora - ultimo[s] > 300),
            }, indent=1, sort_keys=True))
            for task in tasks:
                if task.done():
                    exc = task.exception()
                    if exc:
                        raise exc
                    raise RuntimeError("socket de perpetuos termino sin solicitarlo")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return trades, quotes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--seconds", type=int, default=0, help="0 = para siempre")
    ap.add_argument("--no-tape", action="store_true")
    a = ap.parse_args()

    lock = tomar_lock()
    try:
        okx_syms, bybit_syms = simbolos(a.syms)
    except (RuntimeError, urllib.error.URLError) as e:
        print("[perp-ws] no se pudo resolver el universo: %s" % e, file=sys.stderr)
        return 1
    syms = okx_syms + bybit_syms
    print("[perp-ws] %d simbolos: OKX=%d Bybit=%d | %s" %
          (len(syms), len(okx_syms), len(bybit_syms), " ".join(syms)), file=sys.stderr)

    tape = Tape(activo=not a.no_tape)
    try:
        trades, quotes = asyncio.run(corre(okx_syms, bybit_syms, a.seconds, tape))
    except KeyboardInterrupt:
        return 0
    finally:
        tape.flush()
        tape.close()
        lock.close()
    tot_t, tot_q = sum(trades.values()), sum(quotes.values())
    print("[perp-ws] fin: %d trades, %d quotes" % (tot_t, tot_q), file=sys.stderr)
    return 0 if (tot_t or tot_q) else 1


if __name__ == "__main__":
    sys.exit(main())
