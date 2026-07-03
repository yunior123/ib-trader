#!/usr/bin/env python3
"""uw_endpoint_probe.py — RECONOCIMIENTO medido de la API de Unusual Whales.

Manda 1 request por endpoint, guarda status HTTP, latencia de red, cupo diario leido de
las cabeceras, la FORMA REAL de la respuesta (campos + tipos) y un ejemplo recortado.
No interpreta, no puntua, no habla: es un mapa del terreno, no una señal.

  ./venv/bin/python scripts/uw_endpoint_probe.py --sym SPY --out /tmp/uw_probe.json
  ./venv/bin/python scripts/uw_endpoint_probe.py --only market_tide flow_alerts_global

NUNCA imprime el token (ni entero ni troceado). Un 401/403/404 es INFORMACION y se
reporta con su codigo: jamas se convierte en {} ni en 0 (regla de la casa: fail-loud).
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from uw_premium import token  # noqa: E402  (mismo lector de credencial, no se duplica)

BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (recon senal-solamente)"
TIMEOUT_S = 25
PAUSE_S = 0.4

# nombre -> plantilla de path. {sym} y {date} se sustituyen; el resto son globales.
ENDPOINTS = {
    # --- flujo de opciones ---
    "flow_alerts_global":     "/api/option-trades/flow-alerts?limit=5",
    "flow_alerts_sym":        "/api/stock/{sym}/flow-alerts?limit=5",
    "full_tape":              "/api/option-trades/full-tape/{date}",
    "flow_per_strike":        "/api/stock/{sym}/flow-per-strike",
    "flow_per_expiry":        "/api/stock/{sym}/flow-per-expiry",
    "flow_recent":            "/api/stock/{sym}/flow-recent?limit=5",
    "option_contracts":       "/api/stock/{sym}/option-contracts?limit=5",
    "net_prem_ticks":         "/api/stock/{sym}/net-prem-ticks",
    "option_stock_price_lvl": "/api/stock/{sym}/option/stock-price-levels",
    "oi_per_strike":          "/api/stock/{sym}/oi-per-strike",
    "oi_per_expiry":          "/api/stock/{sym}/oi-per-expiry",
    "oi_change":              "/api/stock/{sym}/oi-change",
    "stock_state":            "/api/stock/{sym}/stock-state",
    "stock_volume_price_lvl": "/api/stock/{sym}/stock-volume-price-levels",
    "atm_chains":             "/api/stock/{sym}/atm-chains?expirations[]={expiry}",
    # --- exposicion de dealer ---
    "greek_exposure":         "/api/stock/{sym}/greek-exposure",
    "gex_strike":             "/api/stock/{sym}/greek-exposure/strike",
    "gex_expiry":             "/api/stock/{sym}/greek-exposure/expiry",
    "gex_strike_expiry":      "/api/stock/{sym}/greek-exposure/strike-expiry?expiry={expiry}",
    "greek_flow":             "/api/stock/{sym}/greek-flow",
    "spot_exposures":         "/api/stock/{sym}/spot-exposures",
    "spot_exposures_strike":  "/api/stock/{sym}/spot-exposures/strike",
    "spot_exposures_expiry":  "/api/stock/{sym}/spot-exposures/expiry-strike/{expiry}",
    "max_pain":               "/api/stock/{sym}/max-pain",
    "interpolated_iv":        "/api/stock/{sym}/interpolated-iv",
    # --- volatilidad ---
    "vol_term_structure":     "/api/stock/{sym}/volatility/term-structure",
    "vol_realized":           "/api/stock/{sym}/volatility/realized",
    "vol_stats":              "/api/stock/{sym}/volatility/stats",
    "iv_rank":                "/api/stock/{sym}/iv-rank",
    # --- mercado / sectores ---
    "market_tide":            "/api/market/market-tide",
    "market_oi_change":       "/api/market/oi-change",
    "sector_etfs":            "/api/market/sector-etfs",
    "etf_tide":               "/api/market/{sector}/etf-tide",
    "market_correlations":    "/api/market/correlations",
    "market_economic_cal":    "/api/market/economic-calendar",
    "market_fda_cal":         "/api/market/fda-calendar",
    "market_spike":           "/api/market/spike",
    "market_total_options":   "/api/market/total-options-volume",
    "market_sector_tide":     "/api/market/sector-tide",
    "market_top_net_impact":  "/api/market/top-net-impact",
    "market_oi_rank":         "/api/market/oi-change",
    "market_insider_buy_sell": "/api/market/insider-buy-sells",
    # --- dark pool ---
    "darkpool_recent":        "/api/darkpool/recent?limit=5",
    "darkpool_sym":           "/api/darkpool/{sym}?limit=5",
    # --- screeners ---
    "screener_option_contracts": "/api/screener/option-contracts?limit=5",
    "screener_stocks":        "/api/screener/stocks?limit=5",
    "screener_analysts":      "/api/screener/analysts?limit=5",
    # --- etf ---
    "etf_exposure":           "/api/etfs/{sym}/exposure",
    "etf_holdings":           "/api/etfs/{sym}/holdings",
    "etf_inout":              "/api/etfs/{sym}/in-outflow",
    "etf_info":               "/api/etfs/{sym}/info",
    "etf_weights":            "/api/etfs/{sym}/weights",
    # --- eventos / posicionamiento ---
    "earnings_afterhours":    "/api/earnings/afterhours",
    "earnings_premarket":     "/api/earnings/premarket",
    "earnings_sym":           "/api/earnings/{sym}",
    "insider_transactions":   "/api/insider/transactions?limit=5",
    "insider_sector_flow":    "/api/insider/{sym}/ticker-flow",
    "congress_recent":        "/api/congress/recent-trades?limit=5",
    "congress_late":          "/api/congress/late-reports?limit=5",
    "congress_trader":        "/api/congress/congress-trader?limit=5",
    "institution_list":       "/api/institutions?limit=5",
    "shorts_data":            "/api/shorts/{sym}/data",
    "shorts_ftds":            "/api/shorts/{sym}/ftds",
    "news_headlines":         "/api/news/headlines?limit=5",
    "alerts_triggered":       "/api/alerts?limit=5",
    "alerts_config":          "/api/alerts/configuration",
    "socket":                 "/api/socket",
    "api_docs":               "/api/docs",
}

# los que valen la pena en un sondeo de FLUJO (por si se quiere abreviar)
FLOW_SET = ["flow_alerts_global", "flow_alerts_sym", "net_prem_ticks", "market_tide",
            "market_oi_change", "gex_strike", "spot_exposures", "darkpool_recent",
            "screener_option_contracts", "alerts_triggered", "socket"]

# los 9 del paso 2 de docs/UW-FLOW-RECON-2026-08-04.md §4: los unicos con sello intradia,
# o sea los unicos cuya latencia se puede medir de verdad con el mercado abierto.
RTH_SET = ["net_prem_ticks", "greek_flow", "spot_exposures", "market_tide", "etf_tide",
           "flow_alerts_global", "flow_alerts_sym", "flow_per_strike", "stock_state"]
REALTIME_S = 60.0   # mismo umbral que scripts/uw_latency_probe.py: 1 cubo de tape


def shape(obj, depth=0, max_depth=3):
    """Resumen de tipos: {campo: tipo} en vez del payload entero. Listas -> [tipo x N]."""
    if depth > max_depth:
        return "..."
    if isinstance(obj, dict):
        return {k: shape(v, depth + 1, max_depth) for k, v in obj.items()}
    if isinstance(obj, list):
        if not obj:
            return "[] (vacia)"
        return [shape(obj[0], depth + 1, max_depth), f"x{len(obj)}"]
    if obj is None:
        return "null"
    return type(obj).__name__


def trim(obj, n=2):
    """Ejemplo recortado: primeras n filas de cada lista, resto elidido."""
    if isinstance(obj, dict):
        return {k: trim(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        head = [trim(x, n) for x in obj[:n]]
        return head + ([f"... +{len(obj) - n} filas"] if len(obj) > n else [])
    return obj


def probe(path, tok):
    """(registro dict). Nunca levanta: el error ES el dato. El token NO entra al registro."""
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json",
                 "User-Agent": UA})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            raw = r.read().decode("utf-8", "replace")
            ms = (time.monotonic() - t0) * 1000.0
            hdr = r.headers
            rec = {"path": path, "status": r.status, "net_ms": round(ms, 1),
                   "bytes": len(raw),
                   "quota_used": hdr.get("x-uw-daily-req-count"),
                   "quota_limit": hdr.get("x-uw-token-req-limit")}
            try:
                payload = json.loads(raw)
            except ValueError:
                rec["shape"] = "no-json"
                rec["sample"] = raw[:300]
                return rec
            rec["shape"] = shape(payload)
            rec["sample"] = trim(payload)
            rec["newest_ts"] = newest_timestamp(payload)
            return rec
    except urllib.error.HTTPError as e:
        ms = (time.monotonic() - t0) * 1000.0
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return {"path": path, "status": e.code, "net_ms": round(ms, 1), "error_body": body,
                "quota_used": (e.headers or {}).get("x-uw-daily-req-count")}
    except Exception as e:
        return {"path": path, "status": None, "error": f"{type(e).__name__}: {e}"}


TS_KEYS = ("timestamp", "executed_at", "tape_time", "created_at", "start_time", "date",
           "last_tape_time", "trf_executed_at", "updated_at", "time")


def newest_timestamp(payload, _depth=0):
    """El sello temporal MAS RECIENTE que aparezca en el payload, en ISO. None si no hay.
    Sirve para la edad del feed; jamas se inventa un 'ahora' si el campo falta."""
    best = None
    stack = [(payload, 0)]
    while stack:
        obj, d = stack.pop()
        if d > 4:
            continue
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in TS_KEYS and isinstance(v, str) and len(v) >= 8:
                    if best is None or v > best:
                        best = v
                elif isinstance(v, (dict, list)):
                    stack.append((v, d + 1))
        elif isinstance(obj, list):
            for x in obj[:400]:
                if isinstance(x, (dict, list)):
                    stack.append((x, d + 1))
    return best


def age_seconds(iso, now=None):
    """Edad en segundos de un sello ISO. None si no se puede parsear (nunca 0 plausible)."""
    if not iso:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    s = iso.strip()
    try:
        if len(s) == 10:   # solo fecha: la edad se cuenta en dias, no en segundos
            d = dt.date.fromisoformat(s)
            return (now.date() - d).days * 86400.0
        p = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if p.tzinfo is None:
            p = p.replace(tzinfo=dt.timezone.utc)
        return (now - p).total_seconds()
    except ValueError:
        return None


def in_rth(now_local=None):
    """True solo dentro de 09:30-16:00 de un dia de mercado. Fuera de ahi la latencia NO se
    puede medir: la edad del sello seria el tiempo desde el cierre, identica para un endpoint
    con 0 s de retraso y para uno con 60 s. Mismo criterio que uw_latency_probe.py."""
    lt = now_local or time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    import em_envelope
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def verdict(ages):
    """(veredicto, peor_edad). ages = {endpoint: feed_age_s}. None si no hay ni una edad:
    jamas se declara 'tiempo real' por ausencia de dato."""
    vivos = {k: v for k, v in ages.items() if v is not None}
    if not vivos:
        return None, None
    peor = max(vivos.values())
    return ("CANDIDATO A TIEMPO-REAL" if peor < REALTIME_S else "DELAYED — no dispara"), peor


def cube_lag(newest_iso, now=None, bucket_s=60):
    """Retraso del CUBO: cuantos cubos de `bucket_s` han pasado desde el sello mas nuevo.
    0 = el cubo del minuto en curso ya esta publicado; 1 = va un cubo por detras (normal en un
    feed que consolida por minuto); >=2 = ya no sirve para disparar. None si no hay sello."""
    age = age_seconds(newest_iso, now=now)
    if age is None:
        return None
    return int(age // bucket_s)


def rth_latency(sym, sector, tok, minutes, every_s, out_path=None):
    """Paso 2 y 3 del procedimiento del martes. Se NIEGA a correr fuera de sesion."""
    if not in_rth():
        print("FUERA DE RTH (fin de semana, festivo o fuera de 09:30-16:00): la latencia de UW "
              "NO es medible ahora — la edad del sello seria el tiempo desde el cierre. "
              "Sondeo NO ejecutado.", file=sys.stderr)
        return 1
    pasadas = max(1, int(minutes * 60 // every_s))
    todo = []
    for i in range(pasadas):
        now = dt.datetime.now(dt.timezone.utc)
        ages = {}
        for name in RTH_SET:
            path = ENDPOINTS[name].format(sym=sym, sector=sector,
                                          date=dt.date.today().isoformat(),
                                          expiry=dt.date.today().isoformat())
            rec = probe(path, tok)
            rec["endpoint"] = name
            rec["ts"] = now.isoformat()
            rec["feed_age_s"] = age_seconds(rec.get("newest_ts"), now=now)
            rec["cube_lag"] = cube_lag(rec.get("newest_ts"), now=now)
            ages[name] = rec["feed_age_s"]
            todo.append(rec)
            edad = rec["feed_age_s"]
            print(f"[{i + 1}/{pasadas}] {name:20s} {rec['status']!s:>4} "
                  f"edad={'n/d' if edad is None else format(edad, '.1f') + 's':>9} "
                  f"cubos={rec['cube_lag']}", file=sys.stderr)
            time.sleep(PAUSE_S)
        v, peor = verdict(ages)
        print(f"  -> pasada {i + 1}: peor edad "
              f"{'n/d' if peor is None else format(peor, '.1f') + 's'} -> {v or 'SIN DATO'}",
              file=sys.stderr)
        if i < pasadas - 1:
            time.sleep(max(0.0, every_s - PAUSE_S * len(RTH_SET)))

    por_ep = {}
    for r in todo:
        por_ep.setdefault(r["endpoint"], []).append(r.get("feed_age_s"))
    print("\n=== RESUMEN (mediana de edad por endpoint) ===", file=sys.stderr)
    for name, vs in por_ep.items():
        vivos = sorted(v for v in vs if v is not None)
        med = vivos[len(vivos) // 2] if vivos else None
        print(f"{name:20s} n={len(vivos)}/{len(vs)} mediana="
              f"{'n/d' if med is None else format(med, '.1f') + 's'}", file=sys.stderr)
    if out_path:
        with open(out_path, "w") as f:
            f.write(json.dumps(todo, indent=1, default=str))
        print(f"-> {out_path}", file=sys.stderr)
    else:
        print(json.dumps(todo, indent=1, default=str))
    print("RECORDATORIO: la edad del feed NO es el desfase contra IBKR. El contraste que decide "
          "(stock_state.tape_time de UW vs el ultimo print de data/bars_<SYM>.txt) exige IBKR "
          "vivo — ver TODOS.md 8f.", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="SPY")
    ap.add_argument("--sector", default="Technology")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD para full-tape")
    ap.add_argument("--expiry", default=None, help="YYYY-MM-DD para endpoints por vencimiento")
    ap.add_argument("--only", nargs="*", default=None, help="nombres de ENDPOINTS a sondear")
    ap.add_argument("--flow", action="store_true", help="solo el subconjunto de FLUJO")
    ap.add_argument("--rth-latency", action="store_true",
                    help="medir latencia intradia (SOLO con el mercado abierto)")
    ap.add_argument("--minutes", type=int, default=30, help="duracion de --rth-latency")
    ap.add_argument("--every", type=int, default=300, help="segundos entre pasadas")
    ap.add_argument("--out", default=None, help="fichero JSON de salida")
    a = ap.parse_args()

    tok = token()
    if not tok:
        print("SIN UW_TOKEN (env ni config/feeds.env): no se sondea nada", file=sys.stderr)
        return 1

    if a.rth_latency:
        return rth_latency(a.sym, a.sector, tok, a.minutes, a.every, a.out)

    names = a.only or (FLOW_SET if a.flow else list(ENDPOINTS))
    date = a.date or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    expiry = a.expiry or (dt.date.today() + dt.timedelta(days=7)).isoformat()
    now = dt.datetime.now(dt.timezone.utc)

    out = {"probed_at_utc": now.isoformat(), "sym": a.sym, "date_arg": date,
           "expiry_arg": expiry, "results": {}}
    for name in names:
        tpl = ENDPOINTS.get(name)
        if tpl is None:
            print(f"desconocido: {name}", file=sys.stderr)
            continue
        path = tpl.format(sym=a.sym, date=date, sector=a.sector, expiry=expiry)
        rec = probe(path, tok)
        rec["feed_age_s"] = age_seconds(rec.get("newest_ts"), now=now)
        out["results"][name] = rec
        print(f"{rec['status']!s:>5}  {rec.get('net_ms', 0):7.1f}ms  {name:26s} {path}",
              file=sys.stderr)
        time.sleep(PAUSE_S)

    txt = json.dumps(out, indent=1, default=str)
    if a.out:
        tmp = a.out + ".tmp"
        with open(tmp, "w") as f:
            f.write(txt)
        os.replace(tmp, a.out)
        print(f"-> {a.out}", file=sys.stderr)
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
