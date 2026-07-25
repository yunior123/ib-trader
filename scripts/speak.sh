#!/bin/bash
# speak.sh — PRODUCTOR de voz: encola un mensaje para voice_queue.sh (no bloquea).
# Uso:  speak.sh <PRIO> "<mensaje>"     PRIO ∈ {DANGER, SIGNAL, INFO}
#
# Reemplaza el viejo patrón `killall say; say -v X '...' &` (que se cortaba).
# Escribe un archivo a data/voice/ — instantáneo. El daemon lo reproduce entero.
#
# FALLBACK: si el daemon no está vivo (sin pidfile fresco / proceso muerto), habla
# directo con flock (serializado) para no quedarse mudo. Robusto ante daemon caído.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
Q="$ROOT/data/voice"; mkdir -p "$Q" "$ROOT/data/voice_spend"
PRIO="${1:-INFO}"; MSG="${2:-}"
[ -z "$MSG" ] && exit 0

# NOMBRES REALES (Yunior 2026-07-18: "usa los nombres reales, TSLA→Tesla").
# Traduce tickers→nombre hablado, centralizado aquí → sirve a TODOS los productores
# (bots + price_alarm) sin tocar cada uno. Word boundaries BSD [[:<:]] para no
# reemplazar dentro de otras palabras. ETFs de materia prima → subyacente real.
MSG="$(printf '%s' "$MSG" | sed -E \
  -e 's/[[:<:]]NVDA[[:>:]]/Nvidia/g'  -e 's/[[:<:]]TSLA[[:>:]]/Tesla/g' \
  -e 's/[[:<:]]AAPL[[:>:]]/Apple/g'   -e 's/[[:<:]]MU[[:>:]]/Micron/g' \
  -e 's/[[:<:]]INTC[[:>:]]/Intel/g'   -e 's/[[:<:]]GOOGL[[:>:]]/Google/g' \
  -e 's/[[:<:]]MSFT[[:>:]]/Microsoft/g' -e 's/[[:<:]]META[[:>:]]/Meta/g' \
  -e 's/[[:<:]]AMZN[[:>:]]/Amazon/g'  -e 's/[[:<:]]AVGO[[:>:]]/Broadcom/g' \
  -e 's/[[:<:]]TSM[[:>:]]/Taiwán Semi/g' -e 's/[[:<:]]QCOM[[:>:]]/Qualcomm/g' \
  -e 's/[[:<:]]TXN[[:>:]]/Texas Instruments/g' -e 's/[[:<:]]SPCX[[:>:]]/Space X/g' \
  -e 's/[[:<:]]SKHY[[:>:]]/S K Hynix/g'  -e 's/[[:<:]]NOK[[:>:]]/Nokia/g' \
  -e 's/[[:<:]]ASML[[:>:]]/A S M L/g'  -e 's/[[:<:]]SMH[[:>:]]/semis/g' -e 's/[[:<:]]EWY[[:>:]]/Korea E T F/g' \
  -e 's/[[:<:]]QQQ[[:>:]]/Nasdaq/g'    -e 's/[[:<:]]XLK[[:>:]]/tecnología/g' \
  -e 's/[[:<:]]AMD[[:>:]]/A M D/g'     -e 's/[[:<:]]DRAM[[:>:]]/D RAM/g' \
  -e 's/[[:<:]]GLD[[:>:]]/oro/g'       -e 's/[[:<:]]SLV[[:>:]]/plata/g' \
  -e 's/[[:<:]]CPER[[:>:]]/cobre/g'    -e 's/[[:<:]]USO[[:>:]]/petróleo/g' \
  -e 's/[[:<:]][Ss][Kk][Hh][Yy][Nn][Ii][Xx][[:>:]]/S K Hynix/g' \
  -e 's/[[:<:]][Kk][Oo][Ss][Pp][Ii][[:>:]]/Kospi/g')"
# ^ Corea (2026-07-19, flota nocturna KRX): price-alerts.txt trae `skhynix`/`kospi`
#   en minúscula → clases por letra = case-insensitive (sed BSD no tiene flag I).
#   samsung ya se lee bien tal cual; los bots KRX ya hablan nombres humanos.

# --- PRESUPUESTO DE VOZ (feature #12, ADITIVO Y REVERSIBLE) -------------------
# DANGER NO pasa por aqui NUNCA (se comprueba antes de todo): es la unica voz que preempta
# y es lo que Yunior oye para operar sin pantalla. INFO tampoco (voice_queue ya no lo
# vocaliza). Solo SIGNAL se raciona, y solo si existe el interruptor:
#     touch data/voice_budget_enable      (borrarlo lo desactiva: inerte en un gesto)
# FAIL-OPEN: solo el codigo 42 silencia. Python roto, json corrupto, disco lleno o
# cualquier otro final -> se habla igual. Un bug del presupuesto no puede volver muda la flota.
if [ "$PRIO" != "DANGER" ] && [ -f "$ROOT/data/voice_budget_enable" ]; then
  PY="$ROOT/venv/bin/python"
  if [ -x "$PY" ]; then
    "$PY" "$ROOT/scripts/voice_budget.py" --gate "$PRIO" --msg "$MSG" >/dev/null 2>&1
    if [ "$?" = "42" ]; then
      osascript -e "display notification \"$(printf '%s' "$MSG" | tr -d '"')\" with title \"🔇 presupuesto de voz\"" >/dev/null 2>&1 &
      exit 0
    fi
  fi
fi

# ¿daemon vivo?
PIDFILE="$ROOT/data/voice_queue.pid"
alive=0
if [ -f "$PIDFILE" ]; then
  pid=$(cat "$PIDFILE" 2>/dev/null)
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && alive=1
fi

if [ "$alive" = "1" ]; then
  # encolar: <epoch><nanos aprox>_<PRIO>.msg
  f="$Q/$(date +%s)$RANDOM""_$PRIO.msg"
  printf '%s' "$MSG" > "$f"
else
  # fallback serializado sin flock (macOS no lo trae): mkdir es un mutex atómico.
  # Espera su turno hasta 4s y habla; nunca mudo aunque el daemon esté caído.
  # SIN -v = voz Siri del sistema (la hermosa que eligió Yunior).
  LOCK="$ROOT/data/voice_fallback.lockd"
  (
    for _ in $(seq 1 40); do
      if mkdir "$LOCK" 2>/dev/null; then
        trap 'rmdir "$LOCK" 2>/dev/null' EXIT
        say "$MSG" >/dev/null 2>&1
        exit 0
      fi
      sleep 0.1
    done
    say "$MSG" >/dev/null 2>&1   # candado atascado >4s: hablar igual
  ) &
fi

# Contabilidad del presupuesto: UNA linea por locucion encolada, SIEMPRE despues de encolar
# (asi no puede retrasar ni bloquear una voz) y sin poder fallar el script. DANGER tambien
# cuenta para el total — cuenta, pero jamas se recorta.
{ printf '%s %s -\n' "$(date +%s)" "$PRIO" >> "$ROOT/data/voice_spend/$(date +%Y-%m-%d).txt"; } 2>/dev/null || true

exit 0
