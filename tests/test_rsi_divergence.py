import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chart_bridge_rsi", REPO / "scripts" / "chart_bridge.py")
CB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CB)


def _bars(lows, highs):
    return [(1_700_000_000 + i * 60, (lo + hi) / 2, hi, lo, (lo + hi) / 2, 1000)
            for i, (lo, hi) in enumerate(zip(lows, highs))]


def test_regular_bullish_divergence_is_marked_on_confirmation_bar():
    lows = [100, 99, 98, 99, 100, 101, 100, 99, 97, 95, 90, 95, 98, 99]
    highs = [x + 5 for x in lows]
    rsi = [50.0] * len(lows)
    rsi[2], rsi[10] = 25.0, 35.0
    got = CB.rsi_divergence_markers(_bars(lows, highs), rsi)
    assert len(got) == 1
    assert got[0]["text"] == "RSI↗"
    assert got[0]["time"] == _bars(lows, highs)[12][0]  # pivote 10 + 2 velas de confirmación


def test_regular_bearish_divergence_is_marked_on_confirmation_bar():
    highs = [100, 101, 105, 101, 100, 101, 102, 104, 108, 112, 110, 106, 104, 103]
    lows = [x - 5 for x in highs]
    rsi = [50.0] * len(highs)
    rsi[2], rsi[9] = 75.0, 65.0
    got = CB.rsi_divergence_markers(_bars(lows, highs), rsi)
    assert len(got) == 1
    assert got[0]["text"] == "RSI↘"
    assert got[0]["time"] == _bars(lows, highs)[11][0]


def test_indicator_payload_contains_rsi_and_confirmed_divergences():
    bars = _bars([100 + i * .1 for i in range(40)], [101 + i * .1 for i in range(40)])
    ind = CB.compute_indicators(bars)
    ser = CB.indicators_series(bars, ind)
    assert len(ser["rsi"]) == 26
    assert len(ser["rsiFast"]) == 35
    assert len(ser["rsiDivergence"]) == 26
    assert isinstance(ser["rsiDivMarkers"], list)


def test_rsi_divergence_study_is_fast_rsi_minus_slow_rsi_with_sign_color():
    closes = [100, 101, 102, 101, 103, 105, 104, 106, 108, 107,
              106, 109, 111, 110, 112, 114, 113, 111, 110, 112,
              115, 117, 116, 118, 120, 119, 121, 122, 120, 119]
    bars = [(1_700_000_000 + i * 60, c, c + 1, c - 1, c, 1000)
            for i, c in enumerate(closes)]
    ind = CB.compute_indicators(bars)
    for fast, slow, div in zip(ind["rsiFast"], ind["rsi"], ind["rsiDivergence"]):
        if fast is None or slow is None:
            assert div is None
        else:
            assert div == fast - slow
    points = CB.indicators_series(bars, ind)["rsiDivergence"]
    assert points
    assert all(p["color"] == ("#26a69a" if p["value"] >= 0 else "#ef5350") for p in points)
