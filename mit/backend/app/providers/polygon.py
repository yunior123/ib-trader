from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.domain import Bar, OptionContract, Quote
from backend.app.providers.base import MarketDataProvider, OptionsDataProvider, ProviderError, register


@register("polygon")
class PolygonProvider(MarketDataProvider, OptionsDataProvider):
    """Options chain (measured greeks/IV/OI via /v3/snapshot/options) + daily aggregates.

    Polygon options snapshot carries REAL greeks/IV/OI (not reconstructed). It is delayed
    (~15min) — provenance is the caller's responsibility to stamp honestly.
    """

    name = "polygon"

    def __init__(self, settings: Settings) -> None:
        if not settings.polygon_api_key:
            raise ProviderError("POLYGON_KEY is required")
        self.settings = settings
        self.client = httpx.AsyncClient(base_url=settings.polygon_base_url, timeout=30)

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        query["apiKey"] = self.settings.polygon_api_key
        response = await self.client.get(url, params=query)
        response.raise_for_status()
        return response.json()

    async def get_option_chain(
        self, symbol: str, *, expiration: datetime | None = None
    ) -> list[OptionContract]:
        url: str | None = f"/v3/snapshot/options/{symbol.upper()}"
        params: dict[str, Any] = {"limit": 250}
        if expiration is not None:
            params["expiration_date"] = expiration.date().isoformat()
        output: list[OptionContract] = []
        for _ in range(40):  # bound pagination for a full chain
            payload = await self._get(url, params if url.startswith("/v3/snapshot") else None)
            for item in payload.get("results") or []:
                det = item.get("details") or {}
                greeks = item.get("greeks") or {}
                oi = item.get("open_interest")
                day = item.get("day") or {}
                lq = item.get("last_quote") or {}
                ctype = str(det.get("contract_type") or "").lower()
                if ctype not in {"call", "put"}:
                    continue
                iv = item.get("implied_volatility")
                output.append(
                    OptionContract(
                        symbol=symbol.upper(),
                        expiration=_parse_date(det.get("expiration_date")),
                        strike=float(det.get("strike_price") or 0),
                        option_type=ctype,
                        bid=float(lq.get("bid") or 0),
                        ask=float(lq.get("ask") or 0),
                        last=float(day.get("close") or 0),
                        volume=float(day.get("volume") or 0),
                        open_interest=float(oi or 0),
                        implied_volatility=(float(iv) if iv else None),
                        delta=_f(greeks.get("delta")),
                        gamma=_f(greeks.get("gamma")),
                        vega=_f(greeks.get("vega")),
                        theta=_f(greeks.get("theta")),
                    )
                )
            nxt = payload.get("next_url")
            if not nxt:
                break
            url, params = nxt.replace(str(self.client.base_url), ""), {}
        if not output:
            raise ProviderError(f"Polygon returned no option contracts for {symbol}")
        return output

    async def get_quote(self, symbol: str) -> Quote:
        payload = await self._get(f"/v2/last/nbbo/{symbol.upper()}")
        res = payload.get("results") or {}
        # Polygon /v2/last/nbbo: p=bid price, P=ask price, s=bid size, S=ask size.
        bid = float(res.get("p") or 0)
        ask = float(res.get("P") or 0)
        ts = res.get("t")
        if not ts:  # sin timestamp no se fabrica now() (mentiria sobre latencia)
            raise ProviderError(f"Polygon nbbo sin timestamp para {symbol}")
        return Quote(
            symbol=symbol.upper(),
            timestamp=datetime.fromtimestamp(ts / 1e9, UTC),
            bid=bid,
            ask=ask,
            last=(bid + ask) / 2 if bid and ask else (bid or ask),
            bid_size=float(res.get("s") or 0),
            ask_size=float(res.get("S") or 0),
        )

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        mult, span = _interval_to_polygon(interval)
        end = date.today()
        start = end.fromordinal(end.toordinal() - max(5, limit // 300 + 3))
        payload = await self._get(
            f"/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        rows = payload.get("results") or []
        result = [
            Bar(
                timestamp=datetime.fromtimestamp(r["t"] / 1000, UTC),
                open=float(r.get("o") or 0),
                high=float(r.get("h") or 0),
                low=float(r.get("l") or 0),
                close=float(r.get("c") or 0),
                volume=float(r.get("v") or 0),
            )
            for r in rows
        ]
        if not result:
            raise ProviderError(f"Polygon returned no bars for {symbol}")
        return result[-limit:]

    async def close(self) -> None:
        await self.client.aclose()


def _interval_to_polygon(interval: str) -> tuple[int, str]:
    if interval.endswith("m"):
        return int(interval[:-1] or 1), "minute"
    if interval.endswith("h"):
        return int(interval[:-1] or 1), "hour"
    if interval in {"1d", "d", "1day"}:
        return 1, "day"
    return 5, "minute"


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _f(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
