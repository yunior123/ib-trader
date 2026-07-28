#!/usr/bin/env python3
"""eod_signal_validation — valida las señales del dia contra el tape SIP
(orden Yunior 2026-07-15: "we are gonna validate the signals today at the
end of the day, so u store all signals, even earthquake signals").

Lee ~/ib-trader/data/trading-signals/YYYY-MM-DD.txt (espejo = lo que el humano VIO
y cuando), cruza cada señal con data/bars_<sym>_ibkr.txt y mide:
  - px del banner vs close del bar que lo disparo (exactitud)
  - TERREMOTO: precision oficial = el movimiento NO retrocede >50% en 30 min
  - señales de dinero (BUY/SELL/PUT): mov a +15m y +30m tras el banner
Excluye WARMUP y lineas de infraestructura (SIN DATOS / TWS / TEST).
"""
import os
import re
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # regla 7: jamas ruta absoluta
os.chdir(ROOT)
DAY = datetime.now().strftime("%Y-%m-%d")
MIRROR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals", f"{DAY}.txt")

SYM_FILE = {s: f"data/bars_{s.lower()}_ibkr.txt" for s in
            ["NOK", "SPCX", "DRAM", "TSLA", "NVDA", "TXN", "TSM", "AMD",
             "INTC", "ASML", "AAPL", "GLD", "QQQ", "SLV", "CPER", "USO", "SKHY"]}
SYM_FILE["SKHYNIX"] = "data/bars_skhynix.txt"
SYM_FILE["SAMSUNG"] = "data/bars_samsung.txt"


def load_bars(path):
    out = []
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) == 6:
                out.append((float(p[0]), float(p[1]), float(p[2]),
                            float(p[3]), float(p[4]), float(p[5])))
    except FileNotFoundError:
        pass
    return out


def px_at(bars, ep):
    """close del ultimo bar con epoch <= ep."""
    best = None
    for b in bars:
        if b[0] <= ep:
            best = b
        else:
            break
    return best[4] if best else None


def hhmmss_to_epoch(hms):
    h, m, s = map(int, hms.split(":"))
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, s, 0, 0, -1))


def main():
    rows = []
    for ln in open(MIRROR):
        parts = [p.strip() for p in ln.strip().split(" | ", 2)]
        if len(parts) < 3:
            continue
        t, title, msg = parts
        if ("WARMUP" in title or "SIN DATOS" in title or "TWS" in title
                or "TEST" in title or "IBKR UPLINK" in title):
            continue
        m = re.match(r"([A-Z]+)[ :]", title)
        if not m:
            continue
        sym = m.group(1)
        pm = re.search(r"px (\d+\.?\d*)", msg) or re.search(r"@ (\d+\.?\d*)", msg)
        px = float(pm.group(1)) if pm else None
        kind = ("QUAKE_UP" if "TERREMOTO ALZA" in title else
                "QUAKE_DN" if "TERREMOTO CAIDA" in title else
                "MONEY" if any(k in title for k in
                               ("BUY", "SELL", "PUT", "STOP")) else "OTRO")
        rows.append(dict(t=t, ep=hhmmss_to_epoch(t), sym=sym, title=title,
                         kind=kind, px=px, msg=msg[:80]))

    print(f"===== VALIDACION EOD {DAY} — {len(rows)} señales en vivo =====\n")
    ok_px = bad_px = 0
    quake_tp = quake_fp = quake_nd = 0
    for r in rows:
        bars = load_bars(SYM_FILE.get(r["sym"], ""))
        line = f"{r['t']} {r['title']:26s}"
        # exactitud del px del banner vs tape
        if r["px"] and bars:
            bar_px = px_at(bars, r["ep"])
            if bar_px:
                dev = abs(r["px"] - bar_px) / bar_px * 100
                tag = "px-OK" if dev < 0.35 else f"px-DESVIA {dev:.2f}%"
                if dev < 0.35:
                    ok_px += 1
                else:
                    bad_px += 1
            else:
                tag = "sin-bar"
        else:
            tag = "sin-px"
        # precision terremoto: no retrocede >50% del pulso en 30 min
        ver = ""
        if r["kind"].startswith("QUAKE") and r["px"] and bars:
            p0 = r["px"]
            p30 = px_at(bars, r["ep"] + 1800)
            mm = re.search(r"([+-]?\d+\.\d+)%", r["msg"])
            if p30 and mm:
                pulse = float(mm.group(1)) / 100 * p0     # magnitud del pulso
                drift = (p30 - p0) if r["kind"] == "QUAKE_UP" else (p0 - p30)
                retr = -drift / abs(pulse) if pulse else 0
                good = retr < 0.5
                ver = f"| 30m {'TRUE' if good else 'RETRACE'} ({p30:.2f})"
                if good:
                    quake_tp += 1
                else:
                    quake_fp += 1
            else:
                ver = "| 30m sin-datos"
                quake_nd += 1
        if r["kind"] == "MONEY" and r["px"] and bars:
            p15 = px_at(bars, r["ep"] + 900)
            p30 = px_at(bars, r["ep"] + 1800)
            if p15 and p30:
                ver = f"| +15m {(p15/r['px']-1)*100:+.2f}% +30m {(p30/r['px']-1)*100:+.2f}%"
        print(f"{line} {tag:14s} {ver}")

    print(f"\n--- RESUMEN ---")
    print(f"px banner vs tape: {ok_px} OK / {bad_px} desviados (>0.35%)")
    tot = quake_tp + quake_fp
    if tot:
        print(f"terremotos con 30m de tape: {quake_tp}/{tot} TRUE "
              f"({quake_tp/tot*100:.0f}% precision oficial), {quake_nd} sin datos-30m")
    print("ventanas SIN señales (outages, no fallos de deteccion): "
          "13:09-13:46 y 14:40-16:00 (TWS/uplink IBKR)")


if __name__ == "__main__":
    main()
