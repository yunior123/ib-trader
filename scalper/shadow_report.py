#!/usr/bin/env python3
"""shadow_report.py — compara las operaciones sombra del ledger contra el
grafico real (barras 1m de QQQ): ¿que hizo el bot y que hizo el precio?

Uso: python3 scalper/shadow_report.py [scalper/ledger/trades_YYYY-MM-DD.jsonl]
Sin argumento: el ledger de hoy.
"""
import json, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_bars():
    bars = {}
    with open(os.path.join(REPO, "data", "bars_qqq_ibkr.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) >= 6:
                ep = int(float(p[0]))
                bars[ep - ep % 60] = tuple(float(x) for x in p[1:5])
    return bars

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REPO, "scalper", "ledger", f"trades_{time.strftime('%Y-%m-%d')}.jsonl")
    if not os.path.exists(path):
        sys.exit(f"sin ledger: {path}")
    bars = load_bars()
    evs = [json.loads(l) for l in open(path) if l.strip()]
    trades, cur = [], {}
    for e in evs:
        if e["ev"] == "ALERT":
            cur = {"alert": e}
        elif e["ev"] == "FILL" and "BUY" in e.get("reason", ""):
            cur["entry"] = e
        elif e["ev"] == "TRADE_CLOSE":
            cur["close"] = e
            trades.append(cur)
            cur = {}
    print(f"# Shadow report — {os.path.basename(path)}")
    print(f"eventos: {len(evs)} | trades cerrados: {len(trades)} | "
          f"skips: {sum(1 for e in evs if e['ev'] == 'GATE_SKIP')} | "
          f"ignoradas: {sum(1 for e in evs if e['ev'] == 'ALERT_IGNORED')}")
    print()
    tot = 0
    for t in trades:
        c = t.get("close", {})
        net = 0
        r = c.get("reason", "")
        if "net " in r:
            net = int(r.split("net ")[1].split("c")[0])
        tot += net
        ep = c.get("tw", 0) // 1000000
        m0 = ep - ep % 60
        ctx = ""
        if m0 in bars and m0 + 300 in bars:
            ctx = f" | QQQ al cierre {bars[m0][3]:.2f} -> +5m {bars[m0 + 300][3]:.2f}"
        strike = c.get("strike_c", 0) / 100
        print(f"{time.strftime('%H:%M:%S', time.localtime(ep))} {strike:g}{c.get('right','?')} "
              f"net {net:+d}c ({r[:60]}){ctx}")
    print(f"\nTOTAL: {tot:+d}c en {len(trades)} trades")
    for e in evs:
        if e["ev"] in ("HALT", "EXIT_STUCK"):
            print(f"⚠ {e['ev']}: {e['reason']}")

if __name__ == "__main__":
    main()
