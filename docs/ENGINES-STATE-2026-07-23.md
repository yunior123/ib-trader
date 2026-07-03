# Estado de los engines — síntesis sobre datos REALES (2026-07-23)

Todo puntuado sobre **opción ATM semanal REAL de Polygon** (TP +100%, sin stop = la prima
es la pérdida máxima, método de la casa) y/o el subyacente. Wilson honesto; n<30 = no
conclusión. Sin look-ahead. Señal-solamente.

## Tabla maestra (lo que PAGA vs lo que NO)

| Motor / señal | Vehículo | n | WR | Ret/trade | Veredicto |
|---|---|---|---|---|---|
| **Yoel cambio-de-tendencia** (SMA20 1H voltea + cruce + confirma 15m) | opción real | 226 | **64%** | **+31%** | ✅ EDGE (n grande) |
| **Yoel fuera-de-banda apertura** | opción real | 46 | **67%** | **+39%** | ✅ EDGE |
| **Confluencia C4** (4+ herramientas alineadas) | opción real | 127 | **59%** | **+19%** | ✅ EDGE |
| Confluencia C3 | opción real | 470 | 56% | +14% | ~ marginal |
| Confluencia C2 | opción real | 1565 | 54% | +9% | ~ marginal |
| Yoel imán (fade) | opción real | 291 | 47% | +1% | ❌ débil |
| **BB solo** (comprado) | opción real | 1937 | **45%** | **−8%** | ❌ PIERDE (theta) |
| **Flow-fade 5-min** (spike → fade) | subyacente | 839 | **52%** | ~0 | ❌ sin edge (FIRME) |
| Flow-fade horario | subyacente | 22 | 43% | −23% | ❌ |
| Flow P/C diario (fade extremos) | subyacente | — | — | −53% | ❌ es continuación |
| Confluencia (cualquiera) | subyacente scalp 15m | 2630 | ~40% | ~0 | ❌ breakeven |

## La lección única
**El edge está en la SELECTIVIDAD, no en el gatillo.** Todo lo que dispara fácil y fadea
reversión ingenua (BB solo, flow-spike, imán) = sin edge o pierde. Todo lo que EXIGE
confluencia/cambio-de-régimen antes de comprar prima convexa (Yoel cambio_tend, confluencia
C4) = paga. En la opción comprada la asimetría +100%/−prima premia los movimientos grandes
y limpios que el filtro selecciona, y castiga los pokes marginales que sangran theta.

Corolario medido: en el SUBYACENTE la confluencia se ve plana (~40%, scalp 1.5ATR/1.0ATR),
pero en la OPCIÓN escala monótona (C2 54 → C3 56 → C4 59). **Puntuar en el vehículo real
cambia el veredicto** — hay que medir sobre la opción, no el subyacente.

## Qué desplegar (recomendación)
1. **Filtros selectivos como gatillo primario**: Yoel cambio-de-tendencia y confluencia C4.
   Son los dos edges con n usable y retorno positivo en el vehículo real.
2. **Yoel-adaptado > Yoel-puro** (medido antes): mismas señales + veto band-walk nuestro,
   59% vs 55%, poda 207 fades de imán malos. El más seguro.
3. **`gex_gate.py` como veto EN VIVO** (overlay, no backtesteado — límite honesto): veta LONG
   pegado al call wall / SHORT al put wall (~70% rebote 1er toque), y modula prob por régimen
   (POS favorece fades, NEG favorece continuación). Contexto que sube/baja prob, no gatillo.
4. **El flow-spike NO como fade** (n=839 firme). Sigue sirviendo como marcador de EXTREMO
   local (espada-ballena) y como contexto de capitanes, pero comprar el fade no tiene edge
   medido. Recalibrar el detector 5-min de SMH (646 spikes = sobre-disparo) es tarea aparte.

## Límites honestos declarados
- **GEX histórico no medido**: exige OI+gamma por día (no disponible barato). El gate GEX es
  overlay en vivo; jamás se cableó por teoría sin número.
- **n chico engaña en ambas direcciones** (los 76%/n=17 del flow eran suerte). Solo n>100 con
  Wilson>50 se trata como edge. fuera-de-banda (n=46) y C4 (n=127) son prometedores pero se
  acumulará más histórico antes de subir su peso.
- Nada cableado a los bots en este pase sin el número que lo respalde.

## Archivos
`scripts/yoel_engine.py` · `yoel_adapted_engine.py` · `confluence_engine.py` ·
`flow_scalp_backtest.py` · `real_option_scorer.py` · `gex_core.py` · `gex_gate.py` ·
`chart_levels.py`. Docs hermanos: YOEL-ENGINES-2026-07-23.md, FLOW-SCALP-2026-07-23.md,
ENGINES-REAL-OPTIONS-2026-07-23.md. Skill: `gamma-exposure`.
