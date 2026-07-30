---
name: semiconductor-captain-check
description: Resolve conflicts between SMH captain flow, broad-market captains, and individual semiconductor names. Use for MU, NVDA, AMD, TSM, memory, or semis when flow and price disagree.
---

# Semiconductor Captain Check

Apply `SPY/QQQ > SMH > individual name`.

1. Read signed flow and price structure for all applicable captains.
2. Compare SMH breadth with MU/NVDA/AMD/TSM rather than counting correlated names as independent.
3. Treat massive captain puts/calls as a possible local extreme only after Bollinger and print
   confirmation.
4. If captain and name conflict, suppress the name's voice and report the conflict.
5. Keep KRX evidence as one regional input, not three independent votes.
