---
name: ibkr-connection-doctor
description: Diagnose IBKR Gateway/TWS connectivity — check ports 7496/7497, RequestTimeout errors (10190 tape limit, 20 timeout for qualifyContracts), MarketDataType (delayed=2 forbidden), order flow, data freshness. Use when bars/NBBO stale or orders stuck.
---

# IBKR Connection Doctor — Diagnóstico Gateway

Verificar salud de conexión TWS/Gateway.

## Check rápido
```bash
cd ~/ib-trader

# ¿Puertos vivos? (7496=paper/live, 7497=otro)
nc -zv localhost 7496 && echo "PAPEL/LIVE OK" || echo "PUERTO MUERTO"
nc -zv localhost 7497 && echo "PAPEL/LIVE-ALT OK" || echo "PUERTO MUERTO"

# ¿Bridge connected?
ps aux | grep ibkr_bar_bridge | grep -v grep || echo "BRIDGE DOWN"

# ¿Errores gateway en logs?
grep -i "error\|timeout\|10190\|10189" logs/ibkr_bar_bridge.log | tail -5 || echo "SIN ERRORES RECIENTES"

# ¿NBBO fresco? (últimas 2 líneas == últimos 10s?)
stat -f %Sm -t "%H:%M:%S" data/nbbo_QQQ.txt && echo "FRESCO (last 10s)" || echo "STALE (>1min)"

# ¿Modo? (paper vs live)
cat scripts/ib_mode.sh | grep "PORT=" | head -1
```

## Diagnóstico profundo
```bash
# Error 10190 = tape limit (max 5 tickers simultáneamente)
grep "10190\|reqTickByTickData" logs/ibkr_bar_bridge.log | head -3

# Error 10189 = undefined contract
grep "10189" logs/ibkr_bar_bridge.log | head -3

# RequestTimeout de 20s (cause de cuelgues en qualifyContracts)
grep "RequestTimeout\|ib.RequestTimeout" scripts/ibkr_bar_bridge.py

# ¿MarketDataType frozen? (línea ~352)
grep -A2 -B2 "reqMarketDataType" scripts/ibkr_bar_bridge.py | head -10
```

## Fixes comunes
1. **Puertos deadlocked**: `pkill -f ib_insync; sleep 2; pkill -f python3`
2. **Timeout 10190**: reducer tape a 3 tickers (SMH capital), esperar 30s
3. **Delayed data (type=2)**: verificar `reqMarketDataType(1)` en línea 352
4. **Order stuck**: `./scripts/cancel_all_bot_orders.py`, check account

## Fuente propia
`scripts/ibkr_bar_bridge.py` (daemon conexión)
