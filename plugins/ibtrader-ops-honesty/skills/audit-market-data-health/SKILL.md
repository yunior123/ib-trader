---
name: audit-market-data-health
description: Diagnose stale or missing ib-trader market data by tracing producer, artifact, consumer, keepalive, source, and entitlement. Use when charts are blank, arrows freeze, or a feed silently stops.
---

# Audit Market Data Health

1. Resolve the screen field to its data artifact with `rg`.
2. Check embedded timestamp and filesystem mtime.
3. Identify producer, keepalive, consumer, log, and current market-hours gate.
4. Label the source realtime, delayed, context-only, or unavailable.
5. Restart only the owning keepalive when authorized; verify two fresh cycles.
6. Report the full path and any remaining entitlement gap.

Do not broaden into fleet-wide restarts or broker operations.
