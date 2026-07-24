#!/usr/bin/env python3
"""whales_week_map.py — mapa de BALLENAS para el resto de la semana.

Por ticker clave: cadena de opciones del viernes (yfinance, todas las expiries),
muros de OI ALTO (top calls = techos/imanes, top puts = pisos), max pain,
P/C de OI, cruzado con el regimen gamma de gexa (data/gexa_snapshot.json) y
las alertas 🐋 recientes. Todo veredicto con probabilidad (doctrina: jamas seco).

Uso: ./venv/bin/python scripts/whales_week_map.py [--exp 2026-07-24] [--out docs/WHALES-WEEK-2026-07-22.md]
SEÑAL-SOLAMENTE.
"""
import argparse, json, os, re, sys, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
import yfinance as yf

SYMS = ["QQQ", "SPY", "NVDA", "MU", "MSFT", "AAPL", "AMZN", "META", "GOOGL",
        "TSLA", "AMD", "AVGO", "SMH", "TSM", "LRCX", "SNDK", "WDC", "STX", "INTC"]

def live_spot(sym):
    try:
        ln = open(f"data/nbbo_{sym.lower()}.txt").read().split()
        if time.time() - float(ln[0]) <= 300:
            return (float(ln[1]) + float(ln[2])) / 2
    except Exception:
        pass
    return None

def whale_alert_bias(sym):
    """ultimo estado 🐋 por simbolo en los logs del Desktop (3 sesiones)."""
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
    rx = re.compile(r"\| 🐋 BALLENA (CALLS|PUTS) \| " + sym + r":")
    last = None
    try:
        for fn in sorted(os.listdir(d))[-3:]:
            for line in open(os.path.join(d, fn), encoding="utf-8"):
                m = rx.search(line)
                if m: last = (fn[:10], line[:8].strip(), m.group(1))
    except Exception:
        pass
    return last

def analyze(sym, exp, gexa):
    t = yf.Ticker(sym)
    spot = live_spot(sym) or float(t.fast_info.last_price)
    exps = t.options
    use = exp if exp in exps else next((e for e in exps if e >= exp), exps[0] if exps else None)
    if not use: return None
    ch = t.option_chain(use)
    calls, puts = ch.calls, ch.puts
    band = lambda df: df[(df.strike >= spot * 0.90) & (df.strike <= spot * 1.10)]
    c, p = band(calls), band(puts)
    if c.empty and p.empty: return None
    topc = c.nlargest(3, "openInterest")[["strike", "openInterest"]].values.tolist() if not c.empty else []
    topp = p.nlargest(3, "openInterest")[["strike", "openInterest"]].values.tolist() if not p.empty else []
    oi_c, oi_p = int(c.openInterest.sum() or 0), int(p.openInterest.sum() or 0)
    pc_oi = oi_p / max(oi_c, 1)
    ks = sorted(set(c.strike) | set(p.strike))
    coi = dict(zip(c.strike, c.openInterest.fillna(0)))
    poi = dict(zip(p.strike, p.openInterest.fillna(0)))
    mp = min(ks, key=lambda k: sum(max(0, k - s) * coi.get(s, 0) for s in ks)
                              + sum(max(0, s - k) * poi.get(s, 0) for s in ks)) if ks else spot
    gx = (gexa or {}).get(sym) or {}
    return dict(sym=sym, spot=spot, exp=use, topc=topc, topp=topp,
                pc_oi=pc_oi, max_pain=mp, gx=gx, whale=whale_alert_bias(sym))

def verdict(a):
    """probabilidades por doctrina imanes/gamma: hacia el iman si, a traves del muro no."""
    spot, mp = a["spot"], a["max_pain"]
    cw = a["topc"][0][0] if a["topc"] else None
    pw = a["topp"][0][0] if a["topp"] else None
    reg = (a["gx"].get("regime") or "").upper()
    flip = a["gx"].get("flip")
    drift_pain = (mp - spot) / spot * 100
    lines = []
    if cw and pw and pw <= spot <= cw:
        prob = 60 if reg == "POSITIVE" else 50
        lines.append(f"caja {pw:g}-{cw:g}: pin hacia max pain {mp:g} ({drift_pain:+.1f}%) prob~{prob}%")
    elif cw and spot > cw:
        lines.append(f"SOBRE el muro de calls {cw:g}: band-walk si aguanta 2 cierres (prob~45%), retorno al muro prob~55%")
    elif pw and spot < pw:
        lines.append(f"BAJO el piso de puts {pw:g}: rebote al piso prob~55%, aceleracion si gamma NEG")
    if flip:
        lado = "SOBRE" if spot > flip else "BAJO"
        lines.append(f"flip gexa {flip:g} ({lado}): {'dealers amortiguan' if spot > flip else 'dealers amplifican'}")
    if a["whale"]:
        d, h, side = a["whale"]
        lines.append(f"ultima 🐋 {side} {d} {h} -> {'techo local/iman arriba' if side=='CALLS' else 'piso/tesis bajista'}")
    return lines

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="2026-07-24")
    ap.add_argument("--out", default=f"docs/WHALES-WEEK-{time.strftime('%Y-%m-%d')}.md")
    a = ap.parse_args()
    gexa = {}
    try: gexa = json.load(open("data/gexa_snapshot.json"))
    except Exception: pass
    L = [f"# Mapa de ballenas — semana al {a.exp} (generado {time.strftime('%Y-%m-%d %H:%M ET')})",
         "", "OI ALTO del viernes = campos de fuerza: pico de calls = techo/iman; masivos puts = piso.",
         "Probabilidades por doctrina gamma-regime-walls. SEÑAL-SOLAMENTE.", ""]
    for sym in SYMS:
        try:
            r = analyze(sym, a.exp, gexa)
            if not r: print(f"{sym}: sin cadena", file=sys.stderr); continue
            fc = " ".join(f"{k:g}({int(oi/1000)}k)" for k, oi in r["topc"])
            fp = " ".join(f"{k:g}({int(oi/1000)}k)" for k, oi in r["topp"])
            L.append(f"## {sym} — spot {r['spot']:.2f} | exp {r['exp']} | P/C OI {r['pc_oi']:.2f} | max pain {r['max_pain']:g}")
            L.append(f"- Techos (calls OI): {fc or 's/d'}")
            L.append(f"- Pisos (puts OI): {fp or 's/d'}")
            for v in verdict(r): L.append(f"- {v}")
            L.append("")
            print(f"{sym}: ok", file=sys.stderr)
        except Exception as e:
            print(f"{sym}: FALLO {e}", file=sys.stderr)
    out = "\n".join(L) + "\n"
    open(a.out, "w").write(out)
    print(out)
    print(f"-> {a.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
