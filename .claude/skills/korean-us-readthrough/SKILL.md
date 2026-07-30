---
name: korean-us-readthrough
description: Map live Korean memory and KOSPI behavior into US semiconductor risk without double counting correlated inputs. Use for Samsung, SK Hynix, KOSPI, MU, SMH, NVDA, TSM, DRAM, SKHY, EWY, or Korea-open alarms.
---

# Korean US Read-through

Read `data/overnight_ctx.json` and fresh KRX bars. Verify Samsung, SK Hynix, and KOSPI timestamps.

- Weight the regional basket once; do not count each constituent as an independent family.
- Distinguish earnings quality from post-earnings price acceptance.
- Cross-check NQ/ES and SMH before projecting the move into US names.
- Use X Korean sentiment only as context and identify spam/sarcasm limits.
- Require print confirmation at the named KRX or US level before a buy/sell alarm.

Report leader, breadth, divergence, level, invalidation, and data age.
