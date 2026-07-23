#!/usr/bin/env python
"""gexa_parse.py — herramienta REUTILIZABLE: parsea el texto de gexa.ai/terminal
(de get_page_text via la extension Chrome) a JSON estructurado. Rapido: parsear
texto es <1ms vs 29s de un screenshot. El browser saca el texto; esto lo estructura.

Flujo en vivo: navegar gexa, seleccionar ticker (skill gexa-terminal), get_page_text,
guardar a un .txt, correr:  ./venv/bin/python scripts/gexa_parse.py <archivo.txt> <SYM>
-> fusiona a data/gexa_snapshot.json (lo que leen el generador y los posters X).

Extrae: flip, dealer pressure, bias, Call$/Put$, POC, y los IMANES del panel
INSTITUTIONAL FOOTPRINT (strike, tipo HIGH MAGNET/SUPPORT, score /100, sweeps, flow).
SEÑAL-SOLAMENTE."""
import json, os, re, sys, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

def parse(text):
    d = {}
    # header ticker + precio
    m = re.search(r"\n([A-Z]{1,5})\n▾\n([\d.]+)", text)
    if m: d["sym"], d["price"] = m.group(1), float(m.group(2))
    # flip (0DTE o el que muestre el header): "flip 719 −23pt"
    m = re.search(r"flip\s+([\d.]+)", text)
    if m: d["flip"] = float(m.group(1))
    # dealer pressure: "Pressure +97" y BID/FLAT
    m = re.search(r"Pressure\s+([+-]?\d+)\s*(STRONG\s+)?(BID|FLAT|ASK)?", text)
    if m: d["pressure"], d["lean"] = int(m.group(1)), ((m.group(2) or "")+(m.group(3) or "")).strip()
    # dealer gamma score grande: "-39 NEGATIVE GAMMA" / "+76 ... POSITIVE"
    m = re.search(r"([+-]?\d+)\s+(DEEP\s+)?(NEGATIVE|POSITIVE)\s+GAMMA", text)
    if m: d["dealer_score"] = int(m.group(1)); d["regime"] = m.group(3)
    else:
        m = re.search(r"DEALER PRESSURE\s*\n?\s*([+-]?\d+)\s*\n?\s*(NEAR THE FLIP|[A-Z ]+)", text)
        if m: d["dealer_score"] = int(m.group(1)); d["regime"] = m.group(2).strip()[:20]
    # bias + premium
    m = re.search(r"Bias\s+(\w+)", text)
    if m: d["bias"] = m.group(1)
    m = re.search(r"Call\$\s*\$?([\d,]+).*?Put\$\s*\$?([\d,]+)", text, re.S)
    if m: d["call_usd"] = int(m.group(1).replace(",", "")); d["put_usd"] = int(m.group(2).replace(",", ""))
    # POC: "POC -66.2M 85%P"  o etiqueta "-396.5M 93%P"
    m = re.search(r"POC\s+([-\d.]+M?)\s+(\d+)%([PC])", text) or re.search(r"([-\d.]+M)\s+(\d+)%([PC])", text)
    if m: d["poc_gex"], d["poc_pct"], d["poc_side"] = m.group(1), int(m.group(2)), m.group(3)
    # IMANES del INSTITUTIONAL FOOTPRINT: "695 — HIGH MAGNET ... 95/100 · ... 7 sweeps · $4.1M flow"
    magnets = []
    for mm in re.finditer(r"(\d+(?:\.\d+)?)\s*[—-]?\s*(HIGH MAGNET|HIGH SUPPORT|HIGH RESISTANCE|MAGNET|SUPPORT|RESISTANCE)\b[^\n]*?(\d+)/100(?:[^\n]*?(\d+)\s+sweeps)?(?:[^\n]*?\$?([\d.]+M)\s+flow)?", text):
        magnets.append(dict(strike=float(mm.group(1)), type=mm.group(2), score=int(mm.group(3)),
                            sweeps=int(mm.group(4)) if mm.group(4) else None,
                            flow=mm.group(5) if mm.group(5) else None))
    if magnets:
        d["magnets"] = sorted(magnets, key=lambda x: -x["score"])[:8]
    d["ts"] = int(time.time())
    return d

def main():
    if len(sys.argv) < 2:
        sys.exit("uso: gexa_parse.py <archivo_pagetext.txt|-> [SYM]  (- = stdin)")
    src = sys.argv[1]
    text = sys.stdin.read() if src == "-" else open(src).read()
    d = parse(text)
    sym = sys.argv[2].upper() if len(sys.argv) > 2 else d.get("sym")
    if not sym:
        print(json.dumps(d, indent=1)); return
    # fusionar a gexa_snapshot.json (lo que leen generador + posters)
    snap = {}
    try: snap = json.load(open("data/gexa_snapshot.json"))
    except Exception: pass
    # normalizar a las claves que espera append_gexa/generador
    snap[sym] = dict(flip=d.get("flip"), score=d.get("dealer_score", d.get("pressure")),
                     bias=d.get("bias"), poc=d.get("poc_gex"),
                     magnets=d.get("magnets"), regime=d.get("regime"),
                     call_usd=d.get("call_usd"), put_usd=d.get("put_usd"), ts=d["ts"])
    json.dump(snap, open("data/gexa_snapshot.json", "w"), indent=1)
    try:
        # historia intradia para backtesting (orden Yunior 2026-07-22)
        with open("data/history/gexa_hist.jsonl", "a") as hf:
            hf.write(json.dumps({"sym": sym, **snap[sym]}, separators=(",", ":")) + "\n")
    except Exception:
        pass
    print(f"{sym} -> gexa_snapshot.json:", json.dumps(snap[sym]))

if __name__ == "__main__":
    main()
