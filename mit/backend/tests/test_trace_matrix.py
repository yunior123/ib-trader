from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.app.analytics.options_positioning import MATRIX_BAND, compute_trace_matrix
from backend.app.domain import OptionContract
from backend.app.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_trace_gex_shape_banding_and_levels() -> None:
    provider = MockProvider()
    quote = await provider.get_quote("SPY")
    chain = await provider.get_option_chain("SPY")
    matrix = compute_trace_matrix("SPY", quote.last, chain, metric="gex")
    assert matrix["metric"] == "gex"
    assert matrix["strikes"] == sorted(matrix["strikes"], reverse=True)
    assert matrix["by_strike"]
    # Banding: every returned strike is within +/-MATRIX_BAND of spot.
    lo, hi = quote.last * (1 - MATRIX_BAND), quote.last * (1 + MATRIX_BAND)
    assert all(lo <= s <= hi for s in matrix["strikes"])
    # Levels present (from analyze_dealer_positioning).
    for key in ("call_wall", "put_wall", "gamma_flip", "max_pain"):
        assert key in matrix["levels"]


def test_trace_sign_convention_and_metrics() -> None:
    expiry = date.today() + timedelta(days=30)
    call = OptionContract(symbol="X", expiration=expiry, strike=100, option_type="call",
                          open_interest=1000, gamma=0.02, vega=0.1)
    put = call.model_copy(update={"option_type": "put"})
    # GEX: call +, put - (house sign).
    assert compute_trace_matrix("X", 100.0, [call], metric="gex")["by_strike"]["100"] > 0
    assert compute_trace_matrix("X", 100.0, [put], metric="gex")["by_strike"]["100"] < 0
    # Net OI: call +, put -.
    assert compute_trace_matrix("X", 100.0, [call], metric="netoi")["by_strike"]["100"] == 1000
    assert compute_trace_matrix("X", 100.0, [put], metric="netoi")["by_strike"]["100"] == -1000


def test_trace_fail_loud_empty_and_missing_greeks() -> None:
    expiry = date.today() + timedelta(days=30)
    # Empty chain -> empty by_strike (no fabricated 0).
    empty = compute_trace_matrix("X", 100.0, [], metric="gex")
    assert empty["by_strike"] == {} and empty["strikes"] == []
    # GEX omits strikes without measured gamma; Net OI still counts them.
    no_gamma = OptionContract(symbol="X", expiration=expiry, strike=100, option_type="call",
                              open_interest=500, gamma=None)
    assert compute_trace_matrix("X", 100.0, [no_gamma], metric="gex")["by_strike"] == {}
    assert compute_trace_matrix("X", 100.0, [no_gamma], metric="netoi")["by_strike"]["100"] == 500


def test_trace_bad_metric_raises() -> None:
    with pytest.raises(ValueError):
        compute_trace_matrix("X", 100.0, [], metric="bogus")
