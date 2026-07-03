from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.analytics.overnight_futures import read_overnight
from backend.app.config import get_settings
from backend.app.engine import EventBus, MarketIntelligenceEngine
from backend.app.providers.registry import build_providers

STATIC_DIR = Path(__file__).resolve().parent / "static"
settings = get_settings()
bus = EventBus()
providers = build_providers(settings)
engine = MarketIntelligenceEngine(settings, providers, bus)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.close()


app = FastAPI(title="Market Intelligence Terminal", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mode": settings.mode,
        "watchlist": settings.watchlist,
        "providers": {
            "market": settings.market_provider,
            "options": settings.options_provider,
            "depth": settings.depth_provider,
            "flow": settings.flow_provider,
        },
    }


@app.get("/api/watchlist")
async def watchlist() -> dict:
    return {"symbols": settings.watchlist}


@app.get("/api/snapshot/{symbol}")
async def snapshot(symbol: str, force: bool = False):
    symbol = symbol.upper()
    if not symbol.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")
    return await engine.snapshot(symbol, force=force)


@app.get("/api/gex_heatmap/{symbol}")
async def gex_heatmap(symbol: str, metric: str = "gex"):
    symbol = symbol.upper()
    if not symbol.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")
    metric = metric.lower()
    if metric not in {"gex", "vex"}:
        raise HTTPException(status_code=400, detail="Invalid metric")
    return await engine.gex_heatmap(symbol, metric=metric)


@app.get("/api/futures")
async def futures():
    """Mapa de HUECO de la noche (futuros CME + apertura implicita + liderazgo coreano)."""
    return read_overnight()


@app.get("/api/trace/{symbol}")
async def trace(symbol: str, metric: str = "gex"):
    symbol = symbol.upper()
    if not symbol.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")
    metric = metric.lower()
    if metric not in {"gex", "netoi"}:
        raise HTTPException(status_code=400, detail="Invalid metric")
    return await engine.trace_matrix(symbol, metric=metric)


@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()
    queue = await bus.subscribe(symbol)
    producer = asyncio.create_task(_producer(symbol))
    try:
        initial = await engine.snapshot(symbol)
        await websocket.send_json(initial.model_dump(mode="json"))
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
        await bus.unsubscribe(symbol, queue)


async def _producer(symbol: str) -> None:
    while True:
        await asyncio.sleep(settings.refresh_seconds)
        try:
            await engine.snapshot(symbol, force=True)
        except Exception:
            continue
