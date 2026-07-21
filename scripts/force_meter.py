#!/usr/bin/env python
"""force_meter.py — FUERZA en tiempo real del movimiento + detección de AGOTAMIENTO.

Un movimiento envejece: el precio puede seguir subiendo pero con MENOS fuerza cada
vez (volumen que cae, rango que se encoge, aceleración que se gira). Eso avisa ANTES
del giro y dice CUÁNDO apretar el stop. Este módulo lo mide en vivo desde las barras
1m y clasifica una FASE con su acción de stop:

  IMPULSO      fuerza fuerte + acelerando + volumen confirma -> dar aire, stop ancho
  MADURO       fuerza fuerte pero desacelerando            -> trail normal
  AGOTAMIENTO  precio extiende con volumen/rango/RSI cayendo (divergencia) -> stop a
               breakeven, media fuera; ojo posible giro
  GIRO         la fuerza cruzó cero / vela de reversión con volumen -> FUERA, reversal

Nada hardcoded: todo se normaliza por el ATR y las stats recientes del PROPIO ticker.
Escribe data/force.json. SEÑAL-SOLAMENTE. Aditivo.

Uso: ./venv/bin/python scripts/force_meter.py NVDA QQQ   (o --fleet, o --loop daemon)"""
import argparse, json, os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

def load_bars(sym, n=40):
    """Ultimas n barras 1m desde el archivo IBKR (epoch O H L C V). Fallback yfinance."""
    pth = f"data/bars_{sym.lower()}_ibkr.txt"
    rows = []
    try:
        if time.time() - os.path.getmtime(pth) < 900:  # <15min = mercado activo
            for ln in open(pth):
                p = ln.split()
                if len(p) >= 6:
                    try: rows.append([float(x) for x in p[:6]])
                    except Exception: pass
    except Exception:
        pass
    if len(rows) >= 12:
        return np.array(rows[-n:])
    # fallback yfinance (fuera de sesion o sin bridge)
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period="2d", interval="1m")
        if len(h) < 12: return None
        arr = np.column_stack([h.index.astype(np.int64)//10**9, h.Open, h.High, h.Low, h.Close, h.Volume])
        return arr[-n:]
    except Exception:
        return None

def rsi(closes, p=14):
    if len(closes) < p + 1: return 50.0
    d = np.diff(closes)
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.mean(up[-p:]); ad = np.mean(dn[-p:])
    if ad == 0: return 100.0
    return 100 - 100 / (1 + au / ad)

def measure(sym):
    b = load_bars(sym)
    if b is None or len(b) < 12:
        return dict(sym=sym, force=0, phase="s/d", note="sin barras suficientes")
    o, h, l, c, v = b[:, 1], b[:, 2], b[:, 3], b[:, 4], b[:, 5]
    n = len(c)
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
    if atr <= 0: atr = float(np.std(c)) or 1e-6
    # velocidad normalizada por ATR (EMA corto), signo = direccion
    ret = np.diff(c) / atr
    def ema(x, k):
        a = 2 / (k + 1); e = x[0]
        for z in x[1:]: e = a * z + (1 - a) * e
        return e
    vel = ema(ret[-10:], 5)                       # velocidad reciente
    vel_prev = ema(ret[-20:-10], 5) if len(ret) >= 20 else vel
    accel = vel - vel_prev                          # 2a derivada: acelera o frena
    dirn = np.sign(vel) or 1
    # persistencia: fraccion de barras recientes en la direccion dominante
    persist = float(np.mean(np.sign(ret[-10:]) == dirn))
    # confirmacion de volumen: ¿el volumen sube con el movimiento o cae? (tendencia lineal)
    vv = v[-12:]
    vtrend = float(np.polyfit(np.arange(len(vv)), vv / (np.mean(vv) or 1), 1)[0])
    # rango: ¿las velas se encogen? (agotamiento)
    rng = (h - l)[-12:] / atr
    rtrend = float(np.polyfit(np.arange(len(rng)), rng, 1)[0])
    # divergencia RSI: precio hace nuevo extremo pero RSI no confirma
    r_now = rsi(c); r_prev = rsi(c[:-5]) if n > 20 else r_now
    price_new_extreme = (c[-1] >= np.max(c[-10:-1])) if dirn > 0 else (c[-1] <= np.min(c[-10:-1]))
    rsi_div = price_new_extreme and ((r_now < r_prev) if dirn > 0 else (r_now > r_prev))
    # cuanto lleva corriendo la pierna actual (barras del mismo signo consecutivas)
    leg = 0
    for x in reversed(np.sign(ret)):
        if x == dirn: leg += 1
        else: break
    # FUERZA [-100,+100]: magnitud * confirmaciones, con signo
    mag = min(abs(vel) * 40, 60) + persist * 25 + (15 if vtrend > 0 else 0)
    force = float(np.clip(dirn * mag, -100, 100))
    # señales de agotamiento
    exh = sum([vtrend < -0.02, rtrend < -0.02, rsi_div, accel * dirn < -0.05, leg >= 12])
    # FASE
    if abs(force) < 20:
        phase = "SIN FUERZA"
    elif exh >= 3 or (accel * dirn < 0 and abs(force) > 40 and (vtrend < 0 or rsi_div)):
        phase = "AGOTAMIENTO"
    elif accel * dirn < -0.02:
        phase = "MADURO"
    elif accel * dirn >= 0 and abs(force) > 30:
        phase = "IMPULSO"
    else:
        phase = "MADURO"
    # deteccion de GIRO: la fuerza reciente cruzo cero o vela de reversion con volumen
    reversal_bar = (c[-1] < o[-1] and dirn > 0 or c[-1] > o[-1] and dirn < 0) and v[-1] > np.mean(v[-12:]) * 1.3
    if (np.sign(vel) != np.sign(vel_prev) and abs(vel_prev) > 0.1) or (phase == "AGOTAMIENTO" and reversal_bar):
        phase = "GIRO"
    # ACCION DE STOP segun fase (esto responde a lo que Yunior pidio)
    action = {
        "IMPULSO":     "dar aire: stop ancho (2 ATR), dejar correr",
        "MADURO":      "trail normal: stop a 1.2 ATR bajo el ultimo swing, no adelantar",
        "AGOTAMIENTO": "APRETAR: stop a breakeven o +1 tick, tomar MITAD; el movimiento pierde fuerza",
        "GIRO":        "FUERA: la fuerza se giro — cerrar; solo re-entrar en direccion opuesta con print",
        "SIN FUERZA":  "no hay tendencia: no perseguir, esperar impulso con volumen",
        "s/d":         "sin datos en vivo",
    }[phase]
    dirn_txt = "ARRIBA" if dirn > 0 else "ABAJO"
    return dict(sym=sym, force=round(force, 1), dir=dirn_txt, phase=phase,
                accel=round(float(accel), 3), vol_trend=round(vtrend, 3),
                rng_trend=round(rtrend, 3), rsi=round(r_now, 1), rsi_div=bool(rsi_div),
                leg_bars=int(leg), exhaustion=int(exh), action=action, ts=int(time.time()))

def run(syms, as_json=False):
    out = {s.upper(): measure(s.upper()) for s in syms}
    json.dump(out, open("data/force.json", "w"), indent=1)
    if as_json:
        print(json.dumps(out, indent=1)); return out
    for s, m in out.items():
        if m["phase"] in ("s/d", "SIN FUERZA"):
            print(f"{s:5} {m['phase']}  ({m.get('note','')})"); continue
        flag = "⚠" if m["phase"] in ("AGOTAMIENTO", "GIRO") else " "
        print(f"{s:5} fuerza {m['force']:+6.1f} {m['dir']:6} | {flag}{m['phase']:12} "
              f"| leg {m['leg_bars']:2}b exh {m['exhaustion']}/5 rsi {m['rsi']:.0f}"
              f"{' DIV' if m['rsi_div'] else ''}\n      -> {m['action']}")
    return out

FLEET = ["QQQ","SPY","NVDA","TSLA","MU","SMH","AMD","AAPL","MSFT","META","AMZN","GOOGL","NOK"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--loop", action="store_true", help="daemon: refresca cada 30s en sesion")
    a = ap.parse_args()
    syms = FLEET if a.fleet else (a.syms or ["QQQ", "SPY", "NVDA"])
    if a.loop:
        while True:
            lt = time.localtime()
            if lt.tm_wday < 5 and 930 <= lt.tm_hour * 100 + lt.tm_min < 1600:
                try: run(syms, False)
                except Exception as e: print("err", e, file=sys.stderr)
                time.sleep(30)
            else:
                time.sleep(120)
    else:
        run(syms, a.json)

if __name__ == "__main__":
    main()
