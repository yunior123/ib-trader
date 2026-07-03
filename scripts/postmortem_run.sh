#!/bin/zsh
IBT_OSA="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/osa_gate"  # portero: respeta data/notify_off
# postmortem_run.sh — cierre del dia (16:20 ET): califica los planes contra el
# resultado real, recalibra las probabilidades medidas, y postea el repaso.
# Aditivo: si algo falla, el resto sigue. SEÑAL-SOLAMENTE.
cd "$(dirname "$0")/.." || exit 1
echo "$(date) === EOD ===" >> logs/dailyplans.log
# 1) calificar + recalibrar (el loop de aprendizaje)
./venv/bin/python scripts/calibration_ledger.py eod >> logs/dailyplans.log 2>&1
# 2) postmortem a X + archivo (lo que ya existia)
# picardia jaula->liberacion after-hours (solo a veces hay setup)
./venv/bin/python scripts/posthours_cage.py --fleet >> logs/dailyplans.log 2>&1
./venv/bin/python scripts/x_postmortem.py >> logs/dailyplans.log 2>&1
"$IBT_OSA" -e 'display notification "Calibracion actualizada + repaso posteado" with title "📚 ib-trader EOD"' 2>/dev/null
