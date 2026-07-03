#!/usr/bin/env python3
"""leveraged_backtest.py — backtest de la TRADUCCION señal->ETF apalancado.

Simula las reglas EXACTAS del fleet_executor (orden Yunior 2026-07-11) sobre
90d de datos reales: señales del subyacente (bots C++ con la config viva de
los keepalives) ejecutadas en el ETF bull/bear mapeado (data/leveraged_map.json):

  BULL: compra al primer bar del ETF >= t_entrada; en la señal de salida vende
        SOLO si >= entry*(1+BAG_MIN_GAIN%); si no -> BOLSA con GTC en floor,
        se llena cuando un high posterior lo toca; si nunca -> bolsa abierta (MTM).
  BEAR: compra en la señal PUT; STOP -BEAR_STOP% servidor (low<=stop -> fill
        pesimista min(open,stop)); si no, sale con la señal de cover del bot.

Fees modeladas 0.2%/lado (IBKR cap 0.5%, micro-ordenes pagan centavos).
Sin limite de slots/cash (mide calidad de traduccion; con 500 USD el cash
limita ~4 concurrentes — el executor ya lo aplica en vivo).

Uso: venv/bin/python scripts/leveraged_backtest.py [days=90]
Salida: stdout + data/leveraged_bt_90d.txt
"""
import bisect, json, os, re, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)
import fleet_backtest_audit as A   # load_keepalive_env / fetch_one reutilizados

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 90
FEE = 0.002                # por lado
BAG_MIN_GAIN = 1.0 / 100
BEAR_STOP = 5.0 / 100
MAP = json.load(open("data/leveraged_map.json"))

d = {}
for line in open("alpaca.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1); d[k] = v.strip().strip('"')
H = {"APCA-API-KEY-ID": d["ALPACA_KEY"], "APCA-API-SECRET-KEY": d["ALPACA_SECRET"]}

def fetch_bars(sym):
    start = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min"
           f"&feed=iex&limit=10000&adjustment=raw&start={start}")
    bars, tok = [], None
    while True:
        u = url + (f"&page_token={tok}" if tok else "")
        j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read())
        for b in j.get("bars") or []:
            ep = int(datetime.fromisoformat(b["t"].split(".")[0].rstrip("Z") + "+00:00").timestamp())
            bars.append((ep, b["o"], b["h"], b["l"], b["c"]))
        tok = j.get("next_page_token")
        if not tok: break
        time.sleep(0.35)
    return bars

RX_L_IN  = re.compile(r"\*\*\* \w+: COMPRAR \*\*\* ~([\d.]+).*t=(\d+)")
RX_L_OUT = re.compile(r"\*\*\* \w+: VENDER \*\*\* ~([\d.]+).*t=(\d+)")
RX_S_IN  = re.compile(r"\*\*\* \w+: PUT \*\*\* ~([\d.]+).*t=(\d+)")
RX_S_OUT = re.compile(r"\*\*\* \w+: VENDER PUT \*\*\* ~([\d.]+).*t=(\d+)")

def signals(base):
    env = dict(os.environ); env.update(A.load_keepalive_env(base))
    hist = A.fetch_one(base, DAYS)
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "data"), exist_ok=True)
        with open(hist) as f:
            proc = subprocess.run([os.path.join(ROOT, f"{base.lower()}_signal_bot"), "--stdin"],
                                  stdin=f, capture_output=True, text=True, cwd=td, env=env)
    longs, shorts, cur_l, cur_s = [], [], None, None
    for line in proc.stdout.splitlines():
        if m := RX_L_IN.search(line):   cur_l = (int(m.group(2)), float(m.group(1)))
        elif m := RX_L_OUT.search(line):
            if cur_l: longs.append((cur_l[0], int(m.group(2)))); cur_l = None
        elif m := RX_S_IN.search(line): cur_s = (int(m.group(2)), float(m.group(1)))
        elif m := RX_S_OUT.search(line):
            if cur_s: shorts.append((cur_s[0], int(m.group(2)))); cur_s = None
    if cur_l: longs.append((cur_l[0], None))     # abierta al final
    if cur_s: shorts.append((cur_s[0], None))
    return longs, shorts

def sim(base):
    bull, bear = MAP[base]["bull"], MAP[base].get("bear")
    longs, shorts = signals(base)
    out = {"base": base, "bull": bull, "bear": bear, "closed": [], "bags": [],
           "bear_closed": [], "skipped": 0}
    def near(bars, eps, t, tol=300):
        i = bisect.bisect_left(eps, t)
        return i if i < len(bars) and eps[i] - t <= tol else None
    if longs:
        bb = fetch_bars(bull); eps = [b[0] for b in bb]
        for t_in, t_out in longs:
            i = near(bb, eps, t_in)
            if i is None: out["skipped"] += 1; continue
            entry = bb[i][1] * (1 + FEE)              # open + fee
            floor = entry * (1 + BAG_MIN_GAIN)
            j = near(bb, eps, t_out, tol=900) if t_out else None
            if j is not None and bb[j][4] >= floor:   # señal de venta y ESTAMOS arriba
                out["closed"].append((bb[j][4] * (1 - FEE) / entry - 1) * 100)
                continue
            # bolsa: GTC en floor desde la señal (o desde entrada si sigue abierta)
            start = j if j is not None else i + 1
            fill = next((k for k in range(start, len(bb)) if bb[k][2] >= floor), None)
            if fill is not None:
                out["closed"].append((floor * (1 - FEE) / entry - 1) * 100)
                out["bags"].append(("recuperada", (bb[fill][0] - t_in) / 86400))
            else:
                mtm = (bb[-1][4] * (1 - FEE) / entry - 1) * 100
                out["bags"].append(("ABIERTA", (bb[-1][0] - t_in) / 86400, mtm))
    if bear and shorts:
        sb = fetch_bars(bear); eps = [b[0] for b in sb]
        for t_in, t_out in shorts:
            i = near(sb, eps, t_in)
            if i is None: out["skipped"] += 1; continue
            entry = sb[i][1] * (1 + FEE)
            stop = entry * (1 - BEAR_STOP)
            end = near(sb, eps, t_out, tol=900) if t_out else len(sb) - 1
            if end is None: end = len(sb) - 1
            hit = next((k for k in range(i + 1, end + 1) if sb[k][3] <= stop), None)
            if hit is not None:
                px = min(sb[hit][1], stop)
                out["bear_closed"].append((px * (1 - FEE) / entry - 1) * 100)
            else:
                out["bear_closed"].append((sb[end][4] * (1 - FEE) / entry - 1) * 100)
    return out

def main():
    rep = []
    tot_closed, tot_bear, open_bags = [], [], []
    for base in MAP:
        try:
            r = sim(base)
        except Exception as e:
            rep.append(f"{base:5s} ERROR {e}"); continue
        c, bc = r["closed"], r["bear_closed"]
        ob = [b for b in r["bags"] if b[0] == "ABIERTA"]
        rec = [b for b in r["bags"] if b[0] == "recuperada"]
        wr = 100.0 * sum(1 for x in c if x > 0) / len(c) if c else 0
        bwr = 100.0 * sum(1 for x in bc if x > 0) / len(bc) if bc else 0
        line = (f"{base:5s} {r['bull']:5s} L:{len(c):3d} cerradas wr={wr:3.0f}% tot={sum(c):+7.1f}% "
                f"bolsas_rec={len(rec):2d} (max {max([b[1] for b in rec], default=0):.1f}d) "
                f"ABIERTAS={len(ob)} mtm={sum(b[2] for b in ob):+6.1f}% | "
                + (f"{r['bear']:5s} S:{len(bc):3d} wr={bwr:3.0f}% tot={sum(bc):+7.1f}%"
                   if r["bear"] else "sin bear") +
                (f" | skip={r['skipped']}" if r["skipped"] else ""))
        rep.append(line)
        tot_closed += c; tot_bear += bc; open_bags += [b[2] for b in ob]
    rep.append("-" * 100)
    wr = 100.0 * sum(1 for x in tot_closed if x > 0) / len(tot_closed) if tot_closed else 0
    bwr = 100.0 * sum(1 for x in tot_bear if x > 0) / len(tot_bear) if tot_bear else 0
    rep.append(f"TOTAL bull cerradas: n={len(tot_closed)} wr={wr:.0f}% tot={sum(tot_closed):+.1f}% "
               f"| bolsas abiertas: {len(open_bags)} mtm={sum(open_bags):+.1f}% "
               f"| bear: n={len(tot_bear)} wr={bwr:.0f}% tot={sum(tot_bear):+.1f}%")
    rep.append(f"(fees {FEE*100:.1f}%/lado; wr bull cerradas ~100% POR CONSTRUCCION — la regla "
               f"'solo vender arriba' convierte perdidas en bolsas; el coste real son las ABIERTAS)")
    text = "\n".join(rep)
    print(text)
    open("data/leveraged_bt_90d.txt", "w").write(text + "\n")

if __name__ == "__main__":
    main()
