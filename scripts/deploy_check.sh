#!/usr/bin/env bash
# deploy_check.sh — estado del despliegue de ib-trader en UNA pantalla. Solo lee, no toca nada.
# exit 0 = todo bien | exit 1 = hay CRITICOS (enganchable a cron/launchd).
#   bash scripts/deploy_check.sh          informe completo
#   bash scripts/deploy_check.sh --quiet  solo CRIT y AVISO
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
UID_N="$(id -u)"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1
CRIT=0; WARN=0

if [[ -t 1 ]]; then R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; Z=$'\033[0m'
else R=; G=; Y=; C=; B=; Z=; fi
crit() { printf '  %sCRIT%s  %s\n' "$R" "$Z" "$1"; CRIT=$((CRIT+1)); }
warn() { printf '  %sAVISO%s %s\n' "$Y" "$Z" "$1"; WARN=$((WARN+1)); }
ok()   { (( QUIET )) || printf '  %sok%s    %s\n' "$G" "$Z" "$1"; }
head_() { (( QUIET )) || printf '\n%s%s== %s ==%s\n' "$B" "$C" "$1" "$Z"; }

printf '%s%sDESPLIEGUE ib-trader%s  %s  repo=%s\n' "$B" "$C" "$Z" "$(date '+%F %H:%M:%S %Z')" "$ROOT"

# ---------------------------------------------------------------- 1) ventana horaria
head_ "ventana horaria de la flota"
FLEET_LIVE=0
if [[ -x bin/fleet_hours ]]; then
  WHY="$(./bin/fleet_hours --why 2>&1 | head -1)"
  if ./bin/fleet_hours >/dev/null 2>&1; then FLEET_LIVE=1; ok "DENTRO de ventana — $WHY"
  else ok "FUERA de ventana (que la flota este parada es CORRECTO) — $WHY"; fi
else
  crit "bin/fleet_hours no existe o no es ejecutable — sin portero la flota no arranca (scripts/build_fleet_hours.sh)"
fi

# ---------------------------------------------------------------- 2) centinela de sueno
head_ "centinela de sueno manual"
if [[ -f data/fleet_sleep ]]; then
  SL="$(head -1 data/fleet_sleep 2>/dev/null)"
  WK="$(grep -o 'wake: [0-9]*' data/fleet_sleep 2>/dev/null | awk '{print $2}')"
  if [[ -n "$WK" ]]; then
    warn "data/fleet_sleep ACTIVO hasta $(date -r "$WK" '+%F %H:%M' 2>/dev/null || echo "epoch $WK") — \"$SL\""
  else
    warn "data/fleet_sleep ACTIVO SIN 'wake:' (sueno INDEFINIDO, no despierta sola) — \"$SL\""
  fi
  warn "  mientras exista, fleet_keepalive_start.sh para todo y sale. Despertar: rm data/fleet_sleep"
  SLEEPING=1
else
  ok "sin centinela: la flota puede arrancar sola"
  SLEEPING=0
fi

# ---------------------------------------------------------------- 3) launchd
head_ "jobs launchd com.ibtrader.*"
LA="$HOME/Library/LaunchAgents"
DISABLED="$(launchctl print-disabled "gui/$UID_N" 2>/dev/null | awk -F'"' '/=> disabled/ {print $2}')"
N_PLIST=0; N_DIS=0; N_BADPATH=0; N_BADEXIT=0
while IFS= read -r plist; do
  [[ -z "$plist" ]] && continue
  N_PLIST=$((N_PLIST+1))
  label="$(basename "$plist" .plist)"
  # ruta del programa/script que lanza (primer path absoluto o relativo al repo que aparezca)
  target="$(python3 - "$plist" "$ROOT" <<'PY'
import plistlib,sys,os
p,root=sys.argv[1],sys.argv[2]
home=os.path.expanduser('~')
QUOTES=''.join(chr(c) for c in (34,39))
try: d=plistlib.load(open(p,'rb'))
except Exception as e: print("ERR:%s"%e); raise SystemExit
args=[str(a) for a in (d.get('ProgramArguments') or ([d['Program']] if 'Program' in d else []))]
def norm(t):
    t=t.strip().strip(QUOTES).replace('$HOME',home).replace('${HOME}',home)
    if t.startswith('~'): t=os.path.expanduser(t)
    if t.startswith('./'): t=os.path.join(root,t[2:])
    elif not t.startswith('/'): t=os.path.join(root,t)
    return os.path.normpath(t)
out=[]
# args[0] es el programa: solo se comprueba si es una ruta absoluta
if args and args[0].startswith('/'): out.append(args[0])
# comillas, punto y coma, & | y parentesis por chr: literales cortarian el $ - del shell
BAD=''.join(chr(c) for c in (34,39,59,38,124,40,41))
for a in args[1:]:
    for t in a.split():
        t=t.strip(BAD)
        if not t or t.startswith('-'): continue
        if t.endswith(('.sh','.py')) or '/bin/python' in t or t.startswith('./bin/'):
            q=norm(t)
            if q not in out: out.append(q)
print('\n'.join(out))
PY
)"
  missing=""
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    [[ "$t" == ERR:* ]] && { missing="plist ilegible ($t)"; break; }
    [[ -e "$t" ]] || missing="${missing} ${t}"
  done <<< "$target"
  if [[ -n "$missing" ]]; then crit "$label: ruta inexistente ->$missing"; N_BADPATH=$((N_BADPATH+1)); fi

  if grep -qx "$label" <<< "$DISABLED"; then
    N_DIS=$((N_DIS+1)); continue
  fi
  info="$(launchctl list "$label" 2>/dev/null)"
  if [[ -z "$info" ]]; then
    warn "$label: habilitado pero NO cargado (launchctl bootstrap gui/$UID_N $plist)"
  else
    ex="$(awk -F'= ' '/LastExitStatus/{gsub(/;/,"",$2);print $2}' <<< "$info")"
    if [[ -n "$ex" && "$ex" != "0" ]]; then
      N_BADEXIT=$((N_BADEXIT+1))
      case "$ex" in
        78|19968) crit "$label: exit 78 (EX_CONFIG) — plist/rutas mal, revisa StandardErrorPath" ;;
        *)        crit "$label: LastExitStatus=$ex" ;;
      esac
    else ok "$label: exit 0"; fi
  fi
done < <(ls "$LA"/com.ibtrader.*.plist 2>/dev/null)

if (( N_DIS > 0 )); then
  if (( N_DIS >= N_PLIST - 1 )); then
    warn "$N_DIS/$N_PLIST jobs DESHABILITADOS en el override de launchd (persiste al reiniciar)."
    warn "  Casi todo el despliegue esta apagado. Si NO es intencionado, reactivar con:"
    warn "  for f in ~/Library/LaunchAgents/com.ibtrader.*.plist; do l=\$(basename \$f .plist); launchctl enable gui/$UID_N/\$l; launchctl bootstrap gui/$UID_N \$f; done"
  else
    warn "$N_DIS/$N_PLIST jobs deshabilitados: $(tr '\n' ' ' <<< "$DISABLED")"
  fi
fi
(( QUIET )) || printf '  %s%d plists · %d deshabilitados · %d con ruta rota · %d con exit != 0%s\n' "$C" "$N_PLIST" "$N_DIS" "$N_BADPATH" "$N_BADEXIT" "$Z"

# ---------------------------------------------------------------- 4) binarios vs fuente
head_ "binarios C++ vs su fuente"
STALE="$(python3 - "$ROOT" <<'PY'
import os,sys,time
root=sys.argv[1]
srcdirs=['scripts','bots','engines','screener']
# binarios que son otro nombre/variante del mismo .cpp (verificado por tamano+strings 2026-08-22)
ALIAS={'lse_price_alarm':'scripts/price_alarm.cpp','replay_asan':'scripts/replay.cpp'}
hdrs=[os.path.join(root,h) for h in ('scripts/gate_core.hpp','scripts/options_alert_engine_core.h',
      'scripts/level_react.h','bots/fleet_notify.h','engines/bb_core.h','engines/combo_core.h')]
hmax=max([os.path.getmtime(h) for h in hdrs if os.path.exists(h)] or [0])
bind=os.path.join(root,'bin')
for b in sorted(os.listdir(bind)):
    bp=os.path.join(bind,b)
    if not os.path.isfile(bp) or not os.access(bp,os.X_OK) or b.endswith('.dSYM'): continue
    src=next((os.path.join(root,d,b+'.cpp') for d in srcdirs
              if os.path.exists(os.path.join(root,d,b+'.cpp'))),None)
    if src is None and b in ALIAS and os.path.exists(os.path.join(root,ALIAS[b])):
        src=os.path.join(root,ALIAS[b])
    if src is None:
        print("HUERFANO\t%s\t-"%b); continue
    sm=os.path.getmtime(src)
    if sm>os.path.getmtime(bp):
        print("STALE\t%s\t%s (fuente %s > binario %s)"%(b,os.path.relpath(src,root),
              time.strftime('%m-%d %H:%M',time.localtime(sm)),
              time.strftime('%m-%d %H:%M',time.localtime(os.path.getmtime(bp)))))
PY
)"
if [[ -z "$STALE" ]]; then ok "todos los binarios de bin/ son mas nuevos que su .cpp"
else
  while IFS=$'\t' read -r kind name det; do
    [[ -z "$kind" ]] && continue
    if [[ "$kind" == STALE ]]; then crit "bin/$name DESACTUALIZADO: $det"
    else warn "bin/$name sin .cpp en el repo (no se puede recompilar) — $det"; fi
  done <<< "$STALE"
fi

# ---------------------------------------------------------------- 5) procesos esperados vs vivos
head_ "procesos: esperados vs vivos"
alive() { pgrep -f "$1" >/dev/null 2>&1; }
esperado() { # patron  etiqueta  requiere_ventana(1/0)
  local pat="$1" lab="$2" gate="$3"
  if alive "$pat"; then ok "$lab: vivo"
  elif (( SLEEPING )); then ok "$lab: parado (centinela de sueno, correcto)"
  elif (( gate == 1 && FLEET_LIVE == 0 )); then ok "$lab: parado (fuera de ventana, correcto)"
  else crit "$lab: CAIDO y deberia estar vivo"; fi
}
NB="$(pgrep -f '_signal_bot$' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$NB" -gt 0 ]]; then ok "bots de senal: $NB vivos"
elif (( SLEEPING )); then ok "bots de senal: 0 (centinela de sueno, correcto)"
elif (( FLEET_LIVE == 0 )); then ok "bots de senal: 0 (fuera de ventana, correcto)"
else crit "bots de senal: NINGUNO y estamos en ventana"; fi
MS="$(cat data/market_source.txt 2>/dev/null || echo ibkr)"
if [[ "$MS" == "ibkr" ]]; then esperado "ibkr_bar_bridge.py" "puente de barras IBKR" 1
else esperado "provider_bridge.py" "provider_bridge ($MS)" 1; fi
esperado "voice_queue.sh"  "cola de voz"       1
esperado "bin/price_alarm" "alarma de precio"  1
# el cockpit es 24/7: lo mantiene com.ibtrader.chartqa, no depende de la ventana ni del sueno
if alive "chart_bridge.py"; then
  NW="$(pgrep -f 'chart_bridge.py' | wc -l | tr -d ' ')"; ok "cockpit: $NW ventanas vivas"
else crit "cockpit CAIDO (com.ibtrader.chartqa deberia mantenerlo 24/7)"; fi

# ---------------------------------------------------------------- 6) logs con errores recientes
head_ "logs con errores en la ultima hora"
HITS="$(IBT_LOG_WINDOW_S="${IBT_LOG_WINDOW_S:-3600}" python3 - "$ROOT" <<'PY'
import os,re,sys,time
root=sys.argv[1]; cut=time.time()-float(os.environ.get('IBT_LOG_WINDOW_S','3600'))
# '401' a secas cazaba precios (AVGO flip 401.78): exigir contexto de error o de token
pat=re.compile(r"Traceback|can.t open input file|EX_CONFIG|exit 78|Unauthorized|NOT_AUTHORIZED"
               r"|token caducado|error 401|HTTP ?401|rest=401|: ?401:|CRITICO:|FATAL"
               r"|No such file or directory|ModuleNotFoundError|Permission denied",re.I)
found=False
for d in (os.path.join(root,'logs'),root):
    if not os.path.isdir(d): continue
    for f in sorted(os.listdir(d)):
        if not f.endswith('.log'): continue
        p=os.path.join(d,f)
        try:
            if not os.path.isfile(p) or os.path.getmtime(p)<cut: continue
            with open(p,'rb') as fh:
                sz=fh.seek(0,2); fh.seek(max(0,sz-20000))
                tail=fh.read().decode('utf-8','replace').splitlines()
        except OSError: continue
        bad=[l for l in tail[-200:] if pat.search(l)]
        if bad:
            found=True
            print("%s\t%s"%(os.path.relpath(p,root),bad[-1][:140]))
if not found: print("")
PY
)"
if [[ -z "${HITS//[$'\n\t ']/}" ]]; then ok "ningun .log tocado en la ultima hora trae error"
else
  while IFS=$'\t' read -r f line; do
    [[ -z "$f" ]] && continue
    warn "$f: $line"
  done <<< "$HITS"
fi

# ---------------------------------------------------------------- resumen
printf '\n%s%sRESUMEN%s  %s%d CRITICOS%s · %s%d avisos%s\n' "$B" "$C" "$Z" "$R" "$CRIT" "$Z" "$Y" "$WARN" "$Z"
(( CRIT > 0 )) && exit 1
exit 0
