# COBERTURA DISCORD — qué llega al servidor y qué no (2026-08-04)

Auditoría del camino `productor → scripts/notify_short.py → data/notify_push.txt → scripts/discord_relay.py → Discord`.
Todo `fichero:línea` está verificado con grep/read sobre el repo; nada supuesto.

**Titular medido:**

> El **08-03 el feed completo tuvo 642 líneas y el embudo solo 215**. Contando por
> `(título)`, **469 líneas del feed no tienen gemelo en el embudo** — el **73 %** de lo
> que la flota emitió ese día **no habría llegado a Discord**.
> De **59 productores de alerta** identificados (regla de conteo: un productor = un par
> *fichero × familia de título* que emite una alerta dirigida a un humano),
> **17 llegaban** al embudo y **42 no**. De esos 42, **29 son binarios C++** (los 21 signal
> bots, `price_alarm`, `korea_watch`…) y su arreglo exige recompilar y **reiniciar la flota**,
> imposible en ventana LIVE.
> Esta sesión **enchufa 4 productores** (`korea_naver_bridge`, `provider_bridge`,
> `finnhub_ws_bridge`, la ficha `🎯 ZONA` de `chart_bridge`) → **21 llegan / 38 no**,
> **ensancha 1** (`earnings_fall_scout`, que se callaba con IBKR caído) y **añade 1 nuevo**
> de documentos (`dailyplans_run.sh` → `#planes-premarket` + `#estado-flota`).

Reproducir la medida:

```bash
./venv/bin/python -m pytest tests/test_discord_cobertura.py -q     # 29 passed
```

> **Nota de concurrencia (2026-08-04):** durante esta auditoría, otro agente cambió dos
> ficheros de los que depende este informe, y los cambios **se han incorporado, no revertido**:
> (a) `scripts/notify_short.py:22-34` ahora **corta el push bajo pytest** — medido: la suite
> había metido 52 alarmas reales `🕳 CINTA CIEGA` en el embudo de producción. Es correcto y
> `tests/test_discord_cobertura.py` lo blinda con un test propio, levantando la guarda solo
> contra `tmp_path`; (b) `scripts/discord_layout.py:103-113` añade `#opciones-contratos` y
> desvía las fichas `NO-GO` a `#senales-rechazadas`. La ficha `🎯 ZONA` que se enchufa en §4.5
> queda enrutada por esas reglas y **ninguno de sus dos veredictos cae en el fallback**
> (verificado; test `test_ficha_de_zona_enruta_segun_el_veredicto`).

---

## 1. El hueco medido: `trading-signals` vs `notify_push` (08-03)

`data/notify_push.txt` **no tiene campo de fecha**. Se atribuyó a sesión detectando los saltos
del reloj hacia atrás (4 saltos, 5 tramos) y validando cada tramo contra su fichero de señales:

| tramo (índice de línea) | sesión | líneas | coincidencias exactas `(hora,título)` |
|---|---|--:|--:|
| 138-356 | 2026-07-31 | 219 | 210 |
| 357-460 | 2026-08-02 | 104 | 37 |
| **461-675** | **2026-08-03** | **215** | **168** |
| 676-681 | 2026-08-04 | 6 | 2 |

Diferencia del **2026-08-03**, contada por título:

| líneas del feed SIN gemelo en el embudo | productor | veredicto |
|--:|---|---|
| **179** `🧲 ESTRUCTURAL pin <SYM>` | `scripts/chart_bridge.py:3754` | **NO DEBE LLEGAR** — backtest `hit 0,041` vs null `0,021`, **KILL**; 82 textos distintos en 179 líneas |
| **98** `🔒 TRUTH-LOCK INFO` | `scripts/truth_lock.py:344` | **NO DEBE LLEGAR** — 98/día de infraestructura; mudo por diseño (`:223-226`) |
| **52** `🧲 ESTRUCTURAL magnet <SYM>` | `scripts/chart_bridge.py:3754` | **NO DEBE LLEGAR** — KILL |
| **47** `🎈 BB 15m RE-ENTRADA [MUTED p<55]` | `scripts/bollinger_alarm.py:196` | **NO DEBE LLEGAR** — `MUTED` significa prob medida < 55 %; la variante *hablada* es **anti-señal** (edge −0,130) |
| **49** `🎈 BB REBOTE` / `[VETO medido]` | `scripts/bollinger_alarm.py:267` | **NO DEBE LLEGAR** — solo hablan `VOICE_CORE` (`:56`); BB_REBOTE = 48,8 % vs null 49,4 %, KILL |
| **15** `🎈 BB BAND-WALK [MUTED p<55]` | `scripts/bollinger_alarm.py:253` | **NO DEBE LLEGAR** — mismo motivo |
| **12** `<SYM> TERREMOTO ALZA/CAIDA` | `bots/<sym>_signal_bot.cpp:1539/1545` | **HUECO discutible** — edge **−0,178** (anti-señal con CI que excluye el 0). Ver §5 |
| **9** `<SYM>: BUY` / `<SYM>: SELL` | `bots/<sym>_signal_bot.cpp:495/508/916/1689/1710/1725/1808/1829` | **HUECO #1** — es literalmente "compra/vende + ticker" y **no sale del Mac**. Ver §5 |
| **2** `🌊 FLOW PULSE v4` (arranque/cierre) | `scripts/flow_pulse.cpp:491/639` | **NO DEBE LLEGAR** — latido del daemon |
| **2** `🩸 EARNINGS-FALL <SYM>` | `scripts/earnings_fall_scout.py:351` | **ARREGLADO** (§4.1) |
| **1** `🛰 FINVIZ ROTO` | `scripts/finviz_scout.cpp:373` | **HUECO** — ver §6 (regla propuesta) |

Y **42 líneas del embudo sin gemelo en el feed**: son `INTRINIO WS` (`scripts/intrinio_ws_probe.py:257`),
que empuja al embudo pero no escribe fichero de señales. Correcto: es infraestructura y
`discord_layout.RULES` ya la manda a `#estado-proveedores`.

**Conclusión del §1:** de las 469 líneas perdidas, **448 (95,5 %) NO deben llegar** — son ruido
que el backtest ya declaró KILL, o infraestructura. **El hueco de valor son las ~21 líneas/día
de los bots C++ (`BUY`/`SELL`, `TERREMOTO`) más `🛰 FINVIZ ROTO`.**

---

## 2. Tabla productor × embudo × canal × veredicto

`✅` = ya llegaba · `🆕` = enchufado en esta sesión · `❌` = no llega.

### 2.1 Python — llegan al embudo

| productor `fichero:línea` | títulos | canal Discord | estado |
|---|---|---|:-:|
| `scripts/ibkr_bar_bridge.py:339` | `🕳 CINTA CIEGA` | `#estado-proveedores` | ✅ |
| `scripts/korea_bar_bridge.py:201` | `🇰🇷 KRX BRIDGE SIN GATEWAY/CIEGO/CAIDO`, `🇰🇷 BARRAS COREA RANCIAS` | `#estado-proveedores` | ✅ |
| `scripts/opt_whale_watch.py:209` | `🐋 ALERTA BALLENA CALLS/PUTS`, `🐋📈 …CRECE`, `🟢📈/🔴📉 FLUJO AGRESOR` (título de `scripts/uw_premium_alert.py:44`), `🕳 BALLENAS CIEGAS` | `#ballenas-flujo` / `#estado-proveedores` | ✅ |
| `scripts/fleet_consensus.py:164` | `🐘 MANADA ALCISTA/BAJISTA` | `#manada` | ✅ |
| `scripts/bollinger_alarm.py:70` | `🎈 BB REBOTE / BAND-WALK / 15m RE-ENTRADA / BOLLINGER VIGIA` | `#senales-flota` | ✅ **parcial**: solo si `sym ∈ VOICE_CORE` (`:56`) |
| `scripts/dip_alert.py:78` | `🩸 DIP REAL` | `#senales-flota` | ✅ **parcial**: `🩸 DIP VETADO` (`:280`) y `🩸 DIP VIGIA` (`:294`) van con `voice=False` → sin push. Correcto: un VETO no es una señal |
| `scripts/band_open_watch.py:38` | `🎯 APERTURA FUERA DE BANDA`, `🎯 RE-ENTRADA A BANDA` | `#senales-flota` | ✅ |
| `scripts/dram_guard_today.py:28` | `🛡 DRAM GUARD`, `🟢/🔴 MEMORIA CONFLUENCIA`, `⚡ DRAM MOVIDA` | `#sin-clasificar` ⚠ | ✅ llega, **mal enrutado** — regla propuesta en §6 |
| `scripts/position_close_reminder.py:34` | `⏰ EXPIRA HOY` | `#earnings-catalizadores` | ✅ |
| `scripts/capitulacion_qqq.py:52` | `💀 CAPITULACION QQQ` | `#criticas` | ✅ |
| `scripts/today_alarm5.py:48` | `🟢/🔴 <SYM> CALL/PUT <evento>` | `#sin-clasificar` ⚠ | ✅ llega, **mal enrutado** — §6 |
| `scripts/uw_flow_archive.py:223` | `⚠ ARCHIVO UW` | `#flujo-uw` | ✅ |
| `scripts/intrinio_ws_probe.py:257` | `INTRINIO WS` | `#estado-proveedores` | ✅ |
| `scripts/earnings_fall_scout.py:351` | `🩸 EARNINGS-FALL <SYM> ±x%` | `#earnings-catalizadores` | 🆕 §4.1 |
| `scripts/korea_naver_bridge.py:358` | `🇰🇷 KRX NAVER BRIDGE CIEGO` | `#estado-proveedores` | 🆕 §4.2 |
| `scripts/provider_bridge.py:339` | `🕳 MANADA MUDA` | `#estado-proveedores` | 🆕 §4.3 |
| `scripts/finnhub_ws_bridge.py:241` | `FINNHUB WS` | `#estado-proveedores` | 🆕 §4.4 |
| `scripts/chart_bridge.py:2306` | `🎯 ZONA <SYM>` (ficha de orden) | `#senales-flota` | 🆕 §4.5 |
| `scripts/dailyplans_run.sh:62` | PDFs de planes + salud de la flota | `#planes-premarket`, `#estado-flota` | 🆕 §4.6 |

### 2.2 Python — NO llegan

| productor `fichero:línea` | títulos | canal que le tocaría | veredicto |
|---|---|---|---|
| `scripts/chart_bridge.py:3754` | `🧲 ESTRUCTURAL pin/magnet/flip` | `#gamma-niveles` | **NO DEBE LLEGAR** — 231/día, KILL. Blindado por `tests/test_discord_cobertura.py::test_estructural_sigue_FUERA_del_embudo` |
| `scripts/chart_bridge.py:3587/3614/3630/3642/3512/2272/2391/1045` | `broadcast_levels/narr/signals/tick/engine/direction/watchlist` | — | **NO DEBE LLEGAR** — es el *estado* del cockpit (imanes, flip, muros, régimen, marcadores), refrescado varias veces por segundo. Es una PANTALLA, no un evento. **Único evento accionable de ese daemon: la ficha `🎯 ZONA`, ya enchufada (§4.5)** |
| `scripts/truth_lock.py:344` | `🔒 TRUTH-LOCK INFO` | `#estado-proveedores` | **HUECO deliberado** — 98/día. Regla propuesta en §6 por si Yunior lo quiere; **no enchufado** |
| `scripts/options_enrich.py:254` | `<SYM>: OPT | …` | — | **NO DEBE LLEGAR** — enriquece señales ya publicadas; duplicaría cada alerta |
| `scripts/intrinio_ws_autostart.py:103` | voz "WebSocket de Intrinio ARRIBA/sin datos" | `#estado-proveedores` | **NO ENCHUFADO** — `intrinio_ws_probe.py` ya publica 42 líneas/día del mismo socket. Enchufarlo duplica |
| `scripts/fleet_healthcheck.py:748` | `🩺 ib-trader healthcheck` | `#estado-flota` | **HUECO** — lote; mejor por `discord_post.py --channel estado-flota` que por el embudo. §6 |
| `scripts/finviz_auth_check.py:146` | voz "Token de Finviz caducado" | `#finviz-screeners` | **HUECO** — token caducado = 3 screeners muertos y nadie se entera fuera del Mac |
| `screener/state.py:56` (`notify_mac`; llaman `scanner.py:209`, `revet_watchlist.py:54`, `bargain_hunt.py:113`, `bargain_scan.py:168`) | `Top gainers (TA BUY)`, `BARGAIN HUNT (TA BUY)`, `TA BUY nuevo (finviz)` | `#finviz-screeners` | **HUECO** — 23 líneas en 12 sesiones. Necesita regla nueva (§6): sin ella cae en `#sin-clasificar` |
| `screener/alert_bot.py:39` | `BUY-CONSIDER` | `#senales-flota` | **HUECO, el peor**: banner propio que **ni siquiera escribe `data/trading-signals/`**, así que no lo ve ningún relé ni ningún backtest. Necesita regla nueva |
| `scripts/opt_sentinel.py:58` | `OPCIONES URGENTE` | — | **NO DEBE LLEGAR** — retirado en duro (`:43-47`, `sys.exit(78)` desde el 2026-07-17) |
| `scripts/uw_flow_tape.py` | ninguno (cabecera `:5` "SEÑAL-SOLAMENTE, cero voz") | — | **NO DEBE LLEGAR** como está. ⚠ **`#flujo-uw` no tiene productor de flujo**: solo recibe `⚠ ARCHIVO UW` (fallos de archivo). El canal existe casi vacío |
| `scripts/overnight_feed.py`, `chart_levels.py`, `gex_snapshot.py`, `gex_gate.py`, `direction_view.py`, `signal_conditioning.py` | ninguno | — | **NO DEBE LLEGAR** — productores de dato / librerías |
| `scripts/x_signal_poster.py`, `scalper/sim_feed.py`, `scalper/backtest_whale_scalp.py` | — | — | **NO DEBE LLEGAR** — consumidores del feed, no productores |

### 2.3 C++ — llegan al embudo (solo 3 binarios)

| productor `fichero:línea` | mecanismo | canal | estado |
|---|---|---|:-:|
| `scripts/flow_pulse.cpp:342` | spawn de `notify_short.py`, **solo si `voice==true`** | `#ballenas-flujo`, `#manada`, `#capitanes` | ✅ parcial |
| `scripts/finviz_screener_watch.cpp:289-295` | `posix_spawn` de `notify_short.py`, siempre | `#finviz-screeners` | ✅ |
| `order_engine/order_engine.cpp:233-240` | `ofstream` directo a `notify_push.txt` | `#criticas` | ✅ **solo 3 fallos de doble llave** (`:740`, `:765`, `:933`) |

Los que `flow_pulse` calla a propósito (`sing(..., voice=false)`): `🚀 SPIKE CALLS/PUTS (VETADO)`
(`:533`/`:578`), `🔄 GIRO A CALLS/PUTS` (`:617`/`:624`), `🌊 FLOW PULSE v4` (`:491`/`:639`) y los
`🔇🚀 SPIKE … (capitan opuesto)` (`:560`/`:602`). **Correcto**: son vetos y contexto, y el capitán
anulando al nombre es la regla 12 funcionando. **NO DEBEN LLEGAR.**

### 2.4 C++ — NO llegan (29 binarios) — **la causa raíz**

`bots/fleet_notify.h:45-58` (llamado en `:113`) escribe **solo** en `data/trading-signals/<fecha>.txt`.
**Nada de lo que pase por `fleet_notify_urgent` sale del Mac**: ni ntfy, ni email, ni Discord.

| productor `fichero:línea` | títulos | canal que le tocaría | veredicto |
|---|---|---|---|
| **21 × `bots/<sym>_signal_bot.cpp:495, 508, 916, 1689, 1710, 1725, 1808, 1829`** | `<SYM>: BUY`, `<SYM>: SELL`, `<SYM>: BUY (STOP)`, `<SYM>: SELL (STOP)` | `#senales-flota` (y `#criticas` los `(STOP)`) | **HUECO #1** — 48 líneas en 12 sesiones (**4/sesión**). Es exactamente lo que Yunior pide en Discord y hoy **muere en el banner del Mac** |
| `bots/<sym>_signal_bot.cpp:1539/1545` | `<SYM> TERREMOTO ALZA/CAIDA` | `#criticas` (ya casa por `TERREMOTO`) | **HUECO discutible** — 168 en 12 sesiones, edge **−0,178** medido. Recomendación: **enchufar solo BUY/SELL, no TERREMOTO** |
| `bots/<sym>_signal_bot.cpp:267-268` | `WARMUP <título>` | — | **NO DEBE LLEGAR** — 1.759 líneas en 12 sesiones; es el bot recalentando estado al arrancar, no una señal |
| `bots/<sym>_signal_bot.cpp:1581/1584/1602/1607` | `<SYM> tendencia/breakout/breakdown` | — | **NO DEBE LLEGAR** — ya son `notify(..., false)` = solo log |
| `scripts/price_alarm.cpp:260/263` | `<SYM> ALARMA PRECIO` | `#criticas` | **HUECO #2** — 21 en 12 sesiones. Es el **PRINT** de la doctrina "print o nada": el nivel que se imprimió. `bin/price_alarm` está **vivo ahora mismo** y su alarma no sale del Mac. Necesita regla nueva (§6) |
| `scripts/korea_watch.cpp:128-154` | `🟢 PRINT <x> — COMPRA KORU`, `🟡 KODEX reclaim`, `🔻 KODEX <x — bajista`, `🔻🔻 V ROTA — EWY puts`, `🔪 VETO`, `🐻/🐂 READ-THROUGH Hynix+Samsung ±2%`, `⚠️ FEED COREA CONGELADO` | `#corea-overnight` | **HUECO #3 (Corea, pregunta 4)** — Corea lidera semis ~13 h y la sesión KRX es 20:00→02:30 ET, **cuando Yunior duerme**: es justo el tramo donde Discord vale más que un banner. `🔪 VETO`, `🐻/🐂 READ-THROUGH` y `⚠️ FEED COREA CONGELADO` **no casan con ninguna regla** → §6 |
| `scripts/korea_tape.cpp:36-48` | veredicto one-shot | — | **NO DEBE LLEGAR** — herramienta de consola |
| `scripts/fleet_consensus.cpp:426/438` | `🐘 MANADA ALCISTA/BAJISTA` | `#manada` | **NO ES HUECO** — verificado: el keepalive lanza la versión **Python** (`scripts/fleet_consensus_keepalive.sh:8-9`, PID vivo confirmado). `bin/fleet_consensus` no corre |
| `scalper/whale_scalper.cpp:83` (títulos en `scalper/scalper_core.h:600/634/653/664/708/712`) | `🛑 SCALPER EXIT STUCK / FILL HUERFANO / DOBLE FILL / DOBLE VENTA / HALT`, `💰 SCALPER VERDE` | `#criticas` | **HUECO (pregunta 5)** — y además solo emite con `--banners`; el binario **aborta en LIVE** (`:376`, "Fase 4 no implementada, SIM solamente"). Prioridad baja mientras siga en SIM. Necesita regla nueva |
| `order_engine/order_engine.cpp` — ciclo de vida | `SENT` (`:1211`, `:1333`), `FILLED` (`:588-592`), fill parcial (`:598-605`), `STOP_HIT` (`:607-610`), `REJECTED` (`:612-617`), `CANCELED` (`:618-623`), **18 sitios `VETOED`**, `NAKED_STOP` (`:1406`), arm/`disarm-on-exit` (`:424-428`) | `#criticas` | **HUECO #4 (pregunta 5)** — **ningún fill, rechazo, stop ni cambio de armado notifica**. Solo notifican 3 fallos de doble llave. `discord_layout.RULES` ya tiene `\bSTOP\b|order_engine|ORDEN ENVIADA|FILL\b` → **el canal existe y está esperando al productor** |
| `scripts/x_whale_bot.cpp:906/938/965/975` | `X WHALE BOT`, `X BUDGET`, `X POSTED`, `X AUTH FAIL` | `#bot-logs` | **HUECO menor** — necesita regla |
| `scripts/finviz_scout.cpp:373/382/479-543` | `🛰 FINVIZ`, `🛰 FINVIZ ROTO` | `#finviz-screeners` | **HUECO** — casa por `FINVIZ`, solo falta el push |
| `scripts/qqq_xray.cpp:205-226/361` | `QQQ X-RAY` | `#gamma-niveles` | **HUECO menor** — necesita regla |
| `scripts/compass.cpp`, `level_react.cpp`, `momentum_calc.cpp`, `gate.cpp`, `opt_quick.cpp`, `volume_profile.cpp`, `engines/bb_engine.cpp`, `engines/combo_engine.cpp` | ninguno | — | **NO DEBE LLEGAR** — calculan, no alertan. `level_react.cpp:19` lo declara: "LA VOZ ESTA APAGADA" |

---

## 3. Por qué NO se tocó ni un `.cpp`

`bin/fleet_hours` dice **LIVE** (dom 20:00 → vie 20:00 Toronto; ahora quedan 89 h de ventana), y
el 08-04 02:53 EDT hay **21 signal bots + `bin/price_alarm` + `bin/compass` + `chart_bridge` +
`opt_whale_watch` + `korea_naver_bridge` corriendo**. El deploy canónico
`scripts/deploy_signals_to_data.sh:11-16` **aborta él solo en ventana LIVE** y sin `--force`
("no se mata la flota"), y con `--force` hace `pkill -f '_signal_bot$'` (`:87`).

Además: en macOS no se puede sobrescribir un binario en ejecución (`ETXTBSY`), y **no existe
ningún `scripts/build_*.sh` que compile los bots** — el único build de flota documentado es un
one-liner (`.claude/skills/cpp23-fleet/SKILL.md:28`) o el propio `deploy_signals_to_data.sh`,
21 TU monolíticas de ~1.873 líneas cada una, secuenciales en el Mac de 8 GB.

**Los parches C++ están escritos en §5 pero NO aplicados.** Aplicarlos y desplegarlos es una
sola orden con el mercado cerrado.

---

## 4. Lo que SÍ se enchufó (Python, aditivo, verificado)

Los 6 cambios siguen el patrón de `scripts/bollinger_alarm.py:66-70` y
`scripts/fleet_consensus.py:163-165`. Ninguno habla más alto, ninguno añade voz, ninguno
devuelve `0`/`0.5`/`{}` en un `except`. Todos entran en vigor **en el próximo relanzamiento
del keepalive** (no se reinició nada).

### 4.1 `scripts/earnings_fall_scout.py:69-84` y `:351-355` — la señal que IBKR silenciaba

La voz exigía `score ≥ 70` **y** `opciones == "OK"` (`:347`). El 08-03, con IBKR caído,
`OPCIONES s/d` puso `voice=False` y **dos caídas post-earnings con score 68 y 65 no salieron del
Mac**. Ahora `say()` acepta `push` separado de `voice` (idéntico a `bollinger_alarm.say`) y el
emisor pasa `push=True`.
Gate de ruido intacto: `SCORE_FEED=45` + un aviso por símbolo y día (`:342`) →
**3 líneas en 12 sesiones medidas**. Canal: `#earnings-catalizadores` (casa por `EARNINGS`).

### 4.2 `scripts/korea_naver_bridge.py:314-324` y `:358-360` — Corea (pregunta 4)

Este puente es **la única fuente KRX esta semana** (memoria `no-ibkr-this-week`, orden 2026-08-02)
y está corriendo ahora. Su `grita()` era **solo voz**: ni banner, ni fichero, ni embudo —
asimétrico contra `korea_bar_bridge.py:201`, que hace las cuatro cosas. Si el respaldo se cae de
madrugada con KRX abierto, nadie se entera fuera del Mac (precedente: 08-03 09:0x KST, 126
reintentos mudos con KRX cayendo −8 %).
`grita(msg, titulo=..., corto=...)` empuja al embudo **solo si se le da título**; las llamadas
antiguas siguen siendo solo voz. Gate: `if fallos == FAILS_LOUD` — **un aviso por caída, no por
sondeo**. Título `🇰🇷 KRX NAVER BRIDGE CIEGO` → `#estado-proveedores` (casa por `BRIDGE CIEGO`,
igual que el `🇰🇷 KRX BRIDGE CIEGO` del puente IBKR).

### 4.3 `scripts/provider_bridge.py:339-343` — `🕳 MANADA MUDA`

Guarda directa del precedente de `~/CLAUDE.md`: **21/26 = 80,8 % disparó voz DANGER "comprar
PUTS" cuando 21/30 = 70 % no debía**. `grita_si_manada_muda` gritaba solo por altavoz. Ahora
también al embudo, con los números **medidos** (`votan`/`universo`), nunca un plausible.
Triple guarda intacta (`operativa` / `_rth()` / throttle 1.800 s) → **máximo 1 línea cada 30 min
y solo en RTH**. Canal `#estado-proveedores`.
Verificado en vivo con `./venv-mit/bin/python` (el módulo exige `datetime.UTC`, py ≥ 3.11):
push a la 1.ª llamada, silencio a la 2.ª por throttle, silencio con `operativa=True`.

### 4.4 `scripts/finnhub_ws_bridge.py:125-136` y `:241-243` — `FINNHUB WS`

`discord_layout.RULES:1` ya contenía el patrón `FINNHUB WS` y **no había ningún productor que lo
alimentara**. Mismo patrón `titulo=` opcional. Gate: `if caidas % 5 == 0` (`:238`).

### 4.5 `scripts/chart_bridge.py:2306-2312` — `🎯 ZONA <SYM>` (pregunta 3)

La ficha de orden que dispara al cruzar una zona **dibujada a mano por Yunior** se escribía en el
fichero de señales y se emitía por websocket al cockpit: **no salía del navegador**.
Es el único evento accionable del cockpit (el resto —imanes, flip, muros, régimen, marcadores—
es estado de pantalla refrescado varias veces por segundo, no un evento).
Volumen medido: **2 disparos en 12 sesiones**, con histéresis `ZONE_REFIRE_S = 30` y guarda
`MOCK` **anterior** al push (un feed sintético no puede empujar al teléfono).
Canal (verificado con `L.classify` sobre los textos literales de `order_ticket.py:131` y
`:135-137`): la ficha **GO** → `#opciones-contratos`, la **NO-GO** → `#senales-rechazadas`
(privado, para auditar el veto). Ninguna cae en el fallback.

### 4.6 `scripts/dailyplans_run.sh:62` — los planes de las 04:00

`scripts/discord_post.py` existía completo (`--plans/--trees/--guide/--status`) y **nadie lo
llamaba** salvo `discord_bootstrap.sh --guide`: `#planes-premarket`, `#estado-flota` y los demás
canales de análisis nacían vacíos. Se añade **solo en la pasada FULL** (04:00), redirigido al log
y detrás del `x_plan_poster`. Sin webhooks configurados imprime `ROTO` y el 4AM sigue
(`dailyplans_run.sh` no tiene `set -e`).
**`--trees` NO se enchufó**: `data/trees_horizonte/` está congelado desde el 2026-07-28 y
publicaría PDFs rancios a diario.

---

## 5. Parches C++ propuestos (NO aplicados) — cerrar el hueco #1

### 5.1 Helper común, sin `fork` ni Python

`bots/fleet_notify.h`, junto a `fleet_notify_desktop_mirror` (mismo estilo `open/write/close`,
append atómico `< PIPE_BUF`, cero latencia — **no** el `shell_bg` de `flow_pulse.cpp:342`, que
paga un `fork` + arranque de intérprete en el camino de señal):

```c
// Embudo del telefono/Discord. Mismo contrato que scripts/notify_short.py y que
// order_engine.cpp:233: append-only, sello HH:MM:SS al principio de la linea.
static void fleet_notify_push(const char* title, const char* corto) {
    time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
    char line[600];
    int n = snprintf(line, sizeof line, "%02d:%02d:%02d | %s | %s\n",
                     lt.tm_hour, lt.tm_min, lt.tm_sec, title, corto);
    if (n <= 0) return;
    size_t len = (size_t)n < sizeof line ? (size_t)n : sizeof line - 1;
    int fd = open("data/notify_push.txt", O_WRONLY | O_APPEND | O_CREAT, 0600);
    if (fd >= 0) { write(fd, line, len); close(fd); }
}
```

### 5.2 Los 21 bots — solo BUY/SELL, nunca TERREMOTO ni WARMUP

En el `notify()` local de cada bot (`bots/<sym>_signal_bot.cpp:264`, mismo bloque en los 21),
tras el `fleet_notify_urgent` existente:

```c
    // Al embudo SOLO la decision de compra/venta: 4 lineas por sesion medidas.
    // TERREMOTO (edge -0,178) y WARMUP (1.759 lineas en 12 sesiones) se quedan fuera.
    if ((strstr(title, ": BUY") || strstr(title, ": SELL")) && !strstr(title, "WARMUP"))
        fleet_notify_push(title, corto);
```

Regla nueva necesaria en `discord_layout.RULES` (ver §6, regla **R1**): sin ella,
`INTC: SELL | VENDER INTC @ 87.99 …` cae en `#sin-clasificar` (verificado con `L.classify`).
Ojo al orden: `\bSTOP\b` va antes, así que `NVDA: SELL (STOP)` → `#criticas`, correcto.

### 5.3 `scripts/price_alarm.cpp:263` — el PRINT

```c
    fleet_notify_urgent(title, msg, "ProAlarm");
    fleet_notify_push(title, msg);      // <-- añadir
```

### 5.4 `scripts/korea_watch.cpp:128-154` — Corea overnight

Añadir `fleet_notify_push(t, m);` en los **cinco** veredictos operables (`:129`, `:133`, `:138`,
`:142`, `:145`) y en `⚠️ FEED COREA CONGELADO` (`:154`). Dejar fuera `case NADIE` (ya es mudo).

### 5.5 `order_engine/order_engine.cpp` — el ciclo de vida

`push_notify` ya existe (`:233`). Añadir en:

| línea | evento | título propuesto | cuerpo corto |
|---|---|---|---|
| `:1211`, `:1333` | `SENT` | `⚡ order_engine ORDEN ENVIADA` | `<SYM> <side> x<qty> @ <lim>` |
| `:588-592` | `FILLED` | `⚡ order_engine FILL` | `<SYM> llenado @ <px> x<qty>` |
| `:607-610` | `STOP_HIT` | `🚨 order_engine STOP` | `<SYM> stop @ <px>` |
| `:612-617` | `REJECTED` | `🚨 order_engine RECHAZO` | `<SYM>: <motivo>` |
| `:1406` | `NAKED_STOP` | `🚨 order_engine POSICION DESNUDA` | `<SYM> sin stop` |
| `:424-428` | `disarm-on-exit` | `⚡ order_engine DESARMADO` | `llaves retiradas al salir` |

Todos casan ya con la regla existente `\bSTOP\b|order_engine|ORDEN ENVIADA|FILL\b` →
`#criticas` + mención al rol. **Cero reglas nuevas.** Los 18 sitios `VETOED` **NO** se enchufan:
un veto por zona armada inundaría `#criticas`; su sitio es `#senales-rechazadas` y por lote.

### 5.6 Despliegue

```bash
# con el mercado CERRADO (bin/fleet_hours devuelve 1) y ps aux | grep -c "[c]lang++" == 0
zsh scripts/deploy_signals_to_data.sh
```

Recompila los 21 bots + `price_alarm` + `korea_watch` + `flow_pulse` secuencialmente (candado
`/tmp/cc.lock`), aborta si algo falla y relanza la flota. `order_engine` va aparte
(`cd order_engine && zsh build.sh`).

---

## 6. Reglas nuevas propuestas para `discord_layout.RULES`

**No se editó `scripts/discord_layout.py`.** Regex exactos, en el orden en que deben insertarse.
El orden importa: la primera que casa gana.

| id | insertar | regex | canal | severidad | por qué |
|---|---|---|---|---|---|
| **R1** | justo **antes** de la regla `🎈\|BOLLINGER…` | `r"^[A-Z0-9]{1,6}: (BUY\|SELL)\|\bCOMPRAR\b\|\bVENDER\b"` | `senales-flota` | `NORMAL` | los 21 bots (§5.2). Va después de `\bSTOP\b` para que `(STOP)` siga yendo a `#criticas` |
| **R2** | en el bloque de **críticas**, tras `\bSTOP\b…` | `r"ALARMA PRECIO"` | `criticas` | `CRITICA` | `price_alarm.cpp:260` — el PRINT de "print o nada" |
| **R3** | junto a la regla de Corea | `r"READ-?THROUGH\|KODEX\|KORU\|V ROTA\|🔪 VETO"` | `corea-overnight` | `NORMAL` | `korea_watch.cpp:141-151`; hoy `🔪 VETO` y `🐻/🐂 READ-THROUGH` caen en `#sin-clasificar` |
| **R4** | bloque de screeners | `r"TA BUY\|BUY-CONSIDER\|BARGAIN"` | `finviz-screeners` | `NORMAL` | `screener/state.py:56`, `screener/alert_bot.py:39` |
| **R5** | bloque de críticas | `r"🛑\|SCALPER"` | `criticas` | `CRITICA` | `scalper/scalper_core.h:600-712` |
| **R6** | bloque de sistema (primero) | `r"TRUTH-?LOCK"` | `estado-proveedores` | `SISTEMA` | `truth_lock.py:344`. **Solo si Yunior lo quiere**: son 98/día |
| **R7** | bloque de sistema | `r"^X (POSTED\|BUDGET\|AUTH FAIL\|WHALE BOT)\|🩺\|HEALTHCHECK"` | `bot-logs` / `estado-flota` | `SISTEMA` | `x_whale_bot.cpp:906-975`, `fleet_healthcheck.py:748` |
| **R8** | señales de flota | `r"MEMORIA CONFLUENCIA\|DRAM GUARD\|X-RAY\|RETEST_REJECT\|BOUNCE"` | `senales-flota` / `gamma-niveles` | `NORMAL` | `dram_guard_today.py:49-76`, `today_alarm5.py:123`, `qqq_xray.cpp:205` — **ya llegan hoy y caen en `#sin-clasificar`** |

**R8 es la más urgente de las 8**: son productores que **ya empujan al embudo** y cuyo destino
hoy es el canal de descarte.

---

## 7. Canales sin productor real

`discord_layout.py` promete "cada canal de alerta tiene un PRODUCTOR REAL verificado". Tras esta
auditoría, tres no lo tienen:

| canal | situación |
|---|---|
| `#flujo-uw` | solo recibe `⚠ ARCHIVO UW` (fallos del archivador, `uw_flow_archive.py:223`). `uw_flow_tape.py` es **señal-solamente, cero voz** por diseño y `uw_net_prem/darkpool/oi_delta` son descriptivos. **No hay flujo UW en vivo hacia Discord** |
| `#dark-pool` | `uw_darkpool.py` no alerta (killlist #3). Canal correctamente vacío; su topic ya lo dice |
| `#confluencia` | el título `🔗 FLUJO + BB` no aparece en 12 sesiones de `data/trading-signals/`. Verificar que el correlador esté vivo antes de contar con él |

---

## 8. Lo que este informe NO afirma

1. **Que enchufar los bots mejore el P&L.** El backtest del mismo día
   (`docs/BACKTEST-ALERTAS-FLOTA-2026-08-04.md`) no encuentra **ni una** familia que pase
   BH-FDR. Esto es cobertura de **entrega**, no de calidad.
2. **Que las 469 líneas perdidas fueran valor perdido.** Medido: **95,5 % es ruido que el
   backtest ya declaró KILL**. El problema de la casa sigue siendo exceso de alertas.
3. **Que los cambios ya estén activos.** Los 6 productores Python entran en vigor cuando el
   keepalive los relance. **No se reinició ni se mató ningún proceso.**
4. **Nada sobre latencia de Discord.** No se midió; el relé hereda las leyes del de ntfy
   (frescura 45 s, backlog 300 s, dedup 60 s, cap 1/5 s con bypass de prioridad) y
   `data/discord_webhooks.json` aún tiene **0 webhooks**, así que nada se ha publicado todavía.

**SEÑAL-SOLAMENTE.** Ningún cambio de esta sesión ordena nada al bróker.
