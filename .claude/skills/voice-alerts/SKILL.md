---
name: voice-alerts
description: Política y arquitectura de la voz de la flota ib-trader (scripts/voice_queue.sh + speak.sh) — voz serializada con PREEMPCIÓN por prioridad para que las alarmas importantes suenen a tiempo y jamás con retraso (retraso = dinero), INFO solo como notificación Mac, y auditoría en voice_log. Usar al tocar la voz, diagnosticar "sonó/no sonó", o clasificar la prioridad de un emisor nuevo. SEÑAL-SOLAMENTE.
---

# voice-alerts — voz a tiempo, jamás con retraso (Yunior 2026-07-23)

Un solo consumidor habla (evita el "las voces se pisan"). Los productores ENCOLAN vía
`scripts/speak.sh <PRIO> "<msg>"`; el daemon `scripts/voice_queue.sh` reproduce con
prioridad + preempción. Voz = Siri del sistema (SIN `-v`; se fija en Ajustes > Spoken Content).
Arranca con `scripts/voice_queue_keepalive.sh`. Instancia única (pidfile guard).

## LEY: "retraso = dinero" (Yunior 2026-07-23)
Una alarma que llega tarde puede costar la entrada. Por eso la voz es **preemptiva**:

| Prioridad | Emisores | Comportamiento |
|---|---|---|
| **DANGER** | 🐋 ballena (opt_whale) · ⏰ price_alarm · 🚀 spike fuerte · 🩸 dip | Voz **INMEDIATA y COMPLETA**. **PREEMPTA** cualquier voz de menor prioridad en curso (la mata y habla YA). Nunca se retrasa, nunca se coalesce/descarta. |
| **SIGNAL** | 🚀 spike · band_open · señales de nombre | Se habla completa (FIFO); coalesce SOLO en avalancha (>FLOOD=4); **preemptible por DANGER**. |
| **INFO** | 🎈 BB muted (p<55), chatter | **SOLO notificación Mac** (el banner osascript ya lo disparó el emisor). **NO se vocaliza** → no congestiona la cola. |

Latencia de una DANGER: ~0 si nada habla, ~50ms si preempta una SIGNAL. Nunca espera a INFO.

## Mecánica de la preempción (bash 3.2)
`say "$msg" & spid=$!` en background; mientras vive, si aparece un `*_DANGER.msg` en la cola
y lo que suena es < DANGER → `kill $spid` y se cede el turno. DANGER se habla sin ceder.
Antes (≤2026-07-22) el coalescing + descarte-stale-25s mataba voces individuales → ese era
el "a veces solo símbolo sin voz" (CONFIRMADO, era por diseño). Ya no: solo INFO no habla.

## Cómo elegir la prioridad de un emisor nuevo
- ¿Marca un EXTREMO/MOVIMIENTO accionable (ballena, spike, dip, sirena de precio)? → **DANGER**.
- ¿Señal útil pero no urgente (rebote BB con prob, señal de nombre)? → **SIGNAL**.
- ¿Ruido/contexto (muted, band-walk sin edge, info)? → **INFO** (solo notificación).
`speak.sh` traduce tickers→nombre hablado (NVDA→Nvidia) centralizado — no hacerlo en cada emisor.

## Auditoría: voice_log (¿sonó de verdad?)
`voice_queue.sh` registra en `trades.db` tabla `voice_log(ts_epoch, action, priority, msg)`
con `action ∈ {spoke, preempted, notify_only, coalesced, dropped_stale}` y `busy_timeout=5000`
(no perder filas por lock WAL concurrente). Para verificar empíricamente:
```bash
sqlite3 trades.db "SELECT datetime(ts_epoch,'unixepoch','localtime'),action,priority,substr(msg,1,50) FROM voice_log ORDER BY id DESC LIMIT 20"
sqlite3 trades.db "SELECT action,COUNT(*) FROM voice_log WHERE date(ts_epoch,'unixepoch','localtime')='YYYY-MM-DD' GROUP BY action"
```
`notify_only` alto = mucho chatter INFO (normal). `preempted` = SIGNAL cortada por DANGER
(deseado). `dropped_stale` alto en DANGER/SIGNAL = revisar (no debería pasar).

## Reglas
Fallback en `speak.sh` si el daemon cae (mkdir-mutex, nunca mudo). Señal-solamente (solo lee
cola + `say`). No `say -v` directo (se pisa). Ver cockpit [[chart-cockpit]] (los marcadores del
chart salen de las mismas señales) y [[fleet-ops]] (arranque de la flota).
