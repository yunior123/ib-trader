# OVI, Zero Lag y el win rate real de @astocks92 (2026-08-08)

## 1. OVI — Option Volume Imbalance

**Buscado primero**, como pediste. Hay DOS cosas con ese nombre y no son la misma:

- **OVI de Guy Cohen** — propietario, oscila −1..+1, mezcla volumen con cambio de OI. No es
  reproducible: no publica la fórmula.
- **Option Volume Imbalance** (arXiv 2201.09319) — el académico, y el que coincide con tu
  frase. Afirma: el desequilibrio normalizado entre volumen de visión alcista y bajista
  predice el retorno direccional, **el horizonte con señal es el OVERNIGHT**, las opciones de
  IV alta informan más, y las **puts** predicen mejor que las calls.

Implementado el académico (`scripts/ovi.py`) sobre `uw_flow_per_strike` archivado —
**2.376 observaciones, 30 símbolos, 84 días**. Tres variantes en [−1,+1]:

```
OVI_cp    = (vol_call − vol_put) / (vol_call + vol_put)
OVI_vista = (alcista − bajista) / (alcista + bajista)      <- el del paper
            alcista = calls compradas (ask) + puts vendidas (bid)
            bajista = puts compradas (ask) + calls vendidas (bid)
OVI_otm   = solo volumen fuera del dinero (proxy de IV alta)
```

**Resultado — sale CONTRARIAN, no direccional.** Seguir el desequilibrio pierde:

| variante | retorno | win rate | media | t (n de días) |
|---|---|---|---|---|
| OVI_vista | **overnight** | 44,9% | **−0,238%** | **−2,09** |
| OVI_vista | total | 49,5% | −0,431% | −2,10 |
| OVI_cp | intradía | 44,9% | −0,209% | −1,59 |
| OVI_otm | intradía | 53,9% | +0,222% | +1,25 |

Con el test correcto (spread transversal largo‑corto por día, quintiles) el sesgo se queda en
**t = −1,75** para OVI_vista total: **no significativo**. Pero el signo es consistente en las
tres variantes y en los tres horizontes, y coincide con la regla 11 de la casa (fadear el
extremo de flujo de ballenas).

**VEREDICTO: UNPROVEN, con sesgo contrarian.** Lo que SÍ queda claro es que la lectura ingenua
("mucho volumen de calls = alcista") está medida y es **falsa** en nuestro universo.

## 2. Zero Lag Trend Signals (MTF) [AlgoAlpha] — añadido, y medido

Port fiel del Pine v5 a C++23 (`scripts/zerolag.cpp` → `bin/zerolag`).

**Medido ANTES de enchufarlo** (`scripts/zerolag_backtest.py`, 939.784 minutos, 30 syms):

| señal | n | win rate | null | edge |
|---|---|---|---|---|
| entrada (flecha pequeña) | 10.838 | 0,496 | 0,494 | +0,12 pp |
| giro de tendencia (flecha grande) | 5.607 | 0,389 | 0,392 | −0,28 pp |

**0 de 24 celdas pasan BH‑FDR q=0,10.** Plano.

Por eso el binario es **DESCRIPTIVO**: publica `data/zerolag.json`, no canta señales y no tiene
voz. Lo que sí aporta es la **tabla multi‑temporalidad**, que es el valor real del indicador:

```
SPY    5m=+ 15m=- 60m=- 240m=+ 1D=+  (3/5 alcistas)
NVDA   5m=+ 15m=+ 60m=+ 240m=+ 1D=+  (5/5 alcistas)
```

Para que 60m/240m/1D tengan las 212 velas que pide `length*3` hizo falta
`scripts/export_hist_bars.py` (vuelca meses de `poly_bars` a `data/bars_hist_<sym>.txt`); el
binario lee el histórico y le superpone el vivo.

## 3. Win rate REAL de @astocks92

De sus 610 tuits se extraen **53 operaciones concretas** (ticker + strike + C/P). Se descartan
**22** que no son entradas suyas (reportes de P&L ya ganados, flujo de terceros) — incluirlas
sería hindsight puro. Quedan **29 entradas anunciadas** con precio: **25 calls, 4 puts**.

| horizonte | SUYO | **SIEMPRE LARGO el mismo ticker** | SPY |
|---|---|---|---|
| H=1 | 55,2% · −0,25% | 55,2% · −0,53% | −0,11% |
| H=3 | **59,3%** · +0,43% | 55,6% · +0,30% | +0,29% |
| H=5 | 44,0% · −2,10% | 48,0% · −1,62% | +0,05% |
| H=10 | 52,2% · −0,66% | 52,2% · −0,89% | −0,03% |

**Su win rate ES el de estar largo esos mismos nombres.** El 86% de sus entradas son calls, así
que "acertar la dirección" y "el ticker subió" son la misma cosa. El retorno medio es NEGATIVO
en 3 de los 4 horizontes.

Y son opciones: **strike a +6,2% de media** del spot, y **solo 15 de 29 (51,7%)** llegaron a
tocar el strike antes del vencimiento. Con theta y a esa distancia, un 51,7% de toques con la
dirección a cara o cruz **pierde dinero**.

n=29 es muestra chica y se dice. Pero no hay ni rastro de la precisión que publica.
