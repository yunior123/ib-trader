#!/usr/bin/env python3
"""Critical + edge-case tests for the top-gainer system.

Focus: the money-safety invariants (never sell at a loss, interlocks block live
orders, watchdog exit logic) and state IO robustness. Run:
    venv/bin/python -m pytest topgainer/test_topgainer.py -q
or standalone:
    venv/bin/python topgainer/test_topgainer.py
"""
import importlib
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import state  # noqa: E402
from day_trading_bot import floor_price, exit_limit_price, DEFAULT_CONFIG  # noqa: E402


# ---------- never-loss floor invariants ----------
def test_floor_above_entry_and_breakeven():
    cfg = DEFAULT_CONFIG
    for entry, qty in [(0.20, 5), (1.50, 100), (3.33, 30), (0.11, 1)]:
        f = floor_price(entry, qty, cfg)
        assert f > entry, f"floor {f} must be above entry {entry}"
        # floor must at least cover entry + both commissions (breakeven)
        comm = min(cfg["commission_per_order"], entry * qty * 0.5 / 100)
        breakeven = entry + (2 * comm) / qty
        assert f >= breakeven * 0.999, f"floor {f} below breakeven {breakeven}"


def test_exit_limit_never_below_floor():
    cfg = DEFAULT_CONFIG
    for entry, qty in [(0.20, 5), (1.00, 50), (5.0, 20)]:
        assert exit_limit_price(entry, qty, cfg) >= floor_price(entry, qty, cfg) * 0.999


# ---------- interlock: live orders blocked unless armed AND env ----------
def test_live_disabled_by_default(monkeypatch):
    import exec_trade
    monkeypatch.delenv("TOPGAINER_LIVE", raising=False)
    monkeypatch.setattr(exec_trade.state, "is_armed", lambda: False)
    assert exec_trade._live_enabled() is False
    # armed but no env -> still blocked
    monkeypatch.setattr(exec_trade.state, "is_armed", lambda: True)
    assert exec_trade._live_enabled() is False
    # env but not armed -> still blocked
    monkeypatch.setenv("TOPGAINER_LIVE", "1")
    monkeypatch.setattr(exec_trade.state, "is_armed", lambda: False)
    assert exec_trade._live_enabled() is False
    # both -> enabled
    monkeypatch.setattr(exec_trade.state, "is_armed", lambda: True)
    assert exec_trade._live_enabled() is True


def test_dry_buy_places_no_order(monkeypatch, capsys):
    import exec_trade
    monkeypatch.setattr(exec_trade, "last_price", lambda s: {"price": 0.20, "prev_close": 0.18})
    monkeypatch.setattr(exec_trade, "_live_enabled", lambda: False)
    # if it tried to connect, this would blow up; ensure it never does
    monkeypatch.setattr(exec_trade, "_connect", lambda: (_ for _ in ()).throw(AssertionError("connected in DRY!")))
    rc = exec_trade.do_buy("GNS", 5)
    assert rc == 0
    assert "[DRY] BUY" in capsys.readouterr().out


def test_buy_limit_clamped_to_band():
    import exec_trade
    # never chase more than BAND above market
    mkt = 1.00
    assert exec_trade._clamp_buy_limit(mkt, 5.0) <= mkt * (1 + exec_trade.BAND) + 1e-9


# ---------- watchdog exit logic (deterministic, no LLM, no orders) ----------
def _wd_with_price(monkeypatch, price):
    import watchdog
    importlib.reload(watchdog)
    monkeypatch.setattr(watchdog, "last_price", lambda s: {"price": price, "prev_close": price})
    sold = {}
    monkeypatch.setattr(watchdog, "sell", lambda pos, reason: sold.update(pos=pos, reason=reason))
    monkeypatch.setattr(watchdog.state, "write_position", lambda p: None)
    return watchdog, sold


def _pos(entry=0.20, qty=5, **kw):
    p = {"sym": "GNS", "qty": qty, "entry": entry, "peak": entry}
    p.update(kw)
    return p


def test_watchdog_sells_at_target(monkeypatch):
    wd, sold = _wd_with_price(monkeypatch, 0.30)   # well above target
    _, closed = wd.manage(_pos())
    assert closed and "target" in sold["reason"]


def test_watchdog_holds_below_floor_never_loss(monkeypatch):
    wd, sold = _wd_with_price(monkeypatch, 0.15)   # under floor -> BAG, must NOT sell
    pos, closed = wd.manage(_pos())
    assert not closed and not sold
    assert pos["in_bag"] is True


def test_watchdog_trailing_locks_gain_above_floor(monkeypatch):
    # price rose to a peak above floor, then retraced past TRAIL_PCT but still >= floor
    wd, sold = _wd_with_price(monkeypatch, 0.205)
    floor = floor_price(0.20, 5, DEFAULT_CONFIG)
    peak = 0.205 * (1 + (wd.TRAIL_PCT + 0.5) / 100)   # peak high enough that 0.205 is a >TRAIL retrace
    pos = _pos(peak=peak, reached_floor=True)
    assert 0.205 >= floor
    _, closed = wd.manage(pos)
    assert closed and "trail" in sold["reason"]


def test_watchdog_no_sell_when_between_floor_and_target_no_retrace(monkeypatch):
    wd, sold = _wd_with_price(monkeypatch, 0.205)   # above floor, below target, at peak
    pos = _pos(peak=0.205, reached_floor=True)
    _, closed = wd.manage(pos)
    assert not closed and not sold


# ---------- state IO robustness ----------
def test_position_roundtrip_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "POSITION", str(tmp_path / "position.json"))
    assert state.read_position() is None
    state.write_position({"sym": "X", "qty": 1, "entry": 1.0})
    assert state.read_position()["sym"] == "X"
    state.clear_position()
    assert state.read_position() is None


def test_atomic_write_no_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "POSITION", str(tmp_path / "p.json"))
    state.write_position({"sym": "Y", "qty": 2, "entry": 2.0})
    # no leftover temp files
    assert not any(f.name.startswith("p.json.tmp") for f in tmp_path.iterdir())


def test_signals_unconsumed_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "SIGNALS", str(tmp_path / "sig.jsonl"))
    state.append_signal({"kind": "a"})
    state.append_signal({"kind": "b", "consumed": True})
    got = state.unconsumed_signals()
    assert len(got) == 1 and got[0]["kind"] == "a"


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
