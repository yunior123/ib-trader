from __future__ import annotations

import pytest

from backend.app.analytics.orderbook import analyze_order_book
from backend.app.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_book_analytics_are_bounded() -> None:
    book = await MockProvider().get_order_book("TSLA", depth=12)
    result = analyze_order_book(book)
    assert result.spread >= 0
    assert -1 <= result.imbalance <= 1
    assert result.bid_wall is not None
    assert result.ask_wall is not None
    assert result.microprice is not None
