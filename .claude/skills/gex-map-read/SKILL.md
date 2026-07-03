---
name: gex-map-read
description: Read gex_snapshot.json and narrate gamma exposure map — flip zones, dealer pressure, imane levels, POC, regime (NEG/neutral/POS), and probability of move. Use for premarket briefing or mapa verification.
---

# GEX Map Narration — Leer el mapa gamma

Lee mapa GEX calculado en casa (source única `scripts/gex_snapshot.py`) e interpreta para trading.

## Comando
```bash
cd ~/ib-trader
cat data/gex_snapshot.json | python3 -m json.tool | head -50
python3 scripts/gex_snapshot.py --sym NVDA  # recomputa on-demand
```

## Estructura de salida (JSON)
```
{
  "sym": "NVDA",
  "spot": 119.45,
  "timestamp": "2026-07-29T15:45:00Z",
  "flip": { "type": "call_to_put", "strike": 120.0, "prob": 0.62 },
  "gex": { "strike": 118.5, "gamma_exp": 2.3, "regime": "NEG" },
  "walls": { "calls": [{"strike": 125.0, "oi": 45000}], "puts": [...] },
  "poc": { "gamma_poc": 119.0, "delta_poc": 118.75 },
  "probability": { "up": 0.55, "down": 0.45 }
}
```

## Lectura rápida
1. **Flip**: ¿llama→venta = techo? ¿venta→llama = piso?
2. **GEX NEG**: acelerador (whipsaw risk)
3. **Walls**: muros próximos son imanes
4. **POC**: point of max gamma concentration
5. **Prob**: probabilidad de movimiento (calibrada)

## Fuente propia
`scripts/gex_snapshot.py` → `data/gex_snapshot.json` (computado 4am + on-demand)
