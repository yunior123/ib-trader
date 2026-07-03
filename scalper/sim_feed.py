#!/usr/bin/env python3
"""sim_feed.py — replay REALTIME de un dia real para el whale scalper.

Toma barras 1m reales (data/bars_qqq_ibkr.txt) + alertas 🐋 reales del Desktop
y las reproduce en un directorio sandbox con ticks sub-minuto (puente
browniano O->H/L->C). El motor corre con --sim --data DIR y vive en el reloj
del feeder (clock.txt) — mismo codigo que en vivo.

Uso:
  python3 scalper/sim_feed.py --date 2026-07-21 --speed 5 --seed 7 --out /tmp/simdata &
  ./scalper/whale_scalper --sim --data /tmp/simdata --ledger /tmp/simledger
Velocidad honesta: <=5x (los timeouts de fill del sim son de 50-1200ms reales;
mas rapido que 5x distorsiona la mecanica — para iterar rapido usar --replay).
"""
import argparse, json, os, random, re, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_bars(sym, date):
    """data/bars_<sym>_ibkr.txt: EPOCH O H L C V (1m). Filtra al dia pedido."""
    day_start = int(time.mktime(time.strptime(date, "%Y-%m-%d")))
    day_end = day_start + 86400
    out = []
    with open(os.path.join(REPO, "data", f"bars_{sym.lower()}_ibkr.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) < 6:
                continue
            ep = int(float(p[0]))
            if day_start <= ep < day_end:
                out.append((ep, *(float(x) for x in p[1:5])))
    return out

def load_alerts(date):
    """~/ib-trader/data/trading-signals/DATE.txt -> [(epoch, side, sym, linea_jsonl)]"""
    path = os.path.expanduser(f"~/ib-trader/data/trading-signals/{date}.txt")
    day_start = int(time.mktime(time.strptime(date, "%Y-%m-%d")))
    out = []
    if not os.path.exists(path):
        return out
    rx = re.compile(r"^(\d\d):(\d\d):(\d\d) \| 🐋 BALLENA (CALLS|PUTS) \| ([A-Z]+):")
    for line in open(path, encoding="utf-8"):
        m = rx.match(line)
        if not m:
            continue
        hh, mm, ss, side, sym = int(m[1]), int(m[2]), int(m[3]), m[4], m[5]
        ep = day_start + hh * 3600 + mm * 60 + ss
        out.append((ep, side, sym))
    return out

def bridge_ticks(o, h, l, c, n, rng):
    """puente browniano simple por la barra: O -> (H,L en orden segun cierre) -> C."""
    up_first = c >= o if rng.random() > 0.3 else c < o
    anchors = [o, h if up_first else l, l if up_first else h, c]
    ticks = []
    seg = max(1, n // 3)
    for i in range(3):
        a, b = anchors[i], anchors[i + 1]
        for j in range(seg):
            f = (j + 1) / seg
            px = a + (b - a) * f + rng.gauss(0, abs(h - l) * 0.05)
            ticks.append(min(max(px, l), h))
    return ticks[:n] or [c]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sym", default="QQQ")
    ap.add_argument("--start", default="09:40", help="HH:MM ET de arranque del replay")
    a = ap.parse_args()
    if a.speed > 5:
        print("AVISO: speed>5 distorsiona la mecanica de fills; usar --replay para iterar", file=sys.stderr)
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)

    bars = load_bars(a.sym, a.date)
    alerts = load_alerts(a.date)
    if not bars:
        sys.exit(f"sin barras de {a.sym} para {a.date}")
    print(f"feed: {len(bars)} barras, {len(alerts)} alertas 🐋, speed {a.speed}x", file=sys.stderr)

    # cadena sintetica desde snapshot real (IV/spread tipicos si no hay archivo)
    iv, spread_d = 0.20, 0.04
    chain_path = os.path.join(REPO, "data", f"opt_chain_{a.sym.lower()}.txt")
    if os.path.exists(chain_path):
        rows = [l.split() for l in open(chain_path) if l[0] != "#"]
        ivs = [float(r[7]) for r in rows if len(r) >= 8 and float(r[7]) > 0]
        sps = [float(r[4]) - float(r[3]) for r in rows if len(r) >= 5 and float(r[3]) > 0]
        if ivs: iv = sorted(ivs)[len(ivs) // 2]
        if sps: spread_d = max(0.01, sorted(sps)[len(sps) // 2])
    exp = a.date.replace("-", "")

    def write_chain(spot, ep):
        """misma forma que opt_chain_cache.py; el motor solo usa strikes/bid/ask/iv."""
        lines = [f"# opt_chain {a.sym} | epoch {ep} | {a.date} | spot {spot:.2f} | exps {exp} {exp}",
                 "# strike right exp bid ask vol oi iv delta gamma"]
        import math
        secs = max((16 - int(hhmm_of(ep) / 100)) * 3600 - (int(hhmm_of(ep)) % 100) * 60, 60)
        T = secs / (365.0 * 24 * 3600)
        for d in range(-5, 6):
            k = round(spot) + d
            for right in "CP":
                # BS rapido via erfc
                sq = iv * math.sqrt(T)
                d1 = (math.log(spot / k) + 0.5 * iv * iv * T) / sq
                d2 = d1 - sq
                N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))
                mid = spot * N(d1) - k * N(d2) if right == "C" else k * N(-d2) - spot * N(-d1)
                bid = max(0.01, mid - spread_d / 2)
                lines.append(f"{k:.2f} {right} {exp} {bid:.2f} {bid + spread_d:.2f} 1000 1000 {iv:.4f} 0.4000 0.2000")
        tmp = os.path.join(a.out, ".chain.tmp")
        open(tmp, "w").write("\n".join(lines) + "\n")
        os.replace(tmp, os.path.join(a.out, f"opt_chain_{a.sym.lower()}.txt"))

    def hhmm_of(ep):
        lt = time.localtime(ep)
        return lt.tm_hour * 100 + lt.tm_min

    h0, m0 = map(int, a.start.split(":"))
    t0 = bars[0][0] - (bars[0][0] % 86400)
    sim_ep = int(time.mktime(time.strptime(a.date, "%Y-%m-%d"))) + h0 * 3600 + m0 * 60
    alerts = [x for x in alerts if x[0] >= sim_ep]
    ai = 0
    last_chain = 0
    alerts_path = os.path.join(a.out, "whale_alerts.jsonl")
    open(alerts_path, "w").close()

    TICK = 0.25          # 250ms sim por tick
    for ep, o, h, l, c in bars:
        if ep < sim_ep:
            continue
        n = int(60 / TICK)
        for i, px in enumerate(bridge_ticks(o, h, l, c, n, rng)):
            sim_now = ep + i * TICK
            # clock del motor: "EPOCH.mmm HHMM"
            tmp = os.path.join(a.out, ".clock.tmp")
            open(tmp, "w").write(f"{sim_now:.3f} {hhmm_of(int(sim_now))}\n")
            os.replace(tmp, os.path.join(a.out, "clock.txt"))
            # NBBO (sobrescrito, como el real)
            half = spread_d * 1.25 / 2   # spread subyacente tipico QQQ ~3c
            open(os.path.join(a.out, "nbbo_qqq.txt"), "w").write(
                f"{int(sim_now)} {px - 0.015:.4f} {px + 0.015:.4f}\n")
            # cadena cada 60s sim
            if sim_now - last_chain >= 60:
                write_chain(px, int(sim_now))
                last_chain = sim_now
            # alertas en su segundo historico
            while ai < len(alerts) and alerts[ai][0] <= sim_now:
                _, side, sym = alerts[ai]
                with open(alerts_path, "a") as f:
                    f.write(json.dumps({"ts": int(sim_now), "side": side, "sym": sym,
                                        "pc": 0.0, "vc": 0, "vp": 0},
                                       separators=(",", ":")) + "\n")
                print(f"ALERTA {side} {sym} @ {time.strftime('%H:%M:%S', time.localtime(sim_now))}", file=sys.stderr)
                ai += 1
            time.sleep(TICK / a.speed)
    print("fin del dia replay", file=sys.stderr)

if __name__ == "__main__":
    main()
