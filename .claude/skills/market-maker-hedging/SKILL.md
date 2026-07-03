---
name: market-maker-hedging
description: El modelo mental del ELEFANTE EN LA HABITACION — los 6-7 creadores de mercado que dan el 90% de la liquidez de opciones y que, al cubrirse para quedar P&L-neutrales, MUEVEN el subyacente. Destilado de Brent Kochuba (SpotGamma). Cubre el mecanismo de transmision, los cuatro griegos como motores de cobertura (delta base, gamma por precio, vanna por IV, charm por tiempo), las zonas de LIQUIDEZ como imanes (strikes en percentil 99, y el flujo que se APAGA al llegar), HIRO/Trace-Map/Captain-Condor/Vol-Trigger, la ventaja de informacion del creador, y el edge real: las DISLOCACIONES por miedo/codicia. Usar al leer un mapa gamma, al preguntarse "por que se movio si no hubo noticia", al evaluar una feature de vendedor de flujo, o cuando Yunior hable de market makers, elefantes, zonas de liquidez, HIRO o SpotGamma. SEÑAL-SOLAMENTE.
---

# El elefante en la habitación: cómo la cobertura del creador de mercado mueve el precio

> Fuente: Brent Kochuba (fundador de SpotGamma), entrevista en Pirate Traders.
> Guardado el 2026-07-25 por orden de Yunior: **"market makers are the elephants in the room"**.
> Complementa [[gexa-framework]] (taxonomía de niveles), [[gamma-exposure]] (nuestro cómputo),
> [[dealer-flow-limits]] (lo que NO se puede medir sin cinta) y [[flip-and-vol-trigger]].

---

## 1. El mecanismo de transmisión (la idea entera en un párrafo)

Solo hay **seis o siete creadores de mercado** grandes (Citadel, Susquehanna…) y dan
**~90% de la liquidez** de opciones. Cuando compras una call, **se la compras a uno de ellos**.
Al vendértela queda con riesgo, y para seguir **P&L-neutral** tiene que cubrirse **comprando el
subyacente**. Esa compra no es una opinión sobre la empresa: es mecánica.

**Ese flujo de cobertura es el único puente entre el mercado de opciones y el precio de la acción.**
Todo lo demás de esta skill son detalles de ese puente.

Por qué pesa hoy más que nunca: **0DTE es >60% del volumen diario del S&P 500**. Y aunque el
complejo de índice es el mayor del mundo, el volumen de opciones de los *Mag Seven* — sobre todo
**NVDA y TSLA** — puede arrastrar al índice entero. *(En casa eso ya está codificado como la
jerarquía de capitanes, [[flow-captains]].)*

---

## 2. Los cuatro griegos, leídos como MOTORES DE COBERTURA

No son matemáticas de valoración aquí: son **la respuesta a "cuántas acciones tiene que comprar o
vender el creador, y por qué"**.

| Griego | Qué mide | Qué OBLIGA a hacer al creador |
|---|---|---|
| **Delta** | ratio de cobertura base | cuántas acciones debe tener **ahora mismo** |
| **Gamma** | cómo cambia el delta **con el precio** | si la acción sube, cuántas **más** debe comprar para seguir cubierto |
| **Vanna** | cómo cambia el delta **con la IV (VIX)** | si el VIX salta, puede tener que **cortar en masa** aunque el precio no se haya movido |
| **Charm** | cómo cambia el delta **con el tiempo** | el arrastre de la **tarde**, según decae theta hacia el cierre |

La consecuencia operativa que más se olvida: **vanna y charm mueven precio sin que pase nada en el
precio**. Un día plano con VIX cayendo tiene flujo de cobertura real. *(En casa: `gex_core.bs_vanna`
y `bs_charm`; la ventana de charm es 13:30-15:45, ver [[pin-and-expiry-mechanics]].)*

---

## 3. Zonas de liquidez: el mercado va hacia donde puede comerciar

La idea más accionable del vídeo, y la que Yunior subrayó:

> **El mercado se mueve HACIA las zonas de liquidez.** Los strikes en **percentil 99** de tamaño
> son objetivos, casi imanes. Y cuando el precio llega, **el flujo simplemente se apaga**.

Dos lecturas prácticas:
1. Un objetivo no es "hasta donde creo que sube": es **hasta el siguiente charco de liquidez**.
2. **Llegar al charco es una señal de salida, no de continuación.** Si el flujo que empujaba se
   apaga al tocar el Put Wall, exprimir más allá es operar sin el motor que te trajo.

Encaja exactamente con la doctrina de la casa: *hacia el imán sí, a través del muro no*
(protocolo de imanes, [[gamma-regime-walls]]).

---

## 4. Los niveles, y cómo se comportan

- **Call Wall / Put Wall** — funcionan **como unas Bollinger del mercado**: el índice tiende a
  quedarse entre ellas y a revertir si se estira. Las posiciones trimestrales antiguas del Put Wall
  siguen siendo un barómetro excelente de suelos, mucho más estable que el ruido 0DTE del día.
- **Vol Trigger** — barómetro **risk-on / risk-off**. Por encima, risk-on. Romper por debajo pide
  protección. *(En casa: `scripts/vol_trigger.py`, congelado a las 09:35.)*
- **"Captain Condor"** — apodo de una posición 0DTE **recurrente y enorme** que fabrica un
  soporte y una resistencia el mismo día (en el vídeo, 6.300 y 6.350). Lección general:
  **algunos niveles del día no son técnicos, son una sola posición de alguien.** Si no miras
  opciones, no sabes que están ahí.
- **Trace Map** — mapa de calor que **pronostica la respuesta de cobertura** según se mueva el
  precio: **azul/morado = zona sostenida** (hay compradores debajo), **rojo = alta volatilidad**,
  donde el creador **persigue** el precio en vez de amortiguarlo.
- **HIRO / HERO** — línea en **tiempo real** que dice, operación a operación, si el creador está
  siendo forzado a **comprar o a vender** acción. Si baja, están entrando apuestas bajistas y el
  creador vende. Se puede separar flujo de **índice** vs **acciones individuales** para saber
  quién manda hoy.

---

## 5. Cómo gana dinero el creador (y por qué eso importa para leerle)

- El grueso del día a día: **spread bid-ask** + **decaimiento temporal (theta)**.
- Pero además tienen **ventaja de información**: una firma que ve el 40% del flujo sabe cómo está
  posicionado el mercado y puede **inclinar** sus coberturas.
- En crisis (2008) **ensanchan el spread cuanto quieren**, porque el que necesita operar no tiene
  alternativa. De ahí los beneficios récord en pánico.

Lectura para nosotros: **el spread es información, no solo un coste.** Un spread que se abre es el
creador diciendo que no quiere ese riesgo. *(Ya está codificado como veto duro: regla 4 y
`gate_core.hpp`, `MAX_SPREAD_PCT = 5.0`.)*

---

## 6. Dónde está el edge de verdad: DISLOCACIONES

El edge no es "saber el nivel". Es detectar cuándo **el miedo o la codicia** han empujado el
posicionamiento a un sitio insostenible:

- **Efecto "Sydney Sweeney"**: el minorista inunda un nombre de calls cortas de plazo → el creador
  debe cubrir comprando → sube → entran más calls → **ciclo de apalancamiento** que lleva el precio
  a niveles que no se sostienen. Cuando la codicia es excesiva, se opera **contra** la dislocación.
- **Un movimiento brusco suele ser un CAMBIO DE POSICIÓN, no una noticia.** Ver en vivo que alguien
  cierra un lote de 10.000 te deja comprar la caída con criterio, en vez de suponer que el mundo
  ha cambiado.

Esto es, literalmente, la **táctica espada-ballena** de la casa (regla 11) descrita desde el otro
lado del mostrador.

---

## 7. Qué de esto tenemos, qué NO, y qué acaba de cambiar

Honestidad primero: esta skill es un **modelo mental de vendedor**. Antes de construir nada de
aquí, pasa por [[anti-overfit-killlist]] y [[measured-probability]].

| Concepto | Estado en casa (medido 2026-07-25) |
|---|---|
| Muros call/put, abs_wall, POC gamma | **TENEMOS** — `gex_core.build_gex` |
| Flip / régimen, repreciado por bisección | **TENEMOS** — y el naíf (raíz del GEX acumulado) está demostrado basura |
| Vol Trigger congelado 09:35 | **TENEMOS** — `vol_trigger.py` |
| Vanna / charm | **TENEMOS** la matemática (`bs_vanna`, `bs_charm`); falta la capa CHARM en el chart |
| Zonas de liquidez / percentil 99 | **NO** — construible desde el perfil que ya calculamos |
| Trace Map (pronóstico de cobertura) | **NO** — construible: es reevaluar el perfil a spots hipotéticos, que `_gex_at` ya sabe hacer |
| **HIRO** (dirección forzada en vivo) | Estaba **BLOQUEADO** por falta de cinta OPRA firmada… |
| Market tide firmado, dark pool | …**y también** |

⚠️ **Lo que cambió el 2026-07-25**: el trial de **Unusual Whales** (`UW_TOKEN` en `feeds.env`,
caduca ~2026-08-01) devuelve 200 en `/api/market/market-tide` (net call/put premium y **net_volume
FIRMADO** en cubos de 5 min), `/api/stock/<SYM>/spot-exposures` (gamma/vanna/charm por 1% intradía
= equivalente a HIRO), `/api/stock/<SYM>/greek-exposure` (**un año** de griegas de dealer diarias),
`/api/darkpool/<SYM>` y `/api/stock/<SYM>/flow-alerts`.

**Regla dura**: una fuente de pago con reloj de 7 días **NO puede ser dependencia de una señal**
— es la lección de gexa.ai, que murió y se llevó ocho consumidores por delante. Lo correcto
mientras dura el trial es **archivar su histórico** y **medirlo contra el nuestro**, no cablearlo.

---

## 8. Cómo usar esta skill

1. **Al leer un mapa**: pregunta siempre *"¿qué le OBLIGA esto a hacer al creador?"* antes de
   *"¿qué nivel es este?"*. Un muro no es una línea: es un sitio donde alguien tiene que operar.
2. **Al fijar un objetivo**: el objetivo es el siguiente charco de liquidez, y **llegar es salir**.
3. **Ante un movimiento sin noticia**: la primera hipótesis es cobertura o cierre de posición,
   no información nueva.
4. **Ante una feature nueva de vendedor**: pasa por [[anti-overfit-killlist]]. Que el modelo mental
   sea correcto no hace que la feature esté medida.
5. **Nunca** conviertas nada de aquí en una probabilidad hablada sin pasarla por
   [[measured-probability]]: triple barrera, Wilson sobre muestra efectiva (ρ̄ de la flota = 0,41),
   null de entrada aleatoria y BH-FDR. **SEÑAL-SOLAMENTE.**
