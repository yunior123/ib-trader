# Whale Scalper — spec (2026-07-21)

Motor C++23 de la **táctica espada-ballena** (CLAUDE.md regla 11): tras una alerta
🐋 del vigía `opt_whale_watch.py`, esperar 2.5s y comprar el 0DTE de QQQ **contra**
el flujo (CALLS→PUT en el techo local, PUTS→CALL en el piso), profit 1→5% NETO en
≤60s con trailing, salida forzada a los 60s, y **un trade rojo neto = HALT total**.

**Estado actual: SIM/SHADOW solamente.** `--arm-live` aborta (Fase 4 no implementada).
La ley SEÑAL-SOLAMENTE de la flota queda intacta.

## Archivos
| Archivo | Qué es |
|---|---|
| `scalper_core.h` | Núcleo puro: FSM, dinero (int64 cents), selección de contrato, parsers, gates, BS, Clock |
| `exec_adapter.h` | `ExecutionAdapter`: SimAdapter (fills simulados, latencia 50-300ms, adversidad=tiempo) + TwsAdapter stub |
| `ledger.h` | JSONL append-only (O_APPEND+fsync) + recovery + post-mortem automático |
| `whale_scalper.cpp` | Binario: `--replay` (reloj virtual, tests), `--sim --data DIR` (archivos reales o feeder) |
| `shadow.sh` | **Modo sombra en vivo**: datos reales de TWS, órdenes solo REGISTRADAS al ledger |
| `shadow_report.py` | Compara operaciones sombra vs el gráfico (barras 1m) |
| `sim_feed.py` | Replay realtime de un día real (puente browniano sub-minuto, ≤5x) |
| `mock_gen.py` | Fábrica de escenarios sintéticos (pop_pullback, band_walk, whipsaw…) |
| `backtest_whale_scalp.py` | Estudio histórico honesto (alertas reales × barras 1m) |
| `tests/` | 39 unit (release+ASan) + 13 escenarios replay + suite mock (18) |

## FSM
`IDLE → ARMED_WAIT(2.5s) → ENTRY_PENDING(1.5s×3 re-price al ask) → HOLDING → EXIT_PENDING → IDLE|HALTED`
- **Profit**: activo desde fill+3s. +5% neto → vende YA. +1% neto → arma trailing
  (retro 3c del pico → cobra; a los 55s cobra lo armado). Si evapora: cobra si aún
  verde, **jamás vende rojo voluntariamente** — desarma y espera (60s = salida forzada).
- **Salidas forzadas**: 60s sin profit, force-flat 15:55 ET, HALT file, NBBO stale >5s
  o NBBO inválido (jamás visto), ambos con gracia de 2s (`NBBO_HOLD_GRACE_MS`).
- **Aborto de entrada** (2026-07-22): HALT file o force-flat con BUY vivo en
  ENTRY_PENDING → cancel inmediato; un fill que gane al cancel se adopta (FILL_ADOPT).
- **Escaladas 🐋📈 (prev=ESCALADA)**: jamás gatillo de entrada; en ARMED_WAIT una
  escalada del MISMO símbolo y lado aborta la entrada contraria (la marea sigue creciendo).
- **Salida**: SELL al bid, re-price cada 2s, tras 3 → bid−2c; watchdog 60s → EXIT_STUCK + sirena.
- **Cierre rojo neto (comisiones incluidas) → HALTED** + `scalper/HALT` + post-mortem en `ledger/postmortem_*.md`.

## Gates de entrada
IMPACT_SYMS (QQQ NVDA MSFT AAPL AVGO AMZN META GOOGL TSLA MU) · ventanas 9:45-11:30 y
14:00-15:30 ET · máx 3 trades/día · cooldown 120s · presupuesto $200 (ask×100+comisión) ·
premium ≤$2.00 · bid ≥1c (veta -1.00) · spread ≤max(5% ask, 3c) · NBBO ≤5s · chain ≤10min ·
primer expiry == hoy · contrato: primer OTM (+1 de reserva).

## Dinero
`int64_t` cents. Comisión 65c/lado (RT $1.30). `net_cost = fill×100+65`,
`net_exit = bid×100−65`, umbral entero `exit×10000 ≥ cost×(10000+bp)`.

## Config
`scalper/scalper.conf` (key=value). Todo timeout/umbral/lista es configurable — nada hardcoded.

## Datos que alimentan (y sus hooks de almacenamiento, 2026-07-21)
- `data/whale_alerts.jsonl` ← hook en `opt_whale_watch.py` (toda transición, incl. →MID)
- `data/whale_flow_hist.jsonl` ← TODO escaneo de TODOS los símbolos (P/C, spot, cada 5min)
- `data/nbbo_hist_qqq_YYYYMMDD.txt` ← hook en `ibkr_bar_bridge.py` (ticks QQQ 4/s, ~3MB/día)
- Fallback de alertas: parser del txt del Desktop (funciona sin los hooks).

## Backtest 2026-07 (honesto)
n=17 alertas en scope (2 sesiones) → **DATA-INSUFFICIENT**. Señal direccional
prometedora: fade a +5min 59% WR (única celda positiva tras costos); a +1min pierde —
la alerta llega hasta 5min tarde (cadencia del vigía). Implicación: el hold de 60s
quizá es corto; decidirá la data de la grabadora (≥2 semanas, ≥30 alertas).
Reporte: `docs/BACKTEST-WHALE-SCALP-2026-07.md`.

## Fase 4 (LIVE — NO implementada, requiere orden explícita de Yunior)
TwsAdapter nativo con la API C++ oficial vendoreada (`scalper/vendor/IBJts/`):
EClientSocket/EWrapper/EReader, clientId 90, **paper 7497 primero**. Receta de build
(Intel Decimal lib) y patrón completo: `.claude/skills/ibkr-tws/SKILL.md`.
Doble llave: `--arm-live` **y** `scalper/ARM_LIVE` con la fecha de hoy. P&L real por
`execDetails`+`commissionReport`, reconciliación de posición al arranque vs ledger.

## Comandos
```bash
./scalper/build.sh                      # release + ASan
./scalper/tests/run.sh                  # suite completa
python3 scalper/mock_gen.py --suite --outdir /tmp/mock_suite   # sintéticos
python3 scalper/sim_feed.py --date 2026-07-21 --speed 5 --out /tmp/simdata &
./scalper/whale_scalper --sim --data /tmp/simdata --ledger /tmp/simledger
./scalper/shadow.sh                     # sombra en vivo (RTH)
python3 scalper/shadow_report.py        # sombra vs gráfico
python3 scalper/backtest_whale_scalp.py # re-correr el estudio
```
