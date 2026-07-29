# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`.

## 🔴 SESIÓN 2026-07-29 (madrugada) — retomar y cerrar todo
- [ ] **"resume last two sessions, finish all pending. new: u can use codex now as helper and
      extra hands, also for hard deficcult tasks, calculos, etc." + "there are also some features
      another session was working on, make sure to complete those, delegate to codex as much as
      possible"** (Yunior 2026-07-29 ~02:45) — plan aprobado
      `~/.claude/plans/resume-last-two-sessions-sorted-penguin.md`. Estado: `en curso`.
      Hallazgos al retomar: Mac reiniciado 02:39 (flota launchd viva, 6 bridges 200 con código
      de anoche), relanzadores 09:31 MUERTOS por el reboot, DeepSeek RECARGADO ($1.65),
      posts-en-inglés ya hecho (d51e34d), `overnight_feed.py` escrito sin cablear, las 2
      sesiones de anoche murieron por session-limit a las 21:35 vigilando el short NQ/SQQQ.
      Cerrado esta madrugada (detalle en Done.md): relanzadores 09:31 rearmados (18731/18732),
      factor overnight NQ/Corea cableado y encendido, compass medido (1ª celda real
      CONTINUACION|f0|POS n=270 wr30 57,4% lo 0,514; pool 50,5%), barras KRX archivadas
      pre-truncado, alarma premium UW ampliada a capitanes con p97 propio, TradingAgents SKHY
      bear, X sentiment solo bajo demanda.
      Pendiente para RTH hoy: latencia cinta UW, cintas whale capitanes, TradingFlow 9:31,
      pasada visual Chrome, ficha 9:31 SKHY + estrangle TQQQ/SQQQ, buscador perpetuos en vivo.
- [ ] **"send codex to finish the widgets + ui nicer"** (Yunior 2026-07-29 ~03:40) — hecho:
      pasada codex a live.html (emojis, TODO comment) + RANCIA legible + "Vende"; verificado
      en Chrome, bridges redeployados. Falta solo la pasada visual en RTH con datos vivos.
- [ ] **"one branch + files are a mess, organize + agente caza-bugs al final"** (Yunior
      2026-07-29 ~03:55) — reorganización hecha (7af8b72a): logs/→119 logs, bots/→21 cpp+bins,
      artefactos fuera, TODOS 435→80 líneas a Done.md. Caza-bugs codex CORRIDO: 2 bugs reales
      (4 awaits sin timeout en chart_bridge — ARREGLADOS; from __future__ en
      fleet_backtest_audit — pendiente, colisiona con codex migración). Migración contrato C++
      logs de bots delegada a codex (en curso).
- [x] **TODOS.md fue VACIADO ~03:33 y RESTAURADO de memoria 03:50.** Forense: ningún script
      de la casa lo escribe (los 6 candidatos solo lo leen); la ventana coincide con agentes
      codex activos (uno además violó el "no commitees" — commit 23d4c537, contenido correcto,
      se conserva). Regla nueva: tras CADA codex, `git status` obligatorio + prohibición
      explícita de TODOS.md/Done.md en briefs.

## ⏳ ABIERTOS de sesiones anteriores (renumerados 2026-07-29, el detalle cerrado vive en Done.md)
- [ ] **TradingFlow 9:31 pícaro** (Yunior 2026-07-28 07:36) — leer la ventana TradingFlow vía
      Chrome a las 9:31 (expiry/side/aggressor/premium/volOI/IV). Chrome YA conectado; timer 9:25 armado.
- [ ] **Estrangle TQQQ 65C + SQQQ 50C 31jul ~$162 (presupuesto $150) + árboles 5 tickers +
      "investigate where the market will be moving based on options chain, priority qqq/spy"**
      (Yunior 2026-07-28) — ficha 9:31 HOY con spread real (optgate); premarket 04:30: TQQQ
      61,76 / SQQQ 46,35 / SKHY 127,41 (-2,1%, TA bear). FOMC mañana + MSFT/META mié + AAPL/AMZN jue.
- [ ] **"take look at chrome... improve logic and visuals, take screenshots"** (Yunior 2026-07-28)
      — baseline y post-redeploy capturados esta madrugada; pasada completa con datos VIVOS en RTH.
- [ ] **"avisame cuando comprar o vender"** (Yunior 2026-07-28 ~20:30) — relanzador 09:31 de
      today_alarm5 rearmado (PID 18731); la voz compra/vende con print desde las 9:31.
- [ ] **"predigo una caida brutal, compro etf invertido, avisame"** (Yunior 2026-07-28 ~20:35) —
      capitulacion_qqq rearmada para 09:31 (PID 18732); regla intacta: sin print no hay inverso.
      Nota 04:30: cuenta SIN posiciones; NQ +0,7% overnight — la cinta contradice el inverso hoy.
- [ ] **Migrar contrato C++ de logs de bots** (nuevo 2026-07-29): bridge_<sym>.log y
      <sym>_operations.log → logs/ con replay validado. `delegado a codex (en curso)`.
- [ ] **fleet_backtest_audit.py NO COMPILA en py3.9** (preexistente): `from __future__` fuera
      de sitio. (fleet_wfo.py era legacy Alpaca con guard anti-uso → backup 2026-07-29.)
- [ ] **5 features candidatas del caza-bugs codex 2026-07-29** (dato MEDIBLE ya archivado,
      filtro anti-overfit pasado; decide Yunior cuáles construir):
      (1) IV percentil 60d por símbolo (chain_full_* archivados) — compresión P10 = ruptura cerca;
      (2) decay de gamma por expiry en gex_snapshot (anticipar flip NEG→POS pre-OPEX);
      (3) RV(20 barras 1m) vs IV de cadena — premium caro/barato medible;
      (4) profundidad del book de opciones (marca THIN en opt_flow, veto liquidez falsa);
      (5) heatmap de concentración call/put por estrato ITM/ATM/OTM (coladas de gamma).
