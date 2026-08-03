# DAILY-SYSTEM — manual del operador del pipeline diario autónomo

*ib-trader · SEÑAL-SOLAMENTE · escrito 2026-07-21*

Este documento describe el sistema de **planes diarios autónomos**: un pipeline que
arranca a las 4AM, refresca hasta la apertura, y cierra el día calificándose a sí
mismo a las 16:20. **Jamás ejecuta órdenes** — solo genera mapas (PDF), correos,
posts de X educativos, y un loop de aprendizaje que mide sus propias probabilidades.

---

## 1. Visión general

```
04:00 ET  FULL      planes flota (26 tickers) → PDF + email + X + patrones + calib.record
08:30 ET  REFRESH   re-genera planes con datos frescos (tag REFRESH-8AM), sin re-postear
09:12 ET  APERTURA  10 tickers líquidos, mapa de apertura (tag APERTURA-912)
08:00-16:05        x_signal_poster (daemon aparte) postea señales fuertes en vivo
16:20 ET  EOD       calibration eod (grade+recalibrate) + postmortem X + docs
```

Tres capas apiladas, todas **aditivas** (si una falta, el resto sigue — ver §8):

1. **Generador** (`daily_fleet_plans.py`) — arma el plan pícaro por ticker.
2. **Calibración** (`calibration_ledger.py`) — cierra el loop: mide la probabilidad
   real por *tipo de setup*, no por ticker; el generador la lee.
3. **Patrones** (`pattern_detect.py`) — detecta figuras de chart y mide su
   follow-through empírico; es **capa de contexto, no gatillo**.

Encima, **3 posters de X** comparten un presupuesto y todos cierran cada post con
"No es consejo financiero".

---

## 2. Cronograma launchd

Cinco jobs de launchd (usuario, en `~/Library/LaunchAgents/`):

| Job | Plist | Disparo | Script |
|-----|-------|---------|--------|
| `com.ibtrader.dailyplans` | `com.ibtrader.dailyplans.plist` | 04:00, 08:30, 09:12 ET | `scripts/dailyplans_run.sh` |
| `com.ibtrader.postmortem` | `com.ibtrader.postmortem.plist` | 16:20 ET | `scripts/postmortem_run.sh` |
| `com.ibtrader.printpremarket` | `com.ibtrader.printpremarket.plist` | 09:12 ET, lun-vie | `scripts/print_premarket_trees.sh` → `data/print_syms_premarket.txt` |
| `com.ibtrader.printopen5` | `com.ibtrader.printopen5.plist` | 09:35 ET, lun-vie | `scripts/print_open5_spy_aapl.sh` → `data/print_syms_open5.txt` |
| `com.ibtrader.printpostmarket` | `com.ibtrader.printpostmarket.plist` | 16:25 ET, lun-vie | `scripts/print_postmarket_plans.sh` → `data/print_syms_postmarket.txt` |

Los tres jobs de impresión son envoltorios finos sobre el motor `scripts/print_plans.sh`
(`--syms-file` + `--trees` / `--envelope` / `--archive` / `--market-day` / `--print`). Reglas:

- **launchd no conoce los festivos** (`Weekday 1-5` es solo lun-vie): el filtro real es
  `--market-day`, que usa la tabla única `em_envelope.HOLIDAYS` (levanta si se agota, no
  asume "hoy sí hay mercado").
- **Fail-loud**: un símbolo sin `data/history/*/chain_full_<sym>.json` fresco (≤4 días) se
  SALTA, se canta por notificación y el job sale con código ≠0. Nunca se imprime un plan con
  niveles fabricados. `GLW/NBIS/BE` no están en `data/universe_gamma.txt`, así que el job de
  post-market lleva `--archive` y se trae su propia cadena antes de dibujar.
- **Papel**: `IBT_ALLOW_PRINT=1` o `--print` (orden Yunior 2026-07-27). Los tres jobs pasan
  `--print`; para correr en seco: `IBT_ALLOW_PRINT=0 ./scripts/print_plans.sh --syms-file ...`.

`RunAtLoad` es `false` en todos: solo corren en su horario, no al cargar. El modo
del job de planes lo decide `dailyplans_run.sh` según la hora (`$HM = date +%H%M`):

```zsh
HM < 0500  → MODE=FULL      ARGS=""                              (mapa gamma + planes completos + email + X + patrones + calib.record + verify del mapa)
HM < 0900  → MODE=REFRESH   ARGS="--tag REFRESH-8AM"             (solo re-genera planes; NO re-postea ni recalibra)
else       → MODE=APERTURA  ARGS="--tickers QQQ,SPY,NVDA,TSLA,MU,SMH,META,MSFT,AMD,NOK --tag APERTURA-912"
```

Solo el modo **FULL** corre `pattern_detect.py --fleet`, `calibration_ledger.py record`,
el **verify del mapa gamma** y `x_plan_poster.py`. REFRESH y APERTURA solo re-dibujan el mapa.

### El daemon de señales en vivo

`x_signal_poster.py` **no** es launchd — es un daemon de larga vida (loop 60s) que se
lanza aparte (keepalive/manual) y trabaja solo dentro de la ventana **8:00-16:05 ET**
en días hábiles. Verificá que esté vivo con `pgrep -f x_signal_poster`.

### Comandos launchctl

```bash
# Verificar que están cargados
launchctl list | grep ibtrader

# Instalar / recargar tras editar un plist (los plists viven en scripts/, se COPIAN a LaunchAgents)
cp ~/ib-trader/scripts/com.ibtrader.printopen5.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.ibtrader.printopen5.plist
launchctl load   ~/Library/LaunchAgents/com.ibtrader.printopen5.plist
# (idem dailyplans / postmortem / printpremarket / printpostmarket)

# Forzar una corrida AHORA (respeta el modo por hora en dailyplans)
launchctl start com.ibtrader.dailyplans
launchctl start com.ibtrader.postmortem
launchctl start com.ibtrader.printopen5      # en fin de semana sale por el portero, sin imprimir

# Apagar un job (deja de dispararse hasta recargarlo)
launchctl unload ~/Library/LaunchAgents/com.ibtrader.dailyplans.plist
```

---

## 3. `daily_fleet_plans.py` — el generador del plan pícaro

### Flota (26 tickers)

`QQQ, SPY, NVDA, TSLA, MU, SMH, AMD, AAPL, MSFT, META, AMZN, GOOGL, INTC, TSM,
ASML, TXN, QCOM, AVGO, NFLX, NOK, GLD, XLK, EWY, DRAM, SPCX, SKHY`.

Cada uno lleva metadata: `style` (`0dte` para QQQ/SPY, `weekly` el resto), `fut`
(NQ=F o ES=F) y `korea` (bool — si tiene lead coreano). `NOK` está marcado `no_gex_map`.

### Fuentes de la cadena de opciones (en orden)

1. **IBKR cache** — `data/opt_chain_<sym>.txt` (lo escribe `opt_chain_cache.py` con
   TWS vivo). Se usa **solo si tiene <45 min** de antigüedad. Es la cadena real.
2. **yfinance fallback** — si el cache falta o está viejo, baja la cadena de yfinance.
   El expiry se elige con `pick_expiry`: 0DTE → primer expiry ≥ hoy; weekly → primer
   viernes ≥ hoy.

El PDF marca `exp` con `IBKR✓` cuando usó la fuente 1.

### Qué calcula por ticker

- **Muros de OI** — top-4 calls (techos) y top-4 puts (pisos) por open interest,
  en la ventana ±3.5% del spot.
- **Max pain** — strike que minimiza el valor total de las opciones en el vencimiento.
- **GEX / flip propio** — gamma Black-Scholes × OI × 100 × S, calls (+) / puts (−);
  net GEX y el **flip** = strike donde el GEX acumulado cruza cero. Régimen NEGATIVO
  (dealers amplifican) si net GEX < 0, POSITIVO (dealers fijan) si > 0.
- **Griegas BS** — delta/gamma/theta/vega del ATM (`bs_greeks`, con `math.erfc`).
- **Overnight / gap-fill histórico** — gap %, expansión en ATRs, y sobre 3 meses:
  qué fracción de gaps similares hizo *dip de liquidez* de vuelta al cierre previo
  (fill_rate + n). Alimenta la "PROB DIP APERTURA".
- **Bollinger diario** — BB(20,2) y %B; veta cortos frescos si %B<0.12, largos si >0.88.
- **Ballenas** — tape propia `data/whale_<sym>.txt` (buys vs sells hasta 15:58).
- **Korea** — KOSPI / Samsung / SK-Hynix vía memoria/yfinance (solo tickers `korea=True`).
- **Futuros** — NQ=F y ES=F % overnight.
- **VX term structure** — VIX spot + futuros VX de CBOE (delayed ~15m); contango /
  backwardation → régimen de volatilidad (`vx_term`).
- **Finviz scout** — `data/finviz_<sym>.txt` (<36h): earnings, short float, target,
  RSI, rvol.
- **Árbol de escenarios** — página 2 del PDF: probabilidades ALCISTA / PIN / BAJISTA
  derivadas por reglas (régimen + P/C + Bollinger) con flechas hacia muros/imán.
- **Forma intradía** — serie 48h con pre/post-market (5m) dibujada bajo los muros.
- **mapa gamma MEDIDO** — si existe `data/gex_snapshot.json` (<36h **y** con `chain_date`
  de los últimos 5 días), el régimen gamma usa su flip/score/bias/POC, calculado en casa
  por `scripts/gex_snapshot.py` con las griegas REALES de Polygon sobre las cadenas
  archivadas. El PDF imprime la procedencia (fecha de cadena, nº de contratos, % de
  griegas usables). Sin mapa NO se afirma régimen: el plan lo marca ESTIMADO.
  (gexa.ai desapareció el 2026-07-25; el scrape por Chrome ya no existe.)

### Probabilidad medida (no adivinada)

`measured_prob(setup_type, regime, heuristic)` consulta `data/calibration.json`. Si el
bucket `(setup_type|regime)` tiene `trust=True`, reemplaza la heurística por el
**CI-low medido** (honesto, no la tasa central). Si hay muestra pero no fiable, avisa
"provisional". Si no hay datos, usa la heurística. Nada hardcoded.

### Salidas

- `~/Desktop/planes-YYYY-MM-DD/<SYM>_plan.pdf` — 3 páginas: (1) mapa de muros +
  griegas, (2) árbol de escenarios, (3) plan pícaro en texto.
- `~/Desktop/planes-YYYY-MM-DD/x_drafts/<SYM>.txt` — borrador para X.
- `~/Desktop/planes-YYYY-MM-DD/ranking.json` — `[{sym, score, dip, reg}]` ordenable.
- Email vía Resend con los PDF adjuntos (salvo `--no-email`).

### Flags

```bash
./venv/bin/python scripts/daily_fleet_plans.py \
    [--tickers QQQ,NVDA]         # subconjunto (default: toda la flota)
    [--no-email]                 # no manda el correo Resend
    [--tag REFRESH-8AM]          # prefijo en el subject del email
    [--outdir /ruta/planes-...]  # default ~/Desktop/planes-<fecha>
```

---

## 4. Capa de calibración — `calibration_ledger.py`

Cierra el loop: registra cada plan, lo califica contra el resultado real, y calcula la
**probabilidad empírica por tipo de setup × régimen** (NO por ticker). El bucket es
`"{setup_type}|{regime}"` — p.ej. `reclaim_wall|POSITIVO`, `breakdown|NEGATIVO`.

- **`record`** — tras generar planes (modo FULL), parsea los `x_drafts/` + `ranking.json`
  y apila una fila por setup a `data/calib_log.jsonl` (con `result=None`).
- **`grade`** — al cierre baja el OHLC 15m del día de cada fila sin resultado y decide:
  `no_entry` (nunca imprimió la entrada), `win` (target antes que stop), `loss` (stop
  antes). Reescribe el log con el veredicto.
- **`calibrate`** — agrega por bucket con **decaimiento temporal** (`DECAY_DAYS=120`,
  las filas viejas pesan menos) e **intervalo Wilson**. Escribe `data/calibration.json`.
- **`report`** — imprime la tabla de tasas medidas.
- **`eod`** — `grade` + `calibrate` + `report` (lo que corre postmortem_run.sh).

Parámetros clave: **`MIN_N=20`** (una tasa solo es "confiable"/`trust` con ≥20 muestras),
Wilson CI al 95%, `no_entry` no cuenta para el acierto direccional. El generador solo
sustituye la heurística cuando `trust=True`, y usa el **CI-low** (la cota baja honesta),
nunca la tasa central optimista.

Archivos: `data/calib_log.jsonl` (registro append-only, una fila por setup/día) →
`data/calibration.json` (agregado que lee el generador).

---

## 5. Capa de patrones — `pattern_detect.py`

Detector **algorítmico** de figuras clásicas + medición **empírica** de su acierto.
Anti-hardcode: nada de "NVDA hace doble techo"; se detecta por geometría pura.

- **Zigzag ATR** — swing points confirmados cuando el precio revierte ≥ k·ATR.
- **Detectores** — H&S y H&S invertido, doble techo / doble suelo, triángulos
  (ascendente / descendente / simétrico). Cada uno da trigger, target (measured-move),
  stop y `confidence` 0-1 (qué tan limpia es la geometría).
- **Medición empírica** — escanea **2 años** de la propia historia del ticker y cuenta
  cuántas veces, tras el gatillo, se tocó el target antes que el stop (win rate + n
  reales). Si `n < 8` para un ticker, se **poolea** con la flota de la corrida.
- **Salida** — `data/patterns.json`: `active` (patrón formándose ahora, ≤15 barras) +
  `empirical` (tasas por tipo).

**HONESTIDAD (crítica):** un patrón es **operable solo si `confidence ≥ 0.5` Y `n ≥ 8`**;
todo lo demás es **contexto, no gatillo**. Y las tasas medidas son **flojas** — la
mayoría cae por **debajo del 50%**. El sistema las reporta tal cual, con su n, sin
maquillar. En el PDF un patrón sin muestra suficiente sale marcado "solo contexto".
Corrida manual: `pattern_detect.py SYM [SYM2 ...]` o `--fleet` (21 tickers).

---

## 6. Posting en X (3 posters, señal-solamente)

### Presupuesto compartido — `x_post_common.py`

Ledger único `data/x_plan_budget.json` (`{month, posts, spent}`). **$0.015/post**,
caps duros **20 posts/día** y **$4.00/mes**, compartidos entre los posters que usan
este módulo. El conteo diario escanea las líneas `" POSTED "` de HOY en los logs de
los tres posters, así ninguno se salta el cap de otro. `MAX_CHARS=275`.

> Nota de precisión: `x_signal_poster.py` y `x_postmortem.py` usan este ledger
> compartido (20/día, $4/mes). `x_plan_poster.py` escribe al **mismo archivo** pero
> tiene su propio límite interno más estricto (`MAX_POSTS_PER_DAY=3`, `$2/mes`) y
> cuenta solo su propio log. En la práctica el poster premarket se auto-limita a 3.

### `x_plan_poster.py` — premarket (top-5)

Modo FULL (4AM). Lee `ranking.json`, ordena por score, y postea los TOP-N drafts
(`--top 5`) como texto simple. Flags: `--top`, `--dry-run`, `--dir`.

### `x_signal_poster.py` — daemon realtime

Ventana 8:00-16:05. Lee en vivo `~/Desktop/trading-signals/YYYY-MM-DD.txt`. Una señal
califica si: **prob ≥ 70**, o **BALLENA ratio ≥ 3:1**, o contiene **reclaim /
retest-ok / ruptura confirmada**. Caps propios: **5 posts realtime/día** (dentro del
cap compartido), **≥25 min entre posts**, dedup por ticker+nivel, y **máx 1 post en
premarket** (8:00-9:25). Ignora líneas de >10 min (arranques tardíos). Estado en
`data/x_signal_state.json` (se resetea al cambiar de día).

**COMBOS:** `data/x_combo_triggers.txt`, líneas `QQQ>=705 & MSFT>=403 : mensaje`. Cada
loop evalúa las patas contra el último close de `data/bars_<sym>_ibkr.txt` (fallback
yfinance si >5 min). Cuando **todas** las patas son ciertas a la vez, postea
`🎯 COMBO: ...` una vez al día por línea. El template se autocrea si falta.

### `x_postmortem.py` — cierre (16:20)

Lee `ranking.json` + `x_drafts/` de los top-5, baja el OHLC del día y califica cada
plan sin maquillaje: ¿imprimió el piso? ¿tocó el techo? ¿el stop? Postea **1-2 posts**
con **honestidad**: preferencia 1 ganador + 1 error; **si todo falló, se dicen los
fallos**. Anexa el repaso completo a `docs/POSTMORTEM-X.md`. Flags: `--dry-run`,
`--date`, `--dir`.

### Humor

`daily_fleet_plans.py` rota **8 quips** (uno por ticker/día, determinista) que cierran
el draft — p.ej. *"Si persigues el gap, TÚ eres la liquidez."* Todos los posts terminan
en **"No es consejo financiero"** y son puramente educativos.

---

## 7. Email (Resend) y notificaciones

Dos caminos distintos:

- **Email de planes** — lo manda `daily_fleet_plans.py` **directo** vía Resend API
  (`RESEND_KEY` / `RESEND_TO` en `feeds.env`/`x.env`), con los PDF adjuntos. El subject
  lleva el `--tag` (p.ej. `📋 REFRESH-8AM Planes flota ...`).
- **Alertas en vivo** — `notify_relay.sh` espeja `~/Desktop/trading-signals/<fecha>.txt`
  a **ntfy.sh** (push) y a **Resend** (email, solo líneas `🚨`). **DEBE estar vivo** —
  fue el fallo por el que no llegaban notificaciones. Ley anti-ruido: descarta alertas
  no frescas (>45s), dedup + cap 1/5s. Verificá: `pgrep -f notify_relay`.

---

## 8. Archivos de datos generados

| Archivo | Quién lo escribe | Qué es | Reset / inspección |
|---------|------------------|--------|--------------------|
| `data/calib_log.jsonl` | `calibration_ledger record/grade` | registro append-only, 1 fila/setup | `wc -l`; borrar = reset del histórico |
| `data/calibration.json` | `calibration_ledger calibrate` | tasas por bucket (lo LEE el generador) | `calibration_ledger.py report`; borrar → generador cae a heurísticas |
| `data/patterns.json` | `pattern_detect.py` | patrón activo + tasas empíricas | `python -m json.tool`; borrar → sin capa de patrones |
| `data/gex_snapshot.json` | `gex_snapshot.py` (4AM, tras archivar cadenas) | flip/regimen/muros/POC/net GEX MEDIDOS (griegas Polygon) + `_meta.cobertura` | `gex_snapshot.py --dry-run`; falta → healthcheck 🔴 |
| `data/x_plan_budget.json` | los 3 posters de X | ledger `{month,posts,spent}` | `cat`; se autoresetea al cambiar de mes |
| `data/x_signal_state.json` | `x_signal_poster` | estado diario (offset, posts, keys) | se autoresetea al cambiar de día |
| `data/x_combo_triggers.txt` | operador (autocreado) | combos multi-ticker | editar a mano |
| `~/Desktop/planes-<fecha>/` | `daily_fleet_plans.py` | PDFs + x_drafts + ranking.json | por día |

Para **resetear** la calibración: borrar `data/calibration.json` (vuelve a heurísticas)
y opcionalmente `data/calib_log.jsonl` (borra el histórico). Para **inspeccionar** una
tasa: `./venv/bin/python scripts/calibration_ledger.py report`.

---

## 9. Degradación limpia (aditivo, no rompe)

El sistema está diseñado para **nunca romperse por falta de un insumo**:

- Sin `data/calibration.json` → el generador usa sus **heurísticas** (55%/50% base).
- Sin `data/patterns.json` → simplemente no muestra la línea de patrón.
- Sin `data/gex_snapshot.json` (o caducado) → el PDF NO afirma régimen: imprime
  "REGIMEN GAMMA NO MEDIDO HOY: <motivo>" y sigue con su **GEX estimado** de un solo
  vencimiento (gamma Black-Scholes de la IV de yfinance), marcado ESTIMADO y con menos peso.
- Sin cache IBKR fresco → cae a **yfinance**.
- Sin `RESEND_KEY/TO` → salta el email, sigue generando PDFs.

**verify del mapa gamma:** en modo FULL, si `data/gex_snapshot.json` no se escribió, pasa
de 36h o pierde más de media flota, `dailyplans_run.sh` **grita en el log** y lanza una
notificación macOS (*"Mapa gamma incompleto: planes sin régimen gamma"*) — el pipeline
continúa igual, pero el operador se entera de que revise `poly_chain_archive`.
`fleet_healthcheck.py` lo vigila también, y su ausencia es 🔴.

---

## 10. Troubleshooting — correr cada pieza a mano

```bash
cd /Users/yuniorrodriguezosorio/ib-trader

# Planes completos (sin email, solo QQQ+NVDA)
./venv/bin/python scripts/daily_fleet_plans.py --tickers QQQ,NVDA --no-email

# Patrones de un ticker o la flota
./venv/bin/python scripts/pattern_detect.py NVDA
./venv/bin/python scripts/pattern_detect.py --fleet

# Loop de calibración a mano
./venv/bin/python scripts/calibration_ledger.py record      # registra el dir de hoy
./venv/bin/python scripts/calibration_ledger.py eod         # grade + calibrate + report
./venv/bin/python scripts/calibration_ledger.py report      # solo la tabla

# Posters en seco (no gastan presupuesto ni postean)
./venv/bin/python scripts/x_plan_poster.py --top 5 --dry-run
./venv/bin/python scripts/x_signal_poster.py --once --dry-run
./venv/bin/python scripts/x_postmortem.py --dry-run --date 2026-07-21

# Forzar los jobs launchd
launchctl start com.ibtrader.dailyplans
launchctl start com.ibtrader.postmortem
```

### Dónde están los logs

| Log | Contenido |
|-----|-----------|
| `dailyplans.log` | toda la corrida 4AM/8:30/9:12 + EOD (mapa gamma, patrones, calib, x_plan) |
| `x_signal_poster.log` | daemon realtime (SKIP/POSTED/COMBO) |
| `x_postmortem.log` | calificación EOD y posts |
| `x_plan_poster.log` | posts premarket |
| `x_postmortem_launchd.log` | stdout/stderr del job postmortem (del plist) |
| `notify_relay.log` | alertas enviadas/descartadas al relay ntfy+email |

Chequeos rápidos: `launchctl list | grep ibtrader` (jobs cargados),
`pgrep -f x_signal_poster` y `pgrep -f notify_relay` (daemons vivos),
`tail -f dailyplans.log` (seguir una corrida).

---

## 11. Las cuatro piezas vivas que faltaban en este manual

*Añadido 2026-07-25. Auditoría: este manual tenía **0 menciones** de las cuatro, pese a estar
todas en producción. Un daemon que no aparece en el manual es un daemon que la sesión
siguiente no sabe reiniciar ni diagnosticar — y en esta casa el manual es la memoria.*

Las cuatro son **señal-solamente**: ninguna coloca, modifica ni cancela una orden.

### 11.1 `fleet_healthcheck.py` — el auditor que se cura solo
Corre **3×/día** por launchd (`com.ibtrader.healthcheck`). Revisa que los daemons estén vivos,
que los ficheros de datos estén frescos y que el mapa gamma exista, y **relanza** lo que se haya
caído. Su ausencia del mapa gamma se marca 🔴.

Códigos de salida (importan, y fueron un bug de verdad):
- **0** = todo bien, o **solo avisos 🟡**.
- **2** = hay al menos un 🔴.

> **Por qué el 0 con avisos**: antes salía `1` con cualquier aviso 🟡, launchd lo grababa como job
> fallido, y la corrida siguiente auditaba su propio `LastExitStatus=1` y lo cantaba como aviso
> nuevo — un bucle que se alimentaba de sí mismo. Además, el job propio (label leído del plist)
> queda **fuera** de su propia auditoría. Arreglado 2026-07-25 (`2370d20`).

```bash
./venv/bin/python scripts/fleet_healthcheck.py          # a mano
launchctl kickstart -k gui/$UID/com.ibtrader.healthcheck
```

### 11.2 `index_breadth.py` — el engranaje QQQ/SPY
Calcula la **amplitud PONDERADA** de los componentes del índice: si MSFT+NVDA+AAPL rompen abajo,
SPY/QQQ heredan la presión. Es lo que permite decir *"el índice va a seguir a sus motores"* en vez
de mirar solo su propia vela. Alimenta el PDF y la brújula.

> **Bug histórico que explica por qué hay que vigilarlo**: partía por `,` unos ficheros separados
> por **espacios**, así que la guarda de frescura de 600 s era **código muerto** y cada corrida caía
> en silencio a yfinance retrasado — con Yahoo prohibido por orden permanente #6. Arreglado en la
> cacería del 2026-07-24. Si vuelve a aparecer un dato viejo aquí, ese es el primer sitio a mirar.

```bash
./venv/bin/python scripts/index_breadth.py QQQ
```

### 11.3 `force_meter.py` — fuerza y agotamiento en vivo
Mide la **fuerza** del movimiento en curso y la clasifica en 4 fases, cada una con su acción de
stop asociada. Es la pieza que da cuerpo a la **regla 9** (*jamás responder sobre un ticker sin
mirar la fuerza de las últimas 6-8 velas y el %B*): la fuerza es parte del veredicto SIEMPRE.

> **Pendiente conocido** (`TODOS.md`): vive **fuera** de los signal bots C++. Los bots deciden hoy
> sin ella. Plegarla por-tick dentro del bot es una casilla abierta.

```bash
./venv/bin/python scripts/force_meter.py NVDA
```

### 11.4 `posthours_cage.py` — la picardía de la jaula
Detecta el patrón **JAULA → LIBERACIÓN**: cuando las ballenas 0DTE mantienen el precio enjaulado
todo el día y, al expirar esos contratos, el after-hours se libera hacia las ballenas **semanales**
(no-0DTE). Análisis post-market para un posible producto apalancado unas horas.
Doctrina completa en la skill `postmarket-cage-release`.

> **Estado honesto**: el código y sus tests pasan, pero **nunca se ha visto disparar en vivo**.
> Hasta la primera cacería real (lunes al cierre) es teoría, y así debe tratarse.

```bash
./venv/bin/python scripts/posthours_cage.py
```

### Chequeo rápido de las cuatro

```bash
launchctl print gui/$UID/com.ibtrader.healthcheck | grep "last exit code"   # 0 o 2, nunca 1
./venv/bin/python scripts/index_breadth.py QQQ      # que NO diga fuente yfinance
./venv/bin/python scripts/force_meter.py QQQ
./venv/bin/python scripts/posthours_cage.py
```
