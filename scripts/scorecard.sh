#!/bin/zsh
# scorecard.sh — expectancy REAL de las señales de dinero de la flota.
# Solo cuenta lineas BUY/SELL en vivo (las WARMUP del replay quedan fuera —
# desde 2026-07-10 el ops log las etiqueta). Uso: scripts/scorecard.sh [dias]
cd "$(dirname "$0")/.." || exit 1
DAYS="${1:-30}"
SINCE=$(date -v-${DAYS}d '+%Y-%m-%d')

echo "== scorecard señales de dinero (desde $SINCE, sin WARMUP) =="
for f in dram nok spcx tsla; do
  L="${f}_operations.log"
  [[ -f $L ]] || continue
  awk -v since="$SINCE" -v sym="${f:u}" '
    $1 >= since && !/WARMUP/ && /SELL NOW|SELL-STOP|VENDER/ {
      if (match($0, /PnL [+-][0-9.]+%/)) {
        pnl = substr($0, RSTART+4, RLENGTH-5) + 0
        n++; tot += pnl; if (pnl > 0) w++
        if (/SELL-STOP/) stops++
      }
    }
    $1 >= since && !/WARMUP/ && /BUY NOW|COMPRAR/ { buys++ }
    END {
      if (n + buys == 0) { printf "  %-5s sin señales\n", sym; exit }
      printf "  %-5s %d buys, %d sells (%d wins, %d stops) | PnL total %+.1f%% | media %+.2f%%/trade\n",
             sym, buys, n, w, stops, tot, n ? tot/n : 0
    }' "$L"
done
echo "(bruto, sin comisiones ~\$1/orden IBKR — restar ~0.1-0.5% por roundtrip segun tamaño)"
