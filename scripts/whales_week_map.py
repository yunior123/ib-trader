#!/usr/bin/env python3
"""whales_week_map.py — mapa de BALLENAS para el resto de la semana.

Por ticker clave: cadena de opciones del viernes (yfinance, todas las expiries),
muros de OI ALTO (top calls = techos/imanes, top puts = pisos), max pain,
P/C de OI, cruzado con el regimen gamma MEDIDO EN CASA (`gex_snapshot.load()`, griegas
reales de Polygon via gex_core — gexa.ai se jubilo el 2026-07-25) y las alertas 🐋
recientes. Todo veredicto con probabilidad (doctrina: jamas seco).

Si no hay mapa gamma fresco, la linea de flip/regimen NO se emite: se degrada a muros de
OI solamente y se dice en la cabecera. Jamas un flip inventado.

Uso: ./venv/bin/python scripts/whales_week_map.py [--exp 2026-07-24] [--out docs/WHALES-WEEK-2026-07-22.md]
SEÑAL-SOLAMENTE.
"""
import argparse, os, re, sys, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
DATA = os.path.join(REPO, "data")
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gex_snapshot  # noqa: E402  (mapa gamma propio: flip/regimen/muros MEDIDOS)
import yfinance as yf  # noqa: E402

GEX_MAX_AGE_H = 36   # el mapa del viernes sigue siendo el vigente el sabado; mas viejo, no

SYMS = ["QQQ", "SPY", "NVDA", "MU", "MSFT", "AAPL", "AMZN", "META", "GOOGL",
        "TSLA", "AMD", "AVGO", "SMH", "TSM", "LRCX", "SNDK", "WDC", "STX", "INTC"]

def live_spot(sym):
    """Mid del NBBO si es fresco (<=5 min), o None. Jamas un precio fabricado."""
    try:
        ln = open(os.path.join(DATA, f"nbbo_{sym.lower()}.txt")).read().split()
        if time.time() - float(ln[0]) <= 300:
            return (float(ln[1]) + float(ln[2])) / 2
    except (OSError, ValueError, IndexError) as e:
        print(f"{sym}: nbbo no usable ({type(e).__name__}) -> spot de yfinance", file=sys.stderr)
    return None

def whale_alert_bias(sym):
    """ultimo estado 🐋 por simbolo en los logs de señales (3 sesiones), o None."""
    d = os.path.join(DATA, "trading-signals")
    rx = re.compile(r"\| 🐋 BALLENA (CALLS|PUTS) \| " + sym + r":")
    last = None
    try:
        for fn in sorted(os.listdir(d))[-3:]:
            for line in open(os.path.join(d, fn), encoding="utf-8"):
                m = rx.search(line)
                if m: last = (fn[:10], line[:8].strip(), m.group(1))
    except OSError as e:
        print(f"{sym}: log de ballenas ilegible ({type(e).__name__}: {e})", file=sys.stderr)
    return last

def analyze(sym, exp, gmap):
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
    gx = (gmap or {}).get(sym) or {}   # gmap puede ser None (sin mapa): sin flip, no inventado
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
        # sin regimen MEDIDO el 50% no esta condicionado: se dice, para que nadie lo lea
        # como "medimos y salio neutro" (un numero plausible tapando un "no se")
        nota = "" if reg else " [regimen NO medido: prob sin condicionar]"
        lines.append(f"caja {pw:g}-{cw:g}: pin hacia max pain {mp:g} "
                     f"({drift_pain:+.1f}%) prob~{prob}%{nota}")
    elif cw and spot > cw:
        lines.append(f"SOBRE el muro de calls {cw:g}: band-walk si aguanta 2 cierres (prob~45%), retorno al muro prob~55%")
    elif pw and spot < pw:
        lines.append(f"BAJO el piso de puts {pw:g}: rebote al piso prob~55%, aceleracion si gamma NEG")
    if flip:
        lado = "SOBRE" if spot > flip else "BAJO"
        reg_txt = f", regimen {reg} MEDIDO" if reg else ""
        lines.append(f"flip medido {flip:g} ({lado}{reg_txt}): "
                     f"{'dealers amortiguan' if spot > flip else 'dealers amplifican'}")
    if a["whale"]:
        d, h, side = a["whale"]
        lines.append(f"ultima 🐋 {side} {d} {h} -> {'techo local/iman arriba' if side=='CALLS' else 'piso/tesis bajista'}")
    return lines

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="2026-07-24")
    ap.add_argument("--out", default=f"docs/WHALES-WEEK-{time.strftime('%Y-%m-%d')}.md")
    a = ap.parse_args()
    # mapa gamma propio: load() devuelve None (jamas {}) si falta, esta roto o excede la edad
    gmap = gex_snapshot.load(max_age_h=GEX_MAX_AGE_H)
    if gmap:
        gsrc = (f"Regimen gamma MEDIDO en casa: {len(gmap)} simbolos con griegas reales de "
                f"Polygon (gex_snapshot.py + gex_core).")
    else:
        gsrc = (f"SIN mapa gamma (data/gex_snapshot.json ausente, roto o >{GEX_MAX_AGE_H} h): "
                f"solo muros de OI — no se afirma flip ni regimen.")
        print(f"AVISO: {gsrc}", file=sys.stderr)
    L = [f"# Mapa de ballenas — semana al {a.exp} (generado {time.strftime('%Y-%m-%d %H:%M ET')})",
         "", "OI ALTO del viernes = campos de fuerza: pico de calls = techo/iman; masivos puts = piso.",
         "Probabilidades por doctrina gamma-regime-walls. SEÑAL-SOLAMENTE.", gsrc, ""]
    for sym in SYMS:
        try:
            r = analyze(sym, a.exp, gmap)
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
    dst = a.out if os.path.isabs(a.out) else os.path.join(REPO, a.out)   # ruta desde __file__
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"                                                   # escritura ATOMICA
    with open(tmp, "w") as f:
        f.write(out)
    os.replace(tmp, dst)
    print(out)
    print(f"-> {dst}", file=sys.stderr)

if __name__ == "__main__":
    main()
