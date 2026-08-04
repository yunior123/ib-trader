# FORENSE DE LOGS — 2026-08-04 (martes, madrugada)

Barrido de **194 ficheros de log** (`logs/` 164, raíz 10, `screener/*.{log,err,out}` 20,
`/tmp/ibtrader.*` 17, `/tmp/w6_*.log` 6) = **48,03 MB** en el repo + **18 MB** en `/tmp`.
1.177.349 líneas normalizadas y contadas.

Contexto medido en el momento del barrido: `data/market_source.txt` = **intrinio**,
`data/ib_mode.txt` = **live** (resuelve al puerto 4001, cerrado por orden de la semana),
flota VIVA (sesión de Corea), 26 jobs launchd cargados.

Todo lleva número y `fichero:línea` verificado con `grep -n` / `stat` / `ps`.
**No se arregló código. No se rotó nada (ver §7). No se mató ni reinició nada.**

---

## 0. Resumen ejecutivo — los 5 que más duelen

| # | bug | daño | evidencia en una línea |
|---|---|---|---|
| 1 | **Las fotos de cadena 5-min dejaron de archivarse el 1-ago** | ⛔ **PIERDE DATOS SIN VUELTA ATRÁS** | `data/history/2026-07-31` = **1.715** fotos `_HHMM`; **08-01, 08-02, 08-03 = 0** |
| 2 | **La alarma de ballenas (Espada de Napoleón) lleva 2 sesiones muda… y el healthcheck la pinta VERDE** | ⛔ pierde señales + **falso VERDE** | `data/opt_flow.txt` congelado **Jul 31 16:03**; 129 relanzamientos el 08-03; healthcheck: `🟢 opt_whale: parado fuera de horario (correcto)` |
| 3 | **`force.json` lleva 14 días rancio: la FUERZA está apagada dentro de la brújula, en silencio** | ⛔ pierde señal, **sin una sola línea de log** | `data/force.json` mtime **2026-07-21 04:00**; `scripts/compass.cpp:1497` exige `ts` < 2 min; **nadie lanza `force_meter.py`** |
| 4 | **El cockpit gráfico lleva 16 h ciego reintentando IBKR cada 5 s** | ⛔ pierde visión; el error va a `/tmp`, no a `logs/` | 6 × `chart_bridge.py`, **68.662** `ConnectionRefusedError` en `/tmp/w6_*.log` (18 MB) |
| 5 | **`pytest tests/` mete alarmas DANGER REALES en el ntfy/email de Yunior** | ⛔ **crying wolf** (viola regla 3) | **52** pushes `🕳 CINTA CIEGA` en `data/notify_push.txt`, el último **hoy 02:47:05** |

Y el ruido: **21,97 MB de los 48,03 MB de `logs/` (46 %) son basura identificada**; con `/tmp/w6_*`
(18 MB, 100 % ruido) sube a **40 MB de 66 MB = 60 %**.

---

## 1. Logs por tamaño, tasa de crecimiento y veredicto

Crecimiento medido en vivo con dos `stat` separados 191 s (02:50→02:53 ET, mercado US cerrado —
en sesión estas cifras se multiplican).

| log | tamaño | líneas | crecimiento | ratio repetición | veredicto |
|---|---:|---:|---:|---:|---|
| `logs/prints_archiver.log` | **7,93 MB** | 528.813 | 0,8 MB/día | **44.068:1** (12 patrones) | 🟠 **B-11** volcado JSON completo cada 120 s, 88 % vacío |
| `logs/truth_lock.log` | **6,47 MB** | 148.093 | **1,2 MB/día** ← el que más crece | **49.364:1** (3 patrones) | 🟠 **B-12** "SUCIO" con 0/0, 142.043 veces |
| `logs/bridge_korea.log` | 4,15 MB | 49.529 | 0 (muerto 08-02) | 359:1 | ⚪ 15.025 `korea bridge CAIDO`; se rindió bien y Naver lo sustituye |
| `logs/fleet_consensus_py.log` | 2,67 MB | 17.891 | 0,6 MB/día | 235:1 | 🟡 5.488 `cobertura insuficiente` + 7.490 `NO VOTARON` de noche (§4) |
| `logs/provider_bridge.log` | 1,59 MB | 23.005 | 0,8 MB/día | 264:1 | 🟢 sano (es la fuente viva) |
| `logs/watchlist_quotes.log` | 1,46 MB | 18.940 | ~0,4 MB/día | 379:1 | 🔴 **B-6** 382 tracebacks contra 4001, relanzado cada 5 min |
| `logs/opt_whale.log` | 1,29 MB | 12.660 | 0 desde 08-03 16:00 | 234:1 | 🔴 **B-2** 1.454 refused + 285 relanzamientos (129 el 08-03) |
| `screener/watchdog.log` | 1,16 MB | 7.424 | **0 desde Jul 16** | — | ⚪ muerto (ejecutores retirados, `screener/ensure_all.sh:10`) |
| `screener/rescan.log` | 1,15 MB | 17.767 | 0 desde 08-03 | 538:1 | 🔴 **B-8** acaba en `HTTPError 401` (finviz) |
| `logs/order_engine_live.log` | 0,92 MB | 16.921 | 0 desde Jul 31 | 260:1 | ⚪ inactivo |
| `logs/levels5m.log` | 0,89 MB | 77.077 | 0,03 MB/día | **3.351:1** | 🟠 **B-11b** 1.866 de 2.353 corridas son `{"skipped":"fuera_de_sesion"}` |
| `logs/futures_feed.log` | 0,54 MB | 1.713 | 0,5 MB/día | — | 🟢 |
| `logs/relaunch_today_alarm5.log` | 0,54 MB | 4.687 | 0 desde Jul 29 | **1.562:1** | ⚪ 4.685 × `level_react` en raíz; ruta YA ARREGLADA, pero el script está huérfano (**B-14**) |
| `screener/ensure.log` | 0,61 MB | 3.760 | 0 desde 08-03 07:10 | 376:1 | ⚪ **2.784 de 3.760 (74 %) = `PORTERO AUSENTE`**; arreglado hace 43 h |
| `logs/perp_stock_fetch.log` | 0,62 MB | 15.274 | 0,1 MB/día | 347:1 | 🟡 12.100 × `N/28 symbols -> data/perp_stocks.json` + **B-16** |
| `logs/healthcheck.log` | 0,25 MB | 5.375 | — | — | 🔴 **B-7**: **88 corridas seguidas en exit 2** desde el 08-01 |
| `screener/heartbeat.log` | 0,43 MB | 13.318 | 0,04 MB/día | **6.656:1** (2 patrones) | 🟡 `heartbeat: alive, flat` cada 60 s |
| `logs/strike_heatmap.log` | 0,06 MB | 1.341 | — | **1.341:1** (1 patrón) | 🟡 línea única repetida 1.341 veces |
| **`/tmp/w6_{qqq,nvda,smh,mu,aapl,msft}.log`** | **3,0 MB c/u = 18 MB** | 34,5k–35,3k c/u | **VIVO** | — | 🔴 **B-4** 68.662 `ConnectionRefusedError`, 6 procesos, 16 h |

---

## 2. TOP 20 de líneas repetidas (normalizadas: sin horas, números ni tickers)

**El TOP 20 cubre ~72 % de TODAS las líneas de log del repo.**

| # | conteo | patrón | log | emisor `fichero:línea` |
|---:|---:|---|---|---|
| 1 | **142.231** | `<SYM> SUCIO: # materiales, # desaparecidas` | truth_lock | `scripts/truth_lock.py:517` |
| 2 | 106.607 | `},` (JSON pretty-print) | prints_archiver 95.091 · levels5m 11.422 | `scripts/equity_prints_archiver.py:383` · `scripts/levels_5min_archive.py:376` |
| 3 | 100.736 | `"rows": #` | prints_archiver | `scripts/equity_prints_archiver.py:182,201,222` → `:383` |
| 4 | 95.091 | `"<SYM>": {` | prints_archiver | `scripts/equity_prints_archiver.py:222` → `:383` |
| 5 | 54.467 | `"last_ep": #,` | prints_archiver | ídem `:222` → `:383` |
| 6 | 54.467 | `"gap": false,` | prints_archiver | ídem `:222` → `:383` |
| 7 | 54.467 | `"total_archived": #` | prints_archiver | `scripts/equity_prints_archiver.py:223` → `:383` |
| 8 | 40.624 | `"zero_byte": true` | prints_archiver | `scripts/equity_prints_archiver.py:199,201,272` → `:383` |
| 9 | **22.026** | `API connection failed: ConnectionRefusedError(61, …('127.0.0.1', 4001))` | **20 logs** (bridge_korea 15.025 · rescan 2.886 · opt_whale 1.454 · fastscan 1.347…) | librería `venv/lib/python3.9/site-packages/ib_insync/client.py:221` · `venv-chart/…/ib_async/client.py:231` |
| 10 | 22.026 | `Make sure API port on TWS/IBG is open` | mismos 20 logs | `ib_insync/client.py:225` · `ib_async/client.py:235` |
| 11 | 19.847 | `{` | levels5m 14.177 · prints_archiver 5.645 | ídem #2 |
| 12 | 15.025 | `korea bridge CAIDO: … reintento en #s (¿TWS en #?)` | bridge_korea | **emisor histórico**: hoy `scripts/korea_bar_bridge.py:508` emite otro formato; el texto exacto solo vive en `scripts/ibkr_bar_bridge.py:558` |
| 13 | 14.123 | `"<SYM>",` | levels5m | `scripts/levels_5min_archive.py:176` → `:376` |
| 14 | 14.079 | `}` | prints_archiver 11.290 · levels5m 2.755 | ídem #2 |
| 15 | 13.120 | `HH:MM:SS heartbeat: alive, flat` | screener/heartbeat | `screener/heartbeat.sh:25` |
| 16 | 12.100 | `#/# symbols -> data/perp_stocks.json` | perp_stock_fetch | `scripts/perp_stock_fetch.py:140` |
| 17 | 11.824 | `"sym": "<SYM>",` | levels5m | `scripts/levels_5min_archive.py:157` → `:376` |
| 18 | 11.824 | `"age_s": #` | levels5m | ídem `:157` → `:376` |
| 19 | 8.654 | `[tws] reqPositions — pidiendo posiciones reales (#/#)` | order_engine_live | `order_engine/tws_adapter.cpp:219` |
| 20 | 7.930 | `[tws] positionEnd — # posicion(es) conocida(s)` | order_engine_live | `order_engine/tws_adapter.cpp:362` |

**21-30**: 6.637 `[provider_bridge] … +# barras` (`scripts/provider_bridge.py:145`, señal real) ·
5.857 `chequeados # syms, # reescrituras materiales` (`scripts/truth_lock.py:514`) ·
**4.685** `<SYM>: level_react fallo (No such file …/ib-trader/level_react)` (`scripts/today_alarm5.py:67`) ·
4.261 `[ibkr_data] <SYM> no disponible … SIN datos (delayed prohibido)` (`screener/ibkr_data.py:36-37`) ·
3.901 `Error 300, Can't find EId with tickerId` (ruido normal de `reqMktData`) ·
4.237 `ciclo …: # filas / # tickers` (`scripts/finviz_scout.cpp:536`) ·
~4.000 × 13 bots `<x>_signal_bot (C++): bridge <SYM> 1m real iniciado` (`bots/*_signal_bot.cpp:1380`).

⚠ Ese último **NO es un bucle vivo**: 768 (13-jul) + 2.273 (14-jul) + 929 (15-jul), era la era TCC de
`~/Documents` (`logs/nok_signals.log` lo prueba: `sh: bridge_nok.log: Operation not permitted`).
Desde el 16-jul van a 1-4/día. **Cerrado.**

---

## 3. Bugs REALES, ordenados por daño

### ⛔ B-1 — Las fotos de cadena de 5 minutos dejaron de archivarse el 1-ago: **historia intradía perdida para siempre**
**Daño: PIERDE DATOS DE FORMA IRRECUPERABLE. Es el único cuyo coste crece cada hora.**

Medido (`ls data/history/<fecha>/ | grep -cE 'opt_chain_.*_[0-9]{4}\.txt'`):

| fecha | fotos `_HHMM` | ficheros totales |
|---|---:|---:|
| 2026-07-29 | **1.632** | 1.774 |
| 2026-07-30 | **1.761** | 2.188 |
| 2026-07-31 | **1.715** | 2.242 |
| 2026-08-01 | **0** | 0 |
| 2026-08-02 | **0** | 141 |
| 2026-08-03 | **0** | 3.049 (todo `chain_full_*.json` de Polygon, no fotos 5-min) |

El productor es `scripts/opt_chain_cache.py:303-306`, que escribe
`data/history/<fecha>/opt_chain_<sym>_HHMM.txt` — **es IBKR y está apagado**. Su sustituto
`scripts/provider_bridge.py` escribe solo la foto actual `opt_chain_<sym>.txt` y **no tiene ni una
línea de escritura a `data/history`** (`grep -nE 'history|hdir|%H%M' scripts/provider_bridge.py` → 0).
Peor: `scripts/fleet_keepalive_start.sh:218` hace `pkill -f "scripts/opt_chain_cache.py"` y `:290`
solo lo arranca `if [[ "$MARKET_SOURCE" == "ibkr" ]]`, así que con `intrinio` el archivador se mata
activamente y **nadie ocupa su puesto**.

Consecuencia aguas abajo (**B-9**): `scripts/trace_cube.py:103` levanta
`ValueError: SPY 2026-08-03: cero fotos utilizables en data/history (leidas 0, descartadas 0)` —
**252 fallos**, 84 tracebacks (42 SPY + 42 QQQ). El eje de tiempo del panel TRACE (GEX y NetOI por
strike × epoch) está muerto desde el 1-ago. Y `com.ibtrader.tracecube` sale con **exit 1**, que es
exactamente el mismo código que usa su portero horario → **el fallo es indistinguible de "fuera de horario"**.

**Parche propuesto**: añadir a `scripts/provider_bridge.py` (junto al `os.replace` de
`opt_chain_<sym>.txt`) una copia a `data/history/<fecha>/opt_chain_<sym>_HHMM.txt`, replicando
`scripts/opt_chain_cache.py:303-306`. Es una escritura de 3 líneas y **para la hemorragia hoy**.
Además: dar a `com.ibtrader.tracecube` un código de salida distinto para "fuera de horario" (0)
y para "falló" (≠1), o el fallo seguirá camuflado.

### ⛔ B-2 — La alarma de ballenas lleva **2 sesiones muda** y el healthcheck la pinta VERDE
**Daño: pierde la señal que la casa llama "el recurso más poderoso" + FALSO VERDE, que es peor que un falso rojo.**

`scripts/opt_whale_keepalive.sh:4-10` es un `while true` **sin ningún gate de `market_source`**:
```zsh
while true; do
  pkill -f "scripts/opt_whale_watch.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/opt_whale_watch.py >> logs/opt_whale.log 2>&1
  echo "$(date) opt_whale_watch salio; relanzando" >> logs/opt_whale.log
  sleep 60
done
```
`scripts/opt_whale_watch.py:297` va directo a `ib.connect(...)` → 4001 cerrado. El script **sí**
se rinde bien (`whale watch: 5 fallos seguidos … SALGO para que el keepalive recargue`), pero el
keepalive lo resucita a los 60 s, para siempre. Medido: **1.454 `ConnectionRefusedError` y 285
relanzamientos, de los cuales 129 el 2026-08-03** (media histórica: 1-8/día).

Salida real del vigía, congelada:
- `data/opt_flow.txt` → **Jul 31 16:03**
- `data/whale_aapl.txt` → **Jul 31 16:45**; `whale_amd/asml/gld.txt` → **0 bytes desde Jul 15**

O sea: sin táctica espada-ballena (regla 11) y sin jerarquía de capitanes por flujo (regla 12)
durante toda la sesión del lunes 3-ago.

**Y el healthcheck lo tapa**: `logs/healthcheck.log` canta `🟢 opt_whale (ballenas opciones): vivo`
y `🟢 opt_whale (ballenas opciones): parado fuera de horario (correcto)`. Está parado, sí — pero
**también estaba parado dentro de horario**. Un verde falso apaga la vigilancia entera.

**Parche propuesto**: copiar el gate de `scripts/sox_keepalive.sh:9-18` a
`scripts/opt_whale_keepalive.sh:4` (una línea/hora `opt_whale EN PAUSA: market_source=…`), y en
`scripts/fleet_healthcheck.py` **no** declarar 🟢 "parado fuera de horario" sin comprobar la
frescura de `data/opt_flow.txt`: si el fichero tiene >1 sesión, es 🔴, no 🟢.

### ⛔ B-3 — `force.json` lleva **14 días** rancio: la FUERZA está apagada dentro de la brújula, en silencio
**Daño: pierde una entrada de señal que la casa declara obligatoria (~/CLAUDE.md regla 9: "La fuerza … es parte del veredicto SIEMPRE"). Cero líneas de log: el fallo perfecto.**

`scripts/compass.cpp:1493-1502` lee `data/force.json` y **solo lo usa si `ts` es fresco**
(`FORCE_MAX_AGE`, 2 min). `data/force.json` tiene mtime **2026-07-21 04:00 = 14,0 días**.
El productor `scripts/force_meter.py` existe (8.136 B, editado el 28-jul) pero **no lo lanza NADIE**:
`grep -rl force_meter` fuera de `logs|backup|.git` devuelve solo `Done.md`, `tests/`, `docs/`.
Resultado: `e.force_phase` y `e.exhaustion` nunca se rellenan y **degrada limpio**, o sea sin ruido.

Mismo patrón (productor presente, scheduler ausente), todos verificados con `stat`:

| dato | edad | lo LEE | productor sin scheduler |
|---|---:|---|---|
| **`data/force.json`** | **14,0 d** | `scripts/compass.cpp:1493` (bucle 0,25 s) | `scripts/force_meter.py` |
| `data/etf_weights.json` | 10,0 d | `scripts/compass.cpp:353` — **sin control de edad** | `scripts/etf_weights_refresh.py` |
| `data/timeofday_factors.json` | 10,0 d | `scripts/signal_conditioning.py:204` | `scripts/timeofday_calib.py:169` |
| `data/signal_enable.json` | 9,7 d | `scripts/signal_conditioning.py:266` (apaga celdas muertas) | `scripts/timeofday_calib.py:169` |
| `data/bollinger_probs.json` | 12,4 d | `scripts/bollinger_alarm.py:29` | — |
| `data/dip_probs.json` | 12,4 d | `scripts/dip_alert.py:103` | — |
| `data/momentum_thresholds.txt` | 13,6 d | `scripts/momentum_calc.cpp:33` | — |
| `data/korea_levels.txt` | **NO EXISTE** | `scripts/korea_watch.cpp:36,48` | **nadie en todo el repo** (**B-13**) |

**Parche propuesto**: `force_meter.py` como **daemon** en `scripts/fleet_keepalive_start.sh`
(no como lote de las 4am: `compass.cpp` exige 2 min de frescura), y `etf_weights_refresh.py` +
`timeofday_calib.py` en `scripts/dailyplans_run.sh`. Además `compass.cpp:353` debe exigir `asof`
fresco igual que hace con `force.json`, o seguirá usando pesos de hace 10 días sin decirlo.

### ⛔ B-4 — El cockpit gráfico lleva 16 h ciego reintentando IBKR cada 5 s, y el error va a `/tmp`
**Daño: pierde visión. El log está fuera de `logs/`, por eso lleva días invisible.**

6 procesos `chart_bridge.py` (pids 14974/14977/14981/14984/14987/14991, `etime` **16 h 02 m**)
sirven los puertos 8080-8085 (verificado OPEN) pero **ninguno tiene fuente**:
`scripts/chart_bridge.py` **no lee `data/market_source.txt` en ninguna línea**
(`grep -n market_source` → solo un comentario en `:1259`). Va directo a IBKR:

- `scripts/chart_bridge.py:3988` `await asyncio.wait_for(ib.connectAsync("127.0.0.1", port, clientId=client_id), 15)`
- `scripts/chart_bridge.py:3991` `print(f"[live] reconnect en 5s ({e})")` → **bucle de 5 s**

Evidencia: `/tmp/w6_qqq.log` con **11.389** `ConnectionRefusedError(61, …4001)`; ×6 ficheros =
**68.662 fallos, 18 MB**. Lanzador: `scripts/.chartqa_run.sh:9` (job `com.ibtrader.chartqa`,
`KeepAlive=true`, pid 24836), que redirige a `/tmp/w6_$s.log`.

**Parche propuesto**: en `scripts/chart_bridge.py:3985` (antes del `connectAsync`) leer
`data/market_source.txt`; si != `ibkr`, tomar precio de `data/bars_<sym>_ibkr.txt` (que
`provider_bridge` sí escribe) en vez de reconectar. Mínimo viable hoy: gatear
`scripts/.chartqa_run.sh:9` y redirigir a `logs/chart_bridge_<sym>.log` — **un log de producción
no puede vivir en `/tmp`**.

### ⛔ B-5 — `pytest tests/` mete alarmas DANGER **reales** en el ntfy y el email de Yunior
**Daño: CRYING WOLF. Viola directamente la regla 3 de disciplina de trading.**

Medido: **52** pushes `🕳 CINTA CIEGA | No veo las ballenas de 3 acciones.` en
`data/notify_push.txt`, agrupados en ventanas de sesión de agente (07:09-08:21 y **02:29-02:47 de hoy**).

Cadena exacta, verificada línea a línea:
1. `tests/test_whale_tape.py:111` → `m.declare_blind(["AAPL","AMD","TSM"], ...)` — **3 símbolos**, que
   es literalmente el texto de la alarma.
2. `tests/test_whale_tape.py:110` parchea `m.subprocess.Popen` (mata osascript y speak.sh) **pero no
   parchea `notify_short.push`**.
3. `scripts/ibkr_bar_bridge.py:339` → `import notify_short; notify_short.push("🕳 CINTA CIEGA", voz)`
4. `scripts/notify_short.py:18-19` → `REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`,
   `PATH = os.path.join(REPO, "data", "notify_push.txt")` → **derivado de `__file__`, así que el
   `monkeypatch.chdir(tmp_path)` del test NO lo aísla.** Escribe en el fichero real.
5. `scripts/notify_relay.sh:35` lo reenvía a ntfy + Resend.

**Parche propuesto**: en `tests/test_whale_tape.py:110` añadir
`monkeypatch.setattr(m.notify_short, "push", lambda *a, **k: None)`; y como cinturón, en
`scripts/notify_short.py:19` respetar `IBT_NOTIFY_PUSH` del entorno para que `conftest.py` lo
redirija a `tmp_path` en toda la suite.

### 🔴 B-6 — `watchlist_quotes` relanzado **291 veces/día** contra un puerto cerrado, y su salida es un `{}` fabricado
**Daño: la watchlist manual de Yunior lleva 82 h sin cotizar + 1,46 MB de tracebacks.**

`scripts/fleet_keepalive_start.sh:227-229` lanza el daemon **sin gate**, al contrario que sus dos
vecinos: `:219-221` (`provider_bridge`, dentro del `if` de `:199`) y `:238` (`korea_bar_bridge`,
`[[ "$(cat data/market_source.txt)" == "ibkr" ]] && ...`), que **sí** miran la fuente.
El proceso muere en `scripts/watchlist_quotes.py:110`
(`await ib.connectAsync(...)`) antes de entrar al bucle, dejando **un traceback de ~15 líneas**.

Medido: **382 tracebacks / 764 menciones a 4001**. Relanzamientos: `2 (07-31) · 55 (08-02) ·
291 (08-03) · 35 en las 2,8 h de hoy` = uno cada 5 min exactos (`logs/fleet_autostart.log`,
últimas `02:44:59`, `02:50:02`, `02:55:05`). **El bucle está corriendo ahora mismo.**

Y lo que deja escrito es peor que nada:
```
data/watchlist_stats.json   (Jul 31 16:46, 82,1 h)
{"ts": 1785530809, "src": "watchlist_quotes.py (TWS snapshot)", "stats": {}}
```
Un `{}` con `src` que afirma "TWS snapshot" — **cero plausible con firma de autoridad**, justo lo
que prohíbe la ley de la casa. TQQQ, MSFU, MUU, SOXS, METD, MSFD, KO salen en blanco en el cockpit.

**Parche propuesto**: copiar el gate de `scripts/sox_keepalive.sh:9-18` a
`scripts/fleet_keepalive_start.sh:227`. Y que `watchlist_quotes.py` **no escriba el `.json`** si
`stats` viene vacío (o escriba `"stats": null` con `"error"`), en vez de firmar un vacío como snapshot.

### 🔴 B-7 — El healthcheck lleva **88 corridas seguidas en rojo** y 266 de sus 330 críticos son falsos
**Daño: MIENTE. Un semáforo 4 días en rojo deja de ser un semáforo.**

Exit code por día: `20×exit0 / 3×exit2` (07-25) … → **08-01: 3/3 exit 2 · 08-02: 37/37 · 08-03: 44/44 ·
08-04: 4/4**. **100 % de las corridas desde el 1 de agosto.**

Críticos agrupados en todo el log:
| conteo | crítico | ¿real? |
|---:|---|---|
| 134 | `🔴 notify_relay (notificaciones): MUERTO` | **FALSO** — `pgrep -f notify_relay.sh` → **55496 VIVO** |
| 132 | `🔴 x_signal_poster (X realtime): MUERTO` | **FALSO** — `pgrep -f x_signal_keepalive.sh` → **25211 VIVO** (+ poster 25254) |
| 115+115 | `launchd com.ibtrader.{postmortem,dailyplans}: NO CARGADO` | **FALSO** — ambos cargados con exit 0 |
| **64** | `🔴 finviz token CADUCADO … scout/valuation/x_bot CIEGOS` | **REAL** → B-8 |
| 9 | `planes de hoy: # PDFs (el run de 4am fallo?)` | real, ver B-10 |

`scripts/fleet_healthcheck.py:542` (dentro de `heal()`) produce además **258** líneas
`NO revivido — el keepalive murio al instante (exit 127)`. La guarda `pgrep_ciego()` (`:58-65`)
cubre el caso "no veo NI a launchd", pero **no** el caso "veo unos procesos y otros no", que es el
que genera estos. Efecto colateral: cada corrida **lanza duplicados** de daemons que ya están vivos.

**Parche propuesto**: en `scripts/fleet_healthcheck.py:542`, si el heal sale 127 → degradar a 🟡
con texto `"no verificable desde este entorno"` en vez de 🔴 MUERTO (un `exit 127` del keepalive
es síntoma de entorno, no de flota). Y no contarlo para el exit code.

### 🔴 B-8 — Token Finviz Elite 401: scout, valuation, bargain y x_bot CIEGOS desde el 08-02
**Daño: pierde señales. NO es parche de código — es renovar el token.**

**1.585 líneas** repartidas: `screener/fastscan.log` 596 · `screener/bargain.log` 528 ·
`logs/finviz_scout.log` 153 · `logs/dip_alert.log` 149 · `screener/rescan.log` 80 ·
`logs/healthcheck.log` 66 · `logs/dailyplans.log` 7 · `screener/scan_6am.log` 6.
Primer crítico **2026-08-02 08:55**, último **2026-08-04 02:41**. `config/feeds.env` se tocó a las
02:15 de hoy y **sigue caducado**.

Código: `screener/sources.py:86`, `scripts/finviz_valuation.py:71`.
Aguas abajo el diseño es **honesto** (no inventa): `[sources] SIN DATOS REALTIME (FINVIZ_AUTH
caido/ausente). Fuentes delayed PROHIBIDAS — universo vacio a proposito`. Pero `dip_alert` ya sirve
un CSV de **19,2 h** y a las 24 h se queda sin nada.

Agravante: `screener/rescan.log` + `fastscan.log` tienen además **4.233** líneas
`[ibkr_data] TWS no disponible — SIN datos (delayed prohibido)` (`screener/ibkr_data.py:36-37`).
**El screener está doblemente ciego** (sin Finviz y sin NBBO) y nadie lo canta como tal.

### 🔴 B-9 — `trace_cube`: 252 fallos, "cero fotos utilizables" → ver **B-1** (misma causa raíz)

### 🔴 B-10 — `daily_fleet_plans`: **QQQ y MU sin plan** por un `IndexError` tragado
**Daño: pierde señales. Los dos tickers 0DTE del presupuesto se quedan sin plan, sin PDF y sin borrador X.**

14 líneas `FALLO list index out of range`; afectados **QQQ, MU**, ASML, SNDK, WDC, STX.
Salieron **8 PDFs de 10** en la corrida APERTURA del 2026-08-03 09:13
(`logs/dailyplans.log:4846-4849, 4961-4962`).

Origen: `scripts/daily_fleet_plans.py:564`
```python
cw0 = sorted(cs["cw"], key=lambda r: -r[1])[0]; pw0 = sorted(cs["pw"], key=lambda r: -r[1])[0]
```
`[0]` sobre lista vacía cuando la banda ±3,5 % de la cadena no trae strikes. Se traga en
`scripts/daily_fleet_plans.py:882` `except Exception as e: print(f"{sym}: FALLO {e}")` — un `except`
tan ancho que convierte "no tengo cadena" en "este ticker hoy no toca".

**Parche propuesto**: en `:564`, comprobar `if not cs["cw"] or not cs["pw"]:` y saltar **solo la
sección BOLETOS** (el resto del plan es válido sin ella), en vez de perder el PDF entero.

### 🟠 B-11 — `prints_archiver` y `levels5m` vuelcan el informe JSON entero en cada corrida
**Daño: solo ensucia — pero son 8,8 MB y ~600.000 líneas, el 18 % de todos los logs.**

`~/Library/LaunchAgents/com.ibtrader.prints.plist` invoca `equity_prints_archiver.py **--once**`
con `StartInterval 120` y `StandardOutPath = logs/prints_archiver.log`. Sin `--loop`, `main()` cae en
`scripts/equity_prints_archiver.py:383` `print(json.dumps(r, indent=1))` → ~94 líneas por corrida.
Medido: **100.776 bloques `"rows"`, de los cuales 89.074 (88,4 %) son `"rows": 0`**.
**La rama `--loop` SÍ imprime una línea resumen** (`:377`). El plist eligió la rama ruidosa.

Gemelo: `com.ibtrader.levels5m` → `levels_5min_archive.py --once --session-only`, `StartInterval 300`,
volcado en `scripts/levels_5min_archive.py:376`; **1.866 de 2.353 corridas (79 %) son
`{"skipped":"fuera_de_sesion"}`** (`:121`), 4 líneas cada una.

**Parche propuesto**: cambiar ambos plists a `--loop 120` / `--loop 300` (rama que ya resume en 1
línea), o mover el `json.dumps` detrás de un flag `--json`. **Ahorro: 8,8 MB / ~600.000 líneas.**

### 🟠 B-12 — `truth_lock` grita "SUCIO" 142.043 veces con 0 materiales y 0 desaparecidas
**Daño: etiqueta engañosa + 6,47 MB, el log que más rápido crece (1,2 MB/día).**

`scripts/truth_lock.py:516-518`:
```python
for s, v in sorted(r["syms"].items()):
    if v.get("adjusted"):
        print("  %s SUCIO: %d materiales, %d desaparecidas" % (s, v.get("material", 0), v.get("missing", 0)))
```
Se dispara con `adjusted` (cualquier ajuste, aunque sea inmaterial). Medido: **142.261 líneas
`SUCIO`, de las cuales 142.043 (99,85 %) dicen `0 materiales, 0 desaparecidas`. Solo 218 tenían
contenido real.** Job `com.ibtrader.truthlock`, `StartInterval 120` → ~24 líneas cada 2 min = 17.280/día.

**Parche propuesto**: `scripts/truth_lock.py:516` → `if v.get("material") or v.get("missing"):`
y renombrar la etiqueta a `REESCRITO` (que es lo que mide). **Ahorro: 6,4 MB / ~142.000 líneas.**

### 🟡 B-13 — `data/korea_levels.txt` no existe y NADIE lo escribe
`scripts/korea_watch.cpp:36,48` lo lee; `:86` grita
`"korea_watch: data/korea_levels.txt ausente/incompleto/rancio"`. `grep -rn korea_levels` devuelve
**solo las 4 líneas del propio `.cpp`**. `bin/korea_watch` no corre esta noche pese a ser sesión de
Corea. **Escribir el productor o retirar `korea_watch` del arranque**: hoy solo puede fallar.

### 🟡 B-14 — Dos productores de señal HUÉRFANOS: `today_alarm5.py` y `capitulacion_qqq.py`
`logs/relaunch_today_alarm5.log` (4.687 líneas) y `logs/relaunch_capitulacion_qqq.log` (783)
**no reciben una línea desde `Jul 29 16:01`**. `grep -rl today_alarm5` fuera de logs/backup/docs/tests
devuelve solo `Done.md`, `TODOS.md` y el propio script: **ningún `.sh`, ningún plist, ningún
keepalive los lanza.** Su bug de ruta (`level_react` en la raíz) ya está arreglado
(`today_alarm5.py:34`, `capitulacion_qqq.py:35` con `bin/` primero) — pero da igual: nadie los arranca.

Además `scripts/today_alarm5.py:66-68` hace `except Exception: … return []`. Un `[]` en camino de
señal significa "no hay eventos operables" = el cero plausible prohibido. **Si se reengancha,
arreglar eso primero** (`return None` o levantar).

### 🟡 B-15 — `band_open_watch` relanzado **163 veces un domingo**: el precedente de las 718 sigue abierto
`scripts/band_open_watch.py:101` → `if hm >= 1035 or lt.tm_wday >= 5: break` (sale al instante fuera
de 09:29-10:35 y en fin de semana). `scripts/fleet_keepalive_start.sh:350-352` lo relanza cada 5 min
**sin guarda horaria**, aunque el comentario de `:349` dice literalmente *"Corre solo 9:29-10:35 y muere"*.
En el MISMO fichero, `position_close_reminder` (`:378-379`) **sí** lleva
`(( FP_DOW <= 5 && FP_HM >= 930 && FP_HM < 1600 ))`.

Serie: 109 (7-25) · 48 (7-26) · **163** (7-27) · 133 (7-28) · **164** (7-29) · 129 (7-30) · 73 (7-31)
· 55 (8-02) · **163 (8-03, domingo)** · 1 (8-04) = **1.037 en 12 días**.
`logs/band_open_watch.log` = 360 B sin escribir desde Jul 31 → **muere sin dejar ni una línea**.

**Parche propuesto**: `scripts/fleet_keepalive_start.sh:350` — copiar la guarda de `:378` con
ventana `925..1035`. Mata 163/día. Y que el script escriba su motivo de salida.

### 🟡 B-16 — `perp_stock_fetch`: un `socket.timeout` sin capturar tumba el ciclo entero
11 tracebacks. `scripts/perp_stock_fetch.py:31` `urllib.request.urlopen(req, timeout=10)` sin `try`;
propaga por `:49` → `:102` → `:132` → `:144`. El keepalive rearranca y el `.json` no se pisa con
basura (bien), pero **un timeout de red debería saltarse un símbolo, no matar la vuelta**.
(El 403 de TXN/XLK que producía `26/28 symbols` **ya se resolvió**: las últimas ~1.370 corridas dan `28/28`.)

### 🟡 B-17 — `uw_flow_tape` diagnostica "token caducado" cuando el token está SANO
**Daño: miente sobre la causa y manda a renovar un token que funciona.**

`scripts/uw_flow_tape.py:58` `return None, "error 401 (token caducado)"` — texto **hardcodeado**
para cualquier 401 (40 ocurrencias). Pero `scripts/uw_gex_expiry.py` usa **el mismo token**
(`from uw_premium import token`, `:27` vs `uw_flow_tape.py:17`) y esa misma noche registra
`uw_gex_expiry: 35 syms ok, 0 fallos`. Endpoints distintos:
`/api/stock/{sym}/greek-exposure/expiry` (**200**) vs `/api/stock/{sym}/flow-alerts` (**401**).
→ el 401 es **de entitlement del endpoint**, no de caducidad. Además `:167-168` duerme 600 s por
cada 401, así que la cinta de flujo UW está muda.

**Parche propuesto**: `scripts/uw_flow_tape.py:58` → `"error 401 en /flow-alerts (el mismo token
sirve /greek-exposure: es ENTITLEMENT, no caducidad)"`. Y verificar el plan UW antes de renovar nada.

### 🟡 B-18 — pytest escribe en el log de producción
`printplans.log` (raíz):
`Tue Aug 4 02:29:42 EDT 2026 === print_plans [pytest] ZZINEXISTENTE (imprimir=0 …) ===` ×2 hoy.
Higiene: los tests deben escribir a `tmp_path`. (Primo pequeño de B-5.)

### 🟡 B-19 — `_pgrep` con `-a` incluye a los ANCESTROS en macOS (mina latente)
`scripts/fleet_healthcheck.py:43` usa `pgrep -a -f <pat>`. En macOS `-a` **no** significa "añade
cmdline" (eso es Linux, y así lo dice el comentario en `:37-39`): significa *no excluir al invocante
ni a sus ancestros*. Medido ahora: `pgrep -a -f notify_relay.sh` → `18802, 18835, 55496`, donde
**55496 es el daemon real y 18802/18835 son mis propios ancestros de shell**.
El `-a` se puso por una razón buena y medida (`:38`), así que **no se quita: se filtra**.
**Parche propuesto**: validar cada pid con `ps -o command= -p <pid>` y descartar shells ancestros.

### 🟡 B-20 — `compass` duplicado en la raíz: riesgo de empotrar un binario rancio en el Cockpit
`./compass` y `bin/compass` son el MISMO binario (sha1 `86b149be…`, 175.176 B, ambos Jul 29 21:20).
`macapp/bundle_backend.sh:145` tiene `elif [ -x "compass" ]`: si algún día solo se recompila `bin/`,
el bundle puede empotrar la copia rancia de la raíz. También quedan `./compass_asan` (Jul 29) y
`./volume_profile_asan` (Aug 3) sin gemelo en `bin/`. **Borrar los duplicados de la raíz** cierra
el precedente de la mudanza del todo.

---

## 4. Falsos rojos — dejar de pintarlos en rojo

| lo que se ve | por qué NO es un bug | evidencia |
|---|---|---|
| `com.ibtrader.polychains.intraday` **exit 1** | es su portero horario: `[ "$H" -ge 0935 ] && [ "$H" -le 1600 ]` falla fuera de ventana y el shell sale 1 | plist. **Verificado además que los ceros a la izquierda NO rompen la comparación en zsh** (`0948 -ge 0935` → OK): no hay bug octal |
| `com.ibtrader.tracecube` **exit 1** | mismo portero (`0935..1625`) | ⚠ pero **enmascara B-9**: el mismo exit 1 sirve para "fuera de horario" y para "falló 252 veces" |
| `flow_pulse` caído de noche | salida limpia y declarada: `flow_pulse: fuera de RTH, salida silenciosa` + `15:56 — pulso de flujo fuera hasta manana` | `logs/flow_pulse.log` |
| `sox_feed EN PAUSA: market_source=intrinio` (545 líneas) | **gate perfecto**: 1 línea/hora, sin traceback, sin reintentos. Antes eran 24.091 relanzamientos y 21 MB | `scripts/sox_keepalive.sh:9-18` — **es el patrón a copiar en B-2, B-6 y B-15** |
| WebSocket Intrinio caído toda la noche (210+44 `RemoteDisconnected`) | apagón programado del vendor. El sondeo lo confirma cada ~10 min: `auth_up=NINGUNO socket_ok=NINGUNO \| rest=200 polygon_ws=True` — **REST 200, o sea el token está vivo** | `logs/intrinio_ws_probe.log` 02:50:42 |
| 22.026 `ConnectionRefusedError …4001` en 20 logs | IBKR está PROHIBIDO esta semana. **El refused en sí es esperado.** El bug es *quién sigue reintentando* (B-2, B-4, B-6) y *quién se queda sin dato* (B-1) | ver §3 |
| `bridge_korea.log` con 15.025 `korea bridge CAIDO` | el bridge IBKR de Corea se rindió correctamente el 08-02 20:13 tras 164 intentos, y Naver lo sustituye: `[korea-naver] 02:32:02 … 12 prev_close oficiales`, `data/bars_kospi.txt` fresco a las 02:32 | `logs/bridge_korea_naver.log` |
| `fleet_consensus`: `barras rancias (393min)` de madrugada | las barras US paran a las 20:15 (fin de extended hours). A las 02:48 la antigüedad correcta **ES** ~393 min | `data/bars_qqq_ibkr.txt` mtime `08-03 20:15` |
| `fleet_consensus`: `cobertura insuficiente 0/26 (min 23) — esto es FEED, no direccion` | el denominador **no** se fabrica y lo dice explícitamente. Es el bug de julio ya curado, funcionando | `scripts/fleet_consensus.py:109-112` |
| `logs/uw_flow_archive.log` con **una sola línea** | job nuevo `com.ibtrader.uwflowarchive` (pid 91339) esperando a la apertura; su línea es el presupuesto: `5 syms x 3 series -> ~4290 peticiones/sesion (tope propio 15000 de 30000)` | correcto |
| healthcheck: `🟡 VISTA CIEGA: pgrep no ve ni a launchd` | es la guarda BUENA (`scripts/fleet_healthcheck.py:58-65`): distingue "no puedo mirar" de "está muerto". Reproducido: `pgrep -x launchd` desde entorno aislado → vacío | ✅ dejarlo así |
| healthcheck: `🔴 notify_relay / x_signal_poster MUERTO` (266 líneas) + `heal exit 127` (258) | **falso positivo de entorno**, ya documentado en `fleet_healthcheck.py:61-64`. Verificado: pids **55496** y **25211/25254** vivos, ambos keepalives existen y son ejecutables | ver B-7 |
| `screener/ensure.log` lleno de `PORTERO AUSENTE` | **ARREGLADO hace 43 h**: `screener/ensure_all.sh:26` ya hace `bin/fleet_hours` con la raíz de respaldo. Último caso `08-03 07:08:03`, seguido de `07:10:03 ensure: alert bot relanzado` | ⚠ pero fueron **2.784 de 3.760 líneas (74 %)** = 6 días en los que ese supervisor **no relanzó nada** |
| 4.685 `level_react fallo` + 9 `falta el binario …/gate` | **ARREGLADOS**: `today_alarm5.py:34`, `capitulacion_qqq.py:35`, `optgate.py:40`, `fleet_window.py:37` prueban `bin/` primero; los 14 binarios de `bin/` existen y son ejecutables | último caso Jul 29 / Jul 31 |
| `logs/*_signals.log` con ~4.000 `relanzando` cada uno | historia de la era TCC `~/Documents`: 768 (7-13) + 2.273 (7-14) + 929 (7-15). Desde el 16-jul: 1-4/día | `sh: bridge_nok.log: Operation not permitted` |
| `Error 300, Can't find EId with tickerId` (3.901) y `No security definition Option(...)` (~2.800) | ruido normal de `reqMktData` snapshot y strikes inexistentes; `opt_chain_cache.py` los ignora por diseño | — |
| `Databento GLBX fuera de licencia` en `futures_feed.log` | el aviso viaja **pegado al dato** (`avisos: …` en la misma línea que los %) — exactamente la ley de la casa | — |
| Los 17 `/tmp/ibtrader.*.{out,err}` | **todos a 0 bytes**. Nada que reportar | — |

**Lo importante de esta sección**: los dos peores no son rojos falsos sino **VERDES falsos** —
`🟢 opt_whale: parado fuera de horario (correcto)` con la salida congelada desde el 31-jul (B-2), y
el `exit 1` de `tracecube` que camufla 252 fallos (B-9). Un rojo falso enseña a ignorar rojos;
un verde falso apaga la vigilancia entera.

---

## 5. Jobs colgados y bucles — con números

### Colgados
| job | evidencia | pérdida |
|---|---|---|
| **`com.ibtrader.intrinioprobe`** | `logs/healthcheck.log`: `COLGADO — 188 min` (08-03 07:04) → `216` (07:32) → `299` (08:55) → `514` (12:30) → **`759 min`** (08-03 16:35). `StartInterval 600 s`. Una sola corrida iniciada ~03:56 seguía viva **12 h 39 m** después | **~75 sondas perdidas** (el precedente de la casa eran 18). launchd no relanza mientras el anterior viva **y el exit code no cambia** |
| estado hoy | **RECUPERADO**: cadencia normal de 642 s (600 + 42 s de corrida) toda la noche, última `02:50:42` | — |

`scripts/intrinio_ws_probe.py:45` fija `TIMEOUT = 20` y `:128` `ws.settimeout(10)`, pero **no hay
tope global de corrida**. **Parche**: envolver `main()` con `signal.alarm(300)` o poner `ExitTimeOut`
en el plist. Un job periódico sin tope de corrida es un job que se pierde en silencio.

`com.ibtrader.chartqa` (pid 24836, 19 h 53 m) **NO está colgado**: es `KeepAlive=true`, o sea un
daemon. Lo que hace mal es B-4.

### Bucles de relanzamiento (`logs/fleet_autostart.log`, últimos 7 días)
```
proceso                   07-29  07-30  07-31  08-02  08-03  08-04*  TOTAL
band_open_watch             164    129     73     55    163      1     585   ← B-15
watchlist_quotes              -      -      2     55    291     34     382   ← B-6
position_close_reminder       1      1      1      -     79       -      82
earnings_fall_scout           6      7      7      -      7       -      27
x_signal_keepalive            4      -      2      2      4       -      12
opt_whale_keepalive           5      -      2      2      -       -       9   ← ver nota
flow_pulse                    3      2      2      -      2       -       9
sox_keepalive                 3      -      2      2      1       -       8   ← ya parcheado 08-03
notify_relay                  3      -      2      2      1       -       8
~30 × <ticker>_keepalive      3      -      2      2      -       -       7 c/u
```
`*` hoy solo hasta las 02:50 (2,8 h). **34 lanzamientos de `watchlist_quotes` en 170 min = uno cada
5 min exactos: el bucle corre AHORA MISMO.**

Nota: los relanzamientos de `opt_whale` **no** se cuentan aquí sino dentro de su propio log —
`logs/opt_whale.log` tiene **285** `opt_whale_watch salio; relanzando`, de ellos **129 el 08-03**
(media histórica 1-8/día). Ese es el bucle real de B-2.

### Riesgo de denominador (NO es bug hoy, pero hay que verlo)
4 de los 30 de `data/fleet.txt` llevan **sin barras desde 2026-07-31 16:45**: **DRAM, EWY, SKHY, SPCX**
(no están en `data/provider_syms.txt`, que tiene 26). `scripts/fleet_consensus.py:26-36` usa
deliberadamente ese universo de 26 como denominador y **lo declara** en la alarma
(`:136-138` `[universo RECORTADO 26/30: sin feed …]`). Aritmética:

- universo 30 → hacen falta **24** alineados para el 78 %
- universo 26 → hacen falta **21** — y **21/30 = 70 %**, que es exactamente el falso DANGER del 2026-07-25

Hoy **no ha disparado** ninguna manada con universo recortado (la única `DISPARADA UP` del log es
`25/30 (n=30)`), pero **el umbral efectivo está más bajo desde que IBKR está apagado**.
**Decisión para Yunior**: conseguir feed para DRAM/EWY/SKHY/SPCX, o subir `FLEET_CONS_PCT` mientras
el universo esté recortado.

---

## 6. Rutas rotas — estado

- **Los 14 binarios de `bin/` existen y son ejecutables**; sus 14 fallbacks a la raíz **nunca
  resuelven** (verificado con `test -x` uno a uno). El patrón `bin/ primero, raíz de respaldo` está
  aplicado en `fleet_keepalive_start.sh:124-125`, `screener/ensure_all.sh:26`, `screener/start_all.sh:21`,
  `optgate.py:40`, `today_alarm5.py:34`, `capitulacion_qqq.py:35`, `level_events_ingest.py:33`,
  `level_react_validate.py:44`, `fleet_window.py:37`, `x_whale_bot_keepalive.sh:8`, `regen_signals.py:679`.
  **El precedente `bin/` está cerrado** salvo el duplicado de `compass` (B-20).
- **Ruta vieja `~/Documents/GitHub/ib-trader`**: 58 apariciones en `logs/opt_whale.log`, todas entre
  `Jul 25 01:46` y `Jul 25 03:30` (el día de la mudanza) + colas en `logs/healthcheck_err.log`
  (Jul 22, con `PermissionError … /Desktop/planes-…`). **Cero en código vivo.** Sí queda en docs
  (`README.md:16`, `docs/OPERATIONS.md:9,116`, `docs/X-WHALE-BOT.md:135`, `docs/QUANT-STACK.md:8`,
  `.claude/skills/fleet-ops/SKILL.md:8`, `.claude/skills/cpp23-fleet/SKILL.md:26`) — anotado en `TODOS.md:230`.
- **`~/Desktop` sigue siendo destino de los planes diarios** (`scripts/daily_fleet_plans.py:7`,
  `x_plan_poster.py:90`, `xpost.py:19`, `x_postmortem.py:151`, `calibration_ledger.py:257`,
  `fleet_healthcheck.py:639`, `daily_archive.py:40-41`) y los produce `com.ibtrader.dailyplans` bajo
  launchd → **riesgo TCC vigente**, ya cazado 34 veces:
  `🟡 planes de hoy: Desktop vetado por TCC (dar Full Disk Access al runner) — no pude contar PDFs`.
  Contradice la regla de la casa "jamás bajo Documents/Desktop/Downloads para launchd".
- **Plists basura no cargados** que apuntan a ficheros inexistentes:
  `scripts/com.ibtrader.scan.plist:13` → `/…/ib-trader/scan_server` (no existe);
  `scripts/com.ibtrader.dram.plist:9` → `scripts/run_dram_bot.sh` (no existe).
- Los **26 plists cargados** están limpios: todos sus `ProgramArguments` / `StandardOutPath` /
  `StandardErrorPath` existen (validado con `plistlib`).
- **Un log de producción vive en `/tmp`**: `/tmp/w6_<sym>.log` (`scripts/.chartqa_run.sh:9`). Ver B-4.

---

## 7. Rotación: **no se rotó nada, y es la respuesta correcta**

Ningún log del repo supera los 20 MB. El mayor es `logs/prints_archiver.log` con **7,93 MB**.
El único fichero >20 MB del árbol es `data/history/2026-08-03/levels_5m.jsonl` (20 MB), que **no es
un log sino un archivo de datos** — rotarlo destruiría historia.
`/tmp/w6_*.log` son 3,0 MB cada uno (18 MB) y están **abiertos por 6 procesos vivos**: truncarlos
con `tail`+`mv` rompería sus descriptores y mataría el cockpit.

**Espacio recuperado rotando: 0 MB.**

La autorrotación que ya existe (`scripts/notify_relay.sh:30-33`: corta a 2.000 líneas al pasar de
20 MB) es la razón de que `notify_relay.log` esté hoy en **0,22 MB** y no en los 196 MB del
precedente. **Esas 4 líneas deberían copiarse a `equity_prints_archiver.py` y `truth_lock.py`**,
que son los dos que van camino de repetirlo. Con B-11 + B-12 arreglados se ahorran **15,2 MB y
~742.000 líneas/semana sin rotar nada**.

---

## 8. Lo que NO pude determinar

1. **Si el plan de Unusual Whales cubre `/api/stock/{sym}/flow-alerts`**. Deduje que el 401 es de
   entitlement porque el mismo token da 200 en `/greek-exposure/expiry`, pero no consulté la cuenta.
2. **Por qué `band_open_watch` moría 163 veces también en horario de sesión** (07-27, 07-29, 08-03):
   su log lleva mudo desde Jul 31, así que la causa de muerte **no está registrada**. Lo primero es
   hacerle escribir el motivo de salida.
3. **Si `provider_bridge` PUEDE archivar fotos 5-min** con el dato que recibe de Intrinio/Polygon
   (B-1), o si hace falta otra fuente. No abrí el módulo a fondo para no pisar a los agentes que
   trabajan en `docs/`.
4. **Emisor de las 15.025 líneas `korea bridge CAIDO … (¿TWS en N?)`**: ese texto exacto ya no existe
   en el árbol vivo; solo aparece en `backup/tainted_logs_2026-07-13/`. Residuo de una versión anterior.
5. **Latencia real de crecimiento en sesión**: las tasas de §1 se midieron con el mercado US cerrado.
   Repetir la medición entre 09:30 y 16:00 para conocer el caudal verdadero.
6. **Si `data/etf_weights.json` a 10 días desvía de verdad los pesos del engranaje QQQ/SPY**.
   `compass.cpp:353` lo lee sin comprobar `asof`, pero no medí cuánto se movieron los pesos reales.
7. **`samsung_pct: 0.0` exacto** en `logs/overnight_feed.log` (25 líneas hoy) con KOSPI +1,62 % y
   Hynix +0,51 %. **No es un cero fabricado**: `data/korea_prevclose.json` da Samsung 239.500 y la
   última barra de `data/bars_samsung.txt` es 239.500 → cierre plano real. Pero las últimas 10 barras
   tienen **volumen 0** (arrastre post-cierre) y el campo no distingue "plano" de "congelado".
   Candidato a `samsung_ref_src` con marca de frescura — no medido.

---

## 9. Orden de ataque sugerido (para antes de la apertura de hoy)

| prioridad | acción | fichero:línea | coste |
|---|---|---|---|
| 1 | Archivar fotos 5-min desde `provider_bridge` | `scripts/provider_bridge.py` (junto al `os.replace` de `opt_chain_<sym>.txt`), copiando `scripts/opt_chain_cache.py:303-306` | 3 líneas; **el único daño que crece cada hora** |
| 2 | Gate de `market_source` en el keepalive de ballenas | `scripts/opt_whale_keepalive.sh:4` ← patrón de `scripts/sox_keepalive.sh:9-18` | 10 líneas |
| 3 | Gate de `market_source` en `watchlist_quotes` | `scripts/fleet_keepalive_start.sh:227` ← patrón de `:238` | 1 línea |
| 4 | Que los tests no empujen al ntfy real | `tests/test_whale_tape.py:110` + `scripts/notify_short.py:19` (respetar `IBT_NOTIFY_PUSH`) | 2 líneas |
| 5 | Renovar el token Finviz Elite | `config/feeds.env` (`FINVIZ_AUTH3`, …8625) | acción de Yunior, no código |
| 6 | Lanzar `force_meter.py` como daemon | `scripts/fleet_keepalive_start.sh` | 4 líneas; devuelve la FUERZA a la brújula |
| 7 | Guarda horaria de `band_open_watch` | `scripts/fleet_keepalive_start.sh:350` ← copiar de `:378` | 1 línea; mata 163 relanzamientos/día |
| 8 | Callar `truth_lock` y `prints_archiver` | `scripts/truth_lock.py:516` + los dos plists a `--loop` | 15,2 MB/semana |

---

*Barrido: 2026-08-04 02:40–03:20 ET. No se modificó código, no se borró ni rotó ningún log,
no se mató ni reinició ningún proceso, no se lanzó TWS/Gateway, no se tocó git.*
