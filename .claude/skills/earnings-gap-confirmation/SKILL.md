---
name: earnings-gap-confirmation
description: Confirm whether an earnings gap is holding, rejecting, or filling using ib-trader data. Use after results when after-hours price, options flow, and the prior close produce conflicting direction.
---

# Earnings Gap Confirmation

Record prior close, after-hours high/low, current IBKR print, expected move, and nearest walls.
Classify only after two fresh prints:

- `HOLD`: above the gap pivot with a successful retest;
- `REJECT`: failed pivot and return through the event midpoint;
- `FILL`: entry into the prior session range;
- `UNCONFIRMED`: insufficient prints.

Do not let pre-earnings flow overrule post-release price. Publish the exact level that changes the
classification and suppress a directional probability until confirmation.
