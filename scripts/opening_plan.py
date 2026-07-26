#!/usr/bin/env python3
"""Plan de apertura por ticker: mapa 15m + muros + flujo firmado + ramas condicionales.

SENAL-SOLAMENTE. No canta probabilidad de la apertura: lo unico MEDIDO de esa ventana
(data/timeofday_factors.json) tiene el CI cruzando el 50% en las 5 celdas que existen.
Se publican RAMAS con su gatillo, no un porcentaje inventado.
"""
import json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uw_premium

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREES = os.path.join(ROOT, "data", "trees")
SYMS = ["QQQ", "NVDA", "SMH", "MU", "AAPL", "MSFT"]
TF_MIN = 15


def bars_1m(sym):
    p = os.path.join(ROOT, "data", f"bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p):
        f = line.split()
        if len(f) >= 6:
            out.append([int(float(f[0]))] + [float(x) for x in f[1:6]])
    return out


def agg(bars, minutes=TF_MIN):
    """1m -> Nm. El bucket lo fija el epoch, no el indice: una barra que falta no corre el reloj."""
    step, out = minutes * 60, []
    for b in bars:
        k = b[0] - (b[0] % step)
        if out and out[-1][0] == k:
            c = out[-1]
            c[2] = max(c[2], b[2]); c[3] = min(c[3], b[3]); c[4] = b[4]; c[5] += b[5]
        else:
            out.append([k, b[1], b[2], b[3], b[4], b[5]])
    return out


def bb(closes, n=20, k=2.0):
    if len(closes) < n:
        return None
    w = closes[-n:]
    m = sum(w) / n
    var = sum((x - m) ** 2 for x in w) / n
    sd = var ** 0.5
    if sd <= 0:
        return None
    up, lo = m + k * sd, m - k * sd
    return {"mid": m, "up": up, "lo": lo, "pctb": (closes[-1] - lo) / (up - lo)}


def atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        h, l, pc = bars[i][2], bars[i][3], bars[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)


def flow(sym):
    """Premium FIRMADO por el agresor (UW). Ausente si no hay fichero: nunca 0."""
    for d in sorted(os.listdir(os.path.join(ROOT, "data", "history")), reverse=True):
        p = os.path.join(ROOT, "data", "history", d, f"uw_net_prem_ticks_{sym.lower()}.json")
        if not os.path.exists(p):
            continue
        try:
            rows = json.load(open(p))["payload"]["data"]
        except (KeyError, json.JSONDecodeError):
            continue
        s = uw_premium.signed_premium(rows, window_min=100000)
        if s:
            s["fecha"] = d
            return s
    return None


def perp(sym, px_ref):
    """Perp 24/7 del MISMO nombre (Bybit). Es lo unico que cotiza con US cerrado."""
    p = os.path.join(ROOT, "data", "perp_stocks.json")
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p)).get(sym.upper())
    except (json.JSONDecodeError, OSError):
        return None
    if not d or not d.get("px") or not px_ref:
        return None
    d = dict(d)
    d["gap_pct"] = 100.0 * (d["px"] / px_ref - 1)
    d["ref_cierre"] = px_ref
    return d


def ramas(t, f, px, b15, pp=None):
    """Ramas CONDICIONALES con su gatillo. Cada una dice que la confirma y que la mata."""
    out = []
    cw, pw, flip, reg = t.get("call_wall"), t.get("put_wall"), t.get("flip"), t.get("regime")
    ck, pk = t.get("call_wall_kind"), t.get("put_wall_kind")
    if flip is not None and px is not None:
        lado = "POS" if px >= flip else "NEG"
        d = 100 * (flip / px - 1)
        out.append({
            "gatillo": f"flip {flip:,.2f} ({d:+.2f}% del precio)",
            "lee": (f"el precio abre en {lado}. " +
                    ("POS = dealers amortiguan: los niveles aguantan y el rango se comprime."
                     if lado == "POS" else
                     "NEG = dealers amplifican LOS DOS lados: es una CAJA, no una dirección.")),
            "invalida": f"cruzar {flip:,.2f} con 2 cierres de {TF_MIN}m cambia el régimen entero",
        })
    if cw is not None and px:
        out.append({
            "gatillo": f"muro de calls {cw:,.2f} ({100*(cw/px-1):+.2f}%)",
            "lee": ("PIN: los dealers lo defienden — se cobra AL llegar, no se persigue a través."
                    if ck == "pin" else
                    "TRAMPILLA: en NEG el precio lo ATRAVIESA. Prohibido fadear en el aire; "
                    "hace falta toque + rechazo IMPRESO (2 lecturas) de IBKR."),
            "invalida": "romperlo y RETESTARLO desde arriba lo convierte en suelo",
        })
    if pw is not None and px:
        out.append({
            "gatillo": f"muro de puts {pw:,.2f} ({100*(pw/px-1):+.2f}%)",
            "lee": ("PIN: suelo defendido, el rebote es la rama probable."
                    if pk == "pin" else
                    "TRAMPILLA: NO es piso. En NEG el nivel acelera la caída al perderse."),
            "invalida": "perderlo con volumen abre el siguiente strike de OI hacia abajo",
        })
    if f:
        sp, ncp, npp = f["signed_premium"], f["net_call_premium"], f["net_put_premium"]
        lado = "ALCISTA" if sp > 0 else "BAJISTA"
        det = []
        det.append("calls COMPRADAS" if ncp > 0 else "calls VENDIDAS")
        det.append("puts COMPRADAS" if npp > 0 else "puts VENDIDAS")
        out.append({
            "gatillo": f"flujo firmado del viernes: {sp:+,.0f} $ ({lado})",
            "lee": (f"{det[0]} ({ncp:+,.0f}) y {det[1]} ({npp:+,.0f}). El signo lo da el AGRESOR "
                    f"(ask menos bid), no el tipo de contrato: puts VENDIDAS son alcistas."),
            "invalida": "es posicionamiento del viernes, no del lunes: lo mata el print de apertura",
        })
    if pp:
        g = pp["gap_pct"]
        out.append({
            "gatillo": f"perp 24/7 en {pp['px']:,.2f} → gap {g:+.2f}% sobre el cierre del viernes",
            "lee": (f"el MISMO nombre cotizando con US cerrado (Bybit, vol 24h "
                    f"{pp['vol24h_usd']:,.0f} $, OI {pp['oi_usd']:,.0f} $, spread "
                    f"{pp['spread_pct']:.3f}%). Es el único descubrimiento de precio que hay "
                    f"ahora mismo, y apunta " + ("ARRIBA." if g > 0 else "ABAJO.")),
            "invalida": ("el perp cotiza con prima propia y libro fino de fin de semana: "
                         "un gap sin volumen es premio, no pronóstico. Lo confirma o lo mata "
                         "la apertura de IBKR"),
        })
    if b15:
        out.append({
            "gatillo": f"%B de {TF_MIN}m = {b15['pctb']:.2f} (banda {b15['lo']:,.2f}–{b15['up']:,.2f})",
            "lee": ("banda ALTA: estirado arriba, el rebote elástico juega en contra de perseguir."
                    if b15["pctb"] > 0.9 else
                    "banda BAJA: estirado abajo, cuidado con vender el suelo."
                    if b15["pctb"] < 0.1 else
                    "en la caja de la banda: sin extremo que fadear."),
            "invalida": "en régimen NEG la banda se camina (band-walk); el extremo no basta solo",
        })
    return out


def build(sym):
    p = os.path.join(TREES, f"{sym.lower()}.json")
    if not os.path.exists(p):
        return None, f"falta data/trees/{sym.lower()}.json — corre tree_sheets.py"
    t = json.load(open(p))
    b1 = bars_1m(sym)
    b15 = agg(b1)
    closes = [b[4] for b in b15]
    px = closes[-1] if closes else t.get("spot")
    f = flow(sym)
    a = atr(b15)
    pp = perp(sym, t.get("spot"))
    return {
        "sym": sym,
        "generado": dt.datetime.now().isoformat(timespec="seconds"),
        "tf_min": TF_MIN,
        "px_ultimo": px,
        "px_ts": b15[-1][0] if b15 else None,
        "n_barras_15m": len(b15),
        "bb15": bb(closes),
        "atr15": a,
        "atr15_pct": None if not (a and px) else 100 * a / px,
        "bars15": [[b[0], round(b[1], 2), round(b[2], 2), round(b[3], 2), round(b[4], 2), b[5]]
                   for b in b15[-90:]],
        "flujo": f,
        "perp": pp,
        "arbol": t,
        "ramas": ramas(t, f, px, bb(closes), pp),
        "apertura_medida": {
            "veredicto": "SIN EDGE MEDIDO en la ventana de apertura",
            "detalle": ("data/timeofday_factors.json: las 5 celdas que existen para "
                        "auction/golden tienen el CI de Wilson CRUZANDO el 50% "
                        "(cusum 56% [27,81] y 53% [39,66], whale 55% [28,79] y 33% [15,58], "
                        "bollinger 50% [36,64]). No se publica probabilidad de la apertura."),
        },
    }, None


def main():
    out = {}
    for s in (sys.argv[1:] or SYMS):
        s = s.upper()
        d, err = build(s)
        if d is None:
            print(f"{s}: {err}"); continue
        out[s] = d
        bbv = d["bb15"]
        print(f"{s:5} px {d['px_ultimo']:>9,.2f} | 15m n={d['n_barras_15m']:<5} "
              f"%B {bbv['pctb']:.2f} | ATR {d['atr15_pct']:.2f}% | "
              f"flujo {d['flujo']['signed_premium']:+,.0f} | ramas {len(d['ramas'])}"
              if bbv and d["flujo"] else f"{s:5} px {d['px_ultimo']}")
    dest = os.path.join(TREES, "opening_plan.json")
    with open(dest, "w") as fh:
        json.dump(out, fh, indent=1)
    print(dest)


if __name__ == "__main__":
    main()
