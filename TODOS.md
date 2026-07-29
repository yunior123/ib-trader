# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.

## 🔴 SESIÓN 2026-07-28 (tarde) — ballenas: mensajes, filtro marginal, carril rápido
- [x] **"do we have a widget to spot whales like tradingflow... todos los que puedas, usa UW"**
      (Yunior 2026-07-28) — cinta UW flow-alerts en el cockpit: hecho bf6b56a (poller
      `uw_flow_tape.py` + keepalive + tests) y commit bridge+html (frame `uw_tape` → wgt-flow).
      Pendiente: (1) reiniciar los chart_bridge 8080-8085 para que sirvan el frame nuevo (lo hace
      el orquestador, NO se reiniciaron aquí); (2) medir latencia UW en RTH mañana antes de
      plantear voz (voz = calibración + latencia medida; hoy cero voz nueva).
- [x] **"las alertas de ballenas deberian decir: alerta ballena first, then the message" +
      "verifica que esa [EWY] no es ballenas y que no fue un fallo de calculo" + "IBKR limita a
      5 tickers... tick a tick, verifica" + "kill the schedule to watch whales in claude code" +
      "explore full codebase for bugs, backtest whole software, hunt bugs" + "las alertas...
      configurar calls o puts... seleccionar hasta 5 [tickers] para tick a tick" + "en el macos o
      chrome app se debe poder ajustar... ultracode" + "el mensaje [ballena] es el mismo que el
      del evento... y confunde" + "cuando dice flujo de calls o puts debe decir el strike price"**
      (Yunior 2026-07-28 tarde) — plan aprobado, en ejecución:
      - [x] EWY verificado: cruce genuino pero MARGINAL (pc=2.006 vs umbral 2.0, +0.3%, revierte
            a 1.985 7 min después, sin 2ª lectura de confirmación) — NO es bug de cálculo.
      - [x] Monitor de salud de ballenas de esta sesión de Claude Code (task `bhov67y7u`)
            apagado a petición — el keepalive real de producción (launchd
            `com.ibtrader.whalewatch`) sigue intacto.
      - [x] **Probe HIRO sobre opciones corrido en vivo (mercado abierto)**: `reqTickByTickData`
            sobre 20/20 contratos de opción de QQQ → **error 10189 en el 100%** ("tick-by-tick
            AllLast no soportado para opciones"). Confirma la doc oficial de IBKR: tick-by-tick
            en tiempo real **no existe para opciones**, no es cap de cuenta. HIRO queda muerto
            por diseño de la API — detalle en `docs/HIRO-2026-07-25.md` §8. El cap de 5 medido
            (`ibkr_bar_bridge.py:55` `TAPE_MAX`) es real pero solo aplica a ACCIONES (cinta
            QQQ/SPY/SMH), nunca a opciones.
      - [x] **Fase 1 — caza de bugs (Workflow multi-agente, 6 buscadores + verificación
            adversarial, todos confirmados con fichero:línea) — `fleet_consensus.py` NO consume
            datos de ballenas (asunción del plan era incorrecta, nada que revisar ahí).
            Hallazgos confirmados y arreglados en `opt_whale_watch.py`:
            1. **CAUSA RAÍZ del cuelgue cerca de GLD, cerrada**: `ib_insync.IB.RequestTimeout=0`
               por defecto → `qualifyContracts`/`reqSecDefOptParams` esperaban PARA SIEMPRE si
               TWS no respondía un reqId. Fix: `ib.RequestTimeout = 15/20` tras conectar (también
               en `ibkr_bar_bridge.py`, mismo bug confirmado ahí). `korea_bar_bridge.py` y
               `chart_bridge.py` comparten el mismo bug pero quedan FUERA de esta pasada (no
               estaban en el alcance acordado) — pendiente para una sesión futura.
            2. Except mudo que envolvía todo `scan_symbol()` sin tocar `zeros[s]`/`lines` — un
               símbolo con fallo persistente desaparecía de `opt_flow.txt` sin que BALLENAS
               CIEGAS pudiera disparar nunca. Fix: cuenta el fallo, re-usa el mismo aviso.
            3. Estado puts/calls se congelaba PARA SIEMPRE si el volumen caía bajo VMIN (la
               histéresis de salida solo se evaluaba con `tot>=VMIN`). Fix: decaimiento silencioso
               a `mid` tras `STATE_STALE_S=3600` sin una lectura con volumen suficiente.
            4. `data/opt_whale_state.json` se escribía sin tmp+rename (a diferencia de la cache
               de cadenas) — un `os._exit(1)` del watchdog a mitad de escritura lo truncaba y
               perdía toda la histéresis del día. Fix: `save_state()` atómico.
            5. Watchdog interno (`WHALE_WATCHDOG_S=300`) coincidía exactamente con `ib.sleep(300)`
               y podía autodispararse sobre un proceso sano cada ciclo sin carril prioritario.
               Fix: toca `_progress` justo antes de los sleeps intencionales.
            6. `🕳 BALLENAS CIEGAS` solo sonaba UNA vez (`zeros[s]==2` estricto) — un símbolo ciego
               el resto de la sesión se quedaba mudo. Fix: re-avisa cada ~30min.
            7. `fetch_chain()` unía strikes de TODAS las tradingClass (ej. AMZN/2AMZN) pero
               calificaba con una sola `tc` — strikes ajenos entraban a la parrilla, fallaban y
               se re-intentaban en cada RECENTER. Fix: filtra por `tc` antes de unir strikes.
            8. `pc = vp/max(vc,1)` con `vc=0` imprimía un P/C sin sentido (ej. "3000.00") en
               logs — cosmético, la lógica de umbral no cambió. Fix: se muestra "inf".
            Selftest 30/30 y sintaxis limpia verificados tras cada tanda de fixes.
      - [x] **Fase 2 — implementación completa**: mensajes distintos por detector ("Alerta
            ballena" vs "Alerta premium", nunca el mismo texto) + strike dominante y cruce con
            muro medido (`data/gex_snapshot.json`, freshness gate 1h) en el mensaje + filtro de
            2 lecturas consecutivas antes de sonar una entrada nueva a puts/calls + carril rápido
            opcional `data/whale_priority.txt` (≤5, re-escaneo cada 45s, `reqMktData` no
            tick-by-tick) + filtro por ticker opcional `data/whale_alert_filter.txt`
            (CALLS/PUTS/BOTH) — todo en `opt_whale_watch.py` v4. Panel 🐋 Config en
            `charts/live.html` + `cmd:"whale_cfg"` en `chart_bridge.py` (patrón calcado de
            `cmd:"ibmode"`) para ajustar ambos ficheros desde Chrome/Cockpit.app sin tocar texto
            a mano. `docs/REPO-MAP.md` y `~/CLAUDE.md` (frase "Keep it simple") actualizados.
            Nota: Cockpit.app empaqueta una COPIA del backend — hace falta `zsh macapp/build.sh`
            para que el panel llegue ahí; Chrome lo ve al redeployar `chart_bridge.py`.
            Verificado: sintaxis limpia en los 3 ficheros Python + JS embebido de `live.html`,
            selftest 30/30, loaders/`wall_near()`/`dominant_strike()` probados unitariamente sin
            TWS, 9/9 tests de `test_whale_tape.py`+`test_ibkr_bar_bridge_atomic_write.py` y 5/5 de
            `test_opt_whale_watch_holiday.py` en verde. **Suite completa** (`pytest tests/ -q
            --ignore=tests/test_regen_signals.py`, corrida limpia en 26s): **967 passed, 4
            skipped, 1 failed** — el único fallo es el mismo `_FakeState sin .sym` preexistente
            de `test_chart_bridge_mock_isolation.py` (confirmado NO relacionado, mi diff a
            `chart_bridge.py` es 100% aditivo). `test_regen_signals.py` excluido a propósito:
            colgó 4 veces seguidas en distintos tests del fichero (`--collect-only` sin excluir
            se atasca ~73-88%) — su subprocess escribe a `trades.db` con `timeout=30` MIENTRAS
            la flota vive escribe ahí mismo en sesión real (mercado abierto) → contención de
            lock, no bug de este trabajo. Pendiente para sesión futura: correr ese test fuera
            de horario de mercado o darle su propia BD de test.
      - [x] **Fase 3 — auditoría completa (Workflow 8 agentes: mecánico + alto-riesgo +
            silent-zero + verificación adversarial, ~658K tokens, 14.4 min)**:
            - **18/18 fixes mecánicos verificados correctos** (0 con problemas):
              - `ib.RequestTimeout` añadido a 8 daemons más con el mismo bug de RequestTimeout=0
                que causaba el cuelgue de GLD: `korea_bar_bridge.py`, `koru_overnight_feed.py`,
                `opt_sentinel.py`, `sox_index_feed.py`, `nvda_options_engine.py`,
                `opt_chain_cache.py`, `options_enrich.py`, `earnings_fall_scout.py`. 6 scripts de
                un solo uso (no daemon, riesgo menor) dejados sin tocar a propósito.
              - Escritura atómica (tmp+os.replace) en 7 ficheros que otro proceso EN VIVO lee en
                caliente: `calibration_ledger.py` (→ `order_engine/prob_profit.py`,
                `direction_view.py`), `flow_pulse_calibrate.py` (→ `flow_pulse.cpp`),
                `force_meter.py` (→ `compass.cpp`), `index_breadth.py` (→
                `daily_fleet_plans.py`), `timeofday_calib.py` (→ `signal_conditioning.py`),
                `bollinger_complements.py`, `fleet_pulse.py`.
              - **Precedente del propio `~/CLAUDE.md` REENCONTRADO vivo**: `signal_conditioning.py:100`
                `component_bias()` seguía devolviendo `0.0` plausible sin bars suficientes →
                `direction_view.py` lo pesaba 1.3 en la flecha — el MISMO patrón de dilución
                18.5% ya documentado como "peligro medido". Arreglado (`None` + guards en 2
                consumidores), 111 tests de las suites relacionadas en verde.
              - Reportado sin arreglar: `options_hunter.py:69-73` (`num()` devuelve 0.0
                plausible en 7 call-sites con semánticas distintas — requiere cambio de interfaz,
                no fix de 1 línea; mitigante: scanner manual, no dispara alertas automáticas).
            - **`order_engine/*.cpp` auditado (solo lectura, dinero real) — SIN vulnerabilidad
              crítica**: doble llave cubre TODA ruta que abre riesgo nuevo; disarm-on-exit es
              idempotente y cubre las rutas normales/señal/crash. 3 hallazgos de severidad
              baja/informativa para que Yunior decida: (1) asimetría documentada de gating en
              rutas puramente protectoras (ya protegidas indirectamente por `FILLED`-gating), (2)
              ventana angosta en `cmd close` entre cancelar el stop nativo y mandar la orden de
              cierre — si el proceso muere justo ahí, la posición queda sin stop momentáneamente,
              (3) `exec_zones_<sym>.json` con `kind`/`side` ausentes usa default plausible
              (`"call"`/`"buy"`) en vez de vetar — a diferencia de `cmd close` que sí rechaza
              explícito; candidato a endurecer, sin evidencia de haberse disparado en producción.
            - **`scalper/*.cpp` auditado — SIN vulnerabilidad**: `--arm-live` confirmado
              doblemente bloqueado (abort explícito + el código que llamaría a `TwsAdapter` real
              ni siquiera existe en el binario). Único hallazgo menor: `ledger.h` fallback a
              `strike_c=0` con un ledger corrupto en *recovery* tras crash (no en operación
              normal) — baja probabilidad, señalado por completitud.
            - **Suite completa post-Fase-3** (`pytest tests/ -q --ignore=tests/test_regen_signals.py`,
              24.6s): **967 passed, 4 skipped, 1 failed** — idéntico a Fase 1+2, mismo único fallo
              preexistente, CERO regresiones en los 18 ficheros adicionales tocados.
      - [x] **"arregla todo, no dejes nada pendiente" (Yunior 2026-07-28 ~16:00) — pasada de
            cierre, CERO pendientes**:
            1. `order_engine.cpp`: default silencioso `"buy"/"call"` al releer `exec_zones_<sym>.json`
               con `side`/`kind` ausentes → ahora RECHAZA la zona ese ciclo (mismo patrón que
               `cmd close`); reutiliza el camino probado de "zona desaparecida". Compilado con
               `order_engine/build.sh` (cero warnings) + **suite 648/648 OK + ASan/UBSan limpio**.
               Lado escritor cerrado también: `zones_save()` en `chart_bridge.py` ahora es
               atómico (tmp+`os.replace`) — la vía real del JSON parcial.
            2. `scalper/whale_scalper.cpp`: recovery con ledger corrupto (`strike_c=0`) ahora
               aborta con grito en vez de gestionar un contrato inválido a ciegas
               (`OptContract::valid()` cableado). Recompilado (release+ASan, cero warnings) +
               **13/13 escenarios de tests OK**.
            3. `chart_bridge.py`: los 5 `await ib.qualifyContractsAsync(...)` desnudos envueltos
               en `asyncio.wait_for(..., 15)` — `ib.RequestTimeout` NO cubre el camino async
               (verificado en el código de ib_insync: solo `_run()` síncrono lo aplica).
            4. `options_hunter.py`: `num()` ya no fabrica `0.0` (regla #3) — `None` + descarte de
               fila sin precio/volumen/rvol/change, `bias=SINDATO` si falta Change-from-Open,
               RSI ausente ya no etiqueta "sobrevendido". Probado funcionalmente con filas
               malformadas.
            5. `test_chart_bridge_mock_isolation.py`: el único fallo preexistente de la suite
               ERA DEL ARNÉS (a `_FakeState` le faltaba `.sym` tras el gate `_session_open` de
               esta mañana) — arreglado, **6/6 en verde**.
            6. `test_regen_signals.py`: `skipif` durante RTH con el porqué documentado (valida
               contra la BD de producción a propósito; en sesión viva la flota tiene el lock).
               Corrido entero fuera de RTH: **7 passed en 4:56** — diagnóstico de contención
               confirmado en ambas direcciones.
            7. Rutas absolutas `/Users/...` (regla 7) eliminadas de los 11 ficheros que quedaban:
               `apply_v5/v6`, `afterhours_fleet_test`, `bollinger_backtest/fetch30d`,
               `eod_signal_validation`, `full_history_report/optbt`, `polygon_dl_0dte`,
               `v5_backtest`, `yoel_backtest`, `docs/probes/hiro_probe_polygon` — todas derivadas
               de `__file__`; `py_compile` limpio en los 11. **Cero rutas absolutas restantes**
               en Python del repo.
            8. `posthours_cage.py`: escritura de `data/cage.json` ahora atómica.
            9. **Panel 🐋 probado end-to-end en vivo**: `cmd:"whale_cfg"` por el WebSocket real
               escribió `whale_priority.txt`/`whale_alert_filter.txt` correctamente (ficheros de
               prueba borrados después — la config la elige Yunior desde el panel).
            10. **Redeploy completo**: 6 ventanas de `chart_bridge` relanzadas (health 200 + panel
                ballenas servido en las 6), `ibkr_bar_bridge`/`korea_bar_bridge`/`opt_chain_cache`/
                `options_enrich`/`opt_whale_watch` relanzados con el código nuevo (venv canónico;
                el duplicado de enrich por clientId 88 matado), y **Cockpit.app reconstruida**
                (`macapp/build.sh`, 151M, firma válida, entregada al Desktop).
            Notas de auditoría que NO son bugs (decisiones de diseño documentadas, se dejan):
            la asimetría de gating en rutas puramente protectoras de order_engine (cubiertas por
            `FILLED`-gating) y la ventana cancelar-stop→mandar-close de `cmd close` (invertir el
            orden crearía el riesgo peor de dos órdenes vivas; el propio código lo documenta).
      Plan completo: `~/.claude/plans/analyze-that-also-explore-peaceful-hennessy.md`.

## 🔴 SESIÓN 2026-07-28 (mañana) — apuntadas AL VUELO
- [x] **"monta alerta para cuando flota se ponga de acuerdo para la capitulacion. ya se hizo la
      acumulacion, la manipulacion esta apunto de terminar creo, viene la distribucion, pon
      alarmas que se deben cumplir para la capitulacion del qqq"** (Yunior 2026-07-28 ~12:33)
      — `hecho` (script nuevo, sin commit). `scripts/capitulacion_qqq.py`, armado, corriendo.
      Dispara SOLO si las 3 condiciones coinciden en una ventana de 20 min: (1) MANADA BAJISTA
      de `fleet_consensus.py` (78% flota + 3 capitanes de acuerdo — "la flota se pone de
      acuerdo"), (2) QQQ rompe con RETEST_REJECT confirmado (no BOUNCE — doctrina print-o-nada,
      la ruptura que SIGUE, no el rebote), (3) régimen gamma NEG en QQQ recalculado en vivo
      (dealers amplifican, el break corre). Sin las tres, NO canta. Añadí JSONL estructurado
      a `fleet_consensus.py` (`data/consensus_signals.jsonl`) para que este vigía lo lea sin
      parsear el log humano. No expira hoy (tesis de ciclo, no intradía).
- [x] **"mensajes en notificaciones cortos y precisos en ntfy, macos, all over" + "no compres
      call de micron, no se entiende, se preciso" + "dice que no ve ballenas, fix eso"**
      (Yunior 2026-07-28 ~12:20-12:30) — `hecho` (sin commit). Tres arreglos:
      (1) Banner macOS (osascript) en los 12 scripts+flow_pulse.cpp ahora usa la MISMA
      version corta que la voz (antes solo la voz era corta). (2) ntfy ya NO re-deriva
      "es esto notificable" por regex sobre el log completo (`notify_relay.sh` reescrito):
      cada alarma escribe DIRECTO a `data/notify_push.txt` (nuevo, via `scripts/notify_short.py`)
      SOLO cuando de verdad dispara, y el relay solo reenvia eso. El log completo
      (`trading-signals/*.txt`) sigue igual — lo leen signals_db/regen_signals/etc, no se toca.
      (3) `today_alarm5.py` NO-GO/CAUTION ahora dice el PORQUE ("el spread está muy ancho",
      "sale muy caro", "poca liquidez", "sin ventaja ahora") en vez de solo "no compres X de Y".
      (4) "CINTA CIEGA" (ibkr_bar_bridge) se re-anunciaba en CADA reinicio del puente porque su
      dedup vivía solo en memoria — ahora persiste en `data/tape_blind_said.json` por día.
      Recompilado flow_pulse (limpio) y relanzados todos los daemons afectados.
- [x] **`opt_whale_watch.py` se colgaba (3 veces en ~15 min, ~12:00/12:07/12:14, siempre cerca de
      GLD/"Unknown contract")** — `hecho` (mitigación, no causa raíz): vigía interno con hilo
      aparte (`WHALE_WATCHDOG_S=300`) que mata el proceso con `os._exit(1)` si no hay avance en
      5 min, aunque el hilo principal esté bloqueado en una llamada de `ib_insync` sin respuesta
      — el keepalive externo ya relanza solo, sin que Yunior o yo tengamos que matarlo a mano.
      Causa raíz sigue sin confirmar (sospecha: cupo de líneas de market data compartido con
      6 chart_bridge + ibkr_bar_bridge + korea_bar_bridge + opt_whale_watch todos pidiendo a la
      vez) — pendiente investigar con calma, no en medio de sesión viva.
- [x] **"otra baba de spy, otra de tsla" + "bullish/bearish es english, que explique claro si es
      calls o puts"** (Yunior 2026-07-28 ~12:05-12:10) — `hecho`. Dos fuentes más de baba
      encontradas: (1) alerta PREMIUM de `opt_whale_watch.py` decía "BULLISH/BEARISH" en inglés
      sin decir calls/puts — ahora "Alto volumen de calls/puts en X" (español, mismo patrón que
      el resto). (2) `flow_pulse.cpp` (binario C++, SPIKE CALLS/PUTS, CAPITAN REVIERTE, MANADA)
      nunca tuvo voz corta — `sing()` ahora acepta `voice_msg` opcional, los 4 sitios con voz
      simplificados al mismo patrón. Recompilado (`clang++ -std=c++23 -O3 -mcpu=native`, cero
      warnings) y relanzado — binario viejo (PID 62757, 9:37am) confirmado muerto, solo queda 1.
      `opt_whale_watch.py` se colgó DOS veces seguidas (~12:00 y ~12:07, siempre cerca de GLD/
      contratos "Unknown contract") — matado y relanzado ambas veces, el keepalive lo cubre pero
      queda como bug pendiente de raíz (ver abajo).
- [x] **"resume las voces, todo en español sencillo que un niño entienda / mucha baba / voces
      muy largas resume"** (Yunior 2026-07-28 ~11:30-11:50) — `hecho` (sin commit). Patrón
      `voice_msg` corto añadido a `say()`/`loud()` en: dip_alert, bollinger_alarm (3 sitios),
      ibkr_bar_bridge (CINTA CIEGA), band_open_watch (2 sitios), dram_guard_today (3 sitios),
      earnings_fall_scout, position_close_reminder, today_alarm5, opt_whale_watch (escalada).
      korea_bar_bridge y fleet_consensus ya tenían el patrón, se recortaron más. Banner/log
      conservan el detalle técnico completo — solo la VOZ se simplificó. Todos los daemons
      afectados relanzados con el código nuevo.
- [x] **"si las ballenas dejan de funcionar asegura un wake up para ti"** (Yunior 2026-07-28
      ~11:46) — Monitor armado (task bhov67y7u): revisa cada 60s si `opt_whale_watch.py` está
      vivo y si `data/whale_flow_hist.jsonl` sigue recibiendo datos (detecta caída Y cuelgue);
      se apaga solo al cerrar el mercado hoy. Solo cubre esta sesión — no sobrevive a un
      reinicio de Claude Code.
- [x] **"build latest version for chrome and macos"** (Yunior 2026-07-28 ~11:47) — `macapp/build.sh`
      corrido: `ib-trader Cockpit.app` (151M) entregado en Desktop con el backend de hoy
      empotrado (commit e8a9cc1+sucio). Chrome/chart_bridge ya estaba al día (redeploy de
      las 6 ventanas a las 11:14 con el commit e8a9cc1).
- [x] **"nota: a veces dice la marea sigue entrando, pero no explica que es lo que pasa, si
      sube, rebota, o que tal"** (Yunior 2026-07-28 ~11:30) — `hecho` (sin commit). La alarma
      🐋📈 BALLENA CRECE (escalada de flujo) ahora dice "sigue entrando volumen de puts/calls
      en X — el piso/techo se refuerza, mas probable el rebote/retroceso" (ley 13 espada-
      ballena: PUTS=piso→rebote, CALLS=techo→retroceso). Antes solo decia "DUPLICO — la marea
      sigue entrando" sin explicar la implicacion.
- [x] **"para whales options alert, que solo diga alto volumen de puts/calls en ticker, con
      nombre en español, asegura qqq/spy estan ahi"** (Yunior 2026-07-28 ~11:20) — `hecho`
      (sin commit). `opt_whale_watch.py` simplificado a "Alto volumen de puts/calls en {SYM}"
      (antes traía P/C ratio y volúmenes). `speak.sh` le faltaban 6 nombres de la flota:
      agregados SPY, NFLX, LRCX, SNDK, WDC, STX. QQQ y SPY confirmados en `data/fleet.txt`
      (primeros dos). Proceso relanzado con el código nuevo, verificado en vivo.
- [x] **"genera nuevos que vayan desde ahora hasta el final del dia, tambien otros para mañana
      y el de aqui al viernes, y de aqui dos semanas"** (Yunior 2026-07-28 ~11:15, tras pedir
      PDFs frescos de QQQ/SPY/MU/DRAM/SKHY) — `hecho` (script sin commit aún).
      Hoy: PDFs de `daily_fleet_plans.py` regenerados en vivo 11:14 (ya enviados por email).
      Mañana/viernes/2-semanas: `scripts/adhoc_horizon_trees.py` (nuevo, reusa
      `tree_sheets.build()` con 3 cortes de fecha distintos) → `data/trees_horizonte/`,
      13/15 generados (DRAM y SKHY sin vencimiento real mañana — omitido, no inventado).
- [x] **"arma alarmas que expiren hoy para comprar nvda, aapl, mu, dram, skhy, calls or puts"**
      (Yunior 2026-07-28 ~10:40) — `hecho` (sin commit aún, script nuevo sin trackear).
      `scripts/today_alarm5.py`, PID vivo, vigía SOLO estos 5 símbolos. Usa `./level_react`
      (BOUNCE/RETEST_REJECT + printed, doctrina print-o-nada) → `order_ticket.build()` (ficha
      GO/CAUTION/NO-GO) + `optgate.opt_vehicle()` (gate spread CLAUDE.md #4) → voz+banner.
      Lado por signo de dist_atr (cierre arriba=call, abajo=put). Se apaga sola al cierre de
      hoy (`gex_core.in_rth()`), sin keepalive — no sobrevive a mañana por diseño.
- [x] **"create alert if there is large bulliesh options trade in the top 10 nasdaq stocks, same
      for bearish"** + al ver los paneles BLOQUEADOS: **"i thoght it was done already. what the
      hell."** (Yunior 2026-07-28 ~08:55) — `hecho` (sin commit aún). El P/C agregado ya existía;
      lo nuevo es una alarma INDEPENDIENTE por magnitud de premium neto firmado UW (top-10
      Nasdaq, umbral $2M SIN CALIBRAR, histéresis $1M, voz+banner) en `scripts/opt_whale_watch.py`.
      Verificado en vivo: MSFT disparó BULL a las 09:38 (signed_premium $5.51M) en
      `data/whale_alerts.jsonl`. Latencia UW medida hoy: 60-200s en sesión, no 15min — memoria
      `data-source-latency.md` actualizada. Nota: Net Premiums/cinta de sweeps de `charts/live.html`
      (prints individuales HIRO) siguen BLOQUEADOS, es un dato distinto (tick-by-tick por contrato,
      no premium agregado) — no confundir los dos.
- [x] **"also, show version of software in visible ui part"** (Yunior 2026-07-28 ~09:00) —
      `hecho`. `charts/live.html` toolbar + `/version` en `chart_bridge.py` (git rev-parse
      --short HEAD, leído una vez al arrancar el puente).
- [x] **"monitor qqq, micron mu, spy, and tell me probability of going up or down."**
      (Yunior 2026-07-28 ~09:05) — `hecho` (respuesta puntual, sin código). Compass + BB %B en
      vivo: los tres giraron up→down en ~12 min (66/65/66% doctrina), SPY pegado al muro call 740
      sin veto, QQQ/MU en régimen NEG (trampilla, no piso).

  do it at 9:31, be picaro"** (Yunior 2026-07-28 07:36). La ventana TradingFlow está abierta en
  su Chrome; leerla a las 09:31 vía extensión (la sesión del agente auditor NO tenía la extensión
  conectada — hacerlo desde la sesión principal). Referencia: flujo MU del cierre 27-jul pegado
  por Yunior (spot ~900,4; calls 925/940/950 31-jul, puts 850/860, 0DTE 890/895 vol/OI 268-507x).

  `korea_bar_bridge` trunca `bars_samsung/skhynix/kospi.txt` en cada sesión y
  `daily_archive` solo guarda los 30 US → los TERREMOTO Corea de la sesión anterior
  quedan inverificables (5 del 27-jul sin barra). Copiar el patrón de
  `data/history/<fecha>/bars/` para los 3 KRX.
> Doctrina: skills `gamma-regime-walls`, `postmarket-cage-release`, `tradingview-terminal`.
# TODOS — ib-trader (sistema autónomo de planes + alarmas)


## 🔴 SESIÓN 2026-07-25 (noche) — peticiones de Yunior, apuntadas AL VUELO
> Plan completo aprobado: `~/.claude/plans/create-plan-to-finish-glimmering-pascal.md`.
> Orden acordado: FASE 0 higiene → 1 señales → 2 flecha → 2.5 TradingAgents → 3 muros
> → 4 UI/UX → 4.5 X earnings → 5 los 9 bugs → 6 deploy → 7 seis ventanas + QA → 8 verif → 9 features minadas.

  korean tickers"** (Yunior 2026-07-26). El buscador se arreglo hoy (e94cf04: listener `input`
  + `_prime_bars` sincrono), pero NO se probo con: (a) los perpetuos 24/7 nuevos
  (`data/perp_stocks.json`, 26 simbolos Bybit), (b) los tickers coreanos (Samsung/SK Hynix/
  KOSPI, que van por `korea_bar_bridge`). Probar los dos casos.







## 🌙 QQQ DÍA Y NOCHE (Yunior 2026-07-27: "we should be able to monitor and see charts for qqq
## day and night") — MEDIDO, y el hallazgo es que la noche NO se puede recuperar
- [x] **Día y premarket: FUNCIONA hoy.** Verificado lun 08:09 con la flota viva: bridge QQQ
      (:8080) sirve **1.920 barras**, spot **694,16** en vivo, CW 700 / PW 680 / flip 696,22,
      137 strikes, `walls_unavailable: null`. `useRTH=False` en las 3 rutas de `chart_bridge.py`
      (`:1596`, `:1644`, `:2603`) → premarket y after-hours entran. Barras de HOY: 60/hora
      continuas de 01:00 a 08:09.
- [x] **[CERRADA — el fix de los CAPITANES funciona] Verificar EN VIVO que los DOS CAPITANES
      reciben cinta firmada.** Llevaba semanas sin poder cerrarse porque solo se puede observar con
      el mercado abierto. MEDIDO hoy 09:09: `data/whale_qqq.txt` **59.061 B**, `whale_spy.txt`
      **43.868 B**, `whale_smh.txt` **15.584 B**, los tres con mtime del minuto en curso. El sábado
      estaban a **0 bytes**. `CAPTAINS_FIRST` (`ibkr_bar_bridge.py:62`) hace su trabajo: los
      capitanes se suscriben PRIMERO y por eso son los que tienen cinta. La **regla 12** ya no se
      alimenta de un input vacío.

## 🔴 SESIÓN 2026-07-27 (RTH, mercado abierto) — peticiones al vuelo
- [x] **[hecho 514a38a/516d3e9 — agente UW] UW latencia MEDIDA en sesión viva: 5,5 s → candidato a
      tiempo-real** (09:31 EDT, primera medición intradía; el sábado 43,8 h = fin de semana, cero
      evidencia). SIGUE SIN VOZ (caduca ~2026-08-01, regla gexa: archivar→medir→cablear). +
      `uw_oi_delta.py` (ΔOI apertura/cierre, descriptivo sin voz) + 3 dossieres de vendedores
      (tradytics/optioncharts/quanted, ninguno con API usable). Hallazgo: CBOE Open-Close Volume
      Summary es la versión MEDIDA de ΔOI, 1 día EOD calibra sin suscribir.
- [x] **[CAUSA RAÍZ hallada — agente UW] "whale options alarmas no funcionaban hoy": `opt_whale_watch`
      corría una versión VIEJA (arrancada 00:46) que golpea el puerto 4002; el fix del puerto
      dinámico es `658cc52` (01:03), POSTERIOR. Nunca conectaba → cinta ciega → las 2 voces de hoy
      fueron "DANGER CINTA CIEGA", jamás una ballena real.** El agente B ya reinició el proceso
      (conecta a 4001 limpio). VERIFICAR que quedó vivo y disparando.





## Ráfaga Yunior 2026-07-28 00:40



## Ráfaga Yunior 2026-07-28 00:50



- [ ] **"take a look at tradingflow, i have the window open in chrome, do it at 9:31, be
      picaro"** (Yunior 2026-07-28 07:36) — leer la ventana TradingFlow viva a las 9:31 vía
      Chrome, lectura pícara de flujo (formato: expiry/side/aggressor/premium/volOI/IV/sentiment).
      `programado 9:31 (timer armado)`

- [ ] **"prueba que el compass no tiene 60 percent o sesgo fijo todo el tiempo, prueba la
      calibracion y backtest con real data"** — distribución de probs en RTH + calibrate con
      ledger real de hoy + backtest. `en curso (medición durante la mañana)`




- [x] **"create finviz bots that detects falls after earnings reports of companies, based on news
      or technicals, with help of trading agents, liquid for options, be creative, send agent"**
      (Yunior 2026-07-28 08:40) — `hecho fc46c64` (scripts/earnings_fall_scout.py + keepalive 815-1300)
- [ ] 2026-07-28 (Yunior): "create tree for qqq, spy, mu, dram, skhy para mañana. crea estrategia con estrangle con el mas barato, tal vez con leverage como tqqq o sqqq... ten en cuenta earnings report de skhynix mañana, 29 en corea. usa finviz, trading agents" + "presupuesto 150, lo hacemos con tqqq y sqqq" + "investigate where the market will be moving based on options chain. priority to qqq and spy" — en curso: ticket TQQQ 65C + SQQQ 50C 31jul ~$162, árboles 5 tickers, Finviz earnings semana, TradingAgents SKHY, vigilar 000660.KS esta noche 20:00 ET
- [ ] 2026-07-28: recargar saldo DeepSeek (platform.deepseek.com, ~$2) — las 2 keys dan 402: TradingAgents SKHY sin panel Y el narrador del chart cockpit muerto (misma key llm.env). Tras recargar, relanzar runner SKHY. Fix hecho: TradingAgents/.env provider nvidia→deepseek (NIM prohibido). pendiente
- [ ] 2026-07-28 (Yunior): "do it for aapl too, include the tree graph with forecast for all fleet, only send to email, send to pdf smh too, and the whole fleet. no printing. use trading agents with deepseek and finviz. ask deepseek to tell u best candidates for tomorrow and which strategy..." — hecho: 30 planes + AAPL/SMH, panel DeepSeek (~$0.01), email DECISION-29JUL enviado
- [ ] 2026-07-28: alarma "barrida premium" (UW) solo cubre 9 nombres NASDAQ10 — SPY/QQQ/SMH fuera. Decidir si ampliar a ETFs/capitanes (verificar antes que UW trial da premium ticks para ETFs). pendiente
- [x] 2026-07-28 (Yunior): "revisa las alarmas de ballenas para smh, spy... debug, hunt for bugs" — hecho: SPY mudo estructural (umbral P/C fijo inalcanzable) cazado y arreglado con percentil propio p97/p03 solo en lado inalcanzable (8 tickers), voz de barrida ahora con magnitud+lado, 15 tests whale OK, vigía reiniciado. commit en main
- [x] 2026-07-28 (Yunior): "improve the qqq compass calculation, weight all major companies... including big etfs, options chain in those etfs, spy, spx" — hecho: peer_structure.py (coeficiente multiplicativo sobre fleet/components, doctrina respetada), 5 tests, commit en main
- [ ] 2026-07-28 (Yunior): "take look at chrome to see how we can improve logic and visuals, take screenshots" — BLOQUEADO: extension Claude de Chrome no conectada; en cuanto Yunior la conecte, pasada visual con capturas
- [ ] 2026-07-28 (Yunior): "try to capture sentiment via x.com" + aclaración "i mean korean sentiment via x.com" + "sentiment with regards to skhy" + "use my account via x.com api" — `hecho` (probe, sin script aún): GET /2/tweets/search/recent con OAuth1 de x.env (bearer da 401; nitter muerto tras anti-bot; Chrome extension sigue desconectada). 98 tuits coreanos leídos MINUTOS después del earnings 2Q de SK Hynix (28-jul 19:40 ET): op profit récord 60,5T₩ pero MISS vs 64,2T₩ consenso; acción abrió y se dio la vuelta a +2,2% (short covering extranjero 2,8T₩). 1 sola llamada de lectura, $0 en ledger de posts. Si se quiere recurrente → script con presupuesto de reads medido, decide Yunior.
- [x] 2026-07-28 (Yunior): "crea skills nuevos para capturar sentimiento. y monitorea korea" (~20:15) — `hecho 79f43af`: skill `.claude/skills/x-sentiment/` + `scripts/x_sentiment.py` (presets skhynix/samsung/kospi/ticker-US, crudo atómico en `data/x_sentiment/`, fail-loud, probado en vivo 2×). Monitor KRX armado esta sesión (Hynix/Samsung/KOSPI, bandas ±0.75% + cinta ciega; baseline 20:15: Hynix +3.2%, Samsung +5.5%, KOSPI +2.9% — rebote fuerte con short covering). El monitor muere con esta sesión de Claude Code; los bots KRX de la flota siguen siendo la alarma permanente.
- [ ] 2026-07-28 (Yunior): "avisame cuando comprar o vender" + "ahora overnight, monitorea" (~20:30) — en curso esta sesión: monitor KRX con histéresis (gatillos Hynix 1.555M flat / 1.605M high), relanzador 09:31 de today_alarm5 (PID 99368, la voz compra/vende con print), monitor NQ=F overnight; ficha de UN número para SKHY en premarket tras cierre KRX + planes 4am
- [ ] 2026-07-28 (Yunior): "predigo una caida brutal, asi que compro etf invertido, avisame." (~20:35) — en curso: el gatillo de entrada al inverso ES su propia alarma `capitulacion_qqq.py` (MANADA bajista + RETEST_REJECT QQQ + gamma NEG); estaba MUERTA (sale al cierre, sin keepalive) → relanzador 09:31 armado (PID 6635). Aviso overnight vía monitor NQ/ES. Contradicción con números registrada: al momento de la orden la cinta estaba VERDE (NQ +0.31%, ES +0.72%, Samsung +4%, Hynix verde post-miss) → no entrar al inverso sin el print; SQQQ es el vehículo (TFSA no shortea, presupuesto ~$150)
- [ ] 2026-07-28 (Yunior): "make sure the posts are in english in the future and not spanish" — `delegado a agente` (background): solo el CUERPO de los posts a inglés en x_signal_poster/x_postmortem/x_earnings_post/xpost + x_draft() de daily_fleet_plans; voz/logs/email siguen en español; x_whale_bot.cpp ya postea en inglés. Verificar py_compile + tests x_* al volver.
- [ ] 2026-07-28 (Yunior): "todos los que puedas, usa UW" — (1) cinta ballenas UW flow-alerts en cockpit [delegado a agente], (2) cron volume_profile+kde_levels [en curso], (3) fix reparto cap tick-by-tick QQQ/SPY 0 bytes [en curso], (4) pintar KDE/VPVR como capa contexto en chart [pendiente, tras cinta], (5) hiro_pulse.cpp [pendiente, tras 3]. Suite pytest muere al 73% exit 1 — bisección [delegado a agente]
- [x] 2026-07-28 (Yunior): "debug notifications... spanish, simple, real. claude code start should speak spanish. finish all improvements" — hecho: (a) zombi BOLLINGER VIGIA cazado (118 banners fantasma post-cierre, portero RTH en keepalive, commit); (b) arranque Claude Code traducido (echo hook + voz session-start + indice skills + 'Falló el comando'); (c) voz del dia 0 frases en ingles, price_alarm 0 alertas viejas, korea_watch ya fail-loud; (d) capa liquidez en chart delegada a agente; (e) hiro_pulse SUPERADO por la cinta UW (tick opciones IBKR err 10189 = via muerta; UW flow-alerts ya da el flujo firmado)
