"""macro_calendar.py — CPI/FOMC/NFP: fail-loud si el año no esta cubierto, nunca [] fabricado."""
import datetime

import pytest


def test_load_confirmed_wrong_year_returns_none(macro_cal):
    assert macro_cal.load_confirmed(1999) is None


def test_load_confirmed_2026_has_all_three_kinds(macro_cal):
    d = macro_cal.load_confirmed(2026)
    assert d is not None
    assert len(d["fomc"]) == 8
    assert len(d["cpi"]) == 12
    assert len(d["nfp"]) == 5  # medido: solo 5/12 confirmados, el resto se queda ausente


def test_macro_events_near_unknown_year_returns_none(macro_cal):
    assert macro_cal.macro_events_near(datetime.date(1999, 1, 1)) is None


def test_macro_events_near_finds_fomc_within_window(macro_cal):
    # FOMC jul-2026 termina 2026-07-29
    evs = macro_cal.macro_events_near(datetime.date(2026, 7, 27), window_days=2)
    kinds = {e["kind"] for e in evs}
    assert "FOMC" in kinds


def test_macro_events_near_finds_nfp_exact_day(macro_cal):
    evs = macro_cal.macro_events_near(datetime.date(2026, 8, 7), window_days=0)
    assert any(e["kind"] == "NFP" and e["days_away"] == 0 for e in evs)


def test_macro_events_near_finds_cpi_exact_day(macro_cal):
    evs = macro_cal.macro_events_near(datetime.date(2026, 7, 14), window_days=0)
    assert any(e["kind"] == "CPI" and e["days_away"] == 0 for e in evs)


def test_macro_events_near_empty_window_far_from_any_event(macro_cal):
    # 2026-07-20 no cae cerca de ningun CPI/FOMC/NFP confirmado con ventana 0
    evs = macro_cal.macro_events_near(datetime.date(2026, 7, 20), window_days=0)
    assert evs == []


def test_macro_events_near_sorted_by_proximity(macro_cal):
    evs = macro_cal.macro_events_near(datetime.date(2026, 7, 26), window_days=5)
    days = [abs(e["days_away"]) for e in evs]
    assert days == sorted(days)
