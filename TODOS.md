# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.
> Doctrina: skills `gamma-regime-walls`, `postmarket-cage-release`, `tradingview-terminal`.
# TODOS — ib-trader (sistema autónomo de planes + alarmas)


## 🔴 SESIÓN 2026-07-25 (noche) — peticiones de Yunior, apuntadas AL VUELO
> Plan completo aprobado: `~/.claude/plans/create-plan-to-finish-glimmering-pascal.md`.
> Orden acordado: FASE 0 higiene → 1 señales → 2 flecha → 2.5 TradingAgents → 3 muros
> → 4 UI/UX → 4.5 X earnings → 5 los 9 bugs → 6 deploy → 7 seis ventanas + QA → 8 verif → 9 features minadas.

- [ ] **[pendiente] "make sure u already printed the plan, try to save ink, so no black
  background. review the task for the printer"** (Yunior 2026-07-26). El plan de apertura
  (`data/trees/plan-apertura.html`) y los 5 arboles (`cinco-arboles.html`) tienen FONDO OSCURO:
  imprimirlos gasta un cartucho. Hace falta `@media print` con fondo blanco, tinta negra y
  saltos de pagina por hoja. Revisar tambien el generador de PDFs diarios por si tiene el mismo
  problema.

- [ ] **[pendiente] "make sure tickers search work as expected. test with perpetuals plus
  korean tickers"** (Yunior 2026-07-26). El buscador se arreglo hoy (e94cf04: listener `input`
  + `_prime_bars` sincrono), pero NO se probo con: (a) los perpetuos 24/7 nuevos
  (`data/perp_stocks.json`, 26 simbolos Bybit), (b) los tickers coreanos (Samsung/SK Hynix/
  KOSPI, que van por `korea_bar_bridge`). Probar los dos casos.

- [ ] 🔴 **[pendiente — ORDEN VIEJA QUE SE PERDIO, nunca se anoto] Timeframes de SEGUNDOS en el
  chart, estilo TradingView** (Yunior 2026-07-26: *"why i still dont see timeframes for seconds?
  like 30 seconds, 15, 45, similar to trading view, i gave u an order long time ago about it"*).
  **MEDIDO hoy**: `charts/live.html:346-357` solo tiene 1m..1M; el mas pequeno es **1m**.
  `chart_bridge.LIVE_BAR:101` no tiene ninguna entrada sub-minuto, y `agg()` solo agrega HACIA
  ARRIBA desde 1m — de 1m no se puede bajar a 30s, hace falta pedir barras de segundos o
  construirlas del tick stream (que YA existe: `reqMktData`/`pendingTickersEvent`).
  IBKR sirve nativo `1/5/10/15/30 secs` por `reqHistoricalData` (con poca profundidad
  historica) y `reqRealTimeBars` solo da 5s. **45s NO es nativo**: sale de agregar 15s x3 o 5s x9.
  Fallo de proceso: la orden es vieja y JAMAS entro en TODOS.md.

- [ ] **[pendiente] "print me qqq, nvda, smh, mu, aapl, msft trees and charts with upcoming week
  walls, gex, gamma flip, use the 15 min timeframe... planned strategy with updated data... for
  each graph u should predict at least the first 30 minutes or 15 of opening based on puts and
  calls and future accumulation, we repeat again tomorrow"** (Yunior 2026-07-26). **SE REPITE
  CADA DÍA.** 6 tickers, marco 15m, muros de la semana que viene, GEX, gamma-flip, estrategia
  planeada y predicción de los primeros 15-30 min de la apertura.

- [ ] **[pendiente] SKHY es el ÚNICO de la flota con el gate de spread APAGADO** (medido
  2026-07-26). Los otros 23 `*_signal_bot` llevan `export <SYM>_SPREAD_MAX` en su keepalive
  (0,3 casi todos, DRAM 0,5); `scripts/skhy_keepalive.sh` no define `SKHY_SPREAD_MAX`, y el
  default es `envd(...,0)` = **feature OFF**, así que en SKHY el gate no aplica AUNQUE el
  fail-closed esté puesto. Decidir el umbral (SKHY es ADR coreano, spread naturalmente más
  ancho — 0,5 como DRAM, o medirlo antes de fijarlo). Los otros 6 sin gate (cper kospi
  samsung skhynix slv uso) están FUERA de `fleet.txt`: no urge.

- [ ] **[pendiente] "make sure the walls are ok, no excuses, verify and try in depth… plus explore
      and call polygon and others"** (Yunior 2026-07-25). MEDIDO hoy contra DOS referees
      independientes que coinciden entre sí (CBOE CDN y Polygon sin filtrar): **los muros NO están
      bien**. Dos defectos, los dos del patrón prohibido de `~/CLAUDE.md`:
      **(1) `T = 0.02` inventado** — `gex_snapshot.py:114-116` no escribe `T`, `gex_core.py:188,207,
      409,813` caen al default; `_T_of()` existe (`:496`) pero solo lo llama `from_ibkr_cache`
      (`:688`) y `gex_snapshot.py:134` invoca `build_gex` directo → **el flip se reprecia con 7,3
      días para TODOS los vencimientos, 0DTE incluido**, y de ese flip sale `pin`/`trampilla`, que
      es VETO DURO (`compass.cpp:630-634`, `book_quality.py:317-326`). Hoy 15 trampilla / 10 pin.
      **(2) cadena truncada** — `poly_chain_archive.py:46-47` `BAND=0.045 DTE_MAX=10`: QQQ archiva
      854 contratos vs **12.430** reales; net GEX **−481 M** vs **−6,03 B**; call_wall **700** vs
      **730**; NVDA 56 contratos / 7 strikes → **sin mapa gamma**. Prueba del delito: **14 de 25
      flips caen entre 3,7% y 4,6% del spot con la banda a 4,5%** — es el borde de nuestro recorte,
      no un nivel de mercado.
      → **(1) hecho `cf0baaf`** (T real por contrato). **(2) hecho `5a6a34e`**: banda ADAPTATIVA por
      gamma marginal (suelo 10% / techo 60%, calibración en `data/gamma_band.json`) + vencimientos
      hasta el mensual. **35/35 con flip MEDIDO, el más justo a 12,5 pp del borde**; QQQ −5,22 B
      $/1% (referees −5,3/−6,0). Medido antes de fijar parámetros con las 35 cadenas COMPLETAS de
      CBOE. Ojo a los tres hallazgos que cambian el diagnóstico: la mitad del "13×" era **escala**
      (`net_gex` ×spot vs `net_gex_dollar1pct` ×spot²/100), **Polygon no da griegas de índice**
      (SPX 8.512 contratos, 0 con gamma → CBOE), y la **cuota de 5 req/60s ya no existe** (219
      seguidas sin un 429). Detalle en `AGENTS.md` § *EL ARCHIVO DE CADENAS*.

- [ ] **[pendiente — parcial, revisado 2026-07-26]** "priority now goes to signals… test all
      signals with data, full backtesting, arrow is super important too" (Yunior 2026-07-25).
      Estado por pieza:
      **(1) direction_view.py — CERRADO hoy** (ver casilla ~389): `prob = 50 + |score|*40` ya no
      canta; patrón `compass.cpp` copiado, `prob` Optional solo con bucket calibrado propio.
      **(2) compass.cpp — SIGUE ABIERTO, fuera de mi zona (solo lectura)**: `gather()` no puebla
      `calib_lo`/`calib_n` de ningún fichero, solo los recibe por `--ev-stdin` (modo TEST). En
      vivo `prob_of()` cae SIEMPRE a `"doctrina"` — la brújula tampoco está calibrada en
      producción hoy. Haría falta un harness que corra compass en modo backtest (`--ev-stdin`
      en bucle contra barras históricas) para construir la población del ESTADO `S_REV` (nivel
      impreso + ≥2 familias + sin vetos) y calibrarla — no existe.
      **(3) "test all signals with data" — 6/7 fuentes YA corridas** vía `null_control.py` (ver
      `data/null_control.json`): bollinger UNPROVEN (n=1154, n_eff=89), cusum DATA-INSUFFICIENT
      (n_eff=20, y además apagado en `signal_enable.json` por el regen separado de 501
      sesiones), dip/flow/structural DATA-INSUFFICIENT (n_eff 3-14.5), whale DATA-INSUFFICIENT
      (n_eff=18.7). **0/6 con `fdr_cells_passed>0`.** La 7ª fuente, `source='signal'`
      (2085 filas, la MÁS GRANDE de `trades.db`), es **estructuralmente no-etiquetable**:
      `barrier_labels.py:833` — es un relé heterogéneo sin tesis derivable
      (`eod_backtest.thesis()` no la clasifica), no un olvido.
      **(4) "full backtesting" del propio `backtest_harness.py`** ya está hecho (ver los 4
      CRITICAL más abajo, `85bec77`): 0/93 celdas APTA con coste real.

- [ ] **[pendiente — SALIDA del framework, lo que de verdad calibra la flecha]** lo commiteado es
      la ENTRADA (contexto→LLM). Falta el lazo de medición: veredicto **discreto** + razones (jamás
      un número del LLM), registrado en `signals` con `run_id` como cualquier otra fuente, medido con
      `barrier_labels` + `null_control` + BH-FDR, **banner sin voz** hasta tener `n_eff`. Solo si
      sobrevive entra en la flecha como coeficiente que **DESPLAZA** a otro factor (topes duros
      `FAMILIES_MAX=6`/`VETOES_MAX=8`, `scripts/compass.cpp:565-569`; 14 factores en `direction_view`).
      Patrón a copiar: `source_verdict` de `compass.cpp` — publica un veredicto medido como CONTEXTO
      sin convertirlo en probabilidad. Recordatorio: `data/calibration_barrier.json` mide la señal
      CRUDA (n=1154, pool de bollinger), **no** el setup de la brújula → no vale como prob de la flecha.

- [ ] **[pendiente — deriva del anterior] meter los 8 de earnings en los PDFs diarios y en el veto
      de prima comprada** (no tocado a propósito: el generador de PDFs es de otro agente).
      (a) `daily_fleet_plans.py`: marcar en el plan de AAPL AMZN LRCX META MSFT QCOM SKHY STX la
      fecha+sesión de earnings (fuente `data/finviz_earn_nextweek_152.csv`, ya la deja
      `x_earnings_post.py`); (b) **veto duro**: prima comprada que cruce el print del propio ticker
      = prohibida (doctrina "en día de earnings del ticker jamás aguantar el print con premium
      comprado"); (c) todos AMC ⇒ el veto muerde en el **cierre** del día del print, no en la
      apertura; (d) la fecha se re-verifica el mismo día: Finviz mueve fechas.

- [ ] 🥇 **[pendiente — RELOJ DE 7 DÍAS] Unusual Whales** (Yunior 2026-07-25: "save, lets see how
      to use that one"). Token en `feeds.env` `UW_TOKEN`, **trial caduca ~2026-08-01**.
      MEDIDO hoy, los 6 endpoints responden 200 y traen **justo lo que la skill
      `anti-overfit-killlist` daba por IMPOSIBLE** ("necesitan tape firmado + dark-pool
      licenciado que NO tenemos"):
      · `/api/market/market-tide` → `net_call_premium`, `net_put_premium`, **`net_volume` FIRMADO**
        en cubos de 5 min (81 filas/día). Es EXACTAMENTE el panel "Net Call/Put Premium" de la
        captura de Bullflow, y el que habría hecho sonar **el tide de −53 M del 7/21** que el P/C
        de volumen (0,86) se comió.
      · `/api/stock/<SYM>/greek-exposure` → **250 filas = 1 AÑO** de call/put gamma·delta·charm·vanna
        diarios. Rompe el cuello de botella del roadmap: teníamos "whale/flow/structural NO
        regenerables, esperar 40-60 sesiones" y esto es historia YA.
      · `/api/stock/<SYM>/spot-exposures` → gamma/vanna/charm por 1% de movimiento **intradía**
        (491 filas) con precio: el equivalente a HIRO. *(Ojo: los campos `_dir` y `_vol` vinieron a
        0 en la muestra; solo `_oi` poblado — verificar si es de tier superior o solo en RTH.)*
      · `/api/market/oi-change` (100) · `/api/stock/<SYM>/flow-alerts` (100, los sweeps de la
        captura) · `/api/darkpool/<SYM>` (500).
      **REGLA DURA antes de cablear nada**: es de PAGO y con reloj. Una fuente que se apaga en 7
      días NO puede ser dependencia de una señal — es la lección de gexa.ai, que murió y se llevó
      8 consumidores. *Acción correcta en los 7 días*: **ARCHIVAR** todo lo histórico que da
      (1 año de greek-exposure × 30 símbolos, market-tide, darkpool) para quedarnos el DATO
      aunque no se renueve, y **medirlo** contra nuestro `gex_snapshot` antes de pagar.
      MCP disponible en `https://api.unusualwhales.com/api/mcp`.

- [ ] **[pendiente] CONECTAR Unusual Whales esta semana** (Yunior 2026-07-26: "esta semana podemos
      conectar unusual whales, si es bueno extendemos trial"). Plan: **archivar primero, medir
      después, cablear al final** — nunca al revés, por la lección gexa.
      Endpoints medidos que dan mapa de DELTA, que NOSOTROS NO TENEMOS:
      `/api/stock/<SYM>/greek-exposure/strike` → **530 filas POR STRIKE** con `call_delta`,
      `put_delta`, `call_gex`, `put_gex`, `call_charm`, `put_charm`, `call_vanna`, `put_vanna`.
      `/api/stock/<SYM>/greek-exposure` → **250 días (1 año)** de agregados diarios; net DEX de
      QQQ el 24-jul = **−51,0 M**. `/api/stock/<SYM>/greeks` → 237 filas por contrato.
      `/api/stock/<SYM>/option-chains` → 12.904 contratos.
      *Por qué importa*: `scripts/gex_core.py` tiene **CERO delta** (ni `bs_delta`, ni DEX). El DEX
      está diseñado dos veces y nunca construido (`designs-menthorq.md:219` #9 close-drift,
      `designs-spotgamma.md:182` expiry-unwind: *"DEX… currently missing from our stack"*), y son
      dos de las 8 minadas sin fichero. **Trampa de signo ya documentada**
      (`designs-menthorq.md:224`): DEX positivo = cliente alcista **pero** el creador VENDE
      subyacente para quedar neutral → dos campos, `dex_sentiment` y `dex_flow_impact`, jamás uno.

- [ ] **[pendiente] Minar 4 vendedores más** como se hizo con TrendSpider/MenthorQ/SpotGamma
      (Yunior 2026-07-25): tradytics.com/options-market · app.tradingflow.com/app/option-trades/live
      · optioncharts.io/trending/most-active-stock-options · quantedoptions.com.
      **TradingFlow — MEDIDO 2026-07-26: NO TIENE API.** Un solo plan, **$59/mes** (o $504/año);
      la página de precios no menciona API, acceso programático ni descarga CSV/JSON, y el
      **roadmap tampoco** (sus planes son Option Chain, watchlist, filtros, Surge Attribution,
      resúmenes con IA). Es UI-only → para nosotros solo sirve como **fuente de IDEAS a minar**,
      no como feed. Tiene página propia de `/learn/delta-exposure-dex/`, que confirma que el DEX
      es estándar en el sector y un hueco nuestro. La extensión de Chrome no estaba conectada, así
      que esto se midió por HTTP, no navegando: **queda pendiente mirar la UI en vivo** para minar
      las features como se hizo con TrendSpider.
      Destino: `docs/research/designs-<vendor>.md` con features rankeadas y las RECHAZADAS
      razonadas, mismo formato que `designs-trendspider.md`.
      **Marco doctrinal que Yunior fija**: *"los market makers son los elefantes en la habitación"*
      + resumen del vídeo de Brent Kochuba (SpotGamma). Lo aprovechable y que NO tenemos:
      **HIRO** (línea en vivo de si el MM debe comprar o vender), **Trace Map** (mapa de calor que
      PRONOSTICA la respuesta de cobertura: azul/morado = soporte con compradores debajo, rojo =
      zona de alta volatilidad donde el precio se persigue), **strikes en percentil 99 como
      objetivos de liquidez** ("quieren que el precio vaya a las zonas de liquidez", y el flujo se
      APAGA al llegar), **Captain Condor** (posición 0DTE recurrente que fabrica soporte/resistencia),
      y el **mapa de charm** de la tarde. El Vol Trigger ya lo tenemos (`vol_trigger.py`).

- [ ] **[pendiente] organizar el proyecto, ahora mismo hay muchos archivos regados como tsm_signal_bot.cpp, y otros en el mismo nivel, muchos. separate logs to logs folder.

- [ ] **[pendiente — CIERRE DE SESION, "cuando todo listo"] "dejas las 6 windows listas y
      actualizadas para macos, kill chorme pid y restart as well. increase zoom for tiny 6 windows.
      make sure we can see timeframe selector in those 6 windows, right now we cannot"**
      (Yunior 2026-07-27 08:35). Cuatro cosas, y OJO que dos se PELEAN entre si:
      (a) las 6 ventanas reconstruidas con el ultimo commit y datos frescos;
      (b) matar el PID de Chrome y relanzarlo (de paso puede arreglar que la extension de Claude
          NO conecta — TODOS.md ya decia que hace falta reiniciar Chrome);
      (c) **subir el zoom** de las 6 ventanas (son 1/6 de pantalla y se leen pequenas);
      (d) **el selector de TIMEFRAME no se ve** en esas 6 ventanas.
      ⚠️ (c) EMPEORA (d): a 1/6 de pantalla la barra ya desborda —en la captura de las 08:24 solo
      caben "⚠ CADENA Polygon 15min · 📋 QQQ ▾ · ● LIVE · 📈 Opciones" y el selector queda FUERA—
      asi que mas zoom recorta mas. La barra tiene que ser RESPONSIVE (envolver o colapsar lo
      accesorio) antes de tocar el zoom, o el selector seguira invisible.
      Relacionado: la casilla vieja "Selector de timeframe compacto estilo TradingView" y los
      timeframes de SEGUNDOS (5s/15s/30s/45s, commit 132dd28) — si no se ve el selector, esos
      timeframes nuevos son inalcanzables con el raton.

- [ ] **[pendiente] "put refresh button in macos app, also version number of software in top of
      window, right to symbol"** (Yunior 2026-07-27 08:28). El titulo de ventana hoy es
      "QQQ · :8080" (`macapp/main.swift`); el sello del commit ya esta en `Info.plist`
      (`IBTCommit`, hoy 3491c73) pero **no se VE**. Dos cosas: (a) boton de refresco visible
      —hoy solo hay ⌘R, que no se descubre—, (b) version a la derecha del simbolo, arriba.

- [ ] **[pendiente] make the arrow compass nicer, with glowing liquid colors, fast movements, nice to see, test the calibration now with the realtime VIX.
## 🌙 QQQ DÍA Y NOCHE (Yunior 2026-07-27: "we should be able to monitor and see charts for qqq
## day and night") — MEDIDO, y el hallazgo es que la noche NO se puede recuperar
- [x] **Día y premarket: FUNCIONA hoy.** Verificado lun 08:09 con la flota viva: bridge QQQ
      (:8080) sirve **1.920 barras**, spot **694,16** en vivo, CW 700 / PW 680 / flip 696,22,
      137 strikes, `walls_unavailable: null`. `useRTH=False` en las 3 rutas de `chart_bridge.py`
      (`:1596`, `:1644`, `:2603`) → premarket y after-hours entran. Barras de HOY: 60/hora
      continuas de 01:00 a 08:09.
- [ ] 🔴 **[pendiente — DATO IRRECUPERABLE, lo decide Yunior] La cinta nocturna solo existe si la
      capturamos EN VIVO.** MEDIDO pidiendo a IBKR 2 días de QQQ 1m con `useRTH=False`:
      **IBKR sirve solo Fri 04:00-19:00 y Mon 04:00-08:00. Sábado y domingo: CERO. La franja
      20:00-04:00 NO la devuelve por histórico.** En cambio nuestro
      `data/bars_qqq_ibkr.txt` **sí** tiene lun 00:00-03:00 — esas barras existen ÚNICAMENTE porque
      el stream vivo las guardó. Traducción: **cada hora de noche con el puente caído se pierde
      para siempre**, no hay backfill que la recupere.
      *Y ya se perdió una*: la ventana de flota abre **dom 20:00** pero el primer arranque
      registrado en `fleet_autostart.log` es **lun 00:02:08** (`ibkr_bar_bridge` a las 00:48).
      El log salta de "fuera de ventana" a las **dom 19:57:39** directamente a las 00:02 — casi
      **4 h con la ventana ABIERTA y la flota sin arrancar**. `com.ibtrader.fleet` es
      `StartInterval 300` + `RunAtLoad` y marca `runs=142 / last exit code=0`, así que el job no
      falló: simplemente no corrió en esa franja (hubo sueño del Mac ~19:57-20:22 —
      `MAGICWAKE creat=26/7/26 20:22`— pero eso NO explica 20:22→00:02, y no lo voy a suponer).
      *Lo que hace falta*: (a) que la flota esté viva EN EL MINUTO en que abre la ventana el
      domingo (wake programado con `pmset repeat` a las 19:55, o `caffeinate` en la franja), y
      (b) un guardián que GRITE si la ventana está abierta y el bar bridge no escribe — el mismo
      patrón de frescura que se acaba de poner en `korea_bar_bridge.freshness_guard` (`:210-224`).
      **NO lo he tocado a 74 min de la apertura**: `fleet_keepalive_start.sh` es de quien depende
      la flota entera y romperlo en premarket cuesta la sesión. Es un cambio de después del cierre.
- [ ] **[nota] `trades.db` en `mode=ro` falla de forma TRANSITORIA con la flota escribiendo.**
      Medido hoy: `sqlite3 "file:trades.db?mode=ro"` dio `unable to open database file (14)` y
      5 minutos después el MISMO comando devolvió 5.457 filas. Tumbó `tree_sheets.py:82`
      (`touch_stats`) con la traza entera. `touch_stats` ya tiene degradación (`return None` si
      no existe el fichero) pero **no captura el fallo de apertura**, así que un lock momentáneo
      mata la generación del árbol completa. Envolver el `connect`/`execute` y devolver `None`
      (que es la degradación ya diseñada), nunca un cero.

## ✅ VERIFICADO EN SESIÓN VIVA (lun 2026-07-27, mercado ABIERTO)
- [x] **[CERRADA — el fix de los CAPITANES funciona] Verificar EN VIVO que los DOS CAPITANES
      reciben cinta firmada.** Llevaba semanas sin poder cerrarse porque solo se puede observar con
      el mercado abierto. MEDIDO hoy 09:09: `data/whale_qqq.txt` **59.061 B**, `whale_spy.txt`
      **43.868 B**, `whale_smh.txt` **15.584 B**, los tres con mtime del minuto en curso. El sábado
      estaban a **0 bytes**. `CAPTAINS_FIRST` (`ibkr_bar_bridge.py:62`) hace su trabajo: los
      capitanes se suscriben PRIMERO y por eso son los que tienen cinta. La **regla 12** ya no se
      alimenta de un input vacío.
- [ ] 🔴 **[pendiente — HALLAZGO NUEVO de la misma medición] 7 de los 30 de la flota NO tienen
      cinta de ballenas, y es el CAP de IBKR, no un bug nuestro.** Vacíos a las 09:09 con el
      mercado abierto: **AAPL AMD ASML GLD INTC TSM TXN** — los 7 son de `data/fleet.txt`
      (comprobado bien: `fleet.txt` es UNA línea de 30 palabras separadas por espacios; leerlo por
      líneas da un solo token y hace creer que no están en la flota).
      Causa MEDIDA: `bridge_ibkr_fleet.log` tiene **1.103** `Error 10190 "Le nombre maximum de
      demandes tick-by-tick a été atteint"`; los denegados que se ven al final son SPCX SKHY LRCX
      SNDK WDC STX — el orden de suscripción decide quién se queda sin cinta, y `CAPTAINS_FIRST`
      solo garantiza los 3 primeros.
      *Por qué importa*: la escalera de agresor, el HIRO casero y `opt_whale_watch` se alimentan de
      esa cinta. Un ticker sin cinta no es "sin ballenas": es CIEGO, y hoy no lo dice nadie.
      *Qué hace falta decidir*: (a) cuántas líneas tick-by-tick da realmente la cuenta (el probe
      `docs/probes/hiro_probe_ibkr.py` existe para eso y hoy SÍ se puede correr), (b) a qué 8-10
      símbolos se les asigna la cinta a propósito en vez de por orden de arranque, y (c) que un
      símbolo sin cinta salga DECLARADO como ciego en lugar de aparentar silencio de flujo.
