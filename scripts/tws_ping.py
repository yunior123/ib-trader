#!/usr/bin/env python3
"""tws_ping.py — prueba mínima de conectividad IBKR TWS (señal-solamente, solo lee).
Confirma que ib_async conecta y que llega barra 1-min en vivo. clientId 61 (libre)."""
import sys
from ib_async import IB, Stock

sym = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 7496
ib = IB()
try:
    ib.connect("127.0.0.1", port, clientId=61, timeout=8)
except Exception as e:
    print(f"NO CONECTA a TWS :{port} — {e}"); sys.exit(1)
print(f"conectado TWS :{port} (server v{ib.client.serverVersion()})")
c = Stock(sym, "SMART", "USD")
ib.qualifyContracts(c)
bars = ib.reqHistoricalData(c, endDateTime="", durationStr="1 D",
                           barSizeSetting="1 min", whatToShow="TRADES",
                           useRTH=False, keepUpToDate=False)
print(f"{sym}: {len(bars)} barras 1-min")
if bars:
    b = bars[-1]
    print(f"última: {b.date}  O{b.open} H{b.high} L{b.low} C{b.close} V{b.volume}")
ib.disconnect()
