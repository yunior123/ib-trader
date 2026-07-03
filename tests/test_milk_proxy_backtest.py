import datetime as dt
import importlib.util
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "milk_proxy_backtest", REPO / "scripts" / "research" / "milk_proxy_backtest.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_implied_greeks_recovers_known_black_scholes_volatility():
    premium = M.bs_price(100, 105, 7 / 365, 0.35, "C")
    delta, gamma, iv = M.implied_greeks(100, 105, 7 / 365, premium, "C")
    assert abs(iv - 0.35) < 1e-6
    assert 0 < delta < 1 and gamma > 0


def test_daily_snapshot_rolls_same_day_friday_to_next_week():
    assert M.next_friday(dt.date(2026, 8, 12)) == dt.date(2026, 8, 14)
    assert M.next_friday(dt.date(2026, 8, 14)) == dt.date(2026, 8, 21)


def test_volume_pain_tie_is_deterministically_nearest_spot():
    frame = pd.DataFrame([
        {"opt_type": "C", "strike": 105.0, "volume": 50},
        {"opt_type": "P", "strike": 95.0, "volume": 40},
    ])
    assert M.volume_pain(frame, 103) == 105


def test_observation_uses_only_next_session_and_symmetric_barrier():
    day = dt.date(2026, 8, 10)
    nxt = dt.date(2026, 8, 11)
    prices = {"QQQ": {day: (99, 101, 98, 100), nxt: (100, 102, 98, 101)}}
    rows = [{"symbol": "QQQ", "date": day, "spot": 100,
             "wdn": 102, "mm_top": 99}]
    got = M.observations(rows, prices, "wdn")
    assert len(got) == 1 and got[0]["next_date"] == nxt
    assert got[0]["hit"] == 1
    # Target 102 and symmetric stop 98 both trade inside the daily bar: tie=failure.
    assert got[0]["barrier"] == -1


def test_promotion_gate_refuses_short_date_history():
    rows = []
    start = dt.date(2026, 1, 1)
    for i in range(30):
        rows.append({"date": start + dt.timedelta(days=i), "distance_pct": 0.2,
                     "hit": 1, "null_hit": 0, "barrier": 1})
    out = M.audit("TEST", rows)
    assert out["verdict"] == "DATA_INSUFFICIENT"
    assert out["train_dates"] == 18 and out["oos_dates"] == 12
