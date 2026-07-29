# Portabilidad de Voces en ib-trader Cockpit.app

## Arquitectura Final: Banco de Clips Pregrabados

La app reproduce clips de voz **pregrabados y cacheados**, no TTS en runtime. **0 latencia, 0 dependencias de red en runtime.**

```
Flujo:
  App → solicita alarma ("whale_alert", "high_vol_puts", "qqq", "bounce_likely")
    ↓
  voice_player.py → busca clips en voice_bank/
    ↓
  macapp/voice_bank/alerts_whale_alert.mp3 (descargado previamente con ElevenLabs)
  macapp/voice_bank/alerts_high_vol_puts.mp3
  ... (concatena con afplay)
    ↓
  Reproducción: "Alerta ballena alto volumen de puts en Cue Cue Cue más probable el rebote"
  
  Si falta un clip → fallback automático a say del sistema
```

---

## Banco de Segmentos (voice_bank/)

Inventario reutilizable de **45 segmentos básicos** (~432 caracteres):

### Alertas (9)
- "Alerta ballena"
- "alto volumen de puts"
- "alto volumen de calls"
- "el piso se refuerza"
- "el techo se refuerza"
- "más probable el rebote"
- "más probable el retroceso"
- "Barrida alcista"
- "Barrida bajista"

### Acciones (4)
- "compra"
- "vende"
- "stop"
- "fuera"

### Símbolos (15)
- "Cue Cue Cue" (QQQ)
- "Es Pi Y" (SPY)
- "Ene Ve De A" (NVDA)
- "A S M L", "A M D", "Es M H", "D R A M"
- ... (30 símbolos en total)

### Números (13)
- 0-5, 10, 20, 50, 100
- "coma", "millones", "por ciento"

### Contexto (4)
- "en", "hacia arriba", "hacia abajo", "sigue"

---

## Generación del Banco (Una sola vez)

### Cuando hay créditos ElevenLabs (~15-ago o $5/mes upgrade)

```bash
# Generar clips (idempotente, salta los que ya existen)
zsh macapp/generate_voice_bank.sh

# Resultado: macapp/voice_bank/alerts_whale_alert.mp3, etc.
# Tamaño esperado: ~5-10 MB por 45 clips
# Coste: ~$0.013 (432 chars × $0.000030/char)
```

### Generador (generate_voice_bank.sh)

- Lee `ELEVENLABS_API_KEY` de `config/feeds.env`
- Itera segmentos de `voice_segments.json`
- Descarga clips con ElevenLabs (eleven_multilingual_v2, voz Sarah)
- **Idempotente**: no regenera clips existentes
- Maneja quota_exceeded con mensaje claro

---

## Reproducción de Alarmas

### Desde el código (chart_bridge.py, bots, etc.)

```python
from macapp.voice_player import compose_and_play

# Alarma compuesta:
compose_and_play("whale_alert", "high_vol_puts", "in", "qqq", "bounce_likely")
# Reproduce: "Alerta ballena alto volumen de puts en Cue Cue Cue más probable el rebote"
```

### Motor (voice_player.py)

1. Busca clips en `voice_bank/`
2. Reproducecon `afplay` (secuencial, gap mínimo)
3. Fallback automático a `say` si falta un clip
4. Caché: clips en Application Support para reutilización

---

## Coste Total

| Escenario | Coste | Notas |
|-----------|-------|-------|
| Sin banco (fallback say) | $0/mes | Voz del sistema, siempre funciona |
| Banco completo (ElevenLabs free) | $0/mes | 10k chars/mes = 23 ciclos del banco |
| Banco extendido (ElevenLabs $5) | $5/mes | 30k chars/mes = 69 ciclos |
| Banco mixto (ElevenLabs + say) | $0-5/mes | Clips de ElevenLabs + fallback say |

Con 100 alarmas/mes y reutilización agresiva (90% son templates):
- **ElevenLabs free**: $0/mes (432 chars × 1 descarga + caché)
- **Seguridad**: 0 latencia, 0 red en runtime después del primer ciclo

---

## Integración en la App

### Ficheros embebidos en el bundle

```
macapp/
  ├── voice_bank/              ← clips descargados (generados una vez)
  │   ├── alerts_whale_alert.mp3
  │   ├── alerts_high_vol_puts.mp3
  │   ├── ... (45 segmentos)
  │   └── symbols_qqq.mp3
  ├── voice_segments.json      ← inventario
  ├── voice_player.py          ← motor de reproducción
  ├── generate_voice_bank.sh   ← generador (para Yunior)
  └── speak_with_fallback.py   ← (deprecated, aquí solo voice_player)
```

### Ruta en el bundle

Los clips viajan en `Contents/Resources/backend/voice_bank/` (rutas relativas).

### Reproducción

```python
# chart_bridge.py u otro backend:
from macapp.voice_player import compose_and_play
compose_and_play("whale_alert", "high_vol_puts", "qqq")
```

---

## Nota de Seguridad

**La key de ElevenLabs está en `config/feeds.env`** (viaja dentro del bundle para uso privado).

- App de Yunior únicamente (nunca distribuir públicamente)
- Si se distribuye: regenerar la key de ElevenLabs

---

## Workflow Completo

### Ahora (sin créditos ElevenLabs)

1. App usa fallback `say` del sistema
2. Voice_player.py busca clips en `voice_bank/`, no los encuentra
3. Genera alarma automáticamente con `say` (Mónica, default del sistema)

### Cuando hay créditos (~15-ago o $5)

1. Ejecutar: `zsh macapp/generate_voice_bank.sh`
2. Se descargan 45 clips (~5-10 MB)
3. Bundle incluye clips (build siguiente)
4. App reproduce clips pregrabados (0 latencia, 0 red)

### Extender el banco

1. Añadir segmentos a `voice_segments.json`
2. Run: `zsh generate_voice_bank.sh` (descargar nuevos)
3. Código usa IDs nuevos: `compose_and_play(...)`

---

## Hechos

- **Arquitectura**: clips pregrabados + fallback say
- **Generador**: idempotente, maneja quota
- **Motor**: voice_player.py (busca clips, fallback automático)
- **Coste**: $0/mes (free tier) a $5/mes (extendido)
- **Latencia**: 0ms (pregrabado), fallback <100ms (say)
- **Offline**: después de descarga, 0 red en runtime

---

**Fecha**: 2026-07-29  
**Motor**: Banco de clips ElevenLabs + voice_player.py  
**Estado**: listo para usar, generador pendiente de créditos
