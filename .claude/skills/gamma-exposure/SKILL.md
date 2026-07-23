---
name: gamma-exposure
description: Exposición gamma de dealers para la flota ib-trader — GEX por strike y neto, régimen positivo/negativo, gamma-flip (zero-gamma) recomputado, muros call/put (por gamma y por OI), muro absoluto, y cómo se fusiona con muros OI/gexa y la doctrina de imanes. Usar cuando se hable de GEX, gamma exposure, gamma flip, zero gamma, régimen gamma, call wall, put wall, muros de gamma, dealer positioning, o pin/imán por gamma. SEÑAL-SOLAMENTE — jamás órdenes al broker.
---

# gamma-exposure — el mapa de fuerzas de los dealers (2026-07-23)

Herramienta única de cálculo: **`scripts/gex_core.py`** (la fuente que consumen los
engines y el chart; extraída de la lógica ya probada en `daily_fleet_plans.py`).
GEX/flip/walls son UN sistema: el flip y los muros se DERIVAN del perfil GEX. Es un
**mapa de fuerzas, no un gatillo** — se cruza con el print, el flujo y Bollinger.
Cross-links: [[oi-magnets-protocol]] · [[gamma-regime-walls]] · [[flow-captains]] ·
[[bollinger-mastery]] · gexa via skill `gexa-terminal`.

## 1. GEX — Gamma Exposure (fórmula)
Por strike, convención **dealer-long-calls** (calls +, puts −; limpia en índices/
líquidos, más ruidosa en nombres — marcar baja confianza en single-names):

```
GEX_strike = signo · gamma · OI · 100 · Spot² · 0.01        (ESTÁNDAR, $ por 1% de move)
GEX_strike = signo · gamma · OI · 100 · Spot                (CASA/lineal — mismo ranking de strikes)
net_gex    = Σ_strikes GEX_strike
```
- `gamma` = gamma BS por acción (usar la del proveedor Polygon/IBKR; si falta, `bs_gamma`).
- `100` = multiplicador; `Spot²·0.01` = Δ-dólar que los dealers ajustan por 1% de move.
- `gex_core.build_gex(contracts, spot, scale="dollar1pct")` da la versión estándar en $/1%;
  `scale="house"` (default) la lineal — **el flip y los muros no cambian de strike** entre ambas.
- **Pitfalls** (verificados 2026-07-23): (a) 0DTE — gamma ATM ∝ 1/√T explota cerca de expiry;
  `gex_core` pisa T a ~5min (`T_FLOOR`). (b) `Spot²` obligatorio (olvidarlo = $/$1, incomparable
  entre tickers). (c) OI es EOD/stale — el intradía (0DTE) mueve la exposición antes que el OI;
  parear con la alarma de flujo/ballenas. (d) ETFs temáticos (DRAM/SPCX/SKHY/EWY) y NOK: OI ralo
  → GEX poco fiable, caer a muros OI de TWS.

## 2. Régimen gamma (el interruptor)
- **net_gex > 0 → POSITIVA**: dealers venden rallies / compran dips → **amortiguan**:
  mean-reversion, rango, **pin** al strike de mayor gamma. Vol realizada < implícita.
  → Fadear extremos, cobrar en el imán, romper hacia arriba FALLA (trampa). Es el día-pin/jaula ([[pin-day-playbook]]).
- **net_gex < 0 → NEGATIVA**: dealers compran rallies / venden dips → **amplifican**:
  momentum, **band-walk**, colas, gaps, stops barridos.
  → Operar CON la tendencia; las rupturas extienden; prohibido el scalp de reversión ciego.

## 3. Gamma-flip / zero-gamma (la línea de vida de la vol)
Precio donde el GEX agregado cruza cero = frontera POS↔NEG.
- **Precio POR ENCIMA del flip = régimen positivo** (amortigua); **por debajo = negativo** (amplifica).
- Cálculo CORRECTO (`gex_core.flip_recompute`): **recomputar la gamma BS a cada spot hipotético S**
  del grid (la gamma DEPENDE de S), armar GEX(S) y hallar la raíz por interpolación — no basta
  interpolar el perfil estático. `build_gex` usa el recompute **solo si hay dispersión real de IV**
  (skew); con IV plana de respaldo (greeks no disponibles) cae al estático `_flip` (guarda ambos:
  `flip`, `flip_static`, `flip_recompute`). El recompute suele plantar el flip cerca del dinero (ahí
  vive la gamma); el estático lo sesga hacia el cruce acumulado de OI.
- **Táctica**: por encima del flip + dentro de los muros = fadear el rango. Debajo del flip = respetar
  tendencia, ampliar stops, las rupturas funcionan. **Flip justo bajo el spot = toro frágil** (un dip
  lo voltea a amplificación) — cantarlo. Es zona, no tick (salta día a día al rolar el OI).

## 4. Muros call / put (imanes y soporte-resistencia)
- **Call wall** = strike de mayor gamma+ **por encima** del spot → techo/resistencia + imán desde abajo
  (dealers cortos calls venden acciones al subir). **Put wall** = mayor |gamma−| **por debajo** → piso/
  soporte + imán desde arriba. **Muro absoluto** (`abs_wall`) = mayor |gex| = pin dominante/POC gamma.
- `gex_core` da AMBOS: muros por **gamma** (`call_wall`/`put_wall`/`abs_wall`) y por **OI puro**
  (`oi_call_wall`/`oi_put_wall`, lo clásico de la casa). **Coincidencia gamma≈OI = nivel muy fuerte**;
  divergencia = el de gamma es mejor imán intradía, el OI lejano es gravedad débil.
- Fusión con doctrina de imanes ([[oi-magnets-protocol]]): 1er toque rebota ~70% (dealers defienden),
  **decae por toques** (3+ = exhausto), ruptura confirmada (retest-rechazo) **invierte** el nivel.
  Operar HACIA el imán desde el lado cercano, **jamás a través de un muro intermedio**. OI/gamma
  monstruo a ±1 del spot = pin → **prohibido 0DTE comprado ahí**. En NEG los muros son más débiles:
  romper el call wall puede ACELERAR (la compra dealer da gasolina), perder el put wall abre aire.

## 5. `wall_context(gexinfo, price)` — el gate para engines/copiloto
Devuelve distancias en % a call_wall/put_wall/flip + flags `near_*` (≤0.4% = muro inmediato) +
`regime` local visto desde el precio. Uso en señales:
- **near_call_wall & LONG** = comprar a la resistencia → veto/degradar (rebote esperado).
- **near_put_wall & SHORT** = vender al soporte → veto/degradar.
- **régimen POS** = favorece reversión/pin (sube prob de fades a la SMA20/POC); **NEG** = favorece
  continuación (sube prob de band-walk, baja la de fade). Es un multiplicador de contexto, no un gatillo.

## 6. Fuentes de datos
- **En vivo**: `data/opt_chain_<sym>.txt` (cache TWS de `opt_chain_cache.py`) → `gex_core.from_ibkr_cache`.
  Si iv/gamma = −1 (mercado cerrado/sin OPRA) usa BS con IV 0.3 de respaldo (aprox, sin skew → flip estático).
- **gexa.ai** (skill `gexa-terminal`): flip 0DTE vs ALL-EXP, dealer pressure, magnets footprint —
  contraste institucional. Cubre large-caps US; NO NOK ni temáticos.
- **Chart en vivo**: `scripts/chart_levels.py` escribe `charts/data/levels_<sym>.json`; el visor
  `charts/live.html` dibuja walls/flip (createPriceLine) + perfil GEX.

## 7. Límite honesto de backtest
GEX/flip/walls históricos exigen **OI+gamma por día**, que no tenemos barato (Polygon da OI/greeks
snapshot actual, no serie histórica). Por eso el gate GEX es **overlay EN VIVO**, no medido en histórico
todavía. Las señales medidas que SÍ pagan (opción real, n grande) son el filtro selectivo: **confluencia
C4 59%/+19% n=127** y **Yoel cambio-de-tendencia 64%/+31% n=226**; BB solo comprado PIERDE (−8%). El GEX
se espera que ayude por teoría (régimen), pero se declara NO-MEDIDO hasta tener OI histórico. Nunca cablear
un gate por teoría sin número — se ofrece como contexto que sube/baja prob, con esa honestidad.
