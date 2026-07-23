#!/usr/bin/env bash
# dedup_regression.sh — combo_engine backtest debe DESCARTAR barras con
# timestamp duplicado/desordenado (misma semantica que live `b.t<=last_seen`).
# Sin dedup, una barra 5m repetida en el feed envenena la BB rodante ~20 barras
# y produce una señal DISTINTA -> backtest que miente. Este test lo veta.
set -euo pipefail
cd "$(dirname "$0")/../.."
BIN=engines/combo_engine
BARS=data/backtest/bars3mo5m_nvda.csv
FLOW=data/whale_flow_hist.jsonl
[ -x "$BIN" ] || { echo "FALTA $BIN (compilar primero)"; exit 2; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# duplica la barra 09:55 (epoch 1784728500), justo dentro de la ventana BB que
# alimenta el candidato de las 10:00 — el caso que probamos que flipa la señal.
awk -F, '{print; if ($1=="1784728500") print}' "$BARS" > "$TMP/dup.csv"
"$BIN" --backtest "$BARS"      --sym NVDA --flow "$FLOW" --out "$TMP/clean.csv" 2>/dev/null
"$BIN" --backtest "$TMP/dup.csv" --sym NVDA --flow "$FLOW" --out "$TMP/dup_out.csv" 2>/dev/null
if diff -q <(grep -v '^epoch' "$TMP/clean.csv") <(grep -v '^epoch' "$TMP/dup_out.csv") >/dev/null; then
    echo "dedup_regression OK — barra duplicada ignorada, señales identicas"
else
    echo "dedup_regression FAIL — la barra duplicada cambio las señales:"
    diff "$TMP/clean.csv" "$TMP/dup_out.csv" || true
    exit 1
fi
