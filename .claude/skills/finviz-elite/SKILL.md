---
name: finviz-elite
description: Datos Finviz Elite en tiempo real que IBKR no da — short float, insider, float, gaps, earnings dates, screener, ratings. Usar para premarket, day trading, o cuando Yunior pida datos fundamentales/screener rápidos. Incluye el scout C++ y las alertas por email.
---

# finviz-elite — la capa de datos que IBKR no ofrece (creado 2026-07-17)

Tokens en `feeds.env` (GITIGNORED): `FINVIZ_AUTH` (cta 1), `FINVIZ_AUTH3` (cta 3).
**URL nueva `/export/screener?...` — la vieja `.ashx` devuelve VACÍO** (verificado 2026-07-17).
Rate limit: 1 request por ciclo (todos los tickers en un `t=`), mínimo 60s entre requests.

## 1. Por-ticker (fundamentales + técnica que IBKR no da)
```bash
source feeds.env
curl -s "https://elite.finviz.com/export/screener?v=152&t=NVDA,MU,SPCX&auth=$FINVIZ_AUTH3&c=1,6,24,25,26,30,31,59,60,61,63,64,65,66,67,68,70"
```
Columnas verificadas: 1=Ticker 6=MktCap 24=SharesOut 25=Float 26=InsiderOwn
30=**ShortFloat** 31=ShortRatio 59=RSI(14) 60=ChangeFromOpen 61=**Gap**
63=AvgVol 64=**RelVolume** 65=Price 66=Change 67=Volume 68=**EarningsDate** 70=IPODate
Sondeadas 2026-07-17 (header CSV, posicional): **62=AnalystRecom** (numérico, menor=mejor)
**69=TargetPrice**; además 27=InsiderTrans 28=InstOwn 29=InstTrans 32-40=fundamentales
41-58=performance/SMA/52w 71=AH-Close 72=AH-Change 81=PrevClose 84=ShortInterest 85=Float%.
(Más columnas: probar empíricamente — el CSV devuelve el header con nombres, en orden ascendente de id.)
Joyas del día 1: SPCX short float 17.23% (explicó la violencia del -6% AH).

## 2. Screener (filtros custom — la URL del usuario)
```bash
curl -s "https://elite.finviz.com/export/screener?v=111&f=fa_div_pos,sec_technology&auth=$FINVIZ_AUTH3"
```
Filtros `f=`: sintaxis estándar finviz (sec_, ind_, fa_, ta_, sh_...). Presets Elite: 200.

## 3. finviz_scout (C++ + libcurl) — el bot (VIVO 2026-07-17)
`scripts/finviz_scout.cpp` → `./finviz_scout` (compilar: `clang++ -std=c++17 -O2 -o finviz_scout scripts/finviz_scout.cpp -lcurl`).
Keepalive `scripts/finviz_scout_keepalive.sh`, lanzado por fleet_keepalive_start.sh (tras candado fleet_sleep).
- Ciclo: 60s en premarket (4:00-9:30 ET), 180s en RTH, apagado fuera (chequeo 5 min; finde=OFF).
- Tickers: data/focus_ticker (US upper; salta kospi/samsung/skhynix/sleep) + SIEMPRE
  MSFT,AVGO,AMZN,META,QQQ,SMH; dedup. UN request → `data/finviz_{sym}.txt` (clave=valor,
  ts+time, escritura atómica). Columnas: base + 62=Recom + 69=TargetPrice (auto-validadas
  contra el header en el 1er fetch: si Finviz las mueve, se caen solas y se loguea).
- NOTIFICA (banner Mac + espejo Desktop, via fleet_notify.h) SOLO cambios de estado vs
  snapshot previo en memoria: gap >±2%, rel volume cruza 2.5x, short float ±0.5pt,
  earnings <48h (1/día/ticker, persistido en data/finviz_earn_notified.txt),
  target/recom cambian. PRIMER CICLO SIEMPRE SILENCIOSO (sin snapshot previo = sin spam).
- Token: env FINVIZ_AUTH3 > feeds.env FINVIZ_AUTH3 > FINVIZ_AUTH — JAMÁS hardcodeado.
- Robustez: HTTP≠200/CSV vacío/HTML/0 filas → log "FINVIZ ROTO" + banner UNA vez +
  backoff 5 min (429 incluido); banner de recuperación al volver. Mínimo 60s entre requests.
- Test manual: `./finviz_scout --once [SYM extra...]` (un fetch+parse+write, sin loop;
  exit 1 si el feed está roto). Log: finviz_scout.log.

## 4. Alertas por EMAIL de Finviz (canal extra a los banners Mac)
La export API es read-only — las alertas se configuran en la web (una vez):
1. elite.finviz.com → Portfolio → crear "fleet" con los tickers del día
2. En el portfolio: Notify → **Price** (niveles = espejo de price-alerts.txt),
   **News**, **Insider**, **Ratings**, **SEC Filings** → al email de la cuenta.
3. Con Claude-in-Chrome se puede automatizar si Yunior tiene sesión abierta
   (pedir permiso del sitio primero). Email destino: el de la cuenta Elite.

## Reglas
- Señal-solamente. Datos Finviz = confirmación/contexto; el print de precio manda.
- Si el CSV vuelve vacío o HTML → token/URL rotos: FALLAR EN VOZ ALTA (ley #6).
- No mezclar volumen finviz (consolidado) con volumen IEX de los bots en un mismo gate.
- **Claude way (2026-07-17):** consumers (`x_whale_bot`, agents) leen `data/finviz_*.txt` si frescos (<30m) ANTES de otro export; live solo si cache fría. Premarket: gap/short/AH mandan; RVOL overnight ~0.1x es ruido. Skill doctrina: `claude-way`. Obsidian: `~/Documents/Obsidian Vault/ib-trader/Finviz Elite.md`.
