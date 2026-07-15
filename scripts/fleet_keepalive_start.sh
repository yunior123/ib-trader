#!/bin/zsh
# fleet_keepalive_start.sh — arranca los 4 keepalives de los signal bots
# (16 bots: dram/nok/spcx/tsla + nvda/txn/tsm/amd/intc/asml/aapl + gld/qqq + slv/cper/uso). Idempotente: si un keepalive ya corre, no lo duplica
# (dos keepalives del mismo bot se matarian el bot mutuamente). launchd lo
# re-ejecuta cada 5 min (StartInterval) = watchdog de los watchdogs.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
for b in dram nok spcx tsla nvda txn tsm amd intc asml aapl gld qqq slv cper uso skhy skhynix samsung kospi; do
  if ! pgrep -f "scripts/${b}_keepalive.sh" >/dev/null; then
    nohup zsh "$ROOT/scripts/${b}_keepalive.sh" >/dev/null 2>&1 &
    echo "$(date) fleet: ${b}_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
  fi
done

# daemon IBKR de flota — FUENTE UNICA desde 2026-07-15 ("connect to ibkr
# only"; subs NA reales compradas: Cboe One + Network A/B/C, 10089 muerto).
# SIP warm-up historico + bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt.
# Reader C++ en modo IBKR-ONLY (sin alpaca; ALPACA_FALLBACK=1 revive dual).
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup ./venv/bin/python scripts/ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO SKHY >> bridge_ibkr_fleet.log 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >> fleet_autostart.log
fi

# bridge KRX realtime (SK Hynix + Samsung) — sub Korea waived cubre la API
# (verificado 2026-07-12): mercado de memoria/DRAM en vivo y gratis, lider ~13h
# antes que EE.UU. para MU/DRAM. Escribe data/bars_{skhynix,samsung}.txt.
if ! pgrep -f "scripts/korea_bar_bridge.py" >/dev/null; then
  nohup ./venv/bin/python scripts/korea_bar_bridge.py --daemon >> bridge_korea.log 2>&1 &
  echo "$(date) fleet: korea bridge lanzado (pid $!)" >> fleet_autostart.log
fi

# TWS watchdog (2026-07-15, tras 75 min de ceguera): vigila puerto 7496 en
# ventanas de mercado, relanza TWS colgado y GRITA por el login (que siempre
# es del humano). El eslabon debil del dia fue TWS, no las señales.
if ! pgrep -f "scripts/tws_watchdog.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/tws_watchdog.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: tws_watchdog lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# bargain bot (2026-07-15): gangas en flota + top gainers + oversold, vetadas
# por TradingAgents — solo BUY notifica. Signal-only, cada 10 min en RTH.
if ! pgrep -f "scripts/bargain_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/bargain_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: bargain_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi

# ejecutor de ETFs apalancados (dinero real cuando TFSA >= 450 USD + etf_armed)
if ! pgrep -f "scripts/executor_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/executor_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: executor_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi
