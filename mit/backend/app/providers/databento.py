from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.app.config import Settings
from backend.app.domain import Bar, BookLevel, OrderBook, Quote
from backend.app.providers.base import DepthDataProvider, MarketDataProvider, ProviderError, register
from backend.app.providers.databento_live import DatabentoLiveHub


@register("databento")
class DatabentoProvider(MarketDataProvider, DepthDataProvider):
    """Databento adapter.

    Historical calls are used for a self-contained reference implementation. For production,
    keep one db.Live client per dataset, subscribe once, and update the same caches from callbacks.
    The method names and schemas below match the official Python client.
    """

    name = "databento"

    def __init__(self, settings: Settings) -> None:
        if not settings.databento_api_key:
            raise ProviderError("DATABENTO_API_KEY is required")
        try:
            import databento as db  # type: ignore
        except ImportError as exc:
            raise ProviderError("Install the databento extra: pip install -e '.[databento]'") from exc
        self.db = db
        self.settings = settings
        self.historical = db.Historical(settings.databento_api_key)
        self.live = DatabentoLiveHub(db, settings) if settings.databento_use_live else None

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        if self.live and interval in {"1m", "5m"}:
            self.live.ensure_bars(symbol)
        schema = {"1m": "ohlcv-1m", "5m": "ohlcv-1m", "1h": "ohlcv-1h"}.get(interval, "ohlcv-1m")
        minutes = 1 if schema == "ohlcv-1m" else 60
        span = max(limit * (5 if interval == "5m" else minutes) * 3, 60 * 24 * 5)
        end = datetime.now(UTC)
        start = end - timedelta(minutes=span)

        store = await asyncio.to_thread(
            self.historical.timeseries.get_range,
            dataset=self.settings.databento_market_dataset,
            schema=schema,
            symbols=[symbol.upper()],
            stype_in="raw_symbol",
            start=start,
            end=end,
        )
        frame = await asyncio.to_thread(store.to_df)
        if frame.empty:
            raise ProviderError(f"Databento returned no bars for {symbol}")
        frame = frame.reset_index()
        time_col = next((c for c in ("ts_event", "index", "timestamp") if c in frame.columns), frame.columns[0])
        records: list[Bar] = []
        for _, row in frame.iterrows():
            records.append(
                Bar(
                    timestamp=_as_datetime(row[time_col]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                )
            )
        records.sort(key=lambda x: x.timestamp)
        if self.live and interval in {"1m", "5m"}:
            live_records = self.live.bars(symbol)
            if live_records:
                merged = {bar.timestamp: bar for bar in records}
                merged.update({bar.timestamp: bar for bar in live_records})
                records = sorted(merged.values(), key=lambda bar: bar.timestamp)
        if interval == "5m" and schema == "ohlcv-1m":
            records = _aggregate(records, 5)
        return records[-limit:]


    async def get_daily_bars(self, symbol: str, *, limit: int = 756) -> list[Bar]:
        end = datetime.now(UTC)
        start = end - timedelta(days=int(limit * 1.7))
        store = await asyncio.to_thread(
            self.historical.timeseries.get_range,
            dataset=self.settings.databento_market_dataset,
            schema="ohlcv-1d",
            symbols=[symbol.upper()],
            stype_in="raw_symbol",
            start=start,
            end=end,
        )
        frame = await asyncio.to_thread(store.to_df)
        if frame.empty:
            raise ProviderError(f"Databento returned no daily bars for {symbol}")
        frame = frame.reset_index()
        time_col = next((c for c in ("ts_event", "index", "timestamp") if c in frame.columns), frame.columns[0])
        result = [Bar(timestamp=_as_datetime(row[time_col]), open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]), volume=float(row.get("volume", 0))) for _, row in frame.iterrows()]
        result.sort(key=lambda x: x.timestamp)
        return result[-limit:]

    async def get_quote(self, symbol: str) -> Quote:
        if self.live:
            self.live.ensure_quote(symbol)
            await asyncio.sleep(self.settings.databento_live_warmup_seconds)
            cached = self.live.quote(symbol)
            if cached:
                return cached
        end = datetime.now(UTC)
        store = await asyncio.to_thread(
            self.historical.timeseries.get_range,
            dataset=self.settings.databento_market_dataset,
            schema="mbp-1",
            symbols=[symbol.upper()],
            stype_in="raw_symbol",
            start=end - timedelta(minutes=15),
            end=end,
        )
        frame = await asyncio.to_thread(store.to_df)
        if frame.empty:
            raise ProviderError(f"Databento returned no quote for {symbol}")
        row = frame.reset_index().iloc[-1]
        bid = _scaled(row.get("bid_px_00", row.get("bid_px", 0)))
        ask = _scaled(row.get("ask_px_00", row.get("ask_px", 0)))
        last = _scaled(row.get("price", 0)) or (bid + ask) / 2
        return Quote(
            symbol=symbol.upper(),
            timestamp=_as_datetime(row.get("ts_event", datetime.now(UTC))),
            bid=bid,
            ask=ask,
            last=last,
            bid_size=float(row.get("bid_sz_00", row.get("bid_size", 0))),
            ask_size=float(row.get("ask_sz_00", row.get("ask_size", 0))),
        )

    async def get_order_book(self, symbol: str, *, depth: int = 10) -> OrderBook:
        if self.live:
            self.live.ensure_depth(symbol)
            await asyncio.sleep(self.settings.databento_live_warmup_seconds)
            cached = self.live.book(symbol)
            if cached:
                return OrderBook(symbol=cached.symbol, timestamp=cached.timestamp, bids=cached.bids[:depth], asks=cached.asks[:depth])
        end = datetime.now(UTC)
        store = await asyncio.to_thread(
            self.historical.timeseries.get_range,
            dataset=self.settings.databento_depth_dataset,
            schema=self.settings.databento_depth_schema,
            symbols=[symbol.upper()],
            stype_in="raw_symbol",
            start=end - timedelta(minutes=10),
            end=end,
        )
        frame = await asyncio.to_thread(store.to_df)
        if frame.empty:
            raise ProviderError(f"Databento returned no depth for {symbol}; verify dataset entitlement")
        row = frame.reset_index().iloc[-1]
        bids: list[BookLevel] = []
        asks: list[BookLevel] = []
        for i in range(depth):
            suffix = f"{i:02d}"
            bp = _scaled(row.get(f"bid_px_{suffix}", 0))
            ap = _scaled(row.get(f"ask_px_{suffix}", 0))
            if bp:
                bids.append(
                    BookLevel(
                        price=bp,
                        size=float(row.get(f"bid_sz_{suffix}", 0)),
                        orders=_int_or_none(row.get(f"bid_ct_{suffix}")),
                    )
                )
            if ap:
                asks.append(
                    BookLevel(
                        price=ap,
                        size=float(row.get(f"ask_sz_{suffix}", 0)),
                        orders=_int_or_none(row.get(f"ask_ct_{suffix}")),
                    )
                )
        return OrderBook(
            symbol=symbol.upper(),
            timestamp=_as_datetime(row.get("ts_event", datetime.now(UTC))),
            bids=bids,
            asks=asks,
        )

    async def close(self) -> None:
        if self.live:
            await asyncio.to_thread(self.live.close)


def _aggregate(values: list[Bar], size: int) -> list[Bar]:
    output: list[Bar] = []
    for i in range(0, len(values), size):
        group = values[i : i + size]
        if len(group) != size:
            continue
        output.append(
            Bar(
                timestamp=group[0].timestamp,
                open=group[0].open,
                high=max(x.high for x in group),
                low=min(x.low for x in group),
                close=group[-1].close,
                volume=sum(x.volume for x in group),
            )
        )
    return output


def _scaled(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    # Databento DBN fixed-price fields may be raw nanounits depending on dataframe mode.
    return number / 1e9 if abs(number) > 1e7 else number


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if hasattr(value, "to_pydatetime"):
        result = value.to_pydatetime()
        return result if result.tzinfo else result.replace(tzinfo=UTC)
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
