from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.engine import EventBus, MarketIntelligenceEngine
from backend.app.providers.registry import build_providers


@pytest.mark.asyncio
async def test_complete_mock_snapshot() -> None:
    settings = Settings(watchlist=["SPY", "TSLA"], reversion_lookback_days=260)
    providers = build_providers(settings)
    engine = MarketIntelligenceEngine(settings, providers, EventBus())
    try:
        snapshot = await engine.snapshot("SPY", force=True)
        assert snapshot.quote.symbol == "SPY"
        assert len(snapshot.bars) == 600
        assert snapshot.dealer.magnets
        assert snapshot.weekly
        assert snapshot.provider_status
        assert snapshot.metadata["mode"] == "mock"
    finally:
        await engine.close()
