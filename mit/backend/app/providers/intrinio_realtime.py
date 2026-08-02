"""Intrinio FMV realtime por WebSocket (EquitiesEdge / OptionsEdge).

Por que existe: el REST de Intrinio NUNCA es realtime — /prices/realtime y /prices/intervals
sirven el ultimo trade consolidado con retraso. El feed FMV que se paga viaja por el WebSocket
del SDK oficial `intriniorealtime`. Este fichero es UN plugin auto-registrado (@register): el
resto del sistema no cambia, solo MIT_MARKET_PROVIDER=intrinio_realtime en feeds.env.

Estado del socket del proveedor (medido 2026-08-02, ver scripts/intrinio_ws_probe.py): los 7 hosts
de streaming cierran la conexion a los ~5,2 s sin responder. Este provider NO disimula eso: si el
socket no esta arriba, get_quote LEVANTA. Nunca sirve un precio viejo como si fuera vivo, y nunca
cae al REST delayed por su cuenta — quien quiera delayed que pida el provider 'intrinio'.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from datetime import UTC, datetime

from backend.app.config import Settings
from backend.app.domain import Bar, Quote
from backend.app.providers.base import MarketDataProvider, ProviderError, register

# Un tick mas viejo que esto no es "vivo". La regla de la casa: nada delayed dispara una orden,
# y un precio rancio disfrazado de vivo es peor que no tener precio.
MAX_TICK_AGE_S = float(os.environ.get("MIT_INTRINIO_RT_MAX_AGE_S", "15"))
CONNECT_TIMEOUT_S = float(os.environ.get("MIT_INTRINIO_RT_CONNECT_TIMEOUT_S", "30"))


@register("intrinio_realtime")
class IntrinioRealtimeProvider(MarketDataProvider):
    name = "intrinio_realtime"
    __capabilities__: set[str] = {"market"}

    def __init__(self, settings: Settings) -> None:
        key = getattr(settings, "intrinio_api_key", None) or os.environ.get("INTRINIO_API_KEY")
        if not key:
            raise ProviderError("INTRINIO_API_KEY is required", provider=self.name, capability="market")
        try:
            from intriniorealtime.equities_client import IntrinioRealtimeEquitiesClient  # noqa: F401
        except ImportError as e:
            raise ProviderError(
                f"pip install intriniorealtime en el venv que corre el puente ({e})",
                provider=self.name, capability="market", error_code="sdk_missing",
            ) from e

        self._key = key
        self._provider = os.environ.get("MIT_INTRINIO_RT_PROVIDER", "EQUITIES_EDGE")
        self._lock = threading.Lock()
        self._trades: dict[str, tuple[float, float, float]] = {}   # sym -> (epoch, price, size)
        self._quotes: dict[str, dict[str, tuple[float, float]]] = {}  # sym -> {bid|ask: (price,size)}
        self._client = None
        self._joined: set[str] = set()
        self._connect_error: str | None = None
        # El REST del mismo proveedor cubre historia (barras): el WS solo trae el tick vivo.
        from backend.app.providers.intrinio import IntrinioProvider

        self._rest = IntrinioProvider(settings)

    # --- socket ---------------------------------------------------------------
    @staticmethod
    def _exchange_epoch(raw) -> float | None:
        """El SDK entrega el timestamp de BOLSA en nanosegundos (equities_replay_client.py:366,
        options_client.py:456). Hay que usar ese, no la hora de llegada: si el feed viniera con
        retraso, marcarlo con la hora local lo disfrazaria de vivo y pasaria el gate de 10 s.
        Un valor fuera de rango razonable devuelve None (el tick se descarta, no se 'arregla')."""
        if raw is None:
            return None
        try:
            secs = float(raw) / 1e9
        except (TypeError, ValueError):
            return None
        now = time.time()
        if not (now - 7 * 86400) < secs < (now + 3600):
            return None
        return secs

    def _on_trade(self, trade) -> None:
        sym = getattr(trade, "symbol", None)
        price = getattr(trade, "price", None)
        ts = self._exchange_epoch(getattr(trade, "timestamp", None))
        if not sym or price is None or ts is None:
            return
        with self._lock:
            self._trades[sym.upper()] = (ts, float(price), float(getattr(trade, "size", 0) or 0))

    def _on_quote(self, quote) -> None:
        sym = getattr(quote, "symbol", None)
        price = getattr(quote, "price", None)
        ts = self._exchange_epoch(getattr(quote, "timestamp", None))
        if not sym or price is None or ts is None:
            return
        # El SDK marca el lado en .type ('ask'|'bid'); sin lado no se puede usar (un bid guardado
        # como ask fabrica un spread invertido que pasaria cualquier gate).
        side = str(getattr(quote, "type", "")).lower()
        if side not in ("bid", "ask"):
            return
        with self._lock:
            self._quotes.setdefault(sym.upper(), {})[side] = (
                float(price), float(getattr(quote, "size", 0) or 0), ts
            )

    _AUTH_HOST = {
        "EQUITIES_EDGE": "equities-edge", "CBOE_ONE": "cboe-one",
        "DELAYED_SIP": "realtime-delayed-sip", "NASDAQ_BASIC": "realtime-nasdaq-basic",
        "REALTIME": "realtime-mx", "IEX": "realtime-mx",
    }

    def _auth_alcanzable(self) -> str | None:
        """Pre-chequeo ACOTADO antes de tocar el SDK. Motivo: equities_client.py:262 hace
        requests.get SIN timeout y connect() reintenta en bucle infinito -> un socket apagado
        (lo normal fuera de horario) dejaria un hilo girando para siempre. Devuelve el motivo
        del fallo, o None si el auth responde."""
        import requests

        host = self._AUTH_HOST.get(self._provider)
        if host is None:
            return None  # proveedor no mapeado: que decida el SDK
        try:
            r = requests.get(
                f"https://{host}.intrinio.com/auth",
                params={"api_key": self._key},
                headers={"Client-Information": "IntrinioPythonSDKv6.3.0"},
                timeout=10,
            )
        except Exception as e:
            return f"{host}/auth no responde ({type(e).__name__}) — socket apagado o incidencia"
        if r.status_code != 200 or len((r.text or "").strip()) <= 20:
            return f"{host}/auth -> HTTP {r.status_code} sin token"
        return None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        if self._connect_error:
            raise ProviderError(self._connect_error, provider=self.name, capability="market",
                                error_code="socket_down")
        motivo = self._auth_alcanzable()
        if motivo:
            self._connect_error = f"{motivo} — ver data/intrinio_ws_status.json"
            raise ProviderError(self._connect_error, provider=self.name, capability="market",
                                error_code="socket_down")
        from intriniorealtime.equities_client import IntrinioRealtimeEquitiesClient

        cfg = {"api_key": self._key, "provider": self._provider}
        client = IntrinioRealtimeEquitiesClient(cfg, self._on_trade, self._on_quote)

        done = threading.Event()
        err: list[str] = []

        def _connect() -> None:
            try:
                client.connect()
            except Exception as e:  # el SDK reintenta en bucle; aqui solo interesa el primer fallo
                err.append(f"{type(e).__name__}: {e}")
            finally:
                done.set()

        threading.Thread(target=_connect, daemon=True, name="intrinio-rt-connect").start()
        if not done.wait(CONNECT_TIMEOUT_S) or err:
            # Sintoma medido hoy: los hosts aceptan TLS y cierran a los ~5,2 s sin un byte.
            self._connect_error = (
                f"socket Intrinio {self._provider} no conecta"
                + (f": {err[0]}" if err else f" (timeout {CONNECT_TIMEOUT_S}s)")
                + " — comprobar data/intrinio_ws_status.json"
            )
            raise ProviderError(self._connect_error, provider=self.name, capability="market",
                                error_code="socket_down")
        self._client = client

    def _join(self, symbol: str) -> None:
        if symbol in self._joined:
            return
        self._client.join([symbol])
        self._joined.add(symbol)

    # --- interfaz MarketDataProvider ------------------------------------------
    @staticmethod
    def _lado(entrada) -> tuple[float, float]:
        """(precio, tamaño) del lado si sigue fresco; (0,0) si falta o esta rancio — el puente
        rechaza un NBBO con cero, que es justo lo que queremos frente a inventar un spread."""
        if not entrada:
            return (0.0, 0.0)
        price, size, ts = entrada
        if (time.time() - ts) > MAX_TICK_AGE_S:
            return (0.0, 0.0)
        return (price, size)

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper()
        await asyncio.to_thread(self._ensure_client)
        await asyncio.to_thread(self._join, sym)

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self._lock:
                tr = self._trades.get(sym)
                q = dict(self._quotes.get(sym) or {})
            if tr and (time.time() - tr[0]) <= MAX_TICK_AGE_S:
                # Un lado rancio no se mezcla con uno fresco: daria un spread inventado.
                bid, bid_sz = self._lado(q.get("bid"))
                ask, ask_sz = self._lado(q.get("ask"))
                return Quote(
                    symbol=sym,
                    timestamp=datetime.fromtimestamp(tr[0], tz=UTC),  # epoch de BOLSA
                    bid=bid, ask=ask, last=tr[1],
                    bid_size=bid_sz, ask_size=ask_sz,
                )
            await asyncio.sleep(0.1)

        raise ProviderError(
            f"sin tick vivo de {sym} en {MAX_TICK_AGE_S}s por el socket {self._provider}",
            provider=self.name, capability="market", error_code="no_tick",
        )

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        # Historia por REST del mismo proveedor: el socket no reproduce el pasado.
        return await self._rest.get_bars(symbol, interval=interval, limit=limit)

    async def get_daily_bars(self, symbol: str, *, limit: int = 756) -> list[Bar]:
        return await self._rest.get_daily_bars(symbol, limit=limit)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await asyncio.to_thread(client.disconnect)
        await self._rest.close()
