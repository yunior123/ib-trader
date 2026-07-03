# ¿Cae el Nasdaq drásticamente el mismo día en que Corea se desploma?

**Estudio medido — 2026-08-03, premarket (~07:30 ET). Señal-solamente: nada de aquí dispara una orden.**

Afirmación a verificar (Yunior): *"historic possibility of nasdaq falling drastically today given a fall in kospi, the pattern is quite common, verify"*.
Se entra con escepticismo. El resultado por defecto es "no existe" hasta que los datos digan otra cosa.

Datos: `kospi_nasdaq_estudio.json` · series crudas en `raw/`.

---

## 0. Veredicto en cuatro líneas

| Afirmación | Veredicto | Número |
|---|---|---|
| "Corea cae → el Nasdaq cae el mismo día" | **PARCIALMENTE MEDIDO**, pero mucho más débil de lo que suena | P(NDX rojo) pasa de **45,1%** (base) a **57,3%** con KOSPI ≤ −5%; n=75, n_eff=49 |
| "…drásticamente" | **REFUTADO** | P(NDX cae ≥2%) = **28,0%** con KOSPI ≤ −5%. En 72% de esos días NO hubo caída drástica |
| "…y hoy" (give-back tras rally coreano) | **REFUTADO para el caso de hoy** | Post-rally: P(NDX rojo) **53,8%**, media **−0,33%**, z=0,80 **p=0,21** — indistinguible del azar |
| "el patrón es común" | **INVERTIDO** | corr(NDX[D−1]→KOSPI[D]) = **0,310** vs corr(KOSPI[D]→NDX[D]) = **0,130**. Wall Street arrastra a Seúl más del doble de lo que Seúl arrastra a Wall Street |

**Y el hallazgo operativo que importa hoy:** el daño está en el **HUECO DE APERTURA**, no en la sesión.
Tras KOSPI ≤ −5% el gap medio de QQQ es **−0,90%** y el open→close medio es **+0,62%** (mediana 0,00%,
P(open→close rojo) 46,3% ≈ base 46,9%). **Para las 09:30 ya no queda edge corto**: lo que se iba a
pagar, se pagó en el hueco.

---

## 1. Método (cada decisión declarada)

### 1.1 Fuentes y latencia

| Serie | Ticker | n sesiones | Rango | Latencia |
|---|---|---|---|---|
| KOSPI composite | `^KS11` | 7.295 | 1996-12-12 → 2026-08-03 | EOD. La fila de HOY es el cierre coreano YA consumado (02:30 ET) |
| Nasdaq-100 | `^NDX` | 10.287 | 1985-10-01 → 2026-07-31 | EOD. **La sesión US de hoy NO existe todavía** |
| Nasdaq Composite | `^IXIC` | 13.988 | 1971-02-05 → 2026-07-31 | EOD |
| QQQ (ETF) | `QQQ` | 6.891 | 1999-03-10 → 2026-07-31 | EOD, **Open real de bolsa** |

Fuente única: **yfinance / Yahoo Finance**, barras diarias, `auto_adjust=False`, descargadas 2026-08-03 ~07:00 ET.
No se usó IBKR (prohibido esta semana), ni Polygon (15 min y sin índices coreanos), ni CBOE.

**Series DESCARTADAS y por qué** (no en silencio):
- **`^KS200`**: hueco de datos, salta de 2026-07-16 a 2026-08-03. Serie inutilizable → **no se usa**.
- **`Open` de `^NDX`**: **30,34%** de las sesiones tienen gap exactamente 0 = el Open está replicado del cierre previo. Inservible para medir huecos. Todo el análisis de gap se hace con **QQQ** (1,18% de ceros).

### 1.2 Alineación temporal — lo que hace o rompe el estudio

Corea cierra 15:30 KST = **01:30 ET (EST) / 02:30 ET (EDT)** del **mismo día calendario**, 7-8 h **antes**
de la apertura US (09:30 ET). Por tanto el join correcto es por **fecha de calendario local, sin desplazamiento**:
`KOSPI[D]` es información **ya disponible** cuando arranca la sesión `US[D]`. No hay look-ahead.

> **BUG CAZADO EN ESTE MISMO ESTUDIO (queda documentado porque casi publica un patrón falso).**
> La primera versión parseaba el índice con `pd.to_datetime(..., utc=True)`: `2026-08-03 00:00+09:00` (Seúl)
> → `2026-08-02 15:00 UTC` → `normalize()` → **2026-08-02**. Eso desplazaba **toda** la serie coreana un día
> atrás, y el estudio acababa midiendo **Nasdaq[D] → KOSPI[D+1]**, es decir la causalidad **al revés**.
> Producía un falso "patrón" precioso: P(rojo) **78,2%** con KOSPI ≤ −5%.
> Se detectó porque `corr(NDX[D−1], KOSPI[D])` salía **0,003** cuando el lead conocido de Wall Street sobre
> Seúl exige ~0,3. Tras corregir: 0,310. **Ese es el test de cordura que debe correr cualquiera que repita esto.**

### 1.3 Exclusiones por festivo (explícitas)

| Caso | n días | Motivo |
|---|---|---|
| KOSPI abierto, US cerrado | **226** | 4-Jul, Thanksgiving, Navidad, Labor Day… (últimos: 2026-04-03, 2026-06-19, 2026-07-03) |
| US abierto, KOSPI cerrado | **386** | Seollal, Chuseok, Día de la Fundación, elecciones… (últimos: 2026-05-05, 2026-06-03, 2026-07-17) |

Si una de las dos bolsas no abrió ese día, **el par no existe y se excluye**. Nunca se rellena con 0 ni se arrastra el cierre previo.
**Muestra final: 7.068 sesiones conjuntas, 1996-12-12 → 2026-07-31.**

### 1.4 Muestra efectiva (`n_eff`) y cómo se leen los CI

Los días que califican llegan en **ráfagas** (una crisis = varios días seguidos). Contarlos como
observaciones independientes ensancha falsamente la confianza. Por eso:

```
n_eff = nº de EPISODIOS independientes (grupos separados por >5 sesiones), topado por n
```

Todo Wilson 95% se calcula sobre `n_eff`. Las **bases** usan `n` (el retorno diario del índice no tiene
autocorrelación apreciable). La asimetría es **deliberada y conservadora**: endurece el test del condicional, no lo afloja.
**Umbral de publicación: `n_eff ≥ 30`.** Por debajo se dice "n insuficiente" y se cita el conteo crudo, nunca una probabilidad.

Todos los contrastes son de **una cola** (¿el condicional cae MÁS que su base?) y pasan por **BH-FDR q=0,10**
sobre la familia completa de **64 contrastes**: 39 sobreviven.

---

## 2. Tabla 1 — incondicional: KOSPI[D] ≤ −X% → Nasdaq-100[D]

| Bucket | n | episodios | n_eff | P(rojo) | CI95 (n_eff) | P(≤−1%) | P(≤−2%) | media | **mediana** |
|---|---|---|---|---|---|---|---|---|---|
| **BASE** (todas) | 7.068 | — | 7.068 | **45,12%** | [43,96 – 46,28] | 20,02% | 9,34% | +0,059% | +0,118% |
| KOSPI ≤ −2% | 562 | 239 | 239 | 54,45% | [48,11 – 60,64] | 38,08% | 22,42% | −0,357% | −0,282% |
| KOSPI ≤ −3% | 275 | 141 | 141 | 53,45% | [45,24 – 61,49] | 41,09% | 24,36% | −0,411% | −0,280% |
| KOSPI ≤ −5% | 75 | 49 | 49 | **57,33%** | [43,45 – 70,15] | 48,00% | 28,00% | −0,537% | −0,646% |
| KOSPI ≤ −8% | 13 | 13 | 13 | 53,85% | [29,14 – 76,79] | 46,15% | 38,46% | +0,255% | −0,985% |

**Lectura honesta:** el efecto **existe** pero es pequeño en dirección: +9 a +12 puntos de P(rojo) sobre una
base de 45%. La media del Nasdaq pasa de +0,06% a −0,54%. **Eso no es "caer drásticamente"**: es sesgar
una moneda de 45/55 a 57/43.

### 2.1 Curva de sensibilidad — el test que mata barato

| Umbral KOSPI | −1% | −1,5% | −2% | −2,5% | −3% | −4% | −5% | −6% | −8% |
|---|---|---|---|---|---|---|---|---|---|
| n | 1.292 | 862 | 562 | 391 | 275 | 137 | 75 | 39 | 13 |
| **P(NDX rojo)** | 54,4% | 54,1% | **54,5%** | 53,7% | 53,5% | 59,1% | 57,3% | 61,5% | **53,8%** |
| P(NDX ≤ −1%) | 32,5% | 35,6% | 38,1% | 38,1% | 41,1% | 48,2% | 48,0% | 53,9% | 46,2% |
| media NDX | −0,29% | −0,33% | −0,36% | −0,36% | −0,41% | −0,66% | −0,54% | −0,66% | +0,25% |

**P(rojo) es prácticamente PLANA en 53-61% desde −1% hasta −8%.** No escala con la magnitud del desplome
coreano. Lo que sí escala monótonamente es **P(NDX ≤ −1%)**: 32,5% → 53,9%. Eso ya avisa de qué es
realmente esta señal (§5).

---

## 3. Tabla 2 — condicionado por CAUSA (lo más importante)

Cada celda se contrasta contra **la base de su propio grupo**, no contra la base global.

### A. Corea cae por lo suyo — Wall Street NO cayó la víspera (`NDX[D−1] ≥ 0`)

| Bucket | n | n_eff | P(rojo) | CI95 | media | mediana | lift | z (1 cola) |
|---|---|---|---|---|---|---|---|---|
| BASE grupo A | 3.884 | 3.884 | 46,06% | [44,50 – 47,63] | +0,007% | +0,091% | — | — |
| & KOSPI ≤ −2% | 188 | 127 | 54,79% | [46,12 – 63,18] | −0,347% | −0,267% | +8,7 pp | 1,94 (p=0,026) |
| & KOSPI ≤ −3% | 82 | 61 | 53,66% | [41,30 – 65,58] | −0,499% | −0,651% | +7,6 pp | 1,18 (p=0,119) |
| & KOSPI ≤ −5% | 14 | 14 | 78,57% | [52,41 – 92,43] | −1,361% | −1,316% | +32,5 pp | 2,44 (p=0,007) |

### B. Corea REPLICA a Wall Street — el NDX ya cayó ≥1% la víspera (`NDX[D−1] ≤ −1%`)

| Bucket | n | n_eff | P(rojo) | CI95 | media | mediana | lift | z (1 cola) |
|---|---|---|---|---|---|---|---|---|
| BASE grupo B | 1.410 | 1.410 | 44,40% | [41,82 – 47,00] | +0,188% | +0,182% | — | — |
| & KOSPI ≤ −2% | 284 | 178 | 51,76% | [44,46 – 58,99] | −0,312% | −0,119% | +7,4 pp | 1,86 (p=0,032) |
| & KOSPI ≤ −3% | 148 | 96 | 48,65% | [38,90 – 58,50] | −0,223% | **+0,044%** | +4,3 pp | 0,81 (p=0,209) |
| & KOSPI ≤ −5% | 49 | 38 | **42,86%** | [28,50 – 58,52] | −0,041% | **+0,125%** | **−1,5 pp** | −0,19 (p=0,575) |
| & KOSPI ≤ −8% | 8 | 8 | **25,00%** | [7,15 – 59,07] | **+1,868%** | **+1,544%** | −19,4 pp | −1,10 (p=0,865) |

> **El patrón se INVIERTE según la causa.** Cuando Corea sólo está devolviendo el golpe que Wall Street
> le dio anoche, el Nasdaq del día siguiente **rebota**: con KOSPI ≤ −5% la P(rojo) BAJA a 42,9% y la
> mediana es **positiva**. Ahí la correlación es circular y no informa de nada.

### AC. Combinado "NO es eco" (`NDX[D−1] > −1%`) — la celda más fuerte del estudio

| Bucket | n | episodios | P(rojo) | CI95 (n_eff) | P(≤−2%) | media | mediana | z (1 cola) | BH q=0,10 |
|---|---|---|---|---|---|---|---|---|---|
| BASE grupo AC | 5.658 | — | 45,30% | [44,01 – 46,60] | 8,36% | +0,027% | +0,108% | — | — |
| & KOSPI ≤ −2% | 278 | 177 | 57,19% | [49,83 – 64,25] | 21,94% | −0,403% | −0,408% | 3,13 (p=0,0009) | **pasa** |
| & KOSPI ≤ −3% | 127 | 89 | 59,06% | [48,67 – 68,69] | 26,77% | −0,630% | −0,744% | 2,59 (p=0,005) | **pasa** |
| & KOSPI ≤ −5% | 26 | 23 | **84,62%** | [65,14 – 94,18] | 42,31% | **−1,471%** | **−1,674%** | 3,78 (p=8e-5) | **pasa** |

**Este es el número real que respalda la intuición de Yunior… con dos condiciones que hoy NO se cumplen del todo (§4)
y un caveat de concentración que lo debilita mucho (§6).**

---

## 4. Tabla 3 — el caso de HOY: give-back tras rally parabólico coreano

Hoy no es "Corea se desploma". Hoy es **Corea devuelve parte de un +17,91% récord de ayer**.
Eso hay que medirlo aparte, y se puede: hay muestra.

### Post-rally coreano (`KOSPI[D−1] ≥ +3%`), base propia del grupo

| Bucket | n | n_eff | P(rojo) | CI95 (n_eff) | P(≤−2%) | media | mediana | lift | z (1 cola) |
|---|---|---|---|---|---|---|---|---|---|
| BASE `KOSPI[D−1] ≥ +3%` | 246 | 246 | 50,81% | [44,60 – 57,00] | 15,85% | +0,003% | −0,025% | — | — |
| & KOSPI ≤ −2% | 43 | 36 | 48,84% | [33,43 – 64,47] | 18,60% | −0,231% | **+0,070%** | −2,0 pp | −0,22 (p=0,588) |
| & KOSPI ≤ −3% | 26 | 21 | 53,85% | [33,64 – 72,86] | 15,38% | −0,331% | −0,355% | +3,0 pp | 0,27 (p=0,395) |
| & KOSPI ≤ −5% | 12 | 10 | 66,67% | [36,78 – 87,30] | 25,00% | −0,991% | −1,095% | +15,9 pp | 0,98 (p=0,163) |

### Apretando el filtro hasta el perfil exacto de hoy

| Filtro | n | n_eff | P(rojo) | CI95 | P(≤−2%) | media | mediana | z vs base global |
|---|---|---|---|---|---|---|---|---|
| KOSPI ≤ −3% **&** KOSPI[D−1] ≥ +3% | 26 | 21 | 53,85% | [33,64 – 72,86] | 15,38% | −0,331% | −0,355% | 0,80 (**p=0,211**) |
| **+** NDX[D−1] > −1% (Wall St. sana) | 16 | 14 | 50,00% | [26,80 – 73,20] | 12,50% | **−0,005%** | −0,172% | 0,37 (**p=0,357**) |
| **+** gap QQQ ≥ −1,5% (proxy del NQ plano) | 8 | 7 | 62,50% | [28,91 – 87,23] | 12,50% | −0,027% | −0,986% | 0,92 (**p=0,178**) |

**Ninguna de las tres celdas de P(rojo) pasa BH-FDR q=0,10. Ninguna alcanza `n_eff ≥ 30`.**
La celda central (n=16) da exactamente la base: **50% de rojo, media −0,005%. Cero señal.**

> **Matiz que va en contra de mi propia conclusión y por eso se publica:** en esas mismas celdas,
> **P(NDX ≤ −1%) SÍ está elevada y SÍ pasa BH-FDR**: 42,31% vs 20,02% de base (z=2,55, p=0,0055) en el
> post-rally, y 50,0% vs 20,02% (z=1,98, p=0,024) en la celda con gap plano. Es decir: **la dirección
> (rojo/verde) es un volado, pero la cola de −1% está claramente inflada.** Es la misma historia de §5:
> lo que hay es **amplitud**, no rumbo. Sigue sin ser publicable como probabilidad (`n_eff` 7-21 < 30).

Los 8 casos con el perfil más cercano al de hoy, uno a uno:

| Fecha | KOSPI[D] | KOSPI[D−1] | NDX[D−1] | gap QQQ | QQQ open→close | **NDX cierre-cierre** |
|---|---|---|---|---|---|---|
| 1999-11-17 | −3,98% | +3,38% | +2,24% | 0,00% | −1,35% | −0,97% |
| 2000-10-17 | −6,77% | +4,86% | −0,86% | +1,37% | −5,86% | −2,38% |
| 2000-10-23 | −3,22% | +6,01% | +1,58% | −0,14% | 0,00% | −1,00% |
| 2004-05-13 | −3,30% | +3,30% | −0,50% | −0,57% | −0,14% | +0,16% |
| 2008-10-29 | −3,02% | +5,57% | +10,92% | +0,16% | −0,41% | +0,35% |
| 2008-11-24 | −3,35% | +5,80% | +4,73% | +2,06% | +3,97% | **+6,33%** |
| 2026-06-26 | −5,81% | +5,42% | +0,75% | −1,29% | −0,09% | −1,09% |
| 2026-07-16 | −6,37% | +6,24% | −0,28% | −0,80% | −0,85% | −1,62% |

5 rojos, 3 verdes. **Ninguno cayó ≥2%.** Peor caso −2,38%… en el pinchazo de la burbuja puntocom.

---

## 5. Lo que la señal REALMENTE predice: volatilidad, no dirección

| Celda | n | P(cae ≥1%) | P(sube ≥1%) | **P(\|mov\| ≥1%)** | P(cae ≥2%) | P(sube ≥2%) | ratio colas | sd NDX |
|---|---|---|---|---|---|---|---|---|
| BASE | 7.068 | 20,02% | 22,01% | **42,03%** | 9,34% | 8,62% | 0,91 | 1,75% |
| KOSPI ≤ −2% | 562 | 38,08% | 26,69% | **64,77%** | 22,42% | 13,35% | 1,43 | 2,58% |
| KOSPI ≤ −3% | 275 | 41,09% | 28,36% | **69,45%** | 24,36% | 13,82% | 1,45 | 2,81% |
| KOSPI ≤ −5% | 75 | 48,00% | 22,67% | **70,67%** | 28,00% | 10,67% | 2,12 | 2,73% |

**Un desplome coreano infla LAS DOS colas**: P(|movimiento| ≥1%) sube de 42% a 71%, y la desviación típica del
Nasdaq pasa de 1,75% a 2,73% (**+56%**). La cola baja crece más que la alta (ratio 0,91 → 2,12), así que hay
un sesgo direccional real, pero **el efecto dominante y de largo el más fiable es de VOLATILIDAD**.

**Traducción operativa:** el KOSPI desplomado es un **gate de régimen** (hoy toca día ancho, stops anchos,
mala jornada para vender prima), **no una flecha corta**. Esta es la lectura que sobrevive a todos los cortes.

## 5.1 …y el daño está en el HUECO, no en la sesión

Descomposición con QQQ (Open real de bolsa):

| Celda | n con Open | gap medio | gap mediana | open→close medio | open→close mediana | P(open→close rojo) |
|---|---|---|---|---|---|---|
| BASE | 6.538 | +0,06% | +0,07% | −0,01% | +0,06% | 46,93% |
| KOSPI ≤ −2% | 451 | −0,53% | −0,35% | **+0,07%** | 0,00% | 48,78% |
| KOSPI ≤ −3% | 211 | −0,63% | −0,39% | **+0,19%** | +0,05% | 46,45% |
| KOSPI ≤ −5% | 54 | −0,90% | −0,80% | **+0,62%** | 0,00% | 46,30% |
| KOSPI ≤ −8% | 11 | −1,61% | −0,86% | **+2,30%** | +1,09% | 45,45% |

**Todo el retorno negativo de cierre-a-cierre es el HUECO. Desde la campana, el open→close es plano o
positivo y su P(rojo) es indistinguible de la base (46-49% vs 46,9%).**
Corolario duro, y es el que manda hoy: **a las 09:30 la información coreana ya está en el precio.**
Vender el Nasdaq en la apertura porque Corea cayó es comprar el descuento ya pagado.

---

## 6. Caveats que rebajan el resultado (no enterrados en una nota al pie)

1. **La celda fuerte se apoya en dos crisis y en el presente.** El reparto por época de
   `AC no-eco & KOSPI ≤ −5%` (n=26): **1997-1999 → 11 casos · 2000-2011 → 6 · 2012-2025 → 0 · 2026 → 9**.
   **Catorce años (2012-2025) con CERO observaciones.** Llamarlos "23 episodios independientes" es generoso:
   son la crisis asiática, el pinchazo puntocom/GFC y el régimen actual. El intervalo de Wilson no captura ese riesgo.
2. **El régimen coreano de hoy está FUERA de la muestra.** sd del KOSPI en la muestra completa: **1,72%**.
   sd de las últimas 23 sesiones: **6,32%**. La sd rodante de 63 días está en el **percentil 99,99 de 30 años**.
   **8 de los 80 días ≤ −5% de toda la historia (10%) ocurrieron desde el 2026-07-01.** Y el +17,91% del viernes
   es el **mayor movimiento diario absoluto del KOSPI en 30 años** (supera al −12,06% de 2026-03-04 y al
   −12,02% del 12-sep-2001). Toda probabilidad de este informe se estimó en un mundo con **un cuarto** de la volatilidad coreana actual.
3. **Estabilidad por época — el efecto no es estable:**

   | Época | n sesiones | base P(rojo) | KOSPI≤−3%: n / P(rojo) / media | KOSPI≤−5%: n / P(rojo) / media |
   |---|---|---|---|---|
   | 1997-2007 | 2.633 | 46,1% | 179 / 52,0% / −0,27% | 42 / 61,9% / −0,46% |
   | 2008-2016 | 2.167 | 46,0% | 41 / 46,3% / −0,08% | 12 / 41,7% / −0,44% |
   | 2017-2025 | 2.130 | 43,0% | 30 / 63,3% / −1,43% | 4 / 25,0% / −0,25% |
   | 2026 | 138 | 45,7% | 25 / 64,0% / −0,76% | 17 / 64,7% / −0,85% |

   En 2008-2016 el efecto **desaparece** (46,3% ≈ base) y en 2017-2025 con ≤−5% se **invierte** (25%, n=4).
4. **El proxy interno de la casa exagera.** KODEX 200 cayó **−8,93%** hoy; el índice ^KS11 cayó **−5,1%**.
   Estas tablas usan el **ÍNDICE**. Meter el −8,93% en el bucket "≤ −8%" sería **mezclar universos** y llevaría a leer una celda de n=13 que además es la única no monótona.
5. **Discrepancia de cifra de hoy, declarada y no promediada.** yfinance: −5,125% (cierre 6.257,45).
   Prensa coreana (Seoul Economic Daily / Korea JoongAng): **−4,88% en 6.273**. Con el cierre previo de
   6.595,45, el número de prensa cuadra (−4,89%) y es probablemente el oficial; yfinance parece provisional.
   **Ambos caen en el mismo bucket** (≤−3%, sin llegar a −8%), así que ninguna conclusión cambia.
6. **`n_eff` < 30 en TODA celda que describa el caso de hoy.** Por la regla de la casa, **no son publicables como probabilidad**.

---

## 7. Contexto de hoy y el analógico más cercano que existe

**Perfil de hoy:** KOSPI **−5,1%** (índice) / KODEX 200 **−8,93%** (proxy) · KOSPI[D−1] **+17,91%** (récord de 30 años) ·
NDX[D−1] **+0,597%** (viernes 31-jul) · **NQ −0,613% a las 06:41 ET** · caída concentrada en memoria
(Samsung −8,76%, SK Hynix −8,79%) · catalizador regulatorio doméstico (límite de apalancamiento de ETF 2x → 1,5x/1x).
Grupo causal: **A (doméstica, Wall Street sana) Y ADEMÁS post-rally**.

### "¿Cuántas veces el futuro estaba tan plano tras una caída coreana así, y qué pasó?"

No hay historia diaria del NQ intradía a las 06:50, así que el proxy medible es el **gap de apertura de QQQ**.
Hoy el NQ marca −0,61%; el gap histórico medio tras KOSPI ≤ −5% es **−0,90%**. **Hoy el futuro está reaccionando
MENOS de lo normal.**

**Los 9 casos del régimen 2026 con `NDX[D−1] > −1%` y KOSPI ≤ −5%** (el corte más parecido a hoy en volatilidad):

| Fecha | KOSPI[D] | gap QQQ | QQQ open→close | NDX cierre-cierre |
|---|---|---|---|---|
| 2026-03-03 | −7,24% | −1,93% | +0,88% | −1,09% |
| 2026-05-15 | −6,12% | −1,34% | −0,17% | −1,54% |
| 2026-06-05 | −5,54% | −1,42% | −3,42% | −4,77% |
| 2026-06-23 | −9,99% | −3,01% | −0,29% | −3,29% |
| 2026-06-26 | −5,81% | −1,29% | −0,09% | −1,09% |
| 2026-07-13 | −8,95% | −1,07% | −0,83% | −1,88% |
| 2026-07-16 | −6,37% | −0,80% | −0,85% | −1,62% |
| 2026-07-28 | −10,84% | −0,86% | −0,11% | −0,98% |
| 2026-07-29 | −5,98% | 0,00% | −2,04% | −2,06% |

**9 de 9 rojos**, media −2,04%, mediana −1,62%. **PERO**: `n=9` en **un solo régimen**, días muy solapados
→ **n INSUFICIENTE. Se cita como conteo crudo (9 de 9), jamás como "100%".**
Dato relevante para hoy: **8 de esos 9 abrieron con un hueco de al menos −0,80%.** Hoy el NQ marca −0,61%,
**más suave que 8 de los 9**.

Y los **give-back post-rally de 2026** (el subgrupo que sí describe hoy): **n=5 — 4 rojos, 4 con caída ≥1%,
CERO con caída ≥2%**, media −1,15%. `n=5` → **n insuficiente**, conteo crudo.

---

## 8. VEREDICTO

| Sub-afirmación | Estado | Evidencia |
|---|---|---|
| Existe *algún* enlace KOSPI[D] → Nasdaq[D] | **MEDIDO** | P(rojo) 45,1% → 57,3% con ≤−5% (n=75/n_eff=49); pasa BH-FDR q=0,10 |
| El enlace escala con la magnitud de la caída coreana | **REFUTADO** | P(rojo) plana en 53-61% de −1% a −8% |
| "Cae **drásticamente**" | **REFUTADO** | P(NDX ≤ −2%) = 28% con ≤−5%. Lo normal es un −0,5% de media |
| Sirve para operar corto en la apertura | **REFUTADO** | Todo el daño es el hueco. open→close medio **+0,62%**, P(rojo intradía) 46,3% ≈ base |
| Aplica a HOY (give-back tras rally, Wall St. sana, NQ plano) | **NO DEMOSTRADO — n insuficiente y p=0,21-0,36** | 3 celdas, todas con n_eff 7-21, ninguna pasa BH-FDR; la central da 50,0% de rojo y media −0,005% |
| Lo que sí predice | **MEDIDO** | **VOLATILIDAD**: P(\|mov\| ≥1%) 42% → 71%, sd +56% |
| Dirección de la causalidad | **INVERTIDA respecto al relato** | corr(NDX[D−1]→KOSPI[D]) **0,310** > corr(KOSPI[D]→NDX[D]) **0,130** |

### En una frase

> **El patrón "Corea se desploma → el Nasdaq cae drásticamente el mismo día" NO está medido en la forma en
> que se cuenta.** Lo que está medido es (a) un sesgo direccional **modesto** (+12 pp de P(rojo) en el peor
> bucket) que además **ya está pagado en el hueco de apertura**, (b) un aumento **grande y fiable de la
> VOLATILIDAD** del día, y (c) una causalidad que va **mayoritariamente de Wall Street a Seúl**, no al revés.
> **Para el caso concreto de hoy** —give-back tras un rally récord, con Wall Street sana y el NQ apenas
> −0,6%— **el histórico no da señal bajista: da la base**, con n insuficiente para publicar nada.

### Lo que se puede decir en voz alta hoy, y lo que no

- **SÍ:** "día de rango ancho, gate de volatilidad activo" — medido, sd +56%, P(|mov|≥1%) 71%.
- **SÍ:** "el hueco es la información; después de la campana el edge coreano se ha agotado" — medido.
- **SÍ (con etiqueta):** "en el régimen 2026, 9 de 9 casos parecidos cerraron rojos" — **conteo crudo, n=9, un solo régimen, NO es una probabilidad.**
- **NO:** cualquier "P(el Nasdaq cae hoy) = X%" derivada del KOSPI. Todas las celdas que describen hoy tienen `n_eff` entre 7 y 21 y `p` entre 0,16 y 0,36.
- **NO:** confundir el −8,93% del KODEX 200 con el −4,88%/−5,1% del índice. Son universos distintos.

---

*Regla de la casa aplicada: `n_eff ≥ 30` para publicar probabilidad · Wilson sobre muestra efectiva por
episodios · BH-FDR q=0,10 sobre los 64 contrastes · toda fuente con su latencia · ningún `except` devolvió
un número plausible. Señal-solamente.*
