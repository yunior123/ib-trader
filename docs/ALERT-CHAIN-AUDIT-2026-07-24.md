# Auditoría de la CADENA DE ENTREGA de alertas — 2026-07-24

> Pregunta central: **¿cada señal que se generó llegó de verdad a Yunior?**
> Una señal que no suena es una señal que no existe.
> Método: sólo lectura. Todo número de abajo sale de `trades.db`, del archivo plano,
> de `notify_relay.log` y del código. Donde no pude determinar la causa, lo digo.

---

## 0. Veredicto en una línea

**La cadena está mayormente SANA, pero tiene 3 fugas reales y 1 mentira de clasificación.**
Nada se perdió en el salto archivo→BD (0 pérdidas). El teléfono entregó el 91%. La voz
cumplió la política de preempción (DANGER p50 = 0 s). Las fugas: (1) 77 señales
estructurales que no salen a ningún canal audible, (2) 11/11 señales V6 BUY/SELL de los
bots sin voz, (3) 11 pushes perdidos por el cap 1/5 s — tres de ellos ballenas.

---

## 1. Conciliación de las tres fuentes

| Fuente | Filas | Comentario |
|---|---:|---|
| `trades.db` tabla `signals`, `date='2026-07-24'` | **852** | |
| `data/trading-signals/2026-07-24.txt` | **774** | 774 líneas, 774 únicas |
| `trades.db` tabla `voice_log` (hoy) | **195** | eventos del daemon de voz |

### 1.1 Archivo → BD: **0 pérdidas**
Comprobado línea a línea: **774 de 774** líneas del archivo tienen fila en `signals`
(`file lines NOT in db: 0`). El daemon `scripts/signals_db.py --daemon` (PID 61450, vivo
desde 09:19) no perdió ni una. La `UNIQUE(date,ts_txt,msg)` colapsa repeticiones exactas,
pero hoy no hubo ninguna que colapsara (774 líneas = 774 únicas).

### 1.2 El excedente 852 − 774 = 78: señales que NUNCA pasaron por el archivo

| Origen | Filas | Consecuencia |
|---|---:|---|
| `🧲 ESTRUCTURAL` (imán/pin/flip) | **77** | **FUGA — ver §2.1** |
| `🎯 ZONA NVDA` 14:44:06 (ficha 0DTE) | **1** | línea que SÍ se escribió al archivo y luego **desapareció** — ver §6.2 |

### 1.3 Descomposición de las 852

- **76** son `WARMUP …` = replay histórico que los bots vuelcan al arrancar (09:18:23).
  No son señales del día. **Señales reales de hoy: 776.**
- Por prioridad (clasificación de `scripts/signals_db.py:32-47`): SIGNAL 460, INFO 229, DANGER 163.
- Por fuente: bollinger 452, signal 160, structural 77, cusum 65, flow 56, whale 42.

### 1.4 Señales reales → voz: 180 de 776 (23%)

El hueco 852 → 195 **es mayoritariamente diseño**, no pérdida. Desglose auditado de las
596 señales reales sin ningún evento en `voice_log`:

| # | Causa | Filas | ¿Diseño? |
|---|---|---:|---|
| A | `🧲 ESTRUCTURAL` — `chart_bridge._log_structural()` escribe DIRECTO a la BD | **77** | **NO — fuga** |
| B | `[MUTED p<55]` / `[VETO medido]` → `log_only()` (`bollinger_alarm.py:191,220,235`): ni voz, ni banner, ni teléfono | 229 | Sí |
| C | `🎈 BB REBOTE` de símbolo fuera de `VOICE_CORE={qqq,spy,nvda,smh,mu}` y sin ⭐ (`bollinger_alarm.py:54,232-236`) | 150 | Sí |
| D | `🔄 GIRO A CALLS/PUTS` — `sing(..., false)` = banner de contexto (`scripts/flow_pulse.cpp:509,516`) | 80 | Sí |
| E | `CUSUM TERREMOTO` — `QUAKE_BANNER=0`, radar solo-log (`nvda_signal_bot.cpp:137,1511,1517`) | 15 | Sí, **pero la BD miente** — ver §2.3 |
| F | Spikes `(VETADO)` / `🔇 (capitán opuesto)` — ley 12, banner sin voz | 13 | Sí |
| G | Señales **V6 BUY/SELL** de los bots C++ | **11** | **NO — fuga, ver §2.2** |
| H | Otros (FINVIZ scout ×2, arranque/cierre de daemons ×2, SCALPER HALT, fichas ZONA ×2, etc.) | 21 | Sí |

Los 15 eventos de `voice_log` que mi emparejador no ligó a una fila de `signals` **sí sonaron**
y sí tienen señal (el texto hablado difiere del texto del archivo): 6 `ALARMA DE PRECIO`,
6 `TWS WATCHDOG`, 2 `MANADA BAJISTA`, 1 `sell S M H now`.

### 1.5 Ballenas: `whale_alerts.jsonl` vs BD
60 alertas hoy (22 PUTS / 20 CALLS / 18 MID). Las 42 direccionales tienen fila; de las 18
`MID` (vuelta a neutro, sin alerta por diseño) 8 no tienen fila. **Sin pérdida.**

---

## 2. Las tres fugas reales

### 2.1 🔴 GRAVE — 77 señales ESTRUCTURALES mudas e invisibles al teléfono

`scripts/chart_bridge.py:1707-1722` (`_log_structural`) hace `INSERT` directo en
`trades.db` con `priority='SIGNAL'` y **nunca**:
- escribe en `data/trading-signals/<fecha>.txt`, y
- nunca llama a `scripts/speak.sh`.

Resultado: imanes, pins y flips (los niveles que ordenan el trade) **sólo existen si Yunior
tiene el chart abierto en el navegador**. Ironía: `scripts/notify_relay.sh:13` ya incluye
`🧲` y `ESTRUCTURAL` en su filtro — el relay las mandaría al teléfono, pero nunca llegan a
verlas porque no pasan por el archivo. Verificado: `ESTRUCTURAL en notify_relay hoy: 0`.

Ejemplos perdidos hoy: `09:19:49 NVDA se dirige a su imán 210.0 ↑ prob 66%`,
`10:24:53 AAPL en su imán 330.0 — pin prob 75%`.

**Fix (1 línea):** llamar a `_signals_file_line(sig['sym'], msg)` — la función ya existe en
el mismo archivo (`chart_bridge.py:1099`) y ya se usa para las fichas ZONA.

### 2.2 🔴 GRAVE — 11 de 11 señales V6 BUY/SELL sin voz

Las únicas señales de dinero de los bots (BUY/SELL con prob% medida) **no sonaron ninguna vez**:

```
09:37:00 AAPL: BUY   prob 56%      09:41:00 SMH: SELL  prob 56%
09:37:00 EWY:  SELL  prob 56%      09:41:00 TSM: SELL  prob 56%
09:37:00 SKHY: SELL  prob 56%      09:53:00 SPY: SELL  prob 55%
09:39:00 QQQ:  SELL  prob 56%      10:01:00 SLV: BUY   prob 56%
10:10:00 USO:  SELL  prob 57%      13:07:00 CPER:SELL  prob 62%
14:06:01 GLD:  SELL  prob 62%
```

Toda la voz de bots del día fue **una sola frase**: `sell S M H now` (09:31:04), y viene del
camino **clásico**, no del V6 (formato de mensaje distinto: `VENDER SMH @ … target … floor …`).

Lo que descarté con evidencia:
- El binario **sí** contiene la frase V6: `strings qqq_signal_bot` → `"sell NASDAQ one hundred now, probability %.0f percent"`.
- El gate `bar_is_live()` **era true**: `notify()` etiqueta `WARMUP` en el espejo y en el
  ops log cuando la barra no está viva (`qqq_signal_bot.cpp:260-280`), y
  `qqq_operations.log:3124` muestra `2026-07-24 09:39:00 | QQQ: SELL | …` **sin** tag WARMUP.
- `audio_gate(true)` sólo exige `bar_is_live()` (`qqq_signal_bot.cpp:211-217`); `money=true`
  salta el anti-ráfaga de 20 s.
- El daemon de voz estaba vivo (PID 59425 desde 09:18), luego `speak.sh` no cayó al fallback.
- El cwd del bot es el repo (`lsof -p 59587` → `/Users/…/ib-trader`), luego
  `scripts/speak.sh` resuelve.

**No puedo determinar la causa por lectura estática.** Toda la evidencia dice que `speak()`
debió llamarse y que `voice_queue.sh` debió registrar la fila. Hace falta instrumentar:
un `fprintf` en `speak()` del bot + un log de recepción en `speak.sh`. **No inventar la causa.**

### 2.3 🟡 La BD miente sobre la prioridad de CUSUM TERREMOTO

`signals_db.py:36` clasifica cualquier `TERREMOTO` como **DANGER**. Pero el emisor los manda
con `QUAKE_BANNER=0` (`nvda_signal_bot.cpp:137`), es decir **solo-log**: sin banner, sin
sonido, sin voz — por diseño y bien documentado ("el radar CUSUM va SOLO al log — ratio
ruido:dinero era 40-160:1"). Hoy: 15 TERREMOTO reales marcados DANGER en la BD, 0 voz.

Consecuencia: cualquier backtest o auditoría que use `priority` de la BD como proxy de
"lo que Yunior oyó" arroja resultados falsos. La BD debe reflejar el canal real
(`log_only` / `banner` / `voz`), no la severidad teórica.

---

## 3. Política de voz — ✅ SE CUMPLIÓ

`voice_log` hoy: **195** eventos → `spoke` 147, `notify_only` 28, `coalesced` 13,
`preempted` 7, **`dropped_stale` 0**.

Latencia medida (emparejando cada evento de voz con su señal, tras aplicar las mismas
traducciones ticker→nombre de `speak.sh:21-36`):

| Prioridad | n | min | p50 | p90 | max |
|---|---:|---:|---:|---:|---:|
| DANGER | 63 | 0 s | **0 s** | 9 s | 25 s |
| SIGNAL | 90 | 0 s | 22 s | 58 s | **143 s** |
| INFO | 27 | 0 s | 0 s | 0 s | 12 s |

- **¿Alguna alerta ALTA detrás de una INFO? NO — es estructuralmente imposible.**
  `voice_queue.sh:84` drena y descarta TODOS los `*_INFO.msg` al inicio de cada iteración
  del bucle, antes de mirar la cola DANGER (`:87`). INFO nunca se vocaliza → nunca ocupa el
  canal. Los 28 `notify_only` confirman que se drenaron sin hablar.
- **Preempción operativa:** 7 SIGNAL cortadas por DANGER (`say_preemptible`, `:67-78`).
  DANGER p50 = 0 s, p90 = 9 s. La ley "retraso = dinero" se respetó para lo urgente.
- **Cola larga: no.** `data/voice/` está vacío al cierre; 0 `dropped_stale`.

### 🟡 Aviso: las BB REBOTE ⭐ llegan tarde
Las 7 peores latencias son todas `🎈 BB REBOTE ⭐` (58-143 s). Son la celda ESTRELLA — la
capa selectiva que sí tiene edge — pero salen con `prio="SIGNAL"` (`bollinger_alarm.py:232-236`)
y esperan FIFO detrás del resto. `bollinger_alarm` barre la flota entera de golpe, así que
un lote de 8 ⭐ tarda ~2 minutos en vaciarse. Peores casos de hoy:
SNDK 143 s, DRAM 113 s, LRCX 109 s, SMH 84 s, TXN 80 s.

---

## 4. `notify_relay.sh` — vivo, pero con un bug latente serio

**Vivo hoy:** PID 59462, arrancado 09:18 AM, sigue corriendo (última escritura 18:00:24).
`fleet_healthcheck` lo reporta 🟢. **No hubo hueco después de las 09:18.**

### Entrega real al teléfono (excluyendo el volcado WARMUP)

| | |
|---|---:|
| Líneas del archivo que pasan el filtro de `notify_relay.sh:13` sin `MUTED` | 189 |
| … de las cuales WARMUP (replay, no deben ir) | 65 |
| **Elegibles reales** | **124** |
| **ENVIADAS al menos una vez** | **113 (91%)** |
| Vistas por el relay pero nunca enviadas | **11** |
| Nunca vistas por el relay | **0** |

**Las 11 perdidas — TODAS por el cap de 1 push cada 5 s (`notify_relay.sh:25`):**

```
09:28:00 SPCX TERREMOTO CAIDA
09:31:01 CPER TERREMOTO CAIDA
09:37:00 TSM  TERREMOTO CAIDA
09:37:54 🐋📈 BALLENA CRECE  MSFT calls DUPLICADO 13,994   <-- DANGER
09:51:02 🚀 SPIKE PUTS (VETADO) TSM
09:57:31 🐋 BALLENA PUTS  AMD 3.8 a 1 (17,314 puts)        <-- DANGER
10:57:12 🐋📈 BALLENA CRECE  TSM puts DUPLICADO 6,428      <-- DANGER
11:16:00 NVDA TERREMOTO ALZA
11:30:56 🚀 SPIKE CALLS (VETADO) NFLX
14:45:26 🚀 SPIKE CALLS NFLX  18 mil contratos, 9x
15:37:34 🔇🚀 SPIKE PUTS (capitán opuesto) AAPL
```

**Tres ballenas al teléfono perdidas por un cap de 5 segundos.** El cap es global y sin
prioridad: una ballena cae porque un BB banal se llevó el turno 4 s antes. Debería ser
cap por prioridad (DANGER exento) o una cola corta en vez de descarte.

### 🔴 Bug latente: sin rollover de medianoche
`notify_relay.sh:7` fija `F="…/$(date +%F).txt"` **una sola vez al arrancar** y luego hace
`tail -n0 -F "$F"` (`:9`). Un relay que sobreviva a la medianoche sigue mirando el archivo
de AYER y **no manda absolutamente nada en todo el día**, en silencio.
El keepalive (`fleet_keepalive_start.sh:145`) usa `pgrep` — ve el proceso vivo y no lo
reinicia, así que **no puede detectar este fallo**. Hoy nos salvó la casualidad: el relay
estaba muerto a las 09:18 y arrancó limpio.
Evidencia de que reinicia a horas distintas cada día (los saltos de reloj en el log marcan
reinicios): 15:25, 08:58, 04:20, 09:18.

### El ruido del log NO es pérdida
`DESCARTADA` 269 y `CAP 1/5s` 73 parecen alarmantes; son casi todos **re-lecturas** del
archivo y el volcado WARMUP:
- 263 de las 269 descartadas tenían >600 s de edad (p50 = 8 880 s ≈ 2,5 h).
- El relay releyó el archivo desde el principio **dos veces**: a las 10:33:53 y a las
  14:44:19 (firma clásica de `tail -F` cuando el archivo cambia de inodo o encoge).
- La ley anti-ruido (`:21-23`) hizo exactamente su trabajo: no reenvió información vieja.

---

## 5. Duplicados — mínimos y todos del mismo emisor

- **Mismo símbolo + kind + minuto:** 3 grupos, 4 filas extra. **Los 3 son `🧲 ESTRUCTURAL pin NVDA`**
  (13:02, 13:04, 13:06).
- **Mensaje idéntico repetido:** 17 mensajes, **33 filas extra** — 29 estructurales
  (peor caso: `NVDA en su imán 210.0 — pin · prob 77%` ×9) + 4 `TWS WATCHDOG` (reales, TWS
  murió 4 veces entre 17:50 y 18:00).
- **43% de las filas estructurales son repetición.** El dedupe de `chart_bridge.py:1732`
  usa la firma `sym|kind|price|dir`, que no incluye `prob`; cuando el estado oscila
  (pin ↔ magnet ↔ pin) la firma vuelve a cambiar y re-loguea el mismo texto.
- **Sin procesos duplicados.** `ps` confirma exactamente 1 de cada:
  `voice_queue.sh`, `notify_relay.sh`, `signals_db.py --daemon`, `opt_whale_watch.py`,
  y 24 `*_signal_bot`. El pidfile guard de `voice_queue.sh:29-33` funcionó.

---

## 6. Huecos temporales — ✅ sin zonas muertas

Histograma de hoy (señales reales, sin WARMUP):

| Hora | señales | DANGER | SIGNAL | INFO | voces |
|---|---:|---:|---:|---:|---:|
| 04 | 1 | 0 | 1 | 0 | 0 |
| 08 | 1 | 0 | 1 | 0 | 1 |
| 09 | 226 | 78 | 113 | 35 | 43 |
| 10 | 144 | 19 | 67 | 58 | 26 |
| 11 | 90 | 14 | 48 | 28 | 17 |
| 12 | 86 | 9 | 66 | 11 | 20 |
| 13 | 68 | 12 | 47 | 9 | 21 |
| 14 | 112 | 17 | 55 | 40 | 39 |
| 15 | 115 | 14 | 53 | 48 | 23 |
| 16 | 5 | 0 | 5 | 0 | 1 |
| 17 | 3 | 0 | 3 | 0 | 3 |
| 18 | 1 | 0 | 1 | 0 | 1 |

- **Buckets de 15 min VACÍOS entre 09:30 y 16:00: NINGUNO.** Sólo dos flojos:
  13:15 (1 señal) y 16:00 (2, ya post-cierre).
- **Ventana de oro 09:45-10:30: 117 señales reales** (20 DANGER, 52 SIGNAL, 45 INFO). Sana.
- **Falsa alarma descartada:** las mtimes de `*_signals.log` parecen congelarse a media
  mañana (mu 09:31, qqq 09:39, dram 09:35). **No es muerte de la flota** — esos logs sólo
  se escriben cuando hay evento. Los 24 bots están vivos desde las 9:18 AM y las barras
  están frescas (`data/bars_qqq_ibkr.txt`, última barra 16:25:00).

---

## 7. Permisos y escritura

### 7.1 🔴 `bollinger_alarm` MURIÓ hoy por TCC, en silencio
`bollinger_alarm.log` (única entrada del archivo):
```
Traceback (most recent call last):
  File ".../scripts/bollinger_alarm.py", line 154, in <module>
    say("🎈 BOLLINGER VIGIA", "Vigia Bollinger intradia arriba: …")
  File ".../scripts/bollinger_alarm.py", line 67, in say
PermissionError: [Errno 1] Operation not permitted:
  '/Users/yuniorrodriguezosorio/Desktop/trading-signals/2026-07-24.txt'
```
Murió a las **08:55:02** (hay un `notify_only` en `voice_log` a esa hora: la voz se encoló
justo antes del crash). Reinició a las **09:18:23** con el código nuevo. **23 minutos caído.**
Pre-apertura, así que hoy no costó señales — pero el fallo fue **silencioso**: sin voz
DANGER, sin `data/PERM_DENIED`, sin banner. Si pasa a las 10:00 nadie se entera.

### 7.2 🔴 Los 24 binarios C++ + `price_alarm` + `flow_pulse` siguen apuntando al Desktop
```
strings dram_signal_bot | grep trading-signals  ->  %s/Desktop/trading-signals
strings qqq_signal_bot  ...                     ->  %s/Desktop/trading-signals
strings price_alarm     ...                     ->  %s/Desktop/trading-signals
strings flow_pulse      ...                     ->  %s/Desktop/trading-signals/%04d-%02d-%02d.txt
```
El fuente ya está migrado (`fleet_notify.h:45` → `data/trading-signals`), pero los binarios
son del **Jul 20 10:05** y no se han redesplegado (TODOS.md: "DESPLIEGUE PENDIENTE").
**Hoy funcionan sólo porque `~/Desktop/trading-signals` es un symlink al repo, creado a las
10:33 de hoy.** Si ese symlink se borra o TCC vuelve a bloquear Desktop, los 26 emisores
C++ **fallan en silencio** — `fleet_notify.h:36` lo dice explícitamente: "Si Desktop no es
escribible, falla en silencio".

### 7.3 Otros
- `daily_archive.log:89` — sigue fallando TCC al archivar `Desktop/planes-2026-07-24/ranking.json`.
- `fleet_healthcheck` lo reporta: "🟡 planes de hoy: Desktop vetado por TCC".
- La migración Desktop→repo **no perdió nada**: las 277 líneas de
  `~/Desktop/.trading-signals.bak/2026-07-24.txt` (hasta 10:32:30) son un subconjunto
  exacto de las 774 del archivo del repo (`bak lines NOT in new: 0`).
- **Ningún** marcador `data/PERM_DENIED` se creó hoy.

---

## 8. Anomalía sin causa determinada

Una línea que **estuvo** en el archivo desapareció:
`14:44:06 | 🎯 ZONA NVDA | 🔴 COMPRA 100x NVDA 210C 0DTE @ límite $0.02 …`
Está en `signals` (el daemon la ingirió) pero ya no está en
`data/trading-signals/2026-07-24.txt`. Coincide con la segunda re-lectura de
`notify_relay` (14:44:19-20), que es la firma de un archivo que encoge o cambia de inodo.

Todos los escritores que revisé usan append atómico:
`open(O_WRONLY|O_APPEND|O_CREAT)` en `fleet_notify.h:50`, `open(path,"a")` en
`bollinger_alarm.py:66`, `chart_bridge.py:1105`, `>>` en `tws_watchdog.sh:111,132,148`.
**No pude determinar quién truncó el archivo.** No invento la causa. Acción: instrumentar
(guardar tamaño+inodo cada minuto) y volver a mirar mañana.

---

## 9. Lo que hay que arreglar, por gravedad

| # | Gravedad | Qué | Dónde |
|---|---|---|---|
| 1 | 🔴 | Señales V6 BUY/SELL sin voz (11/11). Instrumentar `speak()` y `speak.sh` para hallar la causa | `qqq_signal_bot.cpp:915-922`, `scripts/speak.sh` |
| 2 | 🔴 | ESTRUCTURAL no llega a ningún canal audible ni al teléfono. Añadir `_signals_file_line()` | `scripts/chart_bridge.py:1707-1722` |
| 3 | 🔴 | `notify_relay` sin rollover de medianoche + keepalive `pgrep` ciego a ese fallo | `scripts/notify_relay.sh:7`, `fleet_keepalive_start.sh:145` |
| 4 | 🔴 | Los 26 binarios C++ escriben al Desktop; sólo el symlink de hoy los salva. Redesplegar con mercado cerrado | `deploy_signals_to_data.sh` |
| 5 | 🟠 | Cap 1/5 s sin prioridad: perdió 3 ballenas al teléfono. Eximir DANGER o encolar | `scripts/notify_relay.sh:25` |
| 6 | 🟠 | `bollinger_alarm` murió por TCC sin avisar. Envolver `say()`/`log_only()` en try/except que dispare voz DANGER + `data/PERM_DENIED` | `scripts/bollinger_alarm.py:59-68` |
| 7 | 🟠 | BB REBOTE ⭐ con hasta 143 s de retraso: subir la celda ESTRELLA a DANGER (o carril propio) | `scripts/bollinger_alarm.py:232-236` |
| 8 | 🟡 | La BD miente: TERREMOTO se guarda DANGER pero es solo-log. Guardar el canal real, no la severidad teórica | `scripts/signals_db.py:36` |
| 9 | 🟡 | 43% de filas ESTRUCTURAL son repetición: meter `prob` (redondeada) o histéresis en la firma de dedupe | `scripts/chart_bridge.py:1732` |
| 10 | 🟡 | Línea `🎯 ZONA NVDA` 14:44:06 desapareció del archivo; causa desconocida. Instrumentar tamaño+inodo | — |
