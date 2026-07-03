# PLAN DE DELEGACIÓN — Overhaul de algoritmos "detectar y anticipar" (2026-07-22 noche)

**Lema (a CLAUDE.md + AGENTS.md): "Nos especializamos en detectar y anticipar movimientos."**

## TODOs (orden de Yunior)
1. **Bollinger alerts** — backtest ≥1 mes × ticker (30d de 1m vía yfinance por chunks), optimizar por ticker, probs medidas en el mensaje.
2. **Options flow alerts** — verificar estado del viernes (commit 82ce0d3), estudiar el caso del día (NVDA calls-flow → deriva abajo → SPY puts-flow lo REVIRTIÓ; "estaba divino"), jerarquía: índice manda > SMH capitán de memoria > nombres. flow_pulse v4.
3. **Testing + backtesting** — todo verificado por agentes adversarios + suite completa al final.
4. **Autolearn de los errores de hoy** — forense de logs (alarma 214.40 quemada al armarla, artefacto 12:22, entradas tardías) → LEARNED + fixes.
5. **Scalper C++** — review profundo + mejoras con tests verdes.
6. Config: solo skills/plugins de trading + software (C++/Python/IBKR) activos.

## Restricción honesta
Flujo de opciones: la grabadora existe desde 2026-07-21 → backtest de flujo = 1 día completo (1,500 escaneos). UN MES imposible hasta ~2026-08-22 (la grabadora acumula sola). Bollinger sí tiene su mes (yfinance 1m×30d).

## Enjambre (Workflow, 4 builders ∥ + 1 verificador adversario c/u)
| Agente | Entregable | Verificador |
|---|---|---|
| B1 bollinger-backtester | data/backtest/bars30d_*.csv + bollinger_probs.json + patch bollinger_alarm.py + docs/BACKTEST-BOLLINGER | V1 recomputa 3 tickers desde cero |
| B2 flow-v4 | análisis viernes vs hoy + caso NVDA/SPY + jerarquía capitanes + flow_pulse v4 + calibrate v4 | V2 compila, sandbox, re-verifica el caso |
| B3 log-forensics | POSTMORTEM-ALGOS + LEARNED.md + lista de fixes verificados contra código | V3 confirma cada error contra logs crudos |
| B4 scalper-review | mejoras a scalper/ con 21 unit + 12 replays verdes | V4 corre tests, intenta refutar |

Reglas para todos: señal-solamente, aditivo + degradación limpia, backup/ antes de tocar, compilas C++ con lock (/tmp/cc.lock, 8GB), no tocar launchd.

## Integración final (yo, secuencial)
Aplicar parches aprobados → builds secuenciales → suites completas → sandbox → lema a CLAUDE.md/AGENTS.md → higiene de plugins → memoria.

## Ola 2 (añadida en vivo)
7. **DIP ALERT con gate de valuación** (B5+V5, en paralelo con ola 1): dips reales de la flota + Finviz Elite (Forward P/E, PEG, etc.) — jamás comprar inflado; sin ruido (print de estabilización, cooldown, ventanas). `scripts/dip_alert.py` + `data/finviz_valuation.csv` + backtest diario 1 año.
8. **Caza-bugs de proyecto completo** (ola 3, POST-integración de ola 1): 3 exploradores por área (pipeline Python/datos, binarios C++, ops/keepalive/launchd/docs) + test integral final. Ojos frescos sobre el estado FINAL.

## Refinamiento capitanes (Yunior, en vivo)
En la integracion de flow v4: la señal de un NOMBRE con capitan opuesto VIGENTE se DEGRADA a banner sin voz (no solo anotar 'el indice manda') — el capitan prevalece; capitan-puts = rebote del grupo siempre (SIGNAL para SMH, DANGER para SPY/QQQ en reverses). Re-testear el sandbox con este caso.

## Ola 4 (orden Yunior ~18:00) — LOS 3 MOTORES
- `engines/` nuevo: E1=flujo (flow_pulse v4, ya existe — se le añade harness comparable), E2=`bb_engine` C++23 solo-Bollinger, E3=`combo_engine` C++23 (BB gated por flujo/capitanes).
- Datos: 3 meses 5m + 30d 1m vía IBKR histórico (clientId 40-49, pacing) → data/backtest/.
- SCORER ÚNICO compartido (scorer.py): las 3 salidas de señales se puntúan con el MISMO código (entrada barra siguiente, target/stop/horizonte idénticos) → win rates comparables.
- Optimización WALK-FORWARD (skill walk-forward-validation): params en meses 1-2, WR reportado en mes 3 (holdout). Sin holdout no hay número.
- Caza de edge-cases DE PÉRDIDA: 3 cazadores adversarios (lookahead, datos stale/huecos/halts, spread ignorado, doble-fire, sd=0, overnight, DST).
- Final (yo): reporte WR 3 motores → email Resend a Yunior → commit + push.
- Flujo: 3 meses imposible (grabadora 2026-07-21) — E1 y pata-flujo de E3 medidos con días grabados, declarado en el reporte.
