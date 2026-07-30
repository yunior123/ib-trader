---
name: compass-calibration-gate
description: Audit whether an ib-trader compass probability is measured, pooled, doctrinal, or correctly suppressed. Use for green/red arrow complaints, `prob_source`, `sin_edge`, `sin_medir`, Wilson gates, or `compass_calib.json`.
---

# Compass Calibration Gate

1. Read `data/compass_<sym>.json`, `data/compass_calib.json`, and the matching rows in
   `data/compass_ledger.jsonl`.
2. Map the output to `STATE|fN|REGIME`; clamp `N` exactly as `scripts/compass.cpp` does.
3. Require `n_eff >= 30` and Wilson `lo > 0.50` before calling an arrow measured.
4. Label a pooled state cell `medido_pool`; never present it as symbol-specific.
5. Treat `lo <= 0.50` as `sin_edge`: flat arrow, null probability, candidate direction retained
   only for calibration.
6. Verify with:

```sh
./venv/bin/python -m pytest tests/test_compass.py tests/test_compass_calibrate.py -q
```

Report `n_eff`, `n_raw`, WR30, Wilson low, exclusions, and exact source timestamps.
