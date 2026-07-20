# AGENTS.md — ib-trader

## ORDENES PERMANENTES DE YUNIOR (no negociables)

### Claude Way (2026-07-17) — cómo deben operar todos los agentes
Doctrina completa: `~/Documents/Obsidian Vault/AI Brain/The Claude Way.md` + skill **`claude-way`**
(`.claude/skills/claude-way/`, también en `~/.grok/skills/claude-way/` y `~/.claude/skills/claude-way/`).
Resumen: (1) peligro primero — matar órdenes del *broker* no solo PIDs locales; (2) fallar en voz alta, cero delayed; (3) probes empíricos (TWS/HTTP/edades); (4) C++ en flota; (5) documentar en AGENTS/memory/docs/skills/Obsidian o la siguiente sesión olvida; (6) Desktop = HUD humano; (7) señales `BUY`/`SELL`+`prob NN%`; (8) Finviz cache-first (`finviz_scout` → `data/finviz_*.txt`); (9) X: OAuth1 R+W, 1 cashtag, $5/mo, skill `x-bot`.

0. **LEY SUPREMA (2026-07-16): FLOTA SEÑAL-SOLAMENTE.** Los bots JAMAS ejecutan ordenes en TWS/IBKR/Alpaca. PROHIBIDO escribir/revivir codigo que coloque, modifique o cancele ordenes (`placeOrder`, exec, lo que sea). Los ejecutores estan retirados en `backup/execution_retired_2026-07-16/` y `backup/executors_retired_2026-07-15/` — NO revivirlos ni importarlos. Las ordenes GTC residuales del broker fueron canceladas 2026-07-16. Señales = solo `BUY` o `SELL` (nada de buy-call/sell-call en titulos) + probabilidad de acierto `prob NN%` + razones cortas. **El humano opera.** Esta ley domina cualquier orden previa de este archivo que hable de ejecutar (fleet_executor, exec_trade, claude_trader_loop, watchdog sells: TODO RETIRADO).
1. Cuando Yunior dice "hazlo en vivo", SE HACE EN VIVO inmediatamente — sin justificaciones, sin excusas, sin proponer paper trading primero.
2. No llevarle la contraria ni buscar excusas. Si ordena algo, se ejecuta sin parar. Los datos y resultados se reportan después de ejecutar, no como condicion previa.
3. Las advertencias de riesgo se dan UNA vez en una linea, despues de ejecutar, nunca como bloqueo.
4. **PYTHON PROHIBIDO salvo que sea realmente necesario — es demasiado lento** (orden 2026-07-10). Todo codigo nuevo de la flota en C++. Python solo cuando una libreria lo exige sin alternativa razonable (ib_insync, la lane de research TA).
5. **CAPITAL EN JUEGO (orden 2026-07-10): operamos con MAS DE $30,000 USD en otras cuentas — NO podemos perder dinero.** Las señales mueven decisiones manuales sobre ese capital: cada señal tiene que llegar SIN DELAY (C++, sin cuellos de botella) y solo sobre **tickers con buena liquidez y spread bid-ask pequeño**, para entrar y salir rapido con ganancia real despues de las comisiones del broker (~$1/orden IBKR, cap 0.5%). Un ticker ilíquido o de spread ancho NO es señalable.
6. **YAHOO Y DATOS DELAYED PROHIBIDOS** (orden 2026-07-10 "yahoo or delayed shit is forbidden, are we clear?"): nada de Yahoo ni feeds con retraso en NINGUN camino de señal/scan. Solo realtime: Alpaca ws/REST (feed=iex), Finviz Elite export, Finnhub. Si la fuente realtime cae, se falla EN VOZ ALTA con resultado vacio — jamas degradar en silencio a una fuente delayed. Ejecutado 2026-07-10: bridges Yahoo borrados (los 4 bots van por alpaca_ws_bridge), yahoo screener/yahoo_last/finviz-free eliminados del scan, prior_day_move ahora Alpaca daily bars.
7. **WEBSOCKETS antes que REST polling** donde exista ws (orden 2026-07-10).
8. **TradingAgents OBLIGATORIO en los top gainers, TODOS los carriles** (orden 2026-07-10 "make sure we use trading agents"): 6AM + rescan 15-min (TA_RESEARCH=1) + fastscan 1-min (revet_watchlist en background). Los veredictos ta_action PERSISTEN entre rescans (scanner los arrastra del watchlist previo; enrich vetea los top-N SIN vetar) → la cobertura crece durante el dia en vez de re-vetear los mismos 3.

## V6 (2026-07-16) — pedido completo de Yunior (spec: docs/V6_SPEC.md, fuente de verdad)
Motor v6 MTF señal-solamente que EXTIENDE el bloque v5 en los 20 `*_signal_bot.cpp` (disparo v5 neutralizado con `V5_MIN=99` default; v5 queda de feeder). Todo C++ (Python solo donde una libreria lo exige: ib_insync/ib_async para greeks). 24/5, todo visible en el Desktop (mirror `~/Desktop/trading-signals/YYYY-MM-DD.txt` + banners Mac + voz/sonidos).
1. **Escenarios de apertura** (clasificador de fase, evaluado 10:00/10:30 y congelado): SPIKE_FADE (spike y desangre bajo VWAP), DIP_CLIMB (gap-up, dip bajo VWAP, reclaim con volumen 2x), TREND_UP/TREND_DOWN (>=80% de bars de un lado del VWAP), LATERAL (OR estrecho + VWAP plano). Gap breakaway (>1xATR15) veta los fades contra el gap. La fase habilita/veta clases de señal.
2. **Pullback vs cambio de tendencia**: pullback = retroceso <=50% del ultimo swing + hold VWAP/BB15mid + gatillo MACD 1m (continuacion); reversal = >=2 de 3 {retr>62% o higher-low roto, flip MACD15, cierre al otro lado de BB15.mid tras band-walk}.
3. **Bollinger multi-TF**: BB 1m/5m/15m con %B y bandwidth-percentile; squeeze (percentil <=10) + primer cierre fuera con RVOL>=1.5 = breakout; reversion MTF (bandas reventadas en >=2 TF) solo con ADX15<20; band-walk con ADX>25 prohibe vender por tocar banda.
4. **MACD 4-color (CM)**: 15m = contexto que MANDA (a_dn veta BUY, a_up veta SELL — excepciones: MTF_BB_REV en rango y TREND_REVERSAL); 1m = gatillo de timing.
5. **Trendlines** (LuxAlgo): break 1m confirmado sin trendline 15m intacta en contra.
6. **Probabilidad %**: cada señal sale como `BUY`/`SELL` + `prob NN%` (tabla `data/prob_table_<sym>.txt` calibrada por backtest 30d + WFO 60/40, shrinkage k=20 hacia priors; sin señal bajo `V6_PROB_MIN=55`).
7. **Overlay de opciones** (`scripts/options_enrich.py`, ib_insync **readonly=True**, TWS 7496, jamas delayed): tras cada `SYM: BUY`/`SYM: SELL` del mirror elige el contrato 0-2 DTE delta~0.55 y anexa linea `SYM: OPT | C/P fecha strike | delta gamma theta IV | OI vol spread | APTO same-day / NO-APTO (razon)` — para que el humano compre la opcion y la venda el mismo dia.
8. **Alarmas de precio** (`scripts/price_alarm.cpp` + `~/Desktop/price-alerts.txt` editable a mano: `sym precio [up|down]`): al tocar el nivel → SIRENA 3x (`sounds/fire_alarm.wav`) + voz + banner + mirror; la linea queda `FIRED ...`. **Alerta urgente activa: `intc 100 down`** (INTC < 100).
9. **Sin flatten por reloj**: ninguna venta programada 15:30/15:45/15:50 por defecto (branch EOD gated por `{SYM}_EOD_FLATTEN`, default 0); salidas por stop/target/trail/time-stop por duracion se mantienen.
Modulos M1-M5, contratos de formato, gates G1-G10 y plan de rollout: `docs/V6_SPEC.md`.

### v6.1 retest-confirm (2026-07-16 noche) — señales anti-trampa
Mejora #2 de Yunior ("no entrar cuando viene el pullback; confirmacion completa y rebote hecho; ojo trampas de ballena") = regla 2 del PLAYBOOK codificada. En los **22 bots** (los 20 del spec + mu/smh): las clases de ruptura (TLINE_BREAK_*, ORB_*, SQUEEZE_BREAK_*, VWAP_LOSS_SHORT) ya NO disparan al romper — quedan **ARMADAS** y solo emiten con (a) pullback al nivel roto (retrace 30-70% del impulso o toque ±0.25×ATR) + (b) vela 1m de RECHAZO en la direccion (tag `+retest-ok`), o (c) 3 cierres consecutivos sosteniendo sin retest (tag `+breakaway`). Pullback que ATRAVIESA el nivel (cierre en contra >50% del impulso) = **TRAMPA-EVITADA** (cancelada + log; 107 trampas evitadas en el backtest 30d). Expira a 20 bars; veto 15m re-verificado al confirmar. Off por bot: `{SYM}_V6_RETEST=0`. Backtest antes/despues en `docs/V6_BACKTEST.md` §v6.1: TLINE_BREAK_LONG 37%→50% WR; VWAP_LOSS_SHORT empeoraba (62%→44%) → **EXENTA por clase** via `{SYM}_V6_RETEST_EXEMPT` (csv, default `"VWAP_LOSS_SHORT"`, ""=ninguna): dispara inmediato v6.0 y su WR quedo restaurado (62.3% comb. / 73.3% OOS en el re-backtest). Re-aplicar template a la flota: `python3 scripts/apply_v6.py --update` (remueve el bloque viejo por marcadores y re-inserta; compila+smoke secuencial). Voz de mu/smh corregida de paso (decian "buy Intel now" por clonado; ahora "Micron" / "S M H").

### Ley flujo de opciones en el análisis (orden Yunior 2026-07-17)
Toda señal direccional DEBE integrar el flujo de opciones (delta de volumen call/put por strike entre lecturas — `scripts/fetch_option_walls.py` via TWS 7496, o alertas de flujo del humano). Reglas observadas en vivo (OPEX 2026-07-17, NVDA +117k calls 205-210 → empuje a 204.8 y retroceso):
1. **Flujo alto de CALLS ≠ subida inmediata**: pico de compra de calls = retail tarde + dealers cortos de gamma vendiendo el subyacente al cubrir → techo/retroceso local ANTES de continuar. No gatillar compra en el primer empuje; la entrada es el pullback posterior.
2. Strike con calls masivos = imán Y techo al primer toque; puts masivos en un strike = piso probable (cobertura).
3. Flujo unilateral extremo intradía (especialmente OPEX) = riesgo de reversión/pin a corto plazo. El flujo confirma dirección a medio plazo; NO es gatillo de persecución.
4. Cada señal menciona el flujo explícitamente y ajusta su `prob NN%` con él.

### Opciones rapidas: opt_chain_cache + opt_quick (2026-07-16 noche)
- **`scripts/opt_chain_cache.py`** (ib_insync **readonly=True**, TWS 7496, clientId **48**, realtime `reqMarketDataType(1)` — jamas delayed): cada 3 min durante 9:00-16:15 ET vuelca a `data/opt_chain_<sym>.txt` la cadena **±6% ATM** del vencimiento mas cercano + el siguiente, para los 17 de la flota (SMH TSM QQQ NVDA MU ASML INTC DRAM SKHY SPCX AMD TXN TSLA NOK AAPL GOOGL QCOM): `strike right exp bid ask vol oi iv delta gamma` (n/d = -1; escritura atomica). Watchdog `scripts/opt_chain_keepalive.sh` (lanzado por fleet_keepalive_start.sh). Test manual: `--once` (ignora la ventana). Ciclo medido: ~157s / 972 contratos.
- **`opt_quick`** (C++, `scripts/opt_quick.cpp`, compilar `clang++ -std=c++17 -O2 -o opt_quick scripts/opt_quick.cpp`): lector instantaneo del cache, CERO red. `./opt_quick NVDA` → P/C de volumen y de OI (total y por vencimiento), **max pain**, top-5 muros (OI+vol), spread% por strike con gates del playbook (**spread<=5% y OI>500** → APTO). `./opt_quick NVDA 210 C` → detalle del contrato con veredicto de gates. Aviso "CACHE VIEJO" si >5 min.
- (2026-07-16 noche) opt_chain_cache ampliado 17→21 syms: +MSFT AVGO AMZN META (banda ±4%, 12 strikes, 4s ticks) para el P/C de qqq_xray; verificar ciclo <180s en vivo.

### qqq_xray — radiografia instantanea del QQQ (2026-07-16 noche, C++, señal-solamente)
- **`scripts/qqq_xray.cpp`** → `./qqq_xray` (<50ms, CERO red, solo lee `data/`): por miembro top-10 (`data/qqq_weights.txt`, editable, refrescar MENSUAL) precio, %dia, contribucion ponderada, tendencia (OLS 30 closes 1m + HH/HL vs LH/LL), RVOL y P/C; agregado: contrib top-10 vs %real QQQ (divergencia), **DIQUE** (MSFT+AAPL: VERDE/MIXTO/ROTO), **LASTRE** (NVDA+AVGO+AMD: SANGRAN/NEUTRO/EMPUJAN) y VEREDICTO estilo playbook ("dique aguanta + semis sangran = empate interno, no operar QQQ").
- `./qqq_xray --watch`: loop 60s; SOLO al CAMBIAR dique/veredicto → banner Mac + voz Paulina + linea en `~/Desktop/trading-signals/YYYY-MM-DD.txt` (anti-spam). `--data DIR` para tests sinteticos. Miembros sin feed (COST/NFLX) → "s/d" + pesos renormalizados. Compilar: `clang++ -std=c++17 -O2 -o qqq_xray scripts/qqq_xray.cpp`.

### finviz_scout — datos Finviz Elite en vivo (2026-07-17 madrugada, C++, señal-solamente)
- `scripts/finviz_scout.cpp` → `./finviz_scout` (compilar `clang++ -std=c++17 -O2 -o finviz_scout scripts/finviz_scout.cpp -lcurl`): UN request/ciclo (60s premarket 4:00-9:30 ET, 180s RTH, dormido fuera) con focus_ticker(US)+MSFT AVGO AMZN META QQQ SMH → `data/finviz_<sym>.txt` (clave=valor: short float, gap, rel vol, earnings date, analyst recom col 62, target price col 69...). Token `FINVIZ_AUTH3` de feeds.env, jamas hardcodeado.
- Banners (fleet_notify.h) SOLO cambios de estado vs ciclo previo: gap>±2%, rel vol cruza 2.5x, short float ±0.5pt, earnings <48h (1/dia/ticker, `data/finviz_earn_notified.txt`), target/recom cambian; primer ciclo silencioso. Feed roto (HTTP≠200/CSV vacio/HTML/429) → "FINVIZ ROTO" banner+log en voz alta + backoff 5 min.
- Test manual: `./finviz_scout --once [SYM extra...]`; watchdog `scripts/finviz_scout_keepalive.sh` (lo lanza fleet_keepalive_start.sh; fleet_sleep lo mata). Detalles: `.claude/skills/finviz-elite/SKILL.md`.

### Skill fleet-ops
`.claude/skills/fleet-ops` — operacion rapida de la flota (modo foco `data/focus_ticker`, reinicios via keepalives, sirenas/alarmas de precio, escaneo de opciones, estado). Usarla cuando Yunior pida activar/apagar bots o estado; todo señal-only (ley #0).

### x_whale_bot — posts diarios a X / semis+whales (2026-07-17, C++, señal-solamente)
- **Memo canónico:** [`docs/X-WHALE-BOT.md`](docs/X-WHALE-BOT.md) (presupuesto, auth, comandos, flujo). Runbook: `docs/OPERATIONS.md` § X whale bot. Playbook: inventario en `docs/PLAYBOOK-2026-07-16-el-mejor-dia.md`.
- `scripts/x_whale_bot.cpp` → `./x_whale_bot` (compilar con Homebrew OpenSSL: `-I/opt/homebrew/opt/openssl@3/include -L.../lib -lcurl -lcrypto`).
- **Budget hard $5/mo** (X pay-per-use ~$0.015/post sin URL; **URLs prohibidas** ~$0.20). Ledger `data/x_budget.txt`, audit `data/x_posts.jsonl`. Max 1 post/día, ≤30/mes.
- Fuente: Finviz Elite live (`FINVIZ_AUTH3`) o cache `data/finviz_*.txt`. Universo = focus_ticker + semis flota. Score RVOL/gap/short float.
- Creds en `x.env` (gitignored): **OAuth1 user** Read+Write; Bearer app-only = 403 (probado 2026-07-17).
- Schedule: `--daemon` ventana 09:00–09:15 America/Toronto (keepalive `scripts/x_whale_bot_keepalive.sh`).
- Skill agentes: `.claude/skills/x-bot/SKILL.md` — dry-run por defecto; `--post-now` solo si Yunior lo pide.
- Manual: `./x_whale_bot --dry-run` | `--budget` | `--post-now` | `--daemon`.

## [RETIRADA 2026-07-16] EJECUCION CON ETFs APALANCADOS — fleet_executor (era LEY 2026-07-11)
**SECCION RETIRADA por la ORDEN PERMANENTE #0 (flota señal-solamente).** El fleet_executor y su keepalive viven en `backup/execution_retired_2026-07-16/`; las GTC/stops residuales del broker se cancelaron 2026-07-16. NO seguir estas instrucciones; se conservan solo como historia del mapa de ETFs apalancados y sus reglas de riesgo.
- **No se opera el ticker, se opera su ETF apalancado** (mapa VERIFICADO en vivo Alpaca+IBKR: `data/leveraged_map.json`): BUY del subyacente → comprar ETF **bull** (TSLA→TSLL, AAPL→AAPU, TSM→TSMU, NVDA→NVDL, AMD→AMDL, INTC→INTW, ASML→ASMU, TXN→TXNU, QQQ→TQQQ, GLD→UGL, SLV→AGQ, USO→UCO, CPER→CPXR, NOK→LNOK, SPCX→LOFF, DRAM→RAM); señal de BAJADA (BUY PUT) → comprar ETF **bear** (TSLS/AAPD/TSMZ/NVDD/AMDD/SQQQ/GLL/ZSL/SCO/SNK). Sin bear listado (INTC/ASML/TXN/NOK/DRAM/CPER): el put queda señal-solo.
- **BULL: "we buy and sell higher only, if not we keep the bag"** — vender SOLO ≥ profit_floor (entry + max(1%, fees ida+vuelta + 0.2%)); señal de venta por debajo ⇒ BOLSA + limit **GTC** de recuperacion EN EL BROKER (sobrevive reinicios/muerte del Mac). **PERO con STOP CATASTROFICO en precio** (orden 2026-07-11 "stop loss on price as well... a lot of money in the future"): STP GTC a −25% del ETF (`ETF_BULL_STOP`, ~−12% subyacente en 2x) — la bolsa vive para caidas normales (backtest: bolsas ~−20% recuperan 86%), el colapso del nombre se corta. GTC de recuperacion + stop en el MISMO grupo **OCA** del broker: una se llena → la otra se cancela sola (imposible oversell, cero dependencia del Mac).
- **BEAR: jamas bolsa** — STOP GTC servidor-side SIEMPRE (bears regulares −5% `ETF_BEAR_STOP`; QUAKE-bears normalizado por leverage: `lev × 1.5%` acotado 1.5–4.5%, i.e. TSLS 1.5% / GLL 3% / SQQQ 4.5% — mismo riesgo subyacente en todos); si el stop no se puede colocar, la posicion se cierra al instante. QUAKE-bears (los UNICOS activos por defecto, `ETF_QUAKE_BEARS=1`): entran SOLO con banner TERREMOTO CAIDA, time-stop 45min, sin entradas despues de 15:20, flatten 15:50, edad max 8h, max 2 simultaneos, bloqueados si hay bull/bolsa del mismo subyacente. Sale ademas con la señal de cover / TERREMOTO ALZA.
- **IBKR primario** (TFSA U26942420, LA UNICA cuenta; shares enteras — API fraccional bloqueada); **Alpaca fallback = cuenta PAPER** (clave PK) → banner "PAPER, NO REAL" si se usa.
- **Activacion**: existe `data/etf_armed` (creado 2026-07-11) **y** NetLiq ≥ **500** USD (`ETF_MIN_EQUITY`) → opera solo. **KILL SWITCH: `rm data/etf_armed`** (dry-run inmediato). Verificado en vivo: señal inyectada → "SKIP equity 68 USD < 500 — esperar fondeo". **CIRCUIT BREAKERS** (auditoria pro 2026-07-11): halt diario a −5% realizado (`ETF_DAY_LOSS_PCT`), max 2 activos por sector tech/commod (`ETF_BUCKET_MAX`; ≥2 bolsas del sector tambien bloquean), apalancamiento bruto ≤ 1.5× NetLiq (`ETF_GROSS_CAP`), presupuesto = min(AvailableFunds, SettledCash) − 25 reserva.
- Presupuesto vivo: slot = NetLiq/`ETF_MAX_OPEN`(4), bolsas no bloquean slots (el cash manda), cooldown 15min/ETF, sin re-entrada con posicion/bolsa abierta, solo RTH, precio confiable o no se opera (IBKR snapshot → Alpaca quote/trade fresco → abort; JAMAS delayed).
- Piezas: `scripts/fleet_executor.py` (motor, `--selftest`), `scripts/executor_keepalive.sh`, estado en `data/etf_positions.json` (offsets de logs + posiciones), reconcile con el broker al arrancar y cada 5min (adopta posiciones, re-coloca GTC/stops perdidos, detecta fills server-side). Señales = tail de `*_operations.log` (WARMUP filtrado; TERREMOTO CAIDA/ALZA SI se opera — es el gatillo de los quake-bears; el resto de radar no). Todas las señales y operaciones quedan registradas en `trades.db` (tablas `etf_signals`, `etf_operations`) ademas del CSV. Los motores C++ validados NO SE TOCAN.
- Backtest de la traduccion (90d, fees 0.2%/lado): `scripts/leveraged_backtest.py` → `data/leveraged_bt_90d.txt`. Veredicto: BULLS bien (349 ventas cerradas +632.9%, 198 bolsas recuperadas = 86%, 32 abiertas mtm −654% — con 500 USD el cash se congela con ~4-5 bolsas hasta que las GTC llenen, es la regla operando). **BEARS pierden como estan especificados (WR 37%, −84%): el stop plano −5% es 2-5× los stops afinados y las fees se comen el edge → `ETF_BEARS=0` por defecto (orden permanente #7: sin WR≥70 queda OFF)**; para activar: export ETF_BEARS=1 en executor_keepalive.sh — antes conviene re-afinar stop por ticker (S_STOP del bot × leverage del ETF).

## MASTER TRADING PLAYBOOK (2026-07-11 — conocimiento vivo para day/swing/options)
Destilado de investigacion web 2025-2026 + repos quant de referencia + experiencia de la flota.
Fuentes clave: tradersmastermind ORB, chartswatcher VWAP, je-suis-tm/quant-trading (patrones,
London Breakout, Dual Thrust, parabolic SAR), wilsonfreitas/awesome-quant, leoncuhk/awesome-quant-ai.

### 1. Marcos temporales — quien manda a quien
- **Regla de 3 marcos**: contexto (15m) → setup (5m/3m) → gatillo (1m). El marco superior VETA:
  nunca comprar un gatillo 1m contra la tendencia 15m; nunca shortear sobre VWAP con 15m alcista.
- 1m = SOLO ejecucion (ruido 60-70%); 3m = compromiso (menos fakeouts que 1m, mas entradas que 5m);
  5m = el caballo de batalla intradia (nuestra flota: Supertrend 5m); 15m = estructura del dia
  (nuestro z15 de BB-15m ya lo codifica). Swing: 1h contexto → 15m gatillo, o diario → 1h.
- **Alineacion**: A+ setup = los 3 marcos apuntan igual. Solo-gatillo sin contexto = C setup, skip.

### 2. Setups nucleo (mecanicos, backtesteables)
- **ORB (Opening Range Breakout)**: rango = primeros 15 min (9:30-9:45); entrada = CIERRE de vela
  5m fuera del rango CON volumen > promedio Y VWAP del mismo lado Y 21-EMA alineada. Stop = lado
  opuesto del rango (o 50%). Target 2R o cierre EOD. Estudios 2025: ~60-65% dias con seguimiento
  cuando el gap inicial > 0.5 ATR diario; una sola operacion/dia. NUESTRO SKIP_OPEN ya evita
  operar DENTRO de la subasta — el ORB opera la RESOLUCION de esa subasta.
- **VWAP**: (a) reclaim — precio pierde VWAP, lo recupera con volumen → long, stop bajo el minimo
  del reclaim; (b) fade a VWAP — extension >2 ATR de VWAP sin noticia → reversion a VWAP (nuestro
  s_vw del score v3 es exactamente esta distancia); (c) tendencia — pullbacks que respetan VWAP
  todo el dia = institucional, comprarlos. VWAP win-rate historico ~60% con 1:1 — la ventaja esta
  en el filtro de contexto, no en el indicador.
- **Break-and-retest**: la ruptura NO se persigue; se espera el retest del nivel roto que aguanta
  (cierre en la direccion) — mitad del riesgo, misma ganancia. Aplica a ORB, Donchian y trendlines
  (skill trendline-trading: fractal-5, 3 toques, cierre ±0.25 ATR).
- **Capitulacion confirmada** (motor de la flota): BB inferior + RSI<umbral + volumen → NO se
  compra el cuchillo: se ARMA y se compra la vela verde que recupera el maximo del panico. La
  confirmacion es lo que sube el WR de ~45% a 70%+. Espejo para blow-off arriba.
- **Liquidity sweep** (skill liquidity-trading): barrida de maximos/minimos iguales (wick >0.25 ATR
  que CIERRA de vuelta) + confirmacion = entrada contra el sweep; los stops cazados son el combustible.
- **London/Dual-Thrust (sesiones)**: rangos de sesion previa como niveles (je-suis-tm) — util para
  el overnight 24/5: el rango overnight define el mapa del open.

### 3. Patrones de velas que SI mueven la aguja (contexto > patron)
Engulfing / hammer / shooting-star / marubozu (ya en los bots via {SYM}_CANDLE) SOLO valen:
en nivel (VWAP, banda, trendline, rango) + con volumen + en el marco 5m/15m (en 1m son ruido).
Tres velas del mismo color acelerando + volumen decreciente = agotamiento, no fuerza.

### 4. Regimen — la meta-señal (nuestro regime-detection skill)
- Tendencia vs rango: ADX>25 o Supertrend estable = seguir rupturas; ADX<20 = fade extremos.
  Cambiar de familia de setup segun regimen VALE MAS que optimizar parametros dentro de una.
- Volatilidad: ATR% define stops y targets — stops fijos en % son mentira; 3xATR trail (flota) ✓.
- El CUSUM/terremoto ES un detector de cambio de regimen: tras un quake, el playbook cambia
  (momentum manda 30-60 min; mean-reversion queda vetada ese rato). Por eso los quake-bears.

### 5. Opciones (el humano opera con las señales; regla broker-generico #9)
- BUY NOW → CALL (o shares); BUY PUT → PUT. Vencimiento: intradia = 0-2 DTE solo con liquidez
  (spread <5% del premium); swing = 2-4 semanas, delta 0.5-0.7 (ITM ligero paga el theta).
- 0DTE: solo primeras 2h o ultima 1h, tamaño mitad, NUNCA hold overnight, el theta es un incendio.
- IV alta (earnings, VIX>25): comprar opciones = pagar caro — usar debit spreads (compra ITM,
  vende OTM) para neutralizar IV; IV baja = calls/puts secas mejor.
- Nuestra ventaja: el bot da la DIRECCION y el TIMING; la opcion es solo el vehiculo con
  perdida maxima definida (TFSA-safe, sin margen).
- FLUJO (ley 2026-07-17): pico de flujo de calls = techo local probable (dealers cubren vendiendo);
  entrar en el pullback, no en el empuje. Calls masivos en strike = iman+techo; puts masivos = piso.
  Toda señal cita el flujo y ajusta su prob.

### 6. Riesgo — lo unico no negociable
- Riesgo por trade <=1-2% del equity (Kelly fraccional 0.25-0.5 del Kelly pleno; skill kelly-criterion).
- 3 perdidas seguidas = STOP del dia (tilt es real). Perdida diaria max 5% = semana protegida.
- Fees SIEMPRE en el calculo: floor de venta = entry + max(1%, fees ida+vuelta + 0.2%) — codificado
  en fleet_executor.profit_floor(). Posiciones chicas exigen % mayor; sin excepcion.
- Bolsas (regla Yunior): SOLO en bulls apalancados de tickers favoritos, con GTC de recuperacion
  en el broker; JAMAS en inversos (decay diario + rebalanceo los pudre — stop y fuera).
- Apalancados 2x-3x: producto DIARIO — la variance drag castiga holds largos; una bolsa 2x tarda
  MAS en recuperar que el subyacente. Aceptado por orden explicita; no añadir sin orden.

### 7. Microestructura (por que ganamos con ~1ms)
- Primer trade del minuto siguiente cierra el bar → señal ~1ms despues (kqueue). El edge no es
  HFT: es NO llegar tarde al retest/confirmacion que el resto ve 3-30s despues (pollers).
- Spread gate (SPREAD_MAX/NBBO) antes de confirmar: un spread ancho se come un dia de expectancy.
- Volumen IEX ≈2-5% del SIP: gates de volumen RELATIVOS (vol/volMA) son escala-invariantes ✓;
  jamas mezclar fuentes de volumen por minuto (reader dual-source: hold 2s anti-mezcla).

### 8. Proceso (lo que separa pro de amateur)
- Todo setup nuevo: replay 90d → train/OOS 60/40 → WR>=70 + OOS positivo o NO SE ENVIA (#7).
- Cada regla optimizada contra los MISMOS datos dos veces = overfit; walk-forward o nada.
- Diario de operaciones = data/etf_ledger.csv (auto) + scorecard. Revision semanal: bolsas
  abiertas, stop-rate de bears, expectancy por ticker. Lo que no se mide se degrada.

## Overview
Rules-based dip/breakout trading system for Interactive Brokers (IBKR), US equities via SMART routing.
Main bot: **`day_trading_bot.py`** (multi-ticker via `--symbol`; formerly dram_dip_bot.py).
Legacy multi-symbol EMA system: `main.py` + config.py/strategy.py/etc (KOD, dormant).

## Yunior's Favorite Tickers (memo, 2026-07-06)
TSM, AMD, DRAM, ASML, SPCX, TSLA, NVDA, NOK, AAPL, INTC, TXN, MU, GOOGL, QCOM, SMH, SPY, QQQ
- Mostly semis + big tech + index ETFs. Backtest each before trading: params tuned on DRAM's volatility.
- 7d test 2026-07-06 ($500, defaults): bot only fires on real panic — big winners DRAM +4.5% (vs −21% B&H), TSM +4.6%, TXN +2.5%, GOOGL +3.0%, AAPL +2.4%; calm tickers (SPY/QQQ/SMH/MU/ASML) = 0 trades, in cash. Never lost realized money on any of 17.

## Strategy (day_trading_bot.py)
- **Entry** (`--entry-mode`): `confirmed` (DEFAULT: capitulation BB(20,3.0)+RSI≤25+vol arms; buy ONLY on reversal confirmation bar — green close above panic bar's high with RSI turning up) | `dip` (buy panic bar directly) | `reclaim` (dip + close > 10-bar high) | `momentum` (Donchian 20-bar breakout + RSI≥60) | `both` (dip OR momentum).
- **Exit** (`--exit-mode`): `adaptive` (DEFAULT: resting limit at +4% target → trail 3×ATR → after 120 bars time-stop decays limit to floor → 15:45 ET flatten; floor = max(entry+1%, break-even+fees), NEVER sells below) | `breakout` (ATR trail, floor entry+5%) | `fixed` (GTC limit entry+target).
- **Session discipline**: entries only 9:30–15:30 ET (rth_only + entry_cutoff); EOD flatten prefers cash over overnight bags.
- 17-ticker 7d validation (crash week): new defaults = 7 cycles all profitable, 1 bag (vs 6 bags before), 0 losing sells, worst sell +$0.77. Cash-first behavior confirmed.
- **Never sell at a loss**: exit floor = max(entry × (1 + min_profit_pct), break-even incl. fees), enforced at fill. Realized PnL cannot be negative. Bag is held until recovery (unrealized losses possible — that's accepted risk).
- **Sizing**: `use_all_cash: True` — full balance each cycle, whole shares, compounding. Live buys use 98% (fee/slippage buffer; TFSA = cash account).
- **Costs modeled**: $1/order commission. With 1 share of a ~$70 stock, fees force the floor to ~+3%; commission drag fades with budget ≥ $500.
- Defaults: min_profit_pct 5.0 (floor), trail 3×ATR, max_lots 1, cooldown 0.

## Validated Results (real data, fees included, all realized-positive)
| Window ($500) | dip+breakout 3ATR (DEFAULT) | dip+fixed +5% |
|---|---|---|
| 14d crash 1m (DRAM −18%) | **+18.53%** | +13.47% |
| 7d crash 1m (DRAM −17.7%) | **+4.53%** | +4.51% |
| 60d 15m (DRAM +104%) | +13.39% | **+26.98%** |

Engine honesty: signal on completed bar → fill next bar open (no look-ahead); limit sells fill intrabar at limit-or-better; whole shares; commissions; same-bar exits blocked.

## Commands
```bash
# Fetch real data (yfinance; raw urllib gets 429). Any symbol:
venv/bin/python scripts/fetch_dram_data.py DRAM   # -> data/dram_15m.csv + dram_daily.csv

# Backtest
venv/bin/python day_trading_bot.py --mode backtest --data-file data/dram_1m_14d.csv --capital 500

# Param sweep
venv/bin/python scripts/dram_backtest_analysis.py data/dram_1m_14d.csv

# Paper trading smoke test (IB Gateway paper 4002 / TWS paper 7497)
venv/bin/python day_trading_bot.py --mode trade --port 4002 --once --wait-tws

# Production paper run (24/5 window + TWS wait + auto-reconnect)
venv/bin/python day_trading_bot.py --mode trade --port 4002 --schedule --wait-tws

# Live (REAL MONEY, TFSA only, manual YES confirmation)
venv/bin/python day_trading_bot.py --mode trade --port 7496 --live
```
Key flags: `--symbol/--exchange/--currency`, `--entry-mode dip|reclaim`, `--exit-mode breakout|fixed`,
`--min-profit-pct`, `--trail-atr-mult`, `--bb-std`, `--rsi-oversold`, `--commission`, `--schedule`, `--wait-tws`.

## 24/5 Operation (Sun 20:00 → Fri 20:00 Toronto)
- `--schedule` sleeps outside the window (DST-aware, edge-tested). `--wait-tws` socket-probes TWS/Gateway and waits instead of dying; also used on reconnect.
- launchd service: `cp scripts/com.ibtrader.dram.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.ibtrader.dram.plist` (RunAtLoad + KeepAlive; runner: `scripts/run_dram_bot.sh`).
- TWS/Gateway must be running & logged in (bot waits, can't start it). Use IB Gateway + Auto restart for unattended weeks. No web server needed.

## IBKR Integration (audited 2026-07-06)
- ib_insync 0.9.86 (imports prefer `ib_async` if installed). Verified: connect/qualifyContracts/reqHistoricalData/accountSummary/positions/openTrades/placeOrder/LimitOrder(tif=GTC).
- Live loop: acts on last COMPLETED bar only; reconnect guard; restart recovery (seeds lot from IBKR avgCost so breakout trail works after a crash); all sells are LIMIT ≥ floor — no loss possible even on slippage; cash-checked whole-share buys.
- Ports: TWS paper 7497 / live 7496; IB Gateway paper 4002 / live 4001. All closed as of 2026-07-06 (TWS not running).

## Accounts & Safety
| Account | Purpose |
|---|---|
| `U26642820` | Cash account — NEVER for live bot orders |
| `U26942420` | TFSA — only allowed live account (enforced in code) |
| `DUR197573` | Paper account (pending approval ~2026-07-07) |
- Default = paper/dry-run. Live needs `--live` + typed "YES". Weeks of paper testing before live.
- Paper accounts appear as `DU*`. If only `U*` visible, session is live infrastructure — read-only only.
- IB Gateway download: interactivebrokers.com → Technology → IB Gateway (login: IB API + Paper Trading; API port 4002; enable Socket Clients; Auto restart on).

## Conventions
- Timestamps UTC in data files; schedule logic in America/Toronto.
- Data files: `data/<sym>_{1m_7d,1m_14d,15m,daily}.csv` (columns: date,open,high,low,close,volume).
- Logging INFO → stdout + ib_trader.log; launchd logs → dram_bot_stdout/stderr.log.
- Deps: ib_insync≥0.9.86, pandas, numpy, yfinance (venv/, Python 3.9 — no `X | Y` type syntax).
- DRAM thesis: supply shortage through 2028, long-bias justified; thesis ≠ guarantee — backtests must report realized AND mark-to-market.

## Options Bot — `options_trading_bot.py` (2026-07-07)
Same confirmed-reversal engine, options execution: capitulation->CALL, euphoria->PUT.
- **Never 0DTE**: hard floor DTE>=3 (default min 5, weekly Fridays); DTE<=2 escape exit only at >= floor.
- **Liquidity gates** (live): spread <= 10% of mid, OI >= 100, limit-at-mid orders ONLY (never market). Chain via reqSecDefOptParams, ATM strike.
- **Profit-only sells**: GTC limit premium+25%; trail 25% giveback; floor = max(premium+3%, break-even+fees).
- **THETA WARNING (cannot be engineered away)**: an option held past its floor window can expire worthless — expiration can realize a loss even though the bot never *sells* at one. Sizing (`risk_fraction` 0.5) is the real protection. 30d test: 2 expiry losses (INTC -$555, QQQ bag) out of 38 positions.
- Backtest prices synthetic ATM options via Black-Scholes over real underlying 1m bars (RV*1.10 IV proxy) — optimistic vs real spreads; treat results as upper bound.
- 30d/17-ticker result ($1k each): **+27.9% total**, 36 cycles, stars GOOGL +183%, NVDA +75%, TSLA +68%; failures INTC -56% (expiry), QQQ -65% MTM (single contract ate full budget on expensive underlying).
- **Sizing rule learned**: on expensive underlyings (QQQ/SPY/GOOGL), 1 ATM contract > risk budget with $1k — either fund $2.5k+ per options ticker or trade only underlyings where premium*100 <= risk_fraction*cash.
- Run: `venv/bin/python options_trading_bot.py --mode backtest --data-file data/nvda_1m_30d.csv --capital 1000`
- Live: `venv/bin/python options_trading_bot.py --mode trade --symbol NVDA --port 4002 --wait-tws --schedule` (paper first; requires options trading permission + market data on the account).
- Refs: PyOptionTrader (ib_insync patterns), lambdaclass/options_portfolio_backtester (DTE/delta/liquidity gating), lumibot.

## Leveraged Bot — `day_trading_leveraged_bot.py` (2026-07-07)
Signals on the BASE ticker, trades its LEVERAGED ETF (2x wrapper). Pairs:
DRAM->RAM, SPCX->SPCH, TSLA->TSLL, AAPL->AAPU, NVDA->NVDL, TSM->TSMU, TXN->TXNU, AMD->AMDD, INTC->INTW, ASML->ASMU
- Engine: same confirmed entry + adaptive exit; floors/targets on the ETF's own prices (never-sell-below-floor intact). EOD flatten extra-critical here (daily-reset decay makes LETF bags bleed).
- 30d backtest ($500/pair): **+$108.95 (+2.18%), 18/18 cycles profitable, 1 bag (AMDD -$14)**.
  Star result: bot +3.7% on NVDL while NVDL B&H did **-70.7%**; +6.6% on INTW vs B&H -86.7% — scalp the bounce, never hold the decay.
- **WARNING - verify ETF direction before live**: AMDD moved OPPOSITE to AMD (+15.6% vs -12.6%) => likely a BEAR/inverse ETF; INTW's -80.8% vs INTC +19.8% also suggests inverse/heavy decay. Buying a bear ETF on a bullish base signal is backwards. Confirm each wrapper is 2x LONG (check issuer sheet) or remap.
- Thin tapes: TSMU (~2.5k bars/30d), TXNU (~2k), RAM (~8k) = illiquid; expect wide spreads live.
- Run: `venv/bin/python day_trading_leveraged_bot.py --mode backtest --base NVDA --letf NVDL --base-file data/nvda_1m_30d.csv --letf-file data/nvdl_1m_30d.csv --capital 500`
- Live: `venv/bin/python day_trading_leveraged_bot.py --mode trade --base NVDA --port 4002 --wait-tws --schedule`

## Memory Sector Bot — `ram_leveraged_bot.py` (2026-07-07)
Long/short memory complex WITHOUT shorting (TFSA-safe): signals from DRAM+MU+Samsung(005930.KS)+SK Hynix(000660.KS), executes RAM (bull) or SOXS (bear, 3x inverse semis — closest liquid proxy, not memory-pure).
- Entries: (a) confirmed reversal on any constituent + quorum >=2 corroborating via RSI breadth; (b) **Korea read-through**: both .KS names close same session beyond +/-2% -> arm matching ETF for next US open (Korea trades overnight Toronto = the 24/5 window's edge).
- Exits: adaptive profit-only (target/trail/time-stop/EOD flatten, floor entry+1%/break-even). One position at a time (bull XOR bear).
- 30d backtest ($1k): **+34.53%, 6/6 cycles profitable, ended in cash** (4 bear + 2 bull wins; read-through fired 3x correctly).
- Catalysts: `--mode catalysts` fetches earnings+news for the complex; seeded: SK Hynix US ADR listing 2026-07-10. `--blackout` blocks new entries on catalyst days.
- Live: US legs via IBKR; Korean legs polled via yfinance (IBKR retail lacks KRX). `venv/bin/python ram_leveraged_bot.py --mode trade --port 4002 --wait-tws --schedule`

## Best Trading Repos on GitHub — Distilled (2026-07-08)
Top frameworks by stars: freqtrade (~48k, crypto bot, mature strategy/backtest framework), Zipline (~20k), QuantConnect/Lean (~18k, institutional-grade multi-asset), Hummingbot (~18k, market making), vectorbt (fast numpy backtesting), Qlib (Microsoft, ML alpha factors). Rising 2026: ai-hedge-fund + TauricResearch/TradingAgents (multi-agent LLM traders, +9k stars/week).
**What we took from them (already in our bots):**
1. Signal != execution: signal on completed bars, fill next bar open, limit orders always (Lean/freqtrade discipline).
2. Regime awareness: mean-reversion (buy panic) wins in chop/crash; momentum-chasing loses (verified 2x on our data). VWAP as fair-value anchor.
3. Defined risk beats stops on noisy marks: spreads/floors > price stops (tastytrade mechanics, options_portfolio_backtester).
4. Costs modeled ALWAYS (commissions capped 0.5% IBKR Canada, spread haircuts both ways) — every repo that skips this overfits.
5. Breadth/quorum: multiple constituents confirming > single-name signals (sector rotation pattern, QuantConnect ETF rotation).
6. One position, full attention; DB-log everything (bot_trades/bot_snapshots in trades.db); sounds for human awareness.
**Fleet:** day_trading_bot (stock dip-cycle) | day_trading_leveraged_bot (2x wrappers) | ram_leveraged_bot (memory sector long/short, LIVE 24/5) | options_trading_bot (debit spreads) | octopus_bot (opening-drive scalps, +2.1%/30d marginal - scalping is the hardest game) | momentum_bot.cpp (C++ detector + sounds).

## HF PPO Agent Evaluation (2026-07-08)
Model: Adilbai/stock-trading-rl-agent (SB3 PPO, 4.9MB, runs instantly on the 8GB Mac, CPU).
Evaluated on 250 fresh out-of-sample days with REAL price accounting (`hf_ppo_bot.py`;
the repo's own env extracts "prices" from normalized features — broken, we fixed accounting):
- Absolute returns positive everywhere (AAPL +22%, AMD +145%, MU +299%) BUT loses to
  buy&hold on ALL 6 tickers (avg -102 pts). It holds ~78% of days, buys small, almost
  never sells (0-2 sells/250d) = a diluted long with cash drag.
- Verdict: NOT better than our rule-based bots. Kept as reference; don't trade it.
- Octopus note: opening-drive scalps only marginally positive (+2.1%/30d after tuning) —
  scalping is the hardest edge; the sector bot remains the flagship.

## Live Trading Learnings (2026-07-08 — first real fill)
- **FIRST REAL TRADE: BUY 1 GNS @ $0.1833 USD (AMEX, via IBKRATS), TFSA U26942420. Commission $0.001836** — confirms the 0.5%-of-value cap model exactly. Position lives in the account.
- **CUPR/Canadian products**: IBKR Canada hard-blocks API orders for Canadian products (Error 201 CTCI). Manual TWS orders work. US products flow fine via API.
- **Price-band protection**: IBKR rejects limits "too aggressive" vs market (GNS: cap was ~+9.8% over mkt). Marketable limits must stay within ~5-10% of last — retry closer to market on Error/Warning 202.
- **Tiny USD buys work from a CAD-only balance** (IBKR carried the $0.18 USD debit) — micro US positions don't need pre-conversion.
- Penny screening: yfinance across candidate list, filter price 0.05-0.25 + vol>100k. 2026-07-08 survivors: GNS $0.184 (1.9M vol), COSM $0.247 (29M vol) — most 2021-era pennies are delisted.
- All manual orders logged to trades.db (bot=manual, mode=live).
- **Fractional via API: BLOCKED by IBKR Canada** (Error 10243, tested live 2026-07-08 despite "Global Trade in Fractions" permission — desktop TWS only). Bots trade whole shares + alloc_pct equal allocation.
- **Auto-FX is FREE for micro buys**: GNS purchase auto-converted CAD->USD via IDEALPRO at $0.00 commission (auto-liquidation). No pre-conversion needed for small US buys.

## Top-gainer safety regime (2026-07-09 — ordenes de Yunior)
- **Claude Code SIEMPRE decide**; el loop corre en la ventana de compra Y siempre que haya posicion abierta (management mode). Cada ciclo sano toca `data/screener/claude_alive`.
- **DEAD-MAN**: si Claude deja de responder (`claude_alive` viejo > TG_DEADMAN_SEC=240) con posicion abierta → el watchdog VENDE YA (force-flat, limite market*0.97). Probado en DRY.
- **STOP-LOSS SIEMPRE** (TG_STOP_PCT=3%) + **TIME-STOP** (TG_MAX_HOLD_SEC=900; ideal ~5 min por trade) — reemplaza el hold-the-bag SOLO en screener. Entrada solo con breakout CONFIRMADO (precio aguantando el nivel, nunca el primer spike).
- **RECONCILE** cada 60s vs IBKR (readonly): venta manual/externa detectada → limpia position.json (bug fantasma CIRC 2026-07-09: venta manual dejo al watchdog spammeando sells rechazados Error 201). `exec_trade.py reconcile SYM`.
- Cooldown de sell (TG_SELL_RETRY_SEC=90) — no mas spam de notificaciones.
- **Notificaciones SOLO Mac** (osascript banner+Glass, async) — ntfy eliminado de TODA la flota (llegaba tarde/acumulado). TradingAgents research OBLIGATORIO en cada scan (default ON, opt-out TA_RESEARCH=0).
- **LaunchAgent autostart NO funciona** (TCC: launchd no puede leer ~/Documents, exit 127). Arranque manual `SCREENER_LIVE=1 zsh screener/start_all.sh` hasta que Yunior de Full Disk Access a /bin/zsh (System Settings → Privacy → Full Disk Access).
- Python dormante movido a `backup/` (ver backup/README.md); C++ preferido en toda la flota. `day_trading_bot.py` queda en la raiz (exec_trade importa sus helpers).
- **HOT LOOPS EN C++ (2026-07-09)**: `screener/screener_watchdog.cpp` (guardian por-segundo: stop/target/trail/time-stop/deadman/reconcile/cooldown, Finnhub libcurl + price.py fallback, paridad matematica verificada 32/32 vs Python, ventas via exec_trade.py subprocess porque ib_insync no tiene gemelo C++) y `screener/screener_alert.cpp` (señales BUY-CONSIDER). Build: `clang++ -std=c++17 -O2 -o <bin> <src> -lcurl`. watchdog.py/alert_bot.py quedan como fallback probado (keepalive/start_all usan el binario si existe).
- **LECCION telegram plugin (2026-07-09)**: cada `claude -p` del trader loop heredaba los plugins globales; el plugin telegram filtraba un daemon bun (~35% CPU c/u) POR CICLO → 8 huerfanos rompieron coreaudiod (audio) y dispararon el fan. Fix: `screener/claude_settings/settings.json` ahora pone enabledPlugins todo-false, y telegram quedo deshabilitado global. Si el audio se rompe: `sudo killall coreaudiod`.

## MODO ACTUAL: 5 BOTS DE SEÑALES, CERO TRADING (2026-07-10, orden de Yunior)
"For now we are only using top gainers for sending signals, claude will not
operate trades." — TFSA liquidada (flat, $98.06 CAD cash), `armed` borrado,
`data/screener/signal_only` presente → ensure_all/start_all NO lanzan el
claude_trader_loop (lo matan si revive) y fuerzan SCREENER_LIVE=0. El plist
com.ibtrader.screener ya no exporta SCREENER_LIVE=1. Quitar el flag
signal_only + touch armed + SCREENER_LIVE=1 restaura el trading.
- **Los 5 bots de señales**: dram/nok/spcx/tsla_signal_bot (C++) + screener
  (alert C++ + 3 carriles de research). El watchdog sigue vivo como red de
  seguridad (sin posiciones no hace nada).
- **EMAIL Y TELEGRAM ELIMINADOS (orden Yunior 2026-07-10 "lets remove
  telegram and email, just mac")**: canal único = banner Mac URGENTE via
  `fleet_notify.h` (posix_spawn C++, 0.2-1.4ms medidos en el caller, cero
  red, cero daemons). signal_email_bot / email_signal / email.env /
  notify.env borrados; NO re-proponer email/telegram/ntfy.
  fastscan sigue mandando banner Mac al MINUTO cuando entra un gainer nuevo.
- **Scoring con liquidez Y volatilidad (orden 2026-07-10)**: scanner.evaluate
  añade range_pct (rango intradía % vía Finnhub, solo survivors) →
  score = gain*(0.4+0.6*liq)*(0.7+0.6*vola)*tight − extended_pen*10.
- **Spread bid-ask (orden 2026-07-10 "gran liquidez y poca diferencia bid-ask")**:
  `price.alpaca_spread()` (Alpaca latest quote IEX, stale-guard 5 min) — gate
  duro SCAN_MAX_SPREAD=3% (salvo spread de 1 tick) + multiplicador `tight`.
- **PRE-BREAKOUT (orden 2026-07-10 "detectar breakout antes de que ocurra")**:
  screener_alert.cpp avisa cuando el precio esta a <=TG_NEAR_PCT (1.5%) del
  nivel del dia con CUSUM >=50% del umbral de burst → banner "PRE-BREAKOUT"
  + signals.jsonl (kind pre_breakout), 1 por simbolo por dia.
- **PRIORIDAD USA (orden 2026-07-10 "priority to us companies")**: sources
  captura la columna Country de Finviz; scanner.evaluate multiplica el score
  por us_mult = 1.0 USA / 0.9 desconocido / 0.6 extranjero (pumps chinos de
  reverse-split = trampa clásica). Verificado: SNAL (USA) supera a YMAT/PMA
  (Taiwan/HK) aunque suban más %.

## IBKR MARKET DATA (Client Portal verificado 2026-07-10)
- **Status subscriber: NON-PROFESSIONAL confirmado**; Market Data API
  Acknowledgement firmado 2026-07-03; cuenta facturable U26642820; CAD 0/mes.
- Subs activas (todas fee-waived): **US Real-Time Non Consolidated Streaming
  Quotes** (streaming US real-time YA existe, pero tape parcial no-SIP),
  PAXOS crypto, US Mutual Funds, Alt EU Equities, Eurex Core, HK Derivatives,
  Korea Equities, IDEALPRO FX, US/EU Bonds.
- **Snapshots US Equities de pago funcionan** ($0.01/snapshot; contador vivo:
  2 usados = USD 0.02).
- **Falta para tape completo**: "US Securities Snapshot and Futures Value
  Bundle" $10/mes non-pro (waived con $30/mes de comisiones) = Network A+B+C
  consolidado. Es el upgrade que decide la calidad de volumen de los bars.
- **VERIFICADO 2026-07-10 en vivo: Error 10089 SIGUE para la API** — la sub
  waived de streaming no-consolidado es SOLO para el desktop de TWS, no API.
  Para streaming API hay que COMPRAR una sub (el bundle $10 o Cboe One $1).
  Al comprarla: reiniciar TWS, re-probar reqMktData, y entonces construir el
  bridge C++ TWS → data/bars_*.txt (bots sin cambios).

## FLOTA 13 BOTS (2026-07-10 noche, orden "add these as essentials")
- **13 signal bots C++**: dram nok spcx tsla + NUEVOS nvda txn tsm amd intc
  asml aapl + gld (proxy oro = GLD ETF) + qqq (proxy NAS100 = QQQ ETF).
  Todos clones del motor NOK (v2/v2.1 completo), todos por alpaca_ws_bridge
  (13 syms en bars+trades SELF-AGG; watchlist screener baja a 17 slots —
  limite Alpaca free 30 syms). Keepalives scripts/<sym>_keepalive.sh,
  lanzados por fleet_keepalive_start.sh (launchd com.ibtrader.fleet).
- **Sweep walk-forward 90d (train 60d / OOS 30d) de los 9 nuevos**:
  SHIP (OOS positivo): AMD +7.3%, INTC +14.7% (el mejor), ASML +3.5%.
- **GLD/QQQ = TREND MODE ("super important", 2026-07-10)**: la reversion 1m
  en ETFs calmados/eficientes falla OOS o exige stop 3% (riesgo 7x). Ambos
  corren trend (flip Supertrend 5m / ruptura max del dia + CUSUM tunable
  {SYM}_TREND_CUSUM=0.002, stop 0.4%, EOD plano forzado, max 2/dia):
  GLD OOS +1.87% 25T/19W, QQQ OOS +1.61% 33T/25W (76% WR ambos).
  Motor trend vive en spcx/gld/qqq. ATRs: GLD 0.033%/1m, QQQ 0.042%/1m.
  NO-SHIP (OOS negativo en todo el grid): NVDA, TXN, TSM, AAPL → defaults
  raro-limpio (BB3/RSI25, solo panico real) + stop/skip-open/time-stop.
  Regla vigente: sin OOS positivo no se shippean params.

## TERREMOTO BANNER-GRADE, AMBAS DIRECCIONES, LOS 13 (2026-07-11)
CUSUM quake promovido de solo-log a banner+sonido ({SYM}_QUAKE_BANNER=1),
umbral {SYM}_QUAKE_MIN por ticker (backtest 2026: precision 88-99% en AMBAS
direcciones, TP = el movimiento no retrocede >50% en 30 min, <=10/semana).
DETECCION universal en los 13 (sube Y baja); tomar POSICION sigue siendo
solo donde valido OOS (largos 13, cortos 8).

## v4 AMBAS DIRECCIONES (2026-07-11, "signals when going down and also up")
Espejo corto completo: euforia sobre banda + RSI sobrecomprado + volumen,
confirmado por bar rojo que pierde el minimo del bar de euforia -> SHORT NOW;
en trend: flip bajista/ruptura del minimo del dia + CUSUM negativo. Cover
simetrico con exits PROPIOS ({SYM}_S_*). El largo NO cambia (invariancia
verificada); un largo confirmado cubre el corto (reversal). Gate {SYM}_SHORTS.
Optimizacion independiente del corto (entradas propias {SYM}_S_MODE/
S_BB_STD/S_RSI_OS/S_SCORE_MIN/S_TREND_CUSUM — el corto puede correr OTRO
motor que el largo): 8/13 bidireccionales — INTC trend-short 255T WR80%
+106% pf2.1 (OOS +53%!), AMD +46.8% pf4.7, GLD +32% pf4.3, NVDA 87% pf8.8,
TXN 80% +28%, QQQ 74%, SPCX 85% pf8.3, ASML 70%. Long-only tras busqueda
completa: DRAM/NOK/TSLA/TSM/AAPL (re-barrer si cambia el regimen).

## MANDATO WR-70 (2026-07-11 PM, "all of them should be above 70 percent")
Backtest 2026 completo (ene-jul), seleccion WR-first con validacion OOS:
12/13 bots >=70% WR full-year (tabla en el commit). TSLA y TXN pasaron a
TREND. NOK/AMD/NVDA/TSM/INTC usan STOP=8% (casi nunca dispara — el WR alto
viene de realizar solo ganancias; una perdida puede quedar en bag: el riesgo
se movio de stop realizado a bag no realizado, vigilar con scorecard).
GLD = unica excepcion (79% OOS / 61% full-year; ningun motor llego a 70).

## MOTOR v3 CONFLUENCE (2026-07-11, orden "backtest 2026 real, bollinger 50%
## en 1m y 15m, vwap, whales, bids/asks, terremoto sin falsos positivos")
- **Arm por confluencia PONDERADA** ({SYM}_SCORE_MIN > 0; 0 = gate clasico
  intacto): 0.25 BB-1m(z) + 0.25 BB-15m(z) [= Bollinger 50%] + 0.15 RSI +
  0.15 dist-VWAP(sesion RTH, en ATRs) + 0.15 volumen + 0.05 whales (live).
  El confirm (reclaim verde) sigue siendo el anti-falso-positivo central.
- **Daemon v3**: quotes ws de los 13 syms → data/nbbo_*.txt (bid/ask 1/s;
  gate {SYM}_SPREAD_MAX bloquea confirms con spread ancho, live-only);
  prints >= $50k → data/whale_*.txt (tick-rule dir; bot filtra {SYM}_WHALE_USD).
- **Radar CUSUM con gate de volumen** (terremoto: sin volumen no hay alerta).
- **Backtest 2026 COMPLETO (ene-jul reales IEX), train ene-abr / OOS may-jul**:
  BASELINES CONFIRMADOS en 2.5 meses OOS: DRAM +28.0%, INTC +23.7%,
  ASML +13.1%, AMD +10.0%, QQQ trend +3.7% pf1.6, GLD trend +1.5%,
  SPCX trend +17.5% pf4.8 (vida completa).
  V3 SHIPPED donde gana OOS: NOK S0.72/RSI25/BB2.5 (+2.25% vs -7.2% del
  baseline — el unico baseline que FALLO el año), TSM S0.72/RSI35/BB2.0
  (+10.9% pf1.3), NVDA S0.65/RSI25/BB2.0 (+8.0% pf1.4, WR 54%).
  RECHAZADO por OOS: v3 en DRAM/INTC/ASML/AMD/TXN/TSLA/AAPL (baseline gana);
  TREND_VWAP=1 en gld/qqq/spcx (mejora train, degrada OOS = overfit).
- Regresion verificada: SCORE_MIN=0 reproduce v2 bit a bit (DRAM 20T +20.36%).
- Los 13 .cpp REGENERADOS del master NOK (drift cero); trend mode ahora
  generico ({SYM}_MODE=trend + {SYM}_TREND_CUSUM/{SYM}_TREND_VWAP).

## MOTOR DE SEÑALES v2 (2026-07-10 PM, decisiones de Yunior tras auditoria)
- **HARD STOP alert**: a -X% del entry (default 3%, env {SYM}_STOP) el bot grita
  "SELL-STOP" en vez de callarse a esperar el floor. La posicion virtual se
  cierra (realized) — humano decide, pero enterado.
- **MONEY-ONLY banners**: solo BUY/SELL/STOP hacen banner+voz+sonido; el radar
  (CUSUM/Supertrend/Donchian) va SOLO a ops log + stdout. Ratio ruido:dinero
  era 40-160:1.
- **Posicion persistida**: data/pos_<sym>.txt sobrevive restarts; bars previos
  al entry no la gestionan; su SELL avisa aunque caiga en warm-up.
- **Ops log etiqueta WARMUP**: las lineas de replay historico ya no se
  confunden con señales vivas. `scripts/scorecard.sh [dias]` = expectancy real
  (solo lineas vivas, PnL por bot).
- **Fill realista**: target reporta target_px (limit), no el close del bar.
- **PARAMS POR TICKER via env {SYM}_*** (sweep 30d bars reales 2026-07-10,
  seteados en los keepalives): DRAM BB2.5/RSI35/TGT6 (+15.7% 20T/16W vs
  baseline -3.1%); NOK RSI30/TGT6/TRAIL2 (+1.5%); SPCX RSI30/TRAIL2 (+2.1%);
  TSLA VOL1.0 (IEX fino en TSLA). Baseline clonado era malpractice — re-tunear
  tras cambios de regimen (sweep en scratchpad/bench).
- **Quotes por ws para screener_alert (fix 429)**: alert escribe
  data/screener/ws_watch → daemon suscribe trades (cap 24) → data/quote_*.txt;
  Finnhub queda en 1 llamada/sym/dia (prev_close) + fallback.
- **Knobs de riesgo v2.1 (skills mean-reversion/exit-strategies, 2026-07-10)**,
  todos via env {SYM}_*, default = comportamiento previo: SKIP_OPEN (min sin
  entradas tras 9:30), TIME_STOP_MIN (no revirtio en N min = hipotesis muerta,
  eject bajo floor), EOD_FORCE (15:45 plano SIEMPRE), CONFIRM_STRICT (bar de
  confirmacion con vol>=volMA y close en mitad alta), MAX_DAY (entradas/dia).
- **SPCX = TREND MODE** (`SPCX_MODE=trend`): dip-engine REFUTADO en SPCX
  (0% confirmacion default, -3.8% estricto; ticker joven, solo ~30d de vida).
  Trend: entra en Supertrend-5m flip UP o ruptura del max del dia con CUSUM
  >=1%, sale en flip DOWN/trail 2ATR/stop 2%/EOD forzado, max 2/dia.
  In-sample +17.2% (16/18W con stops reales); OOS corto -> scorecard semanal,
  revisar ~2026-07-24.
- **TSLA: retune agresivo RECHAZADO por walk-forward** (BB2/RSI30/T1.5 dio
  +0.06% en 58 trades sobre 60 dias NUNCA vistos = churn sin edge; los +27-45%
  del estudio eran artefactos never-sell-loss). TSLA queda raro-y-limpio
  (BB3/RSI25/V1.0/T4) + stop 1.5% + skip-open 5m. Regla: NINGUN param se
  shippea sin walk-forward OOS positivo.
- **DRAM/NOK re-validados con stops reales**: DRAM +20.4% (mejor que sin stop:
  el stop corta el drag de bags), NOK +1.5%. Time-stop 240 min añadido a ambos.

## NOTIFICACIONES: URGENTES + C++ (2026-07-10, ordenes de Yunior)
- **Todas las notificaciones son URGENTES y en C++**: `fleet_notify.h` →
  `fleet_notify_urgent()` hace posix_spawn de /usr/bin/osascript directo (sin
  shell, ~1.5ms, inyección imposible, SIGCHLD auto-reap). Los 5 bots la usan.
- Para banners persistentes: System Settings → Notifications → Script Editor
  → estilo "Alerts" (no scriptable, ajuste manual una vez).
- **FIX señales tarde (2026-07-10)**: los bots recibian bars 5-19 min tarde.
  Causa raiz: los bridges ws (nok_bar_bridge, ws_bar_bridge) solo emitian el
  bar al llegar el PRIMER tick del minuto siguiente — en feeds finos (IEX =
  2-3% del volumen) pasan minutos sin tick. Fix: WALL-CLOCK FLUSH — loop de
  2s emite el bar formado cuando su minuto cerro hace >=3s, con o sin tick.
  Ademas stderr de bridges ya NO va a /dev/null → bridge_{dram,nok,spcx,tsla}.log
  (los 429/errores de feed eran invisibles).
- **WEBSOCKETS, no REST (orden 2026-07-10 "avoid rest api calls when u can
  use websockets")**: `alpaca_ws_bridge.cpp` (C++, Network.framework — el
  libcurl del sistema no trae ws). Alpaca free = UNA conexion ws por cuenta →
  un daemon compartido (`./alpaca_ws_bridge NOK SPCX`, vigilado por
  ensure_all/start_all, log ws_daemon.log) se suscribe al canal "bars" (bares
  1m NATIVOS, llegan ~1s tras cerrar el minuto) y los escribe en
  data/bars_<sym>.txt; cada bot popen-ea `./alpaca_ws_bridge read SYM`
  (warm-up REST una sola vez — historia no existe por ws — y sigue el archivo
  cada 200ms). Esto MATO los bridges python de NOK (Alpaca ticks) y SPCX
  (Polygon ws que NUNCA conecto: plan sin acceso ws — bridge_spcx.log lo
  revelo). 2026-07-10 PM: DRAM (Yahoo poll 30s ⇒ ~2-30s tarde) y TSLA
  (Finnhub ws + backfill Yahoo) tambien migrados → el daemon corre
  `NOK SPCX DRAM TSLA`, CERO bridges python, CERO Yahoo (orden #6). Los .py
  viejos en backup/bridges_python_2026-07-10/. Feed iex: minuto sin trades
  IEX = sin bar (REST tiene el mismo hueco, es el mismo feed).
  Velocidad v2 (orden "1ms average", 2026-07-10 noche): el daemon tambien
  suscribe TRADES de los 4 syms y ARMA el bar 1m el mismo (SELF-AGG),
  emitiendolo <=250ms tras cerrar el minuto (sin esperar el push agregado de
  Alpaca de ~0.1-1s; canal bars oficial queda de fallback, reader dedupe por
  epoch). Reader poll 200ms→50ms (hop medido: mediana 20ms). Presupuesto por
  bar: emision <=250ms + hop ~20ms + motor 5µs + banner ~0.2ms ≈ <=0.3s del
  cierre del minuto al banner; el procesamiento en el Mac es <1ms — el resto
  es la fisica del feed. screener: quotes via trades ws (fix 429).

## DOCTRINA DE FLOTA (2026-07-09, orden de Yunior — "from zero to hero")
[HISTÓRICO — trading suspendido 2026-07-10, ver MODO ACTUAL arriba]
Dos sistemas TOTALMENTE SEPARADOS; no se mezclan nunca:

**1) Flota de señales (4 bots C++, SOLO ALERTAS — jamás ordenan):**
`dram/nok/spcx/tsla_signal_bot` + keepalives + bridges. Voz/banner/log para
YUNIOR (humano). Motor validado (capitulación confirmada + CUSUM + Supertrend +
Donchian). Cero conexión con screener; cero acceso a órdenes IBKR.

**2) El "AI dios" — screener/ (el ÚNICO sistema que tradea, Claude decide):**
- **Research AUTONOMO en 3 carriles (2026-07-10)**: 6AM scan completo |
  rescan cada 15 min con TA vetting obligatorio (com.ibtrader.rescan) |
  **fast lane Finviz cada 1 MIN** (com.ibtrader.fastscan: fastscan.py mergea
  movers nuevos al watchlist al minuto; el proximo rescan los veta).
- **Ventana ALL-DAY**: alertas y compras 09:30-15:30 ET (corte RTH de la
  flota); el time-stop de 15 min del watchdog garantiza flat ~15:45.
- **En sesión**: el motor de breakout confirmado (Donchian level + hold 45s +
  CUSUM burst, nuestros algos) detecta la entrada EN los top gainers elegidos;
  Claude (loop bash headless) valida contra el snapshot COMPLETO de la cuenta
  (`exec_trade.py account`: fondos, posiciones, órdenes — obligatorio antes de
  CUALQUIER transacción) y compra; vende para profit completo (target/trail);
  el watchdog determinista C++ garantiza stop-3%/time-stop/dead-man.
- **SIZING zero-to-hero**: 10% de la cuenta por trade al inicio, escalar
  gradualmente con resultados, TECHO DURO 25% (clamp en exec_trade.py ALLOC;
  env SCREENER_ALLOC dentro de [0.01, 0.25]).
- Solo Claude abre posiciones. El watchdog solo hace ventas protectoras. Los
  signal bots jamás tocan la cuenta.

## ESTADO HISTORICO — DRAM-ONLY MODE (2026-07-08, superseded: hoy corren los 4 signal bots + screener)
**Unico bot conectado**: `dram_signal_bot` (C++) via `scripts/dram_keepalive.sh`, 24/5, instancia unica.
- Habla: "buy DRAM now" / "sell DRAM now" (voz sistema Daniel; override `DRAM_VOICE`; killall-say = una sola voz). Sonidos propios: sounds/dram_buy.wav / dram_sell.wav.
- Datos: Yahoo 1m REAL (delayed IBKR rechazado por Yunior; cuenta sin subscripciones RT), bridge `scripts/dram_bar_bridge.py`, almacenado en trades.db (dram_bars).
- Motor C++ con paridad de senales verificada vs Python en 30d reales (BUY $70.09 / SELL +4% identicos).
- Todos los demas bots APAGADOS por orden (sector live, momentum 17-ticker, señalizador python).
- Rebuild: `clang++ -std=c++17 -O2 -o dram_signal_bot dram_signal_bot.cpp`
- Voz premium gratis: System Settings > Accessibility > Spoken Content > Manage Voices > "Ava (Premium)" -> `export DRAM_VOICE="Ava (Premium)"`.

## First Real Trades Log
- 2026-07-08: BUY 1 GNS @ $0.1833 (FILLED, fee $0.0018) — primera posicion real, vive en TFSA.
- 2026-07-08: CUPR rechazada (Error 201 CTCI API canadiense) | fraccional SOXS rechazada (Error 10243).

## NOK Bot + Alpaca Seconds (2026-07-08)
- `nok_signal_bot` (C++23) live 24/5: same detection suite as DRAM, voice "buy/sell Nokia now".
- Data: **Alpaca IEX websocket tick-by-tick** (wss://stream.data.alpaca.markets/v2/iex, trades NOK) -> 1m bars emitted ~1s after minute close + every tick in nok_ticks; REST backfill/gap-fill each 60s; Yahoo fallback. Keys: alpaca.env (GITIGNORED — never commit).
- Replay 30d NOK: 6 BUY/5 SELL signals, ~11 alerts/day.

### Ley de sesión de trading en vivo (orden Yunior 2026-07-18)
Durante horario de mercado, Claude Code es INFRAESTRUCTURA CRÍTICA de trading:
- **Velocidad primero**: respuestas inmediatas, paralelismo máximo (tool calls,
  subagentes, compilaciones xargs -P). La regla secuencial-8GB NO aplica aquí.
- **Vigilancia continua**: siempre mirando tickers, flota, barras (data/bars_*,
  data/nbbo_*) — liderar el análisis o dar soporte al humano que opera, sin que
  lo pida. Trabajo en background (subagentes, Monitor, run_in_background) para
  no bloquear la conversación.
- **Herramientas de ritmo**: usar sleep/schedule/cron/wakeups para loops de
  vigilancia (ej: revisar flota cada 1 min con prioridad al ticker en juego).
- Siempre señal-solamente (ley #0): Claude guía, el humano ejecuta.

## FLOTA KOREA (2026-07-19 — "prepare the fleet for korea", paridad con la flota Toronto)

KRX abre 09:00–15:30 KST = **20:00 ET (domingo–jueves) a 02:30 ET**. Los 3 bots
(skhynix 000660 / samsung 005930 / kospi = KODEX200 069500) son detection-only
(SCORE_MIN=9, señal-solamente), motor idéntico a la flota NA (v5/v6+v6.1
retest-confirm), reloj KST, compilados `clang++ -std=c++2c -O3 -march=native`
(cero warnings, Apple clang 21). Datos: `scripts/korea_bar_bridge.py`
(clientId 86, sub Korea Equities waived = realtime GRATIS via API).

Paridad Toronto portada 2026-07-19 (la ceguera del viernes 2026-07-17 — bridge
"suscrito" sin bars desde el jueves 10:10 KST — no puede repetirse):
- **korea_bar_bridge**: handler Error 1101 + stall-watchdog (5 min sin bars en
  sesión KRX → resub + banner `🇰🇷 KRX BRIDGE CIEGO` ProAlarm + espejo Desktop),
  cooldown 5 min anti-thrash pre-open (cazado en vivo; portado también al
  daemon NA `ibkr_bar_bridge.py`).
- **tws_watchdog**: ventana ahora incluye **domingo ≥19:45 ET** (la sesión KRX
  del lunes abre domingo 20:00 ET — antes el domingo estaba excluido entero) y
  excluye viernes ≥20:00 (KRX no abre sábado). El proxy de salud lee también
  `bars_{skhynix,samsung,kospi}.txt`. FIX: la detección ZOMBIE (446360c) contaba
  fallos pero jamás actuaba — ahora 3 zombies seguidos relanzan TWS (banner 🧟 +
  voz), con gracia 15 min post-open (sin falsos positivos a las 04:00/20:00).
- **Voz**: todo el camino usa la voz Siri del sistema via `scripts/speak.sh`
  serializado (watchdog y heartbeat migrados; `-v Daniel` erradicado del código
  activo). `speak.sh` pronuncia `skhynix`→"S K Hynix", `kospi`→"Kospi".
- **fleet_sleep / focus_ticker**: si `data/fleet_sleep` tiene `wake:` debe ser
  ANTES de 19:45 ET dom–jue o la flota duerme la sesión KRX (cazado 2026-07-19:
  wake apuntaba al lunes 08:00). `data/focus_ticker` debe listar
  skhynix/samsung/kospi o el tick de 5 min los mata.
- **price_alarm** cubre Corea: línea `skhynix <precio>` (o samsung/kospi) en
  `~/Desktop/price-alerts.txt` — usa `data/nbbo_<name>.txt` del bridge.
