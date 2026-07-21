#!/usr/bin/env python
"""finviz_scan.py — multi-screen Finviz Elite (2026-07-21, orden Yunior "usa mas skills de finviz").
Lanes nuevos ademas del hunter: VALLES (anti-montaña: large caps rojos hoy), EARN-MAN (reportan
mañana BMO), VOL-FRESCO (volumen inusual lejos del maximo 52w), REBOTE (perdedores con volumen).
Reusa el parser probado de options_hunter (CSV DictReader). Señal-solamente, throttle 2s.
Uso: ./venv/bin/python scripts/finviz_scan.py [lane...]   (sin args = todas)"""
import os, sys, time
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "scripts")
_argv = sys.argv; sys.argv = [sys.argv[0]]  # options_hunter parsea argv al importar (bug apuntado)
import options_hunter as oh
sys.argv = _argv   # auth(), fetch-style, parse(), num()

LANES = {
  "valles":     "cap_largeover,sh_opt_option,sh_avgvol_o2000,ta_perf_ddown",
  "earn-man":   "earningsdate_tomorrowbefore,sh_opt_option,sh_avgvol_o1000",
  "vol-fresco": "sh_relvol_o2,sh_opt_option,sh_avgvol_o1000,ta_highlow52w_a30h",
  "rebote":     "sh_opt_option,sh_avgvol_o2000,ta_perf_dn",
}

def fetch(filt):
    import urllib.request
    url = oh.BASE.format(f=filt, a=oh.auth())
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")

def main():
    want = sys.argv[1:] or list(LANES)
    for lane in want:
        try:
            rows = oh.parse(lane, fetch(LANES[lane]))
        except Exception as e:
            print(f"[{lane}] error: {e}"); time.sleep(2); continue
        rows.sort(key=lambda r: -r["score"])
        print(f"\n=== {lane.upper()} (top 8 de {len(rows)}) ===")
        for r in rows[:8]:
            print(f"  {r['sym']:6} {r['px']:>9.2f} {r['chg']:+6.1f}% rvol {r['rvol']:.1f} "
                  f"rsi {r['rsi']:.0f} $vol {r['dollar_m']:.0f}M {r['bias']:6} earn:{r['earn'][:10]}")
        time.sleep(2)

if __name__ == "__main__":
    main()
