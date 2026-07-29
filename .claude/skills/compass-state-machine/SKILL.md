---
name: compass-state-machine
description: Understand compass.cpp state machine — drivers (levels, momentum, gamma, book, flip), amplitude (lash/rebound/scalp), decay over time, probability by bucket, when flecha toggles direction. Use for debugging "why did compass say UP when price was down?".
---

# Compass — Máquina de estados de flecha

La brújula (`scripts/compass.cpp`) fija dirección del próximo movimiento.

## Estados
1. **NO OPINION** → wait calibration
2. **UP/DOWN** → fijo hasta convergencia de drivers
3. **SCALP** → neutral alta frecuencia (no apto para hold)

## Drivers (en orden de prevalencia)
```
1. Levels: ¿rebote de soporte reciente? → UP
2. Momentum: ¿Z-score RSI/MACD? → señal fuerte
3. Gamma: ¿GEX positivo = acelerador? o ¿NEG = trampa?
4. Book: ¿Q-balance sesgo? (comprador vs vendedor dominante)
5. Flip: ¿cruce de muros OI próximo? → probability de giro
```

## Decay
- Compass "envejece": cada barra sin confirmation, prob decae 10%
- A los 30 min (15 barras 1m) sin reconfirmación: "STALE"
- Reset en nuevos niveles impresos

## Debug
```bash
cd ~/ib-trader

# Ver estado compass actual (JSON)
cat data/compass_out.json | python3 -m json.tool | head -30

# Ver drivers de última computación
python3 << 'PYEOF'
import json
d = json.load(open('data/compass_out.json'))
print(f"Direction: {d.get('direction')}")
print(f"Prob: {d.get('probability'):.2%}")
print(f"Drivers: {json.dumps(d.get('drivers', {}), indent=2)}")
print(f"Amplitude: {d.get('amplitude_type')} ({d.get('amplitude_points'):.2f})")
PYEOF

# Recomputar manualmente (0DTE)
./bin/compass --sym NVDA --force-recompute
```

## Cuando confiar
- **n >= 30 en compass_calib.json para ese bucket**: medición solida
- **Múltiples drivers alineados** (>= 2): consenso
- **!STALE** (timestamp < 15 barras): fresco
- **Prob >= 55%**: umbral Yunior "commitment" de compass

## Fuente propia
`scripts/compass.cpp` (máquina estados C++23, 2026-07-15)
