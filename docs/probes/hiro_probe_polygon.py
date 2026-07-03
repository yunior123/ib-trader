#!/usr/bin/env python3
"""Probe EMPIRICO del entitlement de Polygon para HIRO. Read-only. No toca el repo."""
import json, os, sys, time, urllib.request, urllib.error, datetime

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "feeds.env")   # regla 7
KEY = None
for ln in open(ENV):
    if ln.startswith("POLYGON_KEY="):
        KEY = ln.split("=", 1)[1].strip()
assert KEY, "no key"
print(f"key len={len(KEY)}  hoy={datetime.datetime.now():%Y-%m-%d %H:%M:%S %a}")

def get(path, tag):
    url = f"https://api.polygon.io{path}{'&' if '?' in path else '?'}apiKey={KEY}"
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            body = r.read().decode()
            code = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode(); code = e.code
    except Exception as e:
        print(f"{tag:34s} EXC {type(e).__name__}: {e}"); return None
    ms = (time.time() - t0) * 1000
    try:
        j = json.loads(body)
    except Exception:
        j = {"raw": body[:200]}
    st = j.get("status") or j.get("error") or ""
    n = len(j.get("results") or []) if isinstance(j.get("results"), list) else ("obj" if j.get("results") else 0)
    msg = (j.get("message") or "")[:150]
    print(f"{tag:34s} {code} {str(st)[:16]:16s} n={str(n):5s} {ms:6.0f}ms {msg}")
    return j

print("\n=== 1. LO QUE SABEMOS QUE FUNCIONA (control) ===")
snap = get("/v3/snapshot/options/QQQ?limit=250", "snapshot/options/QQQ")
otk = None
if snap and isinstance(snap.get("results"), list) and snap["results"]:
    rs = snap["results"]
    greeks = sum(1 for r in rs if r.get("greeks"))
    oi = sum(1 for r in rs if r.get("open_interest"))
    iv = sum(1 for r in rs if r.get("implied_volatility"))
    vol = sum(1 for r in rs if (r.get("day") or {}).get("volume"))
    lq = sum(1 for r in rs if r.get("last_quote"))
    lt = sum(1 for r in rs if r.get("last_trade"))
    print(f"   pagina1: {len(rs)} contratos | greeks {greeks} | oi {oi} | iv {iv} | day.volume {vol} | last_quote {lq} | last_trade {lt}")
    # coger el contrato mas liquido para las pruebas
    rs2 = sorted(rs, key=lambda r: -((r.get("day") or {}).get("volume") or 0))
    otk = rs2[0]["details"]["ticker"]
    print(f"   contrato de prueba (mas volumen): {otk}  vol={(rs2[0].get('day') or {}).get('volume')}")
    if rs2[0].get("last_quote"):
        print(f"   last_quote del snapshot: {json.dumps(rs2[0]['last_quote'])[:200]}")
    if rs2[0].get("last_trade"):
        print(f"   last_trade del snapshot: {json.dumps(rs2[0]['last_trade'])[:200]}")

if not otk:
    otk = "O:QQQ260731C00690000"

print(f"\n=== 2. LA CINTA DE OPCIONES (lo que HIRO necesita) — contrato {otk} ===")
get(f"/v3/trades/{otk}?limit=5", "v3/trades/O:  (prints)")
get(f"/v3/quotes/{otk}?limit=5", "v3/quotes/O:  (NBBO)")
get(f"/v2/last/trade/{otk}", "v2/last/trade/O:")
get(f"/v2/last/nbbo/{otk}", "v2/last/nbbo/O:")
get(f"/v3/snapshot?ticker={otk}", "v3/snapshot (unified)")
get(f"/v2/aggs/ticker/{otk}/range/1/minute/2026-07-23/2026-07-24?limit=5", "v2/aggs/O: 1m")
get(f"/v3/snapshot/options/QQQ/{otk}", "snapshot/options/QQQ/{contract}")

print("\n=== 3. LA MISMA CINTA EN ACCIONES (para aislar si es 'opciones' o 'trades') ===")
get("/v3/trades/AAPL?limit=3", "v3/trades/AAPL")
get("/v3/quotes/AAPL?limit=3", "v3/quotes/AAPL")
get("/v2/last/trade/AAPL", "v2/last/trade/AAPL")
get("/v2/last/nbbo/AAPL", "v2/last/nbbo/AAPL")

print("\n=== 4. INDICES / OTROS (contexto de entitlement) ===")
get("/v3/reference/options/contracts?underlying_ticker=QQQ&limit=3", "reference/options/contracts")
get("/v2/aggs/ticker/QQQ/range/1/minute/2026-07-24/2026-07-24?limit=3", "v2/aggs/QQQ 1m (equity)")
get("/v3/snapshot/indices?ticker=I:SPX", "snapshot/indices I:SPX")
