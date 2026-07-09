#!/usr/bin/env python3
"""Alert bot — watches today's watchlist during the trade window and fires
signals to BOTH the human (ntfy/Mac) and the Claude decision session (signal
file). This is the "send data to me AND to claude-u" piece.

Per-second-ish scan of each candidate. CONFIRMED-BREAKOUT engine (parity with
topgainer_alert.cpp, the primary): Donchian intraday-high break + price must
HOLD at/above the broken level for TG_CONFIRM_SECS + CUSUM statistical burst
(fleet algos — never signal the first green spike). Only emits actionable BUY
signals inside the RTH execution window 9:30-10:00 ET (env-widenable). It never
places orders — Claude does (selectivity), guarded by the watchdog.
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from price import last_price  # noqa: E402

import math

POLL = float(os.getenv("ALERT_POLL", "2.0"))
CONFIRM_SECS = float(os.getenv("TG_CONFIRM_SECS", "45"))
BURST_MIN = float(os.getenv("TG_BURST_MIN", "0.015"))
FADE_TOL = float(os.getenv("TG_FADE_TOL", "0.002"))
WIN_START = os.getenv("ALERT_WIN_START", "09:30")
WIN_END = os.getenv("ALERT_WIN_END", "10:00")


def in_window(now=None):
    now = now or datetime.now().astimezone()
    hm = now.strftime("%H:%M")
    return WIN_START <= hm <= WIN_END and now.weekday() < 5


def notify(title, msg, urgent=False):
    # Mac-only por orden de Yunior 2026-07-09 (ntfy llegaba tarde/acumulado)
    import subprocess
    try:
        subprocess.Popen(["osascript", "-e",
                          f'display notification "{msg}" with title "{title}" sound name "Glass"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main():
    print(f"[alert_bot] up. window {WIN_START}-{WIN_END} ET. poll {POLL}s. "
          f"confirm {CONFIRM_SECS:.0f}s hold + CUSUM burst", flush=True)
    tracks = {}      # sym -> confirmed-breakout state (fleet detection suite)
    fired = set()    # sym already signaled today (one BUY-CONSIDER per name)
    day = None
    while True:
        try:
            today = datetime.now().astimezone().strftime("%Y%m%d")
            if today != day:
                day, tracks, fired = today, {}, set()
            wl = state.read_watchlist()
            cands = wl.get("candidates", [])
            for c in cands:
                sym = c["sym"]
                q = last_price(sym)
                if not q:
                    continue
                px = q["price"]
                tr = tracks.setdefault(sym, {"high": c.get("price", px) or px,
                                             "last_px": 0.0, "ret_var": 1e-6,
                                             "cusum_up": 0.0, "pending_level": 0.0,
                                             "pending_since": 0.0})
                gain = (px - (q.get("prev_close") or c.get("price", px))) / \
                       (q.get("prev_close") or px) * 100
                # 1) CUSUM burst filter (same math as the signal bots)
                if tr["last_px"] > 0 and px > 0:
                    r = math.log(px / tr["last_px"])
                    tr["ret_var"] += (r * r - tr["ret_var"]) / 50.0
                    tr["cusum_up"] = max(0.0, tr["cusum_up"] + r)
                tr["last_px"] = px
                hthr = max(6.0 * math.sqrt(tr["ret_var"]), BURST_MIN)
                now = time.time()
                if tr["pending_level"] > 0:
                    # 3) HOLD confirmation: stay at/above the broken level
                    if px < tr["pending_level"] * (1.0 - FADE_TOL):
                        print(f"[alert_bot] {sym} breakout FAILED (fell under "
                              f"{tr['pending_level']:.4f}) — re-armed", flush=True)
                        tr["pending_level"] = 0.0
                    elif now - tr["pending_since"] >= CONFIRM_SECS:
                        burst = tr["cusum_up"] >= hthr
                        if in_window() and sym not in fired and gain >= 5.0 and burst:
                            fired.add(sym)
                            held = now - tr["pending_since"]
                            msg = (f"{sym} breakout CONFIRMADO: aguanta {held:.0f}s sobre "
                                   f"${tr['pending_level']:.4f} (+{gain:.1f}%, CUSUM "
                                   f"+{tr['cusum_up']*100:.1f}%). Claude evalua.")
                            notify("BUY-CONSIDER", msg, urgent=True)
                            state.append_signal({"kind": "buy_consider", "sym": sym,
                                                 "price": px, "gain_pct": round(gain, 2),
                                                 "watchlist_score": c.get("score"),
                                                 "breakout_level": round(tr["pending_level"], 4),
                                                 "held_secs": round(held),
                                                 "cusum_pct": round(tr["cusum_up"] * 100, 2),
                                                 "note": f"CONFIRMED breakout: held {held:.0f}s "
                                                         f"above level, CUSUM burst"})
                            print(f"[alert_bot] CONFIRMED SIGNAL {sym} ${px:.4f} "
                                  f"+{gain:.1f}% (level {tr['pending_level']:.4f})", flush=True)
                            tr["cusum_up"] = 0.0
                            tr["pending_level"] = 0.0
                        elif not burst and now - tr["pending_since"] > CONFIRM_SECS * 4:
                            print(f"[alert_bot] {sym}: held level but no CUSUM burst — "
                                  f"stale, re-armed", flush=True)
                            tr["pending_level"] = 0.0
                if px > tr["high"]:
                    # 2) Donchian break: fresh high starts the confirmation clock
                    if tr["pending_level"] <= 0 and sym not in fired and gain >= 5.0:
                        tr["pending_level"] = tr["high"]
                        tr["pending_since"] = now
                        print(f"[alert_bot] {sym} breaks level {tr['high']:.4f} -> "
                              f"confirming ({CONFIRM_SECS:.0f}s hold + burst)", flush=True)
                    tr["high"] = px
        except Exception as e:
            print(f"[alert_bot] err {str(e)[:120]}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
