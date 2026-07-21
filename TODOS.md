# TODOS — ib-trader (sistema autónomo de planes + alarmas)

> Vivo. Marcar [x] al cerrar. Manual completo: `docs/DAILY-SYSTEM.md`. Doctrina: skills `gamma-regime-walls`, `gexa-terminal`, `postmarket-cage-release`, `tradingview-terminal`.

## ✅ HECHO (2026-07-20/21)
- [x] Post-mortem imanes 2026-07-20 (hacia el imán, jamás a través del muro; decay por toques)
- [x] Investigación NOK (crash = Ericsson AI-cost read-through; 40% layoff = sin evidencia; earnings 23-jul BMO)
- [x] SPY añadido a la flota (bot C++ + keepalive)
- [x] Impresora: Brother NO era tuya (removida); HP 9120e bloqueada por tinta color (firmware HP+); PNGs a Desktop
- [x] Árboles de escenarios NOK/NVDA/QQQ/SPY + estrategias con opciones a Desktop
- [x] Estudio gexa.ai → régimen gamma; skills `gexa-terminal` + `gamma-regime-walls`
- [x] 26 skills por ticker + `korea-memoria` con patrones 6m + forma intradía 60d (`skill_patterns_refresh.py`)
- [x] Sistema diario: launchd `dailyplans` (04:00/08:30/09:12) + `postmortem` (16:20)
- [x] Generador 26 tickers (IBKR-first, gexa, VX CBOE, Finviz, Korea, futuros, griegas, árbol, forma)
- [x] Calibración empírica por setup×régimen (Wilson, no por ticker) — `calibration_ledger.py`
- [x] Patrones medidos (H&S/dobles/triángulos, follow-through empírico) — `pattern_detect.py`
- [x] Engranaje QQQ/SPY (amplitud ponderada de componentes) — `index_breadth.py`
- [x] Posters X: premarket/realtime/postmortem, ledger 10/día $4/mes, humor, "No consejo fin."
- [x] Draft X compacto+visual (escalera emojis 🔴🎯📍🟢🛑) + Corea semis + tendencia overnight
- [x] `force_meter.py` — fuerza/agotamiento en vivo (4 fases → acción de stop)
- [x] `posthours_cage.py` — picardía jaula 0DTE→liberación after-hours (ballenas semanales)
- [x] Healthcheck 3x/día auto-curador (`fleet_healthcheck.py`, launchd)
- [x] Flota canónica única `data/fleet.txt` (26) — nadie queda atrás
- [x] Alarmas flujo put/call alineadas a 21 tickers; DB limpia; cadena notificación verificada
- [x] X auth verificado (@YuniorR62327146, 200 OK, read-only, sin gastar post)
- [x] Tests Python 48 pasan (incl. put-call parity); bug arreglado (main() sin guard en generador)
- [x] TradingView: zoom inspección + zoom chart verificados; skill documentada

## 🔄 EN CURSO / PENDIENTE
- [x] Magnets gexa dominados: find→scroll_to ref→read_page (estructurado, no screenshot); parser gexa_parse los captura
- [x] X posts scheduled cada día verificado (4AM premarket + realtime daemon + 16:20 postmortem)
- [x] Auto-mejora semanal (domingo 19:00): refresca patrones/formas 6m + recalibra + corre tests + reporta
- [x] Conocimiento consolidado en LEARNED.md + skills + memoria; herramientas reutilizables xpost.py + gexa_parse.py
- [x] **Europa para ASML**: momentum Ámsterdam (ASML.AS ~6h lead) + STOXX50 al plan+draft (prob bump, línea 🇪🇺)
- [x] Tests C++23: 25/25 correctness pass + benchmark (Bollinger 9.46ns/op, resto inline, 0 bugs)
- [ ] Verificar gexa headless conecta REALMENTE en el run de 4am (Chrome/extension sin sesión interactiva)
- [ ] Raíz del `com.ibtrader.fleet` exit=78 (EX_CONFIG) — hoy se sortea con el healthcheck que relanza; falta arreglar el porqué bajo entorno launchd
- [ ] Primera cacería REAL de jaula-liberación (lunes al cierre, cuando el after-hours vive)
- [ ] Documentar force/cage/healthcheck/breadth en `docs/DAILY-SYSTEM.md` (parcial)

## 💡 IDEAS / FUTURO (cuando se pidan)
- [x] Tweets con imagen adjunta (árbol PNG en x_media/) + gexa gamma (flip/dealer/POC) en posts intradía
- [ ] `opt_tick_watch` event-driven para el strike ACTIVO (tiempo real, no poll 5min) — filo de ejecución
- [ ] Fuerza/agotamiento por-tick plegada en los signal bots C++ (si se quiere el filo en la decisión)
- [ ] Calendario macro (CPI/FOMC/NFP) al PDF — "no operar el print"
- [ ] Revisar plan Polygon (POLYGON_KEY en feeds.env, quizá opciones/agregados mejores)

## 📌 REGLAS QUE NO SE ROMPEN
- Señal-solamente (jamás ordena). Aditivo + degradación limpia. Respaldo en `backup/` antes de tocar el generador.
- Presupuesto opciones = SOLO 0DTE (semanales requieren excepción explícita).
- `notify_relay.sh` DEBE estar vivo (fue el fallo de notifs). Print o nada. 3 pérdidas = fin.

## 2026-07-21 sesión viva
- [ ] opt_whale_watch: filtrar strikes sin security definition (QQQ 712.5 20260724 spamea Error 200 en loop) — cachear contratos inválidos y saltarlos. Arreglar POST-CIERRE.
- [ ] launchd exit 78 (fleet/scan/screener/fastscan/rescan/screener6am) + healthcheck exit 1 — cazar EX_CONFIG con calma post-cierre.
