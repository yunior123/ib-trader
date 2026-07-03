# Absorción y refuerzo del rebote de Bollinger (2026-08-08)

## 1. ABSORCIÓN refinada — y sigue sin valer

Buscado primero. La definición de la calle tiene **tres piezas**, no una (mi medición anterior
solo tenía la primera y media):

1. **agresión pesada** — |z| del delta acumulado en W min sobre el umbral
2. **ineficiencia** — `|Δprecio en ATR| / |z_delta|` bajo: el precio apenas se movió para tanta
   agresión (*"heavy volume but almost no price movement"*)
3. **repetición en zona** — k minutos seguidos absorbiendo dentro de un rango estrecho
   (*"repeatedly holds the same area"*)

`scripts/absorcion_study.py`, 939.784 minutos, 84 celdas:

| variante | disparos | resultado |
|---|---|---|
| 1 agresión sola (contra el delta) | 26.459 | edge +0,001 |
| 2 **absorción** (agresión + ineficiencia) | 3.720–6.929 | no llega al top |
| 3 + volumen de opciones elevado | 3.198–5.941 | no llega al top |
| 4 + repetición en zona estrecha | **0** | el filtro es tan estricto que no dispara nunca |
| 5 **CONTROL: la misma absorción operada CON el delta** | 3.720 | **es lo que puntúa más alto** |

**0 de 84 celdas pasan BH-FDR.** Y el dato incómodo: las celdas de cabeza son el **control que
opera CON el delta** (+0,041 edge, edge_lo −0,0004), no contra. O sea, en nuestros datos la
absorción se parece más a **continuación que a reversión** — y ni eso alcanza significancia.

La pieza 3 (repetición) quedó **inmedible**: exigir k=3 minutos seguidos de absorción dentro de
0,35 ATR da **cero** disparos en 85 sesiones. O el umbral es absurdo o el patrón no existe a
1 minuto en opciones. Se deja anotado, no se afloja el umbral para que salga algo.

## 2. Reforzar el rebote de Bollinger con la reversión de delta — lo mejor de la línea

Idea de Yunior. Es la pregunta correcta porque las dos partes ya estaban medidas y muertas por
separado: bollinger solo quedó UNPROVEN (0 de 117 celdas) y el delta solo también.

**Setup base** (regla 1 de la casa): el cierre 1m sale de BB(20,2) → se opera la reversión.
**Refuerzos probados**, cada uno en el sentido del fade:

| patrón | disparos | wr | null | **edge** | edge_lo |
|---|---|---|---|---|---|
| BASE bollinger solo | 48.136 | 0,503 | 0,501 | **+0,24 pp** | −0,0040 |
| **A + divergencia del delta acumulado** | 20.643 | 0,504 | 0,495 | **+0,85 pp** | **−0,0012** |
| C + delta del día ya en contra | 22.185 | 0,507 | 0,502 | +0,45 pp | −0,0048 |
| C-INV (control invertido) | 25.951 | — | — | +0,45 pp | −0,0051 |

**A triplica el edge de Bollinger solo**, y lo hace de forma **consistente en las 6 celdas** de
barrera × horizonte (no es una celda con suerte). Sigue **UNPROVEN** (edge_lo = −0,0012, roza el
cero) y **0 de 30 celdas pasan BH-FDR** — pero es el positivo más limpio de toda esta línea.

El refuerzo **C** queda descartado por su propio control: la versión invertida da exactamente lo
mismo (+0,45 pp), así que el delta acumulado del día no aporta información.

Los controles **A-INV** (divergencia al revés) y **B** (absorción en la ruptura) tuvieron 53 y 62
disparos: **no evaluables**. La divergencia en sentido contrario a la ruptura casi nunca ocurre.

## 3. Cómo queda integrado

**No como alerta nueva, sino como GATE de confirmación** sobre un setup que ya existe.
`bin/delta_imbalance` publica ahora dos campos por símbolo en `data/delta_imbalance.json`:

```
"banda": +1 | -1 | 0            cierre 1m fuera de la banda alta / baja / dentro
"refuerzo_bollinger": true      la ruptura de banda coincide con la divergencia en el sentido
                                del fade  ->  el rebote está reforzado
```

Con eso, cualquier bot o el chart puede **exigir** el refuerzo antes de fadear la banda, en vez
de fadearla a secas. Sigue sin voz y sin dimensionar: UNPROVEN es banner, no señal.

Añadido de paso `IBT_DIA=YYYY-MM-DD` al binario para poder verificarlo y hacer replay
(el sábado no hay fichero UW del día y el motor falla-alto, que es lo correcto).

## 4. Qué haría falta para subirlo a PROVEN

`edge_lo = −0,0012` con 2.403 clusters. Es cuestión de muestra: con ~2× sesiones el intervalo
debería despegarse del cero si el efecto es real. El archivo de `uw_greek_flow` crece solo.
