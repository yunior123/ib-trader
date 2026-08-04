# KOREA + SENTIMIENTO SOCIAL + DARKPOOL — martes 2026-08-04 (escrito 14:05 EDT)

Fuentes: puente Naver (`data/bars_*`, `data/korea_prevclose.json`, frescura 13:19 EDT), WebSearch/WebFetch con fecha, UW API (10/12 requests). IBKR prohibido esta semana — nada de aquí dispara órdenes. Señal-solamente.

---

## 1) COREA ESTA NOCHE (KST miércoles 8/5, 20:00→02:30 ET) — VEREDICTO: **MIXTO, sesgo COMPRAN si AMD confirma** (retail compra, extranjeros distribuyen)

### Evidencia

**(1) Últimas 3 sesiones KRX — MEDIDO en los ficheros del puente Naver** (cierres por sesión agregados de `data/bars_samsung.txt` / `bars_skhynix.txt` / `bars_kospi.txt`):

| Sesión KST | KOSPI | Samsung 005930 | SK Hynix 000660 |
|---|---|---|---|
| vie 7/31 | — (sin barras) | cierre 265.000 (rebote récord) | cierre 1.718.000 (rebote récord) |
| lun 8/3 | 6.257,45 (**-5,1%**, Yonhap) | 239.500 (**-9,6%** medido) | 1.567.000 (**-8,8%** medido) |
| mar 8/4 (anoche) | 6.358,95 (**+1,62%**) | 239.500 (**0,0%**; mínimo 228.000 = -4,8% recuperado) | 1.575.000 (**+0,5%**; mínimo 1.484.000 = -5,3% recuperado) |

- Anoche fue una **V intradía violenta**: KOSPI abrió ~6.351, cayó a **6.080,25 (-2,8%)** y cerró +1,62% en 6.358,95. El mínimo 6.080,25 del puente coincide EXACTO con la prensa coreana — puente validado.
- Contexto de régimen: KOSPI **-22,18% en julio** (peor mes desde 2008, desapalancamiento retail del AI-trade), viernes 7/31 rebote récord (Samsung/SKH ~+27/+30%), lunes purga -5%, martes V. Es régimen de latigazos, no tendencia limpia. (CNBC 7/31, Bloomberg 8/3, Benzinga 8/4)

**(2) QUIÉN compra y quién vende — el dato clave:** el rebote de anoche lo hizo el **retail**; los **extranjeros vendieron neto 370,56 MM₩ el 8/4**, y el lunes 8/3 el 95,4% de su venta neta se concentró en Samsung (945,5 MM₩) + SK Hynix (1,77 BN₩). **Los extranjeros llevan 2 sesiones distribuyendo exactamente los dos nombres que nos lideran la memoria.** (Businesskorea/Yonhap 8/4)

**(3) Noticias memoria/HBM frescas:**
- HBM **agotado hasta fin de 2026** en SK Hynix/Samsung/Micron; HBM4 ~$500/stack vs HBM3E ~$300; SKH arrancó producción en masa HBM4 en Q2 con yields "casi maduros" y rampa fuerte en H2; Samsung guía HBM4 Q3 = 3x Q2. (Silicon Analysts, digitimes, sedaily 7/29)
- Samsung: beneficio de chips x250 interanual, acuerdos multianuales con datacenters, avisa de escasez "hasta 2028"; Tim Cook avisa de subidas de precio por coste de memoria. DRAM spot al alza. (recaps 7/30-8/3)
- Contra: la coreana KIS recortó estimación Q2 de SKH un **-8% vs consenso** por envíos HBM4 más lentos — fue el detonante del susto sectorial de julio. El fundamental es alcista; el posicionamiento estaba reventado.

**(4) Lead-lag y los earnings US:**
- Doctrina de la casa (skill `korea-memoria`): Corea lidera **~13h** a MU/DRAM/semis US; al cierre KRX (02:30 ET) se lee el sesgo Samsung/SKH y se aplica al premarket de MU/SMH/NVDA/TSM/ASML. **FAIL-LOUD: no hay en el repo una n medida de "sesión coreana anticipa earnings US de memoria" — es doctrina etiquetada, no probabilidad medida.**
- Secuencia horaria de esta noche (la clave): **AMD reporta hoy 16:00-17:00 ET y SpaceX hoy 16:30 ET — ANTES de que abra KRX a las 20:00 ET.** Corea operará esta noche CON los resultados de AMD ya impresos: si AMD confirma (Polymarket da 95% de beat, pero expectativas por las nubes), los semis coreanos deberían extender el rebote. **SNDK/WDC reportan mañana 8/5 AMC (verificado: Sandisk press release oficial + WDC mismo día)** — eso es DESPUÉS de la sesión coreana de esta noche; Corea no puede anticipar esos números, pero su cierre de 02:30 ET fija el tono del premarket del día de earnings.

### Veredicto razonado
**MIXTO con sesgo a COMPRAN** (continuación del rebote retail) **condicionado a AMD**: fundamental de memoria intacto y agotado hasta 2026, retail coreano comprando el dip 2 noches seguidas, y AMD conocido antes de la apertura. El viento en contra REAL: **extranjeros distribuyendo Samsung/SKH 2 sesiones seguidas** en régimen de desapalancamiento — si AMD decepciona con estas expectativas, la V de anoche se deshace y el mínimo 6.080 vuelve a ser imán. No es una noche para presuponer dirección antes de las 17:05 ET (reacción AMD).

---

## 2) SENTIMIENTO SOCIAL (medido hoy; StockTwits gauge directo INACCESIBLE — API y web 403 Cloudflare; lo salvado viene de sus propios artículos y de recaps WSB con fecha)

| Ticker | Sentimiento | Evidencia + hora |
|---|---|---|
| **MU** | 🟢 Bullish | StockTwits retail "bullish" (artículo ST ~9h antes de 14:00 EDT); WSB score 66 bullish lunes; entre los más mencionados de WSB con TSLA y GME. Spot 895,56 (14:02 EDT, finnhub). +12% semana, net premium +124M (dato coordinador). |
| **SNDK** | 🟢🟢 Extremely bullish | StockTwits "extremely bullish" TODA la semana (dos lecturas: hace 5 días y hace ~9h); WSB 58-75 durante el selloff = dip-buyers firmes. Vísperas de earnings 8/5 AMC. Spot 1.435,75 (14:02). |
| **WDC** | 🟡 Mixto (retail entrando, gauge bearish) | StockTwits gauge "bearish→extremely bearish" esta semana, PERO titular ST "WDC to $1,000? Retail piles into memory underdog". El menos querido de los tres = menos expectativa cargada para su earnings 8/5. Spot 556,59 (14:02). |
| **AMD** | 🟢 Bullish extremo (expectativa cargadísima) | Reporta HOY AMC 17:00 ET. Polymarket 95% prob de beat; consenso EPS $1,61 / rev $11,31B / DC +100%; +8% hoy intradía; Seeking Alpha: "sky-high expectations leave little room for missteps". Spot 526,40 (14:02). |
| **TSLA** | 🟢 Bullish moderado | +3,5% hoy sin catalizador único (narrativa autonomía/robotaxi, rebote post-earnings flojo de Q2); top-trend en WSB. Spot 325,49 (14:02). |
| **SPCX** (SpaceX common stock — NO ETF) | 🔴 Bearish/short-heavy con squeeze posible | **Primera earnings como pública HOY 16:30 ET** + **lockup de 911,5M acciones (12% del total, más que el float de 640M) expira el 8/6**. -30% desde el debut a $150, -50% desde ATH $225,64; racha de 7 días perdedores rota; "short sellers piling in" (CNBC/Axios 8/3) — los cortos son soporte mecánico en el unlock. Hoy volátil: 116,20→118,64 por la mañana, 124,56 a las 14:02 (nuestro rt_last) = **+7% desde el mínimo del día**, dp prints a 125. |
| **Memoria en general** | 🟢 Bullish con nervios | WSB mayormente comprador; DRAM ETF gauge "bearish/extremely bearish" (retail quemado por el latigazo de julio); SKHY "neutral". El gauge castiga los vehículos, no la tesis. |

**FAIL-LOUD:** X/Twitter sin métrica directa medible (sin API); StockTwits gauge numérico inaccesible (403) — las etiquetas de arriba salen de artículos de StockTwits News con timestamp, no del widget. Reddit vía recaps MarketScreener/AltIndex (WSB scores), no conteo propio.

---

## 3) DARKPOOL HOY (UW `/api/darkpool/{sym}`, 10 requests; **limitación: cada request devuelve los ~200 prints más recientes = ventana de minutos, NO el día entero**)

| Ticker | Muestra mañana (~10:28 EDT) | Muestra tarde (13:04-13:21 EDT) | Lectura |
|---|---|---|---|
| **MU** | $48,3M, vwap **883,32** | $53,3M; sobre spot $8,2M / bajo $22,9M (spot 894,5) | Spot 14:02 = 895,56 → TODOS los bloques de la mañana comprados a descuento vs precio actual. Cinta subiendo + bloques absorbidos = **acumulación** |
| **SNDK** | $44,8M, vwap **1.389,67** | $46,7M; bajo spot $35,2M (spot 1.436,5) | Spot 1.435,75 = +3,3% sobre el vwap dp matinal → **acumulación** clara pre-earnings |
| **WDC** | $44,0M, vwap **544,70** (bloque $2,7M a 541,20) | $39,3M; bajo spot $30,5M (spot 553,1) | Spot 556,59 = +2,2% sobre vwap matinal → **acumulación** (la más silenciosa de las tres) |
| **TSLA** | $47,9M, vwap **323,42** | $58,0M; bloques 9.060 acc a 326,00 | Spot 325,49 ≈ prints → **neutral-acumulación**, flujo dp muy denso ($58M en 16 min) |
| **SPCX** | — | ~14:00 EDT: $40,2M en 3 MIN, prints ~**125,0** (bloque 8.600 acc) | Cinta 122→124,6 en 40 min con dp masivo → **acumulación agresiva into earnings** (o cobertura de cortos pre-print; dp no firma el lado) |
| **AMD** | — | ~14:00 EDT: $48,2M en 5 min, prints ~**526,7** (bloque $2,7M) | Denso y subiendo into earnings → **acumulación** |

Honestidad del dato: el darkpool NO firma el lado agresor. La etiqueta "acumulación" sale de: bloques grandes impresos a precios que quedan POR DEBAJO del precio posterior + cinta ascendente todo el día (distribución sería lo contrario). Prints mayoritariamente dentro del NBBO (midpoint). "Sobre/bajo spot" de la tarde usa spot de 13:20 vs prints de 13:04-13:21: ruido de ±minutos, el dato firme es vwap-mañana vs precio-ahora.

---

## 4) SÍNTESIS — ¿el caput de mañana (SNDK/WDC 8/5 AMC) viene con viento coreano a favor o en contra?

**A FAVOR, pero es un viento de retail con extranjeros vendiendo dentro — y el interruptor es AMD esta tarde.**

1. **Secuencia:** AMD + SpaceX imprimen hoy 16:00-17:00 ET → KRX abre 20:00 ET y opera CON esos resultados → cierra 02:30 ET → premarket US hereda el sesgo → SNDK/WDC reportan mañana AMC. La sesión coreana de esta noche es el **puente de sentimiento** entre AMD y el caput de memoria, no un oráculo de los números de SNDK/WDC.
2. **Escenario base (AMD cumple, prob de beat cotizada 95% pero listón altísimo):** Corea extiende la V de anoche → Samsung/SKH verdes → premarket MU/SNDK/WDC con viento a favor → el caput llega con acumulación dp de 2 días y sentimiento extremely-bullish en SNDK. Riesgo entonces: expectativa ya cargada (SNDK +22% en el rebote, gauge extremo) = listón de earnings alto.
3. **Escenario rojo (AMD decepciona):** con extranjeros ya distribuyendo Samsung/SKH y el régimen de desapalancamiento de julio vivo, Corea puede devolver la V entera (imán 6.080) → premarket de memoria rojo el MISMO día de earnings SNDK/WDC → los gaps se venden. La señal de anoche (mínimos -5% intradía recomprados) dice que el retail coreano aún compra los sustos — hasta que no lo haga.
4. **Regla de la casa aplicable:** día de earnings del ticker = jamás aguantar el print con premium comprado (SNDK/WDC mañana); SPCX hoy es binario earnings+lockup 8/6 — short-heavy con squeeze mecánico posible, no es sitio para premium comprado sin print.
5. **Chequeo a las 02:30 ET:** leer cierre Samsung/SKH del puente Naver (`data/korea_prevclose.json` + últimas barras) y aplicar el sesgo al premarket — checklist del skill `korea-memoria`.

**Lo que NO se pudo medir (fail-loud):** StockTwits gauge directo (403), X/Twitter cuantitativo (sin API), n histórica de "Corea anticipa earnings US de memoria" (no existe en el repo), darkpool de día completo (UW pagina de 200 en 200 y la cuota era 12), flujo institucional coreano de ESTA noche (se sabrá al cierre).
