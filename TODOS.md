# TODOS — ib-trader

> Vivo. Apuntar cada petición AL MOMENTO con las palabras de Yunior. Lo cerrado → Done.md.

## 🔴 SESIÓN 2026-07-29 (madrugada, ráfaga ~07:05)
- [x] **"send codex to debug compass overnight, dont think its working"** (Yunior 2026-07-29
      ~06:00) — hecho (codex): causa raíz = `why[:5]` cortaba la línea overnight en QQQ +
      `except: pass` silencioso. Fix en `scripts/direction_view.py:274-290` (fail-loud +
      `why.insert(0, og_why)`); 15 tests verdes, verificado por Claude 2026-07-29.

## SESIÓN 2026-07-29 (noche ~23:50)
- [ ] "verify the software is running overnight, dont see the tickers bars charts moving" — verificado: flota VIVA, barras 1m fluyendo (QQQ/NVDA/KOSPI minuto a minuto). Hallazgo: `overnight_feed.py:korea_pct()` devuelve null desde ~23:46 porque los `bars_*.txt` coreanos solo guardan ~233 barras y ya no queda ninguna barra pre-20:00 como referencia de prev-close → decidir fix (ref=open de sesión, o que korea_bar_bridge persista prev_close). (2026-07-29, pendiente)
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
- [ ] 1. "use finviz picaro and tell me the best top 3 candidates for bullish and bearish today that have cheap leverage etfs" — pendiente
- [ ] 4. "send me today tree and forecast for the fleet based on options chain, futures, kospi, memory etfs... print only plan and tree forecast for spy" — pendiente
- [ ] 5. "schedule task to print spy again 5 min after market open, do the same for apple" — pendiente
- [ ] 9. "make sure we can trade via our software any etf, options, shares, i should be able to find them via search bar in dynamic way, not just the hardcoded ones" — pendiente
- [ ] 11. "after market print updated plan for glw, nbis, be as well plus tree forecast, same for microsoft" — pendiente
- [ ] 12. "send tree for aapl too, before market open and 5 min after open" (2026-07-30 09:02) — pendiente
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
      PENDIENTE: subir max_strikes del cache IBKR para que cruce BAND_FLOOR por si solo.
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
- [ ] "walls/magnets/gamma flip para MU desde el cierre vía Polygon+UW; qué baja el precio mañana para liquidez y si las barreras se van con el FOMO overnight" — EN CURSO (mapa gamma reconstruido de cierre 2026-07-30)
- [x] "email con plan actualizado..." — ENVIADO Resend id 4887d5b4 (2026-07-31)
- [ ] "Korea sentiment vía x.com; qué hace el gobierno para prevenir caída; Samsung report" — HECHO (agente): rebote récord +13-16% KOSPI, F4 manos vacías, Samsung beat HBM
- [ ] "probabilidades de que la acción caiga mañana en la apertura" — EN CURSO (calib medida = coin-flip en NEG gamma; honest)
- [ ] "analiza patrones head & shoulders" — HECHO: ningún H&S activo; NVDA+AAPL double_top bajista (WR bajo, contexto)
- [ ] "qué hace gobierno Korea para prevenir drop + Samsung report" — HECHO (arriba)
- [ ] "mirar TSLA, GOOGL, MSFT, AAPL, NVDA" — EN CURSO (agente noticias overnight)
- [ ] Yunior mid-turn: "Korea alcanzó picks; probabilidad estadística de pump al cierre sesión coreana viernes dado margin calls" — RESPONDIDO: pump ya ocurrió (bear-mkt rally), zona de agotamiento, no continuación durable

## 2026-07-31 ~00:20 ET — ráfaga Yunior (watch overnight + email refresh)
- [x] email refrescado overnight + cruces flip + forense AAPL/AMZN + opciones próx sem + Finviz — ENVIADO id 3eae77b8
- [x] watch 25 min ARMADO (ScheduleWakeup 1500s, SPEC + levels + conids + state); email solo trigger seguro; para 9:30
- [x] forense HECHO: AAPL=ya lleno (OI pre-cargado+50/50)=cayó por guía; AMZN=fresco(ask+dOI)=popó; regla VOI+OI+agresor
- [ ] "SPY ya en 744.92, dime con certeza" — responder con convicción honesta (overnight no dispara, print RTH manda)
- [ ] Yunior: patrón "~12:30 AM se bombea" — MEDIR con timestamps del watch, no afirmar; overnight pump US = AMZN/semis (catalizador nuevo), distinto del agotamiento KRX
- [ ] si dudas: TradingAgents (DeepSeek) + Finviz técnicos

## SESIÓN 2026-08-01 (~21:40 ET) — proveedores genéricos (gold folder market_intelligence_terminal)
- [ ] "save this: intrinio key / databento / Alpha Vantage" — HECHO: config/feeds.env (INTRINIO_API_KEY raw da8cad..., DATABENTO_API_KEY, ALPHAVANTAGE_KEY) (2026-08-01)
- [ ] "in downloads folder there is folder new, copy that to our proyect inside backup folder before start" — HECHO: backup/market_intelligence_terminal_gold_20260801 (era ~/Downloads/market_intelligence_terminal) (2026-08-01)
- [x] "el código lo escribió un senior/mastermind... mantener nuestro código GENÉRICO, conectar a distintos data providers independientemente; esta semana intrinio; IBKR se DESHABILITA para market data (temporal); indicadores + widgets nuevos; take all u can" (2026-08-01):
      HECHO núcleo — capa de proveedores genérica vendorizada en `mit/` (base/registry por CAPACIDAD: market/options/depth/flow, fallback aislado a mock) + `PolygonProvider` nuevo (opciones, griegas medidas) + intrinio.py reescrito a `/prices/intervals` (el viejo /intraday da 400). Puente TONTO `scripts/provider_bridge.py` (venv-mit py3.12) llena bars_<sym>_ibkr.txt + nbbo_<sym>.txt + opt_chain_<sym>.txt con el contrato EXACTO — validado: opt_quick.cpp lee la cadena (spot/PC/maxpain/muros), barras 6-campos crecientes min-alineadas, nbbo ask>bid>0. Toggle `data/market_source.txt` (ibkr|intrinio) en fleet_keepalive_start.sh + fleet_up.sh (bypass gateway si !=ibkr). Puesto a `intrinio`. Indicadores Pine copiados a charts/pine/. Tests: 3 contrato (suite flota) + 3 gold (venv-mit) verdes.
      PENDIENTE Yunior: (1) enganchar el feed REALTIME a la API key en dashboard Intrinio — hoy la key sirve `cboe_one_delayed` para equities aunque el plan sea FMV realtime $333 (medido, no finde); (2) medir latencia LUNES en sesión (sonda en provider_status.json last_exchange_ts). Widgets del oro (GEX-bar CSS, WebAudio) y router Bento/Trinity: follow-up (live.html ya superior; router gated por validación).
- [ ] "disable not main symbols like leveraged (DRAM/SPCX/SKHY/EWY) for the moment; commit+push tras review con 5+ agentes; asegurar todo GENÉRICO/dinámico, fácil cambiar data providers; releer market folder por si me perdí features; review review el commit push" (2026-08-01):
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
