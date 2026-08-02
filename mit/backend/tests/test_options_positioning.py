from __future__ import annotations

import pytest

from backend.app.analytics.options_positioning import (
    analyze_dealer_positioning,
    compute_option_matrix,
)
from backend.app.domain import OptionContract
from backend.app.providers.mock import MockProvider
from datetime import date, timedelta


@pytest.mark.asyncio
async def test_positioning_has_walls_and_gex() -> None:
    provider = MockProvider()
    quote = await provider.get_quote("SPY")
    chain = await provider.get_option_chain("SPY")
    result = analyze_dealer_positioning("SPY", quote.last, chain)
    assert result.call_wall is not None
    assert result.put_wall is not None
    assert result.max_pain is not None
    assert result.expected_move is not None and result.expected_move > 0
    assert result.gex_by_strike
    assert result.gamma_regime in {"POSITIVE / DAMPENING", "NEGATIVE / AMPLIFYING"}


@pytest.mark.asyncio
async def test_gex_heatmap_matrix_shape_and_signs() -> None:
    provider = MockProvider()
    quote = await provider.get_quote("SPY")
    chain = await provider.get_option_chain("SPY")
    matrix = compute_option_matrix("SPY", quote.last, chain, metric="gex")
    assert matrix["metric"] == "gex"
    assert matrix["strikes"] == sorted(matrix["strikes"], reverse=True)
    assert matrix["expirations"] == sorted(matrix["expirations"])
    assert matrix["cells"]
    assert matrix["max_cell"] is not None
    # Every cell key resolves to a strike/expiry present in the axes.
    for key in matrix["cells"]:
        strike_s, expiry = key.split("|")
        assert expiry in matrix["expirations"]
        assert float(strike_s) in matrix["strikes"]
    # Sign convention: single deep call is positive, single deep put is negative (call +, put -).
    expiry = date.today() + timedelta(days=30)
    call = OptionContract(symbol="X", expiration=expiry, strike=100, option_type="call",
                          open_interest=1000, gamma=0.02, vega=0.1)
    put = call.model_copy(update={"option_type": "put"})
    assert compute_option_matrix("X", 100.0, [call], metric="gex")["max_cell"]["value"] > 0
    assert compute_option_matrix("X", 100.0, [put], metric="gex")["max_cell"]["value"] < 0
    # VEX toggle works and empty chain yields no cells (fail-loud blank, no fabricated 0).
    assert compute_option_matrix("X", 100.0, [call], metric="vex")["max_cell"]["value"] > 0
    empty = compute_option_matrix("X", 100.0, [], metric="gex")
    assert empty["cells"] == {} and empty["max_cell"] is None
