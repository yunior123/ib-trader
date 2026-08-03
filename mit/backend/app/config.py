from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Nombre de proveedor: str libre (no Literal cerrado) para que AÑADIR un proveedor sea 1 fichero
# auto-registrado, sin tocar config ni registry. Un nombre desconocido -> UnavailableProvider ->
# el provider_bridge ABORTA fail-loud (guard anti-mock), asi que no hay silencio.
ProviderName = str

# Fichero de secretos de la flota (override con MIT_FEEDS_ENV) + un .env local opcional.
_FEEDS_ENV = Path(os.environ.get("MIT_FEEDS_ENV") or (Path(__file__).resolve().parents[3] / "config" / "feeds.env"))
_ENV_FILES = (str(_FEEDS_ENV), ".env")


def _export_to_environ() -> None:
    """Vuelca los KEY=VALUE de feeds.env a os.environ SIN pisar lo ya presente. Asi un proveedor
    NUEVO puede leer sus keys con os.environ.get('MIPROVEEDOR_KEY') en su __init__ — un solo
    fichero, sin tocar esta clase Settings (idea MVVM: el adaptador trae su propia config)."""
    for f in (str(_FEEDS_ENV), ".env"):
        try:
            for line in Path(f).read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
        except OSError:
            continue


_export_to_environ()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES, extra="ignore", case_sensitive=False, populate_by_name=True
    )

    mode: Literal["mock", "live"] = Field("mock", alias="MIT_MODE")
    host: str = Field("0.0.0.0", alias="MIT_HOST")
    port: int = Field(8000, alias="MIT_PORT")
    refresh_seconds: float = Field(5.0, alias="MIT_REFRESH_SECONDS")
    watchlist: list[str] = Field(
        default_factory=lambda: ["SPY", "QQQ", "IWM", "TSLA", "MSTR", "NVDA", "AAPL", "VIX"],
        alias="MIT_WATCHLIST",
    )

    market_provider: ProviderName = Field("mock", alias="MIT_MARKET_PROVIDER")
    options_provider: ProviderName = Field("mock", alias="MIT_OPTIONS_PROVIDER")
    depth_provider: ProviderName = Field("mock", alias="MIT_DEPTH_PROVIDER")
    flow_provider: ProviderName = Field("mock", alias="MIT_FLOW_PROVIDER")

    shock_pct: float = Field(10.0, alias="MIT_SHOCK_PCT")
    extreme_shock_pct: float = Field(15.0, alias="MIT_EXTREME_SHOCK_PCT")
    shock_zscore: float = Field(2.5, alias="MIT_SHOCK_ZSCORE")
    reversion_lookback_days: int = Field(756, alias="MIT_REVERSION_LOOKBACK_DAYS")
    reversal_horizon_days: int = Field(2, alias="MIT_REVERSAL_HORIZON_DAYS")

    databento_api_key: str | None = Field(None, alias="DATABENTO_API_KEY")
    databento_market_dataset: str = Field("EQUS.MINI", alias="MIT_DATABENTO_MARKET_DATASET")
    databento_depth_dataset: str = Field("XNAS.ITCH", alias="MIT_DATABENTO_DEPTH_DATASET")
    databento_options_dataset: str = Field("OPRA.PILLAR", alias="MIT_DATABENTO_OPTIONS_DATASET")
    databento_depth_schema: str = Field("mbp-10", alias="MIT_DATABENTO_DEPTH_SCHEMA")
    databento_use_live: bool = Field(False, alias="MIT_DATABENTO_USE_LIVE")
    databento_live_warmup_seconds: float = Field(1.5, alias="MIT_DATABENTO_LIVE_WARMUP_SECONDS")

    intrinio_api_key: str | None = Field(None, alias="INTRINIO_API_KEY")
    intrinio_base_url: str = Field("https://api-v2.intrinio.com", alias="MIT_INTRINIO_BASE_URL")
    intrinio_stock_source: str = Field("iex", alias="MIT_INTRINIO_STOCK_SOURCE")
    # /prices/intervals accepts iex|cboe_one_delayed|<none> (NOT intrinio_mx, which is /realtime only).
    intrinio_interval_source: str = Field("iex", alias="MIT_INTRINIO_INTERVAL_SOURCE")
    intrinio_options_source: str = Field("delayed", alias="MIT_INTRINIO_OPTIONS_SOURCE")
    # El LIBRO (bid/ask) NO sale de equities_edge: medido 2026-08-03 10:15 UTC sobre SPY QQQ NVDA
    # MU GLD NOK, `source=equities_edge` devuelve bid=None ask=None en los 6 (y en AAPL un
    # bid=232.84/ask=1.0 sin sentido) -> el puente rechazaba el NBBO y data/nbbo_*.txt llevaba
    # 56 h congelado. `cboe_one` si da libro utilizable (spreads 0,007%-0,111% en esos mismos 6).
    # Sigue siendo delayed: el epoch que se escribe es el de BOLSA, asi que el gate de frescura
    # de los bots (now-ep<=10s) lo rechaza igual para disparar. Sirve para mapa y contexto.
    intrinio_quote_source: str = Field("cboe_one", alias="MIT_INTRINIO_QUOTE_SOURCE")

    # Polygon: options chain (measured greeks/IV/OI via /v3/snapshot/options) + daily aggs.
    polygon_api_key: str | None = Field(None, alias="POLYGON_KEY")
    polygon_base_url: str = Field("https://api.polygon.io", alias="MIT_POLYGON_BASE_URL")
    # Sin este rango, el snapshot solo devuelve el vencimiento frontal; con el, pagina a
    # varias expiraciones (el mapa strike x vencimiento de la semana). Dias naturales hacia delante.
    polygon_chain_days: int = Field(28, alias="MIT_POLYGON_CHAIN_DAYS")
    # TTL de la cadena multi-vencimiento que comparten heatmap y TRACE. 0 = sin cache.
    # 300 s y no 45: la propia descarga tarda 35-80 s (10 vencimientos x paginacion de 250),
    # asi que un TTL corto caducaba ANTES de que llegara la peticion siguiente y no ahorraba nada
    # (medido 2026-08-02: 50,6 / 34,7 / 73,1 s en tres refrescos seguidos con TTL=45).
    chain_cache_ttl_s: float = Field(300.0, alias="MIT_CHAIN_TTL_S")

    unusual_whales_token: str | None = Field(None, alias="UNUSUAL_WHALES_TOKEN")
    uw_ws_url: str | None = Field(None, alias="MIT_UW_WS_URL")
    uw_topics: list[str] = Field(
        default_factory=lambda: ["flow-alerts", "live-gex", "option-state", "greek-flow"],
        alias="MIT_UW_TOPICS",
    )
    uw_auth_message_json: str = Field(
        '{"type":"auth","token":"{token}"}', alias="MIT_UW_AUTH_MESSAGE_JSON"
    )
    uw_subscribe_message_json: str = Field(
        '{"type":"subscribe","topics":{topics},"symbol":"{symbol}"}',
        alias="MIT_UW_SUBSCRIBE_MESSAGE_JSON",
    )

    @field_validator("watchlist", "uw_topics", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("watchlist")
    @classmethod
    def normalize_watchlist(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(symbol.upper() for symbol in value))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
