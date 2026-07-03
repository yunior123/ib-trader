---
name: peer-captain-evidence
description: "La evidencia detras de la jerarquia de capitanes: correlacion realizada de 1m como variable de estado (la implicita seria un proxy del VIX con 6 de 30 nombres) y lead_min valido solo si sobrevive al null de timestamps mezclados y al control de factor comun sobre residuos. Usar antes de afirmar que un ticker lidera a otro, al usar peer_weights, o al proponer niveles prestados, ratios o zonas ciegas."
---

# peer-captain-evidence — que sabemos DE VERDAD sobre quien lidera a quien

La regla 12 (SPY/QQQ = mercado, SMH = semis, el capitan prevalece) es **DOCTRINA**, y funciona.
Esta skill separa lo que es doctrina de lo que seria una **afirmacion medida** — porque tres
features quisieron construir sobre un lead-lag que no esta medido.
Fichas 23 y 29 + los muertos #10, #11, #12 de `docs/FEATURES-MINED-2026-07-25.md`.

## 1. El estado de la evidencia, sin adornos

```
trades.db peer_weights:  19 FILAS EN TOTAL
ajustadas sobre ≤21 sesiones de barras 1m entre activos con ρ ~ 0.8
```
> **Los picos de correlacion cruzada a lag no-cero entre activos co-movientes cotizados de forma
> ASINCRONA son el resultado espurio de libro de texto.** Con 19 filas y ρ~0.8, `lead_min`
> probablemente mide **RANCIDEZ DE COTIZACION**, no liderazgo.

Y **anticipar desde un lag espurio es el modo de fallo mas caro posible**: entras temprano, en la
direccion equivocada, con conviccion.

## 2. Como se mide un lead de verdad (y por que casi nada sobrevive)

1. Retornos de 1 minuto **inner-joined por epoch**, con la **tasa de descarte publicada por par**.
2. `corr` con errores estandar **HAC (Newey-West, lag 5)** y t-stats. La autocorrelacion de los
   retornos 1m infla los t-stats OLS.
3. `lead_min` de la correlacion cruzada aceptado **SOLO si el pico sobrevive AMBOS**:
   - **(a)** un null de **1000× timestamps barajados**;
   - **(b)** un **CONTROL DE FACTOR COMUN**: regresar **ambas patas** sobre SMH y QQQ primero, y
     cross-correlacionar **LOS RESIDUOS**. Sin esto, dos semis que suben juntos porque el sector
     sube producen un pico a lag no-cero **por construccion**.
4. `beta` por OLS sobre retornos **residualizados**, con `n` y `R²`.
5. **PUBLICAR CUANTOS PARES SOBREVIVEN.** Expectativa honesta: **0-2 de 19**.

> **El exito es un numero creible, INCLUIDO EL CERO.**

**Decision rule**: cualquier consumidor (amortiguador del capitan, niveles prestados, ideas de
ratio) puede usar **SOLO** pares con `lead_survives=1`.

> **Si CERO pares sobreviven, `governing_captain()` sigue siendo una regla de DOCTRINA
> (SPY/QQQ = mercado, SMH = semis) SIN ninguna afirmacion de lead medido adjunta — y lo decimos
> aqui en vez de inventar un numero.**

## 3. Las tres features que esta puerta RETIRA formalmente

| Feature | Por que muere |
|---|---|
`ratio-tape` (cinta de ratios capitan-vs-tropa) | descansa sobre las 19 filas; `lead_min` espurio |
`blind-spots` (clusters de niveles proyectados de peers) | igual, **y** con flota 26/30 semis los clusters pueden **reproducir los niveles del propio indice** |
`borrowed-map` (niveles gamma prestados del padre) | igual, **y encima LAVA UN VETO CONVIRTIENDOLO EN SEÑAL**: fabrica niveles gamma **exactamente para los nombres que [[book-quality-veto]] MUTEA**. Su decision rule (*"solo cuando el padre esta en el nivel del padre"*) **es literalmente la regla 12** |

`borrowed-map` es el caso mas instructivo del roster: una feature cuyo efecto neto era **deshacer
un veto de calidad de dato** y presentarlo como informacion nueva. Ver [[anti-overfit-killlist]].

## 4. `cor-fleet` — la correlacion REALIZADA como variable de estado

Esto SI se puede medir hoy, porque solo necesita barras.

```
rho_real = corr de Pearson media por pares de retornos 1m sobre los ultimos 60 min
           computada DOS VECES: componentes de QQQ  y  signal_conditioning.SEMIS
```
- **Inner-join de epochs** entre `data/bars_*_ibkr.txt` y **PUBLICAR la tasa de descarte**;
  **fail loud por encima del 20%** (los nombres iliquidos tienen agujeros).
- `pct_60d` = percentil de `rho_real` frente a sus propias 60 sesiones previas → **`NULL` hasta que
  el backfill provea 60 sesiones**; hasta entonces prior fijo **y etiquetado como tal**.

| Regimen | Condicion | `captain_coef` | `name_coef` | Operativa |
|---|---|---|---|---|
`MACRO` | `pct > 0.7` o `rho_real > 0.75` | **1.25** | 0.8 | **regla 12 a plena fuerza**: capitan opuesto **ANULA** la señal del nombre (banner, sin voz) |
`MIXED` | resto | 1.0 | 1.0 | doctrina normal |
`DISPERSION` | `pct < 0.3` o `rho_real < 0.45` | **0.75** | **1.2** | capitan opuesto solo **degrada DANGER a SIGNAL**; los niveles de nombre individual **SON** el edge |

**ELIMINADO**: `rho_imp` (correlacion implicita). `iv_atm` esta poblado para ~**6 de 30** nombres →
una version implicita seria **un proxy del VIX disfrazado**.

### Como entra en la flecha
**Amortiguador MULTIPLICATIVO** sobre los pesos EXISTENTES `fleet(1.4)` / `components(1.3)` —
**jamas un factor aditivo nuevo** ([[direction-view-architecture]]).
**El coeficiente aplicado DEBE imprimirse en `why[]`**: *"capitan ×1.25, rho 0.81"*. Una flecha
cuyos pesos se mueven con una variable de estado invisible es **inauditable tras una perdida**.

### Kill-risk que hay que vigilar
En una flota que es **26/30 semis**, `rho_real` puede estar por encima de 0.7 **todos los dias**,
dejando el amortiguador como una **constante** — en cuyo caso **es doctrina, no una variable de
estado**, y **debe hardcodearse honestamente como tal**. Eso tambien es un resultado.

Validacion: re-calificar las 972 señales unicas partiendo las de nombre por el **tercil de
`rho_real`** de ese dia. Keep el coeficiente dinamico solo si el acierto en `DISPERSION` excede el
de `MACRO` en **≥8pp** con Wilson corregido por `n_eff` **no solapados** y `n ≥ 100` por tercil.
Hoy subpotenciado (8 sesiones ≈ 3 dias de regimen) → **embarcar con el prior fijo** y revisar
post-backfill.

## 5. Lo que SI esta respaldado por evidencia (y como se cita)

| Afirmacion | Base | Como se dice |
|---|---|---|
Puts-flow masivo del capitan = rebote del grupo | evidencia de sesion (2026-07-18 SMH, 2026-07-22 SPY 14:21) + puts de indice corren estructuralmente altos por hedging | *"88% n=8"* — **con la n**, y es direccional, no ley |
Capitan prevalece sobre el nombre | 2026-07-22 NVDA calls + SPY puts → la de NVDA sin efecto; MU calls + SMH puts → manda SMH | doctrina con casos, no un lead medido |
Corea lidera ~13h a memoria/foundry | estructura de mercado (KRX cierra antes), no cross-correlacion ajustada | doctrina de calendario |
SPY-vs-SMH entre si | **SIN evidencia medida** | prob explicita baja + anotar el caso en el ledger cuando ocurra |

## 6. Al hablar

> *"MU calls-flow, pero SMH puts vigente → manda el capitan (doctrina regla 12, n=8 en la ley (a)).
> `rho_real` 0.81 → **MACRO**: la señal de MU queda anulada, banner sin voz, capitan ×1.25.
> Sin afirmacion de lead: `peer_weights` tiene 19 filas y 0 pares sobreviven al null."*

Ver [[flow-captains]] para la operativa, [[measured-probability]] para los `n`,
[[alert-budget]] para el efecto sobre la voz.
**SEÑAL-SOLAMENTE.**
