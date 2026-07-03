# YOEL ENGINES — PURO vs ADAPTADO (2026-07-23)

Mision 3. Dos motores que emiten el **formato compartido** de señales y se puntuan
sobre el **pago de OPCION REAL** de Polygon (ATM semanal, TP +100%, sin stop — el
metodo Yoel) con `scripts/real_option_scorer.py`.

- `scripts/yoel_engine.py` — **YOEL PURO**: la geometria del libro tal cual
  (top-down 15m→1H→1D, sin stop). 4 estrategias mecanizables desde OHLCV:
  `rebote_sma20` (rebote punto medio, confluencia 1H+1D + toque SMA20 diaria),
  `iman` (precio ≥2 ATR de la media + 15m fuera de banda + vol>MA50 + reversion),
  `cambio_tend` (SMA20 1H voltea pendiente y el precio la cruza, confirma 15m),
  `fuera_banda` (1a vela del dia fuera de la BB diaria → fade).
- `scripts/yoel_adapted_engine.py` — **YOEL ADAPTADO**: las MISMAS señales pero
  filtradas por lo nuestro: prior Bollinger medido (`bollinger_plus.json`, base
  ≥50%), **veto band-walk** (un `iman` contra banda que camina en 15m Y 1H = no es
  rebote elastico, es continuacion), **confirmacion de flujo** (`flow_intraday_<sym>`
  put/call, 5 syms) y **overlay optgate** (spread, solo en vivo — ver caveat).

Datos: `bars3mo5m_<sym>.csv` (5m, 62 dias, 30 tickers). Sin look-ahead: gatillo con
barras cerradas ≤ t, entrada al open de la barra siguiente.

## Resultado (opcion ATM semanal REAL, TP +100%)

OPT = optimista (el HIGH real de la prima toca +100%). CONS = conservador (solo si
un CIERRE 5m real lo alcanza). `wil` = Wilson lo 95%.

### YOEL PURO
| estrategia | n | OPT WR | OPT ret/trade | CONS WR | CONS ret/trade |
|---|---:|---:|---:|---:|---:|
| cambio_tend  | 226 | 64% | +31% | 63% | +29% |
| fuera_banda  |  46 | 67% | +39% | 63% | +31% |
| iman         | 291 | 47% |  +1% | 45% |  -2% |
| rebote_sma20 |  25 | 56% | +12% | 52% |  +4% |
| **TOTAL**    | **588** | **55%** | **+16%** (wil51) | **54%** | **+13%** (wil50) |

### YOEL ADAPTADO
| estrategia | n | OPT WR | OPT ret/trade | CONS WR | CONS ret/trade |
|---|---:|---:|---:|---:|---:|
| cambio_tend  | 220 | 64% | +31% | 63% | +28% |
| fuera_banda  |  46 | 67% | +39% | 63% | +31% |
| iman         | 116 | 48% |  +3% | 46% |  -2% |
| rebote_sma20 |  23 | 52% |  +8% | 48% |  -1% |
| **TOTAL**    | **405** | **59%** | **+22%** (wil54) | **57%** | **+18%** (wil52) |

(De 726 señales puras se resolvieron 588 con contrato/entrada real; de 496 adaptadas, 405.)

## ¿El adaptado supera al puro? SI — y por la razon correcta

- **TOTAL sube**: 55%→**59%** WR y +16%→**+22%** ret (OPT); Wilson_lo 51→54. En
  conservador 54%→57%, +13%→+18%. La cartera adaptada es **mas rentable Y con piso
  Wilson mas alto**, es decir mas segura.
- **La palanca es la poda del `iman`**: el veto band-walk elimino **207** fades
  malos (iman 370→150 en emision; 291→116 puntuados). El `iman` es el pato feo del
  metodo (47% WR ≈ breakeven) — comprar el rebote contra una banda que camina es
  justo el error de CLAUDE.md regla 1. Quitar los peores sube la mezcla global.
- **Flujo**: descarto 23 señales que el put/call contradecia (solo 5 syms con
  fichero: spy/qqq/smh/nvda/mu). Efecto pequeño pero en la direccion correcta.
- **Lo que el adaptado NO toca**: `cambio_tend` (64%, +31%) y `fuera_banda`
  (67%, +39%) — los caballos ganadores — quedan practicamente id+enticos porque los
  filtros (band-walk, flujo-5syms) casi no aplican ahi. Bien: no se rompe lo que
  funciona (regla de oro aditiva).

## Lectura por estrategia (honesta)

- **fuera_banda** (67%/+39%) y **cambio_tend** (64%/+31%) son el nucleo fuerte y
  con n usable (46 y 226). Aqui esta el edge de Yoel de verdad.
- **iman**: 47-48% WR, retorno ≈ 0. Como fade puro NO paga la prima. El adaptado lo
  reduce pero no lo salva (el 48% que queda sigue siendo flojo). Recomendacion:
  operarlo solo con confluencia extra o degradarlo a contexto, no gatillo.
- **rebote_sma20**: n=25/23 → **MUESTRA CHICA, NO es conclusion**. 56%/52% es
  ruido; el rebote-punto-medio necesita mas historico (o mas tickers/dias) antes de
  afirmar nada. El adaptado no lo mejora (mismo puñado de trades).

## Caveats (sin maquillaje)

1. **n por estrategia moderado-chico**; `rebote_sma20` (n<30) queda declarado como
   no-concluyente. Wilson_lo total ~51-54% dice: edge real pero modesto, no loteria.
2. **optgate (spread) NO esta medido** en el backtest: el cache de cadena es de
   AHORA, no se reproduce en fechas historicas. En vivo el adaptado llama
   `optgate.opt_vehicle(sym)` y descarta lo VETADO — solo puede empeorar levemente
   el conteo y mejorar la calidad, nunca inflar el WR aqui reportado.
3. **Flujo solo en 5 syms** (spy/qqq/smh/nvda/mu) — el resto pasa por degradacion
   limpia. Cuando el flujo fino cubra la flota, el filtro tendra mas mordida.
4. Entrada = open de la barra 5m siguiente al gatillo; TP OPT usa el HIGH de la
   prima (orden limite intradia). Es optimista frente a llenado real; por eso el par
   CONS (solo cierres) se reporta siempre al lado.

## Ficheros
- `scripts/yoel_engine.py`, `scripts/yoel_adapted_engine.py`
- `data/backtest/signals_yoel_pure.csv`, `data/backtest/signals_yoel_adapted.csv`
- `data/backtest/scores_real_options_all.json` (salida del scorer)
- Reusa: `real_option_scorer.py` (resolve/opt_path/poly), geometria de
  `yoel_faithful_backtest.py` y `yoel_real_options_backtest.py`.
