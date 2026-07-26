#!/usr/bin/env python
"""index_breadth.py — ENGRANAJE: QQQ/SPY heredan la direccion de sus componentes
pesados. "SPY baja si MSFT+NVDA+AAPL rompen a la baja." Confirmador de amplitud,
NO gatillo suelto: solo suma conviccion cuando los grandes estan ALINEADOS.

Nada hardcoded como veredicto: la direccion de cada componente se CALCULA en vivo
(gap, posicion vs cierre previo, ruptura bajista/alcista de nivel), y el engranaje
es el promedio PONDERADO por peso del indice. Escribe data/breadth.json.

Uso: ./venv/bin/python scripts/index_breadth.py [QQQ SPY] | --json
SEÑAL-SOLAMENTE. Aditivo: el generador lo lee si existe, si no sigue igual."""
import argparse, json, os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np
import yfinance as yf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

# Pesos aproximados de los top holdings (se normalizan entre los disponibles).
# Son PESOS de indice (publicos, cambian lento), no señales — la señal se calcula.
WEIGHTS = {
    "QQQ": {"NVDA": 9.0, "MSFT": 8.0, "AAPL": 7.5, "AMZN": 5.5, "AVGO": 5.0,
            "META": 4.5, "GOOGL": 5.0, "TSLA": 3.0, "NFLX": 3.0, "AMD": 2.0, "QCOM": 1.2},
    "SPY": {"NVDA": 7.5, "MSFT": 7.0, "AAPL": 6.5, "AMZN": 4.0, "META": 3.0,
            "GOOGL": 4.0, "AVGO": 2.5, "TSLA": 2.0, "AMD": 1.2, "NFLX": 1.5},
}

def latest_close(sym):
    """Ultimo precio: bars IBKR local si fresco (<10min), si no yfinance."""
    pth = f"data/bars_{sym.lower()}_ibkr.txt"
    try:
        if time.time() - os.path.getmtime(pth) < 600:
            last = None
            for ln in open(pth):
                # Los bars_*.txt son "EPOCH O H L C V" separados por ESPACIO, no por coma.
                # Con split(",") la condicion de abajo nunca se cumplia: last quedaba None,
                # la guarda de frescura de 600s era codigo MUERTO y cada corrida caia en
                # silencio a la cotizacion retrasada de yfinance. (fix 2026-07-24)
                p = ln.split()
                if len(p) >= 5:
                    try: last = float(p[4])
                    except Exception: pass
            if last: return last
    except Exception:
        pass
    try:
        return float(yf.Ticker(sym).fast_info.last_price)
    except Exception:
        return None

def component_lean(sym):
    """Direccion CALCULADA de un componente en [-1,+1] con etiqueta.
    Combina: gap vs cierre previo, posicion en el rango de ayer, ruptura de nivel."""
    try:
        d = yf.Ticker(sym).history(period="8d", interval="1d")
        if len(d) < 4: return 0.0, "s/d", 0.0
        # iloc[-1] es la vela de HOY (parcial, en vivo): comparar contra ella daba
        # gap~0 siempre. El cierre/rango de referencia es el de AYER, iloc[-2].
        pc = float(d.Close.iloc[-2]); pl = float(d.Low.iloc[-2]); ph = float(d.High.iloc[-2])
        atr = float(np.mean(d.High.values[-4:-1] - d.Low.values[-4:-1]))
        now = latest_close(sym)
        if not now or not atr: return 0.0, "s/d", 0.0
        gap = (now - pc) / pc * 100
        # componentes de la señal (todas calculadas):
        lean = 0.0
        lean += np.clip(gap / 0.6, -1, 1) * 0.5              # gap normalizado
        # ruptura bajista: por debajo del low de ayer = quiebre; alcista: sobre el high
        if now < pl: lean -= 0.4 + min((pl - now) / atr, 1) * 0.3
        elif now > ph: lean += 0.4 + min((now - ph) / atr, 1) * 0.3
        else:
            # posicion dentro del rango de ayer (-1 piso .. +1 techo)
            lean += ((now - pl) / (ph - pl) - 0.5) * 0.6 if ph > pl else 0
        lean = float(np.clip(lean, -1, 1))
        tag = ("RUPTURA BAJISTA" if now < pl else "ruptura alcista" if now > ph
               else "rango")
        return lean, tag, gap
    except Exception:
        return 0.0, "s/d", 0.0

def breadth(index):
    w = WEIGHTS.get(index, {})
    comps = {}
    tot = 0.0; num = 0.0
    for sym, wt in w.items():
        lean, tag, gap = component_lean(sym)
        if tag == "s/d": continue
        comps[sym] = dict(w=wt, lean=round(lean, 2), tag=tag, gap=round(gap, 2))
        tot += wt; num += wt * lean
    score = num / tot if tot else 0.0
    # conviccion: cuantos de los 3 mas pesados coinciden con el signo
    top3 = sorted(w, key=lambda s: -w[s])[:3]
    aligned = [s for s in top3 if s in comps and np.sign(comps[s]["lean"]) == np.sign(score) and abs(comps[s]["lean"]) > 0.2]
    breakdowns = [s for s in comps if comps[s]["tag"] == "RUPTURA BAJISTA"]
    breakouts = [s for s in comps if comps[s]["tag"] == "ruptura alcista"]
    if score <= -0.35 and len(aligned) >= 2:
        verdict = f"ENGRANAJE BAJISTA: {'+'.join(aligned)} arrastran a {index} abajo"
    elif score >= 0.35 and len(aligned) >= 2:
        verdict = f"ENGRANAJE ALCISTA: {'+'.join(aligned)} empujan {index} arriba"
    elif abs(score) < 0.15:
        verdict = f"ENGRANAJE NEUTRO/MIXTO: componentes divididos — {index} sin liderazgo claro"
    else:
        verdict = f"ENGRANAJE DEBIL ({score:+.2f}): sesgo sin confluencia — no confirma"
    return dict(index=index, score=round(score, 3), verdict=verdict,
                aligned_top=aligned, breakdowns=breakdowns, breakouts=breakouts,
                components=comps, ts=int(time.time()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indices", nargs="*", default=["QQQ", "SPY"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = {}
    for idx in (a.indices or ["QQQ", "SPY"]):
        out[idx] = breadth(idx.upper())
    json.dump(out, open("data/breadth.json", "w"), indent=1)
    if a.json:
        print(json.dumps(out, indent=1)); return
    for idx, b in out.items():
        print(f"\n== {idx} score {b['score']:+.2f} ==\n{b['verdict']}")
        if b["breakdowns"]: print("  rupturas BAJISTAS:", ", ".join(b["breakdowns"]))
        if b["breakouts"]: print("  rupturas alcistas:", ", ".join(b["breakouts"]))
        for s, c in sorted(b["components"].items(), key=lambda x: -x[1]["w"]):
            print(f"  {s:5} w{c['w']:>4} lean {c['lean']:+.2f} {c['tag']:16} gap {c['gap']:+.2f}%")

if __name__ == "__main__":
    main()
