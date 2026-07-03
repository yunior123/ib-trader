"""libre.py — proveedor SIN suscripciones (Yunior 2026-08-23: "all free api only, forget polygon").

Reparte cada capacidad a la fuente gratuita que de verdad responde, medido el 2026-08-23:

  market   quote -> Finnhub /quote (gratis, 200 desde el Mac). Sus barras dan 403 desde 2024.
           bars  -> LSE vault /candles (1m desde 2003) y, si no hay clave, Stooq (solo diario).
  options  chain -> CBOE delayed_quotes: cadena COMPLETA con gamma, delta, IV y OI, sin clave.
  flow     -> LSE /options/flow.

LO QUE ESTAS FUENTES NO DAN, y por eso NO se rellena:
  · Finnhub /quote no publica tamanos: bid_size/ask_size quedan en 0 porque el modelo los pide,
    y eso se declara aqui — no son un dato medido.
  · CBOE es DIFERIDA y desigual entre simbolos. Nada que dispare una orden puede colgar de ella.
  · El flujo de LSE NO trae lado agresor (medido: ni side, ni bid, ni ask), asi que `side` se
    queda en "unknown". Inventarlo convertiria "no se" en "se, y es compra".

Cero valores plausibles: si una fuente no responde, se levanta ProviderError. Jamas un 0.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

from backend.app.domain import Bar, OptionContract, OptionFlow, Quote
from backend.app.providers.base import (
    FlowDataProvider,
    MarketDataProvider,
    OptionsDataProvider,
    ProviderError,
    register,
)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
LSE_URL = "https://api.londonstrategicedge.com/vault"
INDICES = {"SPX", "VIX", "NDX", "RUT", "XSP"}
RE_OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
_INTERVALOS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d"}


def _env(nombre: str) -> str | None:
    v = os.environ.get(nombre)
    if v:
        return v
    # feeds.env es la fuente unica de claves del repo; se lee tal cual, sin cachear.
    raiz = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        ruta = os.path.join(raiz, "feeds.env")
        if os.path.exists(ruta):
            for ln in open(ruta):
                if ln.startswith(nombre + "="):
                    return ln.split("=", 1)[1].strip()
            return None
        raiz = os.path.dirname(raiz)
    return None


def _get(url: str, cabeceras: dict | None = None, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(cabeceras or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


async def _json(url: str, cabeceras: dict | None = None, quien: str = "libre", cap: str = ""):
    try:
        crudo = await asyncio.to_thread(_get, url, cabeceras)
    except Exception as e:  # noqa: BLE001 - se re-lanza con contexto; nunca se traga
        raise ProviderError(f"{quien}: {e.__class__.__name__}: {e}",
                            provider="libre", capability=cap) from e
    try:
        return json.loads(crudo)
    except ValueError as e:
        raise ProviderError(f"{quien}: respuesta no es JSON", provider="libre", capability=cap) from e


def _cboe_sym(symbol: str) -> str:
    s = symbol.upper()
    return "_" + s if s in INDICES else s


@register("libre")
class LibreProvider(MarketDataProvider, OptionsDataProvider, FlowDataProvider):
    name = "libre"
    __capabilities__: set[str] = {"market", "options", "flow"}

    def __init__(self, settings=None) -> None:
        self._finnhub = _env("FINNHUB_KEY")
        self._lse = _env("LSE_API_KEY")

    # ---------------- market ----------------
    async def get_quote(self, symbol: str) -> Quote:
        """LSE manda (Yunior: "lse mainly, the rest with free shit"); Finnhub es el respaldo.

        NINGUNO de los dos publica libro: lo que devuelven es el ULTIMO precio, no un NBBO.
        Por eso bid == ask == last y los tamanos van a 0. Un gate de spread montado sobre esto
        estaria midiendo un spread de cero que no existe: hay que sacarlo de la cadena."""
        if self._lse:
            try:
                barras = await self.get_bars(symbol, interval="1m", limit=1)
            except ProviderError:
                barras = []
            if barras:
                b = barras[-1]
                return Quote(symbol=symbol.upper(), timestamp=b.timestamp, bid=b.close,
                             ask=b.close, last=b.close, bid_size=0, ask_size=0, change_pct=0)
        if not self._finnhub:
            raise ProviderError("sin LSE ni FINNHUB_KEY", provider="libre", capability="market")
        u = (f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(symbol)}"
             f"&token={self._finnhub}")
        d = await _json(u, quien="finnhub", cap="market")
        ultimo = d.get("c")
        if not ultimo or ultimo <= 0:
            raise ProviderError(f"finnhub sin precio para {symbol}", provider="libre",
                                capability="market")
        ts = datetime.fromtimestamp(d.get("t") or 0, tz=timezone.utc) if d.get("t") else \
            datetime.now(tz=timezone.utc)
        return Quote(symbol=symbol.upper(), timestamp=ts, bid=float(ultimo), ask=float(ultimo),
                     last=float(ultimo), bid_size=0, ask_size=0,
                     change_pct=float(d.get("dp") or 0))

    async def get_bars(self, symbol: str, *, interval: str = "5m", limit: int = 1200) -> list[Bar]:
        iv = _INTERVALOS.get(interval)
        if not iv:
            raise ProviderError(f"intervalo no soportado: {interval}", provider="libre",
                                capability="market")
        if self._lse:
            u = (f"{LSE_URL}/candles?symbol={urllib.parse.quote(symbol)}&interval={iv}"
                 f"&limit={min(int(limit), 5000)}&order=desc")
            filas = await _json(u, {"X-API-Key": self._lse}, quien="lse", cap="market")
            if not isinstance(filas, list) or not filas:
                raise ProviderError(f"lse sin barras para {symbol}", provider="libre",
                                    capability="market")
            out = []
            for f in reversed(filas):
                ts = f.get("ts")
                out.append(Bar(timestamp=datetime.fromisoformat(str(ts)[:19]).replace(tzinfo=timezone.utc),
                               open=f["open"], high=f["high"], low=f["low"],
                               close=f["close"], volume=f.get("volume") or 0))
            return out
        if iv != "1d":
            raise ProviderError("sin LSE_API_KEY solo hay barras diarias (Stooq)",
                                provider="libre", capability="market")
        return await self._stooq(symbol, limit)

    async def _stooq(self, symbol: str, limit: int) -> list[Bar]:
        u = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol.lower())}.us&i=d"
        try:
            crudo = (await asyncio.to_thread(_get, u)).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"stooq: {e}", provider="libre", capability="market") from e
        lineas = [x for x in crudo.strip().split("\n") if x]
        if len(lineas) < 2:
            raise ProviderError(f"stooq sin datos para {symbol}", provider="libre",
                                capability="market")
        out = []
        for ln in lineas[1:]:
            p = ln.split(",")
            if len(p) < 6:
                continue
            try:
                out.append(Bar(timestamp=datetime.fromisoformat(p[0]).replace(tzinfo=timezone.utc),
                               open=float(p[1]), high=float(p[2]), low=float(p[3]),
                               close=float(p[4]), volume=float(p[5] or 0)))
            except ValueError:
                continue
        return out[-int(limit):]

    # ---------------- options ----------------
    async def get_option_chain(self, symbol: str, *, expiration: datetime | None = None
                               ) -> list[OptionContract]:
        u = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{_cboe_sym(symbol)}.json"
        doc = await _json(u, quien="cboe", cap="options")
        d = (doc or {}).get("data") or {}
        contratos = d.get("options") or []
        if not contratos:
            raise ProviderError(f"cboe sin cadena para {symbol}", provider="libre",
                                capability="options")
        objetivo = expiration.date() if isinstance(expiration, datetime) else expiration
        out = []
        for o in contratos:
            m = RE_OCC.match(o.get("option") or "")
            if not m:
                continue
            exp = date(2000 + int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:]))
            if objetivo and exp != objetivo:
                continue
            iv = o.get("iv")
            out.append(OptionContract(
                symbol=symbol.upper(), expiration=exp, strike=int(m.group(4)) / 1000.0,
                option_type="call" if m.group(3) == "C" else "put",
                bid=o.get("bid") or 0, ask=o.get("ask") or 0,
                last=o.get("last_trade_price") or 0,
                volume=o.get("volume") or 0, open_interest=o.get("open_interest") or 0,
                # iv 0 es lo que publica CBOE cuando no hay actividad: eso es AUSENCIA, no un cero.
                implied_volatility=(iv if isinstance(iv, (int, float)) and iv > 0 else None),
                delta=o.get("delta"), gamma=o.get("gamma")))
        if not out:
            raise ProviderError(f"cboe: ningun contrato para {symbol}"
                                + (f" en {objetivo}" if objetivo else ""),
                                provider="libre", capability="options")
        return out

    # ---------------- flow ----------------
    async def get_option_flow(self, symbol: str, *, limit: int = 100) -> list[OptionFlow]:
        if not self._lse:
            raise ProviderError("falta LSE_API_KEY", provider="libre", capability="flow")
        u = f"{LSE_URL}/options/flow?limit={min(int(limit) * 5, 2000)}"
        filas = await _json(u, {"X-API-Key": self._lse}, quien="lse", cap="flow")
        if not isinstance(filas, list):
            raise ProviderError("lse flow: respuesta no es lista", provider="libre",
                                capability="flow")
        sym = symbol.upper()
        out = []
        for f in filas:
            if f.get("underlying") != sym:
                continue
            out.append(OptionFlow(
                timestamp=datetime.fromisoformat(str(f["ts"])[:19]).replace(tzinfo=timezone.utc),
                symbol=sym, option_symbol=f.get("ticker") or "",
                # LSE NO trae lado agresor: "unknown" es el dato, no un hueco que rellenar.
                side="unknown", sentiment="neutral",
                premium=f.get("premium") or 0, size=f.get("volume") or 0,
                price=f.get("last_price") or 0))
            if len(out) >= limit:
                break
        return out
