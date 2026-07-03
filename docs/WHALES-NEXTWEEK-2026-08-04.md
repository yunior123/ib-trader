# BALLENAS — SEMANA PRÓXIMA (expirys 8/10–8/14) + resto de esta (8/5–8/7)
Martes 2026-08-04, corte 13:18 EDT. Complementa `NET-PREMIUMS-2026-08-04.md` (no repite esta semana).

Fuentes (todo medido, hora indicada):
- **Polygon snapshot** archivado hoy 13:08 (`data/history/2026-08-04/poly_chain_*_1308.txt`, oi/greeks polygon_directo) — 0 requests nuevas.
- **ΔOI lunes** = OI hoy 13:08 − OI lunes 16:20 (`2026-08-03/poly_chain_*_1620.txt`) = posiciones ABIERTAS el lunes.
- **UW flow-per-expiry** fresco 13:18 EDT (6 requests: MU SPY QQQ SMH NVDA SPCX); resto del crudo 12:36 (30 syms, ya pagado). Signed = (call_ask−call_bid)−(put_ask−put_bid).
- **Archivo ballenas local**: `uw_flow_per_strike_*` 8/3 (30 syms sesión completa) + 8/4 (5 núcleo, hasta ~13:10).
- GEX en $mil por strike = Σ gamma·OI·100·spot (call +, put −), solo expirys 8/10–8/14.

## TABLA VEREDICTO

| sym | expiry-clave | strike-imán (GEX) | muro call / put NW | signed NW (UW) | veredicto |
|---|---|---|---|---:|---|
| **MU** | 8/14 | semana: **900** (+918k); 8/14: **1000** (+464k) | 900 (8/10) + 1000 (8/14) / 800–627.5 (8/14) | **+5.5M** (8/14 +6.0) | **BULLISH** |
| **SPY** | 8/14 | **760** (+38.1M) | 750/760 (8/14) / 740–729 | **+52.0M** (8/14 +40.0) | **BULLISH** |
| **QQQ** | 8/14 | **735** (+13.6M) | 735/700 (8/14) / **685** (25.2k OI) | **+11.1M** (8/14 +6.5) | **BULLISH moderado** |
| **MSFT** | 8/14 | **510** (+2.6M) | 510 / 445–450 | +1.5M (12:36) | **BULLISH** (roll 460→510C) |
| **AAPL** | 8/14 | **310** (+7.7M NW) | 325/340 / 300–295 | +2.0M (12:36) | **NEUTRO-BULLISH** (giro vs esta semana) |
| **TSM** | 8/14 (único) | 430 (−1.2M, put) | 430 / 400–430 | +2.5M (12:36) | **NEUTRO-BAJISTA** |
| **ASML** | 8/14 (único) | 1590 (−79k, put) | 1780–1800 / 1590 | +0.1M | **NO MEDIBLE** (cadena fina, ver honestidad) |
| **AMD** | 8/10 + 8/14 | 500/497.5 (+972k NW) | 497.5–500 (8/10) / 530–450 | −1.4M (12:36) | **NEUTRO** |
| **NVDA** | 8/14 | 210–212.5 (+13.1M NW) | 225–212.5 (¿VENDIDAS?) / 180–185 | **−11.9M** (8/14 −7.7) | **BEARISH/capado 212.5–225** |
| **SMH** | 8/14 | **625** (+818k); trampilla 520 (−807k) | 675 + **770 nueva** / 520 | **+5.9M** (8/14 +5.8) | **BULLISH especulativo** |
| **TSLA** | 8/10 | 335–350 (+1.2M c/u) | 400/350 (8/14) / 310–285 | +0.1M | **NEUTRO** (straddle-whale al 8/10) |
| **SPCX** | 8/14 (único) | 80 (−6.7M, put) — gamma NEG | 160/146 / 90 (18.5k OI) | +1.9M | **NEUTRO-VOLÁTIL** (dos colas) |

## 1. Ballenas POSICIONADAS (ΔOI del lunes, contratos abiertos, semana próxima)

Acumulación lejana (≥6% OTM) o gorda detectada hoy 13:08 vs lunes 16:20:

- **SPY 900C 8/14: +5.000 nuevas (OI 5.000, todo del lunes)** — +17% OTM, lotería/hedge de melt-up. Y **758C 8/14 +13.372** (la mayor Δ de todo el estudio; casa con los +9.1M/+7.4M al ask en 756/758C del lunes). Contra-lado: **729P 8/10 +11.478 y 735P 8/11 +9.245** — cobertura comprada para LUNES-MARTES próximos (semana de CPI 8/12): alcista con paraguas.
- **SMH 770C/750C/780C 8/14: +1.643/+912/+675 nuevas (OI≈Δ, posiciones vírgenes)** — +30–36% OTM. Ballena apostando a melt-up de semis. Ojo: hoy 750C se opera −4.0M al bid (alguien la vende contra).
- **MU 900C 8/10 +2.476, 880C +2.107, 1000C 8/14 +1.176, y 1400C 8/14 +420 nuevas (+56% OTM)**. Contra-lado hedge: 627.5P/640P/620P 8/14 +2.3k combinadas (−30% OTM).
- **QQQ puts de cola al 8/10: 635P +6.963, 620P +5.597, 625P +1.751** (−12% OTM, vencen LUNES) — alguien pagó protección de desastre para el finde/lunes. Upside: 710C 8/14 +2.079.
- **AAPL 320C 8/14 +2.786, 310C 8/10 +2.111, 390C 8/14 +688 nuevas (+26% OTM)**. OI calls NW 93.7k vs puts 35.8k (2.6:1) — el posicionamiento de la semana próxima es call-pesado aunque el flujo de ESTA semana sea bajista.
- **MSFT 330P 8/14 +2.172 (−33% OTM, disaster hedge) + 520C +1.218**.
- **TSLA dos colas al 8/10**: 365C +2.316 (+12%) vs 250P/260P/262.5P +4.4k — straddle de ballena apuntando al lunes 8/10.
- **AMD 497.5C/500C 8/10 +1.540/+1.481** (ITM, stock-replacement o buy-write) + disaster put 302.5 8/14 +1.342.
- **SPCX dos colas 8/14**: 160C +3.360, 146C +3.290, 130C +2.132 vs 60P +3.588 — apuesta a movimiento gordo, no a dirección. Todo el libro NW es put-pesado (127k P vs 60k C), GEX profundamente negativo.
- **NVDA call-build 8/14 212.5C +5.674, 207.5C +2.662, 215C +2.550, 220C +1.970, 225C +1.751** — PERO el flujo UW de esos expirys es NEGATIVO (−11.9M): consistente con calls VENDIDAS (covered calls/techo), no compradas. No leerlo como bullish.

## 2. Archivo ballenas de esta semana (lun 8/3 sesión completa + mar 8/4 hasta 13:10)

Signed por strike = ask−bid; convención casa `signed_premium = net_call − net_put` respetada (put vendida = alcista).

**Lunes 8/3** (los gordos):
- **MSFT: roll alcista gigante 460C −94.6M vendidas → 510C +59.0M compradas** (62.6k/80.4k contratos). El 510 es exactamente el imán GEX del 8/14.
- SPY: 760P −17.7M vendidas + 756C +9.1M / 758C +7.4M compradas → hoy aparecen como ΔOI 8/14.
- SMH: 590C +11.0M compradas, 500P −12.5M vendidas (doble alcista).
- NVDA: 170C +19.8M (ITM, stock-replacement), 230C +6.7M.
- SPCX: puts rolando (120P −13.9M vendida → 135P +13.0M / 110P +8.3M compradas) = sube el piso de cobertura.
- MU: 800 con C+7.3M y P+5.5M (collar), 600P −10.6M vendidas (alcista), 880P +9.7M compradas (hedge).

**Martes 8/4 (hoy, 5 núcleo)**:
- **MU: 900C +21.8M + 1000C +10.9M compradas, 900P −7.8M vendidas** — triple alcista, casa con el +37.3M al viernes 8/7 de NET-PREMIUMS.
- **SPY: 775C +39.0M compradas** (strike +0.5% OTM).
- **QQQ: 735C +14.5M + 710C +13.6M compradas; 690C −53.4M vendidas (ITM, cierre/covered)** — el 735 comprado ES el imán GEX del 8/14.
- **NVDA: 205P +9.0M compradas, 260C −7.6M vendidas** — bajista, coherente con NW −11.9M.
- SMH: 550P −10.0M vendidas (alcista) pero 670C −6.4M y 750C −4.0M vendidas (techos).

## 3. Muros resto de ESTA semana (8/5–8/7, OI hoy 13:08)

| sym | call wall | put wall |
|---|---|---|
| MU | 1000 (7.5k) · 900 (6.3k) vie | 500 (21.4k) · 800 (13.0k) vie |
| SPY | 760 (16.4k) vie | **720 (71.8k)** · 750 (58.1k) vie |
| QQQ | 690 (36.3k) vie | **660 (64.7k)** · 645 (46.3k) vie |
| NVDA | 210 (56.9k) · 200 (45.2k) vie | 180 (32.5k) vie |
| TSLA | 330 (19.3k) vie | 305/300 (~6k) vie |
| SMH | 575 (3.5k) vie | 370 (50.4k) · 400 (40.9k) vie (viejas, −30% OTM) |
| AAPL | 350 (22.6k) · 310 (18.1k) vie | 300 (15.3k) vie |
| MSFT | 470 (10.2k) vie | 380 (6.6k) vie |
| TSM | 420 (6.7k) vie | 400 (3.3k) vie |
| SPCX | 150 (18.5k) vie | 100 (31.9k) vie |

## 4. Honestidad / fail-loud

- **opt_whale_watch MUERTO esta semana**: `logs/opt_whale.log` = connect refused 127.0.0.1:4001 (IBKR prohibido esta semana). Cero ballenas TWS lun/mar; el archivo de ballenas usado es UW per-strike, que NO trae expiry — el expiry se infiere cruzando con ΔOI Polygon.
- `data/whale_week.json` está RANCIO (últimos datos 7/31 20:43, fuente uw_premium_flow_hist.jsonl sin alimentar desde el 7/31). No usado.
- **ASML NO MEDIBLE**: OI semana próxima 2.9k C / 4.0k P y el per-strike del lunes muestra strikes 540/560/500 contra spot 1698 (series ajustadas o basura del feed). Sin veredicto.
- ΔOI mide lo abierto el LUNES solamente (OI de hoy aún no incluye lo operado hoy — se asienta overnight). Lo de hoy se lee por flujo (sección 2).
- NVDA: OI call-build vs flujo negativo — resuelto a favor del flujo (calls vendidas). Es inferencia direccional del lado agresor, no lectura de libro.
- AAPL/TSM/AMD/TSLA/MSFT flujo NW citado del crudo 12:36 (no refrescado para no gastar); los 6 calientes refrescados 13:18.
- Cuota UW gastada en este estudio: **6 requests** (quedan ~19 del presupuesto del brief).
- Crudos: scratchpad `whales_nextweek_result.json`, `uw_nw_fresh_1320.json`, `uw_flow_per_expiry_20260804.json`.
