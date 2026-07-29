# TODOS — ib-trader

> Vivo. Apuntar cada petición AL MOMENTO con las palabras de Yunior. Lo cerrado → Done.md.

## 🔴 SESIÓN 2026-07-29 (madrugada, ráfaga ~07:05)
- [ ] **"tell codex to jump into repo with fresh context, explore, plan how to inspect
      1. calculos of compass arrow, missing features or weights, calibration"** — delegado a
      codex A (informe+plan, solo lectura).
- [ ] **"2. create new skills after exploration or search from github and copy paste them,
      more than 10 new skills plus at least a few plugins related to our repo"** — delegado a
      codex B.
- [ ] **"3. inspect ui ux, how we implement modern features similar to spotgamma, trendspider,
      tradingflow, UW... strong, pro and portable. 5. make sure ui is expensive... non
      vibecoded... search github skills for it"** — delegado a codex C.
- [ ] **"6. inspect signals, all signals, add what is missing, fix as needed, calibrate, be
      picaro"** + referencia ChatGPT (GEX/DEX/vanna/charm, vol trading, dealer flows,
      dispersion, event-driven, term structure, skew) — dentro de codex A (plan) → ejecución
      tras aprobar.
- [ ] **"do we need to enable level 2 data in ibkr?"** — respondido: no imprescindible hoy;
      SÍ si queremos el liq_map con profundidad de libro real (Bookmap de verdad). Decide Yunior.
- [ ] **"make sure that even the beautiful spanish voice we have is portable in macos app, all
      portable, send codex agent to inspect that, tell it to create skill for macos app
      creation, tell it to search github for skills"** (Yunior 2026-07-29 ~07:45) — delegado
      a codex: portabilidad de la voz española en la .app + skill macos-app-creation.
- [ ] **"tiny info buttons for widgets explaining the features"** (Yunior 2026-07-29 ~07:55)
      — delegado a codex (live.html).
- [ ] **"i heard a test voice now, i dont like that one, only the beautiful spanish voice we
      have already, only that one"** (Yunior 2026-07-29 ~07:55) — corregido el brief del codex
      de voz: SOLO la voz canónica de la casa; sin voz instalada = silencio + aviso visual +
      guía de descarga; JAMÁS fallback a otra voz ni tests sonoros.
- [ ] **"al abrir app en otra mac la voz ya deberia estar, no hay necesidad de agregar tareas
      al usuario"** (Yunior 2026-07-29 ~08:15) — delegado a codex: TTS neuronal es_ES
      EMPAQUETADO en la .app (la voz viaja con el bundle; voz del sistema solo si ya es la
      Siri española del Mac de Yunior; jamás pasos manuales).
- [x] **"send codex to debug compass overnight, dont think its working"** (Yunior 2026-07-29
      ~06:00) — hecho (codex): causa raíz = `why[:5]` cortaba la línea overnight en QQQ +
      `except: pass` silencioso. Fix en `scripts/direction_view.py:274-290` (fail-loud +
      `why.insert(0, og_why)`); 15 tests verdes, verificado por Claude 2026-07-29.
- [ ] PENDIENTE derivado: la FLECHA del cockpit sale de `compass.cpp` (C++), que NO lee
      `data/overnight_ctx.json` — direction_view aplica overnight pero la flecha del chart
      no lo ve. Implementar overnight_coef en compass.cpp + recompilar
      (`scripts/build_compass.sh`). (2026-07-29, pendiente — decisión de Yunior si va al C++)
- [ ] "relanza todo, build macos new version" (Yunior 2026-07-29, en curso — rebuild .app Cockpit en macOS 26.5.1 + relanzar flota)
- [ ] "send agent to review finviz failure" (Yunior 2026-07-29, delegado a agente)
- [ ] Mudanza feeds.env->config/ dejada A MEDIAS: 17 consumidores leen la raiz (finviz_scout.cpp:92, x_whale_bot.cpp:365, notify_relay.sh:14, picaro.sh, weekly_autoimprove.sh, daily_fleet_plans.py:77, options_hunter.py, polygon_dl.py, poly_client.py, ta_view.py, real_option_scorer.py, reconstruct_flow*.py x3, finviz_auth_check.py, earnings_fall_scout.py, yoel_real_options_backtest.py). PARCHE ya puesto: symlink raiz feeds.env->config/feeds.env (gitignored, no viaja). Falta el barrido durable a config/feeds.env + recompilar los 2 .cpp. (2026-07-29, hallazgo del agente finviz, pendiente)
