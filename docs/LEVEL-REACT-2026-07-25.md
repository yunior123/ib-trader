# `level-react` (ficha #8) — construido, MEDIDO, y mudo con razón

**Fecha**: 2026-07-25 · **Ola 2** · **Estado**: EMBARCADO CON LA VOZ APAGADA
**Veredicto de la medición**: los niveles reconstruibles **NO superan la vara. Refutados.**

---

## 1. Qué se construyó

| Fichero | Qué es |
|---|---|
| `scripts/level_react.h` | El motor. Registro topado a 6 tipos + una máquina de estados por nivel. Header-only para el include de una línea en los bots |
| `scripts/level_react.cpp` | CLI. `--ev-stdin` (arnés de test) y modo ficheros de la flota |
| `scripts/build_level_react.sh` | `-std=c++23 -O3 -mcpu=native -Wall -Wextra`, cero warnings + ASan/UBSan |
| `tests/test_level_react.py` | 17 tests. Python es solo arnés: conduce el binario por stdin, cero cómputo |
| `scripts/level_react_validate.py` | El null de nivel aleatorio sobre `poly_bars` — el arnés que puede matarlo |
| `scripts/level_events_ingest.py` | JSONL → `trades.db level_events`, retención 180 días |

## 2. El problema que resuelve, con la línea exacta

`qqq_signal_bot.cpp:1085`, y variantes copiadas a mano por ~30 bots (44.379 líneas medidas):

```cpp
bool touch = ib ? (b.l <= a.level + 0.25 * atr && b.l >= a.level - 0.25 * atr) : ...
```

Eso es **"el precio está CERCA del nivel"**. La doctrina (CLAUDE.md regla 2) dice **PRINT O NADA**.
`level_react` sustituye 30 definiciones divergentes por una sola, mecánica: **straddle de dos
barras CERRADAS**.

**MEDIDO** sobre los 30 `bars_*_ibkr.txt` de la flota:

| | |
|---|---|
| candidatos `BOUNCE`+`RETEST_REJECT` | **1.511** |
| sobreviven al print de 2 barras | **249 (16,5%)** |
| **descartados por no estar impresos** | **1.262 (83,5%)** |

Cinco de cada seis gatillos de reversión que hoy pasarían por proximidad **no están impresos**.

## 3. La medición que lo refuta — y por qué se publica igual

**MEDIDO** — `scripts/level_react_validate.py`, 6 syms × **1.398 sesiones** de `poly_bars`,
triple barrera `k=1.5·ATR`, `H=30` barras, **el timeout NO es victoria**:

| | n | tasa | Wilson-LB |
|---|---|---|---|
| Niveles REALES (POC_DOM, ROUND, PDH/PDL) | 5.415 | **0,3734** | 0,3606 |
| NULL (mismos patrones a precios aleatorios) | 41.169 | **0,3905** | 0,3858 |
| **delta** | | **−1,71 pp** | vara: **+6,00 pp** |

Los intervalos de Wilson **no se solapan** por ese lado: el nivel real no es "igual que el azar",
es **significativamente PEOR**.

**Curva de sensibilidad** (QQQ+SPY, 40 sesiones) — el delta es negativo en los cuatro umbrales,
así que no es un artefacto de la barrera elegida:

| `k` | real | null | delta |
|---|---|---|---|
| 0.5 | 19,10% | 23,88% | **−4,79 pp** |
| 1.0 | 33,17% | 34,75% | **−1,58 pp** |
| 1.5 | 35,68% | 39,43% | **−3,75 pp** |
| 2.5 | 42,71% | 45,03% | **−2,32 pp** |

La vara (**+6pp**, del prior de Osler 2000: 60,8% vs 56,2%) se fijó en la ficha **antes** de
escribir código, y no se movió después de ver el resultado. Ese es el punto entero del método.

### Consecuencia operativa
- **`POC_DOM`, `ROUND` y `GAP_EDGE`/PDH-PDL NO pueden ganar voz.** No es que les falte `n`: tienen
  `n=5.415` y el resultado es negativo. Están **refutados**, como `cusum`.
- La feature **sigue embarcando**, porque su valor demostrado es otro: **una sola definición de
  reacción a un nivel** en vez de 30 que no coinciden, y el descarte del 83,5%.

## 4. Lo que esta medición NO dice

**No dice nada sobre los muros.** `OI_CALL_WALL`, `OI_PUT_WALL`, `ABS_WALL` y `FLIP_OPEN` **no se
pueden reconstruir hacia atrás**: no existe historia de OI a ningún precio en este plan — el
`?as_of=` del snapshot de Polygon devuelve `status OK` e **ignora la fecha**. Los muros son
justamente los niveles que la doctrina considera campos de fuerza, y siguen **sin medir**.

Por eso existe `level_events_ingest.py`: es su **única** vía de acumulación forward-only.
Primera ingesta **MEDIDA**: 5.457 eventos, de los cuales **3.945 son celdas de muro** y 249
operables.

## 5. Decisiones de diseño que son leyes, no gusto

- **La voz embarca APAGADA** y el binario **no incluye `fleet_notify.h`**: estructuralmente no hay
  voz que encender. Un test lo verifica sobre las líneas `#include`.
- **Solo `BOUNCE` y `RETEST_REJECT` son operables.** `TOUCH` es consolidación; una primera `BREAK`
  sin retest es la trampa del post-mortem 2026-07-20.
- **`touch_ord` sube solo tras una excursión ≥ 0,5·ATR.** Sin eso, el chop pegado al nivel fabrica
  un "3er toque, muro exhausto" en cuatro minutos.
- **Sin ATR no hay veredicto** (`rc=3`). Un ATR inventado da un buffer concreto y convierte "no sé"
  en "sé, y es cero".
- **`flip_open` ausente** → se usa el flip vivo y se **declara** `flip_src=live_fallback`. La
  congelación es media feature; perderla en silencio sería mentir.
- **El binario no escribe en `trades.db`.** 30 bots incluyéndolo serían 30 escritores peleando por
  el lock de una BD de 1,53 GB **en el camino de señal**.

## 6. Lo que queda fuera, y por qué

**El cableado a los ~30 `*_signal_bot.cpp` NO se hizo.** El valor de "borrar código" está en ese
cableado, y se difiere a propósito por tres razones: (1) son ~30 recompilaciones en un Mac de 8 GB
con la regla de un solo `clang++`; (2) la flota está **parada** a propósito, así que el cableado no
se puede verificar en vivo hoy; (3) con la voz apagada y las celdas reconstruibles **refutadas**,
cablearlo hoy no cambia ni una alarma — solo añade riesgo a 30 binarios que funcionan.

Se cablea cuando haya una sesión de mercado para verificarlo, bot a bot.
