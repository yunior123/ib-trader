from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from typing import Any

import websockets

from backend.app.config import Settings
from backend.app.domain import OptionFlow
from backend.app.providers.base import FlowDataProvider, ProviderError, register


@register("unusual_whales")
class UnusualWhalesProvider(FlowDataProvider):
    """Configurable Unusual Whales WebSocket adapter.

    Public docs enumerate stream topics, but account-specific endpoint/auth payloads may differ.
    The URL and two JSON templates are therefore configuration, never guessed in code.
    """

    name = "unusual_whales"
    __capabilities__: set[str] = {"flow"}

    def __init__(self, settings: Settings) -> None:
        if not settings.unusual_whales_token or not settings.uw_ws_url:
            raise ProviderError("UNUSUAL_WHALES_TOKEN and MIT_UW_WS_URL are required")
        self.settings = settings
        self._cache: dict[str, list[OptionFlow]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def get_option_flow(self, symbol: str, *, limit: int = 100) -> list[OptionFlow]:
        symbol = symbol.upper()
        async with self._lock:
            if symbol not in self._tasks or self._tasks[symbol].done():
                self._tasks[symbol] = asyncio.create_task(self._listen(symbol))
        return self._cache.get(symbol, [])[:limit]

    async def _listen(self, symbol: str) -> None:
        topics_json = json.dumps(self.settings.uw_topics)
        auth = self.settings.uw_auth_message_json.format(
            token=self.settings.unusual_whales_token,
            symbol=symbol,
            topics=topics_json,
        )
        subscribe = self.settings.uw_subscribe_message_json.format(
            token=self.settings.unusual_whales_token,
            symbol=symbol,
            topics=topics_json,
        )
        try:
            async with websockets.connect(self.settings.uw_ws_url, ping_interval=20) as socket:
                await socket.send(auth)
                await socket.send(subscribe)
                async for raw in socket:
                    payload = json.loads(raw)
                    for row in _records(payload):
                        event = _normalize_flow(symbol, row)
                        if event:
                            current = self._cache.setdefault(symbol, [])
                            current.insert(0, event)
                            del current[300:]
        except asyncio.CancelledError:
            raise
        except Exception:
            # Orchestrator exposes provider health and can fall back per capability.
            return

    async def close(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or payload.get("payload") or payload.get("events") or payload
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return [data] if isinstance(data, dict) else []


def _normalize_flow(symbol: str, row: dict[str, Any]) -> OptionFlow | None:
    option_symbol = str(row.get("option_symbol") or row.get("contract") or row.get("ticker") or "")
    if not option_symbol and not row.get("premium"):
        return None
    sentiment = str(row.get("sentiment") or row.get("bias") or "neutral").lower()
    side = str(row.get("side") or row.get("trade_side") or "unknown").lower()
    option_type = str(row.get("option_type") or row.get("put_call") or "").lower() or None
    expiration = row.get("expiration") or row.get("expiry")
    tags = row.get("tags") or row.get("flags") or []
    if isinstance(tags, str):
        tags = [tags]
    return OptionFlow(
        timestamp=_dt(row.get("timestamp") or row.get("time")),
        symbol=str(row.get("underlying_symbol") or row.get("underlying") or symbol).upper(),
        option_symbol=option_symbol,
        side=side,
        sentiment=sentiment,
        premium=_number(row.get("premium") or row.get("total_premium")),
        size=_number(row.get("size") or row.get("volume") or row.get("contracts")),
        price=_number(row.get("price") or row.get("trade_price")),
        strike=_optional_number(row.get("strike")),
        expiration=date.fromisoformat(str(expiration)[:10]) if expiration else None,
        option_type=option_type,
        tags=[str(x) for x in tags],
    )


def _dt(value: Any) -> datetime:
    if not value:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
