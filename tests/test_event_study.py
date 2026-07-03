#!/usr/bin/env python3
"""test_event_study.py — arnes de event-study. Corre solo:
  ./venv/bin/python -m pytest tests/test_event_study.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))
import event_study as ES  # noqa: E402


# ---------- first_touch ----------
def test_first_touch_favorable():
    # entra en idx0 (100), sube y toca 105 antes de bajar a 95
    prices = [100, 101, 103, 105, 90]
    assert ES.first_touch(prices, 0, 105, 95, 10) == "favorable"


def test_first_touch_adverse():
    prices = [100, 99, 96, 95, 110]  # toca 95 (abajo) antes de 105
    assert ES.first_touch(prices, 0, 105, 95, 10) == "adverse"


def test_first_touch_unresolved():
    prices = [100, 101, 99, 100, 101]  # nunca alcanza 105 ni 95
    assert ES.first_touch(prices, 0, 105, 95, 10) == "unresolved"


def test_first_touch_horizon_truncates():
    # 105 se toca en idx3 pero horizon=2 solo mira idx1,idx2
    prices = [100, 101, 102, 105]
    assert ES.first_touch(prices, 0, 105, 95, 2) == "unresolved"


def test_first_touch_up_hit_before_down_in_time():
    # sube primero (favorable) aunque mas tarde caiga a la barrera de abajo
    prices = [100, 106, 90]
    assert ES.first_touch(prices, 0, 105, 95, 10) == "favorable"


def test_first_touch_bad_barriers_raises():
    with pytest.raises(ValueError):
        ES.first_touch([100, 101], 0, 95, 105, 5)  # up<=dn


# ---------- mfe_mae ----------
def test_mfe_mae_long():
    prices = [100, 103, 98, 101]  # entry 100: mfe=+3, mae=+2
    r = ES.mfe_mae(prices, 0, 10, direction=1)
    assert r["mfe"] == 3.0 and r["mae"] == 2.0 and r["mfe_gt_mae"] is True


def test_mfe_mae_short():
    prices = [100, 103, 95, 101]  # short: favorable = baja; mfe=+5, mae=+3
    r = ES.mfe_mae(prices, 0, 10, direction=-1)
    assert r["mfe"] == 5.0 and r["mae"] == 3.0 and r["mfe_gt_mae"] is True


def test_mfe_mae_no_forward_returns_none():
    assert ES.mfe_mae([100], 0, 10) is None


# ---------- resolve_event direccion ----------
def test_resolve_event_short_inverts_label():
    prices = [100, 94, 110]  # baja a la barrera de abajo primero
    # long: tocar abajo = adverse ; short: tocar abajo = favorable
    assert ES.resolve_event(prices, 0, 1, 105, 95, 10)["outcome"] == "adverse"
    assert ES.resolve_event(prices, 0, -1, 105, 95, 10)["outcome"] == "favorable"


# ---------- wilson ----------
def test_wilson_reference_50_100():
    p, lo, hi = ES.wilson(50, 100)
    assert p == 0.5
    assert abs(lo - 0.4038) < 0.001
    assert abs(hi - 0.5962) < 0.001


def test_wilson_all_wins():
    p, lo, hi = ES.wilson(30, 30)
    assert p == 1.0 and lo < 1.0 and hi <= 1.0 + 1e-9


def test_wilson_zero_n_raises():
    with pytest.raises(ValueError):
        ES.wilson(0, 0)  # fail-loud: sin muestra no hay tasa


def test_wilson_k_gt_n_raises():
    with pytest.raises(ValueError):
        ES.wilson(11, 10)


# ---------- grade_signal ----------
def _events(n_fav, n_adv, n_unres=0, year=2026, mfe_true=None):
    ev = []
    for _ in range(n_fav):
        ev.append(dict(outcome="favorable", year=year,
                       mfe_gt_mae=(True if mfe_true is None else mfe_true)))
    for _ in range(n_adv):
        ev.append(dict(outcome="adverse", year=year,
                       mfe_gt_mae=(False if mfe_true is None else mfe_true)))
    for _ in range(n_unres):
        ev.append(dict(outcome="unresolved", year=year))
    return ev


def test_grade_below_min_n_returns_none():
    assert ES.grade_signal(_events(10, 10), min_n=30) is None


def test_grade_resolves_and_excludes_unresolved_from_denominator():
    g = ES.grade_signal(_events(40, 40, n_unres=20), min_n=30)
    assert g is not None
    assert g["n_resolved"] == 80          # unresolved fuera del denominador
    assert g["n_unresolved"] == 20
    assert g["n_total"] == 100
    assert g["win_rate"] == 0.5
    assert g["favorable"] == 40


def test_grade_win_rate_matches_wilson():
    g = ES.grade_signal(_events(50, 50), min_n=30)
    p, lo, hi = ES.wilson(50, 100)
    assert g["win_rate"] == round(p, 4)
    assert g["wilson_lo"] == round(lo, 4)
    assert g["wilson_hi"] == round(hi, 4)


def test_grade_mfe_gt_mae_pct():
    # 40 fav (mfe>mae True), 40 adv (False) -> 50%
    g = ES.grade_signal(_events(40, 40), min_n=30)
    assert g["mfe_gt_mae_pct"] == 50.0


def test_grade_by_year_flags_thin_years():
    ev = _events(40, 40, year=2025) + _events(5, 5, year=2026)
    g = ES.grade_signal(ev, min_n=30)
    assert g["by_year"][2025]["win_rate"] == 0.5
    assert g["by_year"][2026]["status"] == "INSUFFICIENT_N"
    assert g["by_year"][2026]["win_rate"] is None


# ---------- ATR / bars ----------
def test_wilder_atr_insufficient_returns_none():
    import numpy as np
    h = np.arange(10, dtype=float) + 1
    l = np.arange(10, dtype=float)
    c = np.arange(10, dtype=float) + 0.5
    assert ES.wilder_atr_at(h, l, c, 5, period=14) is None  # <period previas


def test_wilder_atr_constant_range():
    import numpy as np
    # rango constante de 2.0 por barra, sin gaps de close -> ATR converge a 2.0
    n = 40
    c = np.full(n, 100.0)
    h = c + 1.0
    l = c - 1.0
    atr = ES.wilder_atr_at(h, l, c, n - 1, period=14)
    assert atr is not None and abs(atr - 2.0) < 1e-6


def test_dir_parsing():
    assert ES._dir("long") == 1 and ES._dir("put") == -1
    assert ES._dir(1) == 1 and ES._dir(-3) == -1
    assert ES._dir("nonsense") is None
