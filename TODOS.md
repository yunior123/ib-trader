# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.
> Doctrina: skills `gamma-regime-walls`, `postmarket-cage-release`, `tradingview-terminal`.
> (`gexa-terminal` JUBILADA el 2026-07-25 — gexa.ai desapareció.)

> **AUDITADO EL 2026-07-25.** Las 73 casillas `- [ ]` que había se revisaron **una a una contra
> el código y contra `git log`**, no de memoria. El recuento y las 5 vivas más importantes están
> **al final del fichero**. Estado por casilla: `pendiente` / `hecho <commit>` / `obsoleto: <motivo>`.
> Cada afirmación va marcada **MEDIDO** (comprobado hoy con una orden) o **SOSPECHADO**.

## 🔴 SESIÓN 2026-07-25 (noche) — peticiones de Yunior, apuntadas AL VUELO
> Plan completo aprobado: `~/.claude/plans/create-plan-to-finish-glimmering-pascal.md`.
> Orden acordado: FASE 0 higiene → 1 señales → 2 flecha → 2.5 TradingAgents → 3 muros
> → 4 UI/UX → 4.5 X earnings → 5 los 9 bugs → 6 deploy → 7 seis ventanas + QA → 8 verif → 9 features minadas.

- [x] **"new finviz api till next saturday"** → token nuevo `0c56…8625` puesto en **feeds.env
      `FINVIZ_AUTH3`** (no solo en `llm.env`): MEDIDO que los 4 consumidores prueban `AUTH3`
      ANTES que `AUTH` (`finviz_scout.cpp:91`, `x_whale_bot.cpp:366`, `options_hunter.py:34`,
      y `finviz_valuation.py` **solo** lee AUTH3) → cambiar solo `FINVIZ_AUTH` no lo usaba nadie.
      El anterior seguía dando 200 al sustituirlo; queda comentado. Caduca ~2026-08-01.
- [ ] **[pendiente]** `scripts/finviz_auth_check.py`: GRITAR cuando el token caduque.
      *Por qué importa*: hoy caduca **en silencio** y el scout/valuation/whale-bot se quedan mudos
      sin que nadie se entere. Yunior lo renueva semanalmente.
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
- [ ] **[pendiente] "run ib-gateway simulation engine… show 6 ib-trader window like before, working
      with different tickers, while the graph is moving, while we also see the walls. full qa
      testing on those windows, test everysingle feature in there"** (Yunior 2026-07-25).
      Va DESPUÉS de arreglar los muros: `replay.cpp:314-364` copia/sintetiza los `levels_<sym>.json`,
      así que con muros truncados las 6 ventanas enseñarían la misma basura.
- [ ] **[pendiente] "priority now goes to signals… test all signals with data, full backtesting,
      arrow is super important too"** (Yunior 2026-07-25). Hallazgo nuevo: **la flecha NUNCA está
      calibrada en producción** — `compass.cpp:751-770` da `prob_source="medido"` solo con
      `calib_lo`/`calib_n`, y esos campos **solo se pueblan por `--ev-stdin`** (`:1034`);
      `gather()` no los lee de ningún fichero. Se suma a `direction_view.py:284-285`
      (`prob = 50 + |score|*40`).
- [ ] **[pendiente] "calibramos la flecha con trading agents framework… pásale todo el arsenal,
      y que tenga acceso a finviz technicals"** (Yunior 2026-07-25). MEDIDO: (a)
      `TradingAgents/tradingagents/default_config.py:72` = **`"llm_provider": "nvidia"` = NIM,
      PROHIBIDO** por la orden del 2026-07-16; (b) el puente está roto — `llm.env` define `TA_*`
      pero **solo lo lee `scripts/narrator.py:23,37`**; el framework lee `TRADINGAGENTS_*`
      (`default_config.py:13-16`) → **la config DeepSeek de ib-trader no gobierna el framework**;
      (c) `dataflows/finviz.py:46` usa `v=111` (Overview) → **cero indicadores técnicos**.
      *Objeción escrita*: un LLM NO produce probabilidad calibrada — propone, y la medición dispone
      (barrera+null+BH-FDR, banner sin voz hasta tener n_eff, y entra con el tope duro desplazando
      a otro factor).
- [ ] **[pendiente] "create script to post x.com post of companies with earnings next week,
      include technicals… use finviz… show people nice picaros data"** (Yunior 2026-07-25).
      VERIFICADO hoy con el token nuevo: `f=earningsdate_nextweek` → **753 tickers**; `v=171` da
      Beta/ATR/SMA20-50-200/52W/RSI(14)/Gap; `v=152&c=…` trae **`Earnings Date` con hora**
      (8:30 AM = BMO, 4:30 PM = AMC).
      🔴 **Hallazgo que vale más que el tweet**: **8 de los 30 de la flota reportan la semana que
      viene — AAPL AMZN LRCX META MSFT QCOM SKHY STX**. La regla 4 prohíbe aguantar prima comprada
      a través de un print → esto va a los PDFs y a los vetos, no solo a X.
- [ ] **[pendiente] "terminar todo de trendspider, menthorq… make it nice, surprise me"**
      (Yunior 2026-07-25). MEDIDO: de las 30 minadas, **8 siguen sin fichero** (#19 cube-widening,
      #21 wall-decay, #22 chain-delta, #24 close-drift, #25 expiry-unwind, #26 gap-islands,
      #29 peer-weights, #30 finviz-snap). *La sorpresa elegida*: **#21 wall-decay ledger** — medir
      la constante de la casa ("1er toque rebota ~70%, 3+ exhausto") que **nunca se ha medido** y
      que sin embargo veta de verdad en `compass.cpp:635-638` (`TOUCH_EXHAUST = 3`).
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
- [ ] 🔴 **[pendiente] BB multi-TF: el código CONTRADICE la doctrina escrita** (respuesta a
      "with BB, are we making sure it breaks in 1 min and 15 min? to avoid noise?", Yunior 2026-07-25).
      **NO se exige 1m Y 15m.** `qqq_signal_bot.cpp:458-459` cuenta **2 de 3**:
      `bb_dn_tfs = (v5_bb1_dn_ago<=3) + (v5_bb5_dn_ago<=2) + (v5_bb15_dn_ago<=1)` y dispara con
      `>=2` (`:466`, `:1250`). Es decir **1m+5m basta y el 15m puede no romper nunca**.
      Y el 5m **no es independiente**: `V5TF` (`:337`) es "agregador 5m/15m desde bars de 1m" — un
      único tramo brusco de 3 minutos rompe los dos. La confluencia multi-TF es, en la práctica,
      un timeframe rápido contado dos veces. Justo el ruido que Yunior sospecha.
      **MEDIDO** sobre las 501 sesiones regeneradas (`signals_regen`): **148 señales `BB-2TF` vs
      4 `BB-3TF`** → el 15m participa en el **2,6%** de los casos.
      La memoria `bollinger-always-check` dice "revisar BB 1m+15m en CADA señal"; el código dice
      otra cosa. *Y encaja con que `bollinger` saliera UNPROVEN* (0,482 vs 0,496 aleatorio).
      *Acción*: NO cambiarlo a mano — es una hipótesis que se MIDE (barrier_labels + null_control):
      ¿exigir el 15m mejora el edge, o solo recorta la muestra? Si mejora, la regla pasa a
      `1m AND 15m`; si no, se dice y se deja.
- [ ] **[pendiente] "technicals de la company en tiempo real desde finviz en un widget nuevo;
      solo el gráfico principal por defecto, los demás widgets bajo demanda; yfinance de fallback
      si finviz se cae"** (Yunior 2026-07-25). Va con la FASE 4 de UI/UX.

## 🔴 SESIÓN 2026-07-25 (madrugada) — peticiones de Yunior, apuntadas AL VUELO
> Regla (`~/CLAUDE.md`): cada petición se anota aquí EN EL MOMENTO, con las palabras de
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
- [x] **"el app ib-trader Cockpit should have a nice icon"** (Yunior 2026-07-25) — `hecho 5c2b0c3`.
      MEDIDO: `macapp/icon/AppIcon.icns` con los 10 tamaños (16→512@2x) generados por
      `macapp/icon/make_icon.py` vía `iconutil`; `CFBundleIconFile` en `macapp/build.sh:35` y en
      el bundle vivo; `build.sh:53-57` lo empotra en cada build y GRITA 🔴 si falta.

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
- [ ] **[pendiente] Verificar EN VIVO que los DOS CAPITANES ya reciben cinta firmada.**
      *Qué es*: el fix de prioridad ya está en el código — `scripts/ibkr_bar_bridge.py:62`
      `CAPTAINS_FIRST = ["QQQ","SPY","SMH"]` + `captains_first(syms)` en `:65-71` (`hecho c6e1513`).
      Lo que NO está verificado es el efecto: MEDIDO hoy, `data/whale_qqq.txt` y `whale_spy.txt`
      siguen a **0 bytes** y **9 de los 14** ficheros están vacíos (aapl amd asml gld intc qqq spy
      tsm txn); los 5 con datos son del **24-jul**, nada escrito hoy. Es coherente con la flota
      parada un sábado, así que el fix no está refutado — está **sin observar**.
      *Por qué importa*: la **regla 12 entera** (los capitanes SPY/QQQ/SMH prevalecen sobre la
      tropa) se alimenta de esa cinta. Si tras una sesión viva siguen a 0 bytes, la jerarquía de
      capitanes lleva semanas decidiendo con un input vacío.
      *Cuándo*: primera sesión viva (dom 20:00 / lun premarket). Un `ls -la data/whale_*.txt` basta.
- [ ] **[pendiente]** Correr `docs/probes/hiro_probe_ibkr.py` en la próxima sesión viva (dom 20:00 /
      lun premarket): mide el cap REAL de tick-by-tick y si OPRA por contrato está permitido.
      *Por qué importa*: sin ese número el resto de HIRO es especulación, y ya sabemos que el cap
      (err 10190) es lo que dejó a los capitanes sin cinta. `a2cd4d8`

**DELEGADO a agentes — CERRADO (verificado 2026-07-25):**
- [x] "make the walls look like in there … those look like nice gamma walls" (captura de
      @BullflowIO, `GEX: Bubbles`) → burbujas GEX en `charts/live.html`, coloreando **pin vs
      trampilla** (que Bullflow no muestra). MEDIDO: `charts/live.html:610` `bubbleRows()`,
      `:629` `class BubbleView`, `:677-686` `class WallBubbles`, toggle `#bubblebar` en `:291`
      con tooltip PIN vs TRAMPILLA y persistencia en `localStorage`.
- [x] "engine ibkr reemplazo local … con polygon, datos reales" → `scripts/replay.cpp` (simula el
      DISCO, no el socket) + cadenas del archivo. El gateway socket se **canceló** por decisión de
      Yunior ("si no hace falta websocket fake y es listo, mejor"). `e7438e3` `b1ee715`
- [x] Backfill Polygon 2 años + archivador diario de cadenas con griegas REALES.
      MEDIDO hoy: `poly_bars` = **8.950.177 filas, 30 símbolos, 2024-07-25 → 2026-07-24**
      (eran 21 días). Archivador con cron: `70c0e2c` + `~/Library/LaunchAgents/com.ibtrader.polychains.plist`
      (16:20 y 08:45); **30 cadenas** `data/history/2026-07-25/chain_full_*.json` MEDIDAS hoy.
- [x] Las **30 features minadas** de SpotGamma/TrendSpider/MenthorQ + **13 skills** +
      `docs/FEATURES-MINED-2026-07-25.md` + `docs/research/` (10 dossiers). `7dadf7a`
      `100d3a1` `145766c` `4f9d64d` `71b14cb` `ec6815e` `86d0c4c`
- [ ] **[pendiente] "do we have spx in fleet? … make sure we use it to measure brújula"**
      (Yunior 2026-07-25). *Estado MEDIDO*: SPX **no está** en `data/fleet.txt`, y por Polygon no
      hay carril — `/v3/snapshot/indices?ticker=I:SPX` da **403 NOT_AUTHORIZED**
      (`docs/HIRO-2026-07-25.md:33`). La única vía es la suscripción IBKR **CBOE Global Indexes**,
      **la misma que falta para el VIX** (ver más abajo) → los dos se desbloquean con un solo pago.
      *Por qué importa*: la brújula mide el índice con QQQ/SPY (ETFs). SPX es el subyacente donde
      vive el grueso del OI de índice; sin él, el mapa gamma del índice se lee por su proxy.
      *Riesgo declarado*: **un símbolo muerto encoge denominadores** — no añadirlo hasta que el
      entitlement esté confirmado en vivo.

**OLA 1 — CERRADA (2026-07-25). 15 items en 4 agentes:**
- [x] #1 `barrier-labels` **hecho 1a97611** + #2 `null-control` **hecho c1e3336**. Los dos únicos
      cuya salida es RESTAR. `scripts/barrier_labels.py`, `scripts/null_control.py`,
      `docs/EDGE-SCOREBOARD-2026-07-25.md`, `docs/NULL-CONTROL-2026-07-25.md`.
      Medido: 13-27% de las señales que se cuentan GANADAS habrían sido STOPEADAS antes; el
      re-etiquetado NO es una resta uniforme (bollinger +6.5pp, cusum -28.6pp) porque la barrera
      SÍ ve el TP intra-camino. ρ̄ de la flota = **0.41** → bollinger `n=1154` queda en
      `n_eff=89` (CI estrechados ×3.6) y sale **UNPROVEN**: no bate a entradas ALEATORIAS
      emparejadas (0.482 vs 0.496). **0 de 131 celdas fuente×sym×bucket pasan BH-FDR q=0.10.**
      Propuesta en `data/signal_enable.PROPUESTO.json` — `signal_enable.json` NO tocado.
- [x] #3 `book-quality` + #5 `chain-honesty` + #6 `flip-honesty`+congelar 09:35 + #13 roll-off
      → `hecho 56ed1fe b066f81 1cacc8f`. Detalle en la sección "OLA 1 features minadas".
- [x] #9 `truth-lock` + #10 `em-envelope` + #12 `voice-budget` + #14 `pin-clock` +
      #15 `equity-prints` + #16 `chain-cube` + #18 `levels-5min` → `hecho ea26bc5 176caea daf90de
      d21f2eb b0c1b8a 6bae616 c91c375`. 7 commits, 101 tests.
- [x] #4 `poly-aggs-backfill` (2 años × 30 syms; eran 21 días) — **hecho**. MEDIDO: 8.950.177
      filas de `poly_bars`, 30 símbolos, 2 años exactos.
- [x] #11 `features-fanout` + **tope duro de 14 factores** — `hecho 785b29e` ("TOPE DURO de
      familias y vetos en la brujula"). Sin esto, 30 features = una flecha cuya varianza de prob
      colapsa a ~58% constante.
- [ ] 🥇 **[pendiente] CABLEAR lo que ya se mide: nadie consume la calibración de barrera.**
      *Qué es*: (a) `data/calibration_barrier.json` (123 KB, de hoy) y `data/null_control.json`
      (5,6 KB, de hoy) existen y están llenos, pero **`scripts/direction_view.py` no los lee**.
      MEDIDO: `grep -n "barrier\|null_control\|calibration" scripts/direction_view.py` = **0 hits**
      en 329 líneas. La prob que canta sale de una fórmula fija, `direction_view.py:284-285`:
      `prob = int(round(50 + abs(score)*40))` acotado a [50,90].
      *Por qué importa*: **es el hueco más caro del repo hoy.** Se pagó una ola entera de trabajo
      para medir que 0 de 131 celdas baten al azar, y la flota sigue cantando una probabilidad
      INVENTADA por una fórmula lineal. Cada `prob NN%` que ve Yunior hoy es un número decorativo.
      Cerrar esto es lo que convierte la medición en dinero.
      *Ficheros*: `scripts/direction_view.py` (consumidor), + el PDF y `compass` como consumidores 2 y 3.
      *(b)* `poly_bars` acaba el **2026-07-24 19:59 ET**: 197 señales del 07-25 quedaron sin
      etiquetar (`skip_entry_stale`). *(c)* el null de **16 niveles aleatorios** (parte B de la
      ficha #2) ya NO está bloqueado: `level_react` existe (`53b3f3c`). *(d)* la ruta sub-minuto no
      existe → `ambig_pct` 2.1% es irreducible con `poly_bars`.

**PENDIENTE (no delegado aún):**
- [ ] **[pendiente — LO DECIDE YUNIOR]** Conmutar los keepalives a los binarios C++ nuevos
      (`fleet_consensus`, `gate`). *Estado MEDIDO*: los dos C++ existen y compilan
      (`scripts/fleet_consensus.cpp` 30 KB, `scripts/gate.cpp` 19 KB + `gate_core.hpp`, `e7438e3`),
      pero **el keepalive NO los lanza**: `scripts/fleet_keepalive_start.sh:39` solo hace
      `pkill -x fleet_consensus`; en producción corre `scripts/fleet_consensus.py --daemon`.
      `gate` SÍ está cableado por otra vía: `scripts/optgate.py:62` ejecuta `./gate --json`.
      **Modo SOMBRA: NO existe hoy** — 0 hits de `shadow`/`SOMBRA` en los tres ficheros.
      *Recomendación*: sombra primero (el C++ escribe a fichero aparte y NO habla, se compara una
      sesión contra el Python, y solo entonces se conmuta la voz). Hoy hay que **construir** ese
      modo; no se puede activar tal cual.
- [ ] **[pendiente] Orden de Yunior 2026-07-25**: "después de ola uno testea todo, then todas las
      olas. Testea con Claude in Chrome as needed." → OLA 1 cerrada y suite verde; falta la
      verificación **en Chrome** del chart (burbujas GEX, flecha escalando, tooltip). Olas 2 y 3:
      viabilidad ya medida en `0a9be1f` (5 construibles, 7 bloqueadas).

## 🆕 MINADO DE TRADINGFLOW (2026-07-26) — dossier `docs/research/designs-tradingflow.md`
> Yunior: *"i really like this one too… take a look in chrome, it offers a lot of data, do they
> have api?"*. **Respuesta medida: NO tienen API** (`/api/*`, `/openapi.json`, `/docs` → 404 o
> shell del SPA; backend tras Clerk; un plan de **$59/mes**; el roadmap tampoco la menciona).
> → Es **fuente de IDEAS, no de DATOS**: jamás puede ser dependencia de una señal.
> ⚠️ La UI en vivo **NO se ha visto** (la extensión de Chrome no conecta) — todo esto sale de sus
> docs públicos `/learn/*`. **Falta la pasada visual** para minar la pantalla como se hizo con
> TrendSpider, y para capturar datos suyos con los que verificar los nuestros.

- [ ] 🥇 **[nice-to-have, ALTO VALOR] DEX de ESTRUCTURA** (`Δ · OI · 100 · S`) en `gex_core`.
      *Qué es*: el mapa de delta. Hoy `gex_core.py` tiene **CERO delta** — ni `bs_delta` ni DEX.
      *Por qué importa*: desbloquea las dos minadas nunca construidas, `close-drift` (#24) y
      `expiry-unwind` (#25). El dato YA existe: cadenas archivadas + UW `/greek-exposure/strike`
      (530 filas por strike con `call_delta`/`put_delta`).
      *Trampa obligatoria*: DEX positivo = cliente alcista **pero** el creador VENDE subyacente
      para quedar neutral → **dos campos, `dex_sentiment` y `dex_flow_impact`, jamás uno**.
      TradingFlow **no menciona esta trampa**, lo cual es en sí un aviso sobre su lectura.
- [ ] 🥈 **[nice-to-have] La distinción DEX-de-FLUJO vs DEX-de-ESTRUCTURA**, que no tenemos ni
      nombrada. Suyo, textual: *"DEX describe la DIRECCIÓN DEL FLUJO en la cinta (intradía);
      GEX representa la ESTRUCTURA del mercado"*. Su fórmula de flujo es `delta × size` **por
      operación** (tamaño de la operación, no OI) → requiere cinta de opciones firmada, que es
      justo lo que da UW `/market-tide`.
- [ ] 🥉 **[nice-to-have] DEI — normalizar el impacto por la liquidez del nombre**.
      *Suyo*: *"DEX escalado por el volumen típico de la acción: ¿es esta exposición GRANDE para
      este nombre?"*. *Por qué importa*: hoy nuestros umbrales de ballena son ABSOLUTOS, y por eso
      NOK (precio 8,99) y MU (910) no se pueden rankear juntos. `impact_pctile` ya existe como
      campo en `book_quality.json` y está **`null` en 30/30**.
- [ ] **[nice-to-have] Escalera de agresor de 5 peldaños** (Above Ask / At Ask / **Mid** / At Bid /
      Below Bid) en `opt_whale_watch`. *Por qué importa*: hoy clasificamos con un solo ratio
      (`pc = vp/max(vc,1)`, `:157`) que fuerza cada operación a un bando; **"Mid" debería ser su
      propia categoría, no repartirse**. El motor ya existe: `ibkr_bar_bridge.py:250` corre
      `reqTickByTickData(..., "AllLast", ...)` con firmado Lee-Ready → es el HIRO casero de
      `docs/HIRO-2026-07-25.md`.
- [ ] **[nice-to-have, BARATO] ΔOI = detector de APERTURA vs CIERRE.** Regla suya:
      `volumen ≈ +ΔOI` → posición NUEVA; `volumen ≈ −ΔOI` → **salida**; `volumen >> ΔOI` → churn.
      *Por qué importa*: confirma al día siguiente si la ballena de ayer ABRÍA o CERRABA — y eso es
      el punto de Kochuba (*un movimiento brusco suele ser un cambio de posición, no una noticia*).
      Ya archivamos cadenas a diario desde el 2026-07-25, así que el coste es casi cero.
      ⚠️ **Y corrige una lectura equivocada nuestra**: *"el OI NO es en tiempo real; durante la
      sesión el OI que ves es el cierre de AYER"*.
- [ ] **[nice-to-have] "Inusual" como CONJUNCIÓN, no como umbral suelto**: premium grande + Vol/OI
      alto + lado agresivo + sentimiento claro (no mid) + strike OTM, **todos a la vez**. Más su
      lectura de tamaño: pocas operaciones grandes = convicción institucional; muchas diminutas =
      retail o creador, menos señal. *Por qué importa*: una conjunción es mucho más difícil de
      sobreajustar que un umbral único, y el umbral único es justo por lo que **el tide de −53 M
      del 7/21 no sonó**.
- [ ] **[pendiente] Pasada VISUAL a TradingFlow con la cuenta de Yunior** (Chrome): minar la
      pantalla (no solo los docs) y **capturar datos suyos para verificar los nuestros** —
      su GEX/muros/flip contra `data/gex_snapshot.json`, igual que se hizo con CBOE y Polygon.
      *Bloqueado por*: la extensión de Claude no conecta con Chrome (instalada en 4 perfiles,
      Chrome vivo) → **hace falta reiniciar Chrome**.

> **Lo que NO hay que copiarles** (razonado en el dossier): sus Call/Put Wall son **solo por OI**
> ("el strike con más OI de calls por encima del precio") — el nuestro es por **|gamma|·OI** y
> además publica los de OI puro aparte. Y su GEX/flip **no disclosan fórmula**
> (*"implementation details remain proprietary"*); el nuestro sí, con bisección de 40 iteraciones
> y tests. Su ventaja no es el cálculo: es la UI y la cinta de opciones que ellos tienen.

## ✅ HECHO (2026-07-20/21)
- [x] Post-mortem imanes 2026-07-20 (hacia el imán, jamás a través del muro; decay por toques)
- [x] Investigación NOK (crash = Ericsson AI-cost read-through; 40% layoff = sin evidencia; earnings 23-jul BMO)
- [x] SPY añadido a la flota (bot C++ + keepalive)
- [x] Impresora: Brother NO era tuya (removida); HP 9120e bloqueada por tinta color (firmware HP+); PNGs a Desktop
- [x] Árboles de escenarios NOK/NVDA/QQQ/SPY + estrategias con opciones a Desktop
- [x] Estudio gexa.ai → régimen gamma; skills `gexa-terminal` + `gamma-regime-walls`
- [x] 26 skills por ticker + `korea-memoria` con patrones 6m + forma intradía 60d (`skill_patterns_refresh.py`)
- [x] Sistema diario: launchd `dailyplans` (04:00/08:30/09:12) + `postmortem` (16:20)
- [x] Generador 26 tickers (IBKR-first, VX CBOE, Finviz, Korea, futuros, griegas, árbol, forma)
- [x] Calibración empírica por setup×régimen (Wilson, no por ticker) — `calibration_ledger.py`
- [x] Patrones medidos (H&S/dobles/triángulos, follow-through empírico) — `pattern_detect.py`
- [x] Engranaje QQQ/SPY (amplitud ponderada de componentes) — `index_breadth.py`
- [x] Posters X: premarket/realtime/postmortem, ledger 10/día $4/mes, humor, "No consejo fin."
- [x] Draft X compacto+visual (escalera emojis 🔴🎯📍🟢🛑) + Corea semis + tendencia overnight
- [x] `force_meter.py` — fuerza/agotamiento en vivo (4 fases → acción de stop)
- [x] `posthours_cage.py` — picardía jaula 0DTE→liberación after-hours (ballenas semanales)
- [x] Healthcheck 3x/día auto-curador (`fleet_healthcheck.py`, launchd)
- [x] Flota canónica única `data/fleet.txt` (30) — nadie queda atrás
- [x] Alarmas flujo put/call alineadas a los tickers; DB limpia; cadena notificación verificada
- [x] X auth verificado (@YuniorR62327146, 200 OK, read-only, sin gastar post)
- [x] TradingView: zoom inspección + zoom chart verificados; skill documentada

## 🔄 EN CURSO / PENDIENTE
- [x] Magnets gexa dominados: find→scroll_to ref→read_page; parser gexa_parse los captura
- [x] X posts scheduled cada día verificado (4AM premarket + realtime daemon + 16:20 postmortem)
- [x] Auto-mejora semanal (domingo 19:00): refresca patrones/formas 6m + recalibra + corre tests + reporta
- [x] Conocimiento consolidado en LEARNED.md + skills + memoria; herramientas reutilizables xpost.py + gexa_parse.py
- [x] **Europa para ASML**: momentum Ámsterdam (ASML.AS ~6h lead) + STOXX50 al plan+draft (prob bump, línea 🇪🇺)
- [x] Tests C++23: correctness pass + benchmark (la cifra vieja "9.46 ns/op" era humo — ver `bench.cpp` abajo)
- [x] ~~Verificar gexa headless conecta REALMENTE en el run de 4am~~ **MUERTO 2026-07-25**: gexa.ai
      desaparecio ("gexa is gone now, we are on our own"). Mapa gamma calculado EN CASA:
      `scripts/gex_snapshot.py` -> `data/gex_snapshot.json` (griegas MEDIDAS de Polygon; MEDIDO
      hoy: **25 símbolos + `_meta`**, vs los 16 que se scrapeaban). Consumidores recableados
      `631f40b` `611841b` `8b6e2df` `cbfaa49` `f626e54` `aea3124` `c868877` `95e29b7`.
      Skill `gexa-terminal` y `scripts/gexa_parse.py` marcados JUBILADOS (`5e1c1cc`).
- [x] ~~Raíz del `com.ibtrader.fleet` exit=78 (EX_CONFIG)~~ — **hecho: lo mató la mudanza del repo.**
      MEDIDO hoy: `launchctl print gui/$UID/com.ibtrader.fleet` → **`last exit code = 0`**.
      MEDIDO: **0 de los 17** plists `com.ibtrader.*` apuntan ya a `~/Documents`; 16 apuntan a
      `/Users/yuniorrodriguezosorio/ib-trader` y el 17º (`polychains`) usa `$HOME/ib-trader`.
      La causa era TCC sobre `~/Documents` bajo launchd, documentada en `~/CLAUDE.md`.
      ⚠️ Los ficheros `*_autostart.err` del repo conservan el error VIEJO: son historia, no estado
      — leerlos como estado actual es lo que hace creer que el bug sigue vivo.
      *(Fusiona la casilla duplicada "launchd exit 78 (fleet/scan/screener/fastscan/rescan/screener6am)"
      del 2026-07-21. Del grupo queda un residuo distinto y menor, abajo: `com.ibtrader.scan`.)*
- [x] ~~Residuo del grupo exit-78: `com.ibtrader.scan` apunta a un binario `scan_server` que no
      existe~~ — **obsoleto: el job ya está desinstalado.** MEDIDO hoy:
      `~/Library/LaunchAgents/com.ibtrader.scan.plist` **no existe** y `launchctl print` responde
      *"Could not find service com.ibtrader.scan"*. Yo mismo abrí esta casilla al auditar,
      fiándome de un informe del 24-jul; al comprobarlo con `launchctl` resultó falsa. Queda
      escrito como recordatorio de que **un informe de agente no es evidencia hasta que se mide**.
- [ ] **[pendiente]** Primera cacería REAL de jaula-liberación (lunes al cierre, cuando el
      after-hours vive). *Qué es*: `scripts/posthours_cage.py` + `tests/test_posthours_cage.py`
      existen y pasan; falta EJECUTARLO una vez con mercado real. *Por qué importa*: es la única
      picardía del repo que aún no se ha visto disparar en vivo — hasta entonces es teoría.
- [x] ~~Documentar force/cage/healthcheck/breadth en `docs/DAILY-SYSTEM.md`~~ — **hecho `7875b32`**.
      Eran **0 menciones** de las cuatro en el manual, con las cuatro en producción. Nueva §11 con
      qué hace cada una, cómo correrla a mano, y el bug histórico que explica por qué vigilarla
      (el exit 1 del healthcheck que se auditaba a sí mismo en bucle; el `index_breadth` que caía
      en silencio a yfinance). Dos estados honestos escritos como tales: `force_meter` vive FUERA
      de los bots C++ y `posthours_cage` nunca se ha visto disparar en vivo.

## 💡 IDEAS / FUTURO (cuando se pidan)
- [x] Tweets con imagen adjunta (árbol PNG en x_media/) + gamma (flip/dealer/POC) en posts intradía
- [ ] **[pendiente]** `opt_tick_watch` event-driven para el strike ACTIVO (tiempo real, no poll
      5min). *Por qué importa*: filo de EJECUCIÓN — hoy el strike que estamos operando se relee
      cada 5 min; en 0DTE eso es una eternidad. *Fichero*: no existe (`scripts/opt_tick_watch*` = 0 hits).
- [ ] **[pendiente]** Fuerza/agotamiento por-tick plegada en los signal bots C++ (si se quiere el
      filo en la decisión). *Estado*: `force_meter.py` existe pero vive fuera del bot; MEDIDO:
      `qqq_signal_bot.cpp` tiene 0 refs a fuerza/agotamiento. *Por qué importa*: la regla 9 exige
      que la fuerza sea parte del veredicto SIEMPRE, y hoy el bot decide sin ella.
- [ ] **[pendiente]** Calendario macro (CPI/FOMC/NFP) al PDF — "no operar el print". MEDIDO:
      `scripts/daily_fleet_plans.py` = 0 hits de CPI/FOMC/NFP. *Por qué importa*: entrar con
      premium comprado justo antes de un print macro es la pérdida más evitable que existe.
- [x] ~~Revisar plan Polygon (POLYGON_KEY en feeds.env, quizá opciones/agregados mejores)~~
      **obsoleto: contestado el 2026-07-25 con la key real y grabado en `~/CLAUDE.md`.** El
      snapshot `/v3/snapshot/options/` SÍ da griegas+IV+OI en vivo; `?as_of=` es una TRAMPA (dice
      OK e ignora la fecha); los aggs por contrato no traen OI ni griegas; la cinta (`/v3/trades`)
      da 403. La decisión ya está tomada: archivar snapshots a diario en vez de pagar más.

## 📌 REGLAS QUE NO SE ROMPEN
- Señal-solamente (jamás ordena; única excepción autorizada: `order_engine/` con doble llave).
  Aditivo + degradación limpia. Respaldo en `backup/` antes de tocar el generador.
- Presupuesto opciones = cualquier contrato de la flota con premium ≤ $200 (ENMIENDA 2026-07-22).
- `notify_relay.sh` DEBE estar vivo (fue el fallo de notifs). Print o nada. 3 pérdidas = fin.
- Ningún `except` en camino de señal devuelve `0`, `0.0`, `0.5`, `50` ni `{}` — `None` o levanta.

## 2026-07-21 sesión viva
- [x] ~~opt_whale_watch: filtrar strikes sin security definition (QQQ 712.5 20260724 spamea Error
      200 en loop) — cachear contratos inválidos y saltarlos~~ — **hecho `020d814`**. MEDIDO:
      `scripts/opt_whale_watch.py:88-89` (`qcache` + `badk`), filtro en `:109`
      (`k not in badk[s]`), blacklist SOLO con respuesta definitiva en `:121-128` (si `qualify`
      devolvió 0 de todo se considera fallo transitorio y NO se veta — si no, un fallo de la farm
      dejaba un ticker ciego toda la sesión), tope de 12 strikes ATM en `:114`, y autocura en
      `:166` (`badk.clear()` tras 2 scans en cero).
- [x] ~~7/22 8:30: confirmar fichas CLSK/INTC vs gaps overnight~~ — **obsoleto: la fecha pasó hace
      3 días.** `data/fichas_2026-07-22.txt` queda como histórico.
- [x] ~~x_post_common: sanitizar a MAX 1 cashtag por post (X rechaza 403 con 2+; el $4.7B tambien
      cuenta como cashtag si va pegado a letras — revisar regex)~~ — **hecho `39bd147`**. La regex
      vieja solo veía `$LETRAS` y arrastraba un `... if False else ...` muerto, así que el caso
      que Yunior cazó (`$4.7B`) no lo tocaba. Ahora cuenta como cashtag cualquier `$` seguido de un
      token con al menos una letra; `$200` (solo dígitos) se deja intacto porque X no lo cuenta;
      los importes pierden el `$` y ganan ` USD` para no perder el significado. `count_cashtags()`
      expuesto y **14 tests** con posts reales de la flota.
- [ ] **[pendiente]** opt_whale_watch v2: alarma por PREMIUM NETO en dolares (mid×vol por lado,
      umbral ±$20M o delta brusco/30min) ademas del ratio de volumen. *Por qué importa*: el
      **tide -53M del 7/21 no sonó** porque el P/C de volumen era 0.86 — las ballenas caras y
      silenciosas también deben sonar, y hoy son invisibles. MEDIDO: `scripts/opt_whale_watch.py`
      tiene **0 refs** a `premium`/`notional`/`mid`; la única métrica es `pc = vp/max(vc,1)` (`:157`).

## 2026-07-23 — Chart cockpit GEX en vivo (charts/live.html + chart_bridge.py)
Hecho: lightweight-charts v5 + ib_async (TWS 7496 realtime) · combo_tl (Supertrend Buy/Sell + Madrid ribbon + BB/SMA/VWAP/MACD + trendlines) · selectores ticker/intervalo · GEX/flip/muros en tiempo real (levels_loop 15s, spot vivo) · escala $/1% verificada · imán(oro)/acelerador(morado) por signo · flip 0DTE estático + toggle 0DTE↔ALL-EXP · VEX/vanna/charm + chip Vanna · dealer-pressure score -100..100 · expected-move cone · nuestras señales (whale/flow/alarma) como marcadores · botones info ⓘ + Guía · dominancia POC %C/%P · régimen TRANSICIÓN · icono custom · burbujas GEX pin/trampilla · badge `.bq` de book-quality. Skill `gexa-framework`.
- [ ] **[pendiente — PAGO DE YUNIOR, desbloquea 2 casillas]** **VIX**: código LISTO
      (`scripts/chart_bridge.py:1903-1906`, `reqMarketDataType(1)` realtime + chip en
      `charts/live.html:295`, con degradación limpia). Falta la suscripción IBKR **CBOE Global
      Indexes** (~$1.50/mes). *Por qué importa*: es **la misma suscripción que hace falta para
      SPX**; con un solo pago caen las dos. Ningún cálculo actual lo usa (EM/vanna van por IV
      por-contrato), así que no es crítico — pero sin él, la banda de fragilidad no se puede construir.
- [ ] **[pendiente, BLOQUEADA por el VIX]** Banda de fragilidad / true-flip ajustado por vanna — la
      ÚNICA feature que necesita VIX de verdad: mide cuánto movería el flip un shock de VIX
      (banda <5pt estable, >15pt frágil). *Por qué importa*: distingue un flip que aguanta de uno
      que se mueve solo porque cambió la vol — hoy tratamos todos los flips como igual de sólidos.
- [ ] **[pendiente, buildeable ya]** **Migration-trail del flip**: polilínea del flip histórico
      (horizontal=estable / inclinada=deriva / dentada=régimen no fiable). MEDIDO: 0 hits de
      `migration`/`flip_trail` en `scripts/` y `charts/`. *Por qué importa*: un flip DENTADO
      significa que el régimen que estamos cantando no es fiable, y hoy no hay forma de verlo.
      *Dato ya disponible*: `levels_5m.jsonl` (archivador #18, `c91c375`) guarda el flip cada 5 min.
- [x] ~~**Volume Profile (VPVR)** desde las barras — POC de volumen vs POC de gamma = confluencia~~
      — **hecho `bc670c6`**. `scripts/volume_profile.cpp` (C++23, `-O3 -mcpu=native -Wall -Wextra`,
      cero warnings) + `scripts/build_volume_profile.sh` + `tests/test_volume_profile.py` (22 tests,
      ASan/UBSan limpios) → `data/vpvr.json`. Lee `poly_bars` en **SQLITE_OPEN_READONLY**.
      MEDIDO sobre datos reales (30 syms × 20 sesiones, 20 s): **LRCX POC-vol 319,92 vs POC-gamma
      320,0 = 0,03% CONFLUENCE**; GLD 0,40% NEAR; 23 APART; 5 con `confluence: null` — exactamente
      los 5 sin POC de gamma en el mapa (NVDA QCOM NFLX NOK SKHY): sin con qué comparar se dice
      null, no "APART". **DESCRIPTIVO Y SIN VOZ**: cero probabilidad; las etiquetas
      CONFLUENCE/NEAR/APART son convención de distancia declarada, y el propio JSON lleva
      `thresholds_are_convention_not_measured: true`. La confluencia **NO está medida** todavía.
- [ ] **[pendiente, buildeable ya]** **Pin-risk score** (concentración de |gamma| × proximidad ×
      1/T; "fortress pin" si el POC coincide con el call wall). MEDIDO: 0 hits de
      `pin_risk`/`fortress`. *Por qué importa*: la doctrina prohíbe 0DTE comprado en zona de pin
      (protocolo imanes OI) y hoy esa zona se juzga a ojo. *Nota*: `pin-clock` (`d21f2eb`) ya da
      el max-pain estructural — esto es la otra mitad, la concentración.
- [ ] **[pendiente, buildeable ya]** **Charm al chart**: la matemática YA existe
      (`scripts/gex_core.py:145` `bs_charm`, `build_exposure` con vanna/charm) pero MEDIDO
      `grep -in "charm" charts/live.html` = **0 hits** → falta la capa CHARM en el toggle junto a
      GEX/VEX. *Por qué importa*: el charm es el drift/pin de la TARDE, justo la ventana
      13:30-15:45 que la skill `pin-and-expiry-mechanics` marca como decisiva.
- [ ] **[pendiente]** Ampliar strikes del cache (`scripts/opt_chain_cache.py`). MEDIDO hoy,
      `:49-54`: `PCT_BAND = 0.06` (±6%) y `MAX_STRIKES = 20`. *Por qué importa AHORA*: el motivo
      original ("clavar el flip exacto de gexa") **murió con gexa**, pero el hueco real sigue: con
      ±6% el flip 0DTE queda a ~0.5% y **`book_quality` juzga libros truncados**. *Ojo — puede que
      ya no haga falta*: `poly_chain_archive` trae hoy la cadena COMPLETA con griegas medidas
      (30 cadenas, QQQ 854 contratos), así que antes de ampliar la banda de IBKR conviene decidir
      si el cache de TWS sigue siendo la fuente del flip o pasa a serlo Polygon. **Decisión antes
      que código.** *(Fusiona la casilla duplicada del 2026-07-23 EOD.)*
- BLOQUEADAS (necesitan tape firmado + dark-pool licenciado que NO tenemos): True Dealer Book,
  Dark Pool Nodes, DIX, Market-Tide firmado, GEX direccional. Sustituto casero = daemons whale/flow.
  (Ver skill `anti-overfit-killlist`: no se construyen, y está razonado por qué.)

## 2026-07-23 EOD — gexa se va + fixes chart
- [x] ~~URGENTE (antes de que gexa muera): AMPLIAR strikes del cache … y VALIDAR nuestros números
      vs gexa MIENTRAS SIGA VIVO (última oportunidad de calibrar contra la verdad)~~
      — **obsoleto: gexa.ai desapareció el 2026-07-25.** La oportunidad de calibrar contra ella ya
      no existe y no volverá. Se cierra explícitamente, no en silencio.
      Lo que quedaba de valor (ampliar la banda del cache) vive ahora en la casilla de arriba,
      con su motivo REAL en vez del motivo muerto.
      ⚠️ Y conviene recordar por qué no es una pérdida grande: comparando el último snapshot de
      gexa contra nuestro `gex_core` sobre las cadenas Polygon, **AAPL daba flip 208,0 con spot
      333,47 (−37,6%)** — imposible para un flip de gamma: su scrape estaba roto. Y el campo
      `regime` venía **null en 15 de los 16** símbolos, justo el campo del que depende la doctrina.
- [ ] **[pendiente]** Chart: barra de precios a la derecha muestra precios incorrectos AFTER CLOSE
      — probable autoscale jalado por las líneas de niveles (muros/EM/alarmas) lejos del último
      precio cuando las velas dejan de actualizar. *Fix propuesto*: constreñir el autoscale a la
      serie de velas (`autoscaleInfoProvider`) o esconder líneas lejanas tras el cierre.
      *Por qué importa*: es el eje que Yunior lee para decidir; un eje mal escalado después del
      cierre hace que los niveles del día siguiente se dibujen mal a ojo. *Fichero*:
      `charts/live.html` (en manos de otro agente en la sesión del 25-jul).
- [x] Fix tickMarkFormatter (hora Toronto solo en marcas de tiempo >=3, no en día del mes)

## 2026-07-24 — permiso de bots (TCC) + debug TWS
- [x] Auto-chequeo de permiso en fleet_keepalive_start.sh: si no puede escribir el HUD Desktop -> voz DANGER + data/PERM_DENIED (nunca más pérdida silenciosa).
- [ ] 🥈 **[pendiente — ACCIÓN MANUAL DE YUNIOR]** PERMANENTE (System Settings > Privacy &
      Security > Full Disk Access): añadir `/bin/zsh`, `/usr/bin/python3`, `venv-chart/bin/python`,
      y los binarios C++ (`price_alarm`, `flow_pulse`, `qqq_xray`). *Por qué sigue importando aunque
      el repo ya no viva en `~/Documents`*: la mudanza quitó la causa PRINCIPAL (y los jobs pasaron
      a exit 0), pero cualquier ruta futura bajo Desktop/Documents/Downloads volverá a romperse en
      silencio bajo launchd, y el HUD del Desktop sigue siendo un símlink hacia el repo. Es el único
      fix que garantiza permiso en TODO contexto (launchd/reboot). Coste: 2 minutos.
- [x] ~~POST-CIERRE: centralizar la ruta de señales del Desktop a data/trading-signals/ en los 19
      archivos~~ — **hecho** (fases 1 y 2, ver sección "señales movidas a /data"). Lo único que
      queda de esto es el DEPLOY, fusionado en la casilla de despliegue de abajo.
- [x] Debug TWS: conexiones SANAS (5 conn ESTABLISHED, barras/cache frescos, 253 señales hoy).
      El 326/clientId82 era test viejo. Ruido benigno: opt_chain 'No security definition' +
      chart_bridge Error 366 (cancel hist-data).
- [x] ~~gexa SIGUE VIVA (HTTP 200): calibrar nuestro flip vs gexa (ampliar strikes)~~
      — **obsoleto: gexa.ai desapareció el 2026-07-25** (duplicado del anterior).

## 2026-07-24 EOD — CACERÍA DE BUGS
Workflow de 15 agentes: 87 hallazgos brutos, pero **8 agentes murieron por límite de gasto —
incluidos los 6 refutadores y el team lead**. "0 refutados" NO significa 0 falsos positivos:
significa que nadie pudo verificar. Los de abajo los confirmé A MANO uno por uno.

- [x] **AUTO-CANCELACIÓN** (crítico, evidencia en producción). `openOrder()` cancelaba cualquier
  orden `OE:` sin comprobar si era nuestra y de esta sesión; TWS emite ese callback SIN PEDIRLO
  por cada orden colocada → el motor se cancelaba solo. `ledger/orders.jsonl` id=33: un intent y
  CINCO cancel que nadie pidió, en 150ms. Fix: usar el flag `reconciled_` que YA existía.
- [x] **SIDE PERDIDO** (crítico). `chart_bridge` no pasaba `side` → el motor caía a default SELL.
  Cerrar un CORTO manda "buy" → se vendía otra vez y DUPLICABA el corto. Fix: pasar side+secType.
- [x] **STOP DUPLICADO tras reconnect** (crítico) → segundo STP sobre la misma posición.
  Fix: `adopted_stop_id()` + adoptar el vivo.
- [x] **FILL PARCIAL sin stop** (alto). Fix: emitir FILL por lo llenado + re-armar el stop.
- [x] **TOPE POR ORDEN**: `--max-order` (default = `--budget`). Verificado: qty=4 → VETADO $608.
- [x] **index_breadth** partía por "," archivos separados por ESPACIO → la guarda de frescura era
  CÓDIGO MUERTO y cada corrida caía en silencio a yfinance retrasado.
- [x] **math_test no probaba NADA**: cero `#include` del proyecto. Ahora incluye `engines/bb_core.h`
  con valores de referencia exactos: 39/39 en release Y ASan.
- [x] Skill `bug-hunter` con los 11 olores demostrados + greps de detección.
- [x] ~~`bench.cpp` mide al OPTIMIZADOR: reporta 2.4e12 ops/s (imposible en M1 ~3.2GHz)~~
      — **hecho `3f7010e`**. MEDIDO: `tests/cpp/bench.cpp:41` `sink()` con
      `asm volatile("" : : "r,m"(value) : "memory")`, `:43` `clobber()`, y guarda **fail-loud**
      `:50` `MIN_NS_PER_OP = 0.05` que sale con código 1 si una cifra vuelve a ser imposible.
      2,4e13 ops/s → **2,70 ns/op**. El "9.46 ns/op" que este fichero anunciaba era humo.
- [x] ~~Los 24 bots se compilan con `c++20 -O2` sin arquitectura nativa
      (`deploy_signals_to_data.sh:13`)~~ — **hecho `5d8607f` + `c122128`**. MEDIDO, las flags de
      hoy son `-std=c++2c -O3 -mcpu=native -Wall -Wextra`. Los `-Wall -Wextra` los faltaba y los
      añadí en `c122128`, con conteo de warnings cantado al final del deploy (a propósito **sin**
      `-Werror`: un aviso nuevo de clang no puede dejar a la flota SIN binarios).
      Verificado sin ejecutar el deploy: `qqq_signal_bot.cpp` compila en 2,6 s, exit 0, **0 warnings**.
- [x] ~~**auditoría de TODOS.md** (los `[ ]` de este archivo): el agente murió sin correr~~
      — **hecho: es esta.** 73 casillas revisadas una a una contra código y `git log`. Recuento al final.
- [ ] 🥉 **[pendiente — REPORTAR, NO ARREGLAR]** **~84 hallazgos SIN VERIFICAR** del workflow.
      *Dónde está el fichero*: **NO en el repo.** MEDIDO: `tasks/` no existe aquí y `git log --all
      -- 'tasks/*'` = 0 commits. El fichero vive en un scratchpad de sesión
      (`/private/tmp/claude-502/.../tasks/w7i2a7lhe.output`, 182.703 bytes, 1.448 líneas, mtime
      24-jul 19:06) **y se puede perder al limpiar `/tmp`**.
      *Qué contiene*: JSON con `agentCount: 14`, `logs[]` donde constan los 8 agentes muertos
      (`failed: You've hit your monthly spend limit`), y `result` con
      `total_brutos: 87, refutados: 0, vivos: 87`, repartidos `dinero_real: 34 · señal_falsa: 37 ·
      operativo: 16`. Cada hallazgo trae `file, line, severity, blast, failure_scenario, evidence,
      fix_sketch` y `verdict_note: "sin veredicto"`.
      *Fichero RESCATADO* `hecho 0f7893c`: estaba a una limpieza de `/tmp` de perderse.
      **CLASIFICADOS LOS 87 (2026-07-25), sin arreglar ninguno**: **63 VIVOS · 24 ARREGLADOS ·
      0 no-aplica.** Método validado con 4 controles: los 4 bugs que Yunior confirmó a mano salen
      ARREGLADO y con la huella del fix visible (`tws_adapter.cpp:244` `reconciled_||mia_viva`,
      `chart_bridge.py:1049` side+secType, `order_engine.cpp:510` `adopted_stop_id`,
      `tws_adapter.cpp:213-221` rama `fill_qty>0`).
      Reparto de los 63 vivos: **4 critical · 22 high · 25 medium · 12 low**.
      *Acción que queda*: los 63 siguen **SIN REFUTAR** por un segundo par de ojos — están
      verificados como "el defecto está en el código", no como "el defecto hace daño". Antes de
      tocar nada, refutar por severidad. Los 4 critical y los 5 de dinero están desglosados abajo.
- [ ] 🥈 **[pendiente — LO DECIDE YUNIOR]** **DESPLIEGUE**: los arreglos del motor están compilados
      pero **la flota sigue corriendo los binarios viejos**. `zsh scripts/deploy_signals_to_data.sh`
      recompila 28 binarios (24 bots + price_alarm/flow_pulse/qqq_xray/korea/finviz) y **reinicia
      la flota**. *Por qué importa*: hasta que esto corra, los tres bugs críticos de dinero
      (auto-cancelación, side perdido, stop duplicado) siguen VIVOS en lo que se ejecuta, aunque
      estén arreglados en el código. Además activa el código /data-directo (los bots dejan de
      depender de TCC/Desktop y funcionan bajo launchd/reboot); el símlink del Desktop se queda
      para que Yunior siga viendo las señales. *Cuándo*: SOLO con mercado cerrado. Hoy la flota
      está fuera de ventana a propósito (`./fleet_hours --why`).
      *(Fusiona las dos casillas duplicadas: "DESPLIEGUE PENDIENTE" del hunt y "DEPLOY AL CIERRE"
      de la sección /data.)*

## 2026-07-24 — señales movidas a /data (permiso garantizado, sin TCC)
- [x] FASE 1 (live): bytes migrados Desktop -> data/trading-signals/ (277 líneas, sin pérdida);
      ~/Desktop/trading-signals ahora es symlink -> repo. Cero downtime.
- [x] FASE 2 (fuente): 19 archivos editados para escribir DIRECTO a data/trading-signals
      (Python via `__file__`, shells via `$ROOT`, C++ via `fleet_notify.h` relativo). Cero refs
      de código a Desktop.
- Nota: fase 1 ya da "todo en /data"; el deploy solo elimina el último rastro del path Desktop
  del binario. → casilla de DESPLIEGUE, arriba.

## order_engine — HALLAZGOS AUDITORÍA (2026-07-24, agentes ultracode)
> ⚠️ `order_engine/` es el **ÚNICO** módulo autorizado a colocar órdenes (ENMIENDA 2026-07-24,
> doble llave + paper-first + disarm-on-exit). Por eso sus pendientes pesan más que los del resto
> del repo: aquí un bug es dinero, no una señal fea.

### ✅ ARREGLADOS Y COMPILADOS
- [x] `frozen_` nunca se limpiaba tras reconnect → el motor dejaba de operar el resto del día
- [x] `commands.jsonl` offset TOCTOU → posible **doble-close**
- [x] Fill parcial dejaba posición **sin stop**
- [x] `modify()` sobre STOP escribía `lmtPrice` en vez de `auxPrice` → mover el stop era no-op silencioso
- [x] **Idempotencia entre reinicios**: zona ya llena volvía a COMPRAR al reiniciar
- [x] `reconcile()` cancelaba stops huérfanos → posición desnuda (ahora los **adopta vivos**)
- [x] Disarm-on-exit cancelaba el stop sin aplanar → ahora **deja stops vivos** + aviso en voz alta
- [x] Allowlist de cuenta solo en live → ahora **siempre** (`d9cc62c`)
- [x] Zona borrada del chart mataba el stop de una posición abierta → ahora lo conserva
- [x] Watch-local stop vendía `z.qty` (sobre-venta en fill parcial) → usa `filled_qty`, no remata

### ⬜ PENDIENTES (17 quedaron sin verificar por límite de sesión; estos 9 sí están razonados)
> **Por qué importan, en una línea**: son los que quedan entre el motor y una pérdida real; los
> tres primeros son de TAMAÑO (cuánto se gasta) y los demás de PROTECCIÓN (qué pasa si algo falla).
- [ ] **[pendiente]** Sin tope de exposición AGREGADA por cuenta — hoy es por zona ($200 opción /
      $3000 acción); **N zonas multiplican el gasto sin techo global**. Es el que más dinero puede
      mover de golpe.
- [ ] **[pendiente]** Sin reconciliación contra `reqPositions` — la fuente de verdad debe ser la
      cuenta IBKR REMOTA, no el estado local. Es la lección de 2026-07-16: matar PIDs locales no basta.
- [ ] **[pendiente]** Presupuesto de opciones es **por contrato**, no por zona: `qty>1` multiplica
      el gasto sin cap total. *(Relacionado con el primero; se arreglan juntos.)*
- [ ] **[pendiente]** Panel `close` confía en `cqty` sin comparar contra la posición real →
      posible sobre-venta / flip a corto (**en TFSA no se shortea**: sería un rechazo o una
      posición ilegal).
- [x] ~~`close` del panel no cancela el stop nativo → stop GTC huérfano server-side~~ —
      **hecho `53e12ec` + mapa `7a0ddaf`/`1bd17c1`.** Cancela ANTES del close; empareja por
      identidad de contrato vía `z.entry_c` (no `z.price`). 94 checks, 0 fallos. Verificado en
      frío; **ruta real con fills queda para paper el domingo** — no declarado verificado en vivo.
- [ ] **[pendiente]** STOP nativo **rechazado** no se reporta como fallo de protección (REJECTED
      solo se maneja para la entrada) → te crees protegido y no lo estás. **Fallo silencioso.**
- [ ] **[pendiente]** Reconnect re-arma stops sin verificar que `reconcile` terminó (el arranque sí
      aborta, el reconnect no) → la puerta de vuelta al bug del stop duplicado.
- [ ] **[pendiente]** Allowlist live usa `find()` sobre la lista completa de `managedAccounts`
      (substring, no exacto) → una cuenta cuyo id CONTENGA al permitido pasaría el filtro.
- [ ] **[pendiente]** Clamp asimétrico del stop de opción (caso corto sin cota superior).
- [ ] **[pendiente, del hunt sin refutar]** `order_engine.cpp:772`: el centinela `-1.0000` del
      cache de cadena se usa como **delta REAL** → stop nativo clavado a −5% de la prima
      (stop-out instantáneo). **Patrón "cero plausible"** — verificar y, si se confirma, es de los
      graves. *(Ver la casilla de los 84 hallazgos.)*

### ⬜ UI / DATOS
- [ ] **[pendiente]** **Live market data** (diferido): suscripción IBKR para API en paper, o cablear
      Finnhub (key en feeds.env). *Por qué importa*: sin esto **el spot está STALE y las zonas no
      disparan** — el motor entero es decorativo en paper.
- [ ] **[pendiente]** Selector de timeframe compacto estilo TradingView. *(Cosmético.)*
- [ ] **[pendiente]** Chip de zona dice "Ccall" para acciones — label instrument-aware. *(Cosmético,
      pero induce a error sobre qué instrumento se va a comprar.)*
- [ ] **[pendiente]** Skills de QA engineer + suite de tests automatizada para el motor.
      *Por qué importa*: el módulo que SÍ ordena es el que menos cobertura tiene.
- [ ] **[pendiente]** Optimizar latencia de ráfaga (mediana 1.1s por serialización del pump 2s;
      min real 113ms). *Por qué importa*: "retraso = dinero" (regla propia de Yunior).

## OLA 1 features minadas — CERRADA (2026-07-25)
Spec: `docs/FEATURES-MINED-2026-07-25.md`.
- [x] **#5 `chain-honesty`** — inversión de IV por bisección + forward por paridad en `gex_core`,
      `iv=0.3` BORRADO, cabecera honesta en `opt_chain_cache.py`, contrato en `docs/CHAIN-HEADER.md`,
      `greeks_ok_pct<0.5` → claves gamma a `null` (jamás 0). Medido: RTH 100% griegas, 16:16 = 0%. `56ed1fe`
- [x] **#6 `flip-honesty` + congelar a 09:35** — el repreciado GANA, `flip_src`/`flip_why`, todas
      las raíces con bisección, `trapdoor_root`, `flip_open` congelado / `flip_live` diagnóstico.
- [x] **#13 `next-day-map` roll-off** — `exp_status()` rueda el vencimiento EN EL CIERRE (16:00 ET),
      no a medianoche. Era la causa del salto de MANADA de las 00:00:45.
- [x] **#3 `book-quality gate`** — `scripts/book_quality.py` → `data/book_quality.json`, etiquetas
      THIN/BIFURCATED/NEAR_FLIP/STABLE_PIN + coeficiente multiplicativo. `b066f81`
- [x] **`vol-trigger` (#20) congelado a 09:35** — `scripts/vol_trigger.py` → `data/vt_<sym>.json`. `04b9fcf`
- [x] ~~cablear el `coef` de `book_quality` como MULTIPLICADOR en `direction_view` + badge~~
      — **hecho `b91de93` `13c903d`** *(duplicado: aparecía dos veces en el fichero)*.
- [x] ~~`poly_chain_archive.py` NO tiene job de launchd — hoy solo 3 símbolos~~ — **hecho `70c0e2c`**.
      MEDIDO: `com.ibtrader.polychains.plist` a las 16:20 y 08:45; **30 cadenas archivadas hoy**.
- [x] ~~que `book_quality.py` prefiera `chain_full` cuando `ibkr_tws` dé <50% de griegas~~
      — **hecho `1cacc8f`**. MEDIDO: `book_quality.py:89` `MIN_GREEKS_SRC = 0.5`, regla pura
      `prefer_fallback()` en `:175-192`, y la **procedencia va DENTRO del dato**: `chain_src`
      (`:228`) + `greeks_medidas`. Esto cerró el hallazgo de que **el "THIN" de 25/26 símbolos era
      un artefacto de la fuente, no un hecho del mercado** (AAPL: 20 contratos y 0% griegas por
      IBKR fuera de RTH → THIN coef 0; por Polygon, 96 contratos y **94%** con gamma+OI medidos).
      Sin este fix la flota entera operaba con los niveles gamma apagados fuera de RTH. `6ef5f5d`
- [ ] **[pendiente — ESPERA DATOS, no código]** percentiles `book_pctile`/`impact_pctile` necesitan
      **20 sesiones** de snapshot COMPLETO de Polygon (feature #7); hoy salen `null` DECLARADOS y el
      `coef` cae al suelo 0.35. Se acumulan solos en `data/book_quality_hist.jsonl` desde que el
      cron existe. *Por qué importa*: mientras tanto el gate de libro está en su valor más
      conservador y **frena la gamma de todos los símbolos por igual**, incluidos los libros sanos.
      *Cuándo se desbloquea*: ~20 sesiones desde el 2026-07-21.

## OLA 1 — archivadores, guardas de integridad y presupuesto de voz (2026-07-25)
> 7 features, 7 commits, 101 tests nuevos.
- [x] **#16 `chain-cube archive` + retención** — `6bae616`. Lector ÚNICO de los dos formatos,
      índice de cobertura honesta (2984 fotos, 171.216 filas), retención medida (7,40 → 2,2 MB/día).
      **`--apply` SIN activar**: `local_option_scorer.py`, `option_vehicle_backtest.py` y
      `replay.cpp` leen las fotos SUELTAS por glob. Migrarlos al lector antes de agrupar.
- [x] **#18 `levels-5min archive`** — `c91c375`. Copia cada 5 min sin tocar el generador, con
      `age_s`/`stale` para que copiar un fichero atascado 78 veces no parezca densidad. ~4,7 MB/día.
- [x] **#15 `equity-prints archiver`** — `b0c1b8a`. Salva la cinta firmada ANTES del trim de 900 s
      sin tocar `ibkr_bar_bridge.py`. Primera corrida: 7477 prints salvados.
- [x] **#9 `truth-lock`** — `ea26bc5`. Huella SHA-1 de 120 barras cerradas por sym; inyección sobre
      el fichero REAL detectada (close +0,05). Banner + tabla propia, SIN voz.
- [x] **#10 `em-envelope`** — `176caea`. `data/em_<sym>.json`, 26/30 vallas. Dos bugs cazados con
      datos reales (vallaba el lunes con el straddle 0DTE del viernes).
- [x] **#14 `pin-clock`** — `d21f2eb`. `data/pin_<sym>.json` descriptivo, `p_pin` SIEMPRE null.
- [x] **#12 `voice-budget governor`** — `daf90de`. DANGER ni pasa por el gate, fail-open.
- [ ] **[pendiente — LO DECIDE YUNIOR]** cargar los 5 `.plist`
      (`scripts/com.ibtrader.{prints,levels5m,truthlock,cubeindex,fence}.plist`, `plutil -lint` OK,
      **sin cargar a propósito**). *Por qué importa*: hasta cargarlos, 5 archivadores corren solo
      cuando alguien los lanza a mano, y **las features que esperan 20-40 sesiones no empiezan a
      contar**. Es el cuello de botella de 3 casillas de abajo.
- [ ] **[pendiente — LO DECIDE YUNIOR]** encender el presupuesto de voz con
      `touch data/voice_budget_enable`. Hasta entonces es código muerto **por diseño** (fail-open,
      DANGER exento). *Por qué importa*: sin él nada limita el número de avisos hablados por sesión.
- [ ] **[pendiente — ESPERA DATOS]** (#15) ningún motor de absorción hasta ≥20 sesiones archivadas
      por sym; hoy 1. *Depende de*: cargar el plist `prints`.
- [ ] **[pendiente — ESPERA DATOS]** (#18) ninguna feature puede condicionar sobre gamma a tiempo
      de etiqueta hasta que `levels_5m.jsonl` tenga ≥40 sesiones; hoy 1. *Depende de*: plist `levels5m`.
      *Por qué importa*: es lo que bloquea el **migration-trail del flip** y cualquier feature que
      quiera saber en qué régimen gamma estaba el mercado cuando se etiquetó una señal.
- [x] ~~(#14) el kill por colinealidad de `pin-clock` necesita n≥10 syms con `chain_full` (hoy 3)~~
      — **hecho `6f4fc62`: corrido, y `pin-clock` SOBREVIVE su propia vara.**
      MEDIDO hoy con la muestra completa: **n=30 símbolos, rho=−0,2753**, kill `|rho|>0,9` →
      `APORTA_ALGO`. El max pain **no** es un duplicado del `abs_wall`, así que la feature se queda.
      Sigue **SIN probabilidad medida**: esto mide colinealidad, no edge, y ahora la nota lo dice.
      De paso se arregló un defecto de honestidad: la nota se quedaba clavada en "con n<10 no se
      concluye nada" incluso con n=30, al lado de un veredicto concluyente — un lector no sabía a
      cuál creer. Hay test que prohíbe que la nota niegue la muestra.

## REGENERACIÓN DE SEÑALES (agente regen, 2026-07-25)
- [x] "usa los datos de polygon y reproduce, es sencillo... olvidate del websocket de IBKR,
      reproduce local como si estuviera conectado a IBKR" (Yunior 2026-07-25) —
      `scripts/regen_signals.py` + `scripts/regen_shim/`. `hecho f11c6fb 09d0a80`.
      501 sesiones (2024-07-25 → 2026-07-24). cusum 501/501 COMPLETO (n=12.780).
- [x] ~~CORRIENDO EN BACKGROUND: bollinger va por 63/501 sesiones, ETA ~2,8 h~~
      — **hecho: TERMINÓ.** MEDIDO hoy en `trades.db`: `signals_regen` tiene **200.811 filas
      bollinger cubriendo las 501 fechas** (2024-07-25 → 2026-07-24), y el proceso **ya no corre**.
      ⚠️ **Honestidad**: el log `/tmp/regen_R1_boll.log` tiene **24 sesiones con `rc=-15`** (SIGTERM),
      así que esas 24 pueden estar cubiertas solo en parte. Antes de publicar cualquier número de
      bollinger conviene re-correr esas 24 fechas (es reanudable: mismo comando).
      Cadena a rehacer con la muestra completa:
        `./venv/bin/python scripts/barrier_labels.py --signals-table signals_regen build`
        `./venv/bin/python scripts/null_control.py --signals-table signals_regen --null-exclude sym-date run --seed 7`
      *(El `barrier_labels build` estaba corriendo mientras se escribía esta auditoría.)*
- [x] ~~`cusum` sale **DEAD** con muestra suficiente~~ — **hecho `2804663`**: TERREMOTO pasó a
      **BANNER-SOLAMENTE**. MEDIDO (n_eff 1513, edge −0.034, CI [−.060,−.005] **entero por debajo
      de cero**): la alarma es PEOR que entrar al azar. Prueba en el fichero vivo,
      `data/signal_enable.json:114-122`, con el `why` escrito dentro del dato.
      **Matar una feature con números vale tanto como construirla.**
- [ ] **[pendiente — LÍMITE DE DATOS, no de código]** NO regenerable sin cadenas históricas:
      `whale`, `flow`, `structural` (solo 4 días de cadenas en `data/history/`). Para medirlas hay
      que archivar cadenas a diario y esperar ~40-60 sesiones, o backfillear opciones de Polygon
      (que **no traen OI ni griegas** — medido). *Por qué importa*: son 3 de las fuentes que más
      voz tienen hoy y **ninguna está medida**. Es el mayor punto ciego que queda tras la ola 1.
      *Ya está corriendo el reloj*: el cron de cadenas existe desde el 2026-07-25 (`70c0e2c`).
- [x] ~~Las 30 skills `ticker-*` + `gamma-regime-walls` siguen diciendo "gexa gamma"~~
      — **hecho** (verificado en disco; **sin commit porque viven fuera de git**, en
      `~/.claude/skills/`). MEDIDO: `ticker-qqq/SKILL.md:3` dice hoy "mapa gamma propio, muros OI
      IBKR…", sin gexa; `gamma-regime-walls` = 0 hits de gexa. Residuo benigno: 2 de 31 ficheros
      la mencionan en el CUERPO como nota histórica fechada, no en la `description`.
      Las skills DEL REPO se arreglaron en `a387e03`.

## HUNT 2026-07-24 — los 87 clasificados (2026-07-25). NINGUNO ARREGLADO AQUÍ
> Fichero completo: `docs/hunt/hunt-2026-07-24-w7i2a7lhe.json`. **63 vivos · 24 arreglados.**
> "Vivo" = el defecto está en el código HOY. **No** = está demostrado que hace daño: eso es lo
> que faltan los refutadores. No tratar como bug hasta refutar.

### Los 4 CRITICAL vivos
- [x] ~~`scripts/backtest_harness.py:72` — `ret=(r[0]-entry)/entry*100*th; win=ret>0.05`~~ —
      **CONFIRMADO Y ARREGLADO `85bec77`**. Ya no tiene definición propia de "win": delega en
      `barrier_labels` (triple barrera) y añade el COSTE declarado (`FRICTION_PCT`: acción
      0,040% / opción ATM 0,069% / opción OTM 0,340% del subyacente). MEDIDO en la celda
      pre-comprometida k_tp=k_sl=1,0 H=30: WR viejo TOTAL 47,8% → barrera sin coste **50,0%**
      (que es la moneda al aire analítica `k_sl/(k_tp+k_sl)`) → **42,7% neto** de opción ATM y
      **5,4%** de opción OTM. La expectancia TOTAL pasa de +0,000 ATR a **−0,355 / −0,613 /
      −3,021 ATR**: negativa en TODAS las celdas en cuanto entra cualquier coste. Sobre las 501
      sesiones (`barrier_outcomes_regen`, n=213.656) bollinger va de 50,0% bruto a **37,0% neto**.
      Propuesta en `data/backtest_harness.PROPUESTO.json`: 93 celdas, **0 APTA**. `baseline`
      conserva el etiquetado viejo solo para el scoreboard, con
      `label_def='horizon_return_DEPRECATED'` estampado en la fila. 19 tests.
- [ ] **[pendiente]** `scripts/bollinger_complements.py:394` — grid de **318 tests sin corrección
      por multiplicidad**. *Daño*: **95 celdas de ruido aplicadas como VETO en vivo** en `bb_engine.cpp`.
- [x] ~~`scripts/calibration_ledger.py:110` — `after = d[d.High >= entry]` es una máscara
      booleana, no un corte temporal~~ — **CONFIRMADO Y ARREGLADO** (diff en `75a3442`, barrido
      por el `commit -a` de otro agente; medición en `d77a7a4`). Ahora es corte temporal
      `d.iloc[i0:]` desde la barra que imprime la entrada, con la barra de entrada ambigua
      resuelta STOP-PRIMERO igual que `barrier_labels.triple_barrier`. Los dos tests que fallaban
      lo hacían con `'win' == 'loss'`: el daño literal. MEDIDO: sobre el ledger vivo (56 filas,
      2026-07-21) el replay reproduce exacto el 88,9% publicado y **no cambia ni una fila** →
      `data/calibration.json` intacto, nada que conmutar. Sobre 13.365 sesiones reales de
      `poly_bars` con la geometría del propio ledger: 63,2% → **62,8%** (−0,4 pp), y el sesgo
      tiene SIEMPRE el mismo signo en las 14 geometrías barridas (la máscara nunca es
      conservadora). **La mina**: el daño escala con la resolución de barra — −0,5 pp a 15m
      (lo que `grade()` baja hoy), −2,7 pp a 5m, **−6,6 pp a 1m**. Quien "mejorase" `grade()`
      afinando el `interval` se comía 6,6 pp de mentira sin tocar el bucle.
- [ ] **[pendiente]** `scripts/fleet_healthcheck.py:248,314` — `Popen(["nohup","zsh",...])` sin
      `start_new_session` y plist sin `AbandonProcessGroup`. *Daño*: **el auto-curado es un NO-OP**
      y el informe canta "REVIVIDO" en falso. Creemos tener red de seguridad y no la hay.

### Los 5 vivos más peligrosos por DINERO REAL
1. `order_engine/order_engine.cpp:152,919` — **el centinela `-1.0000` del delta se usa como delta
   REAL** (`ss >> iv >> r.delta` sin validar). MEDIDO: fuera de RTH el **100%** de las filas de
   `data/opt_chain_*.txt` traen `-1.0000` (80 filas hoy en QQQ). El clamp de cordura lo aterriza en
   `fill_px*0.95` → **todo stop nativo de opción nace a −5% de la prima**: stop-out instantáneo.
   `bid`/`ask` sí validan el centinela; `delta` no. **Patrón "cero plausible" del `~/CLAUDE.md`.**
2. `order_engine/order_engine.cpp:632` — el `close` del panel se precia con `nearest_row()`, que
   **nunca exige strike igual**. La orden sale con el límite de OTRO contrato → no llena, y
   `chart_bridge` ya respondió `{"ok":true}` sin esperar al motor. **Crees que estás plano y no lo estás.**
3. `order_engine/order_engine.cpp:980-1002` — el cierre por stop watch-local es **de un solo tiro**:
   `z.close_id` se fija una vez, sin re-precio ni reintento, con un límite que puede venir de una
   cadena vieja. Y es justo el camino al que lleva el watchdog tras 3 rechazos.
4. `nvda_signal_bot.cpp:1375,1423` — `tail -n +1 -F` **sin dedupe por epoch**. Cada warm-up del
   bridge re-inyecta ~2 días de barras a los indicadores VIVOS de los 24 bots: ATR, RSI, BB, CUSUM
   y VWAP envenenados, y hablan señales que luego se operan.
5. `order_engine/order_engine.cpp:626` — `cmd close` pasa el `cqty` del panel **directo, sin
   `budget` ni `stock_budget`**: es la única ruta de orden sin ningún gate de tamaño.

### Otros vivos que contradicen doctrina escrita (muestra, no la lista entera)
- [ ] `aapl_signal_bot.cpp:1738,1839` — el gate de spread **falla ABIERTO**: sin NBBO,
      `sp = 0` y pasa todo. La orden #5 dice que un spread ancho NO es señalable.
- [ ] `aapl_signal_bot.cpp:788,835` — `V6_PRIOR[]` literal y `return prior` sin tabla: **las
      probabilidades habladas son inventadas** en los tickers sin calibración.
- [ ] `scripts/signal_conditioning.py:267` — busca `enable[f"{source}|{symbol}"]` con
      `source="order_engine"/"ticket"`, cuando las claves reales son `bollinger|AAPL`… →
      **el condicionamiento NUNCA aplica justo donde se ordena.**
- [ ] `order_engine/prob_profit.py:42,287` — `prob = 50 + composite*40` sobre pesos literales:
      **el mismo patrón que `direction_view`**, un score heurístico presentado como probabilidad.
- [ ] `scripts/index_breadth.py:58-62` — `pc = d.Close.iloc[-1]` es HOY, comparado contra `now`:
      MEDIDO en `data/breadth.json` de hoy, **gap +0.00 en TODOS los componentes** → el
      ENGRANAJE QQQ/SPY está mudo.
- [ ] `scripts/deploy_signals_to_data.sh:49` — `pkill -f '_signal_bot$'` **sin guard de horario**:
      mataría 24 bots + relay + BD con el mercado abierto. *(Relevante para la casilla de DEPLOY.)*
- [ ] `scripts/opt_whale_watch.py:41` — `in_session()` solo mira lunes-viernes: **cero calendario
      de feriados en todo el repo.**
- [ ] `fleet_notify.h:54` — `write(fd, line, (size_t)n)` con el `n` de `snprintf`: un mensaje largo
      = **lectura fuera de buffer** y línea corrupta.
- [ ] `scripts/ibkr_bar_bridge.py:147` — `open(...,"w")` 4×/s **sin tmp+rename**: el lector puede
      ver el fichero VACÍO. (La regla de frontera de `~/CLAUDE.md` pide escritura atómica.)
- [ ] `scripts/fleet_keepalive_start.sh:257` + `scripts/nvda_keepalive.sh:31` — dedup por `pgrep`
      contra un keepalive que hace `pkill -x`: dos arranques concurrentes = **bot asesinado cada 31 s**.

---

# 📊 RESULTADO DE LA AUDITORÍA (2026-07-25)

**Había 73 casillas `- [ ]`.** Revisadas una a una contra el código y `git log`:

| Clase | N.º | Qué significa |
|---|---:|---|
| **YA HECHAS** (nadie las tachó) | **22** | Estaban hechas y commiteadas. Marcadas `[x]` con su commit. |
| **OBSOLETAS** | **5** | La oportunidad ya no existe. Cerradas **con el motivo escrito**, no borradas. |
| **DUPLICADAS** (fusionadas) | **3** | Misma tarea contada 2 veces. Fusionadas en una, con nota. |
| **VIVAS** | **43** | Reescritas con qué es, fichero(s) y **por qué importa**. |
| **TOTAL** | **73** | |

**Casi la mitad de lo "pendiente" ya estaba hecho** (30 de 73 cerradas). La sospecha era correcta:
el fichero llevaba días midiendo trabajo que ya existía, y eso hace que lo urgente de verdad no se vea.

De esas 43 vivas, **2 se cerraron en esta misma tanda** (`pin-clock` con n=30 y la documentación
de los 4 daemons), así que quedan **41** de las originales. El fichero cuenta hoy **43** casillas
abiertas: esas 41 **+ 2 nuevas** que salieron al auditar y no estaban antes — el residuo
`com.ibtrader.scan` (plist apuntando a un binario inexistente; se separa de la casilla del exit 78
porque es OTRA raíz distinta) y el centinela `-1.0000` usado como delta real en
`order_engine.cpp:772`, que venía enterrado en el montón de los 84 sin refutar.

**Cerradas de verdad HOY en esta tanda** (no solo tachadas — código nuevo + tests):
- `39bd147` — cashtags de X: `$4.7B` también cuenta. 14 tests. *(era la casilla ~169)*
- `c122128` — `-Wall -Wextra` en el deploy de los 28 binarios; MEDIDO 0 warnings. *(era la ~228)*
- `bc670c6` — **VPVR**: POC de volumen en C++23 + confluencia con el POC de gamma. 22 tests. *(era la ~177)*
- `6f4fc62` — `pin-clock` corrido con n=30: **sobrevive** (rho −0,2753 vs kill 0,9), y la nota deja
  de contradecir al veredicto. *(era la ~331)*
- `7875b32` — los 4 daemons que el manual no mencionaba, documentados. *(era la ~151)*
- `0f7893c` — los 87 hallazgos del hunt **rescatados de `/tmp`** al repo antes de perderse. *(parte de la ~223)*

**Suite completa tras la tanda: `581 passed`, 0 fallos** (la referencia eran 412+; los 36 nuevos
son 14 de cashtags y 22 de VPVR).

**Las 5 obsoletas y por qué** (ninguna se borró en silencio):
1. Calibrar el flip contra gexa "MIENTRAS SIGA VIVA" (~184) — **gexa.ai desapareció el 2026-07-25**.
2. "gexa SIGUE VIVA (HTTP 200): calibrar nuestro flip" (~193) — ídem, y además duplicada.
3. "Revisar plan Polygon" (~158) — contestado hoy con la key real y grabado en `~/CLAUDE.md`.
4. Fichas CLSK/INTC del 7/22 (~168) — la fecha pasó hace 3 días.
5. "gexa es hoy CASI REDUNDANTE" (~347) — la decisión la tomaron los hechos: gexa murió.

**Las 5 duplicadas fusionadas**: exit 78 de launchd (~149 + ~167) · ampliar strikes del cache
(~180 + ~184) · deploy de los 28 binarios (~230 + ~236) · cablear `book_quality` en `direction_view`
(~292, ya `[x]` en ~335) · centralizar señales a `/data` (~191, ya hecho en fases 1-2).

---

## 🎯 LAS 5 VIVAS MÁS IMPORTANTES, por DAÑO si no se hacen

1. 🥇 **Nadie consume la calibración de barrera.** `data/calibration_barrier.json` y
   `null_control.json` están llenos y frescos, y `direction_view.py` **no los lee** (0 hits, medido).
   La prob que canta la flota sale de `prob = 50 + |score|*40`. **Daño**: se pagó una ola entera
   para medir que 0 de 131 celdas baten al azar, y seguimos publicando un número inventado a un
   humano que opera con >$30.000. Es medición tirada a la basura y, peor, confianza mal puesta.

2. 🥈 **El DEPLOY no se ha hecho: la flota corre binarios viejos.** Los tres bugs críticos de
   dinero (auto-cancelación, side perdido → corto duplicado, stop duplicado) están arreglados en el
   código y **no en lo que se ejecuta**. **Daño**: directo y en dólares, a la primera orden real.
   *(Lo decide Yunior; hoy la flota está fuera de ventana a propósito.)*

3. 🥉 **63 de los 87 hallazgos del hunt siguen vivos, 4 de ellos critical.** El fichero ya está
   rescatado (`0f7893c`) y los 87 clasificados (`63 vivos · 24 arreglados`, método validado con 4
   controles). **Daño**: el peor es del patrón prohibido — el centinela `-1.0000` usado como delta
   real (`order_engine.cpp:152,919`) hace que **todo stop nativo de opción nazca a −5% de la
   prima**, y MEDIDO fuera de RTH el 100% de las filas de cadena traen ese centinela. Y tres de
   los critical atacan la base numérica: el backtest sin costes ni stop (WR 44%→29,6%), las 95
   celdas de ruido aplicadas como VETO en vivo, y el healthcheck cuyo auto-curado es un NO-OP que
   canta "REVIVIDO" en falso. Siguen **sin refutar**: verificar antes de tocar.

4. **Los 5 `.plist` de archivadores sin cargar bloquean 3 features y el reloj no corre.**
   `book_pctile` (20 sesiones), absorción (20), condicionar sobre gamma (40) — hoy van por 1.
   **Daño**: cada día que pasa sin cargarlos es un día que NO se acumula. Mientras tanto el gate de
   libro se queda en su suelo (0.35) y frena la gamma de todos los símbolos, sanos incluidos.

5. **Los capitanes pueden llevar semanas decidiendo con la cinta vacía.** El fix de prioridad
   QQQ→SPY→SMH está commiteado (`c6e1513`), pero MEDIDO hoy `whale_qqq.txt` y `whale_spy.txt`
   siguen a **0 bytes** y 9 de 14 están vacíos. **Daño**: la **regla 12** (el capitán prevalece y
   anula la señal del nombre) es una de las reglas más fuertes de la casa y se alimenta de ahí.
   Verificarlo cuesta un `ls -la` en la primera sesión viva.

> **Honestidad de esta auditoría**: todo lo marcado MEDIDO se comprobó hoy con una orden concreta
> (`git log`, `grep`, `launchctl print`, `sqlite3`, `ls`). Lo que no pude observar —porque la flota
> está parada un sábado— queda dicho como **sin observar**, no como hecho. Dos afirmaciones del
> fichero anterior resultaron FALSAS al medirlas: el exit 78 (hoy `last exit code = 0`) y el regen
> de bollinger ("63/501" cuando en realidad cubre las 501 fechas).
