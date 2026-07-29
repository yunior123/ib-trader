---
name: calibration-review
description: Review compass calibration ledger (compass_calib.json, setup_type×regime buckets) — identify dead cells (n<30), high-variance setups, trend in win-rates, which buckets are measured vs doctrine. Use for recalibration decisions before session.
---

# Calibration Review — Auditar probabilidades medidas

Revisar `compass_calib.json` y detectar celdas débiles, drifts, doctrina vieja.

## Comandos
```bash
cd ~/ib-trader

# Resumen de calibración
python3 << 'PYEOF'
import json
calib = json.load(open('data/compass_calib.json'))
print(f"Cells: {len(calib)}")
ns = [v['n'] for v in calib.values()]
probs = [v.get('measured_prob', v.get('prob', 0)) for v in calib.values()]
print(f"n: min={min(ns)}, median={sorted(ns)[len(ns)//2]}, max={max(ns)}")
print(f"prob: min={min(probs):.2%}, median={sorted(probs)[len(probs)//2]:.2%}, max={max(probs):.2%}")

# Celdas muertas (n < 30)
dead = {k: v for k, v in calib.items() if v['n'] < 30}
print(f"Dead cells (n<30): {len(dead)}")
for k, v in sorted(dead.items(), key=lambda x: x[1]['n'])[:5]:
  print(f"  {k}: n={v['n']}, prob={v.get('measured_prob', 0):.2%}")
PYEOF

# Ledger crudo (último 100 eventos calibrados)
tail -100 data/calibration_ledger.csv 2>/dev/null | cut -d, -f1-5,8,9 || echo "NO LEDGER"
```

## Diagnóstico
- **n<30**: experimental, no confiar todavía
- **n>100**: medición solida
- **drift >10% último mes**: posible cambio de régimen, recalibrar
- **prob outlier (>90% o <10%)**: validar manualmente (sesgo de selección?)

## Fuente propia
`scripts/compass_calibrate.py` (cron 4am) → `data/compass_calib.json`
