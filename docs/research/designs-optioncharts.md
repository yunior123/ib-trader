# OptionCharts → ib-trader: 3 aceptadas, 2 confirmaciones de propuestas ya vivas, 6 rechazadas

> Minado el 2026-07-27 por petición de Yunior (`optioncharts.io/trending/most-active-stock-options`).
> Método: mismo que `designs-trendspider.md`. **Fuentes**: `/trending/*`, `/docs/`, páginas de
> producto. Sin cuenta. Todas las ideas pasaron por `anti-overfit-killlist`.

---

## 0. Veredicto de acceso — MEDIDO (2026-07-27)

| Pregunta | Respuesta medida |
|---|---|
| ¿API? | **NO documentada.** `optioncharts.io/api` → **HTTP 404** (79.930 b). `/docs/` existe y **no menciona API** |
| ¿Metodología? | Parcial y **en prosa, sin fórmula**: GEX = *"estimated dollar hedging required by market makers per 1% underlying move to maintain gamma neutrality"*; DEX = lo mismo con delta; "unusual" = *"abnormal trading activity highlighted by volume-to-open-interest ratios"*; max pain = *"max pain theory"*; distribución de probabilidad = *"Black-Scholes modeling and current option prices"* |
| ¿Latencia? | **No la declaran.** El plan alto ("Ultimate") vende "real-time options data" ⇒ el resto es delayed, sin decir cuánto. Un vendor que no publica su latencia **no puede alimentar un disparo** (`docs/LATENCIA-FUENTES.md`) |
| ¿IV Rank / IV Percentile documentados? | **NO**, ni ventana ni fórmula (`/docs/` no los menciona) |

**Conclusión**: OptionCharts es **matemática de commodity bien presentada**. Su GEX/DEX es
literalmente la fórmula que `gex_core` ya calcula desde una cadena con OI y griegas. Como **fuente de
datos vale cero** (sin API, latencia no declarada); como **catálogo de qué falta en nuestro mapa**
vale bastante, y en dos puntos coincide con propuestas que ya teníamos — lo cual es la única clase de
"validación externa" que un dossier puede dar.

---

## 1. 🥇 Historia POR CONTRATO (precio, volumen, OI y griegas) — `contract-hist`

**Inspirado en**: su **Contract History** ("the price, volume, open interest and greeks of a specific
option contract over time") y su **Historical Data** ("key option metrics over time for any ticker").
Es lo único suyo que nosotros **no** tenemos en ninguna forma.

**Qué computa**: una tabla por `(contrato, fecha)` con `close, vol, oi, iv, delta, gamma` reunida de
las dos mitades que ya poseemos, y con la **procedencia por columna** en la cabecera:
- `close, vol` ← `trades.db poly_opt_bars` (medido 2026-07-25: 114.337 filas, 22 días, **sin
  iv/griegas/OI**).
- `oi, iv, greeks` ← `data/history/<fecha>/chain_full_<sym>.json` (Polygon **directo**: `oi:
  "polygon_directo"`, `greeks: "polygon_directo"`; 3.552 contratos en QQQ el 26-jul).
- Regla dura: el `oi` de la fila de fecha D es el **cierre de D-1** (la OCC lo publica a la mañana
  siguiente). La columna se llama `oi_asof` y lleva su propia fecha, no la del fichero. Ver
  `scripts/uw_oi_delta.py:oi_asof`.

**Inputs**: los dos de arriba. Nada falta para las fechas archivadas; **hacia atrás no existe** (el
archivo de cadenas empieza el 25-jul) ⇒ la historia crece a razón de una sesión por día.

**Output**: tabla nueva `trades.db contract_hist(sym, contract, fecha, close, vol, oi, oi_asof, iv,
delta, gamma, src_precio, src_oi)`. Es **substrato**, no señal: alimenta `uw_oi_delta` con más de una
sesión, la vida de un muro (`wall-decay`) y el `relvol` por contrato.

**Decision rule**: ninguna. No habla, no ordena, no entra en la flecha.

**Validación**: no aplica — no afirma nada. Lo que sí exige es una prueba de **integridad**: para cada
fecha, cuántos contratos aparecen en `poly_opt_bars` y no en `chain_full` (la banda de `chain_full` es
**adaptativa**, `band: 0.18` en QQQ, así que faltan los strikes lejanos) y al revés. Ese porcentaje se
publica en la cabecera; sin él, cualquier estudio sobre esta tabla tiene un sesgo de selección oculto.

**Effort**: S/M. `scripts/contract_hist.py`, lote fuera de sesión.

**Kill risk**: el solape entre las dos fuentes puede ser bajo (banda adaptativa vs universo de
`poly_opt_bars`) y quedarse en los ATM, que son justo los que ya vemos bien. Se mide antes de
construir nada encima.

---

## 2. Densidad implícita por el precio de las opciones — `rn-density`

**Inspirado en**: su **Probability Distribution** ("statistical likelihood of various price outcomes
calculated using Black-Scholes modeling and current option prices").

**Qué computa**: la densidad **neutral al riesgo** del subyacente al vencimiento, sacada de la propia
cadena (Breeden-Litzenberger: `f(K) = e^{rT} · ∂²C/∂K²`), suavizada sobre la sonrisa de IV en vez de
sobre precios crudos, más sus cuantiles 16/50/84 %.
**Por qué NO es un prior inventado** (el filtro que mata a la mayoría, killlist §2): no elige pesos ni
umbrales — es una **transformación** de precios observados. Lo que afirma es "esto es lo que cotiza el
mercado", no "esto va a pasar".

**Inputs**: `chain_full_<sym>.json` (IV y griegas medidas por strike), skill `option-pricing-pro`
(`math.erfc`, sin scipy), `em_envelope` para comparar. Nada falta.
Ojo: `bid_ask: "NO_ENTITLED"` en Polygon ⇒ la densidad sale del **mid teórico via IV**, no de un
mid de mercado. Se declara en la cabecera.

**Output**: `data/rn_density.json` → cuantiles y la densidad muestreada. Capa del cockpit y página del
PDF. **Descriptivo, sin voz.**

**Decision rule**: recorta objetivos. Un objetivo fuera del cuantil 84 % del vencimiento del propio
contrato es perseguir; la confluencia **cuantil ≈ muro de OI** es el mejor fade del día
(`expected-move-envelope`).

**Validación**: cobertura, no acierto. `P(cierre real dentro del intervalo 16-84 %)` debe salir ≈68 %;
si sale muy por encima o por debajo, la sonrisa o el suavizado están mal. Es un test **calibrado**,
que no consume celdas de señal. Con 3 sesiones archivadas, hoy es **DATA-INSUFFICIENT**: se mide, no
se publica un número.

**Effort**: M. `scripts/rn_density.py`. **Kill risk**: con la banda adaptativa la segunda derivada en
los bordes es basura y la densidad sale bimodal por artefacto numérico; hay que exigir strikes
contiguos y descartar la cola en vez de rellenarla.

---

## 3. `vol/OI` como definición única de "inusual" — unificar, no duplicar

**Inspirado en**: que su definición de unusual es **exactamente** `volumen / OI`. Es la misma cantidad
que `scripts/uw_oi_delta.py` usa como `ratio` en su denominador conceptual, y la misma que la
killlist usa para matar `signed-oi` (#1: QQQ 685C vol 238.672 vs OI 2.348 ⇒ `open_frac ≈ 0.01`).

**Qué se hace**: **nada nuevo**. Se anota que tres vendors independientes (Tradytics "RelVol",
OptionCharts "unusual", UW `days_of_vol_greater_than_oi`) usan la misma razón, y que en casa vive en
**un solo sitio** — `uw_oi_delta.classify()` — con las etiquetas NUEVA/SALIDA/CHURN. Cualquier
segunda implementación es la 5ª definición del horario otra vez (CLAUDE.md §7).

---

## 4-5. Confirmaciones de propuestas que YA existen (no se re-proponen)

| Producto de OptionCharts | Dónde vive ya | Qué cambia |
|---|---|---|
| **DEX** ($ por 1 % para quedar delta-neutral, por strike y total) | `designs-menthorq.md` #9 y `designs-spotgamma.md` #12. `gex_core` **no** calcula delta hoy; el mapa de delta por strike sí está archivado en `uw_greek_exposure_strike_<sym>.json` (530 filas/sym) | Sube prioridad: tres vendors lo consideran básico y nosotros no lo tenemos. **No se abre propuesta nueva** |
| **IV Rank / IV Percentile** | Ya está **DIFERIDA con condición** en `anti-overfit-killlist` §5: "Rejilla Compass / IV-rank 25Δ → 2027, tras un año de `iv_hist`" | Nada. Un IV-rank con 22 días de IV es un percentil sobre 22 muestras: eso es el disfraz "input muerto" |

---

## Rechazadas, con el motivo

| Idea de OptionCharts | Motivo del rechazo |
|---|---|
| **Most Active / Highest OI / Highest IV *by ticker*** (rankings de mercado) | Ranking transversal ⇒ killlist §4 "prohibido el ranking transversal" y #13. Además choca con la **ley de los dos universos**: `fleet.txt` (30) se define por tener **barras 1m**, no por aparecer en un trending; un símbolo mudo metido ahí rompe el denominador de MANADA (precedente: 21/26 = 80,8 % disparó DANGER falso) |
| **High IV Rank / Low IV Rank** como escáner | Mismo input muerto que arriba (22 días de IV) ⇒ killlist §2 "input muerto". Diferida con condición explícita, no muerta |
| **Max Pain como nivel suelto** | Ya lo tenemos, y **mejor condicionado**: la skill `pin-and-expiry-mechanics` solo admite zona de pin si el max pain **coincide con un `abs_wall` tipo pin**. Adoptar su versión sin la puerta sería degradar lo que hay |
| **Su GEX/DEX como FUENTE** (leer sus números) | Sin API, y sin latencia declarada. Regla 4 de CLAUDE.md: ningún nivel que dispare una orden viene de fuente delayed — y una latencia **no medida** es peor que una medida y grande |
| **Volatility Skew como producto aparte** | Es un corte de la misma sonrisa que `rn-density` (#2) ya necesita; publicarlo dos veces son dos definiciones del mismo objeto (CLAUDE.md §7) |
| **Las páginas `/trending/*` como expansor de universo** | Ver arriba: el universo no se decide por popularidad. `universe_gamma.txt` (35) exige cadena; `fleet.txt` (30) exige barras. Ninguno exige estar de moda |

---

**SEÑAL-SOLAMENTE.** Nada cableado. Lo único con valor real aquí es `contract-hist` (#1), y su
primer entregable no es una señal: es el **porcentaje de solape** entre `poly_opt_bars` y las cadenas
archivadas, que hoy nadie ha medido.
