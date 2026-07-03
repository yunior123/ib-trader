# Architecture

## Data flow

```text
Databento / Intrinio / Unusual Whales / Mock
                    │
            provider adapters
                    │
        normalized domain models
                    │
      MarketIntelligenceEngine
       ├── technical classifier
       ├── options positioning
       ├── order-book analytics
       ├── shock/reversion study
       └── alert rules
                    │
          FastAPI REST + WebSocket
                    │
  TradingView Lightweight Charts dashboard
```

## Provider-neutral interfaces

`backend/app/providers/base.py` separates four capabilities:

- `MarketDataProvider`
- `OptionsDataProvider`
- `DepthDataProvider`
- `FlowDataProvider`

A new vendor only needs to translate its payloads into the Pydantic models in `domain.py`. Analytics never imports vendor SDKs.

## Production live-stream hub

Do not create a Databento or flow-vendor WebSocket connection for every UI browser. Use one process/service-level connection per dataset/account:

1. Subscribe to all active symbols.
2. Normalize callbacks into `Quote`, `Bar`, `OrderBook` and `OptionFlow` events.
3. Update a bounded in-memory cache or Redis streams.
4. Publish internal events to the FastAPI WebSocket fan-out.
5. Reconnect with exponential backoff and replay from persisted sequence/timestamp when supported.

The reference orchestrator uses short-lived provider calls so mock mode and REST-capable subscriptions work immediately. Its interfaces are intentionally compatible with swapping in a cache-backed stream hub.

## Signal architecture

### Bento

The first 15-minute signal is an early watch. The strong setup waits until the first 30-minute candle is complete and requires 15m and 30m Bollinger/RSI extremes in the same direction after an opening gap. Its prediction is the opposite direction.

### Trinity

Continuation quality is built from:

- 5m, 15m, 1h, 4h and daily price-vs-EMA5 alignment;
- 20-period High/HLC3/Low ribbon;
- RSI relative to 50 and its own basis/Bollinger state;
- +DI/-DI and ADX;
- five-minute ATR relative to prior daily ATR.

### Router

When Bento is armed, the router scores six changes:

1. price re-enters the Bollinger Band;
2. price enters/crosses the ribbon;
3. RSI turns;
4. DMI flips;
5. original five-timeframe alignment breaks;
6. a reversal candle confirms.

Five of six confirms reversal. Until then, opposing Trinity continuation produces `DO NOT FADE`.

## Reliability upgrades for production

- Use exchange calendars rather than naive wall-clock grouping.
- Store raw vendor sequence numbers and timestamps.
- Separate event time from ingest time.
- Reconstruct the book from MBO when L3 precision is required.
- Track wall persistence and cancellation/execution ratio.
- Use point-in-time option chains for backtests; never backfill with today's open interest.
- Calibrate shock thresholds per symbol and volatility regime.
- Add notification deduplication in Redis/Postgres for multi-process deployments.
