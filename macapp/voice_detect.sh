#!/bin/zsh
# voice_detect.sh — INFORMACIÓN SOBRE LA VOZ ACTUAL (NO audio de prueba).
# 
# La app usa SIEMPRE `say` sin -v, que usa la voz del sistema que el usuario
# configuró en Ajustes > Accesibilidad > Contenido Hablado > Voz del Sistema.
#
# Esta función SOLO detecta si la voz actual es Premium/Enhanced (hermosa) o
# estándar (robótica), para INFORMAR al usuario. Jamás sustituye la voz.
#
# Retorna: "premium" | "standard" | "unknown"
# (No produce audio, solo lista con `say -v '?' ` para detectar.)

set -u

# Detectar si hay voces Premium/Enhanced disponibles en el sistema
# Las Siri Voices (Siri Voice 1, 2, etc) NO aparecen en `say -v '?'`
# pero otras Premium/Enhanced SÍ (Mónica, Paulina, Eddy Enhanced, etc)

PREMIUM_INDICATORS=$(say -v '?' 2>/dev/null | grep -E "(Mónica|Paulina|Eddy|Flo|Grandma|Grandpa|Reed|Rocko|Sandy|Shelley).*(es_ES|es_MX)" | wc -l)

if [ "$PREMIUM_INDICATORS" -gt 0 ]; then
  echo "premium"
else
  echo "standard"
fi

exit 0
