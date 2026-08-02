from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, timedelta
from statistics import NormalDist

from backend.app.domain import Bar, BookLevel, OptionContract, OptionFlow, OrderBook, Quote
from backend.app.providers.base import (
    DepthDataProvider,
    FlowDataProvider,
    MarketDataProvider,
    OptionsDataProvider,
)

_BASE = {
    "SPY": 640.0,
    "QQQ": 570.0,
    "IWM": 245.0,
    "TSLA": 385.0,
    "MSTR": 375.0,
    "NVDA": 185.0,
    "AAPL": 245.0,
    "VIX": 19.0,
}


class MockProvider(MarketDataProvider, OptionsDataProvider, DepthDataProvider, FlowDataProvider):
    name = "mock"

    def __init__(self) -> None:
        self._cache: dict[str, list[Bar]] = {}

    @staticmethod
    def _seed(symbol: str) -> int:
        today = datetime.now(UTC).date().toordinal()
        return sum((i + 1) * ord(ch) for i, ch in enumerate(symbol.upper())) + today

    def _bars(self, symbol: str, limit: int = 1200) -> list[Bar]:
        symbol = symbol.upper()
        existing = self._cache.get(symbol)
        if existing and len(existing) >= limit:
            return existing[-limit:]

        rng = random.Random(self._seed(symbol))
        base = _BASE.get(symbol, 100.0)
        vol = 0.0025 if symbol not in {"TSLA", "MSTR", "VIX"} else 0.0065
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        now -= timedelta(minutes=now.minute % 5)
        start = now - timedelta(minutes=5 * limit)
        price = base * (0.96 + rng.random() * 0.08)
        result: list[Bar] = []
        phase = rng.random() * math.tau

        for i in range(limit):
            ts = start + timedelta(minutes=5 * i)
            cycle = math.sin(i / 38 + phase) * vol * 0.22
            drift = math.sin(i / 220 + phase / 2) * vol * 0.06
            shock = rng.gauss(0, vol)
            ret = drift + cycle + shock
            open_ = price
            close = max(0.5, open_ * math.exp(ret))
            wick = abs(rng.gauss(vol * 0.65, vol * 0.25))
            high = max(open_, close) * (1 + wick)
            low = min(open_, close) * (1 - wick)
            volume = max(100, rng.lognormvariate(10.8, 0.75))
            result.append(
                Bar(
                    timestamp=ts,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )
            price = close
        self._cache[symbol] = result
        return result

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        bars = self._bars(symbol, max(limit, 1200))
        if interval == "5m":
            return bars[-limit:]
        multiplier = {"15m": 3, "30m": 6, "1h": 12, "4h": 48}.get(interval, 1)
        output: list[Bar] = []
        for i in range(0, len(bars), multiplier):
            group = bars[i : i + multiplier]
            if not group:
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
        return output[-limit:]


    async def get_daily_bars(self, symbol: str, *, limit: int = 756) -> list[Bar]:
        symbol = symbol.upper()
        rng = random.Random(self._seed(symbol) - 999)
        base = _BASE.get(symbol, 100.0)
        vol = 0.012 if symbol not in {"TSLA", "MSTR", "VIX"} else 0.035
        now = datetime.now(UTC).replace(hour=21, minute=0, second=0, microsecond=0)
        price = base * (0.72 + rng.random() * 0.35)
        result: list[Bar] = []
        day = now - timedelta(days=int(limit * 1.55))
        while len(result) < limit:
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            # Insert occasional large shocks so the alert/reversion calibration has examples.
            shock = rng.gauss(0, vol)
            if rng.random() < 0.012:
                shock += rng.choice([-1, 1]) * rng.uniform(0.10, 0.18)
            open_ = price * math.exp(rng.gauss(0, vol * 0.25))
            close = max(0.5, open_ * math.exp(shock))
            wick = abs(rng.gauss(vol * 0.8, vol * 0.25))
            result.append(Bar(timestamp=day, open=open_, high=max(open_, close)*(1+wick), low=min(open_, close)*(1-wick), close=close, volume=max(1000, rng.lognormvariate(14, .6))))
            price = close
        return result[-limit:]

    async def get_quote(self, symbol: str) -> Quote:
        bars = self._bars(symbol)
        last = bars[-1].close
        previous = bars[-79].close if len(bars) > 79 else bars[0].close
        spread = max(0.01, last * (0.00008 if symbol.upper() not in {"MSTR", "TSLA"} else 0.0002))
        rng = random.Random(self._seed(symbol) + 44)
        return Quote(
            symbol=symbol.upper(),
            timestamp=datetime.now(UTC),
            bid=last - spread / 2,
            ask=last + spread / 2,
            last=last,
            bid_size=rng.randint(100, 2500),
            ask_size=rng.randint(100, 2500),
            change_pct=(last / previous - 1) * 100,
        )

    async def get_order_book(self, symbol: str, *, depth: int = 10) -> OrderBook:
        quote = await self.get_quote(symbol)
        tick = max(0.01, quote.last * 0.00005)
        rng = random.Random(self._seed(symbol) + 99)
        bids: list[BookLevel] = []
        asks: list[BookLevel] = []
        bid_wall_index = rng.randrange(2, min(depth, 8))
        ask_wall_index = rng.randrange(2, min(depth, 8))
        for i in range(depth):
            base_size = rng.randint(100, 1800)
            bids.append(
                BookLevel(
                    price=round(quote.bid - i * tick, 4),
                    size=base_size * (6 if i == bid_wall_index else 1),
                    orders=rng.randint(1, 25),
                )
            )
            base_size = rng.randint(100, 1800)
            asks.append(
                BookLevel(
                    price=round(quote.ask + i * tick, 4),
                    size=base_size * (6 if i == ask_wall_index else 1),
                    orders=rng.randint(1, 25),
                )
            )
        return OrderBook(symbol=symbol.upper(), timestamp=datetime.now(UTC), bids=bids, asks=asks)

    @staticmethod
    def _bs_greeks(spot: float, strike: float, days: int, iv: float, is_call: bool) -> tuple[float, float]:
        t = max(days / 365, 1 / 365)
        sigma = max(iv, 0.05)
        d1 = (math.log(spot / strike) + (0.045 + sigma * sigma / 2) * t) / (sigma * math.sqrt(t))
        normal = NormalDist()
        delta = normal.cdf(d1) if is_call else normal.cdf(d1) - 1
        gamma = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (spot * sigma * math.sqrt(t))
        return delta, gamma

    async def get_option_chain(
        self, symbol: str, *, expiration: datetime | None = None
    ) -> list[OptionContract]:
        quote = await self.get_quote(symbol)
        spot = quote.last
        rng = random.Random(self._seed(symbol) + 188)
        expirations = [7, 14, 30, 60]
        chain: list[OptionContract] = []
        step = max(1, round(spot * 0.0125 / 5) * 5)
        center = round(spot / step) * step
        for days in expirations:
            expiry = date.today() + timedelta(days=days)
            for offset in range(-14, 15):
                strike = max(step, center + offset * step)
                moneyness = abs(strike / spot - 1)
                iv = (0.22 if symbol.upper() not in {"TSLA", "MSTR"} else 0.58) + moneyness * 1.3
                for kind in ("call", "put"):
                    delta, gamma = self._bs_greeks(spot, strike, days, iv, kind == "call")
                    oi_curve = math.exp(-((strike - spot) / (spot * 0.12)) ** 2)
                    wall_boost = 6 if offset in ({5, 8} if kind == "call" else {-5, -8}) else 1
                    oi = max(10, int((300 + rng.random() * 4500) * oi_curve * wall_boost))
                    volume = max(0, int(oi * rng.uniform(0.03, 0.8)))
                    intrinsic = max(0.0, spot - strike) if kind == "call" else max(0.0, strike - spot)
                    time_value = spot * iv * math.sqrt(days / 365) * 0.22 * math.exp(-moneyness * 7)
                    mid = max(0.01, intrinsic + time_value)
                    spread = max(0.02, mid * 0.04)
                    chain.append(
                        OptionContract(
                            symbol=symbol.upper(),
                            expiration=expiry,
                            strike=strike,
                            option_type=kind,
                            bid=max(0.0, mid - spread / 2),
                            ask=mid + spread / 2,
                            last=mid,
                            volume=volume,
                            open_interest=oi,
                            implied_volatility=iv,
                            delta=delta,
                            gamma=gamma,
                            vega=spot * 0.01 * math.sqrt(days / 365),
                            theta=-mid / max(days, 1),
                        )
                    )
        return chain

    async def get_option_flow(self, symbol: str, *, limit: int = 100) -> list[OptionFlow]:
        quote = await self.get_quote(symbol)
        rng = random.Random(self._seed(symbol) + 211)
        output: list[OptionFlow] = []
        for i in range(min(limit, 35)):
            bullish = rng.random() > 0.47
            kind = "call" if bullish else "put"
            strike = round(quote.last * (1 + rng.uniform(-0.12, 0.12)), 1)
            size = rng.randint(10, 1800)
            price = rng.uniform(0.15, max(0.2, quote.last * 0.025))
            tags = []
            if size * price * 100 > 250_000:
                tags.append("sweep")
            if rng.random() > 0.8:
                tags.append("ask-side")
            output.append(
                OptionFlow(
                    timestamp=datetime.now(UTC) - timedelta(seconds=i * rng.randint(8, 45)),
                    symbol=symbol.upper(),
                    option_symbol=f"{symbol.upper()}-{kind[0].upper()}-{strike}",
                    side="ask" if bullish else "bid",
                    sentiment="bullish" if bullish else "bearish",
                    premium=size * price * 100,
                    size=size,
                    price=price,
                    strike=strike,
                    expiration=date.today() + timedelta(days=rng.choice([7, 14, 30, 60])),
                    option_type=kind,
                    tags=tags,
                )
            )
        return sorted(output, key=lambda x: x.timestamp, reverse=True)
