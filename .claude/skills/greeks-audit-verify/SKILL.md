---
name: greeks-audit-verify
description: Audit greeks (delta, gamma, theta, vega) against Black-Scholes and IBKR cache — verify chain math, IV inversion, OI provenance, and parity violations. Use for debugging option pricing anomalies or validating chain_full backfills.
---

# Greeks Audit — Verificar deltas/gammas vs BS

Auditar integridad de griegas en cadena viva o histórica. Detecta IV inconsistentes, deltas imposibles, gamma spikes, OI discrepancias, parity breaks.

## Verificación rápida
```bash
cd ~/ib-trader
python3 scripts/gex_core.py --chain-audit NVDA
python3 scripts/gex_core.py --chain-audit NVDA --verbose
```

## Fuentes
- `scripts/gex_core.py` (línea ~150-200: `invert_chain_iv()`, `bs_delta()`, `bs_gamma()`)
- `data/opt_chain_<sym>.txt` (cache IBKR, ~45min)
- `data/chain_full_*/chain_full_<sym>.json` (Polygon snapshots)

## Casos
1. GEX flip roto → audit muestra parity breaks
2. Backfill validation → IV/griegas en `poly_opt_bars` correctas?
3. IBKR vs Polygon divergence → audit ambas, compara
4. Max pain sospechoso → ¿OI creíble?

## Salida
JSON: [strike, bid, ask, delta_reported, delta_bs, gamma, oi, violations[]].
