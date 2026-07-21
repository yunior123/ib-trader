#!/bin/zsh
# weekly_autoimprove.sh — el sistema se mejora SOLO cada semana (domingo noche, antes
# de la semana Korea). Refresca los patrones/formas de 6m de cada skill, recalcula el
# follow-through empírico de los patrones, recalibra probabilidades, corre los tests, y
# reporta qué aprendió. Aditivo, señal-solamente.
cd "$(dirname "$0")/.." || exit 1
LOG=autoimprove.log
echo "\n$(date) === AUTO-MEJORA SEMANAL ===" >> $LOG
# 1) refrescar patrones 6m + forma intradía en las 26 skills (stats por ticker al día)
./venv/bin/python scripts/skill_patterns_refresh.py >> $LOG 2>&1
# 2) recalcular follow-through empírico de patrones (H&S/dobles/triángulos)
./venv/bin/python scripts/pattern_detect.py --fleet >> $LOG 2>&1
# 3) recalibrar probabilidades con todo el histórico acumulado
./venv/bin/python scripts/calibration_ledger.py grade >> $LOG 2>&1
./venv/bin/python scripts/calibration_ledger.py calibrate >> $LOG 2>&1
# 4) correr los tests (que nada se rompió con los datos nuevos)
PYT=$(./venv/bin/python -m pytest tests/ -q 2>&1 | tail -1)
CPP=$(zsh tests/cpp/run.sh 2>&1 | grep -E 'PASS:|FAIL:' | tr '\n' ' ')
echo "tests: py[$PYT] cpp[$CPP]" >> $LOG
# 5) reporte de lo aprendido (qué setups ya tienen muestra suficiente)
echo "--- calibración medida ---" >> $LOG
./venv/bin/python scripts/calibration_ledger.py report >> $LOG 2>&1
# 6) email + notificación con el resumen
REP=$(./venv/bin/python scripts/calibration_ledger.py report 2>/dev/null | head -12)
osascript -e 'display notification "Patrones/formas refrescados, calibración recalculada, tests corridos" with title "🧠 ib-trader auto-mejora semanal"' 2>/dev/null
./venv/bin/python - <<PYEOF >> $LOG 2>&1
import os,requests
def gv(k):
    for ln in open("feeds.env"):
        if ln.startswith(k+"="): return ln.split("=",1)[1].strip().strip('"').strip("'")
try:
    requests.post("https://api.resend.com/emails",timeout=20,
      headers={"Authorization":f"Bearer {gv('RESEND_KEY')}","Content-Type":"application/json"},
      json={"from":"onboarding@resend.dev","to":[gv('RESEND_TO')],
            "subject":"🧠 Auto-mejora semanal ib-trader",
            "text":"Patrones 6m + forma intradía refrescados en 26 skills. Patrones follow-through recalculado. Calibración recalibrada. Tests corridos.\n\n"+'''$REP'''})
except Exception as e: print("email fallo",e)
PYEOF
echo "$(date) auto-mejora fin" >> $LOG
