from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from backend.app.domain import Bar, OptionContract, OptionFlow, OrderBook, Quote


class ProviderError(RuntimeError):
    # Optional structured context; all default to None so existing bare raises keep working.
    def __init__(
        self,
        message: str = "",
        *,
        provider: str | None = None,
        capability: str | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.capability = capability
        self.error_code = error_code


# --- Registro de plugins de proveedor -----------------------------------------
# AÑADIR un proveedor (incl. IBKR en el futuro) = crear UN fichero en providers/ con la clase
# decorada @register("nombre"). registry.py auto-descubre el paquete; NO se toca registry ni
# config. El nombre es el valor de MIT_<CAP>_PROVIDER en feeds.env. (idea MVVM: el adaptador de
# la API es lo unico que cambia; el servicio generico queda intacto.)
PROVIDER_REGISTRY: dict[str, type] = {}


def register(name: str):
    def deco(cls: type) -> type:
        PROVIDER_REGISTRY[name] = cls
        return cls
    return deco


class MarketDataProvider(ABC):
    name = "market-base"

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    async def get_bars(
        self, symbol: str, *, interval: str = "5m", limit: int = 1200
    ) -> list[Bar]: ...

    async def get_daily_bars(self, symbol: str, *, limit: int = 756) -> list[Bar]:
        return await self.get_bars(symbol, interval="1d", limit=limit)

    async def close(self) -> None:
        return None


class OptionsDataProvider(ABC):
    name = "options-base"

    @abstractmethod
    async def get_option_chain(
        self, symbol: str, *, expiration: datetime | None = None
    ) -> list[OptionContract]: ...

    async def close(self) -> None:
        return None


class DepthDataProvider(ABC):
    name = "depth-base"

    @abstractmethod
    async def get_order_book(self, symbol: str, *, depth: int = 10) -> OrderBook: ...

    async def close(self) -> None:
        return None


class FlowDataProvider(ABC):
    name = "flow-base"

    @abstractmethod
    async def get_option_flow(self, symbol: str, *, limit: int = 100) -> list[OptionFlow]: ...

    async def close(self) -> None:
        return None


class UnavailableProvider(MarketDataProvider, OptionsDataProvider, DepthDataProvider, FlowDataProvider):
    """Placeholder that preserves process startup and triggers capability-local fallback."""

    def __init__(self, requested_name: str, message: str) -> None:
        self.name = requested_name
        self.message = message

    def _raise(self) -> None:
        raise ProviderError(self.message)

    async def get_quote(self, symbol: str) -> Quote:
        self._raise()

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        self._raise()

    async def get_daily_bars(self, symbol: str, *, limit: int = 756) -> list[Bar]:
        self._raise()

    async def get_option_chain(self, symbol: str, *, expiration: datetime | None = None) -> list[OptionContract]:
        self._raise()

    async def get_order_book(self, symbol: str, *, depth: int = 10) -> OrderBook:
        self._raise()

    async def get_option_flow(self, symbol: str, *, limit: int = 100) -> list[OptionFlow]:
        self._raise()
