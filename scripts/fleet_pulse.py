#!/usr/bin/env python
"""fleet_pulse.py — pulso de la FLOTA COMPLETA por ciclo (orden Yunior 2026-07-21:
"tenemos toda una flota aparte del QQQ, que no pase lo de Micron de nuevo").
Lee los 26 NBBO, compara contra el estado del ciclo anterior y contra el open aprox,
e imprime SOLO los que se mueven (>0.35% desde el ciclo previo) o marcan extremos.
Señal-solamente. Uso: ./venv/bin/python scripts/fleet_pulse.py"""
import json, os, time
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ST = "data/fleet_pulse_state.json"
fleet = open("data/fleet.txt").read().split()
try: st = json.load(open(ST))
except Exception: st = {}
now = {}
out = []
for s in fleet:
    f = f"data/nbbo_{s.lower()}.txt"
    if not os.path.exists(f) or time.time()-os.path.getmtime(f) > 120: continue
    t = open(f).read().split()
    px = (float(t[1])+float(t[2]))/2
    now[s] = px
    prev = st.get("px", {}).get(s)
    hi = max(st.get("hi", {}).get(s, px), px)
    lo = min(st.get("lo", {}).get(s, px), px)
    if prev:
        d = (px/prev-1)*100
        tag = ""
        if px >= hi: tag = "🔺HOD-sesion"
        elif px <= lo: tag = "🔻LOD-sesion"
        if abs(d) >= 0.35 or tag:
            out.append(f"{s} {px:.2f} {d:+.2f}%/ciclo {tag}")
    st.setdefault("hi", {})[s] = hi
    st.setdefault("lo", {})[s] = lo
st["px"] = now; st["ts"] = int(time.time())
json.dump(st, open(ST, "w"))
print("\n".join(out) if out else "flota quieta")
