# tests/ — critical trading-module guards

Deterministic, offline (no yfinance/IBKR network). Run:

```
./venv/bin/python -m pytest tests/ -q
```

Covers division-by-zero / empty-input / missing-file guards in
`calibration_ledger`, `force_meter`, `index_breadth`, `posthours_cage`,
`daily_fleet_plans` (bs_greeks + graceful loaders) — the paths that break the 4am run.
