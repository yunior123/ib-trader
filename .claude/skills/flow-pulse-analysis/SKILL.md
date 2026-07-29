---
name: flow-pulse-analysis
description: Analyze flow_pulse.cpp output — captain hierarchy (SPY/QQQ market, SMH memory), opposing-captain vetoes, probability by flow type (puts spike vs calls spike), timing of herd signals (DANGER when 3+ tickers align). Use for real-time confirmation when captain is dominant.
---

# Flow Pulse — Jerarquía de capitanes

Detector de flujo de opciones con jerarquía: capitanes (SPY/QQQ/SMH) prevalecen sobre nombres.

## Jerarquía (orden 2026-07-22)
1. **SPY/QQQ** = capitanes mercado
2. **SMH** = capitán memoria (tropa: MU/SKHY/DRAM/SNDK/WDC/STX/LRCX/NVDA/AMD/TSM/ASML)
3. **Otros** = tropa, vetados si capitán opuesto

## Regla
- **SPY puts spike**: rebote mercado SIEMPRE (evidencia 7/18, 7/21, 7/29)
- **SMH puts spike**: rebote memoria sector
- **Conflict**: NVDA calls + SPY puts → SPY prevalece, NVDA sin efecto
- **2 lecturas**: confirma antes de sonar alarma

## Comando
```bash
cd ~/ib-trader

# Output bruto flow_pulse
./bin/flow_pulse 2>&1 | head -20

# O parse logs si está grabado
tail -50 logs/flow_pulse.log 2>/dev/null | grep -E "(SPIKE|DANGER|CAPTAIN)" || echo "SIN LOG"
```

## Probabilidad medida
- **Puts spike**: 70-80% rebound confirmado en +15min (data 2026-07 backtest)
- **Calls spike**: 50-60% (menos fiable, puede ser continuación o acumulación)
- **Captain-opposite**: prob anulada (prevalece capitán)

## Fuente propia
`scripts/flow_pulse.cpp` (v4, 2026-07-28)
