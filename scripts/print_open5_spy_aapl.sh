#!/bin/zsh
# 09:35 ET (open+5): regenera arbol + plan + valla de SPY y AAPL con dato VIVO y los MANDA AL HP.
# Yunior 2026-07-30: "print via my printer hp". Senal-solamente.
cd /Users/yuniorrodriguezosorio/ib-trader || exit 1
DAY=$(date +%Y-%m-%d)
DEST=$HOME/Desktop/ib-trader/hoy/planes-$DAY
PRINTER=HP_OfficeJet_Pro_9120e_Series
OUT=data/open5_$(date +%Y%m%d).txt
{
  echo "### OPEN+5 $(date '+%Y-%m-%d %H:%M:%S %Z')"
  python3 scripts/tree_sheets.py SPY AAPL
  python3 scripts/tree_sheets_html.py SPY AAPL
  echo "--- VALLA ---"
  python3 scripts/em_envelope.py --sym SPY --print | tail -30
  python3 scripts/em_envelope.py --sym AAPL --print | tail -30
} > "$OUT" 2>&1

# planes 3-pag (incluye arbol de escenarios) -> papel
IBT_ALLOW_PRINT=1 ./scripts/print_plans.sh SPY,AAPL --print >> "$OUT" 2>&1
# hoja de arboles HTML -> PDF -> papel
PDF="$DEST/ARBOLES_open5_spy_aapl.pdf"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --no-pdf-header-footer --print-to-pdf="$PDF" \
  "file:///Users/yuniorrodriguezosorio/ib-trader/data/trees/arboles.html" >> "$OUT" 2>&1
if [[ -s "$PDF" ]]; then lpr -P $PRINTER "$PDF" && echo "IMPRESO ARBOLES open5" >> "$OUT"
else echo "FALLO: no se genero $PDF" >> "$OUT"; fi
echo "LISTO $OUT"
