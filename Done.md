# Done.md — ib-trader · archivo de lo CERRADO

> Aqui vive lo terminado, con su commit y su medicion (orden de Yunior 2026-07-27: "when todos
> done move them to Done.md"). **`TODOS.md` queda como unica fuente de lo que FALTA.**
> Nada se borra: si algo se reabre, vuelve a `TODOS.md` con el motivo escrito.

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
