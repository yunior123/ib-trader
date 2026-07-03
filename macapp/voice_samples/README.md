# Voice Samples — Candidatos para ib-trader Cockpit.app

**Objetivo**: Yunior elige la voz que la app usará. Las muestras se generaron con una frase de alarma real.

> "Alerta ballena. Alto volumen de puts en QQQ. El piso se refuerza. Espera el rebote."

---

## Candidatos Disponibles

### Muestras Presentes (macOS TTS)

| Muestra | Motor | Idioma | Calidad | Embedding |
|---------|-------|--------|---------|-----------|
| `monica.wav` | macOS Text-to-Speech | es_ES | Estándar, femenino | ✓ (sistema) |
| `paulina.wav` | macOS Text-to-Speech | es_MX | Estándar, femenino | ✓ (sistema) |
| `eddy_es.wav` | macOS Text-to-Speech | es_ES | Robótico/estándar | ✓ (sistema) |
| `shelley_es.wav` | macOS Text-to-Speech | es_ES | Estándar, femenino | ✓ (sistema) |

### Muestras Pendientes (cuando hay créditos)

| Motor | Voz | Calidad | Coste | Estado |
|-------|-----|---------|-------|--------|
| **ElevenLabs** (motor canónico) | Sarah (femenino, professional) | Superior | Free: 10k/mes, Starter: $5/mes | 🔴 Sin créditos (~reset 15-ago) |
| OpenAI TTS-1-HD | nova (femenino) | Superior | $0.015 / 1k chars (~$15/1M) | 📋 Integrado, sin key |
| Piper arm64 embebido | es_ES-medium | Buena | Gratis (offline) | ⏳ Compilación pending |

---

## Arquitectura de Fallback

La app **elige automáticamente** la mejor voz disponible sin intervención del usuario:

```
1. ElevenLabs TTS (key en config/feeds.env)
   ↓ (si no hay créditos/red)
2. OpenAI TTS (key en config/llm.env)
   ↓ (si no hay key/red)
3. Piper embebido (arm64 + modelo dentro del .app)
   ↓ (si no está compilado)
4. say de macOS (voz del sistema, always-on)
```

Cada nivel cachea sus wav en `~/Library/Application Support/ib-trader/voice_cache/`. 
**Resultado**: frases repetidas (90% de alarmas) suenan gratis tras la primera llamada.

---

## Cómo Yunior Elige la Voz Canónica

### Opción 1: Usar una de las muestras presentes (macOS TTS)

1. Escucha: `monica.wav`, `paulina.wav`, etc.
2. Elige la que suene mejor
3. Actualiza en `macapp/speak_with_fallback.py`:
   ```python
   VOICE_VOICE = "monica"  # o "paulina", "shelley_es", "eddy_es"
   ```
4. Build: `zsh macapp/build.sh`
5. La voz viaja con la app (gratis, siempre disponible)

### Opción 2: Esperar a ElevenLabs (mejor calidad, requiere créditos)

1. ElevenLabs: upgrade a $5/mes o espera reset (~15-ago para 10k chars gratis)
2. Run: `zsh macapp/generate_voice_samples.sh` (genera muestras reales)
3. Escucha las muestras ElevenLabs
4. Actualiza `VOICE_VOICE` en speak_with_fallback.py
5. Build: `zsh macapp/build.sh`
6. La key de ElevenLabs viaja con la app (uso privado, no distribuir públicamente)

### Opción 3: Compilar Piper arm64 (mejor offline, mejor que macOS say)

1. Compilar: `cd ~/ib-trader/macapp/piper-src && mkdir build && cd build && cmake .. && make` (~20 min)
2. Descargar modelo: `es_ES-medium.onnx` de huggingface/rhasspy/piper-voices
3. Empaquetar en `macapp/engine/`
4. Build: `zsh macapp/build.sh`
5. La app sale con Piper embebido (~40-50 MB extra)

---

## Coste Total (Ninguno a ~$0.90/año)

| Opción | Mensual | Anual | Por alarma | Incluído en bundle |
|--------|---------|-------|-----------|-------------------|
| macOS TTS (say) | $0 | $0 | $0 | ✓ siempre |
| ElevenLabs (plan free) | $0 | $0 | $0.0083 | ✓ key viaja |
| ElevenLabs (starter) | $5 | $60 | $0.0083 | ✓ key viaja |
| OpenAI TTS-1-HD | ~$0.075 | ~$0.90 | $0.00075 | (key en config/) |
| Piper embebido | $0 | $0 | $0 | ✓ binario + modelo |

Con 100 alarmas/mes y 80% repetidas (caché):
- **ElevenLabs free**: $0/mes (caché activo)
- **ElevenLabs starter**: $5/mes (ínfimo por alarma, mejor calidad)
- **OpenAI**: $0.075/mes (opción B si no hay ElevenLabs)
- **Piper**: $0/mes (offline, sin key)
- **macOS say**: $0/mes (siempre funciona, calidad estándar)

---

## Generación de Muestras

### macOS TTS (ya hechas)

```bash
# Los wav en este directorio ya están generados.
# Para regenerar:
zsh ../generate_voice_samples.sh  # script en macapp/
```

### ElevenLabs (cuando hay créditos)

```bash
# Si se actualizó la key y hay créditos:
zsh ../generate_voice_samples.sh

# Genera: elevenlabs_sarah_professional.wav, etc.
```

---

## Integración en la App

**Archivo motor**: `macapp/speak_with_fallback.py`

```python
def speak(text, voice_name=None):
    """Reproduce texto con fallback inteligente."""
    # Cadena de fallback automática
    # No necesita intervención del usuario
```

**Llamadas desde el backend**:
```python
# Desde chart_bridge.py:
from macapp.speak_with_fallback import speak
speak("Alerta ballena!")  # elige automáticamente
```

---

## Notas Técnicas

### Caché
- Hash MD5 de la frase = nombre del wav
- Misma frase siempre = mismo wav reutilizado
- Ubicación: `~/Library/Application Support/ib-trader/voice_cache/`
- Permisos: readable por cualquier proceso ib-trader, writable por speak_with_fallback.py

### Seguridad (keys en bundle)
- `config/feeds.env` (ElevenLabs) viaja dentro del .app
- `config/llm.env` (OpenAI) viaja dentro del .app
- Solo seguro para uso privado (nunca distribuir públicamente)
- Si se distribuye: regenerar keys

### Fallback
- Si ElevenLabs devuelve 401 quota_exceeded → OpenAI
- Si OpenAI no tiene key/red → Piper
- Si Piper no existe → say
- Si say falla → mensaje de error (nunca ejecuta sin voz)

---

**Fecha**: 2026-07-29  
**Motor canónico**: ElevenLabs (eleven_multilingual_v2)  
**Alternativa offline**: Piper arm64 embebido  
**Fallback final**: macOS say
