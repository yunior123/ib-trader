# PEER-WEIGHTS HARDENING — resultado MEDIDO (2026-07-25)

**Conclusión en una línea: SOBREVIVEN 0 DE 19 PARES. No existe ninguna relación lead-lag
medible entre NVDA y sus pares de flota en barras de 1 minuto; todo lo que hay es
co-movimiento CONTEMPORÁNEO, así que `governing_captain()` queda como regla de DOCTRINA
(SPY/QQQ = mercado, SMH = semis) SIN ninguna afirmación de lead medido adjunta.**

Feature 29 de `docs/FEATURES-MINED-2026-07-25.md`. Su entregable no es una feature nueva:
es la medición que **retira formalmente** `ratio-tape` (TS-10), `blind-spots` (MQ-6) y
`borrowed-map` (MQ-11), las tres construidas sobre `trades.db peer_weights`.

- Script: `scripts/peer_health.py` · Tests: `tests/test_peer_health.py` (9 pasan, <1 s)
- Salida máquina: `data/peer_health.json` · Tabla: `trades.db peer_weights` extendida con
  `(se, tstat, lead_survives, shuffle_p, resid_corr, n_eff)`
- Consumidor endurecido: `scripts/peer_influence.py`

---

## Método (exactamente el de la ficha, sin recortes)

1. **Retornos log de 1 minuto** de `poly_bars`, formados **solo entre barras consecutivas**
   (`Δts == 60000 ms`) para que ningún salto overnight ni hueco de datos entre como retorno.
   **`ts` está en MILISEGUNDOS** — tratarlo como segundos hace que `date(ts,'unixepoch')`
   devuelva NULL sobre las 540 sesiones y lleva a concluir "no hay datos" sobre 8,95 M de filas.
2. **Inner join POR EPOCH** de las dos patas (más los controles), con **tasa de descarte
   publicada por par** (`drop_rate = 1 − n_join / n_union`).
3. `corr` con **SE HAC (Newey-West, kernel Bartlett, lag 5)** y t-stat; `n_eff` = tamaño de
   muestra efectivo tras la corrección HAC.
4. **Correlación cruzada por TIEMPO, no por posición**: `corr(target[t], peer[t − k·60 s])`
   para k ∈ [−5, +5] min; k>0 ⇒ el peer adelanta. Un hueco de datos no puede fabricar un lag.
5. El pico se acepta **solo si sobrevive AMBOS**:
   - **(a) null de 1000× timestamps barajados** — estadístico `max_{k≠0} |corr|`,
     `p = (1 + #{null ≥ obs}) / 1001`;
   - **(b) control de factor común** — se regresan **ambas patas** sobre **SMH y QQQ** (el
     control excluye al propio peer cuando el peer *es* SMH o QQQ) y se cross-correlacionan
     **los residuos**, con su propio null de barajado. *Las cotizaciones asíncronas en activos
     que co-mueven producen picos espurios a lag no-cero **por construcción**; este control es
     el corazón de la feature.*
6. `beta` por **OLS sobre retornos residualizados**, con `n` y `R²`.

**Regla de decisión implementada** (`lead_survives = 1` exige las cinco):
`lead_min ≠ 0` **y** `shuffle_p < 0.05` **y** `resid_lead_min == lead_min` **y**
`resid_shuffle_p < 0.05` **y** `|resid_corr| > |resid_corr(lag 0)|`.

**Cualquier consumidor puede usar SOLO pares con `lead_survives = 1`.** Hoy no hay ninguno.

---

## Los 19 pares (target = NVDA en los 19; 540 sesiones, 2024-07-25 → 2026-07-24)

| peer | n | drop_rate | corr | SE HAC | t-stat | n_eff | lead_min | shuffle_p | resid_lead | resid_corr | resid lag0 | β resid | R² | **lead_survives** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--:|
| SPY  | 232 883 | 0.173 | +0.582 | 0.0170 | 34.3 | 131 422 | **0** | 0.001 | +1 | −0.068 | +0.003 | +0.010 | 0.000 | **0** |
| QQQ  | 235 189 | 0.121 | +0.667 | 0.0175 | 38.1 | 134 115 | **0** | 0.001 | 0 | +0.410 | +0.410 | +0.974 | 0.168 | **0** |
| XLK  | 202 807 | 0.551 | +0.709 | 0.0152 | 46.7 | 181 675 | **0** | 0.001 | 0 | +0.102 | +0.102 | +0.263 | 0.010 | **0** |
| SMH  | 235 189 | 0.501 | +0.629 | 0.0164 | 38.5 | 131 178 | **0** | 0.001 | 0 | +0.309 | +0.309 | +0.378 | 0.095 | **0** |
| AVGO | 225 650 | 0.344 | +0.467 | 0.0227 | 20.6 | 137 608 | **0** | 0.001 | 0 | +0.060 | +0.060 | +0.047 | 0.004 | **0** |
| TSM  | 224 174 | 0.367 | +0.519 | 0.0123 | 42.4 | 129 087 | **0** | 0.001 | 0 | +0.128 | +0.128 | +0.130 | 0.016 | **0** |
| AMD  | 228 680 | 0.227 | +0.442 | 0.0103 | 42.7 | 137 194 | **0** | 0.001 | 0 | +0.076 | +0.076 | +0.048 | 0.006 | **0** |
| INTC | 232 960 | 0.151 | +0.347 | 0.0090 | 38.7 | 141 304 | **0** | 0.002 | −1 | −0.038 | −0.025 | −0.015 | 0.001 | **0** |
| ASML | 193 264 | 0.560 | +0.434 | 0.0060 | 72.3 | 156 777 | **0** | 0.001 | −1 | −0.044 | −0.007 | −0.006 | 0.000 | **0** |
| DRAM |  45 933 | **0.860** | +0.434 | 0.0149 | 29.1 |  31 232 | **0** | 0.001 | +1 | −0.071 | +0.002 | +0.001 | 0.000 | **0** |
| MU   | 230 427 | 0.285 | +0.455 | 0.0089 | 50.9 | 149 744 | **0** | 0.001 | 0 | +0.063 | +0.063 | +0.039 | 0.004 | **0** |
| TSLA | 234 416 | **0.051** | +0.439 | 0.0118 | 37.1 | 136 606 | **0** | 0.001 | 0 | +0.080 | +0.080 | +0.060 | 0.006 | **0** |
| EWY  | 205 343 | 0.528 | +0.341 | 0.0078 | 43.8 | 170 354 | **0** | 0.001 | 0 | −0.109 | −0.109 | −0.106 | 0.012 | **0** |
| QCOM | 206 675 | 0.529 | +0.358 | 0.0116 | 30.8 | 127 703 | **0** | 0.001 | 0 | −0.080 | −0.080 | −0.056 | 0.006 | **0** |
| SNDK | 158 578 | 0.580 | +0.289 | 0.0065 | 44.6 | 120 374 | **0** | 0.001 | 0 | −0.030 | −0.030 | −0.009 | 0.001 | **0** |
| LRCX | 197 555 | 0.564 | +0.426 | 0.0106 | 40.1 | 125 670 | **0** | 0.001 | 0 | −0.111 | −0.111 | −0.077 | 0.012 | **0** |
| WDC  | 208 398 | 0.528 | +0.338 | 0.0058 | 58.5 | 148 411 | **0** | 0.001 | 0 | −0.057 | −0.057 | −0.027 | 0.003 | **0** |
| NOK  | 213 681 | 0.484 | +0.168 | 0.0101 | 16.6 | 129 887 | **0** | 0.001 | 0 | −0.043 | −0.043 | −0.025 | 0.002 | **0** |
| STX  | 196 925 | 0.573 | +0.302 | 0.0072 | 42.1 | 137 186 | **0** | 0.001 | 0 | −0.090 | −0.090 | −0.046 | 0.008 | **0** |

**`pairs_total` 19 · `pairs_survived` 0 · `drop_rate` media 0.420 (mín 0.051 TSLA, máx 0.860 DRAM).**

`shuffle_p ≈ 0.001` es el mínimo alcanzable con 1000 barajados y **no es una victoria**: mide
que la correlación a lag ±k bate al ruido puro, cosa trivial cuando la correlación a lag 0 es
0.3–0.7 y se derrama a los lags vecinos. **El filtro que decide es el pico en lag 0.**

---

## Qué muestra el número

1. **MEDIDO — el pico de la correlación cruzada está en lag 0 en los 19 pares.** No hace
   falta ni llegar al control de factor común: con 540 sesiones y ~230 000 minutos alineados,
   ningún peer adelanta a NVDA en la rejilla de 1 minuto. La hipótesis entera de `ratio-tape` /
   `blind-spots` / `borrowed-map` (proyectar niveles o cinta desde un peer que "va delante")
   **no tiene soporte en el dato**.
2. **MEDIDO — el `lead_min` guardado antes en `peer_weights` ya era 0 en las 19 filas**, y aun
   así tres features propuestas lo trataban como fuente de anticipación. El endurecimiento
   convierte ese 0 en un **veredicto explícito** (`lead_survives = 0`) en vez de un campo mudo.
3. **MEDIDO — el control de factor común es el que borra los pocos picos residuales.** En 4
   pares (SPY +1, DRAM +1, INTC −1, ASML −1) el residuo sí tiene un extremo a lag ±1, pero de
   magnitud **|0.04–0.07| y de signo NEGATIVO**: es la firma de rebote de horquilla /
   cotización asíncrona (reversión de un minuto), no anticipación. Ninguno pasa porque el pico
   crudo estaba en 0, y aunque se relajara esa condición, un |ρ| de 0.05 con β ≈ 0.01 no mueve
   dinero después del spread.
4. **MEDIDO — la co-movilidad residual sobrevive donde debe: QQQ (+0.41) y SMH (+0.31)** siguen
   correlacionados con NVDA tras residualizar sobre el otro índice. Los capitanes son reales
   **como co-movimiento simultáneo**; lo que NO son es un adelanto temporal.
5. **MEDIDO — la tasa de descarte del inner-join es enorme y desigual**: media 42 %, y **86 %
   en DRAM** (n efectivo 45 933 de ~330 000 minutos). Cualquier estimación de par que incluya
   un nombre poco líquido está midiendo un subconjunto de minutos con volumen, no la sesión.
6. **SOSPECHADO — a resolución de 1 minuto el lead, si existe, es sub-minuto.** Este dato no
   puede refutarlo ni confirmarlo. Reabrir SOLO con barras de segundos o cinta, y con el mismo
   doble control; hasta entonces no se afirma nada.
7. **NOTA de cobertura**: los 19 pares tienen todos target NVDA. **SKHY no aparece en ninguno**
   (solo 10 sesiones en `poly_bars`), así que este informe no dice nada sobre SKHY — y no lo
   promedia con los demás. SNDK (376 sesiones) y DRAM (78) sí entran, con su `n` a la vista.

---

## Consecuencias operativas (esto es lo que cambia hoy)

- **RETIRADAS formalmente**: `ratio-tape` (TS-10), `blind-spots` (MQ-6), `borrowed-map` (MQ-11).
  Ninguna tiene base medible; `borrowed-map` además lavaba un veto de `book-quality` en señal.
- **`governing_captain()` sigue vigente como DOCTRINA**, no como medición: SPY/QQQ mandan sobre
  el mercado y SMH sobre semis porque es la regla de la casa (regla 12), **y se dice así**. Se
  prohíbe adjuntarle un "adelanta N minutos" — ese número no existe.
- `scripts/peer_influence.py` endurecido: lee la BD en solo-lectura, **falla ruidosamente** si
  falta la tabla (antes un `except` devolvía `[]`, es decir "no sé" disfrazado de "no hay
  influencia"), imprime el pico crudo como **SIN VALIDAR**, y solo muestra un lead si
  `lead_survives = 1`. Recomputar pesos con `weights <SYM>` reescribe `lead_survives = 0`:
  hay que volver a correr `peer_health.py` para que un par pueda reclamar un lead.
- El peso de influencia (`beta × |corr|`) **sigue siendo legítimo** como lectura de presión
  **contemporánea** — es lo único que el dato soporta.

---

## Reproducir

```bash
./venv/bin/python -m pytest tests/test_peer_health.py -q     # 9 tests, <1 s, sin red ni TWS
./venv/bin/python scripts/peer_health.py                     # ~8 min, 19 pares × 2 nulls × 1000
./venv/bin/python scripts/peer_health.py --shuffles 50 --limit 2   # corrida rápida
```

El test que justifica la feature entera es
`test_factor_control_kills_spurious_lead`: dos series que son ambas `f(t) + ruido` con el
**mismo** factor y **cero lead real**, una muestreada con retraso. La correlación cruzada cruda
**sí** encuentra un pico a lag ≠ 0; tras residualizar sobre el factor, `lead_survives == 0`.
El complementario, `test_real_injected_lead_survives` (`y[t] = x[t−3] + ruido`), confirma que
el filtro **no** es un rechazador universal: ese sí sale con `lead_survives == 1`.
