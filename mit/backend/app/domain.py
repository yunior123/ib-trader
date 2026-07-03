from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class Severity(StrEnum):
    INFO = "info"
    WATCH = "watch"
    WARNING = "warning"
    CRITICAL = "critical"


class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class Quote(BaseModel):
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last: float
    bid_size: float = 0
    ask_size: float = 0
    change_pct: float = 0


class BookLevel(BaseModel):
    price: float
    size: float
    orders: int | None = None


class OrderBook(BaseModel):
    symbol: str
    timestamp: datetime
    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)


class OptionContract(BaseModel):
    symbol: str
    expiration: date
    strike: float
    option_type: str
    bid: float = 0
    ask: float = 0
    last: float = 0
    volume: float = 0
    open_interest: float = 0
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None


class OptionFlow(BaseModel):
    timestamp: datetime
    symbol: str
    option_symbol: str
    side: str = "unknown"
    sentiment: str = "neutral"
    premium: float = 0
    size: float = 0
    price: float = 0
    strike: float | None = None
    expiration: date | None = None
    option_type: str | None = None
    tags: list[str] = Field(default_factory=list)


class SignalSnapshot(BaseModel):
    symbol: str
    timestamp: datetime
    bento_state: str
    bento_direction: Direction = Direction.NEUTRAL
    bento_score: float = 0
    trinity_state: str
    trinity_direction: Direction = Direction.NEUTRAL
    trinity_score: float = 0
    router_state: str
    router_direction: Direction = Direction.NEUTRAL
    reversal_score: int = 0
    reasons: list[str] = Field(default_factory=list)


class MagnetLevel(BaseModel):
    label: str
    price: float
    strength: float
    kind: str


class DealerPositioning(BaseModel):
    symbol: str
    timestamp: datetime
    spot: float
    net_gex: float
    net_dex: float
    gamma_regime: str
    gamma_flip: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    max_pain: float | None = None
    expected_move: float | None = None
    magnets: list[MagnetLevel] = Field(default_factory=list)
    gex_by_strike: dict[str, float] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)


class BookAnalytics(BaseModel):
    symbol: str
    timestamp: datetime
    spread: float = 0
    microprice: float | None = None
    imbalance: float = 0
    bid_wall: float | None = None
    ask_wall: float | None = None
    bid_wall_size: float = 0
    ask_wall_size: float = 0


class ShockState(BaseModel):
    symbol: str
    timestamp: datetime
    change_pct: float
    zscore: float | None = None
    severity: Severity = Severity.INFO
    direction: Direction = Direction.NEUTRAL
    label: str = "normal"
    historical_reversion_probability: float | None = None
    sample_size: int = 0
    horizon_days: int = 2
    note: str = ""


class WeeklyDay(BaseModel):
    day: str
    date: date
    close: float | None = None
    change_pct: float | None = None
    shock: bool = False
    direction: Direction = Direction.NEUTRAL
    status: str = "pending"


class WeeklyRow(BaseModel):
    symbol: str
    days: list[WeeklyDay]


class AlertEvent(BaseModel):
    id: str
    timestamp: datetime
    symbol: str
    severity: Severity
    title: str
    message: str
    category: str


class ProviderStatus(BaseModel):
    capability: str
    provider: str
    connected: bool
    latency_ms: float | None = None
    message: str = ""


class TerminalSnapshot(BaseModel):
    symbol: str
    generated_at: datetime
    quote: Quote
    bars: list[Bar]
    signals: SignalSnapshot
    dealer: DealerPositioning
    book: BookAnalytics
    shock: ShockState
    weekly: list[WeeklyRow]
    flows: list[OptionFlow]
    alerts: list[AlertEvent]
    provider_status: list[ProviderStatus]
    metadata: dict[str, Any] = Field(default_factory=dict)
