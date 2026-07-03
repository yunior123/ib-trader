# TABLA DE VIABILIDAD — olas 2 y 3 (2026-07-25)

**Por qué existe**: la ola 2 se definió el 2026-07-25 por la mañana como *"necesita los dos
desbloqueos de datos (~4-8 semanas)"*. El backfill de barras aterrizó ese mismo día y esa frase
dejó de ser cierta para una parte del roster. Esta tabla separa, **con la cifra que lo prueba**,
lo que hoy es construible de lo que sigue bloqueado. Sin ella, 15 deseos parecen 15 tareas.

Toda cifra de abajo está **MEDIDA** contra `trades.db` y `data/` el 2026-07-25 (no recordada).
Lo etiquetado SOSPECHADO es lo único que no se verificó.

---

## Los hechos de datos, medidos hoy

| Hecho | Cifra MEDIDA | Cómo se midió |
|---|---|---|
| Barras 1m de equity | **8.950.177 filas · 540 sesiones · 2024-07-25 → 2026-07-24 · 30/30 syms** | `select count(*), count(distinct date(ts/1000,'unixepoch')) from poly_bars` |
| Cobertura por símbolo | **26/30 con ≥512 sesiones**; huecos: **SNDK 376, SPCX 388, DRAM 78, SKHY 10** | `group by sym` sobre `poly_bars` |
| Cadenas archivadas con griegas | **1 sola fecha (2026-07-25)** · 30/30 syms · **3.734 contratos** · griegas **97,5%** · OI **100%** | `data/history/2026-07-25/chain_full_*.json` |
| Forma de esa cadena | **banda ±4,5%, `dte_max=10`** — NO es la cadena completa | `meta` de `chain_full_qqq.json` |
| `data/backfill_report.json` | **NO EXISTE** | `ls` |
| Tabla `iv_hist` | **NO EXISTE** en `trades.db` | `sqlite_master` |
| Tabla `gex_cube` | **NO EXISTE** en `trades.db` | `sqlite_master` |
| 0.25Δ dentro de la banda traída | **16 de 30 símbolos** | barrido de `greeks.delta` sobre el archivo del 25 |

**El `ts` de `poly_bars` está en milisegundos.** `date(ts,'unixepoch')` devuelve `NULL` para las
540 sesiones y una consulta que lo ignore concluye "no hay datos" sobre 8,95 M de filas. Queda
escrito aquí porque es exactamente la clase de cero plausible que la casa prohíbe.

---

## La tabla — 15 features

| # | Feature | Ola | Estado | La cifra que lo decide |
|---|---|---|---|---|
| 4 | `poly-aggs-backfill` | 2 | **SATISFECHA** (ya construida) | 540 sesiones × 30 syms ya en `poly_bars`. Pendiente: `backfill_report.json` no existe, así que la **regla de gobernanza no tiene su artefacto** y 4 syms van cortos |
| 7 | `chain_full_snap` | 2 | **CONSTRUIDA, día 1 de acumulación** | 1 fecha archivada. Todo consumidor que pida ≥2 fechas está bloqueado por el calendario, no por código |
| 8 | **`level-react`** | 2 | **SATISFECHA** | Cero dependencia de opciones en tiempo de señal. 33 `bars_*_ibkr.txt` + 30 `levels_*.json` + 44 `nbbo_*.txt`; sustrato de replay = 540 sesiones |
| 19 | `cube-widening` | 2 | **BLOQUEADA** | Su paso 1 es *medir el techo real de líneas de market-data de la cuenta viva*. Exige TWS vivo + flota corriendo; la flota está parada a propósito |
| 20 | `vol-trigger` congelado | 2 | **CONSTRUIDA** (commit `04b9fcf`) | — |
| 21 | `wall-decay ledger` | 2 | **BLOQUEADA para medir** — forward-only | Los niveles de muro de sesiones pasadas **no se reconstruyen** (no hay OI histórico). Celda pide `n ≥ 40` clusters-día; hay 1 día |
| 23 | `cor-fleet` | 2 | **SATISFECHA — desbloqueada hoy** | `pct_60d` exigía 60 sesiones de `rho_real`; hay **540**. Era el único bloqueo |
| 25 | `expiry-unwind` | 2 | **BLOQUEADA** | Pide cuotas sobre **todos** los expiries; el archivo topa en `dte_max=10`. Y `n ≥ 50` expiries contra 1 día archivado |
| 26 | `gap-islands` | 2 | **SATISFECHA** | Solo barras. 540 sesiones dan ATR14 diario y hacen medible el barrido de `k_on ∈ [0.3, 3.0]` |
| 27 | `kde-levels` | 2 | **SATISFECHA** | Solo barras. 540 sesiones permiten correr su test de muerte (¿bate a `POC_DOM` + PDH/PDL?) |
| 29 | `peer-weights hardening` | 2 | **SATISFECHA** | `peer_weights` tiene 19 filas ajustadas sobre ≤21 días; ahora hay 540 sesiones para re-ajustarlas **con el null correcto** |
| 30 | `finviz-snap archive` | 2 | **BLOQUEADA** (acceso, no datos) | La historia de short-float no existe y el archivo es la feature; requiere credencial Finviz Elite + job nocturno |
| 22 | `chain-delta engine` | 3 | **BLOQUEADA** | Pide pares de snapshots de **5 minutos**; `gex_cube` no existe como tabla y hay 1 snapshot/día. Su pre-puerta de spot congelado no se puede correr |
| 24 | `close-drift` | 3 | **BLOQUEADA** | Su validación-primero compara contra `drift_target(13:30)` sobre `n ≥ 120` sym-sesiones. El único snapshot del día es de las **16:20**; no existe cadena de las 13:30 en ninguna sesión |
| 28 | `skew-lead` | 3 | **BLOQUEADA — y lo publica** | `iv_hist` no existe; `z` pide 60 sesiones y hay 1. Además el 0.25Δ solo cae dentro de la banda en **16/30** syms |

**Recuento: 5 satisfechas y construibles hoy (8, 23, 26, 27, 29), 2 ya construidas (4, 7),
1 construida antes (20), 7 bloqueadas.**

---

## Qué dato exacto desbloquea cada bloqueada

| # | Desbloqueo exacto | Cuándo |
|---|---|---|
| 19 | Una sesión con TWS vivo y la flota corriendo, para medir líneas de market-data y el ciclo antes/después | Próxima ventana de mercado |
| 21 | 40 clusters-día por celda de `(tipo × touch_idx × régimen × health)` sobre muros archivados | 6-12 meses (estimación de la propia ficha) |
| 25 | `chain_full_snap` sin tope `dte_max`, más ~50 expiries archivados | ~12 meses tras ampliar la banda |
| 30 | Credencial Finviz Elite + job nocturno a las 20:00; luego 40 días-candidato archivados | ~2 meses tras el primer archivo |
| 22 | Snapshots de cadena cada 5 minutos intradía persistidos en `gex_cube` | Requiere el daemon de cubo corriendo en RTH |
| 24 | Un snapshot de cadena **a las 13:30** en ≥120 sym-sesiones | ~6 meses de archivo a las 13:30 |
| 28 | `iv_hist` con 60 sesiones **y** una banda que contenga el 0.25Δ en más de 16/30 syms | 2027, según la propia ficha |

Ninguna de estas siete se finge. No se les escribe un `0.0`, un `0.5` ni un `{}`: la que se
construya publica `null` con motivo, o no se construye.

---

## Lo que esta tabla NO reabre

Los 16 muertos de `docs/FEATURES-MINED-2026-07-25.md` siguen muertos. El backfill de barras
**no** resucita a ninguno: `signed-oi` murió por `open_frac ≈ 0.01` (no por falta de barras),
`vanna-ramp` por dos inputs muertos, `trendline-engine` por coste y redundancia. La única que la
ficha marcaba como reabrible tras el backfill es `expansion-clock`, y **solo** como veto de
compresión sin probabilidad — no se reabre en esta ola.
