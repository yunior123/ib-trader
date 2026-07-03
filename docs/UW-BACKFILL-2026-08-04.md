# UW-BACKFILL — 91 sesiones de flujo intradía descargadas y verificadas

**Fecha**: 2026-08-04, 02:55–03:35 ET (mercado CERRADO; última sesión completa 2026-08-03).
**Código**: `scripts/uw_flow_archive.py --backfill --days N` · tests `tests/test_uw_flow_archive.py`.
**Documentos padre**: `docs/UW-FLOW-RECON-2026-08-04.md` (69 rutas) y `docs/UW-NOVEDADES-2026-08-04.md`
(199 rutas). **Ninguno de los dos se ha tocado.**
**Credencial**: `UW_TOKEN` vía `uw_premium.token()`. **No aparece aquí, ni en el código nuevo, ni
en ningún log.**

**SEÑAL-SOLAMENTE.** Esto archiva bytes. No dispara, no vota, no ordena.

---

## 0. Lo que hay que saber en 6 líneas

1. **La muralla es real y la medí yo, no la copié**: `?date=2026-03-24` → **200**;
   `?date=2026-03-23` → **403 `historic_data_access_missing`**. El informe anterior acertaba.
2. **Descargadas 91 sesiones × 5 símbolos × 3 series = 1.365 ficheros. Cobertura 1.365/1.365.**
   **Cero huecos. Cero fallos. Cero sesiones perdidas.**
3. **Coste real: 1.320 peticiones.** Cupo del día **749 → 2.103 de 30.000 = 7,0 %**.
   La estimación de 8.100 del recon era para 30 símbolos; con `DEFAULT_SYMS` (5) son 1.350.
4. **500.312 filas, 247 MB**, en `data/history/<sesión>/uw_<serie>_<sym>.json`.
5. **El daemon `com.ibtrader.uwflowarchive` no se tocó** y sigue vivo (pid 91407, desde 02:40).
   El backfill corrió en paralelo compartiendo cupo, escalonado a 0,7 s/petición.
6. **La premisa `forward-only` del primer recon queda muerta por escrito.** Las 3 alertas se
   pueden medir esta semana. Lo que NO cambia: la validación estadística sigue siendo la
   restricción (BH-FDR, DSR/MinTRL, `n_eff`), y el look-ahead del backfill es un peligro nuevo (§5).

---

## 1. La muralla, medida por mí

Sonda propia contra `/api/stock/SPY/net-prem-ticks?date=`, una petición por fila:

| días atrás (calendario) | fecha | HTTP | filas | lectura |
|---|---|---|---|---|
| 30 | 2026-07-05 | **200** | **0** | domingo → vacío honesto, no cero fabricado |
| 60 | 2026-06-05 | **200** | **405** | sesión completa |
| 90 | 2026-05-06 | **200** | **405** | sesión completa |
| 100 | 2026-04-26 | **200** | **0** | domingo |
| 200 | 2026-01-16 | **403** | — | `historic_data_access_missing` |

Borde exacto, cuatro peticiones más:

| fecha | HTTP | filas | `date` del propio dato |
|---|---|---|---|
| 2026-03-26 | 200 | 405 | 2026-03-26 |
| 2026-03-25 | 200 | 405 | 2026-03-25 |
| **2026-03-24** | **200** | **405** | **2026-03-24** ← la pared |
| **2026-03-23** | **403** | — | *«The earliest date currently available to you is 2026-03-24 (90 trading days)»* |
| 2026-03-20 | 403 | — | idem |

**El informe anterior no se equivocó.** Se confirma sin corrección: la fecha más antigua realmente
disponible es **2026-03-24**, y el servidor la declara él mismo. Re-probado a las 03:33, después de
todo el backfill: **sigue siendo 403 para el 23**.

**Lo que el recon NO había medido y sí hacía falta**: que `?date=` funcione en **las tres** series,
no solo en `net-prem-ticks`. Medido sobre 2026-06-05:

| serie | ruta | HTTP | filas | día del dato |
|---|---|---|---|---|
| `net_prem_ticks` | `/api/stock/SPY/net-prem-ticks?date=` | 200 | 405 | 2026-06-05 ✅ |
| `greek_flow` | `/api/stock/SPY/greek-flow?date=` | 200 | 405 | 2026-06-05 ✅ |
| `flow_per_strike` | `/api/stock/SPY/flow-per-strike?date=` | 200 | 434 | 2026-06-05 ✅ |

Control sin `?date=` en el mismo momento: ambas devuelven la sesión del **2026-08-03**. O sea,
`?date=` **se obedece**, no se ignora. Ésa es la condición que hacía falta comprobar antes de
gastar 1.300 peticiones: si el parámetro se ignorase en silencio, el backfill habría archivado
91 copias de la misma sesión bajo 91 fechas distintas — y ningún backtest posterior lo notaría.
Por eso el guard de §4 es una condición dura del código, no un comentario.

**Si la pared es RODANTE o FIJA sigue sin saberse** (pregunta abierta nº 2 del recon). Se resuelve
con 1 petición dentro de una semana (`?date=2026-03-24` → ¿200 o 403?). **Asumo que rueda**, que es
la hipótesis segura, y por eso el backfill se hizo hoy y no «cuando haya tiempo».

---

## 2. Coste real, medido en dos etapas

### Muestra de 3 sesiones antes de soltar el completo (como se pidió)

| | |
|---|---|
| celdas pedidas | 45 (3 sesiones × 5 syms × 3 series) |
| ya en disco (daemon del 08-03) | 15 |
| **peticiones reales** | **30** |
| cupo `x-uw-daily-req-count` | **719 → 748** |
| **coste medido por celda** | **1,00 petición** (30 celdas, 29-30 de delta) |

**Extrapolación hecha con ese número**: 91 sesiones × 5 syms × 3 series = 1.365 celdas − 45 ya
hechas = **1.320 peticiones**. Cupo previsto al terminar ≈ 2.070. **Muy por debajo del freno del
60 %** (18.000), así que se lanzó el completo.

### Ejecución completa

| | |
|---|---|
| `x-uw-daily-req-count` al empezar | **749** |
| **al terminar** | **2.103** |
| peticiones del backfill | **1.320** |
| delta de cupo | 1.354 (los ~34 de diferencia son el **daemon** capturando en paralelo + mis sondas) |
| **% del cupo diario** | **7,0 %** de 30.000 |
| duración | **1.252 s** (20,9 min) a 0,7 s de escalonado |
| predicho vs real | **1.320 vs 1.320 — exacto** |
| cupo al cerrar la sesión de trabajo (03:40, con sondas de verificación) | **2.119 = 7,1 %** |

**La extrapolación de 3 días acertó al 100 %.** El coste es lineal y sin sorpresas: **1 petición =
1 sesión-símbolo-serie completa** (los ~400 minutos vienen en esa única llamada).

**Coste de repetir el backfill entero ahora: 0 peticiones.** Verificado: re-lanzado con las mismas
91 sesiones, informa *«1.365 celdas, 0 pendientes»* y no toca la red.

---

## 3. Tabla de cobertura — 1.365/1.365

`ok` = fichero presente, `n == len(rows)` y el día del DATO coincide con la carpeta.
`filas/ses` = **mediana** de filas por sesión.

| serie | sym | ok | hueco | falta | filas/ses (mediana) | mínimo (sesión) | máximo |
|---|---|---|---|---|---|---|---|
| `net_prem_ticks` | SPY | **91** | 0 | 0 | 405 | 405 (03-24) | 407 |
| `net_prem_ticks` | QQQ | **91** | 0 | 0 | 405 | 405 (03-25) | 409 |
| `net_prem_ticks` | SMH | **91** | 0 | 0 | 405 | 401 (04-06) | 407 |
| `net_prem_ticks` | NVDA | **91** | 0 | 0 | 390 | 390 (03-24) | 393 |
| `net_prem_ticks` | MU | **91** | 0 | 0 | 390 | 390 (03-24) | 392 |
| `greek_flow` | SPY | **91** | 0 | 0 | 405 | 405 | 407 |
| `greek_flow` | QQQ | **91** | 0 | 0 | 405 | 405 | 409 |
| `greek_flow` | SMH | **91** | 0 | 0 | 405 | 401 | 407 |
| `greek_flow` | NVDA | **91** | 0 | 0 | 390 | 390 | 393 |
| `greek_flow` | MU | **91** | 0 | 0 | 390 | 390 | 392 |
| `flow_per_strike` | SPY | **91** | 0 | 0 | 394 | 341 (04-23) | 452 |
| `flow_per_strike` | QQQ | **91** | 0 | 0 | 381 | 317 (03-25) | 460 |
| `flow_per_strike` | SMH | **91** | 0 | 0 | 210 | 118 (03-31) | 239 |
| `flow_per_strike` | NVDA | **91** | 0 | 0 | 206 | 167 (07-09) | 269 |
| `flow_per_strike` | MU | **91** | 0 | 0 | 353 | 205 (04-02) | 441 |

**Totales**: 1.365 ficheros · **500.312 filas** · **247,3 MB** · sesiones **2026-03-24 → 2026-08-03**.

**Procedencia (declarada en cada fichero, no adivinada)**: **1.350 `source:"backfill"`** + **15 sin
`source` = capturados EN VIVO por el daemon** (los del 2026-08-03, que el backfill respetó y no
sobreescribió).

### Lectura honesta de los números de fila

- **`net_prem_ticks` y `greek_flow` son series de MINUTO**: 405 (SPY/QQQ/SMH) y 390 (NVDA/MU) por
  sesión, **planas en las 91 sesiones**. La diferencia 405 vs 390 no es un hueco: es que los ETF
  traen ~15 minutos extra de cinta fuera de RTH y los nombres no. Ninguna sesión aparece truncada.
- **`flow_per_strike` NO es una serie de minuto**: es una fila por **strike**, así que su recuento
  varía con la anchura de la cadena (118 en SMH un día tranquilo, 460 en QQQ un vencimiento
  gordo). Comparar su `n` entre sesiones no significa nada; se dice aquí para que nadie construya
  un percentil sobre eso.
- **No hay ninguna sesión sospechosamente corta.** El mínimo absoluto de las series de minuto es
  401 (SMH, 2026-04-06), un 1 % por debajo de la mediana. No hay medias sesiones mutiladas.

---

## 4. Qué falta y por qué — la respuesta es «nada, dentro del alcance pedido»

| Categoría | Cuántas | Motivo |
|---|---|---|
| **Sesiones con 0 filas (HUECO)** | **0** | Ninguna sesión del rango devolvió 200 vacío |
| **403 dentro del rango** | **0** | La pared cae justo fuera: 2026-03-24 es la primera sesión y respondió 200 |
| **Fallos de forma / red** | **0** | `data/uw_backfill_report.json` → `"fallos": []` |
| **Festivos y fines de semana** | los que haya | **Nunca se pidieron**: `em_envelope.is_market_day()` los filtra ANTES de gastar la petición. Cero peticiones desperdiciadas |

**Hallazgo lateral que merece decirse**: la tabla de festivos de la casa (`em_envelope.HOLIDAYS`)
**coincidió con el calendario del vendor en las 91 sesiones**. Si hubiera sobrado un festivo, UW
habría devuelto 200 con 0 filas y habría quedado marcado como HUECO. No pasó ni una vez. Es una
verificación cruzada gratis del calendario, y salió limpia.

**Fuera del alcance de este encargo, por si se pide después** (con su coste medido en peticiones):

| Ampliación | Peticiones | % de un día de cupo |
|---|---|---|
| Los otros 25 símbolos de `data/fleet.txt`, 91 sesiones × 3 series | **6.825** | 22,8 % |
| `ohlc/1m` (el etiquetado de triple barrera), 5 syms × 91 | **455** | 1,5 % |
| `ohlc/1m` para los 30 de la flota | **2.730** | 9,1 % |
| `group-flow/{semi,mag7}/greek-flow`, 91 sesiones | **182** | 0,6 % |
| `greek-flow/{expiry}` 0DTE + semanal, 5 syms × 91 × 2 | **910** | 3,0 % |

Todo eso junto son **~11.100 peticiones = 37 % de UN día**. **El cupo nunca fue la restricción**, y
ahora está medido en vez de estimado.

---

## 5. Los tres peligros que introduce este archivo, dichos en voz alta

1. **Look-ahead silencioso.** Lo descargado hoy es el estado **final** de aquella sesión, no lo que
   se veía en vivo. UW tiene `canceled` y añadió *«nullified/modified trade indicator to historical
   data»* (changelog 2025-08-07). **Mitigación implementada**: cada fichero de backfill lleva
   `source:"backfill"` + `pull_date` + `session_date`, y los del daemon **no** llevan `source`. Un
   backtest que mezcle los dos sin declararlo está mintiendo, y ahora el dato mismo lo delata.
   **Lo que sigue sin comprobarse**: si los campos se reescriben. Se resuelve bajando la misma
   sesión dentro de una semana y difiando byte a byte (15 peticiones).
2. **Multiple testing.** 91 sesiones no son licencia para barrer 30 features. Sigue rigiendo
   BH-FDR q=0,10 + DSR/MinTRL, y la corrección por correlación de `n_eff` (ρ̄ = 0,412 medido en el
   recon). Con 5 símbolos correlacionados, 91 sesiones **no** son 455 observaciones independientes.
3. **La muestra es de 5 símbolos, no de 30.** La ALERTA 1 (`CAPITAN-CONTRA-TROPA`) del recon
   necesita la tropa entera para su denominador; con `DEFAULT_SYMS` **no se puede medir todavía**.
   La ALERTA 2 (`VEGA-AGRESOR`, 5 símbolos) **sí**. No se afirme lo contrario.

---

## 6. Cómo se usa

```bash
# Backfill completo (idempotente: lo ya archivado no se vuelve a pedir)
./venv/bin/python scripts/uw_flow_archive.py --backfill --days 91

# Ver cobertura en disco sin gastar NI UNA petición
./venv/bin/python scripts/uw_flow_archive.py --backfill --days 91 --dry-run

# Ampliar a la flota entera, más despacio y con freno de cupo más bajo
./venv/bin/python scripts/uw_flow_archive.py --backfill --days 91 \
    --syms $(tr '\n' ',' < data/fleet.txt) --sleep 1.0 --max-quota-frac 0.5

# Una sola serie, un tramo concreto
./venv/bin/python scripts/uw_flow_archive.py --backfill --days 20 --end 2026-05-30 \
    --series greek_flow

# El daemon NO cambia: sigue siendo el modo por defecto, sin flags
./venv/bin/python scripts/uw_flow_archive.py
```

Reglas que el código impone (no son recomendaciones):

- **La fecha sale del DATO.** Si se pide `?date=2026-06-05` y el dato dice otro día, **se levanta y
  no se escribe nada**. El backfill es incapaz de archivar con la fecha del reloj.
- **0 filas = HUECO explícito** en `uw_<serie>_<sym>.HUECO`, extensión distinta a `.json` a
  propósito: ningún consumidor de `uw_*.json` puede confundir «no había dato» con «había dato».
  **Jamás se rellena.**
- **Reanudable**: un día ya archivado y validado se salta sin tocar la red. Un fichero corrupto,
  vacío o con otro día dentro cuenta como **ausente** y se rehace.
- **Un fallo nunca destruye lo bueno**: si la petición levanta (403, red, forma), no se escribe
  nada — ni el `.json` ni el `.HUECO`.
- **Freno de cupo**: para en `--max-quota-frac` (60 % por defecto) del `x-uw-daily-req-count` que
  informa el propio servidor, y se **niega a arrancar** si el plan supera `SAFETY_FRACTION` (50 %).
- **El 403 de PARED no se reintenta**: `historic_data_access_missing` levanta `WallError` al
  instante. Esperar 60 s no acerca marzo.

**Salida**: `data/uw_backfill_report.json` (cobertura, huecos, faltas, fallos, cupo inicio/fin).

---

## 7. Tests

`tests/test_uw_flow_archive.py`: **20 → 38** (los 20 originales intactos, 18 nuevos).

| Lo que se blinda | Test |
|---|---|
| `?date=` se parsea y se manda | `test_backfill_pide_la_fecha_en_query` |
| procedencia declarada en el fichero | `test_backfill_archiva_bajo_la_fecha_pedida_con_procedencia` |
| **el backfill no puede escribir con la fecha del reloj** | `test_backfill_NO_PUEDE_escribir_con_la_fecha_del_reloj` |
| ni con otro día pasado | `test_backfill_rechaza_dia_distinto_aunque_sea_pasado` |
| **un día ya archivado se salta sin pedir** | `test_dia_ya_archivado_no_gasta_peticion` |
| un hueco ya marcado tampoco se re-pide | `test_hueco_ya_marcado_tampoco_se_repide` |
| fichero corrupto = ausente, se rehace | `test_fichero_corrupto_cuenta_como_ausente_y_se_rehace` |
| fichero con otro día dentro no cuenta | `test_fichero_con_OTRO_dia_dentro_no_se_da_por_bueno` |
| 0 filas → HUECO, sin `.json` de datos | `test_cero_filas_marca_hueco_y_no_escribe_json_de_datos` |
| el HUECO es invisible para `uw_*.json` | `test_la_marca_de_hueco_no_la_ve_un_consumidor_de_uw_json` |
| **un 403 no borra lo bueno** | `test_403_no_borra_el_fichero_bueno` |
| un 403 en día virgen no escribe nada | `test_403_en_un_dia_sin_archivar_no_escribe_nada` |
| pared ≠ estrangulamiento, y no duerme | `test_fetch_distingue_403_de_pared_de_403_de_estrangulamiento` |
| hoy nunca entra en el plan | `test_sessions_back_por_defecto_no_incluye_hoy` |
| fines de semana y festivos fuera | `test_sessions_back_excluye_*` / `test_sessions_back_salta_festivos` |
| cobertura cuenta ok/hueco/falta | `test_coverage_cuenta_ok_hueco_y_falta` |
| la pared del código es la medida | `test_la_pared_medida_es_la_declarada_por_el_servidor` |

```
tests/test_uw_flow_archive.py  ->  38 passed
tests/ (suite completa)        ->  1695 passed, 7 failed, 38 skipped
```

Los **7 fallos son ajenos y previos**: `tests/test_notify_short.py` (3) y
`tests/test_discord_cobertura.py` (4, dependen del anterior). Fallan igual en aislamiento y
`notify_short.py`/`discord_*.py` son de otro agente — **no se han tocado**.

---

## 8. Lo que NO he hecho

- **No he tocado** `scripts/discord_*.py`, `scripts/backtest_*.py`, `scripts/uw_endpoint_probe.py`,
  `docs/UW-FLOW-RECON-*.md`, `docs/UW-NOVEDADES-*.md`, `docs/DISCORD-REFERENCIA-*.md`,
  `docs/FORENSE-LOGS-*.md`, `TODOS.md`.
- **Ningún git** (ni commit, ni checkout, ni revert). **Ningún proceso matado.** **Ningún C++
  compilado.** **TWS/Gateway sin lanzar.**
- **No he construido ninguna señal.** Esto es un archivo, no un motor. Las 3 alertas del recon
  siguen sin medir: ahora simplemente **hay muestra con la que intentarlo**.

**Ficheros modificados**: `scripts/uw_flow_archive.py`, `tests/test_uw_flow_archive.py`, este doc.
**Ficheros creados**: 1.350 `data/history/*/uw_*.json` + `data/uw_backfill_report.json`.
