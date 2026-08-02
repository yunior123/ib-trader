# OVERNIGHT WATCH SPEC (Yunior 2026-07-31)
Watch de la flota cada 25 min mientras dure la sesión overnight. Email SOLO si es SEGURO comprar/vender.
Fuente de precios: IBKR MCP vía sesión viva (Polygon snapshot = 401, TWS cerrado). Corre in-session (ScheduleWakeup).

## Cada wake:
1. Lanzar price-subagent (run_in_background:false): lee `data/overnight_watch_conids.json`, hace get_price_snapshot(["last","change"]) de los 30, devuelve tabla SYM|last|chg%|hora + marca prints >30min viejos. Si falta el fichero de conids, resolver con search_contracts.
2. Leer `data/overnight_watch_levels.json` (flip/call_wall/put_wall/regime/close_spot por símbolo) y `data/overnight_watch_state.json` (dedupe + pull_log).
3. Append al pull_log: {ts, sym→last} de SPY QQQ MU AMZN AAPL + top-mover (para MEDIR el patrón "~00:30 pump" que reportó Yunior; no afirmar hasta tener varias noches).

## Triggers (SOLO estos = "seguro"; todo lo demás = SILENCIO):
AJUSTE Yunior 2026-07-31 ~00:50: AVISAR TEMPRANO al primer trigger confirmado (2 pulls) — NO esperar a la extensión extrema (p.ej. NO esperar a que la memoria esté en 1000 para avisar). Umbral de confirmación = 2 pulls consecutivos, no 3+.
- **LONG_SQUEEZE**: last > call_wall Y regime NEG Y el pull anterior también estaba > call_wall (2 confirmaciones) → squeeze corto-gamma al alza. Capitán (SMH para semis, SPY/QQQ índice) no rojo. AVISAR aquí, no más arriba.
- **LONG_RECLAIM**: last recupera flip por ≥0.3% con call_wall ≥1% de recorrido Y capitán verde. 2 pulls.
- **SHORT_BREAKDOWN**: last < put_wall Y < flip por ≥0.3%, capitán rojo/confirmando (tipo AAPL). 2 pulls.
- **WALL_REJECT / EXHAUSTION (scalp reversión — CRÍTICO para no perseguir el máximo)**: tras squeeze extendido, 2 pulls estancados/bajando en un techo (call_wall o número redondo) = techo local → avisar "posible techo, tomar beneficio / no perseguir". Simétrico en put_wall = rebote.
- **MU ESCALERA HACIA 1000 (foco Yunior)**: MU rompió 900. Niveles a vigilar por encima: 920, 950, 975, **1000 (número redondo/imán psicológico)**. Avisar cuando: (a) MU rompe y AGUANTA 950 con 2 pulls + volumen (posible run a 1000), o (b) MU se estanca/rechaza en un escalón con volumen cayendo (agotamiento antes de 1000). Ambos son accionables — no callar hasta 1000.

## Reglas duras (doctrina casa):
- **Dedupe**: no re-alertar mismo sym|dirección|nivel en la misma noche (state.alerts_sent).
- **Nada marginal**: trigger oscilando en la frontera = NO email (regla 3). Exigir las 2 confirmaciones.
- **Nada con print viejo/thin**: si el único mover tiene print >30min o salto de 1 solo pull, SILENCIO.
- **Conflicto de capitán**: si el nombre va a favor pero su capitán va en contra, señal ANULADA (jerarquía capitanes).
- **Honestidad**: el email dice SIEMPRE "setup overnight, confirmar con print RTH 9:30 — overnight no dispara". Ofrecer nivel exacto de entrada/invalidación, no "está cerca".
- **Si hay DUDA real** (señales cruzadas, flujo ambiguo): antes de emailar, escalar a TradingAgents (DeepSeek) y/o Finviz técnicos; si sigue ambiguo, SILENCIO.
- Email vía Resend (patrón scripts/daily_fleet_plans.py, from onboarding@resend.dev, to RESEND_TO). Asunto: "⚡ OVERNIGHT [SYM DIR] — <hora>".

## Parada:
- Al llegar RTH ~09:30 ET → parar el loop (entregar al sistema premarket 08:30) y mandar 1 email resumen de la noche.
- Si Yunior dice parar → ScheduleWakeup stop.
