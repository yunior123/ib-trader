# Backtest de engines sobre OPCIONES REALES (Polygon) — 2026-07-23

Todas las señales de las engines puntuadas sobre el pago de opción ATM semanal
REAL (Polygon, prima 5m verdadera con theta/spread), TP +100%, sin stop (el
vehículo y la geometría que la flota de verdad opera). `scripts/real_option_scorer.py`.

| Engine | n | WR | Ret/trade | Wilson⌊ |
|---|---|---|---|---|
| FLOW (spikes) | 26 | 62% | +7% | 43% |
| — SPIKE_CALLS→PUT | 17 | **76%** | +14% | — |
| — SPIKE_PUTS→CALL | 9 | 33% | −4% | — |
| BB (Bollinger solo) | 836 | 50% | +1% opt / −2% cons | 47% |
| — ELASTIC | 522 | 49% | −0% | — |
| — SQZ_BRK | 291 | 51% | +4% | — |
| — BWALK | 23 | 52% | +9% | — |
| COMBO (BB+flow+capitán) | 42 | 40% | +2% | 27% |

## Hallazgos (data real, no síntesis)
1. **El FLUJO es el edge, no Bollinger.** Bollinger solo = breakeven sobre 836 trades reales (n firme). El fade del spike de CALLS (→PUT) rinde 76%.
2. **El combo actual decepciona (40%)**: su BB-elástico (39%) lo arrastra. Sobre el subyacente ±0.35% daba 69%; sobre opción real con TP +100% no llega — la diferencia de vehículo importa.
3. **Mejora que dicta la evidencia**: invertir el combo — gatear por el SPIKE DE FLUJO/capitán (el 76%) y usar BB/hora solo como confirmación de timing, no como gatillo primario.
4. **Caveat**: flow/combo n=26/42 (2 días de flujo grabado). Firmar el flow engine requiere reconstruir flujo histórico de Polygon — diario de capitanes+líderes (SPY QQQ SMH NVDA MU) sobre 3 meses ≈ 1000 llamadas (factible); intradía de 30 tickers = miles (inviable).
5. **Herramienta reutilizable**: `real_option_scorer.py` puntúa cualquier CSV de señales (formato compartido) sobre opción real — usar para todo backtest futuro de la flota.

## ADDENDUM — Reconstrucción de flujo 3 meses (Polygon) y por qué NO firma el flow engine
Reconstruí flujo DIARIO real (P/C por volumen call vs put) de los 5 capitanes (SPY QQQ SMH NVDA MU) sobre 3 meses (`scripts/reconstruct_flow.py`, ~1800 llamadas, 55 días c/u). Dos tests sobre opción real:
- **Spikes diarios** (rate ≥2.5× EMA): solo **6 señales** en 3 meses — la agregación diaria lava los spikes (fenómeno intradía).
- **Extremos de P/C diario** (percentil 15/85, fade): **23% WR, −53%** (n=77). DESASTRE.
**Conclusión clave (data real):** el edge del flujo es **INTRADÍA**, no diario. El spike-fade intradía (62-76%, 2 días) caza extremos que revierten; los extremos de P/C DIARIOS son **continuación de tendencia** — fadearlos pierde. **La señal de ballena/flujo debe quedarse intradía; jamás usar P/C diario como contrarian.** Para firmar el flow engine sobre 3 meses se necesita reconstrucción INTRADÍA (miles de llamadas, inviable) o la grabadora en vivo (~1 mes, gratis, acumula desde 2026-07-21).

## ADDENDUM 2 — Flujo INTRADIA horario 3 meses (Polygon Massive, ilimitado): NO confirma el flow engine
Reconstruí flujo intradia HORARIO de los 5 capitanes, 3 meses (440h c/u, `reconstruct_flow_intraday.py`), detecté spikes con la logica de flow_pulse (`flow_intraday_signals.py`) y puntué sobre opcion real: **22 señales, 43% WR, -23% ret** (todas put-spikes). NO reproduce el 76% de los 2 dias en vivo (n=17). Interpretacion honesta: (a) el resultado de 2 dias era muestra chica/suerte, y/o (b) la granularidad HORARIA es 12x mas coarse que los ~5 min de la grabadora viva y lava los spikes. **VEREDICTO: el flow engine NO esta confirmado; el "edge del flujo" era optimismo de n chico.** Conclusiones firmes: BB=breakeven (n=836), combo=flojo (40%). TEST DEFINITIVO pendiente: reconstruccion a 5 MINUTOS (fiel a la grabadora; plan Massive lo permite sin costo) — tarea fresca. Plan Massive = llamadas ilimitadas confirmado (20/20 sin 429).
