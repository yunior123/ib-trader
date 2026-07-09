#!/usr/bin/env python3
"""Order executor for the top-gainer system — IBKR TFSA, US stocks, whole shares.

Hard constraints (live-verified, see memory/ibkr-account-facts):
  - TFSA U26942420 only. US products via API WORK; Canadian BLOCKED (Error 201);
    fractional BLOCKED (Error 10243) -> whole shares only.
  - Auto-FX CAD->USD free for micro buys.
  - Price-band: limits >~10% from market rejected (Warning 202) -> stay close.
  - Commission capped at 0.5% of trade value.

Safety interlocks:
  - LIVE orders fire ONLY if data/topgainer/armed exists AND env TOPGAINER_LIVE=1.
    Otherwise this runs DRY (prints the order it WOULD place). This lets the
    whole pipeline be tested end-to-end without touching the account; Yunior
    arms it with one command when he wants it hot.
  - SELL never below the breakeven+fee floor (never-loss rule) unless
    --force-flat is given (used by the watchdog ONLY at hard EOD as a last
    resort, and even then it prefers the floor).

Usage:
  exec_trade.py buy  SYM QTY [--limit PX]     # QTY whole shares
  exec_trade.py sell SYM QTY --entry PX [--limit PX] [--force-flat]
  exec_trade.py flat SYM                       # sell whatever we hold, at/above floor
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                   # topgainer/
import state  # noqa: E402
from price import last_price, usdcad  # noqa: E402

# reuse the validated engine helpers
from day_trading_bot import (IB, Stock, LimitOrder, floor_price,  # noqa: E402
                             exit_limit_price, order_commission, get_account_value,
                             DEFAULT_CONFIG)

IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7496"))     # live TWS
IB_ACCOUNT = os.getenv("IB_ACCOUNT", "U26942420")
CLIENT_ID = int(os.getenv("TOPGAINER_CLIENTID", "41"))

BAND = 0.08   # keep limit within 8% of market (under the ~10% reject band)
# balance guard: never spend more than available funds minus a fee/FX buffer, so
# the account can NEVER go negative (which would trigger high fees).
ALLOC = float(os.getenv("TOPGAINER_ALLOC", "1.0"))     # fraction of buffered budget to use
FEE_BUFFER_CAD = float(os.getenv("TOPGAINER_FEE_BUFFER_CAD", "1.50"))  # fixed reserve
FX_MARKUP = 1.02                                        # assume FX 2% worse than quoted


def _live_enabled() -> bool:
    return state.is_armed() and os.getenv("TOPGAINER_LIVE") == "1"


def _connect():
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID, timeout=15, account=IB_ACCOUNT)
    return ib


def _clamp_buy_limit(mkt: float, want: float) -> float:
    hi = mkt * (1 + BAND)
    return round(min(want, hi), 4)


def account_budget(ib=None):
    """Return the spendable budget in USD, computed from the LIVE TFSA available
    funds (CAD base) minus a fee/FX buffer, converted at a conservative FX. This
    is the hard ceiling: an order is never allowed to exceed it, so the account
    cannot go negative. Returns dict with cad/usd/fx/available so callers + Claude
    can see the numbers. If ib is None, connects read-only just to read balance."""
    own = False
    if ib is None:
        ib = IB()
        ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID + 30, timeout=15,
                   readonly=True, account=IB_ACCOUNT)
        own = True
    try:
        avail_cad = get_account_value(ib, "AvailableFunds", IB_ACCOUNT)
        if avail_cad <= 0:
            avail_cad = get_account_value(ib, "TotalCashValue", IB_ACCOUNT)
    finally:
        if own:
            ib.disconnect()
    fx = usdcad() * FX_MARKUP                       # conservative (fewer USD)
    buffer_cad = max(FEE_BUFFER_CAD, avail_cad * 0.10)
    budget_cad = max(0.0, (avail_cad - buffer_cad)) * ALLOC
    budget_usd = budget_cad / fx if fx else 0.0
    return {"available_cad": round(avail_cad, 2), "buffer_cad": round(buffer_cad, 2),
            "budget_cad": round(budget_cad, 2), "fx_usdcad": round(fx, 4),
            "budget_usd": round(budget_usd, 2)}


def affordable_qty(limit_px: float, budget_usd: float) -> int:
    """Max whole shares whose cost + commission stays within budget_usd."""
    if limit_px <= 0 or budget_usd <= 0:
        return 0
    q = int(budget_usd // limit_px)
    # back off until value + commission fits (commission is min($1, 0.5% value))
    while q > 0:
        val = q * limit_px
        if val + order_commission(val, DEFAULT_CONFIG) <= budget_usd:
            return q
        q -= 1
    return 0


def do_buy(sym: str, qty: int, limit: float = None):
    q = last_price(sym)
    if not q:
        print(f"buy {sym}: no price, abort", file=sys.stderr)
        return 2
    mkt = q["price"]
    lim = _clamp_buy_limit(mkt, limit if limit else mkt * 1.02)  # cross a hair to fill

    # ---- HARD BALANCE GUARD: never exceed available funds (no negative balance) ----
    ib = None
    if _live_enabled():
        ib = _connect()
        bud = account_budget(ib)
    else:
        try:
            bud = account_budget(None)   # read-only balance check even in DRY
        except Exception as e:
            print(f"[DRY] balance check skipped ({str(e)[:60]}); using $0 budget guard demo")
            bud = {"budget_usd": 0.0, "available_cad": 0.0, "fx_usdcad": usdcad() * FX_MARKUP}
    max_q = affordable_qty(lim, bud["budget_usd"])
    req_q = qty
    qty = min(qty, max_q)
    if qty < 1:
        print(f"REFUSE buy {sym}: budget ${bud['budget_usd']:.2f} USD "
              f"(avail {bud.get('available_cad')} CAD @ fx {bud['fx_usdcad']}) "
              f"buys 0 shares at ${lim} — no order (protects against negative balance).")
        if ib:
            ib.disconnect()
        return 0
    if qty < req_q:
        print(f"[guard] {sym}: requested {req_q} -> clamped to {qty} shares "
              f"(budget ${bud['budget_usd']:.2f} USD @ ${lim})")
    val = lim * qty

    if not _live_enabled():
        print(f"[DRY] BUY {qty} {sym} LMT {lim} (mkt {mkt}, ~${val:.2f}, "
              f"budget ${bud['budget_usd']:.2f} USD / {bud.get('available_cad')} CAD) "
              f"armed={state.is_armed()} LIVE={os.getenv('TOPGAINER_LIVE')}")
        return 0
    try:
        c = Stock(sym, "SMART", "USD")
        ib.qualifyContracts(c)
        trade = ib.placeOrder(c, LimitOrder("BUY", qty, lim, account=IB_ACCOUNT))
        ib.sleep(3)
        for _ in range(20):
            ib.waitOnUpdate(timeout=1)
            if trade.orderStatus.status in ("Filled", "Cancelled", "ApiCancelled"):
                break
        st = trade.orderStatus
        filled = st.filled or 0
        avg = st.avgFillPrice or lim
        state.log_decision({"action": "buy", "sym": sym, "qty": qty, "limit": lim,
                            "status": st.status, "filled": filled, "avg": avg})
        if filled > 0:
            pos = {"sym": sym, "qty": int(filled), "entry": float(avg),
                   "opened": state.now_iso(), "opened_ts": state.utc_ts(),
                   "peak": float(avg)}
            state.write_position(pos)
            print(f"FILLED BUY {filled} {sym} @ {avg}; position recorded")
        else:
            print(f"BUY {sym} status={st.status} filled=0")
        return 0
    finally:
        ib.disconnect()


def do_sell(sym: str, qty: int, entry: float, limit: float = None, force_flat: bool = False):
    q = last_price(sym)
    mkt = q["price"] if q else (limit or entry)
    cfg = DEFAULT_CONFIG
    floor = floor_price(entry, qty, cfg)          # never sell below this...
    want = exit_limit_price(entry, qty, cfg)       # ...target profit limit
    lim = limit if limit else want
    if not force_flat:
        lim = max(lim, floor)                       # never-loss guarantee
    # keep the sell limit reachable (not absurdly above market)
    lim = round(min(lim, mkt * (1 + BAND)) if mkt >= floor else lim, 4)
    lim = max(lim, floor) if not force_flat else lim
    if not _live_enabled():
        print(f"[DRY] SELL {qty} {sym} LMT {lim} (mkt {mkt}, floor {floor:.4f}, "
              f"force_flat={force_flat}) armed={state.is_armed()} LIVE={os.getenv('TOPGAINER_LIVE')}")
        return 0
    ib = _connect()
    try:
        c = Stock(sym, "SMART", "USD")
        ib.qualifyContracts(c)
        trade = ib.placeOrder(c, LimitOrder("SELL", qty, lim, tif="GTC", account=IB_ACCOUNT))
        ib.sleep(3)
        for _ in range(20):
            ib.waitOnUpdate(timeout=1)
            if trade.orderStatus.status in ("Filled", "Cancelled", "ApiCancelled"):
                break
        st = trade.orderStatus
        state.log_decision({"action": "sell", "sym": sym, "qty": qty, "limit": lim,
                            "floor": floor, "status": st.status, "filled": st.filled or 0,
                            "avg": st.avgFillPrice or 0, "force_flat": force_flat})
        if (st.filled or 0) >= qty:
            state.clear_position()
            print(f"FILLED SELL {st.filled} {sym} @ {st.avgFillPrice}; position closed")
        else:
            print(f"SELL {sym} resting/limit status={st.status} filled={st.filled or 0} @ {lim}")
        return 0
    finally:
        ib.disconnect()


def do_reconcile(sym: str):
    """Compare position.json against the LIVE IBKR position (read-only connect).
    If IBKR holds 0 shares the position was sold OUTSIDE the bot (manual TWS sell,
    broker-side fill of a resting GTC, liquidation) -> clear the local position so
    the watchdog stops managing a ghost and spamming sell orders/notifications.
    If IBKR holds fewer shares than recorded (partial manual sell) -> adjust qty."""
    pos = state.read_position()
    if not pos or pos["sym"] != sym:
        print(f"OK no local {sym} position")
        return 0
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID + 32, timeout=15,
               readonly=True, account=IB_ACCOUNT)
    try:
        qty = 0
        for p in ib.positions(IB_ACCOUNT):
            if p.contract.symbol == sym:
                qty += int(p.position)
    finally:
        ib.disconnect()
    if qty <= 0:
        state.log_decision({"action": "reconcile_clear_position", "sym": sym,
                            "reason": "IBKR holds 0 — sold outside the bot",
                            "stale_position": pos})
        state.clear_position()
        print(f"CLEARED {sym}: IBKR holds 0 (sold outside the bot); local position removed")
    elif qty < pos["qty"]:
        old = pos["qty"]
        pos["qty"] = qty
        state.write_position(pos)
        state.log_decision({"action": "reconcile_adjust_qty", "sym": sym,
                            "from": old, "to": qty})
        print(f"ADJUSTED {sym}: qty {old} -> {qty} (partial external sell)")
    else:
        print(f"OK {sym}: IBKR qty {qty} matches local {pos['qty']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buy"); b.add_argument("sym"); b.add_argument("qty", type=int)
    b.add_argument("--limit", type=float)
    s = sub.add_parser("sell"); s.add_argument("sym"); s.add_argument("qty", type=int)
    s.add_argument("--entry", type=float, required=True); s.add_argument("--limit", type=float)
    s.add_argument("--force-flat", action="store_true")
    f = sub.add_parser("flat"); f.add_argument("sym")
    sub.add_parser("balance")
    r = sub.add_parser("reconcile"); r.add_argument("sym")
    a = ap.parse_args()
    if a.cmd == "balance":
        import json
        bud = account_budget(None)   # LIVE read from IBKR, never hardcoded
        print(json.dumps(bud, indent=2))
        print(f"\nSpendable now: ~${bud['budget_usd']:.2f} USD "
              f"(= {bud['available_cad']} CAD available - {bud['buffer_cad']} CAD buffer, "
              f"@ fx {bud['fx_usdcad']}). Orders are hard-capped to this.")
        return 0
    if a.cmd == "reconcile":
        return do_reconcile(a.sym)
    if a.cmd == "buy":
        return do_buy(a.sym, a.qty, a.limit)
    if a.cmd == "sell":
        return do_sell(a.sym, a.qty, a.entry, a.limit, a.force_flat)
    if a.cmd == "flat":
        pos = state.read_position()
        if not pos or pos["sym"] != a.sym:
            print(f"no open {a.sym} position"); return 0
        return do_sell(pos["sym"], pos["qty"], pos["entry"])


if __name__ == "__main__":
    sys.exit(main())
