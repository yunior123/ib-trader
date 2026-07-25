# Auditoría de TODOS.md — 2026-07-24 (solo lectura, contra el código real)

45 items `- [ ]` auditados. La sección "2026-07-24 EOD — CACERÍA DE BUGS" se dio por buena
(verificada a mano por Yunior); aquí se auditan las anteriores + los pendientes del hunt.

Leyenda: **VIVO** = el defecto/falta existe hoy · **ARREGLADO** = tachar la casilla ·
**VAGO** = sin evidencia accionable · **PARCIAL** = medio hecho.

| # | Item (línea TODOS.md) | Veredicto | Evidencia file:line | Acción |
|---|---|---|---|---|
| 36 | gexa headless conecta en el run 4am | **VIVO — RESPONDIDO: NO conecta** | `data/gexa_snapshot.json` mtime 07-22 10:44 (2 días rancio); `scripts/dailyplans_run.sh:22` solo comprueba `-s` y `^{}$`, **no frescura** → nunca avisa | Añadir guarda de mtime al verify del shell (el generador sí la tiene: `scripts/daily_fleet_plans.py:348`, 12 h) |
| 37 | Raíz de `com.ibtrader.fleet` exit=78 | **VIVO — RAÍZ HALLADA** | `fleet_autostart.err`: `/bin/zsh: can't open input file: .../scripts/fleet_keepalive_start.sh` con el fichero **existiendo** (`-rwxr-xr-x`) → TCC deniega a `/bin/zsh` bajo launchd leer `~/Documents` (`drwx------@`) | Es el item 78 (Full Disk Access). Alternativa sin FDA: mover los scripts fuera de `~/Documents` o `zsh -c "$(</ruta)"` no sirve — hay que dar FDA |
| 38 | Primera cacería real jaula-liberación | VAGO | `scripts/posthours_cage.py` + `tests/test_posthours_cage.py` existen; es tarea operativa, no defecto | Dejar; no es bug |
| 39 | Documentar force/cage/healthcheck/breadth en DAILY-SYSTEM.md | **VIVO** | `docs/DAILY-SYSTEM.md`: **0** menciones de `force_meter`/`posthours_cage`/`fleet_healthcheck`/`index_breadth` | Documentar los 4 |
| 43 | `opt_tick_watch` event-driven | **VIVO (no construido)** | no existe `scripts/opt_tick_watch*` | Feature pendiente |
| 44 | Fuerza/agotamiento por-tick en bots C++ | **VIVO (no construido)** | `qqq_signal_bot.cpp`: 0 refs a force/agotamiento | Feature pendiente |
| 45 | Calendario macro (CPI/FOMC/NFP) al PDF | **VIVO (no construido)** | `scripts/daily_fleet_plans.py`: 0 hits CPI/FOMC/NFP | Feature pendiente |
| 46 | Revisar plan Polygon | VAGO | `scripts/polygon_dl.py` existe, `POLYGON_KEY` en `feeds.env` | Reformular con criterio de decisión o cerrar |
| 54 | whale: filtrar strikes sin security definition (Error 200) | **ARREGLADO** | `scripts/opt_whale_watch.py:88-89` (`qcache`/`badk`), `:121-128` blacklist solo con respuesta definitiva, `:114` tope 12 strikes | **Tachar.** Nota: `:166` `badk.clear()` reintenta, pero guardado tras 2 scans en cero |
| 55 | launchd exit 78 en fleet/scan/screener/fastscan/rescan/screener6am | **VIVO — DOS RAÍCES DISTINTAS** | (a) **TCC**: `fleet_autostart.err`, `screener/autostart.err`, `screener/rescan_agent.err`, `screener/scan_6am.err` → todos `zsh: can't open input file` sobre ficheros que existen. (b) **`com.ibtrader.scan`: el binario NO EXISTE** — `~/Library/LaunchAgents/com.ibtrader.scan.plist` apunta a `.../ib-trader/scan_server` y `ls scan_server` = *No such file* (por eso `scan_server.err` está vacío). (c) `fastscan` usa `zsh -c` (no abre fichero) pero muere por TWS caído: `screener/fastscan.log` `ConnectionRefused 7496` | (a) FDA a `/bin/zsh` (item 78). (b) **compilar/restaurar `scan_server` o descargar el plist** — hoy launchd reintenta un binario inexistente. (c) aparte |
| 55b | healthcheck exit 1 | **VIVO** | `healthcheck_err.log`: `PermissionError [Errno 1] Operation not permitted: '~/Desktop/planes-2026-07-22'` en `scripts/fleet_healthcheck.py:122` (`os.listdir` sin try) | Envolver en try/except **y** apuntar a `data/` (misma raíz TCC) |
| 56 | Fichas CLSK/INTC 7/22 vs gaps | OBSOLETO | `data/fichas_2026-07-22.txt` existe; la fecha pasó hace 2 días | Borrar el item |
| 57 | x_post_common: MAX 1 cashtag | **ARREGLADO** | `scripts/x_post_common.py:194-202` `sanitize_cashtags`, aplicado en `:210`. La regex `\$([A-Za-z]{1,5}\b)` **no** toca `$4.7B` (empieza por dígito ⇒ X no lo cuenta como cashtag) | **Tachar.** Cosmético: `:202` arrastra un `... if False else ...` muerto |
| 57b | *(docs/ERRORES.md:23)* `post_text` da 401 pero OAuth1 directo da 201 | **VIVO — RAÍZ HALLADA** | `scripts/xpost.py:56` llama `xc.post_text(text, media_path=image)` **sin `tag`, sin `log` y sin `auth`** → firma es `post_text(text, tag, log, dry_run=False, auth=None, ...)`; con `auth=None` el `requests.post(..., auth=None)` de `x_post_common.py:232` sale **sin firmar ⇒ 401**. El `except` de `xpost.py:60` se traga el TypeError | `make_auth()` (`x_post_common.py:115-118`) está **bien** y las 4 claves están en `x.env`. Arreglar el **caller** `xpost.py`, no `auth()` |
| 58 | whale v2: alarma por PREMIUM NETO en dólares | **VIVO** | `scripts/opt_whale_watch.py`: 0 refs a `premium`/`notional`/`mid`; la única métrica es `pc = vp/max(vc,1)` en `:157` y el histórico `:159-162` guarda solo `vc/vp/pc/spot` | Construir. El tide -53 M sigue mudo |
| 62 | VIX: falta suscripción CBOE Global Indexes | **VIVO (externo, no es código)** | `scripts/chart_bridge.py:1903-1906` con degradación limpia; chip en `charts/live.html:295` | Suscribir (~$1.50/mes). Sin impacto en cálculos |
| 63 | Banda de fragilidad / true-flip por vanna | **VIVO (no construido)** | 0 hits en `charts/live.html` | Bloqueado por #62 |
| 64 | Migration-trail del flip | **VIVO (no construido)** | 0 hits `migration` en `charts/live.html` | Buildeable ya |
| 65 | Volume Profile (VPVR) | **VIVO (no construido)** | 0 hits `VPVR` en `charts/live.html` | Buildeable ya |
| 66 | Pin-risk score | **VIVO (no construido)** | 0 hits `pin_risk` en `charts/live.html` | Buildeable ya |
| 67 | Capa CHARM en el toggle | **VIVO** | `scripts/gex_core.py` tiene `bs_charm` (2 hits); `charts/live.html:1342` solo togglea **GEX↔VEX** — no hay CHARM | Añadir la capa UI (backend ya está) |
| 68 | Ampliar strikes de `opt_chain_cache.py` | **VIVO** | `scripts/opt_chain_cache.py:49` `PCT_BAND = 0.06`, `:54` `MAX_STRIKES = 20` con comentario "2 exps × 20 × 2 = **80 líneas TWS max**", `:164` pide **las 80 de golpe** | **OJO**: subir a ±15 %/40 revienta el tope de 100 líneas (error 10197). Fix correcto: **trocear `cons` en lotes ≤80** en `:164` con cancel entre lotes, y luego ampliar band/max |
| 72 | Idem urgente + validar contra gexa mientras viva | **VIVO** (duplicado de 68) | idem | Fusionar con #68 |
| 73 | Chart: precios incorrectos AFTER CLOSE (autoscale) | **VIVO** | `charts/live.html`: **0** hits de `autoscaleInfoProvider`; hay 4 sitios que cuelgan líneas de la serie de velas — `:531` (muros), `:1126` (stops), `:1139` (zonas), `:1228` (alarmas) — y en lightweight-charts las price lines **entran** en el autoscale | Implementar `autoscaleInfoProvider` sobre la serie de velas, o esconder líneas lejanas tras el cierre |
| 78 | FDA a /bin/zsh, python3, venv-chart, binarios C++ | **VIVO — es la raíz de #37 y #55(a)** | ver #37/#55 | **Máxima prioridad no-código.** Sin esto 5 launchd jobs siguen muertos |
| 79 | Centralizar ruta de señales a `data/trading-signals/` | **ARREGLADO en fuente** | los 5 hits restantes de `Desktop/trading-signals` son **docstrings/comentarios**: `signals_db.py:5`, `eod_signal_validation.py:6`, `options_enrich.py:9`, `x_signal_poster.py:6`, `fleet_notify.h:33` | **Tachar** (queda solo el deploy = #124). Limpiar los comentarios de paso |
| 81 | gexa viva: calibrar flip | **VIVO** (duplicado de 68/72) | idem | Fusionar |
| 111 | ~84 hallazgos sin verificar | VAGO (meta) | `tasks/w7i2a7lhe.output` | Mantener |
| 113 | Auditoría de TODOS.md | **HECHO** | este documento | Tachar |
| 114 | `bench.cpp` mide al optimizador | **VIVO** | `tests/cpp/bench.cpp:114-118` el `bench()` llama `f()` sin sumidero; **benchmarks 1,2,3,4,6 no tienen `volatile`** (solo 5,7,8 en `:184,207,216,247`). Peor: `:5-8` **no incluye NADA del proyecto** — testea copias privadas, el mismo pecado que `math_test` | Añadir `DoNotOptimize` + `#include` de `engines/` |
| 116 | Bots con `c++20 -O2` sin arch nativa | **ARREGLADO en el script** | `scripts/deploy_signals_to_data.sh:11-12` `STD="-std=c++2c"`, `ARCH="-mcpu=native"`, compilación en `:19` con `-O3 $ARCH` | **Tachar el "cambio de 1 línea"**; lo que falta es recompilar (#124) |
| 118 | Despliegue pendiente del motor | **VIVO** | ver #124 | Fusionar con #124 |
| 124 | DEPLOY AL CIERRE `deploy_signals_to_data.sh` | **VIVO — NO desplegado** | `.cpp` = **07-24 20:55** (qqq/spy/nvda/mu/smh), binarios = **07-20 10:05** (spy 07-20 18:27); `flow_pulse.cpp` 07-24 10:38 vs binario `flow_pulse` 07-23 03:07; `fleet_notify.h` 07-24 10:39 | **Los 3 fixes críticos (auto-cancelación, side perdido, stop duplicado) NO están en producción.** Correr con mercado cerrado |
| 142 | Sin tope de exposición AGREGADA por cuenta | **VIVO** | `order_engine/order_engine.cpp:294-296, 747, 802` — solo topes por zona/orden, sin acumulador ni net-liq | Construir cap global |
| 143 | Sin reconciliación contra `reqPositions` | **VIVO** | `order_engine/tws_adapter.h:136-150` sin `reqPositions`/`position()`; la única "verdad" es `reqAllOpenOrders()` (`tws_adapter.cpp:161`), que ve **órdenes**, no posiciones | Alta prioridad: habilita #145 |
| 144 | Presupuesto de opciones por contrato, no por zona | **ARREGLADO** | `order_engine/order_engine.cpp:801-812` calcula `qty * g.premium` y vetea contra `cfg.max_order` (default = budget, `:345`) | **Tachar** |
| 145 | `close` confía en `cqty` sin comparar posición real | **VIVO** | `order_engine/order_engine.cpp:598,609,626` — `cqty` viene del JSON del panel (`charts/live.html:889`, snapshot posiblemente rancio) y va tal cual a `place_limit`; no hay contra qué contrastar (ver #143) | Riesgo de flip a corto en TFSA |
| 146 | `close` no cancela el stop nativo | **VIVO** | `order_engine/order_engine.cpp:611-627` — coloca la opuesta con ref `"OE:CLOSE"`, nunca busca la zona ni cancela `z.stop_id`, ni se registra en `oid2zone` → STP GTC **huérfano** | Grave: el huérfano al dispararse abre un corto |
| 147 | STOP rechazado no se reporta como fallo de protección | **VIVO (mitigado)** | `order_engine/order_engine.cpp:547-548` — `REJECTED` solo se atiende si `ev.order_id == z.entry_id`; el watchdog `:892-916` tarda ~30 s × 3 antes de degradar a watch-local | Reportar en voz alta al instante |
| 148 | Reconnect re-arma stops sin verificar `reconcile` | **VIVO** | `order_engine/order_engine.cpp:481-505` bombea 80 ciclos pero no comprueba `tws.reconciled()` (el arranque sí, en `:424`) → si no llegó `openOrderEnd`, `adopted_stop_id()` = -1 y `stop_armed=false` → **segundo STP** | Reintroduce el bug ya arreglado del arranque |
| 149 | Allowlist live usa `find()` (substring) | **VIVO** | `order_engine/order_engine.cpp:401` `tws.account().find(expected) == npos` sobre la lista CSV completa (`tws_adapter.cpp:195`) | Split por `,` + igualdad exacta |
| 150 | Clamp asimétrico del stop de opción | **VIVO** | `order_engine/order_engine.cpp:864-870` — la rama long (`close_side=='S'`) tiene min y max; la rama corta (`:868`) solo `max(opt_stop, fill*1.05)`, sin cota superior | Simetrizar |
| 153 | Live market data / Finnhub | **PARCIAL** | La mitad **live** ya está resuelta: SIP premium activo (ver "MENTIRAS EN LA DOC" abajo). `scripts/chart_bridge.py`: **0** refs a Finnhub; sigue sin cablear para paper | Reescribir el item: solo falta paper/fallback |
| 154 | Selector de timeframe estilo TradingView | **ARREGLADO** | `charts/live.html:254` "fila 1: símbolo + selector de intervalo (TradingView-like)" | **Tachar** |
| 155 | Chip de zona dice "Ccall" para acciones | **VIVO** | `charts/live.html:1116` `zoneLabel()` emite siempre `"call"`/`"put"` sin mirar `secType` | Label instrument-aware |
| 156 | Skills QA + suite de tests automatizada | **PARCIAL** | `tests/`: 6 tests Python + `tests/cpp/` (pero ver #114) | Reformular a lo que falta |
| 157 | Optimizar latencia de ráfaga | VAGO | sin benchmark reproducible en el repo | Añadir medición o cerrar |

## Hallazgos NUEVOS (no estaban en TODOS.md)

| # | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| N1 | **Las corridas 08:30 REFRESH y 09:12 APERTURA de `dailyplans` fallan TODOS LOS DÍAS** | `dailyplans.log:498, 765, 1025` → `daily_fleet_plans.py: error: unrecognized arguments: --tag REFRESH-8AM`. **Raíz**: `scripts/dailyplans_run.sh:10-12` hace `ARGS="--tag REFRESH-8AM"` y `:15` lo expande sin comillas — **zsh NO hace word-splitting** en expansión de parámetros, así que llega **un solo argv** `"--tag REFRESH-8AM"`. `--tag` sí existe (`daily_fleet_plans.py:656`) | **ALTA** — 2 de las 3 corridas diarias llevan ≥3 días muertas. Fix: `ARGS=(--tag REFRESH-8AM)` + `"${ARGS[@]}"`, o `${=ARGS}` |
| N2 | `com.ibtrader.scan` apunta a un binario inexistente | `com.ibtrader.scan.plist` → `.../ib-trader/scan_server`; `ls scan_server` = No such file. `KeepAlive=true` ⇒ launchd reintenta en bucle | MEDIA |

## MENTIRAS EN LA DOC (tachar)

- `AGENTS.md:372` — "Error 10089 SIGUE para la API (sin suscripción SIP)". **FALSO**: `bridge_ibkr_fleet.log` registra "SIP bars+NBBO suscritos (premium activo)" en los ~30 símbolos.
- `docs/OPERATIONS.md:63` — repite la misma mentira.
- `TODOS.md:35` — "Tests C++23: 25/25 pass + benchmark (Bollinger 9.46 ns/op)". Ya marcado como humo en la sección EOD; confirmado también para `bench.cpp` (#114).

---

## RESUMEN

**45 items abiertos auditados: 31 VIVOS · 6 YA-ARREGLADOS (tachar) · 3 PARCIALES · 5 VAGOS/OBSOLETOS.**

Tachar ya (la casilla miente): **#54** (blacklist de strikes ya existe), **#57** (sanitizador de
cashtags ya aplicado), **#79** (fuente ya en `/data`, solo quedan comentarios), **#116** (el script
ya usa `c++2c -O3 -mcpu=native`), **#144** (el engine ya multiplica por `qty`), **#154** (el selector
de intervalo existe). Fusionar los duplicados **#68 = #72 = #81** y **#118 = #124**. Borrar **#56** (fecha pasada).

### Los 5 VIVOS más graves

1. **#124/#118 — DEPLOY NO HECHO.** Fuentes de las 20:55 de hoy, binarios del **07-20**. Los tres
   fixes críticos de la cacería (auto-cancelación, side perdido, stop duplicado) **no corren en
   producción**. Es el único item que ya está escrito, probado y sin desplegar.
2. **#78 → #37/#55 — 6 launchd jobs muertos, raíz identificada.** TCC deniega a `/bin/zsh` bajo
   launchd leer `~/Documents` ⇒ `can't open input file` ⇒ exit 78 en fleet/screener/rescan/screener6am.
   Causa aparte para `scan` (binario `scan_server` inexistente) y para `healthcheck` (exit 1 por
   `os.listdir` de `~/Desktop` sin try, `fleet_healthcheck.py:122`).
3. **N1 (nuevo) — 2 de las 3 corridas diarias llevan ≥3 días fallando** por word-splitting de zsh
   en `dailyplans_run.sh:15`. Silencioso: el log lo dice, nadie lo lee.
4. **order_engine #143 + #145 + #146 — dinero real.** Sin `reqPositions` no hay verdad remota; el
   `close` del panel confía en un `cqty` posiblemente rancio (sobre-venta ⇒ **corto en TFSA**) y deja
   el STP GTC **huérfano**, que al dispararse abre otro corto. Los tres son el mismo agujero.
5. **#36 + #58 — el sistema no sabe que está ciego.** gexa lleva rancio desde el 07-22 y el verify
   del shell no mira frescura; y las ballenas caras siguen mudas porque solo se mide ratio de
   volumen, nunca premium neto en dólares (`opt_whale_watch.py:157`).

**Bonus barato:** `#68` NO es "subir el band a ±15 %" — es **trocear en lotes ≤80 líneas**
(`opt_chain_cache.py:164` pide 80 de golpe; a 160 revienta con 10197). Y el 401 de X
(`ERRORES.md:23`) **no es `auth()`**: es `xpost.py:56` llamando `post_text` sin pasar `auth`.
