"""calibration_ledger.py — wilson() edges + calibrate()/grade() guards."""
import json
import math

import pytest


# ---------- wilson() ----------
def test_wilson_n_zero_no_division(calib):
    # CRITICAL: empty bucket must not divide by zero.
    assert calib.wilson(0, 0) == (0.0, 0.0, 0.0)


def test_wilson_all_wins_rate_one(calib):
    p, lo, hi = calib.wilson(10, 10)
    assert p == 1.0
    assert 0.0 <= lo <= 1.0
    assert hi <= 1.0 + 1e-9
    assert lo < 1.0  # Wilson lower bound never overconfident at small n


def test_wilson_zero_wins_rate_zero(calib):
    p, lo, hi = calib.wilson(0, 10)
    assert p == 0.0
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert hi > 0.0  # upper bound accounts for uncertainty


def test_wilson_typical_25_of_42(calib):
    p, lo, hi = calib.wilson(25, 42)
    assert p == pytest.approx(25 / 42, abs=1e-9)
    assert 0.0 < lo < p < hi < 1.0
    # lower bound must sit meaningfully below the point estimate
    assert p - lo > 0.05


def test_wilson_lower_below_upper_always(calib):
    for w, n in [(1, 2), (3, 100), (99, 100), (50, 50)]:
        p, lo, hi = calib.wilson(w, n)
        assert lo <= p <= hi
        assert 0.0 <= lo and hi <= 1.0 + 1e-9


# ---------- calibrate() / grade() guards ----------
def test_calibrate_empty_log_returns_dict(calib, tmp_path, monkeypatch):
    # CRITICAL: no crash when the ledger file does not exist.
    monkeypatch.setattr(calib, "LOG", str(tmp_path / "nope.jsonl"))
    monkeypatch.setattr(calib, "OUT", str(tmp_path / "out.json"))
    assert calibrate_safe(calib) == {}


def calibrate_safe(calib):
    return calib.calibrate()


def test_grade_missing_log_returns_zero_no_network(calib, tmp_path, monkeypatch):
    # If the log is absent grade() must short-circuit to 0 without any yfinance call.
    monkeypatch.setattr(calib, "LOG", str(tmp_path / "absent.jsonl"))

    def _boom(*a, **k):
        raise AssertionError("grade() hit the network on an empty log")

    monkeypatch.setattr(calib.yf, "Ticker", _boom)
    assert calib.grade() == 0


def test_calibrate_excludes_no_entry_rows(calib, tmp_path, monkeypatch):
    # no_entry rows must NOT count toward win-rate (they never triggered).
    log = tmp_path / "calib_log.jsonl"
    out = tmp_path / "calibration.json"
    rows = [
        dict(date="2026-07-01", sym="NVDA", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result="win"),
        dict(date="2026-07-01", sym="MU", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result="loss"),
        dict(date="2026-07-01", sym="AMD", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result="no_entry"),
        dict(date="2026-07-01", sym="SMH", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result=None),
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(calib, "LOG", str(log))
    monkeypatch.setattr(calib, "OUT", str(out))

    res = calib.calibrate()
    k = "reclaim_wall|POSITIVO"
    assert k in res
    # only the win + loss count; no_entry and ungraded(None) excluded.
    assert res[k]["n"] == 2
    assert res[k]["wins"] == 1
    assert 0.0 <= res[k]["rate"] <= 1.0
    assert res[k]["trust"] is False  # n < MIN_N
    # file was written and is valid json
    assert json.load(open(out)) == res


def test_calibrate_bad_date_does_not_crash(calib, tmp_path, monkeypatch):
    # A malformed date must fall back (age=0) instead of raising.
    log = tmp_path / "calib_log.jsonl"
    log.write_text(json.dumps(dict(
        date="not-a-date", sym="QQQ", setup_type="breakdown",
        regime="NEGATIVO", direction="bear", result="win")) + "\n")
    monkeypatch.setattr(calib, "LOG", str(log))
    monkeypatch.setattr(calib, "OUT", str(tmp_path / "o.json"))
    res = calib.calibrate()
    assert res["breakdown|NEGATIVO"]["n"] == 1
