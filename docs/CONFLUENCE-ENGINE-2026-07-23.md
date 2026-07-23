# CONFLUENCE ENGINE — backtest 2026-07-23

**Lema:** detectar y anticipar movimientos. **Señal-solamente.** Sin look-ahead
(indicadores hasta la barra i al cierre; evaluacion desde i+1). Muestra chica
(n<30) se declara y NO es conclusion.

`scripts/confluence_engine.py` sobre `data/backtest/bars3mo5m_<sym>.csv` (5m, 62
dias) agregado a **15m**. 8 tickers liquidos: qqq spy nvda mu smh amd aapl meta.

## Herramientas (7, cada una vota LONG / SHORT / 0, causal)
1. **Bollinger(20,2)** — %B en extremo (≤0.05 long, ≥0.95 short) = reversion a SMA20 (Yoel).
2. **RSI(14)** — ≤30 long, ≥70 short.
3. **MACD(12,26,9)** — cruce de la linea de señal (momentum).
4. **Velas** — engulfing / martillo / estrella fugaz / doji en extremo de 10 barras.
5. **Trendline break** — ruptura del max/min de 20 barras previas (pivotes causales; logica conceptual `combo_tl.pine`).
6. **Volumen > MA50** — confirma la direccion de la vela (Yoel efecto-iman).
7. **VWAP diario** — cruce de recuperacion/perdida de la sesion.

Señal si **≥2 herramientas se alinean** en el mismo lado. `kind = C2/C3/C4/C5+`
= numero EXACTO de herramientas alineadas. Formato compartido
`epoch,sym,side,kind,ref_px,target_px,stop_px` (target 1.5·ATR, stop 1.0·ATR).
Baseline **BB-solo** en CSV aparte.

Salidas: `data/backtest/signals_confluence.csv` (2630), `signals_bb_baseline.csv`
(2330). Doble scoring: (a) opcion ATM semanal REAL (`real_option_scorer.py`,
Polygon, TP +100% estilo Yoel), (b) scalp del subyacente embebido (R-multiplo).

## RESULTADO A — Opcion ATM semanal REAL (el vehiculo que se opera de verdad)

TP +100% de la prima; OPT = el HIGH 5m toca +100% (orden limite), CONS = un
CIERRE 5m lo alcanza. Sin stop (la prima es la perdida maxima).

| nivel | n | OPT WR | OPT ret | CONS WR | CONS ret | veredicto |
|-------|----|--------|---------|---------|----------|-----------|
| **BB-solo (baseline)** | 1937 | **44.7%** | **−8.3%** | 41.8% | −13.9% | firme, PIERDE |
| **C2** (≥2 tools) | 1565 | 54% | +9% | 52% | +5% | firme, gana |
| **C3** (≥3 tools) | 470 | 56% | +14% | 52% | +7% | firme, mejor |
| **C4** (≥4 tools) | 127 | **59%** | **+19%** | 57% | +14% | firme-ish, el mejor |
| C5+ (≥5 tools) | 7 | 57% | +15% | 57% | +15% | **n=7 → INSUFICIENTE** |
| **TOTAL conf** | 2169 | 54% | +11% (wil 52) | 52% | +6% (wil 50) | firme |

**La confluencia SUPERA a BB-solo de forma clara y MONOTONA en la opcion.** Cada
herramienta añadida sube WR y retorno: BB-solo −8% → C2 +9% → C3 +14% → C4 +19%.
El baseline BB-solo (44.7% WR, ret negativo) confirma el aprendizaje del dia (BB
solo = breakeven/perdedor en el vehiculo opcion). C4 es el mejor (n=127, firme).
C5+ (n=7) NO es conclusion — se necesita mas muestra.

## RESULTADO B — Scalp del subyacente (target 1.5·ATR / stop 1.0·ATR, 8 barras)

| nivel | n | WR | avgR | wilson |
|-------|----|-----|------|--------|
| BB-solo | 2330 | 40.9% | −0.029 | 38.9% |
| C2 | 1894 | 40.3% | −0.051 | 38.1% |
| C3 | 572 | 37.1% | −0.124 | 33.2% |
| C4 | 156 | 41.7% | −0.002 | 34.2% |
| C5+ | 8 | 12.5% | −0.782 | n<30 |
| C≥2 | 2630 | 39.6% | −0.066 | 37.7% |
| C≥3 | 736 | 37.8% | −0.105 | 34.3% |

**En el scalp simetrico del subyacente la confluencia NO bate a BB-solo** — todos
rondan ~40% WR con avgR ≈ 0 / ligeramente negativo. C4 es breakeven (avgR −0.002)
pero no supera al baseline de forma util.

## Lectura honesta (la divergencia A vs B es el hallazgo)
- La confluencia de 3-4 herramientas aporta valor **especificamente al vehiculo
  OPCION** (pago convexo asimetrico, TP +100%, sin stop): cuando 3-4 herramientas
  distintas coinciden marcan movimientos mas grandes y sostenidos que la prima
  captura. El scalp simetrico (stop apretado) muere en el ruido antes de que el
  movimiento se desarrolle — por eso B se queda en ~40%.
- Coherente con la doctrina Yoel: opcion semanal ATM, sin stop, TP +100%. La
  confluencia es un **filtro de calidad de entrada para la opcion**, no para scalp
  apretado de acciones.
- **Regla operativa sugerida:** exigir **C3+** para armar la opcion (WR 56%, ret
  +14%, n=470 firme); **C4** si se quiere maxima calidad (WR 59%, +19%, n=127).
  Nunca C5+ como gatillo hasta acumular n≥30.

## Reproducir
```
venv/bin/python scripts/confluence_engine.py            # genera CSVs + scalp
venv/bin/python scripts/real_option_scorer.py data/backtest/signals_confluence.csv
```
Vars: `CONF_TF` (min, def 15), `CONF_H` (barras horizonte scalp, def 8). Argumentos
posicionales = lista de symbols. Degradacion limpia: symbol sin CSV se salta.

**Limites:** 8 tickers liquidos (opcion semanal con liquidez); 62 dias 5m; regimen
unico del periodo (no cubre todos los regimenes gamma). C5+ y todo n<30 = no
concluyente. No mide spread/slippage de la opcion — el WR es sobre el pago teorico
de la prima 5m de Polygon.
