---
name: cockpit-flow-ui-audit
description: Audit the ib-trader cockpit's options-flow UX against professional flow products without redesigning it. Use for hierarchy, filtering, provenance, accessibility, stale-state, density, or widget usability reviews.
---

# Cockpit Flow UI Audit

Inspect `charts/live.html`, `scripts/chart_bridge.py`, and UI tests. Compare capabilities, not
branding, against official product documentation.

Review:

- price/flow time alignment and rolling windows;
- filters for side, expiry, premium, sweep, OI, and ticker;
- contract aggregation versus raw prints;
- source, age, entitlement, and error states;
- keyboard navigation, focus, contrast, and reduced motion;
- multi-window consistency and saved layout.

Return repo-specific gaps with current code evidence, user impact, smallest implementation, and
validation. Do not propose unsupported dealer-flow claims.
