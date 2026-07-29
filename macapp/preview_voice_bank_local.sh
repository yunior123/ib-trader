#!/bin/zsh
# Preview del banco de voz con la voz del SISTEMA (la de Yunior) para corregir textos
# ANTES de gastar créditos ElevenLabs. Uso: preview_voice_bank_local.sh [--from N] [--solo N]
cd "$(dirname "$0")"
FROM=1; SOLO=""
[ "$1" = "--from" ] && FROM=$2
[ "$1" = "--solo" ] && SOLO=$2
while IFS='|' read -r num txt; do
  n=$(echo $num | tr -d ' ' | sed 's/^0*//')
  [ -n "$SOLO" ] && [ "$n" != "$SOLO" ] && continue
  [ -z "$SOLO" ] && [ "$n" -lt "$FROM" ] && continue
  say "$n.$txt"
  sleep 0.25
done < voice_bank_texts.txt
