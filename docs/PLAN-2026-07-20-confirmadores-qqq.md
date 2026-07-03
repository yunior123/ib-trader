# Plan lunes 2026-07-20 — confirmadores de QQQ + skill Grok

Decidido con Yunior 2026-07-18 (finde). NO ejecutado aún (flota apagada por descanso).

## 1. Skill tradermonty/claude-trading-skills
- **Claude: YA instalada y activa** (plugins en cache, cargados en el índice de skills:
  trading-market-analysis, trading-stock-screeners, equity-research, trading-portfolio-risk,
  trading-earnings-timing, trading-strategy-tools, trading-indicators).
- **Grok: descargada pero NO activa** — solo `~/.grok/marketplace-cache/`; falta instalar en
  `~/.grok/skills/`. TODO lunes: activar el marketplace en Grok.

## 2. Confirmadores de QQQ — qué añadir a la flota

Principio: un confirmador vale solo si puede DIVERGIR del índice (como SMH diverge = señal).

- **XLK (SÍ)** — tech S&P puro, sub-índice real, puede divergir de QQQ. Cierre vie: 177.52.
  contract_id ARCA 4215230.
- **AVGO (SÍ, prioritario)** — semis + top-5 peso de QQQ, hoy NO lo seguimos. Cierre vie: 374.45.
  contract_id NASDAQ 313130367.
- **MSFT + META (SÍ)** — pesos pesados de QQQ que faltan. QQQ se mueve por sus magníficos;
  ya seguimos NVDA/AAPL/GOOGL/TSLA, faltan estos.
- **TQQQ / SQQQ (NO como confirmadores)** — son QQQ×3 y QQQ×−3, derivados matemáticos exactos,
  NO pueden divergir → redundantes con la alarma de QQQ. Son vehículos de EJECUCIÓN
  (apalancamiento direccional), no señales. Solo armar alarma si Yunior los va a operar como
  vehículo, no para "entender QQQ".

## 3. Ejecución lunes (al reencender la flota)
1. Añadir XLK, AVGO, MSFT, META a la lista de símbolos de la flota (feeds bars + nbbo).
2. Fijar alarmas con la estructura del día (VWAP + muros de opciones), NO niveles de finde:
   - XLK: nivel clave = ruptura/pérdida de VWAP + muro OI dominante (mismo método que SMH).
   - AVGO: idem, es el que más aporta por peso+semis.
3. NO crear alarmas TQQQ/SQQQ salvo petición explícita de trade apalancado.

Ver [[options-flow-in-analysis]] y AGENTS.md ley confirmadores sectoriales (SMH).
