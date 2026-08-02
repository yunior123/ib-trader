from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.engine import EventBus, MarketIntelligenceEngine
from backend.app.providers.registry import build_providers


async def main() -> None:
    settings = Settings(watchlist=["SPY", "TSLA", "MSTR"], reversion_lookback_days=260)
    engine = MarketIntelligenceEngine(settings, build_providers(settings), EventBus())
    try:
        snapshot = await engine.snapshot("SPY", force=True)
        print(json.dumps({
            "symbol": snapshot.symbol,
            "last": snapshot.quote.last,
            "router": snapshot.signals.router_state,
            "gamma_regime": snapshot.dealer.gamma_regime,
            "gamma_flip": snapshot.dealer.gamma_flip,
            "shock": snapshot.shock.label,
            "weekly_rows": len(snapshot.weekly),
            "flows": len(snapshot.flows),
            "alerts": len(snapshot.alerts),
            "providers": [item.provider for item in snapshot.provider_status],
        }, indent=2))
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
