---
name: replay-debug
description: Run ./bin/replay with exact date/sym to debug signal timing, compare BUY/SELL outputs, spot missed entries or false positives. Use for post-mortem analysis of why a signal did/didn't fire.
---

# Replay — Debugger de señales

Recrear ejecución de un bot en fecha histórica exacta.

## Compilar
```bash
cd ~/ib-trader
./scripts/build_replay.sh  # compile bin/replay
```

## Uso
```bash
# Replay NVDA 2026-07-28
./bin/replay --sym NVDA --date 2026-07-28

# Con detalle (cada bar + cálculos intermedios)
./bin/replay --sym NVDA --date 2026-07-28 --verbose

# Comparar señal vs compass
./bin/replay --sym NVDA --date 2026-07-28 --compare-compass

# Rango (múltiples días)
./bin/replay --sym NVDA --start 2026-07-22 --end 2026-07-28 --summary
```

## Salida
```
2026-07-28 09:45:00 NVDA bars=12 price=119.45 bb_dn=117.2 bb_up=121.3 rsi=38 signal=BUY
2026-07-28 10:02:00 NVDA price=120.10 trail=120.95 tgt=123.50 (running)
2026-07-28 10:45:00 NVDA price=120.02 bb_dn=117.5 rsi=42 (hold)
2026-07-28 14:30:00 NVDA price=121.80 reached_target=123.50 signal=SELL/TGT
```

## Debugging
1. ¿Por qué no disparó BUY? → --verbose muestra filtro que vetó
2. ¿Señal falsa? → replay muestra la siguiente barra (hit stop?)
3. ¿Compass vs bot diferente? → --compare-compass explica divergencia

## Fuente propia
`scripts/replay.cpp` + barras históricas CSV
