#!/usr/bin/env python3
"""Barrido exhaustivo de la API REST de London Strategic Edge (vault).

Lote fuera de sesion: mide latencia, filas, bytes y profundidad real de cada
endpoint/dataset. Crudo -> data/research/lse_probe.json (escritura atomica).
"""
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "research" / "lse_probe.json"
CATALOG_CACHE = Path("/tmp/lse_catalog.json")

sys.path.insert(0, str(REPO / "venv-lse" / "lib" / "python3.9" / "site-packages"))


def load_key():
    k = os.environ.get("LSE_API_KEY")
    if k:
        return k
    env = REPO / "config" / "feeds.env"
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("LSE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"LSE_API_KEY ausente en env y en {env}")


API_KEY = load_key()

# --- shim de bytes: contamos lo que baja de verdad por cada llamada ---------
_real_urlopen = urllib.request.urlopen
_BYTES = {"total": 0, "last": 0}


class _CapturedResponse:
    def __init__(self, data, status, headers):
        self._data = data
        self.status = status
        self.headers = headers

    def read(self, *_a):
        d, self._data = self._data, b""
        return d

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _counting_urlopen(req, *a, **kw):
    resp = _real_urlopen(req, *a, **kw)
    data = resp.read()
    _BYTES["total"] += len(data)
    _BYTES["last"] = len(data)
    return _CapturedResponse(data, getattr(resp, "status", 200), resp.headers)


urllib.request.urlopen = _counting_urlopen

from lse import LSE, LSEError  # noqa: E402

VAULT = "https://api.londonstrategicedge.com/vault"
UA = "lse-data-sdk (+https://londonstrategicedge.com)"

CLIENT = LSE(api_key=API_KEY, timeout=120)
CALLS = []          # registro de cada llamada
_last_call_ts = [0.0]
MIN_GAP = 0.20      # 200 req/min = 3.3/s; nos quedamos en 5/s como techo duro


def _throttle():
    dt = time.time() - _last_call_ts[0]
    if dt < MIN_GAP:
        time.sleep(MIN_GAP - dt)
    _last_call_ts[0] = time.time()


def raw_get(path):
    """GET directo al vault (endpoints sin metodo en el SDK)."""
    _throttle()
    req = urllib.request.Request(VAULT + path, headers={"x-api-key": API_KEY, "User-Agent": UA})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read().decode())
    ms = (time.perf_counter() - t0) * 1000
    CALLS.append({"kind": "raw", "target": path, "ms": round(ms, 1),
                  "bytes": _BYTES["last"], "rows": len(body) if isinstance(body, list) else None,
                  "ok": True})
    return body


def probe(label, fn, *args, **kwargs):
    """Ejecuta una llamada del SDK midiendo latencia/bytes/filas. Nunca inventa
    un valor: si falla, se registra el error exacto y se devuelve None."""
    _throttle()
    _BYTES["last"] = 0
    t0 = time.perf_counter()
    try:
        rows = fn(*args, **kwargs)
        ms = (time.perf_counter() - t0) * 1000
        rec = {"kind": "sdk", "target": label, "ms": round(ms, 1), "bytes": _BYTES["last"],
               "rows": len(rows) if isinstance(rows, list) else 1, "ok": True,
               "cols": sorted(rows[0].keys()) if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None}
        CALLS.append(rec)
        return rows
    except LSEError as e:
        ms = (time.perf_counter() - t0) * 1000
        CALLS.append({"kind": "sdk", "target": label, "ms": round(ms, 1), "bytes": _BYTES["last"],
                      "rows": None, "ok": False, "status": e.status, "error": e.message[:300]})
        return None
    except Exception as e:  # noqa: BLE001 - se registra el tipo exacto, no se enmascara
        ms = (time.perf_counter() - t0) * 1000
        CALLS.append({"kind": "sdk", "target": label, "ms": round(ms, 1), "bytes": _BYTES["last"],
                      "rows": None, "ok": False, "status": None,
                      "error": f"{type(e).__name__}: {e}"[:300]})
        return None


def last_call():
    return CALLS[-1]


STEP = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400, "1w": 604800}


def parse_ts(v):
    if v is None:
        return None
    s = str(v).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = datetime.fromisoformat(s[:19])
        except ValueError:
            return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def shape(rows, tf, tkey="timestamp"):
    """Rango, huecos y hora-del-dia de una serie de barras. None si no hay filas."""
    if not rows:
        return None
    ts = sorted(t for t in (parse_ts(r.get(tkey) or r.get("ts") or r.get("date") or r.get("minute")) for r in rows) if t)
    if len(ts) < 2:
        return {"n": len(rows), "first": str(ts[0]) if ts else None, "last": str(ts[-1]) if ts else None}
    d = [(ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1)]
    exp = STEP.get(tf)
    med = statistics.median(d)
    big = sorted(d, reverse=True)[:3]
    out = {
        "n": len(rows),
        "first": ts[0].isoformat(), "last": ts[-1].isoformat(),
        "span_days": round((ts[-1] - ts[0]).total_seconds() / 86400, 3),
        "step_median_s": med,
        "gaps_max_s": big,
        "tod_utc_min": min(t.strftime("%H:%M") for t in ts),
        "tod_utc_max": max(t.strftime("%H:%M") for t in ts),
    }
    if exp:
        holes = [x for x in d if x > exp * 1.5]
        out["n_steps"] = len(d)
        out["n_gaps_gt_step"] = len(holes)
        # hueco INTRA-sesion: mayor que el paso pero menor que una pausa nocturna
        limit = 4 * 3600 if exp < 86400 else 4 * 86400
        out["n_gaps_intrasession"] = len([x for x in holes if x <= limit])
        out["bars_expected_if_continuous"] = int((ts[-1] - ts[0]).total_seconds() // exp) + 1
        out["fill_pct_vs_continuous"] = round(100.0 * len(ts) / out["bars_expected_if_continuous"], 2)
    return out


def pick3(rows):
    """Simbolo con mas ticks, uno mediano y el mas raro (con ticks>0)."""
    rs = sorted([r for r in rows if (r.get("ticks") or 0) > 0], key=lambda r: -(r["ticks"] or 0))
    if not rs:
        return []
    idx = {0, len(rs) // 2, len(rs) - 1}
    return [rs[i] for i in sorted(idx)]


def main():
    result = {"probe_utc": datetime.now(timezone.utc).isoformat(), "sdk_version": None}
    import lse
    result["sdk_version"] = lse.__version__

    print("== usage antes ==", flush=True)
    result["usage_before"] = raw_get("/usage")
    print(json.dumps(result["usage_before"]), flush=True)

    result["meta"] = raw_get("/meta")
    result["reference_meta"] = raw_get("/reference")

    # catalogo por el SDK (mide el coste real de catalog(); queda cacheado)
    cat = probe("catalog()", CLIENT.catalog)
    result["catalog_call"] = last_call()
    if cat is None:
        raise SystemExit("catalog() fallo; sin catalogo no hay barrido")
    CATALOG_CACHE.write_text(json.dumps(CLIENT._vault_catalog_cache))

    raw_cat = CLIENT._vault_catalog_cache
    by_ds = defaultdict(list)
    for r in raw_cat:
        by_ds[r["dataset"]].append(r)
    result["dataset_counts"] = {k: len(v) for k, v in sorted(by_ds.items())}

    access = result["meta"]["access"]
    datasets = sorted(by_ds)

    # ---------------- 2. candles/series por dataset ----------------------
    ds_out = {}
    for ds in datasets:
        caps = access.get(ds, [])
        picks = pick3(by_ds[ds])
        entry = {"caps_declared": caps, "n_symbols": len(by_ds[ds]), "samples": []}
        for p in picks:
            sym = p["symbol"]
            s = {"symbol": sym, "name": p.get("name"), "catalog_ticks": p.get("ticks"),
                 "catalog_first_tick": p.get("first_tick"), "catalog_last_tick": p.get("last_tick"),
                 "candles": {}, "series": None, "cross_probe": None}
            if "candles" in caps:
                for tf in ("1m", "5m", "1h", "1d"):
                    rows = probe(f"candles({sym},{tf},desc,5000)", CLIENT.candles, sym, tf,
                                 order="desc", limit=5000)
                    c = dict(last_call())
                    c["shape"] = shape(rows, tf) if rows else None
                    # profundidad real: la barra mas antigua servida
                    old = probe(f"candles({sym},{tf},asc,1)", CLIENT.candles, sym, tf,
                                order="asc", limit=1)
                    c["oldest_call"] = {k: last_call().get(k) for k in ("ms", "ok", "rows", "status", "error")}
                    c["oldest_bar"] = (old[0].get("timestamp") if old else None)
                    s["candles"][tf] = c
                # cross: un dataset de velas NO deberia servir series()
                probe(f"series({sym}) [cross]", CLIENT.series, sym, dataset=ds, limit=3)
                s["cross_probe"] = dict(last_call())
            elif "series" in caps:
                rows = probe(f"series({sym},{ds},desc,5000)", CLIENT.series, sym, dataset=ds,
                             order="desc", limit=5000)
                sc = dict(last_call())
                sc["shape"] = shape(rows, "1d", tkey="date") if rows else None
                sc["sample_row"] = rows[0] if rows else None
                old = probe(f"series({sym},{ds},asc,1)", CLIENT.series, sym, dataset=ds,
                            order="asc", limit=1)
                sc["oldest_row"] = old[0] if old else None
                s["series"] = sc
                # cross: pedir velas a un dataset de series
                probe(f"candles({sym},1d) [cross]", CLIENT.candles, sym, "1d", limit=3)
                s["cross_probe"] = dict(last_call())
            elif "options" in caps:
                s["note"] = "dataset options: se prueba en la seccion de opciones"
            entry["samples"].append(s)
        ds_out[ds] = entry
        print(f"-- {ds}: {len(picks)} muestras, calls={len(CALLS)}", flush=True)
        _save(result | {"datasets": ds_out})

    result["datasets"] = ds_out

    # ---------------- 3. endpoints de referencia -------------------------
    ref = {}

    def ref_probe(name, label, fn, *a, **kw):
        rows = probe(label, fn, *a, **kw)
        rec = dict(last_call())
        rec["shape"] = shape(rows, "1d", tkey="date") if rows else None
        rec["sample_row"] = rows[0] if rows else None
        ref.setdefault(name, []).append(rec)
        return rows

    ref_probe("economic_calendar", "economic_calendar(US,2026)", CLIENT.economic_calendar,
              region="US", start="2026-01-01", limit=5000)
    ref_probe("economic_calendar", "economic_calendar(EU+GB,released,desc)", CLIENT.economic_calendar,
              region=["EU", "GB"], released_only=True, order="desc", limit=500)

    ref_probe("insider_trades", "insider_trades(NVDA)", CLIENT.insider_trades, "NVDA", limit=500)
    ref_probe("insider_trades", "insider_trades(all,P-Purchase,2026)", CLIENT.insider_trades,
              type="P-Purchase", start="2026-01-01", limit=500)

    ref_probe("dividends", "dividends(AAPL)", CLIENT.dividends, "AAPL", limit=500)
    ref_probe("dividends", "dividends(all,2026)", CLIENT.dividends, start="2026-01-01", limit=500)

    ref_probe("splits", "splits(NVDA)", CLIENT.splits, "NVDA", limit=500)
    ref_probe("splits", "splits(all,2020+)", CLIENT.splits, start="2020-01-01", limit=500)

    econ_syms = [r["symbol"] for r in by_ds["economics"] if (r.get("ticks") or 0) > 200][:1]
    ref_probe("series", "series(fdtr)", CLIENT.series, "fdtr", limit=5000)
    if econ_syms:
        ref_probe("series", f"series({econ_syms[0]})", CLIENT.series, econ_syms[0], limit=5000)
    ref_probe("series", "series(US10Y)", CLIENT.series, "US10Y", limit=5000)

    cot_all = ref_probe("cot", "cot(all,desc,50)", CLIENT.cot, order="desc", limit=50)
    cot_sym = cot_all[0].get("symbol") if cot_all else None
    if cot_sym:
        ref_probe("cot", f"cot({cot_sym})", CLIENT.cot, cot_sym, limit=5000)
    else:
        ref_probe("cot", "cot(GOLD)", CLIENT.cot, "GOLD", limit=100)

    ref_probe("financial_reports", "financial_reports(NVDA,income)", CLIENT.financial_reports,
              "NVDA", report_type="income", limit=50)
    ref_probe("financial_reports", "financial_reports(AAPL,balance,FY)", CLIENT.financial_reports,
              "AAPL", report_type="balance", period="FY", limit=50)

    ref_probe("company_profiles", "company_profiles(NVDA)", CLIENT.company_profiles, "NVDA")
    ref_probe("company_profiles", "company_profiles(all,limit=5000)", CLIENT.company_profiles, limit=5000)

    ref_probe("fundamentals", "fundamentals(NVDA)", CLIENT.fundamentals, "NVDA")
    ref_probe("fundamentals", "fundamentals(all,limit=5000)", CLIENT.fundamentals, limit=5000)

    ref_probe("bond_yields", "bond_yields(US10Y)", CLIENT.bond_yields, "US10Y", limit=5000)
    ref_probe("bond_yields", "bond_yields(DE10Y,2020+)", CLIENT.bond_yields, "DE10Y",
              start="2020-01-01", limit=5000)

    ref_probe("catalog", "catalog(cached)", CLIENT.catalog)
    ref_probe("catalog", "catalog('crypto')", CLIENT.catalog, "crypto")
    ref_probe("options_underlyings", "options_underlyings()", CLIENT.options_underlyings)
    result["reference"] = ref
    _save(result)

    # ---------------- 4. opciones ----------------------------------------
    opt = {}
    opt_syms = ["SPY", "QQQ", "NVDA", "NRIM"]
    for sym in opt_syms:
        e = {}
        rows = probe(f"options({sym})", CLIENT.options, sym, limit=5000)
        e["chain"] = dict(last_call())
        e["chain"]["sample_row"] = rows[0] if rows else None
        if rows:
            exps = sorted({r.get("expiry") for r in rows if r.get("expiry")})
            e["chain"]["n_expiries"] = len(exps)
            e["chain"]["expiries_head"] = exps[:6]
            e["chain"]["expiries_tail"] = exps[-3:]
            e["chain"]["n_with_greeks"] = sum(1 for r in rows if r.get("delta") is not None)
            e["chain"]["n_with_oi"] = sum(1 for r in rows if r.get("open_interest") not in (None,))
        f = probe(f"options_flow({sym},5000)", CLIENT.options_flow, sym, limit=5000)
        e["flow"] = dict(last_call())
        e["flow"]["sample_row"] = f[0] if f else None
        e["flow"]["shape"] = shape(f, None, tkey="ts") if f else None
        osi = None
        if f:
            osi = f[0].get("ticker")
        if not osi and rows:
            best = max(rows, key=lambda r: (r.get("volume_today") or r.get("volume") or 0))
            osi = best.get("ticker")
        if osi:
            oc = probe(f"option_candles({osi},asc,5000)", CLIENT.option_candles, osi,
                       order="asc", limit=5000)
            e["candles"] = dict(last_call())
            e["candles"]["contract"] = osi
            e["candles"]["sample_row"] = oc[0] if oc else None
            e["candles"]["shape"] = shape(oc, "1m", tkey="minute") if oc else None
        else:
            e["candles"] = {"ok": False, "error": "sin OSI: ni flow ni chain devolvieron ticker"}
        opt[sym] = e
        print(f"-- options {sym}: calls={len(CALLS)}", flush=True)
        _save(result | {"options": opt})

    # barrido global de la cinta sin underlying
    sw = probe("options_flow(global,min_premium=250k)", CLIENT.options_flow,
               min_premium=250000, limit=5000)
    opt["_global_sweep"] = dict(last_call())
    if sw:
        opt["_global_sweep"]["n_underlyings"] = len({r.get("underlying") for r in sw})
        opt["_global_sweep"]["shape"] = shape(sw, None, tkey="ts")
        opt["_global_sweep"]["sample_row"] = sw[0]
    sw2 = probe("options_flow(puts,min_premium=250k,max_dte=7)", CLIENT.options_flow,
                type="put", min_premium=250000, max_dte=7, limit=1000)
    opt["_global_puts"] = dict(last_call())
    if sw2:
        opt["_global_puts"]["n_underlyings"] = len({r.get("underlying") for r in sw2})
    # profundidad historica de la cinta: cuanto atras llega options_flow
    old = probe("options_flow(SPY,asc,1) [profundidad]", CLIENT.options_flow, "SPY",
                order="asc", limit=1)
    opt["_flow_depth"] = {"call": dict(last_call()), "oldest_row": old[0] if old else None}
    result["options"] = opt
    _save(result)

    # ---------------- 5. sondas de error ---------------------------------
    err = []

    def edge(label, fn, *a, **kw):
        probe(label, fn, *a, **kw)
        err.append(dict(last_call()))

    edge("candles(SPY,2m) tf invalido", CLIENT.candles, "SPY", "2m", limit=5)
    edge("candles(NO_EXISTE,1d)", CLIENT.candles, "ZZZZNOPE", "1d", limit=5)
    edge("candles(SPY,1d,limit=99999)", CLIENT.candles, "SPY", "1d", limit=99999)
    edge("candles(SPY,1s,1 dia)", CLIENT.candles, "SPY", "1s", start="2026-08-06",
         end="2026-08-07", limit=5000)
    edge("candles(SPY,1w)", CLIENT.candles, "SPY", "1w", limit=5000)
    edge("candles(SPY,1mo)", CLIENT.candles, "SPY", "1mo", limit=5000)
    edge("options(ZZZZNOPE)", CLIENT.options, "ZZZZNOPE", limit=5)
    edge("option_candles(basura)", CLIENT.option_candles, "NO-ES-OSI")
    edge("series(SPY) sin dataset", CLIENT.series, "SPY", limit=5)
    edge("get('x_options_chain') legacy", CLIENT.get, "x_options_chain", underlying="eq.SPY", limit="5")
    edge("get('tabla_muerta') legacy", CLIENT.get, "tabla_muerta")
    edge("candles(SPY,1m) sesion viva HOY", CLIENT.candles, "SPY", "1m", order="desc", limit=5)
    edge("candles(BTC/USD,1m) 24/7 HOY", CLIENT.candles, "BTC/USD", "1m", order="desc", limit=5)
    result["edge_cases"] = err

    print("== usage despues ==", flush=True)
    result["usage_after"] = raw_get("/usage")
    result["calls"] = CALLS
    result["bytes_measured_client"] = _BYTES["total"]
    result["summary"] = summarize(result)
    _save(result)
    print(json.dumps(result["summary"], indent=1))


def summarize(res):
    ok = [c for c in CALLS if c.get("ok")]
    bad = [c for c in CALLS if not c.get("ok")]
    ub, ua = res.get("usage_before", {}), res.get("usage_after", {})
    lat = sorted(c["ms"] for c in ok)
    return {
        "n_calls": len(CALLS), "n_ok": len(ok), "n_fail": len(bad),
        "latency_ms_p50": lat[len(lat) // 2] if lat else None,
        "latency_ms_p90": lat[int(len(lat) * 0.9)] if lat else None,
        "latency_ms_max": lat[-1] if lat else None,
        "bytes_client_measured": _BYTES["total"],
        "vault_bytes_week_before": ub.get("bytes_used_week"),
        "vault_bytes_week_after": ua.get("bytes_used_week"),
        "vault_bytes_charged": (ua.get("bytes_used_week", 0) - ub.get("bytes_used_week", 0)),
        "vault_week_cap": ua.get("bytes_cap_week"),
        "pct_of_week_cap": round(100.0 * (ua.get("bytes_used_week", 0) - ub.get("bytes_used_week", 0))
                                 / ua.get("bytes_cap_week", 1), 5),
        "failures": [{"target": c["target"], "status": c.get("status"), "error": c.get("error")} for c in bad],
    }


def _save(obj):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str))
    os.replace(tmp, OUT)


# ======================= FASE 2: verificacion + huecos =======================
# La fase 1 midio superficie. La fase 2 (a) VERIFICA los tres titulares
# (profundidad 1m, cadena sin OI, cinta de 6 semanas) y (b) cubre lo que la
# fase 1 no toco: export Parquet, paginacion, Corea, concurrencia.

def _day_bounds(day):
    return f"{day}T00:00:00", f"{day}T23:59:59"


def p2_deep_history(out):
    """Titular a verificar: hay velas 1m de 2003-2010. Si son reales, el 1m
    de un dia debe RECONSTRUIR la vela 1d del mismo dia."""
    checks = []
    for sym, days in (("NVDA", ["2010-05-06", "2015-08-24", "2020-03-16", "2026-08-07"]),
                      ("SPY", ["2010-05-06", "2026-08-07"])):
        for day in days:
            s, e = _day_bounds(day)
            m1 = probe(f"candles({sym},1m,{day})", CLIENT.candles, sym, "1m",
                       start=s, end=e, limit=5000)
            c1m = dict(last_call())
            d1 = probe(f"candles({sym},1d,{day})", CLIENT.candles, sym, "1d",
                       start=s, end=e, limit=5)
            rec = {"symbol": sym, "day": day, "n_1m": len(m1) if m1 else 0,
                   "ms_1m": c1m.get("ms"), "bar_1d": d1[0] if d1 else None}
            if m1:
                ts = sorted(m1, key=lambda r: str(r.get("timestamp")))
                vol = sum(float(r.get("volume") or 0) for r in ts)
                rec["agg_1m"] = {
                    "first_ts": ts[0].get("timestamp"), "last_ts": ts[-1].get("timestamp"),
                    "open": ts[0].get("open"), "close": ts[-1].get("close"),
                    "high": max(float(r["high"]) for r in ts),
                    "low": min(float(r["low"]) for r in ts),
                    "volume": vol,
                    "n_zero_volume": sum(1 for r in ts if not float(r.get("volume") or 0)),
                }
                if d1:
                    b = d1[0]
                    rec["match"] = {
                        "open": (b.get("open"), ts[0].get("open")),
                        "close": (b.get("close"), ts[-1].get("close")),
                        "high": (b.get("high"), rec["agg_1m"]["high"]),
                        "low": (b.get("low"), rec["agg_1m"]["low"]),
                        "volume_1d_over_1m": (round(float(b.get("volume") or 0) / vol, 4)
                                              if vol else None),
                    }
            checks.append(rec)
    out["p2_deep_history"] = checks


def p2_paging(out):
    """Como se pasa del techo de 5000 filas: ventanas start/end encadenadas."""
    pages, cur, guard = [], "2026-08-03T00:00:00", 0
    total = 0
    while guard < 6:
        rows = probe(f"candles(NVDA,1m,page{guard})", CLIENT.candles, "NVDA", "1m",
                     start=cur, end="2026-08-08T00:00:00", order="asc", limit=5000)
        if rows is None:
            break
        pages.append({"start": cur, "rows": len(rows),
                      "first": rows[0].get("timestamp") if rows else None,
                      "last": rows[-1].get("timestamp") if rows else None,
                      "ms": last_call().get("ms"), "bytes": last_call().get("bytes")})
        total += len(rows)
        if len(rows) < 5000:
            break
        last = parse_ts(rows[-1]["timestamp"])
        cur = (last.replace(tzinfo=None)).isoformat()
        guard += 1
    out["p2_paging"] = {"pages": pages, "rows_total": total,
                        "note": "cursor = timestamp de la ultima fila; el solape de 1 fila se descarta al unir"}


def p2_chain_fields(out):
    """Titular a verificar: la cadena NO trae open_interest ni bid/ask."""
    res = {}
    for label, kw in (("SPY_dte0_9", {"min_dte": 0, "max_dte": 9}),
                      ("SPY_completa", {}),
                      ("NVDA_dte0_9", {"min_dte": 0, "max_dte": 9})):
        sym = label.split("_")[0]
        rows = probe(f"options({sym},{label})", CLIENT.options, sym, limit=5000, **kw)
        rec = dict(last_call())
        if rows:
            keys = set()
            for r in rows:
                keys |= set(r.keys())
            upd = sorted(str(r.get("updated_at")) for r in rows if r.get("updated_at"))
            exps = sorted({r.get("expiry") for r in rows if r.get("expiry")})
            rec["keys_union"] = sorted(keys)
            rec["has_open_interest"] = "open_interest" in keys
            rec["has_bid"] = "bid" in keys
            rec["has_ask"] = "ask" in keys
            rec["n_expiries"] = len(exps)
            rec["expiries"] = exps[:8] + (["..."] + exps[-3:] if len(exps) > 11 else [])
            rec["updated_at_min"] = upd[0] if upd else None
            rec["updated_at_max"] = upd[-1] if upd else None
            rec["n_greeks"] = sum(1 for r in rows if r.get("delta") is not None)
            rec["n_iv"] = sum(1 for r in rows if r.get("iv") is not None)
        res[label] = rec
    out["p2_chain_fields"] = res


def p2_flow_rate(out):
    """Cuantos prints por minuto y por tanto cuantas llamadas cuesta una sesion."""
    res = {}
    for sym in ("SPY", "NVDA"):
        rows = probe(f"options_flow({sym},1 min)", CLIENT.options_flow, sym,
                     start="2026-08-07T19:00:00", end="2026-08-07T19:01:00",
                     order="asc", limit=5000)
        res[sym] = {"call": dict(last_call()), "n_prints_1min": len(rows) if rows else 0,
                    "capped": bool(rows and len(rows) == 5000)}
    out["p2_flow_rate"] = res


def p2_export(out):
    """El unico camino por encima de 5000 filas: job async -> Parquet."""
    dest = str(REPO / "data" / "research" / "lse_export")
    jobs = []

    def one(label, **kw):
        t0 = time.perf_counter()
        try:
            path = CLIENT.history(dest=dest, dataframe=False, **kw)
            ms = (time.perf_counter() - t0) * 1000
            rec = {"label": label, "ok": True, "ms": round(ms, 1), "path": path,
                   "bytes": os.path.getsize(path)}
            try:
                import pyarrow.parquet as pq
                md = pq.read_metadata(path)
                rec["rows"] = md.num_rows
                rec["cols"] = [c for c in pq.read_schema(path).names]
            except ImportError:
                rec["rows"] = None
                rec["cols"] = "pyarrow ausente en este interprete"
        except Exception as e:  # noqa: BLE001 - se registra tal cual, no se enmascara
            ms = (time.perf_counter() - t0) * 1000
            rec = {"label": label, "ok": False, "ms": round(ms, 1),
                   "error": f"{type(e).__name__}: {e}"[:300]}
        jobs.append(rec)
        print("   export", label, rec.get("ok"), rec.get("rows"), rec.get("error", ""), flush=True)

    one("history(NVDA,1d) completo >5000", symbol="NVDA", timeframe="1d")
    one("history(NVDA,1m,1 dia)", symbol="NVDA", timeframe="1m",
        start="2026-08-07", end="2026-08-08")
    one("history(NVDA,options,1m,1 dia)", symbol="NVDA", dataset="options",
        timeframe="1m", start="2026-08-07", end="2026-08-08")
    out["p2_export"] = {"jobs": jobs, "usage": raw_get("/usage")}


def p2_option_candles_tf(out):
    """/meta declara options_timeframes 1m..1mo, pero option_candles() del SDK no
    tiene parametro timeframe. Se prueba el endpoint crudo."""
    res = {}
    osi = "QQQ260810P00722000"
    for tf in ("1m", "1d", "1h"):
        try:
            body = raw_get(f"/options/candles?ticker={osi}&timeframe={tf}&limit=10")
            res[tf] = {"ok": True, "rows": len(body) if isinstance(body, list) else None,
                       "sample": body[0] if isinstance(body, list) and body else None}
        except urllib.error.HTTPError as e:
            res[tf] = {"ok": False, "status": e.code,
                       "error": e.read().decode("utf-8", "replace")[:200]}
        except OSError as e:
            res[tf] = {"ok": False, "status": 0, "error": str(e)[:200]}
    out["p2_option_candles_tf"] = res


def p2_house_symbols(out):
    """Los simbolos que esta casa usa de verdad: flota + Corea + indices."""
    res = {}
    for sym in ("005930.KS", "000660.KS"):
        rows = probe(f"candles({sym},1m,desc)", CLIENT.candles, sym, "1m", order="desc", limit=5000)
        rec = dict(last_call())
        rec["shape"] = shape(rows, "1m") if rows else None
        old = probe(f"candles({sym},1m,asc,1)", CLIENT.candles, sym, "1m", order="asc", limit=1)
        rec["oldest_bar"] = old[0].get("timestamp") if old else None
        d = probe(f"candles({sym},1d,asc,1)", CLIENT.candles, sym, "1d", order="asc", limit=1)
        rec["oldest_1d"] = d[0].get("timestamp") if d else None
        res[sym] = rec
    ausentes = {}
    for sym in ("TSM", "XLK", "EWY", "DRAM", "SKHY", "SPX", "XSP", "NDX", "VIX"):
        probe(f"candles({sym},1d) [ausente?]", CLIENT.candles, sym, "1d", limit=2)
        c = last_call()
        ausentes[sym] = {"ok": c.get("ok"), "rows": c.get("rows"),
                         "status": c.get("status"), "error": c.get("error")}
    res["_ausentes"] = ausentes
    out["p2_house_symbols"] = res


def p2_concurrency(out):
    """vault_concurrency=2: se comprueba disparando 4 a la vez."""
    import threading
    results = []
    lock = threading.Lock()

    def hit(i):
        t0 = time.perf_counter()
        req = urllib.request.Request(
            VAULT + "/candles?symbol=BTC/USD&timeframe=1d&limit=5",
            headers={"x-api-key": API_KEY, "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            rec = {"i": i, "ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1),
                   "bytes": len(body)}
        except urllib.error.HTTPError as e:
            rec = {"i": i, "ok": False, "status": e.code,
                   "ms": round((time.perf_counter() - t0) * 1000, 1),
                   "error": e.read().decode("utf-8", "replace")[:150]}
        except OSError as e:
            rec = {"i": i, "ok": False, "status": 0, "error": str(e)[:150]}
        with lock:
            results.append(rec)

    ths = [threading.Thread(target=hit, args=(i,)) for i in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    out["p2_concurrency"] = sorted(results, key=lambda r: r["i"])


def phase2():
    """Se fusiona sobre el JSON de la fase 1; no se destruye nada."""
    if not OUT.exists():
        raise SystemExit(f"falta {OUT}: la fase 1 no ha corrido")
    result = json.loads(OUT.read_text())
    result["p2_utc"] = datetime.now(timezone.utc).isoformat()
    result["p2_usage_before"] = raw_get("/usage")
    print("== fase2 usage antes ==", json.dumps(result["p2_usage_before"]), flush=True)

    for name, fn in (("deep_history", p2_deep_history), ("paging", p2_paging),
                     ("chain_fields", p2_chain_fields), ("flow_rate", p2_flow_rate),
                     ("option_candles_tf", p2_option_candles_tf),
                     ("house_symbols", p2_house_symbols), ("concurrency", p2_concurrency),
                     ("export", p2_export)):
        print(f"-- fase2 {name} ...", flush=True)
        fn(result)
        _save(result)

    result["p2_usage_after"] = raw_get("/usage")
    result["p2_calls"] = CALLS
    ub, ua = result["p2_usage_before"], result["p2_usage_after"]
    ok = [c for c in CALLS if c.get("ok")]
    lat = sorted(c["ms"] for c in ok)
    result["p2_summary"] = {
        "n_calls": len(CALLS), "n_ok": len(ok), "n_fail": len(CALLS) - len(ok),
        "latency_ms_p50": lat[len(lat) // 2] if lat else None,
        "latency_ms_max": lat[-1] if lat else None,
        "bytes_client_measured": _BYTES["total"],
        "vault_bytes_charged": ua["bytes_used_week"] - ub["bytes_used_week"],
        "pct_of_week_cap": round(100.0 * (ua["bytes_used_week"] - ub["bytes_used_week"])
                                 / ua["bytes_cap_week"], 5),
        "week_used_total_pct": round(100.0 * ua["bytes_used_week"] / ua["bytes_cap_week"], 5),
        "exports_this_hour": ua.get("exports_this_hour"),
        "failures": [{"target": c["target"], "status": c.get("status"), "error": c.get("error")}
                     for c in CALLS if not c.get("ok")],
    }
    _save(result)
    print(json.dumps(result["p2_summary"], indent=1))


def phase2b():
    """Dos comprobaciones que la fase 2 dejo abiertas:
    (1) la cadena viva de SPY solo se alcanza fijando expiry explicito?
    (2) los dos simbolos coreanos traen precios distintos o son el mismo dato?"""
    if not OUT.exists():
        raise SystemExit(f"falta {OUT}")
    result = json.loads(OUT.read_text())
    out = {}

    chain = {}
    for exp in ("2026-08-14", "2026-08-21", "2026-07-02"):
        rows = probe(f"options(SPY,expiry={exp})", CLIENT.options, "SPY", expiry=exp, limit=5000)
        rec = dict(last_call())
        if rows:
            upd = sorted(str(r.get("updated_at")) for r in rows if r.get("updated_at"))
            rec["updated_at_min"], rec["updated_at_max"] = upd[0], upd[-1]
            rec["dte_values"] = sorted({r.get("dte") for r in rows})[:5]
            rec["n_greeks"] = sum(1 for r in rows if r.get("delta") is not None)
            rec["underlying_price_min"] = min(r["underlying_price"] for r in rows if r.get("underlying_price"))
            rec["underlying_price_max"] = max(r["underlying_price"] for r in rows if r.get("underlying_price"))
            rec["sample"] = rows[0]
        chain[exp] = rec
    out["spy_chain_by_expiry"] = chain

    kr = {}
    for sym in ("005930.KS", "000660.KS"):
        rows = probe(f"candles({sym},1m,desc,5)", CLIENT.candles, sym, "1m", order="desc", limit=5)
        kr[sym] = {"call": dict(last_call()), "rows": rows}
    a = kr["005930.KS"]["rows"] or []
    b = kr["000660.KS"]["rows"] or []
    kr["_identicos"] = bool(a and b and [r.get("close") for r in a] == [r.get("close") for r in b])
    out["korea_distintos"] = kr

    result["p2b"] = out
    result["p2b_usage"] = raw_get("/usage")
    _save(result)
    print(json.dumps({k: (v if k != "korea_distintos" else {"identicos": v["_identicos"]})
                      for k, v in out.items()}, indent=1, default=str)[:2500])
    print("KR closes A:", [r.get("close") for r in a], " B:", [r.get("close") for r in b])


if __name__ == "__main__":
    if "--phase2" in sys.argv:
        phase2()
    elif "--phase2b" in sys.argv:
        phase2b()
    else:
        main()
