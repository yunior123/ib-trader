---
name: option-liquidity-gate
description: Verify an option contract is executable before naming it. Use for contract selection, cheap calls/puts, whale-following ideas, spreads, or any recommendation containing strike and expiry.
---

# Option Liquidity Gate

Require fresh entitled quotes and verify:

- exact underlying, right, strike, expiry, and multiplier;
- bid > 0, ask > bid, spread <= 5% of midpoint;
- OI > 500 and meaningful same-day volume;
- premium within the stated budget;
- no stale/expired contract and no substituted expiry.

Use `bin/opt_quick <SYM> <STRIKE> <C|P>` for cached structure, then confirm NBBO through IBKR.
If after-hours bid/ask is unavailable, say `NO-APTO-AH`; do not fabricate a contract price.
