#!/usr/bin/env python
"""posthours_cage.py — PICARDIA de la JAULA: detecta cuando las ballenas 0DTE
mantuvieron el precio enjaulado todo el dia (rango realizado << implícito, pin en
strike pesado) y en el after-hours SE LIBERA hacia donde apuntan las ballenas
SEMANALES (no-0DTE, dinero grande que quiere que su strike se cumpla el viernes).

Cuando eso pasa (NO todos los dias), un producto apalancado por unas horas puede
capturar la liberacion. Se ENTRA con print y se SALE — es un estallido, no tendencia.

Nada hardcoded: jaula = realizado/implícito medido; direccion = sesgo de OI semanal
calculado; solo dispara con confluencia. Se corre en el postmarket (16:20+).
Escribe data/cage.json. SEÑAL-SOLAMENTE, jamas ordena. 2026-07-21."""
import argparse, json, os, time, warnings
warnings.filterwarnings("ignore")
import numpy as np
import yfinance as yf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

# Vehiculo apalancado por ticker (TFSA: bajista = ETF inverso, NO short).
# Solo ETFs que EXISTEN y son liquidos (verificar antes de recomendar — doctrina KORZ).
LEV = {
    "QQQ":  ("TQQQ", "SQQQ"), "SPY": ("UPRO", "SPXU"), "SMH": ("SOXL", "SOXS"),
    "NVDA": ("SOXL", "SOXS"), "MU": ("SOXL", "SOXS"), "AMD": ("SOXL", "SOXS"),
    "TSM": ("SOXL", "SOXS"), "AVGO": ("SOXL", "SOXS"), "DRAM": ("SOXL", "SOXS"),
    "TSLA": ("TSLL", "TSLQ"), "META": ("FBL", "—"), "AAPL": ("AAPU", "AAPD"),
}

def next_friday_exp(t):
    today = time.strftime("%Y-%m-%d")
    for e in t.options:
        if e > today and time.strptime(e, "%Y-%m-%d").tm_wday == 4:
            return e
    return t.options[-1] if t.options else None

def analyze(sym):
    try:
        t = yf.Ticker(sym)
        d = t.history(period="1d", interval="5m", prepost=True)
        rth = d[(d.index.strftime("%H%M") >= "0930") & (d.index.strftime("%H%M") < "1600")]
        if len(rth) < 10: return dict(sym=sym, setup=False, note="sin sesion RTH")
        rth_hi, rth_lo = float(rth.High.max()), float(rth.Low.min())
        rth_close = float(rth.Close.iloc[-1])
        realized = (rth_hi - rth_lo) / rth_close * 100
        # implícito del dia (straddle 0DTE/proximo)
        exp0 = next((e for e in t.options if e >= time.strftime("%Y-%m-%d")), None)
        implied = None
        if exp0:
            ch = t.option_chain(exp0)
            k = min(set(ch.calls.strike) & set(ch.puts.strike), key=lambda x: abs(x - rth_close))
            ca = ch.calls[ch.calls.strike == k]; pa = ch.puts[ch.puts.strike == k]
            if len(ca) and len(pa):
                implied = (float(ca.ask.iloc[0]) + float(pa.ask.iloc[0])) / rth_close * 100
        caged = implied is not None and realized < 0.62 * implied
        # after-hours: ¿se libera de la jaula?
        ah = d[d.index.strftime("%H%M") >= "1600"]
        ah_move = (float(ah.Close.iloc[-1]) - rth_close) / rth_close * 100 if len(ah) else 0.0
        released = abs(ah_move) > max(0.3, 0.35 * realized)
        ah_dir = "ARRIBA" if ah_move > 0 else "ABAJO"
        # sesgo ballenas SEMANALES (no-0DTE): OI neto call vs put del proximo viernes,
        # y donde se apila el OI grande respecto al precio (imán de la semana)
        expW = next_friday_exp(t)
        wk_bias = None; wk_magnet = None
        if expW and expW != exp0:
            cw = t.option_chain(expW)
            c = cw.calls.fillna(0); p = cw.puts.fillna(0)
            lo, hi = rth_close * 0.9, rth_close * 1.1
            c = c[(c.strike >= lo) & (c.strike <= hi)]; p = p[(p.strike >= lo) & (p.strike <= hi)]
            coi, poi = c.openInterest.sum(), p.openInterest.sum()
            pcr = poi / max(coi, 1)
            # imán = strike con mas OI combinado del lado dominante
            if coi > poi * 1.15:
                wk_bias = "ALCISTA"
                wk_magnet = float(c.nlargest(1, "openInterest").strike.iloc[0]) if len(c) else None
            elif poi > coi * 1.15:
                wk_bias = "BAJISTA"
                wk_magnet = float(p.nlargest(1, "openInterest").strike.iloc[0]) if len(p) else None
            else:
                wk_bias = "NEUTRO"
        # CONFLUENCIA: jaula + liberacion + after-hours en la direccion del sesgo semanal
        aligned = caged and released and wk_bias in ("ALCISTA", "BAJISTA") and (
            (ah_dir == "ARRIBA") == (wk_bias == "ALCISTA"))
        setup = bool(aligned)
        vehicle = None
        if setup:
            lv = LEV.get(sym)
            if lv:
                vehicle = lv[0] if ah_dir == "ARRIBA" else lv[1]
        note = ""
        if not caged: note = f"no hubo jaula (realizado {realized:.1f}% vs implícito {implied or 0:.1f}%)"
        elif not released: note = f"enjaulado pero sin liberacion AH ({ah_move:+.2f}%)"
        elif not aligned: note = f"liberacion {ah_dir} pero sesgo semanal {wk_bias} — sin confluencia"
        else: note = f"JAULA LIBERADA {ah_dir} confluye con ballenas semanales {wk_bias}"
        return dict(sym=sym, setup=setup, caged=bool(caged), released=bool(released),
                    realized=round(realized, 2), implied=round(implied, 2) if implied else None,
                    ah_move=round(ah_move, 2), ah_dir=ah_dir, wk_bias=wk_bias,
                    wk_magnet=wk_magnet, vehicle=vehicle, note=note, ts=int(time.time()))
    except Exception as e:
        return dict(sym=sym, setup=False, note=f"error {e}")

def _load_fleet(default):
    try:
        w = open("data/fleet.txt").read().split()
        return w if w else default
    except Exception:
        return default
FLEET = _load_fleet(["QQQ","SPY","NVDA","MU","SMH","AMD","TSM","AVGO","DRAM","TSLA","META","AAPL"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    syms = FLEET if a.fleet else (a.syms or FLEET)
    out = {s.upper(): analyze(s.upper()) for s in syms}
    json.dump(out, open("data/cage.json", "w"), indent=1)
    setups = [m for m in out.values() if m.get("setup")]
    if a.json:
        print(json.dumps(out, indent=1)); return
    print("=== PICARDIA JAULA -> LIBERACION AFTER-HOURS ===")
    if not setups:
        print("Hoy NO hay setup de jaula-liberacion (lo normal). Nada que perseguir.")
    for m in setups:
        v = m["vehicle"] or "underlying"
        mg = f" | imán semanal {m['wk_magnet']:g}" if m.get("wk_magnet") else ""
        print(f"⚡ {m['sym']}: {m['note']}{mg}")
        print(f"   VEHICULO posible (unas horas, entrar con print, SALIR): {v}")
    print("\nRecordatorio: esto pasa A VECES. Estallido, no tendencia. Definir salida ANTES.")
    print("Bajista en TFSA = ETF inverso (no short). No es consejo financiero.")

if __name__ == "__main__":
    main()
