#!/bin/zsh
# notify_relay.sh — espejo Desktop -> ntfy.sh (push) + Resend (email, solo 🚨).
# LEY ANTI-RUIDO (Yunior 2026-07-17): si la alerta no es FRESCA (<=45s) NO se
# envia — una alerta vieja es desinformacion. Dedup + cap 1/5s.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"; source feeds.env 2>/dev/null
F="$ROOT/data/trading-signals/$(date +%F).txt"
touch "$F"; LAST=""; LASTSENT=0
tail -n0 -F "$F" 2>/dev/null | while read -r line; do
  # solo lineas de VALOR al telefono (alineado con la voz DANGER+SIGNAL, 2026-07-23):
  # ballena/spike/dip/cusum/alarma/estructural/BB-rebote + legacy. Se EXCLUYE el chatter
  # INFO (MUTED, p<55). Todo se guarda local igual (BD signals); ntfy = solo push del dia.
  echo "$line" | grep -qE '🐋|🚀|🩸|🧲|🌋|⏰|🚨|BALLENA|SPIKE|DIP REAL|TERREMOTO|ESTRUCTURAL|ALARM|COMPRAR|VENDER|V6 (BUY|SELL)|FLUJO DE (PUTS|CALLS)|TRAMPA' || continue
  # BB REBOTE (~136/dia) se EXCLUYE del telefono: es chatter INFO de baja conviccion
  # (BB-solo pierde en backtest) -> inundaria. Se guarda local + se ve en el chart igual.
  echo "$line" | grep -qE 'MUTED' && continue
  hh=$(echo "$line" | grep -oE '^[0-9]{2}:[0-9]{2}' | head -1)
  [[ -z "$hh" ]] && hh=$(date +%H:%M)
  now_s=$(date +%s); line_s=$(date -j -f '%Y-%m-%d %H:%M' "$(date +%F) $hh" +%s 2>/dev/null || echo $now_s)
  age=$(( now_s - line_s ))
  if (( age > 45 || age < -60 )); then
    echo "$(date +%H:%M:%S) DESCARTADA (${age}s vieja): ${line:0:60}" >> notify_relay.log; continue
  fi
  [[ "$line" == "$LAST" ]] && continue
  (( now_s - LASTSENT < 5 )) && { echo "$(date +%H:%M:%S) CAP 1/5s: ${line:0:50}" >> notify_relay.log; continue; }
  LAST="$line"; LASTSENT=$now_s
  msg="${line:0:180}"
  curl -s --max-time 5 -d "$msg" -H "Title: 🔔 flota" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null &
  if echo "$line" | grep -q '🚨'; then
    curl -s --max-time 8 -X POST https://api.resend.com/emails \
      -H "Authorization: Bearer $RESEND_KEY" -H "Content-Type: application/json" \
      -d "{\"from\":\"onboarding@resend.dev\",\"to\":[\"$RESEND_TO\"],\"subject\":\"🚨 flota: ${msg:0:60}\",\"text\":\"$msg\"}" >/dev/null &
  fi
  echo "$(date +%H:%M:%S) ENVIADA: ${msg:0:60}" >> notify_relay.log
done
