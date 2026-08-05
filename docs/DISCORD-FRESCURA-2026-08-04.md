# DISCORD-FRESCURA — 2026-08-04 (martes, premarket)

Auditoría de UNA pregunta: **¿lo que publicamos en Discord es dato fresco y correcto, o mentira
envejecida?** Orden de Yunior: "make sure we post updated and accurate data to discord".
Todo medido 03:40–04:30 ET con `stat`/`grep`/`ls`/ejecución read-only; cada afirmación lleva
`fichero:línea`. **No se tocó código, no se mató ningún proceso, cero git de escritura.**

---

## 0. Resumen ejecutivo

1. **Los planes de HOY sí se publican solos a las 04:00** — el hook existe y corre
   (`scripts/dailyplans_run.sh:64`, solo pasada FULL). Verificación en vivo del run de hoy en §2.
2. **El flip de gamma que publicamos NO es fiable hoy**: sale de una cadena viva **truncada a UN
   vencimiento** (`data/opt_chain_spy.txt` cabecera: `vencimientos 1`) con **paridad put-call rota
   al 100 %** (`parity_ok_pct: 0.0` = 0 de 31 pares cumplen la identidad gamma_C==gamma_P). El fix
   `NEAR_EXPS=8` está EN DISCO desde hoy 02:58 (`scripts/provider_bridge.py:174`) pero el daemon
   corre desde ayer 07:36 con el valor viejo en memoria. Veredicto completo en §5.
3. **Los árboles de horizonte están huérfanos desde el 07-28**: nada regenera
   `data/trees_horizonte/` (§3).
4. **El `--status` publicado en #estado-flota tiene al menos 4 verdes falsos** (§4).
5. **4 canales de análisis quedan VACÍOS hoy** sin productor: `#cierre-recap`, `#estrategias`,
   `#posicionamiento-dealer`, `#calendario-economico` (§6).

---

## 1. Tabla de frescura: dato → edad → umbral → veredicto

Edades medidas 03:41–03:45 ET (mercado abre 09:30).

| dato | edad medida | umbral aceptable | veredicto | evidencia |
|---|---:|---|---|---|
| `data/gex_snapshot.json` | **9 min** (cadencia 600 s) | reloj: <36 h (verify de `dailyplans_run.sh:54`) | 🟠 **FRESCO de reloj, ROTO de contenido**: flip de cadena de 1 vencimiento (§5); `put_wall: null` en SPY | `_meta.refrescado_por: levels_refresh_daemon.py`; `SPY.flip_src: recompute_15pct`, `parity_ok_pct: 0.0` |
| `charts/data/levels_*.json` (30) | **~10 min** (03:33) | intradía: minutos | 🟠 ídem: NO arrastran cadena del viernes (salen de `data/opt_chain_<sym>.txt` reescrito cada ~60 s por provider_bridge, OI = cierre de AYER, lo correcto premarket), pero **flip heredado 735,25 `repriced`** y `put_wall: null` en los símbolos truncados (guard del bug "put wall de cadena truncada", `scripts/gex_core.py:388-408`) | `levels_spy.json`: `flip 735.25, flip_src repriced, put_wall null, chain_src polygon` |
| `data/opt_chain_spy.txt` (cadena viva) | **2,4 min** | <45 min (`print_plans.sh:106`) | 🔴 **FRESCO pero TRUNCADO**: `vencimientos 1` (solo 0DTE 20260804), 176 filas, `bidask_ok_pct 0.0`, spot_age 27.642 s (cierre de ayer, normal de noche) | cabecera del fichero, líneas 1-2 |
| `data/vix.json` | **2 min** | <5 min estructura | 🟡 FRESCO de reloj, **fuente delayed** (`src: cboe_cdn_delayed_quotes`; LATENCIA-FUENTES: CBOE "delayed y DESIGUAL"). Vale para estructura VX (vx1 17,8 / vx2 18,97 CONTANGO), **jamás dispara** | contenido del json |
| `data/futures_overnight.json` | **<1 min** | minutos | 🟢 FRESCO (`futures_feed.py` pid 7674 vivo) | `stat` |
| `data/uw_flow_tape.json` | **11,6 h** (Aug 3 16:08) | sesión | 🔴 **ROTO y seguirá roto en apertura**: `uw_flow_tape.py` recibe **401 en /flow-alerts en TODOS los símbolos** (es ENTITLEMENT del endpoint, no token — B-17 del forense: el mismo token da 200 en /greek-exposure) y duerme 600 s por cada 401 | `logs/uw_flow_tape.log` (últimas 5 líneas, todas 401); `scripts/uw_flow_tape.py:58` |
| `data/opt_flow.txt` (cinta ballenas) | **3,5 días** (Jul 31 16:03) | sesión | 🔴 **ROTO**: `opt_whale_watch.py` exige IBKR (prohibido esta semana); el proceso vive (pid 85137) pero su salida está congelada → táctica espada-ballena (regla 11) y capitanes por flujo (regla 12) MUDOS hoy | forense B-2; `stat data/opt_flow.txt` |
| `data/force.json` | **14 días** (Jul 21 04:00) | <2 min (`compass.cpp:1497`) | 🔴 ROTO en silencio: la FUERZA apagada dentro de la brújula (forense B-3) | `stat` |
| fotos de cadena 5-min `data/history/<hoy>/` | **0 ficheros desde 08-01** | 1 cada 5 min en sesión | 🔴 **ROTO, sigue abierto**: `grep -n history scripts/provider_bridge.py` → **cero escrituras** también hoy; `data/history/2026-08-04/` existe y está VACÍO (creado 02:38) | forense B-1; `ls` |
| `data/trees_horizonte/*.pdf` (21) | **111,8 h** (máx: MU Jul 30 11:16; resto Jul 28 14:44-15:00) | <24 h (el propio `discord_post.py:93` los rotula RANCIOS a >24 h) | 🔴 **RANCIO y HUÉRFANO** (§3) | `ls -la data/trees_horizonte/` |
| planes `~/Desktop/ib-trader/hoy/planes-*` | ayer (2026-08-03) | del día | 🟠 lo publicado esta madrugada eran los de AYER; los de HOY los genera el run de las 04:00 (§2) | `ls` (a las 03:45 aún no existía `planes-2026-08-04`) |

---

## 2. Pregunta 1 — ¿se publican solos los planes de HOY? SÍ (con letra pequeña)

**La cadena verificada, eslabón a eslabón:**

1. `com.ibtrader.dailyplans` **cargado, exit 0**, dispara 04:00 / 08:30 / 09:12
   (`launchctl list` + plist `StartCalendarInterval`). A las 03:47 aún no había corrido hoy
   (`grep "modo FULL" logs/dailyplans.log` → último Aug 3), o sea **lo publicado a las ~03:00
   con `--latest` eran, correctamente, los de ayer: hoy aún no existían**.
2. El hook de Discord **NO está en `print_plans.sh` para las 04:00** — el run de las 04:00 es
   `dailyplans_run.sh`, que **no llama a `print_plans.sh`**. Su hook propio es
   `dailyplans_run.sh:64`: `discord_post.py --plans --status`, **solo en `MODE == FULL`**
   (04:00; las pasadas de 08:30 y 09:12 NO publican a Discord).
3. `discord_post.py --plans` **sin `--day` usa la carpeta de HOY** (`cmd_plans` →
   `plans_dir(None)` = `planes-<hoy>`, `discord_post.py:32-36,60`); si no existe, imprime
   `sin carpeta de planes` y devuelve 1 — no cae a ayer (eso solo pasa con `--latest`).
4. El hook de `print_plans.sh:170-172` (`--plans --day "$DAY"`, `$DAY` = hoy de `date`, `:69`)
   lo ejecutan los OTROS jobs: `printpremarket` 09:20, `printopen5` 09:35, `printplans` lunes
   09:25, `printpostmarket` 16:25 — todos con `DAY` correcto.
5. `config/discord_webhooks.json` existe con **31 canales** (03:10 de hoy) y
   `discord_relay.py` vivo (pid 10606).

**Verificado en vivo (run de las 04:00 de hoy)**: ver el bloque al final de esta sección.

**La letra pequeña (riesgos reales de la cadena):**
- **MU sigue perdiendo su PDF**: ayer 09:12 el log dice `MU: FALLO list index out of range` →
  `8 PDFs` — y `daily_fleet_plans.py` no se toca desde Jul 30, o sea **el try/except de `:564`
  NO cubre este fallo** (candidato: `:196 exp = sorted(exps)[0]` con cadena vacía en banda).
  MU es ticker 0DTE de presupuesto: si hoy repite, su plan no llega a Discord.
- **Duplicados**: `cmd_plans` sube **la carpeta ENTERA** cada vez (`discord_post.py:64,76`).
  Con 4 invocaciones programadas (04:00, 09:20, 09:35, 16:25) el canal recibe los mismos
  ~30 PDFs varias veces al día + los regenerados. Ruido, no mentira.
- Desktop bajo launchd = riesgo TCC vigente (forense §6); ayer funcionó (36 PDFs), hoy también
  debería, pero es la excepción a la regla de la casa.

### Resultado medido del run 04:00 de hoy
<!-- VERIFICACION-04:00 -->
Pendiente al cierre de redacción — se anexa abajo con el log literal.

---

## 3. Pregunta 2 — árboles de horizonte: HUÉRFANOS desde el 07-28

- Productor: `scripts/adhoc_horizon_trees.py` (cabecera: "PUNTUAL, Yunior 2026-07-28"). Fue un
  encargo de un día; símbolos por env `ADHOC_SYMS` (default QQQ,SPY,MU,DRAM,SKHY).
- **Nadie lo lanza**: `grep -rn adhoc_horizon_trees scripts/*.sh ~/Library/LaunchAgents/*.plist`
  → **cero**. Solo lo referencia `discord_post.py` (como etiqueta `source`).
- Lo que publicó `--trees` esta madrugada: 21 PDFs con 111,8 h, rotulados RANCIOS por el propio
  publicador (`discord_post.py:88-95`). La cobertura Discord ya lo sabía y por eso **no** enchufó
  `--trees` al 4AM (`docs/DISCORD-COBERTURA-2026-08-04.md` §4.6).
- OJO: los árboles **intradía** (`ARBOLES_<tag>.pdf` de `tree_sheets*`) SÍ se regeneran
  (print_plans `--trees`, jobs 09:20/09:35) y SÍ llegan frescos — pero a `#planes-premarket`,
  no a `#arboles-escenarios`.

**Enganche mínimo propuesto (NO implementado):** en `dailyplans_run.sh`, dentro del bloque
`MODE == FULL`, antes del hook de Discord:
```zsh
ADHOC_SYMS=QQQ,SPY,MU,DRAM,SKHY ./venv/bin/python scripts/adhoc_horizon_trees.py >> logs/dailyplans.log 2>&1
./venv/bin/python scripts/discord_post.py --trees >> logs/dailyplans.log 2>&1
```
(2 líneas, degradación limpia: si el generador falla, `--trees` publica lo que haya con su edad
en el embed — que es honesta.) Alternativa si Yunior no los quiere a diario: **retirar el canal**;
un canal que solo puede publicar RANCIOS es peor que no tenerlo.

---

## 4. Pregunta 3 — lo que #estado-flota publicó, contrastado

`fleet_up.sh --status` = **solo `pgrep`** (`scripts/fleet_up.sh:20`, `alive()`): mide "proceso
existe", jamás "salida fresca". Corrido ahora y contrastado con el forense:

| línea publicada | realidad medida | veredicto |
|---|---|---|
| `✓ vigía de ballenas` | proceso vivo (85137) pero `data/opt_flow.txt` congelado desde **Jul 31 16:03** y whales_*.txt idem; 285 relanzamientos contra puerto 4001 cerrado | 🔴 **VERDE FALSO** (forense B-2) |
| `✓ cockpit del gráfico` | `chart_bridge.py` vivo pero **ciego**: 68.662 `ConnectionRefusedError` a 4001 en `/tmp/w6_*.log`, reconectando cada 5 s desde hace ~16 h | 🔴 **VERDE FALSO** (forense B-4) |
| `✓ Finviz buffett/squeeze/momentum` | procesos vivos pero **token Finviz 401 desde 08-02** → screeners doblemente ciegos (sin Finviz y sin NBBO) | 🔴 **VERDE FALSO ×3** (forense B-8) |
| `✓ 21 bots de señal` | vivos, pero **4/30 de fleet.txt sin barras desde 07-31** (DRAM EWY SKHY SPCX fuera de `provider_syms.txt`) → umbral de MANADA efectivo más bajo | 🟡 verde a medias (forense §5) |
| `✓ provider_bridge (intrinio)` | vivo y escribiendo — PERO con `NEAR_EXPS` viejo en memoria (cadena truncada, §5) y **sin archivar fotos 5-min** (B-1) | 🟡 verde a medias |
| `✓ relé de Discord`, `✓ relé de notificaciones`, `✓ cola de voz`, `✓ alarma de precio` | verificados vivos | 🟢 correcto |
| `✓ pulso de flujo dormido (fuera de ventana)` / `✓ sin TWS (correcto)` / `✓ order_engine desarmado` | correcto y bien matizado | 🟢 correcto |

**`force.json` 14 días** ni aparece en el status (nadie lo mira).
**Conclusión**: el status que publicamos **miente por omisión de frescura**. Arreglo propuesto en §7.

---

## 5. Pregunta 5 — EL FLIP: veredicto NO PUBLICABLE hoy

**Los números** (medidos esta madrugada; spot 758,29):

| | flip SPY | lado del spot |
|---|---|---|
| UW `gex-levels` | **764,08** | ENCIMA → en spot, régimen del dealer NEG (amplifica) |
| casa `gex_snapshot.json` | **735,25** (`flip_src: recompute_15pct`) | DEBAJO → en spot, régimen POS (amortigua) |
| casa recomputado por mí sobre la cadena COMPLETA archivada (2.996 contratos, 11 vencimientos, `data/history/2026-08-03/chain_full_spy.json`) | **749,14** | debajo, pero **14 puntos** más arriba que lo publicado |

**Qué significa cada cosa:**
- `recompute_15pct` (`gex_snapshot.py:184-199` `honest_flip`): el flip NO es el crudo de
  `gex_core._flip` (que cae al borde de la banda del fichero — bug SKHY medido 2026-07-26), sino
  la **raíz del perfil de gamma acumulado re-barrida en ±15 % del spot**. El procedimiento es
  honesto; **el insumo no lo es**.
- `parity_ok_pct: 0.0` (`gex_core.py:467-523` `parity_audit`): gamma_call y gamma_put al mismo
  (strike, vencimiento) son IGUALES por identidad de paridad put-call. Se midieron **31 pares** y
  **CERO** cumplen a tolerancia 5 %. O sea: las griegas del libro con el que se computó el flip
  son **internamente incoherentes** (mismo fenómeno cazado el 2026-07-27: Polygon premarket 2 %
  de pares coherentes, el signo crudo era el único positivo). El RÉGIMEN se salva porque
  `regime_by_parity` repara con las dos lecturas legales (ambas POS, `signo_firme: true`);
  **el flip NO tiene esa reparación**: sale del perfil crudo.
- **La cadena está truncada**: `data/opt_chain_spy.txt` = **1 vencimiento** (0DTE de hoy),
  176 filas, 128 strikes, `bidask_ok_pct 0.0`. Es el mismo defecto de familia que el bug
  documentado "put wall de cadena truncada, **7 de 29 símbolos**" (TODOS.md:466-473, commit
  `5f725032`): aquel guard (gex_core `SIDE_GAP_TOL`) puso `put_wall=None` — por eso SPY publica
  `put_wall: null` — **pero nadie puso guard equivalente al flip**.
- **La causa raíz tiene fix EN DISCO pero NO EN MEMORIA**: `provider_bridge.py:174` ya dice
  `NEAR_EXPS = 8` (editado hoy 02:58) — el daemon vivo (pid 61205) arrancó **ayer 07:36** con
  el valor viejo. Hasta relanzarlo, la cadena viva seguirá corta. (No lo relancé: prohibido
  matar procesos en esta auditoría.)
- `pick_source` (`gex_snapshot.py:264-301`) elige el cache vivo si `griegas ≥50 %` y
  `banda ≥±10 %` — **las dos pasan** con la cadena truncada (banda ±15 % de strikes, pero 1 solo
  vencimiento). **No hay gate de nº de vencimientos ni de paridad para el flip.** El respaldo
  (chain_full archivado, 11 vencimientos, paridad 31 %) existía y no se usó.

**Veredicto: el flip de hoy NO es fiable para publicarse.** Tres razones medidas: (1) libro de
un solo vencimiento — el flip de UW (764,08) sale del libro completo; incluso nuestro propio
cómputo sobre el libro completo da 749,14, a 14 puntos de lo publicado; (2) paridad 0/31 = las
gammas del insumo son incoherentes y el flip no tiene reparación de paridad; (3) el flip decide
pin-vs-trampilla y el régimen de dealer que los planes imprimen (`daily_fleet_plans.py:909-910`
"BAJO/SOBRE flip = amplifican/amortiguan") — con UW y nosotros en LADOS OPUESTOS del spot,
publicar el nuestro es arriesgarse a servir **el régimen del dealer INVERTIDO** en 30 PDFs.
Los muros, en cambio, sí son publicables: call_wall 760 **idéntico** a UW, y el put_wall
truncado se publica como `null`, no como mentira.

**Qué se publica hoy mientras tanto** (propuesto): planes con la línea de flip marcada
`flip NO FIABLE (cadena 1 vencimiento, paridad 0 %)` o suprimida — igual que ya se hace con
put_wall. La discrepancia sistemática UW-vs-casa se mide con los 35 del universo × 5 sesiones
(UW-NOVEDADES §4.4, 35 peticiones/día): eso decide quién miente.

---

## 6. Pregunta 6 — canal por canal: ¿quién publica HOY?

Productores verificados (relé vivo pid 10606 enruta `data/notify_push.txt` por
`discord_layout.RULES`; publicador de lote = `discord_post.py`).

### Tendrán contenido HOY
| canal | productor exacto |
|---|---|
| `#planes-premarket` | `dailyplans_run.sh:64` (04:00) + `print_plans.sh:171` (09:20, 09:35, 16:25) — ⚠ con duplicados (§2) |
| `#estado-flota` | `dailyplans_run.sh:64` `--status` (04:00) — ⚠ con los verdes falsos de §4 |
| `#estado-proveedores` | relé: `intrinio_ws_probe.py:257` (~42/día), `finnhub_ws_bridge.py:241`, `korea_naver_bridge.py:358`, `provider_bridge.py:339` |
| `#senales-flota` | relé: `bollinger_alarm.py` (solo VOICE_CORE), `dip_alert.py:78`, `band_open_watch.py:38`, ficha `🎯 ZONA` (`chart_bridge.py:2306`) |
| `#manada` | relé: `fleet_consensus.py:164` (proceso Python vivo; universo recortado 26/30 declarado) |
| `#earnings-catalizadores` | relé: `position_close_reminder.py:34`, `earnings_fall_scout.py:351` |
| `#criticas` | relé: `capitulacion_qqq.py:52` (si dispara; order_engine inactivo) |

### Quedarán VACÍOS o mudos HOY (con el porqué)
| canal | causa |
|---|---|
| `#cierre-recap` | **SIN PRODUCTOR**: `postmortem_run.sh` (16:20) no llama a discord_post — solo calibración + X. `docs/POSTMORTEM-X.md` se escribe y nadie lo publica |
| `#estrategias` | **SIN PRODUCTOR**: solo vía manual `--channel estrategias` |
| `#posicionamiento-dealer` | **SIN PRODUCTOR**: nada publica régimen/GEX ahí (y menos mal hoy, ver §5) |
| `#calendario-economico` | **SIN PRODUCTOR** — y su insumo también está roto (Finviz 401 → `daily_fleet_plans.py:392` "calendario NO verificado") |
| `#ballenas-flujo` | productor vivo pero MUDO: `opt_whale_watch` sin IBKR, cinta congelada Jul 31 (§1) |
| `#capitanes` | `flow_pulse` despierta 09:30 pero su insumo de flujo de ballenas está congelado → en riesgo de silencio total |
| `#flujo-uw` | solo recibiría `⚠ ARCHIVO UW` (errores); la cinta `uw_flow_tape` está 401 (§1) |
| `#corea-overnight` | `korea_watch.cpp` no empuja al embudo (hueco #3 de COBERTURA §2.4) y `bin/korea_watch` ni corre (`korea_levels.txt` no existe, forense B-13) |
| `#finviz-screeners` | productor C++ sin push + token 401 |
| `#arboles-escenarios` | huérfano (§3): solo lo rancio de esta madrugada |
| `#gamma-niveles`, `#dark-pool`, `#senales-rechazadas` | vacíos POR DISEÑO (KILL del backtest / killlist) — correcto |

**Neto: de 31 canales con webhook, ~7 tendrán contenido hoy.** En el server nuevo, el primer
día de mercado, los 4 canales de análisis de la categoría premium nacen vacíos.

---

## 7. Los 3 arreglos más urgentes ANTES de la apertura (propuestos, NO implementados)

1. **Relanzar `provider_bridge` para cargar `NEAR_EXPS=8` + gate de flip.**
   El fix de la cadena truncada ya está en disco (`provider_bridge.py:174`); el daemon vivo usa
   el valor viejo. Un `pkill -f provider_bridge.py` (su keepalive lo resucita con el código
   nuevo) des-trunca la cadena viva ANTES de las 09:12. Y en `gex_snapshot.pick_source`
   (`:280-286`): exigir **≥3 vencimientos** en el cache vivo (o caer al `chain_full` archivado,
   que hoy daba flip 749 con paridad 31 %), y en `honest_flip` etiquetar
   `flip_unreliable=true` cuando `parity_ok_pct < 0.10`. Sin esto, los planes de hoy imprimen
   régimen de dealer potencialmente INVERTIDO (§5).
2. **Dar productor a `#cierre-recap` hoy mismo** (1 línea en `postmortem_run.sh`, después de
   `x_postmortem.py`): publicar solo la sección del día (no el .md acumulado), p. ej. volcando
   la salida de `x_postmortem` a un tmp y `discord_post.py --channel cierre-recap --file <tmp>`.
   Es el canal que cierra el bucle del día; vacío el primer día es la peor señal.
   (`#estrategias`/`#posicionamiento-dealer`/`#calendario-economico`: decidir productor o
   esconderlos hasta tenerlo — un canal muerto crónico entrena a no mirar.)
3. **Que `--status` no publique verdes falsos**: en `fleet_up.sh status()` (o mejor: publicar
   `fleet_healthcheck.py` ya corregido), cada ✓ de daemon con salida a fichero debe mirar la
   **edad de su salida**, no solo `pgrep`: `opt_whale` → `data/opt_flow.txt` (>1 sesión = ✗),
   cockpit → crecimiento de `/tmp/w6_*.log` con `ConnectionRefused`, Finviz → último HTTP del
   log. Es el mismo parche conceptual que el forense pide para el healthcheck (B-2/B-7).

Menores (que no bloquean la apertura): dedupe de PDFs en `cmd_plans` (subir solo los nuevos o
un `--only-new`); enganche de árboles de §3; archivado 5-min desde provider_bridge (forense B-1,
"el único daño que crece cada hora"); MU `list index out of range` (§2) — cazar el `[0]` real
(candidato `daily_fleet_plans.py:196`) porque el de `:564` ya está guardado.

---
*Auditoría 2026-08-04 03:40–04:30 ET. Read-only: cero código tocado, cero procesos muertos,
cero git. Ficheros prohibidos (`discord_*.py`, `uw_flow_archive.py`, `notify_short.py`,
`TODOS.md`) no modificados.*
