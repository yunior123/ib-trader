---
name: bollinger-mastery
description: Bollinger Bands mastery for the ib-trader signal fleet — math (20,2 vs 20,3, population std), %B, bandwidth/squeeze percentile, band-walk vs mean-reversion regimes, W-bottoms/M-tops, the fleet's multi-TF burst rules (1m/5m/15m, 2TF fuerte / 3TF muy fuerte), the confirmed-capitulation engine, and interactions with MACD/Supertrend/trendlines/VWAP/ADX. Use when the user asks about Bollinger Bands, BB squeeze, %B, band bursts, capitulation entries, band-walking, or why a BB touch alone is only a coin flip.
---

# Bollinger Mastery — la especializacion BB de la flota

Regla cero: **una banda tocada o reventada, sola, predice ~50%** (la "prediccion
base" de Yunior — un coin flip). Todo el edge de BB esta en los FILTROS:
regimen (ADX), volumen (RVOL), momentum (RSI/MACD), confirmacion (bar verde),
y alineacion multi-timeframe. El research de la flota lo cuantifica: squeeze
breakout con RVOL>=1.5 ≈ 58% WR vs 31% sin volumen; pullback con alineacion
multi-TF ≈ 64%; reversion MTF ≈ 55%. Sin filtro no hay señal — nunca.

## 1. Matematicas (exactamente como la flota las calcula)

- **mid** = SMA(close, 20). **sd** = desviacion estandar **POBLACIONAL**
  (dividir por N, no N-1 — Bollinger original; `V5BB::upd` en
  `scripts/v5_block.cpp.tmpl` hace `var = s2/k - mid*mid`, que es poblacional).
  Con N=20 la diferencia sample/poblacional es ~2.6% del sd — irrelevante para
  el trade, critico para reproducir backtests byte-identicos.
- **up/dn** = mid ± k·sd.
- **k=2.0** (v5/v6, `V5BB`/`V6BBX`): ~95% del precio dentro si fuera gaussiano
  (no lo es; en la practica ~88-92%). Un cierre fuera es "evento" pero comun:
  úsalo para *bursts* multi-TF y %B, no como pánico.
- **k=3.0** (motor clasico, `DRAM_BB_STD=3.0` en `dram_signal_bot.cpp`):
  evento raro (<1% teorico). Reservado para CAPITULACION — un cierre bajo
  mid−3sd con RSI<=25 y volumen es un flush real, no ruido.
- Incremental O(1)/bar: ring de 20 closes, recomputo de sumas en cada upd.
  Cero mallocs. Cualquier codigo nuevo BB de la flota copia ese patron.

Derivados (v6, `V6BBX`):
- **%B** = (c − dn) / (up − dn). 1.0 = en banda superior, 0.0 = inferior,
  0.5 = en la media. >1/<0 = fuera de banda. Si up==dn (sd=0) ⇒ 0.5.
- **BandWidth** = (up − dn) / mid. Medida de volatilidad normalizada.
- **bw_pctile** = % de los ultimos 125 valores de bandwidth <= al actual.
  ES la definicion de squeeze de la flota (no un umbral absoluto de BW, que
  no compara entre tickers ni regimenes).

## 2. Squeeze (contraccion → expansion)

- **Definicion flota** (`V6BBX::squeeze()`): bandwidth en el **percentil <=10**
  de un ring de 125 bars 15m, con al menos 100 muestras (`bn>=100`). Env:
  `V6_SQUEEZE_PCT` (10.0).
- Fisica: la volatilidad es cíclica; contraccion extrema precede expansion.
  El squeeze NO dice direccion — solo que viene un movimiento.
- **Fire** (clase SQUEEZE_BREAK_*): squeeze activo en los ultimos 5 bars 15m
  + **primer cierre 1m fuera de la banda 15m** + **RVOL>=1.5** + MACD15 no en
  contra (no a_dn para LONG, no a_up para SHORT). El volumen es obligatorio:
  58% WR con RVOL vs 31% sin el — un breakout de squeeze sin volumen es la
  trampa clasica (head-fake).
- **Head-fake**: el primer break de un squeeze falla con frecuencia y el
  movimiento real va al lado opuesto. Defensas de la flota: exigir RVOL,
  exigir contexto MACD15, y la fase de sesion (LATERAL veta SQUEEZE_BREAK).
- Prior de la clase: 56%.

## 3. %B en la practica

- **Mean-reversion** (solo con ADX15 < 20): %B <= 0.1 + RSI14 > 30 y girando
  al alza = candidato MTF_BB_REV_LONG. Si RSI < 30 Y cayendo: NO comprar —
  eso es breakdown de momentum, no sobreventa aprovechable.
- **Band-walk** (ADX15 > 25): %B >= 0.9 sostenido = FUERZA, no sobrecompra.
  PROHIBIDO emitir SELL por toque de banda superior en tendencia. Definicion
  operativa de band-walk en v6: %B >= 0.9 durante >=3 bars 15m dentro de los
  ultimos 10 bars 15m.
- ADX 20-25 = zona muerta: ninguna señal de origen BB (ni breakout ni
  reversion). Esta es la regla BB-2/BB-3 del research y es un veto duro.

## 4. W-bottoms y M-tops (patrones Bollinger clasicos)

**W-bottom** (setup de compra):
1. Primer minimo CIERRA por debajo de la banda inferior (o %B < 0) con panico.
2. Rebote hacia mid.
3. Segundo minimo: precio hace un low igual o MAS BAJO en absoluto, pero
   **%B queda MAS ALTO** (el segundo low no revienta la banda). Esa
   divergencia precio/%B es la firma del W.
4. Confirmacion: bar verde que supera el high del rebote intermedio, con
   volumen. Sin confirmacion no hay señal (mismo principio que la
   capitulacion confirmada, §5).

**M-top** espejo: segundo high absoluto mas alto pero %B mas bajo (el segundo
push no toca la banda superior) ⇒ debilidad; confirma con perdida del low
intermedio. En la flota, W/M no son una clase propia: son el fundamento de
MTF_BB_REV_* (el burst + bar de confirmacion ES un medio-W) y de
TREND_REVERSAL_* (band-walk roto + cierre al otro lado de BB15.mid).

## 5. Capitulacion confirmada — el motor clasico de la flota

Es el corazon de los 20 bots (ver `dram_signal_bot.cpp`), BB(20, **3.0**):

1. **Bar de capitulacion ARMA** (no dispara): `close <= BB_low` Y
   `RSI14 <= 25` Y `vol >= 1.2 * volMA20`. Los tres a la vez — precio en
   extremo, momentum en extremo, y el volumen que demuestra que alguien esta
   vomitando posiciones de verdad.
2. **Confirmacion DISPARA**: dentro de las 60 barras siguientes, un bar VERDE
   que cierra **por encima del high del bar de panico** con RSI subiendo
   ⇒ COMPRAR. Comprar el flush sin confirmacion = agarrar el cuchillo; la
   confirmacion convierte el 50% base en edge.
3. Variante multi-TF (v5, linea ~457 de los bots): banda inferior reventada
   en >=2 TF hace poco + bar verde = capitulacion multi-TF (+2 al score v5).

Todos los umbrales son env-overridables por ticker (`<SYM>_BB_STD`,
`<SYM>_VOL_MULT`, etc.) — nunca hardcodear un cambio, siempre via keepalive.

## 6. Reglas multi-TF de la flota (bursts 1m/5m/15m)

El bloque v5 mantiene tres BB(20,2) — 1m directa, 5m y 15m via `V5TF`
(solo bars CERRADOS) — y cuenta recencia de bursts:

```
burst reciente:  1m si hace <=3 bars | 5m si <=2 bars 5m | 15m si <=1 bar 15m
bb_dn_tfs = (# de TFs con banda INFERIOR reventada recientemente)
```

- **2 TF reventadas = señal FUERTE** (+2 score v5, razon `BB-2TF-abajo`).
- **3 TF reventadas = MUY FUERTE** (`BB-3TF-abajo`).
- Siempre con bar de confirmacion: burst abajo exige bar verde (`c > o`);
  burst arriba exige bar rojo. El burst solo — otra vez — es el 50% base;
  la coincidencia multi-TF + confirmacion es lo que lo sube a ~55% (prior
  MTF_BB_REV) y con RSI/ADX/gap-filter encima es la clase completa v6.
- v6 añade a esa logica: RSI14_1m > 30 y subiendo (long), ADX15 < 20
  (regimen de rango obligatorio), y veto `no_fade` contra gaps breakaway
  (gap > 1.0×ATR15: los gaps grandes solo llenan ~8% — no hagas fade contra
  ellos aunque las 3 bandas esten reventadas).

Ventanas de recencia asimetricas a proposito: 1 bar de 15m "vale" mas tiempo
que 1 de 1m; la cascada 3/2/1 hace que "reciente" signifique lo mismo (~3 min
de mundo real) en los tres TF.

## 7. Interacciones con el resto del stack

- **MACD 4-color CM (15m = contexto, 1m = gatillo)**: MACD15 en a_dn veta
  todo BUY de origen BB EXCEPTO MTF_BB_REV_LONG con ADX15<20 (reversion pura
  en rango es la unica excepcion legal a "15m manda"). El giro del histograma
  1m (b_dn→b_up) es el timing fino tras un touch/burst de banda.
- **Supertrend(10,3) 5m**: filtro de regimen, JAMAS señal sola (COMBO-2).
  `st5.dir==-1` + precio bajo VWAP = veto BUY. Un burst de banda inferior con
  supertrend alcista intacto es pullback (comprable); con supertrend girado
  es posible reversal (aplica §2.5 del spec v6, no compres el dip).
- **Trendlines (V5TL)**: banda inferior + trendline alcista 15m intacta al
  precio = confluencia de soporte (sube score). Break de trendline 1m + burst
  BB en la misma direccion = TLINE_BREAK con banda como combustible de
  expansion (mejor si sale de squeeze).
- **VWAP**: BB dice "extremo relativo a su propia media movil"; VWAP dice
  "extremo relativo al precio pagado hoy". Burst inferior POR ENCIMA de VWAP
  = dip en dia fuerte (mejor long). Burst inferior muy por debajo de VWAP en
  fase TREND_DOWN = band-walk bajista: no es sobreventa, es tendencia.
- **ADX(14) 15m**: el conmutador maestro de modo BB (trending>25 ⇒ band-walk,
  ranging<20 ⇒ mean-reversion, 20-25 ⇒ silencio BB). Sin leer ADX primero,
  cualquier interpretacion de %B es ambigua.

## 8. Errores tipicos (los que matan cuentas)

1. **Vender el toque de banda superior en tendencia** — band-walk es fuerza;
   con ADX>25 el precio puede cabalgar la banda 20+ bars. El error #1.
2. **Comprar %B<0 sin confirmacion ni volumen** — cuchillo cayendo. La flota
   SIEMPRE exige bar verde de confirmacion (capitulacion §5, MTF_BB_REV).
3. **Tradear el primer break de squeeze sin RVOL** — head-fake (31% WR).
4. **Ignorar el regimen** — usar reglas de reversion en tendencia o de
   breakout en rango. ADX primero, BB despues.
5. **sd sample vs poblacional / intrabar vs cierre** — mezclarlos hace que el
   live no reproduzca el backtest. La flota decide TODO con bar 1m CERRADO
   (anti-lookahead CALIB-3) y std poblacional; cualquier tool externa debe
   configurarse igual antes de comparar.
6. **k=2 y k=3 intercambiados** — un burst de 2sd tratado como capitulacion
   genera 5-10x mas señales falsas; una espera de 3sd en logica multi-TF v5
   no dispara nunca.
7. **Fade contra gap breakaway** — bandas reventadas + gap>1×ATR15 en contra:
   el flag `no_fade` existe porque esos gaps no llenan (~8%).
8. **Contar el 50% base como edge** — reportar prob de una señal BB sin tabla
   calibrada ni prior de clase. En v6 la prob mostrada = shrinkage(tabla WFO,
   prior de clase, k=20); nunca el WR crudo de n=3 trades.

## Evidencia por ticker (30d 1m, 2026-07-22)

Mision B6: la señal **elastic-1m** del alarm (pierce BB(20,2) 1m + re-entrada,
gate band-walk 5m, cooldown 30min) medida en 4,619 señales / 30 tickers / 17
sesiones RTH. Outcome: P(toca la media BB20-1m en 30min). Grid completo y
metodologia: `docs/BOLLINGER-COMPLEMENTS-2026-07.md`; JSON operable:
`data/bollinger_plus.json` (n>=15, |uplift|>=5pts).

**Flota base: 65.8% [64.4, 67.1]** — pero MFE30 (0.455%) < MAE30 (0.478%):
sin filtro ni gestion la expectativa es ≈0. El elastico se cobra EN la media,
rapido, o no se cobra.

**Jerarquia de filtros MEDIDA (flota, Wilson 95%):**

| filtro | n | P | uplift | veredicto |
|---|---|---|---|---|
| F5 squeeze (bw pctile≤20) | 1424 | 76.8 | **+11.0** | EL mejor — universal |
| F6 tarde 14:00-15:30 | 1223 | 75.0 | **+9.2** | la hora elastica (edge30 +0.04) |
| **F5+F6 tarde (combo)** | 389 | **85.1** | **+19.3** | celda estrella, ~23 señales/dia flota |
| F1 RVOL≥1.5 | 718 | 68.5 | +2.7 | SOLO por ticker (ver abajo) |
| F8a ADX5m<20 | 1364 | 67.7 | +1.9 | casi nada a este horizonte |
| F7 15m dentro de banda | 3881 | 67.3 | +1.5 | flojo como boost; su complemento (~57%) vale como veto |
| F3 profundidad pierce | ~4527 | 65.9 | +0.1 | IRRELEVANTE (>0.05 vs >0.15 da igual) |
| F6 apertura 9:45-10:30 | 535 | 58.1 | **−7.7** | VETO — peor hora, MAE −0.9% en 30min lado dn |
| F4 z-VWAP≥\|1.5\| | 578 | 54.8 | **−11.0** | VETO — lejos de VWAP = dia tendencia |
| F2 RSI(2) extremo | 281 | 53.0 | **−12.8** | VETO — impulso violento = continuacion |

**Mejor/peor filtro por ticker** (celdas n≥15, |uplift|≥5; base P con Wilson en
el doc):

| ticker | base P | mejor filtro | peor filtro (veto) |
|---|---|---|---|
| NFLX | **78.1** | tarde +10 (88.4%) | z-VWAP −11 |
| AMD | 72.7 | squeeze +15 (87.8%) | RSI2 −43 / z-VWAP −20 |
| AVGO | 70.7 | tarde +11 | z-VWAP −21 |
| QCOM | 70.1 | z-VWAP **+17** (excepcion!) / RVOL +14 | apertura −10 |
| META | 69.6 | tarde +14 | z-VWAP −20 |
| TSLA | 68.9 | squeeze +7 | RVOL **−17** (vol=continuacion) |
| NOK | 68.8 | RVOL +13 / squeeze +12 | z-VWAP −21 |
| ASML | 68.2 | tarde +15 | apertura −15 / picadora −10 |
| GOOGL | 67.5 | squeeze +21 / ADX<20 +16 | ADX≥25 −15 |
| WDC | 67.3 | squeeze +6 | z-VWAP **−36** |
| QQQ | 66.9 | squeeze +18 / tarde +14 | apertura −14 |
| MSFT | 66.5 | squeeze +18 / ADX<20 +12 | z-VWAP **−42** / 10:30-11:30 −18 |
| TSM | 66.5 | tarde +17 | picadora −8 |
| NVDA | 66.0 | RVOL **+22** / squeeze +13 | RSI2 −46 / apertura −23 |
| SPCX | 66.0 | squeeze +11 | 10:30-11:30 −12 |
| TXN | 66.0 | RVOL +19 / tarde +12 | 10:30-11:30 −5 |
| SNDK | 65.8 | tarde +18 | z-VWAP −16 / apertura −16 |
| XLK | 64.7 | tarde +12 / squeeze +11 | RVOL −13 / 10:30-11:30 −15 |
| LRCX | 64.2 | squeeze +15 / tarde +12 | z-VWAP −18 |
| SPY | 64.1 | squeeze +8 | z-VWAP −14 |
| STX | 64.0 | tarde **+21** / squeeze +14 | apertura **−25** |
| GLD | 62.7 | squeeze +13 | apertura −13 |
| SMH | 62.3 | tarde/10:30 +16 | apertura −17 / ADX<20 −14 |
| EWY | 62.1 | apertura +9 (excepcion) | 10:30-11:30 −6 |
| MU | 61.7 | tarde +13 / squeeze +10 | apertura −14 |
| INTC | 61.4 | squeeze +15 | z-VWAP **−25** / apertura −14 |
| AMZN | 61.2 | RVOL +21 / squeeze +12 | RSI2 −43 / z-VWAP −18 |
| DRAM | 58.8 | tarde +17 / squeeze +11 | picadora −12 |
| AAPL | **58.6** | squeeze +10 | apertura **−23** (35%!) |
| SKHY | 57.7 (n=71, 8d) | squeeze +26 | tarde −8 |

**Sorpresas confirmadas (contradicen hipotesis semilla o doctrina):**
1. **Squeeze MEJORA el fade** (hipotesis decia que lo empeoraria). Clave: la
   re-entrada convierte el break post-squeeze en head-fake confirmado. El
   uplift sobrevive el control por distancia-al-target (+7 a +11 en Q1-Q3).
2. **RSI(2) extremo y z-VWAP estirado son VETOS** — "mas estirado = mejor
   elastico" es FALSO a 1m. El elastico bueno es el estirado tranquilo.
3. **La ventana de oro 9:45-10:30 es la PEOR hora del fade** (es ventana de
   momentum, no de reversion). La hora elastica es 14:00-15:30.
4. La profundidad del pierce NO importa; ADX 5m casi no importa (el gate
   band-walk 5m ya hace ese trabajo).
5. RVOL≥1.5 es idiosincratico: climax en NVDA/AMZN/TXN/QCOM/NOK (+13…+22),
   combustible en TSLA/XLK (−17/−13). Jamas como regla de flota.
6. Ningun ticker baja del coin flip, pero AAPL/DRAM/SKHY (Wilson inferior ≈50)
   no se operan SIN filtro. NFLX es el rey del elastico.
7. Fade long 67.3% vs fade short 64.2% — sesgo del regimen alcista de estos
   30d. Recalibrar mensual: `bollinger_complements.py --force` + `--analyze`.

## Referencias en el repo

- `scripts/v5_block.cpp.tmpl` — `V5BB` (population std), `V5TF` (agregador),
  contadores `v5_bbN_dn/up_ago`, scoring 2TF/3TF.
- `dram_signal_bot.cpp` — motor clasico BB(20,3) + capitulacion confirmada
  (lineas ~40, ~611, ~878).
- `docs/V6_SPEC.md` §2.2/§2.7/§2.9 — `V6BBX` (%B, bw_pctile, squeeze),
  regimen ADX, clases SQUEEZE_BREAK_* y MTF_BB_REV_* con priors.
- Skills hermanos: `mean-reversion` (z-score/half-life), `trendline-trading`,
  `regime-detection`.
- `scripts/bollinger_complements.py` + `docs/BOLLINGER-COMPLEMENTS-2026-07.md`
  + `data/bollinger_plus.json` — evidencia B6 por ticker (seccion arriba).

## Doctrina del amigo (verificada 2026-07-22, 17 sesiones — data/bb_amigo.json)

Tres celdas, tres reglas — el mapa horario completo del BB intradia:

| Setup | AM 9:30-11:30 | PM 14:00+ |
|---|---|---|
| **Toque LIGERO** (cierre DENTRO, penetracion <30% del ancho) → rebote a media | ✅ 60.4% (QCOM 74, INTC 69, WDC 68) | ✅ 61.9% |
| **Pierce PROFUNDO + re-entrada** (elastico) → fade | ❌ 58% VETO | ✅ 75-85% con squeeze |
| **Squeeze-break que AGUANTA fuera** → continuacion 1.5×ATR | ✅ NOMBRES (WDC 89, DRAM 80, memoria 67-89) / ❌ **QQQ 36% = trampa → fadear la ruptura matinal del indice (64%)** | ~55-57% neutro |

- El toque ligero es el unico setup all-day: la banda RECHAZA cuando no la revientan.
- La manana es de CONTINUACION en nombres y de TRAMPA en el indice; la tarde es del elastico.
- Vetos AM del squeeze-break: NVDA 46, GOOGL 43, AMZN 44, ASML 46 (megacap growth = head-fake matinal).
- Vetos AM del toque ligero: AVGO 46, SMH 47, MU 50.
