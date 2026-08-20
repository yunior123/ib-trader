#!/usr/bin/env python3
"""Realtime U.S.-equity execution-tape adapter for the footprint engine.

Massive supplies consolidated SIP trades and NBBO quotes but no exchange-native aggressor side.
This bridge joins each trade to the latest *earlier* quote (max 2 s), then applies quote rule and
tick rule while preserving unknowns. It only moves auditable rows to disk; pattern math remains
in C++. A delayed entitlement is rejected from the output path, never relabeled realtime.

Output: data/equity_footprint_tape/footprint_tape_<sym>.txt
        EPOCH PRICE SIZE DIR BID ASK METHOD
METHOD Q=quote rule, T=tick rule, U=unknown. No value is forced into Bid or Ask.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TAPE_DIR = ROOT / "data" / "equity_footprint_tape"
STATE = ROOT / "data" / "equity_footprint_ws_state.json"
DEFAULT_WS = "wss://socket.massive.com/stocks"
QUOTE_MAX_AGE_S = 2.0
LIVE_MAX_AGE_S = 10.0


def _env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for raw in (ROOT / "config" / "feeds.env").read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def secret(*names: str) -> str | None:
    env = _env_file()
    return next((os.environ.get(n) or env.get(n) for n in names if os.environ.get(n) or env.get(n)), None)


def atomic_json(path: Path, body: dict) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(body, separators=(",", ":")))
    os.replace(tmp, path)


class Classifier:
    """Lee/Ready classifier. Quote must precede the trade; zero tick inherits last direction."""

    def __init__(self, quote_max_age_s: float = QUOTE_MAX_AGE_S) -> None:
        self.quote_max_age_s = quote_max_age_s
        self.quotes: dict[str, tuple[float, float, float]] = {}
        self.last: dict[str, tuple[float, int]] = {}

    def quote(self, sym: str, epoch: float, bid: float, ask: float) -> None:
        if epoch > 0 and bid > 0 and ask >= bid:
            self.quotes[sym] = (epoch, bid, ask)

    def trade(self, sym: str, epoch: float, price: float) -> tuple[int, float, float, str]:
        q = self.quotes.get(sym)
        direction, method, bid, ask = 0, "U", 0.0, 0.0
        if q and 0 <= epoch - q[0] <= self.quote_max_age_s:
            _, bid, ask = q
            eps = max(1e-9, price * 1e-9)
            if price >= ask - eps:
                direction, method = 1, "Q"
            elif price <= bid + eps:
                direction, method = -1, "Q"
        if not direction:
            prior = self.last.get(sym)
            if prior:
                if price > prior[0]:
                    direction, method = 1, "T"
                elif price < prior[0]:
                    direction, method = -1, "T"
                elif prior[1]:
                    direction, method = prior[1], "T"
        self.last[sym] = (price, direction or (self.last.get(sym) or (0, 0))[1])
        return direction, bid, ask, method


class TapeWriter:
    def __init__(self, directory: Path = TAPE_DIR) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.files: dict[str, object] = {}

    def write(self, sym: str, epoch: float, price: float, size: float,
              direction: int, bid: float, ask: float, method: str) -> None:
        fh = self.files.get(sym)
        if fh is None:
            fh = open(self.directory / f"footprint_tape_{sym.lower()}.txt", "a", buffering=1)
            self.files[sym] = fh
        fh.write(f"{epoch:.6f} {price:.8f} {size:.8f} {direction} {bid:.8f} {ask:.8f} {method}\n")

    def close(self) -> None:
        for fh in self.files.values():
            fh.close()


def symbols_from(args: list[str]) -> list[str]:
    if args:
        raw = args
    else:
        path = ROOT / "data" / "provider_syms.txt"
        if not path.exists():
            path = ROOT / "data" / "fleet.txt"
        raw = path.read_text().split()
    return list(dict.fromkeys(s.upper() for s in raw if re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", s.upper())))


async def run_massive(symbols: list[str], seconds: float = 0) -> int:
    import asyncio
    import websockets

    key = secret("MASSIVE_KEY", "POLYGON_KEY")
    if not key:
        raise RuntimeError("MASSIVE_KEY/POLYGON_KEY absent")
    url = os.environ.get("MASSIVE_WS_URL", DEFAULT_WS)
    classifier, writer = Classifier(), TapeWriter()
    counts = {"trades": 0, "quotes": 0, "Q": 0, "T": 0, "U": 0,
              "late_rejected": 0, "duplicates": 0}
    seen, seen_set = deque(maxlen=100_000), set()
    started = time.time()
    stop_at = started + seconds if seconds else None

    def state(status: str, reason: str | None = None) -> None:
        atomic_json(STATE, {"provider": "massive", "status": status, "reason": reason,
                            "symbols": symbols, "counts": counts, "ts": time.time(),
                            "pid": os.getpid(), "doctrine": "REALTIME_OR_FAIL_CLOSED"})

    state("CONNECTING")
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=16 << 20) as ws:
            await ws.send(json.dumps({"action": "auth", "params": key}))
            authed = False
            while not authed:
                rows = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                for row in rows if isinstance(rows, list) else [rows]:
                    if row.get("ev") == "status" and row.get("status") == "auth_success":
                        authed = True
                    elif row.get("ev") == "status" and row.get("status") in {"auth_failed", "error"}:
                        raise RuntimeError(row.get("message") or row.get("status"))
            params = ",".join([f"T.{s}" for s in symbols] + [f"Q.{s}" for s in symbols])
            await ws.send(json.dumps({"action": "subscribe", "params": params}))
            state("LIVE_WAITING")
            last_state = 0.0
            while not stop_at or time.time() < stop_at:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0 if stop_at else 30.0)
                except asyncio.TimeoutError:
                    state("LIVE" if counts["trades"] else "LIVE_WAITING")
                    continue
                rows = json.loads(raw)
                for row in rows if isinstance(rows, list) else [rows]:
                    ev, sym = row.get("ev"), str(row.get("sym") or "").upper()
                    if ev == "status" and row.get("status") == "error":
                        raise RuntimeError(row.get("message") or "Massive subscription error")
                    if not sym:
                        continue
                    if ev == "Q":
                        epoch = float(row.get("t") or 0) / 1000.0
                        classifier.quote(sym, epoch, float(row.get("bp") or 0), float(row.get("ap") or 0))
                        counts["quotes"] += 1
                    elif ev == "T":
                        epoch = float(row.get("t") or 0) / 1000.0
                        if epoch <= 0 or time.time() - epoch > LIVE_MAX_AGE_S:
                            counts["late_rejected"] += 1
                            continue
                        price, size = float(row.get("p") or 0), float(row.get("s") or 0)
                        if price <= 0 or size <= 0:
                            continue
                        ident = (sym, row.get("q"), row.get("t"), row.get("x"), price, size)
                        if ident in seen_set:
                            counts["duplicates"] += 1
                            continue
                        if len(seen) == seen.maxlen:
                            seen_set.discard(seen[0])
                        seen.append(ident); seen_set.add(ident)
                        direction, bid, ask, method = classifier.trade(sym, epoch, price)
                        writer.write(sym, epoch, price, size, direction, bid, ask, method)
                        counts["trades"] += 1; counts[method] += 1
                if time.time() - last_state >= 2:
                    state("LIVE" if counts["trades"] else "LIVE_WAITING")
                    last_state = time.time()
    except Exception as exc:
        state("FAILED", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        writer.close()
    state("STOPPED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Massive realtime equity tape -> footprint rows")
    parser.add_argument("symbols", nargs="*")
    parser.add_argument("--provider", choices=["massive"], default="massive")
    parser.add_argument("--seconds", type=float, default=0, help="bounded probe/run; 0 = daemon")
    args = parser.parse_args()
    syms = symbols_from(args.symbols)
    if not syms:
        print("equity footprint: no symbols", file=sys.stderr); return 2
    import asyncio
    try:
        return asyncio.run(run_massive(syms, args.seconds))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"equity footprint FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
