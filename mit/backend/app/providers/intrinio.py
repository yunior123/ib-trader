from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.domain import Bar, OptionContract, Quote
from backend.app.providers.base import MarketDataProvider, OptionsDataProvider, ProviderError, register


@register("intrinio")
class IntrinioProvider(MarketDataProvider, OptionsDataProvider):
    name = "intrinio"
    __capabilities__: set[str] = {"market", "options"}

    def __init__(self, settings: Settings) -> None:
        if not settings.intrinio_api_key:
            raise ProviderError("INTRINIO_API_KEY is required")
        self.settings = settings
        self.client = httpx.AsyncClient(base_url=settings.intrinio_base_url, timeout=20)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        query["api_key"] = self.settings.intrinio_api_key
        response = await self.client.get(path, params=query)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # The request URL contains api_key; exposing the native httpx exception leaks it.
            raise ProviderError(f"Intrinio HTTP {response.status_code} for {path}") from exc
        return response.json()

    async def get_quote(self, symbol: str) -> Quote:
        payload = await self._get(
            f"/securities/{symbol.upper()}/prices/realtime",
            {"source": self.settings.intrinio_quote_source},
        )
        bid = float(payload.get("bid_price") or payload.get("bid") or 0)
        ask = float(payload.get("ask_price") or payload.get("ask") or 0)
        last = float(payload.get("last_price") or payload.get("last") or payload.get("price") or 0)
        return Quote(
            symbol=symbol.upper(),
            timestamp=_parse_dt(payload.get("last_time") or payload.get("timestamp")),
            # NO fabricar bid/ask desde last: un bid≈last da un spread falsamente estrecho que
            # pasaria el gate. Si faltan, quedan 0 -> el puente rechaza el NBBO fail-loud.
            bid=bid,
            ask=ask,
            last=last or (bid + ask) / 2,
            bid_size=float(payload.get("bid_size") or 0),
            ask_size=float(payload.get("ask_size") or 0),
            change_pct=float(payload.get("percent_change") or 0) * (100 if abs(float(payload.get("percent_change") or 0)) < 1 else 1),
        )

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        # /prices/intervals is the modern endpoint (the old /prices/intraday returns 400
        # "no longer supported", measured 2026-08-01). interval_size takes "1m","5m","1h".
        # Response: {"intervals":[{time,open,high,low,close,volume,...}], "next_page":...}
        # newest-first; paginate via next_page until we have `limit` bars.
        result: list[Bar] = []
        next_page: str | None = None
        for _ in range(20):  # hard cap on pages to bound a warmup pull
            params: dict[str, Any] = {
                "source": self.settings.intrinio_interval_source,
                "interval_size": interval,
                "page_size": min(max(limit, 100), 1000),  # /intervals caps at 1000 (10000 -> 400)
            }
            if next_page:
                params["next_page"] = next_page
            payload = await self._get(f"/securities/{symbol.upper()}/prices/intervals", params)
            records = payload.get("intervals") or payload.get("data") or []
            for row in records:
                try:
                    ts = _parse_dt(row.get("time") or row.get("timestamp"))
                except ProviderError:
                    continue  # fila sin timestamp: se salta (no se fabrica), el resto sigue
                result.append(
                    Bar(
                        timestamp=ts,
                        open=float(row.get("open") or 0),
                        high=float(row.get("high") or 0),
                        low=float(row.get("low") or 0),
                        close=float(row.get("close") or 0),
                        # cboe_one_delayed da volume=0 SIEMPRE en acciones pero si da
                        # trade_count (medido 2026-08-05: 550/752/959 por minuto en QQQ). Se usa
                        # como PROXY DECLARADO (provider_status.volume_source): un 0 afirmaria
                        # "no hubo actividad" y mata whale-detector, VWAP y perfil de volumen.
                        volume=float(row.get("volume") or row.get("trade_count") or 0),
                    )
                )
            next_page = payload.get("next_page")
            if not next_page or len(result) >= limit:
                break
        if not result:
            raise ProviderError("Intrinio returned no interval bars; verify entitlement and source")
        result.sort(key=lambda b: b.timestamp)  # endpoint is newest-first; fleet needs ascending
        return result[-limit:]


    async def get_daily_bars(self, symbol: str, *, limit: int = 756) -> list[Bar]:
        payload = await self._get(
            f"/securities/{symbol.upper()}/prices",
            {"page_size": min(limit, 10000), "frequency": "daily"},
        )
        records = payload.get("stock_prices") or payload.get("prices") or payload.get("data") or []
        result: list[Bar] = []
        for item in reversed(records):
            row = item.get("price") or item
            result.append(Bar(
                timestamp=_parse_dt(row.get("date") or row.get("timestamp")),
                open=float(row.get("open") or row.get("open_price") or 0),
                high=float(row.get("high") or row.get("high_price") or 0),
                low=float(row.get("low") or row.get("low_price") or 0),
                close=float(row.get("close") or row.get("close_price") or 0),
                volume=float(row.get("volume") or 0),
            ))
        if not result:
            raise ProviderError("Intrinio returned no daily bars")
        return result[-limit:]

    async def get_option_chain(
        self, symbol: str, *, expiration: datetime | None = None
    ) -> list[OptionContract]:
        expiry = expiration.date() if expiration else await self._nearest_expiration(symbol)
        payload = await self._get(
            f"/options/chain/{symbol.upper()}/{expiry.isoformat()}/realtime",
            {"source": self.settings.intrinio_options_source, "page_size": 10000},
        )
        records = payload.get("chain") or payload.get("options") or payload.get("data") or []
        output: list[OptionContract] = []
        for item in records:
            contract = item.get("option") or item.get("contract") or item
            quote = item.get("price") or item.get("quote") or item
            stats = item.get("stats") or item.get("greeks") or item
            option_type = str(
                contract.get("type") or contract.get("option_type") or contract.get("put_call") or ""
            ).lower()
            if option_type in {"c", "call"}:
                option_type = "call"
            elif option_type in {"p", "put"}:
                option_type = "put"
            else:
                continue
            output.append(
                OptionContract(
                    symbol=symbol.upper(),
                    expiration=_parse_date(contract.get("expiration") or expiry),
                    strike=float(contract.get("strike") or contract.get("strike_price") or 0),
                    option_type=option_type,
                    bid=float(quote.get("bid") or quote.get("bid_price") or 0),
                    ask=float(quote.get("ask") or quote.get("ask_price") or 0),
                    last=float(quote.get("last") or quote.get("last_price") or 0),
                    volume=float(quote.get("volume") or item.get("volume") or 0),
                    open_interest=float(item.get("open_interest") or stats.get("open_interest") or 0),
                    implied_volatility=_float_or_none(stats.get("implied_volatility") or stats.get("iv")),
                    delta=_float_or_none(stats.get("delta")),
                    gamma=_float_or_none(stats.get("gamma")),
                    vega=_float_or_none(stats.get("vega")),
                    theta=_float_or_none(stats.get("theta")),
                )
            )
        return output

    async def _nearest_expiration(self, symbol: str) -> date:
        payload = await self._get(f"/options/expirations/{symbol.upper()}")
        values = payload.get("expirations") or payload.get("data") or []
        dates = sorted(_parse_date(value) for value in values)
        today = date.today()
        return next((value for value in dates if value >= today), dates[-1])

    async def close(self) -> None:
        await self.client.aclose()


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:  # NO fabricar now(): un timestamp ausente reportado como "ahora" miente sobre latencia
        raise ProviderError("timestamp ausente en la respuesta de Intrinio")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
