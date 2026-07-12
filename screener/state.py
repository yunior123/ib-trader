#!/usr/bin/env python3
"""Shared state + IO for the top-gainer system.

Single source of truth on disk so every component (scanner, alert bot, the
headless Claude decision session, the watchdog, the exec scripts) coordinates
through files instead of shared memory. Every file is small JSON, atomically
written, so a crash never leaves a half-written record.

Files (all under data/screener/):
  watchlist_YYYYMMDD.json   scanner output: today's selective candidates
  signals.jsonl             append-only alerts the Claude session consumes
  position.json             the ONE open position the watchdog owns (or null)
  decisions.jsonl           append-only log of every buy/sell Claude/watchdog did
  armed                     interlock file; live orders only fire when it exists
"""
import json
import os
import time
from datetime import datetime, timezone

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "screener")
os.makedirs(BASE, exist_ok=True)

POSITION = os.path.join(BASE, "position.json")
SIGNALS = os.path.join(BASE, "signals.jsonl")
DECISIONS = os.path.join(BASE, "decisions.jsonl")
ARMED = os.path.join(BASE, "armed")

# America/Toronto == Mac local tz (verified in fleet). Keep it simple.
TORONTO_OFFSET_NOTE = "Mac local tz is Toronto/ET"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def utc_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _atomic_write(path: str, text: str) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def is_armed() -> bool:
    """Live orders fire ONLY when this interlock file exists.
    Arm with:  touch data/screener/armed     Disarm with:  rm data/screener/armed"""
    return os.path.exists(ARMED)


def watchlist_path(day: str = None) -> str:
    day = day or datetime.now().astimezone().strftime("%Y%m%d")
    return os.path.join(BASE, f"watchlist_{day}.json")


def read_watchlist(day: str = None):
    p = watchlist_path(day)
    if not os.path.exists(p):
        return {"date": day, "candidates": []}
    with open(p) as f:
        return json.load(f)


def write_watchlist(data: dict, day: str = None) -> str:
    p = watchlist_path(day)
    _atomic_write(p, json.dumps(data, indent=2))
    return p


def read_position():
    if not os.path.exists(POSITION):
        return None
    with open(POSITION) as f:
        txt = f.read().strip()
    if not txt or txt == "null":
        return None
    return json.loads(txt)


def write_position(pos) -> None:
    _atomic_write(POSITION, json.dumps(pos, indent=2) if pos else "null")


def clear_position() -> None:
    write_position(None)


def append_signal(sig: dict) -> None:
    sig = {"ts": now_iso(), **sig}
    with open(SIGNALS, "a") as f:
        f.write(json.dumps(sig) + "\n")


def unconsumed_signals():
    """Signals the Claude session hasn't acted on yet (consumed flag written back)."""
    if not os.path.exists(SIGNALS):
        return []
    out = []
    with open(SIGNALS) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except Exception:
                continue   # partial/malformed line — skip, never crash the decision cycle
            if not s.get("consumed"):
                out.append(s)
    return out


def log_decision(d: dict) -> None:
    d = {"ts": now_iso(), **d}
    with open(DECISIONS, "a") as f:
        f.write(json.dumps(d) + "\n")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print("armed:", is_armed())
        print("position:", json.dumps(read_position(), indent=2))
        print("watchlist:", json.dumps(read_watchlist(), indent=2))
        print("unconsumed signals:", len(unconsumed_signals()))
    elif cmd == "pos":
        # print ONLY the open position symbol (empty if flat) — for the heartbeat
        p = read_position()
        print(p["sym"] if p else "", end="")
    elif cmd == "arm":
        open(ARMED, "w").write(now_iso())
        print("ARMED — live orders enabled")
    elif cmd == "disarm":
        if os.path.exists(ARMED):
            os.remove(ARMED)
        print("DISARMED — live orders blocked")
