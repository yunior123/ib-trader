#!/bin/bash
# shadow.sh — modo SOMBRA en vivo (orden Yunior 2026-07-21): la engine corre
# contra los datos REALES de TWS (bar bridge + whale watch + opt chain vivos)
# pero JAMAS manda ordenes: cada operacion simulada queda en el ledger JSONL
# con NBBO/timestamps reales, para comparar despues contra el grafico
# (scalper/shadow_report.py). 100% compatible con la ley SEÑAL-SOLAMENTE.
#
# Uso:   ./scalper/shadow.sh          # foreground con banners
# Parar: Ctrl-C  (o crear scalper/HALT para bloquear entradas)
cd "$(dirname "$0")/.."
[ -x scalper/whale_scalper ] || ./scalper/build.sh
mkdir -p scalper/ledger
echo "SHADOW: datos reales, fills simulados, ledger en scalper/ledger/"
echo "Requiere vivos: ibkr_bar_bridge (NBBO QQQ), opt_whale_watch (alertas), opt_chain_cache (cadena)"
exec ./scalper/whale_scalper --sim --data data --ledger scalper/ledger --banners
