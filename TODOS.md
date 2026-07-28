# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.

  do it at 9:31, be picaro"** (Yunior 2026-07-28 07:36). La ventana TradingFlow está abierta en
  su Chrome; leerla a las 09:31 vía extensión (la sesión del agente auditor NO tenía la extensión
  conectada — hacerlo desde la sesión principal). Referencia: flujo MU del cierre 27-jul pegado
  por Yunior (spot ~900,4; calls 925/940/950 31-jul, puts 850/860, 0DTE 890/895 vol/OI 268-507x).

  `korea_bar_bridge` trunca `bars_samsung/skhynix/kospi.txt` en cada sesión y
  `daily_archive` solo guarda los 30 US → los TERREMOTO Corea de la sesión anterior
  quedan inverificables (5 del 27-jul sin barra). Copiar el patrón de
  `data/history/<fecha>/bars/` para los 3 KRX.
> Doctrina: skills `gamma-regime-walls`, `postmarket-cage-release`, `tradingview-terminal`.
# TODOS — ib-trader (sistema autónomo de planes + alarmas)


## 🔴 SESIÓN 2026-07-25 (noche) — peticiones de Yunior, apuntadas AL VUELO
> Plan completo aprobado: `~/.claude/plans/create-plan-to-finish-glimmering-pascal.md`.
> Orden acordado: FASE 0 higiene → 1 señales → 2 flecha → 2.5 TradingAgents → 3 muros
> → 4 UI/UX → 4.5 X earnings → 5 los 9 bugs → 6 deploy → 7 seis ventanas + QA → 8 verif → 9 features minadas.

  korean tickers"** (Yunior 2026-07-26). El buscador se arreglo hoy (e94cf04: listener `input`
  + `_prime_bars` sincrono), pero NO se probo con: (a) los perpetuos 24/7 nuevos
  (`data/perp_stocks.json`, 26 simbolos Bybit), (b) los tickers coreanos (Samsung/SK Hynix/
  KOSPI, que van por `korea_bar_bridge`). Probar los dos casos.







## 🌙 QQQ DÍA Y NOCHE (Yunior 2026-07-27: "we should be able to monitor and see charts for qqq
## day and night") — MEDIDO, y el hallazgo es que la noche NO se puede recuperar
- [x] **Día y premarket: FUNCIONA hoy.** Verificado lun 08:09 con la flota viva: bridge QQQ
      (:8080) sirve **1.920 barras**, spot **694,16** en vivo, CW 700 / PW 680 / flip 696,22,
      137 strikes, `walls_unavailable: null`. `useRTH=False` en las 3 rutas de `chart_bridge.py`
      (`:1596`, `:1644`, `:2603`) → premarket y after-hours entran. Barras de HOY: 60/hora
      continuas de 01:00 a 08:09.
- [x] **[CERRADA — el fix de los CAPITANES funciona] Verificar EN VIVO que los DOS CAPITANES
      reciben cinta firmada.** Llevaba semanas sin poder cerrarse porque solo se puede observar con
      el mercado abierto. MEDIDO hoy 09:09: `data/whale_qqq.txt` **59.061 B**, `whale_spy.txt`
      **43.868 B**, `whale_smh.txt` **15.584 B**, los tres con mtime del minuto en curso. El sábado
      estaban a **0 bytes**. `CAPTAINS_FIRST` (`ibkr_bar_bridge.py:62`) hace su trabajo: los
      capitanes se suscriben PRIMERO y por eso son los que tienen cinta. La **regla 12** ya no se
      alimenta de un input vacío.

## 🔴 SESIÓN 2026-07-27 (RTH, mercado abierto) — peticiones al vuelo
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





## Ráfaga Yunior 2026-07-28 00:40



## Ráfaga Yunior 2026-07-28 00:50



- [ ] **"take a look at tradingflow, i have the window open in chrome, do it at 9:31, be
      picaro"** (Yunior 2026-07-28 07:36) — leer la ventana TradingFlow viva a las 9:31 vía
      Chrome, lectura pícara de flujo (formato: expiry/side/aggressor/premium/volOI/IV/sentiment).
      `programado 9:31 (timer armado)`

- [ ] **"revisa el repo, explora, crea un repo map, con clases y top level functions, send minor
      agent for it"** (Yunior 2026-07-28 ~09:05) — `delegado a agente sonnet`
- [ ] **"prueba que el compass no tiene 60 percent o sesgo fijo todo el tiempo, prueba la
      calibracion y backtest con real data"** — distribución de probs en RTH + calibrate con
      ledger real de hoy + backtest. `en curso (medición durante la mañana)`

- [ ] **"make sure we have latest builds running when done. verify the walls and magnets in
      symbols are ok, asegura de incluir probabilidad, no inventos"** (Yunior 2026-07-28 08:15)
      — `en curso (yo)`
