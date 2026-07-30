#!/usr/bin/env python3
"""Arbol de niveles por ticker: muros supervivientes de la semana pasada + libro de esta
semana hasta el viernes + la cadena que expira ese viernes. Senal-solamente."""
import json, os, sys, time, datetime as dt, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gex_core, gex_snapshot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "history")
OUT = os.path.join(ROOT, "data", "trees")
SYMS = ["SPY", "QQQ", "AAPL", "SMH", "NVDA"]


def next_friday(d):
    return d + dt.timedelta(days=(4 - d.weekday()) % 7 or 7) if d.weekday() != 4 else d


def week_dates(fri):
    lw_fri = fri - dt.timedelta(days=7)
    return [(lw_fri - dt.timedelta(days=i)).isoformat() for i in range(4, -1, -1)]


def latest_chain_dir():
    ds = sorted(x for x in os.listdir(HIST) if x[:2] == "20" and os.path.isdir(os.path.join(HIST, x)))
    for d in reversed(ds):
        if any(f.startswith("chain_full_") for f in os.listdir(os.path.join(HIST, d))):
            return d
    return None


def last_week_walls(sym, dates):
    """{('C'|'P', strike): {'dias': n, 'oi_then': max, 'visto': [fechas]}} de levels.json."""
    acc = {}
    for d in dates:
        p = os.path.join(HIST, d, "levels.json")
        if not os.path.exists(p):
            continue
        try:
            L = json.load(open(p)).get("levels") or {}
        except (json.JSONDecodeError, OSError):
            continue
        row = L.get(sym)
        if not row:
            continue
        for right, key in (("C", "call_walls"), ("P", "put_walls")):
            for item in (row.get(key) or []):
                if not item or item[0] is None:
                    continue
                k = (right, float(item[0]))
                oi = float(item[1]) if len(item) > 1 and item[1] is not None else None
                e = acc.setdefault(k, {"dias": 0, "oi_then": None, "visto": [], "exp_then": row.get("exp")})
                if d not in e["visto"]:
                    e["visto"].append(d)
                    e["dias"] += 1
                if oi is not None:
                    e["oi_then"] = oi if e["oi_then"] is None else max(e["oi_then"], oi)
    return acc


def oi_by_strike(cs, right, upto_exp=None, only_exp=None):
    out = {}
    for c in cs:
        if c["right"] != right:
            continue
        e = c["exp"]
        if only_exp and e != only_exp:
            continue
        if upto_exp and e > upto_exp:
            continue
        out[c["strike"]] = out.get(c["strike"], 0) + int(c["oi"])
    return out


def touch_stats(sym):
    db = os.path.join(ROOT, "data", "trades.db")
    if not os.path.exists(db):
        return None
    q = ("select touch_ord, event, count(*) from level_events where sym=? "
         "and event in ('BOUNCE','BREAK','WICK_REJECT','RETEST_REJECT') group by touch_ord,event")
    # Con la flota escribiendo, `mode=ro` falla de forma TRANSITORIA (medido: "unable to open
    # database file (14)" y 5 min despues el mismo comando devuelve 5.457 filas) y tumbaba la
    # generacion ENTERA del arbol. La curva de toques es un ADORNO: si no se puede leer se
    # devuelve None (la degradacion que ya estaba disenada), nunca un cero que parezca medido.
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error as e:
        print(f"touch_stats({sym}): BD no legible ({e}) -> sin curva de toques", file=sys.stderr)
        return None
    try:
        rows = con.execute(q, (sym,)).fetchall()
    except sqlite3.Error as e:
        print(f"touch_stats({sym}): consulta fallida ({e}) -> sin curva de toques", file=sys.stderr)
        return None
    finally:
        con.close()
    if not rows:
        return None
    agg = {}
    for ordn, ev, n in rows:
        a = agg.setdefault(int(ordn), {"hold": 0, "break": 0})
        a["break" if ev == "BREAK" else "hold"] += int(n)
    out = []
    for ordn in sorted(agg):
        a = agg[ordn]
        n = a["hold"] + a["break"]
        out.append({"toque": ordn, "n": n, "aguanta": a["hold"], "rompe": a["break"],
                    "pct_aguanta": round(100.0 * a["hold"] / n, 1) if n else None})
    return out


def live_spot(sym):
    """(px, src, age_s) del precio VIVO, o None. La cadena archivada trae el spot del momento
    del archivo; fuera de la flota eso es el cierre previo de Polygon (GLW: 124.05 con 17h de
    edad y el papel en 130.81, cazado 2026-07-30). El arbol se centra en el precio de AHORA."""
    best = None
    p = os.path.join(ROOT, "data", f"bars_{sym.lower()}_ibkr.txt")
    try:
        rows = [ln.split() for ln in open(p) if ln.strip()]
        r = rows[-1]
        best = (float(r[4]), "ibkr_bars", time.time() - int(r[0]))
    except (OSError, IndexError, ValueError):
        pass
    try:
        d = json.load(open(os.path.join(ROOT, "data", "watchlist_stats.json")))
        row = (d.get("stats") or d.get("quotes") or d).get(sym.upper())
        ts = row.get("ts") or d.get("ts")
        cand = (float(row["last"]), "tws_snapshot", time.time() - float(ts))
        if best is None or cand[2] < best[2]:
            best = cand
    except (OSError, ValueError, TypeError, AttributeError, KeyError, json.JSONDecodeError):
        pass
    return best


def build(sym, chain_dir, fri, lw_dates):
    p = os.path.join(HIST, chain_dir, f"chain_full_{sym.lower()}.json")
    if not os.path.exists(p):
        return None, f"sin chain_full_{sym.lower()}.json en {chain_dir}"
    cs, spot, meta, n_cand = gex_snapshot.contracts_from(p)
    if not cs or spot is None:
        return None, "cadena sin contratos usables"
    lv = live_spot(sym)
    if lv and lv[2] < 900 and (meta.get("spot_age_s") or 1e9) > 300:
        spot, meta = lv[0], dict(meta, spot_source=lv[1], spot_age_s=round(lv[2], 1),
                                 spot_archivo=spot)
    fri_c = fri.replace("-", "")
    upto = [c for c in cs if c["exp"] <= fri_c]
    if not upto:
        return None, f"la cadena no llega al viernes {fri}"
    gi = gex_core.build_gex(upto, spot)
    flip, flip_src = gex_snapshot.honest_flip(upto, spot, gi)
    prof = sorted(((float(k), v) for k, v in (gi.get("profile") or {}).items()), key=lambda x: x[0])

    only_fri = [c for c in cs if c["exp"] == fri_c]
    gi_fri = gex_core.build_gex(only_fri, spot) if only_fri else None
    coi_f, poi_f = oi_by_strike(cs, "C", only_exp=fri_c), oi_by_strike(cs, "P", only_exp=fri_c)

    coi_u, poi_u = oi_by_strike(cs, "C", upto_exp=fri_c), oi_by_strike(cs, "P", upto_exp=fri_c)
    # el OI de la semana pasada es de contratos YA EXPIRADOS: el cociente no es like-for-like.
    # La supervivencia se decide por RANGO del strike en el libro de hoy, no por el ratio.
    rank = {"C": {k: i + 1 for i, (k, _) in enumerate(sorted(coi_u.items(), key=lambda x: -x[1]))},
            "P": {k: i + 1 for i, (k, _) in enumerate(sorted(poi_u.items(), key=lambda x: -x[1]))}}
    surv = []
    for (right, k), e in sorted(last_week_walls(sym, lw_dates).items(), key=lambda x: -(x[1]["oi_then"] or 0)):
        now = (coi_u if right == "C" else poi_u).get(k)
        then = e["oi_then"]
        rk = rank[right].get(k)
        if now is None or rk is None:
            estado = "SIN RASTRO"
        elif rk <= 6:
            estado = "SOBREVIVE"
        elif rk <= 15:
            estado = "DECAIDO"
        else:
            estado = "SIN RASTRO"
        surv.append({"lado": right, "strike": k, "dias_semana_pasada": e["dias"],
                     "oi_entonces": then, "oi_ahora": now, "rank_ahora": rk,
                     "ratio_oi": round(100.0 * now / then, 1) if (now and then) else None,
                     "estado": estado, "exp_entonces": e.get("exp_then"),
                     "oi_viernes": (coi_f if right == "C" else poi_f).get(k)})

    def topn(d, n=6):
        return [{"strike": k, "oi": v} for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]]

    return {
        "sym": sym, "generado": dt.datetime.now().isoformat(timespec="seconds"),
        "viernes": fri, "chain_dir": chain_dir,
        "spot": spot, "spot_source": meta.get("spot_source"), "spot_age_s": meta.get("spot_age_s"),
        "band": meta.get("band"), "exp_hasta_fichero": meta.get("exp_hasta"),
        "greeks_src": meta.get("greeks"), "oi_src": meta.get("oi"), "bid_ask": meta.get("bid_ask"),
        "n_contratos_cadena": len(cs), "n_hasta_viernes": len(upto), "n_solo_viernes": len(only_fri),
        "regime": gi.get("regime"), "net_gex": gi.get("net_gex"),
        "flip": flip, "flip_src": flip_src,
        "call_wall": gi.get("call_wall"), "call_wall_kind": gi.get("call_wall_kind"),
        "put_wall": gi.get("put_wall"), "put_wall_kind": gi.get("put_wall_kind"),
        "abs_wall": gi.get("abs_wall"), "abs_wall_kind": gi.get("abs_wall_kind"),
        "oi_call_wall": gi.get("oi_call_wall"), "oi_put_wall": gi.get("oi_put_wall"),
        "profile": [{"strike": k, "gex": v} for k, v in prof],
        "viernes_call_wall": (gi_fri or {}).get("oi_call_wall"),
        "viernes_put_wall": (gi_fri or {}).get("oi_put_wall"),
        "viernes_calls_oi": sum(coi_f.values()), "viernes_puts_oi": sum(poi_f.values()),
        "viernes_pc_oi": round(sum(poi_f.values()) / sum(coi_f.values()), 3) if sum(coi_f.values()) else None,
        "viernes_top_calls": topn(coi_f), "viernes_top_puts": topn(poi_f),
        "supervivientes": surv,
        "toques": touch_stats(sym),
        "semana_pasada_fechas": lw_dates,
        "caveats": [
            "OI de la semana pasada = contratos YA EXPIRADOS (exp 07-22/23/24): el cociente de OI "
            "NO es like-for-like. La supervivencia se decide por RANGO del strike en el libro de hoy.",
            "Muros de la semana pasada: cadena IBKR/TWS del vencimiento MAS CERCANO de cada dia. "
            "Muros de hoy: cadena Polygon con banda adaptativa, todos los vencimientos hasta el viernes.",
            f"spot {spot} con edad {int(meta.get('spot_age_s') or 0)}s = cierre del viernes (mercado cerrado).",
            "Polygon = 15 min de retraso (HISTORIA/ESTRUCTURA). Ningun nivel de aqui dispara una orden: "
            "el PRINT que confirma es de IBKR en tiempo real.",
            "bid/ask NO_ENTITLED en este plan de Polygon: no hay gate de spread en esta hoja.",
        ],
    }, None


def main():
    fri = next_friday(dt.date.today()).isoformat()
    lw = week_dates(dt.date.fromisoformat(fri))
    cd = latest_chain_dir()
    if not cd:
        raise RuntimeError("no hay ninguna carpeta data/history/<fecha> con chain_full_*")
    os.makedirs(OUT, exist_ok=True)
    for s in (sys.argv[1:] or SYMS):
        s = s.upper()
        d, err = build(s, cd, fri, lw)
        if d is None:
            print(f"{s}: OMITIDO -> {err}")
            continue
        with open(os.path.join(OUT, f"{s.lower()}.json"), "w") as f:
            json.dump(d, f, indent=1)
        print(f"{s}: spot {d['spot']} flip {d['flip']} ({d['flip_src']}) {d['regime']} "
              f"CW {d['call_wall']}/{d['call_wall_kind']} PW {d['put_wall']}/{d['put_wall_kind']} "
              f"| viernes {d['n_solo_viernes']} contratos P/C {d['viernes_pc_oi']} "
              f"| supervivientes {sum(1 for x in d['supervivientes'] if x['estado']=='SOBREVIVE')}"
              f"/{len(d['supervivientes'])}")


if __name__ == "__main__":
    main()
