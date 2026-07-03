---
name: options-event-risk-map
description: Build an honest options map around earnings, macro releases, and binary events. Use when chains are call-heavy/put-heavy before results, IV is elevated, or a user asks where an event stock may move.
---

# Options Event Risk Map

1. Verify event time with Finviz Elite and an issuer source when available.
2. Read the full-chain snapshot metadata before using IV/OI.
3. Publish ATM straddle/implied move, put/call volume and OI, top strikes, and expiry.
4. Separate aggressor-side flow from static OI and from after-hours price confirmation.
5. Mark max pain as descriptive, never a target.
6. Build conditional hold/reject/gap-fill branches around fresh IBKR prints.

Do not turn call-heavy OI into an up forecast or put-heavy OI into a down forecast.
