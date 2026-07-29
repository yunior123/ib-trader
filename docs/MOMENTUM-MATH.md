# MOMENTUM-MATH — ecuaciones del calculador (2026-07-21, orden Yunior)

Lección que codifican: "si hubiésemos entrado en el DIP del día y vendido en el momentum,
habríamos hecho más que $10; ganamos poco los días buenos y perdemos media cuenta los malos."
Objetivo: NO comprar la cima de la colina; comprar el dip con tendencia; salir cuando el
impulso envejece más allá de lo MEDIDO (data/momentum_decay.json).

## 1. Momentum con memoria (EMA de retornos, half-life h=4 min — mediana medida del impulso ≈5)
    r_t = ln(P_t / P_{t-1})
    λ = 1 − 2^(−1/h)
    M_t = λ·r_t + (1−λ)·M_{t−1}          → signo = dirección del impulso vivo

## 2. Eficiencia de Kaufman (¿tendencia limpia o picadora?)
    ER(n) = |P_t − P_{t−n}| / Σ_{i=t-n+1..t} |P_i − P_{i−1}|      n=10
    ER > 0.6 = tramo limpio · ER < 0.3 = chop/trampa (los dealers muelen ahí)

## 3. Extensión vs valor justo (¿cima de la colina?) — VWAP z-score
    VWAP_t = Σ(TP_i·V_i)/Σ(V_i),  TP=(H+L+C)/3   (desde apertura)
    σ_vwap = std(TP_i − VWAP_i)
    z_t = (P_t − VWAP_t)/σ_vwap
    |z| > 2.0 = extendido · |z| > 2.5 = CIMA/SIMA — prohibido comprar en esa dirección
    z < −1.5 con pendiente VWAP > 0 = DIP DEL DÍA en tendencia alcista (la compra buena)

## 4. Edad del impulso vs decaimiento MEDIDO
    A_t = minutos consecutivos con signo(M_t) constante
    med, p75 = data/momentum_decay.json (por lado y sesión; fallback 5/11 bull, 5/13 bear,
               bear-mañana p75=6 — los más traicioneros, 91% retroceden)
    A < med        → IMPULSO (joven, montable con print)
    med ≤ A ≤ p75  → MADURO (no entrar; si dentro, stop al 38.2% del tramo)
    A > p75        → AGOTAMIENTO (estadísticamente muerto; esperar retroceso)
    signo(M) voltea desde |z|>2 → GIRO

## 5. Score de TRAMPA de dealers (0-100, mayor = más trampa)
    T = 30·[[|z|>2]] + 25·[[ER<0.3]] + 20·[[V̄_3 < 0.7·mediana_20(V)]]
      + 15·[[A>p75]] + 10·[[ruptura de banda sin seguimiento (%B>1 y M_t decreciente)]]
    T ≥ 50 = TRAMPA PROBABLE — la "ruptura" es distribución, no continuación
    (Recordar: 91% de rupturas bajistas de mañana retroceden >50% en 30 min — medido.)

## 6. Señal DIP-DEL-DÍA (la entrada que nos faltó hoy)
    COMPRA-DIP válida si TODAS:
      z < −1.5  Y  pendiente_VWAP(30m) > 0  Y  ER recuperando (>0.35)
      Y  print de reclamo (2 lecturas sobre el nivel del dip)
      Y  hora ∉ [11:30, 14:00]
    Vender: cuando A > p75 del lado bull O z > +2 (la colina) — lo que llegue primero.

Implementación: `scripts/momentum_calc.cpp` → binario `bin/momentum_calc SYM` (C++2b -O3).
Umbrales medidos: `data/momentum_thresholds.txt` (regenerado semanal por auto-mejora).
REGLA: el copiloto CORRE el calculador antes de cada veredicto de ticker (junto al
gráfico y NBBO — regla gráfico-primero).
