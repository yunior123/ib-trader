# quantedOptions → ib-trader: 1 hallazgo grande, 3 aceptadas, 6 rechazadas

> Minado el 2026-07-27 por petición de Yunior (`quantedoptions.com`).
> Método: mismo que `designs-trendspider.md`. **Fuentes**: `/`, `/gu/pricing` + búsqueda pública.
> Todas las ideas pasaron por `anti-overfit-killlist`.

---

## 0. Veredicto de acceso — MEDIDO (2026-07-27)

| Plan | Precio | Cobertura | Cadencia | API |
|---|---|---|---|---|
| quantedTrader | $79/mes | SPY QQQ IWM DIA + equities, escáner de 600+ | 1 min | no |
| Lite | $149/mes ($29 prueba 3 días) | **SPX solo** | **10 min** | no |
| Classic | $299/mes | SPX + VIX, "licensed CBOE CGIF 1-minute data" | 1 min | no |
| Ultra | $399/mes | SPX + VIX | 1 min | **sí, 7.500 créditos/mes** |

Su frase de venta es la que importa, y es una **acusación técnica** contra lo que hacemos nosotros:

> *"Direct from the exchange — not modeled, not estimated, not reverse-engineered from public open
> interest."*

Tienen razón en el fondo: nuestro mapa se reconstruye del OI público con griegas de Polygon. La
pregunta útil no es "¿les compramos?" sino **"¿qué dato tienen que nosotros no podemos derivar?"**.
Y la respuesta es una sola cosa, que resulta ser exactamente el agujero de la TAREA 2.

---

## 1. 🥇 EL HALLAZGO: la versión MEDIDA de nuestro ΔOI existe y se llama CBOE Open-Close

**Qué es**: `Cboe Open-Close Volume Summary` (Cboe DataShop) clasifica **cada operación** por
- **tipo de participante**: customer / professional customer / broker-dealer / **market maker**,
- **acción**: buy / sell,
- **posición**: **open / close**,
y desglosa customer y pro-customer por tamaño (<100, 100-199, >199 contratos). Se vende EOD o
intradía (snapshots de 1 o 10 min) sobre C1/C2/BZX/EDGX.

**Por qué es EL hallazgo**: nuestro `scripts/uw_oi_delta.py` responde "¿abría o cerraba?" por
**inferencia neta** — compara `ΔOI` con el volumen del día y etiqueta NUEVA / SALIDA / CHURN. Open-Close
lo responde **bruto y medido**, sin inferencia. Es decir: existe una **verdad de terreno comprable**
para calibrar nuestra heurística, y no hace falta suscribirse para usarla.

**Propuesta concreta y acotada** (no es una suscripción):
1. Comprar **UN día EOD** de Open-Close en DataShop para los símbolos de la flota.
2. Para ese día, correr `uw_oi_delta` (fuente `polygon`, par de snapshots consecutivos) y comparar
   contrato a contrato la etiqueta inferida contra `open_buy + open_sell` vs `close_buy + close_sell`.
3. Medir tres cosas: (a) la tasa de acierto de la etiqueta por cubo de `vol/OI`; (b) **dónde** se
   rompe (la sospecha fuerte: en 0DTE, donde `open_frac ≈ 0.01`, killlist #1); (c) el valor de los
   umbrales `R_NEW` / `R_EXIT` / `R_CHURN` que maximiza la separación — **barridos en 3 valores**,
   killlist §3.4, porque un efecto que solo existe en un umbral no es real.
4. Resultado: o los umbrales quedan **medidos** (y la etiqueta puede aspirar a probabilidad algún día,
   con `n_eff`), o se demuestra que la inferencia neta no discrimina y `uw_oi_delta` se queda
   **descriptivo para siempre** — que también es un resultado, y barato.

**Coste**: el intradía C1 se cita alrededor de **$3.000/mes** — descartado sin discusión. El EOD se
compra por días en DataShop; **su precio NO lo he verificado**, así que no pongo número.

**Inputs nuestros**: `data/history/<fecha>/chain_full_<sym>.json` (dos fechas consecutivas),
`scripts/uw_oi_delta.py`. Ya están.

**Decision rule**: ninguna hasta que esté medido. La etiqueta sigue **sin voz y sin probabilidad**.

**Kill risk**: que el fichero EOD no case con nuestros contratos (símbolo raíz, ajustes) y el
emparejamiento se coma el día; y que Open-Close cubra **solo las bolsas Cboe**, no OPRA entero ⇒ el
volumen no cuadra con el `day.volume` de Polygon por construcción. Eso segundo hay que aceptarlo de
antemano: la comparación es de **proporción** open/close, no de volumen absoluto.

---

## 2. Re-lectura del mapa a 5 min con OI CONGELADO, y dicho así — `gamma-at-spot`

**Inspirado en**: su cadencia de 1 minuto ("SPX market-maker positioning snapshots every 10 minutes"
en Lite, 1 min en Classic). Nosotros tenemos un `chain_full` al día (16:20) más los snapshots de la
cadena IBKR cada 5 min.

**Qué computa**: el mismo perfil GEX/muros/flip re-evaluado cada 5 min con **spot e IV vivos** y **OI
congelado del cierre anterior**, publicado con la etiqueta `oi_asof` bien visible.

**La parte que hay que decir en voz alta**: esto **NO es una derivada temporal**. `dCoM/dt` y
`dflip/dt` sobre OI congelado están **muertos** (killlist #16: "miden el spot moviéndose bajo un libro
congelado", y con ellos murió `converge`/`eta_min`). Lo que sí es legítimo es la **re-lectura**: dónde
está el precio *hoy* respecto de un libro que no cambia. La diferencia no es semántica: la primera
inventa una velocidad, la segunda solo mueve el cursor.

**Inputs**: `data/history/<fecha>/opt_chain_<sym>_HHMM.txt` (snapshots de 5 min de la cadena IBKR, ya
archivados), `gex_core`, spot de IBKR (tiempo real, es el que dispara).

**Output**: campos ya existentes, con `oi_asof` obligatorio. **Cero series derivadas.**

**Decision rule**: la de siempre — PRINT o nada en el nivel, muro con `wall_state`, capitán manda.
Esta feature no añade dirección; quita el error de leer el mapa de las 09:35 a las 15:00.

**Validación**: no afirma nada nuevo ⇒ no consume celdas. Lo único que hay que verificar es que el
`flip` recomputado con spot vivo **no** se use como serie temporal en ningún consumidor.

**Effort**: S, pero **es de otro agente**: `gex_core.py` / `gex_snapshot.py` / `chart_levels.py` no
los toco. Queda como propuesta.

**Kill risk**: que alguien la lea como una velocidad y reintroduzca `dflip/dt` por la puerta de
atrás. Mitigación: el campo se llama `oi_asof`, no `ts`.

---

## 3. Superficie de charm (strike × vencimiento) para la tarde — `charm-surface`

**Inspirado en**: su **Charm Surface** ("time-decay pressure across strike range") y su
**Gamma Surface Heatmap** (matriz strike × expiry).

**Qué computa**: `charm(K, T)` por strike y vencimiento sobre la cadena archivada, con las griegas
**medidas** de Polygon donde existan y `gex_core.bs_charm` donde haya que reconstruirlas —
**marcando cuál es cuál en la cabecera del propio fichero** (CLAUDE.md: jamás mezclar reconstruido con
medido sin decirlo). El uso es el arrastre de la tarde que la skill `pin-and-expiry-mechanics` ya
describe en la ventana 13:30-15:45.

**Inputs**: `chain_full_<sym>.json` (`greeks: polygon_directo` — theta y vega vienen; charm hay que
derivarlo), `uw_greek_exposure_strike_<sym>.json` (530 filas/sym archivadas: incluye charm de UW, útil
como **contraste**, jamás como sustituto).

**Output**: una matriz por símbolo + la cuota de charm del vencimiento más próximo. Capa del cockpit.
**Descriptivo, sin voz.**

**Decision rule**: contexto de tarde. Charm concentrado en el vencimiento de hoy y a favor del pin
refuerza el veto de 0DTE comprado en zona de pin; no genera entradas.

**Validación**: cobertura y consistencia (charm de UW vs charm reconstruido: si divergen en signo,
uno de los dos tiene mal la convención — y esa comprobación **ya cazó** un error de paridad en
premercado, commit `44f830a`). Sin probabilidad.

**Effort**: M. **Kill risk**: charm es pequeño frente a gamma casi todos los días; la superficie
puede ser bonita y sin información. Se mide su rango antes de dibujar nada.

---

## 4. Verificar la entitlement de VIX/SPX en TWS antes de pagar nada — `vix-check`

**Inspirado en**: que su producto caro es **SPX + VIX** en vivo. Yunior **ya paga** la suscripción
IBKR CBOE Global Indexes (~$1,50/mes), y `~/CLAUDE.md` dice que eso debería dar SPX y VIX en vivo
por TWS — **sin verificar en sesión viva**.

**Qué es**: una comprobación, no una feature. Pedir SPX y VIX por el puente y medir la edad del tick.
Si funciona: el VIX desbloquea la banda de fragilidad y SPX pasa de "solo mapa" a candidato, y la
diferencia con quanted Classic ($299/mes) es de **$297,50**.

**Effort**: XS. **Kill risk**: ninguno — es medir. **Y es lo primero que haría antes de mirar precios.**

---

## Rechazadas, con el motivo

| Idea de quanted | Motivo del rechazo |
|---|---|
| **Suscribirse a Lite/Classic/Ultra** ($149-$399/mes) | (a) Cobertura **SPX-only** en Lite/Classic: no cubre la flota, y la flota es el negocio; (b) fuente de pago con reloj **no puede ser dependencia de una señal** — es literalmente la lección de gexa.ai, que murió de un día para otro y se llevó 8 consumidores; (c) el mapa ya lo calculamos en casa con griegas medidas. Lo que falta no es cadencia, es **historia** — y eso lo arregla el backfill, no una suscripción |
| **Su API (7.500 créditos/mes en Ultra)** | 30 símbolos a cadencia intradía agotan 7.500 créditos en horas. Y crearía consumidores atados a un token de terceros: mismo error otra vez |
| **"DEX = market-maker positioning" usado como DIRECCIÓN** | El flujo delta-nocional **firmado** está matado *como afirmación* en `dealer-flow-limits` (killlist, sección "Matado como AFIRMACION"). Que venga con licencia de bolsa no cambia que el paso de "posicionamiento" a "dirección del precio" es el prior inventado |
| **quantedTrader Net Delta** (delta a nivel de posición) | Herramienta de cartera. La flota es **SEÑAL-SOLAMENTE** por ley; `order_engine` es la única excepción y no necesita esto |
| **quantedFlow: escáner sobre 600+ tickers** | Ranking transversal sobre un universo que **no podemos alimentar con barras 1m** ⇒ killlist §4 + ley de los dos universos. 600 nombres es 600 oportunidades de p-hacking, no 600 señales |
| **Su "Historical replay"** | Es su histórico, no el nuestro: un backtest sobre datos **no archivados por nosotros** presentado como medición está prohibido (killlist §4, último punto). Nuestro histórico se archiva o no existe |

---

## Lo que este dossier deja como acción, en orden

1. **`vix-check`** (XS, hoy mismo en sesión): ¿SPX y VIX llegan vivos por TWS con la suscripción que
   ya se paga? Cierra o abre la conversación de los $299.
2. **Un día EOD de CBOE Open-Close** para calibrar `uw_oi_delta`. Es la diferencia entre una etiqueta
   heurística y una etiqueta medida, y cuesta un día de datos, no una suscripción.
3. Nada más. Las otras dos (`gamma-at-spot`, `charm-surface`) son propuestas sobre ficheros de otros
   agentes y descriptivas por definición.

---

**SEÑAL-SOLAMENTE.** Nada cableado.
