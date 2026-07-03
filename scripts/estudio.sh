#!/bin/zsh
# Plan de estudio quant: abre UN modulo por vez en Safari y cierra los demas del plan.
# uso: estudio.sh <0..9|libros|canales>     abre ese modulo (cierra el anterior)
#      estudio.sh <mod> --keep              abre sin cerrar nada
#      estudio.sh <mod> --dry               solo lista
#      estudio.sh all [--dry]               abre los 82 de golpe
#      estudio.sh close                     cierra todas las pestanas del plan
#      estudio.sh list                      indice de modulos
DOC="$(cd "$(dirname "$0")/.." && pwd)/docs/ESTUDIO-QUANT.md"
[[ -f "$DOC" ]] || { echo "falta $DOC"; exit 1; }
if [[ -z "$1" || "$1" == "list" ]]; then
  grep -E '^## ' "$DOC" | sed 's/^## //' | nl -ba -w2 -s'  '
  echo "\nuso: $0 <0..9|all|close> [--keep|--dry]"
  exit 0
fi
python3 - "$DOC" "$1" "$2" <<'PY'
import sys, re, subprocess, time
doc, sel, flag = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv)>3 else "")
txt = open(doc).read()
secs = re.split(r'^## ', txt, flags=re.M)[1:]

def links(sec):
    out, seen = [], set()
    for u in re.findall(r'https?://[^\s)>]+', sec):
        u = u.rstrip('.,;')
        if u not in seen: seen.add(u); out.append(u)
    return out

all_urls = []
for s in secs: all_urls += [u for u in links(s) if u not in all_urls]

def safari_close(urls):
    if not urls: return 0
    def count():
        r = subprocess.run(["osascript","-e",'tell application "Safari" to get (count of tabs of every window)'],
                           capture_output=True, text=True, timeout=30)
        return sum(int(x) for x in re.findall(r'\d+', r.stdout)) if r.stdout.strip() else 0
    before = count()
    lst = ",".join('"%s"' % u.replace('"','') for u in urls)
    scr = f'''set targets to {{{lst}}}
tell application "Safari"
  repeat with w in windows
    repeat with u in targets
      try
        close (every tab of w whose URL is (u as text))
      end try
      try
        close (every tab of w whose URL is ((u as text) & "/"))
      end try
    end repeat
  end repeat
end tell'''
    subprocess.run(["osascript","-e",scr], capture_output=True, text=True, timeout=120)
    return max(0, before - count())

def safari_open_urls():
    r = subprocess.run(["osascript","-e",'tell application "Safari" to get URL of every tab of every window'],
                       capture_output=True, text=True, timeout=30)
    return {x.strip().rstrip('/') for x in r.stdout.split(",")}

if sel == "close":
    print(f"cerradas {safari_close(all_urls)} pestanas del plan"); sys.exit(0)

if sel == "all":
    if flag == "--dry":
        print(f"{len(all_urls)} enlaces"); [print("  "+u) for u in all_urls]; sys.exit(0)
    already = safari_open_urls()
    todo = [u for u in all_urls if u.rstrip('/') not in already]
    print(f"abriendo {len(todo)} de {len(all_urls)}")
    for u in todo: subprocess.run(["open", u]); time.sleep(0.9)
    sys.exit(0)

key = sel.upper() if sel.upper() in ("LIBROS","CANALES") else "M"+sel.lstrip("mM")
hit = [s for s in secs if s.upper().startswith(key)]
if not hit:
    print(f"modulo '{sel}' no existe. usa: estudio.sh list"); sys.exit(1)
sec = hit[0]; urls = links(sec)
print("== " + sec.splitlines()[0])
print(f"{len(urls)} enlaces")
for u in urls: print("  " + u)
if flag == "--dry": sys.exit(0)
if flag != "--keep":
    others = [u for u in all_urls if u not in urls]
    c = safari_close(others)
    if c: print(f"-- cerradas {c} pestanas de otros modulos")
already = safari_open_urls()
for u in urls:
    if u.rstrip('/') in already: continue
    subprocess.run(["open", u]); time.sleep(1.0)
PY
