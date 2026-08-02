from __future__ import annotations

import pytest

from backend.app.analytics.options_positioning import analyze_dealer_positioning
from backend.app.providers.mock import MockProvider


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
