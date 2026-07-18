#!/usr/bin/env python3
"""qqq_breadth.py — RADAR DE AMPLITUD del QQQ (Claude, 2026-07-18).

Sistematiza el edge que Yunior y yo usamos a mano el 17-jul ("AAPL rojo tapaba
el QQQ, por eso NVDA no rompía"). En vez de mirar 8 gráficos, un solo veredicto.

Lee los bars IBKR locales de los pesos pesados del QQQ + confirmadores sectoriales
y responde 3 cosas que el índice solo NO te dice:

  1. BREADTH: cuántos magníficos están sobre su VWAP (fuerza interna real).
  2. DIVERGENCIA: ¿el QQQ sube pero sus componentes no? (aviso temprano de techo)
     o ¿el QQQ cae pero los componentes aguantan? (aviso de suelo). Esto SÍ da edge:
     el índice es la media; los componentes son la verdad.
  3. LÍDERES / REZAGADOS: quién tira y quién lastra, ordenado por fuerza vs VWAP.

Señal-solamente (ley #0): solo LEE archivos. Cero red, cero órdenes.
Uso:  ./venv/bin/python scripts/qqq_breadth.py     (o python3, no usa libs externas)
Pensado para llamarse dentro del fleet-check de 1 min.
"""
import glob, os, sys

# Pesos pesados del QQQ (los que mueven el índice) + confirmadores sectoriales.
# Peso aprox en QQQ para ponderar la divergencia (no hace falta exacto).
QQQ_HEAVY = {
    "nvda": 9, "aapl": 8, "msft": 8, "amzn": 6, "avgo": 5,
    "meta": 5, "googl": 4, "tsla": 3, "qcom": 2, "amd": 2, "intc": 1, "txn": 1,
}
SECTOR = ["smh", "xlk"]          # confirmadores sectoriales (breadth extra)
SESSION_START = 1784282400       # ajustar por día; el fleet-check ya usa este epoch

def load(sym):
    p = f"data/bars_{sym}_ibkr.txt"
    if not os.path.exists(p):
        return None
    rows = [l.split() for l in open(p) if l.strip()]
    bars = [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
            for r in rows]
    td = [b for b in bars if b[0] >= SESSION_START]
    if len(td) < 5:
        return None
    prior = [b for b in bars if b[0] < td[0][0]]
    pc = prior[-1][4] if prior else td[0][1]
    vol = sum(b[5] for b in td) or 1
    vwap = sum(((b[2] + b[3] + b[4]) / 3) * b[5] for b in td) / vol
    last = td[-1][4]
    return dict(last=last, pc=pc, vwap=vwap,
                chg=100 * (last - pc) / pc,
                vs_vwap=100 * (last - vwap) / vwap)

def main():
    comps = {s: load(s) for s in QQQ_HEAVY}
    comps = {s: d for s, d in comps.items() if d}
    qqq = load("qqq")
    if not comps or not qqq:
        print("qqq_breadth: sin datos suficientes"); return

    # 1) breadth ponderado: fracción del peso que está sobre VWAP
    tot_w = sum(QQQ_HEAVY[s] for s in comps)
    up_w = sum(QQQ_HEAVY[s] for s, d in comps.items() if d["vs_vwap"] > 0)
    breadth = 100 * up_w / tot_w
    n_up = sum(1 for d in comps.values() if d["vs_vwap"] > 0)

    # 2) divergencia: signo del QQQ vs signo neto ponderado de componentes
    comp_score = sum(QQQ_HEAVY[s] * (1 if d["vs_vwap"] > 0 else -1)
                     for s, d in comps.items()) / tot_w
    qqq_up = qqq["vs_vwap"] > 0
    diverge = ""
    if qqq_up and comp_score < -0.15:
        diverge = "⚠ DIVERGENCIA BAJISTA: QQQ sobre VWAP pero mayoría de peso DEBAJO — techo probable"
    elif (not qqq_up) and comp_score > 0.15:
        diverge = "⚠ DIVERGENCIA ALCISTA: QQQ bajo VWAP pero mayoría de peso ARRIBA — suelo probable"

    # 3) líderes / rezagados por fuerza vs VWAP
    ranked = sorted(comps.items(), key=lambda kv: kv[1]["vs_vwap"], reverse=True)
    lead = ", ".join(f"{s.upper()} {d['vs_vwap']:+.1f}%" for s, d in ranked[:3])
    lag = ", ".join(f"{s.upper()} {d['vs_vwap']:+.1f}%" for s, d in ranked[-3:])

    sec = []
    for s in SECTOR:
        d = load(s)
        if d: sec.append(f"{s.upper()} {d['vs_vwap']:+.1f}%")

    tag = "FUERTE" if breadth >= 66 else ("DÉBIL" if breadth <= 40 else "MIXTO")
    print(f"QQQ {qqq['last']:.2f} ({qqq['chg']:+.1f}%, vwap {qqq['vs_vwap']:+.1f}%) | "
          f"BREADTH {breadth:.0f}% [{tag}] {n_up}/{len(comps)} magníficos sobre VWAP")
    print(f"  líderes: {lead}   |   rezagados: {lag}")
    if sec: print(f"  sector: {' · '.join(sec)}")
    if diverge: print(f"  {diverge}")

main()
