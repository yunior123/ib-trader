# NET PREMIUMS — martes 2026-08-04 (corte 12:36 EDT)

Convención de la casa: `signed_premium = net_call_premium − net_put_premium` (vender put = alcista).
Viernes de esta semana = **2026-08-07** (8/8 es sábado). Expiries de la semana: 8/4, 8/5, 8/6, 8/7.

Fuentes y horas:
- **UW net-prem-ticks archivado** (lunes 8/3, sesión completa): `data/history/2026-08-03/uw_net_prem_ticks_<sym>.json` (backfill 04:59-05:03 de hoy, 30/30 syms).
- **UW flow-per-expiry medido HOY 12:36 EDT** (30 fleet + 10 fuera de flota): 41 requests nuevas. Signed por lado agresor: `ask_side − bid_side` por expiry.
- **UW net-prem-ticks widget vivo** `data/uw_net_prem.json` 12:34 EDT (8 syms núcleo).
- **UW greek-exposure/expiry** `data/uw_gex_expiry.json` 12:26 EDT; **gex_snapshot.json** 12:38 EDT.
- **Finviz Elite export** 12:38 EDT (relvol>2, optionable).

## 1a. Flota — signed premium semana (lun 8/3 completo + mar 8/4 hasta 12:36), M$

| sym | lun 8/3 | mar 8/4 | SEMANA |
|---|---:|---:|---:|
| SPY | +84.2 | +86.0 | **+170.2** |
| MU | +19.8 | +104.2 | **+124.0** |
| MSFT | +31.1 | +80.5 | **+111.6** |
| AMD | +31.7 | +27.4 | +59.2 |
| NVDA | +69.8 | −17.0 | +52.9 |
| QQQ | +61.2 | −11.6* | +49.6* |
| AVGO | +8.5 | +36.6 | +45.1 |
| META | +55.0 | −18.9 | +36.1 |
| GOOGL | +27.1 | +6.7 | +33.8 |
| SPCX | +14.3 | +16.7 | +30.9 |
| AMZN | +41.8 | −16.5 | +25.3 |
| SNDK | +20.1 | −2.4 | +17.7 |
| LRCX | +5.9 | +8.8 | +14.7 |
| SMH | −0.5 | +14.3 | +13.8 |
| EWY | +7.8 | +4.5 | +12.3 |
| DRAM | +3.3 | +6.4 | +9.7 |
| SKHY | −14.7 | +22.7 | +8.0 |
| INTC | −23.5 | +30.1 | +6.6 |
| TSLA | +15.9 | −11.1 | +4.9 |
| XLK | +0.7 | +2.2 | +2.9 |
| NOK | +1.5 | +0.5 | +1.9 |
| QCOM | +1.6 | +0.1 | +1.7 |
| GLD | −0.8 | +1.4 | +0.6 |
| TXN | +1.5 | −2.6 | −1.1 |
| STX | −1.5 | −0.3 | −1.8 |
| NFLX | −2.0 | −0.9 | −2.8 |
| WDC | −2.5 | −2.1 | −4.5 |
| AAPL | −24.1 | +11.3 | −12.8 |
| ASML | −29.1 | +5.7 | **−23.3** |
| TSM | +5.3 | −32.2 | **−26.9** |

\* **GOTCHA QQQ medido hoy**: los dos métodos UW divergen. flow-per-expiry (ask−bid) da QQQ hoy **−11.6M**; net-prem-ticks (clasificación de agresor de UW, incluye mids) da **+54.4M** a las 12:34. En los otros 7 núcleo la diferencia es <12M (SMH +14.3 vs +14.1, NVDA −16.9 vs −15.4, TSLA −11.1 vs −11.0, MU +104.2 vs +108.0, SKHY +22.7 vs +20.2, DRAM +6.4 vs +5.7, SPY +86.0 vs +73.4). QQQ 0DTE opera masivamente al mid y el ask−bid pierde ese flujo. Los dos son medidos; ninguno se fabrica. Para QQQ hoy: dirección INDETERMINADA entre métodos.

Cross-check widget 12:34 (net-prem-ticks, 8 núcleo): QQQ +54.4 / SPY +73.4 / SMH +14.5 / NVDA −15.7 / TSLA −10.8 / MU +108.0 / SKHY +20.2 / DRAM +5.7.

## 1b. Flota — signed premium por EXPIRY de esta semana (flujo de HOY 12:36, M$)

`-` = ese ticker no tiene ese expiry (dailies solo QQQ/SPY; varios single-names tienen 8/5; el resto solo viernes 8/7). Medido, no rellenado.

| sym | 8/4 0DTE | 8/5 | 8/6 | 8/7 vie |
|---|---:|---:|---:|---:|
| QQQ | +11.7 | −2.8 | +2.1 | **−48.5** |
| SPY | +2.0 | +3.4 | +1.2 | +6.5 |
| NVDA | - | +1.2 | - | −3.4 |
| TSLA | - | +2.8 | - | −7.7 |
| MU | - | +5.6 | - | **+37.3** |
| SMH | - | +0.1 | - | +5.9 |
| AMD | - | −6.1 | - | −3.6 |
| AAPL | - | +1.9 | - | +2.6 |
| MSFT | - | +4.1 | - | −0.3 |
| META | - | −1.0 | - | −2.5 |
| AMZN | - | +6.8 | - | −4.6 |
| GOOGL | - | +6.6 | - | −1.7 |
| INTC | - | +6.2 | - | +11.2 |
| TSM | - | - | - | +1.1 |
| ASML | - | - | - | −2.3 |
| TXN | - | - | - | +0.0 |
| QCOM | - | - | - | +0.6 |
| AVGO | - | +1.6 | - | −1.1 |
| NFLX | - | - | - | +0.5 |
| NOK | - | - | - | +0.2 |
| GLD | - | +0.1 | - | −0.2 |
| XLK | - | - | - | −0.1 |
| EWY | - | - | - | +2.8 |
| DRAM | - | - | - | +1.0 |
| SPCX | - | - | - | −0.2 |
| SKHY | - | - | - | +1.1 |
| LRCX | - | - | - | +0.3 |
| SNDK | - | - | - | **−16.3** |
| WDC | - | - | - | −3.5 |
| STX | - | - | - | −0.5 |

Lecturas del desglose: la put-carga semanal grande de QQQ vive en el **viernes 8/7 (−48.5M)** mientras el 0DTE de hoy es comprador de calls (+11.7M) — cobertura de semana, no pánico intradía. **MU concentra +37.3M en el viernes** = convicción alcista con horizonte. **SNDK −16.3M al viernes** contra un lunes que fue +20.1M: giro de hoy. **INTC +11.2M viernes** apoya su +30.1M del día.

## 2. Flota — top 3 BULLISH / BEARISH (signed semana + confluencia)

**BULLISH**
1. **MU** +124.0M semana (hoy +104.2M, y +37.3M dirigido al viernes). Gamma POS, bias CALL, spot sobre el flip (dist −5.0%), imanes 800/900 (gex_snapshot 12:38). Confluencia total.
2. **SPY** +170.2M semana — el mayor absoluto, y los dos métodos UW coinciden hoy (+86.0/+73.4). Ojo a la composición: hoy es venta de puts (net_put −44.5M) más que compra de calls (+29.0M) — alcista de "no cae", no de persecución. Gamma POS, flip 757.9 debajo, GEX semanal +894.8k.
3. **MSFT** +111.6M semana (hoy +80.5M, incluido sweep CALL 480 sep $4.5M en uw_fleet_flow 12:33). Gamma POS profundo (flip −20.9% debajo), imanes 485/500.

**BEARISH**
1. **TSM** −26.9M semana, hoy −32.2M (el peor flujo del día en la flota). Contra-confluencia: gamma sigue POS con imanes 400/420 arriba — flujo bajista dentro de estructura alcista; vale como fade del rally, no como ruptura.
2. **ASML** −23.3M semana (todo del lunes −29.1M; hoy +5.7M recuperó algo). Flip no calculable (cadena fina), señal solo de flujo.
3. **AAPL** −12.8M semana y la **única de la flota con régimen gamma NEG + bias PUT** (flip 326.4 un 5.8% ARRIBA del spot, imán 300 debajo). Menos premium que TSM/ASML pero la mejor confluencia bajista flujo+estructura.

Menciones: NVDA/META/AMZN hoy en negativo (−17/−19/−16M) tras un lunes muy positivo = toma de beneficios, no cambio de tesis todavía. SNDK viernes −16.3M vigilar.

## 3. Fuera de flota — volumen inusual (Finviz relvol>2 optionable, 12:38) + net premium UW medido 12:40

| sym | chg hoy | relvol | signed UW | detalle |
|---|---:|---:|---:|---|
| **PLTR** | +28.6% | 5.0 | **+177.9M** | net_call +145.0M, net_put −32.9M, vol 1.02M C / 413k P. Post-earnings. El flujo más grande medido hoy, flota incluida. |
| **W** | +31.4% | 3.9 | +1.7M | post-earnings, chico pero positivo |
| **COHR** | +15.1% | 1.9 | +1.4M | brutos enormes (net_call +16.9M pero net_put +15.5M lo neutraliza) — flujo caro en ambos lados, neto apenas alcista |
| **CIFR** | −12.1% | 2.7 | −2.0M | 113k calls de volumen pero vendidas al bid |
| **NRG** | −15.4% | 4.2 | −1.4M | post-earnings, puts al ask |
| **AAOI** | +21.7% | 2.3 | **−3.8M** | GOTCHA: precio +21.7% pero calls vendidas al bid (−3.5M) = cobran el rally, no lo persiguen |

Top 3 bullish fuera de flota: **PLTR, W, COHR** (COHR con la reserva del neto fino).
Top 3 bearish fuera de flota: **AAOI, CIFR, NRG** (AAOI el más interesante: flujo contra precio).
También medidos, planos (<±0.5M): APTV −0.4, IT +0.2, BRKR −0.1, AHCO +0.0.

## 4. Honestidad / límites
- **Semana = lun+mar solamente**: la semana empezó el lunes 8/3; no hay más sesiones que agregar. Martes cortado a las 12:36 EDT, faltan ~3.5h de sesión.
- **QQQ hoy: dirección indeterminada** entre los dos métodos UW (ver gotcha arriba). No se elige uno para forzar el relato.
- El per-expiry (tabla 1b) es **flujo de HOY solamente** — flow-per-expiry no acepta fecha pasada en el plan actual (no probado hoy para no gastar cuota; el desglose por expiry del lunes NO está archivado, solo strike/ticks).
- **Token UW nuevo (2026-08-02) NO cubre todo**: `option-trades/flow-alerts` global da **401** desde ayer (uw_flow_tape muerto, `logs/uw_flow_tape.log`). Sí funcionan: net-prem-ticks, flow-per-expiry, flow-alerts por stock, greek-exposure, darkpool.
- Cuota UW gastada aquí: **41 requests** (30 flota + 10 off-fleet + 1 probe).
- Finviz "unusual OPTIONS volume" como tal no existe en el export Elite; se usó relvol de acciones >2 filtrado a optionable, y el net premium de opciones se midió en UW. Marcado como tal.
- Efecto colateral: importar `options_hunter` para el auth de Finviz regeneró `data/options_picks.txt` (su salida normal, señal-only). Ningún otro fichero de `data/` tocado.
- Crudos de esta corrida: scratchpad `uw_flow_per_expiry_20260804.json`, `uw_offfleet_20260804.json`, `net_prem_computed.json`.
