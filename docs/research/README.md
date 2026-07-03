# `docs/research/` — la investigación cruda de SpotGamma × MenthorQ × TrendSpider (2026-07-25)

Los 9 ficheros de esta carpeta son el **material de origen** del que salió
[`../FEATURES-MINED-2026-07-25.md`](../FEATURES-MINED-2026-07-25.md) (30 features vivas, 16 muertas
con refutación numérica, 13 skills). Son ~450 KB producidos por 13 agentes y ~1.6M tokens.
Se conservan crudos, en inglés y sin editar, porque **la síntesis ya está en el doc de features** y
aquí lo valioso es la evidencia: URLs, nombres de fichero, endpoints, cifras y el razonamiento que
mató cada propuesta.

**No se leen de arriba abajo.** Se consultan cuando hace falta la fuente de una afirmación.

---

## CONCLUSIÓN DEL MINADO (lo único que hay que recordar si no se lee nada más)

> **Los NIVELES de las tres plataformas son matemática de commodity.** Son reproducibles desde un
> snapshot de cadena con **OI + griegas** — no hay algoritmo secreto. Lo único genuinamente caro es
> **HIRO** (cinta OPRA completa con tamaños + NBBO), y está **fuera de alcance verificado**:
> `/v3/trades/O:` y `/v3/quotes/O:` devuelven **`NOT_AUTHORIZED`** con nuestra key.

Repos públicos que lo demuestran (fieles, comprobados en los dossiers):

| Repo | Qué reproduce |
|---|---|
[`billyribeiro-ux/spot-gamma`](https://github.com/billyribeiro-ux/spot-gamma) | los cálculos de SpotGamma (GEX, muros, flip) |
[`maxkru92/mk-quant-monitor-cboe-gex`](https://github.com/maxkru92/mk-quant-monitor-cboe-gex) | Call Resistance / Put Support / Gamma Wall / GEX 1-10 desde cadena cruda de CBOE, **y el formato de salida byte-compatible** de MenthorQ. Fiel salvo en **HVL** (usa max de volumen+OI en vez del gamma flip) |
[`rxsinx/gex-analyzer`](https://github.com/rxsinx/gex-analyzer) | **HVL correcto**: cruce por cero del GEX acumulado = el flip, igual que nuestro `gex_core._flip` |
[`aaguiar10/gflows`](https://github.com/aaguiar10/gflows) | perfiles de gamma/vanna/charm por expiry |
[`joemccann/radon`](https://github.com/joemccann/radon) | **filtra la API privada de MenthorQ**: `scripts/clients/menthorq_dashboard_client.py` trae endpoints, flujo de auth, esquema de payload, nombres de campo **y unidades** |

Y TrendSpider directamente **documenta su propio motor**: su API de indicadores JavaScript expone
las funciones internas (`find_trends`, `find_head_and_shoulders`, `find_double_peak_formation`,
`find_channel`, `find_wedge`, `find_triangle`, `find_cup_and_handle`, `fractal_high/low`) con sus
nombres de variable y defaults. El lenguaje de scoring es **math.js**, los puntos base son
**fractales de Williams**, la unidad de escala universal es **ATR(14)**, y los indicadores estándar
son **TA-Lib**. No hay nada que revertir.

Corolario operativo: **lo que compramos con estas plataformas es presentación, no matemática.**
Nuestro trabajo pendiente nunca fue "descubrir el algoritmo" — fue tener **la cadena completa con
OI y griegas** y **una muestra archivada** para medir. Eso es lo que dicen las 30 features.

---

## Los 9 ficheros

### Dossiers de fuente (6) — qué vende cada plataforma y de dónde sale

| Fichero | Contenido |
|---|---|
[`spotgamma-docs.md`](spotgamma-docs.md) (70 KB) | Catálogo completo de métricas de SpotGamma con su matemática y sus mecanismos. **Hallazgo de acceso**: `support.spotgamma.com` bloquea el fetch normal (403) pero **su API de Zendesk Help Center está abierta y sin autenticar** — 417 artículos con cuerpo HTML completo; es la fuente de casi todas las entradas de confianza ALTA. No hay API pública. El manual PDF de TRACE es **solo imagen, cero texto extraíble** |
[`spotgamma-code.md`](spotgamma-code.md) (35 KB) | Arqueología de código: réplicas públicas de sus cálculos (`spot-gamma`, `gflows`), qué reproducen fielmente y qué no |
[`menthorq-docs.md`](menthorq-docs.md) (57 KB) | Taxonomía de niveles de MenthorQ (Call Resistance, Put Support, HVL, Gamma Wall, GEX 1-10, 1D Min/Max, Blind Spots) y su semántica documentada |
[`menthorq-code.md`](menthorq-code.md) (33 KB) | La arqueología más productiva del lote: tres artefactos open-source filtran la taxonomía exacta y **uno filtra la API privada**. Incluye el mapa definitivo de 19 subgráficos de los estudios de Sierra Chart |
[`trendspider-docs.md`](trendspider-docs.md) (68 KB) | Features de TrendSpider: Dynamic Price Alerts (Touch/Bounce/BreakThrough con sensibilidad ATR y **cierre de vela obligatorio**), ML Quant Lab (sus etiquetas de triple barrera), Price Behavior Explorer (la columna **Random Control**), Truth-in-Analysis, Raindrops, Gap Detector/Islands, TechRank |
[`trendspider-code.md`](trendspider-code.md) (42 KB) | Por qué no hay nada que revertir: su propia API de scripting **es** la especificación del motor (175 KB de markdown descargados) |

### Críticas de diseño (3) — los 41 candidatos, antes de la auditoría

| Fichero | Contenido |
|---|---|
[`designs-trendspider.md`](designs-trendspider.md) (43 KB) | 13 features candidatas desde TrendSpider, ancladas al repo real (ficheros, tablas y conteos de filas verificados) |
[`designs-menthorq.md`](designs-menthorq.md) (47 KB) | 14 candidatas desde MenthorQ |
[`designs-spotgamma.md`](designs-spotgamma.md) (43 KB) | 14 candidatas desde SpotGamma |

**Aviso importante al leer los tres `designs-*`:** son el estado **ANTES** de la auditoría
estadística y operativa. Contienen las 41 propuestas con su optimismo original: coberturas
probabilísticas que no se pueden medir con 21 sesiones, `eta_min`/`dflip/dt` sobre OI congelado,
flujo "firmado" sin cinta autorizada, scores compuestos de z-scores. **De esas 41, la auditoría
mató 16 y degradó la mayoría de las supervivientes.**

> **El veredicto vigente es el de [`../FEATURES-MINED-2026-07-25.md`](../FEATURES-MINED-2026-07-25.md),
> no el de estos tres ficheros.** Si un `designs-*` y el doc de features se contradicen, **manda el
> doc de features**: los `designs-*` se conservan como registro de lo que se propuso y para no
> reinventarlo.

---

## Cómo usar esta carpeta

| Situación | Qué abrir |
|---|---|
"¿De dónde sale este umbral / esta definición?" | el `*-docs.md` de la plataforma de origen |
"¿Ya existe código público que haga esto?" | el `*-code.md` correspondiente |
"¿Por qué se mató esta idea?" | **`../FEATURES-MINED-2026-07-25.md` § LOS 16 MUERTOS** + la skill [[anti-overfit-killlist]] |
"Llega una idea nueva de un vendor" | la skill [[anti-overfit-killlist]] (los 4 tests que matan barato) |
"¿Qué se propuso originalmente y con qué forma?" | el `designs-*.md` — recordando que es pre-auditoría |

Las 13 skills destiladas de todo esto:
[[measured-probability]] · [[chain-data-contract]] · [[print-o-nada-levels]] ·
[[book-quality-veto]] · [[flip-and-vol-trigger]] · [[pin-and-expiry-mechanics]] ·
[[expected-move-envelope]] · [[dealer-flow-limits]] · [[sample-integrity]] ·
[[direction-view-architecture]] · [[alert-budget]] · [[peer-captain-evidence]] ·
[[anti-overfit-killlist]]

**SEÑAL-SOLAMENTE.** Nada de lo que salió de esta investigación ordena al broker.
