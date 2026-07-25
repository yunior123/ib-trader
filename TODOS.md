# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`. Doctrina: skills `gamma-regime-walls`, `gexa-terminal`, `postmarket-cage-release`, `tradingview-terminal`.

## 🔴 SESIÓN 2026-07-25 (madrugada) — peticiones de Yunior, apuntadas AL VUELO
> Regla nueva (`~/CLAUDE.md`): cada petición se anota aquí EN EL MOMENTO, con las palabras de
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

**DELEGADO a agentes (en curso):**
- [ ] "make the walls look like in there … those look like nice gamma walls" (captura de
      @BullflowIO, `GEX: Bubbles`) → burbujas GEX en `charts/live.html`, coloreando **pin vs
      trampilla** (que Bullflow no muestra). *delegado*
- [ ] "do we have spx in fleet? … make sure we use it to measure brújula" → verificar
      entitlement de índice CBOE antes de añadirlo (un símbolo muerto encoge denominadores). *delegado*
- [ ] "engine ibkr reemplazo local … con polygon, datos reales" → `replay.cpp` (simula el DISCO,
      no el socket) + cadenas del archivo. El gateway socket se **canceló** por decisión de
      Yunior ("si no hace falta websocket fake y es listo, mejor"). *delegado*
- [ ] Backfill Polygon 2 años + archivador diario de cadenas con griegas REALES + reconstrucción
      del pasado (21 días) con error medido contra IBKR. *delegado*
- [ ] Las **30 features minadas** de SpotGamma/TrendSpider/MenthorQ + **13 skills** +
      `docs/FEATURES-MINED-2026-07-25.md` + `docs/research/` (6 dossiers, 496 KB). *delegado*

**PENDIENTE (no delegado aún):**
- [ ] Conmutar los keepalives a los binarios C++ nuevos (`fleet_consensus`, `gate`) — lo decide Yunior.
- [ ] Ola 1 de las 30 features: los 5 must-build son `barrier-labels`, `null-control`,
      `book-quality gate` (su fix del signo del Muro YA está en `gex_core.py`),
      `poly-aggs-backfill` (en curso) y `chain-honesty`.

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

## 2026-07-24 — permiso de bots (TCC) + debug TWS
- [x] Auto-chequeo de permiso en fleet_keepalive_start.sh: si no puede escribir el HUD Desktop -> voz DANGER + data/PERM_DENIED (nunca más pérdida silenciosa).
- [ ] PERMANENTE (Yunior, System Settings > Privacy & Security > Full Disk Access): añadir /bin/zsh, /usr/bin/python3, venv-chart/bin/python, y los binarios C++ (price_alarm, flow_pulse, qqq_xray). Único fix que garantiza permiso en TODO contexto (launchd/reboot).
- [ ] POST-CIERRE (bajo riesgo con mercado cerrado): centralizar la ruta de señales del Desktop a data/trading-signals/ del repo (siempre escribible) en los 19 archivos (3 C++ = recompilar). Elimina la dependencia TCC del Desktop de raíz. Symlink Desktop->repo para visibilidad de Yunior.
- [x] Debug TWS: conexiones SANAS (5 conn ESTABLISHED, barras/cache frescos, 253 señales hoy). El 326/clientId82 era test viejo. Ruido benigno: opt_chain 'No security definition' (strikes inexistentes) + chart_bridge Error 366 (cancel hist-data).
- [ ] gexa SIGUE VIVA (HTTP 200): calibrar nuestro flip vs gexa (ampliar strikes) — pendiente de anoche, hacer en ventana no-crítica.

## 2026-07-24 EOD — CACERÍA DE BUGS (rama `hunt/bugfix-2026-07-24`)
Workflow de 15 agentes: 87 hallazgos brutos, pero **8 agentes murieron por límite de gasto —
incluidos los 6 refutadores y el team lead**. "0 refutados" NO significa 0 falsos positivos:
significa que nadie pudo verificar. Los de abajo los confirmé A MANO uno por uno.

- [x] **AUTO-CANCELACIÓN** (crítico, evidencia en producción). `openOrder()` cancelaba cualquier
  orden `OE:` sin comprobar si era nuestra y de esta sesión; TWS emite ese callback SIN PEDIRLO
  por cada orden colocada → el motor se cancelaba solo. `ledger/orders.jsonl` id=33: un intent y
  CINCO cancel que nadie pidió, en 150ms. Llenó de milagro por ser acción marketable; una opción
  0DTE con libro fino se habría cancelado tras el print. Fix: usar el flag `reconciled_` que YA existía.
- [x] **SIDE PERDIDO** (crítico). `chart_bridge` no pasaba `side` → el motor caía a default SELL.
  Cerrar un CORTO manda "buy" → se vendía otra vez y DUPLICABA el corto. Con largos coincidía por
  casualidad. Fix: pasar side+secType, y el motor RECHAZA el cierre si el side no es buy/sell.
- [x] **STOP DUPLICADO tras reconnect** (crítico). Se reseteaba `stop_armed` a ciegas creyendo que
  reconcile canceló el nativo viejo, pero `openOrder` los ADOPTA → segundo STP sobre la misma
  posición → al disparar vendía el doble y te dejaba CORTO en descubierto, ambos GTC. Se disparaba
  en CADA reconexión y el Gateway reinicia a diario. Fix: `adopted_stop_id()` + adoptar el vivo.
- [x] **FILL PARCIAL sin stop** (alto). Un parcial vivo caía a ACK, el FSM no pasaba a FILLED y la
  posición real quedaba SIN STOP hasta que TWS matara la DAY al cierre. Fix: emitir FILL por lo
  llenado + re-armar el stop si luego llenan más.
- [x] **TOPE POR ORDEN**: `run_gate` sólo validaba la prima de UN contrato; el desembolso real era
  qty×prima. Nuevo `--max-order` (default = `--budget`). Verificado: qty=4 → VETADO $608.
- [x] **index_breadth** partía por "," archivos separados por ESPACIO → guarda de frescura de 600s
  era CÓDIGO MUERTO y cada corrida caía en silencio a yfinance retrasado.
- [x] **math_test no probaba NADA**: cero `#include` del proyecto, testeaba copias privadas. El
  "25/25 pass" de la línea 35 de este archivo era humo. Ahora incluye `engines/bb_core.h` con
  valores de referencia exactos: 39/39 en release Y ASan. Cazó un bug de mis propios datos al instante.
- [x] Skill `bug-hunter` con los 11 olores demostrados + greps de detección.
- [ ] **~84 hallazgos SIN VERIFICAR** del workflow (`tasks/w7i2a7lhe.output`). Re-correr los
  refutadores cuando haya presupuesto. NO tratarlos como bugs hasta refutarlos.
- [ ] **auditoría de TODOS.md** (los 40 `[ ]` de este archivo): el agente murió sin correr.
- [ ] `bench.cpp` mide al OPTIMIZADOR: reporta 2.4e12 ops/s (imposible en M1 ~3.2GHz). El
  "9.46 ns/op" de la línea 35 no es real. Arreglar con sumidero volátil / DoNotOptimize.
- [ ] Los 24 bots se compilan con `c++20 -O2` sin arquitectura nativa (`deploy_signals_to_data.sh:13`),
  incumpliendo la doctrina propia (c++23/26 -O3 -mcpu=native). Cambio de 1 línea + recompilar 24.
- [ ] DESPLIEGUE PENDIENTE: los arreglos del motor están compilados pero la flota sigue con los
  binarios viejos. Recompilar y reiniciar SOLO con mercado cerrado.

## 2026-07-24 — señales movidas a /data (permiso garantizado, sin TCC)
- [x] FASE 1 (live): bytes migrados Desktop -> data/trading-signals/ (277 líneas, sin pérdida); ~/Desktop/trading-signals ahora es symlink -> repo (visibilidad + los daemons vivos escriben vía symlink a /data). Cero downtime.
- [x] FASE 2 (fuente): 19 archivos editados para escribir DIRECTO a data/trading-signals (Python via __file__, shells via $ROOT, C++ via fleet_notify.h relativo). AST verde, C++ compila (c++20). Cero refs de código a Desktop.
- [ ] DEPLOY AL CIERRE: `zsh scripts/deploy_signals_to_data.sh` -> recompila 28 binarios C++ (24 bots + price_alarm/flow_pulse/qqq_xray/korea/finviz) + reinicia flota -> activa el código /data-directo. Tras esto los bots SIEMPRE tienen permiso (no dependen de TCC/Desktop, funciona bajo launchd/reboot). El symlink Desktop se queda para que Yunior siga viendo las señales.
- Nota: fase 1 ya da "todo en /data"; el deploy solo elimina el último rastro del path Desktop del binario.

## order_engine — HALLAZGOS AUDITORÍA (2026-07-24, agentes ultracode)

### ✅ ARREGLADOS Y COMPILADOS (esta sesión)
- [x] `frozen_` nunca se limpiaba tras reconnect → el motor dejaba de operar el resto del día (nextValidId ahora lo limpia)
- [x] `commands.jsonl` offset TOCTOU → posible **doble-close** (ahora avanza solo por líneas completas)
- [x] Fill parcial dejaba posición **sin stop** (ahora push FILL + stop sobre `filled_qty`)
- [x] `modify()` sobre STOP escribía `lmtPrice` en vez de `auxPrice` → mover el stop era **no-op silencioso**
- [x] **Idempotencia entre reinicios**: zona ya llena volvía a COMPRAR al reiniciar (lee `state/<sym>.jsonl`, marca DONE)
- [x] `reconcile()` cancelaba stops huérfanos → posición desnuda (ahora los **adopta vivos**)
- [x] Disarm-on-exit cancelaba el stop sin aplanar → ahora **deja stops vivos** + aviso en voz alta
- [x] Allowlist de cuenta solo en live → ahora **siempre** (paper=DUR197573 / live=U26942420; manda el broker, no el modo)
- [x] Zona borrada del chart mataba el stop de una posición abierta → ahora lo conserva
- [x] Watch-local stop vendía `z.qty` (sobre-venta en fill parcial) y remataba a $0.01 sin cadena → usa `filled_qty`, no remata

### ⬜ PENDIENTES (del hunt; 17 quedaron sin verificar por límite de sesión)
- [ ] **Sin tope de exposición AGREGADA por cuenta** — hoy es por zona ($200 opción / $3000 acción); N zonas multiplican el gasto sin techo global
- [ ] **Sin reconciliación contra `reqPositions`** — la fuente de verdad debe ser la cuenta IBKR remota, no el estado local
- [ ] Presupuesto de opciones es **por contrato**, no por zona: `qty>1` multiplica el gasto sin cap total
- [ ] Panel `close` confía en `cqty` sin comparar contra la posición real → posible sobre-venta/flip a corto (TFSA no shortea)
- [ ] `close` del panel no cancela el stop nativo de esa posición → queda stop huérfano tras cerrar
- [ ] STOP nativo **rechazado** no se reporta como fallo de protección (REJECTED solo se maneja para la entrada)
- [ ] Reconnect re-arma stops sin verificar que `reconcile` terminó (el arranque sí aborta, el reconnect no)
- [ ] Allowlist live usa `find()` sobre la lista completa de `managedAccounts` (substring, no exacto)
- [ ] Clamp asimétrico del stop de opción (caso corto sin cota superior)

### ⬜ UI / DATOS
- [ ] **Live market data** (diferido): suscripción IBKR para API en paper, o cablear Finnhub (key en feeds.env). Sin esto el spot está STALE y las zonas no disparan
- [ ] Selector de timeframe compacto estilo TradingView
- [ ] Chip de zona dice "Ccall" para acciones — label instrument-aware
- [ ] Skills de QA engineer + suite de tests automatizada
- [ ] Optimizar latencia de ráfaga (mediana 1.1s por serialización del pump 2s; min real 113ms)
