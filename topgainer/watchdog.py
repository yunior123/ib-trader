#!/usr/bin/env python3
"""Position watchdog — the never-lose-money GUARANTEE. Deterministic, no LLM.

This is the answer to Yunior's #1 fear: "Claude buys then stops looping and
can't sell." The watchdog does NOT depend on Claude at all. It runs as its own
process (keepalive/launchd, restarted forever). The instant a position exists in
data/topgainer/position.json, the watchdog owns it and checks the price EVERY
SECOND until it exits. Claude may ALSO decide to sell early for profit, but even
if the Claude session dies, hangs, or never loops, the position is never orphaned.

Exit rules (mirror the validated engine, never-loss enforced):
  - PROFIT TARGET: price >= exit_limit_price(entry)  -> sell (locked profit).
  - TRAILING LOCK: once price has been >= floor, if it retraces TRAIL_PCT from
    the peak AND is still >= floor -> sell (lock the gain we already have).
  - NEVER SELL BELOW FLOOR: floor = max(entry+1%, breakeven incl. both fees).
    If price is under the floor we HOLD THE BAG and keep watching — across the
    rest of the day and following days if needed (Yunior's rule: cash > bags,
    but never realize a loss). The watchdog never force-sells at a loss.

Alerts: on every exit (and when it first drops under floor into "bag" mode) it
notifies phone (ntfy) + Mac and appends a signal so the Claude session and
Yunior both see what happened.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from price import last_price  # noqa: E402
from day_trading_bot import floor_price, exit_limit_price, DEFAULT_CONFIG  # noqa: E402

POLL = float(os.getenv("WATCHDOG_POLL", "1.0"))     # per-second
TRAIL_PCT = float(os.getenv("WATCHDOG_TRAIL", "1.5"))  # % retrace from peak to lock
NTFY_TOPIC = "yunior-daily-brief-2026"
HERE = os.path.dirname(os.path.abspath(__file__))
EXEC = os.path.join(HERE, "exec_trade.py")
PY = os.path.join(os.path.dirname(HERE), "venv", "bin", "python")
if not os.path.exists(PY):
    PY = sys.executable


def notify(title: str, msg: str, urgent: bool = False):
    try:
        subprocess.Popen(["osascript", "-e",
                          f'display notification "{msg}" with title "{title}" sound name "Glass"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        subprocess.Popen(["curl", "-s", "-m", "10", "-X", "POST", f"https://ntfy.sh/{NTFY_TOPIC}",
                          "-H", f"Title: {title}", "-H", f"Priority: {'urgent' if urgent else 'default'}",
                          "-H", "Tags: chart", "-d", msg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    state.append_signal({"kind": "watchdog", "title": title, "msg": msg})


def sell(pos, reason: str):
    r = subprocess.run([PY, EXEC, "sell", pos["sym"], str(pos["qty"]),
                        "--entry", str(pos["entry"])],
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    notify(f"VENDER {pos['sym']}", f"{reason} — {out.strip()[:120]}", urgent=True)
    print(f"[watchdog] SELL {pos['sym']}: {reason}\n{out}", flush=True)


def manage(pos):
    cfg = DEFAULT_CONFIG
    entry, qty = pos["entry"], pos["qty"]
    floor = floor_price(entry, qty, cfg)
    target = exit_limit_price(entry, qty, cfg)
    peak = pos.get("peak", entry)
    reached_floor = pos.get("reached_floor", False)
    in_bag = pos.get("in_bag", False)

    q = last_price(pos["sym"])
    if not q:
        return pos, False
    px = q["price"]
    if px > peak:
        peak = px
    if px >= floor:
        reached_floor = True
        if in_bag:
            notify(f"{pos['sym']} recuperado", f"px {px:.4f} >= floor {floor:.4f}, en verde otra vez")
            in_bag = False
    elif reached_floor is False and not in_bag:
        # dropped under floor before ever locking a gain -> bag mode
        in_bag = True
        notify(f"{pos['sym']} en rojo", f"px {px:.4f} < floor {floor:.4f} — HOLD, nunca vendo con perdida")

    pos.update(peak=peak, reached_floor=reached_floor, in_bag=in_bag, last=px)
    state.write_position(pos)

    # exit decisions (never below floor)
    if px >= target:
        sell(pos, f"target hit px {px:.4f} >= {target:.4f}")
        return pos, True
    if reached_floor and px >= floor:
        retrace = (peak - px) / peak * 100 if peak else 0
        if retrace >= TRAIL_PCT:
            sell(pos, f"trail lock px {px:.4f} (peak {peak:.4f}, -{retrace:.2f}%) >= floor {floor:.4f}")
            return pos, True
    return pos, False


def main():
    print(f"[watchdog] up. poll={POLL}s trail={TRAIL_PCT}% floor=never-loss. "
          f"armed={state.is_armed()}", flush=True)
    idle_note = 0
    while True:
        try:
            pos = state.read_position()
            if not pos:
                idle_note += 1
                if idle_note % 300 == 1:
                    print("[watchdog] no position, waiting", flush=True)
                time.sleep(POLL)
                continue
            idle_note = 0
            pos, closed = manage(pos)
            if closed and state.read_position() is None:
                print(f"[watchdog] {pos['sym']} closed, back to idle", flush=True)
        except Exception as e:
            print(f"[watchdog] err {str(e)[:120]}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
