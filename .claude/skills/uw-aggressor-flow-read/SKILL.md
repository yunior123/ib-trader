---
name: uw-aggressor-flow-read
description: Read Unusual Whales net premium and flow alerts without inferring direction from call/put labels alone. Use for whale searches, UW tape, signed premium, bid/ask-side alerts, sweeps, or market-tide analysis.
---

# UW Aggressor Flow Read

Use these read-only endpoints:

```text
/api/stock/{SYM}/net-prem-ticks
/api/stock/{SYM}/flow-alerts
/api/market/market-tide
```

Interpret execution side:

- ask call = bullish; bid call = bearish;
- ask put = bearish; bid put = bullish;
- mid = direction unknown.

Compute `signed = net_call_premium - net_put_premium`. State the full-day and final-30-bucket
values separately. Include strike, expiry, premium, side, sweep flag, OI, volume, and feed time.
Never claim opening versus closing or dealer positioning; UW does not reveal it reliably.
