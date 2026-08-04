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
F="${NOTIFY_PUSH_FILE:-$ROOT/data/notify_push.txt}"     # override solo para tests
RLOG="${NOTIFY_RELAY_LOG:-logs/notify_relay.log}"
touch "$F"
BACKLOG_S=${BACKLOG_S:-300}   # mas viejo que esto = relectura/arranque, no una alerta tardia
DEDUP_S=${NOTIFY_DEDUP_S:-60} # payload idéntico en 60s = repetición, aunque cambie HH:MM:SS
CAP_S=${NOTIFY_CAP_S:-5}
# PRIVACIDAD (TODO 20): patrones en config/notify_private.txt (compartidos con discord_layout);
# si el fichero falta se usa la copia embebida — jamas se abre la puerta por un unlink.
PRIV_FILE="${NOTIFY_PRIVATE_FILE:-$ROOT/config/notify_private.txt}"
PRIV_RE=$(grep -hvE '^[[:space:]]*(#|$)' "$PRIV_FILE" 2>/dev/null | paste -sd'|' -)
[[ -z "$PRIV_RE" ]] && PRIV_RE='order_engine|ORDEN (ENVIADA|RECHAZADA|LIMITE)|\bFILL\b|realizedPnl|EXPIRA HOY|POSICIONES? (ABIERTA|CERRADA|DESCONOCIDAS)|\bU[0-9]{8}\b|comisi[oó]n|ARM_LIVE|CERRAR\s'
typeset -A DEDUP_AT
LASTSENT=0
# El log se diagnostica a mano: si crece sin freno deja de servir (llego a 205 MB).
if [[ -f "$RLOG" ]] && (( $(stat -f %z "$RLOG") > 20000000 )); then
  tail -n 2000 "$RLOG" > "$RLOG.tmp" && mv "$RLOG.tmp" "$RLOG"
  echo "$(date +%H:%M:%S) log rotado (>20 MB): conservadas las ultimas 2000 lineas" >> "$RLOG"
fi
tail -n0 -F "$F" 2>/dev/null | while read -r line; do
  hh=$(echo "$line" | grep -oE '^[0-9]{2}:[0-9]{2}' | head -1)
  [[ -z "$hh" ]] && hh=$(date +%H:%M)
  now_s=$(date +%s); line_s=$(date -j -f '%Y-%m-%d %H:%M' "$(date +%F) $hh" +%s 2>/dev/null || echo $now_s)
  age=$(( now_s - line_s ))
  if (( age > BACKLOG_S || age < -60 )); then continue; fi   # relectura del anillo: sin voz y sin log
  if (( age > 45 )); then
    echo "$(date +%H:%M:%S) DESCARTADA (${age}s vieja): ${line:0:60}" >> "$RLOG"; continue
  fi
  # PRIVACIDAD (Yunior 2026-08-04): NUESTRAS operaciones no salen del Mac. El banner y la voz
  # locales ya sonaron; ntfy/Resend se saltan. Patrones compartidos: config/notify_private.txt.
  if echo "$line" | grep -qiE "$PRIV_RE"; then
    echo "$(date +%H:%M:%S) PRIVADA (solo local): ${line:0:50}" >> "$RLOG"; continue
  fi
  payload="${line#* | }"
  prev=${DEDUP_AT[$payload]:-0}
  if (( now_s - prev < DEDUP_S )); then
    continue
  fi
  # PRIORIDAD: SELL/STOP/TERREMOTO/DANGER/🌋 saltan el cap 1/5s (cazado 2026-07-27:
  # el cap mato dos señales SELL seguidas, las mejores del dia).
  if (( now_s - LASTSENT < CAP_S )); then
    if echo "$line" | grep -qE 'SELL|STOP|TERREMOTO|DANGER|🌋'; then
      echo "$(date +%H:%M:%S) PRIORIDAD salta cap: ${line:0:50}" >> "$RLOG"
    else
      echo "$(date +%H:%M:%S) CAP 1/${CAP_S}s: ${line:0:50}" >> "$RLOG"; continue
    fi
  fi
  # TODO 32: dedup SOLO tras pasar el cap — un mensaje capado debe poder reenviarse (medido
  # 2026-08-04: el push 🇹🇼 capado quedaba 60s en dedup y moria en silencio).
  DEDUP_AT[$payload]=$now_s
  LASTSENT=$now_s
  msg="${line:0:180}"
  curl -s --max-time 5 -d "$msg" -H "Title: 🔔 flota" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null &
  if echo "$line" | grep -q '🚨'; then
    curl -s --max-time 8 -X POST https://api.resend.com/emails \
      -H "Authorization: Bearer $RESEND_KEY" -H "Content-Type: application/json" \
      -d "{\"from\":\"onboarding@resend.dev\",\"to\":[\"$RESEND_TO\"],\"subject\":\"🚨 flota: ${msg:0:60}\",\"text\":\"$msg\"}" >/dev/null &
  fi
  echo "$(date +%H:%M:%S) ENVIADA: ${msg:0:60}" >> "$RLOG"
done
