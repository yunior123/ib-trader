# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.
> Doctrina: skills `gamma-regime-walls`, `postmarket-cage-release`, `tradingview-terminal`.
> (`gexa-terminal` JUBILADA el 2026-07-25 — gexa.ai desapareció.)

> **AUDITADO EL 2026-07-25.** Las 73 casillas `- [ ]` que había se revisaron **una a una contra
> el código y contra `git log`**, no de memoria. El recuento y las 5 vivas más importantes están
> **al final del fichero**. Estado por casilla: `pendiente` / `hecho <commit>` / `obsoleto: <motivo>`.
> Cada afirmación va marcada **MEDIDO** (comprobado hoy con una orden) o **SOSPECHADO**.

## 🔴 SESIÓN 2026-07-25 (noche) — peticiones de Yunior, apuntadas AL VUELO
> Plan completo aprobado: `~/.claude/plans/create-plan-to-finish-glimmering-pascal.md`.
> Orden acordado: FASE 0 higiene → 1 señales → 2 flecha → 2.5 TradingAgents → 3 muros
> → 4 UI/UX → 4.5 X earnings → 5 los 9 bugs → 6 deploy → 7 seis ventanas + QA → 8 verif → 9 features minadas.

- [ ] 🔴 **"the chart should load data on demand when scrolling to pass, priority to live data
  please"** (Yunior 2026-07-26). pendiente — lazy-load de historia al hacer pan/scroll hacia
  atrás (estilo TradingView, `subscribeVisibleLogicalRangeChange`), pedir más barras al
  bridge solo cuando se acerca al borde izquierdo cargado; el backfill NUNCA bloquea ni
  retrasa el borde vivo (derecho) — la actualización en vivo manda siempre.

- [x] **"new finviz api till next saturday"** → token nuevo `0c56…8625` puesto en **feeds.env
      `FINVIZ_AUTH3`** (no solo en `llm.env`): MEDIDO que los 4 consumidores prueban `AUTH3`
      ANTES que `AUTH` (`finviz_scout.cpp:91`, `x_whale_bot.cpp:366`, `options_hunter.py:34`,
      y `finviz_valuation.py` **solo** lee AUTH3) → cambiar solo `FINVIZ_AUTH` no lo usaba nadie.
      El anterior seguía dando 200 al sustituirlo; queda comentado. Caduca ~2026-08-01.
- [x] **[CERRADA — era CONTENCIÓN DE RECURSOS, no un bug del chart]** `/health` del chart
  "no respondía con un cliente WebSocket". **Diagnóstico corregido el 2026-07-26 tras aislarlo**:
  un cliente WebSocket propio (Python) deja `/health` en **4-77 ms incluso sin drenar 20 s**, y
  8080 con Chrome conectado responde ahora en **2,7 ms**. El servidor está sano. Lo que había
  cuando "fallaba": **2 `clang++` a la vez** + 6 puentes + Chrome en un Mac de 8 GB, con el
  renderer de Chrome congelado (CDP dio timeout dos veces) y 121.958 pageouts. Era la máquina
  paginando, no el código. `history_frame` cuesta 32 ms y 1,94 MB — no bloquea nada.
  El `SEND_TIMEOUT_S=5` de `broadcast()` se queda (defensivo, correcto), pero **no era la cura**:
  0 descartes registrados en todos los logs. **Lección**: un solo `clang++` a la vez no es una
  recomendación, es la diferencia entre que el cockpit responda o no.

- [x] **[hecho e94cf04] "the filter did not work when changing symbols: no reactive to search and
  no data on symbol when selected after scrolling"** (Yunior 2026-07-26). DOS bugs reales,
  distintos, ambos MEDIDOS con websocket propio + Claude-in-Chrome contra los 6 puentes QA
  (`--mock --mock-dir /tmp/qa6`):
  (1) `wlsearch` (`live.html:1130` antes) solo escuchaba `keydown` Enter — CERO listener de
  `input` — tipear no hacía nada. Añadido filtro en vivo sobre Flota/Mías.
  (2) CARRERA en `cmd:"sym"` (`chart_bridge.py` stream handler): `get_state()` creaba el
  `State` nuevo con `bars=[]` y agendaba `_spawn_state` con `asyncio.ensure_future` (no
  esperado) mientras el handler mandaba `history_frame` en la siguiente línea — el frame
  salía con `bars=0` el 100% de las veces en el primer switch a un símbolo nuevo (medido:
  t0 bars=0, t0+1.5s bars=762). `_prime_bars()` nueva: carga la historia SÍNCRONA antes de
  devolver el `State`, sin carrera. Verificado en vivo (Claude-in-Chrome, ws_probe.py):
  GLD (con barras) 761 al instante; AAPL (fuera del sandbox de 6 símbolos) sigue en 0 pero
  ahora con `history_frame.nodata="sandbox sin barras para AAPL (...)"` y el chart pinta un
  banner en vez de quedar mudo — regla dura de "None o levanta, nunca silencio" respetada.
  Commit toca solo `scripts/chart_bridge.py` + `charts/live.html`. 6/6 tests
  `chart|mock|isolation` OK, selftest OK. Puentes QA reiniciados y dejados VIVOS
  (8080–8085). No probado en modo LIVE real (puerto 4001) — el fix del lado servidor es
  simétrico mock/live por inspección de código (`_prime_bars` cubre ambos), pero no se
  levantó un 7º puente contra TWS para no arriesgar el Mac de 8 GB.

- [x] **[hecho 36a2de8, mismo dia 496e8f9] Repuntar los 3 escritores del escritorio a
  `~/Desktop/ib-trader/hoy/`**. Los 3 apuntan a `IBT_DESKTOP_HOY` (env var, default
  `~/Desktop/ib-trader/hoy`, mkdir -p): `price_alarm.cpp`/`chart_bridge.py:_alarm_path`
  (496e8f9, commit de otro agente concurrente), `print_mon_plans.sh` + `daily_archive.py`
  (36a2de8). HALLAZGO no previsto: `daily_archive.py` (cron 16:10) fallaba con
  `Errno1 Operation not permitted` leyendo Desktop 5 dias seguidos (07-22 a 07-26),
  DESDE ANTES del repunto — su plist invocaba `venv/bin/python` DIRECTO sin wrapper zsh,
  y TCC solo concede FDA a `/bin/zsh` (medido con `launchctl submit`: zsh via launchd
  lee/escribe Desktop OK; python directo via launchd puede CREAR pero no LEER existentes).
  `print_mon_plans.sh` SI puede (corre via zsh) — no necesito el symlink-fuera-de-Desktop
  que Yunior anticipo para ese caso. Fix real: `scripts/daily_archive_run.sh` (wrapper zsh,
  mismo patron que `dailyplans_run.sh`) + plist recargado. `find_ranking_json()` prueba
  hoy/ -> raiz vieja -> archivo/ y GRITA CRITICAL si no aparece en ninguna (antes
  `warn=False` silencioso). Verificado con `launchctl start` real: sin FALLO/CRITICAL,
  `ranking.json` de hoy archivado por primera vez desde el 07-22. Tests:
  `tests/test_daily_archive_ranking.py` (5 casos). Suite completa 837 passed, 1 fallo
  preexistente ajeno (`test_voice_budget.py`).

- [ ] **[pendiente] "the chart should load data on demand when scrolling to pass, priority to
  live data please"** (Yunior 2026-07-26). El chart carga un payload fijo al conectar; al
  desplazarse hacia atras no pide mas historia. Hace falta paginacion bajo demanda
  (lightweight-charts `subscribeVisibleLogicalRangeChange` -> pedir el tramo anterior por WS y
  `setData` con el prefijo). **La prioridad es el DATO VIVO**: la carga de historia va en
  segundo plano y JAMAS bloquea el tick ni el frame de la barra en curso (retraso = dinero).

- [ ] **[pendiente] "make sure u already printed the plan, try to save ink, so no black
  background. review the task for the printer"** (Yunior 2026-07-26). El plan de apertura
  (`data/trees/plan-apertura.html`) y los 5 arboles (`cinco-arboles.html`) tienen FONDO OSCURO:
  imprimirlos gasta un cartucho. Hace falta `@media print` con fondo blanco, tinta negra y
  saltos de pagina por hoja. Revisar tambien el generador de PDFs diarios por si tiene el mismo
  problema.

- [ ] **[pendiente] "make sure tickers search work as expected. test with perpetuals plus
  korean tickers"** (Yunior 2026-07-26). El buscador se arreglo hoy (e94cf04: listener `input`
  + `_prime_bars` sincrono), pero NO se probo con: (a) los perpetuos 24/7 nuevos
  (`data/perp_stocks.json`, 26 simbolos Bybit), (b) los tickers coreanos (Samsung/SK Hynix/
  KOSPI, que van por `korea_bar_bridge`). Probar los dos casos.

- [ ] 🔴 **[pendiente — ORDEN VIEJA QUE SE PERDIO, nunca se anoto] Timeframes de SEGUNDOS en el
  chart, estilo TradingView** (Yunior 2026-07-26: *"why i still dont see timeframes for seconds?
  like 30 seconds, 15, 45, similar to trading view, i gave u an order long time ago about it"*).
  **MEDIDO hoy**: `charts/live.html:346-357` solo tiene 1m..1M; el mas pequeno es **1m**.
  `chart_bridge.LIVE_BAR:101` no tiene ninguna entrada sub-minuto, y `agg()` solo agrega HACIA
  ARRIBA desde 1m — de 1m no se puede bajar a 30s, hace falta pedir barras de segundos o
  construirlas del tick stream (que YA existe: `reqMktData`/`pendingTickersEvent`).
  IBKR sirve nativo `1/5/10/15/30 secs` por `reqHistoricalData` (con poca profundidad
  historica) y `reqRealTimeBars` solo da 5s. **45s NO es nativo**: sale de agregar 15s x3 o 5s x9.
  Fallo de proceso: la orden es vieja y JAMAS entro en TODOS.md.

- [x] **"make sure executable in desktop for software has icon too" + "ib trader software now
  has circle white on top of icon in desktop"** (Yunior 2026-07-26). **NO era el `.icns`**
  (10/10 tamaños, `CFBundleIconFile` correcto, sin alias al binario). Era **LaunchServices**:
  MEDIDO 4 registros del mismo `com.ibtrader.cockpit`, y el que resolvía era un FANTASMA en
  `/private/tmp/apptest/ib-trader Cockpit.app` — borrado, `Bundle node not found on disk:
  fnfErr`, `iconDict` VACÍO → Finder pintaba el **badge prohibitorio** (círculo blanco con
  barra). Purgado con `lsregister -u` + `-f -R -trusted` → icono correcto (captura antes/después).
  `build.sh` lo purga y re-registra en CADA build, así que sobrevive al rebuild.
  **2026-07-26 escritorio limpio:** la app vive en `~/Desktop/ib-trader/ib-trader Cockpit.app`;
  `build.sh` entrega ahí, borra la copia suelta de la raíz y purga también los registros de la
  Papelera — dos copias del mismo bundle id es lo que resucita el fantasma.

- [x] **"in macos i should be able to open the software and manually have as many windows as
  wanted right? how?"** (Yunior 2026-07-26). **CÓMO:** `open ~/Desktop/ib-trader/"ib-trader Cockpit.app"
  --args --windows 6` abre 6 ventanas en los puertos **8080..8085** (una por bridge = un
  símbolo cada una); a mano, **⌘N** = siguiente puerto libre y **⇧⌘N** = pregunta el puerto;
  **⌘D** reparte en rejilla. Puertos sueltos: `--ports 8080,8083,8085`. Un puerto = un símbolo
  porque `chart_bridge.py` tiene un solo `state.sym` por proceso.

- [x] **"make sure that pipeline has the bundle ready packaged in pipeline after commit,
  backend and frontend in same macos bundle so that its portable to any other mac…"** (Yunior
  2026-07-26). `.github/workflows/macapp.yml` (macos-15) genera el icono, construye el bundle y
  **falla** si aparece una ruta absoluta dentro; sube el `.zip`. Local: `zsh
  macapp/install_hooks.sh` instala `post-commit` (rebuild en background) + `pre-push` (entrega a
  Desktop). Arreglados los 6 shebangs de pip que llevaban la ruta del Mac de Yunior.
  **No hay firma Developer ID ni notarización en CI** (GitHub no tiene el certificado): sale con
  firma ad-hoc → en el Mac de destino, primer arranque con clic derecho > Abrir.

- [ ] **[pendiente] "print me qqq, nvda, smh, mu, aapl, msft trees and charts with upcoming week
  walls, gex, gamma flip, use the 15 min timeframe... planned strategy with updated data... for
  each graph u should predict at least the first 30 minutes or 15 of opening based on puts and
  calls and future accumulation, we repeat again tomorrow"** (Yunior 2026-07-26). **SE REPITE
  CADA DÍA.** 6 tickers, marco 15m, muros de la semana que viene, GEX, gamma-flip, estrategia
  planeada y predicción de los primeros 15-30 min de la apertura.

- [ ] **[pendiente] "make sure every new session reads those on start only once"** (Yunior
  2026-07-26): CLAUDE.md + TODOS.md al abrir sesión, UNA sola vez.

- [ ] **[pendiente] SKHY es el ÚNICO de la flota con el gate de spread APAGADO** (medido
  2026-07-26). Los otros 23 `*_signal_bot` llevan `export <SYM>_SPREAD_MAX` en su keepalive
  (0,3 casi todos, DRAM 0,5); `scripts/skhy_keepalive.sh` no define `SKHY_SPREAD_MAX`, y el
  default es `envd(...,0)` = **feature OFF**, así que en SKHY el gate no aplica AUNQUE el
  fail-closed esté puesto. Decidir el umbral (SKHY es ADR coreano, spread naturalmente más
  ancho — 0,5 como DRAM, o medirlo antes de fijarlo). Los otros 6 sin gate (cper kospi
  samsung skhynix slv uso) están FUERA de `fleet.txt`: no urge.

- [x] **[hecho 7b4de2b + 7b01bb5 — TradingFlow minado y las 6 ventanas probadas en Chrome]** **[pendiente] "chrome claude is connected now, u can use tradingflow, plus test all too"**
  (Yunior 2026-07-26). Chrome conectado por fin tras 5 intentos fallidos. Dos cosas:
  (a) minar TradingFlow con la cuenta de Yunior; (b) **probar TODO** en el navegador
  (chart vivo, muros, flecha, burbujas, panel GEX).

- [x] **[hecho 2026-07-26]** `scripts/finviz_auth_check.py`: GRITAR cuando el token caduque.
      Confirmado el bug, pero no donde parecía: el script YA tenía `say("DANGER"/"SIGNAL", ...)`
      bien escrito (líneas 191,219,223) — el problema era que su ÚNICO caller automático en
      producción, `fleet_healthcheck.py:refresh_finviz_health()` (cron 3x/día), le pasaba
      `--quiet` SIEMPRE, y ese flag es "para tests" según el propio docstring del script
      (línea 38). Resultado: la voz nunca sonaba en producción, solo quedaba el JSON +
      notificación/email del healthcheck. Arreglado quitando `--quiet` de esa llamada
      (`scripts/fleet_healthcheck.py:162`). Test de cableado (no de audio):
      `tests/test_finviz_auth_check.py::test_refresh_finviz_health_ya_NO_pasa_quiet`.
- [ ] **[pendiente] "make sure the walls are ok, no excuses, verify and try in depth… plus explore
      and call polygon and others"** (Yunior 2026-07-25). MEDIDO hoy contra DOS referees
      independientes que coinciden entre sí (CBOE CDN y Polygon sin filtrar): **los muros NO están
      bien**. Dos defectos, los dos del patrón prohibido de `~/CLAUDE.md`:
      **(1) `T = 0.02` inventado** — `gex_snapshot.py:114-116` no escribe `T`, `gex_core.py:188,207,
      409,813` caen al default; `_T_of()` existe (`:496`) pero solo lo llama `from_ibkr_cache`
      (`:688`) y `gex_snapshot.py:134` invoca `build_gex` directo → **el flip se reprecia con 7,3
      días para TODOS los vencimientos, 0DTE incluido**, y de ese flip sale `pin`/`trampilla`, que
      es VETO DURO (`compass.cpp:630-634`, `book_quality.py:317-326`). Hoy 15 trampilla / 10 pin.
      **(2) cadena truncada** — `poly_chain_archive.py:46-47` `BAND=0.045 DTE_MAX=10`: QQQ archiva
      854 contratos vs **12.430** reales; net GEX **−481 M** vs **−6,03 B**; call_wall **700** vs
      **730**; NVDA 56 contratos / 7 strikes → **sin mapa gamma**. Prueba del delito: **14 de 25
      flips caen entre 3,7% y 4,6% del spot con la banda a 4,5%** — es el borde de nuestro recorte,
      no un nivel de mercado.
      → **(1) hecho `cf0baaf`** (T real por contrato). **(2) hecho `5a6a34e`**: banda ADAPTATIVA por
      gamma marginal (suelo 10% / techo 60%, calibración en `data/gamma_band.json`) + vencimientos
      hasta el mensual. **35/35 con flip MEDIDO, el más justo a 12,5 pp del borde**; QQQ −5,22 B
      $/1% (referees −5,3/−6,0). Medido antes de fijar parámetros con las 35 cadenas COMPLETAS de
      CBOE. Ojo a los tres hallazgos que cambian el diagnóstico: la mitad del "13×" era **escala**
      (`net_gex` ×spot vs `net_gex_dollar1pct` ×spot²/100), **Polygon no da griegas de índice**
      (SPX 8.512 contratos, 0 con gamma → CBOE), y la **cuota de 5 req/60s ya no existe** (219
      seguidas sin un 429). Detalle en `AGENTS.md` § *EL ARCHIVO DE CADENAS*.
- [x] **[hecho 425afe3 — duplicado, ya cerrado; verificado de nuevo 2026-07-26]** los CONSUMIDORES
      VIVOS siguen recortando a ±3,5%. Esta casilla quedó huérfana: el fix real está en
      `gex_core.from_ibkr_cache` (`scripts/gex_core.py:826`, default `band=None` desde 425afe3), no
      en los 4 call-sites — `chart_levels.py:161,166` y `gex_gate.py:44,53` NUNCA pasan `band`, así
      que heredan `None` → header. Reverificado en vivo hoy con
      `data/history/2026-07-26/poly_chain_qqq_1620.txt` (header `band 0.1800`): `band=None` →
      **138 strikes, flip 696,20, band_used 0.18**; forzando el viejo `band=0.035` → 48 strikes,
      flip 698,02 (el número truncado). `chart_levels.gen('qqq')` end-to-end da `band_used 0.18`;
      `gex_gate.gate('qqq','BUY')` → APTO sin tocar el default. Nada que arreglar en este lote.
- [x] **[hecho 7b01bb5 — 6 ventanas 8080-8085 con muros reales vía --mock-dir del sandbox de replay]** **[pendiente] "run ib-gateway simulation engine… show 6 ib-trader window like before, working
      with different tickers, while the graph is moving, while we also see the walls. full qa
      testing on those windows, test everysingle feature in there"** (Yunior 2026-07-25).
      Va DESPUÉS de arreglar los muros: `replay.cpp:314-364` copia/sintetiza los `levels_<sym>.json`,
      así que con muros truncados las 6 ventanas enseñarían la misma basura.
- [ ] **[pendiente — parcial, revisado 2026-07-26]** "priority now goes to signals… test all
      signals with data, full backtesting, arrow is super important too" (Yunior 2026-07-25).
      Estado por pieza:
      **(1) direction_view.py — CERRADO hoy** (ver casilla ~389): `prob = 50 + |score|*40` ya no
      canta; patrón `compass.cpp` copiado, `prob` Optional solo con bucket calibrado propio.
      **(2) compass.cpp — SIGUE ABIERTO, fuera de mi zona (solo lectura)**: `gather()` no puebla
      `calib_lo`/`calib_n` de ningún fichero, solo los recibe por `--ev-stdin` (modo TEST). En
      vivo `prob_of()` cae SIEMPRE a `"doctrina"` — la brújula tampoco está calibrada en
      producción hoy. Haría falta un harness que corra compass en modo backtest (`--ev-stdin`
      en bucle contra barras históricas) para construir la población del ESTADO `S_REV` (nivel
      impreso + ≥2 familias + sin vetos) y calibrarla — no existe.
      **(3) "test all signals with data" — 6/7 fuentes YA corridas** vía `null_control.py` (ver
      `data/null_control.json`): bollinger UNPROVEN (n=1154, n_eff=89), cusum DATA-INSUFFICIENT
      (n_eff=20, y además apagado en `signal_enable.json` por el regen separado de 501
      sesiones), dip/flow/structural DATA-INSUFFICIENT (n_eff 3-14.5), whale DATA-INSUFFICIENT
      (n_eff=18.7). **0/6 con `fdr_cells_passed>0`.** La 7ª fuente, `source='signal'`
      (2085 filas, la MÁS GRANDE de `trades.db`), es **estructuralmente no-etiquetable**:
      `barrier_labels.py:833` — es un relé heterogéneo sin tesis derivable
      (`eod_backtest.thesis()` no la clasifica), no un olvido.
      **(4) "full backtesting" del propio `backtest_harness.py`** ya está hecho (ver los 4
      CRITICAL más abajo, `85bec77`): 0/93 celdas APTA con coste real.
- [x] **[hecho — ENTRADA del framework] "calibramos la flecha con trading agents framework… pásale
      todo el arsenal, y que tenga acceso a finviz technicals"** (Yunior 2026-07-25).
      Commits: ib-trader `a6090ad` + `e61832e`, TradingAgents `575664b` + `577bef6`.
      (a) **NIM fuera**: `default_config.py:69-71` = `deepseek`/`deepseek-chat`. Guarda
      `test_default_provider_is_never_nim` (`tests/test_env_overrides.py:31`) — **verificada por
      mutación**: al reponer `nvidia`/`kimi` el test FALLA; restaurado, 17 passed.
      (b) **Puente vivo**: `scripts/ta_llm_bridge.py` mapea `TA_*`→`TRADINGAGENTS_*` antes del
      import (`screener/research.py:63-68`). Test end-to-end en `tests/test_ta_llm_bridge.py:49`
      corre `ta_venv` (py3.12) con el entorno limpio y comprueba el DEFAULT_CONFIG REAL:
      `backend_url=https://api.deepseek.com/v1`, `deep/quick=deepseek-chat`.
      (c) **Finviz `v=171` → HTTP 200** (2098 filas con `cap_midover`; token `FINVIZ_AUTH3`
      de `feeds.env`, caduca 2026-08-01). Dos bugs cazados y arreglados: el `.env` de
      TradingAgents inyecta un `FINVIZ_API_KEY` CADUCO que ganaba por `os.environ` (**401**) →
      el token se pasa ahora explícito; y `cap_midover` **excluye ETFs** → QQQ/SPY/GLD/XLK/SMH/EWY
      se quedaban sin técnicos → filtro vacío (acciones+ETFs) → cobertura **0 → 30/30** de `fleet.txt`.
      (d) **Arsenal servido**: `tradingagents/dataflows/ibtrader.py` (solo lectura, cada sección
      con `_source`). Cobertura medida sobre los 30: gex / expected_move / pin / truth_lock /
      wall_decay / finviz_technicals **30/30**, flow_hist 25/30, breadth_component 11/30,
      breadth 2/30, book_quality 1/30. **`data/uw_premium_flow_hist.jsonl` NO EXISTE** — el
      historial real de flujo por ticker es `data/whale_flow_hist.jsonl` (opt_whale_watch).
- [ ] **[pendiente — SALIDA del framework, lo que de verdad calibra la flecha]** lo commiteado es
      la ENTRADA (contexto→LLM). Falta el lazo de medición: veredicto **discreto** + razones (jamás
      un número del LLM), registrado en `signals` con `run_id` como cualquier otra fuente, medido con
      `barrier_labels` + `null_control` + BH-FDR, **banner sin voz** hasta tener `n_eff`. Solo si
      sobrevive entra en la flecha como coeficiente que **DESPLAZA** a otro factor (topes duros
      `FAMILIES_MAX=6`/`VETOES_MAX=8`, `scripts/compass.cpp:565-569`; 14 factores en `direction_view`).
      Patrón a copiar: `source_verdict` de `compass.cpp` — publica un veredicto medido como CONTEXTO
      sin convertirlo en probabilidad. Recordatorio: `data/calibration_barrier.json` mide la señal
      CRUDA (n=1154, pool de bollinger), **no** el setup de la brújula → no vale como prob de la flecha.
- [x] **[cerrado — duplicación documentada, no consolidada]** dos implementaciones de técnicos
      Finviz `v=171`. Verificado viable el import cruzado (`ib-trader` py3.9 stdlib puro,
      `TradingAgents` py3.12: `sys.path.insert(...); import finviz_technicals` funciona sin
      error bajo `venv/bin/python` de TradingAgents). NO se fusionó: los contratos ya
      COMMITEADOS y testeados de cada lado son incompatibles sin reescritura mayor —
      `ib-trader/scripts/finviz_technicals.py` devuelve dict NORMALIZADO (niveles calculados,
      cache disco por símbolo en `ib-trader/data/`, fallback yfinance, excepción
      `TechnicalsUnavailable`); `TradingAgents/tradingagents/dataflows/finviz.py` devuelve la
      fila CSV cruda (para el prompt del LLM), cache en memoria por filtro, excepciones
      `NoMarketDataError`/`VendorNotConfiguredError`/`requests.HTTPError` compartidas con el
      resto de vendors del paquete. `tests/test_ibtrader.py` (10+ tests, ya trackeado) mockea
      esos tipos y formas exactas — cambiar la fuente rompe esos tests y acopla escritura de
      un proceso LLM batch al `data/` de un repo señal-solamente en vivo. Deuda menor real,
      documentada con motivo medido; no cuando toque, sino a propósito.
- [x] **[hecho]** `TradingAgents/tests/test_finviz.py` (5 fallos) arreglado y trackeado.
      3 `_SAMPLE_ROWS`/`DictWriter`: añadido `"Sector"` a `fieldnames` en los 3 mocks CSV.
      2 categorías: `broad_data`→`core_stock_apis`, `financial_metrics`→`fundamental_data`
      (nombres reales en `interface.py:TOOLS_CATEGORIES`). Arreglo expuso un TERCER bug
      oculto tras el de categoría: los tests de routing mockeaban `finviz.get_finviz_stock_data`
      pero `interface.VENDOR_METHODS` guarda la referencia de función al importar — el mock no
      llegaba nunca y con la categoría ya correcta el test golpeaba la RED de verdad (401 real).
      Arreglado con `mock.patch.dict(interface.VENDOR_METHODS[...], {"finviz": mock_get})`.
      `./venv/bin/python -m pytest tests/test_finviz.py -q` → 11 passed (antes 5 failed/6 passed).
      Suite completa TradingAgents: 463 passed (antes ~450), 3 failed preexistentes ajenos
      (`test_ollama_base_url.py`, `test_temperature_config.py` x2 — no tocados, no relacionados
      con finviz).
- [x] **[hecho] "create script to post x.com post of companies with earnings next week,
      include technicals… use finviz… show people nice picaros data"** (Yunior 2026-07-25).
      VERIFICADO hoy con el token nuevo: `f=earningsdate_nextweek` → **753 tickers**; `v=171` da
      Beta/ATR/SMA20-50-200/52W/RSI(14)/Gap; `v=152&c=…` trae **`Earnings Date` con hora**
      (8:30 AM = BMO, 4:30 PM = AMC).
      ENTREGADO: `scripts/x_earnings_post.py` — **rejilla PNG** (5 columnas lun-vie × ☀️antes de
      abrir / 🌙tras el cierre, tiles de 3 en fila, `+N` de resto, flota con borde verde) + franja
      de escaleras 🔴🎯📍🟢🛑 con niveles medidos (precio±ATR, SMA20/50/200 a ≤2 ATR) + **1 línea**
      de tweet con **1 cashtag**. `--dry-run` es el default; publica solo con `--post`.
      Tests: `tests/test_x_earnings_post.py` (34). Media por `x_post_common.upload_media` (v1.1).
      · Cruce contra la referencia @StockOptionCole: **cuadran los 7** (mar28 STX · mié29 MSFT META
      QCOM LRCX · jue30 AAPL AMZN) y el 8º, **SKHY, Finviz lo pone mar 28 AMC**. Ojo: el ADR llega
      **sin RSI ni Beta** → sale en la rejilla pero **sin escalera** (nunca un 0 relleno).
      🔴 **Hallazgo que vale más que el tweet**: **8 de los 30 de la flota reportan la semana que
      viene — AAPL AMZN LRCX META MSFT QCOM SKHY STX**, y **los 8 son AMC** (mar 28: SKHY STX ·
      mié 29: MSFT META QCOM LRCX · jue 30: AAPL AMZN). La regla 4 prohíbe aguantar prima comprada
      a través de un print → esto va a los PDFs y a los vetos, no solo a X.
- [ ] **[pendiente — deriva del anterior] meter los 8 de earnings en los PDFs diarios y en el veto
      de prima comprada** (no tocado a propósito: el generador de PDFs es de otro agente).
      (a) `daily_fleet_plans.py`: marcar en el plan de AAPL AMZN LRCX META MSFT QCOM SKHY STX la
      fecha+sesión de earnings (fuente `data/finviz_earn_nextweek_152.csv`, ya la deja
      `x_earnings_post.py`); (b) **veto duro**: prima comprada que cruce el print del propio ticker
      = prohibida (doctrina "en día de earnings del ticker jamás aguantar el print con premium
      comprado"); (c) todos AMC ⇒ el veto muerde en el **cierre** del día del print, no en la
      apertura; (d) la fecha se re-verifica el mismo día: Finviz mueve fechas.
- [x] **[cerrado — re-auditado 2026-07-26] "terminar todo de trendspider, menthorq… make it nice,
      surprise me"** (Yunior 2026-07-25). La nota anterior ("8 sin fichero") estaba OBSOLETA:
      #26 gap-islands (`ab43fba`), #29 peer-weights hardening (`ebae728`, 0/19 pares sobreviven
      el null) y #21 wall-decay ya estaban construidos. Quedan **5 sin fichero, las 5 BLOQUEADAS
      por dato, no por código** (`docs/WAVE2-3-VIABILITY-2026-07-25.md`, re-verificado HOY):
      - **#19 cube-widening**: exige TWS vivo + flota corriendo. `./fleet_hours --why` →
        **DEAD**, faltan 3h35m para la ventana (dom 20:00 Toronto); 0 procesos TWS/bridge vivos.
      - **#22 chain-delta engine**: pide pares de snapshot cada 5 min en tabla `gex_cube` —
        **no existe** (`sqlite_master`); lo archivado hoy son 7 timestamps sueltos
        (`0845 0944 0946 0947 0957 1001 1620`), no una cadencia de 5 min.
      - **#24 close-drift**: pide cadena a las **13:30** en ≥120 sym-sesiones. Cero: los
        horarios archivados en TODA la historia son `0408 0845 0944 0947 0957 1001 1018 1620`.
      - **#25 expiry-unwind**: pide `chain_full_snap` sin tope de DTE + ~50 expiries. Hay
        **2 fechas** (25 y 26-jul), ambas con `dte_max=10`.
      - **#30 finviz-snap**: pide historia de short-float archivada. **0 ficheros**
        (`find data -iname "*short_float*"` vacío) — falta credencial Elite + job nocturno,
        luego ~40 días.
      Del lado `designs-trendspider.md` (13 candidatos): #2/#3/#4/#6/#7 ya viven en el master
      de 30; #8 sobrevive solo como KDE (`kde_levels.py`); **#1 gex-drift, #9 avwap-anchors,
      #10 ratio-tape, #11 expansion-clock, #13 fleet-rank MUERTOS con refutación numérica**
      (skill `anti-overfit-killlist`, items 16/9/10/14/13) — no se reabren.
      **#5 tape-absorb sigue DIFERIDA**: necesita 20 sesiones de `trades.db equity_prints`;
      la tabla **no existe** (`equity_prints_archiver.py` está escrito pero no ha corrido con
      la flota viva) → 0/20. Ninguna de las 6 publica `null`/`0`/`{}` disfrazado de medición.
- [ ] 🥇 **[pendiente — RELOJ DE 7 DÍAS] Unusual Whales** (Yunior 2026-07-25: "save, lets see how
      to use that one"). Token en `feeds.env` `UW_TOKEN`, **trial caduca ~2026-08-01**.
      MEDIDO hoy, los 6 endpoints responden 200 y traen **justo lo que la skill
      `anti-overfit-killlist` daba por IMPOSIBLE** ("necesitan tape firmado + dark-pool
      licenciado que NO tenemos"):
      · `/api/market/market-tide` → `net_call_premium`, `net_put_premium`, **`net_volume` FIRMADO**
        en cubos de 5 min (81 filas/día). Es EXACTAMENTE el panel "Net Call/Put Premium" de la
        captura de Bullflow, y el que habría hecho sonar **el tide de −53 M del 7/21** que el P/C
        de volumen (0,86) se comió.
      · `/api/stock/<SYM>/greek-exposure` → **250 filas = 1 AÑO** de call/put gamma·delta·charm·vanna
        diarios. Rompe el cuello de botella del roadmap: teníamos "whale/flow/structural NO
        regenerables, esperar 40-60 sesiones" y esto es historia YA.
      · `/api/stock/<SYM>/spot-exposures` → gamma/vanna/charm por 1% de movimiento **intradía**
        (491 filas) con precio: el equivalente a HIRO. *(Ojo: los campos `_dir` y `_vol` vinieron a
        0 en la muestra; solo `_oi` poblado — verificar si es de tier superior o solo en RTH.)*
      · `/api/market/oi-change` (100) · `/api/stock/<SYM>/flow-alerts` (100, los sweeps de la
        captura) · `/api/darkpool/<SYM>` (500).
      **REGLA DURA antes de cablear nada**: es de PAGO y con reloj. Una fuente que se apaga en 7
      días NO puede ser dependencia de una señal — es la lección de gexa.ai, que murió y se llevó
      8 consumidores. *Acción correcta en los 7 días*: **ARCHIVAR** todo lo histórico que da
      (1 año de greek-exposure × 30 símbolos, market-tide, darkpool) para quedarnos el DATO
      aunque no se renueve, y **medirlo** contra nuestro `gex_snapshot` antes de pagar.
      MCP disponible en `https://api.unusualwhales.com/api/mcp`.
- [ ] **[pendiente] CONECTAR Unusual Whales esta semana** (Yunior 2026-07-26: "esta semana podemos
      conectar unusual whales, si es bueno extendemos trial"). Plan: **archivar primero, medir
      después, cablear al final** — nunca al revés, por la lección gexa.
      Endpoints medidos que dan mapa de DELTA, que NOSOTROS NO TENEMOS:
      `/api/stock/<SYM>/greek-exposure/strike` → **530 filas POR STRIKE** con `call_delta`,
      `put_delta`, `call_gex`, `put_gex`, `call_charm`, `put_charm`, `call_vanna`, `put_vanna`.
      `/api/stock/<SYM>/greek-exposure` → **250 días (1 año)** de agregados diarios; net DEX de
      QQQ el 24-jul = **−51,0 M**. `/api/stock/<SYM>/greeks` → 237 filas por contrato.
      `/api/stock/<SYM>/option-chains` → 12.904 contratos.
      *Por qué importa*: `scripts/gex_core.py` tiene **CERO delta** (ni `bs_delta`, ni DEX). El DEX
      está diseñado dos veces y nunca construido (`designs-menthorq.md:219` #9 close-drift,
      `designs-spotgamma.md:182` expiry-unwind: *"DEX… currently missing from our stack"*), y son
      dos de las 8 minadas sin fichero. **Trampa de signo ya documentada**
      (`designs-menthorq.md:224`): DEX positivo = cliente alcista **pero** el creador VENDE
      subyacente para quedar neutral → dos campos, `dex_sentiment` y `dex_flow_impact`, jamás uno.
- [ ] **[pendiente] Minar 4 vendedores más** como se hizo con TrendSpider/MenthorQ/SpotGamma
      (Yunior 2026-07-25): tradytics.com/options-market · app.tradingflow.com/app/option-trades/live
      · optioncharts.io/trending/most-active-stock-options · quantedoptions.com.
      **TradingFlow — MEDIDO 2026-07-26: NO TIENE API.** Un solo plan, **$59/mes** (o $504/año);
      la página de precios no menciona API, acceso programático ni descarga CSV/JSON, y el
      **roadmap tampoco** (sus planes son Option Chain, watchlist, filtros, Surge Attribution,
      resúmenes con IA). Es UI-only → para nosotros solo sirve como **fuente de IDEAS a minar**,
      no como feed. Tiene página propia de `/learn/delta-exposure-dex/`, que confirma que el DEX
      es estándar en el sector y un hueco nuestro. La extensión de Chrome no estaba conectada, así
      que esto se midió por HTTP, no navegando: **queda pendiente mirar la UI en vivo** para minar
      las features como se hizo con TrendSpider.
      Destino: `docs/research/designs-<vendor>.md` con features rankeadas y las RECHAZADAS
      razonadas, mismo formato que `designs-trendspider.md`.
      **Marco doctrinal que Yunior fija**: *"los market makers son los elefantes en la habitación"*
      + resumen del vídeo de Brent Kochuba (SpotGamma). Lo aprovechable y que NO tenemos:
      **HIRO** (línea en vivo de si el MM debe comprar o vender), **Trace Map** (mapa de calor que
      PRONOSTICA la respuesta de cobertura: azul/morado = soporte con compradores debajo, rojo =
      zona de alta volatilidad donde el precio se persigue), **strikes en percentil 99 como
      objetivos de liquidez** ("quieren que el precio vaya a las zonas de liquidez", y el flujo se
      APAGA al llegar), **Captain Condor** (posición 0DTE recurrente que fabrica soporte/resistencia),
      y el **mapa de charm** de la tarde. El Vol Trigger ya lo tenemos (`vol_trigger.py`).
- [x] 🔴 **[cerrado — re-auditado 2026-07-26] BB multi-TF: el código CONTRADICE la doctrina
      escrita** (respuesta a "with BB, are we making sure it breaks in 1 min and 15 min? to avoid
      noise?", Yunior 2026-07-25). El diagnóstico (`qqq_signal_bot.cpp:458-459/466`, 2-de-3 con
      5m derivado de 1m via `V5TF`, 148 `BB-2TF` vs 4 `BB-3TF`) ya estaba bien. La MEDICIÓN pedida
      (barrier_labels + null_control) **ya se hizo y ya se commiteó** (`e2c59f0`, hoy 01:20,
      `scripts/bollinger_complements.py::analizar_tf15` + `data/backtest/bcomp_tf15.json`), solo
      faltaba cerrar la casilla y alinear los skills/docs — hecho ahora.
      **Resultado, 30 tickers × 30 días, P(toca la media BB20-1m en 30min)**:
      67.2% solo 1m roto (n=4031) > 49.4% BB-2TF 1m+5m (n=409) > 43.0% BB-3TF 1m+5m+15m (n=200).
      **Monótona a la BAJA**: exigir el 15m no confirma, recorta el 92% de la muestra y empeora.
      Contraste 15m-roto-vs-no p=0.36 (n_eff~40) y 3TF-vs-2TF p=0.58 → **UNPROVEN, ninguno
      significativo**. *No se cambia* — exigir `1m AND 15m` sería peor, no mejor. Re-verificado
      hoy contra el JSON en disco (números idénticos, reproducible). Docs alineados: SKILL
      `bollinger-mastery` §6 y `engines/README.md`. Nada tocado en `qqq_signal_bot.cpp` ni en los
      demás `*_signal_bot.cpp` (otro agente los tiene abiertos).
- [x] **[hecho 8586347 — ruta /technicals + 4º widget del dock, procedencia y edad visibles]**  ~~ "technicals de la company en tiempo
      real desde finviz en un widget nuevo; solo el gráfico principal por defecto, los demás
      widgets bajo demanda; yfinance de fallback si finviz se cae"** (Yunior 2026-07-25). Va con
      la FASE 4 de UI/UX. **Capa de datos lista y probada**: `scripts/finviz_technicals.py` —
      `get_technicals(sym, ttl_s=60, data_dir=...)`: Finviz Elite `v=171` (Beta/ATR14/SMA20-50-200
      /52W-hi-lo/RSI14/Gap/ChangeFromOpen/Price/Volume, niveles absolutos derivados de las
      distancias % que da Finviz) → cae a yfinance si Finviz falla (403/red/CSV roto, se loguea
      y sigue) → si los dos fallan sirve el cache viejo marcado `stale:true` → si no hay NADA
      levanta `TechnicalsUnavailable` (nunca fabrica 0/None). Cache por símbolo
      `data/finviz_tech_<sym>.json`, TTL 60s, escritura atómica, `src`+`feed_ts` en el dato y
      `feed_age_s` recalculado en cada lectura (nunca congelado). 15 tests en
      `tests/test_finviz_technicals.py`, todos verdes, sin red (monkeypatch).
      **Falta cablear (NO tocado — de `charts/live.html` y `scripts/chart_bridge.py` se encarga
      otro agente ahora)**: (1) un endpoint/ruta en `chart_bridge.py` que llame
      `finviz_technicals.get_technicals(sym_activo)` SOLO para el símbolo del gráfico principal
      por defecto (nunca la flota entera en loop); (2) los demás widgets (si los hay) piden bajo
      demanda al abrirse, mismo `get_technicals`; (3) pintar en `live.html` los campos con su
      `src`/`feed_age_s` visibles (Finviz no es tiempo real — regla 4) y el flag `stale` si aplica.

## 🔴 SESIÓN 2026-07-25 (madrugada) — peticiones de Yunior, apuntadas AL VUELO
> Regla (`~/CLAUDE.md`): cada petición se anota aquí EN EL MOMENTO, con las palabras de
> Yunior, antes de seguir trabajando. Sin esto se pierden — pasó con las 30 features minadas.

**HECHO y commiteado:**
- [x] "remove biomcp from context, alpha fold too" → los 5 MCP fuera de `~/.claude/settings.json`
      (+ pubchem, uniprot, elevenlabs, y desinstalados del disco). Backup con la ELEVENLABS_API_KEY
      en `~/.claude/settings.json.bak-2026-07-25-mcp` (única copia).
- [x] "la flecha debería ser como una brújula … ultraprecisa" → `scripts/compass.cpp` (C++23,
      37 tests). Escenario SPY Muro put 740 + puts: ▲UP 76% en vez de ▼DOWN 61%. `aa7b91a`
- [x] "puede revertir fuerte o solo un poco: calcúlalo y mueve la flecha" → amplitud
      LATIGAZO/REBOTE/SCALP + `mag` que escala la flecha. `aa7b91a`
- [x] "la flecha también se mueve si choca un call wall en rebote" → el nivel se elige por
      TOQUE, no por procedencia (en el rebote r6 sigue negativo). `aa7b91a`
- [x] "muro debería ser con mayúscula" → "Muro" en texto de usuario; claves de calibración
      (`SPIKE_PUTS|muro`) intactas para no partir el histórico. `aa7b91a`
- [x] "python solo para test, la computación en C++" → brújula entera en C++; `compass.py`
      retirado a `backup/`. Regla grabada en `~/CLAUDE.md`. `aa7b91a`
- [x] "imagina si la flecha apunta con retraso de 2 segundos" → ~2.1s → **~0.45s**. El chart
      ya no calcula, solo lee (0.051 ms). `b1d1b0a`
- [x] "manda scout … donde python es peligro" → auditoría; 2 bugs críticos arreglados:
      Espada de Napoleón en crash-loop (`89c71f7`) y MANADA con denominador fabricado
      (21/26=80.8% disparaba cuando 21/30=70% no debía) (`531feb7`).
- [x] "en los etfs … las acciones que los llevan abajo o arriba con fuerza" → motores nombrados
      en `compass.cpp` + `data/etf_weights.json` (los pesos hardcodeados estaban MAL: MSFT 8.0
      en QQQ cuando el real es 4.34). `9d9568b`
- [x] "asegura un solo branch main updated" → una sola rama, todo pusheado.
- [x] "cada versión nueva compilada a app macOS en Desktop" + "verifica los cambios del otro
      Claude Code" → `~/Desktop/ib-trader Cockpit.app` 159 MB, firma válida, abre. Auditoría:
      señal-solamente intacta, cero secretos. `e78c903`
- [x] "polygon da opciones data, graba en claude.md" + "trae las griegas directo" → medido:
      `/v3/snapshot/options/` da greeks+IV+OI, pero **`?as_of=` es TRAMPA** (dice OK e ignora
      la fecha). Grabado en `~/CLAUDE.md`.
- [x] **"el app ib-trader Cockpit should have a nice icon"** (Yunior 2026-07-25) — `hecho 5c2b0c3`.
      MEDIDO: `macapp/icon/AppIcon.icns` con los 10 tamaños (16→512@2x) generados por
      `macapp/icon/make_icon.py` vía `iconutil`; `CFBundleIconFile` en `macapp/build.sh:35` y en
      el bundle vivo; `build.sh:53-57` lo empotra en cada build y GRITA 🔴 si falta.

**PEDIDO A MITAD DE SESIÓN (2026-07-25 09:55, apuntado al vuelo):**
- [x] **"solve this HIRO NOT_AUTHORIZED)"** → RESUELTO EN DIAGNÓSTICO, pendiente de ejecución con TWS
      vivo. Medido con la key real (sábado, mercado cerrado): el 403 **NO es de opciones** —
      `/v3/trades/AAPL` y `/v3/quotes/AAPL` (acciones) y `/v3/snapshot/indices` dan el MISMO
      `NOT_AUTHORIZED`. El plan no tiene carril de CINTA, ni acciones ni opciones. Arreglarlo con
      Polygon = **gasto duplicado** ($199/mo Options Advanced) porque **ya pagamos IBKR por los
      mismos prints de OPRA**. La vía real está PROBADA en nuestra propia cuenta:
      `ibkr_bar_bridge.py:250` ya corre `reqTickByTickData(..., "AllLast", ...)` con firmado
      Lee-Ready. HIRO = el mismo motor apuntado a contratos de OPCIÓN, ponderado por delta.
      Spec completa: **`docs/HIRO-2026-07-25.md`**. Skill `dealer-flow-limits` §6 actualizada.
- [ ] **[pendiente] Verificar EN VIVO que los DOS CAPITANES ya reciben cinta firmada.**
      *Qué es*: el fix de prioridad ya está en el código — `scripts/ibkr_bar_bridge.py:62`
      `CAPTAINS_FIRST = ["QQQ","SPY","SMH"]` + `captains_first(syms)` en `:65-71` (`hecho c6e1513`).
      Lo que NO está verificado es el efecto: MEDIDO hoy, `data/whale_qqq.txt` y `whale_spy.txt`
      siguen a **0 bytes** y **9 de los 14** ficheros están vacíos (aapl amd asml gld intc qqq spy
      tsm txn); los 5 con datos son del **24-jul**, nada escrito hoy. Es coherente con la flota
      parada un sábado, así que el fix no está refutado — está **sin observar**.
      *Por qué importa*: la **regla 12 entera** (los capitanes SPY/QQQ/SMH prevalecen sobre la
      tropa) se alimenta de esa cinta. Si tras una sesión viva siguen a 0 bytes, la jerarquía de
      capitanes lleva semanas decidiendo con un input vacío.
      *Cuándo*: primera sesión viva (dom 20:00 / lun premarket). Un `ls -la data/whale_*.txt` basta.
- [ ] **[pendiente]** Correr `docs/probes/hiro_probe_ibkr.py` en la próxima sesión viva (dom 20:00 /
      lun premarket): mide el cap REAL de tick-by-tick y si OPRA por contrato está permitido.
      *Por qué importa*: sin ese número el resto de HIRO es especulación, y ya sabemos que el cap
      (err 10190) es lo que dejó a los capitanes sin cinta. `a2cd4d8`

**DELEGADO a agentes — CERRADO (verificado 2026-07-25):**
- [x] "make the walls look like in there … those look like nice gamma walls" (captura de
      @BullflowIO, `GEX: Bubbles`) → burbujas GEX en `charts/live.html`, coloreando **pin vs
      trampilla** (que Bullflow no muestra). MEDIDO: `charts/live.html:610` `bubbleRows()`,
      `:629` `class BubbleView`, `:677-686` `class WallBubbles`, toggle `#bubblebar` en `:291`
      con tooltip PIN vs TRAMPILLA y persistencia en `localStorage`.
- [x] "engine ibkr reemplazo local … con polygon, datos reales" → `scripts/replay.cpp` (simula el
      DISCO, no el socket) + cadenas del archivo. El gateway socket se **canceló** por decisión de
      Yunior ("si no hace falta websocket fake y es listo, mejor"). `e7438e3` `b1ee715`
- [x] Backfill Polygon 2 años + archivador diario de cadenas con griegas REALES.
      MEDIDO hoy: `poly_bars` = **8.950.177 filas, 30 símbolos, 2024-07-25 → 2026-07-24**
      (eran 21 días). Archivador con cron: `70c0e2c` + `~/Library/LaunchAgents/com.ibtrader.polychains.plist`
      (16:20 y 08:45); **30 cadenas** `data/history/2026-07-25/chain_full_*.json` MEDIDAS hoy.
- [x] Las **30 features minadas** de SpotGamma/TrendSpider/MenthorQ + **13 skills** +
      `docs/FEATURES-MINED-2026-07-25.md` + `docs/research/` (10 dossiers). `7dadf7a`
      `100d3a1` `145766c` `4f9d64d` `71b14cb` `ec6815e` `86d0c4c`
- [x] **[hecho d16c0b4/309c4c6, mapa; reverificado 2026-07-26]** "do we have spx in fleet? …
      make sure we use it to measure brújula". Lo que SÍ estaba en mi alcance: SPX (+XSP/NDX/DIA/
      IWM) **tienen mapa gamma completo hoy**, no solo cadena. Reverificado en vivo:
      `data/gex_snapshot.json` publica los 5 con `regime`/`flip` (SPX 7484,68 NEG, XSP 760,97 NEG,
      NDX 28767,66 NEG, DIA 517,27 POS, IWM 303,55 NEG — 36 claves incl. `_meta`); `chart_levels.gen`
      corre para los 5 (`data/history/2026-07-26/chain_full_spx.json` etc. presentes,
      `poly_chain_archive` los archiva a diario). SPX sigue **fuera de `data/fleet.txt`** (30,
      sin cambios) — correcto, es la decisión escrita en `docs/UNIVERSOS.md` (sin BARRAS 1m no
      vota). Lo que queda genuinamente pendiente y NO se puede cerrar sin sesión de mercado viva:
      (a) probar BARRAS de SPX por TWS con la suscripción CBOE Global Indexes que Yunior ya tiene
      (decide fleet.txt vs solo-mapa); (b) el consumo de este mapa por la brújula es
      `scripts/compass.cpp`/`direction_view.py`, **fuera de mi alcance en este lote** (otro agente
      los tiene ahora) — la data ya está lista para cuando los toquen.

**OLA 1 — CERRADA (2026-07-25). 15 items en 4 agentes:**
- [x] #1 `barrier-labels` **hecho 1a97611** + #2 `null-control` **hecho c1e3336**. Los dos únicos
      cuya salida es RESTAR. `scripts/barrier_labels.py`, `scripts/null_control.py`,
      `docs/EDGE-SCOREBOARD-2026-07-25.md`, `docs/NULL-CONTROL-2026-07-25.md`.
      Medido: 13-27% de las señales que se cuentan GANADAS habrían sido STOPEADAS antes; el
      re-etiquetado NO es una resta uniforme (bollinger +6.5pp, cusum -28.6pp) porque la barrera
      SÍ ve el TP intra-camino. ρ̄ de la flota = **0.41** → bollinger `n=1154` queda en
      `n_eff=89` (CI estrechados ×3.6) y sale **UNPROVEN**: no bate a entradas ALEATORIAS
      emparejadas (0.482 vs 0.496). **0 de 131 celdas fuente×sym×bucket pasan BH-FDR q=0.10.**
      Propuesta en `data/signal_enable.PROPUESTO.json` — `signal_enable.json` NO tocado.
- [x] #3 `book-quality` + #5 `chain-honesty` + #6 `flip-honesty`+congelar 09:35 + #13 roll-off
      → `hecho 56ed1fe b066f81 1cacc8f`. Detalle en la sección "OLA 1 features minadas".
- [x] #9 `truth-lock` + #10 `em-envelope` + #12 `voice-budget` + #14 `pin-clock` +
      #15 `equity-prints` + #16 `chain-cube` + #18 `levels-5min` → `hecho ea26bc5 176caea daf90de
      d21f2eb b0c1b8a 6bae616 c91c375`. 7 commits, 101 tests.
- [x] #4 `poly-aggs-backfill` (2 años × 30 syms; eran 21 días) — **hecho**. MEDIDO: 8.950.177
      filas de `poly_bars`, 30 símbolos, 2 años exactos.
- [x] #11 `features-fanout` + **tope duro de 14 factores** — `hecho 785b29e` ("TOPE DURO de
      familias y vetos en la brujula"). Sin esto, 30 features = una flecha cuya varianza de prob
      colapsa a ~58% constante.
- [x] **[hecho 2026-07-26 — agente signals]** 🥇 CABLEAR lo que ya se mide: nadie consume la
      calibración de barrera. `scripts/direction_view.py` no leía `barrier`/`null_control`/
      `calibration` (0 hits medido); `prob = int(round(50 + abs(score)*40))` cantaba un
      plausible. **NO se cableó `calibration_barrier.json` a la flecha** (n=1154 = el pool
      CRUDO de bollinger de `null_control.json`, población distinta de "nuestro setup" — misma
      falacia que el código ya rechaza con `prob_retroceso_50`). Se copió el patrón EXACTO de
      `scripts/compass.cpp` `source_verdict()`/`prob_of()`, ya aplicado antes en
      `order_engine/prob_profit.py._measured_prob()`: la vieja media ponderada pasa a llamarse
      `doctrine_score` (CONTEXTO, nunca prob); `prob` es `Optional[int]`, solo se llena con
      bucket `"direction_view|<regimen>"` en `data/calibration.json` (trust + n>=20) →
      `prob_source` "medido"/"sin_medir"/"doctrina" (flat); nuevo `calib_context` lee el
      veredicto CRUDO de `null_control.json` para la familia activa con más peso
      (magnet→structural, captain_flow→whale, bollinger→bollinger, confirmado 1:1 contra
      `trades.db` `signals.source`) y se publica como texto, jamás como número. Hoy no existe
      ningún bucket `direction_view|*` en `calibration.json` → `prob` sale `null` siempre
      (honesto). 7 tests nuevos `tests/test_direction_view_calib.py`. `chart_bridge.py` no se
      tocó (ya lee `compass_<sym>.json` del binario C++, no llama a `direction_view.compute()`
      desde 2026-07-25); `order_engine/prob_profit.py` (off-limits) usa `r.get("score")` para
      la decisión y `r.get("prob")` solo en un string cosmético — con `prob=None` imprimirá
      "None%" ahí, cosmético, fuera de mi zona, no toqué order_engine/.
      *(b)* `poly_bars` acaba el **2026-07-24 19:59 ET**: 197 señales del 07-25 quedaron sin
      etiquetar (`skip_entry_stale`). *(c)* el null de **16 niveles aleatorios** (parte B de la
      ficha #2) ya NO está bloqueado: `level_react` existe (`53b3f3c`). *(d)* la ruta sub-minuto no
      existe → `ambig_pct` 2.1% es irreducible con `poly_bars`. Estas 3 (b/c/d) siguen pendientes,
      no eran mi zona hoy.

**PENDIENTE (no delegado aún):**
- [ ] **[pendiente — LO DECIDE YUNIOR]** Conmutar los keepalives a los binarios C++ nuevos
      (`fleet_consensus`, `gate`). *Estado MEDIDO*: los dos C++ existen y compilan
      (`scripts/fleet_consensus.cpp` 30 KB, `scripts/gate.cpp` 19 KB + `gate_core.hpp`, `e7438e3`),
      pero **el keepalive NO los lanza**: `scripts/fleet_keepalive_start.sh:39` solo hace
      `pkill -x fleet_consensus`; en producción corre `scripts/fleet_consensus.py --daemon`.
      `gate` SÍ está cableado por otra vía: `scripts/optgate.py:62` ejecuta `./gate --json`.
      **Modo SOMBRA: NO existe hoy** — 0 hits de `shadow`/`SOMBRA` en los tres ficheros.
      *Recomendación*: sombra primero (el C++ escribe a fichero aparte y NO habla, se compara una
      sesión contra el Python, y solo entonces se conmuta la voz). Hoy hay que **construir** ese
      modo; no se puede activar tal cual.
- [ ] **[pendiente] Orden de Yunior 2026-07-25**: "después de ola uno testea todo, then todas las
      olas. Testea con Claude in Chrome as needed." → OLA 1 cerrada y suite verde; falta la
      verificación **en Chrome** del chart (burbujas GEX, flecha escalando, tooltip). Olas 2 y 3:
      viabilidad ya medida en `0a9be1f` (5 construibles, 7 bloqueadas).

> ⚠️ **LECCIÓN DE PROCESO (2026-07-26, error del lead)**: con agentes trabajando EN PARALELO,
> **jamás `git add -A`**. Mi commit `75a3442` (una skill) arrastró dentro
> `scripts/calibration_ledger.py` y `tests/test_calibration_ledger.py` de otro agente, que estaban
> a medias en el árbol. No se perdió código, pero el mensaje del commit no describe lo que lleva —
> y la trazabilidad ES el producto cuando se audita un fichero de dinero. Corolario de la regla
> "repartir por FICHERO": el reparto también aplica al `git add`. Usar rutas explícitas.

## 🔴 PEDIDO 2026-07-26 (tarde) — apuntado al vuelo
- [x] "arregla esas 4 lineas tambien" → hecho MEJOR que las 4: el default estaba en
      `gex_core.from_ibkr_cache(band=0.035)`. Ahora `band=None` → lee la banda de la CABECERA
      del fichero (`parse_chain_header` ya la traía). QQQ pasa de **48 a 184 strikes** y
      `chart_levels` publica `band_used: 0.18`. Una línea en el sitio correcto en vez de cuatro
      repetidas en dos ficheros.
- [x] "usa init para que cada session de claude code reads claude.md" → creado `CLAUDE.md` en el
      repo (el harness lo lee solo al abrir sesión aquí). CONCISO por la regla de no gastar
      tokens: punteros a `AGENTS.md`/`docs/`, más las 6 reglas que más rompen cosas.
- [x] **[hecho 7b01bb5 — chart_qa_windows.sh (launchd, supervisión por ventana); cazó 3 bugs: flip extrapolado 58c7b50, panel GEX con spot del mapa b2e1106, régimen con spot del mapa fc53ca0]** **[pendiente] QA de las 6 ventanas** sobre `replay` (tarea que sigue).
- [ ] **[pendiente] Capturar más datos de TradingFlow y Unusual Whales por Chrome/Safari**
      (Yunior: "use trading flow in chrome para capturar mas datos, y otros como unusualwhales").
      Vía que SÍ funciona: **Safari + osascript** (la extensión de Chrome no conecta). Ya probada
      hoy: `osascript -e 'tell application "Safari" to do JavaScript ...'` con la sesión de Yunior.
- [x] **[hecho 5a0d0f3 — data/trees/*.json + cinco-arboles.html; supervivencia por RANGO del strike (el cociente de OI compara vencimientos ya expirados)]** **[pendiente] LOS 5 ÁRBOLES** (Yunior 2026-07-26, después de terminar todo el testing):
      *"imprime tree, solo tree para estos tickers: spy, qqq, aapl, smh, nvda, based on walls that
      still remain from last week, plus the ones for this starting week till friday, search the
      calls, puts expiring upcoming friday, create graph, chart, based on that too. 5 sheets total,
      one per ticker."*
      Es decir, por ticker: (a) muros que **sobreviven** de la semana pasada, (b) muros de la
      semana que empieza hasta el viernes, (c) calls y puts que **expiran el viernes próximo**
      (2026-07-31), (d) gráfico. **5 hojas, una por ticker.**
      *Ya tenemos con qué*: `daily_fleet_plans.py` hace árboles de escenarios en PDF; las cadenas
      archivadas con banda ancha traen 12 vencimientos hasta el 2026-08-21; y el histórico de
      muros por sesión está en `data/history/<fecha>/`.
      *Ojo*: los muros de "la semana pasada" hay que leerlos de las cadenas archivadas de esos
      días, que tenían banda ±4,5% — comparar con los nuevos de banda ancha mezcla dos ventanas
      distintas y hay que declararlo.

## 🔴 PEDIDO 2026-07-26 (noche) — perps de acciones tokenizadas, apuntado al vuelo
- [x] **hecho (agente, sin commit propio — fichero nuevo sin tocar nada de otros)** "we should be
      able to see DRAM and some others like MU in perpetuals right? like INTCUSDT, DRAMUSDT,
      MUUSDT" — SOLO LECTURA, cero órdenes abiertas en ningún exchange.
      **Existen y con volumen real**: Bybit cubre **26/30** de `fleet.txt` (falta AMD, NOK, GLD;
      STX se EXCLUYE — colisiona con el token cripto Stacks, $0.146 vs cierre real IBKR STX
      $853.25 el mismo día). Bitunix también lista 26/30 pero su libro de fin de semana está casi
      muerto (MU $4,257 en 48h sáb+dom); Bybit tiene turnover real de fin de semana (MU
      ~$150-300k/hora sostenido, ~$13M en 48h, OI $14.9M) — MEXC y Gate.io también listan
      MU/INTC/DRAM con volumen decente (Gate: MU $9.8M/24h) pero Bybit es el más completo.
      Kraken y Hyperliquid (universo principal) **no tienen estos perps**. Ostium sin verificar
      (endpoint público no respondió, baja prioridad — es RWA de forex/commodities, no mega-cap).
      **Adelanta o solo copia**: SÍ hay señal de adelanto medible, con el mismo rigor que
      `peer_influence.py` (null de 2000 barajados, no solo correlación cruda) — pero es
      estructuralmente distinto de un "peer": es el MISMO activo en otro venue mientras USA está
      cerrado, no una predicción entre tickers independientes. Movimiento del perp entre el
      cierre real del viernes y el domingo 22:00 UTC vs el gap real del lunes (Bybit, n por
      ticker limitado a semanas desde el listado): **MU corr=0.94 p=0.009 firma 8/8 (100%)**;
      **INTC corr=0.83 p=0.003 firma 8/10 (80%)**; **DRAM corr=0.97 p=0.002 firma 6/6 (100%)**.
      Los tres SOBREVIVEN el null (a diferencia de los 0/19 pares de `peer_influence.py`).
      DRAM con n=6 es fino — no publicar como probabilidad calibrada sin más semanas
      (`measured-probability`: mínimo de muestra).
      **Fetcher tonto creado**: `scripts/perp_stock_fetch.py` (Bybit REST público, sin API key,
      urllib+User-Agent, cero cómputo de señal, escritura atómica, excepciones nunca devuelven
      0 — se saltan y gritan a stderr). `python3 scripts/perp_stock_fetch.py` → 
      `data/perp_stocks.json` (26 símbolos: px/mark/index, bid/ask/spread%, vol24h_usd, oi_usd,
      funding_rate, src/feed_ts/feed_age_s). Probado en vivo: AMD y NOK avisan por stderr y se
      saltan (no están en Bybit), el resto 26/26 OK.
      **Para cablear (NO hecho, pendiente decisión de Yunior)**: esto es un dato nuevo, no un
      gatillo — si se quiere meter en la flecha/compass como coeficiente domingo-noche, entra
      por `direction-view-architecture` (coeficiente multiplicativo con tope, nunca fija el
      signo) y solo para MU/INTC/DRAM (los únicos medidos; el resto de los 26 no se ha
      validado el lead-lag, solo que el precio existe). Cron sugerido: una vez el domingo
      ~20:00-22:00 Toronto, no continuo (fin de semana real está prácticamente muerto salvo
      esa ventana).
- [ ] **nota del agente**: mensaje suelto llegado a media tarea — *"¿Los repunto a
      ~/Desktop/ib-trader/hoy/? :si. 2. delegate the work now the timeframe, right to todos
      first."* — NO ejecutado: (a) `~/Desktop` está prohibido por TCC/launchd (regla dura de
      `~/CLAUDE.md`, la misma que ya rompió los 11 jobs bajo `~/Documents`); (b) parece referirse
      al pedido de timeframes de segundos del chart (`charts/live.html`), que es de OTRO agente
      activo ahora mismo y fuera del alcance de este hilo (perps). Yunior: confirmar a quién iba
      dirigido antes de que alguien cree esa carpeta.

## 🆕 ÍNDICES A LA FLOTA + VERIFICACIÓN CRUZADA CON TRADINGFLOW (2026-07-26)
> Yunior: *"SPX/SPXW/XSP… feel free to add them to fleet"* + captura suya de la tabla de índices
> de TradingFlow (sesión 24-jul) con DIA/NDX/IWM/SPY/QQQ → *"put them on later todo"*.

### 🔬 La captura de Yunior como TERCER REFEREE — y lo que revela
Sus columnas son `sym | spot | netGEX | régimen | put_support | gamma_magnet | call_resistance`:
`DIA 519 −0,1B` · `NDX 28.111 −2,5B` · `IWM 291 −3,0B` · `SPY 739 −5,1B` · `QQQ 685 −5,6B`, **los
cinco NEGATIVOS** (coincide con nuestro 19/25 en NEG y con su propio recap "Dealers Stay Short Gamma").

| net GEX | TradingFlow | CBOE (mío) | Polygon (mío) | **NUESTRO** |
|---|---:|---:|---:|---:|
| QQQ | −5,60 B | −6,03 B | −5,34 B | **−0,48 B** |
| SPY | −5,10 B | −11,79 B | −10,95 B | **−0,65 B** |

- **QQQ: los tres referees coinciden** (−5,3 a −6,0 B) y **nosotros estamos 13× por debajo**.
- **SPY: TradingFlow discrepa de CBOE/Polygon por ~2,3×** — dos vendedores serios pueden no
  coincidir, así que un solo referee externo nunca basta. Nosotros, 18× por debajo de CBOE.
- **Confirma que el defecto 2 (banda ±4,5%) es real y grande.** No es teoría: es 13-18×.
- Sus niveles de QQQ (684/685/685) están **pegados al spot** = son 0DTE puro; los nuestros
  (680/695/700) abarcan más. Comparar sin igualar el scope de vencimientos es comparar otra cosa.

### Símbolos — lo MEDIDO antes de tocar `data/fleet.txt`
- **`SPXW` NO es un símbolo aparte**: la cadena `_SPX` de CBOE trae 28.784 contratos = **9.626 raíz
  `SPX`** (mensuales AM-settled) **+ 19.158 raíz `SPXW`** (weeklies PM-settled). Mismo subyacente,
  mismo spot. Añadirlo por separado = contar el índice dos veces.
- **`XSP` = SPX/10 EXACTO** (741,20 vs 7.411,98). Mismo subyacente a un décimo.
- 🔑 **Y aquí está el motivo REAL para tener XSP**, que no es el que se supuso: contrato ATM del
  vencimiento vivo 27-jul → **SPX call $4.280 / put $1.710 (NO caben en $200)**; **XSP call $396 /
  put $187 → el put SÍ cabe**. **XSP es el único vehículo de índice operable con el presupuesto
  de la casa.** SPX sirve para el MAPA; XSP para OPERAR.
- **NDX** es al QQQ lo que SPX al SPY (índice vs ETF). Su propio recap prueba que **divergen**:
  *"a still-positive SPX and a newly short SPY"* (22-jul) y *"QQQ flips short gamma while SPX and
  SPY stayed long"* (15-jul). **No son redundantes.**
- **DIA** (Dow) e **IWM** (Russell 2000) sí son subyacentes NUEVOS — amplitud de mercado que hoy
  no miramos.

- [x] **[hecho d16c0b4/309c4c6 — plan (a) revisado por `docs/UNIVERSOS.md`, más cauto que el
      propuesto aquí; reverificado 2026-07-26]** Añadir índices, con DOS LISTAS separadas.
      **Lo que quedó, y por qué NO es lo que dice (a) arriba**: `data/fleet.txt` (30, denominador
      de MANADA) **sin tocar** — ni SPX ni NDX/IWM/DIA entraron todavía, porque ninguno tiene bot/
      keepalive/`book_quality` de una semana medido, no solo por XSP/SPXW duplicando voto (eso
      también es cierto). `data/universe_gamma.txt` (35 = fleet + **SPX XSP NDX DIA IWM**) SÍ está
      hecho — verificado con `wc -w` y `universe.gamma_universe()`. Wiring confirmado end-to-end
      hoy: `gex_snapshot.json` publica los 5 con regime/flip, `chart_levels.gen()` corre para los 5,
      **`book_quality.run(['SPX','XSP','NDX','DIA','IWM'])` calcula labels reales** (SPX STABLE_PIN
      coef 0.35 212 strikes 93% griegas, XSP STABLE_PIN 109 strikes, NDX STABLE_PIN 267 strikes,
      DIA NEAR_FLIP 76 strikes, IWM STABLE_PIN 61 strikes) — el gate de "book_quality medido" antes
      de promover a `fleet.txt` YA FUNCIONA, solo falta que pase el calendario (una semana de
      datos, no código). `tests/test_fleet_consensus.py::test_universo_mapa_no_se_cuela_en_el_
      denominador_de_manada` + `test_gex_snapshot.py::test_universo_es_independiente_de_fleet_txt`
      siguen verdes — MANADA intacta en 30.

## 🆕 MINADO DE TRADINGFLOW (2026-07-26) — dossier `docs/research/designs-tradingflow.md`
> Yunior: *"i really like this one too… take a look in chrome, it offers a lot of data, do they
> have api?"*. **Respuesta medida: NO tienen API** (`/api/*`, `/openapi.json`, `/docs` → 404 o
> shell del SPA; backend tras Clerk; un plan de **$59/mes**; el roadmap tampoco la menciona).
> → Es **fuente de IDEAS, no de DATOS**: jamás puede ser dependencia de una señal.
> ⚠️ La UI en vivo **NO se ha visto** (la extensión de Chrome no conecta) — todo esto sale de sus
> docs públicos `/learn/*`. **Falta la pasada visual** para minar la pantalla como se hizo con
> TrendSpider, y para capturar datos suyos con los que verificar los nuestros.

- [x] 🥇 **[HECHO 2026-07-26] DEX de ESTRUCTURA** (`Δ · OI · 100 · S`) en `gex_core`.
      `bs_delta` + `_delta_of` + `build_dex` + `check_dex_signs` (levanta si se publica un solo
      campo de signo) + `dex_by_exp` (la cuota de delta que pedía `expiry-unwind`). Publicado en
      `gex_snapshot.json` y en `from_ibkr_cache` (también en degradado: el DEX no necesita gamma).
      Convención OI-larga, la de UW. Referee UW por PATA: corr +0.52…+0.93 en 5 símbolos; el NETO
      no es comparable (`chain_full` es `dte_max=10`, UW es el libro entero — en MU el neto hasta
      cambia de signo). Tests: `tests/test_dex.py` (12).
- [ ] 🥈 **[nice-to-have] La distinción DEX-de-FLUJO vs DEX-de-ESTRUCTURA**, que no tenemos ni
      nombrada. Suyo, textual: *"DEX describe la DIRECCIÓN DEL FLUJO en la cinta (intradía);
      GEX representa la ESTRUCTURA del mercado"*. Su fórmula de flujo es `delta × size` **por
      operación** (tamaño de la operación, no OI) → requiere cinta de opciones firmada, que es
      justo lo que da UW `/market-tide`.
- [ ] 🥉 **[nice-to-have] DEI — normalizar el impacto por la liquidez del nombre**.
      *Suyo*: *"DEX escalado por el volumen típico de la acción: ¿es esta exposición GRANDE para
      este nombre?"*. *Por qué importa*: hoy nuestros umbrales de ballena son ABSOLUTOS, y por eso
      NOK (precio 8,99) y MU (910) no se pueden rankear juntos. `impact_pctile` ya existe como
      campo en `book_quality.json` y está **`null` en 30/30**.
- [ ] **[nice-to-have] Escalera de agresor de 5 peldaños** (Above Ask / At Ask / **Mid** / At Bid /
      Below Bid) en `opt_whale_watch`. *Por qué importa*: hoy clasificamos con un solo ratio
      (`pc = vp/max(vc,1)`, `:157`) que fuerza cada operación a un bando; **"Mid" debería ser su
      propia categoría, no repartirse**. El motor ya existe: `ibkr_bar_bridge.py:250` corre
      `reqTickByTickData(..., "AllLast", ...)` con firmado Lee-Ready → es el HIRO casero de
      `docs/HIRO-2026-07-25.md`.
- [ ] **[nice-to-have, BARATO] ΔOI = detector de APERTURA vs CIERRE.** Regla suya:
      `volumen ≈ +ΔOI` → posición NUEVA; `volumen ≈ −ΔOI` → **salida**; `volumen >> ΔOI` → churn.
      *Por qué importa*: confirma al día siguiente si la ballena de ayer ABRÍA o CERRABA — y eso es
      el punto de Kochuba (*un movimiento brusco suele ser un cambio de posición, no una noticia*).
      Ya archivamos cadenas a diario desde el 2026-07-25, así que el coste es casi cero.
      ⚠️ **Y corrige una lectura equivocada nuestra**: *"el OI NO es en tiempo real; durante la
      sesión el OI que ves es el cierre de AYER"*.
- [ ] **[nice-to-have] "Inusual" como CONJUNCIÓN, no como umbral suelto**: premium grande + Vol/OI
      alto + lado agresivo + sentimiento claro (no mid) + strike OTM, **todos a la vez**. Más su
      lectura de tamaño: pocas operaciones grandes = convicción institucional; muchas diminutas =
      retail o creador, menos señal. *Por qué importa*: una conjunción es mucho más difícil de
      sobreajustar que un umbral único, y el umbral único es justo por lo que **el tide de −53 M
      del 7/21 no sonó**.
- [x] **[hecho 7b4de2b — docs/research/tradingflow-flujo-agresor.md: escalera de agresor de 5 peldaños + 17 sesiones de régimen + cruce con UW]** **[pendiente] Pasada VISUAL a TradingFlow con la cuenta de Yunior** (Chrome): minar la
      pantalla (no solo los docs) y **capturar datos suyos para verificar los nuestros** —
      su GEX/muros/flip contra `data/gex_snapshot.json`, igual que se hizo con CBOE y Polygon.
      *Bloqueado por*: la extensión de Claude no conecta con Chrome (instalada en 4 perfiles,
      Chrome vivo) → **hace falta reiniciar Chrome**.

> **Lo que NO hay que copiarles** (razonado en el dossier): sus Call/Put Wall son **solo por OI**
> ("el strike con más OI de calls por encima del precio") — el nuestro es por **|gamma|·OI** y
> además publica los de OI puro aparte. Y su GEX/flip **no disclosan fórmula**
> (*"implementation details remain proprietary"*); el nuestro sí, con bisección de 40 iteraciones
> y tests. Su ventaja no es el cálculo: es la UI y la cinta de opciones que ellos tienen.

## ✅ HECHO (2026-07-20/21)
- [x] Post-mortem imanes 2026-07-20 (hacia el imán, jamás a través del muro; decay por toques)
- [x] Investigación NOK (crash = Ericsson AI-cost read-through; 40% layoff = sin evidencia; earnings 23-jul BMO)
- [x] SPY añadido a la flota (bot C++ + keepalive)
- [x] Impresora: Brother NO era tuya (removida); HP 9120e bloqueada por tinta color (firmware HP+); PNGs a Desktop
- [x] Árboles de escenarios NOK/NVDA/QQQ/SPY + estrategias con opciones a Desktop
- [x] Estudio gexa.ai → régimen gamma; skills `gexa-terminal` + `gamma-regime-walls`
- [x] 26 skills por ticker + `korea-memoria` con patrones 6m + forma intradía 60d (`skill_patterns_refresh.py`)
- [x] Sistema diario: launchd `dailyplans` (04:00/08:30/09:12) + `postmortem` (16:20)
- [x] Generador 26 tickers (IBKR-first, VX CBOE, Finviz, Korea, futuros, griegas, árbol, forma)
- [x] Calibración empírica por setup×régimen (Wilson, no por ticker) — `calibration_ledger.py`
- [x] Patrones medidos (H&S/dobles/triángulos, follow-through empírico) — `pattern_detect.py`
- [x] Engranaje QQQ/SPY (amplitud ponderada de componentes) — `index_breadth.py`
- [x] Posters X: premarket/realtime/postmortem, ledger 10/día $4/mes, humor, "No consejo fin."
- [x] Draft X compacto+visual (escalera emojis 🔴🎯📍🟢🛑) + Corea semis + tendencia overnight
- [x] `force_meter.py` — fuerza/agotamiento en vivo (4 fases → acción de stop)
- [x] `posthours_cage.py` — picardía jaula 0DTE→liberación after-hours (ballenas semanales)
- [x] Healthcheck 3x/día auto-curador (`fleet_healthcheck.py`, launchd)
- [x] Flota canónica única `data/fleet.txt` (30) — nadie queda atrás
- [x] Alarmas flujo put/call alineadas a los tickers; DB limpia; cadena notificación verificada
- [x] X auth verificado (@YuniorR62327146, 200 OK, read-only, sin gastar post)
- [x] TradingView: zoom inspección + zoom chart verificados; skill documentada

## 🔄 EN CURSO / PENDIENTE
- [x] Magnets gexa dominados: find→scroll_to ref→read_page; parser gexa_parse los captura
- [x] X posts scheduled cada día verificado (4AM premarket + realtime daemon + 16:20 postmortem)
- [x] Auto-mejora semanal (domingo 19:00): refresca patrones/formas 6m + recalibra + corre tests + reporta
- [x] Conocimiento consolidado en LEARNED.md + skills + memoria; herramientas reutilizables xpost.py + gexa_parse.py
- [x] **Europa para ASML**: momentum Ámsterdam (ASML.AS ~6h lead) + STOXX50 al plan+draft (prob bump, línea 🇪🇺)
- [x] Tests C++23: correctness pass + benchmark (la cifra vieja "9.46 ns/op" era humo — ver `bench.cpp` abajo)
- [x] ~~Verificar gexa headless conecta REALMENTE en el run de 4am~~ **MUERTO 2026-07-25**: gexa.ai
      desaparecio ("gexa is gone now, we are on our own"). Mapa gamma calculado EN CASA:
      `scripts/gex_snapshot.py` -> `data/gex_snapshot.json` (griegas MEDIDAS de Polygon; MEDIDO
      hoy: **25 símbolos + `_meta`**, vs los 16 que se scrapeaban). Consumidores recableados
      `631f40b` `611841b` `8b6e2df` `cbfaa49` `f626e54` `aea3124` `c868877` `95e29b7`.
      Skill `gexa-terminal` y `scripts/gexa_parse.py` marcados JUBILADOS (`5e1c1cc`).
- [x] ~~Raíz del `com.ibtrader.fleet` exit=78 (EX_CONFIG)~~ — **hecho: lo mató la mudanza del repo.**
      MEDIDO hoy: `launchctl print gui/$UID/com.ibtrader.fleet` → **`last exit code = 0`**.
      MEDIDO: **0 de los 17** plists `com.ibtrader.*` apuntan ya a `~/Documents`; 16 apuntan a
      `/Users/yuniorrodriguezosorio/ib-trader` y el 17º (`polychains`) usa `$HOME/ib-trader`.
      La causa era TCC sobre `~/Documents` bajo launchd, documentada en `~/CLAUDE.md`.
      ⚠️ Los ficheros `*_autostart.err` del repo conservan el error VIEJO: son historia, no estado
      — leerlos como estado actual es lo que hace creer que el bug sigue vivo.
      *(Fusiona la casilla duplicada "launchd exit 78 (fleet/scan/screener/fastscan/rescan/screener6am)"
      del 2026-07-21. Del grupo queda un residuo distinto y menor, abajo: `com.ibtrader.scan`.)*
- [x] ~~Residuo del grupo exit-78: `com.ibtrader.scan` apunta a un binario `scan_server` que no
      existe~~ — **obsoleto: el job ya está desinstalado.** MEDIDO hoy:
      `~/Library/LaunchAgents/com.ibtrader.scan.plist` **no existe** y `launchctl print` responde
      *"Could not find service com.ibtrader.scan"*. Yo mismo abrí esta casilla al auditar,
      fiándome de un informe del 24-jul; al comprobarlo con `launchctl` resultó falsa. Queda
      escrito como recordatorio de que **un informe de agente no es evidencia hasta que se mide**.
- [ ] **[pendiente]** Primera cacería REAL de jaula-liberación (lunes al cierre, cuando el
      after-hours vive). *Qué es*: `scripts/posthours_cage.py` + `tests/test_posthours_cage.py`
      existen y pasan; falta EJECUTARLO una vez con mercado real. *Por qué importa*: es la única
      picardía del repo que aún no se ha visto disparar en vivo — hasta entonces es teoría.
- [x] ~~Documentar force/cage/healthcheck/breadth en `docs/DAILY-SYSTEM.md`~~ — **hecho `7875b32`**.
      Eran **0 menciones** de las cuatro en el manual, con las cuatro en producción. Nueva §11 con
      qué hace cada una, cómo correrla a mano, y el bug histórico que explica por qué vigilarla
      (el exit 1 del healthcheck que se auditaba a sí mismo en bucle; el `index_breadth` que caía
      en silencio a yfinance). Dos estados honestos escritos como tales: `force_meter` vive FUERA
      de los bots C++ y `posthours_cage` nunca se ha visto disparar en vivo.

## 💡 IDEAS / FUTURO (cuando se pidan)
- [x] Tweets con imagen adjunta (árbol PNG en x_media/) + gamma (flip/dealer/POC) en posts intradía
- [ ] **[pendiente]** `opt_tick_watch` event-driven para el strike ACTIVO (tiempo real, no poll
      5min). *Por qué importa*: filo de EJECUCIÓN — hoy el strike que estamos operando se relee
      cada 5 min; en 0DTE eso es una eternidad. *Fichero*: no existe (`scripts/opt_tick_watch*` = 0 hits).
- [ ] **[pendiente]** Fuerza/agotamiento por-tick plegada en los signal bots C++ (si se quiere el
      filo en la decisión). *Estado*: `force_meter.py` existe pero vive fuera del bot; MEDIDO:
      `qqq_signal_bot.cpp` tiene 0 refs a fuerza/agotamiento. *Por qué importa*: la regla 9 exige
      que la fuerza sea parte del veredicto SIEMPRE, y hoy el bot decide sin ella.
- [ ] **[pendiente]** Calendario macro (CPI/FOMC/NFP) al PDF — "no operar el print". MEDIDO:
      `scripts/daily_fleet_plans.py` = 0 hits de CPI/FOMC/NFP. *Por qué importa*: entrar con
      premium comprado justo antes de un print macro es la pérdida más evitable que existe.
- [x] ~~Revisar plan Polygon (POLYGON_KEY en feeds.env, quizá opciones/agregados mejores)~~
      **obsoleto: contestado el 2026-07-25 con la key real y grabado en `~/CLAUDE.md`.** El
      snapshot `/v3/snapshot/options/` SÍ da griegas+IV+OI en vivo; `?as_of=` es una TRAMPA (dice
      OK e ignora la fecha); los aggs por contrato no traen OI ni griegas; la cinta (`/v3/trades`)
      da 403. La decisión ya está tomada: archivar snapshots a diario en vez de pagar más.

## 📌 REGLAS QUE NO SE ROMPEN
- Señal-solamente (jamás ordena; única excepción autorizada: `order_engine/` con doble llave).
  Aditivo + degradación limpia. Respaldo en `backup/` antes de tocar el generador.
- Presupuesto opciones = cualquier contrato de la flota con premium ≤ $200 (ENMIENDA 2026-07-22).
- `notify_relay.sh` DEBE estar vivo (fue el fallo de notifs). Print o nada. 3 pérdidas = fin.
- Ningún `except` en camino de señal devuelve `0`, `0.0`, `0.5`, `50` ni `{}` — `None` o levanta.

## 2026-07-21 sesión viva
- [x] ~~opt_whale_watch: filtrar strikes sin security definition (QQQ 712.5 20260724 spamea Error
      200 en loop) — cachear contratos inválidos y saltarlos~~ — **hecho `020d814`**. MEDIDO:
      `scripts/opt_whale_watch.py:88-89` (`qcache` + `badk`), filtro en `:109`
      (`k not in badk[s]`), blacklist SOLO con respuesta definitiva en `:121-128` (si `qualify`
      devolvió 0 de todo se considera fallo transitorio y NO se veta — si no, un fallo de la farm
      dejaba un ticker ciego toda la sesión), tope de 12 strikes ATM en `:114`, y autocura en
      `:166` (`badk.clear()` tras 2 scans en cero).
- [x] ~~7/22 8:30: confirmar fichas CLSK/INTC vs gaps overnight~~ — **obsoleto: la fecha pasó hace
      3 días.** `data/fichas_2026-07-22.txt` queda como histórico.
- [x] ~~x_post_common: sanitizar a MAX 1 cashtag por post (X rechaza 403 con 2+; el $4.7B tambien
      cuenta como cashtag si va pegado a letras — revisar regex)~~ — **hecho `39bd147`**. La regex
      vieja solo veía `$LETRAS` y arrastraba un `... if False else ...` muerto, así que el caso
      que Yunior cazó (`$4.7B`) no lo tocaba. Ahora cuenta como cashtag cualquier `$` seguido de un
      token con al menos una letra; `$200` (solo dígitos) se deja intacto porque X no lo cuenta;
      los importes pierden el `$` y ganan ` USD` para no perder el significado. `count_cashtags()`
      expuesto y **14 tests** con posts reales de la flota.
- [x] ~~opt_whale_watch v2: alarma por PREMIUM NETO en dolares ademas del ratio de volumen~~ —
      **hecho 2026-07-26** (Yunior: "unusual whales conectado ya vale!, almenos donde hace falta
      si de verdad hace falta"). Conectado SOLO `/api/stock/{sym}/net-prem-ticks` (nuevo
      `scripts/uw_premium.py`): trae `net_call_premium`/`net_put_premium` YA firmados
      ask-side−bid-side por UW (el agresor de TradingFlow: PUT vendido = alcista, CALL vendido =
      bajista) — no hizo falta reconstruir NBBO con IBKR. `opt_whale_watch.py` hace overlay cada
      15 min/símbolo (`UW_POLL_S=900`, cupo del trial), banner **SIN VOZ** (ninguna sirena nueva:
      latencia sin medir en sesión viva + sin `n_eff` para calibrar = "banner sin voz" por regla
      de la casa) + historial `data/uw_premium_flow_hist.jsonl` para la futura calibración.
      **Antes/después con el cierre real del 24-jul** (`data/history/2026-07-26/uw_net_prem_ticks_{spy,qqq}.json`,
      405-406 cubos de 1 min sumados el día completo): SPY volC 5,90M volP 7,43M → P/C **1,26**
      (mid, MUDO); QQQ volC 4,09M volP 4,84M → P/C **1,18** (mid, MUDO). Premium neto del mismo
      día: SPY **-$34,7M**, QQQ **-$37,0M**, ambos BEARISH — exactamente la clase de ballena
      silenciosa que el −53M del 7/21 ya había expuesto y que el ratio de volumen se comía.
      **Descartado por redundante/fuera de alcance** (no conectados a opt_whale_watch): `flow-alerts`
      (mismo bid/ask split pero por alerta suelta, ya cubierto por `net-prem-ticks` continuo —
      duplicaría llamadas sin dato nuevo); `market-tide` (global, no por símbolo — candidato para
      `fleet_consensus`/dashboard de manada, NO para un vigía por-ticker, fuera de mi alcance hoy);
      `greek-exposure*`/`spot-exposures*`/`max-pain`/`vol-term-structure`/`oi-change` (mapa
      GEX/delta — territorio de `gex_core.py`, en el NO-TOCAR de hoy; quedan archivados por
      `uw_archive.py`, sin consumidor nuevo).
      **Latencia SIN MEDIR** (hoy domingo, mercado cerrado — MEDIDO que no se puede fingir: una
      llamada real en vivo a `net-prem-ticks` ahora mismo devolvió el último cubo del viernes
      24-jul a **157.828 s** (43,8 h) de antigüedad, que es exactamente lo esperado un fin de
      semana y CERO evidencia de latencia intra-sesión). Probe listo para el lunes:
      `./venv/bin/python scripts/uw_latency_probe.py` (falla honesto fuera de horas — ver
      `data/uw_latency_probe.jsonl`); umbral candidato a "tiempo real" puesto en el probe: <60s
      de edad en el cubo más reciente. **Hasta que ese probe corra en sesión viva y haya `n_eff`
      suficiente, UW no dispara ninguna sirena** — solo banner + historial.

## 2026-07-23 — Chart cockpit GEX en vivo (charts/live.html + chart_bridge.py)
Hecho: lightweight-charts v5 + ib_async (TWS 7496 realtime) · combo_tl (Supertrend Buy/Sell + Madrid ribbon + BB/SMA/VWAP/MACD + trendlines) · selectores ticker/intervalo · GEX/flip/muros en tiempo real (levels_loop 15s, spot vivo) · escala $/1% verificada · imán(oro)/acelerador(morado) por signo · flip 0DTE estático + toggle 0DTE↔ALL-EXP · VEX/vanna/charm + chip Vanna · dealer-pressure score -100..100 · expected-move cone · nuestras señales (whale/flow/alarma) como marcadores · botones info ⓘ + Guía · dominancia POC %C/%P · régimen TRANSICIÓN · icono custom · burbujas GEX pin/trampilla · badge `.bq` de book-quality. Skill `gexa-framework`.
- [ ] **[pendiente — YA PAGADO, solo falta VERIFICAR EN VIVO]** **VIX**: código LISTO
      (`scripts/chart_bridge.py:1903-1906`, `reqMarketDataType(1)` realtime + chip en
      `charts/live.html:295`, con degradación limpia).
      🟢 **Yunior CONFIRMA el 2026-07-26 que YA TIENE la suscripción IBKR CBOE Global Indexes**
      (~$1,50/mes) → deja de ser una casilla de pago y pasa a ser de VERIFICACIÓN: comprobar en la
      primera sesión viva (dom 20:00) que TWS entrega VIX y SPX. Si entrega, esto cierra **y**
      desbloquea la banda de fragilidad **y** las barras de SPX (que Polygon niega con
      `NOT_AUTHORIZED`), con lo que SPX pasaría de "solo mapa" a candidato de `fleet.txt`. *Por qué importa*: es **la misma suscripción que hace falta para
      SPX**; con un solo pago caen las dos. Ningún cálculo actual lo usa (EM/vanna van por IV
      por-contrato), así que no es crítico — pero sin él, la banda de fragilidad no se puede construir.
- [ ] **[pendiente, BLOQUEADA por el VIX]** Banda de fragilidad / true-flip ajustado por vanna — la
      ÚNICA feature que necesita VIX de verdad: mide cuánto movería el flip un shock de VIX
      (banda <5pt estable, >15pt frágil). *Por qué importa*: distingue un flip que aguanta de uno
      que se mueve solo porque cambió la vol — hoy tratamos todos los flips como igual de sólidos.
- [x] **[hecho 2026-07-26]** **Migration-trail del flip**: `gex_core.flip_migration_trail`
      (`scripts/gex_core.py`, tras `wall_context`) + `gex_snapshot.flip_history` (lee
      `levels_5m.jsonl` de hasta 10 días atrás, filtra `stale`/`flip=None`) → campo
      `flip_migration` en cada símbolo de `data/gex_snapshot.json` (polilínea `trail`,
      `drift_pct`, `reversal_rate`, `shape` horizontal/inclinada/dentada, umbrales declarados
      como CONVENCIÓN no medida, igual que VPVR). **`<3` puntos válidos → `status
      insuficiente_datos` y `shape: None`, NUNCA una forma fabricada** — verificado con datos
      reales: QQQ/SPY/NVDA hoy solo tienen 0-1 puntos archivados (el cron de
      `levels_5min_archive.py` casi no corrió el 25/26-jul), así que en producción **hoy**
      todo sale `insuficiente_datos`, honestamente. Clasificación probada con series
      sintéticas (`tests/test_flip_migration.py`, 11 tests): horizontal/inclinada/dentada
      correctas, orden por ts aunque llegue desordenado, fichero corrupto/ausente no revienta.
      *Pendiente real, no de código*: que el cron de 5 min acumule más de 1-2 puntos/día para
      que el campo tenga contenido en vivo.
- [x] ~~**Volume Profile (VPVR)** desde las barras — POC de volumen vs POC de gamma = confluencia~~
      — **hecho `bc670c6`**. `scripts/volume_profile.cpp` (C++23, `-O3 -mcpu=native -Wall -Wextra`,
      cero warnings) + `scripts/build_volume_profile.sh` + `tests/test_volume_profile.py` (22 tests,
      ASan/UBSan limpios) → `data/vpvr.json`. Lee `poly_bars` en **SQLITE_OPEN_READONLY**.
      MEDIDO sobre datos reales (30 syms × 20 sesiones, 20 s): **LRCX POC-vol 319,92 vs POC-gamma
      320,0 = 0,03% CONFLUENCE**; GLD 0,40% NEAR; 23 APART; 5 con `confluence: null` — exactamente
      los 5 sin POC de gamma en el mapa (NVDA QCOM NFLX NOK SKHY): sin con qué comparar se dice
      null, no "APART". **DESCRIPTIVO Y SIN VOZ**: cero probabilidad; las etiquetas
      CONFLUENCE/NEAR/APART son convención de distancia declarada, y el propio JSON lleva
      `thresholds_are_convention_not_measured: true`. La confluencia **NO está medida** todavía.
- [x] **[hecho 2026-07-26]** **Pin-risk score**: `gex_core.pin_risk_score` (junto a
      `wall_context`) = `hhi (concentración |gamma|, ya existía en build_gex) × proximidad al
      POC (1 - |POC-spot|/spot) × 1/T_min` (piso `PIN_T_FLOOR`=1h/año para que no se dispare a
      infinito al cierre 0DTE); `fortress_pin=True` si `abs_wall == call_wall` (comparación
      exacta, no cercanía). Cableado en `gex_snapshot.snapshot_sym` → campo `pin_risk` en cada
      símbolo de `data/gex_snapshot.json`, **`None` si falta HHI, POC o ningún contrato trae
      `T`** (nunca un score fabricado). Verificado en vivo hoy con datos reales: QQQ score
      18,09 (poc 690 vs call_wall 700, no fortress), SPY 13,28, NVDA 20,63, SPX 6,50 — los 4
      con `fortress_pin: False` porque hoy el POC no coincide con el call_wall en ninguno.
      **DESCRIPTIVO Y SIN VOZ** (`convention` en el propio dato: "no es probabilidad, es un
      ranking descriptivo"), igual que VPVR/migration-trail. `tests/test_pin_risk.py` (10
      tests): los 4 `None`-guards, piso de T, orden score-por-concentración y
      score-por-proximidad, fortress exacto.
- [ ] **[pendiente, buildeable ya]** **Charm al chart**: la matemática YA existe
      (`scripts/gex_core.py:145` `bs_charm`, `build_exposure` con vanna/charm) pero MEDIDO
      `grep -in "charm" charts/live.html` = **0 hits** → falta la capa CHARM en el toggle junto a
      GEX/VEX. *Por qué importa*: el charm es el drift/pin de la TARDE, justo la ventana
      13:30-15:45 que la skill `pin-and-expiry-mechanics` marca como decisiva.
- [x] **[hecho 2026-07-26]** Ampliar strikes del cache (`scripts/opt_chain_cache.py:49-55`).
      **Decisión**: TWS sigue siendo la fuente PRIMARIA del chart/brújula (IBKR=tiempo real,
      regla #4); Polygon (`poly_chain_archive.py`) sigue siendo el archivo/histórico con su
      banda-corona propia, no sustituye al bridge vivo. El bridge se queda TONTO (mueve bytes,
      cero cómputo de banda adaptativa) — solo se ensancha la constante fija.
      MEDIDO contra las 35 cadenas completas (`chain_full_<sym>.json` de hoy, nearest expiry,
      strikes únicos dentro de la banda, tope 20/12 como en producción): con `PCT_BAND=0.06` la
      banda —no `MAX_STRIKES`— era el cuello de botella en 15/26 símbolos (NOK 2, QCOM 8, SKHY 9,
      NVDA/AMZN 10, INTC 12, DRAM/SPCX 13, TXN 14, TSLA/LRCX/GOOGL 15, AAPL 16, MSFT/AVGO 18,
      TSM 19 — todos por debajo del cap de 20). A `PCT_BAND=0.15` los 26 llegan al cap de 20
      **salvo NOK** (máx 5 incluso a 15%; estructuralmente fino — el propio `band_trace` de
      Polygon para NOK no converge ni al techo duro 0.60, `ring_share` 0.064 > `RING_EPS` 0.02).
      `NARROW_BAND` (MSFT/AVGO/AMZN/META) 0.04→0.08: solo AMZN estaba truncado (7 de 12 a 0.04,
      14 a 0.08). **Costo en líneas TWS: CERO** — el conteo de contratos pedidos sigue capado
      por `MAX_STRIKES`/`NARROW_MAX_STRIKES` (mismo `[:max_ks]` de siempre), la banda más ancha
      solo cambia CUÁLES strikes entran antes del corte, no cuántos. Ciclo `<180s` intacto.
      *(Fusiona la casilla duplicada del 2026-07-23 EOD.)*
- BLOQUEADAS (necesitan tape firmado + dark-pool licenciado que NO tenemos): True Dealer Book,
  Dark Pool Nodes, DIX, Market-Tide firmado, GEX direccional. Sustituto casero = daemons whale/flow.
  (Ver skill `anti-overfit-killlist`: no se construyen, y está razonado por qué.)

## 2026-07-23 EOD — gexa se va + fixes chart
- [x] ~~URGENTE (antes de que gexa muera): AMPLIAR strikes del cache … y VALIDAR nuestros números
      vs gexa MIENTRAS SIGA VIVO (última oportunidad de calibrar contra la verdad)~~
      — **obsoleto: gexa.ai desapareció el 2026-07-25.** La oportunidad de calibrar contra ella ya
      no existe y no volverá. Se cierra explícitamente, no en silencio.
      Lo que quedaba de valor (ampliar la banda del cache) vive ahora en la casilla de arriba,
      con su motivo REAL en vez del motivo muerto.
      ⚠️ Y conviene recordar por qué no es una pérdida grande: comparando el último snapshot de
      gexa contra nuestro `gex_core` sobre las cadenas Polygon, **AAPL daba flip 208,0 con spot
      333,47 (−37,6%)** — imposible para un flip de gamma: su scrape estaba roto. Y el campo
      `regime` venía **null en 15 de los 16** símbolos, justo el campo del que depende la doctrina.
- [ ] **[pendiente]** Chart: barra de precios a la derecha muestra precios incorrectos AFTER CLOSE
      — probable autoscale jalado por las líneas de niveles (muros/EM/alarmas) lejos del último
      precio cuando las velas dejan de actualizar. *Fix propuesto*: constreñir el autoscale a la
      serie de velas (`autoscaleInfoProvider`) o esconder líneas lejanas tras el cierre.
      *Por qué importa*: es el eje que Yunior lee para decidir; un eje mal escalado después del
      cierre hace que los niveles del día siguiente se dibujen mal a ojo. *Fichero*:
      `charts/live.html` (en manos de otro agente en la sesión del 25-jul).
- [x] Fix tickMarkFormatter (hora Toronto solo en marcas de tiempo >=3, no en día del mes)

## 2026-07-24 — permiso de bots (TCC) + debug TWS
- [x] Auto-chequeo de permiso en fleet_keepalive_start.sh: si no puede escribir el HUD Desktop -> voz DANGER + data/PERM_DENIED (nunca más pérdida silenciosa).
- [ ] 🥈 **[pendiente — ACCIÓN MANUAL DE YUNIOR]** PERMANENTE (System Settings > Privacy &
      Security > Full Disk Access): añadir `/bin/zsh`, `/usr/bin/python3`, `venv-chart/bin/python`,
      y los binarios C++ (`price_alarm`, `flow_pulse`, `qqq_xray`). *Por qué sigue importando aunque
      el repo ya no viva en `~/Documents`*: la mudanza quitó la causa PRINCIPAL (y los jobs pasaron
      a exit 0), pero cualquier ruta futura bajo Desktop/Documents/Downloads volverá a romperse en
      silencio bajo launchd, y el HUD del Desktop sigue siendo un símlink hacia el repo. Es el único
      fix que garantiza permiso en TODO contexto (launchd/reboot). Coste: 2 minutos.
- [x] ~~POST-CIERRE: centralizar la ruta de señales del Desktop a data/trading-signals/ en los 19
      archivos~~ — **hecho** (fases 1 y 2, ver sección "señales movidas a /data"). Lo único que
      queda de esto es el DEPLOY, fusionado en la casilla de despliegue de abajo.
- [x] Debug TWS: conexiones SANAS (5 conn ESTABLISHED, barras/cache frescos, 253 señales hoy).
      El 326/clientId82 era test viejo. Ruido benigno: opt_chain 'No security definition' +
      chart_bridge Error 366 (cancel hist-data).
- [x] ~~gexa SIGUE VIVA (HTTP 200): calibrar nuestro flip vs gexa (ampliar strikes)~~
      — **obsoleto: gexa.ai desapareció el 2026-07-25** (duplicado del anterior).

## 2026-07-24 EOD — CACERÍA DE BUGS
Workflow de 15 agentes: 87 hallazgos brutos, pero **8 agentes murieron por límite de gasto —
incluidos los 6 refutadores y el team lead**. "0 refutados" NO significa 0 falsos positivos:
significa que nadie pudo verificar. Los de abajo los confirmé A MANO uno por uno.

- [x] **AUTO-CANCELACIÓN** (crítico, evidencia en producción). `openOrder()` cancelaba cualquier
  orden `OE:` sin comprobar si era nuestra y de esta sesión; TWS emite ese callback SIN PEDIRLO
  por cada orden colocada → el motor se cancelaba solo. `ledger/orders.jsonl` id=33: un intent y
  CINCO cancel que nadie pidió, en 150ms. Fix: usar el flag `reconciled_` que YA existía.
- [x] **SIDE PERDIDO** (crítico). `chart_bridge` no pasaba `side` → el motor caía a default SELL.
  Cerrar un CORTO manda "buy" → se vendía otra vez y DUPLICABA el corto. Fix: pasar side+secType.
- [x] **STOP DUPLICADO tras reconnect** (crítico) → segundo STP sobre la misma posición.
  Fix: `adopted_stop_id()` + adoptar el vivo.
- [x] **FILL PARCIAL sin stop** (alto). Fix: emitir FILL por lo llenado + re-armar el stop.
- [x] **TOPE POR ORDEN**: `--max-order` (default = `--budget`). Verificado: qty=4 → VETADO $608.
- [x] **index_breadth** partía por "," archivos separados por ESPACIO → la guarda de frescura era
  CÓDIGO MUERTO y cada corrida caía en silencio a yfinance retrasado.
- [x] **math_test no probaba NADA**: cero `#include` del proyecto. Ahora incluye `engines/bb_core.h`
  con valores de referencia exactos: 39/39 en release Y ASan.
- [x] Skill `bug-hunter` con los 11 olores demostrados + greps de detección.
- [x] ~~`bench.cpp` mide al OPTIMIZADOR: reporta 2.4e12 ops/s (imposible en M1 ~3.2GHz)~~
      — **hecho `3f7010e`**. MEDIDO: `tests/cpp/bench.cpp:41` `sink()` con
      `asm volatile("" : : "r,m"(value) : "memory")`, `:43` `clobber()`, y guarda **fail-loud**
      `:50` `MIN_NS_PER_OP = 0.05` que sale con código 1 si una cifra vuelve a ser imposible.
      2,4e13 ops/s → **2,70 ns/op**. El "9.46 ns/op" que este fichero anunciaba era humo.
- [x] ~~Los 24 bots se compilan con `c++20 -O2` sin arquitectura nativa
      (`deploy_signals_to_data.sh:13`)~~ — **hecho `5d8607f` + `c122128`**. MEDIDO, las flags de
      hoy son `-std=c++2c -O3 -mcpu=native -Wall -Wextra`. Los `-Wall -Wextra` los faltaba y los
      añadí en `c122128`, con conteo de warnings cantado al final del deploy (a propósito **sin**
      `-Werror`: un aviso nuevo de clang no puede dejar a la flota SIN binarios).
      Verificado sin ejecutar el deploy: `qqq_signal_bot.cpp` compila en 2,6 s, exit 0, **0 warnings**.
- [x] ~~**auditoría de TODOS.md** (los `[ ]` de este archivo): el agente murió sin correr~~
      — **hecho: es esta.** 73 casillas revisadas una a una contra código y `git log`. Recuento al final.
- [ ] 🥉 **[pendiente — REPORTAR, NO ARREGLAR]** **~84 hallazgos SIN VERIFICAR** del workflow.
      *Dónde está el fichero*: **NO en el repo.** MEDIDO: `tasks/` no existe aquí y `git log --all
      -- 'tasks/*'` = 0 commits. El fichero vive en un scratchpad de sesión
      (`/private/tmp/claude-502/.../tasks/w7i2a7lhe.output`, 182.703 bytes, 1.448 líneas, mtime
      24-jul 19:06) **y se puede perder al limpiar `/tmp`**.
      *Qué contiene*: JSON con `agentCount: 14`, `logs[]` donde constan los 8 agentes muertos
      (`failed: You've hit your monthly spend limit`), y `result` con
      `total_brutos: 87, refutados: 0, vivos: 87`, repartidos `dinero_real: 34 · señal_falsa: 37 ·
      operativo: 16`. Cada hallazgo trae `file, line, severity, blast, failure_scenario, evidence,
      fix_sketch` y `verdict_note: "sin veredicto"`.
      *Fichero RESCATADO* `hecho 0f7893c`: estaba a una limpieza de `/tmp` de perderse.
      **CLASIFICADOS LOS 87 (2026-07-25), sin arreglar ninguno**: **63 VIVOS · 24 ARREGLADOS ·
      0 no-aplica.** Método validado con 4 controles: los 4 bugs que Yunior confirmó a mano salen
      ARREGLADO y con la huella del fix visible (`tws_adapter.cpp:244` `reconciled_||mia_viva`,
      `chart_bridge.py:1049` side+secType, `order_engine.cpp:510` `adopted_stop_id`,
      `tws_adapter.cpp:213-221` rama `fill_qty>0`).
      Reparto de los 63 vivos: **4 critical · 22 high · 25 medium · 12 low**.
      *Acción que queda*: los 63 siguen **SIN REFUTAR** por un segundo par de ojos — están
      verificados como "el defecto está en el código", no como "el defecto hace daño". Antes de
      tocar nada, refutar por severidad. Los 4 critical y los 5 de dinero están desglosados abajo.
- [ ] 🥈 **[pendiente — LO DECIDE YUNIOR]** **DESPLIEGUE**: los arreglos del motor están compilados
      pero **la flota sigue corriendo los binarios viejos**. `zsh scripts/deploy_signals_to_data.sh`
      recompila 28 binarios (24 bots + price_alarm/flow_pulse/qqq_xray/korea/finviz) y **reinicia
      la flota**. *Por qué importa*: hasta que esto corra, los tres bugs críticos de dinero
      (auto-cancelación, side perdido, stop duplicado) siguen VIVOS en lo que se ejecuta, aunque
      estén arreglados en el código. Además activa el código /data-directo (los bots dejan de
      depender de TCC/Desktop y funcionan bajo launchd/reboot); el símlink del Desktop se queda
      para que Yunior siga viendo las señales. *Cuándo*: SOLO con mercado cerrado. Hoy la flota
      está fuera de ventana a propósito (`./fleet_hours --why`).
      *(Fusiona las dos casillas duplicadas: "DESPLIEGUE PENDIENTE" del hunt y "DEPLOY AL CIERRE"
      de la sección /data.)*

## 2026-07-24 — señales movidas a /data (permiso garantizado, sin TCC)
- [x] FASE 1 (live): bytes migrados Desktop -> data/trading-signals/ (277 líneas, sin pérdida);
      ~/Desktop/trading-signals ahora es symlink -> repo. Cero downtime.
- [x] FASE 2 (fuente): 19 archivos editados para escribir DIRECTO a data/trading-signals
      (Python via `__file__`, shells via `$ROOT`, C++ via `fleet_notify.h` relativo). Cero refs
      de código a Desktop.
- Nota: fase 1 ya da "todo en /data"; el deploy solo elimina el último rastro del path Desktop
  del binario. → casilla de DESPLIEGUE, arriba.

## order_engine — HALLAZGOS AUDITORÍA (2026-07-24, agentes ultracode)
> ⚠️ `order_engine/` es el **ÚNICO** módulo autorizado a colocar órdenes (ENMIENDA 2026-07-24,
> doble llave + paper-first + disarm-on-exit). Por eso sus pendientes pesan más que los del resto
> del repo: aquí un bug es dinero, no una señal fea.

### ✅ ARREGLADOS Y COMPILADOS
- [x] `frozen_` nunca se limpiaba tras reconnect → el motor dejaba de operar el resto del día
- [x] `commands.jsonl` offset TOCTOU → posible **doble-close**
- [x] Fill parcial dejaba posición **sin stop**
- [x] `modify()` sobre STOP escribía `lmtPrice` en vez de `auxPrice` → mover el stop era no-op silencioso
- [x] **Idempotencia entre reinicios**: zona ya llena volvía a COMPRAR al reiniciar
- [x] `reconcile()` cancelaba stops huérfanos → posición desnuda (ahora los **adopta vivos**)
- [x] Disarm-on-exit cancelaba el stop sin aplanar → ahora **deja stops vivos** + aviso en voz alta
- [x] Allowlist de cuenta solo en live → ahora **siempre** (`d9cc62c`)
- [x] Zona borrada del chart mataba el stop de una posición abierta → ahora lo conserva
- [x] Watch-local stop vendía `z.qty` (sobre-venta en fill parcial) → usa `filled_qty`, no remata

### ⬜ PENDIENTES (17 quedaron sin verificar por límite de sesión; estos 9 sí están razonados)
> **Por qué importan, en una línea**: son los que quedan entre el motor y una pérdida real; los
> tres primeros son de TAMAÑO (cuánto se gasta) y los demás de PROTECCIÓN (qué pasa si algo falla).
> **CERRADOS LOS 9 el 2026-07-26** (encargo "buy, sell options and shares, full testing for those").
> ⚠️ **Todos verificados EN FRÍO**: compila 0 warnings + ASan/UBSan limpio + 648 checks en 3 suites
> (`order_engine/tests/run_tests.sh`). **Ninguno ha visto un fill real**: los 4 puertos
> (4001/4002/7496/7497) estaban cerrados el 2026-07-26 — no había Gateway. **La pasada de PAPER
> sigue siendo obligatoria** antes de darlos por vivos en producción.
- [x] ~~Sin tope de exposición AGREGADA por cuenta~~ — **hecho.** `ExposureBook` cableado:
      `order_engine.cpp:420` (`--account-cap`, default $3000, **falla cerrado** si es 0), reserva
      antes de colocar en las DOS ramas (`:866` acciones, `:936` opciones) y libera en cada rama
      terminal sin posición (`:547` STOP_HIT, `:553` REJECTED, `:559` CANCELED, `:775` zona
      borrada sin llenar, `:886`/`:959` DRY). *Sesgo conservador consciente*: un `cmd close` del
      panel NO libera (su orderId no entra en `oid2zone`) → sobra-reserva, veta de más, nunca de menos.
- [x] ~~Sin reconciliación contra `reqPositions`~~ — **ya estaba hecho, verificado.**
      `order_engine.cpp:399` pide posiciones al arrancar y `:634` gatea el close contra ellas;
      `decide_close_qty` falla cerrado mientras `positionEnd()` no haya llegado.
- [x] ~~Presupuesto de opciones por contrato, no por zona (`qty>1` multiplica)~~ — **hecho.**
      El tope por ORDEN (`qty*prima`) ya estaba en `:905`; le faltaba el techo global, que es el
      `ExposureBook` de arriba. Los dos juntos cierran el agujero.
- [x] ~~Panel `close` confía en `cqty` sin comparar contra la posición real~~ — **ya estaba hecho,
      verificado.** `order_engine.cpp:634` `decide_close_qty(tws.positions(), ...)`: clampa a la
      posición REAL del broker y **rechaza** si vendería en descubierto (TFSA no shortea).
- [x] ~~`close` del panel no cancela el stop nativo → stop GTC huérfano server-side~~ —
      **hecho `53e12ec` + mapa `7a0ddaf`/`1bd17c1`.** Cancela ANTES del close; empareja por
      identidad de contrato vía `z.entry_c` (no `z.price`). 94 checks, 0 fallos. Verificado en
      frío; **ruta real con fills queda para paper el domingo** — no declarado verificado en vivo.
- [x] ~~STOP nativo **rechazado** no se reporta como fallo de protección~~ — **hecho.**
      `decide_stop_failure` cableado en el watchdog (`order_engine.cpp:1035`). Los **tres**
      desenlaces GRITAN (stderr + `ledger.note` + `state/NAKED_STOP.jsonl`, `:1039` — stderr solo
      se lo come el log y nadie lo mira). El tercero (sin stop nativo **y** sin spot para vigilar
      local) **CIERRA la posición** en vez de dejarla desnuda en silencio. Se conserva el tope de
      3 re-armes (sin él el watchdog giraba para siempre: 24 cancel/replace por stop en 80s).
- [x] ~~Reconnect re-arma stops sin verificar que `reconcile` terminó~~ — **hecho.**
      `safe_to_touch_orders` cableado en `order_engine.cpp:475`: tras un reconnect se espera
      `openOrderEnd` **y** `positionEnd`; si falta cualquiera de las dos verdades del broker no se
      toca NADA y se reintenta con backoff. Antes pasaba directo a adoptar/re-armar sobre un mapa
      a medio llenar → segundo stop sobre la misma posición.
- [x] ~~Allowlist live usa `find()` (substring)~~ — **ya estaba hecho, verificado.**
      `order_engine.cpp:369` `accounts_match()`: tokeniza el CSV de `managedAccounts` por coma y
      compara EXACTO; falla cerrado con lista o cuenta esperada vacías.
- [x] ~~Clamp asimétrico del stop de opción (caso corto sin cota superior)~~ — **ya estaba hecho,
      verificado.** `guards.h clamp_option_stop`: largo `[max(0.01, 0.10*fill), 0.95*fill]`,
      corto `[1.05*fill, 2.50*fill]`. Test de barrido: los 201 deltas de −1.00 a +1.00 caen
      dentro de la banda en ambos lados.
- [x] ~~`order_engine.cpp:772`: el centinela `-1.0000` usado como **delta REAL**~~ —
      **CONFIRMADO** (no era falso positivo) **y arreglado, verificado.** `option_stop_trigger`
      cableado en `:1001`: mira `entry_iv` (siempre acompaña a un delta real, nunca ≤0 salvo el
      centinela) y descarta el par entero si es el centinela, cayendo al fallback DECLARADO
      (0.60·fill largo / 1.40·fill corto). Antes `fabs(delta) > 1e-6` no distinguía "no sé" de
      "sé, y es −1" → el clamp lo topaba en `0.95*fill` = **stop-out instantáneo**. Es exactamente
      el patrón "cero plausible" del `~/CLAUDE.md`.

### ⬜ order_engine — LO QUE QUEDA (2026-07-26)
- [ ] **[pendiente, BLOQUEANTE para armar live]** **Pasada de PAPER del ciclo completo.** Nada de
      lo cerrado arriba ha visto un fill: el 2026-07-26 los 4 puertos estaban cerrados (sin
      Gateway). Falta: **acciones** (24/5, sí llenan) BUY→FILL→SELL→FILL→FLAT + `close` por
      comando; **opciones** place+cancel (fuera de RTH no llenan, es normal). Hasta eso, las
      guardas están verificadas EN FRÍO, no vivas.
- [ ] **[pendiente]** El `cmd close` del panel no libera la reserva del `ExposureBook` (su
      `orderId` no entra en `oid2zone`). Hoy es un sesgo conservador **a propósito** (veta de más).
      Para arreglarlo bien hay que mapear el close del panel a su zona, no parchear el libro.

### ⬜ UI / DATOS
- [ ] **[pendiente]** **Live market data** (diferido): suscripción IBKR para API en paper, o cablear
      Finnhub (key en feeds.env). *Por qué importa*: sin esto **el spot está STALE y las zonas no
      disparan** — el motor entero es decorativo en paper.
- [ ] **[pendiente]** Selector de timeframe compacto estilo TradingView. *(Cosmético.)*
- [ ] **[pendiente]** Chip de zona dice "Ccall" para acciones — label instrument-aware. *(Cosmético,
      pero induce a error sobre qué instrumento se va a comprar.)*
- [ ] **[pendiente]** Skills de QA engineer + suite de tests automatizada para el motor.
      *Por qué importa*: el módulo que SÍ ordena es el que menos cobertura tiene.
- [ ] **[pendiente]** Optimizar latencia de ráfaga (mediana 1.1s por serialización del pump 2s;
      min real 113ms). *Por qué importa*: "retraso = dinero" (regla propia de Yunior).

## OLA 1 features minadas — CERRADA (2026-07-25)
Spec: `docs/FEATURES-MINED-2026-07-25.md`.
- [x] **#5 `chain-honesty`** — inversión de IV por bisección + forward por paridad en `gex_core`,
      `iv=0.3` BORRADO, cabecera honesta en `opt_chain_cache.py`, contrato en `docs/CHAIN-HEADER.md`,
      `greeks_ok_pct<0.5` → claves gamma a `null` (jamás 0). Medido: RTH 100% griegas, 16:16 = 0%. `56ed1fe`
- [x] **#6 `flip-honesty` + congelar a 09:35** — el repreciado GANA, `flip_src`/`flip_why`, todas
      las raíces con bisección, `trapdoor_root`, `flip_open` congelado / `flip_live` diagnóstico.
- [x] **#13 `next-day-map` roll-off** — `exp_status()` rueda el vencimiento EN EL CIERRE (16:00 ET),
      no a medianoche. Era la causa del salto de MANADA de las 00:00:45.
- [x] **#3 `book-quality gate`** — `scripts/book_quality.py` → `data/book_quality.json`, etiquetas
      THIN/BIFURCATED/NEAR_FLIP/STABLE_PIN + coeficiente multiplicativo. `b066f81`
- [x] **`vol-trigger` (#20) congelado a 09:35** — `scripts/vol_trigger.py` → `data/vt_<sym>.json`. `04b9fcf`
- [x] ~~cablear el `coef` de `book_quality` como MULTIPLICADOR en `direction_view` + badge~~
      — **hecho `b91de93` `13c903d`** *(duplicado: aparecía dos veces en el fichero)*.
- [x] ~~`poly_chain_archive.py` NO tiene job de launchd — hoy solo 3 símbolos~~ — **hecho `70c0e2c`**.
      MEDIDO: `com.ibtrader.polychains.plist` a las 16:20 y 08:45; **30 cadenas archivadas hoy**.
- [x] ~~que `book_quality.py` prefiera `chain_full` cuando `ibkr_tws` dé <50% de griegas~~
      — **hecho `1cacc8f`**. MEDIDO: `book_quality.py:89` `MIN_GREEKS_SRC = 0.5`, regla pura
      `prefer_fallback()` en `:175-192`, y la **procedencia va DENTRO del dato**: `chain_src`
      (`:228`) + `greeks_medidas`. Esto cerró el hallazgo de que **el "THIN" de 25/26 símbolos era
      un artefacto de la fuente, no un hecho del mercado** (AAPL: 20 contratos y 0% griegas por
      IBKR fuera de RTH → THIN coef 0; por Polygon, 96 contratos y **94%** con gamma+OI medidos).
      Sin este fix la flota entera operaba con los niveles gamma apagados fuera de RTH. `6ef5f5d`
- [ ] **[pendiente — ESPERA DATOS, no código]** percentiles `book_pctile`/`impact_pctile` necesitan
      **20 sesiones** de snapshot COMPLETO de Polygon (feature #7); hoy salen `null` DECLARADOS y el
      `coef` cae al suelo 0.35. Se acumulan solos en `data/book_quality_hist.jsonl` desde que el
      cron existe. *Por qué importa*: mientras tanto el gate de libro está en su valor más
      conservador y **frena la gamma de todos los símbolos por igual**, incluidos los libros sanos.
      *Cuándo se desbloquea*: ~20 sesiones desde el 2026-07-21.

## OLA 1 — archivadores, guardas de integridad y presupuesto de voz (2026-07-25)
> 7 features, 7 commits, 101 tests nuevos.
- [x] **#16 `chain-cube archive` + retención** — `6bae616`. Lector ÚNICO de los dos formatos,
      índice de cobertura honesta (2984 fotos, 171.216 filas), retención medida (7,40 → 2,2 MB/día).
      **`--apply` SIN activar**: `local_option_scorer.py`, `option_vehicle_backtest.py` y
      `replay.cpp` leen las fotos SUELTAS por glob. Migrarlos al lector antes de agrupar.
- [x] **#18 `levels-5min archive`** — `c91c375`. Copia cada 5 min sin tocar el generador, con
      `age_s`/`stale` para que copiar un fichero atascado 78 veces no parezca densidad. ~4,7 MB/día.
- [x] **#15 `equity-prints archiver`** — `b0c1b8a`. Salva la cinta firmada ANTES del trim de 900 s
      sin tocar `ibkr_bar_bridge.py`. Primera corrida: 7477 prints salvados.
- [x] **#9 `truth-lock`** — `ea26bc5`. Huella SHA-1 de 120 barras cerradas por sym; inyección sobre
      el fichero REAL detectada (close +0,05). Banner + tabla propia, SIN voz.
- [x] **#10 `em-envelope`** — `176caea`. `data/em_<sym>.json`, 26/30 vallas. Dos bugs cazados con
      datos reales (vallaba el lunes con el straddle 0DTE del viernes).
- [x] **#14 `pin-clock`** — `d21f2eb`. `data/pin_<sym>.json` descriptivo, `p_pin` SIEMPRE null.
- [x] **#12 `voice-budget governor`** — `daf90de`. DANGER ni pasa por el gate, fail-open.
- [ ] **[pendiente — LO DECIDE YUNIOR]** cargar los 5 `.plist`
      (`scripts/com.ibtrader.{prints,levels5m,truthlock,cubeindex,fence}.plist`, `plutil -lint` OK,
      **sin cargar a propósito**). *Por qué importa*: hasta cargarlos, 5 archivadores corren solo
      cuando alguien los lanza a mano, y **las features que esperan 20-40 sesiones no empiezan a
      contar**. Es el cuello de botella de 3 casillas de abajo.
- [ ] **[pendiente — LO DECIDE YUNIOR]** encender el presupuesto de voz con
      `touch data/voice_budget_enable`. Hasta entonces es código muerto **por diseño** (fail-open,
      DANGER exento). *Por qué importa*: sin él nada limita el número de avisos hablados por sesión.
- [ ] **[pendiente — ESPERA DATOS]** (#15) ningún motor de absorción hasta ≥20 sesiones archivadas
      por sym; hoy 1. *Depende de*: cargar el plist `prints`.
- [ ] **[pendiente — ESPERA DATOS]** (#18) ninguna feature puede condicionar sobre gamma a tiempo
      de etiqueta hasta que `levels_5m.jsonl` tenga ≥40 sesiones; hoy 1. *Depende de*: plist `levels5m`.
      *Por qué importa*: es lo que bloquea el **migration-trail del flip** y cualquier feature que
      quiera saber en qué régimen gamma estaba el mercado cuando se etiquetó una señal.
- [x] ~~(#14) el kill por colinealidad de `pin-clock` necesita n≥10 syms con `chain_full` (hoy 3)~~
      — **hecho `6f4fc62`: corrido, y `pin-clock` SOBREVIVE su propia vara.**
      MEDIDO hoy con la muestra completa: **n=30 símbolos, rho=−0,2753**, kill `|rho|>0,9` →
      `APORTA_ALGO`. El max pain **no** es un duplicado del `abs_wall`, así que la feature se queda.
      Sigue **SIN probabilidad medida**: esto mide colinealidad, no edge, y ahora la nota lo dice.
      De paso se arregló un defecto de honestidad: la nota se quedaba clavada en "con n<10 no se
      concluye nada" incluso con n=30, al lado de un veredicto concluyente — un lector no sabía a
      cuál creer. Hay test que prohíbe que la nota niegue la muestra.

## REGENERACIÓN DE SEÑALES (agente regen, 2026-07-25)
- [x] "usa los datos de polygon y reproduce, es sencillo... olvidate del websocket de IBKR,
      reproduce local como si estuviera conectado a IBKR" (Yunior 2026-07-25) —
      `scripts/regen_signals.py` + `scripts/regen_shim/`. `hecho f11c6fb 09d0a80`.
      501 sesiones (2024-07-25 → 2026-07-24). cusum 501/501 COMPLETO (n=12.780).
- [x] ~~CORRIENDO EN BACKGROUND: bollinger va por 63/501 sesiones, ETA ~2,8 h~~
      — **hecho: TERMINÓ.** MEDIDO hoy en `trades.db`: `signals_regen` tiene **200.811 filas
      bollinger cubriendo las 501 fechas** (2024-07-25 → 2026-07-24), y el proceso **ya no corre**.
      ⚠️ **Honestidad**: el log `/tmp/regen_R1_boll.log` tiene **24 sesiones con `rc=-15`** (SIGTERM),
      así que esas 24 pueden estar cubiertas solo en parte. Antes de publicar cualquier número de
      bollinger conviene re-correr esas 24 fechas (es reanudable: mismo comando).
      Cadena a rehacer con la muestra completa:
        `./venv/bin/python scripts/barrier_labels.py --signals-table signals_regen build`
        `./venv/bin/python scripts/null_control.py --signals-table signals_regen --null-exclude sym-date run --seed 7`
      *(El `barrier_labels build` estaba corriendo mientras se escribía esta auditoría.)*
- [x] ~~`cusum` sale **DEAD** con muestra suficiente~~ — **hecho `2804663`**: TERREMOTO pasó a
      **BANNER-SOLAMENTE**. MEDIDO (n_eff 1513, edge −0.034, CI [−.060,−.005] **entero por debajo
      de cero**): la alarma es PEOR que entrar al azar. Prueba en el fichero vivo,
      `data/signal_enable.json:114-122`, con el `why` escrito dentro del dato.
      **Matar una feature con números vale tanto como construirla.**
- [ ] **[pendiente — LÍMITE DE DATOS, no de código]** NO regenerable sin cadenas históricas:
      `whale`, `flow`, `structural` (solo 4 días de cadenas en `data/history/`). Para medirlas hay
      que archivar cadenas a diario y esperar ~40-60 sesiones, o backfillear opciones de Polygon
      (que **no traen OI ni griegas** — medido). *Por qué importa*: son 3 de las fuentes que más
      voz tienen hoy y **ninguna está medida**. Es el mayor punto ciego que queda tras la ola 1.
      *Ya está corriendo el reloj*: el cron de cadenas existe desde el 2026-07-25 (`70c0e2c`).
- [x] ~~Las 30 skills `ticker-*` + `gamma-regime-walls` siguen diciendo "gexa gamma"~~
      — **hecho** (verificado en disco; **sin commit porque viven fuera de git**, en
      `~/.claude/skills/`). MEDIDO: `ticker-qqq/SKILL.md:3` dice hoy "mapa gamma propio, muros OI
      IBKR…", sin gexa; `gamma-regime-walls` = 0 hits de gexa. Residuo benigno: 2 de 31 ficheros
      la mencionan en el CUERPO como nota histórica fechada, no en la `description`.
      Las skills DEL REPO se arreglaron en `a387e03`.

## HUNT 2026-07-24 — los 87 clasificados (2026-07-25). NINGUNO ARREGLADO AQUÍ
> Fichero completo: `docs/hunt/hunt-2026-07-24-w7i2a7lhe.json`. **63 vivos · 24 arreglados.**
> "Vivo" = el defecto está en el código HOY. **No** = está demostrado que hace daño: eso es lo
> que faltan los refutadores. No tratar como bug hasta refutar.

### Los 4 CRITICAL vivos
- [x] ~~`scripts/backtest_harness.py:72` — `ret=(r[0]-entry)/entry*100*th; win=ret>0.05`~~ —
      **CONFIRMADO Y ARREGLADO `85bec77`**. Ya no tiene definición propia de "win": delega en
      `barrier_labels` (triple barrera) y añade el COSTE declarado (`FRICTION_PCT`: acción
      0,040% / opción ATM 0,069% / opción OTM 0,340% del subyacente). MEDIDO en la celda
      pre-comprometida k_tp=k_sl=1,0 H=30: WR viejo TOTAL 47,8% → barrera sin coste **50,0%**
      (que es la moneda al aire analítica `k_sl/(k_tp+k_sl)`) → **42,7% neto** de opción ATM y
      **5,4%** de opción OTM. La expectancia TOTAL pasa de +0,000 ATR a **−0,355 / −0,613 /
      −3,021 ATR**: negativa en TODAS las celdas en cuanto entra cualquier coste. Sobre las 501
      sesiones (`barrier_outcomes_regen`, n=213.656) bollinger va de 50,0% bruto a **37,0% neto**.
      Propuesta en `data/backtest_harness.PROPUESTO.json`: 93 celdas, **0 APTA**. `baseline`
      conserva el etiquetado viejo solo para el scoreboard, con
      `label_def='horizon_return_DEPRECATED'` estampado en la fila. 19 tests.
- [ ] **[pendiente]** `scripts/bollinger_complements.py:394` — grid de **318 tests sin corrección
      por multiplicidad**. *Daño*: **95 celdas de ruido aplicadas como VETO en vivo** en `bb_engine.cpp`.
- [x] ~~`scripts/calibration_ledger.py:110` — `after = d[d.High >= entry]` es una máscara
      booleana, no un corte temporal~~ — **CONFIRMADO Y ARREGLADO** (diff en `75a3442`, barrido
      por el `commit -a` de otro agente; medición en `d77a7a4`). Ahora es corte temporal
      `d.iloc[i0:]` desde la barra que imprime la entrada, con la barra de entrada ambigua
      resuelta STOP-PRIMERO igual que `barrier_labels.triple_barrier`. Los dos tests que fallaban
      lo hacían con `'win' == 'loss'`: el daño literal. MEDIDO: sobre el ledger vivo (56 filas,
      2026-07-21) el replay reproduce exacto el 88,9% publicado y **no cambia ni una fila** →
      `data/calibration.json` intacto, nada que conmutar. Sobre 13.365 sesiones reales de
      `poly_bars` con la geometría del propio ledger: 63,2% → **62,8%** (−0,4 pp), y el sesgo
      tiene SIEMPRE el mismo signo en las 14 geometrías barridas (la máscara nunca es
      conservadora). **La mina**: el daño escala con la resolución de barra — −0,5 pp a 15m
      (lo que `grade()` baja hoy), −2,7 pp a 5m, **−6,6 pp a 1m**. Quien "mejorase" `grade()`
      afinando el `interval` se comía 6,6 pp de mentira sin tocar el bucle.
- [x] **[hecho — start_new_session + AbandonProcessGroup]** **[pendiente]** `scripts/fleet_healthcheck.py:248,314` — `Popen(["nohup","zsh",...])` sin
      `start_new_session` y plist sin `AbandonProcessGroup`. *Daño*: **el auto-curado es un NO-OP**
      y el informe canta "REVIVIDO" en falso. Creemos tener red de seguridad y no la hay.

### Los 5 vivos más peligrosos por DINERO REAL
1. ~~`order_engine.cpp:152,919` — **el centinela `-1.0000` del delta usado como delta REAL**~~
   **CERRADO 2026-07-26** (`option_stop_trigger` en `:1001`). Ver la casilla de order_engine.
   Confirmado que era real: fuera de RTH el **100%** de las filas de `data/opt_chain_*.txt`
   traían `-1.0000`, y el clamp lo aterrizaba en `fill_px*0.95` = stop-out instantáneo.
2. ~~`order_engine.cpp:632` — el `close` se precia con `nearest_row()`, que nunca exige strike
   igual~~ **CERRADO** (`run_gate(..., require_exact_strike=true)` en `:654`/`:1095`; `exact_row`
   exige right+exp+strike o falla limpio). Test con testigo: sin el 705 en la cadena,
   `nearest_row` entregaba el 700C con bid 6.00 vs 3.00 — el DOBLE de precio.
3. `order_engine/order_engine.cpp:1095-1110` — **SIGUE ABIERTO.** El cierre por stop watch-local
   es de un solo tiro: `z.close_id` se fija una vez, sin re-precio ni reintento si no llena.
   *(Mitigado en parte: si no hay precio de cadena ya NO remata a 0.01, espera. Pero una vez
   mandado, nadie lo revisa.)* Y es justo el camino al que lleva el watchdog tras 3 rechazos.
4. `nvda_signal_bot.cpp:1375,1423` — `tail -n +1 -F` **sin dedupe por epoch**. Cada warm-up del
   bridge re-inyecta ~2 días de barras a los indicadores VIVOS de los 24 bots: ATR, RSI, BB, CUSUM
   y VWAP envenenados, y hablan señales que luego se operan.
5. ~~`order_engine.cpp:626` — `cmd close` pasa el `cqty` del panel directo, sin gate de tamaño~~
   **CERRADO** (`decide_close_qty` contra `reqPositions` en `:634`, más el gate de cadena en
   `:654`). Cerrar sigue sin vetarse por dinero (presupuesto infinito, correcto: salir nunca se
   veta por caro) pero sí por tamaño, contrato erróneo y cadena podrida.

### Otros vivos que contradicen doctrina escrita (muestra, no la lista entera)
- [x] **[hecho fae191c — fail-closed en los 24, verificado en el BINARIO]** `aapl_signal_bot.cpp:1738,1839` — el gate de spread **falla ABIERTO**: sin NBBO,
      `sp = 0` y pasa todo. La orden #5 dice que un spread ancho NO es señalable.
- [x] **[refutado 2026-07-26]** `aapl_signal_bot.cpp:788,835` — `V6_PRIOR[]` literal: **NO se
      canta suelto**. `V6Prob::prob()` (:831-835) solo lo usa como prior de shrinkage bayesiano
      (k=20) mezclado con filas REALES de `data/prob_table_aapl.txt` (`maybe_reload` en :1053);
      sin fila para la clase devuelve `-1` y `consider()` (:1145-1146) hace `if (p<0) return;`
      — "no se canta prior inventado", literal en el código. Comprobado en los 24 bots: los
      otros 23 (ej. `nvda_signal_bot.cpp:1144-1148`) NO tienen ese `if (p<0) return;`, pero es
      **inerte**: `V6_PROB_MIN` (`nvda_signal_bot.cpp:537`) default 55, la fórmula de shrinkage
      siempre da ≥0, así que un `-1` sin medir JAMÁS gana la comparación `p > best.prob` contra
      un candidato real ni pasa `cb.prob >= V6_PROB_MIN` (:1315,1318) — nunca dispara ni se
      anuncia (el único print con `-1` es de depuración, tras `V6_DEBUG>0`, default 0). Hardening
      de una línea (`if (p<0) return;`) en los 23 restantes es zero-riesgo pero NO urgente —
      pendiente si Yunior quiere el barrido completo (23 recompilaciones secuenciales, 8GB).
- [x] **[FALSO POSITIVO 8cfdb7a — la clave SÍ coincide, probado QCOM/qcom/Qcom]** `scripts/signal_conditioning.py:267` — busca `enable[f"{source}|{symbol}"]` con
      `source="order_engine"/"ticket"`, cuando las claves reales son `bollinger|AAPL`… →
      **el condicionamiento NUNCA aplica justo donde se ordena.**
- [x] **[hecho 2026-07-26]** `order_engine/prob_profit.py:42,287` — `prob = 50 + composite*40`
      sobre pesos literales: confirmado, mismo patrón prohibido. Arreglado con el patrón exacto
      de `scripts/compass.cpp` (`prob_of`/`calib_context`): el score de composición pasa a
      llamarse `doctrine_score` (nunca "prob"), y `prob` es ahora `Optional[int]` — se llena
      SOLO si existe bucket `"order_engine|<régimen>"` con `trust` en `data/calibration.json`
      (`_measured_prob()`, nuevo), si no `None` + `prob_source="sin_medir"`. Hoy ese bucket no
      existe → `prob` sale `null` siempre (honesto), y el verdict GO/CAUTION/NO-GO sigue
      calculándose con `doctrine_score`, no con un número inventado. `chart_bridge.py` (agregado
      ajeno, no tocado) ya usaba `{"prob": None, ...}` como default antes de este fix — cero
      riesgo de romperlo. Tests: `order_engine/prob_profit_test.py` (nuevos casos 1,5,6,6b) +
      `bash order_engine/tests/run_tests.sh` sigue en 499 OK (C++ intacto).
- [x] **[hecho 8cfdb7a — compara contra el cierre anterior]** `scripts/index_breadth.py:58-62` — `pc = d.Close.iloc[-1]` es HOY, comparado contra `now`:
      MEDIDO en `data/breadth.json` de hoy, **gap +0.00 en TODOS los componentes** → el
      ENGRANAJE QQQ/SPY está mudo.
- [x] **[hecho 8cfdb7a — portero ./fleet_hours, aborta en sesión viva]** `scripts/deploy_signals_to_data.sh:49` — `pkill -f '_signal_bot$'` **sin guard de horario**:
      mataría 24 bots + relay + BD con el mercado abierto. *(Relevante para la casilla de DEPLOY.)*
- [x] **[hecho 8cfdb7a — calendario de festivos del repo]** `scripts/opt_whale_watch.py:41` — `in_session()` solo mira lunes-viernes: **cero calendario
      de feriados en todo el repo.**
- [x] **[hecho 8cfdb7a — acotado a la capacidad; overflow reproducido con ASan]** `fleet_notify.h:54` — `write(fd, line, (size_t)n)` con el `n` de `snprintf`: un mensaje largo
      = **lectura fuera de buffer** y línea corrupta.
- [x] **[hecho 8cfdb7a — escritura atómica tmp+os.replace]** `scripts/ibkr_bar_bridge.py:147` — `open(...,"w")` 4×/s **sin tmp+rename**: el lector puede
      ver el fichero VACÍO. (La regla de frontera de `~/CLAUDE.md` pide escritura atómica.)
- [x] **[hecho 2026-07-26]** `scripts/fleet_keepalive_start.sh:257` + `scripts/nvda_keepalive.sh:31`
      — confirmado: el dedup `pgrep`-luego-`nohup` tiene ventana TOCTOU entre dos instancias
      concurrentes de `fleet_keepalive_start.sh` (cron 300s solapado con una corrida manual, o
      con el `finviz_valuation.py` síncrono alargando una corrida) → doble `nvda_keepalive.sh`
      (o cualquier símbolo) peleándose con `pkill -x` cada ~31s. Arreglado con mutex `mkdir`
      (atómico, mismo patrón que `speak.sh`) alrededor de TODO el cuerpo del script, con robo de
      lock viejo (>120s) para no dejar la flota apagada si una instancia murió a medias. Test:
      `tests/test_fleet_keepalive_lock.py` (3 casos: dos instancias concurrentes, secuenciales
      normales, lock huérfano) — reproduce la carrera de verdad con `subprocess` y un
      `fleet_hours` stub, sin tocar bots reales.

---

# 📊 RESULTADO DE LA AUDITORÍA (2026-07-25)

**Había 73 casillas `- [ ]`.** Revisadas una a una contra el código y `git log`:

| Clase | N.º | Qué significa |
|---|---:|---|
| **YA HECHAS** (nadie las tachó) | **22** | Estaban hechas y commiteadas. Marcadas `[x]` con su commit. |
| **OBSOLETAS** | **5** | La oportunidad ya no existe. Cerradas **con el motivo escrito**, no borradas. |
| **DUPLICADAS** (fusionadas) | **3** | Misma tarea contada 2 veces. Fusionadas en una, con nota. |
| **VIVAS** | **43** | Reescritas con qué es, fichero(s) y **por qué importa**. |
| **TOTAL** | **73** | |

**Casi la mitad de lo "pendiente" ya estaba hecho** (30 de 73 cerradas). La sospecha era correcta:
el fichero llevaba días midiendo trabajo que ya existía, y eso hace que lo urgente de verdad no se vea.

De esas 43 vivas, **2 se cerraron en esta misma tanda** (`pin-clock` con n=30 y la documentación
de los 4 daemons), así que quedan **41** de las originales. El fichero cuenta hoy **43** casillas
abiertas: esas 41 **+ 2 nuevas** que salieron al auditar y no estaban antes — el residuo
`com.ibtrader.scan` (plist apuntando a un binario inexistente; se separa de la casilla del exit 78
porque es OTRA raíz distinta) y el centinela `-1.0000` usado como delta real en
`order_engine.cpp:772`, que venía enterrado en el montón de los 84 sin refutar.

**Cerradas de verdad HOY en esta tanda** (no solo tachadas — código nuevo + tests):
- `39bd147` — cashtags de X: `$4.7B` también cuenta. 14 tests. *(era la casilla ~169)*
- `c122128` — `-Wall -Wextra` en el deploy de los 28 binarios; MEDIDO 0 warnings. *(era la ~228)*
- `bc670c6` — **VPVR**: POC de volumen en C++23 + confluencia con el POC de gamma. 22 tests. *(era la ~177)*
- `6f4fc62` — `pin-clock` corrido con n=30: **sobrevive** (rho −0,2753 vs kill 0,9), y la nota deja
  de contradecir al veredicto. *(era la ~331)*
- `7875b32` — los 4 daemons que el manual no mencionaba, documentados. *(era la ~151)*
- `0f7893c` — los 87 hallazgos del hunt **rescatados de `/tmp`** al repo antes de perderse. *(parte de la ~223)*

**Suite completa tras la tanda: `581 passed`, 0 fallos** (la referencia eran 412+; los 36 nuevos
son 14 de cashtags y 22 de VPVR).

**Las 5 obsoletas y por qué** (ninguna se borró en silencio):
1. Calibrar el flip contra gexa "MIENTRAS SIGA VIVA" (~184) — **gexa.ai desapareció el 2026-07-25**.
2. "gexa SIGUE VIVA (HTTP 200): calibrar nuestro flip" (~193) — ídem, y además duplicada.
3. "Revisar plan Polygon" (~158) — contestado hoy con la key real y grabado en `~/CLAUDE.md`.
4. Fichas CLSK/INTC del 7/22 (~168) — la fecha pasó hace 3 días.
5. "gexa es hoy CASI REDUNDANTE" (~347) — la decisión la tomaron los hechos: gexa murió.

**Las 5 duplicadas fusionadas**: exit 78 de launchd (~149 + ~167) · ampliar strikes del cache
(~180 + ~184) · deploy de los 28 binarios (~230 + ~236) · cablear `book_quality` en `direction_view`
(~292, ya `[x]` en ~335) · centralizar señales a `/data` (~191, ya hecho en fases 1-2).

---

## 🎯 LAS 5 VIVAS MÁS IMPORTANTES, por DAÑO si no se hacen

1. ~~🥇 **Nadie consume la calibración de barrera.**~~ **CERRADO 2026-07-26.** `direction_view.py`
   ya no canta `prob = 50 + |score|*40`: patrón `compass.cpp` copiado (`doctrine_score` = CONTEXTO,
   `prob` Optional solo con bucket `direction_view|<regimen>` medido, `calib_context` lee
   `null_control.json`). `calibration_barrier.json` sigue SIN usarse aquí a propósito (n=1154 es
   pool crudo de bollinger, población distinta del setup compuesto — no se cablea lo que no mide
   lo mismo). Ver casilla ~389.

2. 🥈 **El DEPLOY no se ha hecho: la flota corre binarios viejos.** Los tres bugs críticos de
   dinero (auto-cancelación, side perdido → corto duplicado, stop duplicado) están arreglados en el
   código y **no en lo que se ejecuta**. **Daño**: directo y en dólares, a la primera orden real.
   *(Lo decide Yunior; hoy la flota está fuera de ventana a propósito.)*

3. 🥉 **63 de los 87 hallazgos del hunt siguen vivos, 4 de ellos critical.** El fichero ya está
   rescatado (`0f7893c`) y los 87 clasificados (`63 vivos · 24 arreglados`, método validado con 4
   controles). **Daño**: el peor es del patrón prohibido — el centinela `-1.0000` usado como delta
   real (`order_engine.cpp:152,919`) hace que **todo stop nativo de opción nazca a −5% de la
   prima**, y MEDIDO fuera de RTH el 100% de las filas de cadena traen ese centinela. Y tres de
   los critical atacan la base numérica: el backtest sin costes ni stop (WR 44%→29,6%), las 95
   celdas de ruido aplicadas como VETO en vivo, y el healthcheck cuyo auto-curado es un NO-OP que
   canta "REVIVIDO" en falso. Siguen **sin refutar**: verificar antes de tocar.

4. **Los 5 `.plist` de archivadores sin cargar bloquean 3 features y el reloj no corre.**
   `book_pctile` (20 sesiones), absorción (20), condicionar sobre gamma (40) — hoy van por 1.
   **Daño**: cada día que pasa sin cargarlos es un día que NO se acumula. Mientras tanto el gate de
   libro se queda en su suelo (0.35) y frena la gamma de todos los símbolos, sanos incluidos.

5. **Los capitanes pueden llevar semanas decidiendo con la cinta vacía.** El fix de prioridad
   QQQ→SPY→SMH está commiteado (`c6e1513`), pero MEDIDO hoy `whale_qqq.txt` y `whale_spy.txt`
   siguen a **0 bytes** y 9 de 14 están vacíos. **Daño**: la **regla 12** (el capitán prevalece y
   anula la señal del nombre) es una de las reglas más fuertes de la casa y se alimenta de ahí.
   Verificarlo cuesta un `ls -la` en la primera sesión viva.

> **Honestidad de esta auditoría**: todo lo marcado MEDIDO se comprobó hoy con una orden concreta
> (`git log`, `grep`, `launchctl print`, `sqlite3`, `ls`). Lo que no pude observar —porque la flota
> está parada un sábado— queda dicho como **sin observar**, no como hecho. Dos afirmaciones del
> fichero anterior resultaron FALSAS al medirlas: el exit 78 (hoy `last exit code = 0`) y el regen
> de bollinger ("63/501" cuando en realidad cubre las 501 fechas).

## VETO DE BOLLINGER — multiplicidad (agente bollinger, 2026-07-26)
- [x] **Grid de ~400 pruebas sin corrección por multiplicidad** (`bollinger_complements.py:394`,
      criterio `n>=15 y |uplift|>=5pts`). **CONFIRMADO Y ARREGLADO**: BH-FDR q=0.10 sobre
      muestra EFECTIVA (ρ̄=0.41 medida) → **0 de 401 celdas sobreviven**; caen las **150**
      publicadas (**70 veto** + 80 best). Sobre RUIDO PURO (etiqueta barajada, 10 semillas) el
      criterio viejo publicaba **112,9 celdas de media**; el nuevo, **0**. `bb_engine` ya no
      aplica un veto sin `fdr_ok:true`: **+1717 señales desbloqueadas** (5865 → 7582, +29%) en
      30 tickers × 30 días. Propuesta en `data/bollinger_plus.PROPUESTO.json`
      (`bollinger_plus.json` VIVO sin tocar — la conmutación la decide el lead).
- [x] **[hecho 2026-07-26 — agente signals, orden explícita de Yunior]** conmutado
      `bollinger_plus.json` a la propuesta. Backup `data/bollinger_plus.json.bak-2026-07-26`
      (fichero viejo intacto). Verificado los 3 consumidores ANTES de conmutar: `bollinger_alarm.py`
      solo MENCIONA el fichero en un comentario (no lo lee); `yoel_adapted_engine.py:37` solo usa
      `base.p`/`base.wilson` por ticker (test single, no forma parte del grid de 401 celdas) —
      valor `p` sin cambios, cero impacto; `regen_signals.py:290` solo lista el nombre del fichero
      como dependencia de refresco. El consumidor real de `veto_filters` es `engines/bb_engine.cpp`
      (ya trae el gate `fdr_ok` desde el fix de arriba) — con la lista ahora vacía de verdad
      (antes vacía "por fallback silencioso" al faltar `fdr_ok`) el comportamiento en vivo no
      cambia (0 vetos aplicados en ambos casos) pero desaparece el `stderr` de aviso y el dato
      deja de mentir sobre lo que contiene. `test_bollinger_multiplicidad.py::test_la_propuesta_no_pisa_el_fichero_vivo`
      sigue verde (usa `tmp_path` con `REPO` monkeypatcheado, no toca el fichero real).
- [x] **[hecho 6ebcbca — alineadas con la medición (3TF NO es más fuerte)]** **[pendiente — doc]** `.claude/skills/bollinger-mastery/SKILL.md:180` y `engines/README.md:56`
      siguen documentando el criterio viejo `n>=15, |uplift|>=5`. No los toqué (fuera de mi zona).
- [x] **"with BB, are we making sure it breaks in 1 min and 15 min? to avoid noise?"** (Yunior
      2026-07-25) → **MEDIDO, y la respuesta es NO exigirlo**: P(toque de la media en 30 min)
      baja monótonamente cuantos MÁS timeframes estén rotos — **67,2% (solo 1m) > 49,4% (BB-2TF
      1m+5m) > 43,0% (BB-3TF)**, n = 4031 / 409 / 200. Exigir el 15m recorta el 92% de la muestra
      y empeora. Romper en más TF no confirma la reversión: es band-walk. `bb_engine` ya hace lo
      correcto (veta el elástico si los TF mayores caminan, `bb_core.h:300-302`); los
      `*_signal_bot.cpp` cuentan `bb_dn_tfs>=2` como CONFIRMACIÓN, que es el signo contrario.
      Números en `data/backtest/bcomp_tf15.json`. Ninguno de los contrastes llega a p<0,05 con
      n_eff → **UNPROVEN**, banner-solamente. Cambio de regla en los bots: lo coordina el lead.
- [ ] **"clean my desktop... only keep updated info, just in one folder"** (Yunior 2026-07-26)
      → **hecho** (agente limpieza escritorio, sin borrar nada, solo `mv`): `~/Desktop/ib-trader/hoy/`
      (planes-2026-07-26 + price-alerts.txt) y `~/Desktop/ib-trader/archivo/` (planes-07-21..25,
      imanes-07-21/22, price-alerts-archivo-20260720.txt, QQQ_plan_caida_BN.pdf/png renombrados
      con fecha, `.trading-signals.bak`). Escritorio raíz quedó con: `ib-trader Cockpit.app`
      (sin tocar, otro agente arreglando su icono), enlace `trading-signals` (sin tocar — 11
      ficheros vivos lo leen/escriben: `price_alarm.cpp`, `whale_scalper.cpp`, `chart_bridge.py`,
      `screener/state.py`, etc.), `ib-trader/` nueva, y **hallazgo**: lo que la petición llamaba
      "10.48.app 79B, alias roto" **NO es basura** — es `IB Gateway 10.48`, symlink real y
      funcional a `~/Applications/IB Gateway 10.48/IB Gateway 10.48.app`. Lo dejé en el escritorio
      intacto, no encaja en el reorg de ib-trader.
      **PENDIENTE DE DECISIÓN — 2 jobs escriben directo a la raíz del Desktop con ruta
      hardcodeada (no a `ib-trader/hoy/`), van a repoblar el escritorio mañana**:
      1. `com.ibtrader.printplans` (lunes 09:25) → `print_mon_plans.sh:8` `DEST=$HOME/Desktop/planes-$DAY`.
      2. `price_alarm.cpp:80` (vía `com.ibtrader.fleet`/`fleet_keepalive_start.sh`, cuando la
         flota despierte hoy 20:00 Toronto) y `chart_bridge.py:665` — ambos hardcodean
         `~/Desktop/price-alerts.txt`, van a recrear el fichero en la raíz en cuanto haya nueva
         alarma. `daily_archive.py:195` también lee `~/Desktop/planes-{date}/ranking.json`
         hardcodeado (hoy ya corrió a las 16:10, sin impacto; mañana si el folder está en
         `hoy/` en vez de la raíz, el `cp` con `warn=False` fallará en silencio y no archivará).
      No toqué estos 3 scripts (fuera de mi encargo). Si Yunior quiere que el reorg se mantenga
      solo, hay que repuntar esas 3 rutas a `~/Desktop/ib-trader/hoy/`.
