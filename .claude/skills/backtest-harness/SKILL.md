---
name: backtest-harness
description: Run full backtest suite — compass/signals vs bars 1m historical, triple-barrier setup (target/stop/time), Sharpe/MDD/WR metrics, calibration ledger feedback, compare paper vs live slippage. Use for validating new signal changes before live.
---

# Backtest Harness — Suite de pruebas

Ejecutar backtests completos con métricas.

## Setup
```bash
cd ~/ib-trader

# Ver configuración
cat scripts/backtest_harness.py | head -50 | grep -E "class|def|TARGET|FLOOR|TRAIL"
```

## Correr backtest
```bash
# Backtest flota completa (30 tickers), últimas 2 semanas
python3 scripts/backtest_harness.py --fleet --days 14 --out backtest_results.json

# O un ticker específico + verbose
python3 scripts/backtest_harness.py --sym NVDA --days 14 --verbose --show-trades

# Con nuevas parámetros (BB_STD, TARGET, etc.)
python3 scripts/backtest_harness.py --fleet --days 14 \
  --param BB_STD=2.5 \
  --param TARGET=3.5 \
  --param FLOOR=0.8

# Backtest triple-barrier (target/stop/max-hold)
python3 scripts/backtest_harness.py --sym NVDA --days 14 \
  --target 4.0 --stop 1.5 --hold-minutes 45
```

## Métricas salida
```json
{
  "sym": "NVDA",
  "trades": 47,
  "wins": 28,
  "losses": 19,
  "wr": 0.596,
  "avg_win": 2.15,
  "avg_loss": -1.08,
  "pf": 2.31,
  "mdd": -8.3,
  "sharpe": 1.45,
  "sortino": 2.11
}
```

## Calibración automática
- Backtest genera `calibration_ledger.csv` (cada trade → entrada en celda setup×régimen)
- Cron 4am: `compass_calibrate.py` lee ledger → actualiza `compass_calib.json`

## Comparar paper vs live
```bash
# Paper slippage = mitad de los spreads NBBO medidos
# Live slippage = spread completo + comisión IB

python3 << 'PYEOF'
import json
bt = json.load(open('backtest_results.json'))
print(f"Backtest Sharpe: {bt.get('sharpe', 0):.2f}")
print(f"Esperado live (~90% de sharpe): {bt.get('sharpe', 0)*0.9:.2f}")
PYEOF
```

## Fuente propia
`scripts/backtest_harness.py` + `scripts/replay.cpp` (core engine)
