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

---

## 3-bis. Win rate medido COMO SE OPERA UNA OPCION (correccion de Yunior)

*"el win rate da igual la fecha de las opciones, es solo q llegue a su objetivo asi sea antes,
mide por ahi"*. Tenia razon: mi primera medicion usaba horizontes fijos (H=1/3/5/10) y eso no
es como se cobra una opcion comprada. Rehecho (`scripts/architect_target.py`):

> **GANA** = el subyacente TOCO el strike en ALGUN momento entre la entrada y el vencimiento.

Vencimiento: el publicado; si no, deducido del texto (WEEKLIES/FRIDAY → viernes, NdTE → N
sesiones, LEAPS → 90 dias) y la regla usada va publicada operacion a operacion. 28 evaluadas
(1 saltada por estar ya ITM al entrar).

### El numero

| | |
|---|---|
| **Llego al strike antes de vencer** | **39,3%** (11 de 28) |
| Control: mismo ticker, misma distancia %, mismos dias, fecha AL AZAR | 55,3% |
| **EDGE** | **−16,0 pp**, t emparejado **−2,66** |

Y con el control apretado al mismo REGIMEN (fecha al azar dentro de ±10 sesiones de su propia
entrada, para que no sea la deriva del periodo la que decide):

| control | base | suyo | edge | t |
|---|---|---|---|---|
| ±10 sesiones | 57,6% | 39,3% | **−18,3 pp** | **−3,14** |
| ±20 sesiones | 52,3% | 39,3% | −13,0 pp | −2,27 |

**Su temporizacion no solo no añade: RESTA.** Comprar el mismo contrato en una fecha al azar
de la misma quincena habria funcionado mejor, y la diferencia es significativa.

### El mecanismo, que es lo interesante

| tipo de objetivo | n | acerto |
|---|---|---|
| **FACILES** (tasa base ≥70%: el strike estaba casi pegado) | 10 | **9 (90%)** |
| **DIFICILES** (tasa base <40%: el strike exigia un movimiento real) | 9 | **0 (0%)** |

Distancia media al strike: **ganadoras +2,7% · perdedoras +13,7%**.

Gana cuando el objetivo era practicamente gratis —NVDA 210C a +0,7% con base 97%, AAPL 290C a
+0,2% con base 100%, C 145C a +1,4% con base 98%— y va **0 de 9** cuando el strike exigia de
verdad un movimiento (MU 1000C a +25,7%, AMKR 110C a +52,4%, ASX 55C a +27,0%, MRVL 350C a
+21,2%, ARM 470C a +18,6%).

Eso explica su linea de tiempo: los near-the-money se publican con "DOINK 100%", y los lottos
lejanos vencen en silencio.

**n=28 y solo lo que ANUNCIO como entrada** (los 22 tuits que eran reportes de P&L ya ganado
se descartaron: contarlos seria hindsight). Con esa muestra el intervalo es ancho, pero el
signo es consistente en los tres controles y el desglose facil/dificil no deja mucho margen
a la interpretacion.
