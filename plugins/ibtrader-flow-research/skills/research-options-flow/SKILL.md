---
name: research-options-flow
description: Analyze ib-trader options flow using UW aggressor side, signed premium, full-chain structure, and freshness labels. Use for whales, tomorrow outlooks, event chains, or bull/bear flow conflicts.
---

# Research Options Flow

- Ask UW for `net-prem-ticks`, `flow-alerts`, and market tide.
- Derive direction from execution side: ask-call/bid-put bullish; bid-call/ask-put bearish.
- Treat mid-side, opening/closing, and multi-leg intent as unknown.
- Read full-chain metadata before using OI, IV, GEX, walls, or expected move.
- Use fresh IBKR price only to confirm a branch.
- Publish full-day versus closing-window flow separately.

Never infer direction from raw call/put counts and never place or simulate orders.
