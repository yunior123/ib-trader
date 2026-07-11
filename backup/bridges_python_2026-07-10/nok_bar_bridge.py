#!/usr/bin/env python3
"""NOK bridge v2: Alpaca WEBSOCKET (tick-by-tick, seconds) -> 1m bars for the
C++ engine + every tick stored in trades.db (nok_ticks). REST/Yahoo fallback."""
import json, os, sqlite3, sys, threading, time, warnings
warnings.filterwarnings("ignore")

for line in open(os.path.join(os.path.dirname(__file__), "..", "alpaca.env")):
    k, _, v = line.strip().partition("=")
    os.environ.setdefault(k, v)
KEY, SEC = os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"]

db = sqlite3.connect("trades.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS nok_bars (ts REAL PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL)")
db.execute("CREATE TABLE IF NOT EXISTS nok_ticks (ts REAL, price REAL, size REAL)")
db.commit()
lock = threading.Lock()
cur = {"m": None, "o": 0, "h": 0, "l": 0, "c": 0, "v": 0}
last_emit = 0.0

def emit_bar():
    global last_emit
    if cur["m"] is None or cur["m"] <= last_emit: return
    sys.stdout.write(f"{cur['m']:.0f} {cur['o']:.4f} {cur['h']:.4f} {cur['l']:.4f} {cur['c']:.4f} {cur['v']:.0f}\n")
    sys.stdout.flush()
    with lock:
        db.execute("INSERT OR IGNORE INTO nok_bars VALUES (?,?,?,?,?,?)",
                   (cur["m"], cur["o"], cur["h"], cur["l"], cur["c"], cur["v"]))
        db.commit()
    last_emit = cur["m"]

def on_tick(px, sz, ep):
    m = ep - (ep % 60)
    if cur["m"] is None:
        cur.update(m=m, o=px, h=px, l=px, c=px, v=sz)
    elif m > cur["m"]:
        emit_bar()                          # minuto cerrado -> al motor en ~1s
        cur.update(m=m, o=px, h=px, l=px, c=px, v=sz)
    else:
        cur["h"] = max(cur["h"], px); cur["l"] = min(cur["l"], px)
        cur["c"] = px; cur["v"] += sz
    with lock:
        db.execute("INSERT INTO nok_ticks VALUES (?,?,?)", (ep, px, sz))

def backfill():
    """REST: historical bars so indicators warm up + gap-fill when ws quiet."""
    import requests
    global last_emit
    try:
        r = requests.get("https://data.alpaca.markets/v2/stocks/NOK/bars",
                         params={"timeframe": "1Min", "limit": 1000, "feed": "iex"},
                         headers={"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}, timeout=15)
        from datetime import datetime
        for b in (r.json().get("bars") or [])[:-1]:
            ep = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).timestamp()
            if ep <= last_emit: continue
            sys.stdout.write(f"{ep:.0f} {b['o']:.4f} {b['h']:.4f} {b['l']:.4f} {b['c']:.4f} {b['v']:.0f}\n")
            with lock:
                db.execute("INSERT OR IGNORE INTO nok_bars VALUES (?,?,?,?,?,?)",
                           (ep, b['o'], b['h'], b['l'], b['c'], float(b['v'])))
            last_emit = max(last_emit, ep)
        sys.stdout.flush()
        with lock: db.commit()
    except Exception as e:
        print(f"backfill error: {str(e)[:60]}", file=sys.stderr)

def ws_loop():
    import websocket
    from datetime import datetime
    def on_message(ws, msg):
        for m in json.loads(msg):
            if m.get("T") == "t" and m.get("S") == "NOK":
                ep = datetime.fromisoformat(m["t"].replace("Z", "+00:00")).timestamp()
                on_tick(float(m["p"]), float(m.get("s", 0)), ep)
            elif m.get("T") == "success":
                print(f"ws: {m.get('msg')}", file=sys.stderr)
    def on_open(ws):
        ws.send(json.dumps({"action": "auth", "key": KEY, "secret": SEC}))
        ws.send(json.dumps({"action": "subscribe", "trades": ["NOK"]}))
    while True:
        try:
            ws = websocket.WebSocketApp("wss://stream.data.alpaca.markets/v2/iex",
                                        on_open=on_open, on_message=on_message)
            ws.run_forever(ping_interval=20)
        except Exception as e:
            print(f"ws error: {str(e)[:60]}", file=sys.stderr)
        time.sleep(10)

def main():
    print("nok bridge v2: Alpaca WEBSOCKET ticks (segundos) + backfill REST", file=sys.stderr)
    backfill()
    threading.Thread(target=ws_loop, daemon=True).start()
    # WALL-CLOCK BAR FLUSH (fix 2026-07-10: señales llegaban 5-15 min tarde).
    # El bar solo se emitia al llegar el PRIMER tick del minuto siguiente — en
    # el feed IEX (2-3% del volumen) NOK puede pasar minutos sin tick y el bar
    # quedaba retenido. Ahora: si el minuto del bar ya cerro hace >=3s, se
    # emite por reloj, con o sin tick nuevo.
    last_backfill = time.time()
    while True:
        time.sleep(2)
        if cur["m"] is not None and time.time() >= cur["m"] + 63:
            emit_bar()
        if time.time() - last_backfill >= 60:
            backfill()  # cubre huecos si el ws estuvo callado
            last_backfill = time.time()

if __name__ == "__main__":
    main()
