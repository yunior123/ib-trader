from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import TypeVar

_log = logging.getLogger("mit.providers")

from backend.app.config import Settings
from backend.app.providers.base import (
    PROVIDER_REGISTRY,
    DepthDataProvider,
    FlowDataProvider,
    MarketDataProvider,
    OptionsDataProvider,
    ProviderError,
    UnavailableProvider,
)
from backend.app.providers.mock import MockProvider


def _discover() -> None:
    """Auto-importa cada modulo de providers/ para que sus @register(...) llenen PROVIDER_REGISTRY.
    AÑADIR un proveedor = soltar UN fichero providers/<x>.py con @register('x'); NO se toca este
    fichero ni config. Un modulo cuya dependencia opcional falte al importar se ignora (su nombre
    quedara 'desconocido' -> UnavailableProvider al pedirlo)."""
    import backend.app.providers as _pkg
    for mod in sorted(pkgutil.iter_modules(_pkg.__path__), key=lambda m: m.name):  # orden determinista
        if mod.name.startswith("_") or mod.name in {"base", "registry"}:
            continue
        try:
            importlib.import_module(f"backend.app.providers.{mod.name}")
        except Exception as e:  # dep opcional ausente O bug real: se registra un WARNING (no silencio)
            _log.warning("provider '%s' no importado: %s: %s", mod.name, type(e).__name__, e)


_discover()


@dataclass(slots=True)
class ProviderSet:
    market: MarketDataProvider
    options: OptionsDataProvider
    depth: DepthDataProvider
    flow: FlowDataProvider
    fallback: MockProvider

    async def close(self) -> None:
        providers = {id(p): p for p in (self.market, self.options, self.depth, self.flow, self.fallback)}
        for provider in providers.values():
            await provider.close()


T = TypeVar("T")


def build_providers(settings: Settings) -> ProviderSet:
    fallback = MockProvider()
    cache: dict[str, object] = {"mock": fallback}

    def get(name: str) -> object:
        if name in cache:
            return cache[name]
        builder = PROVIDER_REGISTRY.get(name)
        try:
            if builder is None:
                raise ProviderError(f"Unknown provider: {name}")
            provider: object = builder(settings)
        except Exception as exc:
            provider = UnavailableProvider(name, f"{type(exc).__name__}: {exc}")
        cache[name] = provider
        return provider

    def capability(name: str, expected: type[T], label: str) -> T:
        provider = get(name)
        if isinstance(provider, expected):
            return provider
        return UnavailableProvider(name, f"{name} does not implement {label}")  # type: ignore[return-value]

    return ProviderSet(
        market=capability(settings.market_provider, MarketDataProvider, "market data"),
        options=capability(settings.options_provider, OptionsDataProvider, "option chains"),
        depth=capability(settings.depth_provider, DepthDataProvider, "order-book depth"),
        flow=capability(settings.flow_provider, FlowDataProvider, "options flow"),
        fallback=fallback,
    )
