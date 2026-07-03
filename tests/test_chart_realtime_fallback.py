import importlib.util
import os
import time

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def cb():
    spec = importlib.util.spec_from_file_location(
        "cb_realtime_fallback", os.path.join(REPO, "scripts", "chart_bridge.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(cb):
    st = cb.State("qqq")
    st.tf = "1m"
    st.bars = [[1_800_000_000, 100.0, 101.0, 99.0, 100.5, 1000.0]]
    return st


def test_fresh_ws_tick_updates_current_candle(cb, monkeypatch):
    st = _state(cb)
    epoch = 1_800_000_030.25
    monkeypatch.setattr(cb.rt_last, "fresh",
                        lambda sym, max_age_s: (102.0, epoch, "finnhub", 0.1))
    assert cb.apply_realtime_fallback_tick(st) == "finnhub"
    assert st.bars[-1][2:5] == [102.0, 99.0, 102.0]
    assert st._rt_tick_epoch == epoch and st._rt_source == "finnhub"


def test_tick_opens_new_bucket_without_fabricating_volume(cb, monkeypatch):
    st = _state(cb)
    epoch = 1_800_000_061.0
    monkeypatch.setattr(cb.rt_last, "fresh",
                        lambda sym, max_age_s: (103.0, epoch, "finnhub", 0.2))
    assert cb.apply_realtime_fallback_tick(st) == "finnhub"
    assert st.bars[-1] == [1_800_000_060, 103.0, 103.0, 103.0, 103.0, 0.0]


def test_old_duplicate_or_unknown_source_never_moves_chart(cb, monkeypatch):
    st = _state(cb)
    original = [list(x) for x in st.bars]
    monkeypatch.setattr(cb.rt_last, "fresh",
                        lambda sym, max_age_s: (999.0, 1_800_000_030, "delayed_rest", 0.1))
    assert cb.apply_realtime_fallback_tick(st) is None
    assert st.bars == original

    st._rt_tick_epoch = 1_800_000_040
    monkeypatch.setattr(cb.rt_last, "fresh",
                        lambda sym, max_age_s: (999.0, 1_800_000_039, "finnhub", 0.1))
    assert cb.apply_realtime_fallback_tick(st) is None
    assert st.bars == original


def test_rt_last_freshness_gate_is_requested(cb, monkeypatch):
    st = _state(cb)
    seen = {}

    def no_tick(sym, max_age_s):
        seen.update(sym=sym, max_age_s=max_age_s)
        return None

    monkeypatch.setattr(cb.rt_last, "fresh", no_tick)
    assert cb.apply_realtime_fallback_tick(st, max_age_s=3.0) is None
    assert seen == {"sym": "qqq", "max_age_s": 3.0}


def test_file_backfill_has_slower_independent_throttle(cb):
    assert cb.BAR_FALLBACK_POLL_S > 0.5
    assert cb.BAR_FALLBACK_POLL_S < cb.STALE_SUB_S
