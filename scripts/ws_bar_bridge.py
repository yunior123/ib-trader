#!/usr/bin/env python3
"""Generic websocket bar bridge: finnhub|polygon -> 1m bars (seconds latency)
Usage: ws_bar_bridge.py <provider> <SYMBOL> <prefix>"""
import json, os, sqlite3, sys, threading, time, warnings
warnings.filterwarnings("ignore")
PROV, SYM, PFX = sys.argv[1], sys.argv[2], sys.argv[3]
for line in open(os.path.join(os.path.dirname(__file__), "..", "feeds.env")):
    k, _, v = line.strip().partition("="); os.environ.setdefault(k, v)

db = sqlite3.connect("trades.db", check_same_thread=False)
db.execute(f"CREATE TABLE IF NOT EXISTS {PFX}_bars (ts REAL PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL)")
db.execute(f"CREATE TABLE IF NOT EXISTS {PFX}_ticks (ts REAL, price REAL, size REAL)")
db.commit()
lock = threading.Lock()
cur = {"m": None}; last_emit = 0.0

def emit():
    global last_emit
    if cur["m"] is None or cur["m"] <= last_emit: return
    sys.stdout.write(f"{cur['m']:.0f} {cur['o']:.4f} {cur['h']:.4f} {cur['l']:.4f} {cur['c']:.4f} {cur['v']:.0f}\n")
    sys.stdout.flush()
    with lock:
        db.execute(f"INSERT OR IGNORE INTO {PFX}_bars VALUES (?,?,?,?,?,?)",
                   (cur["m"], cur["o"], cur["h"], cur["l"], cur["c"], cur["v"])); db.commit()
    last_emit = cur["m"]

def tick(px, sz, ep):
    m = ep - (ep % 60)
    if cur["m"] is None or m > cur.get("m", 0):
        if cur["m"] is not None: emit()
        cur.update(m=m, o=px, h=px, l=px, c=px, v=sz)
    else:
        cur["h"] = max(cur["h"], px); cur["l"] = min(cur["l"], px); cur["c"] = px; cur["v"] += sz
    with lock: db.execute(f"INSERT INTO {PFX}_ticks VALUES (?,?,?)", (ep, px, sz))

def backfill():
    global last_emit
    try:
        import yfinance as yf
        d = yf.Ticker(SYM).history(period="2d", interval="1m", prepost=True)
        for ts, r in d.iloc[:-1].iterrows():
            ep = ts.timestamp()
            if ep <= last_emit: continue
            sys.stdout.write(f"{ep:.0f} {r.Open:.4f} {r.High:.4f} {r.Low:.4f} {r.Close:.4f} {r.Volume:.0f}\n")
            with lock:
                db.execute(f"INSERT OR IGNORE INTO {PFX}_bars VALUES (?,?,?,?,?,?)",
                           (ep, r.Open, r.High, r.Low, r.Close, float(r.Volume)))
            last_emit = max(last_emit, ep)
        sys.stdout.flush()
        with lock: db.commit()
    except Exception as e:
        print(f"backfill err: {str(e)[:60]}", file=sys.stderr)

def ws_loop():
    import websocket
    if PROV == "finnhub":
        url = f"wss://ws.finnhub.io?token={os.environ['FINNHUB_KEY']}"
        def on_open(ws): ws.send(json.dumps({"type": "subscribe", "symbol": SYM}))
        def on_msg(ws, msg):
            m = json.loads(msg)
            if m.get("type") == "trade":
                for t in m.get("data", []):
                    tick(float(t["p"]), float(t.get("v", 0)), t["t"] / 1000.0)
    else:  # polygon
        url = "wss://socket.polygon.io/stocks"
        def on_open(ws):
            ws.send(json.dumps({"action": "auth", "params": os.environ["POLYGON_KEY"]}))
            ws.send(json.dumps({"action": "subscribe", "params": f"T.{SYM}"}))
        def on_msg(ws, msg):
            for m in json.loads(msg):
                if m.get("ev") == "T" and m.get("sym") == SYM:
                    tick(float(m["p"]), float(m.get("s", 0)), m["t"] / 1000.0)
                elif m.get("ev") == "status":
                    print(f"ws: {m.get('message')}", file=sys.stderr)
    while True:
        try:
            ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_msg)
            ws.run_forever(ping_interval=20)
        except Exception as e:
            print(f"ws err: {str(e)[:60]}", file=sys.stderr)
        time.sleep(10)

print(f"{PFX} bridge: {PROV} websocket + Yahoo backfill", file=sys.stderr)
backfill()
threading.Thread(target=ws_loop, daemon=True).start()
while True:
    time.sleep(90); backfill()
