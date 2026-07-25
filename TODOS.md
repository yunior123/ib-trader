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
- [ ] **BUG VIVO destapado por lo anterior (alta prioridad)**: `data/whale_qqq.txt` y
      `data/whale_spy.txt` son **0 BYTES** — los DOS CAPITANES no tienen cinta firmada, y también
      están vacíos aapl/amd/asml/gld/intc/tsm/txn (8 de 14). El cap de tick-by-tick de IBKR
      (err 10190) se reparte **por orden de la lista**, así que se lo llevaron DRAM/NOK/NVDA/SPCX/
      TSLA. La regla 12 entera (capitanes) corre sin su input firmado. Arreglo: prioridad explícita
      QQQ→SPY→SMH antes del best-effort. **Es de `scripts/`: otro agente o sesión siguiente.**
- [ ] Correr `docs/probes/hiro_probe_ibkr.py` en la próxima sesión viva (dom 20:00 / lun premarket):
      mide el cap REAL de tick-by-tick y si OPRA por contrato está permitido. Sin ese número el
      resto de HIRO es especulación.

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

**OLA 1 — delegada entera (2026-07-25 ~04:15), 15 items en 4 agentes:**
- [x] #1 `barrier-labels` **hecho 1a97611** + #2 `null-control` **hecho c1e3336**. Los dos únicos
      cuya salida es RESTAR. `scripts/barrier_labels.py`, `scripts/null_control.py`,
      `docs/EDGE-SCOREBOARD-2026-07-25.md`, `docs/NULL-CONTROL-2026-07-25.md`.
      Medido: 13-27% de las señales que se cuentan GANADAS habrían sido STOPEADAS antes; el
      re-etiquetado NO es una resta uniforme (bollinger +6.5pp, cusum -28.6pp) porque la barrera
      SÍ ve el TP intra-camino. ρ̄ de la flota = **0.41** → bollinger `n=1154` queda en
      `n_eff=89` (CI estrechados ×3.6) y sale **UNPROVEN**: no bate a entradas ALEATORIAS
      emparejadas (0.482 vs 0.496). **0 de 131 celdas fuente×sym×bucket pasan BH-FDR q=0.10.**
      Propuesta en `data/signal_enable.PROPUESTO.json` — `signal_enable.json` NO tocado.
- [ ] PENDIENTE de #1/#2 (no bloqueante, apuntado 2026-07-25): (a) cablear
      `data/calibration_barrier.json` + `null_control.json` a `direction_view`/PDF/compass para
      que la prob cantada sea la de barrera y las celdas UNPROVEN pierdan voz — hoy solo se
      MIDE, nadie lo consume; (b) `poly_bars` acaba el **2026-07-24 19:59 ET**: 197 señales del
      07-25 quedaron sin etiquetar (`skip_entry_stale`); (c) el null de **16 niveles aleatorios**
      (parte B de la ficha #2) espera a `level_react`/`level_events` de la feature #8;
      (d) la ruta sub-minuto no existe → `ambig_pct` 2.1% es irreducible con `poly_bars`.
- [ ] #3 `book-quality` + #5 `chain-honesty` + #6 `flip-honesty`+congelar 09:35 + #13 roll-off
      → *agente*. Medido: NVDA 0/40 filas con IV, SPY 1/80 → el GEX corre sobre griegas ausentes.
- [ ] #9 `truth-lock` + #10 `em-envelope` + #12 `voice-budget` + #14 `pin-clock` +
      #15 `equity-prints` + #16 `chain-cube` + #18 `levels-5min` → *agente*.
- [ ] #4 `poly-aggs-backfill` → *agente* (2 años × 30 syms; hoy solo 21 días).
- [ ] #11 `features-fanout` + **tope duro de 14 factores** → **ME LO QUEDO YO** (toca `compass.cpp`).
      Sin esto, 30 features = una flecha cuya varianza de prob colapsa a ~58% constante.

**PENDIENTE (no delegado aún):**
- [ ] "el app ib-trader Cockpit should have a nice icon" (Yunior 2026-07-25) → `AppIcon.icns`
      propio en `macapp/`, generado con todos los tamaños (16→1024, @2x) vía `iconutil`, y
      referenciado en el `Info.plist` (`CFBundleIconFile`). Hoy usa el icono genérico. Que el
      `macapp/build.sh` lo empotre en cada build.
- [ ] Conmutar los keepalives a los binarios C++ nuevos (`fleet_consensus`, `gate`) — **lo decide
      Yunior**. Mi recomendación: modo SOMBRA primero (el C++ escribe a fichero aparte y NO habla,
      se compara una sesión con el Python, y solo entonces se conmuta la voz).
- [ ] **Orden de Yunior 2026-07-25**: "después de ola uno testea todo, then todas las olas.
      Testea con Claude in Chrome as needed." → tras ola 1: suite completa + verificación en
      Chrome del chart (burbujas GEX, flecha escalando, tooltip), y luego olas 2 y 3.

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
- [x] ~~Verificar gexa headless conecta REALMENTE en el run de 4am~~ **MUERTO 2026-07-25**: gexa.ai
      desaparecio ("gexa is gone now, we are on our own"). Mapa gamma calculado EN CASA:
      `scripts/gex_snapshot.py` -> `data/gex_snapshot.json` (griegas MEDIDAS de Polygon, 25-30 syms
      vs los 16 que se scrapeaban). Consumidores recableados <commit 631f40b..>: daily_fleet_plans
      (regimen con procedencia en el PDF), x_post_common + 3 posters X, whales_week_map,
      skill_patterns_refresh, daily_archive (lee los archivos viejos igual), fleet_healthcheck
      (ausencia del mapa = ROJO), dailyplans_run.sh (fuera el `claude -p` de scraping).
      Skill `gexa-terminal` y `scripts/gexa_parse.py` marcados JUBILADOS.
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
- [ ] launchd exit 78 (fleet/scan/screener/fastscan/rescan/screener6am) — cazar EX_CONFIG con calma post-cierre. **El `healthcheck exit 1` YA está hecho (2026-07-25)**: salía 1 con cualquier aviso 🟡, launchd lo grababa como job fallido y la corrida siguiente auditaba su propio `LastExitStatus=1` y lo cantaba como aviso nuevo (bucle). Ahora exit 0 con solo avisos, exit 2 solo con 🔴, y el job propio (label leído del plist) queda fuera del audit. Verificado: `launchctl kickstart` → LastExitStatus 1 → 0.
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

## OLA 1 features minadas — agente chain/flip/book/next-day (2026-07-25)
Spec: `docs/FEATURES-MINED-2026-07-25.md` (#5 chain-honesty, #6 flip-honesty, #3 book-quality, #13 next-day-map roll-off).
- [x] **#5 `chain-honesty` — matar las degradaciones silenciosas** — hecho: inversion de IV por
      biseccion + forward por paridad en `gex_core`, `iv=0.3` BORRADO, cabecera honesta en
      `opt_chain_cache.py`, contrato en `docs/CHAIN-HEADER.md`, `greeks_ok_pct<0.5` -> claves
      gamma a `null` (jamas 0). Medido: RTH 100% griegas, 16:16 = 0% en toda la flota.
- [x] **#6 `flip-honesty` + congelar a 09:35** — hecho: el repreciado GANA (antes se pagaba y se
      tiraba), `flip_src`/`flip_why`, TODAS las raices con biseccion, `trapdoor_root`,
      `flip_open` congelado / `flip_live` diagnostico.
- [x] **#13 `next-day-map` roll-off (bug determinado)** — hecho: `exp_status()` rueda el
      vencimiento EN EL CIERRE (16:00 ET), no a medianoche. Era la causa del salto de MANADA
      de las 00:00:45.
- [x] **#3 `book-quality gate` — coeficiente MULTIPLICATIVO** — `scripts/book_quality.py` ->
      `data/book_quality.json`, etiquetas THIN/BIFURCATED/NEAR_FLIP/STABLE_PIN + coef.
- [x] **`vol-trigger` (#20) congelado a 09:35** — `scripts/vol_trigger.py` -> `data/vt_<sym>.json`
      (`./compass` ya lo lee: `vt_open`).
- [ ] PENDIENTE (no entra en OLA 1): percentiles `book_pctile`/`impact_pctile` necesitan 20
      sesiones de snapshot COMPLETO de Polygon (feature #7). Hoy salen `null` declarados y el
      `coef` cae al suelo 0.35. Se acumulan en `data/book_quality_hist.jsonl`.
- [ ] PENDIENTE: `poly_chain_archive.py` NO tiene job de launchd — hoy solo hay 3 simbolos
      (qqq/dram/nok) archivados a mano. Sin el, fuera de RTH la flota entera queda MUTEADA.
- [ ] PENDIENTE: cablear el `coef` de `book_quality` como MULTIPLICADOR en `direction_view`
      (pesos flip 1.5 / walls 1.0 / magnet 1.1) y el badge en `charts/live.html`.

## OLA 1 — archivadores, guardas de integridad y presupuesto de voz (agente, 2026-07-25)
> 7 features, 7 commits, 101 tests nuevos. Suite completa: 311/311 en verde.

- [x] **#16 `chain-cube archive` + retencion** — `scripts/chain_cube_archive.py`: lector UNICO
      de los dos formatos (texto IBKR con el `-1.00` intacto + `chain_full` de Polygon), indice
      de cobertura honesta (`data/chain_cube_index.json`: 2984 fotos, 171.216 filas) y
      retencion medida (7,40 MB/dia -> 2,2 MB/dia agrupado). `6bae616`
      **`--apply` SIN activar**: `local_option_scorer.py`, `option_vehicle_backtest.py` y
      `replay.cpp` leen las fotos SUELTAS por glob. Migrarlos al lector antes de agrupar.
- [x] **#18 `levels-5min archive`** — `scripts/levels_5min_archive.py`: copia cada 5 min sin
      tocar el generador (proceso aparte, 0 MB RSS en `chart_bridge`), con `age_s`/`stale` para
      que copiar un fichero atascado 78 veces no parezca densidad. ~4,7 MB/dia. `c91c375`
- [x] **#15 `equity-prints archiver`** — `scripts/equity_prints_archiver.py`: salva la cinta
      firmada ANTES del trim de 900 s SIN tocar `ibkr_bar_bridge.py` (poll 120 s = margen 7,5x).
      Primera corrida: 7477 prints salvados. ~5,6 MB/dia, retencion 180 dias. `b0c1b8a`
- [x] **#9 `truth-lock`** — `scripts/truth_lock.py`: huella SHA-1 de 120 barras cerradas por
      sym; inyeccion sobre el `bars_nvda_ibkr.txt` REAL detectada (close +0,05). Banner + tabla
      propia, SIN voz. `--audit` da el % de señales sobre datos sucios (hoy `null`, no 0%).
      `ea26bc5`
- [x] **#10 `em-envelope`** — `data/em_<sym>.json`, 26/30 vallas. Dos bugs cazados con datos
      reales: vallaba el lunes con el straddle 0DTE del viernes (em 0,11%) y la sesion objetivo
      la fijaba el snapshot. `176caea`
- [x] **#14 `pin-clock`** — `data/pin_<sym>.json` descriptivo, `p_pin` SIEMPRE null. Medido: max
      pain de QQQ 702 con cadena completa vs 691 con la banda de IBKR (sesgo demostrado).
      DRAM PIN_DAY 55,0. Colinealidad n=3 rho=-0,52 -> DATOS_INSUFICIENTES. `d21f2eb`
- [x] **#12 `voice-budget governor`** — `scripts/voice_budget.py` + 12 lineas en `speak.sh`.
      DANGER ni pasa por el gate, interruptor `data/voice_budget_enable` AUSENTE (inerte),
      fail-open (solo el codigo 42 silencia). Verificado en vivo con el daemon: DANGER habla con
      el presupuesto agotado, SIGNAL sale como `budget_suppressed`. `daf90de`
- [ ] PENDIENTE: **cargar los 5 `.plist`** (`scripts/com.ibtrader.{prints,levels5m,truthlock,
      cubeindex,fence}.plist`, `plutil -lint` OK, sin cargar a proposito) — decide Yunior.
- [ ] PENDIENTE: **encender el presupuesto de voz** con `touch data/voice_budget_enable` cuando
      Yunior quiera. Hasta entonces es codigo muerto (por diseño).
- [ ] PENDIENTE (#15): ningun motor de absorcion hasta >=20 sesiones archivadas por sym; hoy 1.
- [ ] PENDIENTE (#18): ninguna feature puede condicionar sobre gamma a tiempo de etiqueta hasta
      que `levels_5m.jsonl` tenga >=40 sesiones; hoy 1.
- [ ] PENDIENTE (#14): el kill por colinealidad de `pin-clock` necesita n>=10 syms con
      `chain_full` (hoy 3) -> depende del job de launchd de `poly_chain_archive.py`.

## 2026-07-25 — hallazgos al cablear book_quality (medidos, no sospechados)
- [x] `book_quality` CABLEADO en `direction_view` como multiplicador de los pesos gamma
      (flip/muros/iman) + badge `.bq` en `charts/live.html` — hecho b91de93/13c903d.
- [ ] **EL "THIN" DE 25/26 SIMBOLOS ES UN ARTEFACTO DE LA FUENTE, NO UN HECHO DEL MERCADO.**
      `book_quality.py` lee las cadenas de `ibkr_tws`, que fuera de RTH traen **0% de griegas**
      (AAPL: 20 contratos, `greeks_ok_pct 0.0` -> THIN, coef 0). Pero `poly_chain_archive` dejo
      HOY las 30 cadenas con griegas **REALES** de Polygon: AAPL 96 contratos / **94%** con
      gamma+OI medidos, NVDA 56 / 98%, QQQ 854 / 96%, y 4-7 vencimientos cada una. Es decir:
      el libro de AAPL NO es fino, es que no lo estabamos mirando donde hay datos.
      -> ACCION: que `book_quality.py` prefiera `data/history/<fecha>/chain_full_<sym>.json`
      cuando `ibkr_tws` de <50% de griegas, y marque `chain_src` en consecuencia. Mientras no
      se haga, la flota entera opera con los niveles gamma apagados fuera de RTH.
      (`book_quality.py` estaba en la lista de NO-TOCAR de esta sesion — de ahi que quede aqui.)
- [ ] **gexa es hoy CASI REDUNDANTE, y en un caso esta MAL.** Comparado el snapshot (16 syms)
      contra el flip/regimen calculado con `gex_core` sobre las cadenas Polygon del dia:
      SPY gexa 747.0 vs nuestro 747.95 (+0.13%), NVDA 203.0 vs 210.43, MU 942 vs 965,
      SMH 571 vs 585 — pero **AAPL gexa flip 208.0 con spot 333.47 (-37.6%)**, imposible para
      un flip de gamma: scrape roto. Y el campo `regime` viene **null en 15 de los 16** syms,
      justo el campo del que depende la doctrina `gamma-regime-walls`. Nosotros lo calculamos
      para los **30**. Lo unico que gexa aporta y no reproducimos es su score/bias propietario
      y el Market Narrator (prosa), que son SALIDA DE MODELO ajeno, no dato medido.
      -> **DECIDIDO POR LOS HECHOS el mismo dia: gexa.ai DESAPARECIO** ("gexa is gone now, we
      are on our own"). Sustituto commiteado: `scripts/gex_snapshot.py` -> `data/gex_snapshot.json`,
      cobertura medida **25/30** (gexa daba 16) con `regime` para los 25, griegas Polygon MEDIDAS.
      Los 5 omitidos (NVDA QCOM NFLX NOK SKHY) tienen 2-7 strikes poblados: no aparecen, con el
      motivo en `_meta.skipped`. Recableado de los 6 consumidores + cron: delegado.

## REGENERACION DE SEÑALES (agente regen, 2026-07-25)
- [x] "usa los datos de polygon y reproduce, es sencillo... olvidate del websocket de IBKR,
      reproduce local como si estuviera conectado a IBKR" (Yunior 2026-07-25) —
      `scripts/regen_signals.py` + `scripts/regen_shim/`. hecho f11c6fb 09d0a80.
      501 sesiones (2024-07-25 -> 2026-07-24). cusum 501/501 COMPLETO (n=12.780).
- [ ] **CORRIENDO EN BACKGROUND**: `regen_signals.py run --run-id R1 --sources bollinger`
      (log `/tmp/regen_R1_boll.log`). Va por 63/501 sesiones, ~21 s/sesion, ETA ~2,8 h.
      Es REANUDABLE: si se corta, relanzar el MISMO comando y sigue donde iba.
      Al terminar hay que rehacer la cadena:
        ./venv/bin/python scripts/barrier_labels.py --signals-table signals_regen build
        ./venv/bin/python scripts/null_control.py --signals-table signals_regen \
            --null-exclude sym-date run --seed 7
      Estado hoy (bollinger 57/501): n_eff 1388, edge -0.005 [-.025,+.016] UNPROVEN.
- [ ] `cusum` sale **DEAD** con muestra suficiente (n_eff 1513, edge -0.034 CI
      [-.060,-.005] TODO por debajo de cero): la alarma TERREMOTO es PEOR que entrar al
      azar. Decision de Yunior: apagar la voz del CUSUM o dejarla solo como contexto.
      Propuesta en `data/signal_enable.PROPUESTO.signals_regen.json` (el vivo NO se toco).
- [ ] NO regenerable sin cadenas historicas: `whale`, `flow`, `structural` (4 dias de
      cadenas en data/history/). Si se quiere medirlas hay que archivar cadenas a diario
      y esperar ~40-60 sesiones, o backfillear opciones de Polygon (sin OI ni griegas).
