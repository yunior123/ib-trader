# POSTMORTEM ALGOS — 2026-07-22 (forense de logs + autolearn)

Fuentes: `~/Desktop/trading-signals/2026-07-22.txt` (856 líneas al cierre del forense), `~/Desktop/price-alerts.txt`,
`price_alarm.log`, `opt_whale.log`, `flow_pulse.log`, `data/whale_flow_hist.jsonl` (1.500 filas),
`data/whale_alerts.jsonl`, bars IBKR 1m. Todo verificado contra el código citado.

---

## CRONOLOGÍA DEL DÍA (hitos)

| Hora | Evento | Verificación |
|---|---|---|
| 08:15:41 | fleet_autostart levanta la flota; WARMUP replays (etiquetados, ok) | fleet_autostart.log |
| 08:16:46 | price_alarm arranca → **FLOOD: 10 sirenas en 9 s** (08:16:47-55) + 3 más hasta 08:18:45 — reglas de la víspera ya cruzadas por el gap (ej. "QQQ toco 707.20" con px=702.27) | price_alarm.log:3416+; ERROR-1 |
| 09:32 | opt_whale primer scan del día (whale_flow_hist arranca) | jsonl ts primero 09:32:00 |
| 09:33-10:40 | Ballenas de apertura: NFLX CALLS P/C 0.04 (13.2k), NVDA CALLS 0.28 (26.8k), GOOGL PUTS 4.2 | whale_alerts.jsonl |
| 11:25:25 | **MU SPIKE CALLS** (ACIERTO, sin sirena — gap): vc 10.666→15.857 (+49% en un scan de 6,5 min) a spot 975.21 | whale_flow_hist; abajo |
| 12:22 y 12:35 | **CLUSTER FALSO**: fallback `clase` con spot=NaN → 7 sirenas "BALLENA CRECE" falsas + BALLENA PUTS SMH falsa | ERROR-2 |
| 13:01:40 | flow_pulse (nuevo, C++) arranca — el detector de giros no existió en la mañana | flow_pulse.log:1 |
| 13:01-13:23 | Techo real del día: NVDA high 214.39 (13:02), MU high 982.62 (13:23) | bars ibkr (verificado 3a pasada) |
| 13:06:09 | **DISPARO FALSO**: regla "nvda 214.40 down" armada 13:06:08 con px ya 214.245 → quema al instante | ERROR-1 |
| 13:54:50-13:55:31 | **GIRO A PUTS triple** NVDA+SMH+AMZN (ACIERTO) — la rotación 2h antes del piso | flow_pulse.log |
| 14:21→15:53 | **FLUJO PUTS SPY** ratio 1.41→1.62 escalando (ACIERTO 14:47 "divino") | flow_pulse.log |
| 15:56 | MU toca max pain 960 (alarma cantó 15:56:50, px=960.29; el bar previo 15:55 cerró 961.88 — imán cumplido) | price_alarm.log:3551 |
| 16:00:59 | opt_whale cierre de sesión limpio; keepalive lo relanza a idle | opt_whale.log |

---

## ERROR 1 — price_alarm dispara reglas YA CRUZADAS al armarlas (raíz verificada)

**Evidencia**: `price_alarm.log` 13:06:08 "alertas recargadas: 23" → 13:06:09 "DISPARADA NVDA toco 214.40 ... px=214.2450".
La regla se escribió con NVDA ya DEBAJO de 214.40 (high del día 214.39 a las 13:02; el propio texto decía
"valido SOLO tras tocar 214.90" — NVDA jamás tocó 214.90). Misma raíz que el flood de apertura: price_alarm
reinició 08:16:46 y en 1-9 s quemó 10 reglas de la víspera que el precio había gapeado (px hasta 5 pts lejos
del nivel: "QQQ toco 707.20" px=702.27).

**Causa raíz en el código** — `scripts/price_alarm.cpp:341-342`:
```cpp
if (r.mode == DOWN)      hit = px <= r.px;
else if (r.mode == UP)   hit = px >= r.px;
```
Las reglas UP/DOWN evalúan `hit` desde la primera lectura sin estado de armado. SOLO el modo CROSS tiene la
protección (`price_alarm.cpp:343-349`, "nunca disparar al armar"). La confirmación de 2 lecturas (línea 354)
no ayuda: la condición sigue cumplida al segundo tick.

**Nota honesta**: el disparo falso de 13:06 fue *lucky* (NVDA 214.24→211.78 a 15:56, el put habría pagado),
pero el proceso está roto: 11 de los 13 disparos de 08:16-08:18 eran ruido puro premarket (13 sirenas DANGER
encoladas).

**FIX PROPUESTO (C++ — NO aplicado, binario crítico)** — diff pequeño en `scripts/price_alarm.cpp`:
```cpp
// struct Rule: añadir
    bool armed_dir = false;   // UP/DOWN: visto al menos 1 px del lado "seguro"

// en el loop, ANTES de evaluar hit (reemplaza las líneas 341-342):
    if (r.mode == DOWN)      hit = px <= r.px;
    else if (r.mode == UP)   hit = px >= r.px;
    if ((r.mode == UP || r.mode == DOWN) && !r.armed_dir) {
        if (!hit) { r.armed_dir = true; }        // armada del lado correcto
        else {
            // regla nacida YA CRUZADA: avisar UNA vez y neutralizar
            logline("REGLA YA CRUZADA al armar: '%s' px=%.4f — marcada, no sirena",
                    r.raw.c_str(), px);
            fleet_notify(...banner suave, sin sirena x3...);
            mark_fired(path, r);                  // o prefijo [YA-CRUZADA HH:MM]
            continue;
        }
    }
```
Comportamiento: si al armar la regla el precio ya está del lado del disparo → banner suave "YA CRUZADA,
revisa el nivel" (sin sirena x3, sin voz DANGER) y la línea queda marcada. Si se arma del lado correcto,
todo igual que hoy. Igual que el armado CROSS pero para UP/DOWN. Preservar `armed_dir` en las recargas por
`armed_state` (como ya se hace con `armed`). Estimado: ~15 líneas.

---

## ERROR 2 — Cluster 12:22: NO fue hueco de feed, fue fallback `clase` con spot=NaN (raíz verificada, FIX APLICADO)

> **CORRECCIÓN (2a pasada, ver ADDENDUM A1)**: el NaN/clase explica NOK y las sirenas de 12:35-12:36, pero
> 6 de las 7 CRECE de 12:22-12:24 eran filas por-strikes sanas — la raíz dominante fue la feature ESCALADA
> desplegada 12:20 con baseline vlast=0. Segundo fix aplicado (seed de baseline).

**Evidencia** (`whale_flow_hist.jsonl`): cadencia perfecta ~6,5 min TODO el día (60 scans/sym 09:32-16:00,
cero huecos >10 min). Lo que saltó fueron los NÚMEROS en 2 scans:

| Scan | QQQ vc/vp | MU vc | AAPL vc | NOK vc | src | spot |
|---|---|---|---|---|---|---|
| 12:18 | 48.557 / 45.258 | 17.746 | 56.959 | 4.287 | strikes | ok |
| **12:22-12:24** | **1.482.374 / 1.729.971** | **222.550** | **460.830** | **122.895** | **clase** | **nan** |
| 12:29 | 46.681 / 42.698 | 19.616 | 56.993 | — | strikes | ok |

Y otra vez 12:35-12:36 (SMH 28.813/66.242 clase nan → sirena "BALLENA PUTS SMH" falsa; AVGO 158.377 clase →
"BALLENA CRECE" falsa; GLD flapping calls→mid→calls con re-sirena 12:43).

**Causa raíz en el código** — `scripts/opt_whale_watch.py`:
1. Línea 96: `spot = tk.last if tk.last == tk.last and tk.last else tk.close` — en un hipo transitorio de la
   farm de datos (12:22 y 12:35, varios símbolos a la vez) `last` Y `close` vienen NaN.
2. Línea 99 (pre-fix): `if not spot or ...` — **NaN es truthy en Python** → pasa el filtro.
3. Línea 104: `abs(k-spot)/spot <= 0.03` con NaN → toda comparación False → `ks=[]` → `vc+vp==0`.
4. Línea 139-151: el fallback legítimo anti-Error-354 pide tick 100/101 del subyacente = volumen de la CLASE
   ENTERA (todas las expiries, todos los strikes) → 30x los números por-strike.
5. Línea 179 (pre-fix): el comparador ESCALADA compara ese volumen clase contra el baseline por-strikes →
   "se DUPLICO" falso en 7 tickers (12:22:21-12:24:01) + QCOM 13:09.

**FIX APLICADO** (backup `backup/opt_whale_watch.py_pre_nanclase.bak`, py_compile OK):
- NaN-guard: `if spot != spot: spot = None` antes del filtro (símbolo sin spot → skip/TICKER CIEGO, jamás clase-con-nan).
- ESCALADA solo compara peras con peras: `if not tag and ...` — un scan `clase` jamás canta "BALLENA CRECE"
  contra baseline strikes. El fallback clase sigue vivo para su propósito original (P/C ratio, que es scale-free).
El proceso vivo toma el fix en el próximo relanzamiento del keepalive (mañana 09:30 o al reiniciar; no se tocó el daemon).

**Defensa en profundidad (C++ — propuesto, no aplicado)**: `scripts/flow_pulse.cpp` (ingesta en línea 326)
debería descartar filas con `"src":"clase"` o `"spot":nan` del histórico que alimenta sus ratios — hoy el
flow_pulse arrancó 13:01 y no comió las filas malas, pero un reinicio a las 12:30 las habría tragado.

---

## ERROR 3 — Cronología de la tarde: qué llegó tarde / qué faltó

1. **flow_pulse no existió en la mañana** (arrancó 13:01:40): el spike de calls de MU a las 11:25 (+49% en un
   scan, EL techo del clímax local) no tuvo sirena de ningún proceso — opt_whale solo canta cruce de umbral
   P/C (0.35/2.0) o ESCALADA 2x dentro del estado; MU estaba en P/C 0.52 = zona muda. El hueco que motivó
   construir flow_pulse a mediodía es real y está MEDIDO abajo.
2. **GIRO A PUTS 13:54 = confirmación, no anticipación**: el techo real fue NVDA 214.39 a las 13:02 y MU 982.62
   a las 13:23 (bars ibkr, corregido en 3a pasada — no 982.88/13:01).
   El giro llegó ~52 min después del pico de NVDA (~31 min tras el de MU) — PERO 2h antes de la pierna gorda (QQQ 707.4→705.2, NVDA→211.78).
   Latencia estructural: scan 6,5 min/sym + cooldown 600 s de flow_pulse ⇒ peor caso ~13 min. Aceptable para
   rotación; no sirve para picos de 1-2 min (eso es de bollinger_alarm/price_alarm, que sí cantaron: "709
   PERDIDO" 13:33:30, "PIERNA FRESCA" 13:55:11 px=707.10 — sincronizada al minuto con el giro de flujo).
3. **Voz**: `data/voice/` drenada (0 pendientes, último proceso 17:08) — sin evidencia de voces perdidas. Lo
   malo fue el EXCESO: 13 DANGER encoladas 08:16-08:18 (ERROR-1).
4. **Mensaje del FLUJO PUTS SPY contradice lo que pasó**: el texto dice "Piso local probable — rebote corto si
   imprime" (doctrina espada), pero el ratio SUBIÓ 6 scans seguidos (1.41→1.62) y SPY siguió cayendo 1,2 pts
   hasta el cierre. Put-flow *persistente y creciente* = presión/continuación; el extremo-reversión es para
   *spikes* de un scan. Propuesta (flow_pulse.cpp, C++): si el ratio lleva ≥3 lecturas subiendo, cambiar la
   frase a "presión sostenida — continuación, NO fade". Señal correcta, narrativa invertida.

### Otros hallazgos (no pedidos, cazados en el forense)
- **NFLX 67.5 Error-200 en bucle**: `opt_whale.log` lleno de "No security definition NFLX 67.5 C/P" cada scan
  (reqId 4080→9408+, ~12 ciclos). La blacklist `badk` (opt_whale_watch.py:120-123) no retiene el strike —
  sospecha: `badk[s].clear()` de la autocura (línea 161) tras scans con volumen 0, o requalify tras
  reconexión. Ruido de log + 2 requests IBKR quemados por scan. Investigar con `FP_TEST` otro día; no crítico.
- **Spreads de veto oscilantes**: SMH "spread 36%"/"26%"/"5%" en la misma hora — optgate parece leer quotes
  distintas (¿strike lejano / cache viejo?) según el minuto. Afecta el veto OPCIONES OK/VETADAS de cada señal.
  Auditar `optgate.py` con la cadena SMH de hoy.
- `bollinger_alarm.log` y `band_open_watch.log` = 0 bytes (todo va al espejo Desktop; sin log propio no hay
  forense de esos procesos — añadir logline mínimo al arrancar/cantar).
- zsh: `echo ===` revienta con "(eval):1: == not found" (expansión `=cmd`); usar `---` en scripts/comandos.

---

## ACIERTOS (números medidos, para reforzar)

1. **SPY FLUJO PUTS 14:47:54** ("divino"): 154k puts vs 110k calls, ratio 1.40, spread 1% OK. SPY 748.50 en la
   señal → 747.41 (15:40) → 747.30 cierre. La serie completa 14:21→15:53 escaló 1.41→1.62 mientras QQQ
   707.29→705.22 y NVDA 213.78→211.78 (-0.94%). Como veto-de-calls + sesgo corto: perfecto. (Ver ERROR-3.4:
   la frase "rebote corto" era la lectura equivocada; lo divino fue la persistencia del ratio.)
2. **GIRO A PUTS triple 13:54:50-13:55:31** (NVDA 0.25→0.33, SMH 0.67→1.35, AMZN 0.55→0.97): la rotación
   cantada con QQQ 707.43 / NVDA 213.58 → a 15:56 QQQ 705.71 (-1.7 pts) y NVDA 211.78 (-0.84%). Tres tickers
   girando en 41 s = señal de manada, no de ticker. flow_pulse pagó su construcción el mismo día.
3. **MU SPIKE CALLS 11:25:25**: +5.191 calls en un scan (10.666→15.857, +49%) con MU vertical en 975.21 —
   retro inmediato a 971.6 (-0.37% al scan siguiente) y techo definitivo 982.62 a las 13:23 (bars ibkr,
   corregido) → max pain 960 cumplido 15:56 (-2.2% desde el clímax). La ley 13 (call-spike = techo local)
   MEDIDA otra vez — con matiz honesto: el techo definitivo llegó ~2h después del spike, con un tramo
   975→982 en medio; el spike marcó el clímax LOCAL (retro inmediato), no el high del día. Gap: sin
   sirena automática (ver ERROR-3.1).
4. **Bonus max pain**: alarma "MU 960.50 MAX PAIN" disparó 15:56:50 con px=960.29 (bar 15:59 cerró 959.52,
   bar 16:00 961.01) — segundo
   día seguido que el imán gordo cumple al cierre (NVDA 207.50 ayer).

---

## FIXES PRIORIZADOS

| # | Prio | Archivo | Fix | Estado |
|---|---|---|---|---|
| 1 | ALTA | scripts/opt_whale_watch.py | NaN-guard spot + ESCALADA solo strikes-vs-strikes | **APLICADO** (backup + py_compile OK) |
| 2 | ALTA | scripts/price_alarm.cpp:341 | armado direccional UP/DOWN: regla nacida ya-cruzada → banner suave [YA-CRUZADA], sin sirena (diff arriba) | PROPUESTO (C++, ~15 líneas) |
| 3 | MEDIA | scripts/flow_pulse.cpp:326 | descartar filas src=clase / spot=nan al ingerir el jsonl | PROPUESTO (C++, 3 líneas) |
| 4 | MEDIA | scripts/flow_pulse.cpp | ratio subiendo ≥3 scans → mensaje "presión sostenida, NO fade" (evita narrativa invertida del FLUJO PUTS SPY) | PROPUESTO |
| 5 | BAJA | scripts/opt_whale_watch.py | blacklist NFLX 67.5 que no retiene (autocura línea 161 la borra) — investigar con FP_TEST | PENDIENTE (raíz abajo, A3) |
| 6 | BAJA | scripts/optgate.py | auditar spreads oscilantes (SMH 5%↔36%) | PENDIENTE |
| 7 | BAJA | bollinger_alarm / band_open_watch | logline mínimo propio (hoy 0 bytes = sin forense) | PENDIENTE |
| 8 | ALTA | scripts/opt_whale_watch.py | ESCALADA con vlast=0 canta en falso (raíz REAL del cluster 12:22, ver ADDENDUM A1) — seed de baseline en 1a observación + no sembrar baseline con volumen clase | **APLICADO** (backup `opt_whale_watch.py_pre_escalada_seed.bak`, py_compile OK) |
| 9 | BAJA | scripts/fleet_healthcheck.py:122 | PermissionError TCC en Desktop planes-* tumbaba el healthcheck entero (6 traces en healthcheck_err.log: 3× planes-2026-07-21 + 3× planes-2026-07-22) → try/except + WARN "dar Full Disk Access", degradación limpia | **APLICADO** (backup `fleet_healthcheck.py_pre_tccfix.bak`, py_compile OK) |

---

## ADDENDUM (2a pasada forense — verificación contra whale_flow_hist fila por fila)

### A1 — La raíz REAL del cluster 12:22 NO fue el NaN: fue la ESCALADA desplegada a mediodía con baseline 0

El NaN/clase explica solo 1 de las 7 sirenas. Filas exactas del jsonl en los timestamps de las 7 "BALLENA CRECE":

| ts | sym | src | spot | vc |
|---|---|---|---|---|
| 12:22:21 | NVDA | **strikes** | 213.91 | 265.468 |
| 12:22:27 | AMD | **strikes** | 556.32 | 13.888 |
| 12:23:11 | MSFT | **strikes** | 388.72 | 23.048 |
| 12:23:31 | AVGO | **strikes** | 394.34 | 19.730 |
| 12:23:43 | NOK | clase | nan | 122.895 |
| 12:23:57 | NFLX | **strikes** | 70.13 | 88.434 |
| 12:24:01 | GLD | **strikes** | 381.03 | 11.922 |

6 de 7 filas eran por-strikes con spot válido — el hipo NaN de la farm no las toca. Cadena causal verificada:

1. La feature ESCALADA se desplegó ~12:20 (comentario "ESCALADA (Yunior 12:20)" en el código) y el proceso
   reinició a las **12:21:01** (`opt_whale.log:1441` "salio; relanzando").
2. `opt_whale_state.json` (escrito por el código viejo) no tenía claves `<sym>_v` → `vlast = state.get(vkey, 0) = 0`.
3. Condición pre-fix: `vdom >= 2 * max(vlast, 1)` → con vlast=0 basta `vdom > VMIN` → canta "se DUPLICO"
   para TODO símbolo que estuviera en estado calls/puts. Los 7 que cantaron = exactamente los 7 con BALLENA
   CALLS activa de la mañana (NFLX 09:33, MSFT 09:39, NVDA 09:46, AMD 09:46, AVGO 09:47, GLD 09:47, NOK 10:40).
4. **Prueba de la residual**: QCOM cantó CRECE a las 13:09:58 con vc=3.002 (src=strikes, spot 176.87) — eso es
   cruzar VMIN=3000, NO duplicarse (baseline real de su canto 11:32 era 2.916 → 2x=5.832; a las 12:23 calló
   porque vc=2.692 < VMIN). **Corrección 3a pasada**: el fix nanclase NO estaba a bordo a las 13:09 (se aplicó
   ~17:30, backup `opt_whale_watch.py_pre_nanclase.bak` 17:30; el propio doc dice arriba que el proceso vivo
   lo toma en el próximo relanzamiento). La prueba sigue en pie por la fila misma: src=strikes con spot
   válido — el NaN-guard no la habría cubierto aunque hubiera estado vivo.
5. **Honestidad**: 5 de las 7 (NVDA 26.8k→265k, MSFT 2.6k→23k, NFLX 13.3k→88k, AVGO 3k→19.7k, GLD 3.2k→11.9k)
   eran FACTUALMENTE ciertas midiendo contra el canto de la mañana — el volumen sí se había multiplicado en
   2.5 horas. Lo falso fue el TIMING comprimido ("la marea sigue entrando" cuando era acumulado de horas) y
   NOK/QCOM/AVGO-12:36 que eran puro artefacto.

**Fix aplicado** (`scripts/opt_whale_watch.py`, backup `backup/opt_whale_watch.py_pre_escalada_seed.bak`):
- `vlast <= 0` → SIEMBRA el baseline (`state[vkey] = vdom`) y jamás canta. Primera observación = calibración.
- En transición de estado con scan `clase`, el baseline se siembra a 0 (re-siembra limpia en el próximo scan
  por-strikes) — hoy quedaron envenenados `AVGO_v=158.377` y `NOK_v=122.895` (volumen de clase entera) en
  `data/opt_whale_state.json`: cualquier escalada real por-strikes de AVGO/NOK habría quedado MUDA el resto
  del día (necesitaba 2×158k). El estado es diario, muere a medianoche — no hace falta limpiarlo a mano.
- El proceso vivo toma el fix en el próximo relanzamiento (state file es del día, la siembra ocurre sola).

### A2 — Regla nacida-ya-cruzada extra cazada: TXN 285 down a las 16:02
"TXN toco 285.00 ... px=274.4300" (16:02:01): legítima en intención (canario pre-earnings) pero disparó
post-cierre sobre el gap de earnings — el nivel quedó 10.6 pts atrás y el mensaje "toco 285" es mentira
piadosa (gapeó a través). El fix #2 (armado direccional) también corrige la narración de gaps: la regla se
armó con TXN ~290 (lado correcto), así que habría disparado igual — pero el mensaje debería decir
"GAP-THROUGH 285→274.43". Mejora opcional del mismo diff: si `|px - r.px|/r.px > 0.5%` al disparar, decir
"gapeo a traves de" en vez de "toco".

### A3 — NFLX 67.5 Error-200 en bucle: raíz encontrada (línea 125 `if ok:`)
`qualifyContracts` por lotes: tras el primer scan, los strikes buenos quedan en `qcache` → el lote `new` de
los scans siguientes contiene SOLO los malos (67.5 C/P) → `ok=[]` → el guard `if ok:` (anti-veto-transitorio,
lección AAPL 07-20) impide blacklistear → reintento infinito, 2 requests IBKR + 4 líneas de log por scan
todo el día (reqId 4080→9408+). Fix propuesto (no aplicado, para no rozar la lección AAPL): contador
`failk[s][k] += 1` cuando `(k,C)` y `(k,P)` fallan juntos; blacklist al 3er fallo consecutivo — el veto
transitorio de farm fría no llega a 3, el strike inexistente sí.
