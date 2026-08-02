from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.providers.base import (
    PROVIDER_REGISTRY,
    FlowDataProvider,
    ProviderError,
    UnavailableProvider,
    register,
)
from backend.app.providers.databento import DatabentoProvider
from backend.app.providers.intrinio import IntrinioProvider
from backend.app.providers.mock import MockProvider
from backend.app.providers.polygon import PolygonProvider
from backend.app.providers.registry import ProviderSet, build_providers
from backend.app.providers.unusual_whales import UnusualWhalesProvider


def test_declared_capabilities():
    assert IntrinioProvider.__capabilities__ == {"market", "options"}
    assert PolygonProvider.__capabilities__ == {"market", "options"}
    assert DatabentoProvider.__capabilities__ == {"market", "depth"}
    assert UnusualWhalesProvider.__capabilities__ == {"flow"}
    assert MockProvider.__capabilities__ == {"market", "options", "depth", "flow"}


def test_provider_error_backward_compat():
    err = ProviderError("boom")
    assert str(err) == "boom"
    assert err.provider is None and err.capability is None and err.error_code is None


def test_provider_error_structured():
    err = ProviderError("nope", provider="polygon", capability="flow", error_code="E1")
    assert err.provider == "polygon"
    assert err.capability == "flow"
    assert err.error_code == "E1"
    assert isinstance(err, RuntimeError)


def test_capability_rejects_undeclared_without_instantiating():
    # A registered provider declaring only {"market"} whose __init__ blows up if ever called.
    instantiated = {"count": 0}

    @register("_polish_probe")
    class _Probe(FlowDataProvider):
        name = "_polish_probe"
        __capabilities__ = {"market"}

        def __init__(self, settings):
            instantiated["count"] += 1
            raise RuntimeError("must not be instantiated for undeclared capability")

        async def get_option_flow(self, symbol, *, limit=100):
            return []

    try:
        settings = Settings(watchlist=["SPY"], flow_provider="_polish_probe")
        providers = build_providers(settings)
        assert isinstance(providers.flow, UnavailableProvider)
        assert "does not declare" in providers.flow.message
        assert instantiated["count"] == 0  # rejected pre-instantiation
    finally:
        PROVIDER_REGISTRY.pop("_polish_probe", None)


@pytest.mark.asyncio
async def test_close_survives_one_bad_provider():
    settings = Settings(watchlist=["SPY"])
    providers = build_providers(settings)

    closed = {"market": False, "options": False}

    class _GoodClose:
        name = "good"

        async def close(self):
            closed["options"] = True

    class _BadClose:
        name = "bad"

        async def close(self):
            raise RuntimeError("close explodes")

    fresh = ProviderSet(
        market=_BadClose(),
        options=_GoodClose(),
        depth=providers.depth,
        flow=providers.flow,
        fallback=providers.fallback,
    )
    # Must not raise despite the bad provider; the good one still closes.
    await fresh.close()
    assert closed["options"] is True
