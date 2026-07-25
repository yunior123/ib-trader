---
name: sample-integrity
description: "Integridad de la muestra: warmup_sym reescribe dos dias de velas 1m que la calibracion luego lee, la cinta firmada de ballenas se trunca cada 15 minutos, el cubo de opciones solo vive en ficheros planos y levels.json es un snapshot al dia; archivar ANTES de medir, con SHA de velas, exclusion data_adjusted y retencion declarada. Usar antes de cualquier backtest, al crear una tabla nueva, o al tocar ibkr_bar_bridge y chart_bridge."
---

# sample-integrity — si la muestra se reescribe, el numero es ficcion

Cuatro agujeros medidos por los que se escapa la verdad **antes** de que ninguna estadistica
empiece. Ninguna correccion de Wilson salva una muestra que cambio bajo los pies.
Fichas 9, 15, 16 y 18 de `docs/FEATURES-MINED-2026-07-25.md`.

## 1. Los cuatro agujeros

| # | Agujero | Medido |
|---|---|---|
1 | **`warmup_sym()` en `ibkr_bar_bridge.py` TRUNCA Y REESCRIBE dos dias de barras 1m** que la calibracion lee despues | `data/bars_<sym>_ibkr.txt` ≈ 1690 filas ≈ 2 sesiones. **Nadie sabe que fraccion de nuestro WR medido se computo sobre datos que luego cambiaron** |
2 | **La cinta firmada de ballenas se DESTRUYE cada 15 minutos** (`cut = now-900`) | `data/whale_<sym>.txt` es la **UNICA** cinta firmada que poseemos (`EPOCH PX USD DIR`). Sin archivo, la absorcion no se puede testear NUNCA |
3 | **El cubo de opciones solo vive en ficheros planos de 4 dias** | `data/history/<date>/opt_chain_<sym>_HHMM.txt` = **2140 ficheros, ~171k filas** el 2026-07-24 |
4 | **`levels.json` es UN snapshot al dia** | ninguna feature condicionada por gamma se puede backtestear **en tiempo de etiqueta** |

Regla que sale de los cuatro: **ARCHIVAR ANTES DE MEDIR.** El archivador es barato; la muestra
perdida no se recupera a ningun precio.

## 2. `truth-lock` — el candado de repintado

1. En cada emision de señal, congelar el contexto: `spot`, `nbbo bid/ask`, set de niveles,
   `force.json`, `regime`, y **`bars_sha` = SHA-1 sobre las ultimas 120 barras CERRADAS**
   serializadas `epoch|o|h|l|c|v`.
2. Watchdog de **30 s** recomputa `bars_sha` sobre **la MISMA ventana de epochs**.
3. **FILTRO DE MATERIALIDAD (obligatorio, o se vuelve fatiga)**: un cambio cuenta solo si el
   `o/h/l/c` de una barra **cerrada** difiere en **>1 tick** o su volumen en **>1%**. Los backfills
   benignos del SIP no deben disparar nada.
4. Ante cambio material:
   - `signals.data_adjusted=1` → **`calibration_ledger` EXCLUYE esas filas**;
   - **banner + push ntfy, NO voz DANGER** (un backfill benigno entrenaria a Yunior a ignorarla);
   - **DESARMAR** cualquier ticket armado de `order_engine` para ese sym (re-armar exige doble
     llave — ganancia neta de seguridad bajo la ley señal-solamente).
5. Todo artefacto (pagina de PDF, overlay del chart, flecha) lleva `lock_ts`, y el cockpit dibuja
   la **linea vertical de verdad**. Candado rojo/azul en `charts/live.html`.

**Decision rule**: `adjusted=1` para un sym → **NO-TRADE en ese sym hasta re-lock** (no-trade es
una posicion, regla 6). Todo backtest que toque ventanas ajustadas **IMPRIME el conteo excluido** —
jamas las incluye en silencio.

**Validacion por INYECCION**: reescribir una barra en una **copia** del fichero y afirmar deteccion
dentro de un ciclo de watchdog. Luego medir la incidencia real sobre 30 sesiones. El **subproducto**
— el % de WR medido computado sobre datos que luego cambiaron — **justifica la construccion incluso
con incidencia cero**.

## 3. `equity-prints archiver` — 5 lineas que salvan la cinta

**INMEDIATAMENTE ANTES** del trim existente en `ibkr_bar_bridge.py`, **append** las lineas que se
van a `data/history/prints/<date>/prints_<sym>.txt`.

- **Append de fichero plano, NO un insert sqlite.** Un `fsync` dentro del tick handler pondria
  latencia en **el daemon mas load-bearing del sistema**. Retraso = dinero.
- Cargador batch separado a las **16:30** → `trades.db equity_prints(ts, sym, px, usd, dir)`,
  retencion 180 dias, luego gzip del dia.
- **Cobertura HONESTA, publicada por sym**:
  - `WHALE_MIN_USD=50000` → esto es un **perfil de BALLENAS, no volume-by-price**;
  - `DIR` se clasifica contra un **NBBO cacheado localmente** → **mala clasificacion por rancidez**;
  - **`whale_aapl/amd/asml/gld.txt` son 0 BYTES** porque tick-by-tick solo corre para syms de foco.
- **NINGUN motor de absorcion hasta ≥20 sesiones archivadas** para un sym. Solo entonces se testea
  `ABS(b) = neg(b) / (|Δprice_in_cell|/ATR + 0.1)` contra un null de **1000× barajado de signos**.
- Prior honesto: whale h=15 WR **0.357, n=112, Wilson [0.28, 0.45]**. Es pobre. El archivo es un
  seguro barato, no una promesa.

**Validacion de ops**: reconciliacion de conteo de filas vivo↔archivo (cero perdida) y **cero
latencia añadida medible** en el bridge (jitter de llegada de barras sobre 3 sesiones).

## 4. `chain-cube archive` + la politica de retencion

Cargador batch a las **16:20** → `trades.db gex_cube(sym_id, ts, exp, strike, right, oi, vol, iv,
delta, gamma)` con indice en `(sym_id, ts)`.

| Dato | Retencion (DURA, no negociable) |
|---|---|
filas crudas por-strike de `gex_cube` | **30 dias** |
colapso `gex_snap(sym, ts, gross, net, hhi, com, flip, call_wall, put_wall, turn_max, vol_hhi)` | **indefinido** |
ficheros de texto fuente | gzip tras la carga, borrado a **45 dias** |
`equity_prints` | 180 dias · `level_events` 180 · `signal_context` 90 · `levels_5m` 90 |
`iv_hist` | indefinido (~90 filas/noche) |

**Aserciones de presupuesto que fallan en voz alta y ABORTAN el cargador**: `trades.db > 400 MB`
(las barras 1m viven en un **`bars.db` adjunto separado**) o `data/history > 3 GB`.
Estado medido: `trades.db` 59 MB, `data/` 157 MB, `data/history` 32 MB para 4 sesiones →
**~1 GB/mes de cubo** si se deja sin limite.

> **Toda tabla nueva propuesta SIN politica de retencion declarada se rechaza en review.**
> **Toda consulta de calibracion que pase de 2 s dispara un ROLLUP, no un indice nuevo.**
> Tras la carga, **ninguna feature lee los ficheros de texto planos directamente** — fuente unica.

`calibration_ledger.grade()` debe quedarse **<2 s**. El cockpit vivo manda: si el cubo lo ralentiza,
va a un `options.db` adjunto desde el dia uno.

## 5. `levels-5min archive` — el enabler, con puerta de coste MEDIDA

Append cada 5 minutos a `data/history/<date>/levels_5m.jsonl`:
`{ts, sym, spot, flip_open, flip_live, flip_src, regime, net_gex, gross, hhi, call_wall, put_wall,
abs_wall, abs_wall_sign, em_hi, em_lo, iv_atm, book_label, vt_open}`.

> **MEDIR PRIMERO, mergear despues.** `chart_bridge` son **53 MB**, la caja esta **1.14 GB dentro
> del swap con ~88 MB de paginas libres**. Delta de RSS y latencia por loop sobre **3 sesiones**
> ANTES de mergear. **Si el coste pasa de +5 MB RSS o +20 ms/loop, el escritor se mueve a un cron
> separado de 5 minutos** en vez del daemon WS. La puerta de coste es **dura, no una formalidad**:
> es añadir trabajo al daemon Python **menos prescindible** de la caja.

**Decision rule**: **ninguna feature puede condicionar sobre estado gamma en tiempo de etiqueta
hasta que este archivo tenga ≥40 sesiones.** Es exactamente por esto que `stability-10` fue
**MATADA** en vez de degradada: **sus features no existian en tiempo de etiqueta.**

Datos: ≥**70 snapshots/sesion** (09:30-16:00 cada 5 min) con **<2% de huecos**.

## 6. Checklist antes de cualquier backtest

1. ¿La fuente de barras la reescribe alguien? (`warmup_sym` lo hace.) ¿Hay `bars_sha`?
2. ¿Se excluyen las filas `data_adjusted=1` **y se imprime el conteo excluido**?
3. ¿Las features que condiciono existian **en tiempo de etiqueta**, o las estoy leyendo del
   snapshot de hoy? (Este es look-ahead silencioso, el peor.)
4. ¿La muestra es **archivada** o **reconstruida**? Si es reconstruida, ¿esta marcada como tal en
   la cabecera del fichero?
5. ¿Cuantas sesiones hay **de verdad**? (`poly_bars` = 21. Ver [[measured-probability]] §7.)
6. ¿La tabla nueva tiene retencion declarada y el cargador aborta si revienta el presupuesto?

## 7. Al hablar

- *"n=822 pero 41 filas excluidas por `data_adjusted`"* — el conteo excluido se dice siempre.
- *"cobertura de cinta: MU 12 sesiones, AAPL 0 bytes (sin tick-by-tick)"* — nunca asumir cobertura
  de flota completa.
- **SEÑAL-SOLAMENTE**: los archivadores solo escriben ficheros; no ordenan.
