---
name: whale-tape-read
description: Parse whale alert tapes (opt_whale_watch logs, UW flow, P/C ratio spikes) and summarize extremes — masivo puts/calls, timing, linked ticker impacts. Use for flow confirmation or post-mortem tape analysis.
---

# Whale Tape — Leer flow_pulse y alerts

Leer alertas de ballenas en tiempo real o histórico. Detecta P/C extremos, puts masivos, calls de apertura.

## Archivos
- `logs/opt_whale_watch_<sym>.log` — historial tape (P/C ratio, strikes dominantes)
- `data/whale_alerts.txt` — alertas disparadas (timestamp, sym, ratio, strike)
- `data/flow_tape.jsonl` — tape de flujo en líneas JSON (si está grabado)

## Comandos
```bash
# Alerts de hoy
cd ~/ib-trader
tail -20 logs/opt_whale_watch_QQQ.log

# Resumen últimas 2h (desde logs/)
grep "2026-07-29 1[4-5]:" logs/opt_whale_watch_*.log | cut -d: -f3- | sort | uniq -c | sort -rn

# Parse alerts JSON si existe
cat data/whale_alerts.txt 2>/dev/null | python3 -m json.tool | tail -30
```

## Interpretación
- **P/C >= 2.0 puts**: ballena pone fondo (espera rebote)
- **P/C <= 0.35 calls**: ballena toma techo (espera venta)
- **2 lecturas consecutivas**: confirma (no crying-wolf)
- **Cruce con muro**: es imán, observar comportamiento

## Fuente propia
`scripts/opt_whale_watch.py` (v4, 2026-07-28) + logs/ automáticos
