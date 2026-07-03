# SCALPER REVIEW — 2026-07-22 (Misión B4, ronda B)

Review adversario profundo de `scalper/` (FSM, dinero, parsers, recovery) + mejoras
aplicadas con tests. **Estado final: 39 unit tests (release + ASan/UBSan) y 13 replays
verdes en ambos binarios. Cero hallazgos de ASan/UBSan.**

Nota: una ronda previa del mismo día (backups `_pre_review0722.bak`) ya había añadido
tail.h testeable, saneo NaN/Inf, adopción de stale fills, recovery de contadores del día
y el veto de escaladas. Esta ronda (`_pre_review0722b.bak`) audita todo eso de nuevo y
cierra 4 hallazgos restantes.

## Hallazgos por severidad

### MEDIA (arreglados en esta ronda)
1. **`last_opt_bid_c_` no se reseteaba entre trades** (`scalper_core.h`). Escenario:
   trade 1 cierra (bid memorizado 63c) → trade 2 llena y el NBBO muere antes de la
   primera quote del contrato nuevo → la salida forzada a ciegas mandaba `SELL lmt 63c`
   con el precio del **contrato anterior**. Si ese precio quedaba por encima del mercado,
   la venta descansaba 2s+ (re-price) alargando una salida de emergencia. **Fix**: reset
   a 0 en `close_trade()` y `recover_holding()` → fallback honesto `lmt 1c` (= "fuera a
   cualquier precio", doctrina de salida forzada). Test: `fsm_last_bid_reset_entre_trades`.
2. **ENTRY_PENDING ignoraba HALT file y force-flat**. Un BUY podía descansar hasta
   ~4.5s (3×1.5s) después de que el humano pidiera parar con `scalper/HALT`, o pasado
   15:55. **Fix**: aborto de seguridad — cancel inmediato + IDLE + GATE_SKIP; el fill
   que le gane al cancel se adopta por la vía FILL_ADOPT existente y la posición se
   gestiona/cierra por doctrina normal. Tests: `fsm_entry_abort_halt_y_forceflat` +
   replay `13_halt_durante_entrada.jsonl`. No cambia la semántica de entrada: solo veta.
3. **NBBO jamás visto (`!und.ok()`) con posición no disparaba salida forzada**. El gate
   existente exigía `und.ok() && stale`; si el NBBO nunca fue válido (recovery sin
   `nbbo_qqq.txt`, archivo corrupto desde el arranque) la posición quedaba ciega hasta la
   ventana de 60s. **Fix**: `!ok()` con la misma gracia de 2s = misma salida forzada
   ("NBBO invalido con posicion"). Test: `fsm_nbbo_invalido_en_mano` (borde exacto
   2000/2001ms).

### BAJA (arreglado)
4. **Buffer de `find_open_position` (1024) < línea máxima del writer (2047)**
   (`ledger.h`). Una línea larga (reason 900c + overhead ≈1050c) se partía en dos chunks
   de `fgets`. Analizado: benigno hoy — los campos clave (ev/px_c/strike) viven en los
   primeros ~150 bytes del chunk 1 y el reason va escapado (jamás matchea `"ev":"FILL"`),
   pero era una bomba latente si el formato cambia. Subido a 2048 (paridad con
   `day_state`).

### INFO / verificado sano (no tocado)
- **FSM vs SPEC**: bordes ±1ms correctos y testeados (wait 2499/2500, ventana 59999/60000,
  gracia 2000/2001). Orden de checks en HOLDING correcto (salidas forzadas ANTES del
  early-return de profit_min/quote). Ventanas `[open, close)` coherentes con el spec.
- **Dinero**: todo int64 cents, mul-antes-de-div en `profit_reached` (máx ~2e11, sin
  overflow posible con los gates de cordura ≤$200k), RT 130c verificado por test, red
  neto ≤0 = HALT. `net` cabe en int para el HALT_WRITE.
- **Parsers**: NaN/Inf/absurdos vetados antes de `llround` (tests dedicados); `-1.00`
  sentinel preservado y vetado en selección; tail robusto a rotación/línea gigante/línea
  a medio escribir; CRLF tolerado. Menores no arreglados (riesgo≈0, archivos propios):
  `atoi(exp)` del header sin clamp de overflow; `vol/oi` con `%ld` sin usar; `cfg_set`
  no clampa valores negativos (config controlada por Yunior); rotación-a-archivo-más-
  grande en Tail salta contenido (documentado, conservador).
- **Recovery/kill -9 por estado**:
  - IDLE/ARMED_WAIT → limpio (nada en el ledger).
  - ENTRY_PENDING → sin FILL en ledger → arranca IDLE. En SIM la orden muere con el
    proceso; en Fase 4 live exigirá reconciliación de órdenes vivas vs broker (ya
    anotado en el spec — NO implementar ahora).
  - HOLDING → FILL sin TRADE_CLOSE → `recover_holding` con edad real del `tw`; más
    vieja que 60s = salida directa. Verde.
  - EXIT_PENDING → recuperada como HOLDING → re-emite la salida. En live habría un
    SELL huérfano en broker (misma reconciliación Fase 4).
  - Tras TRADE_CLOSE → `recover_day` restaura trades/día, cooldown y one-loss HALT
    (incluso con posición viva: la gestiona pero jamás re-entra). Verde.
  - Ledger O_APPEND+fsync por evento; reason acotado a 900c → la línea SIEMPRE termina
    en '\n' (test `ledger_trunc_y_daystate`).
- **SimAdapter**: fill model honesto (jamás mejora precio, adversidad como tiempo,
  cancel viaja y puede perder contra el fill), determinista por seed.
- **`scalper/HALT` es ruta relativa al cwd** en `run_sim` — convención "correr desde la
  raíz del repo" (igual que `data/`). No tocado; anotado.

## Escaladas 🐋📈 / SPIKES / MANADA — análisis y recomendación

**Datos verificados hoy**: `opt_whale_watch.py` escribe las escaladas en
`data/whale_alerts.jsonl` con `"prev":"ESCALADA"` (mismo `side`, volumen duplicado) y al
Desktop como "🐋📈 BALLENA CRECE". `flow_pulse` (SPIKES/MANADA) escribe SOLO al txt del
Desktop y su título no matchea el parser fallback (`🐋 BALLENA CALLS|PUTS`) — el scalper
ya los ignora estructuralmente.

**Recomendación: NO usar escaladas como señal de entrada.** Razones con números:
1. La táctica (regla 11) opera el EXTREMO local = el **flip** MID→CALLS/PUTS. La
   escalada es el mismo estado con el flujo duplicándose = evidencia de **continuación**,
   exactamente el caso excepción de la regla 11 donde el fade pierde (band-walk del líder,
   cazado NVDA 82k→248k calls). Entrar contra una marea que crece es perseguir.
2. El backtest es DATA-INSUFFICIENT (n=17, fade gana a +5min no +1min): añadir un
   gatillo nuevo sin base empírica viola la doctrina de probabilidades medidas.
3. **Como filtro de seguridad SÍ** — y ya está implementado y testeado: escalada en IDLE
   jamás arma; escalada del mismo símbolo+lado durante ARMED_WAIT **aborta** la entrada
   contraria (`fsm_escalada_veto`). Eso es lo máximo que la semántica actual admite.
4. **Pendiente de datos (no de código)**: cuando la grabadora acumule ≥30 alertas con
   escaladas, medir si "flip SIN escalada posterior en 2.5s" tiene WR mejor que el flip a
   secas; y evaluar MANADA de flow_pulse como veto adicional. Hoy: señal-contexto, no gate.

## Mejoras aplicadas (resumen)
| Archivo | Cambio | Test |
|---|---|---|
| `scalper_core.h` | reset `last_opt_bid_c_` en close/recover | `fsm_last_bid_reset_entre_trades` |
| `scalper_core.h` | aborto ENTRY_PENDING por HALT/force-flat | `fsm_entry_abort_halt_y_forceflat`, replay 13 |
| `scalper_core.h` | salida forzada con NBBO inválido (no solo stale) | `fsm_nbbo_invalido_en_mano` |
| `ledger.h` | buffer recovery 1024→2048 (= writer) | cubierto por `ledger_trunc_y_daystate` |
| `docs/SCALPER_SPEC.md` | contadores + gates nuevos documentados | — |

Backups: `backup/{scalper_core.h,ledger.h,core_test.cpp,SCALPER_SPEC.md}_pre_review0722b.bak`.

## Verificación final
- `./scalper/tests/run.sh`: **39 unit release OK, 39 unit ASan/UBSan OK, 13/13 replays OK**.
- Replays adicionalmente corridos con `whale_scalper_asan`: **13/13 OK, cero reportes del sanitizer**.
- SEÑAL-SOLAMENTE intacta: TwsAdapter sigue siendo stub que aborta; `--arm-live` retorna 3.

## Adenda del verificador adversario (2026-07-22, misma tarde)
Hallazgo CONFIRMADO sobre el fix (1): el reset de `last_opt_bid_c_` en
`close_trade`/`recover_holding` era INCOMPLETO. Una entrada abandonada
(NO_FILL/REJECTED/halt-cancel) no limpia `con_`; el driver sigue cotizando el
contrato abandonado via `held()` y re-contamina la memoria en IDLE. Test que lo
demostró: `fsm_last_bid_no_contamina_tras_no_fill` (falló con sell lmt 63c del
contrato abandonado en vez de 1c honesto). Fix: reset `last_opt_bid_c_ = 0` al
seleccionar contrato nuevo en ARMED_WAIT (la memoria pertenece SIEMPRE al
contrato seleccionado). Test extra: `fsm_halt_cancel_fill_gana_y_se_gestiona`
(fill gana al cancel con HALT aun puesto -> adopcion + salida forzada, sano por
inspeccion, ahora clavado en test). Suite final: **41 unit release OK, 41 unit
ASan/UBSan OK, 13/13 replays con AMBOS binarios recompilados**. `--arm-live`
re-verificado: exit 3. Backups: `backup/*_pre_verif0722.bak`.
