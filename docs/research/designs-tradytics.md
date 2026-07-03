# Tradytics → ib-trader: 5 aceptadas, 6 rechazadas

> Minado el 2026-07-27 por petición de Yunior (`tradytics.com/options-market`).
> Método: mismo que `designs-trendspider.md` / `designs-spotgamma.md` / `designs-menthorq.md`.
> **Fuentes**: solo páginas públicas (`/options-market`, `/support/*`) + sondeo HTTP. Sin cuenta.
> Toda idea pasó antes por la skill `anti-overfit-killlist`; las que caen ahí se rechazan **citando
> el item**, no se re-descubren.

---

## 0. Veredicto de acceso — MEDIDO, no supuesto (2026-07-27)

| Pregunta | Respuesta medida |
|---|---|
| ¿API? | **NO.** `api.tradytics.com` → **DNS no resuelve (curl 000)**; `tradytics.com/api` → HTTP 200 pero el cuerpo es **su página 404** (69.602 b); `/docs` → 404 |
| ¿Metodología publicada? | **NO.** `/support/what-is-market-net-flow-tradytics` dice literalmente que agrega "the flow for the entire market i.e every stock out there" y **ni una fórmula**; `/support/how-to-understand-dealer-positioning-gamma-vanna-charm` es introductorio, **cero definiciones, cero convención de signo, cero fuente** |
| ¿Latencia? | La propia página lo declara: **"Data delayed by a few days"** en cuenta gratis; "Live Premium Data" solo pagando |

**Conclusión operativa**: igual que TradingFlow, Tradytics es **fuente de IDEAS, jamás de datos**.
Sin API y con la fórmula sin publicar, cualquier cosa suya que entrara en el camino de señal sería
**un prior inventado con el logo de otro** (killlist §2). Y una fuente de pago sin API no puede ser
dependencia: es la lección de gexa.ai.

---

## 1. 🥇 GEX separado por vencimiento, con el 0DTE aislado — `gex-0dte`

**Inspirado en**: sus dos productos distintos **0DTE Flow** y **0DTE GEX** ("chartable by strike,
change, or time progression"), es decir: ellos NO mezclan el 0DTE con el resto de la cadena.
Nosotros sí — `gex_core` agrega todos los vencimientos hasta `exp_hasta` en un solo perfil.

**Qué computa**: el mismo perfil que ya calculamos, partido en tres cubos por DTE y publicado por
separado, sin score y sin sumarlos en un número:
1. `DTE == 0` (el que fija el pin del día), `1 ≤ DTE ≤ 7`, `DTE > 7`.
2. Por cubo: `net_gex`, `flip`, muro de call y de put, y la **cuota** del cubo sobre `Σ|GEX|`.
3. La cuota del cubo 0DTE es el dato nuevo: dice si el mapa de hoy lo manda el vencimiento de hoy
   (jaula, `pin-and-expiry-mechanics`) o el libro largo.

**Inputs**: `data/history/<fecha>/chain_full_<sym>.json` (griegas y OI de Polygon **medidos**,
`expiration_date` por contrato — verificado: 3.552 contratos en QQQ el 26-jul), `data/opt_chain_<sym>.txt`
para el vivo, `gex_core`. Nada falta.

**Output**: campos nuevos en el JSON de niveles: `gex_by_dte{"0":{...},"1_7":{...},"8p":{...}}` +
`share_0dte`. Banner y capa del cockpit. **Sin voz.**

**Decision rule**: `share_0dte` alto ⇒ día de jaula ⇒ prohibido 0DTE comprado en zona de pin
(memoria `oi-magnets-protocol`) y los muros del cubo 0DTE son los que se defienden hoy; los del
cubo `>7` son el mapa de la semana, no el de esta hora.

**Validación**: **primero colinealidad** (killlist §3.1): `ρ` rodante entre `flip_0dte` y `flip_total`
y entre `share_0dte` y `net_gex`. Si `|ρ| > 0.9`, es un re-etiquetado y muere. Solo si sobrevive se
buscan celdas, y con `n_eff` corregido (`measured-probability`), no con 3 sesiones de archivo.

**Effort**: S. Un desglose sobre `gex_core` ya existente. **No lo toco yo**: `gex_core.py` es de
otro agente — esto es una propuesta, no un parche.

**Kill risk**: en índices el 0DTE es la mayoría del `Σ|GEX|` casi todos los días ⇒ `share_0dte`
es una constante disfrazada de señal, y `flip_0dte ≈ flip_total`. Es el resultado más probable.

---

## 2. RelVol POR CONTRATO contra su propia mediana — `contract-relvol`

**Inspirado en**: su columna **RelVol** y los escáneres **Highest Call/Put Vol Change** y
**High Volume Cheaplies**. Nosotros medimos volumen inusual por TICKER, nunca por CONTRATO.

**Qué computa**: `relvol(c) = vol_hoy(c) / mediana(vol_d(c), d en los últimos N días con vol>0)`,
por contrato, junto con `vol/OI` (que es la definición de "unusual" de media industria) y el premium
del contrato para cruzarlo con el presupuesto ≤ $200.

**Inputs**: `trades.db poly_opt_bars` — **medido el 2026-07-25: 114.337 filas, 22 días, con `v` por
contrato y SIN iv/griegas/OI**. Para este cálculo solo hace falta `v`, así que la tabla **sí sirve**
(a diferencia de `vanna-ramp`, killlist #2, que le pedía IV a la misma tabla y por eso murió).
OI del día: `chain_full_<sym>.json`.

**Output**: `data/contract_relvol.json` con las N filas por símbolo, **rankeadas y sin score
compuesto** (killlist §4). Banner del cockpit.

**Decision rule**: no es entrada. Es un **filtro de vehículo**: entre contratos que expresan la misma
tesis, el de `relvol` alto **y** spread ≤5% **y** OI>500 se queda el boleto (regla 4). `relvol` alto
con OI ridículo es la trampa de liquidez, no una señal.

**Validación**: 22 días dan una mediana de 22 muestras por contrato — **suficiente para describir,
insuficiente para probabilizar**. Se publica el número crudo, **cero probabilidad**, hasta que el
backfill de 2 años de `poly_opt_bars` esté hecho. Barrido de `N ∈ {10, 22, 60}` cuando lo haya.

**Effort**: S. `scripts/contract_relvol.py`, nuevo, lote fuera de sesión (pandas legítimo ahí).

**Kill risk**: la mediana de 22 días sobre contratos que nacen y mueren cada semana es casi siempre
`n<5` para los OTM lejanos, que son justo los interesantes ⇒ `relvol` explota a valores enormes por
denominador diminuto. Mitigación obligatoria: `n_dias` en el propio campo y `None` si `n_dias < 8`
(jamás un relvol plausible).

---

## 3. Cuota del agresor a nivel de MERCADO, descriptiva — `aggressor-share`

**Inspirado en**: su **Calls/Puts Market Dashboard**, cuyas columnas son honestas y concretas:
"buy ratio, ask/bid counts, net premiums, premium change, average expiration days, OTM percentage".

**Qué computa**: por lado (call/put), `ask_share = ask_vol / (ask_vol + bid_vol)`, premium neto y DTE
medio ponderado por premium, agregado sobre la flota. **Nada de un índice único.**

**Inputs**: hoy, `data/history/<fecha>/uw_net_prem_ticks_<sym>.json` y `uw_oi_change_<sym>.json`
(este último trae `prev_ask_volume` / `prev_bid_volume` / `prev_neutral_volume`, ya archivados —
verificado en QQQ: 9.000/1.000 en la fila de ejemplo). Cuando el trial de UW muera: `data/whale_<sym>.txt`
(cinta firmada ≥$50k) y, si algún día se hace el spike de `reqTickByTickData`, IBKR.

**Output**: `data/aggressor_share.json`, banner. **Sin voz** — el presupuesto de alarmas no tiene
hueco libre (`alert-budget`), y esto no retira ningún DANGER.

**Decision rule**: contexto para la táctica espada-ballena (regla 11), no gatillo. `ask_share`
extremo en calls del capitán = techo local candidato, y ya hay una alarma para eso.

**Validación**: bloqueada por la fuente. UW se apaga el ~2026-08-01 ⇒ **el histórico archivado es lo
único que quedará**, y son días, no sesiones suficientes. Se publica descriptivo o no se publica.

**Effort**: S. **Kill risk**: la serie muere con el trial y queda un consumidor huérfano — el error
exacto de gexa.ai. Por eso nace **sin consumidores** y leyendo del archivo, no de la API.

---

## 4. Diff día-sobre-día del propio mapa archivado — `map-diary`

**Inspirado en**: su **Dealers Diary** ("historical dealer positioning data queryable by specific
dates"). No hace falta comprárselo: nosotros ya archivamos el mapa cada día.

**Qué computa**: `diff` entre el mapa de hoy y el de ayer: muros que aparecen/desaparecen, `flip`
movido en ATR, cambio de `net_gex` y de `max_pain` por vencimiento — **con la fecha as-of del OI
declarada en cada fila** (el OI de un snapshot es el cierre de la víspera, ver `scripts/uw_oi_delta.py`).

**Inputs**: `data/history/<fecha>/chain_full_<sym>.json` (25, 26 y 27-jul archivados; 30/35 símbolos),
`uw_greek_exposure_<sym>.json` (**250 filas = 1 año** por símbolo, archivado el 26-jul: el único
histórico largo de griegas de dealer que tendremos).

**Output**: `data/map_diary.json`. Página del PDF diario. **Descriptivo.**

**Decision rule**: ninguna todavía. Es el substrato de calibración de `wall-decay` y del régimen
gamma histórico, que es exactamente lo que el año de `greek_exposure` de UW desbloquea.

**Validación**: es la propia infraestructura de validación, no una señal. **Effort**: S.
**Kill risk**: 3 sesiones de `chain_full` (25-jul en adelante) ⇒ hoy el diario tiene una entrada
útil. Crece solo con el tiempo; nada que acelerar.

---

## 5. Escáner de "cheapies" con OI de verdad — `cheapies-gate`

**Inspirado en**: **High Volume Cheaplies** (contratos baratos con volumen anómalo). Encaja exacto
con la ENMIENDA de Yunior 2026-07-22: cualquier contrato de la flota con premium ≤ $200.

**Qué computa**: contratos con `mid ≤ $2.00` (= $200 por boleto), `relvol` de la feature 2,
`spread_pct`, `OI`, `vol/OI`, y la **etiqueta de `uw_oi_delta`** (NUEVA/SALIDA/CHURN) del día
anterior. Todo en una tabla; **cero score**.

**Inputs**: `chain_full_<sym>.json`, `scripts/optgate.py` (spread ≤5%, OI>500), `scripts/uw_oi_delta.py`.
Ojo: `chain_full` tiene `bid_ask: "NO_ENTITLED"` en Polygon ⇒ **el spread sale de IBKR**, no de aquí.

**Output**: `data/cheapies.json` + sección del plan de apertura. **Sin voz.**

**Decision rule**: filtro de vehículo, nunca dirección. Un "cheapie" con etiqueta **CHURN** del día
anterior es ruido de intradía, no acumulación; con **NUEVA** y OI creciente, es posición.

**Validación**: la etiqueta ΔOI ya está construida y es descriptiva; el escáner no añade
probabilidad ninguna. **Effort**: S. **Kill risk**: por debajo de $2 casi todo es 0DTE lejano ⇒ el
escáner acaba siendo una lista de lotería. El gate de OI y de spread es obligatorio, no opcional.

---

## Rechazadas, con el motivo

| Idea de Tradytics | Motivo del rechazo |
|---|---|
| **Market Cross** ("long cuando el volumen de calls cruza por encima del de puts") | Recodificación **monótona** del P/C ratio que `flow_pulse` ya publica ⇒ killlist §3.1 (colinealidad primero) y §2 "colinealidad". Un cruce sobre un cociente ruidoso es además el generador de whipsaw de libro |
| **Momentum + Algo** (su "algo flow line", score acumulado por minuto, >0 bullish) | Fórmula **NO publicada** y de pesos elegidos a mano ⇒ killlist §4 "prohibido un score compuesto de z-scores con pesos a mano" + §2 "prior inventado disfrazado de medición". No se puede ni verificar ni reproducir |
| **Market Net Flow** (agregado de "every stock out there") | Es un agregado transversal sobre un universo correlacionado. Nuestra flota es **26/30 semis**: en días risk-on la dispersión es ~nula ⇒ killlist #13 y §4 "prohibido el ranking transversal". Y `fleet_pulse` ya nombra al líder |
| **OTM Score** | El vendor no define nada. Adoptarlo es adoptar **su prior** ⇒ killlist §2. Si lo que se quiere es "cuán lejos del dinero está el flujo", eso es `OTM %` y ya sale del propio `chain_full` sin score |
| **Weekly Sector Inflow / Sector Flow Premiums** | Horizonte semanal/macro contra un stack cuyo edge es intradía ⇒ mismo patrón que killlist #15 (`mechanical-supply`). La pendiente del VX de `cboe-data` ya da el régimen |
| **Market DEX con medias de 5/10/15/22/30 días** | Dos problemas: (a) DEX ya está propuesto en `designs-menthorq` #9 y `designs-spotgamma` #12 — no se re-propone; (b) una media móvil de 22-30 días de DEX sobre 22 días de datos es **input muerto** ⇒ killlist §2 "input muerto" |
| **Suscribirse** (para quitar el "delayed by a few days") | Fuente de pago **sin API**: no hay forma de que entre en el camino de señal sin un humano copiando números. Y una fuente con reloj no puede ser dependencia (gexa.ai). El dinero rinde más en el backfill de 2 años de `poly_bars` |

---

**SEÑAL-SOLAMENTE.** Nada de este fichero está cableado. Las 5 aceptadas son propuestas con su
test de colinealidad **por delante** del test de acierto.
