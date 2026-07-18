---
name: hft-financial-systems
description: Disciplina de sistemas financieros de alta velocidad para ib-trader — latencia medida en μs/ms, cero pérdida de alertas, testing por capas (unit+integración+replay real+stress+sanitizers), fail-loud, datos frescos o nada, y checklist anti-errores antes de cada cambio. Usar al diseñar/tocar cualquier componente del path de señal, al hacer testing profundo, o cuando Yunior diga "top system", "bulletproof", "no mistakes".
---

# HFT / Financial Systems — cero errores, velocidad medida

## Principios (ley de la casa)

1. **Señal-solamente** (ley #0): nada ejecuta órdenes. Jamás.
2. **Datos frescos o nada**: NBBO ≤10s, bars ≤180s; sin dato fresco NO hay alarma
   (verificado: dato stale jamás dispara). Silencio > mentira.
3. **Fail-loud**: los fallos suenan (banner FINVIZ ROTO, TWS WATCHDOG). Nunca
   fallback silencioso a datos peores.
4. **Una alerta dispara UNA vez** (idempotencia): marca `[DISPARADA ...]` con
   rewrite atómico tmp+rename; re-armar es acción humana.
5. **Latencia presupuestada**: caller de banner ~180μs; encolar voz ~40ms;
   detección→alerta <1s (loop 1Hz). Medir, no asumir (ley 3 empírica).
6. **Sin locks en el hot path**: append atómico O_APPEND <PIPE_BUF, archivos-cola
   con rename, mkdir-como-mutex solo en fallbacks.

## Pirámide de testing (obligatoria tras cambios en el path de señal)

| Capa | Qué | Cómo (probado 2026-07-18) |
|---|---|---|
| Unit | funciones reales de producción | `#define main x_main` + include del .cpp; ASan+UBSan; 41 checks price_alarm |
| Integración | binario completo, entorno aislado | HOME falso + nbbo sintético → 14 asserts (down/cross/stale/inválida/no-doble-disparo/espejo) |
| **Replay real** | lógica contra el mercado real | `./bot_asan --stdin < data/bars_<sym>_ibkr.txt` → debe reproducir las señales del día real |
| Stress | concurrencia | 30 productores paralelos → 0 pérdidas, coalescing, drenaje |
| Sanitizers | memoria/UB | ASan+UBSan en TODAS las capas anteriores → 0 informes |

Datos sintéticos mansos NO disparan señales V6 (probado) — el replay de verdad
se hace con datos reales de IBKR del repo.

## Checklist anti-errores (antes de dar por bueno)

- [ ] ¿Compiló todo con 0 warnings? ¿ASan limpio?
- [ ] ¿La alerta puede disparar DOS veces? ¿Perderse? ¿Llegar tarde? Probar cada una.
- [ ] ¿Qué pasa con dato stale / archivo corrupto / línea inválida / daemon caído?
      (todas tienen ruta probada: skip+log, rechazo, log 1 vez, fallback mutex)
- [ ] ¿Inyección? Todo string a shell pasa por `sh_sanitize`; a AppleScript por `as_escape`.
- [ ] ¿Procesos huérfanos? matar keepalive ANTES que el daemon; guardia de instancia única.
- [ ] ¿Se probó el path que duele (ley 12)? afterhours, casi-umbral, avalancha.

## Sonidos = canal de información (elección Yunior 2026-07-18)

ProChord señal · ProAlert ballena/muro · ProAlarm crítico (3s, ×3 = 9s de sirena;
versión completa en ProAlarmFull.aiff) · voz Siri serializada con nombres reales.
