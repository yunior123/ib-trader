# Market Intelligence Terminal

A reusable FastAPI + TradingView Lightweight Charts decision-support terminal for:

- independent **Bento opening-reversal** detection;
- independent **Trinity continuation** detection;
- a third **regime router** that lets continuation veto a premature fade and confirms reversal only after 5/6 state changes;
- stock/ETF/volatility quotes and intraday candles;
- options-chain analytics: GEX/DEX scenario, gamma flip, call/put walls, max pain, expected move and magnets;
- unusual options flow / whale tape;
- L2/L3 order-book imbalance, microprice and liquidity walls;
- 10% / 15% and z-score shock alerts for every watchlist symbol;
- empirical same-day / next-two-session reversion calibration;
- Monday-to-Friday current-week shock matrix;
- provider health, per-capability fallbacks and WebSocket UI updates.

The included mock provider runs the full product without API keys. Real providers are selected independently by capability.

## Design decision: separate signals + combined router

The research package in `research/` found that Bento and Trinity should **not** be collapsed into one agreement signal:

- Bento asks whether the opening move is stretched enough to arm a reversal.
- Trinity asks whether trend continuation is still aligned.
- The router outputs one of:
  - `CONTINUATION ACTIVE — DO NOT FADE`
  - `REVERSAL ARMED — WAIT`
  - `REVERSAL CONFIRMED`
  - `NEUTRAL / CONFLICT`

The three Pine scripts mirror that architecture and can be used independently.

## Quick start

```bash
cd market_intelligence_terminal
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn backend.app.main:app --reload
```

Open `http://localhost:8000`. Mock mode is enabled by default. The page pins TradingView Lightweight Charts 5.2.0 from UNPKG. Run `python scripts/vendor_lightweight_charts.py` to save a local copy, then point the script tag to `/static/vendor/lightweight-charts.standalone.production.js` for an offline deployment.

### Docker

```bash
docker compose up --build
```

## Real-provider routing

Recommended starting configuration:

```dotenv
MIT_MODE=live
MIT_MARKET_PROVIDER=databento
MIT_DEPTH_PROVIDER=databento
MIT_OPTIONS_PROVIDER=intrinio
MIT_FLOW_PROVIDER=unusual_whales
```

Then supply the corresponding keys and Unusual Whales WebSocket details in `.env`. Set `MIT_DATABENTO_USE_LIVE=true` to start the included process-level Databento live cache; otherwise the adapter polls recent range data.

### Capability boundaries

| Capability | Best included adapter | Notes |
|---|---|---|
| Quotes / candles / daily history | Databento or Intrinio | Databento adapter uses EQUS.MINI by default; Intrinio source is configurable. |
| Deep book | Databento | XNAS.ITCH + `mbp-10` by default; use an entitled depth dataset/schema. |
| Option chain + IV/Greeks/OI | Intrinio | Best source for the included dealer-positioning engine. |
| Live whale/flow topics | Unusual Whales | Configurable WebSocket URL and auth/subscription JSON templates. |
| Development / demos / tests | Mock | Deterministic synthetic data, no network or credentials. |

Every capability has an isolated mock fallback. A failure in options flow does not take down candles or depth.

## Databento live-stream template

The included Databento adapter is a polling-compatible reference using official historical range calls for bars, quotes and depth. For a long-running production deployment, keep one `db.Live` client per dataset, subscribe once, register callbacks and update an in-memory cache:

```python
import databento as db

client = db.Live(key="...")
client.subscribe(
    dataset="EQUS.MINI",
    schema="mbp-1",
    stype_in="raw_symbol",
    symbols=["SPY"],
)
client.add_callback(on_record)
client.start()
```

See `docs/ARCHITECTURE.md` for the cache/worker pattern and why a process-level stream hub is preferable to opening a vendor connection per browser.

## Important interpretation limits

### 10–15% shock does not imply automatic reversal

The shock widget creates an alarm when:

- absolute daily change reaches 10% or 15%; or
- the move exceeds the configured rolling z-score threshold.

It then reports the historical fraction of comparable shocks that experienced **any opposite-direction close** within the configured horizon. Large moves can continue, gap again, or remain one-sided. The UI explicitly displays the sample size and never promotes the heuristic to a certainty.

### Dealer positioning is a scenario unless observed

Open interest does not reveal who owns each contract. The default engine applies a transparent call-positive / put-negative gamma scenario and reprices the chain across spot to estimate a gamma flip. Use vendor-supplied dealer/GEX fields when available and preserve the caveat in the UI.

### Order-book walls are ephemeral

Displayed walls are the largest visible levels in the latest snapshot. They may be cancelled, replenished or spoofed. Combine them with executed volume, persistence and microprice—not as standalone support/resistance guarantees.

## Pine scripts

- `pine/01_bento_reversal_predictor_v2.pine`
- `pine/02_trinity_continuation_predictor_v2.pine`
- `pine/03_combined_regime_router_v2.pine`

All are indicators, not auto-trading strategies. They expose ordinary `alertcondition()` rules plus optional dynamic JSON `alert()` payloads for webhooks.

## API

- `GET /api/health`
- `GET /api/watchlist`
- `GET /api/snapshot/{symbol}`
- `GET /api/snapshot/{symbol}?force=true`
- `WS /ws/{symbol}`

The snapshot schema is defined in `backend/app/domain.py` and is stable across providers.

## Testing

```bash
pytest -q
python scripts/smoke_test.py
```

## Security and deployment

- Keep keys only in `.env` or a secret manager; never expose them to browser JavaScript.
- Put the FastAPI service behind authentication before exposing it publicly.
- Add vendor-specific rate limiting and entitlement controls.
- Run one upstream stream hub per vendor/dataset and fan out normalized events internally.
- Persist raw events when you need auditability or reproducible alerts.
- This project does not place orders and is not investment advice.
