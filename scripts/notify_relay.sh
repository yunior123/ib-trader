#!/bin/zsh
# notify_relay.sh — espejo -> ntfy.sh (push) + Resend (email, solo 🚨).
# v2 (2026-07-28, Yunior "notificaciones cortas y precisas en ntfy, macos, all over"):
# ya NO re-deriva "es esto notificable" por regex sobre el log completo (fragil, y el
# texto que mandaba a ntfy era el mismo parrafo tecnico completo, truncado a lo bruto
# a 180 caracteres). Cada alarma escribe DIRECTO a data/notify_push.txt (via
# scripts/notify_short.py) SOLO cuando de verdad dispara voz/banner — este relay solo
# reenvia esa version corta, ya filtrada por el propio codigo que decide notificar.
# Sin fecha en el nombre: notify_short.py ya trunca a las ultimas 500 lineas el mismo,
# asi que no hace falta reabrir el tail a medianoche.
# LEY ANTI-RUIDO (2026-07-17, sigue vigente): si la alerta no es FRESCA (<=45s) NO se
# envia. Dedup + cap 1/5s con bypass de prioridad.
# BACKLOG SILENCIOSO (2026-08-03): notify_short.py REESCRIBE el fichero entero en cada
# push (anillo de 500 lineas, notify_short.py:26-31). `tail -F` ve encoger el fichero y
# lo RELEE desde el principio -> las 500 lineas vuelven a pasar por aqui, se descartan
# todas por viejas... y cada una dejaba su linea DESCARTADA en el log. Medido: 305.845
# DESCARTADA en 7 dias frente a 1.650 envios reales (ratio 185:1) y logs/notify_relay.log
# de 205 MB. No es un fallo de envio (la ley de frescura hizo su trabajo) sino de RUIDO en
# el log, que es donde se diagnostica. El backlog se salta en SILENCIO; lo que se sigue
# registrando es el retraso INTERESANTE (45s..BACKLOG_S), que si dice algo.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"; source config/feeds.env 2>/dev/null
F="$ROOT/data/notify_push.txt"
touch "$F"
BACKLOG_S=${BACKLOG_S:-300}   # mas viejo que esto = relectura del anillo, no una alerta tardia
LAST=""; LASTSENT=0
# El log se diagnostica a mano: si crece sin freno deja de servir (llego a 205 MB).
if [[ -f logs/notify_relay.log ]] && (( $(stat -f %z logs/notify_relay.log) > 20000000 )); then
  tail -n 2000 logs/notify_relay.log > logs/notify_relay.log.tmp \
    && mv logs/notify_relay.log.tmp logs/notify_relay.log
  echo "$(date +%H:%M:%S) log rotado (>20 MB): conservadas las ultimas 2000 lineas" >> logs/notify_relay.log
fi
tail -n0 -F "$F" 2>/dev/null | while read -r line; do
  hh=$(echo "$line" | grep -oE '^[0-9]{2}:[0-9]{2}' | head -1)
  [[ -z "$hh" ]] && hh=$(date +%H:%M)
  now_s=$(date +%s); line_s=$(date -j -f '%Y-%m-%d %H:%M' "$(date +%F) $hh" +%s 2>/dev/null || echo $now_s)
  age=$(( now_s - line_s ))
  if (( age > BACKLOG_S || age < -60 )); then continue; fi   # relectura del anillo: sin voz y sin log
  if (( age > 45 )); then
    echo "$(date +%H:%M:%S) DESCARTADA (${age}s vieja): ${line:0:60}" >> logs/notify_relay.log; continue
  fi
  [[ "$line" == "$LAST" ]] && continue
  # PRIORIDAD: SELL/STOP/TERREMOTO/DANGER/🌋 saltan el cap 1/5s (cazado 2026-07-27:
  # el cap mato dos señales SELL seguidas, las mejores del dia).
  if (( now_s - LASTSENT < 5 )); then
    if echo "$line" | grep -qE 'SELL|STOP|TERREMOTO|DANGER|🌋'; then
      echo "$(date +%H:%M:%S) PRIORIDAD salta cap: ${line:0:50}" >> logs/notify_relay.log
    else
      echo "$(date +%H:%M:%S) CAP 1/5s: ${line:0:50}" >> logs/notify_relay.log; continue
    fi
  fi
  LAST="$line"; LASTSENT=$now_s
  msg="${line:0:180}"
  curl -s --max-time 5 -d "$msg" -H "Title: 🔔 flota" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null &
  if echo "$line" | grep -q '🚨'; then
    curl -s --max-time 8 -X POST https://api.resend.com/emails \
      -H "Authorization: Bearer $RESEND_KEY" -H "Content-Type: application/json" \
      -d "{\"from\":\"onboarding@resend.dev\",\"to\":[\"$RESEND_TO\"],\"subject\":\"🚨 flota: ${msg:0:60}\",\"text\":\"$msg\"}" >/dev/null &
  fi
  echo "$(date +%H:%M:%S) ENVIADA: ${msg:0:60}" >> logs/notify_relay.log
done
