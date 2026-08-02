"""Tests for scripts/reversal_router.py — Bento/Trinity/Router shadow analyzer.

Synthetic 1m bars drive three regimes:
  - clean multi-session uptrend  -> CONTINUATION_ACTIVE_DO_NOT_FADE
  - gap-up spike then reversal    -> REVERSAL_ARMED_WAIT / REVERSAL_CONFIRMED
  - too few bars                  -> INSUFFICIENT_DATA (fail-loud, never fabricated NEUTRAL/0.5)
Bars are written to a tmp data dir (rr.DATA monkeypatched) so the real data/ is untouched.
"""
import importlib
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import reversal_router as rr  # noqa: E402

ET = ZoneInfo("America/New_York")


def _epoch(d, minute):
    return int((datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET) + timedelta(minutes=minute)).timestamp())


def _sessions(n, start=datetime(2026, 6, 1)):
    out = []
    d = start.date()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d = d + timedelta(days=1)
    return out


def _write_bars(data_dir, sym, sess_dates, close_paths, wick):
    lines = []
    prev = None
    for d, closes in zip(sess_dates, close_paths):
        for m, c in enumerate(closes):
            o = prev if prev is not None else c
            hi = max(o, c) + abs(c) * wick
            lo = min(o, c) - abs(c) * wick
            lines.append(f"{_epoch(d, m)} {o:.4f} {hi:.4f} {lo:.4f} {c:.4f} 1000")
            prev = c
    path = os.path.join(data_dir, f"bars_{sym.lower()}_ibkr.txt")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "DATA", str(tmp_path))
    return str(tmp_path)


def _trend_paths():
    ds = _sessions(20)
    paths = []
    price = 100.0
    rng = np.random.default_rng(3)
    for _ in ds:
        closes = []
        for _m in range(390):
            price *= (1 + 0.0004 + rng.normal(0, 0.00012))
            closes.append(price)
        paths.append(closes)
    return ds, paths, 0.004


def _reversal_paths():
    ds = _sessions(20)
    paths = []
    price = 100.0
    rng = np.random.default_rng(7)
    for _ in ds[:-1]:
        closes = []
        for _m in range(390):
            price += rng.normal(0, 0.02)
            price = max(97.0, min(103.0, price))
            closes.append(price)
        paths.append(closes)
    p = price * 1.04
    last = []
    for _m in range(15):          # gap-up spike to a Bollinger/RSI extreme
        p *= (1 + 0.0016)
        last.append(p)
    for _m in range(18):          # sharp reversal that breaks the base structure
        p *= (1 - 0.0016 * 1.3)
        last.append(p)
    paths.append(last)
    return ds, paths, 0.001


def test_trend_is_continuation(data_dir):
    ds, paths, wick = _trend_paths()
    _write_bars(data_dir, "TREND", ds, paths, wick)
    res = rr._compute("TREND")
    assert res["state"] == "CONTINUATION_ACTIVE_DO_NOT_FADE", res
    assert res["scores"]["trinity_active"] is True
    assert res["scores"]["trinity_dir"] == 1
    assert res["n_bars"] >= rr.REQUIRED_5M_BARS


def test_reversal_after_gap_is_armed_or_confirmed(data_dir):
    ds, paths, wick = _reversal_paths()
    _write_bars(data_dir, "REV", ds, paths, wick)
    res = rr._compute("REV")
    assert res["state"] in ("REVERSAL_ARMED_WAIT", "REVERSAL_CONFIRMED"), res
    assert res["scores"]["bento_dir"] == -1  # overbought -> fade down
    assert 0 <= res["scores"]["reversal_score"] <= 6


def test_too_few_bars_is_insufficient(data_dir):
    ds = _sessions(1)
    paths = [[100.0 + 0.01 * m for m in range(200)]]  # 200 1m bars -> 40 5m bars < 260
    _write_bars(data_dir, "SHORT", ds, paths, 0.001)
    res = rr._compute("SHORT")
    assert res["state"] == "INSUFFICIENT_DATA", res
    assert res["scores"] == {}
    # fail-loud: never a fabricated NEUTRAL / 0.5
    assert "bento_score" not in res["scores"]


def test_missing_file_is_insufficient(data_dir):
    res = rr._compute("NOPE")
    assert res["state"] == "INSUFFICIENT_DATA"
    assert res["n_bars"] == 0


def test_json_is_serializable_and_atomic(data_dir):
    ds, paths, wick = _trend_paths()
    _write_bars(data_dir, "TREND", ds, paths, wick)
    res = rr._compute("TREND")
    path = rr._write("TREND", res)
    assert os.path.exists(path)
    with open(path) as f:
        loaded = json.load(f)  # would raise if numpy types leaked in
    assert loaded["shadow"] is True
    assert loaded["state"] == res["state"]
    assert not os.path.exists(path + ".tmp")


def test_insufficient_is_not_fabricated_number(data_dir):
    """Doctrine: short data must not yield a plausible 0.5/NEUTRAL score."""
    ds = _sessions(2)
    paths = [[100.0 + 0.01 * m for m in range(300)] for _ in ds]  # 120 5m bars < 260
    _write_bars(data_dir, "TWO", ds, paths, 0.001)
    res = rr._compute("TWO")
    assert res["state"] == "INSUFFICIENT_DATA"
    assert res["scores"].get("bento_score") is None
