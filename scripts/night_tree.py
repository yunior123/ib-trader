#!/usr/bin/env python3
"""night_tree.py — LOTE fuera de sesion (no toca la flecha, no dispara nada): arma el arbol de
escenarios de la proxima apertura US con lo MEDIDO ahora y lo deja en data/night_tree.json.

Camino de datos: gex_snapshot.json (mapa) + opt_chain_<sym>.txt (vencimientos, IV ATM, OI) +
bars_* (sesiones US y KRX) + overnight_ctx.json (futuros/Corea) + macro_calendar (evento).
Regla #3: lo que no se puede medir sale None y se DICE; nunca 0.0 plausible.

Uso: night_tree.py [--sym SPY] [--json] [--tag monitor]"""
import argparse
import datetime
import json
import math
import os
import sys
import time
from collections import defaultdict
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")
OUT = os.path.join(REPO, "data", "night_tree.json")
LOG = os.path.join(REPO, "data", "night_tree.jsonl")
KOREA_LEAD = ("skhynix", "samsung", "kospi", "kospi200")
# los que compass ya trata como arrastrados por Corea (compass.cpp:1403 overnight_symbol)
SEMIS_US = ("MU", "SKHY", "DRAM", "SMH", "NVDA", "TSM", "ASML", "AMD", "INTC",
            "AVGO", "TXN", "QCOM", "EWY", "LRCX", "SNDK", "WDC", "STX")
CHAIN_MAX_AGE_S = 3600
IV_ATM_BAND = 2.0          # $ alrededor del spot que cuenta como ATM para la IV
IV_SANE = (0.02, 3.0)      # fuera de esto la IV del proveedor es basura, no valla
OPERABLE_PCT = 3.0         # mas lejos que esto en un dia = cobertura de cola, no objetivo


def jload(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def bars(sym, tz=ET):
    """[(dt, o, h, l, c, v)] del fichero de barras del simbolo. Lista vacia si no hay."""
    for name in (f"bars_{sym}_ibkr.txt", f"bars_{sym}.txt"):
        p = os.path.join(REPO, "data", name)
        if not os.path.exists(p):
            continue
        out = []
        with open(p) as f:
            for ln in f:
                q = ln.split()
                if len(q) < 6:
                    continue
                try:
                    out.append((datetime.datetime.fromtimestamp(float(q[0]), tz),
                                *(float(x) for x in q[1:6])))
                except ValueError:
                    continue
        return out
    return []


def sessions(rows, lo_min, hi_min):
    """Agrupa barras por fecha local quedandose con la franja [lo,hi) en minutos del dia."""
    by = defaultdict(list)
    for r in rows:
        m = r[0].hour * 60 + r[0].minute
        if lo_min <= m < hi_min:
            by[r[0].strftime("%Y-%m-%d")].append(r)
    return by


def ohlc(b):
    return None if not b else {"o": b[0][1], "h": max(x[2] for x in b), "l": min(x[3] for x in b),
                               "c": b[-1][4], "v": sum(x[5] for x in b), "n": len(b),
                               "ini": b[0][0].strftime("%H:%M"), "fin": b[-1][0].strftime("%H:%M")}


def us_day(sym):
    """Cierre RTH de hoy/ultimo dia, el previo, y el ultimo precio incluida la extendida."""
    rows = bars(sym)
    if not rows:
        return None
    rth = sessions(rows, 570, 960)
    if not rth:
        return None
    dias = sorted(rth)
    hoy, prev = ohlc(rth[dias[-1]]), (ohlc(rth[dias[-2]]) if len(dias) > 1 else None)
    ext = [r for r in rows if r[0].strftime("%Y-%m-%d") == dias[-1]
           and r[0].hour * 60 + r[0].minute >= 960]
    pre = [r for r in rows if r[0].strftime("%Y-%m-%d") == dias[-1]
           and r[0].hour * 60 + r[0].minute < 570]
    return {"dia": dias[-1], "rth": hoy, "prev_close": prev["c"] if prev else None,
            "pre": ohlc(pre), "ah": ohlc(ext), "last": (ext[-1][4] if ext else hoy["c"]),
            "last_ts": (ext[-1][0] if ext else rth[dias[-1]][-1][0]).isoformat()}


def chain(sym):
    """Filas de data/opt_chain_<sym>.txt + cabecera. None si falta o esta rancia."""
    p = os.path.join(REPO, "data", f"opt_chain_{sym.lower()}.txt")
    if not os.path.exists(p):
        return None
    age = time.time() - os.stat(p).st_mtime
    rows, spot = [], None
    with open(p) as f:
        for ln in f:
            if ln.startswith("#"):
                if "spot " in ln and spot is None:
                    try:
                        spot = float(ln.split("spot ")[1].split()[0])
                    except (IndexError, ValueError):
                        spot = None
                continue
            q = ln.split()
            if len(q) < 10:
                continue
            try:
                rows.append({"k": float(q[0]), "right": q[1].upper()[0], "exp": q[2],
                             "oi": float(q[6]), "iv": float(q[7]), "gamma": float(q[9])})
            except ValueError:
                continue
    return None if not rows else {"rows": rows, "spot": spot, "age_s": round(age, 1)}


def mapa_manana(ch, spot, hoy_iso):
    """Muros/max-pain de MANANA: fuera los contratos que expiran hoy (skill pin-and-expiry)."""
    hoy = hoy_iso.replace("-", "")
    viv = [r for r in ch["rows"] if r["exp"] > hoy]
    if not viv:
        return None
    oic, oip, gex = defaultdict(float), defaultdict(float), defaultdict(float)
    for r in viv:
        s = 1 if r["right"] == "C" else -1
        (oic if s > 0 else oip)[r["k"]] += r["oi"]
        gex[r["k"]] += s * r["gamma"] * r["oi"] * 100 * spot * spot * 0.01
    ks = sorted(set(list(oic) + list(oip)))
    pain = {x: sum(oic[k] * (x - k) for k in ks if k < x) + sum(oip[k] * (k - x) for k in ks if k > x)
            for x in ks}
    arriba = [(k, oic[k]) for k in ks if k > spot]
    abajo = [(k, oip[k]) for k in ks if k < spot]
    tc, tp = sum(oic.values()), sum(oip.values())
    # un muro a 6% del spot es cobertura de COLA, no un suelo que se toque en un dia: el
    # objetivo operable es el mayor OI dentro de OPERABLE_PCT (2026-08-06: 720 tenia mas OI
    # que 750 y habria puesto un objetivo imposible a un dia vista)
    cerca = [x for x in abajo if (spot - x[0]) / spot * 100 <= OPERABLE_PCT]
    dist = lambda k: round((k / spot - 1) * 100, 2)
    return {
        "n_exp": len(set(r["exp"] for r in viv)),
        "exp_prox": min(r["exp"] for r in viv),
        "call_wall": max(arriba, key=lambda x: x[1])[0] if arriba else None,
        "put_wall": max(abajo, key=lambda x: x[1])[0] if abajo else None,
        "suelo_operable": max(cerca, key=lambda x: x[1])[0] if cerca else None,
        "operable_pct": OPERABLE_PCT,
        "abs_wall": max(gex, key=lambda k: abs(gex[k])) if gex else None,
        "max_pain": min(pain, key=pain.get) if pain else None,
        "pc_oi": round(tp / tc, 3) if tc else None,
        "techos": [{"k": k, "oi": v, "d": dist(k)} for k, v in sorted(arriba, key=lambda x: -x[1])[:4]],
        "suelos": [{"k": k, "oi": v, "d": dist(k)} for k, v in sorted(abajo, key=lambda x: -x[1])[:4]],
    }


def valla(ch, spot, hoy_iso):
    """Valla de la proxima sesion por IV ATM del vencimiento mas cercano VIVO. None si la IV
    del proveedor no es sana — una valla inventada es peor que ninguna."""
    hoy = hoy_iso.replace("-", "")
    viv = [r for r in ch["rows"] if r["exp"] > hoy]
    if not viv:
        return None
    exp = min(r["exp"] for r in viv)
    ivs = [r["iv"] for r in viv
           if r["exp"] == exp and abs(r["k"] - spot) <= IV_ATM_BAND and IV_SANE[0] < r["iv"] < IV_SANE[1]]
    if not ivs:
        return None
    iv = sum(ivs) / len(ivs)
    d = datetime.datetime.strptime(exp, "%Y%m%d").date()
    dias = max((d - datetime.date.fromisoformat(hoy_iso)).days, 1)
    em = spot * iv * math.sqrt(dias / 365.0)
    return {"exp": exp, "iv_atm": round(iv, 4), "dias": dias, "n_iv": len(ivs),
            "em_abs": round(em, 2), "em_pct": round(em / spot * 100, 3),
            "lo": round(spot - em, 2), "hi": round(spot + em, 2)}


def korea():
    """Sesiones KRX cerradas + la viva, con % sobre el cierre de la sesion ANTERIOR."""
    out = {}
    for name in KOREA_LEAD:
        rows = bars(name, KST)
        if not rows:
            out[name] = None
            continue
        by = sessions(rows, 9 * 60, 15 * 60 + 32)
        dias = sorted(by)
        if len(dias) < 2:
            out[name] = None
            continue
        ses = []
        for i in range(1, len(dias)):
            a, b = ohlc(by[dias[i - 1]]), ohlc(by[dias[i]])
            ses.append({"fecha": dias[i], "pct": round((b["c"] / a["c"] - 1) * 100, 2),
                        "close": b["c"], "hi": b["h"], "lo": b["l"], "open": b["o"],
                        "n": b["n"], "fin": b["fin"],
                        "abrio_pct": round((b["o"] / a["c"] - 1) * 100, 2),
                        "max_pct": round((b["h"] / a["c"] - 1) * 100, 2)})
        out[name] = {"sesiones": ses[-3:], "viva": ses[-1] if ses[-1]["n"] < 380 else None}
    return out


def macro(hoy_iso):
    cal = jload(os.path.join(REPO, "data", "macro_calendar_2026.json")) or {}
    manana = (datetime.date.fromisoformat(hoy_iso) + datetime.timedelta(days=1)).isoformat()
    ev = []
    for clave in ("nfp", "cpi", "ppi"):
        for e in cal.get(clave, []) or []:
            if e.get("date") == manana:
                ev.append({"tipo": clave.upper(), "fecha": e["date"], "hora_et": "08:30",
                           "fuente": e.get("source")})
    for f in cal.get("fomc", []) or []:
        if f.get("end") == manana:
            ev.append({"tipo": "FOMC", "fecha": manana, "hora_et": "14:00", "fuente": f.get("source")})
    return ev


def build(sym):
    sl, SU = sym.lower(), sym.upper()
    us = us_day(sl)
    if not us:
        raise SystemExit(f"night_tree: sin barras de {SU} — no se afirma nada")
    ch = chain(SU)
    gex = (jload(os.path.join(REPO, "data", "gex_snapshot.json")) or {}).get(SU)
    ctx = jload(os.path.join(REPO, "data", "overnight_ctx.json"))
    spot = us["last"]
    t = {
        "ts": time.time(), "sym": SU,
        "asof_local": datetime.datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET"),
        "sesion_us": us, "spot": spot,
        "evento": macro(us["dia"]),
        "chain_age_s": ch["age_s"] if ch else None,
        "chain_stale": (ch["age_s"] > CHAIN_MAX_AGE_S) if ch else None,
        "mapa": mapa_manana(ch, spot, us["dia"]) if ch else None,
        "valla": valla(ch, spot, us["dia"]) if ch else None,
        "korea": korea(),
        "futuros": ({k: ctx.get(k) for k in
                     ("nq_pct", "nq_ref_src", "es_pct", "es_ref_src", "ts")} if ctx else None),
        "gex": ({"flip": gex.get("flip"), "regime": gex.get("regime"),
                 "regime_why": gex.get("regime_why"), "net_gex": gex.get("net_gex"),
                 "abs_wall": gex.get("abs_wall"), "abs_wall_kind": gex.get("abs_wall_kind"),
                 "pin_fortress": (gex.get("pin_risk") or {}).get("fortress_pin"),
                 "net_dex": gex.get("net_dex"), "delay": gex.get("data_delay_class"),
                 "oi_asof": "cierre anterior (Polygon)"} if gex else None),
    }
    t["semis_us"] = {s: (lambda d: None if not d or not d["rth"] or not d["prev_close"] else {
        "pct": round((d["rth"]["c"] / d["prev_close"] - 1) * 100, 2),
        "desde_min_pct": round((d["rth"]["c"] / min(d["rth"]["l"],
                               d["pre"]["l"] if d["pre"] else d["rth"]["l"]) - 1) * 100, 2),
        "last": d["last"]})(us_day(s.lower())) for s in SEMIS_US}
    return t


def _pct(x, dec=2):
    return "n/d" if x is None else f"{x:+.{dec}f}%"


def render(t):
    """Arbol en texto. Cada rama cuelga de un NIVEL medido, no de una opinion macro."""
    L, spot, m, v = [], t["spot"], t["mapa"], t["valla"]
    g = t["gex"] or {}
    ev = ", ".join(f"{e['tipo']} {e['hora_et']} ET" for e in t["evento"]) or "sin evento tabulado"
    L.append(f"╔═ {t['sym']} · {t['asof_local']}")
    us = t["sesion_us"]
    if us["rth"] and us["prev_close"]:
        d = (us["rth"]["c"] / us["prev_close"] - 1) * 100
        L.append(f"║ cierre {us['rth']['c']:.2f} ({d:+.2f}%) rango {us['rth']['l']:.2f}-{us['rth']['h']:.2f}"
                 f" · ext {us['last']:.2f}")
    L.append(f"║ EVENTO MANANA: {ev}")
    if t["futuros"]:
        f = t["futuros"]
        L.append(f"║ futuros desde el cierre 16:00 — ES {_pct(f['es_pct'])} NQ {_pct(f['nq_pct'])}"
                 f"  [{f.get('es_ref_src') or 'sin ref'}]")
    if g:
        reg = g.get("regime") or "NO DETERMINADO"
        L.append(f"║ gamma: flip {g.get('flip')} · regimen {reg}"
                 + (f" ({g['regime_why']})" if g.get("regime_why") else "")
                 + f" · OI {g.get('oi_asof')}")
    if m:
        L.append(f"║ mapa de MANANA (sin el vencimiento de hoy): muro {m['abs_wall']} · "
                 f"max pain {m['max_pain']} · suelo operable {m['suelo_operable']} · P/C {m['pc_oi']}")
        L.append("║   techos " + " ".join(f"{x['k']:.0f}({x['oi']:,.0f}|{x['d']:+.1f}%)" for x in m["techos"]))
        L.append("║   suelos " + " ".join(f"{x['k']:.0f}({x['oi']:,.0f}|{x['d']:+.1f}%)" for x in m["suelos"]))
        if m["put_wall"] != m["suelo_operable"]:
            L.append(f"║   ⓘ mayor OI put = {m['put_wall']:.0f} a {(m['put_wall']/spot-1)*100:+.1f}%: "
                     f"cobertura de COLA, no suelo del dia")
    if v:
        L.append(f"║ valla {v['exp']} por IV ATM {v['iv_atm']*100:.1f}%: ±{v['em_abs']:.2f} "
                 f"(±{v['em_pct']:.2f}%) → {v['lo']:.2f} — {v['hi']:.2f}")
    L.append("╠═ ARBOL")
    flip = g.get("flip")
    techo = m["abs_wall"] if m else None
    pain = m["max_pain"] if m else None
    suelo = m["suelo_operable"] if m else None
    if flip and techo:
        L.append(f"║ ├─ A) DENTRO de {flip}–{techo}  ← estado actual ({spot:.2f})")
        L.append("║ │    dealers amortiguan. Direccional aqui = 38.6% wr15 MEDIDO (n=44,")
        L.append("║ │    CAJA/PIN|f0|POS). NO-TRADE es la posicion. Se cobra en los bordes.")
        L.append(f"║ ├─ B) PIERDE {flip} con 2 cierres  → gamma negativa: el dealer AMPLIFICA")
        L.append(f"║ │    objetivo 1 {pain} (max pain) · objetivo 2 {suelo} (mayor OI put)")
        L.append(f"║ │    la valla baja marca {v['lo']:.2f}" if v else "║ │")
        L.append(f"║ ├─ C) ROMPE {techo}"
                 + (" (muro FORTALEZA)" if g.get("pin_fortress") else "")
                 + f" → el mas duro del mapa ({m['techos'][0]['oi']:,.0f} calls)" if m else "")
        L.append(f"║ │    solo con print y retest. La valla alta marca {v['hi']:.2f}" if v else "║ │")
    ks = t["korea"] or {}
    hy, ko = ks.get("skhynix"), ks.get("kospi")
    L.append("╠═ COREA (lidera semis US ~13h)")
    for nom, k in (("HYNIX", hy), ("KOSPI", ko), ("SAMSUNG", ks.get("samsung"))):
        if not k:
            L.append(f"║  {nom:8} sin lectura")
            continue
        s = k["sesiones"][-1]
        viva = " EN CURSO" if k["viva"] else " (cerrada)"
        L.append(f"║  {nom:8} {s['fecha']}{viva} {s['pct']:+.2f}%  abrio {s['abrio_pct']:+.2f}%"
                 f" max {s['max_pct']:+.2f}%  ult {s['fin']} KST")
        if len(k["sesiones"]) > 1:
            L.append(f"║  {'':8} previa {k['sesiones'][-2]['fecha']} {k['sesiones'][-2]['pct']:+.2f}%")
    if hy and hy["sesiones"]:
        s = hy["sesiones"][-1]
        if s["abrio_pct"] > 0 and s["pct"] < 0:
            L.append(f"║  ⚠ REBOTE RECHAZADO: abrio {s['abrio_pct']:+.2f}% y va {s['pct']:+.2f}%")
    sm = {k: v for k, v in (t.get("semis_us") or {}).items() if v}
    if sm:
        L.append("╠═ SEMIS US (cierre de hoy · rebote desde el minimo del dia)")
        for s, d in sorted(sm.items(), key=lambda x: x[1]["pct"])[:6]:
            L.append(f"║  {s:6} {d['pct']:+6.2f}%   +{d['desde_min_pct']:.1f}% desde minimo")
    L.append("╚═ senal-solamente · nada de esto dispara una orden sin PRINT")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="SPY")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tag", default="manual")
    a = ap.parse_args()
    t = build(a.sym)
    t["tag"] = a.tag
    txt = render(t)
    t["render"] = txt
    tmp = OUT + f".tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(t, f)
    os.replace(tmp, OUT)
    with open(LOG, "a") as f:
        f.write(json.dumps({k: v for k, v in t.items() if k != "render"}) + "\n")
    print(json.dumps(t, indent=1) if a.json else txt)


if __name__ == "__main__":
    sys.exit(main())
