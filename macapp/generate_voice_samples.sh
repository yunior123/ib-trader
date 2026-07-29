#!/bin/zsh
# generate_voice_samples.sh — genera muestras con ElevenLabs
# Uso: zsh macapp/generate_voice_samples.sh

set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"

CONFIG="$REPO/config/feeds.env"
if [ ! -f "$CONFIG" ]; then
  echo "🔴 Error: config/feeds.env no encontrado"
  exit 1
fi

KEY=$(grep "ELEVENLABS_API_KEY=" "$CONFIG" | cut -d= -f2 | tr -d '"' | tr -d ' ')
if [ -z "$KEY" ]; then
  echo "🔴 Error: ELEVENLABS_API_KEY no encontrada"
  exit 1
fi

PHRASE="Alerta ballena. Alto volumen de puts en QQQ. El piso se refuerza. Espera el rebote."
SAMPLE_DIR="$REPO/macapp/voice_samples"
mkdir -p "$SAMPLE_DIR"

echo "Generando muestras con ElevenLabs..."
echo "Frase: $PHRASE"
echo ""

# Voces candidatas: nombre y ID
test_voice() {
  local name="$1"
  local voice_id="$2"
  local filename="${SAMPLE_DIR}/elevenlabs_${name}.wav"
  
  echo -n "  $name ... "
  
  curl -fsSL -X POST "https://api.elevenlabs.io/v1/text-to-speech/${voice_id}" \
    -H "xi-api-key: $KEY" \
    -H "Content-Type: application/json" \
    -d '{"text": "'"$PHRASE"'", "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}' \
    -o "$filename" 2>&1
  
  if [ -f "$filename" ] && [ -s "$filename" ]; then
    size=$(du -h "$filename" | cut -f1)
    echo "✓ $size"
    return 0
  else
    cat "$filename" 2>/dev/null | grep -q "quota" && echo "✗ Sin créditos (quota)"
    cat "$filename" 2>/dev/null | grep -q "401" && echo "✗ Key inválida (401)"
    rm -f "$filename" 2>/dev/null || true
    return 1
  fi
}

# Voces femeninas españolas
test_voice "sarah_professional" "EXAVITQu4vr4xnSDxMaL" || true
test_voice "elena_es" "mHFEJFkVmvLmJplqFKJ5" || true
test_voice "sofia_mx" "BZJb5LjkCzhUL0Z1WuC8" || true

echo ""
echo "=== Resultado ===" && \
ls -lh "$SAMPLE_DIR"/elevenlabs_*.wav 2>/dev/null || \
echo "⚠️  No se generaron muestras — probablemente sin créditos ElevenLabs"
