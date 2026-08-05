# Backtest señales de HOY — martes 2026-08-04 (09:30 → ~15:29 ET)

Generado 15:4x ET intra-sesión. SEÑAL-SOLAMENTE. Entrada = close de la vela 1m del epoch de la señal; sin comisiones/slippage/spread. Retorno FIRMADO en la dirección de la señal.
**Verdad de terreno**: barras locales `data/bars_<sym>_ibkr.txt` (flota) + **Intrinio 1m** para no-flota, porque **Polygon devolvió 403 en TODO dato del mismo día** (histórico OK, hoy prohibido — la key hoy se comporta como free tier, no como Starter 15-min delayed). Hallazgo en sí: nada que espere "Polygon delayed 15 min" funciona hoy.
Nota: entre 09:30 y ~12:40 las barras llegaban ~4 min tarde (bug ya arreglado). Los epochs son correctos → el backtest mide bien, pero las señales de esa ventana SONARON tarde en vivo.

## 1. FINVIZ (lo pedido en especial)

### finviz_scout: MUERTO todo el día
HTTP **401 desde las 04:02 hasta ahora (287 reintentos, logs/finviz_scout.log)**. Mismo 401 en `bargain_hunt` y en el export de earnings-fall ("export Finviz caido"). El motor `finviz_screener_watch` (momentum/squeeze/buffett) SÍ funcionó leyendo el mismo feeds.env → divergencia de token/URL a debuggear, no es Finviz caído global.

### Momentum breakout — 15 picks BUY (todos long)
| hora | pick | ent | +30m | a-ahora | MFE | MAE |
|---|---|---|---|---|---|---|
| 09:46 | ANET | 189.99 | -0.53 | +1.43 | +2.27 | -1.15 |
| 09:50 | LIND | 34.09 | -2.11 | -1.01 | +0.19 | -3.74 |
| 09:53 | HSIC | 90.36 | -0.59 | -1.49 | +0.29 | -3.18 |
| 10:02 | REPL | 12.69 | **-5.75** | -4.73 | +0.08 | **-9.38** |
| 10:05 | NET | 294.30 | +1.26 | **+3.08** | +3.19 | +0.11 |
| 10:08 | CSWC | 24.26 | +0.12 | +2.23 | +2.23 | -0.08 |
| 10:16 | AYA | 21.93 | +1.09 | **+3.69** | +5.24 | -0.05 |
| 11:01 | HELP | 9.11 | +0.27 | +1.21 | +1.32 | -2.85 |
| 11:19 | TRIN | 18.19 | n/a | +0.16 | +0.16 | -0.44 |
| 11:34 | VCTR | 104.30 | n/a | -1.49 | +0.21 | -1.90 |
| 11:36 | AMLX | 21.59 | +0.46 | +1.07 | +3.20 | +0.05 |
| 11:37 | ELVN | 60.28 | -0.51 | -0.28 | +0.70 | -2.75 |
| 14:27 | JAZZ | 260.45 | n/a | -0.10 | +0.43 | -0.14 |
| 14:30 | MGA | 70.21 | -0.64 | -0.44 | +0.21 | -0.68 |
| 15:29 | AME | — | sin barras (Intrinio vacío) | | | |

**+30m: 5W/6L, media -0.63%** (compra el pico del spike, igual que el backtest de ayer: -8,4pp vs azar). "A-ahora" media +0.24% solo porque NET/AYA/CSWC siguieron subiendo — en día verde de mercado eso es beta, no edge. MAE medio brutal (-2.1%): perseguir el breakout te hace comer el retroceso primero.

### Short squeeze — 4 accionables
- LIFE BUY premarket 08:46 @28.11 → desde open: **5m -6.06%, MAE -10.65%**, a-ahora +1.82. Cuchillo.
- VTS SELL 10:24 → -1.45% a 30m, **-2.57% a-ahora** (perdedor).
- WIX BUY 12:47 → -0.46 a 30m, +1.54 a 60m, +0.10 a-ahora (MFE +3.29 que no avisó cobrar).
- WLK BUY 15:01 → +0.54 a 5m, -0.07 a-ahora.
**0W/2L a 30m. n=4 → DATA-INSUFFICIENT**, pero el MAE de LIFE dice todo.

### Buffett — 41 alertas-ticker
**40 fueron premarket con RVOL 0.0** = ruido puro que sonó de 04:15 a 09:15 (no evaluables como señal intradía). Única RTH: FSLR BUY 10:27 @235.91 → -0.47 a 30m pero **+3.66 a-ahora** (MFE +6.86). n=1 DATA-INSUFFICIENT.

### ¿Cazaron los movers del día? NO.
- **PLTR**: +13.2% intradía adicional tras el gap (145.07→164.16 medido Intrinio). **Cero menciones en todo el registro del día.**
- **AAOI**: +3.4% intradía post-gap. **Cero menciones.**
- **SPCX**: sin feed de barras hoy (universo recortado 26/30); 1 señal estructural 14:00 (imán 130 ↑) invendible sin datos.
- Causa probable: el screener momentum solo canta **NUEVOS**; un gap-up premarket ya está en la lista antes de la apertura ("10 matches, nuevos=0" de 09:22) y **jamás suena**. El día que más importaba, el diseño lo silenció. Scout —el que barre topgainers— era justo el que estaba muerto por el 401.

## 2. Familias de la flota (deduplicado ≤15 min)

| familia | n | +30m | media +30m | media a-ahora | veredicto |
|---|---|---|---|---|---|
| bb-rebote LONG (banda inferior) | 43 | **30W/13L** | **+0.15%** | +0.17% | pagó — 70% WR |
| bb-rebote SHORT (fade banda sup.) | 61 | **17W/44L** | **-0.19%** | -0.39% | sangró TODO el día (día tendencial alcista) |
| bb-rebote [VETO medido] | 13 | 4W/8L | -0.12% | -0.56% | el veto acertó: lo vetado perdió |
| bb-bandwalk | 4 | 2W/2L | +0.37% | +1.07% | DATA-INSUFFICIENT, dirección correcta |
| re-entrada a banda | 5 | **5W/0L** | **+0.82%** | +1.11% | mejor familia del día; n<5 sesiones → sin % publicable |
| bounce CAUTION (today_alarm5) | 8 | 5W/3L | +0.05% | +0.60% | plano |
| bounce NO-GO (today_alarm5) | 5 | 1W/4L | **-0.58%** | -2.00% | el gate vetó bien: los NO-GO perdieron |
| terremoto CUSUM | 4 | 1W/3L | -0.53% | +0.33% | llega tarde (NOK cantó tras +3% y cayó -1.87 a 30m) |
| manada ALCISTA 12:40 → CALLS | 1 | 1W | +0.25% | +0.62% | correcta; n=1 |
| compass (flechas up, 1ª por símbolo) | 15 | 9W/6L | ~±0.3% | — | solo emitió desde 12:37 (reinicio); mudo toda la mañana |

today_alarm5: **0 GO en todo el día** (3 CAUTION, 7 NO-GO; 5 registros eran eventos rancios del 31-jul procesados al reiniciar a las 12:37). Hoy solo-GO-habla = el sistema calló todo el día, y lo que vetó perdió: gate funcionando.
Ruido residual: NVDA CALL y PUT BOUNCE CAUTION simultáneos (10:18, 10:43) = las dos direcciones a la vez, eso no es señal. EARNINGS-FALL repitió AAA/TGTX 28 veces entre 03:00-03:21 (crash-loop del export roto); TGTX largo desde open habría dado +4.6% pero con el export caído es pick de datos viejos.

## 3. Tres conclusiones accionables

1. **Arreglar el token Finviz Elite del scout HOY** (401 desde las 04:02; scout, bargain y earnings-fall muertos mientras screener_watch funciona con el mismo feeds.env) **y hacer que el screener momentum re-cante los matches vivos al abrir el mercado**, no solo los "nuevos": PLTR y AAOI cumplían filtros desde el gap premarket y por diseño jamás sonaron. El día del mover monstruo, los screeners callaron.
2. **El fade de banda superior debe apagarse en día tendencial**: bb-rebote SHORT 17W/44L (-0.19% a 30m, 61 señales = la mitad del ruido del día) mientras bb-rebote LONG 30W/13L (+0.15%) y re-entrada 5W/0L. El filtro ya existe en casa: con MANADA ALCISTA / capitanes arriba del flip, silenciar el elástico contra-tendencia (el veto medido ya demostró que acierta: lo vetado perdió).
3bis. **Re-backtest VETO CAPITAN (2026-08-05, `scripts/backtest_bb_captain_veto.py --day 2026-08-04`)**: veto = capitan sobre su gamma flip calla el fade SHORT (SMH→semis, SPY/QQQ→resto). Reproduccion dedup 15m: n=77 SHORT, 26W/51L (el doc conto 61=17W/44L cortando en señales con +30m completo a las 15:4x). Variante sector: calla 42/77 — perdedoras 30/51 (59%) pero ganadoras 12/26 (**46%**). Variante SPY-y-QQQ-vetan-todo: calla 77/77 (100% de ganadoras muertas — dia entero sobre el flip). **Mata >30% de lo bueno → NO activo por defecto**: implementado en `bollinger_alarm.py` tras `IBT_BB_CAPTAIN_VETO=1` (registra "[VETO capitan]" banner sin voz). Flip del snapshot vespertino asumido estable intradia (doctrina flip 09:35).

3. **Finviz momentum se opera en el retroceso, no en el banner**: media -0.63% a +30m del pick con MAE medio ~-2%, y lo que acabó verde (NET +3.1, AYA +3.7) primero fue plano/rojo. Regla PRINT-O-NADA aplicada al pick: esperar re-test tras el banner en vez de comprar el spike. Y n=1 día: nada de esto es probabilidad publicable — es la segunda sesión consecutiva (ver BACKTEST-ALERTAS-FINVIZ-2026-08-04.md: -8,4pp vs azar el 08-03) que apunta igual.
