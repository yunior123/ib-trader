# Portabilidad de Voces en ib-trader Cockpit.app

## Política: Una sola voz hermosa

La app usa **EXCLUSIVAMENTE** la voz canónica de la casa: **Siri Voice 2** (Premium/Enhanced).

No hay fallback a otras voces. Si Siri Voice 2 no está disponible en el Mac del usuario, la app queda muda y muestra una **notificación visual** con instrucciones exactas de descarga.

## Cómo funciona la voz

### En el código

Scripts empaquetados (`scripts/speak.sh`, `scripts/voice_queue.sh`):
```bash
say "$MSG"    # SIN -v: usa la voz del SISTEMA (lo que el usuario eligió en Ajustes)
```

### En Ajustes del usuario

El usuario configura la voz en:
**Ajustes > Accesibilidad > Contenido Hablado > Voz del Sistema > [+] Descargar > Siri Voice 2**

- Yunior 2026-07-18: eligió la voz hermosa de macOS (Siri Voice 2)
- `say` sin `-v` usa automáticamente lo que esté ahí
- Si el usuario elige otra voz en Ajustes, la app respetará esa elección

## Para nuevo usuario en Mac sin Siri Voice 2

### Paso 1: Descargar la voz (30 segundos)

1. **Abre Ajustes** de macOS
2. **Accesibilidad > Contenido Hablado**
3. En **Voz del Sistema**, elige una con acceso a descargas (cualquiera)
4. Toca **[+] Descargar**
5. Busca y descarga: **Siri Voice 2** (o Siri Voice 1, si prefieres)
6. Seleccionala como voz del sistema (click en ella)

### Paso 2: Abrir la app

La próxima vez que abras ib-trader Cockpit, hablará en la voz hermosa.

## Detección al arranque

**macapp/voice_detect.sh** se ejecuta al abrir la app:

```bash
# Retorna: "premium" si hay voces Premium/Enhanced disponibles
#          "standard" si no
# NO produce audio. SOLO lista con `say -v '?'` para detectar.
```

Si detecta que la voz actual NO es Premium/Enhanced, la app muestra:

> ⚠️ Para mejor experiencia, descarga Siri Voice 2:  
> Ajustes > Accesibilidad > Contenido Hablado > [+] Descargar

Este es un aviso visual (notificación de macOS), NO audio.

## Auditoría de voz

| Fichero | Voz | Línea | Política |
|---------|-----|-------|----------|
| scripts/speak.sh | `say` sin `-v` | 49, 61 | Usa voz del SISTEMA (Siri Voice 2 esperado) |
| scripts/voice_queue.sh | `say` sin `-v` | 55, 75, 92, 95 | Usa voz del SISTEMA (Siri Voice 2 esperado) |
| macapp/voice_detect.sh | detecta (silencioso) | - | SOLO informa al arranque, NO audio |

## Qué es Siri Voice 2

- **Tipo**: Premium/Enhanced de macOS (se descarga, no viene de fábrica)
- **Idioma**: Español, hermosa y profesional
- **Ubicación en Ajustes**: Voz del Sistema > Descargar > "Siri Voice 2"
- **Acceso**: Solo con `say` sin `-v` (Apple bloquea `say -v "Siri Voice 2"`)
- **Fallback en otro Mac**: voz del sistema por defecto (puede ser robótica/inglés)

## Por qué NO hay fallback a otras voces

Yunior 2026-07-26: "only the beautiful spanish voice we have already, only that one".

- **Precisión**: una sola voz (Siri Voice 2) identifica la flota
- **Autoridad**: alertas críticas (DANGER, SIGNAL) merecen la voz elegida, no un sustituto
- **Privacidad**: no reproducir audio sin consentimiento (si la voz falta, notificación visual)

## Instrucciones para README-INSTALL.md

Ver el fichero hermano: `macapp/README-INSTALL.md` (sección "Voz en Español").

## Referencias

- **Siri Voices de macOS**: https://support.apple.com/guide/voiceover/use-siri-voice/mac
- **macOS Accessibility Spoken Content**: Ajustes > Accesibilidad > Contenido Hablado
