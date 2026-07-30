---
name: audit-live-signal
description: Trace one ib-trader compass signal from live inputs through families, vetoes, calibration, and cockpit output. Use when an arrow looks wrong, changes color unexpectedly, or shows no measured probability.
---

# Audit Live Signal

1. Read fresh bars, levels, book quality, VT, overnight context, and captain flow.
2. Reproduce the state with `bin/compass --ev-stdin`.
3. List each independent family and veto from `scripts/compass.cpp`.
4. Verify `STATE|fN|REGIME` against `data/compass_calib.json`.
5. Require `n_eff>=30` and Wilson low above 0.50 for a measured arrow.
6. Trace `data/compass_<sym>.json` through `scripts/chart_bridge.py` to `charts/live.html`.

Return evidence with file/line, timestamps, and already-fixed versus remaining gaps. Never execute
or stage an order.
