from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime
from typing import Awaitable, Callable, TypeVar

from backend.app.analytics import (
    analyze_dealer_positioning,
    analyze_order_book,
    analyze_shock,
    analyze_signals,
    build_weekly_rows,
)
from backend.app.analytics.options_positioning import (
    compute_option_matrix,
    compute_trace_matrix,
    read_trace_cube,
)
from backend.app.config import Settings
from backend.app.domain import (
    AlertEvent,
    Bar,
    Direction,
    ProviderStatus,
    Severity,
    TerminalSnapshot,
)
from backend.app.engine.event_bus import EventBus
from backend.app.providers.registry import ProviderSet

_log = logging.getLogger("mit.orchestrator")


def _prob_txt(prob, n):
    """'0%' MEDIDO y 'no hay muestra' son cosas distintas: `or 0` las hacia indistinguibles.
    Un 0% con n=1 leido como probabilidad medida es exactamente el cero plausible de la casa."""
    if prob is None:
        return f"not measured (n={n})"
    return f"{prob:.0%}"


T = TypeVar("T")


class MarketIntelligenceEngine:
    def __init__(self, settings: Settings, providers: ProviderSet, bus: EventBus) -> None:
        self.settings = settings
        self.providers = providers
        self.bus = bus
        self._bar_cache: dict[str, tuple[float, list[Bar]]] = {}
        self._daily_cache: dict[str, tuple[float, list[Bar]]] = {}
        self._snapshot_cache: dict[str, tuple[float, TerminalSnapshot]] = {}
        self._chain_cache: dict[str, tuple[float, list]] = {}
        self._chain_fetched_at: dict[str, float] = {}
        self._chain_locks: dict[str, asyncio.Lock] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def snapshot(self, symbol: str, *, force: bool = False) -> TerminalSnapshot:
        symbol = symbol.upper()
        cached = self._snapshot_cache.get(symbol)
        if not force and cached and time.monotonic() - cached[0] < self.settings.refresh_seconds:
            return cached[1]
        lock = self._locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            cached = self._snapshot_cache.get(symbol)
            if not force and cached and time.monotonic() - cached[0] < self.settings.refresh_seconds:
                return cached[1]
            result = await self._build_snapshot(symbol)
            self._snapshot_cache[symbol] = (time.monotonic(), result)
            await self.bus.publish(symbol, result.model_dump(mode="json"))
            return result

    async def _build_snapshot(self, symbol: str) -> TerminalSnapshot:
        status: list[ProviderStatus] = []
        bars, daily_bars, quote, chain, book, flows = await asyncio.gather(
            self._with_fallback(
                "market-bars",
                self.providers.market.name,
                lambda: self.providers.market.get_bars(symbol, interval="5m", limit=5000),
                lambda: self.providers.fallback.get_bars(symbol, interval="5m", limit=5000),
                status,
            ),
            self._with_fallback(
                "daily-history",
                self.providers.market.name,
                lambda: self.providers.market.get_daily_bars(symbol, limit=self.settings.reversion_lookback_days),
                lambda: self.providers.fallback.get_daily_bars(symbol, limit=self.settings.reversion_lookback_days),
                status,
            ),
            self._with_fallback(
                "quote",
                self.providers.market.name,
                lambda: self.providers.market.get_quote(symbol),
                lambda: self.providers.fallback.get_quote(symbol),
                status,
            ),
            self._with_fallback(
                "options",
                self.providers.options.name,
                lambda: self.providers.options.get_option_chain(symbol),
                lambda: self.providers.fallback.get_option_chain(symbol),
                status,
            ),
            self._with_fallback(
                "depth",
                self.providers.depth.name,
                lambda: self.providers.depth.get_order_book(symbol, depth=12),
                lambda: self.providers.fallback.get_order_book(symbol, depth=12),
                status,
            ),
            self._with_fallback(
                "flow",
                self.providers.flow.name,
                lambda: self.providers.flow.get_option_flow(symbol, limit=80),
                lambda: self.providers.fallback.get_option_flow(symbol, limit=80),
                status,
            ),
        )
        self._bar_cache[symbol] = (time.monotonic(), bars)
        self._daily_cache[symbol] = (time.monotonic(), daily_bars)

        signals = analyze_signals(symbol, bars)
        dealer = analyze_dealer_positioning(symbol, quote.last, chain)
        book_analytics = analyze_order_book(book)
        shock = analyze_shock(symbol, daily_bars, self.settings)
        weekly = await self._weekly_map(symbol, daily_bars)
        alerts = self._alerts(symbol, quote.last, signals, dealer, book_analytics, shock, flows)
        alerts.extend(self._cross_symbol_shock_alerts(exclude=symbol))

        return TerminalSnapshot(
            symbol=symbol,
            generated_at=datetime.now(UTC),
            quote=quote,
            bars=bars[-600:],
            signals=signals,
            dealer=dealer,
            book=book_analytics,
            shock=shock,
            weekly=weekly,
            flows=flows[:50],
            alerts=alerts,
            provider_status=status,
            metadata={
                "mode": self.settings.mode,
                "refresh_seconds": self.settings.refresh_seconds,
                "disclaimer": "Research/decision-support software, not investment advice or an autonomous trading system.",
            },
        )

    async def gex_heatmap(self, symbol: str, *, metric: str = "gex") -> dict:
        symbol = symbol.upper()
        status: list[ProviderStatus] = []
        quote, chain = await asyncio.gather(
            self._with_fallback(
                "quote",
                self.providers.market.name,
                lambda: self.providers.market.get_quote(symbol),
                lambda: self.providers.fallback.get_quote(symbol),
                status,
            ),
            self._with_fallback(
                "options",
                self.providers.options.name,
                lambda: self._multi_expiry_chain(symbol),
                lambda: self.providers.fallback.get_option_chain(symbol),
                status,
            ),
        )
        matrix = compute_option_matrix(symbol, quote.last, chain, metric=metric)
        matrix["quote"] = {"last": quote.last, "change_pct": quote.change_pct}
        matrix["provider_status"] = [s.model_dump(mode="json") for s in status]
        matrix["generated_at"] = datetime.now(UTC).isoformat()
        matrix["chain_age_s"] = self._chain_age_s(symbol)
        return matrix

    def _chain_age_s(self, symbol: str) -> float | None:
        """Edad de la cadena servida (s), o None si no vino del cache. Se publica para que la
        pantalla no pueda hacer pasar por fresco un mapa de hace 5 min."""
        t = self._chain_fetched_at.get(symbol)
        return None if t is None else round(time.time() - t, 1)

    async def trace_matrix(self, symbol: str, *, metric: str = "gex") -> dict:
        symbol = symbol.upper()
        status: list[ProviderStatus] = []
        quote, chain = await asyncio.gather(
            self._with_fallback(
                "quote",
                self.providers.market.name,
                lambda: self.providers.market.get_quote(symbol),
                lambda: self.providers.fallback.get_quote(symbol),
                status,
            ),
            self._with_fallback(
                "options",
                self.providers.options.name,
                lambda: self._multi_expiry_chain(symbol),
                lambda: self.providers.fallback.get_option_chain(symbol),
                status,
            ),
        )
        matrix = compute_trace_matrix(
            symbol, quote.last, chain, metric=metric, cube=read_trace_cube(symbol)
        )
        bars = await self._bars_for_trace(symbol, status)
        trace_time = matrix.get("trace_time")
        if trace_time:
            # el panel muestra UNA sesion: la del cubo medido. Velas de otro dia fuera.
            epochs = [c["epoch"] for c in trace_time["columns"]]
            lo, hi = min(epochs) - 3600, max(epochs) + 3600
            bars = [b for b in bars if lo <= b.timestamp.timestamp() <= hi]
            matrix["spot_track"] = [
                {"time": c["epoch"], "value": c["spot"]}
                for c in trace_time["columns"]
                if c["spot"] is not None
            ]
        # candles with wicks for the price overlay; empty list if no data (fail-loud, no fabricated bars)
        matrix["candles"] = [
            {"time": int(b.timestamp.timestamp()), "open": b.open, "high": b.high, "low": b.low, "close": b.close}
            for b in bars
        ]
        matrix["price_source"] = (
            "candles" if bars else ("spot_track" if matrix.get("spot_track") else "none")
        )
        matrix["levels"]["last_close"] = bars[-2].close if len(bars) >= 2 else None
        matrix["quote"] = {"last": quote.last, "change_pct": quote.change_pct}
        matrix["provider_status"] = [s.model_dump(mode="json") for s in status]
        matrix["generated_at"] = datetime.now(UTC).isoformat()
        return matrix

    async def _bars_for_trace(self, symbol: str, status: list[ProviderStatus]) -> list[Bar]:
        """5m candles for the trace overlay; degrade to [] on total failure (no fabricated bars)."""
        try:
            return await self._with_fallback(
                "market-bars",
                self.providers.market.name,
                lambda: self.providers.market.get_bars(symbol, interval="5m", limit=120),
                lambda: self.providers.fallback.get_bars(symbol, interval="5m", limit=120),
                status,
            )
        except Exception:
            return []

    async def _multi_expiry_chain(self, symbol: str, *, max_expiries: int = 10):
        """Cadena multi-vencimiento con TTL corto compartido por heatmap y TRACE.

        Sin cache, cada widget rehacia las 10 cadenas: medido 2026-08-02 con SPY -> heatmap
        82,9 s y TRACE 51,1 s, y cada refresco del navegador repetia la factura entera. El TTL
        (MIT_CHAIN_TTL_S, 45 s por defecto) es despreciable frente a los ~15 min de retraso que
        la cadena de Polygon YA declara, asi que no disfraza de fresco nada que no lo fuera.
        """
        ttl = self.settings.chain_cache_ttl_s
        if ttl > 0:
            hit = self._chain_cache.get(symbol)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            lock = self._chain_locks.setdefault(symbol, asyncio.Lock())
            async with lock:   # una sola descarga aunque lleguen heatmap y TRACE a la vez
                hit = self._chain_cache.get(symbol)
                if hit and time.monotonic() - hit[0] < ttl:
                    return hit[1]
                chain = await self._fetch_multi_expiry_chain(symbol, max_expiries=max_expiries)
                self._chain_cache[symbol] = (time.monotonic(), chain)
                self._chain_fetched_at[symbol] = time.time()
                return chain
        return await self._fetch_multi_expiry_chain(symbol, max_expiries=max_expiries)

    async def _fetch_multi_expiry_chain(self, symbol: str, *, max_expiries: int = 10):
        """Si el provider sabe listar vencimientos, pide la cadena de cada uno (los N cercanos)
        y las fusiona; si no, una sola cadena."""
        opt = self.providers.options
        get_exps = getattr(opt, "get_expirations", None)
        if get_exps is None:
            return await opt.get_option_chain(symbol)
        exps = (await get_exps(symbol))[:max_expiries]
        if not exps:
            return await opt.get_option_chain(symbol)

        async def _una(e):
            return await opt.get_option_chain(symbol, expiration=datetime(e.year, e.month, e.day))

        chains = await asyncio.gather(*(_una(e) for e in exps), return_exceptions=True)

        # Un vencimiento que falla desaparecia EN SILENCIO y los muros se calculaban sobre la
        # cadena que sobrevivio: medido el 2026-08-02 con SPY al mismo spot 744.27 -> una corrida
        # daba call_wall 775 / flip 729.98 con 4 vencimientos y la siguiente call_wall 700 /
        # flip 647.68 con 3. Un nivel que parpadea entre refrescos es peor que no tener nivel.
        fallidos = [(e, r) for e, r in zip(exps, chains) if isinstance(r, Exception)]
        if fallidos:
            _log.warning("%s: %d/%d vencimientos fallaron, reintentando: %s", symbol,
                         len(fallidos), len(exps), [str(e) for e, _ in fallidos])
            reintento = await asyncio.gather(*(_una(e) for e, _ in fallidos), return_exceptions=True)
            porexp = dict(zip(exps, chains))
            porexp.update({e: r for (e, _), r in zip(fallidos, reintento)})
            chains = [porexp[e] for e in exps]
            fallidos = [(e, r) for e, r in zip(exps, chains) if isinstance(r, Exception)]

        merged = [c for r in chains if not isinstance(r, Exception) for c in r]
        vivos = len(exps) - len(fallidos)
        if not merged or vivos * 2 < len(exps):
            # Cobertura por debajo de la mitad: el mapa ya no describe el mismo libro. Se levanta
            # para que _with_fallback lo declare (connected=False) en vez de servir un mapa parcial
            # como si fuera completo.
            primera = fallidos[0][1] if fallidos else RuntimeError(f"{symbol}: sin cadena")
            raise primera
        if fallidos:
            _log.error("%s: mapa con %d/%d vencimientos (faltan %s) — muros NO comparables entre "
                       "refrescos", symbol, vivos, len(exps), [str(e) for e, _ in fallidos])
        return merged

    async def _weekly_map(self, current_symbol: str, current_bars: list[Bar]):
        bars_by_symbol = {current_symbol: current_bars}
        tasks: list[tuple[str, asyncio.Task[list[Bar]]]] = []
        for symbol in self.settings.watchlist:
            if symbol == current_symbol:
                continue
            cached = self._daily_cache.get(symbol)
            if cached and time.monotonic() - cached[0] < 60:
                bars_by_symbol[symbol] = cached[1]
            else:
                tasks.append(
                    (
                        symbol,
                        asyncio.create_task(
                            self._daily_with_silent_fallback(symbol, limit=self.settings.reversion_lookback_days)
                        ),
                    )
                )
        for symbol, task in tasks:
            try:
                bars = await task
                bars_by_symbol[symbol] = bars
                self._daily_cache[symbol] = (time.monotonic(), bars)
            except Exception:
                continue
        return build_weekly_rows(bars_by_symbol, self.settings)

    async def _daily_with_silent_fallback(self, symbol: str, limit: int) -> list[Bar]:
        try:
            return await self.providers.market.get_daily_bars(symbol, limit=limit)
        except Exception:
            return await self.providers.fallback.get_daily_bars(symbol, limit=limit)

    async def _with_fallback(
        self,
        capability: str,
        provider_name: str,
        primary: Callable[[], Awaitable[T]],
        fallback: Callable[[], Awaitable[T]],
        status: list[ProviderStatus],
    ) -> T:
        started = time.perf_counter()
        try:
            value = await primary()
            status.append(
                ProviderStatus(
                    capability=capability,
                    provider=provider_name,
                    connected=True,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
            return value
        except Exception as exc:
            value = await fallback()
            status.append(
                ProviderStatus(
                    capability=capability,
                    provider=f"mock fallback ({provider_name})",
                    connected=False,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
            return value

    def _alerts(self, symbol, spot, signals, dealer, book, shock, flows) -> list[AlertEvent]:
        now = datetime.now(UTC)
        alerts: list[AlertEvent] = []

        def add(severity: Severity, title: str, message: str, category: str) -> None:
            raw = f"{symbol}|{title}|{message}|{now:%Y-%m-%d-%H-%M}"
            alerts.append(
                AlertEvent(
                    id=hashlib.sha1(raw.encode()).hexdigest()[:12],
                    timestamp=now,
                    symbol=symbol,
                    severity=severity,
                    title=title,
                    message=message,
                    category=category,
                )
            )

        if shock.severity in {Severity.WARNING, Severity.CRITICAL}:
            add(
                shock.severity,
                f"{shock.label.upper()} — {shock.change_pct:+.2f}%",
                f"Historical opposite-direction move within {shock.horizon_days} sessions: "
                f"{_prob_txt(shock.historical_reversion_probability, shock.sample_size)} across "
                f"{shock.sample_size} comparable events. Not a guarantee.",
                "shock",
            )
        elif shock.severity == Severity.WATCH:
            add(Severity.WATCH, "STATISTICAL SHOCK", f"Move is {shock.zscore:+.2f}σ from recent daily behavior.", "shock")

        if signals.router_state == "REVERSAL CONFIRMED":
            add(
                Severity.WARNING,
                "REVERSAL CONFIRMED",
                f"Combined router: {signals.reversal_score}/6 factors point {signals.router_direction.value}.",
                "signal",
            )
        elif "DO NOT FADE" in signals.router_state:
            add(
                Severity.WATCH,
                "CONTINUATION VETO",
                f"Bento is stretched but Trinity remains {signals.router_direction.value}; wait for confirmation.",
                "signal",
            )
        elif signals.router_state == "CONTINUATION ACTIVE":
            add(
                Severity.INFO,
                "CONTINUATION ACTIVE",
                f"Trinity alignment points {signals.router_direction.value} with score {signals.trinity_score:.0%}.",
                "signal",
            )

        if dealer.gamma_flip and abs(dealer.gamma_flip / spot - 1) <= 0.005:
            add(
                Severity.WATCH,
                "GAMMA FLIP NEARBY",
                f"Spot {spot:.2f} is within 0.5% of estimated gamma flip {dealer.gamma_flip:.2f}.",
                "dealer",
            )
        if abs(book.imbalance) >= 0.35:
            side = "bid" if book.imbalance > 0 else "ask"
            add(
                Severity.WATCH,
                "DEEP-BOOK IMBALANCE",
                f"Top depth is {abs(book.imbalance):.0%} tilted to the {side} side.",
                "book",
            )
        large = [flow for flow in flows if flow.premium >= 500_000]
        if large:
            total = sum(flow.premium for flow in large)
            bullish = sum(flow.premium for flow in large if flow.sentiment == "bullish")
            bias = "bullish" if bullish > total / 2 else "bearish"
            add(
                Severity.WATCH,
                "WHALE PREMIUM DETECTED",
                f"{len(large)} prints ≥$500k; ${total / 1e6:.1f}M aggregate, {bias} bias.",
                "flow",
            )
        return alerts


    def _cross_symbol_shock_alerts(self, *, exclude: str) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []
        now = datetime.now(UTC)
        for symbol in self.settings.watchlist:
            if symbol == exclude:
                continue
            cached = self._daily_cache.get(symbol)
            if not cached:
                continue
            state = analyze_shock(symbol, cached[1], self.settings)
            if state.severity not in {Severity.WARNING, Severity.CRITICAL}:
                continue
            message = (
                f"{state.change_pct:+.2f}% daily shock. Historical opposite-direction close within "
                f"{state.horizon_days} sessions: "
                f"{_prob_txt(state.historical_reversion_probability, state.sample_size)} "
                f"across {state.sample_size} events. Not a guarantee."
            )
            raw = f"{symbol}|watchlist-shock|{state.label}|{now:%Y-%m-%d-%H-%M}"
            alerts.append(AlertEvent(
                id=hashlib.sha1(raw.encode()).hexdigest()[:12],
                timestamp=now, symbol=symbol, severity=state.severity,
                title=state.label.upper(), message=message, category="watchlist-shock",
            ))
        return alerts

    async def close(self) -> None:
        await self.providers.close()
