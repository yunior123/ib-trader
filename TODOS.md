# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`. Doctrina: skills `gamma-regime-walls`, `gexa-terminal`, `postmarket-cage-release`, `tradingview-terminal`.

## ✅ HECHO (2026-07-20/21)
- [x] Post-mortem imanes 2026-07-20 (hacia el imán, jamás a través del muro; decay por toques)
- [x] Investigación NOK (crash = Ericsson AI-cost read-through; 40% layoff = sin evidencia; earnings 23-jul BMO)
- [x] SPY añadido a la flota (bot C++ + keepalive)
- [x] Impresora: Brother NO era tuya (removida); HP 9120e bloqueada por tinta color (firmware HP+); PNGs a Desktop
- [x] Árboles de escenarios NOK/NVDA/QQQ/SPY + estrategias con opciones a Desktop
- [x] Estudio gexa.ai → régimen gamma; skills `gexa-terminal` + `gamma-regime-walls`
- [x] 26 skills por ticker + `korea-memoria` con patrones 6m + forma intradía 60d (`skill_patterns_refresh.py`)
- [x] Sistema diario: launchd `dailyplans` (04:00/08:30/09:12) + `postmortem` (16:20)
- [x] Generador 26 tickers (IBKR-first, gexa, VX CBOE, Finviz, Korea, futuros, griegas, árbol, forma)
- [x] Calibración empírica por setup×régimen (Wilson, no por ticker) — `calibration_ledger.py`
- [x] Patrones medidos (H&S/dobles/triángulos, follow-through empírico) — `pattern_detect.py`
- [x] Engranaje QQQ/SPY (amplitud ponderada de componentes) — `index_breadth.py`
- [x] Posters X: premarket/realtime/postmortem, ledger 10/día $4/mes, humor, "No consejo fin."
- [x] Draft X compacto+visual (escalera emojis 🔴🎯📍🟢🛑) + Corea semis + tendencia overnight
- [x] `force_meter.py` — fuerza/agotamiento en vivo (4 fases → acción de stop)
- [x] `posthours_cage.py` — picardía jaula 0DTE→liberación after-hours (ballenas semanales)
- [x] Healthcheck 3x/día auto-curador (`fleet_healthcheck.py`, launchd)
- [x] Flota canónica única `data/fleet.txt` (26) — nadie queda atrás
- [x] Alarmas flujo put/call alineadas a 21 tickers; DB limpia; cadena notificación verificada
- [x] X auth verificado (@YuniorR62327146, 200 OK, read-only, sin gastar post)
- [x] Tests Python 48 pasan (incl. put-call parity); bug arreglado (main() sin guard en generador)
- [x] TradingView: zoom inspección + zoom chart verificados; skill documentada

## 🔄 EN CURSO / PENDIENTE
- [x] Magnets gexa dominados: find→scroll_to ref→read_page (estructurado, no screenshot); parser gexa_parse los captura
- [x] X posts scheduled cada día verificado (4AM premarket + realtime daemon + 16:20 postmortem)
- [x] Auto-mejora semanal (domingo 19:00): refresca patrones/formas 6m + recalibra + corre tests + reporta
- [x] Conocimiento consolidado en LEARNED.md + skills + memoria; herramientas reutilizables xpost.py + gexa_parse.py
- [x] **Europa para ASML**: momentum Ámsterdam (ASML.AS ~6h lead) + STOXX50 al plan+draft (prob bump, línea 🇪🇺)
- [x] Tests C++23: 25/25 correctness pass + benchmark (Bollinger 9.46ns/op, resto inline, 0 bugs)
- [ ] Verificar gexa headless conecta REALMENTE en el run de 4am (Chrome/extension sin sesión interactiva)
- [ ] Raíz del `com.ibtrader.fleet` exit=78 (EX_CONFIG) — hoy se sortea con el healthcheck que relanza; falta arreglar el porqué bajo entorno launchd
- [ ] Primera cacería REAL de jaula-liberación (lunes al cierre, cuando el after-hours vive)
- [ ] Documentar force/cage/healthcheck/breadth en `docs/DAILY-SYSTEM.md` (parcial)

## 💡 IDEAS / FUTURO (cuando se pidan)
- [x] Tweets con imagen adjunta (árbol PNG en x_media/) + gexa gamma (flip/dealer/POC) en posts intradía
- [ ] `opt_tick_watch` event-driven para el strike ACTIVO (tiempo real, no poll 5min) — filo de ejecución
- [ ] Fuerza/agotamiento por-tick plegada en los signal bots C++ (si se quiere el filo en la decisión)
- [ ] Calendario macro (CPI/FOMC/NFP) al PDF — "no operar el print"
- [ ] Revisar plan Polygon (POLYGON_KEY en feeds.env, quizá opciones/agregados mejores)

## 📌 REGLAS QUE NO SE ROMPEN
- Señal-solamente (jamás ordena). Aditivo + degradación limpia. Respaldo en `backup/` antes de tocar el generador.
- Presupuesto opciones = SOLO 0DTE (semanales requieren excepción explícita).
- `notify_relay.sh` DEBE estar vivo (fue el fallo de notifs). Print o nada. 3 pérdidas = fin.

## 2026-07-21 sesión viva
- [ ] opt_whale_watch: filtrar strikes sin security definition (QQQ 712.5 20260724 spamea Error 200 en loop) — cachear contratos inválidos y saltarlos. Arreglar POST-CIERRE.
- [ ] launchd exit 78 (fleet/scan/screener/fastscan/rescan/screener6am) + healthcheck exit 1 — cazar EX_CONFIG con calma post-cierre.
- [ ] 7/22 8:30: confirmar fichas CLSK/INTC vs gaps overnight (data/fichas_2026-07-22.txt) + KOSPI check
- [ ] x_post_common: sanitizar a MAX 1 cashtag por post (X rechaza 403 con 2+; el $4.7B tambien cuenta como cashtag si va pegado a letras — revisar regex)
- [ ] opt_whale_watch v2: alarma por PREMIUM NETO en dolares (mid×vol por lado, umbral ±$20M o delta brusco/30min) ademas del ratio de volumen — el tide -53M del 7/21 no sono porque P/C volumen era 0.86. Las ballenas caras y silenciosas tambien deben sonar. POST-CIERRE.

## 2026-07-23 — Chart cockpit GEX en vivo (charts/live.html + chart_bridge.py, estilo gexa)
Hecho: lightweight-charts v5 + ib_async (TWS 7496 realtime) · combo_tl (Supertrend Buy/Sell + Madrid ribbon + BB/SMA/VWAP/MACD + trendlines) · selectores ticker/intervalo · GEX/flip/muros en tiempo real (levels_loop 15s, spot vivo) · escala $/1% = gexa (verificado 736: -371M vs gexa -369M) · imán(oro)/acelerador(morado) por signo, semi-transparente+blur · flip 0DTE estático + toggle 0DTE↔ALL-EXP (Vanna salta en ALL) · VEX/vanna/charm + chip Vanna · dealer-pressure score -100..100 · expected-move cone (spot·IV·√T) · nuestras señales (whale/flow/alarma) como marcadores · botones info ⓘ + Guía · dominancia POC %C/%P · régimen TRANSICIÓN · icono custom. Skill `gexa-framework`.
- [ ] **VIX**: código LISTO (reqMarketDataType(1) realtime + chip). Falta suscripción IBKR **CBOE Global Indexes** (~$1.50/mes) → Yunior la activa. NO es crítico (ningún cálculo lo usa; EM/vanna usan IV por-contrato). Aparece solo al suscribir.
- [ ] **Banda de fragilidad / true-flip ajustado por vanna** (gexa) — la ÚNICA feature que necesita VIX de verdad: mide cuánto movería el flip un shock de VIX (banda <5pt estable, >15pt frágil). Construir CUANDO haya VIX vivo.
- [ ] **Migration-trail del flip** (polilínea del flip histórico: horizontal=estable / inclinada=deriva / dentada=régimen no fiable). Buildeable ya.
- [ ] **Volume Profile (VPVR)** desde las barras — POC de volumen vs POC de gamma = confluencia (edge). Buildeable ya.
- [ ] **Pin-risk score** (concentración de |gamma| × proximidad × 1/T; "fortress pin" si POC coincide con call wall). Buildeable ya.
- [ ] **Charm al chart** (ya está bs_charm/build_exposure en gex_core; falta capa CHARM en el toggle junto a GEX/VEX) — drift/pin tardío.
- [ ] Ampliar strikes del cache (`opt_chain_cache.py`) para clavar el flip 0DTE exacto de gexa (hoy near-ATM 730-749 lo deja a ~0.5%).
- BLOQUEADAS (necesitan tape firmado + dark-pool licenciado que NO tenemos): True Dealer Book, Dark Pool Nodes, DIX, Market-Tide firmado, GEX direccional. Sustituto casero = nuestros daemons whale/flow.

## 2026-07-23 EOD — gexa se va + fixes chart
- [ ] URGENTE (antes de que gexa muera): AMPLIAR strikes del cache (opt_chain_cache.py band ±6%→±15%, MAX_STRIKES 20→~40) para igualar la cadena completa de gexa, y VALIDAR nuestros números vs gexa MIENTRAS SIGA VIVO (última oportunidad de calibrar contra la verdad).
- [ ] Chart: barra de precios a la derecha muestra precios incorrectos AFTER CLOSE — probable autoscale jalado por las líneas de niveles (muros/EM/alarmas) lejos del último precio cuando las velas dejan de actualizar. Fix: constreñir autoscale a la serie de velas (autoscaleInfoProvider) o esconder líneas lejanas tras el cierre. Verificar al despertar.
- [x] Fix tickMarkFormatter (hora Toronto solo en marcas de tiempo >=3, no en día del mes) — aplicado, se ve al despertar.
