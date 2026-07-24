---
name: bug-hunter
description: Cacería de bugs en la flota ib-trader — catálogo de OLORES demostrados reales (auto-cancelación por callback no solicitado, default silencioso en órdenes, tope por-unidad vs por-orden, guarda de frescura muerta, test que no incluye el código, look-ahead por rebanado, backtest sin costes, lógica clonada ×24), cada uno con su grep de detección, y el workflow multi-agente con verificación adversarial. Usar antes de un despliegue, tras tocar el camino del dinero, al auditar TODOS.md, o cuando Yunior pida "cazar bugs", "find bugs", "revisar el sistema", "errores financieros" o "edge cases".
---

# Bug hunter — flota ib-trader

Destilado de la cacería del **2026-07-24** (87 hallazgos brutos, 6 confirmados a mano
y arreglados). Cada olor de aquí **se cazó de verdad en este repo** — no son buenas
prácticas genéricas.

## Ley 0 — el ranking es por DINERO, no por elegancia

```
dinero-real  >  señal-falsa  >  operativo
```
Un bug que manda una orden mal vale más que veinte de estilo. Si un hallazgo no
tiene `file:line` **y** un escenario concreto (entradas → salida incorrecta), no
es un hallazgo: es una corazonada.

## Ley 1 — sin refutación no hay hallazgo

La cacería del 24-jul devolvió **87 hallazgos, 0 refutados** — pero sólo porque los
refutadores se quedaron sin presupuesto y nunca corrieron. Cero refutados **no**
significa cero falsos positivos; significa cero verificación.

> Un hallazgo sin verificar es materia prima. Nunca lo reportes como hecho.
> Ante la duda: `refuted = true`. Un falso positivo cuesta más que uno perdido,
> porque Yunior actúa sobre lo que le decimos.

---

## Catálogo de olores (todos cazados aquí)

### 1. Callback no solicitado que se confunde con estado huérfano ⭐ el peor
`openOrder()` cancelaba cualquier orden `OE:` sin comprobar si era **nuestra y de
esta sesión**. TWS emite ese callback **sin pedirlo** por cada orden colocada → el
motor se cancelaba a sí mismo. Evidencia: `ledger/orders.jsonl` id=33, un `intent`
y **cinco `cancel`** que nadie pidió en 150 ms.

**Detección**: toda rutina de reconciliación necesita una ventana explícita.
```bash
grep -n 'cancelOrder\|cancel(' order_engine/*.cpp | grep -v 'reconciled_'
```
**Regla**: reconciliar sólo entre `reqAllOpenOrders()` y `openOrderEnd()`. Fuera de
esa ventana, un callback es información, no una orden de matar.

### 2. Default silencioso en un campo de dinero ⭐
`chart_bridge` no pasaba `side` y el motor caía a `'S'` (SELL). Cerrar un **corto**
manda `"buy"` → se vendía otra vez y **duplicaba el corto**. Con largos coincidía
por casualidad: por eso sobrevivió meses.

**Detección**:
```bash
grep -rn 'c.s("side"\|get("side"\|== "buy") ?' --include=*.cpp --include=*.py
```
**Regla**: en una orden, un campo ausente se **RECHAZA**, no se adivina. El default
que "casi siempre acierta" es el más peligroso: no falla hasta que importa.

### 3. Tope por-unidad donde hace falta por-orden ⭐
`run_gate` validaba la prima de **un** contrato; el desembolso real era `qty × prima`.
Las acciones sí tenían control de notional; las opciones no.

**Detección**: por cada control de presupuesto, preguntar *"¿de qué es este tope:
de la unidad o del total?"*.
```bash
grep -rn 'budget\|presupuesto\|max_order' --include=*.cpp --include=*.py | grep -v 'qty'
```
**Regla**: `qty` que viene de una UI **siempre** se valida en el motor. El `<input>`
no es una validación — es una sugerencia.

### 4. Reset a ciegas de un recurso que otro adoptó ⭐
Tras reconnect el motor reseteaba `stop_armed/stop_id` creyendo que reconcile había
cancelado el stop viejo — pero `openOrder` los **adopta**. Resultado: dos STP sobre
la misma posición → al disparar vendía el doble y te dejaba **corto en descubierto**,
ambos GTC. Se dispara en cada reconexión, y el Gateway reinicia a diario.

**Regla**: antes de recrear un recurso tras una reconexión, **preguntar si sigue
vivo**. Y desconfía del comentario: aquí decía "reconcile canceló el stop viejo" y
era falso desde otro commit.

### 5. Estado parcial que no avanza la máquina ⭐
`orderStatus` sólo emitía FILL con `remaining <= 0`. Un parcial vivo caía a ACK, el
FSM no pasaba a FILLED y la posición **real** quedaba sin stop hasta que TWS matara
la DAY al cierre. Horas desnudo, justo en el caso más probable de un libro fino.

**Regla**: todo estado intermedio (parcial, degradado, a medias) necesita su rama.
El camino feliz nunca es el que te arruina.

### 6. Guarda de frescura muerta por un parser mudo ⭐
`index_breadth.py` partía por `,` archivos separados por **espacio** → la condición
nunca se cumplía, la guarda de 600 s era **código muerto** y cada corrida caía en
silencio a una cotización retrasada.

**Detección**:
```bash
grep -rn "split(',')\|split(\",\")" scripts/*.py     # ¿el archivo es CSV de verdad?
grep -rLn 'getmtime\|MAX_AGE\|stale' scripts/*.py    # lectores sin chequeo de edad
```
**Regla**: un parser que falla debe **gritar**, no devolver `None`. Y todo dato que
alimenta una decisión viva lleva chequeo de edad — `order_ticket.py:72` (`MAX_AGE_S=900`)
es el patrón bueno del repo.

### 7. El test que no incluye el código ⭐⭐ el más traicionero
`tests/cpp/math_test.cpp` reimplementaba EMA/SMA/RSI/ATR/BB/VWAP/CUSUM en copias
privadas y las testeaba a ellas. **Cero `#include` del proyecto.** El "25/25 pass"
no decía nada sobre nada. Las aserciones eran además tautológicas: `atr >= 0`,
`rsi > 70` — pasan con casi cualquier implementación, incluida una rota.

**Detección**:
```bash
grep -L '#include "' tests/**/*.cpp          # tests sin incluir codigo del repo
grep -rn 'assert.*>= 0\|> 70\|< 30' tests/   # aserciones sin valor de referencia
```
**Regla**: un test necesita **valores de referencia calculados a mano** (var
poblacional de 1..20 = 33.25 exacto; Wilder = (2·13+12)/14), no desigualdades
vagas. Y un discriminador que distinga la implementación correcta de la plausible
(poblacional /N vs muestral /(N-1) difieren en 0.14 — el test lo detecta).
> Se ganó el sueldo al instante: cazó que los campos de `Bar` iban en orden
> equivocado. Con las aserciones viejas habría pasado en verde.

### 8. Benchmark que mide el optimizador
`bench.cpp` reporta 2.4×10¹² ops/s en Bollinger — imposible en un M1 (~3.2 GHz):
el compilador elimina el código sin usar. El "9.46 ns/op" citado en `TODOS.md`
**no es real**.
**Regla**: si el número es físicamente imposible, mide otra cosa. Sumidero volátil
o `DoNotOptimize` obligatorios.

### 9. Look-ahead por rebanado *(pendiente de confirmar)*
`pattern_detect.py:281-300` calcula el zigzag sobre la serie **completa** y luego
rebana. Un pivote sólo se confirma cuando el precio revierte k·ATR **después**. Si
se confirma, toda tasa de `data/patterns.json` está inflada.
**Regla**: en un backtest, preguntar de cada dato *"¿esto se sabía en ese instante?"*.

### 10. Backtest sin costes *(pendiente de confirmar)*
Ningún backtest modela comisiones, slippage, spread ni probabilidad de fill. Con
spread permitido del 5% en opciones de ≤$200, eso se come una parte grande del
win-rate reportado.

### 11. Lógica clonada ×24
Los 24 `*_signal_bot.cpp` son clones (1834 líneas). Un bug lógico está replicado 24
veces, y cada bot lleva **tres** Bollinger distintos (`V5BB`, `V6BBX`, principal) más
una cuarta en `engines/bb_core.h`.

**Detección** — hash módulo-ticker; debe colapsar a pocas variantes:
```bash
for f in *_signal_bot.cpp; do s=$(basename $f _signal_bot.cpp); S=$(echo $s|tr a-z A-Z)
  echo "$(sed "s/$S/SYM/g;s/$s/sym/g" $f | grep -v 'speak(' | md5) $s"
done | sort | uniq -c -w32
```
**Regla**: todo hallazgo en un bot se reporta **×24**. Y todo arreglo va al header
compartido, nunca a un solo clon.

---

## Cómo cazar (workflow)

Pipeline con verificación adversarial por dimensión — `pipeline()`, sin barrera:

| Dimensión | Alcance |
|---|---|
| exec-cpp | `order_engine/` + camino `live.html` → `exec_zones_*.json` |
| bots-cpp | 1 bot canónico + desviaciones + `engines/` + `scalper/` |
| opciones-py | `gex_core`, `options_enrich`, `opt_chain_cache`, `order_ticket` |
| quant-stats | look-ahead, costes, Wilson, in-sample, n pequeño |
| qa | integridad del suite, `except: pass`, datos rancios, edge cases |
| ops-shell | 14 launchd, 57 shells, carreras, dedup, exit 78 |
| todos-audit | los `[ ]` de `TODOS.md`: VIVO / YA-ARREGLADO / NO-REPRODUCE |

**Presupuesto**: 7 cazadores + 7 refutadores + 1 lead ≈ 1.4M tokens. Si el
presupuesto aprieta, **recorta dimensiones, no refutadores** — un hallazgo sin
verificar no sirve.

## Reglas de la cacería

1. **Solo lectura** mientras se caza. La flota está viva (24 bots + daemons).
2. **Mercado cerrado** para arreglar. Viernes tarde / fin de semana.
3. **Una sola mano** aplica los arreglos: los agentes cazan, el copiloto arregla.
4. **Verificar contra el paper gateway, DESARMADO.** Sin `ARM_LIVE` la ruta DRY
   registra "DRY colocaría…" sin mandar nada: ahí se lee el veto. Nunca armar para probar.
5. **Un test nuevo debe fallar primero** contra el código viejo. Si no, no prueba nada.
6. **Commitear antes de tocar.** `order_engine/` vivió meses fuera de git.

## Verificación final

```bash
bash order_engine/build.sh          # c++23, debe decir OK
zsh  tests/cpp/run.sh               # release + ASan + bench
./venv/bin/python -m pytest tests/ -q
```
Y el humo real: `python3 order_engine/smoke_paper.py` (coloca límite a $0.01 y cancela).
