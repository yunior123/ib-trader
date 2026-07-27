# TradingFlow → ib-trader: qué se puede robar, y qué NO hace falta

> Minado el 2026-07-26 por petición de Yunior ("i really like this one too… do they have api?").
> Método: mismo que `designs-trendspider.md` / `designs-menthorq.md` / `designs-spotgamma.md`.
> **Fuentes**: solo docs PÚBLICOS (`/learn/*`, `/pricing/`, `/roadmap/`) + sondeo HTTP de la app.
> **Pendiente**: la UI en vivo (`app.tradingflow.com/app/option-trades/live`) NO se ha visto —
> la extensión de Chrome no conectaba. Lo de aquí sale de su documentación, no de la pantalla.

---

## 0. Veredicto de acceso — MEDIDO, no supuesto

| Pregunta | Respuesta medida (2026-07-26) |
|---|---|
| ¿Tienen API? | **NO.** `/api/*`, `/openapi.json`, `/api/swagger.json`, `/docs` → 404 o el shell del SPA |
| ¿La mencionan en precios? | **NO.** Un solo plan, **$59/mes** ($177/trim, $504/año) |
| ¿Está en el roadmap? | **NO.** Su roadmap es Option Chain, watchlist, filtros, Surge Attribution, resúmenes IA |
| ¿Cómo sirven el dato? | SPA Next.js + auth **Clerk** (`clerk.tradingflow.com`) → backend tras sesión |

**Conclusión operativa**: TradingFlow es **fuente de IDEAS, no fuente de DATOS**. No puede ser
dependencia de ninguna señal. Pagar $59/mes solo tendría sentido como *terminal de consulta*
manual, y ahí compite con lo que ya tenemos en `charts/live.html`.

---

## 1. Lo que su documentación revela y nosotros NO tenemos

### 1.1 🥇 DEX de FLUJO, y la distinción DEX-vs-GEX que nos falta nombrar

Su definición, textual: **`DEX = delta × size`** — y `size` es el **tamaño de la operación**,
no el OI. Eso los separa en dos cosas que en casa mezclamos sin darles nombre:

> **"DEX describes *flow direction* on the tape (intraday activity), whereas GEX represents
> *market structure* — how existing options positions influence dealer hedging."**

Nosotros tenemos GEX (estructura) y **cero delta de ninguna clase**. Esto propone además que hay
**dos DEX distintos**, y conviene no confundirlos nunca:

| | fórmula | qué mide | fuente nuestra |
|---|---|---|---|
| **DEX de estructura** | `Δ · OI · 100 · S` | posicionamiento acumulado | cadena archivada (Polygon/CBOE) o UW `/greek-exposure/strike` |
| **DEX de flujo** | `Δ · size` por operación | lo que se está haciendo HOY | necesita cinta de opciones firmada — **UW `/market-tide`** |

⚠️ **La trampa de signo sigue en pie** (`designs-menthorq.md:224`, y TradingFlow **no la menciona**,
lo cual es en sí un aviso): su "DEX positivo = alcista" es la lectura del CLIENTE. Para el creador
de mercado es lo contrario: cliente largo delta → el creador **vende subyacente** para quedar
neutral. Dos campos, jamás uno: `dex_sentiment` (cliente) y `dex_flow_impact` (creador).

### 1.2 🥈 DEI — normalizar el impacto por la liquidez del nombre

> **"DEI = DEX escalado por el volumen típico de la acción. Pregunta: ¿es esta exposición
> direccional GRANDE para este nombre?"**

Es la pieza que hace comparable NOK con NVDA. Hoy nuestros umbrales de ballena son absolutos, y
por eso NOK (con 8,99 de precio) y MU (con 910) no se pueden rankear juntos. **El mismo DEX
significa cosas distintas según el símbolo** — eso es exactamente lo que ya nos mordió con los
umbrales de OI mínimo.

*Encaja con lo nuestro*: `book_quality.py` ya hace percentil **propio del ticker**; DEI es la misma
idea aplicada al flujo. Y `impact_pctile` ya existe como campo… **hoy `null` en 30/30**.

### 1.3 🥉 La escalera de agresor de 5 peldaños

Nosotros clasificamos por lado (`pc = vp/max(vc,1)`); ellos por **agresividad respecto al NBBO**:

| Peldaño | Lectura |
|---|---|
| **Above Ask** | comprador muy agresivo — convicción fuerte |
| **At Ask** | comprador agresivo |
| **Mid** | neutro — puede ser cualquiera |
| **At Bid** | vendedor agresivo |
| **Below Bid** | vendedor muy agresivo — con prisa por salir |

Regla base: *at-ask-o-arriba = el comprador fue el agresor; at-bid-o-abajo = el vendedor*.
**Ya tenemos el motor**: `ibkr_bar_bridge.py:250` corre `reqTickByTickData(..., "AllLast", ...)`
con firmado Lee-Ready. Es la misma clasificación, aplicada a contratos de opción en vez de acciones
— es decir, **el HIRO casero descrito en `docs/HIRO-2026-07-25.md`**.

Detalle valioso: **"Mid" es su propia categoría, no un lado**. Nuestro P/C fuerza cada operación a
un bando; la mitad neutra debería contarse aparte, no repartirse.

### 1.4 ΔOI como detector de APERTURA vs CIERRE — y el aviso de frescura

Su regla, que es limpia y medible:

| Señal | Lectura |
|---|---|
| `volumen ≈ +ΔOI` | contratos NUEVOS → **apertura** (dinero nuevo) |
| `volumen ≈ −ΔOI` | contratos cerrados → **salida** |
| `volumen >> ΔOI` | churn (intradía, OI plano) |

Y el aviso que vale oro y **contradice cómo leemos nuestro propio dato**:

> **"El open interest NO es en tiempo real. Durante la sesión, el OI que ves es el cierre de AYER."**

Eso conecta con el punto de Kochuba (skill [[market-maker-hedging]]): *un movimiento brusco suele
ser un CAMBIO DE POSICIÓN, no una noticia*. ΔOI al día siguiente **confirma** si la ballena de ayer
abría o cerraba. Es barato: ya archivamos cadenas a diario desde el 2026-07-25.

### 1.5 Unusual activity como CONJUNCIÓN, no como umbral suelto

Marcan una operación como inusual cuando **coinciden varios** factores: premium grande **+**
Vol/OI alto **+** lado agresivo **+** sentimiento claro (no mid) **+** strike OTM.

Y la lectura de tamaño: *"unas pocas operaciones muy grandes (bloques) apuntan a convicción
INSTITUCIONAL; muchas operaciones diminutas son más bien retail o creador de mercado, y llevan
menos señal direccional"*.

Nuestra `opt_whale_watch` dispara con **una sola métrica** (`pc = vp/max(vc,1)`, `:157`) — por eso
el tide de −53 M del 7/21 no sonó. La conjunción es más difícil de sobreajustar que un umbral.

---

## 2. Lo que ya tenemos y NO hay que reconstruir

| Suyo | Nuestro | Estado |
|---|---|---|
| Call/Put Wall | `gex_core.build_gex` | **NUESTRO ES MEJOR**: ellos definen los muros **solo por OI** ("el strike con más OI de calls por encima del precio"); nosotros por **\|gamma\|·OI** *y además* publicamos `oi_call_wall`/`oi_put_wall` como segunda lectura |
| Max pain | `pin_clock.py` (`d21f2eb`) | nuestro exige además coincidencia con `abs_wall` y OI mínimo |
| Gamma flip / zero gamma | `gex_core.flip_recompute` | **NUESTRO ES MEJOR**: bisección de 40 iteraciones + `flip_src`/`flip_why`; ellos no publican método |
| Vol/OI | ya en `opt_chain_cache` | — |
| IV Rank / percentil | `iv_hist` (3.019 filas) | — |
| Badge de régimen GEX | `regime` / `regime_short` | el nuestro además distingue **pin vs trampilla** |
| Glosario / cookbooks | skills `gexa-framework`, `gamma-exposure` | — |

**Importante para no acomplejarse**: en GEX y flip **no disclosan la fórmula** ("implementation
details remain proprietary"). Nosotros sí, y con tests. Su ventaja no es el cálculo: es la UI y la
cinta de opciones a la que tienen acceso y nosotros no.

---

## 3. RECHAZADAS (y por qué), para no rehacerlas

- **Pagar los $59/mes como feed** — no hay API. Sin salida programática, no entra en la flota.
- **Scrapear la app** — tras Clerk, es un SPA, y sería una dependencia frágil de la peor clase:
  exactamente lo que nos pasó con gexa.ai (murió y se llevó 8 consumidores).
- **Copiar su Call/Put Wall por OI puro** — es un retroceso respecto a lo que ya calculamos.
- **"Surge Attribution" y "resúmenes con IA"** de su roadmap — sin definición pública, y lo segundo
  choca con la regla de la casa: un LLM no produce probabilidad calibrada.

---

## 4. Orden recomendado (por valor / coste)

1. **DEX de estructura** (`Δ·OI·100·S`) en `gex_core`, con los **dos campos de signo**. Desbloquea
   `close-drift` (#24) y `expiry-unwind` (#25), las dos minadas y nunca construidas. Ya tenemos el
   delta medido en las cadenas archivadas y en UW `/greek-exposure/strike` (530 filas por strike).
2. **ΔOI apertura-vs-cierre**: barato, ya archivamos cadenas a diario. Y arregla una lectura
   equivocada (creer que el OI intradía es de hoy).
3. **Escalera de agresor de 5 peldaños + "Mid" aparte** en `opt_whale_watch`, sobre el
   `reqTickByTickData` que ya corre. Es el HIRO casero.
4. **DEI** (normalizar por volumen típico) — desbloquea rankear la flota entera junta.
5. **Unusual como conjunción** en vez de un solo ratio.

Todo pasa por [[measured-probability]] antes de tener voz: triple barrera, Wilson sobre muestra
efectiva (ρ̄ = 0,41), null de entrada aleatoria y BH-FDR. Y por [[anti-overfit-killlist]]: que la
idea venga de un vendedor no la hace medida.

---

## 5. PASADA HTTP (2026-07-27) — la visual sigue BLOQUEADA, y se dice

Yunior pidió la pasada **visual** de `app.tradingflow.com/app/option-trades/live`. **No se pudo**: la
extensión de Chrome no conecta y el JS por AppleScript está desactivado. Así que se hizo por HTTP, y
esto es lo que se midió:

| URL sondeada | Código | Tamaño | Lectura |
|---|---|---|---|
| `/app/option-trades/live` | 200 | 34.684 b | el **shell del SPA**, sin datos |
| `/openapi.json` | **200** | **34.684 b** | **el MISMO shell byte a byte** ⇒ no es un OpenAPI, es el catch-all de Next.js. Un 200 aquí engaña si solo se mira el código |
| `/_next/data` | 200 | 34.684 b | idem shell |
| `/api/trpc/optionTrades.live` | 404 | 36.168 b | página 404 |
| `/api/health` | 404 | 36.168 b | página 404 |
| `tradingflow.com/roadmap/` | 200 | 45.854 b | público, ya minado en §1 |

**Confirma el veredicto de §0 y lo endurece**: no hay API, y el `200` de `/openapi.json` es un falso
positivo del enrutado del SPA — se detecta comparando el **tamaño** con el del shell, no el código.
La pasada visual queda **pendiente** de que la extensión de Chrome vuelva a conectar; no cambia nada
operativo, porque sin API TradingFlow no puede ser fuente de datos en ningún caso.
