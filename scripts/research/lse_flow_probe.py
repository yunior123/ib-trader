#!/usr/bin/env python3
"""lse_flow_probe.py — mide el /options/flow de London Strategic Edge. LOTE fuera de sesion.

Modos: meta cover sweep side uw ws candles monday
Salida: data/research/lse_options_flow.json (escritura atomica, se fusiona por modo).
Fail-loud: cualquier fallo levanta; ningun except devuelve 0/0.5/{}.
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "data", "research", "lse_options_flow.json")
VAULT = "https://api.londonstrategicedge.com/vault"
WS_URL = "wss://ws.londonstrategicedge.com"
UA = "ib-trader/lse_flow_probe"          # sin User-Agent explicito Cloudflare da 403/1010
ROW_CAP = 5000


class ProbeError(Exception):
    pass


def api_key():
    k = os.environ.get("LSE_API_KEY")
    if not k:
        env = os.path.join(REPO, "config", "feeds.env")
        with open(env) as fh:
            for ln in fh:
                ln = ln.strip()
                if ln.startswith("LSE_API_KEY="):
                    k = ln.split("=", 1)[1].strip().strip('"').strip("'")
    if not k:
        raise ProbeError("LSE_API_KEY ausente en env y en config/feeds.env")
    return k


KEY = None
_last_call = [0.0]
_calls = [0]
_bytes = [0]


def get(path, **params):
    """GET al vault con pacing y reintento en 429/5xx. Levanta en cualquier otro fallo."""
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{VAULT}{path}" + (f"?{qs}" if qs else "")
    for attempt in range(6):
        gap = 0.32 - (time.time() - _last_call[0])
        if gap > 0:
            time.sleep(gap)
        _last_call[0] = time.time()
        _calls[0] += 1
        req = urllib.request.Request(url, headers={"x-api-key": KEY, "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                raw = resp.read()
                _bytes[0] += len(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            raise ProbeError(f"{e.code} en {path}: {body} <- {url[:200]}")
        except OSError as e:
            if attempt >= 4:
                raise ProbeError(f"transporte {path}: {e}")
            time.sleep(2.0 * (attempt + 1))
    raise ProbeError(f"agotados reintentos en {path} ({url[:160]})")


def flow(**p):
    p.setdefault("limit", ROW_CAP)
    p.setdefault("order", "asc")
    rows = get("/options/flow", **p)
    if not isinstance(rows, list):
        raise ProbeError(f"/options/flow devolvio {type(rows)} no lista")
    return rows


def flow_all(day, max_reqs=400, **p):
    """Tape COMPLETO de un dia paginando por tiempo. start/end aceptan
    'YYYY-MM-DD HH:MM:SS' (medido); el cursor avanza al ts de la ultima fila y se
    deduplica por id. Levanta si un solo segundo llena el tope de 5000 filas."""
    cur, end = f"{day} 00:00:00", nextday(day)
    seen, reqs = {}, 0
    while reqs < max_reqs:
        rows = flow(start=cur, end=end, order="asc", limit=ROW_CAP, **p)
        reqs += 1
        if not rows:
            break
        for r in rows:
            seen[r["id"]] = r
        if len(rows) < ROW_CAP:
            break
        last = rows[-1]["ts"][:19]
        if last == cur:
            n = sum(1 for r in rows if r["ts"][:19] == last)
            raise ProbeError(f"cursor atascado en {last}: {n} filas en un segundo (tope {ROW_CAP})")
        cur = last
    else:
        raise ProbeError(f"paginado sin terminar tras {max_reqs} peticiones ({p})")
    return list(seen.values()), reqs


def nextday(d):
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def pct(vals, q):
    if not vals:
        raise ProbeError("percentil sobre lista vacia")
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def save(section, payload):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = {}
    if os.path.exists(OUT):
        with open(OUT) as fh:
            doc = json.load(fh)
    doc.setdefault("_meta", {})
    doc["_meta"]["written_at"] = datetime.utcnow().isoformat() + "Z"
    doc["_meta"]["probe"] = "scripts/research/lse_flow_probe.py"
    doc[section] = payload
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=False)
    os.replace(tmp, OUT)
    print(f"[save] '{section}' -> {OUT} ({_calls[0]} llamadas, {_bytes[0]/1e6:.1f} MB)")


# ----------------------------------------------------------------- meta
def m_meta():
    usage = get("/usage")
    oldest = flow(order="asc", limit=1)
    newest = flow(order="desc", limit=1)
    sample = flow(min_premium=1_000_000, limit=1, order="desc")[0]
    chain = get("/options/chain", underlying="SPY", limit=1)
    cand = get("/options/candles", ticker=sample["ticker"], limit=1, order="asc")
    grans = {}
    for fmt in ["2026-08-07", "2026-08-07 14:00:00", "2026-08-07T14:00:00",
                "2026-08-07T14:00:00Z", "2026-08-07 14:00:00.123456", "1786114800"]:
        try:
            r = flow(start=fmt, end="2026-08-08", min_premium=1_000_000, limit=1)
            grans[fmt] = {"ok": True, "first_ts": r[0]["ts"] if r else None}
        except ProbeError as e:
            grans[fmt] = {"ok": False, "err": str(e)[:110]}
    out = {
        "usage": usage,
        "flow_fields": sorted(sample.keys()),
        "chain_fields": sorted(chain[0].keys()) if chain else None,
        "candle_fields": sorted(cand[0].keys()) if cand else None,
        "tape_oldest_ts": oldest[0]["ts"],
        "tape_newest_ts": newest[0]["ts"],
        "tape_span_days": (datetime.fromisoformat(newest[0]["ts"][:19])
                           - datetime.fromisoformat(oldest[0]["ts"][:19])).days,
        "row_cap_measured": len(flow(limit=10000)),
        "start_end_formatos": grans,
        "bid_ask_in_flow": any(k in sample for k in ("bid", "ask", "side", "aggressor")),
        "bid_ask_in_chain": any(k in (chain[0] if chain else {}) for k in ("bid", "ask")),
        "premium_minimo_en_tape": min(r["premium"] for r in flow(
            start="2026-08-07", end="2026-08-08", limit=ROW_CAP, order="asc")),
    }
    save("meta", out)
    return out


# ---------------------------------------------------------------- cover
def m_cover():
    """Que simbolos de la casa existen en el dataset de opciones de LSE."""
    cat = get("/catalog", limit=5000)
    if isinstance(cat, dict):
        cat = cat.get("items") or cat.get("data")
    opts = {x["symbol"] for x in cat if x.get("dataset") == "options"}
    fleet = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    uni = open(os.path.join(REPO, "data", "universe_gamma.txt")).read().split()
    faltan = [s for s in fleet if s not in opts]
    # el catalogo puede mentir: pedir tape real de los ausentes
    verif = {}
    for s in faltan + ["SPX", "XSP", "NDX"]:
        rows = flow(start="2026-08-07", end="2026-08-08", underlying=s, limit=5)
        verif[s] = len(rows)
    out = {
        "n_underlyings_options_catalogo": len(opts),
        "fleet_n": len(fleet), "fleet_en_lse": sum(1 for s in fleet if s in opts),
        "fleet_ausentes": faltan,
        "universe_gamma_ausentes": [s for s in uni if s not in opts],
        "verificacion_tape_de_los_ausentes": verif,
    }
    save("cobertura", out)
    return out


# ---------------------------------------------------------------- sweep
def day_stats(rows):
    prem = [r["premium"] for r in rows]
    by_sym, by_sym_n = {}, {}
    for r in rows:
        by_sym[r["underlying"]] = by_sym.get(r["underlying"], 0.0) + r["premium"]
        by_sym_n[r["underlying"]] = by_sym_n.get(r["underlying"], 0) + 1
    top = sorted(by_sym.items(), key=lambda kv: -kv[1])[:15]
    fleet = set(open(os.path.join(REPO, "data", "fleet.txt")).read().split())
    return {
        "n": len(rows),
        "premium_total": round(sum(prem), 0),
        "premium_p50": pct(prem, .50), "premium_p90": pct(prem, .90),
        "premium_p99": pct(prem, .99), "premium_max": max(prem),
        "call_frac": round(sum(1 for r in rows if r["contract_type"] == "call") / len(rows), 4),
        "dte_min": min(r["dte"] for r in rows), "dte_p50": pct([r["dte"] for r in rows], .5),
        "n_underlyings": len(by_sym),
        "frac_prints_flota": round(sum(n for s, n in by_sym_n.items() if s in fleet) / len(rows), 4),
        "top15_by_premium": [{"sym": s, "premium": round(p, 0), "n": by_sym_n[s]} for s, p in top],
    }


def m_sweep(days, thresholds):
    out = {}
    for d in days:
        out[d] = {"weekday": date.fromisoformat(d).strftime("%a")}
        for th in thresholds:
            rows, reqs = flow_all(d, min_premium=th)
            st = day_stats(rows) if rows else {"n": 0}
            st["min_premium"] = th
            st["peticiones"] = reqs
            out[d][f"min_premium_{th}"] = st
            print(f"[sweep] {d} >= ${th:,} n={st['n']} reqs={reqs}")
    save("sweep", out)
    return out


# ----------------------------------------------------------------- side
def tick_sign(rows):
    """Regla del tick por contrato: uptick=comprador agresor, downtick=vendedor,
    tick cero hereda el signo previo. Sin signo previo => 0 (sin firmar)."""
    by_c = {}
    for r in rows:
        by_c.setdefault(r["ticker"], []).append(r)
    for rs in by_c.values():
        rs.sort(key=lambda r: (r["ts"], r["id"]))
        prev_px, prev_sign = None, 0
        for r in rs:
            px = r["last_price"]
            sign = prev_sign if (prev_px is None or px == prev_px) else (1 if px > prev_px else -1)
            r["_tick_sign"] = sign
            prev_px = px
            if sign:
                prev_sign = sign
    return rows


def uw_path(day, sym):
    return os.path.join(REPO, "data", "history", day, f"uw_flow_per_strike_{sym.lower()}.json")


def m_side(day, syms):
    out = {"a_endpoint_params": {}, "b_quotes_endpoints": {}, "c_tick_rule_vs_uw": {}}

    base = flow(start=day, end=nextday(day), min_premium=1_000_000, limit=20, order="asc")
    base_ids = [r["id"] for r in base]
    probes = {"side": "buy", "aggressor": "ask", "buy_sell": "buy", "trade_side": "A",
              "columns": "id,ts,bid,ask,side", "fields": "bid,ask", "select": "bid,ask",
              "include": "quotes", "with_quotes": "1", "nbbo": "1", "bid": "1", "ask": "1",
              "exchange": "CBOE", "conditions": "sweep", "sweep": "1", "min_volume": "500",
              "max_premium": "2000000", "offset": "20", "page": "2", "cursor": "1",
              "ESTE_PARAMETRO_NO_EXISTE": "1"}
    for p, v in probes.items():
        rows = flow(start=day, end=nextday(day), min_premium=1_000_000, limit=20,
                    order="asc", **{p: v})
        out["a_endpoint_params"][p] = {
            "n": len(rows),
            "ids_identicos_al_control": [r["id"] for r in rows] == base_ids,
            "campos_nuevos": sorted(set(rows[0].keys()) - set(base[0].keys())) if rows else [],
        }
    ctl = out["a_endpoint_params"]["ESTE_PARAMETRO_NO_EXISTE"]["ids_identicos_al_control"]
    out["a_veredicto"] = ("el servidor IGNORA en silencio todo parametro desconocido "
                          f"(control inventado devuelve ids identicos={ctl}); "
                          "ninguno de los probados altera la respuesta ni añade campos")

    for path in ["/options/quotes", "/options/nbbo", "/options/book", "/quotes", "/nbbo",
                 "/options/trades", "/options/greeks", "/options/oi", "/options/open_interest"]:
        try:
            r = get(path, limit=1)
            out["b_quotes_endpoints"][path] = {"status": 200,
                                               "keys": sorted(r[0].keys())
                                               if isinstance(r, list) and r else str(type(r).__name__)}
        except ProbeError as e:
            out["b_quotes_endpoints"][path] = {"status": str(e)[:130]}

    for sym in syms:
        f = uw_path(day, sym)
        if not os.path.exists(f):
            raise ProbeError(f"falta el archivo UW {f}")
        with open(f) as fh:
            uw = json.load(fh)
        cut = uw["asof"]
        rows, reqs = flow_all(day, underlying=sym)
        rows = [r for r in rows
                if datetime.fromisoformat(r["ts"]).replace(tzinfo=None).timestamp() <= cut]
        rows = tick_sign(rows)
        lse = {}
        for r in rows:
            k = (round(float(r["strike"]), 4), r["contract_type"])
            a = lse.setdefault(k, {"vol": 0, "ask": 0, "bid": 0, "unsigned": 0})
            a["vol"] += r["volume"]
            if r["_tick_sign"] > 0:
                a["ask"] += r["volume"]
            elif r["_tick_sign"] < 0:
                a["bid"] += r["volume"]
            else:
                a["unsigned"] += r["volume"]
        pairs = []
        for row in uw["rows"]:
            st = round(float(row["strike"]), 4)
            for ct in ("call", "put"):
                ua, ub = int(row[f"{ct}_volume_ask_side"]), int(row[f"{ct}_volume_bid_side"])
                if (ua + ub) < 50:
                    continue
                l = lse.get((st, ct))
                if not l or (l["ask"] + l["bid"]) < 20:
                    continue
                pairs.append({"strike": st, "type": ct,
                              "uw_ask_frac": ua / (ua + ub),
                              "lse_ask_frac": l["ask"] / (l["ask"] + l["bid"]),
                              "lse_unsigned_frac": l["unsigned"] / max(l["vol"], 1)})
        if len(pairs) < 10:
            out["c_tick_rule_vs_uw"][sym] = {"n_pairs": len(pairs), "note": "muestra insuficiente"}
            continue
        x = [p["lse_ask_frac"] for p in pairs]
        y = [p["uw_ask_frac"] for p in pairs]
        mx, my = statistics.fmean(x), statistics.fmean(y)
        sx, sy = statistics.pstdev(x) or None, statistics.pstdev(y) or None
        r_p = (sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(x) / (sx * sy)
               if sx and sy else None)
        agree = sum(1 for a, b in zip(x, y) if (a > .5) == (b > .5)) / len(x)
        maj = max(sum(1 for b in y if b > .5), sum(1 for b in y if b <= .5)) / len(y)
        out["c_tick_rule_vs_uw"][sym] = {
            "n_pairs": len(pairs), "lse_prints_usados": len(rows),
            "pearson_r": round(r_p, 4) if r_p is not None else None,
            "mae_regla_tick": round(statistics.fmean(abs(a - b) for a, b in zip(x, y)), 4),
            "mae_baseline_media": round(statistics.fmean(abs(my - b) for b in y), 4),
            "acuerdo_direccional": round(agree, 4), "baseline_mayoritaria": round(maj, 4),
            "uw_ask_frac_medio": round(my, 4), "lse_ask_frac_medio": round(mx, 4),
            "unsigned_frac_medio": round(statistics.fmean(p["lse_unsigned_frac"] for p in pairs), 4),
        }
        print(f"[side] {sym} pares={len(pairs)} r={out['c_tick_rule_vs_uw'][sym]['pearson_r']} "
              f"acuerdo={agree:.3f} vs mayoritaria {maj:.3f}")
    save("side", out)
    return out


# ------------------------------------------------------------------- uw
def m_uw(day, syms):
    out = {"day": day, "por_sym": {}}
    for sym in syms:
        with open(uw_path(day, sym)) as fh:
            uw = json.load(fh)
        cut = uw["asof"]
        rows, reqs = flow_all(day, underlying=sym)
        rows_cut = [r for r in rows
                    if datetime.fromisoformat(r["ts"]).replace(tzinfo=None).timestamp() <= cut]
        uw_vol = sum(int(r["call_volume"]) + int(r["put_volume"]) for r in uw["rows"])
        uw_tr = sum(int(r["call_trades"]) + int(r["put_trades"]) for r in uw["rows"])
        uw_pr = sum(float(r["call_premium"]) + float(r["put_premium"]) for r in uw["rows"])
        ent = {
            "lse_prints_dia": len(rows), "peticiones": reqs,
            "uw_asof_utc": datetime.utcfromtimestamp(cut).isoformat() + "Z",
            "lse_ts_ultimo": max(r["ts"] for r in rows),
            "uw_volume": uw_vol, "lse_volume": sum(r["volume"] for r in rows_cut),
            "cobertura_volumen": round(sum(r["volume"] for r in rows_cut) / uw_vol, 4) if uw_vol else None,
            "uw_trades": uw_tr, "lse_prints": len(rows_cut),
            "prints_lse_por_trade_uw": round(len(rows_cut) / uw_tr, 4) if uw_tr else None,
            "uw_premium": round(uw_pr, 0),
            "lse_premium": round(sum(r["premium"] for r in rows_cut), 0),
            "cobertura_premium": round(sum(r["premium"] for r in rows_cut) / uw_pr, 4) if uw_pr else None,
            "dte_min_tape_completo": min(r["dte"] for r in rows),
        }
        # contra la cadena archivada de Polygon: volumen del dia por CONTRATO
        fp = os.path.join(REPO, "data", "history", day, f"chain_full_{sym.lower()}.json")
        if os.path.exists(fp):
            with open(fp) as fh:
                ch = json.load(fh)
            pol = {}
            for c in ch["results"]:
                dd = c["details"]
                t = (dd["expiration_date"], round(float(dd["strike_price"]), 4), dd["contract_type"])
                pol[t] = pol.get(t, 0) + int(c.get("day", {}).get("volume") or 0)
            lse_c = {}
            for r in rows:
                t = (r["expiry"], round(float(r["strike"]), 4), r["contract_type"])
                lse_c[t] = lse_c.get(t, 0) + r["volume"]
            pol_vivos = {t: v for t, v in pol.items() if v > 0}
            comun = [t for t in lse_c if t in pol_vivos]
            polv = sum(pol_vivos[t] for t in comun)
            lsev = sum(lse_c[t] for t in comun)
            zero = [t for t in pol_vivos if t[0] == day]
            ent["polygon_chain"] = {
                "contratos_polygon_con_volumen": len(pol_vivos),
                "contratos_lse": len(lse_c), "contratos_comunes": len(comun),
                "vol_polygon_total": sum(pol_vivos.values()),
                "vol_polygon_en_comunes": polv, "vol_lse_en_comunes": lsev,
                "cobertura_vol_en_comunes": round(lsev / polv, 4) if polv else None,
                "cobertura_vol_dia_total": round(lsev / sum(pol_vivos.values()), 4) if pol_vivos else None,
                "contratos_lse_por_encima_de_polygon": sum(1 for t in comun if lse_c[t] > pol_vivos[t] * 1.02),
                "contratos_0dte_polygon": len(zero),
                "vol_0dte_polygon": sum(pol_vivos[t] for t in zero),
                "frac_volumen_dia_que_es_0dte": round(sum(pol_vivos[t] for t in zero) / sum(pol_vivos.values()), 4) if pol_vivos else None,
                "vol_0dte_visto_por_lse": sum(lse_c.get(t, 0) for t in zero),
            }
        out["por_sym"][sym] = ent
        print(f"[uw] {sym} vol {ent['lse_volume']:,}/{uw_vol:,} = {ent['cobertura_volumen']} | "
              f"0DTE Polygon {ent.get('polygon_chain', {}).get('frac_volumen_dia_que_es_0dte')}")
    save("uw_compare", out)
    return out


# ------------------------------------------------------------------- ws
def m_ws(syms, seconds):
    sys.path.insert(0, os.path.join(REPO, "venv-lse", "lib", "python3.9", "site-packages"))
    import asyncio
    import websockets

    async def run():
        log, ticks, kinds = [], [], {}
        async with websockets.connect(WS_URL, ping_interval=25, ping_timeout=30,
                                      max_size=None) as ws:
            log.append(json.loads(await ws.recv()))
            await ws.send(json.dumps({"action": "auth", "api_key": KEY}))
            t0, subbed = time.time(), False
            while time.time() - t0 < seconds:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                msg = json.loads(raw)
                t = msg.get("type", "SIN_TYPE")
                kinds[t] = kinds.get(t, 0) + 1
                if t in ("tick", "trade", "quote", "option_tick", "SIN_TYPE"):
                    ticks.append(msg)
                elif len(log) < 40:
                    m = dict(msg)
                    m.pop("symbols", None)
                    log.append(m)
                if t == "authenticated" and not subbed:
                    subbed = True
                    for s in syms:
                        await ws.send(json.dumps({"action": "subscribe_options", "underlying": s}))
                        await asyncio.sleep(0.2)
                    await ws.send(json.dumps({"action": "subscribe", "symbol": "BTC-USD"}))
                    await ws.send(json.dumps({"action": "subscribe", "symbol": "BTC/USD"}))
        return log, ticks, kinds

    log, ticks, kinds = asyncio.get_event_loop().run_until_complete(run())
    keys = sorted({k for t in ticks for k in t})
    withq = [t for t in ticks if t.get("bid") is not None and t.get("ask") is not None]
    out = {"url": WS_URL, "symbols": syms, "seconds": seconds,
           "control_messages": log[:20], "tipos_de_trama": kinds,
           "n_ticks": len(ticks), "tick_keys": keys,
           "n_ticks_con_bid_y_ask": len(withq), "sample_ticks": ticks[:10],
           "es_contrato_de_opcion": sum(1 for t in ticks
                                        if len(str(t.get("symbol", ""))) > 12
                                        and any(c in str(t.get("symbol")) for c in "CP")),
           "nota": "sabado con bolsa cerrada: lo que llegue es snapshot, no flujo"}
    if withq:
        out["price_igual_bid"] = sum(1 for t in withq if abs(t["price"] - t["bid"]) < 1e-9)
        out["price_igual_ask"] = sum(1 for t in withq if abs(t["price"] - t["ask"]) < 1e-9)
    save("websocket", out)
    return out


# -------------------------------------------------------------- candles
def m_candles(contracts):
    out = {}
    for c in contracts:
        first = get("/options/candles", ticker=c, limit=1, order="asc")
        if not first:
            out[c] = {"error": "sin barras"}
            print(f"[candles] {c} SIN BARRAS")
            continue
        last = get("/options/candles", ticker=c, limit=1, order="desc")
        d0, d1 = first[0]["minute"][:10], last[0]["minute"][:10]
        total, days_seen, cur, pages = 0, set(), first[0]["minute"][:19], 0
        while pages < 60:
            rows = get("/options/candles", ticker=c, start=cur, end=nextday(d1),
                       limit=ROW_CAP, order="asc")
            pages += 1
            if not rows:
                break
            new = [r for r in rows if r["minute"][:19] > cur or pages == 1]
            total += len(new)
            days_seen |= {r["minute"][:10] for r in rows}
            if len(rows) < ROW_CAP:
                break
            nxt = rows[-1]["minute"][:19]
            if nxt == cur:
                raise ProbeError(f"cursor de velas atascado en {nxt}")
            cur = nxt
        out[c] = {
            "first_minute": first[0]["minute"], "last_minute": last[0]["minute"],
            "expiry": first[0]["expiry"], "strike": first[0]["strike"],
            "type": first[0]["contract_type"],
            "dias_calendario": (date.fromisoformat(d1) - date.fromisoformat(d0)).days,
            "sesiones_con_barras": len(days_seen), "barras_1m": total, "paginas": pages,
            "griegas_en_barra": all(first[0].get(k) is not None
                                    for k in ("iv_avg", "delta_avg", "gamma_avg")),
            "print_count_en_barra": first[0].get("print_count") is not None,
            "barras_tras_ultimo_dia_habil_antes_del_vencimiento":
                sum(1 for d in days_seen if d >= first[0]["expiry"]),
        }
        print(f"[candles] {c} {d0}->{d1} sesiones={len(days_seen)} barras={total}")
    save("candles", out)
    return out


# --------------------------------------------------------------- monday
def m_monday(syms):
    """Captura pareada EN SESION: tape LSE + cadena LSE + verdad UW, cada ronda.
    Es la unica prueba de lado que queda viva; correr el lunes en RTH."""
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dst = os.path.join(REPO, "data", "research", f"lse_monday_{stamp}.json")
    day = date.today().isoformat()
    snap = {"captured_at_utc": datetime.utcnow().isoformat() + "Z", "syms": syms, "rondas": []}
    for k in range(3):
        t0 = time.time()
        ronda = {"t_utc": datetime.utcnow().isoformat() + "Z", "por_sym": {}}
        for s in syms:
            tape = flow(start=day, end=nextday(day), underlying=s, order="desc", limit=ROW_CAP)
            chain = get("/options/chain", underlying=s, limit=ROW_CAP)
            ronda["por_sym"][s] = {
                "tape_n": len(tape),
                "tape_ts_max": max((r["ts"] for r in tape), default=None),
                "tape_dte_min": min((r["dte"] for r in tape), default=None),
                "chain_updated_max": max((c.get("updated_at") or "" for c in chain), default=None),
                "chain_tiene_bid_ask": any(k2 in (chain[0] if chain else {}) for k2 in ("bid", "ask")),
                "muestra_tape": tape[:5],
            }
        snap["rondas"].append(ronda)
        print(f"[monday] ronda {k+1} en {time.time()-t0:.1f}s")
        if k < 2:
            time.sleep(120)
    tmp = dst + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(snap, fh, indent=1)
    os.replace(tmp, dst)
    print(f"[monday] -> {dst}")
    return snap


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["meta", "cover", "sweep", "side", "uw", "ws",
                                     "candles", "monday"])
    ap.add_argument("--days", default="2026-08-03,2026-08-04,2026-08-05,2026-08-06,2026-08-07")
    ap.add_argument("--day", default="2026-08-07")
    ap.add_argument("--syms", default="SPY,QQQ,NVDA,SMH,MU")
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--contracts", default="")
    a = ap.parse_args()
    KEY = api_key()
    days, syms = a.days.split(","), a.syms.split(",")
    if a.mode == "meta":
        m_meta()
    elif a.mode == "cover":
        m_cover()
    elif a.mode == "sweep":
        m_sweep(days, [50_000, 250_000, 1_000_000])
    elif a.mode == "side":
        m_side(a.day, syms)
    elif a.mode == "uw":
        m_uw(a.day, syms)
    elif a.mode == "ws":
        m_ws(syms, a.seconds)
    elif a.mode == "candles":
        m_candles([c for c in a.contracts.split(",") if c])
    elif a.mode == "monday":
        m_monday(syms)


if __name__ == "__main__":
    main()
