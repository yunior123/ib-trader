#!/usr/bin/env python3
"""fleet_cp_scan.py — barrido C/P + ballenas + dark pool + cadena + muros para flota y bargain.

DESCRIPTIVO. Cero probabilidad publicada, cero voz, cero orden. Recoge lo que UW MIDE y lo
escribe crudo; el ranking se hace aparte con votos binarios de umbral fijo (la killlist prohibe
compuestos de z-scores con pesos a mano y el ranking transversal con autoridad).

Por simbolo y por vencimiento (esta semana / la proxima):
  max-pain · oi-per-strike (muros) · flow-per-strike (lado agresor del dia) ·
  option-contracts (ΔOI = open_interest − prev_oi, sweeps, NBBO) · greek-exposure/strike-expiry
Por simbolo: stock-state (spot) · net-prem-ticks (C/P del dia + premium firmado) ·
  flow-alerts (ballenas) · darkpool (prints de bloque, DESCRIPTIVO — killlist #3) · earnings

Un fallo se propaga como error del simbolo; jamas se rellena con 0.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from uw_premium import token  # noqa: E402

BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (fleet_cp_scan senal-solamente)"
TIMEOUT_S = 25
RETRIES = 3
WORKERS = 6
OUTDIR = os.path.join(REPO, "data", "scan")

_lock = threading.Lock()
_last = [0.0]
MIN_GAP_S = 0.04


def get(path, tok):
    """rows o levanta. Nunca [] fingido."""
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json",
                 "User-Agent": UA})
    last = None
    for attempt in range(RETRIES):
        with _lock:
            gap = time.time() - _last[0]
            if gap < MIN_GAP_S:
                time.sleep(MIN_GAP_S - gap)
            _last[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
            return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError("UW_TOKEN caducado (401)") from e
            last = e
            time.sleep((2, 6, 15)[attempt])
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise RuntimeError("UW %s fallo tras %d intentos: %s" % (path, RETRIES, last))


def f(x):
    """float o None. NUNCA 0.0 por defecto."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pick_expiries(exps, today):
    """(esta_semana, proxima_semana): primer vencimiento >= hoy dentro de los 4 dias
    siguientes, y el primero de la semana siguiente. None si no existe (no se inventa)."""
    fut = sorted(e for e in exps if e >= today.isoformat())
    if not fut:
        return None, None
    # viernes de esta semana (o hoy si es viernes)
    fri = today + dt.timedelta(days=(4 - today.weekday()) % 7)
    nxt_fri = fri + dt.timedelta(days=7)
    w1 = next((e for e in fut if e <= fri.isoformat()), None)
    w2 = next((e for e in fut if fri.isoformat() < e <= nxt_fri.isoformat()), None)
    if w1 is None:                      # sin semanal: el mas cercano es "esta semana"
        w1, w2 = fut[0], (fut[1] if len(fut) > 1 else None)
    elif w2 is None:
        w2 = next((e for e in fut if e > w1), None)
    return w1, w2


def walls(oi_rows, spot):
    """Muros desde filas (strike, call_oi, put_oi). Distingue el muro ABSOLUTO del EFECTIVO:
    un muro de puts por ENCIMA del spot no es un suelo (es iman/resistencia) y uno de calls
    por DEBAJO no es techo. El voto de direccion usa los efectivos.

    MEDIDO 2026-08-05: `/oi-per-strike?expiry=X` **IGNORA el parametro expiry** (NOK 08-07 y
    08-14 devuelven el MISMO agregado de toda la cadena). Los muros POR VENCIMIENTO se
    construyen por eso desde `/option-contracts?expiry=X`, que si lo respeta (76 vs 74
    contratos). Esta funcion sirve a los dos: se le pasan las filas ya normalizadas."""
    rows = [(f(r["strike"]), int(r.get("call_oi") or 0), int(r.get("put_oi") or 0))
            for r in oi_rows if f(r.get("strike")) is not None]
    if not rows:
        return None
    cw = max(rows, key=lambda r: r[1])
    pw = max(rows, key=lambda r: r[2])
    tot_c = sum(r[1] for r in rows)
    tot_p = sum(r[2] for r in rows)
    top = sorted(rows, key=lambda r: -(r[1] + r[2]))[:6]
    out = {"call_wall": cw[0], "call_wall_oi": cw[1],
           "put_wall": pw[0], "put_wall_oi": pw[2],
           "tot_call_oi": tot_c, "tot_put_oi": tot_p,
           "cp_oi": round(tot_c / tot_p, 2) if tot_p else None,
           "top_strikes": [{"k": k, "coi": c, "poi": p} for k, c, p in top]}
    if spot:
        up = [r for r in rows if r[0] > spot]
        dn = [r for r in rows if r[0] < spot]
        cwe = max(up, key=lambda r: r[1]) if up else None      # techo real: calls por encima
        pwe = max(dn, key=lambda r: r[2]) if dn else None      # suelo real: puts por debajo
        out["call_wall_above"] = cwe[0] if cwe else None
        out["call_wall_above_oi"] = cwe[1] if cwe else None
        out["put_wall_below"] = pwe[0] if pwe else None
        out["put_wall_below_oi"] = pwe[2] if pwe else None
        # perfil recortado a ±25% del spot (para dibujar el mapa sin cargar toda la cadena)
        out["profile"] = [{"k": k, "coi": c, "poi": p} for k, c, p in sorted(rows)
                          if 0.75 * spot <= k <= 1.25 * spot]
    return out


def flow_day(rows):
    """Agrega flow-per-strike: volumen y premium por lado agresor.

    OJO: este endpoint IGNORA `expiry` (medido 2026-08-05: 08-07, 08-14 y sin parametro dan
    los tres 54.877 calls en NOK). Es por tanto el flujo del DIA de TODA la cadena, y se pide
    UNA sola vez. Sumar "w1 + w2" contaba dos veces el mismo total."""
    if not rows:
        return None
    cv = sum(int(r.get("call_volume") or 0) for r in rows)
    pv = sum(int(r.get("put_volume") or 0) for r in rows)
    ca = sum(int(r.get("call_volume_ask_side") or 0) for r in rows)
    cb = sum(int(r.get("call_volume_bid_side") or 0) for r in rows)
    pa = sum(int(r.get("put_volume_ask_side") or 0) for r in rows)
    pb = sum(int(r.get("put_volume_bid_side") or 0) for r in rows)
    cpa = sum(f(r.get("call_premium_ask_side")) or 0.0 for r in rows)
    cpb = sum(f(r.get("call_premium_bid_side")) or 0.0 for r in rows)
    ppa = sum(f(r.get("put_premium_ask_side")) or 0.0 for r in rows)
    ppb = sum(f(r.get("put_premium_bid_side")) or 0.0 for r in rows)
    # strikes con mas premium de call y de put en el dia
    byk = {}
    for r in rows:
        k = f(r.get("strike"))
        if k is None:
            continue
        e = byk.setdefault(k, [0.0, 0.0])
        e[0] += f(r.get("call_premium")) or 0.0
        e[1] += f(r.get("put_premium")) or 0.0
    hot_c = sorted(byk.items(), key=lambda kv: -kv[1][0])[:3]
    hot_p = sorted(byk.items(), key=lambda kv: -kv[1][1])[:3]
    return {"call_vol": cv, "put_vol": pv,
            "cp_vol": round(cv / pv, 2) if pv else None,
            "call_ask": ca, "call_bid": cb, "put_ask": pa, "put_bid": pb,
            "call_prem_ask": cpa, "call_prem_bid": cpb,
            "put_prem_ask": ppa, "put_prem_bid": ppb,
            # firmado del vencimiento: calls compradas − calls vendidas − (puts compradas − vendidas)
            "signed_prem": (cpa - cpb) - (ppa - ppb),
            "hot_call_strikes": [{"k": k, "prem": v[0]} for k, v in hot_c],
            "hot_put_strikes": [{"k": k, "prem": v[1]} for k, v in hot_p]}


def contracts_expiry(rows, spot):
    """ΔOI real (open_interest − prev_oi), sweeps, OI y flujo firmado POR VENCIMIENTO.

    Es la unica fuente por-vencimiento fiable de OI y volumen: oi-per-strike y flow-per-strike
    ignoran `expiry` (medido). De aqui salen los muros del vencimiento y su flujo del dia."""
    if not rows:
        return None
    out = {"doi_call": 0, "doi_put": 0, "sweep_call_vol": 0, "sweep_put_vol": 0,
           "prem_call": 0.0, "prem_put": 0.0, "top_doi": [], "n": len(rows),
           "oi_call": 0, "oi_put": 0, "vol_call": 0, "vol_put": 0,
           "ask_call": 0, "bid_call": 0, "ask_put": 0, "bid_put": 0}
    detail = []
    oi_by_k = {}
    for r in rows:
        sym = r.get("option_symbol") or ""
        right = "C" if "C" in sym[6:] and sym[-9] == "C" else ("P" if sym and sym[-9] == "P" else None)
        if right is None:
            continue
        oi = r.get("open_interest")
        poi = r.get("prev_oi")
        doi = (int(oi) - int(poi)) if oi is not None and poi is not None else None
        vol = int(r.get("volume") or 0)
        prem = f(r.get("total_premium")) or 0.0
        strike = f(sym[-8:]) / 1000.0 if len(sym) >= 8 else None
        sw = int(r.get("sweep_volume") or 0)
        av, bv = int(r.get("ask_volume") or 0), int(r.get("bid_volume") or 0)
        avg = f(r.get("avg_price"))
        if strike is not None:
            e = oi_by_k.setdefault(strike, {"strike": strike, "call_oi": 0, "put_oi": 0})
            e["call_oi" if right == "C" else "put_oi"] += int(oi or 0)
        if right == "C":
            out["prem_call"] += prem
            out["sweep_call_vol"] += sw
            out["oi_call"] += int(oi or 0)
            out["vol_call"] += vol
            out["ask_call"] += av
            out["bid_call"] += bv
            if doi is not None:
                out["doi_call"] += doi
        else:
            out["prem_put"] += prem
            out["sweep_put_vol"] += sw
            out["oi_put"] += int(oi or 0)
            out["vol_put"] += vol
            out["ask_put"] += av
            out["bid_put"] += bv
            if doi is not None:
                out["doi_put"] += doi
        # premium firmado DERIVADO de este vencimiento: (ask−bid) x precio medio x 100.
        # option-contracts no da premium por lado; se marca como derivado, no como medido.
        if avg:
            s_ = (av - bv) * avg * 100.0
            out["signed_prem_deriv"] = out.get("signed_prem_deriv", 0.0) + (
                s_ if right == "C" else -s_)
            out["gross_prem_deriv"] = out.get("gross_prem_deriv", 0.0) + (av + bv) * avg * 100.0
        if doi is not None:
            detail.append({"k": strike, "r": right, "doi": doi, "vol": vol, "oi": int(oi),
                           "prem": prem, "ask_v": av, "bid_v": bv, "sweep": sw,
                           "iv": f(r.get("implied_volatility")),
                           "bid": f(r.get("nbbo_bid")), "ask": f(r.get("nbbo_ask"))})
    detail.sort(key=lambda d: -abs(d["doi"]))
    out["top_doi"] = detail[:10]
    out["top_prem"] = sorted(detail, key=lambda d: -d["prem"])[:6]
    out["cp_oi"] = round(out["oi_call"] / out["oi_put"], 2) if out["oi_put"] else None
    out["cp_vol"] = round(out["vol_call"] / out["vol_put"], 2) if out["vol_put"] else None
    # muros REALES de este vencimiento (oi-per-strike no sirve: ignora expiry)
    out["walls"] = walls(list(oi_by_k.values()), spot)
    return out


def gex_expiry(rows, spot):
    if not rows:
        return None
    cg = sum(f(r.get("call_gex")) or 0.0 for r in rows)
    pg = sum(f(r.get("put_gex")) or 0.0 for r in rows)
    cc = sum(f(r.get("call_charm")) or 0.0 for r in rows)
    pc = sum(f(r.get("put_charm")) or 0.0 for r in rows)
    cd = sum(f(r.get("call_delta")) or 0.0 for r in rows)
    pd = sum(f(r.get("put_delta")) or 0.0 for r in rows)
    peak = max(rows, key=lambda r: abs((f(r.get("call_gex")) or 0.0) + (f(r.get("put_gex")) or 0.0)))
    prof = sorted(((f(r.get("strike")), (f(r.get("call_gex")) or 0.0) + (f(r.get("put_gex")) or 0.0))
                   for r in rows if f(r.get("strike")) is not None), key=lambda x: x[0])
    # Flip de ESTE vencimiento: cruce de cero del GEX neto acumulado. Se recogen TODOS los
    # cruces y se elige el MAS CERCANO AL SPOT — quedarse con el primero daba artefactos
    # (COIN "flip 65" con el spot en 150: el acumulado cruza en la cola de puts baratos).
    # None si no cruza: "todo positivo"/"todo negativo" es una respuesta valida, no un hueco.
    cruces = []
    acc = 0.0
    prev_k = prev_acc = None
    for k, g in prof:
        acc += g
        if prev_acc is not None and (prev_acc < 0) != (acc < 0):
            span = acc - prev_acc
            cruces.append(round(prev_k + (k - prev_k) * (-prev_acc / span), 2) if span else k)
        prev_k, prev_acc = k, acc
    flip = min(cruces, key=lambda x: abs(x - spot)) if (cruces and spot) else (
        cruces[0] if cruces else None)
    # Un cruce a >20% del spot no es un flip operativo (SPCX daba 40 con el spot en 115): el
    # libro no cambia de signo cerca del precio. Se publica None con motivo, no el numero.
    flip_note = None
    if flip is not None and spot and abs(flip - spot) / spot > 0.20:
        flip_note = "cruce mas cercano en %.2f, a %.0f%% del spot: sin flip operativo" % (
            flip, 100.0 * abs(flip - spot) / spot)
        flip = None
    elif not cruces:
        flip_note = "el GEX acumulado no cruza cero en la cadena"
    return {"call_gex": cg, "put_gex": pg, "net_gex": cg + pg,
            "call_charm": cc, "put_charm": pc, "net_charm": cc + pc,
            "call_delta": cd, "put_delta": pd,
            "peak_gex_strike": f(peak.get("strike")), "flip": flip, "flip_note": flip_note,
            "profile": [{"k": k, "gex": g} for k, g in prof
                        if spot and 0.8 * spot <= k <= 1.2 * spot]}


DP_LIMIT = 500


def darkpool_agg(rows, spot):
    """DESCRIPTIVO (killlist #3: dark pool NO es señal). Agrega tamaño y niveles.
    UW sirve como maximo DP_LIMIT prints por llamada: si llegan justo esos, el agregado
    esta TRUNCADO a los mas recientes y NO es el dia completo — se marca y se publica la
    ventana real cubierta. Un total truncado presentado como total del dia seria mentira."""
    if not rows:
        return None
    prem = sum(f(r.get("premium")) or 0.0 for r in rows)
    size = sum(int(r.get("size") or 0) for r in rows)
    if not size:
        return None
    vwap = sum((f(r["price"]) or 0.0) * int(r["size"]) for r in rows) / size
    above = sum(int(r["size"]) for r in rows if spot and (f(r["price"]) or 0) > spot)
    lvl = {}
    for r in rows:
        p = f(r.get("price"))
        if p is None:
            continue
        k = round(p, 2)
        lvl[k] = lvl.get(k, 0) + int(r.get("size") or 0)
    top = sorted(lvl.items(), key=lambda kv: -kv[1])[:5]
    biggest = sorted(rows, key=lambda r: -(f(r.get("premium")) or 0.0))[:3]
    times = sorted(r.get("executed_at") or "" for r in rows)
    return {"n_prints": len(rows), "truncated": len(rows) >= DP_LIMIT,
            "window_from": times[0] if times else None, "window_to": times[-1] if times else None,
            "premium": prem, "size": size, "vwap": round(vwap, 4),
            "pct_above_spot": round(100.0 * above / size, 1) if spot else None,
            "top_levels": [{"px": k, "sz": v} for k, v in top],
            "biggest": [{"px": f(b.get("price")), "sz": int(b.get("size") or 0),
                         "prem": f(b.get("premium")), "at": b.get("executed_at")}
                        for b in biggest]}


def whales_agg(rows, w1, w2):
    """Ballenas UW del simbolo, separadas por vencimiento objetivo."""
    if rows is None:
        return None
    out = {"n": len(rows), "alerts": []}
    for r in rows[:60]:
        prem = f(r.get("total_premium")) or 0.0
        ask = f(r.get("total_ask_side_prem"))
        bid = f(r.get("total_bid_side_prem"))
        out["alerts"].append({
            "type": r.get("type"), "expiry": r.get("expiry"), "strike": f(r.get("strike")),
            "prem": prem, "vol": r.get("volume"), "oi": r.get("open_interest"),
            "ask_prem": ask, "bid_prem": bid, "sweep": r.get("has_sweep"),
            "opening": r.get("all_opening_trades"), "rule": r.get("alert_rule"),
            "at": r.get("created_at"), "px": f(r.get("underlying_price"))})
    tgt = [a for a in out["alerts"] if a["expiry"] in (w1, w2)]
    out["target_n"] = len(tgt)
    out["target_call_prem"] = sum(a["prem"] for a in tgt if a["type"] == "call")
    out["target_put_prem"] = sum(a["prem"] for a in tgt if a["type"] == "put")
    # firmado por lado agresor de las ballenas del objetivo
    out["target_signed"] = sum(
        ((a["ask_prem"] or 0.0) - (a["bid_prem"] or 0.0)) * (1 if a["type"] == "call" else -1)
        for a in tgt)
    return out


def day_flow(ticks):
    """C/P del dia y premium firmado desde net-prem-ticks (buckets de minuto)."""
    if not ticks:
        return None
    cv = sum(int(r.get("call_volume") or 0) for r in ticks)
    pv = sum(int(r.get("put_volume") or 0) for r in ticks)
    ncp = sum(f(r.get("net_call_premium")) or 0.0 for r in ticks)
    npp = sum(f(r.get("net_put_premium")) or 0.0 for r in ticks)
    nd = sum(f(r.get("net_delta")) or 0.0 for r in ticks)
    ca = sum(int(r.get("call_volume_ask_side") or 0) for r in ticks)
    cb = sum(int(r.get("call_volume_bid_side") or 0) for r in ticks)
    pa = sum(int(r.get("put_volume_ask_side") or 0) for r in ticks)
    pb = sum(int(r.get("put_volume_bid_side") or 0) for r in ticks)
    return {"call_vol": cv, "put_vol": pv,
            "cp_vol": round(cv / pv, 2) if pv else None,
            "net_call_prem": ncp, "net_put_prem": npp,
            # GOTCHA de la casa: firmado = net_call − net_put (vender put es alcista)
            "signed_prem": ncp - npp, "net_delta": nd,
            "call_ask": ca, "call_bid": cb, "put_ask": pa, "put_bid": pb,
            "buckets": len(ticks), "last_tape": ticks[-1].get("tape_time") if ticks else None}


def next_earnings(rows, today):
    if not rows:
        return None
    fut = sorted((r for r in rows if (r.get("report_date") or "") >= today.isoformat()),
                 key=lambda r: r["report_date"])
    if not fut:
        return None
    return {"date": fut[0]["report_date"], "time": fut[0].get("report_time")}


def scan_symbol(sym, tok, today):
    r = {"sym": sym, "errors": []}
    try:
        mp = get("/api/stock/%s/max-pain" % sym, tok)
        exps = [x["expiry"] for x in mp]
        w1, w2 = pick_expiries(exps, today)
        r["exp_w1"], r["exp_w2"] = w1, w2
        r["max_pain"] = {x["expiry"]: f(x.get("max_pain")) for x in mp if x["expiry"] in (w1, w2)}
        st = get("/api/stock/%s/stock-state" % sym, tok)
        spot = f(st.get("close"))
        prev = f(st.get("prev_close"))
        r["spot"] = spot
        r["prev_close"] = prev
        r["chg_pct"] = round(100.0 * (spot - prev) / prev, 2) if spot and prev else None
        r["stock_vol"] = st.get("total_volume")
        r["tape_time"] = st.get("tape_time")
        r["day"] = day_flow(get("/api/stock/%s/net-prem-ticks" % sym, tok))
        r["dp"] = darkpool_agg(get("/api/darkpool/%s?limit=500" % sym, tok), spot)
        r["whales"] = whales_agg(get("/api/stock/%s/flow-alerts?limit=60" % sym, tok), w1, w2)
        try:
            r["earnings"] = next_earnings(get("/api/stock/%s/earnings" % sym, tok), today)
        except Exception as e:
            r["errors"].append("earnings: %s" % e)
            r["earnings"] = None
        # flujo del dia por strike: UNA vez, el endpoint ignora expiry (medido)
        r["flow_day"] = flow_day(get("/api/stock/%s/flow-per-strike" % sym, tok))
        # OI de la cadena COMPLETA (tambien ignora expiry): mapa global, no del vencimiento
        r["oi_chain_all"] = walls(get("/api/stock/%s/oi-per-strike" % sym, tok), spot)
        r["exp"] = {}
        for tag, exp in (("w1", w1), ("w2", w2)):
            if not exp:
                continue
            q = urllib.parse.quote(exp)
            e = {"expiry": exp}
            try:
                # los dos unicos endpoints que SI respetan expiry (verificado)
                e["chain"] = contracts_expiry(
                    get("/api/stock/%s/option-contracts?expiry=%s&limit=500" % (sym, q), tok), spot)
                e["walls"] = (e["chain"] or {}).get("walls")
                e["gex"] = gex_expiry(
                    get("/api/stock/%s/greek-exposure/strike-expiry?expiry=%s" % (sym, q), tok), spot)
            except Exception as ex:
                r["errors"].append("%s %s: %s" % (tag, exp, ex))
            r["exp"][tag] = e
    except Exception as ex:
        r["errors"].append("fatal: %s" % ex)
    return r


def main():
    tok = token()
    if not tok:
        raise SystemExit("sin UW_TOKEN")
    today = dt.date.today()
    fleet = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    bargain = open(os.path.join(REPO, "data", "bargain_fleet.txt")).read().split()
    syms = list(dict.fromkeys([s.upper() for s in fleet + bargain]))
    if len(sys.argv) > 1:
        syms = [s.upper() for s in sys.argv[1:]]
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()
    res = {}
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(scan_symbol, s, tok, today): s for s in syms}
        done = 0
        for fu in cf.as_completed(futs):
            s = futs[fu]
            res[s] = fu.result()
            done += 1
            err = res[s].get("errors")
            print("[%2d/%2d] %-5s %s" % (done, len(syms), s, ("ERR " + err[0][:70]) if err else "ok"),
                  flush=True)
    out = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "today": today.isoformat(), "n_syms": len(syms),
           "fleet": [s.upper() for s in fleet], "bargain": [s.upper() for s in bargain],
           "elapsed_s": round(time.time() - t0, 1), "syms": res}
    path = os.path.join(OUTDIR, "cp_scan_%s.json" % dt.datetime.now().strftime("%Y%m%d_%H%M"))
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, default=str)
    os.rename(tmp, path)
    latest = os.path.join(OUTDIR, "cp_scan_latest.json")
    if os.path.islink(latest) or os.path.exists(latest):
        os.remove(latest)
    os.symlink(os.path.basename(path), latest)
    print("\n-> %s  (%.1fs, %d syms)" % (path, out["elapsed_s"], len(syms)))


if __name__ == "__main__":
    main()
