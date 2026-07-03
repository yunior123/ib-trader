---
name: order-engine-manual
description: Manual execution of options orders via order_engine C++ — buy/sell/cancel/modify contracts, paper-first safety switch, disarm-on-exit guard, double-key (password) for live, trailing stops, show state. Use for 0DTE tactical entries when rules permit.
---

# Order Engine — Motor de órdenes

Motor C++ que coloca órdenes REALES de opciones en TWS.

## Modo (paper vs live)
```bash
cd ~/ib-trader

# Ver modo actual
cat scripts/ib_mode.sh | grep PORT=

# Cambiar a PAPER (puerto 7497)
./scripts/ib_mode.sh paper

# Cambiar a LIVE (puerto 7496, requiere YUNIOR password)
./scripts/ib_mode.sh live  # pide passcode
```

## Compilar order_engine
```bash
cd ~/ib-trader
cd order_engine
./build.sh  # crea bin/order_engine (C++23)
```

## Ejecutar (ejemplos)
```bash
# Estado actual (órdenes abiertas, posiciones)
./bin/order_engine --status

# BUY 1 contrato QQQ call 430C (nearest exp)
./bin/order_engine --buy QQQ 430C 1 --limit 2.50 --tif gtc

# SELL posición (exit)
./bin/order_engine --sell QQQ 430C 1 --limit 2.70 --tif day

# CANCEL orden abierta (por ID)
./bin/order_engine --cancel ORDER_ID_123

# MODIFY trail (trailing stop)
./bin/order_engine --trail ORDER_ID_123 --distance 0.50

# Paper mode check (double-key off)
./bin/order_engine --paper --buy SPY 560C 1
```

## Seguridades (CRÍTICAS)
1. **Paper first**: `./scripts/ib_mode.sh paper` antes de TODO
2. **Disarm on exit**: cierra sesión → anula órdenes GTC abiertas
3. **Double-key**: live requiere passcode (Yunior solo)
4. **Max per-symbol**: límite configurado en `config/order_engine.json`

## Fuente
`order_engine/` (subdirectorio C++23, motor independiente)
