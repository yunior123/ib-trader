# Mapa de opciones de la flota — LUNES 2026-08-03 (premarket)

Generado 2026-08-03 06:58:02 ET. **Señal-solamente.** Ninguna orden sale de este fichero.

## 0. Procedencia y latencia (leer antes que cualquier número)

| qué | fuente | latencia | consecuencia |
|---|---|---|---|
| OI, gamma, delta, IV de cada contrato | Polygon `/v3/snapshot/options`, descargado hoy ~06:52 ET | **15 min delayed** (doctrina medida, `docs/LATENCIA-FUENTES.md`) + **el OI es el del CIERRE DEL VIERNES 31-jul** | los muros son de ayer: describen el libro con el que abre el dealer, no el flujo de hoy |
| spot de **QQQ NVDA META GOOGL MU AAPL INTC** | Finnhub WS, `data/rt_last_<SYM>.txt` | **SIN retraso de proveedor**, pero es el ÚLTIMO PRINT y el premercado es fino: QQQ 16 min, NVDA 9 min, META 17 min, GOOGL 14 min, MU 17 min, AAPL 14 min, INTC 20 min | es el precio más honesto que hay hoy; su antigüedad es la del mercado, no la del feed |
| spot de **SPY SMH AMZN NOK** | cabecera de `data/opt_chain_<sym>.txt` | **Polygon ~15 min delayed** | SPY/SMH/NOK: hueco conocido, no existe su `rt_last`. AMZN: su `rt_last` existe pero el último print tiene 33 min y se descarta por encima de 30 min. **Sus distancias % al muro pueden ir 15 min desfasadas.** |
| bid/ask de opciones | — | — | **NO EXISTEN**: 0 en el 100% de las filas (el plan Polygon no sirve `last_quote`) |
| IBKR / TWS | — | — | **NO USADO**. Prohibido esta semana (orden 2026-08-02). Cero conexiones a 4001/4002/7496/7497 |

**Lo que NO se puede publicar hoy y por qué:**
- **Straddle ATM capturado** (skill `expected-move-envelope`): imposible. Sin bid/ask no hay mid. Se publican DOS sustitutos, ambos etiquetados: EM por IV medida, y el straddle al **cierre del viernes**.
- **Spread de opciones** (gate <5% del premium, regla 4 de la casa): **SIN DATO**. Ningún vehículo de opciones puede aprobarse hoy con este fichero — el gate de spread no es calculable sin NBBO.
- **Probabilidades**: ninguna. Este documento es descriptivo. El único umbral que aparece (PIN = 3x la mediana de OI) es **doctrina etiquetada, no medición**.

## 1. Frescura y cobertura de las cadenas

| sym | fichero | edad | fuente decl. | contratos | OI>0 | gamma>0 | bid/ask | vencs en fichero | vencs vivos reales | agosto completo |
|---|---|---|---|---|---|---|---|---|---|---|
| QQQ | `opt_chain_qqq.txt` | 0.6 min | polygon | 180 | 150 | 100 | **0** | 1 (20260803) | 17 | **NO** |
| SPY | `opt_chain_spy.txt` | 0.4 min | polygon | 176 | 166 | 110 | **0** | 1 (20260803) | 17 | **NO** |
| SMH | `opt_chain_smh.txt` | 3.9 min | polygon | 128 | 115 | 102 | **0** | 1 (20260803) | 11 | **NO** |
| NVDA | `opt_chain_nvda.txt` | 0.3 min | polygon | 96 | 92 | 79 | **0** | 2 (20260803 20260805) | 11 | **NO** |
| AMZN | `opt_chain_amzn.txt` | 3.2 min | polygon | 120 | 117 | 91 | **0** | 2 (20260803 20260805) | 11 | **NO** |
| META | `opt_chain_meta.txt` | 3.3 min | polygon | 136 | 125 | 104 | **0** | 1 (20260803) | 11 | **NO** |
| GOOGL | `opt_chain_googl.txt` | 3.0 min | polygon | 150 | 125 | 109 | **0** | 2 (20260803 20260805) | 11 | **NO** |
| MU | `opt_chain_mu.txt` | -0.0 min | polygon | 69 | 61 | 69 | **0** | 1 (20260803) | 11 | **NO** |
| AAPL | `opt_chain_aapl.txt` | 3.6 min | polygon | 140 | 136 | 114 | **0** | 2 (20260803 20260805) | 11 | **NO** |
| NOK | `opt_chain_nok.txt` | 1.9 min | polygon | 258 | 258 | 257 | **0** | 2 (20260807 20260814) | 7 | **NO** |
| INTC | `opt_chain_intc.txt` | 2.9 min | polygon | 81 | 81 | 72 | **0** | 2 (20260803 20260805) | 11 | **NO** |

**Diagnóstico:** las cadenas vivas están **frescas** (todas <6 min, `provider_bridge` refresca cada 180 s) pero **recortadas a los 2 vencimientos más cercanos** — `scripts/provider_bridge.py:163` (`NEAR_EXPS = 2`) y `:169` (`exps = sorted({c.expiration for c in chain})[:NEAR_EXPS]`). Polygon SÍ trae hasta 28 días (`mit/backend/app/config.py:92`, `polygon_chain_days=28`): **17 vencimientos vivos en QQQ/SPY y 11 en el resto, mensual 2026-08-21 incluido**. Se descargan y se tiran antes de escribir el fichero.

Consecuencia dura: **el mensual del 21-ago —donde vive el OI que ancla el mes— no entra en el mapa de la flota.** Ningún consumidor de `data/opt_chain_*.txt` puede ver hoy más allá del miércoles. Este análisis lo recupera bajándose las 11 cadenas completas a `data/analisis_2026-08-03/raw/`.

*(Nota de concurrencia: `scripts/provider_bridge.py` fue modificado a las 06:56 ET por otro agente mientras se escribía esto. Los números de línea se verificaron a las 06:56; `NEAR_EXPS = 2` sigue vigente en esa lectura.)*

## 2. `data/gex_snapshot.json` de las 04:00 — rancio y con la procedencia mal etiquetada

Edad: **0.06 h** (asof 2026-08-03 06:54:33). **Recomputado**: sí, aquí, sobre cadenas frescas — pero escrito **solo en este directorio**, NO se ha tocado `data/gex_snapshot.json` (lo leen otros procesos vivos y hay agentes trabajando en paralelo).

| sym | spot 04:00 | spot ahora | deriva | flip 04:00 | flip ahora | abs_wall 04:00 | abs_wall ahora |
|---|---|---|---|---|---|---|---|
| QQQ | 690.78 | 690.97 | -0.03% | 675.79 | 689.04 | 690.00 | 680.00 |
| SPY | 750.87 | 750.86 | 0.00% | 748.64 | 748.82 | 751.00 | 750.00 |
| SMH | 536.50 | 536.00 | 0.09% | 554.01 | 590.24 | 530.00 | 500.00 |
| NVDA | 199.99 | 200.19 | -0.10% | 196.67 | 193.24 | 205.00 | 210.00 |
| AMZN | 276.29 | 276.29 | 0.00% | 269.86 | 256.19 | 280.00 | 280.00 |
| META | 565.59 | 565.09 | 0.09% | 558.27 | 558.35 | 570.00 | 570.00 |
| GOOGL | 362.90 | 363.10 | -0.06% | 360.28 | 347.15 | 362.50 | 360.00 |
| MU | 802.22 | 802.61 | -0.05% | 717.77 | 907.10 | 835.00 | 800.00 |
| AAPL | 310.33 | 310.50 | -0.05% | 305.85 | 298.16 | 310.00 | 310.00 |
| NOK | **AUSENTE del snapshot** | 8.99 | — | — | 9.85 | — | 9.00 |
| INTC | 89.09 | 89.05 | 0.04% | 92.10 | 94.22 | 86.00 | 80.00 |

**Dos defectos que hay que decir en voz alta:**

1. **Procedencia falsa en el fichero que hay en disco.** Los 34 símbolos del snapshot de las 04:00 declaran `chain_src: "ibkr_tws"` y `src: "gex_core + ibkr_tws (griegas MEDIDAS: ibkr_tws)"`. Era **una etiqueta hardcodeada**, no una medición: `contracts_from_tws` escribía `"greeks": "ibkr_tws"` sin mirar el campo `fuente` de la cabecera — que dice `fuente polygon`. Con IBKR **prohibido** esta semana, el mapa estaba afirmando una fuente imposible, y quien dedujera "es IBKR, luego es tiempo real" estaría tomando 15 min de retraso por tiempo real. **Estado a las 06:56 ET: el código YA ESTÁ CORREGIDO** — `scripts/gex_snapshot.py:239-244` ahora hace `fuente = hdr.get("fuente") or "desconocida"` (lo arregló otro agente durante esta misma sesión). **Pero el JSON en disco sigue mintiendo hasta que se regenere el snapshot**: no fiarse de su `chain_src` mientras `_meta.asof_local` siga siendo 04:00:03.
2. **NOK ausente** del snapshot (`_meta.skipped`: "5 strikes poblados (<8): perfil sin lectura"). Con la cadena completa de Polygon sí hay perfil (79 contratos con gamma medida) — el recorte a 2 vencimientos era lo que lo mataba.

## 3. Mapa por símbolo — TODOS los vencimientos vivos (banda strikes ±22%)

| sym | spot (fuente) | flip | dist flip | régimen | por qué | net GEX $/1% | net DEX | score M/pt | bias |
|---|---|---|---|---|---|---|---|---|---|
| QQQ | 690.97 (RT) | 689.04 | -0.28% | **NEG** | signo crudo POS CONTRADICHO por la paridad put-call (pares coherentes  | +0.38B | -2.60B | 55.5 | PUT |
| SPY | 750.86 (**+15min**) | 748.82 | -0.27% | **INDETERMINADO** | signo NO determinado: las dos lecturas de paridad discrepan (-2.67 vs  | +5.14B | +8.27B | 684.4 | CALL |
| SMH | 536.00 (**+15min**) | 590.24 | 10.12% | **NEG** | signo crudo del net GEX; paridad no determina | -0.44B | -4.79B | -82.1 | PUT |
| NVDA | 200.19 (RT) | 193.24 | -3.47% | **POS** | signo crudo del net GEX; paridad no determina | +0.43B | +5.30B | 212.8 | CALL |
| AMZN | 276.29 (**+15min**) | 256.19 | -7.28% | **POS** | signo crudo del net GEX; paridad no determina | +0.75B | +5.75B | 271.8 | CALL |
| META | 565.09 (RT) | 558.35 | -1.19% | **INDETERMINADO** | signo NO determinado: las dos lecturas de paridad discrepan (-0.01 vs  | +0.09B | -2.34B | 15.6 | CALL |
| GOOGL | 363.10 (RT) | 347.15 | -4.39% | **POS** | signo crudo del net GEX; paridad no determina | +0.37B | +2.40B | 102.5 | CALL |
| MU | 802.61 (RT) | 907.10 | 13.02% | **NEG** | signo crudo del net GEX; paridad no determina | -0.24B | -3.26B | -30.3 | PUT |
| AAPL | 310.50 (RT) | 298.16 | -3.97% | **POS** | signo crudo del net GEX; paridad no determina | +0.43B | +3.77B | 139.9 | CALL |
| NOK | 8.99 (**+15min**) | 9.85 | 9.57% | **NEG** | signo crudo del net GEX; paridad no determina | -0.00B | -0.03B | -18.7 | PUT |
| INTC | 89.05 (RT) | 94.22 | 5.81% | **NEG** | signo crudo del net GEX; paridad no determina | -0.02B | -0.19B | -24.2 | PUT |

| sym | call wall | put wall | **abs_wall** | tipo | POC | imanes | max pain (venc. cercano) | dist max pain |
|---|---|---|---|---|---|---|---|---|
| QQQ | 700.00 (pin) | 680.00 (trampilla) | **680.00** | **trampilla** | 680.00 | 680.00 / 700.00 | 689.00 | -0.29% |
| SPY | 752.00 (pin) | 750.00 (pin) | **750.00** | **pin** | 750.00 | 750.00 / 752.00 | 751.00 | 0.02% |
| SMH | 550.00 (trampilla) | 530.00 (trampilla) | **500.00** | **trampilla** | 500.00 | 500.00 / 530.00 / 550.00 | 540.00 | 0.75% |
| NVDA | 210.00 (pin) | 200.00 (pin) | **210.00** | **pin** | 210.00 | 200.00 / 210.00 | 195.00 | -2.59% |
| AMZN | 280.00 (pin) | 260.00 (pin) | **280.00** | **pin** | 280.00 | 260.00 / 280.00 | 275.00 | -0.47% |
| META | 600.00 (pin) | 550.00 (trampilla) | **570.00** | **pin** | 570.00 | 550.00 / 570.00 / 600.00 | 567.50 | 0.43% |
| GOOGL | 370.00 (pin) | 350.00 (pin) | **360.00** | **pin** | 360.00 | 350.00 / 360.00 / 370.00 | 362.50 | -0.17% |
| MU | 900.00 (trampilla) | 800.00 (trampilla) | **800.00** | **trampilla** | 800.00 | 800.00 / 900.00 | 800.00 | -0.33% |
| AAPL | 320.00 (pin) | 300.00 (pin) | **310.00** | **pin** | 310.00 | 300.00 / 310.00 / 320.00 | 310.00 | -0.16% |
| NOK | 10.00 (pin) | 8.00 (trampilla) | **9.00** | **trampilla** | 9.00 | 8.00 / 9.00 / 10.00 | 9.00 | 0.11% |
| INTC | 100.00 (pin) | 80.00 (trampilla) | **80.00** | **trampilla** | 80.00 | 80.00 / 100.00 | 90.00 | 1.07% |

Convención: `net GEX $/1%` es la escala que cita el mundo (CBOE/SpotGamma); `score` es la de la casa (M$ por punto). `net DEX` es OI-larga (calls +, puts −, la misma que publica Unusual Whales): `dex_sentiment` es el CLIENTE, `dex_flow_impact` es lo que el creador hace en el subyacente — están en el JSON, son opuestos y publicar solo uno invierte la lectura.

**Régimen INDETERMINADO en SPY y META**: no es un fallo tapado con un cero. `gex_core.regime_by_parity` exige que las dos lecturas legales de la identidad de paridad (gamma_call == gamma_put al mismo strike/vencimiento) coincidan en signo; en SPY dan **−2,67B y +3,96B $/1%** y en META **−0,01B y +0,02B**. Con solo 6.4% y 6.2% de pares coherentes el libro de Polygon no determina el signo. **SPY y META hoy no tienen régimen publicable.** QQQ sí lo tiene, y es NEG **porque la paridad CONTRADICE el signo crudo** (crudo POS +55,5M/pt, paridad NEG): quien lea solo el net GEX de QQQ leerá el régimen al revés.

### 3b. Lo que cambia si solo miras los 2 vencimientos del fichero vivo

| sym | flip (2 vencs) | flip (todos) | régimen (2 vencs) | régimen (todos) | abs_wall (2 vencs) | abs_wall (todos) |
|---|---|---|---|---|---|---|
| QQQ | 686.75 | 689.04 | POS | NEG | 690.00 | 680.00 |
| SPY | 749.53 | 748.82 | n/d | n/d | 752.00 | 750.00 |
| SMH | 553.33 | 590.24 | NEG | NEG | 530.00 | 500.00 |
| NVDA | 196.68 | 193.24 | POS | POS | 205.00 | 210.00 |
| AMZN | 270.01 | 256.19 | POS | POS | 275.00 | 280.00 |
| META | 558.12 | 558.35 | POS | n/d | 570.00 | 570.00 |
| GOOGL | 360.37 | 347.15 | n/d | POS | 362.50 | 360.00 |
| MU | 824.77 | 907.10 | NEG | NEG | 790.00 | 800.00 |
| AAPL | 304.15 | 298.16 | POS | POS | 300.00 | 310.00 |
| NOK | 9.12 | 9.85 | POS | NEG | 9.00 | 9.00 |
| INTC | 92.22 | 94.22 | NEG | NEG | 86.00 | 80.00 |

## 4. Expected move — DOS métodos, ninguno es el straddle de hoy

| sym | venc | IV ATM medida | EM 1σ ($) | EM 1σ (%) | rango | straddle cierre viernes (%) | coherencia |
|---|---|---|---|---|---|---|---|
| QQQ | 20260803 | 0.360 | 8.00 | **1.16%** | 682.97 – 698.97 | 1.12 | +4% |
| SPY | 20260803 | 0.210 | 5.06 | **0.67%** | 745.80 – 755.92 | 0.64 | +5% |
| SMH | 20260803 | 0.991 | 17.05 | **3.18%** | 518.95 – 553.05 | 3.55 | -10% |
| NVDA | 20260803 | 0.694 | 4.46 | **2.23%** | 195.73 – 204.65 | 2.13 | +5% |
| AMZN | 20260803 | 1.023 | 9.08 | **3.29%** | 267.21 – 285.37 | 3.19 | +3% |
| META | 20260803 | 0.809 | 14.69 | **2.60%** | 550.40 – 579.78 | 2.55 | +2% |
| GOOGL | 20260803 | 0.759 | 8.85 | **2.44%** | 354.25 – 371.95 | 2.35 | +4% |
| MU | 20260803 | 1.955 | 50.38 | **6.28%** | 752.23 – 852.99 | 6.34 | -1% |
| AAPL | 20260803 | 0.703 | 7.01 | **2.26%** | 303.49 – 317.51 | 2.14 | +6% |
| NOK | 20260807 | 0.848 | 0.84 | **9.29%** | 8.15 – 9.83 | 7.45 | +25% |
| INTC | 20260803 | 1.718 | 4.91 | **5.52%** | 84.14 – 93.96 | 5.29 | +4% |

- **Método 1 (columna EM)**: `spot × IV_ATM × √T` con la IV **medida por Polygon** (delayed 15 min; para el 0DTE de hoy esa IV se calculó con precios del viernes). Es una aproximación lognormal de 1σ, **no** el straddle.
- **Método 2 (straddle cierre viernes)**: `call.close + put.close` del strike ATM, contratos de HOY con el cierre del **viernes 31-jul**, cuando les quedaba un día más de vida. Es una **cota superior**.
- **Los dos métodos coinciden dentro de ±6% en 10 de 11 símbolos** (la excepción es NOK, +25%, cuyo vencimiento más cercano es el 07-ago, no 0DTE, y cuyo libro es el más fino). Que dos caminos independientes den lo mismo es la única razón por la que la valla se publica; sigue sin ser un straddle capturado.

## 5. Top-5 OI por vencimiento (cercano y siguiente)

`EM` = el strike cae dentro del rango 1σ de la tabla 4. OI del **cierre del viernes**.

### QQQ — spot 690.97 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **700.00** 12,690 (+1.3%)  | **705.00** 7,766 (+2.0%)  | **695.00** 7,198 (+0.6%) ✓EM | **690.00** 6,645 (-0.1%) ✓EM | **703.00** 6,560 (+1.7%)  |
| 20260803 (cercano) | PUT | **650.00** 8,670 (-5.9%)  | **685.00** 8,208 (-0.9%) ✓EM | **595.00** 7,710 (-13.9%)  | **620.00** 7,579 (-10.3%)  | **670.00** 7,465 (-3.0%)  |
| 20260804 (siguiente) | CALL | **710.00** 3,340 (+2.8%)  | **705.00** 2,415 (+2.0%)  | **700.00** 2,373 (+1.3%) ✓EM | **709.00** 2,322 (+2.6%)  | **698.00** 2,294 (+1.0%) ✓EM |
| 20260804 (siguiente) | PUT | **575.00** 6,973 (-16.8%)  | **635.00** 6,490 (-8.1%)  | **620.00** 5,684 (-10.3%)  | **650.00** 5,283 (-5.9%)  | **630.00** 4,305 (-8.8%)  |

### SPY — spot 750.86 (Polygon +15min)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **754.00** 12,676 (+0.4%) ✓EM | **753.00** 11,514 (+0.3%) ✓EM | **755.00** 10,628 (+0.6%) ✓EM | **752.00** 9,089 (+0.1%) ✓EM | **756.00** 7,296 (+0.7%)  |
| 20260803 (cercano) | PUT | **695.00** 20,455 (-7.4%)  | **740.00** 15,153 (-1.4%)  | **735.00** 12,711 (-2.1%)  | **725.00** 11,277 (-3.4%)  | **730.00** 10,299 (-2.8%)  |
| 20260804 (siguiente) | CALL | **750.00** 5,353 (-0.1%) ✓EM | **752.00** 3,618 (+0.1%) ✓EM | **769.00** 3,208 (+2.4%)  | **755.00** 2,982 (+0.6%) ✓EM | **760.00** 2,773 (+1.2%)  |
| 20260804 (siguiente) | PUT | **714.00** 12,375 (-4.9%)  | **721.00** 11,029 (-4.0%)  | **704.00** 8,388 (-6.2%)  | **703.00** 7,774 (-6.4%)  | **726.00** 6,959 (-3.3%)  |

### SMH — spot 536.00 (Polygon +15min)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **590.00** 5,172 (+10.1%)  | **550.00** 1,113 (+2.6%) ✓EM | **580.00** 774 (+8.2%)  | **602.50** 632 (+12.4%)  | **600.00** 503 (+11.9%)  |
| 20260803 (cercano) | PUT | **427.50** 16,968 (-20.2%)  | **500.00** 4,230 (-6.7%)  | **495.00** 3,068 (-7.7%)  | **530.00** 2,452 (-1.1%) ✓EM | **527.50** 2,143 (-1.6%) ✓EM |
| 20260805 (siguiente) | CALL | **580.00** 858 (+8.2%)  | **535.00** 510 (-0.2%) ✓EM | **610.00** 303 (+13.8%)  | **555.00** 238 (+3.5%) ✓EM | **560.00** 217 (+4.5%) ✓EM |
| 20260805 (siguiente) | PUT | **525.00** 1,464 (-2.0%) ✓EM | **500.00** 468 (-6.7%)  | **492.50** 445 (-8.1%)  | **425.00** 427 (-20.7%)  | **527.50** 331 (-1.6%) ✓EM |

### NVDA — spot 200.19 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **200.00** 14,745 (-0.1%) ✓EM | **205.00** 14,614 (+2.4%)  | **210.00** 13,214 (+4.9%)  | **202.50** 12,114 (+1.1%) ✓EM | **207.50** 8,540 (+3.6%)  |
| 20260803 (cercano) | PUT | **195.00** 9,768 (-2.6%)  | **190.00** 8,486 (-5.1%)  | **185.00** 6,207 (-7.6%)  | **200.00** 5,638 (-0.1%) ✓EM | **192.50** 5,624 (-3.8%)  |
| 20260805 (siguiente) | CALL | **205.00** 6,537 (+2.4%) ✓EM | **212.50** 6,475 (+6.2%)  | **200.00** 5,046 (-0.1%) ✓EM | **210.00** 5,025 (+4.9%)  | **202.50** 4,010 (+1.1%) ✓EM |
| 20260805 (siguiente) | PUT | **187.50** 7,640 (-6.3%)  | **185.00** 6,759 (-7.6%)  | **170.00** 6,431 (-15.1%)  | **177.50** 6,273 (-11.3%)  | **182.50** 5,381 (-8.8%)  |

### AMZN — spot 276.29 (Polygon +15min)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **280.00** 7,631 (+1.3%) ✓EM | **277.50** 4,923 (+0.4%) ✓EM | **275.00** 4,911 (-0.5%) ✓EM | **282.50** 2,779 (+2.2%) ✓EM | **300.00** 1,865 (+8.6%)  |
| 20260803 (cercano) | PUT | **235.00** 4,274 (-14.9%)  | **265.00** 2,457 (-4.1%)  | **255.00** 2,386 (-7.7%)  | **247.50** 2,126 (-10.4%)  | **270.00** 2,082 (-2.3%) ✓EM |
| 20260805 (siguiente) | CALL | **280.00** 4,105 (+1.3%) ✓EM | **272.50** 2,176 (-1.4%) ✓EM | **275.00** 1,377 (-0.5%) ✓EM | **285.00** 1,207 (+3.1%) ✓EM | **290.00** 1,187 (+5.0%)  |
| 20260805 (siguiente) | PUT | **225.00** 2,444 (-18.6%)  | **250.00** 2,074 (-9.5%)  | **265.00** 1,424 (-4.1%) ✓EM | **270.00** 1,266 (-2.3%) ✓EM | **230.00** 1,195 (-16.8%)  |

### META — spot 565.09 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **590.00** 2,107 (+4.4%)  | **580.00** 2,099 (+2.6%)  | **627.50** 1,532 (+11.0%)  | **600.00** 1,300 (+6.2%)  | **630.00** 1,202 (+11.5%)  |
| 20260803 (cercano) | PUT | **540.00** 1,083 (-4.4%)  | **525.00** 1,068 (-7.1%)  | **550.00** 854 (-2.7%)  | **535.00** 807 (-5.3%)  | **500.00** 804 (-11.5%)  |
| 20260805 (siguiente) | CALL | **600.00** 855 (+6.2%)  | **605.00** 788 (+7.1%)  | **610.00** 581 (+8.0%)  | **607.50** 442 (+7.5%)  | **597.50** 352 (+5.7%)  |
| 20260805 (siguiente) | PUT | **502.50** 782 (-11.1%)  | **540.00** 539 (-4.4%) ✓EM | **600.00** 535 (+6.2%)  | **487.50** 501 (-13.7%)  | **537.50** 485 (-4.9%)  |

### GOOGL — spot 363.10 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **372.50** 1,554 (+2.6%)  | **362.50** 1,346 (-0.2%) ✓EM | **370.00** 1,187 (+1.9%) ✓EM | **365.00** 980 (+0.5%) ✓EM | **405.00** 478 (+11.5%)  |
| 20260803 (cercano) | PUT | **350.00** 4,221 (-3.6%)  | **345.00** 2,578 (-5.0%)  | **347.50** 2,130 (-4.3%)  | **340.00** 1,776 (-6.4%)  | **355.00** 1,607 (-2.2%) ✓EM |
| 20260805 (siguiente) | CALL | **377.50** 1,762 (+4.0%) ✓EM | **360.00** 738 (-0.8%) ✓EM | **365.00** 515 (+0.5%) ✓EM | **400.00** 327 (+10.2%)  | **362.50** 281 (-0.2%) ✓EM |
| 20260805 (siguiente) | PUT | **295.00** 2,643 (-18.8%)  | **350.00** 2,143 (-3.6%) ✓EM | **347.50** 2,118 (-4.3%)  | **310.00** 489 (-14.6%)  | **340.00** 419 (-6.4%)  |

### MU — spot 802.61 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **900.00** 3,647 (+12.1%)  | **960.00** 2,440 (+19.6%)  | **950.00** 1,959 (+18.4%)  | **835.00** 1,940 (+4.0%) ✓EM | **850.00** 1,767 (+5.9%) ✓EM |
| 20260803 (cercano) | PUT | **700.00** 4,994 (-12.8%)  | **747.50** 1,981 (-6.9%)  | **720.00** 1,935 (-10.3%)  | **710.00** 1,780 (-11.5%)  | **800.00** 1,706 (-0.3%) ✓EM |
| 20260805 (siguiente) | CALL | **900.00** 1,254 (+12.1%)  | **950.00** 946 (+18.4%)  | **920.00** 606 (+14.6%)  | **800.00** 318 (-0.3%) ✓EM | **940.00** 318 (+17.1%)  |
| 20260805 (siguiente) | PUT | **790.00** 1,403 (-1.6%) ✓EM | **700.00** 548 (-12.8%)  | **800.00** 511 (-0.3%) ✓EM | **750.00** 482 (-6.5%) ✓EM | **650.00** 309 (-19.0%)  |

### AAPL — spot 310.50 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **310.00** 6,229 (-0.2%) ✓EM | **315.00** 4,040 (+1.4%) ✓EM | **302.50** 3,826 (-2.6%)  | **305.00** 3,675 (-1.8%) ✓EM | **320.00** 3,522 (+3.1%)  |
| 20260803 (cercano) | PUT | **292.50** 7,512 (-5.8%)  | **300.00** 6,112 (-3.4%)  | **310.00** 5,982 (-0.2%) ✓EM | **297.50** 3,811 (-4.2%)  | **285.00** 3,470 (-8.2%)  |
| 20260805 (siguiente) | CALL | **310.00** 2,759 (-0.2%) ✓EM | **327.50** 2,442 (+5.5%)  | **325.00** 2,186 (+4.7%)  | **305.00** 1,900 (-1.8%) ✓EM | **320.00** 1,364 (+3.1%) ✓EM |
| 20260805 (siguiente) | PUT | **300.00** 5,461 (-3.4%) ✓EM | **307.50** 2,939 (-1.0%) ✓EM | **285.00** 2,319 (-8.2%)  | **295.00** 1,775 (-5.0%)  | **290.00** 1,458 (-6.6%)  |

### NOK — spot 8.99 (Polygon +15min)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260807 (cercano) | CALL | **10.50** 10,442 (+16.8%)  | **10.00** 8,199 (+11.2%)  | **9.50** 6,646 (+5.7%) ✓EM | **9.00** 5,500 (+0.1%) ✓EM | **8.50** 783 (-5.5%) ✓EM |
| 20260807 (cercano) | PUT | **9.00** 13,722 (+0.1%) ✓EM | **8.00** 12,440 (-11.0%)  | **8.50** 5,580 (-5.5%) ✓EM | **9.50** 783 (+5.7%) ✓EM | **7.50** 10 (-16.6%)  |
| 20260814 (siguiente) | CALL | **10.00** 9,989 (+11.2%) ✓EM | **9.50** 7,795 (+5.7%) ✓EM | **9.00** 6,564 (+0.1%) ✓EM | **10.50** 4,256 (+16.8%)  | **8.50** 1,164 (-5.5%) ✓EM |
| 20260814 (siguiente) | PUT | **8.00** 11,196 (-11.0%) ✓EM | **9.00** 4,648 (+0.1%) ✓EM | **9.50** 1,314 (+5.7%) ✓EM | **8.50** 1,009 (-5.5%) ✓EM | **7.50** 454 (-16.6%)  |

### INTC — spot 89.05 (tiempo real Finnhub)

| venc | lado | 1º | 2º | 3º | 4º | 5º |
|---|---|---|---|---|---|---|
| 20260803 (cercano) | CALL | **90.00** 8,428 (+1.1%) ✓EM | **101.00** 5,204 (+13.4%)  | **100.00** 4,619 (+12.3%)  | **88.00** 4,521 (-1.2%) ✓EM | **95.00** 3,720 (+6.7%)  |
| 20260803 (cercano) | PUT | **86.00** 6,365 (-3.4%) ✓EM | **88.00** 6,134 (-1.2%) ✓EM | **90.00** 5,150 (+1.1%) ✓EM | **87.00** 4,748 (-2.3%) ✓EM | **92.00** 3,009 (+3.3%) ✓EM |
| 20260805 (siguiente) | CALL | **102.00** 3,207 (+14.5%)  | **105.00** 3,078 (+17.9%)  | **100.00** 1,280 (+12.3%)  | **95.00** 950 (+6.7%) ✓EM | **93.00** 808 (+4.4%) ✓EM |
| 20260805 (siguiente) | PUT | **90.00** 2,152 (+1.1%) ✓EM | **85.00** 703 (-4.5%) ✓EM | **78.00** 519 (-12.4%)  | **80.00** 496 (-10.2%)  | **87.00** 488 (-2.3%) ✓EM |

## 6. PIN — OI monstruo a ±1 strike del spot

Criterio: OI del strike ATM±1 ≥ **3×** la mediana de OI de los strikes en ±3% del spot. **Umbral de DOCTRINA (`oi-magnets-protocol`), NO medido** — no lleva probabilidad.

| sym | venc | strike ATM±1 | OI | mediana banda ±3% | ratio | ¿PIN? |
|---|---|---|---|---|---|---|
| QQQ | 20260803 | 690.00 | 9,214 | 2,666 | **3.46×** | **SÍ** |
| QQQ | 20260804 | 690.00 | 2,108 | 917 | **2.30×** | no |
| SPY | 20260803 | 751.00 | 6,282 | 4,312 | **1.46×** | no |
| SPY | 20260804 | 750.00 | 6,288 | 1,561 | **4.03×** | **SÍ** |
| SMH | 20260803 | 537.50 | 428 | 1,156 | **0.37×** | no |
| SMH | 20260805 | 535.00 | 642 | 293 | **2.19×** | no |
| NVDA | 20260803 | 200.00 | 20,383 | 14,614 | **1.39×** | no |
| NVDA | 20260805 | 200.00 | 7,819 | 5,576 | **1.40×** | no |
| AMZN | 20260803 | 275.00 | 5,606 | 5,269 | **1.06×** | no |
| AMZN | 20260805 | 275.00 | 1,534 | 1,534 | **1.00×** | no |
| META | 20260803 | 565.00 | 731 | 374 | **1.95×** | no |
| META | 20260805 | 565.00 | 196 | 130 | **1.51×** | no |
| GOOGL | 20260803 | 362.50 | 1,359 | 1,116 | **1.22×** | no |
| GOOGL | 20260805 | 365.00 | 589 | 230 | **2.56×** | no |
| MU | 20260803 | 805.00 | 382 | 828 | **0.46×** | no |
| MU | 20260805 | 805.00 | 170 | 344 | **0.49×** | no |
| AAPL | 20260803 | 310.00 | 12,211 | 5,254 | **2.32×** | no |
| AAPL | 20260805 | 310.00 | 3,271 | 2,041 | **1.60×** | no |
| INTC | 20260803 | 90.00 | 13,578 | 5,369 | **2.53×** | no |
| INTC | 20260805 | 90.00 | 2,404 | 598 | **4.02×** | **SÍ** |

**PIN detectado:**
- **QQQ 20260803 en 690.00** (OI 9,214 = 3.46× la mediana). Doctrina: OI monstruo a ±1 del spot = pin → **prohibido 0DTE comprado ahí**.
- **SPY 20260804 en 750.00** (OI 6,288 = 4.03× la mediana). Doctrina: OI monstruo a ±1 del spot = pin → **prohibido 0DTE comprado ahí**.
- **INTC 20260805 en 90.00** (OI 2,404 = 4.02× la mediana). Doctrina: OI monstruo a ±1 del spot = pin → **prohibido 0DTE comprado ahí**.

**Límite honesto del test**: el criterio es un COCIENTE contra la vecindad, así que castiga a los libros donde *todos* los strikes cercanos son gordos. Caso claro: **NVDA 0DTE tiene 20.383 de OI clavado en el 200 (spot 200,19)** — el mayor cluster absoluto de toda la tabla — y sale 1,39× porque sus vecinos también tienen ~14.600. En OI absoluto NVDA 200 es el imán más pesado del día; en ratio no pasa el corte. **Los dos hechos son ciertos y ninguno se puede ocultar**: quien opere NVDA 0DTE alrededor de 200 está dentro de un cluster monstruo aunque la columna diga "no".

## 7. Límites de este mapa (lo que un consumidor NO debe deducir)

- **La banda de strikes es ±22% del spot.** El max pain y los muros se calculan sobre ese recorte. Cuando el OI dominante vive en el borde —caso medido: **SMH put 427,5 con 16.968 de OI a −20,2%**— el cluster real puede seguir fuera y el max pain estar sesgado. Marcado, no corregido.
- **El OI es del cierre del viernes 31-jul.** Después de un +17,9% en Corea el viernes y un −8,8% esta madrugada, el libro que verá el dealer hoy a las 09:30 puede no parecerse a este. Los muros describen la posición heredada, no el flujo de hoy.
- **Sin bid/ask no hay gate de spread.** Regla 4 de la casa (spread <5% del premium): hoy **no es verificable**. Ningún contrato debería aprobarse por vehículo con este fichero solo.
- **SPY, SMH y NOK van con spot delayed** (~15 min). En premercado de un lunes con hueco eso puede ser mucho: sus distancias % al muro son orientativas hasta que exista `data/rt_last_SPY.txt` / `_SMH.txt` / `_NOK.txt`.
- **Ninguna probabilidad, ningún backtest, ninguna dirección.** El régimen NEG de QQQ/SMH/MU/INTC/NOK significa **caja de whipsaw**, no bajada: doctrina `negative-gamma-whipsaw`. Se espera muro + rechazo **impreso** (2 velas cerradas), nunca "está cerca".

---

**Ficheros**: `data/analisis_2026-08-03/mapa_opciones.json` (estructurado, un objeto por símbolo) · `data/analisis_2026-08-03/raw/chain_<sym>.json` (las 11 cadenas completas de Polygon, tal cual llegaron) · este `.md`.
