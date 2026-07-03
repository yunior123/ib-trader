---
name: earnings-week-map
description: Map earnings and macro calendar for the fleet (NVDA, TSLA, etc.) plus FOMC/CPI/NFP — identify gap risk, blackout periods (no 0DTE day-of), implied move by exp, hedging zones. Use for weekly planning and earnings veto logic.
---

# Earnings Week Map — Calendario de catalizadores

Mapear earnings de la flota + macro eventos para el trading.

## Datos
```bash
cd ~/ib-trader

# Earnings confirmados (sin adivinanzas)
python3 scripts/macro_calendar.py --source ibkr --show-fleet
# Salida: NVDA 2026-07-30 (postmarket), TSLA 2026-08-06 (postmarket), ...

# O revisar docs/
ls docs/ | grep -i "earnings\|calendar" | head -5
cat docs/EARNINGS-WEEK-2026-07.md 2>/dev/null || echo "SIN DOC"

# FOMC/CPI/NFP próximos (macro impactful)
python3 << 'PYEOF'
import json
from datetime import datetime, timedelta
d = json.load(open('data/macro_calendar.json'))
today = datetime.now().date()
for evt in [e for e in d if datetime.fromisoformat(e['date']).date() >= today]:
  print(f"{evt['date']}: {evt['event']}")
PYEOF
```

## Plan por earnings day
1. **Flag 0DTE prohibido ese día**: no comprar opciones, solo acciones/puts de stop
2. **IV previa** (implied move estimado): `option_price / (spot * sqrt(T))` donde T=días a earnings
3. **Implied vs realizado**: backtest muestra qué % de moves son outliers
4. **Support/resistance+muros**: dobles márgenes ese día

## Veto en orden_engine
```cpp
// order_engine.cpp línea ~300
if (is_earnings_today(sym)) {
  if (contract.expiry == today) {
    return ORDER_VETO("0DTE on earnings");
  }
}
```

## Fuente propia
`scripts/macro_calendar.py` + `data/macro_calendar.json` (FOMC confirmados)
