#!/usr/bin/env python3
"""real_option_scorer.py — puntua CUALQUIER CSV de señales sobre el PAGO DE
OPCION REAL de Polygon (2026-07-23). El vehiculo que la flota opera de verdad.

Uso: real_option_scorer.py <signals.csv> [<signals2.csv> ...]
Formato de señal (compartido): epoch,sym,side,kind,ref_px,target_px,stop_px
  side LONG->CALL, SHORT->PUT. Para cada señal resuelve el contrato ATM semanal
  REAL, baja su prima 5m, y mide el TP +100% de la casa:
    - OPTIMISTA: +100% si el HIGH de la opcion lo toca (orden limite intradia).
    - CONSERVADOR: +100% solo si un CIERRE 5m real lo alcanza (evita spikes).
  Sin stop (como el metodo Yoel; la prima es la perdida maxima). Reporta por
  kind y global, WR + Wilson + retorno medio, con y sin (el que traiga el CSV
  no distingue vol — se agrupa por kind).
Cachea contratos y caminos; sin rate-limit observado. Señal-solamente.
"""
import csv, math, os, sys, time, json, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
K = None
for ln in open(os.path.join(REPO, "config", "feeds.env")):
    if ln.startswith("POLYGON_KEY"):
        K = ln.split("=", 1)[1].strip().strip('"')
if not K:
    raise SystemExit("falta POLYGON_KEY")

_cache = {}
def poly(url):
    if url in _cache:
        return _cache[url]
    full = url + ("&" if "?" in url else "?") + "apiKey=" + K
    for _ in range(3):
        try:
            with urllib.request.urlopen(full, timeout=30) as r:
                d = json.load(r)
            _cache[url] = d
            return d
        except Exception:
            time.sleep(1.2)
    return {}

def next_friday(t):
    lt = time.localtime(t)
    return time.strftime("%Y-%m-%d", time.localtime(t + ((4 - lt.tm_wday) % 7) * 86400))

_contract_cache = {}
def resolve(sym, exp, cp, spot):
    key = (sym.upper(), exp, cp, round(spot / max(spot * 0.01, 0.5)))
    if key in _contract_cache:
        return _contract_cache[key]
    typ = "call" if cp == "C" else "put"
    rs = []
    for exp_flag in ("true", "false"):
        d = poly(f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={sym.upper()}"
                 f"&expiration_date={exp}&contract_type={typ}&strike_price.gte={spot*0.95:.0f}"
                 f"&strike_price.lte={spot*1.05:.0f}&expired={exp_flag}&limit=50")
        rs = d.get("results", [])
        if rs:
            break
    out = (None, None)
    if rs:
        best = min(rs, key=lambda r: abs(r["strike_price"] - spot))
        out = (best["ticker"], best["strike_price"])
    _contract_cache[key] = out
    return out

def opt_path(otk, d0, d1):
    d = poly(f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/5/minute/{d0}/{d1}?adjusted=true&limit=5000&sort=asc")
    return [(r["t"] // 1000, r.get("o"), r.get("h"), r.get("l"), r.get("c")) for r in d.get("results", [])]

def score_csv(path, TP=1.00):
    rows = []
    for r in csv.reader(open(path)):
        if not r or r[0] == "epoch":
            continue
        try:
            rows.append((int(r[0]), r[1], r[2], r[3] if len(r) > 3 else "", float(r[4]) if len(r) > 4 and r[4] else 0))
        except Exception:
            continue
    buckets = {}   # kind -> {opt:[w,n,ret], con:[w,n,ret]}
    for (t, sym, side, kind, ref) in rows:
        cp = "C" if side.upper() == "LONG" else "P"
        exp = next_friday(t)
        spot = ref if ref > 0 else None
        if not spot:
            continue
        otk, strike = resolve(sym, exp, cp, spot)
        if not otk:
            continue
        day = time.strftime("%Y-%m-%d", time.localtime(t))
        pth = opt_path(otk, day, exp)
        entry = next(((et, o) for (et, o, h, l, c) in pth if et >= t and o and o > 0.02), None)
        if not entry:
            continue
        e_t, e_px = entry
        # optimista: high toca +100%
        opt_win = any(h and h >= e_px * (1 + TP) for (et, o, h, l, c) in pth if et >= e_t)
        opt_ret = TP if opt_win else None
        # conservador: cierre toca +100%
        con_win = any(c and c >= e_px * (1 + TP) for (et, o, h, l, c) in pth if et >= e_t)
        con_ret = TP if con_win else None
        # si no hay TP, liquidar al ultimo cierre real
        cl = [c for (et, o, h, l, c) in pth if et >= e_t and c is not None]
        settle = max((cl[-1] / e_px - 1), -1.0) if cl else -1.0
        if opt_ret is None: opt_ret = settle
        if con_ret is None: con_ret = settle
        b = buckets.setdefault(kind or "ALL", {"opt": [0, 0, 0.0], "con": [0, 0, 0.0]})
        b["opt"][0] += int(opt_ret > 0); b["opt"][1] += 1; b["opt"][2] += opt_ret
        b["con"][0] += int(con_ret > 0); b["con"][1] += 1; b["con"][2] += con_ret
    return buckets

def wilson(w, n):
    if n == 0: return 0.0
    p = w / n; z = 1.96; d = 1 + z * z / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)

def main():
    allb = {}
    out_json = {}
    for path in sys.argv[1:]:
        name = os.path.basename(path).replace("signals_", "").replace(".csv", "")
        print("=" * 76)
        print(f"### {name}   (opcion ATM semanal REAL, TP +100%)")
        b = score_csv(path)
        tot = {"opt": [0, 0, 0.0], "con": [0, 0, 0.0]}
        for kind, d in sorted(b.items()):
            for m in ("opt", "con"):
                for i in range(3):
                    tot[m][i] += d[m][i]
            o = d["opt"]; c = d["con"]
            if o[1]:
                print(f"  {kind:20s} n={o[1]:4d} | OPT WR {o[0]/o[1]*100:3.0f}% ret {o[2]/o[1]*100:+4.0f}% "
                      f"| CONS WR {c[0]/c[1]*100:3.0f}% ret {c[2]/c[1]*100:+4.0f}%")
        o = tot["opt"]; c = tot["con"]
        if o[1]:
            print(f"  {'TOTAL':20s} n={o[1]:4d} | OPT WR {o[0]/o[1]*100:3.0f}% ret {o[2]/o[1]*100:+4.0f}% wil{wilson(o[0],o[1])*100:.0f} "
                  f"| CONS WR {c[0]/c[1]*100:3.0f}% ret {c[2]/c[1]*100:+4.0f}% wil{wilson(c[0],c[1])*100:.0f}")
        out_json[name] = {"opt": {"n": o[1], "wr": round(o[0]/max(o[1],1),3), "ret": round(o[2]/max(o[1],1),3)},
                          "con": {"n": c[1], "wr": round(c[0]/max(c[1],1),3), "ret": round(c[2]/max(c[1],1),3)}}
    json.dump(out_json, open("data/backtest/scores_real_options_all.json", "w"), indent=1)
    print("\n-> data/backtest/scores_real_options_all.json")

if __name__ == "__main__":
    main()
