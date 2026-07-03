---
name: signal-audit
description: Audit signal firing logs and conditioning pipeline — verify signal_conditioning.py filtering (component_bias, captain_flow_bias, inflation_score), dead cells, lost signals due to hour-of-day or fleet-conflict veto. Use for weekly calibration review and edge debugging.
---

# Signal Audit — Verificar pipeline de señales

Auditar qué señales disparon, cuáles fueron filtradas y por qué.

## Archivos log
```bash
cd ~/ib-trader

# Señales generadas (raw bots)
ls -lah logs/*_signal_bot.log 2>/dev/null | head -5

# Conditioning verdicts (hora, flota, inflación)
tail -20 logs/signal_conditioning.log 2>/dev/null

# Señales finales (después de filtros)
tail -50 data/signals_fired.jsonl 2>/dev/null | python3 -m json.tool | head -30
```

## Filtros aplicados
```python
# signals/signal_conditioning.py línea ~80-120
1. component_bias() — ¿valuation inflada? (PEG z-score)
2. captain_flow_bias() — ¿capitán opuesto? (SPY puts activos)
3. fleet_bias() — ¿consensus en contra? (>60% vendiendo)
4. timeofday_calib() — ¿hora muerta? (11:30-14:00 picadora)
5. inflation_score() — ¿empresa cara? (Fwd P/E > percentil 75)
```

## Verificar señales perdidas
```bash
python3 << 'PYEOF'
import json
from pathlib import Path

# Lee ambos archivos
fired = list(Path('data/signals_fired.jsonl').read_text().strip().split('\n'))
raw_count = len([l for l in fired if '"reason":"raw_signal"' in l])
conditioned = len([l for l in fired if '"filtered"' in l])

print(f"Raw signals: {raw_count}")
print(f"Conditioned out: {conditioned}")
print(f"Net fired: {raw_count - conditioned}")

# Top veto (por razón)
import re
vetos = {}
for line in fired:
  m = re.search(r'"veto":"([^"]+)"', line)
  if m: vetos[m.group(1)] = vetos.get(m.group(1), 0) + 1
for veto, count in sorted(vetos.items(), key=lambda x: -x[1])[:5]:
  print(f"  {veto}: {count}")
PYEOF
```

## Ajustar conditioning
```bash
# Aumentar umbral inflation (menos veto por PE)
python3 scripts/signal_conditioning.py --inflation-percentile 85

# O deshabilitar un filtro específico (debug)
python3 scripts/signal_conditioning.py --disable-captain-flow
```

## Fuente propia
`scripts/signal_conditioning.py` (línea ~50-150, filtros)
