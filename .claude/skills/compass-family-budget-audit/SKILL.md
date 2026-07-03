---
name: compass-family-budget-audit
description: Audit ib-trader compass signal-family independence, veto behavior, hard caps, and hit rates. Use when adding a factor, diagnosing constant reversals/neutrality, or reviewing `FAMILIES_MAX`, `VETOES_MAX`, and `COMPASS_AUDIT`.
---

# Compass Family Budget Audit

Read `families()` and `vetoes_of()` in `scripts/compass.cpp`.

- Preserve one vote per independent category: flow, stretch, exhaustion, pattern.
- Preserve hard caps (`FAMILIES_MAX=6`, `VETOES_MAX=8`).
- Reject additions that duplicate an occupied category; replace an inferior family instead.
- Run `COMPASS_AUDIT=1 bin/compass --json <symbols>` and compare hit rates.
- Flag vetoes that fire nearly always; they are kill switches, not discriminators.
- Require replay/OOS evidence before changing thresholds or giving a new family voice.

Return a keep/replace/remove table with code line, evidence, sample size, and test needed.
