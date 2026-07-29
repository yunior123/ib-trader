---
name: strangle-scanner
description: Find cheap strangles (wide bid-ask distance vs straddle, low premium, high IV rank) — compare expected move (implied vol) vs realized volatility (historical), identify skew outliers (call side expensive), optimal expiry for leverage. Use for 0DTE or weekly earnings hedge.
---

# Strangle Scanner — Buscar estrangle barato

Escanear cadenas de opciones buscando estrangle líquido barato.

## Definición
- **Strangle = (put @ -2σ) + (call @ +2σ)** en lugar de ATM straddle
- **Ventaja**: premium bajo, riesgo de loss limitado pero ancho
- **Cazo**: IV spike = strangle caro, mala entrada

## Comando
```bash
cd ~/ib-trader

# Scan todas las cadenas frescas (opt_chain_*.txt)
python3 << 'PYEOF'
import os, json, re
from pathlib import Path

def scan_strangle(sym):
  path = Path('data') / f'opt_chain_{sym}.txt'
  if not path.exists(): return None
  
  lines = path.read_text().strip().split('\n')
  if len(lines) < 3: return None
  
  header = lines[0].split('|')
  contracts = [dict(zip(header, line.split('|'))) for line in lines[1:]]
  
  # Filter OTM calls/puts, compare straddle vs strangle
  opts = sorted(contracts, key=lambda x: float(x.get('strike', 0)))
  spot = float(opts[len(opts)//2].get('last', 100))
  
  for i, opt in enumerate(opts):
    strike = float(opt['strike'])
    bid = float(opt.get('bid', 0))
    ask = float(opt.get('ask', 0))
    mid = (bid + ask) / 2
    
    # Strangle candidates: delta~0.25-0.35 range
    if 0.9 < strike/spot < 1.1 and bid > 0:
      print(f"{sym} {opt.get('expiry')} {strike:7.1f} bid={bid:6.2f} ask={ask:6.2f} spread={ask-bid:5.2f}")

for sym in ['NVDA', 'QQQ', 'SPY']:
  scan_strangle(sym)
PYEOF

# O usar opt_quick si compilado
./bin/opt_quick --sym NVDA --scan-strangle
```

## Filtro de qualidad
- **Spread <= 3% del mid**: líquido
- **OI > 500**: suficiente libro
- **IV rank > 50%**: no caro históricamente
- **Expected move**: (straddle_price / spot / sqrt(T)) > realized_vol ? → compra

## Fuente propia
`scripts/opt_quick.cpp` + `data/opt_chain_*.txt` (IBKR cache)
