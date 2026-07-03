"""force_meter.py — rsi() edges, measure() degenerate-input guards, load_bars miss."""
import numpy as np
import pytest

VALID_PHASES = {"IMPULSO", "MADURO", "AGOTAMIENTO", "GIRO", "SIN FUERZA", "s/d"}


def _bars(closes, vols=None):
    """Build an (n,6) bar array [epoch,O,H,L,C,V] from a close series."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if vols is None:
        vols = np.full(n, 1000.0)
    epoch = np.arange(n, dtype=float) * 60
    o = closes.copy()
    h = closes + 0.05
    l = closes - 0.05
    return np.column_stack([epoch, o, h, l, closes, np.asarray(vols, float)])


# ---------- rsi() ----------
def test_rsi_short_series_returns_50(force):
    assert force.rsi(np.arange(10, dtype=float)) == 50.0


def test_rsi_all_up_no_div_zero(force):
    # ad == 0 branch must return 100, not raise ZeroDivisionError.
    closes = np.arange(30, dtype=float) + 100.0
    assert force.rsi(closes) == 100.0


def test_rsi_flat_prices_no_div_zero(force):
    # No gains, no losses -> au==0, ad==0 -> hits the ad==0 guard -> 100.
    closes = np.full(30, 50.0)
    r = force.rsi(closes)
    assert r == 100.0  # guard returns 100 when ad==0 (documented behaviour)


def test_rsi_mixed_in_range(force):
    rng = np.random.default_rng(0)
    closes = 100 + np.cumsum(rng.standard_normal(60))
    r = force.rsi(closes)
    assert 0.0 <= r <= 100.0


# ---------- measure() CRITICAL ZONE: degenerate bars ----------
def test_measure_flat_bars_no_div_zero(force, monkeypatch):
    # Zero-volatility bars: atr computes to 0 -> guard must kick in, no crash.
    bars = _bars(np.full(30, 100.0))
    monkeypatch.setattr(force, "load_bars", lambda s, n=40: bars)
    m = force.measure("FLAT")
    assert m["phase"] in VALID_PHASES
    assert np.isfinite(m["force"])
    assert abs(m["force"]) <= 100


def test_measure_insufficient_bars_graceful(force, monkeypatch):
    monkeypatch.setattr(force, "load_bars", lambda s, n=40: None)
    m = force.measure("NODATA")
    assert m["phase"] == "s/d"
    assert m["force"] == 0


def test_measure_too_few_bars_graceful(force, monkeypatch):
    monkeypatch.setattr(force, "load_bars", lambda s, n=40: _bars(np.arange(5.0)))
    m = force.measure("SHORT")
    assert m["phase"] == "s/d"


def test_measure_strong_uptrend_phase_valid(force, monkeypatch):
    closes = 100 + np.cumsum(np.full(40, 0.5))  # steady climb
    monkeypatch.setattr(force, "load_bars", lambda s, n=40: _bars(closes))
    m = force.measure("UP")
    assert m["phase"] in VALID_PHASES
    assert m["dir"] == "ARRIBA"
    assert np.isfinite(m["accel"])
    assert -100 <= m["force"] <= 100


def test_measure_zero_volume_no_crash(force, monkeypatch):
    # Volume all zero -> polyfit normalisation divides by mean(vv) with `or 1` guard.
    closes = 100 + np.cumsum(np.full(30, 0.2))
    bars = _bars(closes, vols=np.zeros(30))
    monkeypatch.setattr(force, "load_bars", lambda s, n=40: bars)
    m = force.measure("ZV")
    assert m["phase"] in VALID_PHASES
    assert np.isfinite(m["vol_trend"])


def test_measure_output_keys_present(force, monkeypatch):
    closes = 100 + np.cumsum(np.full(40, -0.3))  # downtrend
    monkeypatch.setattr(force, "load_bars", lambda s, n=40: _bars(closes))
    m = force.measure("DN")
    for k in ("sym", "force", "phase", "action", "rsi", "exhaustion", "leg_bars"):
        assert k in m
    assert m["action"]  # non-empty action string for every phase


# ---------- load_bars() missing file ----------
def test_load_bars_missing_file_returns_none(force, monkeypatch):
    import yfinance
    # No local bars file for this fake symbol; force the yfinance fallback to fail
    # so we stay offline and confirm the graceful None return.
    def _boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(yfinance, "Ticker", _boom)
    assert force.load_bars("ZZZZNOSUCH") is None
