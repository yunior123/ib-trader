#!/bin/zsh
# fleet_keepalive_start.sh — arranca los 4 keepalives de los signal bots
# (16 bots: dram/nok/spcx/tsla + nvda/txn/tsm/amd/intc/asml/aapl + gld/qqq + slv/cper/uso). Idempotente: si un keepalive ya corre, no lo duplica
# (dos keepalives del mismo bot se matarian el bot mutuamente). launchd lo
# re-ejecuta cada 5 min (StartInterval) = watchdog de los watchdogs.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
for b in dram nok spcx tsla nvda txn tsm amd intc asml aapl gld qqq slv cper uso skhynix samsung kospi; do
  if ! pgrep -f "scripts/${b}_keepalive.sh" >/dev/null; then
    nohup zsh "$ROOT/scripts/${b}_keepalive.sh" >/dev/null 2>&1 &
    echo "$(date) fleet: ${b}_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
  fi
done

# daemon IBKR de flota (orden 2026-07-11 "ready for ibkr, alpaca fallback"):
# SIP bars 1m + NBBO a data/*_ibkr.txt / nbbo_*.txt; auto-activa al comprar
# el sub ($10 SIP bundle, >= USD 500 equity). Reader C++ preferencia+fallback.
if ! pgrep -f "ibkr_bar_bridge.py --daemon" >/dev/null; then
  nohup ./venv/bin/python scripts/ibkr_bar_bridge.py --daemon NOK SPCX DRAM TSLA NVDA TXN TSM AMD INTC ASML AAPL GLD QQQ SLV CPER USO >> bridge_ibkr_fleet.log 2>&1 &
  echo "$(date) fleet: ibkr fleet daemon lanzado (pid $!)" >> fleet_autostart.log
fi

# bridge KRX realtime (SK Hynix + Samsung) — sub Korea waived cubre la API
# (verificado 2026-07-12): mercado de memoria/DRAM en vivo y gratis, lider ~13h
# antes que EE.UU. para MU/DRAM. Escribe data/bars_{skhynix,samsung}.txt.
if ! pgrep -f "scripts/korea_bar_bridge.py" >/dev/null; then
  nohup ./venv/bin/python scripts/korea_bar_bridge.py --daemon >> bridge_korea.log 2>&1 &
  echo "$(date) fleet: korea bridge lanzado (pid $!)" >> fleet_autostart.log
fi

# ejecutor de ETFs apalancados (dinero real cuando TFSA >= 450 USD + etf_armed)
if ! pgrep -f "scripts/executor_keepalive.sh" >/dev/null; then
  nohup zsh "$ROOT/scripts/executor_keepalive.sh" >/dev/null 2>&1 &
  echo "$(date) fleet: executor_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
fi
