# PLAN DE ESTUDIO — QUANT / GAMMA / CHARM / DESEQUILIBRIO DE DELTA
Creado 2026-08-22. Todos los enlaces VERIFICADOS vivos ese día (HTTP 200 / oembed OK).
Abrir por fases: `scripts/estudio.sh <0..9>` (Safari). `scripts/estudio.sh list` para ver el índice.

Regla de la casa aplicada aquí: **nada se acepta porque lo diga un vídeo**. Cada módulo cierra
con un ejercicio MEDIDO sobre datos propios (`data/`, `poly_bars`, `poly_opt_bars`, cadenas
archivadas). Si el ejercicio no reproduce lo que el vídeo afirma, gana el ejercicio.

Ritmo sugerido: 1 módulo/semana, ~1 h/día vídeo+lectura y 1 sesión larga de ejercicio el sábado.
M0 es obligatorio y va PRIMERO: es el filtro que impide que los otros 9 te vendan humo.

---

## M0 — CÓMO SE MIDE (el filtro antifraude) · 3 días
Objetivo: saber cuándo un resultado es real. Sin esto, todo lo demás es coleccionar creencias.

**Vídeo**
- Dangers of Backtest Overfitting — Marcos López de Prado · https://www.youtube.com/watch?v=QxhxLwNbMMg
- How Overfit Is Your Backtest? (PBO, revisión 2026) · https://www.youtube.com/watch?v=T-W0OzzoMKM

**Lectura**
- The Probability of Backtest Overfitting (Bailey, Borwein, LdP, Zhu) · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- The Deflated Sharpe Ratio · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

**Skills propios que ya cubren esto (releer antes de los vídeos)**
`measured-probability` · `drift-confound` · `walk-forward-validation` · `anti-overfit-killlist` · `base-rate-rojo-definicion` (memoria)

**Ejercicio**: coge la última señal viva de la flota, calcula su Wilson-LB sobre muestra EFECTIVA
(corregida por correlación) y su DSR contando cuántas variantes probaste. Si el DSR < 0, apágala.

**Criterio de paso**: sabes decir en 30 s por qué "45% vs apertura" y "12,8% vs cierre previo"
son el mismo dato y por qué el null importa más que el resultado.

---

## M1 — DERIVADOS Y GRIEGAS DE PRIMER ORDEN · 1 semana
Objetivo: derivar Black-Scholes y las griegas a mano; entender el P&L de una posición cubierta.

**Vídeo**
- MIT 18.S096 (playlist completa; aquí solo lecs 1, 15 Volatility Modeling, 17-18 Itô, 21-22 SDE/BS)
  · https://www.youtube.com/playlist?list=PLUl4u3cNGP63ctJIEC1UnZ0btsphnnoHR
  · índice web: https://ocw.mit.edu/courses/18-s096-topics-in-mathematics-with-applications-in-finance-fall-2013/video_galleries/video-lectures/
- Basic Delta Hedging Math (SpotGamma) · https://www.youtube.com/watch?v=GvnWidZZZsU
- Delta Hedging like a Quant — P&L (QuantPy) · https://www.youtube.com/watch?v=By3G_qs9ADU
- Hedging delta y gamma (Bionic Turtle, FRM T4-19) · https://www.youtube.com/watch?v=GCAM8UyCitE
- Delta Hedging y Gamma Scalping — completo (Outlier Trading) · https://www.youtube.com/watch?v=WnZmnltWViM
- Gamma Scalping vs Theta (Quantra) · https://www.youtube.com/watch?v=-jxVX4aijFg

**Lectura**
- OIC — Options Education (gratis, estructurado) · https://www.optionseducation.org/

**Libro**: Natenberg, *Option Volatility & Pricing* (caps. 5-8 griegas). Hull si falta base.

**Ejercicio**: reproduce `gex_core.bs_gamma` desde cero en C++23 y compara contra
`skill option-pricing-pro` en 1.000 strikes; error máximo < 1e-9. Luego simula el P&L de
gamma-scalping de un straddle QQQ con `poly_bars` 1m: ¿realizada > implícita ese día?

**Criterio de paso**: explicas por qué theta y gamma son la misma moneda, y calculas el
breakeven diario de una posición larga de gamma sin mirar apuntes.

---

## M2 — GRIEGAS DE SEGUNDO ORDEN: VANNA, CHARM, VOMMA, SPEED · 1 semana
Objetivo: entender qué mueve delta cuando NO se mueve el spot (tiempo e IV).

**Vídeo**
- Vanna, Charm & Dealer Hedging Flows (SpotGamma) · https://www.youtube.com/watch?v=u6KtNfjpm9E
- Options Vanna Delta Charm: cómo mueve mercados (SpotGamma) · https://www.youtube.com/watch?v=veJRTWLNvoU
- Vanna & Charm: las fuerzas ocultas (MenthorQ) · https://www.youtube.com/watch?v=CflbCveyEOQ
- Gamma, Charm & Vanna explicadas (OptionsDepth) · https://www.youtube.com/watch?v=NrpdRNWEIHg
- Cómo gamma/vanna/charm mueven el mercado (Perfiliev) · https://www.youtube.com/watch?v=0oJqC9QK-I0
- Gamma and Vanna exposures — mecánica del hedge (KeyPaganRush) · https://www.youtube.com/watch?v=zfkOCc2evEk
- Vanna and Charm Exposure (KeyPaganRush) · https://www.youtube.com/watch?v=-RhSCoElB9Y
- Combinar vanna+gamma+charm en un total de hedging (Fatty Trades) · https://www.youtube.com/watch?v=LZuh8HoIpGE
- Cem Karsan — Vol curves, vanna y charm (The Derivative) · https://www.youtube.com/watch?v=8awiGrquYXI
- Cem Karsan — Charming Vanna (Market Huddle 113) · https://www.youtube.com/watch?v=AdN2_7Xat1o
- Cem Karsan — flujos de opciones, 2026 (tastylive) · https://www.youtube.com/watch?v=UfPFk0rHrY4

**Herramienta de referencia**: https://vannacharm.com/ (para ver la forma de las curvas, no para fiarse)

**Libro**: Taleb, *Dynamic Hedging* (caps. de griegas de orden superior). Duro; leer después de M1.

**Ejercicio**: sobre una cadena archivada (`data/history/<fecha>/chain_full_QQQ.json`), calcula
VEX y CHEX por strike y compáralos con el GEX del mismo día. ¿A qué hora del día domina charm?
Contrasta con lo que tu `pin-and-expiry-mechanics` afirma del arrastre de tarde.

**Criterio de paso**: sabes decir, con la cadena delante, cuánta delta tiene que comprar o vender
el dealer mañana **solo por el paso del tiempo**, y cuánta si el IV cae 2 puntos.

**Aviso medido (tu propia sesión)**: ARCHI/@astocks92 **no usa vanna** en sus 610 posts —
usa gamma, charm, speed y zomma. Ver skill `architect-method` antes de copiar a nadie.

---

## M3 — POSICIONAMIENTO DEL DEALER: GEX, DEX, MUROS, PINNING · 1,5 semanas
Objetivo: pasar de "el dealer está corto gamma" como eslogan a calcularlo y falsarlo.

**Vídeo**
- SPX Gamma Basics — introducción al hedge del dealer (SPX Gamma) · https://www.youtube.com/watch?v=uQWSeF8TYoU
- Options Positioning & Dealer Flows: marco moderno (SpotGamma) · https://www.youtube.com/watch?v=BSfvX9MdFUM
- Playing Against the House — poder del posicionamiento (SpotGamma, 2026) · https://www.youtube.com/watch?v=IyI4VzlVLSQ
- Gamma, vanna, charm y cómo las opciones influyen al mercado — Brent Kochuba (Excess Returns) · https://www.youtube.com/watch?v=mSeZpocDnYk
- The Implied Order Book, GEX y cómo revientan los mercados · https://www.youtube.com/watch?v=p9qSlW-jrrk
- Dealer positioning: delta, gamma, vanna y charm flows (Tradytics) · https://www.youtube.com/watch?v=GN2ZXCWOrq8

**Lectura (el núcleo duro)**
- SqueezeMetrics — *The Implied Order Book* (PDF) · https://www.squeezemetrics.com/monitor/download/pdf/The_Implied_Order_Book.pdf
- SqueezeMetrics — guía del master spreadsheet (GEX/DIX) · https://squeezemetrics.com/monitor/static/guide.pdf
- **Gamma Fragility** — Barbon & Buraschi (PDF universidad) · https://alexandria.unisg.ch/server/api/core/bitstreams/25fec636-90a2-4735-a3a4-dfc0b68d3feb/content
- Ni, Pearson, Poteshman, White — *Does Option Trading Have a Pervasive Impact?* (PDF) · https://www.ou.edu/dam/price/Finance/CFS/paper/pdf/pearsonPoteshmanWhite.pdf
- Avellaneda — *Mathematical Models for Stock Pinning near Expiration* (PDF NYU) · https://math.nyu.edu/inmemoriam/avellaneda/PowerLaw.pdf
- Resumen BSIC: cómo la gamma del dealer impacta a la acción · https://www.bsic.it/wp-content/uploads/2022/03/Download-PDF-3.pdf
- SpotGamma: niveles clave · https://spotgamma.com/options-key-levels-explained/

**Skills propios**: `gamma-regime-walls` · `gex-gamma-walls-tooling` · `pin-and-expiry-mechanics` · `print-o-nada-levels` · `oi-magnets-protocol` (memoria)

**Ejercicio**: mide el pinning en TU histórico — para cada OPEX de los últimos 12 meses, distancia
del cierre al strike de mayor OI vs. la misma distancia en un miércoles cualquiera. **Ajusta por
dividendo** (ex-div de SPY cae en el tercer viernes: ese confusor ya te costó un z=-4,85 falso).

**Criterio de paso**: reproduces el GEX de `gex_snapshot.py` a mano en una hoja y sabes en qué
supuesto (signo del OI del dealer) descansa todo el edificio.

---

## M4 — SUPERFICIE DE VOLATILIDAD: SKEW, TÉRMINO, VRP · 1 semana
Objetivo: leer la superficie como información, no como decoración.

**Vídeo**
- Volatility Explained: skew, term structure y VRP (MenthorQ) · https://www.youtube.com/watch?v=FWyXf6wsDX8
- Volatility Skew Explained (tastylive) · https://www.youtube.com/watch?v=cVQudesBUcA
- Smile y skew explicados (Ryan O'Connell CFA/FRM) · https://www.youtube.com/watch?v=ARSQiNi2sHw
- Term structure de volatilidad (Barchart) · https://www.youtube.com/watch?v=txreI2RK9Hg
- Volatility, term structure y vertical skew — Passarelli (Firstrade) · https://www.youtube.com/watch?v=dacv7ji1SjY
- Calcular skew y superficie (Quantra) · https://www.youtube.com/watch?v=8pCRkN8rScY
- Jim Gatheral — 10 años de rough volatility (Cornell CFEM) · https://www.youtube.com/watch?v=sVwQD1GEZys

**Lectura**
- Gatheral, página del curso Baruch MFE (slides y papers) · https://mfe.baruch.cuny.edu/jgatheral/
- Gatheral personal (papers recientes) · https://jgatheral.github.io/
- *Volatility is rough* (arXiv) · https://arxiv.org/pdf/1410.3394
- Metodología oficial del VIX (Cboe) · https://cdn.cboe.com/resources/indices/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf
- Metodología VIX1D (1 día — la que importa para 0DTE) · https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Cboe_1-Day_Volatility_Index.pdf
- Interpolación de vencimientos del VIX (Andersen & Bondarenko) · https://cdn.cboe.com/resources/education/research_publications/VIXInterpolationWhitepaper.pdf

**Libro**: Sinclair, *Volatility Trading* (VRP, medir vol, gestión). Gatheral, *The Volatility Surface*.

**Skills propios**: `volatility-modeling` · `earnings-iv-term-structure` · `expected-move-envelope` · `event-premium-discipline`

**Ejercicio**: construye el RR25 percentilado por ticker de la flota con las cadenas archivadas y
comprueba si predice algo a 1-5 días. Recuerda lo YA MEDIDO: el skew 25-delta con +7,4 pp era
DERIVA, no señal (`drift-confound`). Repite el test con el null correcto.

**Criterio de paso**: distingues carry de IV anualizada de una ganancia real de vol, y sabes por
qué comprar prima antes de un evento anunciado paga 2-3× el movimiento histórico.

---

## M5 — 0DTE Y ESTRUCTURA MODERNA · 1 semana
Objetivo: saber qué está probado y qué no sobre el efecto de los 0DTE.

**Vídeo**
- The Impact of zero DTE Options (SpotGamma) · https://www.youtube.com/watch?v=hNJEcNOyNg8
- El paper de gamma 0DTE de CBOE, comentado (SpotGamma) · https://www.youtube.com/watch?v=ng6jeLRCrz0
- 0DTE Charm — deep dive de posicionamiento (Wizard of Ops) · https://www.youtube.com/watch?v=ctckWAQ4B5A
- 0DTE Delta Decay — hedge intradía cuantificado (Wizard of Ops) · https://www.youtube.com/watch?v=eKffLfXcnp4

**Lectura (lados opuestos — leerlos juntos a propósito)**
- CBOE: *0DTE Index Options and Market Volatility: How Large is Their Impact?* (PDF) · https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf
- Adams, Fontaine, Ornthanalai — los MM **atenúan** la volatilidad · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4881008
- Brogaard, Han, Won — los 0DTE **aumentan** la volatilidad · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4426358
- Resumen QuantPedia del debate · https://quantpedia.com/do-sp500-0dtes-options-increase-market-volatility/
- Guía 0DTE de SpotGamma · https://spotgamma.com/0dte/

**Skills propios**: `0dte-only-budget` (memoria: ≤$200 cualquier ticker) · `pin-day-playbook` · `postmarket-cage-release`

**Ejercicio**: en tus 22 días de `poly_opt_bars`, mide la reversión de flujo intradía en días de
alto volumen 0DTE vs bajo. Muestra pequeña → el resultado esperado es DATA-INSUFFICIENT: escríbelo
así, no lo maquilles.

**Criterio de paso**: puedes defender las dos tesis con sus datos y decir cuál mediría tu propio
histórico si tuvieras 250 sesiones.

---

## M6 — MICROESTRUCTURA Y ORDER FLOW · 1,5 semanas
Objetivo: de dónde sale realmente el precio; por qué el desequilibrio del libro predice el tick.

**Vídeo**
- Curso completo Financial Markets Microstructure (UCPH, Foucault-Pagano-Röell) · https://www.youtube.com/playlist?list=PL4pUs4P_j1Wa2_P1lw44kFWWjKDTGUY7S
  - empieza por Lec 1 Concepts and Institutions · https://www.youtube.com/watch?v=nPqat782ADI
  - Lec 3 Information and Prices (Kyle, Glosten-Milgrom) · https://www.youtube.com/watch?v=P0-92CIfAUo
- Market Microstructure — Skiena, COMP510 · https://www.youtube.com/watch?v=rJqgrH2zroA
- Introducción a microestructura (NPTEL IIT Kanpur) · https://www.youtube.com/watch?v=MrrYFV37jK8 · y https://www.youtube.com/watch?v=-S5X1F2lFP8

**Lectura**
- Lehalle & Laruelle — *Market Microstructure Knowledge Needed for Controlling Order Flow* · https://arxiv.org/pdf/1302.4592
- *Empirical Study of Market Impact Conditional on Order-Flow Imbalance* · https://arxiv.org/pdf/2004.08290
- Guéant, Lehalle, Fernandez-Tapia — *Dealing with Inventory Risk* (market making) · https://arxiv.org/pdf/1105.3115
- Tutorial ejecutable: market making con alpha de order-book imbalance · https://hftbacktest.readthedocs.io/en/latest/tutorials/Market%20Making%20with%20Alpha%20-%20Order%20Book%20Imbalance.html
- Materiales del curso UCPH (slides + ejercicios resueltos) · https://github.com/electronicgore/finmarkets

**Libro**: Larry Harris, *Trading and Exchanges* (el mapa completo del terreno).

**Skill propio**: `market-microstructure`

**Límite físico que ya mediste** (no lo olvides al diseñar nada aquí): en equities el agresor está
limitado — TRF ~52% del ADV llega sin lado. Ver memoria `us-equity-realtime-feed-pricing`.

**Criterio de paso**: calculas la lambda de Kyle de un ticker de la flota con tus barras 1m y sabes
por qué el mismo número no se traslada a la cadena de opciones.

---

## M7 — DESEQUILIBRIO DE DELTA APLICADO (el que tú operas) · 1 semana
Objetivo: convertir flujo en delta que el dealer DEBE cubrir — y saber cuándo eso no es señal.

**Lectura**
- HIRO: qué mide y cómo se lee · https://spotgamma.com/hiro-indicator/
- Cómo el flujo en tiempo real ayuda al 0DTE · https://spotgamma.com/real-time-options-flow-hiro-indicator-can-help-0dte-traders/

**Skills propios — este módulo es sobre todo TUYO, ya está medido**
- `option-volume-imbalance` — las dos OVI; solo la firmada de PUTS pasa FDR (t=+2,84) y muere al neutralizar mercado (t=+0,49). "Mucho volumen de calls = alcista" es **FALSO medido**.
- `delta-divergence-veto` — lo único vivo de toda la línea: −1,02 pp en largos, p=1,2e−7. Es VETO, no entrada. Objetivo MFE p60 = 1,08 ATR; stop MAE p75 = 1,29 ATR.
- `whale-forensics` — prima + ΔOI + charm; la prima sin ΔOI **no es posición**.
- `whale-conviction-gate` — 4 llaves para pasar de 273 pushes/sesión a un puñado.
- `options-chain-reversal-patterns` · `whale-alarm-napoleon-sword` (memoria)

**Ejercicio**: recalcula el veto de divergencia con los datos nuevos desde 2026-08-08 y comprueba
si el p-valor aguanta. Si se cae, apágalo el mismo día.

**Criterio de paso**: sabes por qué un P/C ratio no es una señal y qué le falta a un flujo grande
para ser una posición.

---

## M8 — LA MATEMÁTICA (cálculo estocástico y numérico) · 2 semanas
Objetivo: poder leer un paper sin saltarte las ecuaciones.

**Vídeo**
- MIT 18.S096 completo, en orden · https://www.youtube.com/playlist?list=PLUl4u3cNGP63ctJIEC1UnZ0btsphnnoHR
  (regresión → VaR → series temporales → modelos de volatilidad → procesos estocásticos → Itô → SDE → Black-Scholes)
- Canal QuantPy (implementación en Python de cada concepto) · https://www.youtube.com/@QuantPy

**Skills propios**: `option-pricing-pro` (9 métodos: BS, binomial, trinomial, MC + Longstaff-Schwartz, Bjerksund-Stensland, Heston, Bates) · `stats-trading-core` · `stats-trading-risk`

**Ejercicio**: invierte IV por bisección sobre `poly_opt_bars` (que no trae griegas) y reconstruye
gamma/vanna/charm por Black-Scholes. Marca el OI como proxy en el propio dato (`oi_source`) —
jamás mezclar reconstruido con medido sin decirlo en la cabecera.

**Criterio de paso**: derivas Itô→BS en una pizarra y explicas qué supuesto rompe cada modelo
(Heston: vol estocástica; Bates: saltos; rough vol: memoria larga).

---

## M9 — CONSTRUIR, VALIDAR Y EJECUTAR · 1,5 semanas
Objetivo: cerrar el círculo — de idea a estrategia con probabilidad honesta y ejecución real.

**Lectura / herramientas**
- awesome-quant (catálogo de librerías) · https://github.com/wilsonfreitas/awesome-quant
- QuantStart — artículos de backtesting y ejecución · https://www.quantstart.com/articles/
- Robot Wealth · https://robotwealth.com/ · PyQuantNews · https://www.pyquantnews.com/
- Moontower (Kris Abdelmessih) — sabiduría de trader de opciones · https://blog.moontower.ai/hard-earned-trading-wisdom/
- The Derivative (podcast, RCM) — archivo de episodios · https://www.rcmalternatives.com/education/podcast-the-derivative/

**Skills propios**: `backtesting-pro` · `walk-forward-validation` · `vectorbt` · `measured-probability` · `architect-indicator-backtest` · `guru-backtest` · `signal-conditioning-layer` (memoria) · `order-engine-execution` (memoria)

**Ejercicio final (el que vale)**: coge UNA idea de los módulos 2-7, formúlala como hipótesis
falsable, etiquétala con triple barrera, valídala walk-forward con null de entrada aleatoria y
BH-FDR, y decide keep/kill. Documenta el kill igual de bien que el keep.

**Criterio de paso**: la idea sobrevive o muere **con número**, y el número lo puedes reproducir
tres meses después.

---

## LIBROS — orden de lectura
1. Natenberg, *Option Volatility & Pricing* — la base que dan a todo trader nuevo en una mesa.
2. Larry Harris, *Trading and Exchanges* — cómo funciona el mercado de verdad.
3. Sinclair, *Volatility Trading* — medir vol y encontrar edge; el más cercano a lo que haces.
4. Gatheral, *The Volatility Surface* — la superficie con matemática seria.
5. Taleb, *Dynamic Hedging* — griegas de orden superior y lo que rompe los modelos.
6. López de Prado, *Advances in Financial Machine Learning* — solo por los caps. de validación.

## CANALES A SEGUIR (verificados)
- SpotGamma · https://www.youtube.com/@SpotGamma
- MenthorQ · https://www.youtube.com/@MenthorQ
- QuantPy · https://www.youtube.com/@QuantPy
- Excess Returns · https://www.youtube.com/@ExcessReturns

## LO QUE NO SE ESTUDIA
Ver skill `anti-overfit-killlist`: DIX/dark-pool, vanna-ramp sin historia de IV, OI firmado con
volumen 100× el OI, compuestos de z-scores, rankings de 30 nombres correlacionados. Y el patrón
común: un prior inventado disfrazado de medición.
