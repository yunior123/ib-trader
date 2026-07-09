#!/usr/bin/env python3
"""Alert bot — watches today's watchlist during the trade window and fires
signals to BOTH the human (ntfy/Mac) and the Claude decision session (signal
file). This is the "send data to me AND to claude-u" piece.

Per-second-ish scan of each candidate. A candidate triggers a BUY-CONSIDER
signal when it makes a fresh intraday high with momentum (a real breakout, not
just sitting green). Detection may run premarket/afterhours (4:00-20:00), but it
only emits actionable BUY signals inside the RTH execution window 9:30-10:00 ET
(Yunior's window; can be widened via env). It never places orders — Claude does
(selectivity), guarded by the watchdog.
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from price import last_price  # noqa: E402

POLL = float(os.getenv("ALERT_POLL", "2.0"))
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
    print(f"[alert_bot] up. window {WIN_START}-{WIN_END} ET. poll {POLL}s", flush=True)
    highs = {}       # sym -> running intraday high seen by us
    fired = set()    # sym already signaled today (one BUY-CONSIDER per name)
    day = None
    while True:
        try:
            today = datetime.now().astimezone().strftime("%Y%m%d")
            if today != day:
                day, highs, fired = today, {}, set()
            wl = state.read_watchlist()
            cands = wl.get("candidates", [])
            for c in cands:
                sym = c["sym"]
                q = last_price(sym)
                if not q:
                    continue
                px = q["price"]
                prev_high = highs.get(sym, c.get("price", px))
                # fresh-high breakout with real gain over prior close
                gain = (px - (q.get("prev_close") or c.get("price", px))) / \
                       (q.get("prev_close") or px) * 100
                if px > prev_high:
                    highs[sym] = px
                    if in_window() and sym not in fired and gain >= 5.0:
                        fired.add(sym)
                        msg = (f"{sym} rompe maximo intradia ${px:.4f} (+{gain:.1f}%). "
                               f"Candidato de compra — claude evalua.")
                        notify("BUY-CONSIDER", msg, urgent=True)
                        state.append_signal({"kind": "buy_consider", "sym": sym,
                                             "price": px, "gain_pct": round(gain, 2),
                                             "watchlist_score": c.get("score"),
                                             "note": "fresh intraday high in window"})
                        print(f"[alert_bot] SIGNAL {sym} ${px:.4f} +{gain:.1f}%", flush=True)
        except Exception as e:
            print(f"[alert_bot] err {str(e)[:120]}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
