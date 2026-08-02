# TODOS — ib-trader

> Vivo. Apuntar cada petición AL MOMENTO con las palabras de Yunior. Lo cerrado → Done.md.

## 🔴 SESIÓN 2026-07-29 (madrugada, ráfaga ~07:05)
- [x] **"send codex to debug compass overnight, dont think its working"** (Yunior 2026-07-29
      ~06:00) — hecho (codex): causa raíz = `why[:5]` cortaba la línea overnight en QQQ +
      `except: pass` silencioso. Fix en `scripts/direction_view.py:274-290` (fail-loud +
      `why.insert(0, og_why)`); 15 tests verdes, verificado por Claude 2026-07-29.

## SESIÓN 2026-07-29 (noche ~23:50)
- [x] "verify the software is running overnight, dont see the tickers bars charts moving" — verificado: flota VIVA, barras 1m fluyendo (QQQ/NVDA/KOSPI minuto a minuto). Hallazgo: `overnight_feed.py:korea_pct()` devuelve null desde ~23:46 porque los `bars_*.txt` coreanos solo guardan ~233 barras y ya no queda ninguna barra pre-20:00 como referencia de prev-close → decidir fix (ref=open de sesión, o que korea_bar_bridge persista prev_close). (2026-07-29, pendiente)
- [x] "analyza 5 candidatos en el option chain... top candidates para comprar puts mañana open; research + x.com api; probabilities order de caída" (2026-07-30 ~00:00, hecho — informe entregado en chat: ranking NBIS>BE>VRT>KLAC>IREN(avoid), X API search 401 no disponible con el bearer actual)
- [x] "investiga las ballenas que compran put con expiracion proxima, de preferencia mañana" (2026-07-30 ~00:20, hecho — UW /api/option-trades/flow-alerts + /api/stock/{sym}/flow-alerts, filtro ask_side_prem>bid_side_prem exp 2026-07-31: GLW y VRT con la compra más limpia/grande, SOFI nuevo candidato con catalizador real pero gamma POS, KLAC sin flujo en ese vencimiento)
- [x] "i tapped the cerrar button in nokia to close the position and no loading indicator plus why the position is not filled yet" (2026-07-30 07:47 -> CERRADO 08:26, v9):
      (a) ARM_LIVE contiene "2026-07-29" y hoy es 30 -> safety.h rechaza la llave -> close corrio DRY, JAMAS se envio orden. NOK 1 acc @ 8.37 (fill 23:56:41) SIGUE ABIERTA — VERIFICADO por reqPositions directo a TWS 4001: cuenta U26942420, qty=1.0, avgCost=8.4557, cero ordenes abiertas.
      (b) RACE en order_engine.cpp: reqPositions() (linea 621, cada 15s) pone known()=false y los comandos se evaluan en la MISMA iteracion (linea 719) sin pump() en medio -> decide_close_qty falla "posiciones NO reconciliadas". Fix: mover el refresco DESPUES del bloque de comandos, o pumpear hasta known() antes de decidir.
      (c) UI: el boton Cerrar no muestra pending ni surface el rechazo/DRY del motor -> Yunior no puede saber que no paso nada. Falta feedback.
- [x] "try the endpoint for options again, i think its enabled now for us options" -> IBKR MCP SI funciona ahora (get_option_parameters + get_option_data + get_price_snapshot con OI real). Polygon /v3/trades y /v3/quotes de opciones siguen 403 NOT_AUTHORIZED. (2026-07-30)
      RESUELTO: (a) race arreglado order_engine.cpp:497-502 (await_positions bombeo acotado 80 pumps/3s) + :729-741 (bombea antes de decide_close_qty) + reqPositions movido al FINAL del loop :1487; (b) safety.h:42-84 ArmStatus con motivo accionable, grita a stderr+ledger+notify_push (armed_live() intacto); (c) chart_bridge.py:1825 order_verdict() + :2981 /api/order_verdict, live.html:1930 boton en pendiente ANTES de la red, y cazado de paso el cero plausible "sin posiciones" con error de lectura -> ahora POSICIONES DESCONOCIDAS/RANCIO.
      Tests: 152 OK guards (eran 131) + 502 OK orders + ASan/UBSan limpio, SUITE VERDE. App v9 construida/firmada/relanzada, 6 bridges relanzados con la ruta nueva viva.
      NOK CERRADA: SELL 1 @ 8.90 (limite 8.87, mejor fill), realizedPnl +$0.3519, comision 0.0924. reqPositions confirma qty=0.0, cero ordenes abiertas.

## SESIÓN 2026-07-30 (08:41 ET, ráfaga)
- [~] CADUCADO 2026-08-02 (era "hoy" del 30-jul; lo repetible ya lo cubre com.ibtrader.screener) — 1. "use finviz picaro and tell me the best top 3 candidates for bullish and bearish today that have cheap leverage etfs"
- [~] CADUCADO 2026-08-02 (puntual del 30-jul; lo repetible = jobs de impresion L3) — 4. "send me today tree and forecast for the fleet based on options chain, futures, kospi, memory etfs... print only plan and tree forecast for spy"
- [x] 5. "schedule task to print spy again 5 min after market open, do the same for apple" — HECHO 2026-08-02: com.ibtrader.printopen5 (L-V 09:35) + scripts/print_open5_spy_aapl.sh + data/print_syms_open5.txt. 30 tests.
- [x] 9. "make sure we can trade via our software any etf, options, shares, i should be able to find them via search bar in dynamic way, not just the hardcoded ones" — HECHO (ver el detalle 4 lineas mas abajo: buscador dinamico verificado en vivo + 3 fallos arreglados)
- [x] 11. "after market print updated plan for glw, nbis, be as well plus tree forecast, same for microsoft" — HECHO 2026-08-02: com.ibtrader.printpostmarket (L-V 16:25) con --archive. El plan ahora SI es "actualizado": print_plans.sh recompone data/gex_snapshot.json tras archivar (estaba a 41,9 h; solo lo escribia dailyplans_run.sh:11 a las 04:00/08:30/09:12).
- [x] 12. "send tree for aapl too, before market open and 5 min after open" (2026-07-30 09:02) — HECHO 2026-08-02: com.ibtrader.printpremarket (L-V **09:20**, movido desde 09:12 porque colisionaba con el APERTURA de com.ibtrader.dailyplans sobre el MISMO daily_fleet_plans.py) + printopen5 a las 09:35.
- [x] "did u print via my printer hp? dont see it" (09:00) — NO se habia impreso: existia orden previa (2026-07-27) de no mandar a papel sin permiso. Creado `scripts/print_plans.sh <SYMS> --print` (generico, sustituye al hardcoded print_mon_plans.sh) + hoja de arboles HTML->PDF via Chrome headless. Impresos SPY, AAPL, NOK + ARBOLES.
- [x] "imprime plan para nokia too + plus tree" (09:04) — hecho, jobs 215/216.
- [x] 9. buscador dinamico — VERIFICADO en vivo + 3 fallos arreglados: (a) chart_bridge aceptaba
      simbolos inexistentes (qualifyContractsAsync NO lanza, devuelve lista vacia -> ZZZZZ/ZQXWV9
      en watchlist_user.txt); ahora mira el RESULTADO y avisa en la UI (watchlist_reject).
      (b) filas en blanco fuera de la flota -> nuevo scripts/watchlist_quotes.py (snapshots TWS
      -> watchlist_stats.json, ts por fila) + keepalive. (c) tree_sheets se centraba en el
      cierre previo de Polygon fuera de la flota (GLW 124.05 con 17h vs 130.81 real, cambiaba
      el call wall de 130 a 140): ahora usa live_spot(). Chart YA cargaba TQQQ/MSFU/MSFD/MUU/RAM/SOXS.
- [x] "urgent: print glw plan 3 min after open, tree chart included" -> "print now instead"
      (09:30) — cadena de GLW archivada (no estaba en el universo), plan + arbol impresos 217/218.
- [x] "make sure our software updates magnets, walls, gamma flip realtime, verify current screen data vs what its in ibkr chain" (2026-07-30 11:20)
      HALLAZGO: el chart recomputa cada 15s (LEVELS_REFRESH_S) al SPOT VIVO — pero SOBRE EL LIBRO
      DE LAS 08:45. com.ibtrader.polychains solo corria 08:45 y 16:20. Medido con QQQ a las 11:20:
      libro de 2h36min (spot congelado 672.73 vs 679.05 real), put wall 650 en pantalla vs 675 real,
      flip 668.43 vs 670.14, abs wall 670 vs 680, regimen VACIO, net GEX 619M vs 915M.
      Por que caia a Polygon teniendo cadena IBKR fresca (11:17, griegas 100%): strike_span_pct
      del 0DTE = 0.0979 contra BAND_FLOOR = 0.10. Falla por 0.21pp.
      FIX: com.ibtrader.polychains.intraday.plist — cada 30 min en RTH (portero fleet_hours).
      Verificado: tras refrescar, la pantalla paso a PW 675 / abs 680 / flip 670.14 / regimen POS.
      ~~PENDIENTE: subir max_strikes del cache IBKR~~ → HECHO 2026-08-02: los 4 NARROW (MSFT/META/
      AVGO/AMZN) ya cruzan BAND_FLOOR solos. Causa raiz DOBLE: opt_chain_cache.py los dejaba sin ola
      lejana, Y gex_core.from_ibkr_cache usa el campo `band` de la cabecera como FILTRO al leer, asi
      que ampliar declarando la banda del ATM habria sido INERTE. Cabecera nueva: band=exterior,
      band_atm, far_max_strikes, span_pct (docs/CHAIN-HEADER.md actualizado). 79 tests.
- [x] "solve those issues nowww" + "build new version when done" (2026-07-30 11:30)
      opt_chain_cache: el muestreo de la ola 2 (`rest[::stride]`) arrancaba en el minimo y el
      ultimo paso no llegaba al maximo -> la banda efectiva se quedaba corta. Sustituido por
      muestreo lineal que SIEMPRE incluye los dos bordes. MISMO numero de lineas TWS.
      QQQ 0DTE: 32 strikes 621->754 half-span 0.0979 (bajo BAND_FLOOR)
             -> 35 strikes 585->780 half-span 0.1437 (lo cruza con margen)
      chart_levels.gen ahora devuelve chain_src=ibkr_tws, edad 8s, griegas 100%.
      App v10 construida/firmada/relanzada (6 ventanas), 6 bridges 200, daemons vivos,
      1009 tests OK / 25 skipped.

## 2026-07-31 (madrugada) — petición ráfaga Yunior (plan viernes)
- [~] CADUCADO 2026-08-02 (era para la sesion del viernes 31-jul; el mapa se recalcula solo con com.ibtrader.polychains 08:45/16:20 + .intraday cada 30 min) — "walls/magnets/gamma flip para MU desde el cierre vía Polygon+UW; qué baja el precio mañana para liquidez y si las barreras se van con el FOMO overnight" — EN CURSO (mapa gamma reconstruido de cierre 2026-07-30)
- [x] "email con plan actualizado..." — ENVIADO Resend id 4887d5b4 (2026-07-31)
- [x] "Korea sentiment vía x.com; qué hace el gobierno para prevenir caída; Samsung report" — HECHO (agente): rebote récord +13-16% KOSPI, F4 manos vacías, Samsung beat HBM
- [~] CADUCADO 2026-08-02 (era la apertura del 31-jul, ya pasada; se respondio honesto: coin-flip medido en gamma NEG) — "probabilidades de que la acción caiga mañana en la apertura" — EN CURSO (calib medida = coin-flip en NEG gamma; honest)
- [x] "analiza patrones head & shoulders" — HECHO: ningún H&S activo; NVDA+AAPL double_top bajista (WR bajo, contexto)
- [x] "qué hace gobierno Korea para prevenir drop + Samsung report" — HECHO (arriba)
- [~] CADUCADO 2026-08-02 (barrido de noticias overnight puntual del 31-jul) — "mirar TSLA, GOOGL, MSFT, AAPL, NVDA"
- [x] Yunior mid-turn: "Korea alcanzó picks; probabilidad estadística de pump al cierre sesión coreana viernes dado margin calls" — RESPONDIDO: pump ya ocurrió (bear-mkt rally), zona de agotamiento, no continuación durable

## 2026-07-31 ~00:20 ET — ráfaga Yunior (watch overnight + email refresh)
- [x] email refrescado overnight + cruces flip + forense AAPL/AMZN + opciones próx sem + Finviz — ENVIADO id 3eae77b8
- [x] watch 25 min ARMADO (ScheduleWakeup 1500s, SPEC + levels + conids + state); email solo trigger seguro; para 9:30
- [x] forense HECHO: AAPL=ya lleno (OI pre-cargado+50/50)=cayó por guía; AMZN=fresco(ask+dOI)=popó; regla VOI+OI+agresor
- [~] CADUCADO 2026-08-02 (pregunta sobre un precio de aquella madrugada) — "SPY ya en 744.92, dime con certeza" — responder con convicción honesta (overnight no dispara, print RTH manda)
- [~] Yunior: patrón "~12:30 AM se bombea" — MEDIR con timestamps del watch, no afirmar; overnight pump US = AMZN/semis (catalizador nuevo), distinto del agotamiento KRX
      2026-08-02: ARNÉS LISTO, MUESTRA INSUFICIENTE. `overnight_pump_study.py --us` mide el retorno
      de los futuros NQ/ES (única fuente que cubre las 00:30 ET; poly_bars solo tiene 04:00-19:59)
      por franjas de 30 min de 20:00 a 04:00 ET, con Wilson y piso n=30 NOCHES. Ahora mismo:
      **DATA-INSUFFICIENT, 4 noches, faltan 26** → NO se afirma nada del patrón. Se acumula solo en
      data/history/overnight_ctx.jsonl. El modo KRX que hizo el agente medía el agotamiento coreano,
      que tú mismo marcaste como cosa DISTINTA. 5 tests.
- [~] NO ES TAREA: directriz de metodo, ya viva en dailyplans_run.sh (ta_view.py de los 5 capitanes a las 04:00) — "si dudas: TradingAgents (DeepSeek) + Finviz técnicos"

## SESIÓN 2026-08-01 (~21:40 ET) — proveedores genéricos (gold folder market_intelligence_terminal)
- [x] "save this: intrinio key / databento / Alpha Vantage" — HECHO: config/feeds.env (INTRINIO_API_KEY raw da8cad..., DATABENTO_API_KEY, ALPHAVANTAGE_KEY) (2026-08-01)
- [x] "in downloads folder there is folder new, copy that to our proyect inside backup folder before start" — HECHO: backup/market_intelligence_terminal_gold_20260801 (era ~/Downloads/market_intelligence_terminal) (2026-08-01)
- [x] "el código lo escribió un senior/mastermind... mantener nuestro código GENÉRICO, conectar a distintos data providers independientemente; esta semana intrinio; IBKR se DESHABILITA para market data (temporal); indicadores + widgets nuevos; take all u can" (2026-08-01):
      HECHO núcleo — capa de proveedores genérica vendorizada en `mit/` (base/registry por CAPACIDAD: market/options/depth/flow, fallback aislado a mock) + `PolygonProvider` nuevo (opciones, griegas medidas) + intrinio.py reescrito a `/prices/intervals` (el viejo /intraday da 400). Puente TONTO `scripts/provider_bridge.py` (venv-mit py3.12) llena bars_<sym>_ibkr.txt + nbbo_<sym>.txt + opt_chain_<sym>.txt con el contrato EXACTO — validado: opt_quick.cpp lee la cadena (spot/PC/maxpain/muros), barras 6-campos crecientes min-alineadas, nbbo ask>bid>0. Toggle `data/market_source.txt` (ibkr|intrinio) en fleet_keepalive_start.sh + fleet_up.sh (bypass gateway si !=ibkr). Puesto a `intrinio`. Indicadores Pine copiados a charts/pine/. Tests: 3 contrato (suite flota) + 3 gold (venv-mit) verdes.
      PENDIENTE Yunior: (1) enganchar el feed REALTIME a la API key en dashboard Intrinio — hoy la key sirve `cboe_one_delayed` para equities aunque el plan sea FMV realtime $333 (medido, no finde); (2) medir latencia LUNES en sesión (sonda en provider_status.json last_exchange_ts). Widgets del oro (GEX-bar CSS, WebAudio) y router Bento/Trinity: follow-up (live.html ya superior; router gated por validación).
- [x] "disable not main symbols like leveraged (DRAM/SPCX/SKHY/EWY) for the moment; commit+push tras review con 5+ agentes; asegurar todo GENÉRICO/dinámico, fácil cambiar data providers; releer market folder por si me perdí features; review review el commit push" (2026-08-01):
      HECHO: provider_syms.txt (26, sin DRAM/SPCX/SKHY/EWY). Review 6 agentes + arquitecto (systems-architect P0=0) aplicado:
      🔴 fuga de key en logs (scrub redacta api_key/apiKey); 🔴 guard anti-mock (ABORTA si resuelve a mock, escotilla IBT_ALLOW_MOCK solo tests); 🔴 ciclo de vida provider_bridge (pkill al revertir + en fleet_stop_bridges + mata opt_chain_cache en modo provider); 🟠 MANADA: fleet_consensus.py usa provider_syms.txt como universo si market_source!=ibkr (need 23/26, no muda); 🟠 nbbo epoch=tiempo real de bolsa (delayed falla-cerrado el gate 10s); 🟠 intrinio no fabrica bid/ask desde last; 🟠 Polygon bid/ask swap (p=bid,P=ask); cadena banded ±15%+2 exps; _spot_from_chain -1 (no fabrica); _parse_dt levanta (no now()).
      GENÉRICO/plugin (idea MVVM de Yunior): añadir proveedor = UN fichero auto-registrado @register("x") (base.PROVIDER_REGISTRY + registry auto-discovery pkgutil, orden determinista, log de fallos de import); config.ProviderName=str libre; feeds.env se vuelca a os.environ (proveedor nuevo lee sus keys sin tocar config). IBKR podrá ser uno más (disabled temp).
      Tests: suite flota 1023 passed/14 skip/0 fail; gold 3/3; contrato 3/3. Commit+push a main.
      FOLLOW-UPS del oro — ADOPTADOS (Yunior "finish all new features, i confirm" 2026-08-01):
      [x] scripts/reversal_router.py — motor Bento/Trinity/Router (state machine, live_htf sin repaint en numpy) SHADOW/UNVALIDATED: solo escribe data/reversal_<sym>.json, NO vota/ordena/habla (pendiente walk-forward); fail-loud INSUFFICIENT_DATA (no inventa). 6 tests.
      [x] scripts/shock_calibrator.py — shock diario cross-symbol + reversión empírica Wilson (historia diaria via provider), fail-loud None bajo piso; data/shock_snapshot.json; corre en venv-mit. 14 tests.
      [x] scripts/event_study.py — arnés first-touch/MFE>MAE/Wilson/by-year para GRADEAR señales antes de ir a live (encaja measured-probability). 22 tests.
      [x] Arquitecto: __capabilities__ upfront (rechaza capacidad sin instanciar), ProviderError estructurado, ProviderSet.close con timeout+gather, log de import. Gold suite 8 verde.
      PENDIENTE cablear (cuando pasen validación): reversal_router a cockpit/consenso; shock_snapshot a un lector/cron; usar event_study para gradear reversal_router antes de activarlo.
      Intrinio: key nueva (:020dae47) = MISMO acceso delayed (no es la key, es provisioning de cuenta). Email a success@intrinio.com redactado (pendiente que Yunior lo envíe).
      ⚠️ **NO ENVÍES ESE EMAIL (2026-08-02)**: su premisa ("no tenemos entitlement realtime") está
      REFUTADA — `/securities/replay?subsource=equities_edge` da 200 y el REST `source=equities_edge`
      también, o sea FMV EquitiesEdge SÍ está contratado; el socket cae porque Intrinio lo APAGA de
      noche (documentado por ellos). Si se escribe a soporte, solo quedan 2 preguntas útiles:
      (1) ¿cuál es la ventana horaria exacta (ET) en que el cluster de streaming está encendido, y
      enciende también sábados/domingos?; (2) ¿el feed EQUITIES_EDGE emite mensajes de QUOTE (NBBO)
      por socket, o solo trades como su fichero de replay?
- [x] "search intrinio api+github, create new skills, same for databento/otros" (2026-08-01) — HECHO: skills intrinio-api, databento-api, alphavantage-api, data-provider-layer (commit 41bae1fa).
- [x] "widget del market folder parecido a la imagen de X (heatmap GEX/VEX strike×expiry)" (2026-08-01) — HECHO commit 1fa35c2d: compute_option_matrix + /api/gex_heatmap/{symbol} + matriz CSS-grid divergente.
- [x] "run the software, ver el mapa de la semana + mapa de opciones futuro como el post X; e2e testing de las features nuevas y todos los cambios" (2026-08-01) — HECHO 2026-08-02 18:52:
      software CORRIENDO y capturado (data/e2e_shots/mit_terminal.png): mapa de opciones FUTURO =
      heatmap GEX strike x 4 vencimientos (2026-08-03/04/05/21), 152 strikes, 497 celdas, celda
      maxima 749@08-04 $341,2M; cabeceras vivas (regimen gamma POSITIVE/DAMPENING, book imbalance
      +20%, shock normal); panel TRACE con eje de tiempo y toggles GEX/NetOI/0DTE/5m/Key levels.
      E2E: `zsh scripts/e2e_smoke.sh` 7/7 PASS en --fast y 9/9 con suites, con el mercado CERRADO —
      cubre portero, contrato de ficheros del provider_bridge (ahora **26/26, faltan 0**; antes
      faltaban NFLX/GLD/XLK), opt_quick, reversal_router, shock_calibrator, terminal mit con
      screenshot verificado (magic PNG + IEND), y guarda anti-mock + 0 fugas de key.
## SESIÓN 2026-08-02 (~02:00 ET, domingo — mercado CERRADO)
- [x] "do research about issue previous with intrinio please. go in depth, dont stop till websockets
      is working, verify if the error is due to the market not open yet, full research" (2026-08-02
      02:01) — DIAGNÓSTICO TÉCNICO CERRADO, causa de negocio al 70%. **Probablemente sí es porque el
      mercado está cerrado**: `-csharp-sdk/README.md:500` "…when the markets are closed and **the
      websocket servers are off for the night**" + how-to oficial "Testing the code during market
      hours" + existe un ReplayClient "for when the servers are down". (El "servers turn on every
      morning" de java/go/options-python es **boilerplate copiado = UNA fuente, no cuatro**, y la doc
      NUNCA menciona fin de semana ni una hora concreta.) `/auth` comparte host y app Phoenix con el
      socket → apagar el streaming lo tumba (cierre a 5 s = request_timeout de Cowboy).
      **Queda viva la hipótesis de OUTAGE (17%)**: status.intrinio.com NO tiene componente de
      streaming (punto ciego) y 48/50 incidentes se publican 09:00-17:36 ET entre semana.
      LO DECIDE LA SONDA EL LUNES: si sube en premarket → horario; si sigue caído en RTH → soporte.
      REFUTADAS por medición las 3 hipótesis previas: (1) IP datacenter — check-host.net **20 nodos
      en 4 continentes fallan los 20**, control api-v2 OK en los 20; (2) entitlement — `cboe-one` y
      `realtime-delayed-sip` (delayed que SÍ tenemos) fallan idéntico, y daría 403 con cuerpo;
      (3) outage — status.intrinio.com All Systems Operational. Controles: Polygon y Finnhub SÍ
      aceptan su WS el mismo domingo (vivos, silenciosos).
      ENTREGADO: `scripts/intrinio_ws_probe.py` + job `com.ibtrader.intrinioprobe` (cada 10 min, SIN
      portero horario) → `data/intrinio_ws_probe.jsonl` etiquetado por fase de sesión, avisa por
      notify_push y levanta `data/INTRINIO_WS_UP` en cuanto un host dé token (15 tests).
      `mit/backend/app/providers/intrinio_realtime.py` (@register `intrinio_realtime`, 10 tests):
      fail-loud si el socket no está, epoch de BOLSA en ns (no hora de llegada), lado rancio no se
      mezcla, jamás fabrica bid/ask.
      VALIDADO E2E CON EL MERCADO CERRADO vía replay del propio vendor:
      `GET /securities/replay?subsource=equities_edge&date=2026-07-31` → 200 (S3, 3,25 GB) leído
      **por rangos HTTP** → **216.265 ticks, 0 fallos de parseo**, ventana de bolsa correcta,
      get_quote levanta con el tick del viernes y da last=745.69 SPY con reloj fresco.
      ⚠️ PENDIENTE LUNES: el replay de EQUITIES_EDGE trae **solo trades, 0 quotes** → confirmar si el
      socket vivo emite NBBO; si no, no hay bid/ask de Intrinio y el gate de spread se queda ciego.
      Y medir la ventana horaria exacta de encendido (no está documentada).
- [ ] "do all todos and remaining work, no excuses. investigate in github, web, reddit, stackoverflow,
      etc" (2026-08-02 03:45) — EN CURSO: los 40 problemas de las revisiones + investigacion externa.
- [ ] "solve and investigate all not solved bugs or issues" (2026-08-02 03:40) — EN CURSO: barrido
      de TODOS los problemas medio/bajo que las revisiones adversariales dejaron sin arreglar +
      caza de bugs nueva (skill bug-hunter) con agentes frescos.

### ✅ BUG CERRADO 2026-08-02 19:00 — muros del TRACE fuera de toda banda operativa
`compute_trace_matrix` acota la MATRIZ a ±`MATRIX_BAND` del spot
(`options_positioning.py:288-291`) pero los NIVELES los toma de
`analyze_dealer_positioning(symbol, spot, chain)` con la cadena **COMPLETA sin acotar** (`:302`).
`analyze_dealer_positioning:129-130` hace `max(call_oi)` / `max(put_oi)` sobre TODOS los strikes.
REPRODUCIDO con SPY spot 744,27 y los 4 vencimientos fusionados:
  put_wall = **360,0** (OI 26.722 en UN contrato, un tail hedge lejano) = **−51,6% del spot**
  frente al 710 (OI 21.658, −4,6%) que es el muro operativo de verdad.
Se dibuja en el panel como "Put wall — support". Un soporte a −52% no es un soporte: contradice la
doctrina de muros de la casa (`oi-magnets-protocol`: el muro es un campo de fuerza que se TOCA).
INVESTIGACIÓN EXTERNA (2026-08-02, support.spotgamma.com): el vendor de referencia define
**Call Wall = strike donde la GAMMA NETA de calls es máxima** y **Put Wall = strike donde la gamma
neta de puts es máxima**, y además toma "el call wall más alto POR ENCIMA del precio y el put wall
más grande POR DEBAJO". Nosotros los calculamos por **max Open Interest** y **sin lado ni banda**
(`analyze_dealer_positioning:129-130`) — dos diferencias, y ambas empujan al strike lejano.
Nuestro propio `scripts/gex_core.py` (la flota) ya los calcula por gamma; es `mit/` quien se separó.
HECHO: nuevo `_walls()` en `options_positioning.py` — call wall solo por ENCIMA del spot, put wall
solo por DEBAJO, ambos dentro de `WALL_BAND` (= `MATRIX_BAND`, la misma ventana que el mapa), y por
GAMMA medida cuando la hay, cayendo a OI solo si falta y ETIQUETANDO la fuente en los `caveats`
(`source=gamma|mixto_gamma_oi|oi`). Si ningún strike cae en banda devuelve **None**, jamás el strike
lejano. VERIFICADO con datos reales de Polygon (SPY spot 744,27, 4 vencimientos):
  antes → call_wall 775 / **put_wall 360 (−51,6%)**
  ahora → call_wall **749 (+0,6%)** / put_wall **733 (−1,5%)**, source=gamma
E2E con el terminal levantado: `call_wall=749.0 put_wall=733.0 flip=729.48 max_pain=725.0`.
6 tests nuevos (`mit/backend/tests/test_walls_band.py`), suite mit 51 verdes. PENDIENTE: `options_positioning.py` lo tiene
tomado el lote A del barrido; se aplica en cuanto lo libere.

### ⚠️ CORRECCIÓN 2026-08-02 03:55 — el veredicto de reversal_router NO era robusto
Lo reporté como "sale moneda al aire (WR 0,497)". **Esa certeza estaba mal fundada** y la retiro:
- La barrera del gradador era ±1×ATR14 de barras de **1 MINUTO**. Medido por mí sobre poly_bars:
  QQQ 0,045% del precio, SPY 0,027%, NVDA 0,084%. Eso **no cubre ni el spread**: mide si el precio
  hace un tick a favor antes que en contra = MICROESTRUCTURA, no la tesis de un router que mezcla
  5m/15m/30m/1h/4h/1D.
- El WR resultó INVARIANTE al horizonte (0,506 a 30/120/390/780 barras) porque lo que ata es la
  BARRERA, no el horizonte — señal de que se estaba midiendo ruido.
- Con la barrera escalada al timeframe real del router, **el MISMO código cambia de veredicto**:
  390×4ATR → 0,512 [0,501-0,522]; 390×10 → 0,514 [0,500-0,527]; 780×20 → 0,526 [0,509-0,542],
  que por la propia regla del script (wilson_lo > 0,50) sería PASS.
- Honestidad simétrica: ese PASS es sobre 4 de 30 símbolos, sin corrección por correlación ni null de
  entrada aleatoria. **NO afirmo que el router tenga edge.** Afirmo que el FAIL no está establecido.
→ EN CURSO: sustituir el punto único por un BARRIDO paramétrico con Wilson por celda y veredicto
  "SENSIBLE AL PARÁMETRO — no concluyente" si depende del parámetro. `wired:false` se mantiene.

### Hallazgos del arnés E2E (lote L6) — arreglados por el orquestador 2026-08-02 03:30
- [x] **Niveles del terminal NO deterministas** (era el peor: son números que disparan órdenes).
      `_multi_expiry_chain` usaba `return_exceptions=True` y **descartaba en silencio** los
      vencimientos que fallaban → el mapa se calculaba sobre la cadena que sobrevivía. Medido con
      SPY al MISMO spot 744.27: una corrida daba call_wall 775 / flip 729.98 (4 exps) y la siguiente
      call_wall 700 / flip 647.68 (3 exps). Ahora: reintenta los caídos; si la cobertura queda por
      debajo de la mitad LEVANTA (lo declara `_with_fallback`, connected=False) en vez de servir un
      mapa parcial con la misma pinta que el bueno; si sobrevive con huecos, ERROR en el log diciendo
      que los muros NO son comparables entre refrescos. 5 tests.
- [x] **NFLX, GLD y XLK sin cadena de opciones** (3 de los 26 símbolos, mudos en el mapa). NO era
      del vendor: Polygon los servía. `provider_bridge` no reintentaba, así que **un solo ReadTimeout
      dejaba al símbolo sin mapa toda la sesión**. Ahora reintenta 1 vez y, si falla de verdad, grita
      "SIN MAPA DE OPCIONES" en vez de dejar un hueco callado. Verificado en vivo: los 3 escritos
      (NFLX 329 / GLD 315 / XLK 184 líneas) y leídos por `opt_quick` con spot correcto contra el
      cierre del viernes (NFLX 71.70, GLD 371.10, XLK 174.89). 3 tests.
- [ ] PENDIENTE LUNES (no verificable con el mercado cerrado): frescura real de barras/nbbo, latencia
      de Intrinio en vivo, y que `reversal_router` salga de INSUFFICIENT_DATA (necesita ~15 sesiones
      RTH; hoy SPY tiene 156 barras 5m de las 260 que pide). Correr `zsh scripts/e2e_smoke.sh` tras
      la apertura: los mismos 9 pasos sirven de sonda viva.

- [x] "solve all todos, new features too with fresh agents" (2026-08-02 02:05) — HECHO: triaje +
      6 lotes con agentes frescos (ficheros disjuntos) + revisión adversarial de cada uno.
      18 peticiones CADUCADAS con motivo (puntuales de sesiones pasadas o ya hechas sin marcar);
      6 lotes de trabajo real cerrados: L1 korea_pct, L2 BAND_FLOOR, L3 impresiones automatizadas,
      L4 gradación de reversal_router (FAIL medido, wired:false), L5 TRACE con eje de tiempo real,
      L6 arnés E2E (9/9 PASS con mercado cerrado).
      Las revisiones cazaron 3 fallos graves que arreglé yo: colisión de las 09:12 entre
      printpremarket y el APERTURA de dailyplans; el plan "actualizado" de las 16:25 dibujando un
      gex_snapshot de 41,9 h; y un data/history/<domingo> de una corrida en seco que habría
      desplazado al viernes real en skew.py (--archive ahora EXIGE --market-day).
      NOTA: la revisión adversarial de L6 no llegó a correr (límite de sesión del agente); lo
      verifiqué yo a mano ejecutando el arnés. De 25 pendientes quedan 3.
      TODOS.md pasó de 25 a 3 pendientes. Suite 1023 -> 1213 tests.

- [ ] "check dre image (desktop, SpotGamma TRACE); net OI mostrar movimiento realtime con WICKS (velas sobre el mapa); copiar las mejores features de SpotGamma si no las tenemos" (2026-08-01) — PENDIENTE tras widget #1. Features a copiar: (a) Net OI by Strike (barras call+/put-), (b) heatmap TIEMPO×STRIKE Delta-Pressure/GEX divergente, (c) VELAS con wicks superpuestas en eje precio (bars 1m), (d) líneas Call/Put/Hedge Wall + Gamma Flip + Implied move + Last Close (gex_core), (e) scrubber de tiempo. Dos mapas: strike×expiry (post X) + strike×hora+velas+HIRO (TRACE). drew.png=modo GEX, dre.png=modo NetOI/DeltaPressure: MISMO widget con toggle de métrica. refs en backup/spotgamma_trace_*.png
