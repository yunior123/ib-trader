# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.
> Doctrina: skills `gamma-regime-walls`, `postmarket-cage-release`, `tradingview-terminal`.
# TODOS — ib-trader (sistema autónomo de planes + alarmas)


## 🔴 SESIÓN 2026-07-25 (noche) — peticiones de Yunior, apuntadas AL VUELO
> Plan completo aprobado: `~/.claude/plans/create-plan-to-finish-glimmering-pascal.md`.
> Orden acordado: FASE 0 higiene → 1 señales → 2 flecha → 2.5 TradingAgents → 3 muros
> → 4 UI/UX → 4.5 X earnings → 5 los 9 bugs → 6 deploy → 7 seis ventanas + QA → 8 verif → 9 features minadas.

- [ ] **[pendiente] "make sure tickers search work as expected. test with perpetuals plus
  korean tickers"** (Yunior 2026-07-26). El buscador se arreglo hoy (e94cf04: listener `input`
  + `_prime_bars` sincrono), pero NO se probo con: (a) los perpetuos 24/7 nuevos
  (`data/perp_stocks.json`, 26 simbolos Bybit), (b) los tickers coreanos (Samsung/SK Hynix/
  KOSPI, que van por `korea_bar_bridge`). Probar los dos casos.

- [ ] **[pendiente — el bloqueante de "IBKR primario"] ensanchar `opt_chain_cache.py`** (medido
      2026-07-27, es de otro agente). Orden de Yunior: *"elige ibkr real, polygon only fallback for
      realtime market"*. El gate ya existe y declara la procedencia en el dato
      (`gex_snapshot.pick_source`, `chain_src`/`source_why`), con las dos constantes YA medidas del
      repo: griegas ≥ `book_quality.MIN_GREEKS_SRC` (0,50) **y** ancho ≥
      `poly_chain_archive.BAND_FLOOR` (0,10). Pero **IBKR gana 0/26 hoy**: su cache es de
      **±1,3%–7,1% de ancho, 20 strikes y 2 vencimientos**, donde la gamma necesita ±18%–60%.
      Aunque sus griegas llegasen al 100% no puede llevar el régimen sin reabrir el bug del
      recorte (`5a6a34e`). Hasta que `max_strikes 20` cubra la banda adaptativa, "IBKR primario"
      es correcto en el código y **inalcanzable en el dato**, y el régimen lo sigue firmando
      Polygon/CBOE con su procedencia dicha.

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

- [ ] **[pendiente] organizar el proyecto, ahora mismo hay muchos archivos regados como tsm_signal_bot.cpp, y otros en el mismo nivel, muchos. separate logs to logs folder.

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

## 🔴 SESIÓN 2026-07-27 (RTH, mercado abierto) — peticiones al vuelo
- [ ] 🔴 **[pendiente] "some old voices from a long time are still running, replace them properly,
      same with alarms"** (Yunior 2026-07-27). Hay voces/locuciones y alarmas de hace tiempo aún
      corriendo (procesos viejos, cron viejo, o binarios no redeployados). Identificarlas
      (`ps`, `voice_log`, launchctl) y reemplazarlas por las versiones vigentes, sin dejar dos
      hablando a la vez.
- [ ] **[pendiente] Ventana: buscar info igual desde dom 20:00 (o antes, premarket Corea ~19:00) y
      chart con PRECIO REAL día Y noche hasta vie 20:00** (Yunior 2026-07-27). "from 8pm on sundays
      or before in korea premarket at around 7, search info anyway. till friday at 8pm we see the
      chart with the real price, whether day or night." → el chart debe mostrar precio real 24h en
      la ventana viva (perpetuos 24/7 + Corea de noche + US de día), no quedarse mudo por la noche.
      Relacionado con la cinta nocturna irrecuperable (solo se captura en vivo) y con `fleet_hours`.
- [x] **[hecho 514a38a/516d3e9 — agente UW] UW latencia MEDIDA en sesión viva: 5,5 s → candidato a
      tiempo-real** (09:31 EDT, primera medición intradía; el sábado 43,8 h = fin de semana, cero
      evidencia). SIGUE SIN VOZ (caduca ~2026-08-01, regla gexa: archivar→medir→cablear). +
      `uw_oi_delta.py` (ΔOI apertura/cierre, descriptivo sin voz) + 3 dossieres de vendedores
      (tradytics/optioncharts/quanted, ninguno con API usable). Hallazgo: CBOE Open-Close Volume
      Summary es la versión MEDIDA de ΔOI, 1 día EOD calibra sin suscribir.
- [x] **[CAUSA RAÍZ hallada — agente UW] "whale options alarmas no funcionaban hoy": `opt_whale_watch`
      corría una versión VIEJA (arrancada 00:46) que golpea el puerto 4002; el fix del puerto
      dinámico es `658cc52` (01:03), POSTERIOR. Nunca conectaba → cinta ciega → las 2 voces de hoy
      fueron "DANGER CINTA CIEGA", jamás una ballena real.** El agente B ya reinició el proceso
      (conecta a 4001 limpio). VERIFICAR que quedó vivo y disparando.

- [ ] **[ACCIÓN DIFERIDA con hora — tras cierre KRX ~02:30 ET, o mañana antes de US open]
      Desplegar los binarios coreanos + skhy** (agente RTH, ). Los 3 coreanos siguen con
      binario viejo (su horario 930 KST es correcto, no urgente) y skhy tiene el  staged +
      SKHY_SPREAD_MAX ya en el keepalive. Comando exacto:
      
      
      No se automatizó a propósito (un pkill sin supervisión a las 02:35 rompe la flota si algo falla).
