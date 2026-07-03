# EOD Backtest — 2026-07-23 (análisis profundo de las señales del día)

Fuente: `trades.db` tabla `signals` (335 señales capturadas hoy) evaluadas contra el precio
real 1m posterior (`scripts/eod_backtest.py`). Precio de entrada = close de la barra en el
instante de la señal; resultado = retorno en la dirección de la TESIS a +15/+30/+60min.
Ganó = se movió >0.05% en la dirección de la tesis. Wilson CI 95%.

## WR por fuente (accionables = sin MUTED/VETADO, n=195)

| fuente | n | +15m | +30m | +60m | lectura |
|---|---|---|---|---|---|
| bollinger | 128 | **48%** | 48% | 46% | moneda al aire — SIN edge aun tras mutear |
| whale | 28 | 46% | **54%** | 54% | mejora con el tiempo (la reversion tarda) |
| flow | 29 | 52% | 38% | 34% | **decae** — el fade no tiene edge durable |
| structural | 5 | **80%** | 40% | 40% | mejor a corto (pin rápido); n chico |
| dip | 3 | 33% | 67% | 33% | n muy chico, inconcluso |
| cusum | 2 | 100% | 50% | 0% | n=2, inconcluso |
| **TOTAL** | **195** | **50%** | 47% | 45% | **el firehose es 50/50** |

Firehose completo (con MUTED/VETADO, n=298): 48% @15m. Mutear sube a 50% — **ayuda poco**.

## Veredicto central (repetido, ahora con n=195 EN VIVO)
**El edge NUNCA estuvo en la señal cruda — está en la SELECTIVIDAD.** Las señales sueltas son
una moneda al aire (48-50%). Coincide con los backtests previos (confluencia C4 59%/+19% n=127,
Yoel cambio_tend 64%/+31% n=226). La flota como firehose no es tradeable; los filtros sí.

## Lo que hicimos BIEN
- **Señal estructural nueva (imán/flip): 80% @15m (4/5)** — la mejor del día. El pin/approach es
  jugada RÁPIDA. Validada además por la operación REAL de Yunior (call NVDA camino al imán 210 = +).
- **Los vetos funcionaron**: los DIP VETADO fueron justamente perdedores → el veto los silenció bien.
- **AAPL 🚀 SPIKE CALLS 12:55 → el pullback SÍ llegó** (BB REBOTE 13:20 lo confirmó) — buena lectura.
- El muteo quitó las 103 peores (firehose 48 → accionable 50).

## Lo que hicimos MAL (diagnóstico de las equivocadas)
1. **BOLLINGER (118 perdedoras / MAE +0.46%)** — el fallo mayor. Muchas "🎈 BB REBOTE" dispararon
   con **%B extremo EN CONTRA** (ej GOOGL %B −0.08, META %B 0.99): la banda reventada y el precio
   **SIGUIÓ caminándola** (band-walk) → el "rebote a la media" nunca ocurrió. 17 perdedoras con %B
   extremo. **Es la regla #1 de CLAUDE.md (BOLLINGER SIEMPRE) que el ENGINE no aplica**: llama rebote
   sin confirmar (a) RE-ENTRADA real a la banda, (b) que 15m/otros TF NO estén en band-walk a favor.
2. **WHALE mañana (TSLA 9:31 PUTS −1.45%, 9:38 CRECE −1.46%)** — los dos peores del día. Tres errores
   juntos: (a) **9:30-9:45 = subasta, jamás operar** (regla 7); (b) **PUTS que CRECEN = continuación
   BAJISTA, no piso** (la tesis "puts=piso" es ingenua cuando el flujo se duplica); (c) sin **filtro
   capitán** (si SPY/SMH también en puts, el piso del nombre queda anulado — regla 12).
3. **FLOW-fade decae (52%→34%)** — confirma que no hay edge durable; dejarlo como CONTEXTO, no gatillo.

## Acciones para MAÑANA (aditivas, medidas)
- [ ] **BB rebote**: exigir re-entrada a la banda (2 lecturas cruzando) + veto si 15m está en
      band-walk a favor (%B 15m extremo en la misma dirección) ANTES de cantar rebote. Es donde
      está la fuga (128 señales, 48%). Backtestear el filtro contra hoy.
- [ ] **Whale**: (a) silenciar 9:30-9:45; (b) CRECE = continuación, invertir la tesis; (c) aplicar
      filtro capitán (señal de nombre anulada si el capitán va en contra).
- [ ] **Structural**: seguir midiendo (promete a +15m); es candidato a señal de PRIMERA clase.
- [ ] Horizonte: whale se evalúa a +30/+60m (la reversion tarda); structural/BB a +15m.

## Datos / infraestructura (calidad)
- Barras 1m continuas para 33 símbolos ✓. Opciones ahora en snapshots 5min (`data/history/`) para
  backtest fino de la evolución GEX/muros mañana.
- flow (spike) no traía precio en el mensaje → se resolvió tomando el precio de las barras (mejor).
- No look-ahead: entrada = barra del instante, resultado = barras estrictamente posteriores.

*Ley: n<30 por fuente = declarado, NO conclusión (whale/dip/structural/cusum). No es consejo financiero.*
