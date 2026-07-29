# REPO-MAP — ib-trader

Índice de firmas (clases + funciones top-level), no de lógica. Generado por extracción
grep/head, no lectura completa. Para arquitectura de flujo de datos ver `ARCHITECTURE.md`;
para reglas de trading ver `AGENTS.md`. 30 tickers de flota en `data/fleet.txt`, 35 en
`data/universe_gamma.txt` (30 + SPX XSP NDX DIA IWM, solo mapa).

## FLOTA/BOTS

### `*_signal_bot.cpp` (raíz, 21 binarios — una plantilla compartida)
Confirmado por diff (aapl vs amd, aapl vs nvda): **plantilla byte-idéntica**, solo cambian
prefijo de env var por ticker, rutas de bridge (`bars_<sym>_ibkr.txt`, `bridge_<sym>.log`),
tabla de prob (`prob_table_<sym>.txt`) y hooks de test. Defaults iguales (BB_STD 3.0,
RSI_OS 25, VOL_MULT 1.2, TARGET 4%, FLOOR 1%, TRAIL_ATR 3, STOP 3%), overridable por env.
Motor: BB(20,3)+RSI(14)+volMA(20)+ATR incrementales; BUY=capitulación armada+confirmación
RSI; SELL=target/trail/floor/EOD-flatten; V5/V6 añaden CUSUM, Supertrend(10,3),
Donchian(20), multi-TF 5m/15m, ADX, clasificador de rupturas con prob calibrada.
Dedupe por epoch contra reinyección de barras del warm-up del bridge.
Structs: Bar; V5EMA, V5MACD, V5BB, V5TF, V5TL, V5Ribbon; V6ATR, V6ADX, V6BBX, V6ST,
V6RSI, V6Swing, V6TL, V6TFA, V6Session, V6Prob, V6Armed, V6Cand.
Funcs clave: `envd()`, `candle_bull/bear()`, `whale_score()`, `nbbo_spread_pct()`,
`speak()`/`notify()`, `v5_on_bar()`, `v6_on_bar()`, `v6_emit()`, `v6_bonus()`, `main()`.
Instancias: AAPL AMD ASML DRAM EWY GLD INTC KOSPI MU NOK NVDA QQQ SAMSUNG SKHY SKHYNIX
SMH SPCX SPY TSLA TSM TXN.

### Bots Python de flota
- **scripts/afterhours_fleet_test.py** — test determinista de la flota en after-hours (26 ciclos x 300s, cero LLM). Funcs: `sh()`, `bars()`, `px_at()`, `mirror_lines()`.
- **scripts/apply_v5.py** — aplica motor v5 + renombres BUY/SELL a los 20 `*_signal_bot.cpp` (idempotente). Funcs: `renames()`, `human_name()`, `main()`.
- **scripts/apply_v6.py** — aplica motor v6 MTF a los bots C++ (hook, neutraliza v5, compila secuencial, smoke replay). Funcs: `human_name()`, `renames()`, `patch_source()`, `patch_krx_keepalive()`, `compile_bot()`, `synth_bars()`, `smoke()`, `main()`.
- **scripts/daily_fleet_plans.py** — genera plan pícaro diario por ticker (PDF+email+X drafts): overnight, muros/GEX, griegas BS, Bollinger, ballenas, Korea/Europa/futuros. Funcs: `measured_prob()`, `bs_greeks()`, `ibkr_chain_stats()`, `whale_read()`, `korea_read()`, `vx_term()`, `futures_read()`, `plan_engine()`, `x_draft()`, `make_pdf()` +3 más.
- **scripts/nvda_options_engine.py** — engine señal-solamente NVDA: GEX+flip+muros+imanes+presión de pares+stop-loss, live/backtest/shadow. Funcs: `live_decide()`, `backtest()`, `shadow()`, `_nearest_exp()`, `_assert_no_orders()`.
- **scripts/opening_plan.py** — plan de apertura por ticker: mapa 15m+muros+flujo firmado+ramas condicionales. Funcs: `bars_1m()`, `agg()`, `bb()`, `atr()`, `flow()`, `ramas()`, `build()`.

### Bots de screener (top-gainers/penny, separado de la flota de 30)
- **screener/screener_alert.cpp** — port C++ de alert_bot.py: motor de ruptura confirmada (Donchian + burst CUSUM + hold), solo señala. Structs: Cand, Track. Funcs: `quote()`, `finnhub_quote_rest()`, `read_watchlist()`, `append_signal()`, `in_window()`, `main()`.
- **screener/alert_bot.py** — vigila watchlist del día, dispara señales BUY confirmadas al humano y a la sesión Claude; nunca ordena. Funcs: `in_window()`, `notify()`, `main()`.
- **screener/bargain_hunt.py** — cacería de gangas bajo demanda: pool ancho evaluado por TradingAgents en paralelo (3 procesos, Mac 8GB). Funcs: `lane_toplosers()`, `lane_newlow()`, `lane_rsi_oversold_wide()`, `main()`.
- **screener/bargain_scan.py** — alertas de ganga en 3 carriles realtime (fleet dip / gainer dip / oversold), Finnhub/Finviz. Funcs: `_day()`, `_log_path()`, `_log()`, `_seen_today()`, `lane_fleet_dip()`, `lane_gainer_dip()`, `lane_oversold()`, `main()`.
- **screener/ibkr_data.py** — datos IBKR para el screener: spread NBBO y movimiento día previo. Funcs: `_conn()`, `spread()`, `prior_day_move()`.
- **screener/price.py** — lookup rápido (~1/seg) para watchdog top-gainer: Finnhub REST + yfinance fallback. Funcs: `_load_finnhub_key()`, `finnhub_quote()`, `usdcad()`, `last_price()`.
- **screener/research.py** — capa TradingAgents (multi-agente LLM) sobre candidatos antes de apertura, subprocess-isolado. Funcs: `_load_env_file()`, `_configure_llm_env()`, `_run()`, `research_ticker()`, `enrich_candidates()`.
- **screener/revet_watchlist.py** — re-corre vetting TradingAgents sobre watchlist ya escrita. Func: `main()`.
- **screener/scanner.py** — investigación diaria 6AM: construye/puntúa candidatos penny selectivos. Funcs: `_mcap_m()`, `prior_day_move()`, `evaluate()`, `main()`.
- **screener/sources.py** — universo de top-gainers SOLO realtime vía Finviz Elite export. Funcs: `_load_env()`, `_mcap_millions()`, `_finviz_elite_export()`, `finviz_elite_gainers()`, `finviz_elite_breakouts()`, `finviz_elite_screen()`, `top_gainer_universe()`.
- **screener/state.py** — IO compartido en disco (fuente única) para watchlist/señales/posición/interlock `armed`. Funcs: `now_iso()`, `_atomic_write()`, `is_armed()`, `notify_mac()`, `read/write_pending_ta()`, `read/write_watchlist()`, `read/write_position()`, `append_signal()`, `unconsumed_signals()`, `log_decision()`.
- **screener/test_screener.py** — ~19 tests de invariantes de seguridad (never-sell-at-loss, interlocks, IO atómico).

## PUENTES DE DATOS

- **scripts/ibkr_bar_bridge.py** — daemon TWS realtime para la flota C++: barras 1m+NBBO+ballenas, overnight IBEOS. Clase: SymState. Funcs: `run_daemon()`, `subscribe_sym()`, `make_on_bar5()`, `make_on_nbbo()`, `make_on_whale()`, `tape_subscribe()`. `TAPE_MAX=5` (línea 55) = cupo REAL de `reqTickByTickData` medido en vivo (error 10190 al 6º), solo aplica a ACCIONES (cinta QQQ/SPY/SMH captains) — HIRO confirmó 2026-07-28 que no existe en tiempo real para opciones. `ib.RequestTimeout=20` (2026-07-28, caza de bugs): sin esto `qualifyContracts` colgaba para siempre si TWS no respondía.
- **scripts/korea_bar_bridge.py** — daemon KRX realtime (SK Hynix/Samsung/KOSPI), mismo formato que la flota US. Clase: SymState. Funcs: `run()`, `subscribe_sym()`, `krx_market()`, `freshness_guard()`, `resub_all()`.
- **scripts/koru_overnight_feed.py** — NBBO overnight KORU/KORZ/SOXS/SQQQ/SOXL/TQQQ; delayed prohibido.
- **scripts/opt_chain_cache.py** — cache cadenas opciones cada ~3min a `opt_chain_<sym>.txt` para opt_quick. Clase: ChainCache. Funcs: `in_window()`, `read_nbbo()`.
- **scripts/perp_nbbo_bridge.py** — puente tonto perp_stocks.json(bybit)→`nbbo_<sym>usdt.txt`. Funcs: `write_nbbo()`, `one_pass()`.
- **scripts/perp_stock_fetch.py** — puente tonto precio/OI/spread de perps tokenizados OKX (fallback Bybit). Funcs: `fetch_okx()`, `fetch_bybit()`, `okx_valid_bases()`, `one()`.
- **scripts/bollinger_fetch30d.py** — descarga 30d de barras 1m RTH de la flota (yfinance) a cache CSV.
- **scripts/etf_weights_refresh.py** — pesos reales de holdings ETF (yfinance) → `data/etf_weights.json`, fuente única para compass. Funcs: `fleet()`, `holdings()`, `main()`.
- **scripts/fetch_bars3mo5m.py** — 3 meses de barras 5m de la flota via IBKR (fallback yfinance). Funcs: `bars_to_rows()`, `fetch_ibkr()`, `fetch_yf()`, `write_csv()`, `main()`.
- **scripts/finviz_scan.py** — multi-screen Finviz Elite, reusa parser de options_hunter. Funcs: `fetch()`, `main()`.
- **scripts/finviz_technicals.py** — technicals por ticker (Finviz v=171 + fallback yfinance) con cache. Funcs: `token()`, `parse_finviz_csv()`, `fetch_finviz()`, `fetch_technicals_finviz()`, `fetch_technicals_yfinance()`, `get_technicals()` +6 más.
- **scripts/finviz_valuation.py** — snapshot diario de valuación de la flota (Forward P/E, PEG). Funcs: `token()`, `fleet()`, `fresh_enough()`, `main()`.
- **scripts/poly_backfill_opts.py** — backfill diario de opciones a `poly_opt_bars` para IV histórica por bisección. Funcs: `db()`, `mark()`, `daily_closes()`, `ref_spot()`, `expiries()`, `contracts_for()`, `download_contract()`, `run()`, `status()`, `plan()`, `main()` +6 más.
- **scripts/poly_chain_archive.py** — archivador de cadenas con griegas/IV/OI reales (snapshot Polygon), banda adaptativa. Funcs: `spot_ibkr()`, `spot_poly_bars()`, `spot_cboe()`, `spot_of()`, `gamma_mass()`, `fetch_chain_adaptive()`, `cboe_rows()`, `to_production_text()`, `run()`, `main()`.
- **scripts/poly_client.py** — cliente Polygon con rate-limiter compartido entre procesos (5 req/60s persistido). Clases: PolygonError, RateLimiter, Polygon. Funcs: `api_key()`, `atomic_write()`, `fleet()`, `market_days()`.
- **scripts/polygon_dl.py** — descarga histórico Polygon (barras subyacente+opción) a trades.db, incremental. Funcs: `poly()`, `db()`, `last_ts()`, `dl_bars()`, `dl_opts()`, `stats()`, `main()`.
- **scripts/polygon_dl_0dte.py** — baja barras 5m de contratos 0DTE (QQQ/SPY/NVDA), reusa polygon_dl. Func: `spot()`.
- **scripts/sox_index_feed.py** — feed liviano SOX (PHLX Semis) en vivo via IBKR a `nbbo_sox.txt` cada ~5s.
- **scripts/uw_archive.py** — archiva histórico Unusual Whales (greek-exposure, 250 días) antes del trial. Funcs: `token()`, `fleet()`, `fetch()`, `rows_of()`, `latest_feed_ts()`, `write_atomic()`, `archive_one()`, `main()`.

Ver también **scripts/finviz_scout.cpp** (SEÑALES/ALARMAS, escribe `finviz_<sym>.txt` desde
Finviz Elite en tiempo real, notifica solo cambios de estado).

## SEÑALES/ALARMAS

### C++ (scripts/*.cpp)
- **scripts/compass.cpp** — la BRÚJULA: máquina de estados que fija la flecha de próximo movimiento; reemplaza la media ponderada de direction_view.py. Structs: Bar, Level, Ev, Amp, Drv, Drivers, Met, Out, DecayCell, Hist. Funcs: `metrics_of()`, `strong_enough()`, `etf_weights()`, `drivers_for()`, `nearest_level()`, `rebound_dir()`, `families()`, `vetoes_of()`, `decay_cell()`, `amplitude()`, `prob_of()`.
- **scripts/finviz_scout.cpp** — bot Finviz Elite en tiempo real, escribe `finviz_<sym>.txt`, notifica solo cambios de estado. Structs: HttpResp, SymState. Funcs: `get_token()`, `build_tickers()`, `http_get()`, `parse_earnings()`, `market_phase()`, `main()`.
- **scripts/fleet_consensus.cpp** — alarma de MANADA (port C++ del daemon Python), % siempre sobre flota completa (30) nunca sobre los que parsearon. Structs: Cfg, SymSnap, Vote, Agg, Hyst. Funcs: `load_fleet()`, `evaluate()`, `aggregate()`, `consensus_dir()`, `hyst_step()`, `fire()`, `gather()`, `ev_snaps()`.
- **scripts/flow_pulse.cpp** — detector v4 de spikes/giros de flujo con jerarquía de capitanes (SPY/QQQ mercado, SMH memoria) y "capitán revierte". Structs: Rec, Hist, Bands, ChainInfo. Funcs: `is_captain()`, `in_memory_troop()`, `captains_of()`, `prob_of()`, `bands_of()`, `chain_info()`, `sing()`, `rth_open()`, `qqq_spot()`.
- **scripts/korea_tape.cpp** — veredicto instantáneo KOSPI/Corea leyendo `nbbo_{kospi,skhynix,samsung,koru}.txt`. Struct: Q. Funcs: `read_nbbo()`, `main()`.
- **scripts/korea_watch.cpp** — vigilante nocturno KRX, máquina de estados PRINT/RECLAIM/NADIE/BAJISTA/V_ROTA/VETO/READTHRU_BEAR/FEED_MUERTO. Structs: Niveles, Q. Funcs: `prev_close()`, `rd_niveles()`, `rd()`, `speak()`, `main()`.
- **scripts/level_react.cpp** — CLI del primitivo de reacción a niveles; modos `--ev-stdin` (arnés de test) y ficheros; emite JSONL. Structs: Val, Parser. Funcs: `type_of_name()`, `print_events()`, `run_stdin()`, `load_bars()`, `last_half_spread()`, `run_files()`.
- **scripts/momentum_calc.cpp** — calculador de momentum/trampas contra umbrales medidos. Structs: Bar, Thresh. Funcs: `load_bars()`, `load_thresh()`, `median()`, `main()`.
- **scripts/price_alarm.cpp** — watcher de alarmas de precio (loop 4Hz, <=250ms), lee price-alerts.txt + NBBO/bars. Struct: Rule. Funcs: `alerts_path()`, `parse_rule()`, `ensure_seed()`, `px_from_nbbo()`, `px_from_bars()`, `current_price()`, `mark_fired()`, `fire()`.
- **scripts/qqq_xray.cpp** — radiografía instantánea de QQQ por componentes (dique MSFT+AAPL vs semis) en <50ms. Structs: Bar, Member, Snapshot. Funcs: `read_bars()`, `prev_close_of()`, `trend_of()`, `rvol_of()`, `load_member()`, `notify()`, `build()`, `print_snapshot()`.

### Python
- **scripts/force_meter.py** — fuerza en vivo + agotamiento por fase (IMPULSO/MADURO/AGOTAMIENTO/GIRO) normalizado por ATR. Funcs: `measure()`, `rsi()`, `run()`, `load_bars()`.
- **scripts/gaps.py** — huecos overnight/intradía, registro sin rellenar, gap_proximity, cortes de isla; p_fill NUNCA se computa. Funcs: `detect_overnight_gaps()`, `detect_intraday_discontinuities()`, `island_cuts()`, `build()`, `validate()`.
- **scripts/index_breadth.py** — engranaje: QQQ/SPY heredan dirección de componentes pesados, amplitud ponderada en vivo. Funcs: `component_lean()`, `breadth()`, `latest_close()`.
- **scripts/inflation_score.py** — score continuo [-1,1] de cuán inflada está cada empresa (Fwd P/E+PEG, z-score sectorial). Funcs: `compute()`, `group_of()`, `load_valuation()`.
- **scripts/kde_levels.py** — niveles KDE gaussiano 1m/5m/15m, tope 5/TF, consciente de islas, cede a muros OI/capitán. Funcs: `kde_levels()`, `aggregate()`, `peak_prominences()`, `bounce_stats()`, `deathtest()`.
- **scripts/macro_calendar.py** — CPI/FOMC/NFP confirmados (sin relleno adivinado). Funcs: `load_confirmed()`, `macro_events_near()`.
- **scripts/opt_sentinel.py** — centinela exit-advisor de posición puntual + flujo put/call de la flota cada 5min. Funcs: `call_premium()`, `call_pnl_voice()`, `rule()`, `shout()`.
- **scripts/opt_whale_watch.py** — vigía de ballenas de opciones, P/C≥2.0 puts / ≤0.35 calls con histéresis. Funcs: `fetch_chain()`, `get_spot()`, `load_chain_cache()`, `loud()`, `scan_symbol()`, `dominant_strike()`, `wall_near()`, `load_symlist()`, `load_ticker_filter()`, `save_state()`. v4 (2026-07-28): mensaje "Alerta ballena…" (ratio P/C) distinto de "Alerta premium…" (barrida UW, antes compartían texto y confundían); strike dominante + cruce con muro medido en `data/gex_snapshot.json`; 2 lecturas consecutivas antes de sonar (señal marginal ≠ decisiva); carril rápido opcional `data/whale_priority.txt` (≤5, `reqMktData` cada 45s, NO tick-by-tick); filtro opcional `data/whale_alert_filter.txt` (CALLS/PUTS/BOTH por ticker); `ib.RequestTimeout=15` (causa raíz del cuelgue cerca de GLD). Ambos configs ajustables en vivo desde el panel 🐋 Config de `charts/live.html` (sin reiniciar el proceso).
- **scripts/options_enrich.py** — overlay solo-lectura: arma contrato ATM 0-2DTE con delta~0.55+greeks por señal BUY/SELL. Funcs: `enrich()`, `daemon()`, `parse_title()`, `connect_retry()`.
- **scripts/options_hunter.py** — cazador manual de candidatos opcionables líquidos+volátiles (no en keepalives). Funcs: `fetch()`, `parse()`, `auth()`.
- **scripts/pattern_detect.py** — detector geométrico H&S/dobles/triángulos sobre zigzag + win-rate medido histórico. Funcs: `det_head_shoulders()`, `det_double()`, `det_triangle()`, `scan_history()`, `zigzag()`, `detect_active()`.
- **scripts/peer_influence.py** — influencia cruzada medida: beta×corr×lead-lag desde poly_bars, autocalibrado. Funcs: `compute()`, `pressure()`, `save()`, `load_weights()`.
- **scripts/band_open_watch.py** — apertura fuera de bandas Bollinger 15m RTH tiende a volver dentro (prob medida 60/36). Funcs: `fleet()`, `say()`, `bars_of()`, `vol_confirm()`, `bb15_prev_rth()`, `main()`.
- **scripts/bollinger_alarm.py** — vigía Bollinger intradía: PIERCE/RE-ENTRADA elástica vs BAND-WALK. Funcs: `prob_info()`, `log_only()`, `fleet()`, `say()`, `bars_of()`, `bb_context()`, `bb()`, `agg_tf()`.
- **scripts/candles.py** — patrones de velas japonesas (doji/martillo/engulfing/harami/tweezer/estrella) como CONTEXTO. Funcs: `load()`, `_feat()`, `trend()`, `detect()`, `read()`, `main()`.
- **scripts/confluence_engine.py** — motor multi-herramienta (BB/RSI/MACD/velas/trendline/volumen/VWAP), señal si ≥2 alinean. Funcs: `load5m()`, `aggregate()`, `rsi_series()`, `atr_series()`, `votes_for_series()`, `gen_signals()`, `scalp_score()`, `wilson()`, `main()` +4 más.
- **scripts/cor_fleet.py** — correlación Pearson (QQQ/SMH) que amortigua pesos capitán vs nombre. Clase: CorFleetError. Funcs: `mean_pairwise_rho()`, `percentile_of()`, `classify()`, `session_rho()`, `build_history()`, `kill_test()`, `compute_live()`, `captain_damper()`, `apply_damper()`, `main()` +5 más.
- **scripts/dip_alert.py** — alerta de dip técnico con gate de valuación y veto por band-walk bajista 5m. Funcs: `fleet()`, `say()`, `load_valuation()`, `load_probs()`, `bandwalk_down_5m()`, `intraday_high()`, `valuation_verdict()`, `load_alerted()`, `main()` +4 más.
- **scripts/dram_guard_today.py** — guardián de DRAM/memoria (MU/SNDK/WDC/STX/SKHY/LRCX+SMH), confluencia con histéresis. Funcs: `say()`, `chg5m()`.
- **scripts/fleet_consensus.py** — alarma de MANADA en Python (predecesora del port C++): dispara DANGER cuando capitanes+% flota coinciden. Funcs: `_pb()`, `snapshot()`, `consensus_dir()`, `fire()`, `main()`.
- **scripts/fleet_pulse.py** — pulso de la flota completa por ciclo, imprime solo movimientos >0.35% o extremos.
- **scripts/posthours_cage.py** — detecta jaula 0DTE (rango realizado << implícito) y liberación post-market hacia ballenas semanales. Funcs: `next_friday_exp()`, `analyze()`, `_load_fleet()`, `main()`.
- **scripts/qqq_breadth.py** — radar de amplitud QQQ: breadth, divergencia y líderes/rezagados vs VWAP. Funcs: `load()`, `main()`.
- **scripts/signal_conditioning.py** — condiciona probabilidad de señal por hora/dirección-flota/inflación; apaga celdas muertas. Funcs: `component_bias()`, `captain_flow_bias()`, `fleet_bias()`, `governing_captain()`, `conditioned_prob()`, `_cli()`.
- **scripts/uw_premium.py** — premium neto por lado en vivo (UW net-prem-ticks) para opt_whale_watch v2. Funcs: `token()`, `fetch_net_prem_ticks()`, `signed_premium()`, `latest_feed_age_s()`.
- **scripts/vw_drops.py** — series OHLC ponderadas por volumen tipo "raindrop" (vwap izq/der/mass, migración, %B). Funcs: `_vwap()`, `raindrop()`, `migration_live()`, `rolling_pctb()`, `validate()`, `build_live()`, `main()` +5 más.

### Motores standalone (engines/)
- **engines/bb_engine.cpp** — MOTOR 2 (B7) CLI solo-Bollinger, `--backtest`/`--live` (tail de `bars_<sym>_ibkr.txt`). Funcs: `load_config()`, `load_bars()`, `run_backtest()`, `run_live()`, `main()`.
- **engines/combo_engine.cpp** — MOTOR 3 (B8) CLI Bollinger+FLUJO fusionado sin look-ahead; sin flujo no hay señal. Funcs: `load_bars()`, `load_flow()`, `fmt_et()`, `run_backtest()`, `run_live()`, `main()`.
- **engines/bb_core.h** — núcleo Bollinger header-only: BB(20,2) O(1), %B, bandwidth percentil, elastic pierce+reentrada, band-walk, squeeze-break. Structs: Bar, BB, BWPct, ATR14, TFAgg, ElasticEvent, Elastic, BandWalk, Signal, Config, Engine.
- **engines/combo_core.h** — combo Bollinger+flujo con jerarquía de capitanes (regla 12): elastic LONG requiere ausencia de spike-calls propio y del capitán. Structs: FlowRec, FlowBook, ComboStats, ComboEngine.

## CHART/COCKPIT

- **charts/live.html** — cockpit vivo del chart (2766 líneas): candelas+ribbon+GEX+zonas+ficha 0DTE sobre lightweight-charts v5, alimentado por WebSocket. Clases JS: `BubbleView`/`WallBubbles` (burbujas de muros OI), `GexView`/`GexProfile` (perfil GEX overlay). Funcs por bloque: init (`setRibbon()`, `updRibbon()`, `candleAutoscale()`, `mkLine()`, `barIndexFor()`); señales (`clusterSignals()`, `applyMarkers()`); niveles/muros (`wallIntensity()`, `drawLevels()`, `bubbleRows()`); trendlines (`drawTrendline(s)()`); header/OHLC (`fmtBig()`, `setSourceBadge()`, `drawHeader()`, `setOHLC()`); zoom/TF (`setShowBars()`, `zoomRecent()`, `setActiveTf()`); watchlist (`switchSymbol()`, `syncSymSel()`, `renderWatchlist()`, `liveQuoteTick()`); cuenta paper/live (`onIbMode()`, `reqAccount()`, `sendAction()`, `onOrderAction()`); narrador (`onNarrator()`, `onStructural()`); zonas/alarmas/stop arrastrable (`hitAtY()`, `zoneStopAtY()`, `moveStopLine()`, `drawZones()`, `renderChips()`); ficha 0DTE (`reqProb()`, `onProb()`, `onEngine()`, `onTicket()`); brújula (`dirVar()`, `onDirection()`); countdown (`tfSeconds()`, `fmtCountdown()`, `tickPriceAge()`); WS pipeline (`connect()`, `onHistory()`, `onBackfill()`, `mirrorBar()`, `onTick()`, `onBar()`, `onLevels()`); widgets acoplables Technicals/GEX-por-strike/Premarket/Flow (`techDraw()`, `wgApply()`, `wgDrag()`, `wgexDraw()`).
- **charts/index.html** — visor liviano alternativo (132 líneas), solo 13 símbolos fijos, sin zonas/órdenes/widgets.
- **charts/symbols.json** — lista de 13 tickers que alimenta `index.html`.
- **charts/lightweight-charts.js / lightweight-charts-v5.js** — librería vendorizada (Apache-2.0), no es código propio.
- **macapp/main.swift** (398 líneas) — envoltorio nativo Swift+WKWebView del cockpit (no Electron, por RAM 8GB). Multi-ventana, cada ventana = un puerto = un símbolo. Clases: `CockpitWindow` (NSWindowDelegate/WKNavigationDelegate), `AppDelegate` (arranque, menú, tiling). Funcs: `load()`, `installRefreshButton()`, `targetURL()`, `startupURLs()`, `nextFreeURL()`, `applicationDidFinishLaunching()`, `installMainMenu()`, `openWindow()`, `tile()`, `savedZoom()`/`setZoom()`, `openSettings()`.
- **macapp/Settings.swift** (427 líneas) — panel de configuración embebido; guarda en `~/Library/Application Support/ib-trader/config.json` con la misma precedencia que el motor C++ (env → config.json → account.txt). Tipos: `enum RepoSource`, `struct Resolved`, `struct Config: Codable`, `struct Prefill`, `class SettingsWindow`. Funcs: `pretty()`, `envFile()`, `accountFile()`, `Config.load()/save()`, `account(live:)`, `secret()`, `port()`, `build()`, `saveCfg()`, `revealCfg()`.
- **macapp/** otros: `build.sh`/`bundle_backend.sh`/`rebuild_hook.sh`/`install_hooks.sh` (empaquetado), `appfresh.sh`, `icon/`, `ib-trader Cockpit.app` (bundle compilado) — infraestructura de build, no lógica.
- **scripts/gen_charts.py** — genera `charts/data/<sym>.json` (velas 1m 90d + operaciones marcadas) para el visor. Funcs: `gen()`, `main()`.
- **scripts/narrator.py** — narrador tipo gexa del cockpit: capa determinista gratis + pulido DeepSeek bajo throttle, señal-solamente. Funcs: `deterministic()`, `structural_signal()`, `deepseek()`, `trigger_key()`.
- **scripts/opening_plan_html.py** — hoja HTML diaria de apertura: gráfico 15m SVG + árbol + muros + flujo firmado. Funcs: `candles_svg()`, `sheet()`, `usd()`, `oi()`.
- **scripts/chart_bridge.py** — puente realtime WebSocket para el chart (FastAPI/uvicorn), señal-solamente, jamás coloca órdenes. Clase: State. Funcs (~90): `assert_signal_only()`, `load_ibkr_bars()`, `compute_indicators()`, `load_levels()`, `load_signal_markers()`, `load_engine_ops()`, `alarm_add()`, `zone_add()`, `build_ticket()`, `read_compass()`, `whale_cfg_status()` +~80 más. Puerto real 8080 por defecto (`--http-port`), no confundir con números de línea citados alguna vez en TODOS.md. `cmd:"whale_cfg"` (WS `/stream`, patrón igual a `cmd:"ibmode"`) escribe `data/whale_priority.txt`/`data/whale_alert_filter.txt` desde el panel 🐋 Config de `charts/live.html` — los lee `opt_whale_watch.py`.
- **scripts/direction_view.py** — flecha direccional compuesta (flip/muros/GEX/flota/momentum/inflación/imán), score y prob medida por bucket. Funcs: `_measured_prob()`, `_calib_context()`, `_bars_mom()`, `_pctb()`, `book_coef()`, `compute()`, `_cli()`.
- **scripts/ui_cdp.py** — driver CDP mínimo (arnés de test, cero cómputo de señal) para el bucle de feedback visual. Clases: CDP, Results. Funcs: `launch_chrome()`, `dir_msg()`, `main()`.
- **scripts/watchlist_stats.py** — estadísticas tipo TradingView para la watchlist del cockpit (Finnhub+IBKR). Funcs: `finnhub_quote()`, `ibkr_today_volume()`, `finviz_cache()`, `stats_for()`, `build()`, `run_once()`, `main()` +3 más.

## OPCIONES/GEX

- **scripts/gate.cpp** — EL GATE DE OPCIONES, fuente única de verdad (misma cabecera que order_engine); modos SONDEO y FICHA. Struct: Ev. Funcs: `to_json()`, `human()`, `write_atomic()`, `ev_from_json()`, `main()`.
- **scripts/opt_quick.cpp** — lector instantáneo del cache de cadena (v6.1): P/C, muros OI+vol, max pain, gates spread≤5%/OI>500. Struct: Row. Funcs: `max_pain()`, `pc_line()`, `main()`.
- **scripts/volume_profile.cpp** — POC de VOLUMEN (complemento al POC de GAMMA de gex_snapshot.json); cruce como descripción, no probabilidad. Structs: Bar, Profile, GammaRef. Funcs: `write_atomic()`, `main()`.
- **scripts/gex_core.py** — fuente única GEX/gamma-flip/muros put-call, BS/IV/vanna/charm, parity audit. Funcs: `build_gex()`, `build_dex()`, `flip_recompute()`, `regime_at()`, `wall_context()`, `pin_risk_score()`, `from_ibkr_cache()`, `invert_chain_iv()` +15 más.
- **scripts/gex_gate.py** — gate GEX en vivo: régimen local+proximidad a muros/flip → APTO/DEGRADAR/VETO. Funcs: `gate()`, `spot_from_cache()`.
- **scripts/gex_snapshot.py** — mapa gamma de la flota calculado en casa (sustituye gexa.ai): flip/GEX/muros/POC/régimen. Funcs: `snapshot_sym()`, `build()`, `latest_chain()`, `honest_flip()`, `pick_source()`, `contracts_from_tws()`.
- **scripts/gexa_parse.py** — parser de texto gexa.ai (via Chrome) a JSON: flip, dealer pressure, imanes institucionales. Func: `parse()`.
- **scripts/pin_clock.py** — max pain estructural descriptivo, único nivel útil en NOK/DRAM/SPCX/SKHY. Funcs: `pain_profile()`, `max_pain_of()`, `pin_clock()`, `oi_within()`, `colinearity()`.
- **scripts/book_quality.py** — veto multiplicativo por calidad de libro de opciones (coef 0-1) sobre pesos gamma de direction_view. Funcs: `atomic_write()`, `adv20()`, `percentile()`, `usable_greeks()`, `chain_full_map()`, `provenance()`, `evaluate()`, `measure()`, `run()`, `main()` +5 más.
- **scripts/chain_cube_archive.py** — índice/retención/lector reutilizable del cubo de cadenas (IBKR texto + Polygon json). Funcs: `parse_ibkr_text()`, `parse_polygon_json()`, `read_chain()`, `build_index()`, `bundle_day()`, `gzip_full_chains()`, `retention()`, `du_report()`, `main()` +10 más.
- **scripts/chart_levels.py** — genera `levels_<sym>.json` (GEX/flip/muros) desde cache IBKR via gex_core, sin red. Funcs: `_freeze_clock()`, `_asof_of()`, `spot_from_cache()`, `poly_chain_path()`, `freeze_decision()`, `_frozen_flip()`, `gen()`, `main()`.
- **scripts/em_envelope.py** — valla del día (expected move) via straddle ATM capturado <=15:55, consciente del calendario. Funcs: `is_market_day()`, `next_market_day()`, `target_session()`, `quote_snapshot()`, `front_expiry()`, `atm_straddle()`, `iv_atm_from()`, `envelope()`, `write_envelope()`, `main()` +2 más.
- **scripts/fetch_option_walls.py** — muros OI por strike via TWS local (fallback del MCP roto). Func: `main()`.
- **scripts/skew.py** — risk reversal 25-delta (IV put−call); corrobora techo/piso de un print de ballena. Funcs: `load_chain()`, `interp_iv_at_delta()`, `rr_for()`, `rr_history()`, `zscore()`, `main()`.
- **scripts/tree_sheets.py** — árbol de niveles/muros por ticker: supervivientes semana pasada + libro actual + cadena expira viernes. Funcs: `next_friday()`, `last_week_walls()`, `oi_by_strike()`, `touch_stats()`, `build()`, `main()`.
- **scripts/tree_sheets_html.py** — hojas HTML de `data/trees/*.json` (perfil SVG, ladder, árbol de ramas, supervivencia). Funcs: `fleet_touch_curve()`, `profile_svg()`, `ladder()`, `tree()`, `surv_table()`, `friday_table()`, `sheet()`, `main()` +2 más.
- **scripts/uw_gex_compare.py** — referee GEX/DEX propio vs Unusual Whales, pata por pata con scope declarado. Funcs: `our_legs()`, `uw_legs()`, `compare_sym()`, `spearman()`, `main()`.
- **scripts/uw_oi_delta.py** — clasifica flujo de ayer (abre/cierra) via volumen vs ΔOI, estrictamente día-sobre-día. Funcs: `prev_market_day()`, `oi_asof()`, `classify()`, `from_uw()`, `from_polygon()`, `main()`.
- **scripts/vol_trigger.py** — interruptor "licencia-para-fadear" congelado a 09:35 (VT): reversión vs momentum según spot vs vt_open. Funcs: `strike_width()`, `vt_from_profile()`, `freeze_decision()`, `gen()`, `main()`.
- **scripts/wall_decay.py** — ledger de decaimiento real de muros por número de toque. Funcs: `wilson()`, `n_effective()`, `tally()`, `cell()`, `build()`, `main()`.
- **scripts/whales_week_map.py** — mapa de ballenas para el resto de la semana: muros OI, max pain, P/C, régimen gamma. Funcs: `live_spot()`, `whale_alert_bias()`, `analyze()`, `verdict()`, `main()`.

## VOZ/NOTIFICACIONES

- **scripts/x_whale_bot.cpp** — post diario en X sobre semis/ballenas bajo budget duro $5/mes. Structs: Budget, Row, XAuth. Funcs: `load_budget()`, `save_budget()`, `posts_today()`, `fetch_finviz_live()`, `score_rows()`, `compose_post()`, `oauth1_header()`, `http_post_json()`.
- **scripts/make_fire_alarm.py** — genera `sounds/fire_alarm.wav` sintético (barrido 600-1200Hz+vibrato), solo stdlib. Func: `main()`.
- **scripts/voice_budget.py** — presupuesto de alarmas SIGNAL (DANGER/INFO intactos), racionamiento diario. Funcs: `caps()`, `decide()`, `record()`, `flush()`, `publish()`, `prune_spend()`, `check_registry()`, `main()` +6 más.
- **scripts/x_earnings_post.py** — calendario PNG de earnings semana siguiente (Finviz Elite) + tweet picaro. Funcs: `fetch_csv()`, `parse_csv()`, `merge()`, `score()`, `render_calendar()`, `build_tweet_text()`, `main()` +8 más.
- **scripts/x_plan_poster.py** — publica en X los TOP-N drafts de los planes diarios de flota. Funcs: `load_budget()`, `save_budget()`, `posts_today()`, `main()`.
- **scripts/x_post_common.py** — post/ledger compartido para todos los posters de X (OAuth1, cap duro 10/día $4/mes). Funcs: `load_budget()`, `posts_today_all()`, `make_auth()`, `upload_media()`, `gex_line()`, `post_text()` +4 más.
- **scripts/x_postmortem.py** — repaso honesto del día en X: califica cada plan contra el OHLC real. Funcs: `parse_draft()`, `day_ohlc()`, `grade()`, `build_post()`, `append_doc()`, `main()`.
- **scripts/x_signal_poster.py** — daemon que postea señales fuertes de la flota (prob≥70 o ballena≥3:1), límites estrictos. Funcs: `qualifies()`, `extract_levels()`, `build_post()`, `process_signals()`, `process_combos()`, `main()` +3 más.
- **scripts/xpost.py** — herramienta reutilizable de post on-demand a X (texto/imagen/draft), reusa x_post_common. Func: `main()`.

## EJECUCIÓN (order_engine + scalper)

Único módulo autorizado a operar en TWS. Doble llave (`--arm-live` + `ARM_LIVE` fecha de
hoy) + disarm-on-exit; PAPER(7497) default, LIVE(7496) opt-in; clientId 92.

- **order_engine/order_engine.cpp** — main: zone-watcher que vigila NBBO local contra zonas pintadas (`data/exec_zones_<sym>.json`), gate (spread≤5%, OI>500, prima≤budget, cadena fresca), FSM PLACED→TRIGGERED→SENT→FILLED→STOP_HIT. Structs: JVal, JParser, ZoneRT, Cfg. Funcs: `last_close()`, `eps_of()`, `crossed()`, `write_state()`, `shout_naked_stop()`, `port_open()`, `resolve_port()`, `main()`.
- **order_engine/tws_adapter.h/.cpp** — `TwsAdapter : DefaultEWrapper`, único adaptador que coloca órdenes reales (EReaderOSSignal/EClientSocket/EReader). Structs: OptContract, OptQuote, ExecReport. Funcs: `connect()`, `reconnect()`, `pump()`, `reqPositions()`, `place_limit()`, `place_stop()`, `cancel()`, `modify()`, `cancel_all_own()`, `reconcile()`, `poll()`, `nextValidId()`, `orderStatus()`, `execDetails()`, `commissionReport()`.
- **order_engine/account_cfg.h** — resuelve cuenta esperada (env → config.json de la .app → data/account.txt), fail-closed sin cuenta configurada. Funcs: `cfg_trim()`, `json_str_field()`, `expected_account()`.
- **order_engine/chain.h** — cadena de opciones + gate de tamaño/liquidez, puros/testeables (cierra bug del centinela delta=-1.0). Structs: ChainRow, Chain, Gate. Funcs: `load_chain()`, `run_gate()`.
- **order_engine/guards.h** — decisiones de seguridad de dinero puras (nunca 0/0.5 como "adelante"). Structs: ExposureBook, StockEntry, PosKey, PositionBook, CloseDecision, NakedDecision, StopRef, CloseReq, OrphanCancel. Funcs: `accounts_match()`, `decide_stock_entry()`, `decide_close_qty()`, `clamp_option_stop()`, `decide_stop_failure()`, `safe_to_touch_orders()`, `option_stop_trigger()`, `stops_orphaned_by_close()`.
- **order_engine/ledger.h** — libro JSONL append-only (`ledger/orders.jsonl`); P&L neto casado execId→commission real. Clase: Ledger. Funcs: `intent()`, `ack()`, `fill()`, `cancel()`, `reject()`, `commission()`, `note()`, `flush()`.
- **order_engine/safety.h** — doble llave + disarm-on-exit (SIGINT/SIGTERM/crash/atexit → cancel_all_own+flush). Clase: Guard. Funcs: `today_date()`, `armed_live()`.
- **order_engine/paper_soak.py** — soak de 30+ órdenes reales contra gateway PAPER (bug auto-cancel/stop huérfano solo aparece con órdenes reales). Funcs: `die()`, `build_zones()`, `main()`.
- **order_engine/prob_profit.py** — overlay de probabilidad de profit (chip junto al icono buy): 4 capas medidas (gamma/flujo/técnico/agentes). Funcs: `_clamp()`, `_dfav()`, `_days_to_exp()`, `_measured_prob()`, `_gamma_component()`, `_flow_component()`, `_tech_component()`, `_agents_component()`, `prob_profit()`, `_cli()`.
- **order_engine/prob_profit_test.py** — smoke test sin red, stubbea chart_levels/narrator/direction_view/signal_conditioning para verificar vetos de doctrina. Funcs: `check()`, `_stub()`.
- **order_engine/smoke_paper.py** — prueba independiente de place/cancel de opciones en PAPER vía ib_insync. Funcs: `_paper_acct()`, `die()`, `main()`.
- **scripts/optgate.py** — envoltura fina Python del gate C++ (`bin/gate --json`) para spread de opciones antes de alarma/orden. Funcs: `gate_json()`, `opt_gate()`, `opt_ok()`, `opt_veto()`, `opt_vehicle()`.
- **scripts/order_ticket.py** — ficha de orden 0DTE para clic humano en IBKR: contrato+límite+size+OI+prob condicionada+veredicto GO/CAUTION/NO-GO. Funcs: `build()`, `_parse_chain()`.
- **scripts/cancel_all_bot_orders.py** — cancela TODAS las órdenes abiertas (GTC/OCA) que ejecutores retirados dejaron vivas (ley "solo señales"). Script plano, conecta ib_insync.

### scalper/ — whale scalper 0DTE QQQ (SIM/shadow-only)
- **scalper/whale_scalper.cpp** — motor 0DTE QQQ de la táctica espada-ballena, SIM-first (`--replay`/`--sim`); LIVE exige `--arm-live` (Fase 4 aún no existe). Structs: RealClock, FeedClock. Funcs: `run_actions()`, `synth_chain()`, `run_replay()`, `run_sim()`, `main()`.
- **scalper/exec_adapter.h** — interfaz `ExecutionAdapter` única; SimAdapter completo/determinista; TwsAdapter = stub Fase 4. Struct: ExecReport. Clases: ExecutionAdapter, SimAdapter, TwsAdapter.
- **scalper/ledger.h** — libro append-only JSONL (O_APPEND+fsync); recovery detecta posición viva al arrancar. Clase: Ledger.
- **scalper/scalper_core.h** — núcleo puro: FSM, dinero en int64 cents, selección de contrato, parsers JSONL/txt, gates, Black-Scholes, Clock. Structs: Cfg, Clock, SimClock, Nbbo, ChainRow, Chain, OptContract, OptQuote, Alert, Selection, Action, Inputs. Clase: Fsm. Funcs: `cfg_set()`, `profit_reached()`, `norm_cdf()`, `bs_price()`, `parse_nbbo()`, `parse_chain()`, `parse_alert_jsonl()`, `spread_ok()`, `select_contract()`.
- **scalper/tail.h** — tail incremental por offset: arranca en EOF, salta a EOF si el fichero rota/encoge. Struct: Tail.
- **scalper/backtest_whale_scalp.py** — backtest honesto de la táctica espada-ballena: fade a +1/+2/+5/+15min, P&L 0DTE vía Black-Scholes. Funcs: `N()`, `bs()`, `wilson()`, `load_bars()`, `load_alerts()`, `main()`.
- **scalper/mock_gen.py** — fábrica de escenarios sintéticos JSONL (pop_pullback, band_walk, whipsaw, flat, etc). Funcs: `w()`, `preamble()`, `path()`, `pop_pullback()`, `band_walk()`, `whipsaw()`, `flat()`, `pullback_lento()`, `main()`.
- **scalper/shadow_report.py** — compara operaciones sombra del ledger contra el gráfico real de barras 1m QQQ. Funcs: `load_bars()`, `main()`.
- **scalper/sim_feed.py** — replay REALTIME de un día real con ticks sub-minuto (puente browniano) para `--sim`. Funcs: `load_bars()`, `load_alerts()`, `bridge_ticks()`, `main()`.

## BACKTEST/CALIBRACIÓN

- **scripts/replay.cpp** — gateway IBKR falso: simula el disco (bars/nbbo/levels/chains) con reloj virtual para correr la flota real sobre historia sin tocarla. Structs: Rng, Bar, Db, Feed, Snap, WalkRow. Funcs: `sandbox_guard()`, `levels_copy()`, `patch_levels_spot()`, `levels_synth()`, `scan_chains()`, `append_bar()`, `publish_chain()`, `apply_hyst()`, `bridge_ticks()`.
- **engines/tests/bb_test.cpp** / **combo_test.cpp** — ver sección TESTS.
- **scripts/backtest_bargain_week.py** — backtest de candidatos del bargain hunter contra retorno forward real. Funcs: `closes()`, `stats()`.
- **scripts/backtest_harness.py** — win rate CON COSTE sobre etiquetado de triple barrera. Funcs: `cost_in_atr()`, `net_payoff()`, `net_stats()`, `load_cells()`, `verdict_of()`, `run_net()`, `run_compare()`, `run_propose()`, `run_baseline()`, `main()` +4 más.
- **scripts/backtest_replay.py** — harness de re-tuning: bars reales de Alpaca → bots C++ via `--stdin`. Funcs: `fetch()`, `run()`.
- **scripts/barrier_labels.py** — etiquetado de TRIPLE BARRERA (arregla denominador de todas las probs de la flota). Funcs: `true_range()`, `wilder_atr()`, `triple_barrier()`, `purged_folds()`, `label_all()`, `write_rows()`, `aggregate()`, `best_cell()`, `scoreboard()`, `main()` +20 más.
- **scripts/bollinger_backtest.py** — réplica exacta de bollinger_alarm sobre 30d de barras. Funcs: `load_bars()`, `by_day()`, `bb()`, `agg_tf()`, `wilson_lb()`, `detect_day()`, `measure()`, `run_config()`, `main()`.
- **scripts/bollinger_complements.py** — misión B6: complementos Bollinger con FDR y Wilson. Clases: Wilder, ADX. Funcs: `clusters()`, `n_efectiva()`, `wilson()`, `bb_pop()`, `run_ticker()`, `analyze()`, `sobrevive()`, `write_outputs()`, `emit_grid_md()`, `main()` +8 más.
- **scripts/calibration_ledger.py** — registra plan/señal, califica contra resultado real, prob empírica por bucket (setup_type×régimen). Funcs: `wilson()`, `record()`, `record_from_ranking()`, `grade()`, `calibrate()`, `wilson_lb_expectancy()`, `calibrate_barrier()`, `report()`, `main()`.
- **scripts/compass_calibrate.py** — calibra la brújula C++ contra barras reales a +15/30m, escribe compass_calib.json. Funcs: `wilson_lo()`, `load_bars()`, `close_at()`, `main()`.
- **scripts/conditioned_backtest.py** — demuestra lift de selectividad: RAW vs SIN-MUERTAS vs SELECTIVO. Funcs: `load()`, `wr()`, `main()`.
- **scripts/dip_backtest.py** — backtest honesto de señal de dip (barras diarias 1 año), sin gate intradía. Funcs: `fleet()`, `median()`, `backtest_one()`, `main()`.
- **scripts/eod_backtest.py** — backtest EOD de señales del día (whale/flow/dip/bollinger/structural/cusum) vs precio real. Funcs: `load_bars()`, `price_at()`, `window()`, `bb_pctb()`, `wilson()`, `thesis()`, `extract_symbol()`, `main()`.
- **scripts/eod_signal_validation.py** — valida señales del día contra tape SIP. Funcs: `load_bars()`, `px_at()`, `hhmmss_to_epoch()`, `main()`.
- **scripts/equity_prints_archiver.py** — salva la cinta firmada antes del prune a 900s, archivador solo-lectura. Funcs: `atomic_write_json()`, `append_lines()`, `parse_line()`, `new_lines()`, `archive_once()`, `coverage()`, `retention()`, `main()` +2 más.
- **scripts/fleet_backtest_audit.py** — backtest full-fleet de los bots C++ (bars Alpaca via `--stdin`), WR/PF/train-OOS. Funcs: `load_keepalive_env()`, `fetch_one()`, `parse_run()`, `summarize()`, `run_one()`, `regen_pos()`, `print_report()`, `main()`.
- **scripts/fleet_optimize.py** — coordinate-descent de re-tuning full-profit por ticker/lado. Clase: Runner. Funcs: `side_metrics()`, `grids()`, `descend()`, `fmt()`, `main()`.
- **scripts/fleet_wfo.py** — walk-forward optimization v2 (train/OOS 60/40, test de meseta). Clase: WFORunner. Funcs: `full_math()`, `entry_grids()`, `exit_grids()`, `train_gate()`, `plateau_ok()`, `optimize_side()`, `fmt()`, `main()`.
- **scripts/flow_daily_signals.py** — señales de flujo diario (spike EMA volumen call/put, fade, jerarquía capitanes) para backtest 3 meses. Funcs: `captains_of()`, `load()`, `detect()`, `next_day_open_epoch()`, `main()`.
- **scripts/flow_intraday_signals.py** — versión intradía (horaria) de flow_daily_signals. Funcs: `captains_of()`, `load()`, `detect()`, `next_hour_open()`, `main()`.
- **scripts/flow_pulse_calibrate.py** — calibración EOD de flow_pulse v3: replay con mismo algoritmo, hit/mfe a +15m por bucket. Funcs: `is_market_captain()`, `is_captain()`, `captains_of()`, `wilson_lo()`, `load_bars()`, `bands_ctx()`, `wall_ctx()`, `replay()`, `main()`.
- **scripts/flow_scalp_backtest.py** — mide si el spike de flujo (espada-ballena) tiene edge como FADE de minutos, no opción semanal. Funcs: `detect_spikes()`, `scalp_underlying()`, `scalp_option()`, `captain_filter()`, `wilson()`.
- **scripts/flow_signals_export.py** — replay histórico exacto del núcleo de spikes de flow_pulse.cpp sobre `whale_flow_hist.jsonl`. Clase: BandChecker. Funcs: `load_1m()`, `rth_open()`, `bb()`.
- **scripts/fri_bars_prep.py** — arma CSVs compuestos (histórico yfinance+recientes IBKR) para backtestear un día concreto. Funcs: `read_csv()`, `read_ibkr()`, `agg()`, `write()`.
- **scripts/full_history_backtest.py** — backtest de todo el historial de señales vs precio real, Poisson-binomial cluster-robusto + BH-FDR. Funcs: `classify()`, `build_baselines()`, `cluster_score_test()`, `bh_fdr()`, `wilson()`.
- **scripts/full_history_optbt.py** — backtest en la opción real 0DTE (poly_opt_bars 5m) para QQQ/SPY/NVDA. Funcs: `opt_baseline()`, `agg()`.
- **scripts/full_history_report.py** — reporte del backtest full-history: WR condicional al movimiento. Funcs: `report()`, `obs_cond()`, `obs_raw()`, `alpha()`, `mfe_mae()`.
- **scripts/iv_hist_build.py** — reconstruye superficie IV histórica invirtiendo por bisección desde poly_opt_bars. Funcs: `main()`, `spot_index()`, `nearest_spot()`, `bs_delta()`.
- **scripts/level_react_validate.py** — mide si el NIVEL añade sobre el giro de vela puro, conduce el binario C++ level_react sobre poly_bars. Funcs: `run_engine()`, `label()`, `score()`, `wilson()`.
- **scripts/leveraged_backtest.py** — backtest de la traducción señal→ETF apalancado con reglas de fleet_executor. Funcs: `sim()`, `signals()`, `fetch_bars()`.
- **scripts/local_option_scorer.py** — puntúa señales sobre prima real usando fotos locales de cadena (sin Polygon). Funcs: `score_option()`, `score_underlying()`, `pick_contract()`, `load_chains()`, `bench_day()`.
- **scripts/momentum_decay.py** — estudio empírico de cuánto tarda en morir un impulso intradía. Funcs: `detect_impulses()`, `summarize()`, `compute_indicators()`, `fetch()`.
- **scripts/null_control.py** — null de entrada aleatoria pareado + control de factor común, bootstrap, DSR, veredicto keep/kill. Funcs: `run()`, `bootstrap_edge()`, `draw_random()`, `label_batch()`, `verdict_of()` +8 más.
- **scripts/opt_recon.py** — reconstruye IV/griegas del pasado invirtiendo bisección desde precio contrato+spot. Funcs: `rebuild_chain()`, `implied_vol()`, `bs_price()`, `spot_at()`, `chain_to_text()`.
- **scripts/option_vehicle_backtest.py** — re-puntúa señales de un día en la opción ATM real. Funcs: `direction()`, `snap_at_or_after()`, `atm_key()`, `quote()`, `load_chains()`.
- **scripts/option_vehicle_report.py** — informe del backtest en vehículo real. Funcs: `line()`, `paired()`, `agg()`, `tp()`.
- **scripts/peer_health.py** — endurecimiento medido de peer_weights: HAC Newey-West, lead-lag validado contra null de shuffle. Funcs: `pair_health()`, `hac_corr()`, `xcorr_profile()`, `shuffle_null()`, `residualize()`, `run()`.
- **scripts/real_option_scorer.py** — puntúa CSV de señales sobre el pago de opción REAL (Polygon). Funcs: `resolve()`, `score_csv()`, `wilson()`, `main()`.
- **scripts/reconstruct_flow.py** / **reconstruct_flow_5min.py** / **reconstruct_flow_intraday.py** — reconstruyen flujo histórico (P/C por volumen) desde Polygon a granularidad diaria/horaria/intradía. Funcs comunes: `spot_of/daily()`, `fridays()`, `recon()`.
- **scripts/regen_signals.py** — regenera señales de la flota corriendo los bots C++ sobre 540 sesiones de poly_bars, sin look-ahead por construcción. Funcs: `load_bars()`, `run_bots()`, `run_bollinger()`, `harvest_signal_file()`, `write_signals()`, `cmd_run()`, `cmd_nolookahead()`, `cmd_verify_replay()`, `cmd_stats()`, `main()` +12 más.
- **scripts/scorer.py** — EL puntuador único del formato de señal compartido (E1H): entrada en open de siguiente barra 5m. Funcs: `wilson_lo()`, `load_bars_5m()`, `score_signal()`, `read_signals()`, `bucket_stats()`, `spread_impact()`, `main()`.
- **scripts/timeofday_calib.py** — mide edge de cada fuente de señal por hora del día y símbolo (Wilson+shrinkage). Funcs: `bucket_of()`, `load_outcomes()`, `calibrate()`, `write_report()`, `main()`.
- **scripts/v5_backtest.py** — backtest del motor v5 sobre bars 1m reales; ajusta logística prob por IRLS. Funcs: `load_bars()`, `atr_at()`, `outcome()`, `run_sym()`, `fit_logistic()`, `main()`.
- **scripts/v6_backtest.py** — calibración de prob por clase del motor v6 (M3), split temporal 60/40, replay via bots C++ en tmpdir aislado. Funcs: `load_keepalive_env()`, `load_bars()`, `wilder_atr14()`, `replay()`, `eval_outcome()`, `shrink()`, `run_sym()`, `write_reports()`, `main()`.
- **scripts/yoel_adapted_engine.py** — engine Yoel fusionado con filtros propios: prior bollinger medido, veto band-walk, confirmación de flujo. Funcs: `load_bollinger()`, `base_ok()`, `load_flow()`, `flow_confirms()`, `bandwalk_veto()`, `main()`.
- **scripts/yoel_backtest.py** — backtest honesto del subconjunto medible de la doctrina Yoel (BB+SMA+volumen). Clase: HourlyView. Funcs: `load_5m()`, `hourly_bars()`, `bb20()`, `gen_signals()`, `score()`, `main()`.
- **scripts/yoel_engine.py** — engine Yoel puro: estrategias top-down 15m→1H→1D sin stop, TP+100%. Funcs: `load()`, `agg()`, `sma_dir_at()`, `bb_at()`, `detect()`, `main()`.
- **scripts/yoel_faithful_backtest.py** — test justo del método Yoel: confluencia 3-TF, sin stop, pago via Black-Scholes con IV realizada. Funcs: `bs_price()`, `load()`, `realized_iv()`, `secs_to_friday_close()`, `run()`.
- **scripts/yoel_real_options_backtest.py** — test definitivo del rebote Yoel con primas REALES de Polygon. Funcs: `poly()`, `resolve_contract()`, `option_path()`, `detect_rebote()`, `main()`.

*Nota: `scripts/yoel_*` (5 ficheros) implementan/backtestean el método Yoel Sardinas — medido
NO superar baselines (ver skill `yoel-sardinas`); se conservan como referencia, no en producción.*

## INFRA/KEEPALIVES

- **scripts/fleet_hours.cpp** — portero horario de la flota (dom 20h→vie 20h Toronto vía TZ real); exit0=LIVE, exit1=DEAD, exit2=uso incorrecto. Funcs: `pin_zone_or_die()`, `in_window()`, `file_exists()`, `usage()`, `main()`.
- **scripts/ib_mode.py** — fuente única de verdad modo IBKR paper/live → puerto/cuenta. Funcs: `get_mode()`, `set_mode()`, `get_port()`, `get_account()`, `is_paper()`.
- **scripts/level_events_ingest.py** — sumidero JSONL→trades.db de level_events del binario C++ level_react, cero cómputo de señal. Funcs: `events_for()`, `regime_of()`, `fleet()`.
- **scripts/levels_5min_archive.py** — densifica snapshot de niveles de 1/día a 1/5min. Funcs: `snapshot()`, `verify()`, `retention()`, `atomic_write_json()`.
- **scripts/poly_backfill_bars.py** — backfill de 2 años de barras 1m a poly_bars: idempotente, reanudable, reporta huecos de sesión. Funcs: `backfill_sym()`, `run()`, `status()`, `gaps()`, `progress()`.
- **scripts/daily_archive.py** — archivo histórico diario (cadenas, GEX, levels, barras, whale, señales) para backtesting. Funcs: `ranking_json_candidates()`, `find_ranking_json()`, `archive_ranking()`, `day_bounds()`, `cp()`, `slice_epoch_file()`, `slice_jsonl_ts()`, `read_gex_map()`, `build_levels()`, `main()`.
- **scripts/finviz_auth_check.py** — detecta caducidad silenciosa del token Finviz Elite (200 con CSV vacío) → voz. Funcs: `_env_files()`, `effective_token()`, `declared_expiry()`, `judge()`, `probe()`, `say()`, `write_health()`, `main()`.
- **scripts/fleet_healthcheck.py** — verificador diario: bots/posters/alarmas/relay/launchd/frescura/cobertura/presupuesto X, auto-cura. Funcs: `proc_alive()`, `launchd_state()`, `audit_launchd()`, `poly_chains_today()`, `finviz_token_status()`, `gex_map_status()`, `heal()`, `canonical_fleet()`, `spawn_keepalive()`, `main()` +3 más.
- **scripts/fleet_window.py** — puente único "¿la flota debe estar viva ahora?" (cálculo real vive en fleet_hours.cpp). Funcs: `live()`, `why()`, `guard_or_exit()`.
- **scripts/signals_db.py** — captura TODAS las señales/alarmas en trades.db (`signals`, `voice_log`) para backtest del software completo. Funcs: `classify()`, `extract_symbol()`, `init()`, `parse_line()`, `ingest_file()`, `backfill()`, `daemon()`, `stats()`, `dry_run()`, `main()`.
- **scripts/skill_patterns_refresh.py** — inyecta patrones/muros/backtest WR/mapa gamma medido en las skills `ticker-<sym>`. Funcs: `backtest_line()`, `stats()`, `intraday_shape()`, `walls_today()`, `gex_line()`, `section()`, `main()`.
- **scripts/ta_llm_bridge.py** — puente env `TA_*` (llm.env) → `TRADINGAGENTS_*`, debe correr antes de importar tradingagents. Func: `apply()`.
- **scripts/truth_lock.py** — detector de repintado: SHA-1 de últimas 120 barras cerradas por (sym,día), alarma si el pasado cambia. Funcs: `material_diff()`, `check()`, `relock()`, `status()`, `audit()`, `prune_events()`, `context_blob()`, `main()` +7 más.
- **scripts/tws_ping.py** — prueba mínima de conectividad IBKR TWS (ib_async connect + 1 barra 1m); clientId 61.
- **scripts/universe.py** — fuente única de listas de símbolos: `fleet()` (30, vota/dispara) vs `gamma_universe()` (35, solo mapa). Funcs: `_read_list()`, `fleet()`, `gamma_universe()`.
- **scripts/uw_latency_probe.py** — mide (no supone) la latencia real de UW en sesión viva; fuera de horas dice por qué no midió. Funcs: `in_session()`, `main()`.

## TESTS

`conftest.py` carga cada script de `scripts/` por ruta absoluta vía importlib (fixture
session-scope autouse), simulando el `os.chdir(REPO)` de cada módulo, y restaura el cwd al
final. Patrón dominante confirmado en 6 ficheros (compass, fleet_consensus, fleet_hours,
level_react, volume_profile, fleet_notify): **pytest es solo arnés que compila/invoca el
binario C++ real vía stdin y verifica el JSON — cero cómputo de negocio en Python.**

### Motor C++ vía stdin (arnés Python)
- `tests/test_compass.py` (40 tests) — brújula direccional, inyecta evidencia por stdin.
- `tests/test_fleet_consensus.py` (17) — alarma de MANADA, fija el bug histórico 21/30≠DANGER.
- `tests/test_fleet_hours.py` (17) — portero de horario, veredicto vivo/muerto por instante inyectado.
- `tests/test_level_react.py` (17) — primitivo PRINT-O-NADA, dos barras cerradas cruzando = print.
- `tests/test_volume_profile.py` (23) — POC de volumen, sigue volumen no tiempo.
- `tests/test_fleet_notify_write.py`/`.cpp` (1) — compila `fleet_notify.h` con ASan/UBSan, regresión de buffer overflow en `write()`.
- `tests/cpp/bar_dedupe_test.cpp` — dedupe por epoch: el warm-up del bridge no altera lo que dice ningún bot.
- `tests/cpp/bench.cpp` — benchmarks de la matemática de los signal bots (corrige dead-store elimination).
- `tests/cpp/math_test.cpp` — BB/ATR contra el código real de la flota.
- `engines/tests/bb_test.cpp` (14 tests) — bb_core.h: BB math, elastic, band-walk, engine RTH.
- `engines/tests/combo_test.cpp` (11 tests) — combo_core.h: spikes, capitanes, jerarquía de memoria.

### Flota / gates de entrada
- `test_aapl_spread_gate.py` (6) — gate de spread NBBO falla CERRADO.
- `test_rth_session_end.py` (3) — fin de RTH es 16:00 no 15:30.
- `test_deploy_signals_gate.py` (4) — portero de ventana viva antes de deploy.
- `test_fleet_keepalive_lock.py` (3) — mutex mkdir contra TOCTOU de keepalives concurrentes.
- `test_fleet_healthcheck.py` (37) — contrato de exit code (solo 🔴 non-zero).
- `test_bar_bridge_captains.py` (4) — reparto de cupo tick-by-tick prioriza capitanes.
- `test_whale_tape.py` (7) — reparto deliberado de cinta (cupo 5), símbolos fuera declarados ciegos.
- `test_ibkr_bar_bridge_atomic_write.py` (2) — escritura NBBO atómica (tmp+os.replace).
- `test_korea_bridge.py` (10) — autodetección de puerto IBKR/Gateway.
- `test_signal_conditioning_enable.py` (4) — clave de apagado en duro bloquea speak.
- `test_voice_budget.py` (17) — DANGER nunca se recorta por presupuesto; SIGNAL sí se raciona.
- `test_chart_bridge_mock_isolation.py` (6) — modo `--mock` no escribe en trades.db de producción.

### Gamma / GEX / opciones / muros
- `test_gex_snapshot.py` (16), `test_gex_consumers.py` (15) — mapa gamma propio, símbolo ilegible se omite.
- `test_gamma_band.py` (25) — banda adaptativa vs fija, flip honesto en el borde.
- `test_dex.py` (10) — delta exposure, paridad BS, prohibido publicar signo único.
- `test_pin_clock.py` (17), `test_pin_risk.py` (10) — max pain, pin_risk_score None si falta insumo.
- `test_flip_migration.py` (10) — polilínea del flip archivada c/5min, <3 puntos = insuficiente.
- `test_chain_honesty.py` (35), `test_chain_cube_archive.py` (12) — iv=-1 nunca se convierte en 0.3 default.
- `test_book_quality.py` (25) — veto por calidad de libro, coef=0 borra confirmación falsa.
- `test_skew.py` (15) — smile fuera de banda SUPRIME no extrapola.
- `test_em_envelope.py` (16) — expected move, conteo días viernes→lunes.
- `test_kde_levels.py` (22), `test_gaps.py` (17), `test_vw_drops.py` (19) — niveles/huecos/raindrops sintéticos.
- `test_uw_gex_compare.py` (3), `test_uw_oi_delta.py` (20), `test_uw_premium.py` (16), `test_uw_archive.py` (16) — referee/premium/OI de Unusual Whales, nunca relleno con 0.
- `test_poly_backfill_opts.py` (23) — backfill de barras diarias de opciones, 429 reintenta.

### Calibración / estadística / anti-overfitting
- `test_calibration_ledger.py` (14), `test_direction_view_calib.py` (7) — wilson(), bucket sin medir = None.
- `test_barrier_labels.py` (20) — triple barrera: TP antes que SL, purga/embargo sin fuga.
- `test_null_control.py` (29) — n_eff por correlación, bootstrap CI, BH-FDR real.
- `test_bollinger_multiplicidad.py` (10) — veto de multiplicidad vs grid de ~400 pruebas.
- `test_cor_fleet.py` (30) — rho plausible prohibido sin dato.
- `test_peer_health.py` (9) — control de factor común mata lead espurio.
- `test_backtest_harness.py` (14) — WR con coste real, prohíbe retorno-a-horizonte.
- `test_regen_signals.py` (7) — no-look-ahead invariante, determinismo por semilla.
- `test_truth_lock.py` (16) — detecta reescritura de barra pasada.

### Índices / breadth / macro
- `test_index_breadth.py` (6), `test_index_breadth_prev_close.py` (3) — gap usa cierre anterior.
- `test_macro_calendar.py` (8) — año no cubierto grita, nunca `[]` fabricado.
- `test_opt_whale_watch_holiday.py` (5), `test_posthours_cage.py` (5) — calendario de festivos compartido.
- `test_force_meter.py` (11) — rsi()/measure() con inputs degenerados.

### Datos / archivado / Finviz / X / LLM
- `test_equity_prints_archiver.py` (13), `test_levels_5min_archive.py` (11), `test_daily_archive_ranking.py` (5), `test_daily_fleet_plans.py` (38).
- `test_finviz_auth_check.py` (27), `test_finviz_technicals.py` (15) — token caducado en silencio (200 vacío).
- `test_x_cashtags.py` (14), `test_x_earnings_post.py` (35) — X rechaza 2+ cashtags, ticker sin dato no se rellena con 0.
- `test_ta_llm_bridge.py` (5) — TA_* gobierna TRADINGAGENTS_*.
- `screener/test_screener.py` — ver FLOTA/BOTS.

## HUECOS

- **`scripts/fleet_consensus.py` vs `scripts/fleet_consensus.cpp`** — daemon Python original y su port C++ conviven; la memoria del proyecto marca C++ como el estándar (Python peligroso). Verificar si el `.py` sigue en producción o es legacy sin apagar.
- **`screener/alert_bot.py` vs `screener/screener_alert.cpp`** — mismo patrón: bot Python + port C++. Confirmar cuál corre en el cron/launchd real.
- **`scripts/korea_tape.cpp` vs `scripts/korea_watch.cpp`** — dos herramientas C++ de Corea con solapamiento (veredicto instantáneo vs máquina de estados nocturna); no está documentado si una reemplaza a la otra o son complementarias por diseño.
- **`scripts/gexa_parse.py`** — parsea salida de gexa.ai vía Chrome; la skill `gexa-terminal` está marcada JUBILADA (2026-07-25, el sitio desapareció). Este script probablemente está huérfano — candidato a archivar.
- **21 × `*_signal_bot.cpp`** — plantilla byte-idéntica duplicada 21 veces (confirmado por diff). Cualquier fix debe aplicarse 21 veces; existen `apply_v5.py`/`apply_v6.py` justamente para automatizar ese parcheo, pero el riesgo de una instancia desincronizada (patch parcial) es estructural.
- **`scripts/reconstruct_flow.py` / `_5min.py` / `_intraday.py`** — mismo método a 3 granularidades en 3 ficheros casi idénticos; candidato a fusionar con un parámetro de granularidad.
- **`scripts/opt_recon.py` vs `scripts/iv_hist_build.py`** — ambos reconstruyen IV/griegas históricas por bisección desde Polygon, de fuentes ligeramente distintas (`poly_opt_bars` vs precio de contrato+spot). Verificar si son redundantes o cada uno alimenta un consumidor distinto.
- **`scripts/yoel_*` (5 ficheros)** — motor + 4 variantes de backtest del método Yoel Sardinas; medido que NO supera baselines (skill `yoel-sardinas`). Vivo como referencia, no en producción — candidato a mover a `backup/` si no se usa.
- **`scripts/opening_plan.py` + `opening_plan_html.py` vs `scripts/daily_fleet_plans.py`** — tres generadores de "plan" con alcance solapado (plan de apertura vs plan diario completo PDF+X). No está claro si `opening_plan*` fue reemplazado por `daily_fleet_plans.py` o sigue en uso independiente.
- **`engines/` (bb_engine, combo_engine) vs la flota `*_signal_bot.cpp`** — dos sistemas de generación de señal C++ en paralelo (motores standalone genéricos por config vs bots hardcodeados por ticker). No documentado si `engines/` es el sucesor planeado de la flota o un experimento paralelo (MOTOR 2/MOTOR 3 sugiere roadmap de reemplazo).
- **`docs/ARCHITECTURE.md`** — ya existe un diagrama de arquitectura de datos/señal/ejecución (última verificación 2026-07-11), con foco en flujo de datos en vivo, no en índice de funciones. Este `REPO-MAP.md` es complementario (firmas de código), no duplicado, pero ARCHITECTURE.md describe un pipeline (`alpaca_ws_bridge`) que ya no aparece como binario vivo en el árbol actual — posible desactualización a verificar.
- **`scripts/full_history_backtest.py` / `_optbt.py` / `_report.py`** — trío de pipeline (no duplicado, cada uno es una etapa), mencionado aquí solo para que quede claro que NO es redundancia sino cadena backtest→opción→reporte.
