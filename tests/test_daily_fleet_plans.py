"""daily_fleet_plans.py — bs_greeks() (money path), measured_prob, load_* guards."""
import datetime
import math
import os
import sys
import time

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


# ---------- CSV rancio / ausente: se dice la edad, jamas silencio ni veto a ciegas ----------
def _fake_xep(cache_path, fetch_ok, parsed):
    class FakeXep:
        CACHE_152 = str(cache_path)
        COLS_152 = "irrelevant"
        token = staticmethod(lambda: "tok")
        fetch_csv = staticmethod(lambda *a, **k: ("csv-body" if fetch_ok else None))
        parse_csv = staticmethod(lambda body: [{"Ticker": "STX", "Earnings Date": "x"}] if body else None)
        parse_earn = staticmethod(lambda s: parsed)
    return FakeXep


def test_earnings_calendar_dated_stale_cache_served_with_age(fleet, tmp_path, monkeypatch):
    # Finviz caido (fetch None) + cache de 3 dias -> se sirve el dato CON su edad, no None.
    parsed = ("2026-07-28", "AMC", datetime.datetime(2026, 7, 28, 16, 30))
    cache = tmp_path / "earn.csv"
    cache.write_text("csv-body")
    old = time.time() - 3 * 86400
    os.utime(cache, (old, old))
    monkeypatch.setitem(sys.modules, "x_earnings_post", _fake_xep(cache, False, parsed))
    cal, age_h = fleet.earnings_calendar_dated()
    assert cal == {"STX": parsed}
    assert 70 < age_h < 74


def test_earnings_calendar_dated_no_cache_returns_none_none(fleet, tmp_path, monkeypatch):
    missing = tmp_path / "no-such.csv"
    monkeypatch.setitem(sys.modules, "x_earnings_post", _fake_xep(missing, False, None))
    assert fleet.earnings_calendar_dated() == (None, None)


def test_earnings_veto_lines_stale_marks_age_and_does_not_veto_blind(fleet):
    earn = ("2026-07-28", "AMC", datetime.datetime(2026, 7, 28, 16, 30))
    lines = fleet.earnings_veto_lines("STX", earn, today="2026-07-28", age_h=72.0)
    assert any("RANCIO (72h" in ln for ln in lines)
    assert any("VETO HOY" in ln for ln in lines)
    assert any("confirmarla antes de fiarse del veto" in ln for ln in lines)


def test_earnings_veto_lines_fresh_has_no_stale_tag(fleet):
    earn = ("2026-07-28", "AMC", datetime.datetime(2026, 7, 28, 16, 30))
    lines = fleet.earnings_veto_lines("STX", earn, today="2026-07-28", age_h=1.0)
    assert not any("RANCIO" in ln for ln in lines)


def test_earnings_veto_lines_broken_calendar_warns_never_silent(fleet):
    lines = fleet.earnings_veto_lines("NVDA", None, today="2026-07-28", cal_ok=False)
    assert lines and any("NO verificado" in ln for ln in lines)
    assert not any("VETO HOY" in ln for ln in lines)   # aviso, jamas un veto fabricado


def test_earnings_veto_lines_healthy_calendar_no_earnings_is_silent(fleet):
    assert fleet.earnings_veto_lines("NVDA", None, today="2026-07-28", cal_ok=True) == []


# ---------- macro en el plan (plan_engine) ----------
def _plan_args():
    cs = dict(pain=100.0, gex={100.0: 1.0}, net_gex=1e6, flip=99.0,
              cw=[[102.0, 5000, 100, 1.0, 1.1, 0.3]], pw=[[98.0, 4000, 100, 1.0, 1.1, 0.3]],
              atm=100.0, straddle=2.0, imove=2.0, iv=0.3, pcv=1.0, pco=1.0, T=0.01,
              greeks=dict(delta=0.5, gamma=0.01, theta=-0.1, vega=0.1), exp="2026-07-31")
    on = dict(prev_close=99.5, atr=1.5, gap_pct=0.5, ext_atr=0.3, fill_rate=60,
              n_gaps=20, bb_lo=95.0, bb_hi=105.0, pb=0.5)
    return cs, on


def test_plan_engine_macro_today_appears_with_veto(fleet):
    cs, on = _plan_args()
    macro = [dict(kind="FOMC", date="2026-07-29", hora="2:00pm ET (decision)",
                  days_away=0, source="federalreserve.gov")]
    lines, *_ = fleet.plan_engine("NVDA", 100.0, cs, on, 0, 0, {}, {},
                                  dict(style="weekly", korea=False), macro=macro)
    assert any("MACRO FOMC 2026-07-29" in ln for ln in lines)
    assert any("NO OPERAR EL PRINT" in ln for ln in lines)


def test_plan_engine_no_macro_event_no_macro_line(fleet):
    cs, on = _plan_args()
    lines, *_ = fleet.plan_engine("NVDA", 100.0, cs, on, 0, 0, {}, {},
                                  dict(style="weekly", korea=False), macro=[])
    assert not any("MACRO" in ln for ln in lines)


def test_plan_engine_macro_calendar_missing_shouts(fleet):
    cs, on = _plan_args()
    lines, *_ = fleet.plan_engine("NVDA", 100.0, cs, on, 0, 0, {}, {},
                                  dict(style="weekly", korea=False), macro=None)
    assert any("SIN calendario CPI/FOMC/NFP" in ln for ln in lines)


def test_plan_engine_earnings_amc_veto_lands_in_plan(fleet, monkeypatch):
    cs, on = _plan_args()
    real = time.strftime
    monkeypatch.setattr(fleet.time, "strftime",
                        lambda f, *a: "2026-07-29" if f == "%Y-%m-%d" else real(f, *a))
    earn = ("2026-07-29", "AMC", datetime.datetime(2026, 7, 29, 16, 30))
    lines, *_ = fleet.plan_engine("MSFT", 100.0, cs, on, 0, 0, {}, {},
                                  dict(style="weekly", korea=False), earn=earn, macro=[])
    assert any("EARNINGS 2026-07-29 tras el cierre (AMC)" in ln for ln in lines)
    assert any("VETO HOY" in ln for ln in lines)


def test_load_macro_events_looks_a_week_ahead_but_not_back(fleet, monkeypatch):
    # el FOMC del miercoles tiene que verse ya el domingo; lo de hace 5 dias, no.
    class FakeMc:
        @staticmethod
        def macro_events_near(d, window_days=2):
            assert window_days == fleet.MACRO_AHEAD_D
            return [dict(kind="FOMC", date="x", hora="h", days_away=3, source="s"),
                    dict(kind="CPI", date="y", hora="h", days_away=-5, source="s")]

    monkeypatch.setitem(sys.modules, "macro_calendar", FakeMc)
    evs = fleet.load_macro_events()
    assert [e["kind"] for e in evs] == ["FOMC"]


def test_load_macro_events_uncovered_year_returns_none(fleet, monkeypatch):
    class FakeMc:
        macro_events_near = staticmethod(lambda d, window_days=2: None)

    monkeypatch.setitem(sys.modules, "macro_calendar", FakeMc)
    assert fleet.load_macro_events() is None


def test_plan_engine_ticker_without_earnings_has_no_veto(fleet):
    cs, on = _plan_args()
    lines, *_ = fleet.plan_engine("NVDA", 100.0, cs, on, 0, 0, {}, {},
                                  dict(style="weekly", korea=False), earn=None, macro=[])
    assert not any("EARNINGS" in ln for ln in lines if "FINVIZ" not in ln)
