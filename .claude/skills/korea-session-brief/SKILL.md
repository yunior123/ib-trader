---
name: korea-session-brief
description: Korea overnight brief (KRX 20:00→02:30 ET, SKY/Samsung/KOSPI leads memory complex 13h early) — read bars_krx archives, compare Korea-to-US leadership, identify dip opportunities, check fleet_sleep/wake logic, influence on SMH/MU/ASML/NVDA.
---

# Korea Session Brief — Overnight antes del US

Leer sesión Korea (KRX dom-jue 20:00→02:30 ET), influencia en flota.

## Archivos
```bash
cd ~/ib-trader

# Barras Korea archivadas (~1h delay postmarket)
ls data/bars_krx_1m* data/nbbo_skhynix.txt data/nbbo_samsung.txt 2>/dev/null

# Cuál fue el close Korea anoche?
tail -1 data/nbbo_kospi.txt 2>/dev/null | cut -d, -f2,3 | xargs echo "KOSPI"
tail -1 data/nbbo_skhynix.txt 2>/dev/null | cut -d, -f2,3 | xargs echo "SKHY"
```

## Análisis
```bash
# ¿Korea lideró? (KOSPI +0.5% → SMH/MU típicamente siguen)
python3 << 'PYEOF'
import subprocess, json
def last_line(f):
  try: return subprocess.check_output(['tail', '-1', f'data/{f}']).decode().strip().split(',')
  except: return [None]*3
kospi = last_line('nbbo_kospi.txt')
if kospi[0]:
  print(f"KOSPI: {kospi[1]} ({kospi[2]} chg)")
  print("Implicación: SMH/MU siguen en ~30min + memory complex")
PYEOF
```

## Fleet impact
- **Korea UP >= +0.8%**: SMH probable UP, veto SHORT de memoria
- **Korea DOWN >= -0.8%**: MU/SKHY/ASML dip esperado, compra técnica
- **Leadership**: Samsung/SK Hynix (fabricación) > KOSPI broad > ETFs (EWY)

## Configuración
- `scripts/fleet_sleep.py`: apaga daemons durante "dead hours" (2:30-8am ET)
- `scripts/fleet_wake.py`: enciende a las 8:30am et
- Revisar si `data/FLEET_HOURS_MISSING` existe (flag si horario se rompió)

## Fuente propia
`scripts/korea_bar_bridge.py` → archivos NK + influencia calculada en `index_breadth.py`
