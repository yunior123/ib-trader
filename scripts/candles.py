#!/usr/bin/env python3
"""candles.py — detector de patrones de velas japonesas sobre las barras 1m de la flota
(orden Yunior 2026-07-24: "check candlestick patterns, sometimes they tell a lot").

CONTEXTO, no gatillo: un patrón EN un muro/flip o extremo BB es una pista de reversión/
continuación; solo (regla PRINT O NADA) el nivel impreso da la entrada. Se combina con
muros/flip/GEX (chart_levels) en el pre-chequeo antes de responder sobre un ticker.

Detecta (single/dual/triple): doji, marubozu, martillo/hombre-colgado, estrella-fugaz/
martillo-invertido, engulfing alcista/bajista, harami, tweezer, estrella maña/tarde.
Usa contexto de tendencia (pendiente SMA corta) para el sesgo del patrón.

Uso: python3 scripts/candles.py SYM [tf_min]   (default 1m; tf_min agrega N velas 1m)
SEÑAL-SOLAMENTE: solo lee barras. Sin red, sin órdenes.
"""
import os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)


def load(sym, tf=1):
    path = f"data/bars_{sym.lower()}_ibkr.txt"
    if not os.path.exists(path):
        return []
    raw = []
    for ln in open(path):
        p = ln.split()
        if len(p) >= 5:
            try:
                raw.append([int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4])])
            except Exception:
                pass
    if tf <= 1:
        return raw
    # agrega cada tf velas 1m -> OHLC
    out = []
    for i in range(0, len(raw) - len(raw) % tf, tf):
        g = raw[i:i + tf]
        out.append([g[0][0], g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]])
    return out


def _feat(c):
    o, h, l, cl = c[1], c[2], c[3], c[4]
    rng = h - l or 1e-9
    body = abs(cl - o)
    up = h - max(o, cl)
    dn = min(o, cl) - l
    return dict(o=o, h=h, l=l, c=cl, rng=rng, body=body, up=up, dn=dn,
               bull=cl > o, bear=cl < o, bodyfrac=body / rng)


def trend(bars, n=10):
    """+1 sube, -1 baja, 0 plano — pendiente de los cierres recientes (antes de la vela actual)."""
    cl = [b[4] for b in bars[-(n + 1):-1]]
    if len(cl) < 3:
        return 0
    d = (cl[-1] - cl[0]) / (abs(cl[0]) or 1) * 100
    return 1 if d > 0.05 else (-1 if d < -0.05 else 0)


def detect(bars):
    """Devuelve lista de (patrón, sesgo, nota) de las 1-3 últimas velas. Sesgo: bull/bear/neutral."""
    if len(bars) < 3:
        return []
    a, b, c = _feat(bars[-3]), _feat(bars[-2]), _feat(bars[-1])  # c = vela actual
    t = trend(bars)
    out = []
    # --- single (vela actual c) ---
    if c["bodyfrac"] <= 0.10:
        out.append(("Doji", "neutral", "indecisión — reversión si está en muro/extremo"))
    if c["bodyfrac"] >= 0.90:
        out.append(("Marubozu " + ("alcista" if c["bull"] else "bajista"),
                    "bull" if c["bull"] else "bear", "convicción fuerte, continuación"))
    # martillo / estrella fugaz: mecha larga (>=2x cuerpo), cuerpo chico, mecha opuesta corta
    if c["body"] > 0 and c["dn"] >= 2 * c["body"] and c["up"] <= c["body"]:
        out.append(("Martillo" if t < 0 else "Hombre colgado", "bull" if t < 0 else "bear",
                    "mecha inferior larga = compradores en el fondo" if t < 0 else "aviso de techo"))
    if c["body"] > 0 and c["up"] >= 2 * c["body"] and c["dn"] <= c["body"]:
        out.append(("Estrella fugaz" if t > 0 else "Martillo invertido", "bear" if t > 0 else "bull",
                    "mecha superior larga = rechazo arriba" if t > 0 else "posible giro al alza"))
    # --- dual (b,c) ---
    if b["bear"] and c["bull"] and c["o"] <= b["c"] and c["c"] >= b["o"] and c["body"] > b["body"]:
        out.append(("Envolvente alcista", "bull", "cuerpo verde engulle al rojo previo — giro alcista" + (" (en tendencia baja)" if t < 0 else "")))
    if b["bull"] and c["bear"] and c["o"] >= b["c"] and c["c"] <= b["o"] and c["body"] > b["body"]:
        out.append(("Envolvente bajista", "bear", "cuerpo rojo engulle al verde previo — giro bajista" + (" (en tendencia alta)" if t > 0 else "")))
    if b["body"] > 0 and c["body"] < b["body"] and max(c["o"], c["c"]) <= max(b["o"], b["c"]) and min(c["o"], c["c"]) >= min(b["o"], b["c"]):
        out.append(("Harami", "bull" if t < 0 else "bear" if t > 0 else "neutral", "vela dentro de la previa — pausa/posible giro"))
    # tweezer: dos mechas casi iguales
    if abs(b["h"] - c["h"]) / (c["rng"] or 1) < 0.05 and t > 0:
        out.append(("Tweezer top", "bear", "dos techos iguales — resistencia"))
    if abs(b["l"] - c["l"]) / (c["rng"] or 1) < 0.05 and t < 0:
        out.append(("Tweezer bottom", "bull", "dos pisos iguales — soporte"))
    # --- triple (a,b,c): estrellas ---
    if a["bear"] and b["bodyfrac"] < 0.3 and c["bull"] and c["c"] > (a["o"] + a["c"]) / 2:
        out.append(("Estrella de la mañana", "bull", "3 velas: giro alcista tras caída"))
    if a["bull"] and b["bodyfrac"] < 0.3 and c["bear"] and c["c"] < (a["o"] + a["c"]) / 2:
        out.append(("Estrella de la tarde", "bear", "3 velas: giro bajista tras subida"))
    return out


def read(sym, tf=1):
    """API para el pre-chequeo: dict con velas recientes + patrones detectados."""
    bars = load(sym, tf)
    if len(bars) < 3:
        return {"sym": sym.upper(), "patterns": [], "note": "sin barras"}
    pats = detect(bars)
    last = bars[-1]
    return {"sym": sym.upper(), "tf": tf, "close": last[4],
            "patterns": [{"name": n, "bias": bz, "note": nt} for n, bz, nt in pats],
            "last3": [[round(b[1], 2), round(b[2], 2), round(b[3], 2), round(b[4], 2)] for b in bars[-3:]]}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    sym = sys.argv[1]
    tf = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    r = read(sym, tf)
    print(f"{r['sym']} {tf}m  close {r.get('close')}  (últimas 3 velas OHLC: {r.get('last3')})")
    if not r["patterns"]:
        print("  patrones de vela: ninguno claro en las últimas velas")
    for p in r["patterns"]:
        icon = "🟢" if p["bias"] == "bull" else "🔴" if p["bias"] == "bear" else "⚪"
        print(f"  {icon} {p['name']} [{p['bias']}] — {p['note']}")


if __name__ == "__main__":
    main()
