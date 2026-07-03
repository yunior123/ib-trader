# V6_BACKTEST.md — Backtest completo del motor v6 (calibracion de prob por clase)

**Fecha**: 2026-07-16 | **Autor**: M3 (`scripts/v6_backtest.py`) | **Datos**: `data/bt_<sym>.txt` (1m Alpaca IEX, fetch pre-veda 2026-07-11), recorte a las ultimas 30 sesiones (2026-05-28..2026-07-10; SPCX solo 19 sesiones por IPO/historial corto). **Cero fetch nuevo** (guardia NO-ALPACA respetada, cero Yahoo).

## Metodo (fijado ex-ante, V6_SPEC §4)

- Replay determinista: `<sym>_signal_bot --stdin` en tmpdir aislado, env de produccion (keepalive) + `<PREFIX>_V6_PROB_MIN=0` (para OBSERVAR todas las clases, incluidas las de prior<55 como ORB que en produccion no disparan sin tabla). SECUENCIAL, un ticker a la vez (8GB).
- Split temporal 60/40 por sesiones: TRAIN = primeras 18, OOS = ultimas 12. La tabla se construye SOLO con TRAIN; el OOS se evalua en una segunda pasada con la tabla congelada presente (pass B).
- Outcome **triple-barrier** identico para todas las clases y ambos splits: entry = open del bar siguiente a la señal; WIN si toca `entry+0.75*ATR14_1m` antes que `entry-0.75*ATR14_1m` (BUY; SELL espejo); bar ambiguo = LOSS (pesimista); a 60 min sin toque: WIN si close>entry (BUY). ATR14 Wilder recalculado por el harness (misma formula que `V6ATR`).
- Prob mostrada por el bot = shrinkage bayesiano k=20 hacia el prior de la clase (la tabla guarda datos crudos `CLASE n wins wr%`).

## Veredictos por clase-ticker

- **CALIBRADA**: n_train>=20 y WR_train>=55% y n_oos>=5 y WR_oos>=0.5*WR_train y WR_oos>=55%.
- **DEGRADADA** (la honestidad manda): n_oos>=5 y **WR_oos<55%** — la fila de `data/prob_table_<sym>.txt` lleva stats train+OOS **combinadas** para que el bot muestre la prob real baja. Deliberadamente NO se usa `#FAIL_OOS`→prior del spec §4.3: eso re-mostraria un prior optimista (55-62%) y ocultaria la degradacion.
- **PRIOR**: muestras insuficientes (n_train<20) o WR_train<55% — la fila existe pero el shrinkage k=20 domina.
- **SIN_OOS**: n_oos<5, sin validacion posible.

## Resumen por ticker

| Ticker | Sesiones | Trades (train+OOS) | WR global | Train n | OOS n | Tabla |
|---|---|---|---|---|---|---|
| AAPL | 30 (2026-05-28..2026-07-10) | 68 | 50% | 36 | 32 | `data/prob_table_aapl.txt` |
| AMD | 30 (2026-05-28..2026-07-10) | 67 | 46% | 39 | 28 | `data/prob_table_amd.txt` |
| ASML | 30 (2026-05-28..2026-07-10) | 64 | 50% | 39 | 25 | `data/prob_table_asml.txt` |
| CPER | 30 (2026-05-28..2026-07-10) | 48 | 44% | 35 | 13 | `data/prob_table_cper.txt` |
| DRAM | 30 (2026-05-28..2026-07-10) | 58 | 40% | 40 | 18 | `data/prob_table_dram.txt` |
| GLD | 30 (2026-05-28..2026-07-10) | 68 | 51% | 43 | 25 | `data/prob_table_gld.txt` |
| INTC | 30 (2026-05-28..2026-07-10) | 67 | 37% | 39 | 28 | `data/prob_table_intc.txt` |
| NOK | 30 (2026-05-28..2026-07-10) | 76 | 49% | 45 | 31 | `data/prob_table_nok.txt` |
| NVDA | 30 (2026-05-28..2026-07-10) | 63 | 44% | 36 | 27 | `data/prob_table_nvda.txt` |
| QQQ | 30 (2026-05-28..2026-07-10) | 72 | 44% | 44 | 28 | `data/prob_table_qqq.txt` |
| SLV | 30 (2026-05-28..2026-07-10) | 75 | 48% | 45 | 30 | `data/prob_table_slv.txt` |
| SPCX | 19 (2026-06-12..2026-07-10) | 43 | 53% | 22 | 21 | `data/prob_table_spcx.txt` |
| TSLA | 30 (2026-05-28..2026-07-10) | 77 | 51% | 44 | 33 | `data/prob_table_tsla.txt` |
| TSM | 30 (2026-05-28..2026-07-10) | 66 | 58% | 44 | 22 | `data/prob_table_tsm.txt` |
| TXN | 30 (2026-05-28..2026-07-10) | 69 | 49% | 47 | 22 | `data/prob_table_txn.txt` |
| USO | 30 (2026-05-28..2026-07-10) | 59 | 44% | 29 | 30 | `data/prob_table_uso.txt` |

Sin datos suficientes (quedan en **priors**, estado valido por spec): SKHY (~2 sesiones IBKR), KOSPI/SAMSUNG/SKHYNIX (1 sesion KRX). No se genero tabla para ellos.

## Tabla completa por ticker y clase

`avgW`/`avgL` = retorno medio realizado por trade ganador/perdedor (barrera 0.75*ATR o cierre a 60 min). `prob_bot` = prob que el bot muestra hoy con la tabla desplegada (shrinkage k=20).

| Ticker | Clase | n train | WR train | n OOS | WR OOS | avgW | avgL | prob_bot | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | ORB_LONG | 3 | 33% | 8 | 88% | +0.10% | -0.10% | 50% | PRIOR |
| AAPL | ORB_SHORT | 8 | 38% | 2 | 50% | +0.10% | -0.08% | 49% | PRIOR |
| AAPL | SQUEEZE_BREAK_LONG | 1 | 100% | 2 | 50% | +0.13% | -0.11% | 58% | PRIOR |
| AAPL | TLINE_BREAK_LONG | 2 | 100% | 5 | 20% | +0.05% | -0.07% | 52% | **DEGRADADA** |
| AAPL | TLINE_BREAK_SHORT | 9 | 22% | 3 | 33% | +0.06% | -0.07% | 45% | PRIOR |
| AAPL | TREND_PULLBACK_LONG | 1 | 0% | 3 | 100% | +0.06% | -0.09% | 59% | PRIOR |
| AAPL | TREND_REVERSAL_LONG | 5 | 60% | 4 | 25% | +0.14% | -0.10% | 56% | PRIOR |
| AAPL | TREND_REVERSAL_SHORT | 5 | 80% | 5 | 40% | +0.14% | -0.09% | 57% | **DEGRADADA** |
| AAPL | VWAP_LOSS_SHORT | 2 | 50% | 0 | 0% | +0.04% | -0.04% | 59% | PRIOR |
| AMD | ORB_LONG | 2 | 50% | 2 | 0% | +0.20% | -0.21% | 53% | PRIOR |
| AMD | ORB_SHORT | 5 | 80% | 7 | 57% | +0.24% | -0.25% | 58% | PRIOR |
| AMD | TLINE_BREAK_LONG | 6 | 17% | 3 | 67% | +0.08% | -0.08% | 46% | PRIOR |
| AMD | TLINE_BREAK_SHORT | 6 | 67% | 3 | 33% | +0.14% | -0.13% | 58% | PRIOR |
| AMD | TREND_PULLBACK_LONG | 3 | 67% | 1 | 0% | +0.27% | -0.20% | 63% | PRIOR |
| AMD | TREND_PULLBACK_SHORT | 1 | 100% | 1 | 0% | +0.17% | -0.08% | 64% | PRIOR |
| AMD | TREND_REVERSAL_LONG | 7 | 43% | 3 | 33% | +0.20% | -0.23% | 52% | PRIOR |
| AMD | TREND_REVERSAL_SHORT | 8 | 38% | 6 | 33% | +0.32% | -0.24% | 47% | **DEGRADADA** |
| AMD | VWAP_LOSS_SHORT | 1 | 0% | 2 | 100% | +0.26% | -0.30% | 57% | PRIOR |
| ASML | MTF_BB_REV_LONG | 0 | 0% | 1 | 0% | +0.00% | -0.09% | 55% | PRIOR |
| ASML | ORB_LONG | 4 | 0% | 1 | 100% | +0.12% | -0.12% | 44% | PRIOR |
| ASML | ORB_SHORT | 1 | 0% | 5 | 40% | +0.16% | -0.13% | 48% | **DEGRADADA** |
| ASML | TLINE_BREAK_LONG | 7 | 14% | 4 | 50% | +0.13% | -0.09% | 44% | PRIOR |
| ASML | TLINE_BREAK_SHORT | 8 | 75% | 3 | 100% | +0.12% | -0.09% | 61% | PRIOR |
| ASML | TREND_PULLBACK_LONG | 1 | 0% | 1 | 0% | +0.00% | -0.05% | 59% | PRIOR |
| ASML | TREND_PULLBACK_SHORT | 2 | 50% | 2 | 100% | +0.12% | -0.21% | 61% | PRIOR |
| ASML | TREND_REVERSAL_LONG | 6 | 100% | 2 | 50% | +0.21% | -0.25% | 65% | PRIOR |
| ASML | TREND_REVERSAL_SHORT | 7 | 29% | 6 | 50% | +0.12% | -0.21% | 48% | **DEGRADADA** |
| ASML | VWAP_LOSS_SHORT | 3 | 67% | 0 | 0% | +0.15% | -0.09% | 61% | PRIOR |
| CPER | ORB_LONG | 3 | 33% | 1 | 100% | +0.09% | -0.07% | 50% | PRIOR |
| CPER | ORB_SHORT | 4 | 50% | 4 | 0% | +0.07% | -0.07% | 52% | PRIOR |
| CPER | SQUEEZE_BREAK_LONG | 1 | 0% | 0 | 0% | +0.00% | -0.05% | 53% | PRIOR |
| CPER | SQUEEZE_BREAK_SHORT | 1 | 100% | 0 | 0% | +0.16% | +0.00% | 58% | PRIOR |
| CPER | TLINE_BREAK_SHORT | 1 | 100% | 0 | 0% | +0.02% | +0.00% | 57% | PRIOR |
| CPER | TREND_REVERSAL_LONG | 8 | 12% | 5 | 40% | +0.08% | -0.07% | 42% | **DEGRADADA** |
| CPER | TREND_REVERSAL_SHORT | 11 | 73% | 3 | 33% | +0.09% | -0.07% | 61% | PRIOR |
| CPER | VWAP_LOSS_SHORT | 6 | 50% | 0 | 0% | +0.05% | -0.04% | 58% | PRIOR |
| DRAM | MTF_BB_REV_LONG | 1 | 0% | 0 | 0% | +0.00% | -0.17% | 52% | PRIOR |
| DRAM | ORB_LONG | 2 | 0% | 1 | 0% | +0.00% | -0.19% | 48% | PRIOR |
| DRAM | ORB_SHORT | 1 | 100% | 6 | 83% | +0.26% | -0.34% | 55% | PRIOR |
| DRAM | SQUEEZE_BREAK_LONG | 3 | 33% | 0 | 0% | +0.32% | -0.31% | 53% | PRIOR |
| DRAM | SQUEEZE_BREAK_SHORT | 0 | 0% | 2 | 0% | +0.00% | -0.19% | 56% | PRIOR |
| DRAM | TLINE_BREAK_LONG | 9 | 33% | 1 | 0% | +0.07% | -0.19% | 48% | PRIOR |
| DRAM | TLINE_BREAK_SHORT | 3 | 0% | 1 | 100% | +0.18% | -0.14% | 48% | PRIOR |
| DRAM | TREND_PULLBACK_LONG | 3 | 33% | 1 | 0% | +0.19% | -0.10% | 58% | PRIOR |
| DRAM | TREND_PULLBACK_SHORT | 1 | 100% | 0 | 0% | +0.41% | +0.00% | 64% | PRIOR |
| DRAM | TREND_REVERSAL_LONG | 5 | 40% | 2 | 50% | +0.15% | -0.24% | 52% | PRIOR |
| DRAM | TREND_REVERSAL_SHORT | 9 | 44% | 4 | 50% | +0.24% | -0.27% | 52% | PRIOR |
| DRAM | VWAP_LOSS_SHORT | 3 | 33% | 0 | 0% | +0.19% | -0.19% | 57% | PRIOR |
| GLD | ORB_LONG | 4 | 25% | 2 | 50% | +0.05% | -0.05% | 48% | PRIOR |
| GLD | ORB_SHORT | 4 | 75% | 6 | 67% | +0.05% | -0.05% | 57% | PRIOR |
| GLD | SQUEEZE_BREAK_LONG | 1 | 100% | 1 | 0% | +0.13% | -0.05% | 58% | PRIOR |
| GLD | SQUEEZE_BREAK_SHORT | 0 | 0% | 2 | 50% | +0.02% | -0.02% | 56% | PRIOR |
| GLD | TLINE_BREAK_LONG | 6 | 17% | 3 | 33% | +0.04% | -0.03% | 46% | PRIOR |
| GLD | TLINE_BREAK_SHORT | 6 | 67% | 0 | 0% | +0.05% | -0.05% | 58% | PRIOR |
| GLD | TREND_PULLBACK_LONG | 2 | 100% | 0 | 0% | +0.04% | +0.00% | 65% | PRIOR |
| GLD | TREND_PULLBACK_SHORT | 1 | 0% | 0 | 0% | +0.00% | -0.03% | 59% | PRIOR |
| GLD | TREND_REVERSAL_LONG | 4 | 50% | 6 | 33% | +0.06% | -0.07% | 50% | **DEGRADADA** |
| GLD | TREND_REVERSAL_SHORT | 11 | 54% | 5 | 60% | +0.04% | -0.06% | 55% | PRIOR |
| GLD | VWAP_LOSS_SHORT | 4 | 75% | 0 | 0% | +0.03% | -0.03% | 62% | PRIOR |
| INTC | ORB_LONG | 3 | 33% | 1 | 0% | +0.40% | -0.33% | 50% | PRIOR |
| INTC | ORB_SHORT | 1 | 0% | 6 | 50% | +0.29% | -0.30% | 50% | **DEGRADADA** |
| INTC | TLINE_BREAK_LONG | 7 | 43% | 4 | 0% | +0.13% | -0.20% | 52% | PRIOR |
| INTC | TLINE_BREAK_SHORT | 6 | 50% | 2 | 100% | +0.22% | -0.21% | 54% | PRIOR |
| INTC | TREND_PULLBACK_LONG | 1 | 100% | 0 | 0% | +0.16% | +0.00% | 64% | PRIOR |
| INTC | TREND_PULLBACK_SHORT | 4 | 75% | 3 | 33% | +0.23% | -0.23% | 64% | PRIOR |
| INTC | TREND_REVERSAL_LONG | 7 | 29% | 1 | 0% | +0.31% | -0.28% | 48% | PRIOR |
| INTC | TREND_REVERSAL_SHORT | 8 | 38% | 11 | 27% | +0.41% | -0.31% | 44% | **DEGRADADA** |
| INTC | VWAP_LOSS_SHORT | 1 | 0% | 0 | 0% | +0.00% | -0.38% | 57% | PRIOR |
| INTC | VWAP_RECLAIM_LONG | 1 | 0% | 0 | 0% | +0.00% | -0.21% | 57% | PRIOR |
| NOK | ORB_LONG | 3 | 67% | 1 | 100% | +0.22% | -0.12% | 55% | PRIOR |
| NOK | ORB_SHORT | 8 | 50% | 8 | 75% | +0.20% | -0.22% | 52% | PRIOR |
| NOK | SQUEEZE_BREAK_LONG | 2 | 50% | 2 | 0% | +0.14% | -0.15% | 55% | PRIOR |
| NOK | SQUEEZE_BREAK_SHORT | 2 | 0% | 1 | 0% | +0.00% | -0.23% | 51% | PRIOR |
| NOK | TLINE_BREAK_LONG | 3 | 33% | 3 | 33% | +0.11% | -0.17% | 52% | PRIOR |
| NOK | TLINE_BREAK_SHORT | 8 | 50% | 2 | 50% | +0.20% | -0.18% | 54% | PRIOR |
| NOK | TREND_PULLBACK_LONG | 4 | 75% | 0 | 0% | +0.16% | -0.05% | 64% | PRIOR |
| NOK | TREND_PULLBACK_SHORT | 2 | 0% | 0 | 0% | +0.00% | -0.24% | 56% | PRIOR |
| NOK | TREND_REVERSAL_LONG | 5 | 40% | 1 | 0% | +0.18% | -0.24% | 52% | PRIOR |
| NOK | TREND_REVERSAL_SHORT | 8 | 50% | 9 | 56% | +0.18% | -0.20% | 54% | PRIOR |
| NOK | VWAP_LOSS_SHORT | 0 | 0% | 4 | 50% | +0.05% | -0.16% | 60% | PRIOR |
| NVDA | ORB_LONG | 3 | 0% | 3 | 0% | +0.00% | -0.13% | 46% | PRIOR |
| NVDA | ORB_SHORT | 4 | 50% | 4 | 75% | +0.14% | -0.13% | 52% | PRIOR |
| NVDA | SQUEEZE_BREAK_LONG | 0 | 0% | 1 | 0% | +0.00% | -0.19% | 56% | PRIOR |
| NVDA | TLINE_BREAK_LONG | 4 | 50% | 2 | 0% | +0.14% | -0.08% | 54% | PRIOR |
| NVDA | TLINE_BREAK_SHORT | 6 | 50% | 3 | 67% | +0.12% | -0.15% | 54% | PRIOR |
| NVDA | TREND_PULLBACK_LONG | 1 | 100% | 1 | 100% | +0.09% | +0.00% | 64% | PRIOR |
| NVDA | TREND_PULLBACK_SHORT | 1 | 0% | 1 | 0% | +0.00% | -0.10% | 59% | PRIOR |
| NVDA | TREND_REVERSAL_LONG | 6 | 50% | 2 | 50% | +0.21% | -0.17% | 54% | PRIOR |
| NVDA | TREND_REVERSAL_SHORT | 10 | 40% | 8 | 38% | +0.15% | -0.17% | 47% | **DEGRADADA** |
| NVDA | VWAP_LOSS_SHORT | 1 | 100% | 2 | 100% | +0.15% | +0.00% | 62% | PRIOR |
| QQQ | ORB_LONG | 6 | 33% | 1 | 0% | +0.06% | -0.06% | 48% | PRIOR |
| QQQ | ORB_SHORT | 3 | 33% | 6 | 67% | +0.07% | -0.08% | 50% | PRIOR |
| QQQ | SQUEEZE_BREAK_LONG | 0 | 0% | 2 | 50% | +0.03% | -0.08% | 56% | PRIOR |
| QQQ | SQUEEZE_BREAK_SHORT | 0 | 0% | 1 | 0% | +0.00% | -0.10% | 56% | PRIOR |
| QQQ | TLINE_BREAK_LONG | 5 | 60% | 3 | 0% | +0.03% | -0.06% | 56% | PRIOR |
| QQQ | TLINE_BREAK_SHORT | 6 | 67% | 2 | 50% | +0.09% | -0.04% | 58% | PRIOR |
| QQQ | TREND_PULLBACK_LONG | 1 | 0% | 0 | 0% | +0.00% | -0.02% | 59% | PRIOR |
| QQQ | TREND_REVERSAL_LONG | 10 | 50% | 7 | 14% | +0.07% | -0.08% | 46% | **DEGRADADA** |
| QQQ | TREND_REVERSAL_SHORT | 11 | 36% | 4 | 75% | +0.08% | -0.09% | 48% | PRIOR |
| QQQ | VWAP_LOSS_SHORT | 2 | 100% | 2 | 50% | +0.07% | -0.06% | 64% | PRIOR |
| SLV | MTF_BB_REV_LONG | 0 | 0% | 1 | 0% | +0.00% | -0.06% | 55% | PRIOR |
| SLV | ORB_LONG | 2 | 50% | 4 | 50% | +0.15% | -0.11% | 53% | PRIOR |
| SLV | ORB_SHORT | 6 | 50% | 5 | 20% | +0.11% | -0.12% | 47% | **DEGRADADA** |
| SLV | SQUEEZE_BREAK_SHORT | 2 | 50% | 0 | 0% | +0.26% | -0.05% | 55% | PRIOR |
| SLV | TLINE_BREAK_LONG | 5 | 80% | 5 | 20% | +0.15% | -0.08% | 53% | **DEGRADADA** |
| SLV | TLINE_BREAK_SHORT | 5 | 60% | 4 | 100% | +0.08% | -0.08% | 56% | PRIOR |
| SLV | TREND_PULLBACK_SHORT | 2 | 50% | 1 | 0% | +0.10% | -0.04% | 61% | PRIOR |
| SLV | TREND_REVERSAL_LONG | 7 | 57% | 4 | 100% | +0.09% | -0.12% | 56% | PRIOR |
| SLV | TREND_REVERSAL_SHORT | 13 | 23% | 4 | 25% | +0.11% | -0.09% | 42% | PRIOR |
| SLV | VWAP_LOSS_SHORT | 3 | 33% | 2 | 100% | +0.08% | -0.10% | 57% | PRIOR |
| SPCX | ORB_LONG | 1 | 0% | 2 | 100% | +0.28% | -0.32% | 50% | PRIOR |
| SPCX | ORB_SHORT | 2 | 50% | 6 | 17% | +0.26% | -0.21% | 45% | **DEGRADADA** |
| SPCX | TLINE_BREAK_LONG | 5 | 20% | 1 | 0% | +0.44% | -0.21% | 48% | PRIOR |
| SPCX | TLINE_BREAK_SHORT | 4 | 75% | 3 | 67% | +0.18% | -0.33% | 58% | PRIOR |
| SPCX | TREND_PULLBACK_LONG | 0 | 0% | 1 | 100% | +0.11% | +0.00% | 62% | PRIOR |
| SPCX | TREND_PULLBACK_SHORT | 1 | 100% | 3 | 33% | +0.25% | -0.14% | 64% | PRIOR |
| SPCX | TREND_REVERSAL_LONG | 3 | 0% | 0 | 0% | +0.00% | -0.20% | 48% | PRIOR |
| SPCX | TREND_REVERSAL_SHORT | 4 | 100% | 5 | 80% | +0.40% | -0.38% | 62% | PRIOR |
| SPCX | VWAP_LOSS_SHORT | 2 | 100% | 0 | 0% | +0.47% | +0.00% | 64% | PRIOR |
| TSLA | ORB_LONG | 2 | 50% | 6 | 50% | +0.17% | -0.14% | 52% | **DEGRADADA** |
| TSLA | ORB_SHORT | 6 | 33% | 2 | 0% | +0.10% | -0.13% | 48% | PRIOR |
| TSLA | SQUEEZE_BREAK_SHORT | 0 | 0% | 1 | 100% | +0.06% | +0.00% | 56% | PRIOR |
| TSLA | TLINE_BREAK_LONG | 3 | 0% | 3 | 67% | +0.13% | -0.06% | 48% | PRIOR |
| TSLA | TLINE_BREAK_SHORT | 8 | 75% | 7 | 86% | +0.11% | -0.10% | 61% | PRIOR |
| TSLA | TREND_PULLBACK_LONG | 2 | 0% | 3 | 0% | +0.00% | -0.09% | 56% | PRIOR |
| TSLA | TREND_PULLBACK_SHORT | 2 | 0% | 2 | 50% | +0.14% | -0.11% | 56% | PRIOR |
| TSLA | TREND_REVERSAL_LONG | 6 | 67% | 3 | 33% | +0.21% | -0.16% | 58% | PRIOR |
| TSLA | TREND_REVERSAL_SHORT | 9 | 44% | 3 | 67% | +0.20% | -0.14% | 52% | PRIOR |
| TSLA | VWAP_LOSS_SHORT | 6 | 67% | 3 | 67% | +0.21% | -0.13% | 62% | PRIOR |
| TSM | ORB_LONG | 5 | 40% | 3 | 67% | +0.13% | -0.16% | 50% | PRIOR |
| TSM | ORB_SHORT | 3 | 100% | 3 | 33% | +0.12% | -0.13% | 59% | PRIOR |
| TSM | TLINE_BREAK_LONG | 4 | 75% | 3 | 33% | +0.06% | -0.07% | 58% | PRIOR |
| TSM | TLINE_BREAK_SHORT | 7 | 86% | 1 | 100% | +0.08% | -0.06% | 63% | PRIOR |
| TSM | TREND_PULLBACK_LONG | 4 | 0% | 0 | 0% | +0.00% | -0.09% | 52% | PRIOR |
| TSM | TREND_PULLBACK_SHORT | 3 | 67% | 3 | 67% | +0.10% | -0.08% | 63% | PRIOR |
| TSM | TREND_REVERSAL_LONG | 8 | 75% | 1 | 100% | +0.22% | -0.19% | 61% | PRIOR |
| TSM | TREND_REVERSAL_SHORT | 8 | 50% | 8 | 38% | +0.17% | -0.15% | 50% | **DEGRADADA** |
| TSM | VWAP_LOSS_SHORT | 2 | 50% | 0 | 0% | +0.04% | -0.09% | 59% | PRIOR |
| TXN | ORB_LONG | 5 | 80% | 2 | 100% | +0.11% | -0.15% | 58% | PRIOR |
| TXN | ORB_SHORT | 5 | 0% | 3 | 33% | +0.12% | -0.13% | 42% | PRIOR |
| TXN | SQUEEZE_BREAK_LONG | 1 | 100% | 0 | 0% | +0.19% | +0.00% | 58% | PRIOR |
| TXN | SQUEEZE_BREAK_SHORT | 0 | 0% | 1 | 100% | +0.06% | +0.00% | 56% | PRIOR |
| TXN | TLINE_BREAK_LONG | 4 | 25% | 5 | 60% | +0.10% | -0.07% | 50% | PRIOR |
| TXN | TLINE_BREAK_SHORT | 11 | 27% | 2 | 50% | +0.11% | -0.09% | 45% | PRIOR |
| TXN | TREND_PULLBACK_LONG | 3 | 67% | 2 | 100% | +0.09% | -0.09% | 63% | PRIOR |
| TXN | TREND_PULLBACK_SHORT | 1 | 100% | 1 | 0% | +0.14% | -0.08% | 64% | PRIOR |
| TXN | TREND_REVERSAL_LONG | 5 | 60% | 1 | 0% | +0.20% | -0.19% | 56% | PRIOR |
| TXN | TREND_REVERSAL_SHORT | 10 | 60% | 5 | 40% | +0.14% | -0.12% | 54% | **DEGRADADA** |
| TXN | VWAP_LOSS_SHORT | 2 | 50% | 0 | 0% | +0.12% | -0.19% | 59% | PRIOR |
| USO | ORB_LONG | 1 | 0% | 6 | 50% | +0.10% | -0.11% | 50% | **DEGRADADA** |
| USO | ORB_SHORT | 6 | 50% | 6 | 33% | +0.12% | -0.08% | 49% | **DEGRADADA** |
| USO | SQUEEZE_BREAK_SHORT | 0 | 0% | 1 | 100% | +0.23% | +0.00% | 56% | PRIOR |
| USO | TLINE_BREAK_LONG | 3 | 100% | 4 | 50% | +0.10% | -0.09% | 61% | PRIOR |
| USO | TLINE_BREAK_SHORT | 2 | 100% | 1 | 0% | +0.16% | -0.08% | 59% | PRIOR |
| USO | TREND_PULLBACK_LONG | 0 | 0% | 1 | 100% | +0.09% | +0.00% | 62% | PRIOR |
| USO | TREND_PULLBACK_SHORT | 2 | 50% | 0 | 0% | +0.13% | -0.10% | 61% | PRIOR |
| USO | TREND_REVERSAL_LONG | 7 | 14% | 3 | 67% | +0.10% | -0.13% | 44% | PRIOR |
| USO | TREND_REVERSAL_SHORT | 8 | 12% | 8 | 50% | +0.10% | -0.14% | 44% | **DEGRADADA** |

## Resumen de flota por clase (agregado 16 US)

| Clase | n train | WR train | n OOS | WR OOS | Veredicto de clase |
|---|---|---|---|---|---|
| MTF_BB_REV_LONG | 1 | 0.0% | 2 | 0.0% | muestras insuficientes |
| ORB_LONG | 49 | 34.7% | 44 | 56.8% | edge OOS (train debil — vigilar) |
| ORB_SHORT | 67 | 47.8% | 79 | 48.1% | **DEGRADADA** (WR OOS<55%) |
| SQUEEZE_BREAK_LONG | 9 | 55.6% | 8 | 25.0% | **DEGRADADA** (WR OOS<55%) |
| SQUEEZE_BREAK_SHORT | 5 | 40.0% | 9 | 44.4% | **DEGRADADA** (WR OOS<55%) |
| TLINE_BREAK_LONG | 73 | 39.7% | 49 | 32.7% | **DEGRADADA** (WR OOS<55%) |
| TLINE_BREAK_SHORT | 96 | 56.2% | 37 | 70.3% | EDGE REAL train+OOS |
| TREND_PULLBACK_LONG | 26 | 46.2% | 14 | 57.1% | edge OOS (train debil — vigilar) |
| TREND_PULLBACK_SHORT | 23 | 52.2% | 17 | 41.2% | **DEGRADADA** (WR OOS<55%) |
| TREND_REVERSAL_LONG | 99 | 47.5% | 45 | 40.0% | **DEGRADADA** (WR OOS<55%) |
| TREND_REVERSAL_SHORT | 140 | 45.7% | 94 | 45.7% | **DEGRADADA** (WR OOS<55%) |
| VWAP_LOSS_SHORT | 38 | 57.9% | 15 | 73.3% | EDGE REAL train+OOS |
| VWAP_RECLAIM_LONG | 1 | 0.0% | 0 | 0.0% | muestras insuficientes |

## Veredicto global y hallazgos

1. **CERO clases CALIBRADAS** (0 de 158 combinaciones clase-ticker): el gate `n_train>=20` nunca se alcanza — el maximo es 19 (INTC TREND_REVERSAL_SHORT). Causa estructural: cooldown 1800s/lado + max 2 señales/clase/dia + score>=6 dan ~2.2 trades/dia/ticker. El gate G5 del spec (>=1 clase calibrada en >=6 tickers) **NO se cumple con 30 sesiones**; para cumplirlo hace falta ventana de ~90 sesiones (los bt_*.txt ya la tienen) o relajar los limites SOLO en calibracion (cambiaria la distribucion vs produccion — decision de Yunior).
2. **20 clases-ticker DEGRADADAS** (WR OOS<55% con n_oos>=5). La peor familia: **TREND_REVERSAL_SHORT** — degradada en 7 tickers, agregado 140n train WR 45.7% / 94n OOS 45.7%. Tambien debiles en OOS: TREND_REVERSAL_LONG (45n OOS 40.0%), TLINE_BREAK_LONG (49n OOS 32.7%), SQUEEZE_BREAK_LONG (8n OOS 25.0%). Sus filas llevan datos reales combinados → el bot mostrara prob 42-54% y `V6_PROB_MIN=55` las silenciara en produccion. Honesto: el detector de reversal §2.5 y el squeeze-long NO tienen edge en esta ventana.
3. **Edge real donde SI lo hay (lado corto/bajista)**: TLINE_BREAK_SHORT 96n train 56.2% / 37n OOS **70.3%**; VWAP_LOSS_SHORT 38n train 57.9% / 15n OOS **73.3%**. Consistente con la ventana jun-jul con correcciones intradia. ORB_LONG invierte: train 34.7% pero OOS 56.8% (44n) — inestable, no confiable.
4. **WR global de flota ~47%** (1017 trades resueltos, barreras simetricas): el motor v6 con defaults es ~moneda al aire SIN seleccion; el valor esta en el filtro prob (tabla real + shrinkage + PROB_MIN=55). Con las tablas desplegadas, solo las clases-ticker que superan 55% tras shrinkage emiten señal — exactamente el diseño.
5. **La tabla cambia el flujo de señales** (11/16 tickers con set distinto entre pass A y pass B): la prob altera el tie-break BUY/SELL del mismo bar y la cadena de cooldowns. Implicacion operativa: desplegar las 16 tablas a la vez y **regenerar semanalmente** (ventana movil 30d) con este mismo script; los bots las releen en runtime (stat cada 3600s) — **no hace falta recompilar**.

Notas de alcance: (a) el grid WFO de 3 parametros (27 combos, spec §4.3) NO se corrio — `data/v6_wfo_report.txt` documenta la calibracion con defaults; fase 2 manual. (b) 'quake' y 'capitulacion' NO son clases v6 (son banners del motor clasico/radar TERREMOTO, fuera del enum cerrado §2.9) — no se calibran aqui. (c) Señales sin bar siguiente o ATR=0 se excluyen (irresolubles).

---

# v6.1 retest-confirm (2026-07-16 noche) — señales anti-trampa en las rupturas

**Motivacion (Yunior, mejora #2 del dia)**: "no entrar cuando viene el pullback; señal con confirmacion completa y rebote hecho; ojo trampas de ballena". Codifica la regla 2 del PLAYBOOK ("nunca comprar la ruptura en el 1er toque del muro — esperar retest-y-rechazo").

## Mecanica (en `scripts/v6_block.cpp.tmpl`, desplegada a los 22 bots)

Las clases de ruptura (**TLINE_BREAK_***, **ORB_***, **SQUEEZE_BREAK_***, **VWAP_LOSS_SHORT**) ya NO disparan al romper el nivel: la señal queda **ARMADA** (nivel roto congelado: OR hi/lo, BB15 up/dn, proyeccion de la trendline 1m, VWAP) y solo se emite cuando:

- **(a)+(b) retest-ok**: el precio hace pullback hacia el nivel roto (retrace 30-70% del impulso post-ruptura, o toque del nivel ±0.25×ATR14-1m) **y lo RECHAZA** — vela 1m que cierra de vuelta en la direccion de la ruptura y del lado correcto del nivel; o
- **(c) breakaway**: 3 cierres 1m consecutivos sosteniendo mas alla del nivel sin retest (ruptura fuerte que no da segunda oportunidad).

Si el pullback **ATRAVIESA** el nivel de vuelta (cierre en contra >50% del impulso pasado el nivel) → **trampa de ballena**: la señal armada se CANCELA y se registra `TRAMPA-EVITADA` en stdout/ops-log (con nivel, precio e impulso); ese lado queda 5 min sin re-armar. La armada tambien expira a los 20 bars sin confirmar (`{SYM}_V6_RETEST_MAX`) y se re-verifica el veto 15m + cooldown/cupo AL CONFIRMAR (una ruptura cuyo contexto 15m giro durante el retest muere en silencio — G3 intacto). Las señales emitidas llevan el tag `+retest-ok` o `+breakaway` en las razones. **Kill-switch: `{SYM}_V6_RETEST=0`** restaura el disparo inmediato v6.0. Las clases no-ruptura (TREND_PULLBACK, VWAP_RECLAIM, MTF_BB_REV, TREND_REVERSAL) no cambian.

## Backtest antes/despues (mismas 30 sesiones, mismo triple-barrier; la entrada v6.1 se evalua desde el bar de CONFIRMACION — la "2ª pierna", que es la que operaria el humano)

Agregado de flota (16 US, train+OOS combinados), clases de ruptura:

| Clase | v6.0 n | v6.0 WR | v6.1 n | v6.1 WR | Δ WR | Lectura |
|---|---|---|---|---|---|---|
| TLINE_BREAK_LONG | 122 | 36.9% | 80 | 50.0% | **+13.1** | La peor clase de v6.0 — el retest le corta las falsas |
| TLINE_BREAK_SHORT | 133 | 60.2% | 101 | 56.4% | −3.8 | Sigue siendo edge; OOS cayo (70%→46%, n 37→28) — vigilar |
| ORB_LONG | 93 | 45.2% | 78 | 43.6% | −1.6 | Sin mejora; ya era inestable train-vs-OOS |
| ORB_SHORT | 146 | 47.9% | 130 | 43.8% | −4.1 | Sin edge con o sin retest |
| SQUEEZE_BREAK_LONG | 17 | 41.2% | 14 | 50.0% | +8.8 | n chico |
| SQUEEZE_BREAK_SHORT | 14 | 42.9% | 7 | 42.9% | 0.0 | n chico |
| VWAP_LOSS_SHORT | 53 | 62.3% | 48 | 43.8% | **−18.5** | EMPEORA: el desangre bajo VWAP no suele dar retest limpio — el rebote a VWAP que exigimos es justo el que mata el momentum |
| **Total rupturas** | **578** | **49.0%** | **458** | **47.8%** | −1.2 | −21% de señales de ruptura (trampas+expiradas filtradas) |

Trampas evitadas: **107 en 30 sesiones × 16 tickers** (~0.22/dia/ticker; top: NOK 14, INTC 11, TSLA 11, TXN 10). Tags emitidos: ~350 retest-ok / ~106 breakaway.

## Veredicto honesto

1. **Gana donde la trampa vive**: TLINE_BREAK_LONG (la familia que motivo la mejora) sube +13 pts y pasa de 37% a 50% con un 35% menos de señales. SQUEEZE_LONG tambien mejora.
2. **VWAP_LOSS_SHORT empeora claramente** (62%→44%): era una clase de MOMENTUM (3er cierre bajo VWAP = ya confirmada por diseño), no de ruptura de nivel estatico; exigirle retest retrasa la entrada al punto muerto. **RESUELTO (Yunior, misma noche): exencion POR CLASE implementada** — `{SYM}_V6_RETEST_EXEMPT` (csv, default `"VWAP_LOSS_SHORT"`) dispara inmediato como v6.0; re-backtest con la exencion: VWAP_LOSS_SHORT **restaurada a 57.9% train / 73.3% OOS (62.3% combinado)**, el resto de rupturas conserva el retest (tablas regeneradas). TLINE_BREAK_SHORT se queda CON retest (n chico, vigilar por scorecard).
3. Neto de flota casi plano (49.0%→47.8% en rupturas, WR global ~46-47%): el retest REDISTRIBUYE el edge (menos señales, mejores en trendline-breaks, peores en vwap-loss). Con las tablas v6.1 desplegadas + `V6_PROB_MIN=55`, las combinaciones degradadas quedan silenciadas en produccion — el filtro de prob sigue siendo el que manda.
4. Las tablas `data/prob_table_*.txt` fueron regeneradas con la logica v6.1 (los bots las releen solos, sin recompilar). Reporte previo conservado en `data/v6_wfo_report_v6.0_preretest.txt`.
