# TODOS — ib-trader

> Vivo. Apuntar cada petición AL MOMENTO con las palabras de Yunior. Lo cerrado → Done.md.

- [ ] 43. "add news for all fleet in discord, but make sure they dont get repeated, no need to
      store them more than 24 h, debug, fix, improve" (2026-08-05 13:25) — pendiente
- [ ] 44. "debug channels in discord, make sure we are using them properly and all integrated"
      (2026-08-05 13:25) — pendiente
- [ ] 45. "be more strict for BB alerts, go rsi 80/20, filter out noise" (2026-08-05 13:25) —
      pendiente
- [ ] 46. "try alpaca for news too, do tests on providers to see the best ones" (2026-08-05 13:45)
      — adaptador `src_alpaca()` escrito (1 sola petición para los 30, Benzinga tiempo real).
      BLOQUEADO: Alpaca se purgó del repo el 2026-07-15 ("no alpaca all over") y no queda ninguna
      clave; el endpoint da 401 sin credencial. Hace falta que Yunior pegue en config/feeds.env:
      `ALPACA_API_KEY_ID=` y `ALPACA_API_SECRET_KEY=` (sirven las de cuenta paper, gratis) y el
      barrido comparativo lo incluye solo.
- [ ] 39. DATO PERDIDO: `data/trading-signals/2026-08-03.txt` esta truncado (2,6 KB vs 122 KB
      del 08-04) — el dia se regenero/corto. El test ya no clava esa fecha (usa el dia completo
      mas reciente), pero el backtest de ese dia NO es reproducible. Investigar quien lo trunco
      antes de fiarse de metricas historicas del 08-03. (2026-08-05)
- [x] 40. "still dont see the 2 new indicators, take a look at my safari" (2026-08-05) — HECHO:
      (a) CAUSA RAIZ del whale detector muerto: Intrinio cboe_one_delayed manda volume=0 SIEMPRE
      en acciones pero SI manda trade_count (539/463/455 por minuto medido) -> proxy DECLARADO en
      provider_status.volume_source. La flota llevaba TODA la semana con volumen 0 (afectaba VWAP,
      perfil de volumen y el detector). 0 -> 53 marcadores; calibrado a 20/3.5 (13% de velas -> 4%).
      (b) Target Trend estaba renderizando pero invisible bajo el ribbon de 18 EMAs: lineas 0.45
      dashed -> 0.85 solidas y niveles con etiqueta EN EL EJE (TT T3/T2/✔T1/◉entry/TT stop), como
      el original de TradingView. Verificado con captura del cockpit.
- [ ] 41. BUG (preexistente, hallado 2026-08-05): `tests/test_chart_bridge_liq.py::test_liq_map_reads_polygon_archive_and_fresh_live_cache` falla — el mapa de liquidez
      devuelve cols=["0936"] y NO incluye la columna del cache VIVO (mtime 10:00). O el mapa
      ignora el dato vivo (bug de camino vivo, malo en RTH) o el test es fragil. Verificar cual.
- [x] 42. "finviz message wrong: buy sell watch instead of just one" + "UW notifications should
      say bearish or bullish" + "keep it simple" (2026-08-05) — HECHO y VERIFICADO EN VIVO:
      finviz "· NUEVOS · BUY 2 SELL 0 WATCH 0 | URGN BUY $43.94 ... score 7/7" -> "· BUY | ATKR
      $93.61 +0.1% RVOL 12.5x" (sin recuento, sin score, sin NUEVOS; "(giro)" solo si cambia de
      opinion; lado por fila solo si la tanda es mixta). OJO: la 1a vez fallo porque edite el .cpp
      y NO recompile — el binario es lo que corre.
      UW: "CALLS ask-side ... premium 1.0M ask-side" -> "UW FLOW NVDA 🟢 BULLISH | CALLS compradas
      220 exp 08-05 · vol/OI 8.3 $252k". Doctrina aplicada: vender put = BULLISH, vender call =
      BEARISH; al mid NO se afirma direccion. Enrutado a #flujo-uw verificado con los 5 casos.
## 🔴 SESIÓN 2026-08-04 (martes — ráfaga Discord + UW flows + backtest de alertas)
- [x] 29. "for displaying in chart priority goes to realtime data, old data is not priority for display, we can keep up to 24h top, no need for more on chart, it will make them heavier. we can still store locally data for backtesting" (2026-08-04 ~15:15) — HECHO commit 50f4db93 (bars_*.txt tope display 24h: warmup 1440 + poda al doblar; backtest sigue en poly_bars/history)
- [x] 30. "review spcx in depth, seeing some alerts now for high volume, also check x.com sentiment, something big is coming, musk says that things will be big, lets see" (2026-08-04 ~15:20) — HECHO en sesión: 941k contratos, IV 232%, dos colas, 330C OI 547k; Musk "Few understand"; Kalshi 92% data-center; Polymarket 34% beat
- [x] 31. "analyze taiwan and japanese markets and chinese cxmt semis, create new channels, analyze meta and msft too" (2026-08-04 ~15:48) — HECHO: canales #taiwan-japon/#china-semis + webhooks + RULES; asia_semis_watch.py launchd 30min con titulares CXMT entregados; docs/ASIA-SEMIS-2026-08-04.md; META caja 580-600 (flip corregido con puts), MSFT drift 485-500
- [x] 32. BUG relay (agente Asia): notify_relay.sh:56 registra dedup ANTES del cap 1/5s — mensaje capado no puede reenviarse en 60s y se pierde en silencio. Mover dedup a después del envío OK. — HECHO: dedup movido a después del cap en notify_relay.sh (~:75) Y en discord_relay.py:197 (mismo bug heredado); reproducido EN VIVO hoy 17:23:19 (🇹🇼 NOTICIA SEMIS capada y perdida en ambos relés); 3 tests e2e nuevos con arnés zsh+curl-stub (tests/test_notify_relay.py); relés relanzados y push de prueba ENVIADA #bot-logs 17:27:47
- [x] 33. "review amd and spcx reports, amd is falling like knife, how down can it go?" (2026-08-04 ~16:2x AH) — HECHO: escalera 470-468/450 (put-wall 9.9k)/440-430/424-428 (low 7/28 + precedente -18.7%); 40% gamma muere viernes; SPCX -8.2% mapa 110→100 lockup jueves; MU 884 sobre el 883 darkpool
- [x] 34. "post amd plan and spcx plan on x.com, in depth, two posts" (2026-08-04 ~16:4x) — HECHO 16:31: 2 posts con imagen-plan (ids 2084738925885530490 AMD / 2084738929979257014 SPCX), ledger 17/30, inglés+disclaimer
- [x] 35. "send agents solve bugs/todos; net premium like Quant Data; agents debug; backtest failed signals; surprise" (2026-08-04 ~17:0x) — HECHO: agente bugs cerró 32/20/29/9 (f2274eab, dedup en AMBOS relés + privacidad config/notify_private.txt; TODO 5 token bloqueado en Yunior); widget NET PREMIUM estilo QuantData en Cockpit v12 (pane 4: verde cum_call/rojo cum_put/blanco neto, update en vivo via ws, verificado renderizado; la 3ª línea de QuantData es el PRECIO=ya en pane 0); SORPRESA: detector 🔀 DIVERGENCIA FLUJO-PRECIO 30m en uw_net_prem (flujo fuerte contra precio = acumulación oculta, banner sin voz, cooldown 30min); agentes auditoría + anti-ruido aún corriendo (informarán)
- [x] 36. "add charm and tools for nice analysis like this... create skills for it, save to memo" (2026-08-05) — HECHO: scripts/whale_forensics.py (per-strike UW + ΔOI overnight + gamma/charm por expiry; reproduce el caso MSFT y reveló rotación 500C→530C), skill whale-forensics, memoria whale-forensics-method
- [x] 37. "add Target Trend [BigBeluga] + Big Trades Whale Detector [HK] to chart, a bit transparent" (2026-08-05) — HECHO: port en chart_bridge (target_trend: SMA10±ATR200*0.8, flips, entry/stop/T1-3 con ✔; whale_vol_markers: anomalias σ intrabar 3 tamaños) + front translucido (lineas 0.45, circulos 0.35, price-lines dashed); verificado en vivo premarket; whale espera volumen (feed Intrinio vol=0 esta semana, activa solo con IBKR)
- [x] 38. "create new skills for what u learned today, save to memo, commit, push" (2026-08-05) — HECHO: skills realtime-freshness-debug (3 patrones de bug del 8/4) + event-premium-discipline (ratio max 0,49 medido) en ~/.claude/skills; memoria session-2026-08-04-lessons + índice; whale-forensics ya creada antes
- [x] 28. "review again with fresh data. 2. backtest todays signals so far, specially finviz, send fresh agent for it. 3. review with strength micron, tell me positives or bad scenarios if amd or wdc go bad today after earnings" (2026-08-04 ~14:1x) — HECHO: docs/BACKTEST-SIGNALS-2026-08-04.md (finviz_scout 401 todo el dia -> causa: keepalive del domingo con token pre-rotacion en env, matado y relanzado; bb-fade-sup 17W/44L; today_alarm5 vetos acertaron; PLTR/AAOI no cazados por diseño momentum-solo-nuevos); refresh+MU entregados en sesion; BONUS: fix paginacion Polygon (cadenas sin puts toda la semana)
- [x] 27. "analyze walls too, how explosive it could go tomorrow or next week, but tomorrow is the day, it does caput, specially korean at night, might they sell or buy? analyze sentiment in social media. us UW api" (2026-08-04 ~13:05) — HECHO: Corea MIXTO sesgo compran condicionado a AMD 16:05; explosividad medida (MU 51% gamma muere 8/5, SNDK EM ±19,5%)
- [x] 26. "dime para la semana que viene, y esta tambien, con studio de ballenas. give me top 5 bullish and top 5 bearish based on evidence from this week and next one. weather from fleet or finviz with high volume, do fresh research. take a look at gamma, gamma flip. think about doing some sort of strangle. take a look at spcx too, tsla. give me the best strangle with low risk high reward and based on catalysts, tomorrow is the day, we can also choose next tuesday, within 200 usd budget" (2026-08-04 ~12:50) — HECHO: 4 docs (WHALES-NEXTWEEK, CATALYSTS-2W, STRANGLE-SCAN, KOREA-SENTIMENT) + sintesis en sesion; hallazgo gordo: SPCX=SpaceX common (memoria nueva); strangle veredicto NO-TRADE medido (ratio max 0,49), boleto NOK $29 unica alternativa
- [x] 23. "analyze UW, polygon, and others and tell me about the fleet net premiums for week and per day expiration this week, find me the most bullish and bearish tickers either from the fleet or high volume for options from finviz" (2026-08-04 12:32) — HECHO por agente — docs/NET-PREMIUMS-2026-08-04.md (41 req UW)
- [x] 24. "bugs in ib trader, not updating realtime properly, real crazy, debug" (2026-08-04 12:32) — causa hallada y arreglada: cadenas Polygon en serie con barras/nbbo secuestraban el bucle vivo (cada símbolo cada ~4 min); chain_loop separado en provider_bridge.py, daemon relanzado; MEDIDO tras fix: barra 1m a ~30-50 s de cerrar, manada operativa 26/26 (commit ef90f3da). Pendiente aparte: uw_flow_tape muerto desde ayer, el token UW nuevo da 401 en flow-alerts (entitlement, decision de Yunior)
- [x] 25. "build new version and make sure new version have the v11 ... or higher text in window" (2026-08-04 ~12:40) — HECHO: VERSION 10→11, rebuild+firma+relanzo, 6 ventanas verificadas con "v11" en el título
- [x] 20. "dont reveal personal info on our personal trades via notifications, only via local
      notification in mac with editeur de script as always" (2026-08-04 ~11:30) — HECHO: títulos
      personales identificados en el embudo real (🚨 order_engine ×4, ⏰ EXPIRA HOY; +FILL/
      realizedPnl/POSICION/U########/comisión/ARM_LIVE/CERRAR de position_close_reminder y
      order_engine); patrones movidos a `config/notify_private.txt` (fuente única, sin hardcode)
      leído por notify_relay.sh y discord_layout.is_private() con respaldo embebido si falta el
      fichero; el banner local osascript lo dispara el propio emisor (position_close_reminder.py:28,
      patrón de la casa) y los 2 relés externos saltan (verificado en vivo 17:28:00: "PRIVADA
      (solo local)" en ambos logs, cero curl); 6 tests (tests/test_notify_relay.py)
- [x] 21. "use osacript here vs3d.volsignals.com... take screenshots, read them, change
      selectors to gamma as well, then tell me whether is going up or down" — HECHO 11:51 via
      SAFARI (la sesion vivia ahi; CDP/Chrome daba login wall). osascript abrio la pestaña,
      `do JavaScript` cambio el dropdown custom Delta→Gamma (button.dropdown + MouseEvent),
      screencapture + lectura propia. VEREDICTO publicado en #posicionamiento-dealer: SPX
      sentado EXACTO en el flip (~7710-15), estanteria 0DTE -9k/-6k en 7715/7725, suelo +6k en
      7690 (=borde de la valla), straddle subiendo. SUBE pero contra techo: print de 7715-16 =
      acelera (gamma negativa) a 7725/7735; rechazo = caja 7690-7710. Picadora hasta 14:00.
- [x] 22. "activate alert to buy and sell in options, post them to discord channel, also post
      lottos with high confidence for the best ones in fleet based on gamma, net options,
      whales for tomorrow and whole week till friday" — HECHO. Fichas buy/sell YA activas y
      verificadas (GO call y GO put enrutan a #opciones-contratos; today_alarm5 con candado y
      solo-GO). LOTTOS publicados en #opciones-contratos (docs/LOTTOS-SEMANA-2026-08-04.md):
      solo 2 pasaron TODOS los gates — AAPL 307.5c 8/5 @$165 (spr 2,5%, OI 5.608, imán 310,
      net +$4,3M) y AMZN 275p 8/5 @$157 (spr 1,3%, OI 2.842, put-wall 275, net −$17M).
      Viernes: CERO legales (AAPL 310c falla prima por $8; NOK 10c spread 7,4%). Las 4
      confluencias 3/3 plenas (MU→900 +$95,8M, MSFT→500, INTC→100, SMH→580) NO caben en $200
      — publicadas como info. Vetos que más mataron: prima, PIN (QQQ/SPY/NVDA pegados al
      muro), earnings (AMD hoy AH, SNDK/WDC 8/5). Cuota: 35 requests.
- [x] 19. "make sure we have signals working properly. 2. bug: con cuidado call the nvda is
      bad, it repeats 3 times plus its a bad signal" (2026-08-04 ~11:2x) — HECHO. Causas
      MEDIDAS del bug: (a) 4 niveles de NVDA cruzaron en el MISMO poll -> 4 fichas con la misma
      voz en el mismo segundo (11:24:56 x4 en el embudo); (b) multiples instancias de
      today_alarm5 (5 lineas "armado" en el log: cron 09:31 + arranques manuales sin candado);
      (c) un CAUTION "sale muy caro" hablando no es señal. Arreglos en today_alarm5: candado
      de instancia unica (flock, verificado: el doble arranque rebota), SOLO GO habla/pushea
      (CAUTION/NO-GO se registran en FIRED_LOG con motivo y callan), cooldown 30 min por
      (sym,kind). Señales verificadas por SALIDA: embudo/relay/uw_fleet_flow/cboe_nbbo/levels/
      gex/vix todo 0-5 min de edad, relay entregando en #flujo-uw en <2 s.
- [x] 18. "busca cuchillos con trading agents, maybe stocks with high put/call ratio, search
      options chain, UW net, 0dte for today. 2. search high call/put ratio for this week till
      friday, calculate net premium from today tuesday 10:35 till friday, search whales,
      darkpool, ... sentiment." (2026-08-04 10:35) — HECHO por 2 agentes, ambos publicados en
      #estrategias + docs. (1) `docs/CUCHILLOS-0DTE-2026-08-04.md`: CAT y VST cuchillos REALES
      pero VETADOS por regla 4 (spreads 11-62% / 15-18% + earnings VST 8/7); SPX con hedge
      masivo (net_call -171,7M) pero SPY en maximos = sin print; embudo en SILENCIO a proposito.
      ⚠️ TradingAgents SIN OPINAR: DeepSeek 402 Insufficient Balance — RECARGAR SALDO (accion
      Yunior). (2) `docs/SEMANA-VIERNES-2026-08-04.md`: NOK el unico que pasa TODO (C/P 9,4,
      10C 8/7 spread 3,9%, OI 14k, cabe en $200); GRAB/BBAI C/P altisimos pero opciones VETADAS
      -> acciones; bajista CVX 190P $205k la ballena mayor <=viernes; VIXW vendiendo calls VIX
      (apuesta a calma); WBD C/P 0,05 pero puts VENDIDAS (+514k, el ratio miente). Dark pool y
      headlines DESCRIPTIVOS rotulados (killlist #3). Cupo UW total dia: 12.457/30.000.
      ADENDA 10:57 ("si no hay deepseek then use your own analysis"): veredictos PROPIOS con
      dato fresco (UW ohlc/1m + BB(20,2) + net-prem-ticks 10 min) publicados en #estrategias:
      CAT cuchillo MUERTO (reboto +8 del low, flujo +827k comprador — regla 11); VST cuchillo
      VIVO sin vehiculo (band-walk 15m + flujo -264k, pero spreads 15-18% + earnings 8/7 —
      se mira, no se paga); NOK CONFIRMA y acelera (+363k en 10 min, %B 0,78/0,31 girando sin
      extension) -> vigilancia armada en el embudo: print de 10,13 dos lecturas = 10C 8/7.
- [x] 17. "find me best tickers with high liquidity for options that might go down like a
      kniefe today starting now" (2026-08-04 10:11) — RESPONDIDO 10:15 en chat + #estrategias +
      embudo. Medido (Finviz losers opcionables + puts ATM CBOE + flujo UW): los cuchillos
      grandes tienen opciones IMPAGABLES (BRKR -17,6% spread 188% · APTV 22% · NRG 18,8% ·
      HUT 53%) — regla 4 los VETA todos. CIFR -12,6% el unico casi-operable (7,9%, OI 780)
      pero reboto +4,3% desde apertura: solo retest-rechazo impreso. AMZN reboto EXACTO en su
      put wall 275 (gano el lado CALL del plan premarket). NVDA con $2,8M de puts VENDIDAS
      (bid-side, alcista). Veredicto honesto: sin cuchillo liquido que pase el gate a esa hora.
- [x] 16. "make sure we post the best signals to x.com realtime" (2026-08-04 ~10:0x) — HECHO.
      Medido el problema: 15 posts hoy en X, TODOS Finviz (anti-señal a -8,4pp) y CERO de flota
      (`posted_keys: []` — qualifies() exigia "prob>=70" que el feed casi nunca trae).
      Arreglo en x_signal_poster: (a) Finviz DEGRADADO — cap 20->3/dia y RVOL>=2,0 (el unico
      corte del backtest con vida propia, +24,7pp); (b) rama FACTUAL nueva: los prints UW
      grandes (premium>=$1M con lado declarado, o SWEEP) postean el DATO en ingles sin fabricar
      probabilidad (ley measured-probability), cap 6/dia, dedup por contrato; los 🧱 MUROS se
      quedan en Discord (redactados en espanol). Relanzado y verificado: "FINVIZ-SKIP cap
      3/day" ya en el log. 6 tests nuevos.
- [x] 15. "are signals ready for fleet calls or puts?" (2026-08-04 09:54) — NO lo estaban, y
      ahora SÍ (con techo honesto). Diagnóstico medido: la cadena Polygon trae CERO bid/ask
      (`bidask_ok_pct 0.0000`; /v3/quotes = 403) → order_ticket daba NO-GO "sin bid/ask" en
      TODA la flota, y today_alarm5 (el armador de fichas) NO tenía launcher (última corrida
      07-28). Arreglo: (a) `scripts/cboe_nbbo_sidecar.py` + com.ibtrader.cboenbbo — bid/ask de
      RESPALDO CBOE delayed (medido: 11.985 contratos QQQ) cada 5 min, doctrina LATENCIA-FUENTES;
      (b) order_ticket cae al respaldo ETIQUETADO "[spread CBOE delayed]" y con techo CAUTION —
      un GO exige NBBO vivo (IBKR); (c) today_alarm5 lanzado + com.ibtrader.todayalarm5 (L-V
      09:31). Verificado en vivo 09:57: QQQ 709C spread 0,4% CAUTION · MU 870C 3,2% CAUTION ·
      SNDK 1370C 1,4% CAUTION · SMH 565C 28,4% NO-GO (el gate VETA con dato real). 20 tests.
- [x] 14. "avoid too much noise with finviz" (2026-08-04 09:1x) — HECHO commit (siguiente).
      Los 4 filtros del backtest aplicados EN EL EMISOR (finviz_screener_watch.cpp): ventana
      09:45-15:30, solo BUY/SELL interrumpen (WATCH al CSV), RVOL>=1.5 (el unico corte con vida
      propia del estudio), y 1 alerta/ticker/dia — direction_change tambien consume el cupo
      (la mediana de momentum era UNA interrupcion cada 3 min por oscilacion WATCH<->BUY).
      El CSV/estado/eventos se escriben SIEMPRE: solo se gatea la interrupcion, el backtest
      no pierde memoria. Proyeccion con los numeros del 08-03: de 184 alertas a ~16-38.
      Rebuild + selftest OK + 3 instancias relanzadas 09:22 con el binario nuevo.
- [x] 13. "1. create alerts for unusual whales as well for the fleet. 2. make sure software
      running 3. create alert for possible puts or calls of the fleet based on evidence, a lot
      going on right now premarket, take a look." (2026-08-04 08:47 premarket) — HECHO.
      (1) `scripts/uw_fleet_flow.py` + keepalive + `com.ibtrader.uwfleetflow` CARGADO: cinta UW
      de los 30 (1 req global/60s = 1,3% cupo), descriptiva señal-solamente (premium>=1M con
      lado dominante / vol-OI>=2 con >=250k / sweep>=500k), dedup persistido + cooldown 15min
      por contrato + tope 3/min. Titulo "UW FLOW <SYM>" -> #flujo-uw (canal que estaba SIN
      productor). Probado contra la API real: cazo SNDK CALLS 1370 bid-side = venta de calls
      EN el muro del plan. 17 tests. Es el sustituto del vigia IBKR (opt_flow.txt congelado
      desde 07-31), y fleet_up --status ya lo vigila (el verde falso del vigia viejo, avisado).
      (2) flota verificada verde + salidas REALES comprobadas (no solo procesos).
      (3) plan premarket con evidencia publicado 09:10 en #estrategias + embudo (#gamma-niveles):
      ROTACION memoria/semis en gap (WDC +6,4% SNDK +6,3% MU +5,0%) vs megacap software en rojo
      (AMZN -2,5%); SNDK y SMH CLAVADOS en su call wall (1370/565) = candidato fade con print;
      AMZN dos caras en su put wall 275 (flip 271); QQQ abre sobre su muro 710 = retest manda;
      SPY pegado a 761 = pin, sin 0DTE. VIX 15,6 contango. Doctrina: 09:45-10:30 ventana de oro.
- [x] 11. "make sure we have options alerts separately, take a look at spartan for reference"
      (2026-08-04) — HECHO commits 8bd15bcc: #opciones-contratos (ficha GO/CAUTION de
      order_ticket), NO-GO a #senales-rechazadas; Spartan separa por vehiculo, 19 ideas/dia
      vs nuestras 390, mudez medida 11:00-12:59.
      VERIFICADO 2026-08-05: (a) classify() 6/6 sobre los strings REALES de los productores
      (GO/CAUTION → opciones-contratos; NO-GO, sin bid/ask, OPCIONES VETADAS → senales-rechazadas;
      discord_layout.py:117-124); (b) relay log 04-ago 03:02 → 05-ago 06:56: 614 ENVIADAs y CERO
      fichas en canal equivocado — no hubo ficha que enrutar porque today_alarm5 registro las 16
      del 08-04 (6 CAUTION + 10 NO-GO, 0 GO) en data/today_alarm5_fired.jsonl SIN empujar al
      embudo (solo GO interrumpe, orden Yunior 2026-08-04); (c) webhook probado en vivo: ficha
      TEST GO → #opciones-contratos OK (05-ago). El canal espera el primer GO real.
      HALLAZGO colateral: "🟢 SPX PRINT 7715 — CALL" cayo a #sin-clasificar el 08-04 11:57 —
      falta regla para los PRINT de SPX (apuntado en 13d).
- [x] 12. "continue, review all changes, hunt for bugs, logic issues, make sure we post updated
      and accurate data to discord. commit and push when done, but first review all in depth and
      send agents to review the whole repo. hunt hunt hunt." (2026-08-04) — HECHO. 3 revisores:
      (a) puente Discord: cazado el bug de MEDIANOCHE (alerta de las 23:59 leida a las 00:05 =
      edad -86099s -> descartada en silencio; arreglado en parse()), tope de sleep en 429 a 10s
      (60s atascaba la cola y pudria el resto), validacion --end;
      (b) parches de productores: throttle temporal en finnhub (el payload con contador
      derrotaba el dedup -> ~96 pings/noche), throttle de MANADA MUDA persistido a disco
      (crash-loop lo reseteaba), gate krx_en_horario() (Naver caido a mediodia US ya no es
      DANGER), cap diario 5/dia/sym en la ficha de zona del chart (max era 120/h), guardas
      try en los 3 puentes (un aviso jamas tumba el feed);
      (c) frescura: cayo por limite de sesion; verificado a mano lo esencial — el 04:00 de HOY
      genero 30 PDFs y los publico solo (planes: 30/30 subidos + estado: publicado).
      Relanzados con el codigo nuevo: korea_naver, finnhub_ws, provider_bridge, chart_bridge x6,
      discord_relay — todos verificados con logs frescos. Suite 1727 passed.
      HALLAZGO COLATERAL: la suscripcion Finviz Elite EXPIRO ("User's subscription expired" en
      dailyplans.log) — lane jugosas y valuation ROTOS hasta renovar.
      Backfill UW de los 30 de la flota COMPLETO: 8.412 ficheros + 414 HUECO declarados, 1,7 GB,
      cupo 9.282/30.000. data/history/*/uw_*.json queda fuera del repo (re-descargable).
- [ ] 8. "send another agent to explore UW to see if there is some other feature they have we
      could exploit, take a look at latest updates from them" (2026-08-04) — delegado a agente
- [x] 9. "make sure the we send all realtime updates and signals to discord server, send agent
      for that" (2026-08-04) — HECHO, MEDIDO 17:26: última hora el embudo tuvo 2 líneas reales
      (17:23:18 🇨🇳 y 17:23:19 🇹🇼 NOTICIA SEMIS) y Discord entregó 1/2 — la 🇹🇼 murió por el
      cap+dedup (bug 32, arreglado hoy) y la 🇨🇳 salió a #sin-clasificar porque el relé corría
      desde 11:41 con código anterior a f9391259 (sin reglas Asia). Tras fix+relanzo 17:27:23:
      33 webhooks/33 canales (taiwan-japon y china-semis incluidos), push de prueba ENVIADA
      #bot-logs en <1 s y puerta PRIVADA operando. Familias que no llegaban: (a) capadas en
      ráfaga → arreglado con dedup-tras-cap; (b) Asia mal enrutada → arreglado con relanzo.
      El resto del día: ENVIADAS a #flujo-uw/#senales-flota/#estado-proveedores según log
- [x] 10. "send agent to investigate all logs, noise/bugs/broken" — HECHO 2026-08-05: auditoria completa docs/AUDIT-2026-08-04.md (TOP-10 + 15 medios + 17 descartados); fixes en curso
      (2026-08-04) — delegado a agente

- [ ] 1. "create alert system with UW to detect flows, advanced ones" (2026-08-04) — **RECON HECHO,
      motor pendiente**. Informe: `docs/UW-FLOW-RECON-2026-08-04.md`. Sonda reutilizable
      `scripts/uw_endpoint_probe.py` (+13 tests). **64/69 rutas → 200, cero 401/403: el plan da
      acceso a TODO** (129 peticiones = 0,43% del cupo de 30.000). Websocket: **101 y cierre en
      0,09 s con 0 bytes** → puerta de plan, el motor va por REST. 3 alertas diseñadas
      (CAPITAN-CONTRA-TROPA, VEGA-AGRESOR EXTREMO, MURO EN CONSTRUCCIÓN), nacen UNPROVEN.
      El motor NO se cablea hasta medir la latencia en RTH (punto 8) y las colinealidades (8c).
      **ARCHIVADOR YA VIVO (cierra el 8d)**: `scripts/uw_flow_archive.py` + keepalive +
      `com.ibtrader.uwflowarchive` cargado y esperando la apertura (LastExitStatus 0). Rescatada
      de paso la sesión ENTERA del 2026-08-03 para SPY/QQQ/SMH/NVDA/MU (15 ficheros en
      `data/history/2026-08-03/`) porque el endpoint del día aún la servía. Cazado y arreglado un
      fallo real: etiquetaba por RELOJ, así que a las 02:37 archivaba la sesión del lunes en la
      carpeta del martes; ahora el día sale del propio dato y levanta si la respuesta mezcla días.
      +20 tests (`tests/test_uw_flow_archive.py`).
- [~] 2. "100 percent of alert system, including finviz should be also in our discord
      1534075283093848094 server DISCORD_GUILD_ID, use mcp" (guild 1534075283093848094,
      canal 1534075287480959088, app 1534079940675240066) — CÓDIGO COMPLETO Y VERIFICADO EN SECO,
      **BLOQUEADO** en que el bot no está autorizado en el servidor (0 servidores, 404 al guild).
      6 módulos `scripts/discord_{client,layout,setup,webhooks,send,relay,post}.py` + keepalive +
      `com.ibtrader.discordrelay.plist` + `discord_bootstrap.sh` (un comando, idempotente).
      El embudo `data/notify_push.txt` (19 productores: bots, bollinger, ballenas, manada, finviz,
      corea, proveedores) se enruta ENTERO: **676/676 líneas reales clasificadas, 0 al fallback**.
      Consumidor INDEPENDIENTE de `notify_relay.sh`: si Discord cae, ntfy/voz/email siguen.
      55 tests. MCP de Discord NO instalado: decisión pendiente de Yunior (riesgo de cadena de
      suministro — un paquete npm de terceros recibiría el bot token; nuestro código ya hace todo).
- [~] 3. "full backtest to todays alerts, finetune them, lets see how we can maybe filter more
      and be more excusite to avoid signal noise weather for fleet or finviz. review one by one
      with fresh agents" (2026-08-04) — FLOTA HECHA: `docs/BACKTEST-ALERTAS-FLOTA-2026-08-04.md`,
      10 sesiones, 5.366 alertas, 3.907 medibles, triple barrera + Wilson sobre n_eff (ρ̄ medida
      0,351) + null emparejado + BH-FDR. **0 KEEP de 95 tests.** `🧲 ESTRUCTURAL pin` canta
      74-76% y el precio se queda quieto el **1,0%** (es el 46% del feed); el **mute p<55 está
      INVERTIDO** (BAND-WALK hablada −0,080, silenciada +0,065); la confluencia es PEOR que la
      alerta suelta. FINVIZ HECHA: `docs/BACKTEST-ALERTAS-FINVIZ-2026-08-04.md`. 184 alertas el 08-03 en 116
      banners; hit 43,3% contra null 51,7% = **−8,4 pp CONTRA EL AZAR**, signo negativo en 3 de
      4 umbrales, cero cortes sobreviven BH-FDR. El score es INVENTADO (ningún fichero de
      calibración) y además **el componente SMA20 NO EXISTE**: `finviz_screener_watch.cpp:340-341`
      tiene el comentario corrido un puesto, las columnas c=53,54,55 son 50-Day SMA/200-Day
      SMA/50-Day High, `sma20_pct` sale vacío en el 100% de las filas. Momentum **se auto-vota**:
      3 de sus 7 votos ya están en el filtro que manda a Finviz. Y `score N/6` no es una
      fracción (`add(r,0,…)` sube `possible` aunque el voto valga 0) pero la voz lo canta como si
      lo fuera. **NINGÚN filtro aplicado: la decisión es de Yunior.**
- [~] 4. "make sure we post all signals during the day to discord" + estructura de canales/roles
      del brief (categorías START HERE / LIVE TRADING ALERTS / WATCHLISTS / ANALYSIS / SYSTEM),
      webhooks por canal, secretos fuera del repo — hecho salvo la autorización (ver punto 2).
      Estructura ADAPTADA al proyecto: 5 categorías / 33 canales, **cada uno con un productor real
      verificado en el repo** (ley: canal sin productor no existe). Enganchado a `print_plans.sh`
      (planes del día) y a `fleet_up.sh --status`. Roles con permisos mínimos, sin Administrator.
      Canales nuevos que salieron de MEDIR el embudo: `#confluencia` y `#capitanes` (las 8 líneas
      que ninguna regla reconocía eran las dos señales más selectivas de la casa).
- [x] 5. Token bot Discord — VERIFICADO 2026-08-05 06:45: feeds.env:48 responde 200 (bot "Gamma War Room" id 1534079940675240066), fichero actualizado por Yunior 8/4 02:15 ("ya te di todo"); 33/33 webhooks entregando. Si el token del chat viejo sigue activo en el portal, resetearlo allí sigue recomendado.
      — bloqueado: requiere portal Discord de Yunior. El token vive en `config/feeds.env:48`
      (`DISCORD_BOT_TOKEN`, chmod 600, gitignored — verificado con git check-ignore). Los 3 pasos
      de Yunior: (1) discord.com/developers/applications → app 1534079940675240066 → pestaña
      Bot → "Reset Token" (invalida el viejo al instante); (2) copiar el token nuevo y pegarlo
      en `config/feeds.env:48` como valor de `DISCORD_BOT_TOKEN=` (sin comillas); (3) avisar a
      Claude para relanzar `com.ibtrader.discordrelay` y verificar con `scripts/discord_relay.py
      --once --dry-run` + push de prueba. Los WEBHOOKS de canal (config/discord_webhooks.json)
      NO dependen del bot token: el relé sigue publicando mientras tanto
- [x] 6. "we post plans, trees, strategies there too" (2026-08-04) — HECHO 2026-08-05:
      PLANES ya cableados (dailyplans_run.sh → discord_post.py --plans; evidencia HOY 04:02
      "planes: 30/30 subidos" en logs/dailyplans.log:5678) + prueba con UN PDF real
      (QQQ_plan.pdf → #planes-premarket OK). ARBOLES nuevos: cmd_trees lee data/trees/*.json
      (resumen 1 línea/sym: spot, régimen, flip, muros, viernes, edad) + arboles.html adjunto,
      fallback a los PDFs adhoc de trees_horizonte; cron FULL+REFRESH con degradación limpia
      (falla → log, jamás aborta). Probado en vivo: "árboles: 11 líneas + html OK (0.5 h)" →
      #arboles-escenarios. ESTRATEGIAS sigue sin productor automático → capturado en 13b.
      EVIDENCIA EN EL CANAL (API Discord, no solo rc=0): #planes-premarket 2026-08-05T08 UTC =
      **31 mensajes** (1 embed + 30 PDFs, el 04:02 del cron) y T11 el PDF de prueba;
      #arboles-escenarios T11 = 3 (resumen + arboles.html + otro agente). Los 3 webhooks
      resueltos por channel_id a su canal correcto. Nota: los PDFs NO pasan por
      discord_relay.log — discord_post.py publica por webhook directo; el log del relé solo
      espeja data/notify_push.txt.
- [x] 7. "take a look at this server and see what we can learn and take from them to boost and
      improve our server architecture: discord.com/channels/492093482576510982/493845991523352579.
      server in spanish for now, with posibility for english too later. send agent for this task,
      let it use claude in chrome" (2026-08-04) — HECHO: estudio completo en
      docs/DISCORD-REFERENCIA-2026-08-04.md (617 líneas, botín de 13 hallazgos con canal+fecha,
      §11 respondió el item 11). Destiladas 2026-08-05 las 3 mejoras de más valor/coste AÚN NO
      implementadas → items 13a-13c (verificado con grep: ni mudez horaria en el relé, ni
      productor de víspera, ni plantilla de 6 huecos existen hoy).

### 13. Derivados del estudio Spartan (2026-08-05) — top-3 del botín de docs/DISCORD-REFERENCIA-2026-08-04.md §10, NO implementados (apuntar, no construir)
- [ ] 13a. **APAGÓN 11:00-12:59 ET en el relé** (botín #1): Spartan calla en la picadora
      (medido: cero mensajes en sus 3 canales de alerta 2026-08-03); nuestra flota publica igual
      (390 alertas/día). Ventana de mudez en discord_relay.py: en 11:00-12:59 solo pasa
      #criticas, el resto se registra sin publicar. 1 función horaria + tests — pendiente
- [ ] 13b. **VÍSPERA A LAS 15:45, NO A LAS 16:25** (botín #4): productor para #estrategias (hoy
      SIN productor automático) que publique ANTES de la campana las condiciones copiables del
      día siguiente formato `Alert: Bid>X` desde chart_levels/gex_core — es la regla 10 ("fichas
      preparadas la víspera") sin implementar. Spartan: side-charts 15:45-16:09; nuestro
      postmortem 16:20 llega cuando ya no se puede armar nada. ~80 líneas — pendiente
- [ ] 13c. **PLANTILLA DE 6 HUECOS GOTEADA EN PREMARKET** (botín #5): los 30 PDFs de las 04:00
      no se leen en Discord; Spartan publica 1 párrafo/ticker (pivote + 2 res + 2 sop + sesgo)
      goteando 08:54→09:29, 23 sesiones sin variar. Publicar en #planes-premarket una línea de
      6 huecos por ticker sobre datos ya calculados (daily_fleet_plans/gex_snapshot), PDF como
      adjunto para quien lo quiera — pendiente
- [x] 13d. Regla de enrutado para los PRINT de SPX: "🟢 SPX PRINT 7715 — CALL" cayó a — HECHO 2026-08-05: regla PRINT->#criticas en discord_layout.py (verificada con los 3 emisores reales: spx_print_watch, korea_watch, korea_tape; 135 tests verdes)
      #sin-clasificar (relay log 08-04 11:57). Un PRINT es el gatillo de la casa → #criticas.
      Cazado verificando el item 11 — pendiente

### 8. Derivados del recon UW (2026-08-04) — "add new todos for the future as needed once we have better tools or ibkr" (Yunior)
- [x] 8a. **MEDIR LA LATENCIA DE UW EN RTH** — es la condición dura de `~/CLAUDE.md` antes de
      fiarse de una fuente, y sigue abierta desde el 2026-07-26. De madrugada NO se puede: "edad
      del sello" = "tiempo desde el cierre". Un comando, ya implementado:
      `./venv/bin/python scripts/uw_endpoint_probe.py --rth-latency --sym SPY --minutes 30`
      (6 pasadas × 9 endpoints = 54 peticiones, 0,18% del cupo). Procedimiento completo en
      `docs/UW-FLOW-RECON-2026-08-04.md` §4. **Predicción registrada de antemano: 30-90 s.**
      Al terminar, sustituir la fila de UW en `docs/LATENCIA-FUENTES.md:18` (dice "trial, caduca
      ~2026-08-01", obsoleta: el token se renovó el 08-03) por el número medido
      — **MEDIDO-PENDIENTE 2026-08-05: PROGRAMADO, no medido aún.** A las 07:20 ET el mercado
      estaba en PREMARKET y la doctrina prohíbe medir fuera de sesión. Verificado con el propio
      dato (1 petición): `stock-state` SPY → `market_time:"premarket"`, `tape_time`
      2026-08-05T11:19:28Z, 149 ms, cupo 2.417/30.000. Sonda nueva
      `scripts/uw_latency_probe.py --rth-measure` (tope duro 10 req/corrida; compara contra el
      reloj Y contra el print de finnhub `data/rt_last_<SYM>.txt`, que es el proxy del
      disparador sin IBKR) + `com.ibtrader.uwlatency.plist` a las **09:35 ET**, cargado y
      registrado (`launchctl list` → `com.ibtrader.uwlatency`). El portero de RTH vive DENTRO
      del script y **aborta fail-loud con 0 peticiones** (verificado en premarket). Escribe
      `data/uw_latency.json` y reescribe `docs/UW-LATENCIA-RTH-2026-08-05.md`
      — **MEDIDO 2026-08-05 09:35-09:37 ET** (el job launchd disparó solo, `runs=1`, 9 peticiones,
      cupo 3.704/30.000). `market_time:"regular"` confirmando sesión viva:
      **`stock-state` mediana 1,5 s** (min −1,3 / max 1,7) · **`net-prem-ticks` mediana 8,5 s**
      (min 5,7) con **`cube_lag=0`** · **UW − print finnhub mediana +0,2 s**.
      Los dos → **CANDIDATO A TIEMPO-REAL** (umbral <60 s). Fila de `docs/LATENCIA-FUENTES.md`
      sustituida: UW pasa de "🟠 mixto (trial caducado)" a "🟢 segundos (MEDIDO)".
      **LA PREDICCIÓN FALLÓ: dije 30-90 s y salió 1,5-8,5 s.** No se celebra, por la regla que
      yo mismo registré ("<30 s = sospechar antes de celebrar"): (a) hay **desfase de reloj** con
      UW — una edad salió **−1,3 s**, así que afirmar por debajo de ~2 s no está justificado;
      (b) el −224 s del mínimo de UW−finnhub mide la RANCIEDAD DE FINNHUB (print SPY de 102 s),
      no un adelanto de UW; (c) ventana estrecha: 2 pasadas, 2 syms, en la APERTURA — falta la
      picadora de 11:30-14:00. **La regla dura no cambia: UW es candidato, NO disparador**
- [x] 8b. **RE-PROBAR EL WEBSOCKET EN RTH** — el único experimento cuyo resultado puede cambiar
      con el mercado abierto. Hoy: 101 Switching Protocols y cierre en 0,05-0,09 s sin close-frame
      y con 0 bytes, insensible a 4 formatos de join y a no enviar nada; `GET /api/socket` declara
      `{"data":[]}` = cero canales. Si en RTH entrega mensajes, **el veredicto se revoca y el
      socket pasa a ser la vía preferente** (latencia = dinero)
      — **MEDIDO-PENDIENTE 2026-08-05: va en la MISMA corrida de las 09:35** (no gasta corrida
      aparte). Implementado en `uw_latency_probe.ws_suite()`: handshake WS crudo por ssl+socket
      (cero dependencias), los 3 casos de control del recon (sin enviar nada / join lista /
      join objeto), midiendo status, t_handshake, t_cierre, bytes y close-frame; además mide si
      el 101 **consume cupo** comparando el contador antes/después. `GET /api/socket` se repite
      en RTH para ver si declara canales
      — **MEDIDO 2026-08-05 en RTH: EL VEREDICTO DE MADRUGADA SE MANTIENE.** Los 3 casos dan la
      **misma firma exacta** con el mercado abierto: **101 Switching Protocols** y cierre en
      **0,19-0,37 s con 0 bytes y sin close-frame**, insensible a lo que se envíe.
      `GET /api/socket` sigue declarando **`[]` = cero canales**.
      **La hipótesis falsable ("UW apaga el socket fuera de horario") queda REFUTADA**: es una
      puerta de plan, no un horario. **NO se construye consumidor de websocket**; el motor de
      flujo va por REST con sondeo (latencia de 8a). Lo que NO se pudo medir: si el 101 consume
      cupo — el contador saltó 3.651→3.704 (+53) pero en esa ventana también pedían `uw_flow_tape`
      y el resto de la flota; **el contador es global del token**, así que se declara no medible
      por esta vía en vez de atribuirle el salto al socket
- [x] 8c. **TRES COLINEALIDADES QUE HAY QUE MEDIR ANTES DE ESCRIBIR UNA LÍNEA DE MOTOR** (test 1
      de la killlist: ρ antes que edge, |ρ|>0,9 = muere ya):
      (1) `dir_vega_flow` vs el `signed_premium` que ya publica `uw_net_prem.py`;
      (2) `señal_capitan` vs `fleet_consensus` (que mide manada sobre BARRAS, no sobre premium);
      (3) `max_pain` de UW vs nuestro `abs_wall`/`pin-and-expiry-mechanics`.
      Precedente que justifica el orden: `greek-flow.dir_delta_flow` resultó **byte-idéntico** a
      `net_prem_ticks.net_delta` en 406/406 minutos (ρ=1,0) y mató la idea del HIRO-lite
      — **HECHO 2026-08-05** con `scripts/uw_colinealidad.py` (cero peticiones UW: todo de
      `data/history/`). **LAS 3 SOBREVIVEN, ninguna con |ρ|>0,9.** Números en
      `data/uw_colinealidad.json` y `docs/UW-LATENCIA-RTH-2026-08-05.md`:
      (1) ρ agrupado **0,0706** (n=1.013.120 min, 92 días, 30 syms), per-sym min/mediana/max
      **−0,242/0,193/0,544** → vega NO es re-etiquetado del premium firmado. Aviso: SPY agrupado
      −0,082 pero SPY el 8/4 solo **+0,327** → la relación CAMBIA DE SIGNO entre días;
      (2) capitán vs manada-barras ρ = SPY **0,420** · QQQ **0,506** · SMH **0,123** (acuerdo de
      signo 68,1/72,2/56,6%) → miden cosas distintas, que es lo que la regla 12 afirmaba sin
      medir. Aviso: n=678 son buckets SOLAPADOS de solo 9 sesiones, n_eff ≪ 678;
      (3) `max_pain` vs `abs_wall` ρ **−0,0196** (n=185 sym-días, 7 sesiones), strike idéntico
      solo **8,6%**, mediana |d|/spot **5,14%** → no son el mismo imán.
      **CONTROL DE MÉTODO**: el precedente se reproduce a escala — ρ(dir_delta_flow, net_delta)
      = **0,9999992** y **1.013.079/1.013.120 byte-idénticos (99,996%)**.
      **BUG DE HIGIENE CAZADO**: la 1ª pasada colaba `07-25` (sábado), `07-26` y `08-02`
      (domingos) porque hay `levels.json` rancio en esas carpetas = 77 sym-días duplicados;
      corregido con `dias_de_mercado()` (n 262→185, ρ −0,025→−0,0196). Sobrevivir ≠ tener edge:
      publicar probabilidad sigue bloqueado en 8e
- [x] 8d. **ARCHIVADOR FORWARD-ONLY de la serie intradía de UW** — `net-prem-ticks` de los 30 + los
      3 capitanes y `flow-per-strike` de los 8 de la cinta. La serie intradía **NO es recuperable
      hacia atrás**: el reloj de la muestra empieza el día que se encienda, así que cada día que
      pasa sin archivar es un día que las 3 alertas nunca podrán validar. `uw_archive.py:88-103`
      ya archiva `net_prem_ticks` a diario — solo hay que subir la frecuencia a intradía.
      Presupuesto calculado: ~7.560 req/día = 25,2% del cupo, cabe con margen ×4
      — **HECHO 2026-08-05**: `scripts/uw_netprem_archive.py` + `com.ibtrader.uwnetpremarchive.plist`
      a las **16:10 ET** (cargado, `launchctl list` → `com.ibtrader.uwnetpremarchive`).
      **Una pasada al cierre en vez de muestreo intradía**: el endpoint devuelve la SESIÓN ENTERA
      en una llamada, así que 31 req/día = **0,10% del cupo** en vez de los 7.560 (25,2%)
      presupuestados — mismo dato, 250× más barato. Lee `data/fleet.txt` como fuente única (hoy
      31 syms: alguien añadió HOOD). **VERIFICADO EN VIVO** con `--syms SPY`: escribió 405 filas
      cubriendo 13:30:00Z→20:14:00Z (sesión completa incl. post-cierre) contra las 391 que tenía
      el snapshot a media sesión del daemon → el diseño EOD da MEJOR cobertura.
      **Trampa confirmada y manejada**: lanzado en premarket, UW sirve la sesión de AYER y
      `session_day()` lo archivó correctamente bajo `2026-08-04`, no bajo `08-05`
- [ ] 8e. **BLOQUEADO POR HERRAMIENTAS/DATOS** (no se toca hasta que exista la muestra):
      · las 3 alertas no publican probabilidad hasta que su celda tenga `n_eff` suficiente
        (ρ̄=0,412 → `n_eff` = n/(1+(k−1)ρ̄)), pase el null de entrada aleatoria y BH-FDR q=0,10;
      · `CAPITAN-CONTRA-TROPA` solo actúa cuando hay conflicto, y el conflicto es raro: puede
        tardar 2-3 meses en salir de DATA-INSUFFICIENT. **Dicho de antemano** para que nadie lo
        presente como fracaso en septiembre;
      · `full-tape/{date}` (ZIP 1,54 GB/día) para backtest de un día concreto: solo por streaming
        a disco, JAMÁS en memoria en el Mac de 8 GB. ~380 GB/año si se archivara a diario
      — **SIGUE BLOQUEADO A PROPÓSITO 2026-08-05.** Que 8c diga "las 3 sobreviven" NO las
      desbloquea: sobrevivir a la colinealidad es el test 1, no el edge. Dato nuevo que refuerza
      el bloqueo: la muestra de (2) son 9 sesiones con buckets solapados (n_eff ≪ 678) y el signo
      de (1) cambia entre días. El reloj de la muestra de verdad empieza HOY con 8d encendido
- [ ] 8f. **CUANDO VUELVA IBKR** (orden vigente: sin TWS/Gateway esta semana) — el contraste que
      de verdad decide: `stock_state.tape_time` de UW contra el último print de IBKR del mismo
      símbolo (`data/bars_SPY.txt`, que escribe `ibkr_bar_bridge.py`). La diferencia de sellos ES
      la latencia de UW contra la fuente de disparo. Sin IBKR vivo esa comparación no existe y la
      medición del 8a queda a medias (mide la edad del feed, no el desfase contra el disparador).
      **Regla que no cambia pase lo que pase: ningún nivel que dispare una orden viene de UW** —
      el nivel se calcula, el PRINT que lo confirma es de IBKR
      — **SIGUE BLOQUEADO 2026-08-05** (sin TWS/Gateway esta semana). Mitigación parcial ya
      cableada: la sonda de las 09:35 compara UW contra el print de **finnhub**
      (`data/rt_last_<SYM>.txt`, campo `uw_menos_finnhub_s`), que es el mejor proxy disponible
      del disparador. **No sustituye a IBKR**: cuando vuelva, repetir el contraste contra
      `data/bars_<SYM>.txt` y sustituir la fila de `docs/LATENCIA-FUENTES.md:18` — pendiente

## 🔴 SESIÓN 2026-08-03 (lunes 06:40 ET — ráfaga de apertura)
- [x] 12. "save finviz new token" + "create bot ... breakouts" + "add 3 bots for new finviz
      popular screeners: warren buffet, short squeeze, momentum breakout; add signal weather to
      buy or sell; fix annoying notifications, solve todos/issues/pending, build latest, commit,
      push" (2026-08-03 07:4x) — HECHO. Token nuevo en `config/feeds.env` (600, gitignored).
      Motor C++ compartido `finviz_screener_watch` con 3 instancias/estados/keepalives, filtros
      Elite validados HTTP 200 y weather BUY/SELL/WATCH por score explícito. Snapshot inicial
      silencioso, una alerta agrupada, membresía persistente y fallo de API agrupado entre los 3.
      Ruido adicional cerrado: `notify_short` append-only (se acabó releer 500 líneas), dedup real
      por payload en el relay e Intrinio sólo notifica transición REAL del socket (auth OK ya no
      crea UP ni push). Build/selftest + live smoke de los tres verdes; commit/push al cierre.
- [x] 1. "run the fleet with the 6 windows in ib trader" (2026-08-03 06:38) — HECHO 06:49.
      Flota: 21 bots de señal, provider_bridge (intrinio), vigía de ballenas, relé, cola de voz,
      alarma de precio, uw_flow_tape, fleet_consensus, compass, korea_naver_bridge, finnhub_ws_bridge.
      6 ventanas VIVAS en 8080-8085 (qqq nvda smh mu aapl msft) + `ib-trader Cockpit.app --windows 6`
      (v10) abierta y VERIFICADA con captura: las 6 renderizan velas, imán, régimen y net GEX.
      flow_pulse caído es CORRECTO (su ventana es 09:30-15:56). "NO hay TWS/Gateway" es CORRECTO
      (orden: sin IBKR esta semana).
      Hallazgos de la captura, ver punto 4: SMH "SIN LECTURA — barras no contiguas (hueco de feed)"
      justo el día del desplome coreano; "Sin fotos de cadena hoy" es NORMAL antes de las 09:35
      (com.ibtrader.polychains.intraday sólo corre 09:35-16:00; su exit 1 a las 06:50 es el portero
      horario, no un fallo).
- [ ] 2. "run full analysis of fleet, specially for amazon, meta, google, mu, apple, nokia, intc.
      use unusual whales features to gain insights, search darkpool, whales, make sure we have
      widgets for those in our software, analyze premium net, gamma, gex... Review in depth.
      also qqq, spy, smh, futures, kospi, historic posibility of nasdaq falling drastically today
      given a fall in kospi, the pattern is quite common, verify, send me plan via email, one email
      per ticker, include futures analysis so far, options chain data in depth, kospi, and
      probaility of going up or down today, plus the tree with the direction and arrows if it goes
      up or down with walls, magnets, gamma flip, gex" (2026-08-03 06:38) — pendiente
- [x] 3. "add in chart indicator at the top left, with RSI data and weather its bearish or not based
      on bollinger, take inspiration by bento indicator or trinity one, make sure it updates
      automattically" (2026-08-03 06:38) — HECHO commit 544d933d (+ el .py/.html cayeron en 2851ed67).
      Tarjeta PULSO 186px arriba-izquierda: RSI(14) + %B de BB(20,2) en 1m/15m (+3ª fila si el tf
      activo es otro) y veredicto ALCISTA/BAJISTA/NEUTRO/SIN DATOS por la doctrina de la regla 1
      (>=2 marcos reventados = band-walk; UNO solo = elastico -> sesgo CONTRARIO). Calculado en el
      BACKEND (compute_pulse en chart_bridge) con ce.sma/ce.stdev/ce.rsi_series: las MISMAS que
      dibujan las bandas y que usa bollinger_alarm, asi no puede contradecirlas. Fail-loud con el
      motivo escrito y edad de vela/frame siempre visible. 21 tests (RSI contra Wilder + pandas
      ewm); suite 1364 passed. Render VERIFICADO por CDP: valores cambiando solos 4 min en la misma
      pestaña, 0 errores de consola. charts/indicator_panel.js añadido a macapp/bundled_paths.txt
      (sin eso la .app pedia un fichero fuera del bundle) y .app v10 reconstruida + relanzada.
      DE PASO: macapp/.rebuild-waiting estaba rancio desde el 2026-07-29 12:58 -> el post-commit
      hook llevaba DIAS respondiendo "ya hay build/espera en curso" y NUNCA reconstruia. Marcador
      borrado; el auto-rebuild vuelve a funcionar.
- [x] 4. "solve any remaining todos as well, make sure real time is connected, intrinio is delayed
      as per the docs, so finnhub is probably better" (2026-08-03 06:38) — HECHO (parte realtime).
      Medido en sesión, no de la doc: **Finnhub WS 0,00–0,04 s** vs **Intrinio quote 1.216–1.279 s
      y barras 997–1.657 s**. Finnhub REST `/quote` = cierre del viernes (2,6 días) y
      `/stock/candle` = 403; **Databento Live no entitlado** ("live data license is required").
      El print de Finnhub **no lo leía nadie**: ahora `provider_bridge.resolve_spot()` es el punto
      ÚNICO de decisión (tabla `PROVEEDORES` con capacidades y latencia por proveedor, **IBKR
      declarado e intacto**), el spot vivo manda y la fuente viaja con el número
      (`spot_src`/`spot_age` en la cabecera de la cadena + `provider_status.latencia`).
      Arreglado también: dos puentes Finnhub compartiendo la key (free = 1 socket) → lockfile;
      `caidas == 5` que gritaba una sola vez en toda la vida del proceso; socket vivo pero mudo;
      suscripción a los 30 de fleet.txt (SPCX ya tiene su único precio vivo).
      Doc: `docs/REALTIME-FUENTES-2026-08-03.md`. **Abierto**: las barras siguen delayed ~16 min
      con `fleet_consensus.MAX_BAR_AGE=180 s` → MANADA muda por construcción; 16/26 símbolos con
      huecos de barras (XLK 25/30, SMH 11/30); volumen 0 en 30/30 barras de premarket.
- [x] 5. "save unusual whales again: e43cebd2-1ff4-4b04-b944-29e02955497c" (2026-08-03 07:14) —
      HECHO, y NO era redundante: `UW_TOKEN` ya era el bueno pero **`UNUSUAL_WHALES_TOKEN` tenía
      otro valor** (mismos 8 primeros caracteres, distinto después — por eso pasó desapercibido).
      Ese es el nombre que lee la capa `mit/` (`mit/backend/app/config.py:99` y
      `providers/unusual_whales.py:28`), así que el terminal iba con una clave desincronizada.
      Los dos sincronizados y VERIFICADOS en vivo: 200 en flow-alerts, darkpool, greek-exposure y
      market-tide. Escritura atómica, permisos 600, `UW_TOKEN_ISSUED=2026-08-03`.
      (config/feeds.env está en .gitignore: la clave no viaja al repo.)
- [x] 2b. Parte UW del punto 2: "use unusual whales features to gain insights, search darkpool,
      whales, make sure we have widgets for those in our software, analyze premium net, gamma, gex"
      (2026-08-03 06:38) — HECHO. 3 widgets nuevos en el cockpit (`charts/uw_widgets.js`, fichero
      aparte para no pisar el panel RSI/BB): **Dark Pool** (no existía consumidor: `/api/darkpool`
      sólo aparecía en `uw_archive.py:98`), **Net Premiums** (existía VACÍO rotulado "requiere
      tick-by-tick IBKR" — no hacía falta, UW ya firma el lado agresor) y **GEX por vencimiento**.
      Fetchers: `scripts/uw_darkpool.py`, `uw_net_prem.py`, `uw_gex_expiry.py`. 40 tests.
      Dark pool va **DESCRIPTIVO y rotulado**, sin probabilidad ni gatillo: la killlist #3
      (`dpi-lite`) mató el dark pool como SEÑAL y se respeta.
- [x] 9b. Parte de vencimientos del 2026-08-02 19:47: "make sure we have data for options net, gex
      for next weeks, at least 2-3 from now, whole agoust" — MEDIDO y CERRADO por la vía UW.
      Había DOS agujeros: el archivo propio se paraba en 2026-08-21 (`poly_chain_archive.py:445`,
      `--dte` None en los 3 invocadores) y la cadena VIVA se recorta a 2 vencimientos
      (`provider_bridge.py:160 NEAR_EXPS = 2`), así que QQQ/SPY publicaban UN solo vencimiento y
      08-24…08-31 no existía en ninguna parte. `uw_gex_expiry.py` trae los 13 vencimientos de
      agosto (08-28 y 08-31 incluidos) en 1 request/símbolo. **Queda pendiente** el arreglo en los
      ficheros que no me tocaba tocar: `NEAR_EXPS = 2 → 8` y `--dte 32` en los 3 invocadores.
- [x] 6. "make sure walls, magnets, gamma flip, gex, vix, get updated constantly, preferably
      realtime" (2026-08-03 07:00) — HECHO. **Cadencia MEDIDA 2026-08-03 07:40** (edad real de
      cada fichero, no lo que dice el plist): `charts/data/levels_qqq.json` **1,5 min** ·
      `data/gex_snapshot.json` **1,3 min** · `data/vix.json` **0,3 min** ·
      `data/futures_overnight.json` **0,3 min** · `data/provider_status.json` 4,8 min. Los muros/flip
      además se **recomputan al SPOT VIVO cada 15 s** dentro del cockpit
      (`chart_bridge.py:3516 LEVELS_REFRESH_S`), sobre el libro que refresca
      `com.ibtrader.polychains.intraday` (StartInterval 1800 s en RTH). O sea: la parte de
      "constantly" del pedido está. La estructura VX **sí existe dentro del contrato canónico
      `data/vix.json`** (`vx1/vx2/vx_b1/vx_b2/vx_regime`; `vix_feed.py`), no necesita un segundo
      `vix_term.json` divergente. El techo real de frescura lo pone la fuente, no el bucle: el spot
      de Intrinio iba **15,4 min por detrás**, por eso el print en vivo se enruta por Finnhub WS.
      ⚠️ De nada sirve refrescar rápido un muro FALSO: ver el bug del put wall de cadena truncada
      (7 de 29 símbolos) en el bloque de "solve and investigate all not solved bugs".
- [x] 7. "review zsh procesess in mac, some are expired or not updated" (2026-08-03 07:00) — HECHO 07:20.
      Inventario: 26 jobs `com.ibtrader.*` + 77 `scripts/*.sh` + 84 procesos vivos. CERRADO:
      (a) **El precedente de `bin/` por TERCERA vez**: `screener/ensure_all.sh:22` y
      `screener/start_all.sh:19` buscaban `$ROOT/fleet_hours` (sin `bin/`) → el supervisor del
      screener (launchd cada 120 s) llevaba desde la mudanza cantando "PORTERO AUSENTE -> no
      relanzo nada": **2.784 de 3.758 líneas de `screener/ensure.log` (74%)**. Nunca revivió nada.
      (b) Misma clase, 5 consumidores Python: `optgate.py` (el gate de spread de la regla 4 —
      decía "falta el binario /gate, SIN VEREDICTO") y 4 de `level_react`
      (`capitulacion_qqq.py`, `today_alarm5.py`, `level_events_ingest.py`, `level_react_validate.py`).
      (c) `x_whale_bot_keepalive.sh` apuntaba a `./x_whale_bot` (recompilaba en cada arranque) y
      escribía el log en la raíz, no en `logs/`.
      (d) Rotados 5 logs desbocados: **357 MB → 1,35 MB** (`notify_relay.log` solo eran 196 MB).
      (e) `whale_watch_keepalive.sh` (huérfano, su job `com.ibtrader.whalewatch` no existe) hacía
      guerra de pkill con el canónico `opt_whale_keepalive.sh` sobre los MISMOS ficheros
      (`whale_alerts.jsonl`, `opt_flow.txt`, `opt_whale_state.json`). Se CONSERVA (regla 10) pero
      se aparta solo si el canónico está vivo; escape `WHALE_KA_FORCE=1`.
      SIN duplicados de proceso (`price_alarm`/`compass` x2 = keepalive + binario, no duplicado;
      `chart_bridge` x7 = 6 símbolos + el mock del agente de QA). Falsos positivos VERIFICADOS y
      descartados: `polychains.intraday`/`tracecube` exit 1 = su propio portero; `flow_pulse` caído
      = su ventana; `dailyplans_run.sh:32` ya usaba `./bin/volume_profile`.
      ABIERTO: `com.ibtrader.intrinioprobe` COLGADO 3h06m (ver punto 8); `band_open_watch` se
      relanzó 718 veces en 7 días (163/día del 27 al 31-jul, 1 hoy — ya no está en bucle, medir si
      vuelve); huérfanos que NO se borran, solo se anotan: `backup_arquimedes.sh`,
      `watchlist_stats_keepalive.sh`, `cper/slv/uso_keepalive.sh` (sus bots no existen),
      `tws_watchdog.sh`; ruta VIEJA `~/Documents/GitHub/ib-trader` aún en `README.md:16`,
      `docs/OPERATIONS.md` y 2 skills.
- [x] 8. "debug notifications, some might not be updated and might be noise" (2026-08-03 07:00) —
      HECHO 07:20. Ruido MEDIDO en 7 días, no impresiones:
      (a) **`notify_relay.sh`: 305.845 `DESCARTADA` contra 1.650 envíos reales (185:1), log de
      196 MB.** Causa: `notify_short.py:26-31` REESCRIBE el anillo de 500 líneas en cada push,
      `tail -F` ve encoger el fichero y RELEE las 500 → todas se descartaban por viejas y cada una
      dejaba su línea. Ahora el backlog (>300 s) se salta en SILENCIO; se sigue registrando el
      retraso interesante (45 s…300 s), que sí dice algo. + autorrotación a 20 MB.
      (b) **`fleet_healthcheck.py` era el ÚNICO fichero que daba por hecho que el feed es IBKR**
      (`ibkr_bar_bridge.py` a pelo): con `market_source=intrinio` cantaba 🔴 CRÍTICO "bar_bridge
      (feed IBKR): MUERTO" 3 veces al día por algo CORRECTO **y relanzaba la flota para resucitar
      un puente prohibido**. Ahora `bar_feed()` bifurca por `data/market_source.txt` (regla 10:
      condicional, el camino IBKR intacto).
      (c) El audit de launchd cantaba "exit 1 (revisar config)" a los jobs con portero horario
      PROPIO. `gated_jobs()` lo DERIVA del plist (nunca una lista a mano) y excusa solo el exit 1.
      (d) **`sox_keepalive.sh`: 24.091 relanzados y 20 MB de log** estrellándose contra el puerto
      4001 cerrado (`sox_index_feed.py:14` es `ib_insync` puro). Portero de proveedor: en pausa con
      `market_source != ibkr`, UNA línea por hora, código IBKR intacto.
      (e) `fleet_up.sh --status` pintaba en ✗ ROJO dos cosas correctas: "NO hay TWS ni Gateway" (con
      feed no-IBKR es lo esperado) y `flow_pulse` fuera de su ventana 09:30-15:56. Cero falsos rojos.
      NUEVO detector: `stuck_jobs()` caza jobs periódicos COLGADOS (launchd no relanza mientras el
      anterior viva, y el exit code NO cambia) — cazó `com.ibtrader.intrinioprobe` con 3h06m en la
      misma corrida y `StartInterval 600` = **18 sondas perdidas en silencio**.
      CONSERVADO A PROPÓSITO (regla 4): la alarma de ballenas y la de precio, sin tocar volumen ni
      umbrales. ABIERTO para el dueño de `scripts/intrinio_ws_*.py` (no me tocaba tocarlo): grita
      2 mensajes cada ~2 min ("socket NO en weekend" **un lunes** + "socket NO en rth"), 75 de las
      últimas 100 líneas de `notify_push.txt`, por una condición que la casa YA sabe normal
      (el vendor apaga el cluster de noche) — texto obsoleto + falta histéresis.
- [x] 11. "make sure we have latest version of software when done, also: review notifciations of
      failure, some are annoying, not updated. review. send agent if not already" (2026-08-03 07:28)
      — HECHO: relay/cola/Intrinio sin replay ni avisos auth-only; build final + appfresh al cierre.
- [x] 10. "code for ibkr stays, do not delete it, we might connect back to it later on, put
      conditionals per data provider, remember to have all generic to avoid deleting code, and
      modifying preferably just one one service file" (2026-08-03 07:00) — CUMPLIDA y queda como
      regla: código IBKR intacto, selección por registro en `provider_bridge`, Finnhub sólo aporta
      el print más fresco y los screeners Finviz son consumidores independientes señal-only.
- [x] 11. Dos bugs del puente coreano encontrados y verificados por Yunior contra Naver
      (2026-08-03 07:0x) — HECHO 07:15. (a) `kospi` era el ETF KODEX 200 y exageraba el índice
      1,8x: hoy -8,93% contra -5,12% reales del KOSPI. Ahora `kospi`/`kospi200` son los ÍNDICES
      (endpoint `/index/`, tipo declarado en `data/korea_endpoints.txt`) y el ETF vive con nombre
      honesto como `kodex200`. (b) La barra de la subasta de cierre nunca se escribía
      (`localTradedAt` se congela en 15:30 y no llega minuto nuevo): fichero 98.625 contra cierre
      oficial 99.105, y `korea_prevclose` guardaba 108.900 contra 108.820 reales → `korea_pct`
      inventaba medio punto (-9,435% contra -8,93%). `Agg.cierre_oficial` + prev_close OFICIAL
      (closePrice − compareToPreviousClose), idempotente. Los 5 porcentajes cuadran con Naver.

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
- [ ] "envia agents to verify the widgets, make sure we have data for options net, gex for next
      weeks, at least 2-3 from now, whole agoust" (2026-08-02 19:47) — EN CURSO.
- [ ] "termina todo, when done put the korean fleet and windows up for ib trader, wanna see it,
      run some real qa testing on ib trader too, use computer use" (2026-08-02 19:20) — EN CURSO.
      **QA 2026-08-03 07:30 — hecho SIN computer use**: la extensión de Chrome NO está conectada
      ("Browser extension is not connected"), así que el QA se hizo contra los endpoints vivos de las
      6 ventanas + Chrome headless (el mismo camino que usa `e2e_smoke.sh`, con captura PNG
      verificada por magic+IEND). Resultado: **6/6 puertos 8080-8085 responden 200** en `/` y
      `/health`, versión `10` (commit 2026-08-03 06:55), 780 barras por ventana, `signal_only:true`,
      `mock:false`. Hallazgo del QA = el bug del put wall (punto 1 de arriba), cazado precisamente
      en `/health` de QQQ. **Para el QA con computer use hace falta que Yunior conecte la extensión
      Claude de Chrome** (claude.ai/chrome, misma cuenta).
- [ ] "do all todos and remaining work, no excuses. investigate in github, web, reddit, stackoverflow,
      etc" (2026-08-02 03:45) — EN CURSO: los 40 problemas de las revisiones + investigacion externa.
- [ ] "solve and investigate all not solved bugs or issues" (2026-08-02 03:40) — EN CURSO: barrido
      de TODOS los problemas medio/bajo que las revisiones adversariales dejaron sin arreglar +
      caza de bugs nueva (skill bug-hunter) con agentes frescos.
      **LOTE 2026-08-03 (premarket) — 5 números falsos VIVOS cazados y arreglados, commit `5f725032`:**
      1. 🔴 **El put wall del cockpit salía de una cadena TRUNCADA.** La cadena se pide en orden de
         TICKER y la `C` ordena antes que la `P`, así que al cortar en `max_strikes` los PUTs cercanos
         al dinero son lo PRIMERO que se cae. Medido 07:08 en `data/opt_chain_qqq.txt`: **153 CALLs
         (590→790) y sólo 27 PUTs (590→632)** con spot 690,96 → el cockpit dibujaba "Put wall —
         soporte" en **625 (−9,5%)**; MU spot 795,81 con puts 678→698 → **−12,5%**. **7 de 29
         símbolos** afectados (QQQ SPY MU ASML SNDK STX WDC), los otros 22 con `gap 0,000` intactos.
         FIX en `scripts/gex_core.py:388-408`: `put_side_gap_pct`/`call_side_gap_pct` + `SIDE_GAP_TOL`
         (`:46`); si el lado está truncado el muro es **None**, jamás el strike profundo — mismo
         criterio que el `_walls()` de `mit/`. 4 tests en `tests/test_gex_consumers.py`.
         VERIFICADO EN VIVO tras relanzar los 6 bridges: QQQ y MU `put_wall=None` +
         `walls_unavailable="muros sin calcular"`; NVDA −2,2% / SMH −0,7% / AAPL −3,2% / MSFT −4,1%
         sin cambio. **La causa RAÍZ (la cadena truncada) es de `provider_bridge`/`mit`: REPORTADA.**
      2. 🔴 **`iv_regime` publicaba el centinela −1,0 como "IV COMPRIMIDA".** `if not iv_now` sólo es
         falso para `0.0`, así que `-1.0` (= "sin dato" en la cadena) pasaba, `percentile` salía 0 y
         **11 de 26 símbolos** decían `regime: COMPRESSED` (TSLA AAPL MSFT META AMZN GOOGL INTC NOK
         SPCX LRCX WDC) — servido al cockpit por `chart_bridge.py:3108`. Y de paso: `build_iv_history`
         leía `data["rows"]`, clave que el archivador de Polygon **no escribe** (usa `results` +
         `implied_volatility`) → devolvía `[]` SIEMPRE; y el filtro de 60 días comparaba `YYYYMMDD`
         con `epoch/1e6`, inerte. FIX `scripts/iv_regime.py`: `current_iv()` = mediana de las IV
         MEDIDAS o `None`; esquema `results` con respaldo a `rows`; ventana por sesiones reales.
         Ahora **29 símbolos, 0 centinelas** (QQQ 0,62 NORMAL p89 n=15.094). 4 tests.
      3. 🟠 **El healthcheck declaraba MUERTO lo que estaba VIVO.** El `pgrep` de macOS **EXCLUYE al
         invocante y a TODOS sus ancestros** salvo con `-a` (medido: `pgrep -f probe.py` desde dentro
         de probe.py → vacío; `pgrep -a -f` → sus pids). Resultado: **222 líneas** de 🔴 CRÍTICO falso
         en `logs/healthcheck.log` desde 2026-07-26 (notify_relay + x_signal_poster "MUERTO" y heals
         muriendo con exit 127) mientras `pgrep` desde una shell normal los veía vivos (95547/95972),
         y **111 "launchd NO CARGADO"** con dailyplans dejando sus 30 PDFs de las 04:00.
         FIX `scripts/fleet_healthcheck.py`: `_pgrep()` con `-a` y que **LEVANTA** si pgrep falla
         («no puedo mirar» ≠ «no hay»), + guarda **VISTA CIEGA** (ni launchd visible / `launchctl`
         sin un solo job) que no declara nada muerto ni revive a ciegas. 5 tests (55 en el fichero).
      4. 🟠 **`data/vpvr.json` rancio desde el 28-jul** (zonas de liquidez, orden de Yunior 2026-07-28).
         DOS fallos encadenados: `dailyplans_run.sh:32` invocaba `./volume_profile` (vive en `bin/`
         desde la mudanza — **el mismo precedente que mató la flota**) y el binario tenía
         `db_path = "trades.db"` por defecto, que abre el fichero **VACÍO de 0 bytes de la raíz** en
         vez de `data/trades.db` ("no such table: poly_bars"). FIX: `scripts/volume_profile.cpp:368`
         → `data/trades.db`, `dailyplans_run.sh:32` → `./bin/volume_profile`, recompilado
         (`bin/volume_profile`) y **corrido: `data/vpvr.json` regenerado 2026-08-03T11:04:29Z** con
         20 sesiones de `poly_bars`. De paso, **los 6 `scripts/build_*.sh` compilaban a la RAÍZ**
         mientras los consumidores leen `bin/` — la próxima recompilación de `fleet_hours`, `gate`,
         `replay`, `level_react` o `fleet_consensus` habría dejado el binario viejo en `bin/`.
         Corregidos los 6 a `-o bin/<binario>`.
      5. 🟡 **Archivo de un DOMINGO desplazando al viernes** → ver el bloque `session_dirs` abajo.
      **REPORTADO, NO TOCADO (ficheros de otros agentes):** la cadena truncada (punto 1) en
      `provider_bridge`/`mit`; `WARMUP_BARS=1600` que deja a `reversal_router` en INSUFFICIENT_DATA;
      `com.ibtrader.intrinioprobe` **COLGADO 192 min en la misma corrida** (StartInterval 600 s:
      launchd no lo relanza hasta que muera); `walls_status` (`chart_bridge.py:314`) podría decir
      "sin PUTs cerca del dinero" en vez del genérico "muros sin calcular".

### ✅ BUG CERRADO 2026-08-03 07:14 — un DOMINGO archivado desplazaba a la última sesión real
El patrón que `print_plans.sh:47` ya documentaba **volvió a pasar**, por otra puerta:
`com.ibtrader.polychains` dispara `poly_chain_archive.py` a las **08:45 y 16:20 los 7 días de la
semana** y ese script **no tenía portero de día de mercado** (el `--market-day` sólo se le había
puesto a `print_plans.sh`). Resultado: `data/history/2026-08-02/` (domingo) con **35 chain_full**
+ 70 fotos `poly_chain_*`, y su contenido es el del VIERNES:
`chain_full_spy.json` → `spot 744,27` con **`spot_age_s = 159.611` = 44,3 h** (vs el viernes real
747,49 con 67 s). También hay `2026-07-25` (sábado) y `2026-07-26` (domingo) del mismo modo.
**Consumidores que emparejaban "última sesión" por NOMBRE DE CARPETA**, verificados uno a uno:
  · `scripts/skew.py:46` `latest_dates()` → `dates[0]` = el domingo. Su `drr_1d = rr − vals[-1]`
    habría salido domingo−viernes = **0 fabricado**, y el z-score con el viernes duplicado.
  · `scripts/chain_cube_archive.py:293` `full_chain_path(sym, date=None)` → "el más reciente".
    Lo leen `em_envelope.py:363` y `pin_clock.py:203`.
  · `scripts/opening_plan.py:68` `flow()` → primera carpeta con `uw_net_prem_ticks_*`.
  · `scripts/iv_regime.py` → el domingo entraba duplicado en el percentil de IV.
  ✅ `scripts/uw_oi_delta.py:54-65` YA lo hacía bien (decide por la fecha as-of del OI con
    `em_envelope.is_market_day`), tal y como declaraba.
FIX: `scripts/session_dirs.py` nuevo — filtro ÚNICO `session_dirs(hist)` que devuelve sólo
carpetas `YYYY-MM-DD` que son sesión, con la **tabla de festivos única** de `em_envelope`
(LEVANTA si se agota: nunca asume "sin festivos"). Cableado en los 4 consumidores.
`poly_chain_archive.py:558` ya no archiva fuera de sesión (`--force` para forzar).
La carpeta del domingo **no se borra** (es dato, no basura): queda en cuarentena por su propia
fecha — ningún consumidor la elige ya. Verificado: `session_dirs('data/history')` devuelve
`2026-07-21..24, 27..31` y **excluye 07-25, 07-26 y 08-02**. 7 tests (`tests/test_session_dirs.py`).

### ✅ RESUELTO 2026-08-03 — token de Finviz renovado
El `FINVIZ_AUTH3` anterior devolvía **HTTP 401** en el export API. Caducó según lo previsto
(feeds.env: "new finviz api till next saturday" → ~2026-08-01). Con él muerto quedan CIEGOS
`finviz_scout`, `finviz_valuation` y `x_whale_bot`. Yo no puedo renovarlo: hace falta el token
nuevo de la cuenta Elite. **Yunior entregó el reemplazo el 2026-08-03**: guardado en
`config/feeds.env` como `FINVIZ_AUTH3=` (600, gitignored) y verificado HTTP 200 contra los tres
screeners nuevos; scout/valuation/x_whale vuelven a compartir la clave efectiva.

### ✅ BUG CERRADO 2026-08-02 19:10 — el healthcheck había dejado de revivir la flota
`scripts/fleet_window.py:32` apuntaba a `REPO/fleet_hours`, pero el portero vive en
`REPO/bin/fleet_hours` desde la mudanza. Resultado: `live()` devolvía **None**, y con None el
healthcheck **NO revive NINGÚN daemon** ("portero horario AUSENTE: no revivo daemons a ciegas")
mientras `./bin/fleet_hours` respondía perfectamente. Es EL MISMO precedente que ya mató la flota
(mudanza a `bin/`, muerta 05:15-06:48). Ahora busca en `bin/` y cae a la raíz como respaldo;
`live()` devuelve False (correcto un domingo a las 19:08) y desaparecen los avisos falsos de
notify_relay / x_signal_poster. 4 tests (`tests/test_fleet_window_binario.py`).

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
6 tests nuevos (`mit/backend/tests/test_walls_band.py`), suite mit 51 verdes.
✅ **CERRADO 2026-08-03 07:00** — el fix YA ESTÁ APLICADO y commiteado (`ee866100`):
`mit/backend/app/analytics/options_positioning.py:95` `WALL_BAND = MATRIX_BAND`, `:98` `_walls()`
con `pick(fuente, arriba)` filtrando `lo <= k <= hi` y el lado (`k >= spot` / `k <= spot`), `:173`
la llamada, `:212` el caveat con `source=`. `put_wall` a −51,6% es IMPOSIBLE por construcción.
Tests `mit/backend/tests/test_walls_band.py` 6/6 verdes; e2e con el terminal vivo (07:00, spot
750,87): `call_wall=752,0 (+0,15%) put_wall=730,0 (−2,8%) flip=732,74 max_pain=728,0`.

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
→ ✅ **CERRADO 2026-08-03 07:00** — el barrido existe, corrió y publicó el veredicto pedido:
  `scripts/reversal_grade.py` (replay bar a bar sobre `poly_bars`, triple barrera first-touch,
  Wilson sobre n_eff con ρ̄ **MEDIDA in-situ 0,2808** (20 fechas, 29 símbolos, 399 puntos), null de
  entrada aleatoria emparejado por símbolo/hora, BH-FDR q=0,10, piso `MIN_N_EFF=30`).
  `data/reversal_grade.json` (2026-08-02T07:59Z, 55.788 eventos, 29 símbolos):
  **`veredicto_agregado` = "SENSIBLE AL PARAMETRO — no concluyente"**; ALL 58 celdas publicables
  = 0 PASS / 1 FAIL / 57 UNPROVEN; REVERSAL_CONFIRMED 31 celdas = 0 PASS / 5 FAIL / 26 UNPROVEN.
  `wired:false` y `shadow:true` intactos. 33 tests (`tests/test_reversal_grade.py`).

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
- [x] PENDIENTE LUNES — **CORRIDO 2026-08-03 06:51 ET (premarket): `zsh scripts/e2e_smoke.sh --force`
      → 9/9 PASS, 0 FAIL, 0 SKIP** (`data/e2e_report.json`). Los tres puntos que faltaban:
      · **Frescura de barras/nbbo: OK.** 26 símbolos, 78 ficheros del contrato, edad **1–10 min**,
        **faltan 0**. Ningún fichero malformado. (Con el mercado cerrado sólo se podía decir "no
        está roto"; ahora está MEDIDO en vivo.)
      · **Latencia de Intrinio MEDIDA** (`provider_status.last_exchange_ts` vs `epoch`, 26 símbolos,
        06:56:59 ET): **mínimo 15,4 min · mediana 18,4 · máximo 32,1** (más fresco STX, más rancio
        XLK). El **mínimo** es la cota estrecha y cae justo en los **900 s** del tier delayed →
        confirma el hallazgo de `781b1a9a` ("EQUITIES_EDGE a 900,0 s por tercera vez"). Caveat
        honesto: en premarket un símbolo puede no haber IMPRESO en 20 min, así que la mediana y el
        máximo son cota SUPERIOR; el mínimo no. Repetir en RTH. *Sólo medido — actuar es del agente
        que lleva `provider_bridge`/`intrinio_ws_*`.*
      · **`reversal_router` SIGUE en INSUFFICIENT_DATA** y no es cuestión de esperar: QQQ/SPY
        **156** barras 5m RTH y NVDA **155**, de las **260** que pide (`REQUIRED_5M_BARS`,
        `scripts/reversal_router.py:57`). Faltan **104 = 1,33 sesiones RTH**. 156 = exactamente
        2 sesiones (2×78). **CAUSA MEDIDA de que no se acumule**: `scripts/provider_bridge.py:52`
        `WARMUP_BARS = 1600  # ~2 sesiones RTH de 1m`, y `warmup_bars()` (`:98-113`) **reescribe el
        fichero ENTERO** en cada arranque del puente (`one_pass(..., do_warmup)` `:228`). El puente
        lleva 40 min de vida → hoy warmeó a las ~06:11 y volvió a dejarlo en 2 sesiones. `append_bars`
        sí acumula, así que **el router sólo saldrá de INSUFFICIENT_DATA si el puente aguanta VIVO
        desde ahora hasta el miércoles** (Lun+Mar+Mié = 234, aún <260 → **jueves 2026-08-06**);
        cualquier reinicio del puente lo devuelve a 156. *`provider_bridge.py` es de otro agente:
        REPORTADO, no tocado. Arreglo obvio: `WARMUP_BARS` ≥ el máximo que pida un consumidor
        (≥ 2600 para cubrir 260 barras 5m RTH con extendido), o warmup que NO trunque.*

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

- [x] "check dre image (desktop, SpotGamma TRACE); net OI mostrar movimiento realtime con WICKS
      (velas sobre el mapa); copiar las mejores features de SpotGamma si no las tenemos"
      (2026-08-01) — HECHO 2026-08-02 19:10, verificado feature por feature contra el código
      (refs: backup/spotgamma_trace_{gex,netoi}_ref.png):
      (a) Net OI by Strike, call + / put −  → `options_positioning.py:339` (métrica `netoi`) ✓
      (b) heatmap TIEMPO×STRIKE divergente con toggle de métrica → `compute_trace_matrix` (gex|netoi)
          + `compute_option_matrix` (gex|vex). Los DOS mapas del pedido: strike×expiry (post X) y
          strike×hora (TRACE) ✓
      (c) VELAS con wicks sobre el eje de precio → `app.js:158` (wickUp/DownColor) y `:210`; con
          fail-loud explícito en `:162` ("nunca wicks falsas": no se dibujan si no hay velas de la
          misma sesión) ✓
      (d) líneas Call/Put Wall + Gamma Flip + Implied move + Last close → `options_positioning.py:
          347-355` y `orchestrator.py:208` (last_close), pintadas en `app.js:327` ✓
          → y AHORA CORRECTAS: los muros estaban fuera de banda (put wall a −51,6%), arreglado hoy.
      (e) scrubber de tiempo → `app.js` (7 referencias), cableado por el lote L5 ✓
      NO se copian, con motivo:
      · **HIRO** — vía MUERTA y medida: `reqTickByTickData("AllLast")` sobre opciones da **error
        10189 en 20/20** contratos (`Done.md:437`, `docs/HIRO-2026-07-25.md:215`) y Polygon da 403
        en `/v3/trades` de opciones. El skill `dealer-flow-limits` §6 decía "nunca se ha intentado":
        CORREGIDO hoy para que nadie lo rediseñe. El sustituto real son las flow-alerts de UW.
      · **Hedge Wall** — SpotGamma no publica su fórmula; inventar una y etiquetarla con su nombre
        sería un prior disfrazado de medición (skill `anti-overfit-killlist`). Ya tenemos flip,
        call/put wall y max pain, que son los niveles que sí sabemos calcular.

- [x] "urgent: solve korean fleet not working realtime via websocket. no excuses, check intrinio docs, review all in depth" (2026-08-02 20:05 ET) — RESUELTO por `korea_naver_bridge.py`, delayTime 0 medido; índices/ETF y subasta de cierre corregidos (ver punto 11 de esta sesión).
- [x] "new unusual whales key: e43c… save it" (2026-08-02 20:03) — guardada en config/feeds.env (UW_TOKEN + UNUSUAL_WHALES_TOKEN); VERIFICADA contra la API: 200 en /api/stock/SPY/flow-alerts y /greek-exposure
- [x] "remember, no ibkr this week" (2026-08-02 20:15) — Gateway NO se lanza; Corea pasa a scripts/korea_naver_bridge.py (Naver, delayTime 0 medido, 10 simbolos), keepalive cableado
- [x] "intrinio websocket has to be on... search in depth" (2026-08-02 21:00) — agotadas TODAS las vias (tabla en .claude/skills/intrinio-api/SKILL.md): el SDK OFICIAL sin tocar falla igual, hosts identicos en los SDK de Python/Node/Java, sin mTLS, DNS identico en 3 resolvers, IP propia por host, y falla tambien desde OTRA red. La misma key da 200 en api-v2. Vigia intrinio_ws_autostart corriendo: lo enciende solo en cuanto responda.
- [x] "probaste las dos keys de intrinio?" (2026-08-02 21:15) — NO habia dos: en este Mac hay UNA sola (config/feeds.env; el feeds.env de la raiz es symlink al mismo fichero). Corregido el skill, que afirmaba "nuestras 2 keys" sin respaldo. HALLAZGO de la busqueda: la propia API declara el entitlement — source=iex responde "Realtime sources have been adjusted to cboe_one_delayed based on your access" -> el plan es tier DELAYED.

- [x] "make sure walls, magnets, gamma flip, gex, vix, get updated constantly, preferably realtime"
      + "code for ibkr stays, do not delete it, we might connect back to it later on, put
      conditionals per data provider, remember to have all generic to avoid deleting code, and
      modifying preferably just one one service file" (2026-08-03, hecho)

## Sesión 2026-08-05 premarket (6:08 AM)
- [x] "analyze these tickers in full depth premarket... msft y aapl dark pools >$1B ayer... options chain, dark pool, whales, gamma, gex, dealers zones, call wall, put walls... today session and rest of week, also next week... use UW or polygon... msft, aapl, amd, nok, nvda, hood... include plan, tree with directions, strategies, post the results to discord and also to x.com, analyze premarket news, prices" (2026-08-05 06:08) — estado: hecho — plan+árboles+estrategias publicados en Discord (planes-premarket, dark-pool) y X (3 posts); dato clave: MSFT $967M DP agregado @492.81, AAPL $1.049B @309.38, ambos = soportes
- [x] "send agent to add MAG7 to our software for tracking" (2026-08-05 06:08) — estado: hecho 4854885c (data/mag7.txt + scripts/mag7_view.py)
- [x] "add filter finviz for squeeze, vrp or volatility, overpriced options, to find nice trades for puts or calls, be smart on this" (2026-08-05 06:08) — estado: hecho 89891d4c (scripts/finviz_vol_screen.py, 3 lanes → data/screener/vol_screen_YYYYMMDD.jsonl)
- [x] "find nokia similar tickers like we did last week on friday... call/put was like 7... find 20 tickers like nokia that people like, that could go to the moon the next week... add them to watch, we will call it the bargain watch fleet" (2026-08-05 06:08) — estado: hecho 97d843f1 (data/bargain_fleet.txt 20 tickers + docs/BARGAIN-FLEET-2026-08-05.md; spot-check OPEN 4.5C OI 27299 verificado)
- [x] "bargain watch fleet": 20 tickers como NOK (C/P alto, baratos, retail, opciones liquidas) -> data/bargain_fleet.txt + docs/BARGAIN-FLEET-2026-08-05.md (2026-08-05, hecho)
- [x] backtest 2026-08-04: veto capitan al fade bb-rebote SHORT + re-canto apertura finviz momentum (2026-08-05) — estado: hecho. Veto medido retro: sector calla 42/77 fades (perdedoras 30/51) pero mata 12/26 ganadoras (46%) → OFF por defecto, tras IBT_BB_CAPTAIN_VETO=1 (banner sin voz). Re-canto 09:31-09:35 de matches momentum vivos "(pre-open match)" con dedup diario (PLTR/AAOI ya no se pierden).

## Sesión 2026-08-05 mediodía
- [x] "review nokia c/p ratio, whales, dark pool, options chain, walls, same for aapl, nvda, mu,
      tsla, ... plus also for the bargain fleet. do it for this week and next week. order them
      from bullish to bearish, include the whole main fleet as well" (2026-08-05 10:40) —
      estado: hecho. `scripts/fleet_cp_scan.py` (57 syms = flota 36 + bargain 21, ~800 req UW,
      ~40s) + `fleet_cp_rank.py` (5 votos iguales, umbral fijo, sin z-scores compuestos) +
      `fleet_cp_report.py` → `docs/CP-SCAN-2026-08-05.md`.
      **3 GOTCHAS UW MEDIDOS Y CORREGIDOS**: (1) `/oi-per-strike` y `/flow-per-strike` IGNORAN
      `expiry` (NOK: 54.877 calls igual con 08-07, 08-14 y sin parámetro) → muros y OI por
      vencimiento se construyen desde `/option-contracts?expiry=X`, que sí lo respeta; sumar
      w1+w2 contaba el mismo día DOS VECES. (2) `/darkpool` topa en 500 prints: el agregado
      estaba TRUNCADO (el "$1,11B de QQQ" cubría 26 min, no el día) → se marca `TRUNC` + ventana
      real. (3) el flip tomaba el PRIMER cruce de cero (COIN "flip 65" con spot 151) → ahora el
      más cercano al spot, y `None` + motivo si está a >20%.
      Hallazgo de lectura: **C/P alto ≠ alcista** — NOK C/P 7,2 con las calls al BID (agresor
      −0,06) y los puts vendidos (−0,43); por eso el C/P se muestra pero NO vota, vota el lado
      agresor.

## Sesión 2026-08-05 — auditoría TOP-10 (agente, orden "ataca hallazgos #1-#8 del AUDIT-2026-08-04")
- [x] AUDIT #1 NBBO dos relojes: provider_bridge.py write_nbbo → campo1 wall-clock + campo4 epoch de bolsa + feed_tier en provider_status.json; verificado vivo (nbbo_spy campo1 edad 42s, campo4 1021s delayed declarado); lectores parsean 3 campos sin romper (2026-08-05, hecho)
- [x] "add hood to fleet" (2026-08-05 ~07:05) — hecho: HOOD + PLTR MSTR COIN CRWV RKLB en fleet.txt(36)/universe_gamma(41)/provider_syms(32), barras verificadas vivas
- [x] "tell me some contract... next nokia" (2026-08-05) — hecho: NVDA C215 08-14 ($425, IV/RV 0.77, sweep $2.3M ask ABRE) max conviccion; HOOD C95 08-14 replica patron NOK pero IV 73 vs RV 62 = caro; docs/CONTRATOS-2026-08-05.md
- [x] "take a look at C/P ratio find more like hood..." (2026-08-05) — hecho: PLTR MSTR COIN limpios + CRWV RKLB (earnings 08-11/08-10, watch sin premium comprado); medido C/P, netprem, IV/RV, muros
- [x] "run full analysis on bargain fleet this week and next..." (2026-08-05) — hecho: 20 tickers x 2 expiries (muros/max pain/flujo/ballenas/dOI) + vetos earnings medidos; solo ZETA USAR RGTI SOFI combinan flujo+estructura
- [x] "find me the best contracts for the rest of the week or next week expiration" (2026-08-05) — hecho: ranking por sigmas-a-breakeven + IV/RV en docs/CONTRATOS-2026-08-05.md, publicado Discord+X
- [x] AUDIT #4 calibración congelada: calibration_ledger.py record_from_ranking parsea formato emoji (▶️reclaim/🎯/🛑, régimen desde ranking.json porque 🚀 pisa el emoji) + fallback legado; backfill 22-jul→05-ago = 324 filas, 294 calificadas; calibration.json pasa de n=27/1día a reclaim_wall POSITIVO n=131 59% / NEGATIVO n=67 42%, trust=SI; +2 tests (2026-08-05, hecho)
- [x] AUDIT #3 flecha diluida: direction_view.py:212 → fleet=0.0 (sin dato/capitanes discrepan) ya NO se registra con peso 1.4 (dilución 28,6% muerta); verificado vivo (QQQ fleet=1.0 sigue entrando, caso 0 cubierto por test nuevo test_fleet_cero_no_entra_como_familia) (2026-08-05, hecho)
      · AUDIT #1 completado (a): NBBO pasa a tarea async propia (quote_loop, concurrencia 6,
        periodo 7s, back-off x2 si 429) — MEDIDO antes 0/27 símbolos pasaban el gate de 10s de
        los bots (ciclo real 25-27s), DESPUÉS 27/27 sostenido en 8 muestras/40s, edad p50 1,5-6,5s,
        0 respuestas 429; retraso real de bolsa declarado (915s) en nbbo_gate.retraso_bolsa_p50_s
- [x] AUDIT #5 MANADA ciega: fleet_consensus.py:43 MAX_BAR_AGE 180→240 + :47 CYCLE_S 45→20 (voz DANGER 90s→40s), gemelo fleet_consensus.cpp:95,97 igual + rebuild. MEDIDO ahora: barras p50 44s p90 208s max 254s → con 180 votan 23/27 (por debajo del quórum 24 = MANADA CIEGA), con 240 votan 25/27 = operativa (2026-08-05, hecho)
- [x] AUDIT #6 EM inventado al 2%: compass.cpp:703 amplitude() aborta con why="sin EM medido" (LATIGAZO/REBOTE/SCALP ya no se gradúan contra una valla fabricada) + :920 el gate S_APPR cae a NEAR_PCT*2; direction_view.py:156 em sin fallback y el factor flip no vota sin EM (2026-08-05, hecho)
- [x] AUDIT #7 frescura del camino del dinero: gate_core.hpp parsea spot_age del header + OPT_MAX_SPOT_AGE_S=600 y lo mete en `fresh`; gex_core.py SPOT_STALE_S=600 en el veredicto `stale`. MEDIDO: gate SPY antes fresh=true (age 30s del ESCRITOR) → ahora fresh=false "spot de la cadena viejo 919s"; QQQ spot_age 8s sigue fresh=true; gex_core en RTH: SPY/TXN stale=True con motivo (15/20 min) donde antes stale=False (2026-08-05, hecho)
- [x] AUDIT #8 compass adoptaba spot por mtime: compass.cpp:1475 exige además spot_age_s<=300 del propio productor (levels_txn.json: mtime 137s pero spot_age_s 954s) (2026-08-05, hecho)

## Sesión 2026-08-05 tarde
- [x] "make sure to shut up intrinio alert websocket" (2026-08-06 20:25) — hecho: push del
      probe y grita() del autostart ELIMINADOS del todo (antes solo gateados por fase). Ni voz
      ni telefono en ninguna fase; el estado vive en el log, intrinio_ws_up.json y el jsonl del
      probe. Verificado en vivo: transicion a CAIDO detectada y muda.
- [x] "kill finnhub websocket notifications" (2026-08-06 10:00) — hecho: grita() eliminado del
      todo en finnhub_ws_bridge (ni voz ni push, nunca); estado sigue en log + status.json.
- [x] "make sure to kill those fuckin notifications for intrinio and finnhub not connected,
      debug that shit, fix" (2026-08-06 06:50) — hecho. CAUSAS MEDIDAS, no silenciadas a ciegas:
      (1) FINNHUB: overnight sin trades -> el servidor corta por idle sin close frame (185
      caidas/noche, 0 trades perdidos) -> grita() cada 5 caidas 24/7. Fix: voz/push solo en
      RTH + backoff min 120s fuera de RTH (menos churn). (2) INTRINIO: el vendor APAGA el WS
      overnight (~70% medido, memoria) -> el probe pusheaba cada transicion y el autostart
      hablaba a las 3am. Fix: push solo en premarket/rth/afterhours; voz gateada por fase;
      + handler x8 duplicado del SDK deduplicado + timeout duro 540s al probe (colgado 307min).
      Los logs jsonl siguen registrando TODO — solo calla la voz/telefono fuera de sesion.
- [ ] "mejora todo" (2026-08-06 00:50) — en curso: (a) flip forward en pipeline de niveles
      [Claude directo], (b) escáneres UW: bug max-pain + peaje + muros sin céntimos + dOI
      etiquetado [agentes, bloqueados por límite hasta 4:40am — relanzar], (c) "7. backtest finviz signals too" — HECHO:
      docs/BACKTEST-ALERTAS-FINVIZ-2026-08-06.md (3 sesiones, 439 decididas, n_eff 124):
      TODOS 53,1% vs null 51,0% p=0,21; buffett 52,3% (null 53,0%!); momentum 55,0% p=0,19;
      squeeze 51,5%. NADA sobrevive FDR; curva k inestable (momentum +4pp solo en k=1.0)
      = MEDIDO-SIN-EDGE los 3. Siguen grabando, sin voz. Agregador scripts/finviz_bt_agg.py.
      (d) "8. review logs" — HECHO (ver commit e611781a): disco 10->22Gi tras 3 ENOSPC,
      korea relanzado, UW 30k/dia agotado (sonda de reset activa), DeepSeek 402 SIN SALDO
      (decision de Yunior recargar), probe intrinio con timeout 540s.
      PENDIENTE menor: watchlist_quotes y opt_whale_watch en bucle contra 4001 (gate por
      market_source), falso verde healthcheck, Databento timeout->yfinance.
- [x] "calibrate the crazy compass... the arrow should be red when strong trend down based on
      math or whales... only show the arrow, remove the description under" (2026-08-06 00:20) —
      hecho d1fb2b29. Causa del bug medida: regime POS && !near iba a CAJA flat SIN mirar la
      tendencia (INTC 2026-08-05 -1,7% en 53min = flat). Fix: TENDENCIA FUERTE (band-walk >=2TF
      o |z6|>=2 persistente) manda sobre la caja; edge nuevo trend_flow = impulso 2σ + ballena
      (flujo capitán o signed_premium UW >=100k, <=10min); sin ballena sigue flat (honestidad
      OOS). UI: solo la flecha, texto al tooltip. 56 tests, ASan OK, Cockpit relanzada.
- [x] "review intc de nuevo, in depth, net options, walls, delears, gamma, etc" (2026-08-05 15:00) —
      HECHO. Workflow ultracode: 8 dimensiones + 8 refutadores + cruce (17 agentes, 1,05M tokens).
      **REGLA NUEVA MEDIDA: el open_interest de UW es el cierre de AYER incluso a las 23:48 ET**
      (verificado: 09-18 C100 sigue 32.551/prev_oi 32.061 a medianoche). Lo único de HOY es
      ask_volume−bid_volume y la prima. Todo "la ballena construye AHORA" leído del dOI va
      1 sesión desfasado. El C108 08-07 (dOI +19.082) se construyó el 08-04, y con 89,2%
      MULTI-LEG = pata de spread alcista, no call desnuda vendida.
      **FLIP FORWARD 102,90** (reconstruido sin 08-05 y 08-07) vs 98,39 con el 0DTE dentro:
      INTC cerró en 101,06 = POR DEBAJO de su flip forward -> acelerador, no colchón.
      13 contradicciones resueltas y 10 vetos en docs/. Cierre 101,06 (+0,198%), NO 102,66.
- [ ] "review bargain fleet, find me bargains for options tomorrow. maybe VELO?" + "use data
      realtime AH too" (2026-08-05 15:15 / 23:45) — estado: en curso (re-verificacion al CIERRE).
      **VELO = NO**, tres vetos independientes: earnings 11-ago postmarket (confirmado por la
      empresa), spread mediano 13,0% en el dinero (1 de 13 chains cumple <=5%), y flujo VENDEDOR
      (487 calls al ask vs 1.763 al bid; sweep de 500 al BID). Sin semanales: 08-21/09-18/12-18.
      **HALLAZGO ESTRUCTURAL**: en tickers de $3-12 el tick de 1 centavo hace ARITMETICAMENTE
      imposible spread<=5% en contratos de $0,05-0,30 -> 95% de la bargain fleet muere por spread,
      no por falta de flujo (POET P8.5 agresor +2.121 pero spread 21,5%).
      AH medido 16:00-20:00 ET (ya cerrado): SOUN +22,02% (max 8,20, cierra 7,8456 = fade del 4,3%),
      RUN -12,39% (min 8,78, rebota a 9,19), RDW +7,93% (max 12,14, cierra 11,57). Los 3 reportaron
      hoy postmarket. Manana reportan RGTI+CLSK (post) y QBTS (pre) = vetados.
      LA SESION SE DIO LA VUELTA: QQQ -0,90% SMH -1,04% SPY -0,20% cierran los tres en el 3-8% de
      su rango = veto de capitan sobre calls en la apertura. Workflow: 4 lotes (21 bargain + NOK) + VELO dedicado + calendario de vetos
      por earnings; criterios duros spread<=5%, OI>=500, agresor comprador, dOI abre, IV/RV, BE<1σ.
      MEDIDO ya: VELO (Velo3D) NO tiene semanales — vencimientos 08-21/09-18/12-18/03-19; su C17.5
      del 08-21 va al BID (556 bid vs 61 ask) = venden prima, no compran.
- [x] "review expiring gamma for nokia, intc and aapl this week, msft too. take a look at spcx for
      options and leveraged. review with uw" (2026-08-05 14:40) — hecho: uw_gex_expiry + cage_lotto_scan
      (--max-spot 9999) + perfil de muros por expiry vía /option-contracts?expiry= + net-prem-ticks.
      Muere esta semana (08-05+08-07): INTC 32,2% · AAPL 28,8% · MSFT 20,9% · NOK 11,6% · SPCX 30,9%.
      SPCX: lockup 08-06 (911,5M acc / $116B), régimen NEGATIVE, signed −58M; el "muro" C330 08-07
      con OI 558.996 es basura de $0,01 (IV 461%) — NO es imán. Apalancados verificados vivos:
      SPCH/SSPC/SPCU/SPCF/LOFF/SPAL/SNK; SPCK ilíquido (vol 4.370).
- [x] "find me contracts for just 10-30 dolars for this week for cheap tickers similar to nokia,
      with high chances of success, take a look at gamma about to expire that would put the
      tickers out of jail" (2026-08-05 14:35) — estado: hecho, docs/LOTOS-JAULA-2026-08-05.md. Scan de lotos $10-30 sobre
      bargain fleet + baratos de la flota, expiry 08-07/08-14, con score de JAULA (gamma que
      expira el 08-07 vs OI que queda) — scripts/cage_lotto_scan.py
- [x] "put a single window for ib trader instead of 6, 3" (2026-08-05 16:2x) — hecho:
      DEFAULT_WINDOW_COUNT 6->1 (main.swift), test actualizado, VERSION 17, app rebuild+relanzada.
- [x] "review heatmap, that it works properly realtime as widget... should be as beautiful as
      that one [captura Exposure/UW], its the top only widget by default in the right panel"
      (2026-08-05 16:2x) — hecho: scripts/gex_heatmap.py (UW greek-exposure/strike-expiry ->
      data/gex_heatmap_<sym>.json, daemon --loop 60 corriendo) + charts/gex_heatmap_widget.js
      (matriz strike x expiry verde/rojo, MVC morado, fila spot azul, edad pintada, escala
      $/1% = raw x S^2 x 0.01 verificada contra la app de UW) + wgt-gexheat PRIMERO y UNICO
      abierto por defecto en live.html + rutas /data y /js en chart_bridge.py; bridges
      reiniciados, verificado 200 en 8080. GOTCHA: strike-expiry da gamma-share crudo
      (gamma x OI x 100), el endpoint /expiry ya viene en $ — no mezclar escalas.
- [x] "review again, give me 5 with all that needs to be done. go in depth first, news, all"
      (2026-08-05 15:1x) — hecho: docs/LOTOS-TOP5-2026-08-05.md. 2 workflows (16 agentes) se
      comieron el limite de sesion 2 veces; sobrevivieron los 3 de noticias con 3 hallazgos
      que CAMBIARON el ranking: DJT reporta 08-10 17:00 (EDGAR, el scan decia 07-31 = falso),
      GME en ventana VWAP 35 sesiones del canje $1.4B (8-K 08-02, mata el C20 08-14), BBAI
      con ATM de 100M acciones (424B5 07-31, mata el C3 como loto). Top5: OPEN P4 / SNAP C5.5
      08-14 (liberacion) / SOFI P18 print-only / NOK P9.5 doble-cara / DJT P10 vigilancia.
- [x] "1. heatmap 3+ meses adelante, realtime, APIs de fallback. 2. remove zooming velas.
      3. remove madrid ribbon. 5. lineas con nombre (HIRO etc), macd y TODOS los indicadores
      opcionales, panel tipo TradingView" (2026-08-06) — hecho:
      (1) gex_heatmap.py reescrito: horizonte 110 dias (cap 24 exps; 100 dejaba fuera el
      mensual NOK 11-20, cazado por el verificador), cascada uw->polygon->chain_local con
      src/partial/stale declarados, si todo falla NO toca el JSON anterior; widget con
      scroll-x + strike sticky + fuente/avisos en el pie; daemon relanzado (QQQ 20 exps,
      edad 32s; fallback polygon medido 1.4s).
      (2) czbar + setShowBars + rueda custom RETIRADOS, SHOW_BARS=100 fijo, zoom nativo.
      (3+5) live.html: registro IND (localStorage indPanel_v1), TODO opcional y OFF por
      defecto salvo Net Premium; boton "f Indicadores" con checkboxes + leyenda de chips
      con color/nombre (clic quita); title en cada serie (BB/SMA/VWAP/ST/TT/MACD) para
      etiqueta en el eje; ribbon/ttLevels/marcadores respetan el toggle; panes MACD y
      netprem colapsan a 0 si OFF. node --check OK, 12 tests, app relanzada.
- [x] "volume optional; number when hovering (150M); big trades balloons -> beluga and big
      trades optional" (2026-08-06) — hecho: volume y whales en IND_DEF (OFF), pane volumen
      colapsa, Vol en la barra OHLC con el numero de la barra bajo el crosshair (fmtVol
      B/M/K) y color de la vela, whaleTally se oculta con el toggle; Target Trend (beluga)
      ya era opcional; comentario zombie del zoom viejo limpiado.
- [ ] "create a simple macos app called Gamma War Room in swift, websockets realtime, generic
      provider (finnhub/polygon or your choice), features: indicators optionals, chart, heatmap
      widget, hiro, walls, gex, dex, charm, flips, magnets, keep it simple fully portable, pure
      swift, build to desktop + iphone 14 (developer mode, no paid account), layout ok, realtime
      perfect" (2026-08-06) — estado: macOS HECHO (app en ~/Desktop, corre con llaves sembradas; commit inicial en ~/GammaWarRoom rama main); iPhone PENDIENTE de cable+Apple ID en Xcode. AMPLIACION: "for the heatmap use same colors as quantdata and the picture i just sent u, keep same colors and ui ux as quantdata" (fondo azul-negro 0A0F1E, pills azul 2563EB, verde 22C55E, rojo granate DC2626, MVC morado A855F7, fila spot azul)
- [x] "verify, no data [GWR] + icon from downloads" (2026-08-06) — hecho. CAUSAS MEDIDAS del
      no-data: (1) finnhub /stock/candle = 403 en el tier (el WS si va) -> Polygon primero,
      VERIFICADO con el codigo compilado: 400 velas SPY; (2) UW daily limit 30.000 REVENTADO
      por el daemon gex_heatmap (7 syms x ~26 req cada 60s tras subir el horizonte a 110d
      ~260k/dia) -> daemon relanzado QQQ SPY --loop 900 (~5k/dia) y la app dosifica
      (structure/hiro 90s, heatmap 6min) + muestra el error UW REAL en ambar (uwNote);
      hasta que UW resetee, heatmap/cards sin dato y DICIENDO por que. Icono: escudo ChatGPT
      -> AppIcon.appiconset (mac 16-1024 + ios 1024), AppIcon.icns verificado en el bundle.
- [x] "release some space in my mac, old dependencies deleted from cache, explore, send
      agent" (2026-08-06) — hecho: ~23GB liberados en total. Agente: ~8GB de caches
      regenerables (JetBrains 3.9G, Chrome 1.7G, playwright 1.1G, pip 543M + uv 592M,
      com.apple.python 597M, DerivedData 532M, cpptools 517M, brew 228M, logs 198M);
      yo: ~15GB de simulator runtimes viejos (iOS 18.2 + 26.4.1) + dmg de descarga Xcode.
      Disco 99% -> 90% (22Gi libres, VERIFICADO df). Pendiente decision Yunior: cargo 134M,
      node_modules de Documents/GitHub 257M (no tocados).
- [ ] "try the app on my iphone again via wifi, search docs" (2026-08-06) — estado: BLOQUEADO
      por accion fisica. Medido con 3 agentes + verificacion propia: el iPhone NO anuncia
      `_remotepairing._tcp` (5 servicios de pairing vacios) mientras el mDNS del Mac esta SANO
      (llegan _airplay/_ipp/_printer/_companion-link por en0) y ping6 ff02::1%en0 responde 10
      vecinos incluido el iPhone -> ProtonVPN y firewall EXONERADOS por medicion. Causa: iOS
      17+ solo publica ese servicio con MODO DE DESARROLLADOR activado, y el primer
      emparejamiento exige CABLE una vez (doc Device Hub: "otherwise, use a cable"; wireless
      nativo = iOS 27 + Xcode 27). Vias sin cable descartadas por doc: OTA/itms-services (exige
      perfil de DISTRIBUCION; el nuestro es development con get-task-allow=true) y Apple
      Configurator ("Attach the device"). App iOS YA firmada y lista en
      build-ios/Build/Products/Debug-iphoneos/GammaWarRoom-iOS.app (perfil con el UDID, caduca
      2027-08-06). Falta: Yunior activa Modo de desarrollador + cable 60s una vez.

## 2026-08-06 21:35 — peticion nocturna (SPY + monitoreo hasta viernes 09:25)
- [x] "analyze fleet, spy priority and do post to x.com on them, the ones u are confident the
      most, check polygon chain, UW, intrinio, ... provide tree, update as of right now based
      on korea" (2026-08-06) — hecho 6596d7c0. scripts/night_tree.py (arbol re-ejecutable) +
      2 posts en X (ids 2085545037027291336 SPY / 2085545056052682951 Corea). UW: su archivo
      era de AYER (uw_net_prem asof 08-05 14:42) y se dijo; Polygon: acciones a T-1, opciones
      si (el mapa gamma vive de ahi); Intrinio: unica fuente viva de barras 1m premarket.
- [x] "schedule monitoring every 2 hours till 9:30 am friday, last monitoring at 9:25, after
      monitoring create a post in x.com, mainly based on spy, use overnight data, accumulated,
      unconsolidated order flow" (2026-08-06) — hecho f6cb41d3. launchd
      com.ibtrader.nightmonitor 23:25/01:25/03:25/05:25/07:25/09:25, armado por
      data/night_monitor_until.txt (el control final lo borra). El de 09:25 publica en X.
- [x] "make sure we have a feature in software that allows us to read unconsolidated data
      premarket and calibrate arrow based on that before market opens on 9:30 am every day.
      see web on how big softwares do it, big institutions." (2026-08-06) — hecho f6cb41d3 +
      3cdcacc0. bin/premarket_arrow (C++23) + com.ibtrader.premarketarrow (03:58->09:28) +
      premarket_unconsolidated.py/premarket_calibrate.py (Databento a nivel de PLAZA).
      LIMITE MEDIDO: Databento NO tiene licencia live -> lo no consolidado es T-1 y CALIBRA;
      lo vivo es Intrinio equities_edge (consolidado) y el JSON lo declara en 3 campos.
      PENDIENTE: la calibracion tiene 0 buckets medidos (n_eff max 9 < 30). Hacen falta ~40
      sesiones archivadas antes de que la flecha premarket pueda mover `dir`.
- [ ] PENDIENTE DERIVADO: seguir archivando premarket no consolidado a diario (falta el
      launchd de premarket_unconsolidated.py tras el cierre) hasta llegar a n_eff>=30.
- [ ] PENDIENTE DERIVADO: Intrinio equities_edge iba 16 min detras a las 09:12 del 2026-08-07
      (medido contra su propia API). Si eso es cronico, la flecha premarket nunca sera
      "usable" por el portero de edad: o se sube el umbral con motivo, o se busca fuente.
- [x] "chances of SPY going down in opening / review again with full depth" (2026-08-07) — hecho.
      Workflow 9 agentes (flujo, gamma, base rates, macro, tecnico + 3 escepticos incl. auditor
      de metodo) -> docs pendiente, resultado en el journal wf_5d9de5b7-5f4.
      CORRECCION MATERIAL que encontro el auditor: publique 45% midiendo "rojo contra la
      APERTURA" sin declararlo. Contra el CIERRE PREVIO (lo que significa "en rojo") = 12,8%
      [8,5-19,0] n=156, ajustado a 11%. Y el 45% NO MIDE NADA: P(SPY rojo en CUALQUIER ventana
      de 30 min) = 47,85% n=179.056 -> condicionar por gap no separa del incondicional.
      Tambien: el 36,4% de los viernes es pesca (p=0,268, no pasa BH-FDR), y el "-0,18% de
      minimo medio" era la cola izquierda de una distribucion simetrica (maximo medio +0,20%).
      VALIDACION EN VIVO de la doctrina: 3 señales tentadoras, 3 trampas, 0 operaciones,
      0 perdidas. (a) 09:57 pinchazo a 770,51 SIN cierre debajo -> print-o-nada lo veto;
      (b) 10:11-10:12 dos cierres bajo 770,63 = ruptura confirmada, pero entrada 770,55 ya
      perdida y R:R 0,65:1 -> se exigio retest-rechazo; el retest (10:15 H770,72) NO rechazo
      y a las 10:19 recupero 771,30 = trampa bajista, habria costado -1,5 pts; (c) 10:30
      maximo 773,35 = 6 CENTAVOS bajo el gatillo largo 773,41, rechazado por la banda alta
      diaria 773,79 justo donde la regla 1 decia mala entrada.
      Lo pronostico el estudio: netGEX +27.659 sobre absGamma 1.422.984 = 1,9% -> los dealers
      ni amortiguan ni amplifican, los stops se barren en los dos sentidos.
- [ ] AVISO: el agente de macro dijo "Michigan preliminar HOY 10:00" -> FALSO, sale el 08-14
      (segundo viernes); julio final fue 55,2 no 54,4. Verificar fechas de datos macro contra
      el calendario antes de imponer ventanas ciegas.
- [ ] "find me bargains for next week, and today 0dte, the best bearish and bullish, 5 each,
      explore options chain, uw" (2026-08-07 ~11:10) — estado: en curso. 4 listas de 5:
      0DTE bajista / 0DTE alcista / 08-14 bajista / 08-14 alcista

## 2026-08-07 23:00 — peticion nocturna (GWR muros + delta imbalance + UW menos ruidoso)
- [x] "in the new gamma war room app we have the call, put, walls, magnets which is ok, but if
      u look at ib trader u will see that we show even the smaller ones and the amount in
      millions or billions" (2026-08-07) — HECHO. GWR: `Wall` (strike + importe + PIN/TRAMP +
      intensidad), 4 muros por pata dentro de +-6% del spot, grosor/opacidad ~ |gamma|, tarjeta
      "MUROS 2o", imanes y pastillas con importe, y los que salen de escala se anuncian en el
      borde con su distancia (jamas pegados al canto). Verificado renderizando:
      "CW 775.00 +4.0B ·PIN +1.62" / "PW 770.00 -1.4B ·PIN -2.71". GWR pinta CALL WALL/PUT WALL/FLIP/MAGNET
      como lineas con SOLO el strike; ib-trader (charts/live.html:1252 fmtM) pinta CW/PW/POC con
      "+296M / -1.2B" + PIN/TRAMPILLA + grosor ∝ |gamma| + perfil por strike completo.
- [ ] "try to setup delta imbalance alert and weather to enter o exit a trade based on that
      plus the target price, search github for best skills for delta imbalances, take a look at
      these expert posts one year from now and study them, backtest them with real data, see
      what are the patterns he is using that we could also use for our alert system, go in
      depth" (2026-08-07) — HECHO, con veredicto INCOMODO y medido (docs/DELTA-IMBALANCE-2026-08-07.md).
      85 sesiones x 30 syms = 939.784 minutos. Delta crudo (seguir/fadear), apilado, absorcion,
      conviccion y relevancia: 0 de 128 celdas pasan BH-FDR, y el control negativo de la
      picadora puntua IGUAL que los patrones "buenos" = ruido. Lo unico que sobrevive es la
      divergencia sobre el delta ACUMULADO (CVD/HIRO), no sobre el incremento: largo dentro de
      divergencia bajista 48,69% vs 49,72% fuera = -1,02 pp, p=1,2e-7, CI [-1,58,-0,50].
      1 pp NO es una entrada (Wilson-LB de la expectancia sigue negativo) -> se entrega como
      VETO, con objetivo MFE p60 = 1,08 ATR y stop MAE p75 = 1,29 ATR. Motor bin/delta_imbalance
      (C++23) + keepalive; port verificado 576/576 minutos contra Python.
- [x] "review changes, make sure u https://x.com/astocks92 took a look there, its important"
      (2026-08-07) — HECHO y CORRIGE lo anterior. @astocks92 = "The Architect" (35.298 seg.),
      bio "GAMMA, delta, vanna charm analysis... NEVER CHART AGAIN". 304 posts leidos por la
      API de X con OAuth1 de config/x.env (el bearer da 401). Su "delta imbalance" (post del
      2026-08-04: "$AAPL 8/28 $315C Playing the delta imbalance") NO es flujo de delta por
      minuto: es el desequilibrio del SKEW por strike ("SKEW is pricing in inventory"),
      publicado como "call side X% / put side Y%" a $1..$6 del spot, y percentilado con el
      risk reversal 25 delta. Reproducido en scripts/skew_imbalance.py desde chain_full
      (IV+griegas medidas). Lectura deducida de su trade: COMPRA EL LADO BARATO (fadea el
      skew) — el 04-ago AAPL tenia el put mas caro (imbalance -13,1%, RR25 -4,0) y compro
      calls; AAPL 309,44 -> max 315,66. n=1, es anecdota. Solo 13 sesiones de cadenas
      archivadas: el percentil exige 30 y el script lo DICE en vez de inventarlo.
- [ ] PENDIENTE DERIVADO: graduar la hipotesis "comprar el lado barato del skew en el decil
      extremo" cuando chain_full llegue a >=30 sesiones (hoy 13; el archivo crece solo).
- [ ] "create optional widget in gamma war room to detect delta imbalances, search web how to do
      it, search github best project, skills, delta trading, imbalances, https://x.com/astocks92
      he is a goat, study him, backtest him, verify his posts, he hardly fails. see what u can
      learn from it" (2026-08-08, + captura Sierra Chart "Spotting Delta Reversal Easily" de
      @SieraChart: footprint bid×ask, celdas resaltadas, cajas de imbalances apilados) —
      en curso, workflow wf_586269e4-3b4. HALLAZGOS DE VIABILIDAD ya medidos:
      · DATABENTO VIVO (HTTP 200, key en config/feeds.env). XNAS.ITCH 2018-05-01→hoy con
        schemas mbo/mbp-1/mbp-10/tbbo/trades; DBEQ.BASIC y EQUS.MINI desde 2023-03-28;
        OPRA.PILLAR desde 2013. tbbo = trade + BBO en el instante → agresor EXACTO, que es
        justo lo que exige un footprint de verdad. Auth = basic `-u "$DATABENTO_API_KEY:"`.
      · Coste MEDIDO con metadata.get_cost: 1 día RTH de SPY tbbo (XNAS.ITCH) = $0,045.
        20 días × 2 símbolos ≈ $1,8. El backtest real es asequible.
      · X API de LECTURA = HTTP 401 (el plan de config/x.env es solo-escritura) → a
        @astocks92 hay que llegar por frontends alternativos o por el Chrome de Yunior.
      · DATABENTO **LIVE NO** — medido con venv-mit/bin/python + databento 0.82.0: los 4
        datasets devuelven "A live data license is required to access <DS>". O sea histórico
        SÍ (backtest real), tiempo real NO. Consecuencia de diseño obligada.
      · NO EXISTE CINTA COMPLETA EN CASA: data/rt_last_<SYM>.txt y data/ws_trade_<SYM>.txt son
        de UNA SOLA LÍNEA (último print), no un tape; y ni Finnhub WS /trade ni Polygon T
        traen el lado agresor. Sin agresor no hay footprint: el delta vivo tendría que salir
        de tick-rule sobre una cinta completa que HAY QUE ESCRIBIR (candidato:
        scripts/finnhub_ws_bridge.py, que ya recibe cada print y hoy solo guarda el último).
      · SÍ EXISTE una cinta FIRMADA archivada: data/prints/<fecha>/<sym>.txt.gz
        ("EPOCH PX USD DIR", DIR ±1/0), la escribe scripts/equity_prints_archiver.py desde
        data/whale_<sym>.txt del puente IBKR. Límites honestos declarados en su cabecera:
        solo ballenas ≥$50.000 (WHALE_MIN_USD), NBBO cacheado → clasificación rancia, y
        6 sesiones (2026-07-24 → 07-31, ninguna posterior porque IBKR está apagado).
- [ ] **BUG MEDIDO 2026-08-08: data/prints/ tiene 89,1% de líneas DUPLICADAS.** SPY del
      2026-07-31: 1.176.476 líneas totales / 127.693 únicas (×9,2). Hay filas repetidas hasta
      438 veces y todas las multiplicidades altas son múltiplos de 6 → el cursor de
      idempotencia (data/prints_state.json) no está cortando: el archivador re-lee y
      re-anexa la ventana de 900 s del puente en cada corrida de 120 s. Consecuencia: todo
      volumen o delta calculado sobre este archivo sale inflado ~9x y de forma NO uniforme
      (las filas que sobreviven más ventanas se duplican más → sesgo por hora del día).
      Tras deduplicar: DIR −1 46.758 / 0 32.712 / +1 48.223, o sea 25,6% indeterminados.
      CAUSA NO PROBADA: prune_whales() (ibkr_bar_bridge.py:438) SÍ es atómico (tmp+os.replace)
      y el cursor actual está consistente (state last_ep 1785530726 == max del fichero, y
      n_at_last_ep 1 == las filas en ese epoch), así que hoy no duplicaría. Pero el estado
      acumula rows=2.773.983 para SPY frente a 127.693 únicas archivadas del 07-31: se
      re-archivó muchas veces mientras el puente estaba VIVO. Sospecha principal: dos
      procesos del puente a la vez anexando al mismo whale_<sym>.txt (ya hay precedente
      medido de contención de daemons), o la rama de reset del cursor
      equity_prints_archiver.py:155-157 (`file_max < last_ep` → cursor a 0 → re-archiva la
      ventana entera).
      **NO DEDUPLICAR A POSTERIORI**: con epoch de resolución 1 s, dos prints reales de 200
      acciones al mismo precio y segundo producen una línea IDÉNTICA (verificado: 149012 USD
      a 745,06 = 200,0 acciones exactas). Un `sort -u` borraría operaciones reales. Hay que
      arreglar el PRODUCTOR (id de trade único del tick de IBKR en la línea) y considerar
      la historia ya archivada como NO APTA para volumen ni delta.
      → Para el backtest de delta imbalance esto NO bloquea: la fuente correcta es el
        histórico tbbo de Databento, con lado sellado por el exchange.
- [x] "refine UW alerts, lets make them lessannoying, try to filter out irrelevant whales based
      on total volume of shares or whales that are not backed by other whales, we only need
      strong conviction" (2026-08-07) — HECHO en scripts/uw_fleet_flow.py, daemon relanzado.
      Ritmo MEDIDO antes: 1093 pushes en 4 sesiones = ~273/sesion (uno cada 85 s de RTH).
      Cuatro porteros: (1) lado agresor obligatorio en TODAS las reglas (antes solo en la del
      premium); (2) RELEVANCIA notional/ADV$ >= 0,20% = p75 medido sobre 6.000 alertas
      archivadas (deja 51%); (3) RESPALDO: 2 contratos distintos del mismo sesgo en 20 min o se
      queda en banner (deja 14%); (4) presupuesto de voz 2/sym-hora y 14/sesion. Toda candidata
      -- cantada o no -- se archiva en data/history/<dia>/uw_fleet_flow_stream.jsonl para poder
      GRADUAR la conviccion contra el precio (hoy es doctrina medida en ruido, no en acierto).
      6 tests nuevos en tests/test_uw_fleet_flow_conviccion.py (644 -> 321 candidatas, 50% fuera).
