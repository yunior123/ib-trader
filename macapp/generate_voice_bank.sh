#!/bin/zsh
# Genera el banco de clips con ElevenLabs desde voice_bank_texts.txt (fuente única).
# Idempotente: no regenera clips existentes. Uso: generate_voice_bank.sh [--dry-run] [--voice VOICE_ID]
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"

# Resolución de la API key con precedencia: Application Support > config/feeds.env
KEY=""
SUPPORT_DIR="$HOME/Library/Application Support/ib-trader"
CONFIG_JSON="$SUPPORT_DIR/config.json"

# 1. Intentar leer de config.json (guardado en el panel)
if [ -f "$CONFIG_JSON" ]; then
  KEY=$(python3 -c "import json; c=json.load(open('$CONFIG_JSON')); print(c.get('elevenlabsKey',''))" 2>/dev/null)
fi

# 2. Fallback: leer de config/feeds.env (repo o Application Support)
if [ -z "$KEY" ]; then
  if [ -f "$SUPPORT_DIR/config/feeds.env" ]; then
    KEY=$(grep '^ELEVENLABS_API_KEY=' "$SUPPORT_DIR/config/feeds.env" | cut -d= -f2)
  fi
fi

# 3. Fallback: leer de repo feeds.env
if [ -z "$KEY" ]; then
  if [ -f "$ROOT/config/feeds.env" ]; then
    KEY=$(grep '^ELEVENLABS_API_KEY=' "$ROOT/config/feeds.env" | cut -d= -f2)
  fi
fi

if [ -z "$KEY" ]; then
  echo "sin ELEVENLABS_API_KEY en Application Support/config.json, feeds.env o repo"
  exit 1
fi

VOICE="EXAVITQu4vr4xnSDxMaL"   # Sarah multilingual; cambiar con --voice tras elegir Yunior
DRY=0
[ "$1" = "--dry-run" ] && DRY=1
[ "$1" = "--voice" ] && VOICE=$2
mkdir -p voice_bank
tot=0; new=0
while IFS='|' read -r num txt; do
  n=$(echo $num | tr -d ' '); t=$(echo $txt | sed 's/^ //')
  out="voice_bank/${n}.mp3"
  tot=$((tot+${#t}))
  [ -s "$out" ] && continue
  if [ $DRY = 1 ]; then echo "GENERARIA $n: $t"; continue; fi
  code=$(curl -s -m 30 -X POST "https://api.elevenlabs.io/v1/text-to-speech/$VOICE" \
    -H "xi-api-key: $KEY" -H "Content-Type: application/json" \
    -d "{\"text\":$(python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$t"),\"model_id\":\"eleven_multilingual_v2\"}" \
    -o "$out" -w "%{http_code}")
  if [ "$code" != "200" ]; then
    echo "FALLO $n ($code): $(head -c 120 "$out")"; rm -f "$out"
    grep -q quota_exceeded <<< "$(head -c 200 /dev/null)" 2>/dev/null
    [ "$code" = "401" ] && { echo "SIN CRÉDITOS — reintenta tras recarga/reset"; exit 2; }
  else new=$((new+1)); echo "OK $n: $t"; fi
  sleep 0.4
done < voice_bank_texts.txt
echo "clips nuevos: $new | caracteres del banco: $tot | en voice_bank/: $(ls voice_bank/*.mp3 2>/dev/null | wc -l | tr -d ' ')"
