---
name: spy-next-session-tree
description: Build a conditional SPY next-session scenario tree from price, options structure, signed flow, overnight markets, and calibration. Use for tomorrow outlooks, printed decision trees, or bull/bear branch probabilities.
---

# SPY Next-session Tree

Use fresh SPY bars, the converged full chain, UW aggressor flow, market tide, ES/NQ, VIX status,
and compass calibration. Choose 2–4 mutually exclusive root ranges around confluence levels.

- Make every sibling probability sum to 100%.
- Label probabilities measured only when a matching calibrated sample exists; otherwise say
  `judgmental synthesis`.
- Give each branch a fresh-IBKR trigger, target sequence, and invalidation.
- Include an ASCII section headed `SPY TREE PRINT` with exact as-of time.
- Keep max pain, X sentiment, and delayed chain data out of trigger logic.
