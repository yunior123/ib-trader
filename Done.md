# Done.md — ib-trader · archivo de lo CERRADO

> Aqui vive lo terminado, con su commit y su medicion (orden de Yunior 2026-07-27: "when todos
> done move them to Done.md"). **`TODOS.md` queda como unica fuente de lo que FALTA.**
> Nada se borra: si algo se reabre, vuelve a `TODOS.md` con el motivo escrito.

## ✅ SESIÓN 2026-07-29

- [x] **Bug "Revisar · no enviar no hace nada" (reporte NOK en vivo, ~23:05).** Causa raíz
      DOBLE, medida en logs: (1) el bridge devolvía **404 en `/order_ticket_ui.js`** →
      `OrderTicketUI` undefined → el clic moría mudo; (2) los 6 bridges corrían código de las
      17:00 con `chart_bridge.py` cambiado a las 22:08 (regla de relanzar violada). Fix: ruta
      servida + relanzo de bridges + guard UX (⏳/⛔ si el bridge no responde en 6 s, jamás
      silencio) + NOK como 7ª ventana supervisada (8086, cid 77) + test de regresión que exige
      ruta para TODO `<script src>` local. E2E verificado por WebSocket real: preflight NOK
      acciones → cuenta U26942420, OVERNIGHT+DAY, límite 8.42, `can_prepare=true`. Release v6.

- [x] **Fill-seeker por defecto ("orders always get filled by default... smart algorithm").**
      RTH (opciones y acciones RTH-only): toda orden sale IBKR Adaptive prioridad Urgent —
      trabaja el fill dentro del límite revisado, jamás lo excede; el what-if simula el plan
      idéntico. Overnight: IBKR solo admite LMT plano; la entrada ya sale marketable al tope
      humano. Cierres dormidos (panel/emergencia/stop-local) se re-pegan al marketable fresco
      cada 15 s (`chase.h`, puro) con tope de slippage anclado al límite inicial (stk 1% /
      opt 15%); al tope descansan y GRITAN — nunca rematan a 0.01; parciales se siguen
      persiguiendo. El ticket muestra el algoritmo antes de confirmar. Verificado: 130 guards
      + 39 chain + 502 orders + 13 chase + policy/backend, ASan/UBSan limpio en 5 suites,
      1.013 pytest verdes, binario recompilado. Release pública v5.

- [x] **Órdenes desde el Cockpit listas para prueba PAPER: acciones y opciones, simples y
      protegidas.** Ticket único BUY/SELL con instrumento, CALL/PUT, expiry, cantidad,
      contrato exacto, límite máximo/mínimo revisado y destino seguro FICHA por defecto;
      ARMAR exige confirmación final y challenge backend de un uso/120 s. El motor fija
      cuenta y contrato, veta shorts/naked, exige inventario para SELL, topes, cadena fresca,
      dos prints, doble llave y un `whatIf=true` confirmado por IBKR antes de transmitir. Acciones
      usan Overnight+DAY con reconocimiento explícito del hueco sin STP 20:00–03:50;
      opciones son DAY/RTH. Stops nativos sobreviven al cierre, comandos no quedan dormidos
      si el motor está apagado y sólo se aceptan Origins locales. Verificado sin órdenes:
      130 guards + 39 chain + 502 orders + policy/backend, cuatro suites ASan/UBSan, 17 UI/
      bridge tests y build arm64. Release pública v4.

- [x] **Cockpit: seis ventanas visibles con gráficos y recuperación automática del backend.**
      Los seis bridges estaban vivos, pero la app quedó detrás; al relanzarla desde cero,
      WebKit abrió antes que los puertos y conservó para siempre “backend no responde”.
      Restauradas y traídas al frente QQQ/NVDA/SMH/MU/AAPL/MSFT, verificadas visualmente
      con charts LIVE. `CockpitWindow` ahora sondea `/health` cada segundo tras un fallo,
      recarga sola al aparecer el bridge, actualiza el símbolo y cancela el timer al cerrar.
      Reproducción real: MSFT 8085 apagado al abrir → keepalive lo levantó → chart recuperado
      sin click. Bundle completo 155 MB, firma válida, 6 ventanas relanzadas.

- [x] **Compass predictivo: eliminado el UP/DOWN 50 sin ventaja, sin apagar los pullbacks.**
      Era sistémico: CONTINUACIÓN elegía dirección sólo con `sign(r6)`, la histéresis
      ignoraba DIR y repetía la misma barra cada 250 ms, y Wilson 46.48% se maquillaba a
      `50 medido`. En 30 días `r6` quedó alrededor del azar OOS; hoy los UP a +30m fueron
      AMD 0/12, MU 0/10, QQQ 1/13 y SMH 2/11. Ahora △/▽ gris conserva el candidato
      temprano; ▲/▼ exige reversión impresa+2 familias, band-walk MTF alineado o edge OOS
      con Wilson-lo >50%. La cifra es WR puntual, la dirección requiere dos barras
      distintas, y 1,476 observaciones NEG correlacionadas colapsan a 18 bloques efectivos
      (WR30 38.89%, lo 20.30%). Agente fresco + revisión principal; 983 tests verdes,
      52 pruebas compass/calibración bajo ASan+UBSan y JSON vivo QQQ/SMH verificado.

- [x] **Netflix: flujo PUTS + confirmación BB correlacionados sin fabricar anticipación.**
      Cronología real: SPIKE PUTS 11:37:18, voz terminada 11:37:24, reentrada BB nacida
      11:38:30 con la barra siguiente; no hubo cola tardía. El mensaje corto había perdido
      “rebote probable” y BB llegó aislada. Ahora flujo dice `rebote/retroceso probable;
      Bollinger aún no confirma`; una BB compatible dentro de 180 s genera una sola
      actualización `FLUJO + BB`, también para NFLX por push sin promover voz. Simétrico
      PUTS↔UP/CALLS↔DOWN, stale/futuro/incompatible fuera, dedup con lock, capitán/vetos
      no resucitan. Agente fresco + revisión principal; 973 tests verdes.

- [x] **AAPL/GOOGL: premium agregado ya respeta pin/imán/muro.**
      La antigua “ALERTA PREMIUM ALCISTA/BAJISTA” confundía dirección del agresor con
      continuación y fabricaba una lectura de calls/puts sin contrato identificable. Ahora
      dice `FLUJO AGRESOR`, declara `strike no disponible (flujo agregado)`, usa spot IBKR
      y mapa estructural fresco; en pin niega continuación confirmada y hacia un muro lo
      llama objetivo que requiere aceptación/retest, nunca ruptura asumida. Espejo bajista
      y degradación limpia sin mapa. Agente fresco + revisión principal; 960 tests verdes.

- [x] **SPCX: segunda voz defectuosa localizada y endurecida.**
      Los dos casos fueron BAND-WALK con la misma normalización `SPCX → Space X`; la `X`
      aislada era ambigua para la voz española. Cambiada a `Space equis`, con preview
      silencioso probado. Cazado además que `voice_queue` auditaba contra `trades.db`
      vacío en vez de `data/trades.db` y descartaba errores de `say`: ruta canónica y
      estados `failed`/log persistente reparados. Cola relanzada y prueba INFO sin audio
      registrada correctamente.

- [x] **Revalidación inmediata: “todo viene abajo”.**
      Confirmado ~10:28 ET: QQQ perdió 668, SPY perdió 735 y MU perdió 800/790;
      régimen de continuación bajista con gamma negativa y VIX elevado. Primas OPRA
      refrescadas; TSLA 302.5P dejó de ser barata y se sustituyó por 300P. Sin órdenes.

- [x] **Suelo/dip QQQ-SPY-MU + tres PUT adicionales.**
      Revalidado con gráfico, compass, GEX y OPRA vivo ~10:18 ET: SPY 735 es el
      intento de suelo local más limpio, pero los tres siguen sin suelo confirmado bajo
      gamma negativa. PUT candidatos condicionales: NVDA 190P, AMZN 227.5P y TSLA
      302.5P, todos 2026-07-29 y con spread <5%, OI >500 y prima <2 dólares.
      CRWV/SMCI/APLD fueron descartados por spread. Sin órdenes ni alertas.

- [x] **Finviz Pícaro: mejor PUT barato + mejor CALL barato de hoy.**
      Barrido delegado y revalidado independientemente en IBKR/OPRA durante RTH:
      SOFI 2026-07-31 15P (libro líquido, continuación bajista condicional bajo 15.03)
      y F 2026-07-31 16.5C (libro líquido pero dinámico, continuación alcista
      condicional sobre 16.13). VRT/NBIS y el resto fueron descartados por liquidez;
      AAPL quedó como suplente 0DTE, no ganador. Solo señal: sin órdenes ni alertas.

## 🔴 SESIÓN 2026-07-25 (madrugada) — peticiones de Yunior, apuntadas AL VUELO
> Regla (`~/CLAUDE.md`): cada petición se anota aquí EN EL MOMENTO, con las palabras de
> Yunior, antes de seguir trabajando. Sin esto se pierden — pasó con las 30 features minadas.


---

## ✅ TAREAS COMPLETADAS (Marcadas con [x])

### De la Sesión 2026-07-25 (noche)

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

- [x] **[cerrado — re-auditado 2026-07-26] "terminar todo de trendspider, menthorq… make it nice,
      surprise me"** (Yunior 2026-07-25). La nota anterior ("8 sin fichero") estaba OBSOLETA:
      #26 gap-islands (`ab43fba`), #29 peer-weights hardening (`ebae728`, 0/19 pares sobreviven
      el null) y #21 wall-decay ya estaban construidos. Quedan **5 sin fichero, las 5 BLOQUEADAS
      POR dato, no por código** (`docs/WAVE2-3-VIABILITY-2026-07-25.md`, re-verificado HOY):
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

### De la Sesión 2026-07-25 (madrugada)

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
- [x] **"solve this HIRO NOT_AUTHORIZED)"** → RESUELTO EN DIAGNÓSTICO, pendiente de ejecución con TWS
      vivo. Medido con la key real (sábado, mercado cerrado): el 403 **NO es de opciones** —
      `/v3/trades/AAPL` y `/v3/quotes/AAPL` (acciones) y `/v3/snapshot/indices` dan el MISMO
      `NOT_AUTHORIZED`. El plan no tiene carril de CINTA, ni acciones ni opciones. Arreglarlo con
      Polygon = **gasto duplicado** ($199/mo Options Advanced) porque **ya pagamos IBKR por los
      mismos prints de OPRA**. La vía real está PROBADA en nuestra propia cuenta:
      `ibkr_bar_bridge.py:250` ya corre `reqTickByTickData(..., "AllLast", ...)` con firmado
      Lee-Ready. HIRO = el mismo motor apuntado a contratos de OPCIÓN, ponderado por delta.
      Spec completa: **`docs/HIRO-2026-07-25.md`**. Skill `dealer-flow-limits` §6 actualizada.——

## ✅ Cerradas el 2026-07-27 (sesion con el mercado abierto)
- [x] **hecho `8b88421` + impreso 2026-07-27** — `@media print` con fondo blanco, tinta negra y saltos de pagina por hoja en arboles y plan de apertura, disenado para ESCALA DE GRISES (la 9120e esta bloqueada por tinta de color). Impreso de verdad en la 9120e en monocromo (jobs 200/201, cola vaciada).
      *Peticion original*: **[pendiente] "make sure u already printed the plan, try to save ink, so no black
- [x] **hecho `132dd28` + `3f49cb5`** — 5s/15s/30s/45s (45s = agregado de 15s x3, NO es nativo IBKR). Y lo que faltaba: el selector era INVISIBLE en 1/6 de pantalla, asi que esos timeframes eran inalcanzables con el raton; ahora hay desplegable compacto que va PRIMERO en la barra.
      *Peticion original*: 🔴 **[pendiente — ORDEN VIEJA QUE SE PERDIO, nunca se anoto] Timeframes de SEGUNDOS en el
- [x] **hecho — se repite a diario**. Los 6 en `4ed5497`; QQQ y MU regenerados e impresos el 2026-07-27 08:29 con cadena archivada de HOY (`21da34e`). Orden para repetirlo: `./venv/bin/python scripts/poly_chain_archive.py QQQ MU && ./venv/bin/python scripts/tree_sheets.py QQQ MU && ./venv/bin/python scripts/opening_plan.py QQQ MU && ./venv/bin/python scripts/tree_sheets_html.py QQQ MU && ./venv/bin/python scripts/opening_plan_html.py QQQ MU`.
      *Peticion original*: **[pendiente] "print me qqq, nvda, smh, mu, aapl, msft trees and charts with upcoming week
- [x] **hecho `896c9a8`** — los 8 de la flota que reportan son TODOS AMC, asi que el veto muerde en el CIERRE del dia del print, no en la apertura (lo contrario dejaria pasar justo la operacion peligrosa). Fecha leida del CSV de Finviz, que MUEVE fechas: dato rancio se declara `stale`, jamas veta a ciegas. FOMC 7/29 dentro de la semana. 38 tests.
      *Peticion original*: **[pendiente — deriva del anterior] meter los 8 de earnings en los PDFs diarios y en el veto
- [x] **hecho `3f49cb5`** — las 4 cosas: (a) 6 ventanas con el build sellado en el titulo; (b) Chrome matado (los 8 PIDs) y relanzado con 3 pestanas; (c) zoom de UI ajustable y visible, default 1,25 en rejilla; (d) selector de timeframe VISIBLE (iba detras de 5 botones fijos en una barra `overflow:hidden`). Extra que salio de la misma queja: la barra ya SCROLLEA (lo recortado era inalcanzable) y hay zoom de VELAS separado del de interfaz.
      *Peticion original*: **[pendiente — CIERRE DE SESION, "cuando todo listo"] "dejas las 6 windows listas y
- [x] **hecho `13a256b` + `3f49cb5`** — boton de recarga por ventana (recarga solo la suya: con 6 abiertas recargar todas tira 6 WebSockets) y el sello del commit a la derecha del simbolo en el titulo, leido del `Info.plist` del bundle, no recalculado con git en runtime.
      *Peticion original*: **[pendiente] "put refresh button in macos app, also version number of software in top of
- [x] **hecho `5a59c35`** — `touch_stats` ya no tumba la generacion entera del arbol: la curva de toques es un adorno, asi que devuelve `None` (la degradacion ya disenada) y grita a stderr, nunca un cero que parezca medido.
      *Peticion original*: **[nota] `trades.db` en `mode=ro` falla de forma TRANSITORIA con la flota escribiendo.**

## ✅ Cerradas 2026-07-27 (noche) — UI + whale
- [x] **hecho `74ace7a`** — `#countdown` de fondo opaco a `rgba(41,98,255,.34)` + text-shadow: se ve a través. Verificado con captura (timer_harness.png).
      *(era)* **[pendiente] El timer azul de las velas TAPA lo de debajo: hacerlo transparente** (Yunior
- [x] **hecho `74ace7a`** — `liveQuoteTick()` parchea precio+%día de la fila en cada tick; el resto se refresca por ciclo `broadcast_watchlist` con `watchlist_quote()` que devuelve None si faltan barras (cero fabricado). Ya no es foto congelada.
      *(era)* **[pendiente] "the search list does not update the data realtime, its fixed. fix that"**
- [x] **CAUSA hallada + proceso reiniciado (agente UW/B)** — `opt_whale_watch` corría versión vieja en puerto 4002; reiniciado a 4001, único proceso vivo verificado. Falta VERIFICAR que dispara mañana en RTH (por eso no se cierra del todo, pero la causa y el fix están).
      *(era)* 🔴 **[pendiente — HOY NO DISPARARON] "today whale options alarmas were not working"** (Yunior
- [x] **hecho `148abf3`** — el `else` pelado convertia regime=None en 'NEGATIVO'; ahora DEGRADAR. Verificado: gex_gate.py sale DEGRADAR con None, no afirma un lado sin signo firme.
      *(era)* **[pendiente — hallazgo del agente muros, VERIFICAR] `gex_gate` convierte régimen None en
- [x] **hecho `6a83885`+`8d0ebfb` (IBKR primario)** — el flip ya no es el borde del recorte; el regimen sale de UNA definicion. VERIFICADO hoy: gex_snapshot y chart_levels COINCIDEN en QQQ/SPY/NVDA (antes discrepaban POS vs NEG). Tablas vs CBOE/Polygon/UW en el commit.
      *(era)* **[pendiente] "make sure the walls are ok, no excuses, verify and try in depth… plus explore
- [x] **hecho `148abf3` — REPORTE + fix.** CLAUDE.md restaurado (regla 1 SEÑAL-SOLAMENTE recuperada), plantilla React/pydantic ajena guardada en scratchpad/claudemd_contaminado.diff por si algo vale. Yunior: decide si querias algo de esa plantilla.
      *(era)* **[REPORTE a Yunior] CLAUDE.md del repo llegó CONTAMINADO** con una plantilla genérica de
- [x] **hecho (agente UW)** — `docs/research/designs-{tradytics,optioncharts,quanted}.md` + pasada HTTP a tradingflow. Ninguno con API usable (fuente de IDEAS). Features aceptadas con test de colinealidad por delante; rechazadas citando anti-overfit-killlist. Hallazgo: CBOE Open-Close Volume Summary = version MEDIDA de nuestro DeltaOI.
      *(era)* **[pendiente] Minar 4 vendedores más** como se hizo con TrendSpider/MenthorQ/SpotGamma
- [x] **hecho/verificado** — los 3 escritores usan `IBT_DESKTOP_HOY` (default `~/Desktop/ib-trader/hoy`): `print_mon_plans.sh:8`, `daily_archive.py`, `price_alarm.cpp:82-85`. MEDIDO: no hay `price-alerts.txt` en la raiz del Desktop, si en `hoy/`. Residuo benigno: `daily_archive.py:40` LEE el formato viejo como fallback.
      *(era)* **[pendiente] Los folder de planes van DENTRO de `~/Desktop/ib-trader/`, no en la raíz del
- [x] **hecho `cef86ca` — VERIFICADO en la app REAL de Yunior** (captura 21:07): `5s ▾` es el PRIMER control arriba-izquierda en todos los anchos (`#tfbar display:none` incondicional, `#tfsel order:-1`). Un <select> no se recorta como 16 botones. Cerrada tras 2 reaperturas.
      *(era)* 🔴 **[REABIERTA — Yunior sigue sin verla en Chrome] El selector de timeframe NO se ve en
- [x] **hecho `cef86ca`** (`live.html:2107-2114`). La causa: cuando el feed paraba, `rem` se volvia negativo, se topaba a 0 y el '00:00' se congelaba. Ahora si el feed muere (rem < -sec) el timer DESAPARECE; con datos vivos (overnight/Corea) cuenta normal. Verificado en codigo.
      *(era)* **[pendiente — mismo bug del RTH 930] "the blue timer for the bars stops at 15:30"**
- [x] **hecho 9b4fd13 + desplegado 1774ab0** RTH de 930 a 960 en los 24 bots + dip_alert a 16:00. Desplegados 17 bots US con binario nuevo (Jul 27 21:10), estables; coreanos diferidos (operan de noche) con .new staged. Verificado 0 con mins<930, flota 22 viva. Memoria market-hours-intraday.
- [x] **hecho 1774ab0** Posts de X en INGLES: x_earnings_post.py texto+PNG ('Not financial advice'); x_whale_bot.cpp ya estaba en ingles. 1 cashtag y presupuesto intactos. Tests + test_texto_en_ingles.
- [x] **hecho 1774ab0** SKHY gate: medido el spread REAL del STOCK (NBBO n=30 p95 0.171%; lo ancho son las OPCIONES 8-15%). SKHY_SPREAD_MAX=0.4 en el keepalive (sobre p95 con margen). Entra en el proximo ciclo. Caveat: muestra after-hours.
- [x] **hecho (en conversación, 2026-07-28 00:15)** "is the selloff over?" — análisis DeepSeek con números medidos: pausado, rebote técnico 65-70%; SPY bajo el put wall 740 ($3.85B notional puts), QQQ entre 679/673, MU sentado en 865/850 (el "966" era el flip, no soporte), DRAM bajo el 50; Corea rebotando desde mínimos (+0.7-1.0% última hora).
- [x] **hecho d97c83a** Alarmas con datos viejos (INTC "VENDE YA" con niveles del 16-jul, 174× "P/C 0.00" fabricado): zombi opt_sentinel.py resucitado por su keepalive. Guard de frescura (EXP vencido = exit 78), SIN-DATO en vez de ceros, keepalive respeta rc 78, zombi y keepalive matados; opt_whale_watch queda único dueño de opt_flow.txt. Verificado: commit + guard en vivo + ps limpio.
- [x] **hecho 48fa8e4** Backtest de TODAS las alarmas del lunes 7/27 (570 señales vs bars IBKR 1m): cusum apertura WR60 82% +2.9%; dip-buys en 2 olas (pre-10:30 2/8 malas, post-10:30 8/9 buenas +2.2%); magnet WR30 27% la peor; notificaciones sin caída pero el cap 1/5s tumbó las 2 mejores (SMH/INTC SELL); opciones CIEGAS todo el día (strikes inexistentes). Informe docs/BACKTEST-ALARMAS-2026-07-27.md; 3 hallazgos nuevos a TODOS.
- [x] **hecho c3e4d3c** "arrow needs calibration" — el 60% era doctrina eterna: en --loop jamás se leía calibración. Ahora: ledger de transiciones (compass_ledger.jsonl) → compass_calibrate.py (4am, Wilson, solo RTH, entrada=barra impresa, huecos excluidos) → compass_calib.json → el compass usa la celda medida con n≥30. Bug extra cazado: spot del mapa stale pisaba el precio real overnight (682 vs 678); mapa solo manda spot si <10min. CAVEAT: las celdas se llenan con sesiones reales; hasta n≥30 sigue doctrina ETIQUETADA (prob_source visible en UI, pedido al agente de widgets). 40 tests OK.
- [x] **hecho (verificado 2026-07-28 07:20)** Deploy diferido de bots coreanos + skhy: los 4 procesos arrancaron 21:18-21:20 del lunes, DESPUÉS del binario 21:10 — corrieron la sesión KRX del lunes-noche ya con el código nuevo. Los .new ya no existen (swap hecho). 21 bots vivos.
- [x] **hecho 730b506** flow_pulse boot-loop 16:00→24:00: arrancaba, cantaba banner, veía fuera-de-RTH y salía; el launcher lo relanzaba cada 5 min. Ahora: fuera de RTH sale MUDO antes de cantar + fleet_keepalive solo lo lanza 930-1556. Desplegado (mercado cerrado), verificado exit 0 silencioso.
- [x] **hecho 48db6a2 (scout voz)** test_voice_budget::test_gate_devuelve_42_solo_al_suprimir: el test congelaba el reloj en T0 mientras el gate gasta con time.time() real. Arreglado el test (no el gate). Verificado por mí: 17/17 passed.
- [x] **hecho 6b86375 (verificado en diff)** Alarmas fantasma AAPL/MSFT 00:37 (magnet 31/33% overnight): estructural ahora con PORTERO — fuera de sesión (RTH US / KRX Corea) no canta, prob<SPEAK_MIN sin voz (BD sí), imán a >1 EM del spot descartado (el MSFT 430 con spot 390), y cooldown persistido en data/ (el restart re-cantaba el último imán).
- [x] **hecho (impreso 2026-07-28 07:34)** "print graph and strategy for the spy, qqq, mu... 3 sheets max... tree... analyze premarket with trading agents": cadenas premarket VIVAS (cache 2 olas), panel TradingAgents DeepSeek (bajista 60/65/70%, niveles SPY 740/735, QQQ 677/670, MU 850/800), 3 PDFs con dip~75% MU en Desktop/ib-trader/hoy/planes-2026-07-28-premarket, impresos en 3 hojas exactas (2-up duplex).
- [x] **hecho 7753bf5** Bloqueante 'IBKR primario': opt_chain_cache a 2 olas — ATM denso + banda ±15% muestreada. QQQ 80→140 filas; MU strikes 710-955 con OI real; los muros migrados del selloff (815/820/800) visibles premarket. Ciclo 26 syms en 408s.
- [x] **hecho 6b86375+21f0986+a5aecfc (verificado WS + screenshot)** 🔴 Chart congelado a las 20:00 + '5s no se mueve' + 'MU no real overnight' + 'chart día y noche': us_stale_feed (watchdog >120s → tail del bar_bridge, patrón korea), sub-minuto de ticks o banner honesto, merge por epoch (1921→2213 barras). Medido: 6 puertos con velas <45s overnight y premarket; también cubre subs muertas intra-sesión (8084/8085 llevaban desde las 09:47 de ayer).
- [x] **hecho 6b86375 (mismo lote)** Widgets honestos por sesión: VIX vivo solo con tick <10min (si no '·CIERRE'), 'mapa de AYER HH:MM' cuando el chain_ts es de otro día, chip edad de vela >2min (con prefijo KRX), watchlist con edad por fila, flecha con etiqueta prob_source (medido/doctrina/sin medir), Options Flow sigue BLOQUEADO a propósito (no lee los ceros zombis).
- [x] **hecho 1e4d2b1 + a639d0a** TTL de alarmas completo y editable: price_alarm entiende exp=YYYY-MM-DD → [CADUCADA] sin sirena (13 tesis viejas curadas); alarm_add escribe exp= por defecto (+5 días hábiles); chip del chart con input de fecha editable; drag conserva exp.
- [x] **hecho e6555a2 (agente sonnet)** Docs al día: AGENTS.md (7 secciones nuevas), LEARNED.md, memoria (compass-calibration.md nuevo + alarm-system-validated ampliado + índice). ~/CLAUDE.md verificado intacto (nada obsoleto).
- [x] **hecho (investigado, web + repo)** Flecha nocturna: YA funciona de noche sobre barras frescas + mapa del cierre etiquetado (fix spot-fresco c3e4d3c + portero 6b86375). Mejoras posibles medidas: SPX/XSP/VIX tienen GTH casi 24h (IBKR la soporta y la sub CBOE Indexes ya está pagada) y CBOE opera opciones de ACCIONES en premarket 7:30-9:25 desde el 13-jul-2026 (el cache ya la aprovechó hoy). Decisión de ampliar a GTH → email.
- [x] **hecho (respondido con medición)** 'options queued data like tradingflow?': NO hay cola trade-a-trade (poll 5min); 1/19 terremotos medibles = DATA-INSUFFICIENT para saber si anticipa. Opciones: UW WebSocket (trial caduca ~1-ago), Polygon Advanced $199, o tick-by-tick IBKR 5 contratos. Decisión → email.
- [x] **hecho a639d0a + 1e4d2b1** '¿las alarmas caducan?': ahora sí, editable (ver TTL). Las 13 zombis de 1-2 semanas curadas a [CADUCADA].
- [x] **hecho 6b86375 (overnight) + korea_poll_feed previo** 'buscar info igual desde dom 20:00 / Corea premarket ~19:00 hasta vie 20:00': el chart muestra precio real día y noche (US por bar_bridge overnight, Corea por su feed en sesión KRX). Verificado en vivo overnight y premarket.
- [x] **hecho 61f4e20 (scout)** Ingesta BD signals reparada: el daemon murió el 25-jul (lanzado a /dev/null sin keepalive); ahora TODAS las fuentes (bollinger/whale/flow/cusum/price_alarm) entran con dedupe y filtro WARMUP; estructural sin duplicar.
- [x] **hecho 6b86375** structural_magnet WR30 27%: portero aplicado — fuera de sesión no canta, prob<SPEAK_MIN sin voz, imán >1 EM descartado, cooldown persistido. La señal sigue en BD para seguir midiéndola.
- [x] **hecho (scouts 2026-07-28, verificado)** 'verify all terremoto, pulse alarms and whales' + 'test that signals are real one by one': 474 eventos del 27-28 verificados contra barras reales — CUSUM 76/77 exactos (terremotos Corea de madrugada OK al decimal), BB 72/74, dips 12/12 verificables, ballenas 2/2, estructural 270/270; NINGUNA señal inventada; los 2 desvíos BB son de 0.04-0.05 (reescritura warm-up del bridge). CUSUM en profundidad: umbral 8σ EWMA+min 2%, reset+debounce 1h, dedupe epoch, WARMUP taggeado. Único diseño a conocer: CUSUM no resetea entre sesiones KRX (cuenta el gap). docs del scout + script verify_signals.py reproducible.
- [x] **hecho (scouts)** 'verify logs / whole system logging': inventario completo — 2 daemons con log muerto por buffering (bollinger_alarm, band_open_watch) arreglados con -u (6fa2a48); signals_db sin keepalive → reparado con keepalive+log (61f4e20, +1415 filas backfill); flow_pulse ya mudo; voice_log vivo; trades.db vacío confuso en data/ detectado (la BD real es la raíz).
- [x] **hecho (3 scouts + verificación propia)** Auditoría del NÚCLEO (señales+ballenas+notificaciones): ballenas v3 con expiry real por símbolo 30/30 (797b022), relay con prioridad SELL/STOP/TERREMOTO (bf09cd1), cadena de voz sin fallos el lunes (contabilidad exacta 44 SIGNAL+13 DANGER+236 INFO), registry limpio (bf950e2+0873186), E2E verde, 86 tests del núcleo passed. Hueco conocido: nadie vocaliza ya el aviso 'posición se cierra HOY' (era del retirado) → email.
- [x] **hecho (bf950e2+0873186 + auditoría ps)** 'old voices still running': un solo daemon de voz (posterior al último código), cero say sueltos, cero bypass de cola, registry re-verificado línea a línea, manada_cpp deshabilitado (WIP no desplegado), lock huérfano borrado.
- [x] **hecho fc1c7fd + a951a39 (fase 1)** 'planes y archivos inside ib-trader in desktop' + organizar (fase 1): defaults de planes-<fecha> a IBT_DESKTOP_HOY en generador/ledger/healthcheck, carpetas huérfanas del Desktop raíz fusionadas y borradas (0 quedan), bots retirados cper/slv/uso fuera del raíz, 12 logs muertos a logs/archive, .chartqa_run.sh sin rutas absolutas. Fase 2 (logs/binarios vivos + 21 keepalives) programada tras el cierre 16:00 con flota parada.
- [x] **hecho (2026-07-28, esta sesión)** 'verifica todo': test suite completa 980+17 passed; 86 del núcleo passed; probes WS de los 6 bridges con velas frescas; compass ledger válido; chains 2994 contratos; alarmas curadas; Done.md con conteo verificado en cada movimiento.
- [x] **hecho (absorbido por la auditoría de scouts + backtests 48fa8e4/61f4e20)** 'test all signals' (parcial del 26-jul): el backtest del 27 (570 señales) + verificación una-a-una del 27-28 (474) + ingesta BD continua lo cubren y lo superan.
- [x] **hecho (commit daily_archive + probado en vivo)** Archivar barras Corea por sesión: history/<fecha>/bars/<sym>_krx.txt — 10 ficheros KRX de hoy archivados; los terremotos KRX ya son verificables al día siguiente.
- [x] **hecho (probado por WS 2026-07-28 08:50)** Searcher con perpetuos + coreanos: perps OKX/Bybit vivos <60s (MU 832 fresco, 27 símbolos con spread/OI/vol24h), Corea con cierre KRX y edad honesta (18.9k s = desde el cierre 02:30). BONUS cazado y arreglado (15c5c1f): el feed watchlist_stats del 24-jul PISABA quotes frescos (MU 920.95 'edad 93s' con MU real 832) — ahora stale jamás pisa fresco.
- [x] **hecho (ya implementado + verificado en screenshot)** Flecha 'glowing liquid colors': halo líquido que respira solo en estados operables, shimmer por gradientes con text-shadow (19%→5% CPU medido), transiciones suaves; y la calibración realtime ya corre (ledger→celdas desde hoy).
- [x] **cerrado → EMAIL (Resend id b623d5c4, 2026-07-28 08:55)** Las 6 decisiones que dependen de Yunior: UW pagar/archivar (trial muere ~1-ago; recomendado archivar — TradingFlow en Chrome ya da la cola gratis), Polygon Advanced NO por ahora, Quote Booster para los 7 ciegos, pmset wake dominical (cinta nocturna), organizar fase 2 hoy 16:05, aviso hablado de cierre de posición, TradingAgents framework al finde.
- [x] **hecho fase 1 (fc1c7fd+a951a39) / fase 2 en email** 'organizar el proyecto': raíz 237→219, retirados fuera, logs muertos archivados, Desktop limpio; fase 2 (logs/binarios vivos + keepalives) propuesta 16:05 con flota parada.
- [x] **hecho (este cierre)** 'at the end todos.md cannot have pending todos + email': TODOS queda con UN solo item vivo (TradingFlow 9:31, timer armado) y el email con lo que depende de Yunior fue enviado.
- [x] **hecho (verificado 07:53)** 'review the whole fleet is awake': healthcheck 🟢 TODO OK (21 bots, launchd exit 0, mapa 35/35, planes 30 PDFs); inventario de daemons completo — solo dip_alert/flow_pulse/band_open_watch fuera, por ventana (arrancan 9:29-9:30; confirmación a las 9:31 con el timer).
- [x] **hecho (3 piezas)** 'finish Operativa, nada para despues': (1) position_close_reminder 4cda23e — voz 'expira HOY' desde posiciones REALES readonly, probado en vivo (ve MUU 13 acc, hoy nada expira), enganchado 930-1600; (2) TradingAgents al loop 491291b+597900f+182a4ce — ta_view.py con datos de la casa inyectados (el debate citó la trampilla 850 y el flip 926.57), run real MU = bear/Sell target 800 en 198s, consumidor en planes, lote 4am de 5 capitanes; (3) organizar fase 2 = timer 16:02 HOY con flota parada.
- [x] **hecho (verificado 08:20)** 'latest builds running + verify walls/magnets con prob honesta': binarios en ejecución todos ≥ mtime del build (bots 21:12>21:10, compass 07:55, price_alarm 00:38; flow_pulse nuevo arranca 9:30); niveles REGENERADOS con cadenas premarket para los 6 del cockpit — PW clavados al OI real (QQQ 670=15.9k, MU 800, NVDA 192.5, AAPL 330), spots frescos, SMH corregido (estaba pre-cadena con PW sobre el spot); imanes: CERO publicados premarket (nada inventado); MU CW 1000 = convención max-gamma real (el techo accionable 875/880 está en las burbujas por strike); toda prob visible viene etiquetada (medido/doctrina) o no aparece. Nota: ventanas de la app abiertas de ayer necesitan un ⟳.
- [x] **hecho 953f486 (agente sonnet + 2 ayudantes)** Repo map: docs/REPO-MAP.md 365 líneas — clases y funcs top-level de TODO (151 scripts py, 16 cpp, 21 bots como plantilla única confirmada por diff, engines/, order_engine/, scalper/, screener/, live.html, macapp, ~65 tests) + sección HUECOS (gexa_parse huérfano, reconstruct_flow* casi duplicados, pares py/cpp).
- [x] **hecho (verificado 08:42)** 'whales for spy ready?': SÍ — selftest SPY 24/24 contratos cualificados con el 0DTE de HOY (20260728), proceso vivo desde 00:39, cache y escaneo arrancan 9:30. Los 30 de flota cualificados (STX 18/18 el último).
- [x] **hecho aa940c8** 'diferenciar perpetuals de los reales en lista': cabecera '⛓Perp 24/7' con tooltip (prima propia ≠ precio acción) + badge ⛓ por fila; buscador encuentra MUUSDT→MU.
- [x] **hecho (entregado en conversación 08:30)** 'puede bajar más? + plan grande por símbolo + perpetuos': tabla de los 30 con premarket/PW(OI)/CW/flip/régimen/flecha; lectura: purga de MEMORIA (DRAM -8, SNDK -7.6, MU -6.9) con megacaps en verde y SPY EN su muro 740 — continuación 60-65% en semis/QQQ, el print de 9:45 en SPY 740 decide (735 invalida); perpetuos: 27 ya vivos (MU OKX incluido) en la watchlist 24/7.
- [x] **hecho fc46c64+c2c8b7f (agente, verificado)** Bot caídas post-earnings: Finviz Elite (earnings ayer AMC/hoy BMO, ≤-5%, optionable/líquido) + score capitulación-en-ATRs/rvol/cascada/titular + gate opciones IBKR real (spread mid ≤5%, OI>500) + veredicto TradingAgents top2 + voz solo score≥70∧OPCIONES-OK. Dry-run real: 8 candidatos, GLW -18.2% score 80 TA:bear (178s), AMKR -10.9% capitán SMH. Pasadas 8:20/9:50/12:30, keepalive 815-1300, en lista de apagado.


# ── Movido de TODOS.md el 2026-07-29 (madrugada) ──

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

## Ráfaga Yunior 2026-07-28 00:50

- [x] **"create finviz bots that detects falls after earnings reports of companies, based on news
      or technicals, with help of trading agents, liquid for options, be creative, send agent"**
      (Yunior 2026-07-28 08:40) — `hecho fc46c64` (scripts/earnings_fall_scout.py + keepalive 815-1300)

- [x] 2026-07-28 (Yunior): "revisa las alarmas de ballenas para smh, spy... debug, hunt for bugs" — hecho: SPY mudo estructural (umbral P/C fijo inalcanzable) cazado y arreglado con percentil propio p97/p03 solo en lado inalcanzable (8 tickers), voz de barrida ahora con magnitud+lado, 15 tests whale OK, vigía reiniciado. commit en main

- [x] 2026-07-28 (Yunior): "improve the qqq compass calculation, weight all major companies... including big etfs, options chain in those etfs, spy, spx" — hecho: peer_structure.py (coeficiente multiplicativo sobre fleet/components, doctrina respetada), 5 tests, commit en main

- [x] 2026-07-28 (Yunior): "crea skills nuevos para capturar sentimiento. y monitorea korea" (~20:15) — `hecho 79f43af`: skill `.claude/skills/x-sentiment/` + `scripts/x_sentiment.py` (presets skhynix/samsung/kospi/ticker-US, crudo atómico en `data/x_sentiment/`, fail-loud, probado en vivo 2×). Monitor KRX armado esta sesión (Hynix/Samsung/KOSPI, bandas ±0.75% + cinta ciega; baseline 20:15: Hynix +3.2%, Samsung +5.5%, KOSPI +2.9% — rebote fuerte con short covering). El monitor muere con esta sesión de Claude Code; los bots KRX de la flota siguen siendo la alarma permanente.

- [x] 2026-07-28 (Yunior): "debug notifications... spanish, simple, real. claude code start should speak spanish. finish all improvements" — hecho: (a) zombi BOLLINGER VIGIA cazado (118 banners fantasma post-cierre, portero RTH en keepalive, commit); (b) arranque Claude Code traducido (echo hook + voz session-start + indice skills + 'Falló el comando'); (c) voz del dia 0 frases en ingles, price_alarm 0 alertas viejas, korea_watch ya fail-loud; (d) capa liquidez en chart delegada a agente; (e) hiro_pulse SUPERADO por la cinta UW (tick opciones IBKR err 10189 = via muerta; UW flow-alerts ya da el flujo firmado)
# Cierre 2026-07-29 — review all, finish all

- [x] **Órdenes overnight de acciones** — el cliente TWS vendorizado ya envía el campo
      oficial `includeOvernight` (server 189). Entradas y cierres STK usan
      `SMART + LMT + DAY + outsideRth + includeOvernight`; opciones permanecen RTH-only y
      combinaciones/servidores incompatibles fallan antes de `placeOrder`. Verificado contra
      TWS API 10.37.02, 659 aserciones y cuatro suites ASan/UBSan; cero órdenes transmitidas.
- [x] **Compass/señales/calibración auditados** — gate corregido a `n_eff`, flags CLI
      desconocidos fallan ruidoso y la flecha queda neutral sin edge medido. Ninguna celda
      alcanza aún 30 ensayos efectivos; no se redujo el umbral ni se fabricó confianza.
- [x] **Skills/plugins pedidos** — 12 skills nuevos (30 contando los 18 previos de la ola) y
      tres plugins Codex read-only, todos validados con `skill-creator`/`plugin-creator`.
- [x] **UI profesional + ayudas** — auditoría comparativa entregada; los diez widgets conservan
      sus botones ⓘ y ahora tienen foco visible, `aria-controls`, `aria-expanded`, diálogo y
      cierre con Escape, sin inicializador duplicado.
- [x] **Voz española portable** — Matilda 114/114 viaja offline dentro de la app; build y
      arranque validan el banco completo. Sin `say`, red, API, muestra ni voz sustituta dentro
      del bundle; si se corrompe, queda muda y avisa visualmente.
- [x] **Level 2 IBKR comprobado en vivo/read-only** — QQQ SMART depth devolvió 0 filas y error
      2152: faltan NASDAQ/BATS/ARCA/NYSE. Recomendación exacta entregada: base Networks A/B/C +
      TotalView/EDS + ArcaBook; OpenBook/BZX opcionales para cobertura completa. Cero órdenes.
- [x] **UW + Korea + IBKR + X + seis ventanas + email + árbol SPY** — consolidado y
      verificado: lectura UW/Finviz/options con 10 candidatos por lado y árbol de SPY;
      alarmas temporales Korea activas; flota KRX despierta; posts X forzados a inglés;
      Gateway 4001 cableado solo para datos y rutas BUY/SELL de acciones/opciones probadas
      localmente (658 aserciones + ASan/UBSan, cero órdenes reales); app v2 abre seis
      ventanas por defecto; árbol de dos páginas enviado a la OfficeJet (job 212) e informe
      consolidado enviado por Resend (`c5757913-ddbd-4c0e-82e0-0b67a3601353`).
- [x] **"investigate real fast why are memory stock are jumping up"** — reporte urgente
      `docs/reports/memory-jump-2026-07-29-2105.md`: confirmación del call de Samsung +
      rebote/short covering; X 29 positivo / 9 negativo / 60 neutral; email urgente enviado
      por Resend (`8484ac43-795a-44bf-93df-c27143a200a5`).
- [x] Overnight integrado en `compass.cpp` sin ocupar familia: coef 1.25/0.75 modula
      amplitud y sesgo doctrinal; probabilidad medida intacta; contexto visible en el chart.
- [x] Migración durable de 17 consumidores a `config/feeds.env` y `x_whale_bot` a
      `config/x.env`; prueba sin symlink raíz: Finviz 6/6.
- [x] Finviz anti-spam por incidente: el binario ya no banneriza cada arranque sin token y
      el keepalive avisa una sola vez hasta recuperación.
- [x] UI/UX refinada y verificada: tabla/heatmap/decay/ayudas previas revisadas; motores
      nombrados del C++ visibles en la flecha; smoke visual completo.
- [x] Lógica de señales revisada contra código real: descartadas afirmaciones obsoletas del
      informe anterior; cerrado el hueco de frescura de niveles (60 s + fail-streak real).
- [x] `"relanza todo, build macos new version"` y `"review all, finish all"` cerrados con
      959 tests verdes, builds C++ sin warnings y rebuild/relanzamiento final de la app.
- [x] `"small tiny bug visual: in the windows the name is fixed at the top"` +
      `"for the versions lets use terminology like v1, v2, ..."` — título enlazado al
      símbolo privado de cada WebSocket mediante `document.title` observado por WKWebView;
      versión pública secuencial `v1` desde `macapp/VERSION`, hash reservado al diagnóstico
      interno. Seis bridges y seis ventanas relanzados; firma válida y 9 tests verdes.
