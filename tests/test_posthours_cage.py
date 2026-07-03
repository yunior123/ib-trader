"""posthours_cage.py — next_friday_exp() logic + analyze() graceful degradation."""
import time

import pandas as pd
import pytest


class FakeTicker:
    def __init__(self, options=None, hist=None):
        self.options = options if options is not None else []
        self._hist = hist

    def history(self, *a, **k):
        if self._hist is None:
            raise RuntimeError("no data")
        return self._hist


def _future_friday():
    # walk forward from today to the next Friday (tm_wday == 4)
    t = time.time()
    for i in range(1, 15):
        d = time.localtime(t + i * 86400)
        if d.tm_wday == 4:
            return time.strftime("%Y-%m-%d", d)
    raise AssertionError("no friday found")


def test_next_friday_exp_picks_future_friday(cage):
    fri = _future_friday()
    # a past date, a future non-friday, and the target future friday
    past = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    nonfri = time.strftime("%Y-%m-%d", time.localtime(time.time() + 1 * 86400))
    t = FakeTicker(options=sorted({past, nonfri, fri}))
    assert cage.next_friday_exp(t) == fri


def test_next_friday_exp_empty_options_none(cage):
    assert cage.next_friday_exp(FakeTicker(options=[])) is None


def test_next_friday_exp_fallback_last_when_no_friday(cage):
    # No future Friday present -> fall back to the last listed expiry.
    past = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    t = FakeTicker(options=[past])
    assert cage.next_friday_exp(t) == past


def test_analyze_ticker_error_setup_false(cage, monkeypatch):
    # yfinance blowing up must yield setup:False, not an exception.
    def _boom(sym):
        raise RuntimeError("network down")

    monkeypatch.setattr(cage.yf, "Ticker", _boom)
    r = cage.analyze("NVDA")
    assert r["setup"] is False
    assert r["sym"] == "NVDA"
    assert r["note"].startswith("error")


def test_analyze_no_rth_data_setup_false(cage, monkeypatch):
    # Empty history (no RTH bars) -> graceful setup:False with the RTH note.
    empty = pd.DataFrame(
        {"High": [], "Low": [], "Close": []},
        index=pd.DatetimeIndex([]),
    )
    monkeypatch.setattr(cage.yf, "Ticker", lambda sym: FakeTicker(hist=empty))
    r = cage.analyze("QQQ")
    assert r["setup"] is False
    assert "RTH" in r["note"]
