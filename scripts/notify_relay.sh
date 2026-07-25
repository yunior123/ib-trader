#!/bin/zsh
# notify_relay.sh — espejo Desktop -> ntfy.sh (push) + Resend (email, solo 🚨).
# LEY ANTI-RUIDO (Yunior 2026-07-17): si la alerta no es FRESCA (<=45s) NO se
# envia — una alerta vieja es desinformacion. Dedup + cap 1/5s.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"; source feeds.env 2>/dev/null
# ROTACION DE MEDIANOCHE (fix 2026-07-24): antes `F` se calculaba UNA VEZ al
# arrancar y `tail -F` seguia ese archivo para siempre. Si el relay sobrevivia a
# medianoche quedaba vigilando el archivo de AYER -> CERO pushes en todo el dia,
# y el keepalive no lo detectaba porque el proceso seguia VIVO (pgrep no sabe que
# esta mirando el fichero equivocado). Ahora el tail muere en el cambio de dia y
# el bucle exterior lo re-abre sobre el archivo nuevo.
LAST=""; LASTSENT=0
while true; do
F="$ROOT/data/trading-signals/$(date +%F).txt"
touch "$F"
SECS_TO_MIDNIGHT=$(( $(date -j -f "%Y-%m-%d %H:%M:%S" "$(date -v+1d +%F) 00:00:05" +%s) - $(date +%s) ))
[ "$SECS_TO_MIDNIGHT" -lt 60 ] && SECS_TO_MIDNIGHT=60
echo "$(date +%H:%M:%S) relay siguiendo $F (rota en ${SECS_TO_MIDNIGHT}s)" >> notify_relay.log
timeout "$SECS_TO_MIDNIGHT" tail -n0 -F "$F" 2>/dev/null | while read -r line; do
  # FIX 2026-07-25: el patron decia `V6 (BUY|SELL)` pero los bots NUNCA escriben "V6"
  # en el titulo — v6_emit() llama a notify("<SYM>: BUY"/"<SYM>: SELL"), asi que la
  # linea real es "AAPL: BUY". Resultado medido el 24-jul: las 12 señales V6 vivas del
  # dia (las de mayor conviccion del motor) no llegaron NI al telefono NI a la voz.
  # Ahora el patron casa el formato que de verdad se emite.
  # solo lineas de VALOR al telefono (alineado con la voz DANGER+SIGNAL, 2026-07-23):
  # ballena/spike/dip/cusum/alarma/estructural/BB-rebote + legacy. Se EXCLUYE el chatter
  # INFO (MUTED, p<55). Todo se guarda local igual (BD signals); ntfy = solo push del dia.
  echo "$line" | grep -qE '🐋|🚀|🩸|🧲|🌋|⏰|🚨|BALLENA|SPIKE|DIP REAL|TERREMOTO|ESTRUCTURAL|ALARM|COMPRAR|VENDER|[A-Z]{2,6}: (BUY|SELL)|FLUJO DE (PUTS|CALLS)|TRAMPA' || continue
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
done   # fin del bucle exterior: re-abre el tail sobre el archivo del dia nuevo
