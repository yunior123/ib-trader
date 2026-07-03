#!/bin/zsh
# e2e_smoke.sh — arnes E2E con el MERCADO CERRADO: puntua la cadena viva (portero, contrato de
# ficheros del provider_bridge, opt_quick, reversal_router, shock_calibrator, terminal mit,
# guarda anti-mock, suites). Informe atomico en data/e2e_report.json. Salida != 0 si hay FAIL.
# Uso: zsh scripts/e2e_smoke.sh [--force] [--fast] [--summary FICHERO]
emulate -L zsh
setopt pipefail
ROOT="${0:A:h}/.."
cd "$ROOT" || exit 1

PY="./venv/bin/python"
PY_MIT="./venv-mit/bin/python"
UVICORN="./venv-mit/bin/uvicorn"
REPORT="data/e2e_report.json"
SHOT_DIR="data/e2e_shots"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_MAX_S=90

FORCE=0
FAST=0
SUMMARY_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --fast) FAST=1 ;;
    --summary) shift; SUMMARY_FILE="${1:-}" ;;
    --help|-h) print -r -- "uso: zsh scripts/e2e_smoke.sh [--force] [--fast] [--summary FICHERO]"; exit 0 ;;
    *) print -r -- "argumento desconocido: $1"; exit 64 ;;
  esac
  shift
done

# ---------- modo parser: resume un informe ya escrito (no ejecuta nada) ----------
if [ -n "$SUMMARY_FILE" ]; then
  [ -x "$PY" ] || { print -r -- "no existe $PY"; exit 70; }
  "$PY" - "$SUMMARY_FILE" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        rep = json.load(fh)
except Exception as exc:
    print("informe ilegible: %s" % type(exc).__name__)
    raise SystemExit(70)
steps = rep.get("steps")
if not isinstance(steps, list):
    print("informe sin lista 'steps'")
    raise SystemExit(70)
n = {"PASS": 0, "FAIL": 0, "SKIPPED": 0}
unknown = 0
for s in steps:
    st = s.get("status")
    if st in n:
        n[st] += 1
    else:
        unknown += 1
icon = {"PASS": "OK  ", "FAIL": "FAIL", "SKIPPED": "SKIP"}
for s in steps:
    print("  [%s] %s — %s" % (icon.get(s.get("status"), "????"), s.get("name", "?"), s.get("evidence", "")))
print("RESUMEN e2e: PASS=%d FAIL=%d SKIPPED=%d TOTAL=%d" % (n["PASS"], n["FAIL"], n["SKIPPED"], len(steps)))
if unknown:
    print("estados desconocidos: %d" % unknown)
raise SystemExit(1 if (n["FAIL"] or unknown) else 0)
PYEOF
  exit $?
fi

[ -x "$PY" ] || { print -r -- "no existe $PY — la suite base necesita ./venv"; exit 70; }

# ---------- guarda de ventana: en LIVE no se corre (patron deploy_signals_to_data.sh) ----------
if [ -x bin/fleet_hours ]; then
  if bin/fleet_hours >/dev/null 2>&1 && [ "$FORCE" -ne 1 ]; then
    print -r -- "ventana LIVE ($(bin/fleet_hours --why 2>/dev/null)) — e2e ABORTADO (usa --force bajo tu responsabilidad)."
    exit 3
  fi
fi

TMPD=$(mktemp -d) || exit 70
RECFILE="$TMPD/records.tsv"
: > "$RECFILE"
UV_PID=""
CH_PID=""
cleanup() {  # jamas dejar uvicorn/Chrome colgados, ni siquiera si nos matan a media corrida
  for p in "$UV_PID" "$CH_PID"; do
    [ -n "$p" ] || continue
    kill "$p" 2>/dev/null
    sleep 1
    kill -9 "$p" 2>/dev/null
    wait "$p" 2>/dev/null
  done
  rm -rf "$TMPD"
}
trap cleanup EXIT INT TERM

N_PASS=0; N_FAIL=0; N_SKIP=0

redact() {  # nunca dejar salir el valor de una key por consola ni al informe
  sed -E \
    -e 's/([Aa][Pp][Ii]_?[Kk][Ee][Yy]"?[[:space:]]*[:=][[:space:]]*"?)[^"[:space:],}&]+/\1<REDACTED>/g' \
    -e 's/([Aa][Pp][Ii][Kk][Ee][Yy]"?[[:space:]]*[:=][[:space:]]*"?)[^"[:space:],}&]+/\1<REDACTED>/g' \
    -e 's/([Tt][Oo][Kk][Ee][Nn]"?[[:space:]]*[:=][[:space:]]*"?)[^"[:space:],}&]+/\1<REDACTED>/g'
}

step() {  # id nombre estado evidencia
  local id="$1" name="$2" st="$3" ev="$4"
  ev=$(print -r -- "$ev" | redact | tr '\n\t' '  ' | cut -c1-700)
  case "$st" in
    PASS) N_PASS=$((N_PASS+1)); print -r -- "  [OK  ] $name — $ev" ;;
    FAIL) N_FAIL=$((N_FAIL+1)); print -r -- "  [FAIL] $name — $ev" ;;
    SKIPPED) N_SKIP=$((N_SKIP+1)); print -r -- "  [SKIP] $name — $ev" ;;
  esac
  printf '%s\t%s\t%s\t%s\n' "$id" "$name" "$st" "$ev" >> "$RECFILE"
}

print -r -- "e2e_smoke — $(date '+%Y-%m-%d %H:%M:%S %Z') — raiz ${ROOT:A}"

# ---------- 1) portero horario ----------
if [ ! -x bin/fleet_hours ]; then
  step 1 "portero fleet_hours" SKIPPED "bin/fleet_hours no existe o no es ejecutable"
  MARKET_STATE="UNKNOWN"
else
  bin/fleet_hours --json 2>&1 | redact > "$TMPD/fh.json"
  bin/fleet_hours >/dev/null 2>&1; FH_EXIT=$?
  FH_OUT=$("$PY" - "$TMPD/fh.json" "$FH_EXIT" <<'PYEOF' 2>&1
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print("json ilegible: %s" % type(exc).__name__); raise SystemExit(1)
exit_live = sys.argv[2] == "0"
st = d.get("state"); live = d.get("live")
if st not in {"LIVE", "DEAD", "FORCED"}:
    print("estado desconocido %r" % st); raise SystemExit(1)
if not isinstance(live, bool) or live != exit_live:
    print("json.live=%r no coincide con el exit code (%s)" % (live, sys.argv[2])); raise SystemExit(1)
print("state=%s live=%s now=%s window=%s detail=%s" % (st, live, d.get("now"), d.get("window"), d.get("detail")))
raise SystemExit(0)
PYEOF
)
  FH_RC=$?
  MARKET_STATE=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1])).get("state","UNKNOWN"))' "$TMPD/fh.json" 2>/dev/null) || MARKET_STATE="UNKNOWN"
  if [ $FH_RC -eq 0 ]; then
    step 1 "portero fleet_hours" PASS "$FH_OUT"
  else
    step 1 "portero fleet_hours" FAIL "$FH_OUT"
  fi
fi

# ---------- 2) contrato de ficheros vivos del provider_bridge ----------
CONTRACT_OUT=$("$PY" - <<'PYEOF' 2>&1
import os, sys, time

DATA = "data"
syms_path = os.path.join(DATA, "provider_syms.txt")
if not os.path.exists(syms_path):
    print("data/provider_syms.txt no existe"); raise SystemExit(2)
with open(syms_path) as fh:
    syms = fh.read().split()
if not syms:
    print("provider_syms.txt vacio"); raise SystemExit(2)

now = time.time()
bad, ages, missing = [], [], []


def age_min(p):
    return (now - os.path.getmtime(p)) / 60.0


def check_bars(sym):
    p = os.path.join(DATA, "bars_%s_ibkr.txt" % sym.lower())
    if not os.path.exists(p):
        missing.append(os.path.basename(p)); return
    prev = None
    n = 0
    with open(p) as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            f = line.split()
            if len(f) != 6:
                bad.append("%s:%d campos=%d (esperado 6)" % (sym, i, len(f))); return
            try:
                ep = int(f[0]); [float(x) for x in f[1:]]
            except ValueError:
                bad.append("%s:%d numero ilegible" % (sym, i)); return
            if ep % 60 != 0:
                bad.append("%s:%d epoch %d no alineado al minuto" % (sym, i, ep)); return
            if prev is not None and ep <= prev:
                bad.append("%s:%d epoch %d no creciente (prev %d)" % (sym, i, ep, prev)); return
            prev = ep; n += 1
    if n == 0:
        bad.append("%s: bars sin filas" % sym); return
    ages.append(("bars_%s" % sym, age_min(p), n))


def check_nbbo(sym):
    p = os.path.join(DATA, "nbbo_%s.txt" % sym.lower())
    if not os.path.exists(p):
        missing.append(os.path.basename(p)); return
    txt = open(p).read().split()
    # DOS RELOJES (provider_bridge.write_nbbo, audit 2026-08-04): campo 1 = wall-clock de
    # escritura, campo 4 OPCIONAL = epoch de bolsa. Los bots leen los tres primeros y el
    # cuarto lo ignoran, asi que 3 y 4 campos son AMBOS contrato valido.
    if len(txt) not in (3, 4):
        bad.append("%s: nbbo campos=%d (esperado 3 o 4)" % (sym, len(txt))); return
    try:
        ep, bid, ask = int(float(txt[0])), float(txt[1]), float(txt[2])
        ep_bolsa = int(float(txt[3])) if len(txt) == 4 else None
    except ValueError:
        bad.append("%s: nbbo numero ilegible" % sym); return
    if ep_bolsa is not None and ep_bolsa <= 0:
        bad.append("%s: nbbo epoch de bolsa %d" % (sym, ep_bolsa)); return
    if not (ask > bid > 0):
        bad.append("%s: nbbo viola ask>bid>0 (bid=%s ask=%s)" % (sym, bid, ask)); return
    if ep <= 0:
        bad.append("%s: nbbo epoch %d" % (sym, ep)); return
    ages.append(("nbbo_%s" % sym, age_min(p), 1))


def check_chain(sym):
    p = os.path.join(DATA, "opt_chain_%s.txt" % sym.lower())
    if not os.path.exists(p):
        missing.append(os.path.basename(p)); return
    lines = [l for l in open(p).read().splitlines() if l.strip()]
    head = [l for l in lines[:3] if l.startswith("#")]
    if len(head) < 2:
        bad.append("%s: cadena con %d lineas de cabecera '#' (esperado 2 o mas)" % (sym, len(head))); return
    # La cabecera es APPEND-ONLY (docs/CHAIN-HEADER.md): se salta por el '#', como hace el lector
    # oficial chain_cube_archive.parse_ibkr_text, no por un numero fijo de lineas.
    rows = [x for x in lines if not x.lstrip().startswith("#")]
    if not rows:
        bad.append("%s: cadena sin filas" % sym); return
    for i, r in enumerate(rows, 4):
        f = r.split()
        if len(f) != 10:
            bad.append("%s:%d cadena campos=%d (esperado 10)" % (sym, i, len(f))); return
        if f[1] not in ("C", "P"):
            bad.append("%s:%d right=%r" % (sym, i, f[1])); return
    ages.append(("chain_%s" % sym, age_min(p), len(rows)))


for s in syms:
    check_bars(s); check_nbbo(s); check_chain(s)

if not ages:
    print("ningun fichero del contrato presente (bridge nunca corrio)"); raise SystemExit(2)

oldest = max(ages, key=lambda t: t[1])
newest = min(ages, key=lambda t: t[1])
summary = ("%d syms | %d ficheros validos | edad %.0f-%.0f min (viejo=%s) | faltan %d%s"
           % (len(syms), len(ages), newest[1], oldest[1], oldest[0], len(missing),
              (": " + ", ".join(missing[:6])) if missing else ""))
if bad:
    print("MALFORMADOS: " + " | ".join(bad[:6]) + " || " + summary); raise SystemExit(1)
print(summary + " (con mercado cerrado la edad alta es correcta; lo que no vale es malformado)")
raise SystemExit(0)
PYEOF
)
C_RC=$?
if [ $C_RC -eq 0 ]; then
  step 2 "contrato ficheros vivos (bars/nbbo/chain)" PASS "$CONTRACT_OUT"
elif [ $C_RC -eq 2 ]; then
  step 2 "contrato ficheros vivos (bars/nbbo/chain)" SKIPPED "$CONTRACT_OUT"
else
  step 2 "contrato ficheros vivos (bars/nbbo/chain)" FAIL "$CONTRACT_OUT"
fi

# ---------- 3) opt_quick lee una cadena real ----------
if [ ! -x bin/opt_quick ]; then
  step 3 "opt_quick sobre cadena real" SKIPPED "bin/opt_quick no existe"
else
  OQ_SYM=""
  for f in data/opt_chain_*.txt; do
    [ -f "$f" ] || continue
    OQ_SYM=${${f:t:r}#opt_chain_}
    OQ_SYM=${(U)OQ_SYM}
    break
  done
  if [ -z "$OQ_SYM" ]; then
    step 3 "opt_quick sobre cadena real" SKIPPED "no hay data/opt_chain_*.txt"
  else
    OQ_OUT=$(bin/opt_quick "$OQ_SYM" 2>&1 | redact)
    OQ_RC=$?
    OQ_MISS=""
    for pat in "spot" "P/C volumen" "MAX PAIN" "MUROS"; do
      print -r -- "$OQ_OUT" | grep -q -- "$pat" || OQ_MISS="$OQ_MISS '$pat'"
    done
    OQ_HEAD=$(print -r -- "$OQ_OUT" | head -1)
    if [ $OQ_RC -ne 0 ]; then
      step 3 "opt_quick sobre cadena real" FAIL "$OQ_SYM: exit $OQ_RC — $OQ_HEAD"
    elif [ -n "$OQ_MISS" ]; then
      step 3 "opt_quick sobre cadena real" FAIL "$OQ_SYM: faltan secciones$OQ_MISS"
    else
      step 3 "opt_quick sobre cadena real" PASS "$OQ_SYM: $OQ_HEAD"
    fi
  fi
fi

# ---------- 4) reversal_router (SHADOW) ----------
RR_SYMS=(QQQ SPY NVDA)
if [ ! -f scripts/reversal_router.py ]; then
  step 4 "reversal_router --once" SKIPPED "scripts/reversal_router.py no existe"
else
  RR_OUT=$("$PY" scripts/reversal_router.py --once ${RR_SYMS[@]} 2>&1 | redact)
  RR_RC=$?
  if [ $RR_RC -ne 0 ]; then
    step 4 "reversal_router --once" FAIL "exit $RR_RC — $(print -r -- "$RR_OUT" | tail -3)"
  else
    RR_CHECK=$("$PY" - ${RR_SYMS[@]} <<'PYEOF' 2>&1
import json, os, sys, time
OK = {"CONTINUATION_ACTIVE_DO_NOT_FADE", "REVERSAL_ARMED_WAIT", "REVERSAL_CONFIRMED",
      "NEUTRAL_CONFLICT", "INSUFFICIENT_DATA"}
now = time.time()
out, bad = [], []
for s in sys.argv[1:]:
    p = os.path.join("data", "reversal_%s.json" % s.upper())
    if not os.path.exists(p):
        bad.append("%s: no se escribio %s" % (s, p)); continue
    if now - os.path.getmtime(p) > 600:
        bad.append("%s: fichero rancio (%.0f min)" % (s, (now - os.path.getmtime(p)) / 60)); continue
    try:
        d = json.load(open(p))
    except Exception as exc:
        bad.append("%s: json ilegible %s" % (s, type(exc).__name__)); continue
    st = d.get("state")
    if st not in OK:
        bad.append("%s: estado INVENTADO %r" % (s, st)); continue
    out.append("%s=%s" % (s.upper(), st))
print(" ".join(out) + ((" || " + " | ".join(bad)) if bad else ""))
raise SystemExit(1 if bad else 0)
PYEOF
)
    if [ $? -eq 0 ]; then
      step 4 "reversal_router --once" PASS "$RR_CHECK (INSUFFICIENT_DATA es el estado legitimo con barras cortas)"
    else
      step 4 "reversal_router --once" FAIL "$RR_CHECK"
    fi
  fi
fi

# ---------- 5) shock_calibrator (venv-mit + PYTHONPATH=mit) ----------
SC_SYMS=(QQQ SPY)
if [ ! -f scripts/shock_calibrator.py ]; then
  step 5 "shock_calibrator --once" SKIPPED "scripts/shock_calibrator.py no existe"
elif [ ! -x "$PY_MIT" ]; then
  step 5 "shock_calibrator --once" SKIPPED "$PY_MIT no existe (venv-mit py3.12)"
else
  SC_OUT=$(PYTHONPATH=mit "$PY_MIT" scripts/shock_calibrator.py --once ${SC_SYMS[@]} 2>&1 | redact)
  SC_RC=$?
  if [ $SC_RC -ne 0 ]; then
    step 5 "shock_calibrator --once" FAIL "exit $SC_RC — $(print -r -- "$SC_OUT" | tail -3)"
  else
    SC_CHECK=$("$PY" - <<'PYEOF' 2>&1
import json, os, time
p = "data/shock_snapshot.json"
if not os.path.exists(p):
    print("no se escribio %s" % p); raise SystemExit(1)
if time.time() - os.path.getmtime(p) > 600:
    print("shock_snapshot.json rancio"); raise SystemExit(1)
try:
    d = json.load(open(p))
except Exception as exc:
    print("json ilegible: %s" % type(exc).__name__); raise SystemExit(1)
syms = d.get("symbols")
if syms is None:
    print("sin clave 'symbols'"); raise SystemExit(1)
if not syms:
    print("symbols VACIO y sin motivo explicito: %s" % d.get("reason", "<ninguno>"))
    raise SystemExit(0 if d.get("reason") else 1)
names = list(syms) if isinstance(syms, dict) else [x.get("symbol") for x in syms]
sev = [(n, (syms[n] if isinstance(syms, dict) else {}).get("severity")) for n in names] if isinstance(syms, dict) else []
print("%d simbolos: %s | metric=%s min_n=%s" % (len(names), ", ".join("%s(%s)" % t for t in sev) or ", ".join(map(str, names)), d.get("metric"), d.get("reversion_min_n")))
raise SystemExit(0)
PYEOF
)
    if [ $? -eq 0 ]; then
      step 5 "shock_calibrator --once" PASS "$SC_CHECK"
    else
      step 5 "shock_calibrator --once" FAIL "$SC_CHECK"
    fi
  fi
fi

# ---------- 6) terminal mit: endpoints + screenshot + cierre limpio ----------
if [ ! -x "$UVICORN" ]; then
  step 6 "terminal mit (gex_heatmap + trace)" SKIPPED "$UVICORN no existe"
else
  PORT="${MIT_PORT:-}"
  if [ -z "$PORT" ]; then
    PORT=$("$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();print(p)')
  fi
  UVLOG="$TMPD/uvicorn.log"
  ( cd mit && export PYTHONPATH=. && exec "../${UVICORN#./}" backend.app.main:app --host 127.0.0.1 --port "$PORT" ) >"$UVLOG" 2>&1 &
  UV_PID=$!
  READY=0
  for i in $(seq 1 60); do
    if curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/api/health"; then READY=1; break; fi
    kill -0 "$UV_PID" 2>/dev/null || break
    sleep 1
  done
  if [ $READY -ne 1 ]; then
    step 6 "terminal mit (gex_heatmap + trace)" FAIL "uvicorn no levanto en puerto $PORT — $(tail -3 "$UVLOG" | redact)"
  else
    HM_CODE=$(curl -s -m 60 -o "$TMPD/heatmap.json" -w '%{http_code}' "http://127.0.0.1:$PORT/api/gex_heatmap/SPY?metric=gex")
    TR_CODE=$(curl -s -m 60 -o "$TMPD/trace.json" -w '%{http_code}' "http://127.0.0.1:$PORT/api/trace/SPY?metric=netoi")
    MIT_CHECK=$("$PY" - "$TMPD/heatmap.json" "$TMPD/trace.json" "$HM_CODE" "$TR_CODE" <<'PYEOF' 2>&1
import json, sys
hm_p, tr_p, hm_c, tr_c = sys.argv[1:5]
if hm_c != "200" or tr_c != "200":
    print("http heatmap=%s trace=%s" % (hm_c, tr_c)); raise SystemExit(1)
try:
    hm = json.load(open(hm_p)); tr = json.load(open(tr_p))
except Exception as exc:
    print("json ilegible: %s" % type(exc).__name__); raise SystemExit(1)
bad = []
if not hm.get("strikes"): bad.append("heatmap sin strikes")
if not hm.get("cells"): bad.append("heatmap sin cells")
if not hm.get("expirations"): bad.append("heatmap sin expirations")
if not tr.get("strikes"): bad.append("trace sin strikes")
if not tr.get("by_strike"): bad.append("trace sin by_strike")
if not isinstance(tr.get("levels"), dict): bad.append("trace sin levels")
if bad:
    print(" | ".join(bad)); raise SystemExit(1)
lv = tr["levels"]
print("heatmap %d strikes x %d exps, %d celdas, spot %s | trace %d strikes, %d velas, call_wall=%s put_wall=%s flip=%s max_pain=%s"
      % (len(hm["strikes"]), len(hm["expirations"]), len(hm["cells"]), hm.get("spot"),
         len(tr["strikes"]), len(tr.get("candles") or []), lv.get("call_wall"), lv.get("put_wall"),
         lv.get("gamma_flip"), lv.get("max_pain")))
raise SystemExit(0)
PYEOF
)
    MIT_RC=$?
    SHOT_EV=""
    if [ -x "$CHROME" ]; then
      mkdir -p "$SHOT_DIR"
      rm -f "$SHOT_DIR/mit_terminal.png"
      # el WebSocket de la pagina impide que Chrome headless salga solo: PNG escrito y kill duro.
      "$CHROME" --headless=new --disable-gpu --no-first-run --no-default-browser-check \
        --disable-extensions --disable-background-networking \
        --user-data-dir="$TMPD/chrome" --hide-scrollbars --window-size=1600,1100 \
        --virtual-time-budget=12000 --screenshot="$SHOT_DIR/mit_terminal.png" \
        "http://127.0.0.1:$PORT/" >/dev/null 2>&1 &
      CH_PID=$!
      for i in $(seq 1 $CHROME_MAX_S); do
        kill -0 "$CH_PID" 2>/dev/null || break
        [ -s "$SHOT_DIR/mit_terminal.png" ] && [ "$i" -ge 3 ] && break
        sleep 1
      done
      kill -9 "$CH_PID" 2>/dev/null; wait "$CH_PID" 2>/dev/null
      SHOT_EV=" | $("$PY" -c '
import sys
p = sys.argv[1]
try:
    b = open(p, "rb").read()
except OSError:
    print("screenshot NO capturada"); raise SystemExit(0)
if b[:8] != b"\x89PNG\r\n\x1a\n" or b[-8:-4] != b"IEND":
    print("screenshot PNG corrupto (%d bytes)" % len(b)); raise SystemExit(0)
print("screenshot %s (%d bytes, PNG completo)" % (p, len(b)))
' "$SHOT_DIR/mit_terminal.png")"
    else
      SHOT_EV=" | Chrome headless no disponible: sin evidencia visual"
    fi
    if [ $MIT_RC -eq 0 ]; then
      step 6 "terminal mit (gex_heatmap + trace)" PASS "puerto $PORT: $MIT_CHECK$SHOT_EV"
    else
      step 6 "terminal mit (gex_heatmap + trace)" FAIL "puerto $PORT: $MIT_CHECK$SHOT_EV"
    fi
  fi
  kill "$UV_PID" 2>/dev/null
  wait "$UV_PID" 2>/dev/null
  UV_PID=""
fi

# ---------- 7) guarda anti-mock + cero fugas de API key ----------
AM_MARKET=""
if [ -x "$PY_MIT" ]; then
  AM_MARKET=$(PYTHONPATH=mit "$PY_MIT" -c '
from backend.app.config import get_settings
from backend.app.providers.registry import build_providers
s = get_settings(); p = build_providers(s)
print("%s %s" % (type(p.market).__name__, type(p.options).__name__))
' 2>&1 | tail -1 | redact)
fi
AM_OUT=$("$PY" - "$AM_MARKET" "${IBT_ALLOW_MOCK:-}" "$RECFILE" <<'PYEOF' 2>&1
import json, os, re, sys
resolved, allow_mock, recfile = sys.argv[1], sys.argv[2], sys.argv[3]
bad, notes = [], []
if allow_mock == "1":
    bad.append("IBT_ALLOW_MOCK=1 en el entorno (escotilla SOLO de tests)")
if resolved:
    parts = resolved.split()
    if len(parts) == 2 and all(re.match(r"^[A-Za-z]+$", x) for x in parts):
        for cap, name in zip(("market", "options"), parts):
            if name in ("MockProvider", "UnavailableProvider"):
                bad.append("%s resolvio a %s" % (cap, name))
        notes.append("resuelto market=%s options=%s" % (parts[0], parts[1]))
    else:
        notes.append("resolucion de providers no legible")
else:
    notes.append("venv-mit ausente: no se pudo resolver providers")
ps = "data/provider_status.json"
if os.path.exists(ps):
    try:
        d = json.load(open(ps))
        for k in ("market_provider", "options_provider"):
            if str(d.get(k, "")).lower() == "mock":
                bad.append("provider_status.%s=mock" % k)
        notes.append("provider_status market=%s options=%s" % (d.get("market_provider"), d.get("options_provider")))
    except Exception as exc:
        bad.append("provider_status.json ilegible: %s" % type(exc).__name__)
else:
    notes.append("data/provider_status.json ausente")
ms = "data/market_source.txt"
if os.path.exists(ms):
    notes.append("market_source=%s" % open(ms).read().strip())
# fuga de secretos: se comparan valores SIN imprimirlos jamas
secrets = []
for env in ("config/feeds.env", "feeds.env"):
    if not os.path.exists(env):
        continue
    for line in open(env):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        v = line.split("=", 1)[1].strip().strip('"').strip("'")
        if len(v) >= 16:
            secrets.append(v)
leaked = 0
for p in (recfile, "data/e2e_report.json"):
    if os.path.exists(p):
        blob = open(p, errors="ignore").read()
        leaked += sum(1 for s in secrets if s in blob)
if leaked:
    bad.append("%d secreto(s) presentes en el informe" % leaked)
notes.append("%d secretos vigilados, %d fugas" % (len(secrets), leaked))
print(" | ".join(notes) + ((" || FALLOS: " + " | ".join(bad)) if bad else ""))
raise SystemExit(1 if bad else 0)
PYEOF
)
if [ $? -eq 0 ]; then
  step 7 "guarda anti-mock + cero fugas de key" PASS "$AM_OUT"
else
  step 7 "guarda anti-mock + cero fugas de key" FAIL "$AM_OUT"
fi

# ---------- 8) suites ----------
if [ "$FAST" -eq 1 ]; then
  step 8 "suite base pytest tests/" SKIPPED "--fast: suites omitidas a peticion"
  step 9 "suite mit backend/tests" SKIPPED "--fast: suites omitidas a peticion"
else
  PT_OUT=$("$PY" -m pytest tests/ -q 2>&1 | tail -25 | redact)
  PT_LINE=$(print -r -- "$PT_OUT" | grep -E '[0-9]+ (passed|failed)' | tail -1)
  if print -r -- "$PT_LINE" | grep -q "failed"; then
    step 8 "suite base pytest tests/" FAIL "$PT_LINE || $(print -r -- "$PT_OUT" | grep -E '^FAILED' | head -3)"
  elif [ -z "$PT_LINE" ]; then
    step 8 "suite base pytest tests/" FAIL "sin linea de resumen: $(print -r -- "$PT_OUT" | tail -2)"
  else
    step 8 "suite base pytest tests/" PASS "$PT_LINE"
  fi
  if [ ! -x "$PY_MIT" ]; then
    step 9 "suite mit backend/tests" SKIPPED "$PY_MIT no existe"
  else
    MT_OUT=$(PYTHONPATH=mit "$PY_MIT" -m pytest mit/backend/tests -q 2>&1 | tail -25 | redact)
    MT_LINE=$(print -r -- "$MT_OUT" | grep -E '[0-9]+ (passed|failed)' | tail -1)
    if print -r -- "$MT_LINE" | grep -q "failed"; then
      step 9 "suite mit backend/tests" FAIL "$MT_LINE || $(print -r -- "$MT_OUT" | grep -E '^FAILED' | head -3)"
    elif [ -z "$MT_LINE" ]; then
      step 9 "suite mit backend/tests" FAIL "sin linea de resumen: $(print -r -- "$MT_OUT" | tail -2)"
    else
      step 9 "suite mit backend/tests" PASS "$MT_LINE"
    fi
  fi
fi

# ---------- informe atomico ----------
"$PY" - "$RECFILE" "$REPORT" "${MARKET_STATE:-UNKNOWN}" <<'PYEOF'
import json, os, sys, time
rec_path, out_path, market_state = sys.argv[1], sys.argv[2], sys.argv[3]
steps = []
with open(rec_path) as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        p = line.split("\t")
        while len(p) < 4:
            p.append("")
        steps.append({"id": p[0], "name": p[1], "status": p[2], "evidence": p[3]})
n = {"PASS": 0, "FAIL": 0, "SKIPPED": 0}
for s in steps:
    if s["status"] in n:
        n[s["status"]] += 1
rep = {
    "generated_epoch": int(time.time()),
    "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "market_state": market_state,
    "steps": steps,
    "summary": {"pass": n["PASS"], "fail": n["FAIL"], "skipped": n["SKIPPED"], "total": len(steps)},
}
tmp = out_path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(rep, fh, indent=2)
os.replace(tmp, out_path)
PYEOF

print -r -- ""
print -r -- "RESUMEN e2e: PASS=$N_PASS FAIL=$N_FAIL SKIPPED=$N_SKIP — informe $REPORT (mercado ${MARKET_STATE:-UNKNOWN})"
[ "$N_FAIL" -gt 0 ] && exit 1
exit 0
