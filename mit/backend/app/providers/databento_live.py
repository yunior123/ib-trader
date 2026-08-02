from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
import threading
from typing import Any

from backend.app.config import Settings
from backend.app.domain import Bar, BookLevel, OrderBook, Quote


class DatabentoLiveHub:
    """Process-level Databento stream cache.

    One client is opened per symbol/schema on first use. In a larger deployment, replace this
    with one subscription manager that batches symbols and publishes normalized events through
    Redis/NATS/Kafka. The callbacks intentionally accept generic record objects so this module
    remains tolerant of DBN message subclasses.
    """

    def __init__(self, db_module: Any, settings: Settings) -> None:
        self.db = db_module
        self.settings = settings
        self._clients: dict[tuple[str, str, str], Any] = {}
        self._threads: dict[tuple[str, str, str], threading.Thread] = {}
        self._quotes: dict[str, Quote] = {}
        self._books: dict[str, OrderBook] = {}
        self._one_minute: dict[str, deque[Bar]] = defaultdict(lambda: deque(maxlen=4000))
        self._lock = threading.RLock()

    def ensure_quote(self, symbol: str) -> None:
        self._ensure(
            symbol=symbol,
            dataset=self.settings.databento_market_dataset,
            schema="mbp-1",
            callback=lambda record: self._on_quote(symbol, record),
        )

    def ensure_bars(self, symbol: str) -> None:
        self._ensure(
            symbol=symbol,
            dataset=self.settings.databento_market_dataset,
            schema="ohlcv-1m",
            callback=lambda record: self._on_bar(symbol, record),
        )

    def ensure_depth(self, symbol: str) -> None:
        self._ensure(
            symbol=symbol,
            dataset=self.settings.databento_depth_dataset,
            schema=self.settings.databento_depth_schema,
            callback=lambda record: self._on_depth(symbol, record),
        )

    def quote(self, symbol: str) -> Quote | None:
        with self._lock:
            return self._quotes.get(symbol.upper())

    def book(self, symbol: str) -> OrderBook | None:
        with self._lock:
            return self._books.get(symbol.upper())

    def bars(self, symbol: str) -> list[Bar]:
        with self._lock:
            return list(self._one_minute.get(symbol.upper(), ()))

    def _ensure(self, *, symbol: str, dataset: str, schema: str, callback: Any) -> None:
        symbol = symbol.upper()
        key = (dataset, schema, symbol)
        with self._lock:
            if key in self._clients:
                return
            client = self.db.Live(key=self.settings.databento_api_key)
            client.subscribe(
                dataset=dataset,
                schema=schema,
                stype_in="raw_symbol",
                symbols=[symbol],
            )
            client.add_callback(callback)
            thread = threading.Thread(target=client.start, name=f"db-{schema}-{symbol}", daemon=True)
            self._clients[key] = client
            self._threads[key] = thread
            thread.start()

    def _on_quote(self, symbol: str, record: Any) -> None:
        levels = getattr(record, "levels", None)
        level = levels[0] if levels else record
        bid = _price(getattr(level, "bid_px", getattr(record, "bid_px_00", 0)))
        ask = _price(getattr(level, "ask_px", getattr(record, "ask_px_00", 0)))
        last = _price(getattr(record, "price", 0)) or (bid + ask) / 2
        if not (bid or ask or last):
            return
        quote = Quote(
            symbol=symbol.upper(),
            timestamp=_timestamp(record),
            bid=bid or last,
            ask=ask or last,
            last=last,
            bid_size=float(getattr(level, "bid_sz", getattr(record, "bid_sz_00", 0))),
            ask_size=float(getattr(level, "ask_sz", getattr(record, "ask_sz_00", 0))),
        )
        with self._lock:
            self._quotes[symbol.upper()] = quote

    def _on_bar(self, symbol: str, record: Any) -> None:
        required = [getattr(record, field, None) for field in ("open", "high", "low", "close")]
        if any(value is None for value in required):
            return
        bar = Bar(
            timestamp=_timestamp(record),
            open=_price(record.open),
            high=_price(record.high),
            low=_price(record.low),
            close=_price(record.close),
            volume=float(getattr(record, "volume", 0)),
        )
        with self._lock:
            values = self._one_minute[symbol.upper()]
            if values and values[-1].timestamp == bar.timestamp:
                values[-1] = bar
            else:
                values.append(bar)

    def _on_depth(self, symbol: str, record: Any) -> None:
        levels = getattr(record, "levels", None)
        if not levels:
            return
        bids: list[BookLevel] = []
        asks: list[BookLevel] = []
        for level in levels:
            bid = _price(getattr(level, "bid_px", 0))
            ask = _price(getattr(level, "ask_px", 0))
            if bid:
                bids.append(
                    BookLevel(
                        price=bid,
                        size=float(getattr(level, "bid_sz", 0)),
                        orders=_optional_int(getattr(level, "bid_ct", None)),
                    )
                )
            if ask:
                asks.append(
                    BookLevel(
                        price=ask,
                        size=float(getattr(level, "ask_sz", 0)),
                        orders=_optional_int(getattr(level, "ask_ct", None)),
                    )
                )
        if bids and asks:
            with self._lock:
                self._books[symbol.upper()] = OrderBook(
                    symbol=symbol.upper(), timestamp=_timestamp(record), bids=bids, asks=asks
                )

    def close(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            stop = getattr(client, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass


def _price(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number / 1e9 if abs(number) > 1e7 else number


def _timestamp(record: Any) -> datetime:
    value = getattr(record, "ts_event", None) or getattr(record, "ts_recv", None)
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        number = int(value)
        return datetime.fromtimestamp(number / 1e9, tz=UTC)
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
