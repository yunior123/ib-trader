#!/usr/bin/env python3
"""Position watchdog — deterministic risk manager, no LLM.

Claude Code (the headless decision loop) is ALWAYS the decision-maker while it
is alive. The watchdog is the deterministic safety net that owns the position
the instant one exists in data/screener/position.json, checking the price every
second. Per Yunior's orders (2026-07-09) the screener trade is a fast in/out:
enter on confirmation, resolve within ~5 minutes ideally, 15 minutes max, and
ALWAYS use a stop loss (this replaces the old hold-the-bag mode for this bot).

Exit rules (first match wins):
  - STOP LOSS:    px <= entry*(1 - TG_STOP_PCT%)         -> flatten NOW.
  - PROFIT TARGET px >= exit_limit_price(entry)          -> sell (locked profit).
  - TRAILING LOCK once px has been >= floor, a TRAIL_PCT retrace from peak
                  while still >= floor                   -> sell (lock the gain).
  - TIME STOP:    held >= TG_MAX_HOLD_SEC (default 15m)  -> flatten, win or lose.
  - DEAD-MAN:     Claude decision loop silent (claude_alive stale) longer than
                  TG_DEADMAN_SEC while money is at risk  -> flatten IMMEDIATELY.
                  "If Claude Code stops responding, we sell immediately."

Broker reconciliation (fixes the ghost-position bug of 2026-07-09): every
TG_RECONCILE_SEC the watchdog asks IBKR (read-only) whether we actually still
hold the shares. If Yunior sold manually in TWS (or a resting GTC filled
broker-side), position.json is cleared/adjusted and the watchdog stands down
instead of spamming rejected sell orders and notifications.

Alerts: phone (ntfy) + Mac + a signal line for the Claude session on every exit.
"""
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from price import last_price  # noqa: E402
from day_trading_bot import floor_price, exit_limit_price, DEFAULT_CONFIG  # noqa: E402

POLL = float(os.getenv("WATCHDOG_POLL", "1.0"))          # per-second
TRAIL_PCT = float(os.getenv("WATCHDOG_TRAIL", "1.5"))    # % retrace from peak to lock
STOP_PCT = float(os.getenv("TG_STOP_PCT", "3.0"))        # hard stop loss below entry
MAX_HOLD = float(os.getenv("TG_MAX_HOLD_SEC", "900"))    # time-box: 15 min max/trade
DEADMAN = float(os.getenv("TG_DEADMAN_SEC", "240"))      # Claude silent this long -> flat
RECONCILE_SEC = float(os.getenv("TG_RECONCILE_SEC", "60"))  # broker truth check; 0=off
SELL_RETRY = float(os.getenv("TG_SELL_RETRY_SEC", "90"))    # min gap between sell attempts
FLAT_DISCOUNT = 0.97                                     # marketable limit for flatten
HERE = os.path.dirname(os.path.abspath(__file__))
EXEC = os.path.join(HERE, "exec_trade.py")
ALIVE = os.path.join(state.BASE, "claude_alive")         # touched by the Claude loop
PY = os.path.join(os.path.dirname(HERE), "venv", "bin", "python")
if not os.path.exists(PY):
    PY = sys.executable


def notify(title: str, msg: str, urgent: bool = False):
    # Mac-only por orden de Yunior 2026-07-09 (ntfy llegaba tarde/acumulado al
    # telefono). urgent se conserva en la firma por si se reactiva el push.
    try:
        subprocess.Popen(["osascript", "-e",
                          f'display notification "{msg}" with title "{title}" sound name "Glass"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    state.append_signal({"kind": "watchdog", "title": title, "msg": msg})


def held_seconds(pos) -> float:
    try:
        return time.time() - datetime.fromisoformat(pos["opened"]).timestamp()
    except Exception:
        return 0.0


def sell(pos, reason: str, force: bool = False, limit: float = None) -> bool:
    """Place the sell via exec_trade. Cooldown so a resting/rejected order does
    not fire a new attempt + notification every second (the 2026-07-09 spam)."""
    now = time.time()
    if now - pos.get("last_sell_ts", 0) < SELL_RETRY:
        return False
    pos["last_sell_ts"] = now
    state.write_position(pos)
    cmd = [PY, EXEC, "sell", pos["sym"], str(pos["qty"]), "--entry", str(pos["entry"])]
    if limit:
        cmd += ["--limit", f"{limit:.4f}"]
    if force:
        cmd.append("--force-flat")
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    notify(f"VENDER {pos['sym']}", f"{reason} — {out.strip()[:120]}", urgent=True)
    print(f"[watchdog] SELL {pos['sym']}: {reason}\n{out}", flush=True)
    return True


def flatten(pos, reason: str, px: float) -> bool:
    """Sell IMMEDIATELY at a marketable limit (px*0.97, crosses the spread but
    stays inside IBKR's price band). Used by stop-loss, time-stop and dead-man —
    may realize a loss, per Yunior's 2026-07-09 order (always use stop loss)."""
    return sell(pos, reason, force=True, limit=round(px * FLAT_DISCOUNT, 4))


def reconcile(pos) -> bool:
    """Ask IBKR whether we still hold the shares. Returns True if the local
    position was cleared (sold outside the bot) so the caller stands down."""
    try:
        r = subprocess.run([PY, EXEC, "reconcile", pos["sym"]],
                           capture_output=True, text=True, timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        if "CLEARED" in out:
            notify(f"{pos['sym']} vendido fuera del bot",
                   "IBKR ya no tiene las acciones — dejo de vigilar esta posicion")
            print(f"[watchdog] reconcile: {out.strip()}", flush=True)
            return True
        if "ADJUSTED" in out:
            print(f"[watchdog] reconcile: {out.strip()}", flush=True)
    except Exception as e:
        print(f"[watchdog] reconcile err {str(e)[:80]}", flush=True)
    return False


def manage(pos):
    cfg = DEFAULT_CONFIG
    entry, qty = pos["entry"], pos["qty"]
    floor = floor_price(entry, qty, cfg)
    target = exit_limit_price(entry, qty, cfg)
    stop = entry * (1 - STOP_PCT / 100.0)
    peak = pos.get("peak", entry)
    reached_floor = pos.get("reached_floor", False)

    q = last_price(pos["sym"])
    if not q:
        return pos, False
    px = q["price"]
    if px > peak:
        peak = px
    if px >= floor:
        reached_floor = True

    pos.update(peak=peak, reached_floor=reached_floor, last=px)
    state.write_position(pos)

    # exit decisions, first match wins
    if px <= stop:
        return pos, flatten(pos, f"STOP-LOSS px {px:.4f} <= {stop:.4f} (-{STOP_PCT}%)", px)
    if px >= target:
        return pos, sell(pos, f"target hit px {px:.4f} >= {target:.4f}")
    if reached_floor and px >= floor:
        retrace = (peak - px) / peak * 100 if peak else 0
        if retrace >= TRAIL_PCT:
            return pos, sell(pos, f"trail lock px {px:.4f} (peak {peak:.4f}, -{retrace:.2f}%) >= floor {floor:.4f}")
    if held_seconds(pos) >= MAX_HOLD:
        return pos, flatten(pos, f"TIME-STOP {int(MAX_HOLD)}s cumplidos px {px:.4f} (entry {entry:.4f})", px)
    return pos, False


def main():
    print(f"[watchdog] up. poll={POLL}s trail={TRAIL_PCT}% stop={STOP_PCT}% "
          f"max_hold={int(MAX_HOLD)}s deadman={int(DEADMAN)}s reconcile={int(RECONCILE_SEC)}s "
          f"armed={state.is_armed()}", flush=True)
    start = time.time()
    last_reconcile = 0.0
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
            now = time.time()

            # 1) broker truth — detect manual/external sells, stop ghost-managing
            if RECONCILE_SEC > 0 and now - last_reconcile >= RECONCILE_SEC:
                last_reconcile = now
                if reconcile(pos):
                    continue
                pos = state.read_position()  # qty may have been adjusted
                if not pos:
                    continue

            # 2) dead-man — Claude Code silent while money at risk -> sell NOW.
            # opened_ts counts as a life signal: the buy itself came from a healthy
            # Claude cycle (fix 2026-07-10: stale alive during a session-limit fired
            # the deadman 4s after the RXT fill — real live race).
            alive = os.path.getmtime(ALIVE) if os.path.exists(ALIVE) else 0.0
            silent = now - max(alive, start, pos.get("opened_ts", 0) or 0)
            if DEADMAN > 0 and silent > DEADMAN:
                q = last_price(pos["sym"])
                px = q["price"] if q else pos.get("last", pos["entry"])
                if flatten(pos, f"DEADMAN: Claude sin responder {int(silent)}s — vendo ya", px):
                    print(f"[watchdog] DEADMAN fired for {pos['sym']}", flush=True)
                time.sleep(POLL)
                continue

            pos, closed = manage(pos)
            if closed and state.read_position() is None:
                print(f"[watchdog] {pos['sym']} closed, back to idle", flush=True)
        except Exception as e:
            print(f"[watchdog] err {str(e)[:120]}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
