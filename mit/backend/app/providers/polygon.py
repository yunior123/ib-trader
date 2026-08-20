from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

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
    __capabilities__: set[str] = {"market", "options"}

    def __init__(self, settings: Settings) -> None:
        if not settings.polygon_api_key:
            raise ProviderError("POLYGON_KEY is required")
        self.settings = settings
        self.client = httpx.AsyncClient(base_url=settings.polygon_base_url, timeout=30)

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # httpx REEMPLAZA la query de la URL si se pasa params= -> el cursor de next_url se
        # perdia y cada "pagina" era la primera otra vez (medido 2026-08-04: MU 120x250
        # contratos duplicados, cadenas sin puts). Fusionar a mano: la query del url MANDA.
        query = dict(params or {})
        query["apiKey"] = self.settings.polygon_api_key
        sep = "&" if "?" in url else "?"
        response = await self.client.get(url + sep + urlencode(query))
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # httpx includes the complete request URL in its exception, including apiKey.
            # Never let provider diagnostics or logs disclose credentials.
            raise ProviderError(
                f"Polygon HTTP {response.status_code} for {url.split('?', 1)[0]}"
            ) from exc
        return response.json()

    async def get_option_chain(
        self, symbol: str, *, expiration: datetime | None = None
    ) -> list[OptionContract]:
        url: str | None = f"/v3/snapshot/options/{symbol.upper()}"
        params: dict[str, Any] = {"limit": 250}
        if expiration is not None:
            params["expiration_date"] = expiration.date().isoformat()
        else:
            # Sin rango el snapshot solo da el vencimiento frontal; el rango pagina a varias
            # expiraciones (mapa de la semana). NUNCA fabricar now(): usa el reloj del sistema.
            today = date.today()
            params["expiration_date.gte"] = today.isoformat()
            params["expiration_date.lte"] = today.fromordinal(
                today.toordinal() + max(1, self.settings.polygon_chain_days)
            ).isoformat()
        output: list[OptionContract] = []
        for _ in range(120):  # bound pagination for a multi-expiry chain
            # Mismo bug que get_expirations: el next_url del cursor pierde el limit y Polygon cae
            # a 10/pagina -> 120 paginas se agotaban en el tramo CALL del expiry frontal y la
            # cadena salia SIN PUTS (medido 2026-08-04: MU 1390C/50P, todo 8/5). Reinyectar limit.
            payload = await self._get(url, params if "cursor" not in url else {"limit": 250})
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

    async def get_expirations(self, symbol: str, *, days: int | None = None) -> list[date]:
        """Vencimientos distintos en la ventana (via /v3/reference/options/contracts, paginado).
        El snapshot se atasca en el frontal; esto lista las fechas para pedir cada cadena aparte."""
        today = date.today()
        lte = today.fromordinal(today.toordinal() + (days or self.settings.polygon_chain_days))
        url: str | None = "/v3/reference/options/contracts"
        # sort=expiration_date es OBLIGATORIO: sin el, la API pagina por TICKER y las 10 paginas se
        # agotan dentro de los primeros vencimientos. Medido 2026-08-02 con SPY a 28 dias: sin sort
        # salian 4 vencimientos (03/04/05/21 ago) y con sort salen 12 — o sea que el mapa de
        # semanas futuras estaba MUDO para casi todo agosto.
        params: dict[str, Any] = {
            "underlying_ticker": symbol.upper(), "expired": "false", "limit": 1000,
            "expiration_date.gte": today.isoformat(), "expiration_date.lte": lte.isoformat(),
            "sort": "expiration_date", "order": "asc",
        }
        exps: set[date] = set()
        for _ in range(10):
            # El next_url del cursor NO conserva el limit y Polygon cae a 10 por pagina: medido
            # 2026-08-02 -> pagina 1 = 1000 resultados, paginas 2..10 = 10 cada una (1090 en total),
            # o sea 4 vencimientos de los 12 que hay en agosto. Se reinyecta el limit en cada salto.
            payload = await self._get(url, params if "cursor" not in url else {"limit": 1000})
            for r in payload.get("results") or []:
                e = r.get("expiration_date")
                if e:
                    exps.add(_parse_date(e))
            nxt = payload.get("next_url")
            if not nxt:
                break
            url, params = nxt.replace(str(self.client.base_url), ""), {}
        return sorted(exps)

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
