---
name: afterhours-source-honesty
description: Audit after-hours and overnight market inputs for freshness, entitlement, and valid use. Use when bid/ask disappears, charts disagree, futures/ADR/perpetual prices are mixed, or a report crosses RTH into KRX.
---

# After-hours Source Honesty

Check timestamp and source for:

```text
data/bars_<sym>_ibkr.txt
data/overnight_ctx.json
data/vix.json
data/history/<date>/chain_full_<sym>.json
data/perp_stocks.json
```

Label each input `trigger-grade`, `structure-only`, `context-only`, or `unavailable`. Reject
future timestamps and stale values. Outside RTH, do not invert IV from missing bid/ask. Polygon
and CBOE describe structure; only fresh IBKR prints confirm levels.
