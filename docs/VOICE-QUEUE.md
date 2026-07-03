# Sistema de VOZ SERIALIZADA + auto-calidad (2026-07-18)

Yunior: "las voces se interponen en mi mac y apenas escucho" + "voice quality is terrible".

## Problema resuelto
Los 23 signal_bots + price_alarm hacían `killall say; say -v X ... &` → cada alerta
**cortaba a la anterior a media frase** (ininteligible en avalanchas).

## Arquitectura (aditiva, no rompe nada)
- **`scripts/voice_queue.sh`** — daemon: único que habla. Serializa (sin `&`, sin
  `killall`) → cada frase entera. Descarta voz stale >25s. Coalesce avalanchas
  ("...y N alertas más"). Prioridad DANGER > SIGNAL > INFO. Bash 3.2 compatible.
- **`scripts/speak.sh <PRIO> "<msg>"`** — productor: encola (instantáneo). Fallback
  con mutex `mkdir` si el daemon está caído (macOS no tiene `flock`).
- **`scripts/voice_queue_keepalive.sh`** — lo mantiene vivo. Enganchado a
  `fleet_keepalive_start.sh` (arranca antes que los productores).
- Migrado 2026-07-18: `price_alarm.cpp` + **los 22 signal_bots** (todos recompilados
  en C++23 -O3 -march=native). Backup en backup/voice_migration_2026-07-18/.

## Auto-calidad de voz
El daemon habla con `say` SIN `-v` = voz del sistema (Siri, la que eligió Yunior).
Una sola voz hermosa para todo; distinción por contenido + orden por prioridad.

### RESUELTO: voz Siri del sistema (Yunior eligió "la hermosa")
Hallazgo: las Siri NO van por `say -v <nombre>` (fallback), PERO `say` SIN `-v` usa
la **voz del SISTEMA**. Yunior la fijó a **Siri Voice 2** en System Settings >
Accessibility > Spoken Content > System Voice. El daemon habla `say "$msg"` (sin -v)
= voz Siri hermosa. Para cambiarla: cambiar la voz del sistema en Ajustes, no el código.
4. Listo: el daemon la detecta y usa automáticamente al reiniciar.

## Migración de los 22 bots — COMPLETADA 2026-07-18
Patrón idéntico reemplazado (`: '%s'` consume el arg de voz sin tocar el snprintf):
`killall say; say -v X ... &`  →  `scripts/speak.sh SIGNAL '...' &`. Los 22
recompilados C++23 -O3 -march=native, 0 fallos. Backup: backup/voice_migration_2026-07-18/.

## Nombres reales de tickers (Yunior 2026-07-18)
Traducción centralizada en `speak.sh` (sirve a todos): NVDA→Nvidia, TSLA→Tesla,
AAPL→Apple, MU→Micron, INTC→Intel, GOOGL→Google, MSFT→Microsoft, META→Meta,
AMZN→Amazon, AVGO→Broadcom, TSM→Taiwán Semi, QCOM→Qualcomm, TXN→Texas Instruments,
SPCX→Space X, SKHY→S K Hynix, NOK→Nokia, ASML→A S M L, SMH→semis, QQQ→Nasdaq,
XLK→tecnología, AMD→A M D, DRAM→D RAM, GLD→oro, SLV→plata, CPER→cobre, USO→petróleo.

## Infra pendiente (bridges, c++ latest)
alpaca_ws_bridge / scan_server / x_whale_bot / screener_alert compilan c++23 pero
necesitan su build command con libs (curl/openssl/Network). Son data-plane, no path
de señal. Actualizar con su Makefile/comando real cuando toque.


Ver [[cpp-latest-fast-quality-emblem]] · [[voice-queue-audio-system]] (memoria).

## Sonidos PRO (2026-07-18, elección Yunior)

Tonos AAC calidad iPhone extraídos de ToneLibrary → convertidos a `~/Library/Sounds/*.aiff`
(afconvert), usables por nombre en `display notification sound name "ProX"`:

| Sonido | Uso | Dónde |
|---|---|---|
| **ProChord** | Señales BUY/SELL (default) | `fleet_notify.h` default → 22 bots |
| **ProAlert** | Ballenas / muros de opciones | `qqq_xray`, banners whale explícitos |
| **ProAlarm** | CRÍTICOS (dinero en juego) | sirena `price_alarm` ×3 + su banner, TWS caído |
| ProComplete | INFO / confirmaciones suaves | disponible |
| ProNote, ProPulse, ProAurora, ProRadar, ProApex, ProBeacon | reserva | `~/Library/Sounds/` |

Sirena `price_alarm`: ProAlarm ×3 con fallback a `sounds/fire_alarm.wav` si falta el aiff.

## Anti-descarte de banners (hallazgo empírico 2026-07-18)

macOS **descarta** banners que llegan en el mismo instante desde la misma app
(3 simultáneos → el de en medio se perdía SIEMPRE; separados 0.4s llegan los 3;
`delay` posterior NO lo arregla). Fix en `fleet_notify.h`: el hijo osascript duerme
un jitter aleatorio 0–0.45s ANTES de publicar + `delay 0.6` final (entrega completa
antes de morir). El caller sigue volviendo en ~0.1ms. Además: Ajustes →
Notificaciones → Script Editor → **Agrupación: Desactivada** (Yunior lo hizo 2026-07-18).

## Guardia de instancia única (voice_queue.sh)

Dos daemons compitiendo por la cola duplican/pierden voces (pasó en test). Si el
pidfile apunta a un proceso vivo, el segundo daemon sale sin arrancar.

Suite bulletproof 2026-07-18: 7/7 ✓ (instancia única, 10 productores concurrentes,
prioridad+coalescing, stale purge, tickers word-boundary, fallback mutex, salud final).

## Campaña de verificación profunda 2026-07-18 (sistema financiero = 0 errores)

- **Unit**: 41/41 ✓ — funciones REALES de producción (parse_rule, sh_sanitize,
  as_escape, px_from_bars, mark_fired, lógica cross) bajo ASan+UBSan.
- **Integración price_alarm**: 14/14 ✓ — binario ASan en entorno aislado: disparo
  down, armado+disparo cross, stale JAMÁS dispara, línea inválida logueada 1 vez,
  marca [DISPARADA] atómica, NO doble disparo, espejo Desktop, 0 errores sanitizer.
- **Replay real**: bot NVDA ASan + 3,257 bars reales del 17-jul → reprodujo la
  sesión (SELL 10:30 reversa, 11:50 pullback, 12:10 ruptura TL = el H&S que se
  tradeó), 33 eventos radar, 0 errores. Datos sintéticos mansos no disparan V6
  (correcto: umbrales reales).
- **Stress**: 30 productores paralelos → 0 pérdidas, coalescing 1 frase + "y N más",
  drenaje completo. Encolar: ~40ms. Banner caller: 151–180μs (1.6ms la 1ª por init).
- **Warnings**: 0 en 24 fuentes (-Wall -Wextra); eliminada variable muerta a5o de los 22 bots.
- **ProAlarm recortada 18.9s → 3.0s** (sirena ×3 = 9s, antes 57s); original en
  ProAlarmFull.aiff. Poll del daemon 30→50ms (CPU idle ~1.7%, latencia imperceptible).
- Regla operativa: matar `voice_queue_keepalive.sh` ANTES que el daemon (si no, resucita).
