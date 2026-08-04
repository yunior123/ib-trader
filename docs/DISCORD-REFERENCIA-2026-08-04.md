# Discord de referencia — Spartan Trading, estudio 2026-08-04

Servidor estudiado: **Spartan Trading - Live Chatroom**, guild `492093482576510982`.
Objetivo: extraer qué copiar a nuestro servidor de alertas.

## 0. ESTADO: OBSERVADO — 29 canales leídos, 2.000+ mensajes

**Primer intento (fallido), se conserva como registro:** la extensión Claude-in-Chrome no
estaba emparejada (`list_connected_browsers` → `[]` en 4 intentos) y el widget público del
guild devuelve **HTTP 403 `Widget Disabled`**. Se paró en vez de insistir.

**Segundo intento (este), con acceso resuelto:** Chrome headless con copia del perfil de
Yunior (sesión de Discord iniciada) escuchando CDP en `127.0.0.1:9333`; driver de solo lectura
que navega, espera al SPA y extrae DOM. **Nada se escribió, ni un mensaje, ni una reacción,
ni un botón.** Gotchas pagados: `/json/new` exige PUT en Chrome 150; el scroller de mensajes
NO es el primer `div[class*="scroller"]` (ese es la barra lateral) — hay que subir desde un
`li[id^="chat-messages-"]`; Discord virtualiza y borra del DOM lo que sale de pantalla, así
que hay que acumular por `id`.

**Cobertura conseguida** (29 canales visibles; los privados/no-visibles se declaran en §9):

| ámbito | profundidad medida |
|---|---|
| mapa completo | 34 items de barra lateral = 4 cabeceras de categoría + 29 canales + 1 contenedor |
| canales de alerta | `options` 132 msgs (07-31→08-03), `equity` 36, `spx` 36 |
| planes | `premarket-on-watch` 300 msgs (07-01→08-03, 23 sesiones) |
| post-mortem | `daily-recap` 276 msgs, **95 recaps** (03-16→08-03) |
| doctrina/onboarding | `new-to-chat` 13, `info-and-definitions` 4, `risk-reward-archives` 45 — texto íntegro |
| resto | 22 canales más, ventana de scroll variable |

⚠ Los conteos por día de los canales de baja frecuencia son **suelo, no total**: solo se cargó
la ventana de scroll. El único día con carga completa en los canales de alerta es
**lunes 2026-08-03**, y de ahí sale toda la cadencia de §3.

---

## 1. Mapa completo del servidor

29 canales, 4 categorías + 3 canales sueltos arriba del árbol. `(Ltd)` = Discord lo marca
"Text (Limited)": lectura sí, escritura restringida — su separación gratis/premium (§7).

| # | categoría | canal (nombre exacto) | id |
|--:|---|---|---|
| 1 | *(sin categoría)* | `🔊disclaimer` | 815655436103581737 |
| 2 | | `📢announcements📢` | 493802045359259648 |
| 3 | | `💸completed-trades` | 492093720749932545 |
| 4 | **New? Read Me!** | `⭐new-to-chat-information⭐` (Ltd) | 493845991523352579 |
| 5 | | `📌info-and-definitions` *(canal tipo Rules)* | 494635306021027840 |
| 6 | **Mod Alerts & Charts** | `❽earnings` (Ltd) | 593854175335546961 |
| 7 | | `📕side-charts` (Ltd) | 571129309884973056 |
| 8 | | `✍high-conviction-small-account` (Ltd) | 943613245183381504 |
| 9 | | `⏰premarket-on-watch` (Ltd) | 493492245220032542 |
| 10 | | `📅options-ideas-alerts` (Ltd) | 821911150727659520 |
| 11 | | `📈equity-ideas-alerts` (Ltd) | 821910847135416360 |
| 12 | | `🤖spx-idea-alerts` (Ltd) | 956760265620336650 |
| 13 | **Members Area** | `📍live-chat-questions` (Ltd) | 492093482576511019 |
| 14 | | `📐support-resistance-levels` (Ltd) | 758737190405799946 |
| 15 | | `✍jc-thesis-and-research` (Ltd) | 800059189925642250 |
| 16 | | `💹charts` (Ltd) | 829496827879096340 |
| 17 | | `🪙crypto-and-sports-betting` (Ltd) | 823691649762590761 |
| 18 | **Resources** | `💻daily-recap` | 928759257019580458 |
| 19 | | `🤖bot-talk` (Ltd) | 493505462277373975 |
| 20 | | `📞spartan-call-schedule` (Ltd) | 497525841555881984 |
| 21 | | `💻tech-and-software` (Ltd) | 515567214170996772 |
| 22 | | `⚖risk-reward-archives` (Ltd) | 745037127863107744 |
| 23 | | `✏-journal-download` (Ltd) | 553674508075008011 |
| 24 | | `🎓spartans-webinars` | 784854431501123604 |
| 25 | | `🤝affiliate-deals` | 619244162629369886 |
| 26 | | `🧠free-resources` | 500499474859163648 |
| 27 | | `📣faq-video-request` (Ltd) | 511279223898636308 |
| 28 | | `❓helpful-q-and-a-archive🅰` (Ltd) | 701118194085134416 |
| 29 | | `📩news-wire` (Ltd) | 493223009847345152 |

Un canal más, `deal-flow-private-placement`, se cita en su propio índice interno
(`new-to-chat`, 2019-02-01) pero **no aparece en la barra lateral** → no visible para esta
cuenta. Ver §9.

**Lo que el mapa dice y hay que copiar:** solo **7 de 29 canales (24 %)** publican señal
(`options`, `equity`, `spx`, `high-conviction`, `premarket`, `side-charts`, `earnings`).
Todo lo demás es doctrina, educación, comunidad o venta. Nuestro `discord_layout.py` tiene
hoy **13 canales en `🚨 ALERTAS EN VIVO` de 32** (41 %) — somos más ruidosos por diseño que la
referencia, antes incluso de emitir la primera alerta.

---

## 2. Formato real de sus alertas — 5 ejemplos textuales

**El hallazgo más importante de todo el estudio, y es un hallazgo NEGATIVO:**

> En **204 mensajes de los tres canales de alerta** (07-31 y 08-03): **0 embeds, 0 bots,
> 0 hilos, 0 ediciones, 1 mensaje con imagen y 1 con reacción.** Todo es texto plano tecleado
> por un humano, en minúsculas, con erratas sin corregir (`odea`, `diea`, `1/10tj elft`,
> `1/4 left\`). (La única edición vista en todo el estudio está en
> `✍high-conviction-small-account`, 2026-07-23 — para corregir una errata, no para actualizar
> un estado.)

Medido con `getComputedStyle` sobre cada `[class*="embedFull"]`: ninguno existe. No hay
color de embed que copiar porque no hay embeds. Los adjuntos (imágenes) viven en
`premarket-on-watch`, `side-charts` y `completed-trades` — **jamás en el canal de alerta**.

### Opciones — `📅options-ideas-alerts`, 2026-08-03

```
09:56 ET  ADBE 290c idea
09:56 ET  .72
09:56 ET  dpm 1
```
```
13:41 ET  TSLA 325c idea
13:41 ET  .27
13:41 ET  dpm .3
```

### Gestión de la misma posición (mensajes nuevos, NUNCA edición del original)

```
09:56 ET  NVDA 1/4 out
09:58 ET  NVDA 1/2 out
10:02 ET  NVDA 1/4 left
10:02 ET  160%
10:06 ET  NVDA 205c roll
13:22 ET  NVDA 207.5c 3/4
13:22 ET  stops entries
13:23 ET  202.5c 1/10th left
13:23 ET  1000%
```

### Acciones — `📈equity-ideas-alerts`, 2026-08-03

```
13:30 ET  WDC Long idea
13:30 ET  529.56
13:30 ET  stops at 510
```

### Índice — `🤖spx-idea-alerts`, plan de la mañana, 2026-08-03 09:22 ET

> «$SPY 751.52 is the pivot to the upside today imo. This level holds, room higher into the
> 753.87 res, breaks we see the 755.96 tested. Pivot unable to hold, room lower into the
> 748.85 support, that breaks 745.58 to be tested. Leaning bullish neutral.»
> — SpartanTrading, `🤖spx-idea-alerts`, 2026-08-03

### Cierre del día

```
15:50 ET  Ideas I like o/n RDDT NBIS AAOI TSLA        (equity)
15:52 ET  ideas I like o/n CRML CRWD CSIQ             (options)
```

### La gramática, tal y como ellos la documentan

De `⭐new-to-chat-information⭐` (2019-05-16) y `📌info-and-definitions` (2018-10-03), citas
cortas con atribución:

| token | significado (suyo) |
|---|---|
| `38c` / `38p` | strike 38, call / put |
| `.22` | precio del contrato **en el momento de la idea** |
| `dpm .3` | *"Do not Pay more then .3"* — **techo de entrada anti-persecución** |
| `stops at 132` | stop de la idea de acciones (stop market) |
| `Trgt 140` | objetivo = siguiente resistencia, "no significa que llegue" |
| `1/2 out`, `1/4 left`, `1/10th left` | escalonado de salida |
| `stops entries` | **mover el stop a la entrada** (posición gratis) |
| `roll` | cerrar y comprar strike más alto/bajo del mismo nombre |
| `Lotto` | *"Options that expire that day and are usually out of the money, Risk to Zero"* = **0DTE** |
| `Weekly` | vencimiento de esta semana |
| `ww` | *worth watching* — poner el gráfico en pantalla, aún no es señal |
| `Pivot` | soporte/resistencia del diario que dicta la dirección intradía al cruzarse |

**La pieza de ingeniería que sí vale oro:** el vencimiento **no está en la alerta**, está en
la GUÍA. Regla suya, textual: *"IF no Date Stated Contract is Weekly"* y *"Always Front
Contract Expiration Date"*. Convención en el documento → 3 caracteres menos por alerta.
Es exactamente lo contrario de nuestro instinto de meter todo el contexto en cada línea.

---

## 3. Cadencia — MEDIDA, lunes 2026-08-03 (día con carga completa)

### 3.1 Los tres canales de alerta

| canal | mensajes | **IDEAS nuevas** | mensajes de gestión | 1er msg | último |
|---|--:|--:|--:|---|---|
| `📅options-ideas-alerts` | 93 | **11** | 15 | 09:18 | 15:52 |
| `📈equity-ideas-alerts` | 36 | **7** | 8 | 10:40 | 15:50 |
| `🤖spx-idea-alerts` | 27 | **1** (+2 sin la palabra "idea") | 8 | 09:18 | 15:17 |
| **total alertas** | **156** | **19** | **31** | | |

**19 ideas nuevas en toda la sesión.** El resto de los 156 mensajes son las líneas de precio
y `dpm` que acompañan a cada idea (3 mensajes por idea) y la gestión de las posiciones vivas.
Servidor entero ese día, sumando los 29 canales crawleados: **197 mensajes**.

Contraste con nosotros, del backtest de esta madrugada
(`docs/BACKTEST-ALERTAS-FLOTA-2026-08-04.md`): la flota emitió **390 alertas de ticker el
2026-08-03**, 642 líneas de feed. Es decir:

> **Nosotros emitimos 20,5 veces más alertas de ticker que la sala de pago que estudiamos
> (390 vs 19), y ninguna de nuestras familias pasa BH-FDR.** Ellos no publican más porque
> encuentran menos: publican menos porque publicar es caro.

### 3.2 El apagón de media sesión — medido, no impresión

Distribución horaria ET del 2026-08-03:

| canal | 09 | 10 | **11** | **12** | 13 | 14 | 15 |
|---|--:|--:|--:|--:|--:|--:|--:|
| options | 40 | 23 | **0** | **0** | 21 | 3 | 6 |
| equity | 0 | 5 | **0** | **0** | 14 | 13 | 4 |
| spx | 19 | 2 | **0** | **0** | 3 | 0 | 3 |

**Cero mensajes entre las 11:00 y las 12:59 ET en los tres canales a la vez.** No es un hueco
de carga: el scroll trajo ambos lados del hueco en la misma ventana contigua. Es la
**picadora de nuestra regla 7** ("11:30-14:00 picadora"), confirmada de forma independiente
por una sala de pago que se juega su suscripción. Nuestra flota, en cambio, publica esas dos
horas exactamente igual que el resto.

### 3.3 Cadencia de los demás canales (suelo medido)

| canal | msgs/día publicado | cuándo (ET) |
|---|--:|---|
| `⏰premarket-on-watch` | **13,0** (23 sesiones, rango 12-16) | 08:54 → 09:29, siempre |
| `💻daily-recap` (el recap en sí) | **1** | 15:49-16:15 (49 de 95 a las 16h, 43 a las 15h) |
| `📕side-charts` | 2 (idea + el "qué es esto") | 15:45-16:09 |
| `❽earnings` | 2 (AMC hoy + BMO mañana) | 13:46-14:14 |
| `🧠free-resources` | 1 (gráfico de psicología) | 14:38-20:57 |
| `📢announcements📢` | 1,1 (marketing de mentoría, se repite en bucle) | variable |
| `💸completed-trades` | 6,3 (lo publican los MIEMBROS, no los mods) | todo el día |

---

## 4. Cómo estructuran el DÍA — comparado con nuestro cron

| hora ET | Spartan (medido) | nuestro cron | veredicto |
|---|---|---|---|
| 04:00 | — | `dailyplans` FULL → 26 PDFs | nuestro, no tienen equivalente |
| 08:30 | — | `dailyplans` REFRESH | |
| **08:54-09:29** | **`premarket-on-watch`: gráficos primero, luego ~13 párrafos de plan, 1 por ticker** | 09:12 APERTURA + 09:20 premarket | **ellos empiezan 18-38 min antes y reparten en 35 min, no en un golpe** |
| 09:18-09:22 | disclaimer del día + plan de SPY en `spx-idea-alerts` | — | copiar el plan de índice a hora fija |
| 09:30-09:45 | **publican** (40 msgs a las 09h en options) | — | ⚠ contradice nuestra regla 7 |
| 09:45-10:59 | pico de gestión (23 msgs) | | |
| **11:00-12:59** | **SILENCIO TOTAL** | flota publica igual | **lección dura** |
| 13:00-15:00 | segunda tanda de ideas (equity sobre todo: 27 de sus 36 msgs) | | |
| 13:46-14:14 | `earnings`: AMC de hoy + BMO de mañana | 16:20 EOD | ellos avisan del catalizador ANTES del cierre |
| 15:17-15:52 | *"stops entries"* general + lista `Ideas I like o/n` | | |
| 15:45-16:09 | `side-charts` mañana + `daily-recap` | 16:20 postmortem / 16:25 postmarket | **ellos cierran antes de la campana, nosotros después** |

**Las dos diferencias que importan:**
1. **La víspera se publica ANTES del cierre (15:45-16:09), no después.** Da tiempo al miembro
   a cargar las alertas en su plataforma con el mercado aún abierto. Nuestro `postmortem`
   16:20 y `postmarket` 16:25 llegan cuando ya nadie puede armar nada.
2. **El premarket se REPARTE en 35 minutos** (08:54→09:29, ~13 mensajes), no se vuelca de
   golpe. Un muro de 26 PDFs a las 04:00 no se lee; 13 párrafos goteando durante la media hora
   previa a la campana, sí. Esto es **inferencia sobre el porqué**; lo medido es solo el
   reparto temporal.

---

## 5. Sus PLANES: una plantilla de 6 huecos, sin excepción

`⏰premarket-on-watch`, mismo esqueleto para cada ticker, 23 sesiones seguidas sin variar:

```
{TICKER} {PIVOT} is the pivot to the {upside|downside} today imo.
This level holds, room higher into the {RES1} res, breaks we see the {RES2} tested.
Pivot unable to hold, room lower into the {SUP1} support, breaks we see the {SUP2} tested.
Leaning {bullish neutral | ... }
```

Ejemplos íntegros (`⏰premarket-on-watch`, 2026-08-03 09:18-09:21 ET):

> «TSLA 311.17 is the pivot to the upside today imo. This level holds, room higher into the
> 314.86 res, breaks we see the 317.73 tested. Pivot unable to hold, room lower into the
> 304.45 support, breaks we see the 297.34 tested. Leaning bullish neutral»

> «MU 797.78 is the pivot to the **downside** today imo. […] Leaning bullish neutral
> **only if pivot reclaims**»

Y la víspera, `📕side-charts` (2026-07-28 y 2026-08-03, ~15:45 ET):

> «$LULU Curling off the lows w/ room for continuation IF we can break and hold above the
> 124.27 res level imo. **Alert: Bid>124.27  Options Note: 130-140 weekly calls**»

### Lo que hay que robar de aquí

1. **Un pivote y CUATRO niveles, nada más.** Un solo número decide el signo del día; dos
   arriba y dos abajo acotan el recorrido. Es nuestra `print-o-nada-levels` (registro topado
   a 6 tipos por ticker) escrita para un humano.
2. **`Alert: Bid>124.27` es una condición de alerta ejecutable**, copiable a TWS/TradingView
   de un vistazo. Nosotros ya calculamos ese número en `chart_levels` / `gex_core` y **no lo
   publicamos jamás en formato de gatillo**.
3. **La invalidación NO existe como campo.** Está implícita: *"Pivot unable to hold"* es la
   invalidación. Buscado explícitamente en los 2.000+ mensajes: la palabra `invalidat`
   aparece **0 veces**. En opciones la invalidación es un stop de **premium** (−50 %), no de
   precio del subyacente.
4. **`Leaning bullish neutral` es un sesgo declarado, sin probabilidad.** Ni una sola cifra de
   probabilidad en ninguna alerta. Nosotros publicamos `prob 76 %` en cada `🧲 ESTRUCTURAL`
   — 179 veces el 08-03 — y el backtest dice que esas probabilidades no sobreviven BH-FDR.

---

## 6. Track record: cómo lo estructuran, y por qué NO es auditable

`💻daily-recap`, un mensaje entre 15:49 y 16:15 ET, 95 encontrados desde marzo:

> «Equity Idea Highlights Today: $DFNS Long 22pts $NBIS Long 21pts $AAOI Long 16pts […]
> Options Idea Highlights Today: $META 590c 1614% $NVDA 202.5c 1057% $SPX 7545c 963%
> $SPX 7560c 742% $NVDA 207.5c 294% $SPX 7595c 228%»
> — `💻daily-recap`, 2026-08-03 15:55 ET

Los viernes cambia de formato: `#lottofriday Ideas so far Today: 83% Win ratio` + ~28
contratos con su % + una línea **`Failed: MU 900 SNDK SPX 7505c MU 810p MU 890c SPX`**.

### Pasado por la killlist — tres defectos medidos

| defecto | evidencia |
|---|---|
| **Supervivencia.** El recap se llama *"Highlights"*. El 2026-08-03 publicaron **14 ideas de opciones** en `options`+`spx` (11 con la palabra "idea" + `SPX 7545c` y `7560c`) y el recap nombra **6 (43 %)**. De las otras 8 (SMCI 31c, GOOGL 380c, NFLX 77c, INTC 90c, ADBE 290c, CSIQ 16.5c, AMD 500c, TSLA 325c, MU 840c) el recap no dice nada. | conteo directo sobre `options`/`spx` 08-03 vs recap 15:55 |
| **El % no se reconstruye.** `SPX 7595c`: idea 13:25 a **4,7** (`dpm 4,9`), salida publicada 15:17 *"3/4 out / 12.88"* → **+174 %** (o +163 % pagando el dpm). El recap dice **228 %**. No hay ningún mensaje en el canal que produzca 228 %. | `spx-idea-alerts` 2026-08-03 13:25 y 15:17 vs `daily-recap` 15:55 |
| **El "83 % win ratio" no tiene denominador.** Se publica el ratio y la lista de ganadores; `Failed:` da 6 nombres sin %. Sin n, sin muestra efectiva y sin corrección por correlación (nuestra `ρ̄` medida es 0,32), ese número no es una probabilidad, es marketing. | `daily-recap` 2026-07-31 |

**Conclusión operativa:** su formato de recap es **excelente como envoltorio** (una línea por
idea: `$TICKER STRIKE %`) y **inaceptable como método** (solo ganadores, % no verificable).
Se copia el envoltorio; el contenido lo pone nuestro `eod_signal_validation` /
`barrier_labels`, que sí etiqueta con triple barrera y sí cuenta los perdedores.

---

## 7. Arquitectura, roles y separación gratis/premium

| observado | detalle |
|---|---|
| **permisos** | 22 de 29 canales marcados `Text (Limited)` por Discord = lectura sí, escritura no para esta cuenta. Los 7 abiertos son los sociales/marketing (`disclaimer`, `announcements`, `completed-trades`, `daily-recap`, `webinars`, `affiliate-deals`, `free-resources`). |
| **premium** | **NO hay canales premium separados** dentro del guild. Todo el guild ES el producto de pago; el gratis vive fuera (web, X, webinars). El upsell se hace DENTRO de los canales: el pie de cada `daily-recap` lleva cupones (`50% off Weekly: IDEA50`) y `📞spartan-call-schedule` es un Calendly repetido 12 veces. |
| **roles** | no enumerables sin permisos. Visibles por mención: `SpartanTrading [SPTN]` (head mod), `mommas delta options 👀` (options mod), `Lorenzo` (ventas), `Sunset`, y una etiqueta de servidor `SPTN`. `📌info-and-definitions` lista **8 mods con especialidad declarada** (técnico, macro, opciones, biotech, breakouts, scalping, rotación, largo plazo). |
| **hilos / foros / eventos** | **cero**. `thread=false` en los 2.000+ mensajes; ningún canal de tipo foro; ningún evento programado visible. |
| **reacciones** | abundantes en los mensajes de doctrina (141, 150, 78, 43…) y **cero en las alertas**. No hay roles por reacción. |
| **moderación** | dos avisos fijados: (a) republicar sus trades = expulsión, con **recompensa de un mes gratis** al que lo denuncie (2020-07-28, 2025-06-10); (b) anti-suplantación — *"We do not have copy trading, we will never reach out first"* (2025-12-31). |
| **notificaciones** | instrucción explícita al nuevo: **silenciar `📍live-chat-questions` y dejar notificaciones SOLO en `equity-ideas-alerts` y `options-ideas-alerts`** (2020-03-29). El propio servidor reconoce que su charla es ruido. |

---

## 8. Tecnología, fuentes y bots que se les ven

| herramienta | dónde se vio | para qué | ¿la tenemos? |
|---|---|---|---|
| **Interactive Brokers + DAS Trader** como front-end de ejecución | `💻tech-and-software` 2026-06-19: *"IMO interactive and connect it DAS trade for execution front end"* | ejecución de day trading | IBKR sí; DAS no (ni falta: nuestro `order_engine` es el front-end) |
| **TradingView** | `🧠free-resources` 2026-07-27 (paso 6 de su ruta de aprendizaje) | gráficos | sí (skill `tradingview-terminal`) |
| **SP FLOW BOT** (bot verificado) | `🤖bot-talk`, 12 msgs en 44 min el 2026-08-04 | **cinta de titulares macro con marca de tiempo**: bancos centrales, aranceles, datos macro, resultados. Ej. *"02:45 - FRENCH BUDGET BALANCE ACTUAL -106.773B"* | **NO.** Ver §10, es el hallazgo de fuente más valioso |
| flujo de barridos, cantado a mano por la mod de opciones | `📅options-ideas-alerts` 2026-08-03 10:41: *"AMZN $13.2mln sweep CRWv 421mln"* | contexto de flujo | sí — `opt_whale_watch` + `flujo-uw` |
| **Seeking Alpha @MarketCurrents** vía integración de X | `📩news-wire` (última actividad 2025-06) | dividendos/distribuciones de ETFs | no, y no hace falta |
| calculadora de riesgo/recompensa en **.xlsx** + vídeo | `⚖risk-reward-archives` 2020-09-17 | dimensionamiento | equivalente propio: `order_ticket` (presupuesto ≤ $200) |
| Calendly, cupones, programa de afiliados | `📞spartan-call-schedule`, `🤝affiliate-deals` | venta | fuera de alcance |

**Lo que NO usan y podría esperarse:** ni una mención de GEX, gamma flip, max pain, muros de
OI, dark pool ni Unusual Whales en 2.000+ mensajes. Su mapa es **pivote + soporte/resistencia
del diario + volumen relativo**. Toda nuestra maquinaria de estructura de opciones
(`gex_core`, `chart_levels`, `pin-and-expiry-mechanics`) **no tiene equivalente ahí** — o es
nuestra ventaja real, o es sobreingeniería que ellos ya descartaron. El backtest de hoy
(179 `🧲 ESTRUCTURAL pin` el 08-03, ninguna familia pasa BH-FDR) apunta más a lo segundo de
lo que nos gustaría.

---

## 9. Lo que NO se pudo ver — explícito

- **Roles y overwrites de permisos**: no enumerables sin la API con permisos de gestión.
- **`deal-flow-private-placement`**: citado en su propio índice, ausente de la barra lateral
  → canal privado al que esta cuenta no tiene acceso.
- **Historial anterior a la ventana de scroll** en los 22 canales de baja frecuencia. Los
  msgs/día de §3.3 son suelos.
- **Latencia real de su publicación** frente al print: no medible sin cinta sincronizada.
- **Si hay más canales ocultos por rol**: por construcción, invisibles.

---

## 10. BOTÍN APROVECHABLE — ordenado por valor/coste

Todo con canal + fecha. `[INF]` = inferencia, no observación.

| # | hallazgo | dónde lo vimos | cómo lo usaríamos en ib-trader | coste |
|--:|---|---|---|---|
| 1 | **Apagón 11:00-12:59 ET.** Cero mensajes en los 3 canales de alerta a la vez. | `options`/`equity`/`spx`, 2026-08-03 | Ventana de mudez en el relé: en 11:00-12:59 solo pasa `criticas`. Ataca directo el problema medido de exceso (390 alertas/día). Toca `discord_router.py`, no `discord_layout.py`. | 1 función horaria |
| 2 | **19 ideas/día es el techo de una sala de pago.** | conteo 2026-08-03 | Cupo duro diario por canal de alerta, y el excedente a `senales-rechazadas` (que ya existe, es privado y está para auditar el ruido). El cupo NO se inventa: se fija en el percentil del backtest. | 1 contador + persistencia |
| 3 | **El vencimiento vive en la GUÍA, no en la alerta** (*"IF no Date Stated Contract is Weekly"*). | `new-to-chat`, 2019-05-16 | Nuestra `guia-alertas` es autogenerada: que declare la convención (0DTE por defecto en flota, presupuesto ≤$200, spread ≤5 %) y las alertas dejen de repetirla. Menos caracteres, misma información. | texto en el generador |
| 4 | **`Alert: Bid>124.27` — gatillo copiable la víspera.** | `side-charts`, 2026-07-28 / 08-03 15:45 ET | `estrategias` (canal existente, hoy sin productor claro) publica a las **15:45**, no a las 16:25, las condiciones `Bid>X` del día siguiente desde `chart_levels`/`gex_core`. Es nuestra regla 10 ("fichas preparadas la víspera") sin implementar. | productor nuevo, ~80 líneas |
| 5 | **Plantilla de plan de 6 huecos** (pivote + 2 res + 2 sop + sesgo). | `premarket-on-watch`, 23 sesiones | Los 26 PDFs de las 04:00 no se leen en Discord. Publicar en `planes-premarket` **una línea de 6 huecos por ticker**, goteando 08:54→09:29, y el PDF como adjunto para quien lo quiera. | plantilla sobre datos ya calculados |
| 6 | **`dpm` = techo de entrada anti-persecución.** | `info-and-definitions`, 2018-10-03 | `order_ticket.py` ya calcula el límite marketable; **falta publicar el techo**. Añadir `dpm $X` al string del ticket = anti-FOMO explícito, coherente con la regla 2 (print o nada). | 1 línea en `order_ticket.py:134` |
| 7 | **Recap de una línea por idea: `$TICKER STRIKE %`.** | `daily-recap`, 95 recaps | Formato de `cierre-recap`. **Con el arreglo de la killlist: TODAS las ideas, no los "highlights", y el % de `barrier_labels` con triple barrera.** Sin eso, copiamos su marketing. | formateador sobre datos existentes |
| 8 | **Cinta de titulares macro con marca de tiempo** (SP FLOW BOT). | `bot-talk`, 2026-08-04 02:25-03:04 | **La fuente que no tenemos.** Nuestro `calendario-economico` está vacío de productor. Advertencia de killlist: es **contexto, jamás gatillo** — mismo estatus que `dark-pool`. Y hay que medir su latencia antes de fiarse (precedente Unusual Whales). | evaluar proveedor; NO construir todavía |
| 9 | **`stops entries` — mover el stop a la entrada tras la primera toma.** | `options`, 4 veces el 2026-08-03 | Estado explícito en `data/pos_*.txt` (ya existe el campo `FLOOR`) y una sola línea al publicarlo. Convierte la gestión en 2 palabras. | etiqueta en el emisor |
| 10 | **Cierre del día = lista de nombres, no párrafo** (`Ideas I like o/n …`). | `options`/`equity`, 15:50-15:52 | Un mensaje de cierre en `cierre-recap` con los símbolos que siguen vivos. | trivial |
| 11 | **Instrucción de notificaciones al nuevo**: silenciar la charla, notificar SOLO 2 canales. | `new-to-chat`, 2020-03-29 | En `bienvenida`: decir qué canales notificar (`criticas`, `opciones-contratos`) y cuáles silenciar. Nuestro problema es de volumen; esto lo mitiga sin borrar nada. | texto |
| 12 | **Cero embeds en alertas.** | 204 msgs medidos | Nuestro relé usa embeds con color por severidad. **Mantenerlos**: el color codifica severidad y nosotros sí tenemos taxonomía. Pero **cero adjuntos y cero imágenes en los canales de alerta**: los gráficos van a `analisis`. | regla en el router |
| 13 | Mods con especialidad declarada (8, con su área). | `info-and-definitions` | Nuestro equivalente son los MOTORES. `guia-alertas` debería listar los productores con su especialidad y su tasa medida. | texto autogenerado |

### Descartado a propósito (infla el servidor sin productor detrás)

| idea suya | por qué NO |
|---|---|
| `📍live-chat-questions`, `💹charts`, `📐support-resistance-levels`, `💸completed-trades` | Son canales de COMUNIDAD humana. Sin comunidad, canal muerto. Nuestra ley: canal sin productor real no existe. |
| `🪙crypto-and-sports-betting` | Fuera del mandato (detectamos movimientos de equity/opciones). |
| `📢announcements📢`, `📞spartan-call-schedule`, `🤝affiliate-deals`, `🎓webinars` | Marketing. No tenemos producto que vender. |
| `🧠free-resources` (1 gráfico de psicología/día) | Ruido con envoltorio bonito. Cero productor. |
| `#lottofriday` como evento semanal | Un día dedicado a 0DTE OTM "risk to zero" es **exactamente** la regla 5 rota ("no 0DTE comprado en zona de pin") y el sesgo de supervivencia de §6. **NO se copia.** |
| Su "83 % win ratio" y las % del recap | Sin denominador, sin muestra efectiva, sin corrección por correlación. Es el mismo defecto por el que matamos el `score N/6` del screener Finviz. |
| Publicar en la ventana 09:30-09:45 | Ellos lo hacen (40 msgs a las 09h); nuestra regla 7 lo prohíbe. Su práctica **no valida** nuestra excepción: no hay medición detrás de la suya. |

---

## 11. ALERTAS DE OPCIONES SEPARADAS — respuesta a la orden de Yunior 2026-08-04

> *"make sure we have options alerts separately, take a look at spartan for reference"*

### 11.1 Cómo lo separa Spartan

**Por VEHÍCULO y por TAMAÑO DE CUENTA, nunca por horizonte.** Los 4 canales operables, todos
en la categoría `Mod Alerts & Charts`:

| canal | qué publica | según su propio índice (`new-to-chat`, 2019-02-01) |
|---|---|---|
| `📅options-ideas-alerts` | opciones sobre acciones/ETF | *"Options traders channel… Max stops are always 50% on starter positions. IF no Date Stated Contract is Weekly"* |
| `📈equity-ideas-alerts` | acciones | *"Stops are posted, use them"* |
| `🤖spx-idea-alerts` | **solo índice**: SPX y SPY | *"SPX and SPY Ideas Posted here"* |
| `✍high-conviction-small-account` | **1-2 ideas/día, cuenta pequeña** (medido: QQQ 704c/709c/690c/698c) | *"1-2 Trades a day, higher conviction or small account related… Credit Spreads Also Posted in Here"* |

**No** hay canal de swing, ni de LEAPS, ni de 0DTE. El horizonte se marca **dentro** del
mensaje (`scalp idea`, `Ideas I like o/n`) o por la convención de la guía.

### 11.2 Formato exacto — 5 ejemplos textuales

```
ADBE 290c idea / .72 / dpm 1                      (options,  09:56 ET 08-03)
TSLA 325c idea / .27 / dpm .3                     (options,  13:41 ET 08-03)
CSIQ 16.5c idea / 17.5c ** / .25 / dpm .3         (options,  10:29 ET 08-03)
SPX 7545c / 6 / dpm 6.5                           (spx,      09:33 ET 08-03)
QQQ 690c / 1.38 / dpm 1.45                        (small-acc, 11:34 ET 07-23)
```

Campos: **ticker · strike+lado · precio actual · techo de entrada.** Y nada más.
**No hay** vencimiento (convención de la guía), **no hay** objetivo, **no hay** invalidación
de precio, **no hay** probabilidad, **no hay** spread, **no hay** OI, **no hay** tamaño.
El stop está en la guía: **−50 % del premium en posición inicial**.

### 11.3 ¿Publican el cierre? Sí — como mensajes nuevos, no editando

**Nunca editan el original** (1 edición en 204 mensajes). Cada movimiento es un mensaje nuevo:
`1/2 out` → `stops entries` → `1/4 left` → `1/8th left` → `1000%`. La cadena completa del
NVDA del 08-03 está en §2.

**¿Es auditable?** Parcialmente, y esa es la respuesta honesta:
- ✅ Se reconstruye **la secuencia**: entrada, escalones y % final publicado.
- ❌ **No se reconstruye el resultado** de todas: el `daily-recap` nombra 6 de 14 ideas de
  opciones del 08-03 y el % que publica de `SPX 7595c` (228 %) no cuadra con lo que el propio
  canal publicó (4,7 → 12,88 = +174 %). Detalle y evidencia en §6.
- ❌ El ancla es el **primer** escalón: `1000 %` es el 1/10 final, no el retorno de la
  posición. Sin el peso de cada escalón el % es incomparable con un backtest de barrera.

**Lo copiable es la MECÁNICA** (mensaje nuevo por evento, jamás editar → historial inmutable),
no la contabilidad.

### 11.4 Cadencia de opciones — el número

**14 ideas de opciones el 2026-08-03** (11 en `options` + 3 en `spx`), en 93+27 = 120 mensajes.
Media de **~3 mensajes por idea** al abrir y **~2,3 de gestión** por idea después.
`high-conviction-small-account`: **1-2 ideas/día declaradas**, y medido 7,2 msgs/día en 5 días.

### 11.5 ¿Distinguen 0DTE? Sí, pero no lo llaman así

La cadena `0dte` aparece **1 vez en 2.000+ mensajes**. Su palabra es **`Lotto`**:

> «Lotto = Options that expire that day and are usually out of the money, Risk to Zero»
> — `📌info-and-definitions`, 2020-04-09

Y las reglas asociadas, textuales de esa misma ficha y de `Spartans Options Rules`:
- *"If your risk is $200 per trade you only max buy $200 worth of contracts. Meaning no Stops"*
  → **el mismo presupuesto de $200 que la casa**, y con la lógica correcta: si no hay stop, el
  premium ES el stop.
- *"MAAG 7 Will always be Weekly Unless its Friday OR STATED Lotto which will = 0dte"*
  → 0DTE es la **excepción declarada**, no el estado por defecto.
- *"If not Experienced, Have a Small Account or a not Profitable Trading Options You do not
  Trade Lottos, Trade Next Weeks Expiration!"*
- *"Anyone with a small account -> less than 10k IMO STOP PLAYING LOTTOS. Cheap contracts =
  lower probability of working that is why they are cheap."*
- *"last hour you can treat as lotto"* (regla de SPX)

**No tienen canal 0DTE.** El 0DTE es un ESTADO del contrato, marcado en el mensaje.
Recomendación derivada: **no crear un canal `0dte`** — sería un canal por atributo, no por
productor, y duplicaría el flujo de `opciones-contratos`.

### 11.6 Propuesta concreta para `discord_layout.py`

Estado verificado hoy: **`opciones-contratos` YA EXISTE** en `discord_layout.py` (categoría
`alertas-vivo`) con la regla
`(r"OPCIONES (OK|VETADAS|s/d)|\bNO-GO\b|\bCAUTION\b|sin cadena — no puedo armar ficha", "opciones-contratos", NORMAL)`
colocada **antes** de `🐋|BALLENA` (si no, `🐋 BALLENA CALLS` se llevaría las fichas por el
"CALLS"). Verificado ejecutando `discord_layout.classify()` sobre la línea real que compone
`today_alarm5.py:100-104`:

```
10:15:03 | 🟢 NVDA CALL BOUNCE | NVDA BOUNCE en muro 210 — 🟢 COMPRA 1x NVDA 210c 0DTE
@ límite $1.85 (prima $185, spread 3%, OI 4200, prob 61%) — GO. Ejecuta TÚ en IBKR.
| OPCIONES OK (spread 1%)
   → ('opciones-contratos', 'normal')   espejo: ['semis-memoria']    ✅
```

**El productor es real y ya emite al embudo:**
- `scripts/order_ticket.py:128-137` → contrato + strike + `0DTE` + límite + prima + spread% +
  OI + prob + veredicto `GO/CAUTION/NO-GO`.
- `scripts/today_alarm5.py:99-104` lo compone con `optgate.opt_vehicle()` (gate del 5 %,
  regla 4) y `scripts/notify_short.py:33` lo escribe en `data/notify_push.txt` — que es
  justo lo que lee el relé.
- Segundo consumidor vivo: `scripts/chart_bridge.py:2318`.

Gates ya dentro del productor, sin tocar nada: **≤ $200** (`order_ticket.py:27`),
**spread ≤ 5 % sobre MID** y **OI ≥ 500**.

#### Lo que falta (3 huecos verificados, ninguno resuelto)

| # | hueco | evidencia | arreglo propuesto |
|--:|---|---|---|
| A | **Solo 5 símbolos.** `today_alarm5.py` vigila una lista fija de Yunior (NVDA, AAPL, MU, DRAM, SKHY), no `data/fleet.txt`. El canal se alimentará de 5 de 30. | `today_alarm5.py` docstring y `SYMS` | decisión de Yunior, no de diseño. Documentado, no tocado. |
| B | **El canal recibe también los NO-GO.** La regla casa `OPCIONES VETADAS` y `NO-GO`. Un canal de contratos operables lleno de vetos es ruido — y el ruido es el problema medido de la casa. | `discord_layout.py` RULES + prueba de arriba | enrutar `NO-GO`/`VETADAS` a `senales-rechazadas` (privado, ya existe, ya es el sitio donde se audita el filtro) y dejar en `opciones-contratos` solo `GO` y `CAUTION`. **1 regla más, antes de la actual.** |
| C | **`dpm` no existe.** Publicamos el límite pero no el techo anti-persecución. | `order_ticket.py:134` | añadir `dpm $X` al string del ticket (botín #6). |

#### Canales de opciones: qué se crea y qué NO

| canal propuesto | ¿se crea? | productor real | razón |
|---|---|---|---|
| `opciones-contratos` | **YA EXISTE — se conserva** | `order_ticket.build()` vía `today_alarm5.py` + `chart_bridge.py` | único canal de la casa con un contrato ejecutable. Es el hueco que `ballenas-flujo`/`flujo-uw`/`gamma-niveles`/`dark-pool` no cubren: esos son flujo y contexto, ninguno emite un contrato. |
| `opciones-0dte` | **NO** | — | 0DTE es un atributo del contrato, no un productor. Spartan tampoco lo separa (§11.5). Duplicaría el flujo y rompería "una tesis = un boleto". |
| `opciones-swing` / `leaps` | **NO** | **no existe productor**: `order_ticket.py:76` solo mira la expiry más próxima y devuelve `NO-GO` si no hay 0DTE. Canal sin productor no existe. | |
| `spx-xsp` (a lo `🤖spx-idea-alerts`) | **NO — usar el espejo que ya existe** | `MIRRORS` ya define `SPY_QQQ = (SPY, QQQ, SPX, XSP, NDX, DIA, IWM)` → `#spy-qqq` | el índice ya tiene canal-espejo. Uno nuevo sería el tercer sitio donde aparece la misma alerta. |
| `alta-conviccion` (a lo `high-conviction-small-account`) | **NO por ahora** | `#confluencia` ya es exactamente eso: "dos motores de acuerdo, lo más selectivo". | crear otro sería partir en dos la señal más escasa que tenemos. |

**Resumen de la propuesta: cero canales nuevos, tres arreglos.** (B) sacar los NO-GO a
`senales-rechazadas`, (C) publicar `dpm`, y (A) decidir si `today_alarm5` pasa de 5 símbolos
a la flota. La separación que pide Yunior **ya está estructuralmente hecha**; lo que falta es
que el canal no se llene de vetos.

---

## 12. Multi-idioma (español ahora, inglés después)

Esta sección no dependía del servidor ajeno; se conserva íntegra y se **amplía** al final con
lo observado.

### El coste oculto que YA teníamos (y que ya está arreglado)

Tanto el creador de estructura como el de webhooks buscaban el canal **por su NOMBRE
VISIBLE**. Consecuencia: renombrar `criticas` → `critical` habría creado un canal nuevo vacío,
dejado el viejo huérfano con el historial, y el webhook habría seguido publicando en el viejo.

**Estado 2026-08-04: RESUELTO.** `discord_layout.py` ya trae `load_ids()` / `save_ids()` /
`resolve(key, chans, ids)` con caché `data/discord_channels.json` y casado **por ID primero,
por nombre después**. El propio docstring de `resolve()` documenta el precedente. El paso 2 de
la recomendación original está hecho.

### Opciones

| opción | qué es | coste | veredicto |
|---|---|---|---|
| **A. Canales duplicados por idioma** (`criticas` + `critical`) | cada alerta se publica 2 veces | duplica canales (12 → 24), duplica webhooks, **duplica el rate-limit del relé** y obliga a traducir en el camino de señal (latencia = dinero). Una alerta traducida por LLM es una alerta con riesgo de mentir | **NO** |
| **B. Servidor inglés aparte** | otro guild | `discord_client.py` asume UN `DISCORD_GUILD_ID`; habría que parametrizarlo todo + segundo set de webhooks + doble mantenimiento | **NO por ahora** — solo si hay audiencia inglesa de pago |
| **C. Un solo árbol, idioma como capa de presentación** | los canales son los mismos; cambia el nombre visible, el topic y los estáticos | 1 cambio en `discord_layout.py` + 1 línea por consumidor | **SÍ** |

### C, concreto (qué falta tocar en `scripts/discord_layout.py`)

1. **Separar CLAVE de NOMBRE VISIBLE.** Hoy la clave ES el nombre. Añadir:
   ```
   LANG   = os.environ.get("IBT_DISCORD_LANG", "es")
   NAMES  = {"criticas": {"es": "criticas", "en": "critical"}, ...}
   TOPICS = {"criticas": {"es": "🚨 DANGER · …", "en": "…"}, ...}
   ```
   más `channel_name(key, lang)` / `channel_topic(key, lang)`.
2. ~~Casar por ID~~ **HECHO** — `resolve()` + `data/discord_channels.json`.
3. **Rol de idioma, no canales**: a `ROLES` → `("EN", 0x?, False, "interfaz en inglés")`.
   Discord no traduce nombres de canal por rol; el rol sirve para menciones separadas y para
   qué versión de los ESTÁTICOS ve cada uno.
4. **Solo se duplican los estáticos.** Como mucho `bienvenida-en` y `guia-alertas-en`, y solo
   cuando exista el productor (`guia-alertas` es autogenerada: su generador emitiría las dos).
   **Los canales de `🚨 ALERTAS EN VIVO` NO se duplican jamás.**
5. **El texto de la alerta se queda en español.** Es texto de máquina, corto y con
   emoji-código. Traducirlo en vivo mete latencia y riesgo en el camino de señal.

### Lo que Spartan añade a esta decisión (observado)

- **Su alerta es prácticamente idioma-neutra ya**: `ADBE 290c idea / .72 / dpm 1` no tiene ni
  un verbo. La única palabra traducible es `idea`. **Eso valida la opción C por la vía dura**:
  cuanto más corta la alerta, menos idioma hay que traducir. Nuestro
  `🟢 COMPRA 1x NVDA 210c 0DTE @ límite $1.85 … Ejecuta TÚ en IBKR` tiene 6 palabras
  traducibles de más.
- **Toda su carga de idioma está en los estáticos**: `info-and-definitions`, `new-to-chat`,
  `free-resources`. Es exactamente el reparto que propone C (traducir la guía, no la línea).
- **Tienen miembros hispanohablantes activos** (`Mauricio 🇲🇽`, `💸completed-trades`, 8 mensajes
  entre 07-09 y 08-03) y **cero adaptación de idioma**: el servidor es 100 % inglés y ellos
  escriben en inglés. `[INF]` Sugiere que un solo idioma con vocabulario mínimo aguanta una
  audiencia mixta sin bifurcar el servidor — que es el argumento de coste a favor de C.
- **Su glosario de 40 términos** (`info-and-definitions`) es el artefacto que habría que
  traducir primero: es lo que hace legible la alerta corta. Nuestro equivalente es
  `guia-alertas`, y hoy no existe una versión inglesa porque no existe el generador bilingüe.

**Coste de dejarlo preparado hoy**: ~30 líneas en `discord_layout.py` (el paso 2, el caro, ya
está hecho). **Coste de no hacerlo**: recrear canales y perder historial — mitigado desde que
`resolve()` casa por ID, pero el trabajo de nombres/topics sigue pendiente.

---

## Reproducir este estudio

```bash
curl -s http://127.0.0.1:9333/json/version          # Chrome headless con perfil copiado
# driver de solo lectura en el scratchpad de la sesión:
#   dsc.py  map|read <url> [scrolls]   -> árbol / mensajes con scroll-back
#   batch.py [canal ...]               -> N canales reusando una pestaña
```
Gotchas: `/json/new` exige PUT en Chrome 150; el scroller de mensajes se alcanza subiendo
desde un `li[id^="chat-messages-"]`, no con `querySelector('div[class*="scroller"]')`;
Discord virtualiza el DOM → acumular por `id` entre scrolls; los `ts` son UTC (ET = UTC−4).
