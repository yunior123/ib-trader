"""daily_fleet_plans.py — bs_greeks() (money path), measured_prob, load_* guards."""
import datetime
import math
import sys

import pytest


# ---------- bs_greeks() CRITICAL: degenerate inputs never crash ----------
def test_bs_greeks_expired_returns_empty(fleet):
    assert fleet.bs_greeks(100, 100, 0, 0.3, "C") == {}
    assert fleet.bs_greeks(100, 100, -0.1, 0.3, "C") == {}


def test_bs_greeks_zero_iv_returns_empty(fleet):
    assert fleet.bs_greeks(100, 100, 0.1, 0.0, "C") == {}
    assert fleet.bs_greeks(100, 100, 0.1, -0.5, "C") == {}


def test_bs_greeks_zero_spot_returns_empty(fleet):
    assert fleet.bs_greeks(0, 100, 0.1, 0.3, "C") == {}


def test_bs_greeks_atm_call_delta_near_half(fleet):
    g = fleet.bs_greeks(100, 100, 30 / 365, 0.30, "C")
    assert g
    assert 0.30 <= g["delta"] <= 0.70   # ATM call ~0.5
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_bs_greeks_atm_put_delta_near_minus_half(fleet):
    g = fleet.bs_greeks(100, 100, 30 / 365, 0.30, "P")
    assert -0.70 <= g["delta"] <= -0.30  # ATM put ~-0.5
    assert g["gamma"] > 0


def test_bs_greeks_deep_itm_call_delta_high(fleet):
    g = fleet.bs_greeks(200, 100, 30 / 365, 0.30, "C")
    assert 0.90 <= g["delta"] <= 1.0


def test_bs_greeks_deep_otm_call_delta_low(fleet):
    g = fleet.bs_greeks(50, 100, 30 / 365, 0.30, "C")
    assert 0.0 <= g["delta"] <= 0.10


def test_bs_greeks_call_delta_bounds(fleet):
    for S in (60, 90, 100, 110, 150):
        g = fleet.bs_greeks(S, 100, 20 / 365, 0.4, "C")
        assert 0.0 <= g["delta"] <= 1.0
        assert g["gamma"] > 0


def test_bs_greeks_put_delta_bounds(fleet):
    for S in (60, 90, 100, 110, 150):
        g = fleet.bs_greeks(S, 100, 20 / 365, 0.4, "P")
        assert -1.0 <= g["delta"] <= 0.0


def test_bs_greeks_put_call_parity_delta(fleet):
    # delta_call - delta_put == 1 (exact under BS with same inputs)
    c = fleet.bs_greeks(105, 100, 40 / 365, 0.35, "C")
    p = fleet.bs_greeks(105, 100, 40 / 365, 0.35, "P")
    assert c["delta"] - p["delta"] == pytest.approx(1.0, abs=1e-9)
    # gamma and vega are identical for call/put
    assert c["gamma"] == pytest.approx(p["gamma"], rel=1e-9)
    assert c["vega"] == pytest.approx(p["vega"], rel=1e-9)


def test_bs_greeks_all_finite(fleet):
    g = fleet.bs_greeks(123.45, 120, 15 / 365, 0.5, "C")
    assert all(math.isfinite(v) for v in g.values())


# ---------- measured_prob() ----------
def test_measured_prob_empty_calib_returns_heuristic(fleet, monkeypatch):
    # CRITICAL: with no calibration file the generator must fall back to heuristic.
    monkeypatch.setattr(fleet, "CALIB", {})
    prob, note = fleet.measured_prob("reclaim_wall", "POSITIVO", 55)
    assert prob == 55
    assert "heuristica" in note


def test_measured_prob_untrusted_bucket_keeps_heuristic(fleet, monkeypatch):
    monkeypatch.setattr(fleet, "CALIB", {
        "reclaim_wall|POSITIVO": dict(trust=False, n=5, ci_low=0.4, rate=0.5)
    })
    prob, note = fleet.measured_prob("reclaim_wall", "POSITIVO", 60)
    assert prob == 60  # heuristic retained
    assert "provisional" in note


def test_measured_prob_trusted_bucket_uses_measured(fleet, monkeypatch):
    monkeypatch.setattr(fleet, "CALIB", {
        "reclaim_wall|POSITIVO": dict(trust=True, n=40, ci_low=0.62, rate=0.7)
    })
    prob, note = fleet.measured_prob("reclaim_wall", "POSITIVO", 55)
    assert prob == 62  # ci_low * 100, rounded — the honest lower bound
    assert "MEDIDA" in note


# ---------- load_* graceful degradation (keeps the 4am run alive) ----------
def test_loaders_missing_files_return_empty(fleet, tmp_path, monkeypatch):
    # Run from a dir with no data/ folder: every loader must return {} not crash.
    monkeypatch.chdir(tmp_path)
    assert fleet.load_calibration() == {}
    assert fleet.load_breadth() == {}
    assert fleet.load_patterns() == {}


def test_load_calibration_reads_valid_json(fleet, tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "calibration.json").write_text('{"k|R": {"trust": true}}')
    monkeypatch.chdir(tmp_path)
    assert fleet.load_calibration() == {"k|R": {"trust": True}}


def test_load_patterns_corrupt_json_returns_empty(fleet, tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "patterns.json").write_text("{ this is not json ")
    monkeypatch.chdir(tmp_path)
    assert fleet.load_patterns() == {}  # broad except -> graceful {}


# ---------- earnings veto (regla 4: jamas aguantar prima comprada a traves del print) ----------
def test_earnings_veto_lines_no_earn_returns_empty(fleet):
    assert fleet.earnings_veto_lines("NVDA", None) == []


def test_earnings_veto_lines_amc_vetoes_on_report_day(fleet):
    earn = ("2026-07-28", "AMC", datetime.datetime(2026, 7, 28, 16, 30))
    lines = fleet.earnings_veto_lines("STX", earn, today="2026-07-28")
    assert any("VETO HOY" in ln for ln in lines)


def test_earnings_veto_lines_amc_pending_before_report_day(fleet):
    earn = ("2026-07-28", "AMC", datetime.datetime(2026, 7, 28, 16, 30))
    lines = fleet.earnings_veto_lines("STX", earn, today="2026-07-25")
    assert not any("VETO HOY" in ln for ln in lines)
    assert any("entra en vigor al cierre de 2026-07-28" in ln for ln in lines)


def test_earnings_veto_lines_bmo_vetoes_day_before(fleet):
    # BMO: el print sale antes de abrir -> el veto muerde al cierre del dia ANTERIOR.
    earn = ("2026-07-30", "BMO", datetime.datetime(2026, 7, 30, 8, 30))
    lines = fleet.earnings_veto_lines("AAPL", earn, today="2026-07-29")
    assert any("VETO HOY" in ln for ln in lines)


def test_earnings_veto_lines_bmo_report_day_already_passed(fleet):
    earn = ("2026-07-30", "BMO", datetime.datetime(2026, 7, 30, 8, 30))
    lines = fleet.earnings_veto_lines("AAPL", earn, today="2026-07-30")
    assert any("veto ya no aplica" in ln for ln in lines)


# ---------- load_earnings_calendar: re-verificado via x_earnings_post, nunca {} fabricado ----------
def test_load_earnings_calendar_missing_module_returns_none(fleet, monkeypatch):
    monkeypatch.setitem(sys.modules, "x_earnings_post", None)
    assert fleet.load_earnings_calendar() is None


def test_load_earnings_calendar_broken_feed_returns_none(fleet, monkeypatch):
    class FakeXep:
        CACHE_152 = "irrelevant"
        COLS_152 = "irrelevant"
        token = staticmethod(lambda: "tok")
        fetch_csv = staticmethod(lambda *a, **k: None)
        parse_csv = staticmethod(lambda body: None)
        parse_earn = staticmethod(lambda s: None)

    monkeypatch.setitem(sys.modules, "x_earnings_post", FakeXep)
    assert fleet.load_earnings_calendar() is None


def test_load_earnings_calendar_parses_rows_into_dict(fleet, monkeypatch):
    parsed = ("2026-07-28", "AMC", datetime.datetime(2026, 7, 28, 16, 30))

    class FakeXep:
        CACHE_152 = "irrelevant"
        COLS_152 = "irrelevant"
        token = staticmethod(lambda: "tok")
        fetch_csv = staticmethod(lambda *a, **k: "csv-body")
        parse_csv = staticmethod(lambda body: [{"Ticker": "STX", "Earnings Date": "7/28/2026 4:30:00 PM"}])
        parse_earn = staticmethod(lambda s: parsed)

    monkeypatch.setitem(sys.modules, "x_earnings_post", FakeXep)
    assert fleet.load_earnings_calendar() == {"STX": parsed}
