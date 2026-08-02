# Validation performed before packaging

- `python -m compileall -q backend scripts` — passed.
- `pytest -q` — 3 tests passed.
- `node --check backend/app/static/app.js` — passed.
- `python scripts/smoke_test.py` — built a complete mock SPY snapshot with candles, chain analytics, depth, flow, shock map and alerts.
- FastAPI was launched locally; `/api/health` and `/api/snapshot/SPY` returned successfully.

The vendor adapters compile but were not authenticated against private paid accounts because no user API keys were supplied. Pine Script source was reviewed for Pine v6 syntax; TradingView does not provide a local Pine compiler in this environment, so paste each file into the TradingView editor for final account-side compilation and alert setup.
