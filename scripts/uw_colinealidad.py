#!/usr/bin/env python3
"""uw_colinealidad.py — TODOS 8c: las 3 colinealidades que hay que medir ANTES de escribir
una linea de motor (test 1 de la killlist: rho antes que edge, |rho|>0.9 = muere ya).
Solo disco (data/history/), cero peticiones UW salvo --verify-uw (3 req a /max-pain).
  (1) greek_flow.dir_vega_flow  vs  signed_premium (net_call_premium - net_put_premium) por minuto
  (2) senal_capitan (signed_premium 15m del capitan) vs manada sobre BARRAS (breadth ret15 flota)
  (3) max_pain (OI completo, levels.json) vs abs_wall (gex) por sym-dia
Escribe data/uw_colinealidad.json. Los numeros van a docs/UW-LATENCIA-RTH-<fecha>.md a mano."""
import argparse
import datetime as dt
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import em_envelope  # noqa: E402

HIST = os.path.join(REPO, "data", "history")
CAPS = ("SPY", "QQQ", "SMH")
MIN_COBERTURA = 27   # mismo minimo que fleet_consensus: menos de 27/30 votando = FEED, no direccion


class Acc:
    """Acumulador de Pearson en streaming (sin cargar todo en memoria)."""
    __slots__ = ("n", "sx", "sy", "sxx", "syy", "sxy")

    def __init__(self):
        self.n = 0; self.sx = self.sy = self.sxx = self.syy = self.sxy = 0.0

    def add(self, x, y):
        self.n += 1; self.sx += x; self.sy += y
        self.sxx += x * x; self.syy += y * y; self.sxy += x * y

    def rho(self):
        if self.n < 3:
            return None
        cov = self.sxy - self.sx * self.sy / self.n
        vx = self.sxx - self.sx * self.sx / self.n
        vy = self.syy - self.sy * self.sy / self.n
        if vx <= 0 or vy <= 0:
            return None
        return cov / math.sqrt(vx * vy)


def minuto(ts):
    return ts.replace(" ", "T")[:16]   # YYYY-MM-DDTHH:MM


def dias_de_mercado():
    """Solo sesiones reales. Un levels.json de sabado es una copia rancia del viernes: contarlo
    duplica filas e infla n (cazado el 2026-08-05: 07-25, 07-26 y 08-02 colados en coli_3)."""
    out = []
    for d in sorted(os.listdir(HIST)):
        if not os.path.isdir(os.path.join(HIST, d)):
            continue
        try:
            fecha = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if em_envelope.is_market_day(fecha):
            out.append(d)
    return out


def days_with(fname_fmt, sym="spy"):
    out = []
    for d in sorted(os.listdir(HIST)):
        if os.path.isfile(os.path.join(HIST, d, fname_fmt.format(sym=sym))):
            out.append(d)
    return out


def load_rows(day, kind, sym):
    """Las dos formas de archivo que conviven: {'rows':[...]} (uw_flow_archive /
    uw_netprem_archive) y {'_meta','payload':{'data':[...]}} (uw_archive). Forma
    desconocida -> None, jamas [] fingido."""
    p = os.path.join(HIST, day, "uw_%s_%s.json" % (kind, sym.lower()))
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as f:
            d = json.load(f)
    except ValueError:
        return None
    if isinstance(d, dict) and isinstance(d.get("rows"), list):
        return d["rows"]
    pl = d.get("payload") if isinstance(d, dict) else None
    if isinstance(pl, dict) and isinstance(pl.get("data"), list):
        return pl["data"]
    if isinstance(pl, list):
        return pl
    return None


def fleet():
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        return [s for s in f.read().split() if s]


# ------------------------- (1) dir_vega_flow vs signed_premium -------------------------

def coli_1():
    pooled, per_sym = Acc(), {}
    control = Acc()            # dir_delta_flow vs net_delta: precedente rho=1.0, debe repetirse
    control_eq = [0, 0]        # [iguales, comparados] igualdad de string exacta
    n_days = 0
    syms_seen = set()
    for d in dias_de_mercado():
        base = os.path.join(HIST, d)
        gf_files = [x for x in os.listdir(base) if x.startswith("uw_greek_flow_") and x.endswith(".json")]
        if not gf_files:
            continue
        n_days += 1
        for gf in gf_files:
            sym = gf[len("uw_greek_flow_"):-len(".json")].upper()
            g = load_rows(d, "greek_flow", sym)
            npr = load_rows(d, "net_prem_ticks", sym)
            if not g or not npr:
                continue
            syms_seen.add(sym)
            gmap = {minuto(r["timestamp"]): r for r in g if r.get("timestamp")}
            acc = per_sym.setdefault(sym, Acc())
            for r in npr:
                k = minuto(r["tape_time"])
                gr = gmap.get(k)
                if gr is None:
                    continue
                try:
                    x = float(gr["dir_vega_flow"])
                    y = float(r["net_call_premium"]) - float(r["net_put_premium"])
                except (KeyError, TypeError, ValueError):
                    continue
                pooled.add(x, y); acc.add(x, y)
                try:
                    xd = float(gr["dir_delta_flow"]); yd = float(r["net_delta"])
                    control.add(xd, yd)
                    control_eq[1] += 1
                    if str(gr["dir_delta_flow"]) == str(r["net_delta"]):
                        control_eq[0] += 1
                except (KeyError, TypeError, ValueError):
                    pass
    per = {s: {"rho": a.rho(), "n": a.n} for s, a in sorted(per_sym.items())}
    rhos = [v["rho"] for v in per.values() if v["rho"] is not None]
    return {"que": "dir_vega_flow vs signed_premium (por minuto)",
            "dias": n_days, "syms": len(syms_seen),
            "rho_pooled": pooled.rho(), "n_minutos": pooled.n,
            "rho_per_sym_min": min(rhos) if rhos else None,
            "rho_per_sym_max": max(rhos) if rhos else None,
            "rho_per_sym_mediana": sorted(rhos)[len(rhos) // 2] if rhos else None,
            "per_sym": per,
            "control_delta": {"que": "dir_delta_flow vs net_delta (precedente rho=1.0)",
                              "rho": control.rho(), "n": control.n,
                              "byte_identicos": control_eq[0], "comparados": control_eq[1]}}


# ------------------- (2) senal_capitan vs manada sobre BARRAS --------------------------

def load_bars(day, sym):
    p = os.path.join(HIST, day, "bars", sym.lower() + ".txt")
    if not os.path.isfile(p):
        return None
    out = {}
    with open(p) as f:
        for ln in f:
            t = ln.split()
            if len(t) >= 5:
                try:
                    out[int(t[0])] = float(t[4])
                except ValueError:
                    continue
    return out or None


def closest(bars, epoch, tol=120):
    """Cierre de la barra <= epoch mas cercana (tolerancia tol s). None si no hay."""
    for e in range(epoch, epoch - tol - 1, -60):
        if e in bars:
            return bars[e]
    return None


def coli_2():
    fl = fleet()
    accs = {c: Acc() for c in CAPS}
    agree = {c: [0, 0] for c in CAPS}   # [mismo signo, comparables]
    days_used = []
    for d in dias_de_mercado():
        bdir = os.path.join(HIST, d, "bars")
        if not os.path.isdir(bdir):
            continue
        caps_rows = {c: load_rows(d, "net_prem_ticks", c) for c in CAPS}
        if not any(caps_rows.values()):
            continue
        bars = {s: load_bars(d, s) for s in fl}
        bars = {s: b for s, b in bars.items() if b}
        if len(bars) < MIN_COBERTURA:
            continue
        days_used.append(d)
        prem = {}
        for c, rows in caps_rows.items():
            if not rows:
                continue
            m = {}
            for r in rows:
                try:
                    ep = int(dt.datetime.fromisoformat(
                        r["tape_time"].replace("Z", "+00:00")).timestamp())
                    m[ep - ep % 60] = float(r["net_call_premium"]) - float(r["net_put_premium"])
                except (KeyError, ValueError):
                    continue
            prem[c] = m
        # rejilla de 5 min, 09:45-16:00 ET del dia d
        d0 = dt.datetime.fromisoformat(d + "T09:45:00-04:00")
        for i in range(0, 76):
            t = int((d0 + dt.timedelta(minutes=5 * i)).timestamp())
            up = dn = 0
            for s, b in bars.items():
                c_now, c_prev = closest(b, t), closest(b, t - 900)
                if c_now is None or c_prev is None:
                    continue
                if c_now > c_prev:
                    up += 1
                elif c_now < c_prev:
                    dn += 1
            if up + dn < MIN_COBERTURA:
                continue
            breadth = (up - dn) / float(up + dn)
            for c in CAPS:
                pm = prem.get(c)
                if not pm:
                    continue
                s15 = [pm[e] for e in range(t - 840, t + 60, 60) if e in pm]
                if len(s15) < 10:
                    continue
                x = sum(s15)
                accs[c].add(x, breadth)
                if x != 0 and breadth != 0:
                    agree[c][1] += 1
                    if (x > 0) == (breadth > 0):
                        agree[c][0] += 1
    out = {"que": "signed_premium 15m del capitan vs breadth ret15 de la flota (barras, rejilla 5m)",
           "dias": days_used, "min_cobertura": MIN_COBERTURA, "capitanes": {}}
    for c in CAPS:
        a, (ok, tot) = accs[c], agree[c]
        out["capitanes"][c] = {"rho": a.rho(), "n_buckets": a.n,
                               "acuerdo_signo_pct": round(100.0 * ok / tot, 1) if tot else None,
                               "n_signo": tot}
    return out


# ------------------------- (3) max_pain vs abs_wall ------------------------------------

def coli_3():
    acc = Acc()
    match = [0, 0]
    diffs = []
    days_used = []
    for d in dias_de_mercado():
        p = os.path.join(HIST, d, "levels.json")
        if not os.path.isfile(p):
            continue
        try:
            with open(p) as f:
                lv = json.load(f)["levels"]
        except (ValueError, KeyError):
            continue
        used = False
        for sym, e in lv.items():
            try:
                mp = float(e["max_pain"])
                aw = float(e["gex"]["abs_wall"])
                spot = float(e["spot"])
            except (KeyError, TypeError, ValueError):
                continue
            if spot <= 0:
                continue
            a, b = (mp - spot) / spot, (aw - spot) / spot
            acc.add(a, b)
            match[1] += 1
            if abs(mp - aw) < 1e-9:
                match[0] += 1
            diffs.append(abs(mp - aw) / spot * 100.0)
            used = True
        if used:
            days_used.append(d)
    diffs.sort()
    return {"que": "(max_pain-spot)/spot vs (abs_wall-spot)/spot, por sym-dia (levels.json)",
            "dias": days_used, "rho": acc.rho(), "n_sym_dias": acc.n,
            "strike_identico_pct": round(100.0 * match[0] / match[1], 1) if match[1] else None,
            "mediana_dist_pct": round(diffs[len(diffs) // 2], 2) if diffs else None}


def verify_uw_maxpain():
    """3 peticiones: el max_pain de UW (ultima fecha) vs el nuestro (levels.json de esa fecha).
    Justifica usar NUESTRO max_pain como proxy del de UW en coli_3."""
    import urllib.request
    from uw_premium import token
    tok = token()
    if not tok:
        return {"error": "sin UW_TOKEN"}
    out = {}
    for sym in CAPS:
        try:
            req = urllib.request.Request(
                "https://api.unusualwhales.com/api/stock/%s/max-pain" % sym,
                headers={"Authorization": "Bearer " + tok, "Accept": "application/json",
                         "User-Agent": "ib-trader/1.0 (uw_colinealidad verify)"})
            with urllib.request.urlopen(req, timeout=15) as r:
                rows = json.load(r).get("data") or []
        except Exception as e:
            out[sym] = {"error": str(e)[:120]}
            continue
        if not rows:
            out[sym] = {"error": "sin filas"}
            continue
        last = max(rows, key=lambda r: str(r.get("date", "")))
        day = str(last.get("date", ""))[:10]
        vals = last.get("values") or []
        # values = [[expiry, max_pain], ...] o campo max_pain directo segun version del payload
        uw_mp = None
        if isinstance(vals, list) and vals:
            uw_mp = vals[0][1] if isinstance(vals[0], list) else None
        if uw_mp is None:
            uw_mp = last.get("max_pain")
        ours = None
        p = os.path.join(HIST, day, "levels.json")
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    ours = json.load(f)["levels"][sym]["max_pain"]
            except (ValueError, KeyError):
                ours = None
        out[sym] = {"uw_date": day, "uw_max_pain_exp_cercana": uw_mp, "nuestro_max_pain": ours,
                    "payload_last": {k: last[k] for k in list(last)[:4]}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-uw", action="store_true", help="3 req UW /max-pain de control")
    a = ap.parse_args()
    rep = {"generado": dt.datetime.now().isoformat(timespec="seconds"),
           "regla": "killlist test 1: |rho|>0.9 = muere ya",
           "coli_1_vega_vs_signed_premium": coli_1(),
           "coli_2_capitan_vs_manada_barras": coli_2(),
           "coli_3_maxpain_vs_abswall": coli_3()}
    if a.verify_uw:
        rep["verify_uw_maxpain"] = verify_uw_maxpain()
    out = os.path.join(REPO, "data", "uw_colinealidad.json")
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, indent=1, default=str)
    os.replace(tmp, out)
    c1, c2, c3 = (rep["coli_1_vega_vs_signed_premium"],
                  rep["coli_2_capitan_vs_manada_barras"],
                  rep["coli_3_maxpain_vs_abswall"])
    print("(1) dir_vega_flow vs signed_premium: rho_pooled=%s n=%d dias=%d syms=%d "
          "per-sym[min=%s med=%s max=%s]"
          % (c1["rho_pooled"], c1["n_minutos"], c1["dias"], c1["syms"],
             c1["rho_per_sym_min"], c1["rho_per_sym_mediana"], c1["rho_per_sym_max"]))
    print("    control dir_delta_flow vs net_delta: rho=%s byte-identicos %d/%d"
          % (c1["control_delta"]["rho"], c1["control_delta"]["byte_identicos"],
             c1["control_delta"]["comparados"]))
    for c, v in c2["capitanes"].items():
        print("(2) %s vs manada-barras: rho=%s n=%s acuerdo-signo=%s%% (dias=%d)"
              % (c, v["rho"], v["n_buckets"], v["acuerdo_signo_pct"], len(c2["dias"])))
    print("(3) max_pain vs abs_wall: rho=%s n=%d strike-identico=%s%% mediana|d|=%s%% (dias=%d)"
          % (c3["rho"], c3["n_sym_dias"], c3["strike_identico_pct"],
             c3["mediana_dist_pct"], len(c3["dias"])))
    if a.verify_uw:
        print("verify UW max-pain:", json.dumps(rep["verify_uw_maxpain"], default=str)[:400])
    print("-> data/uw_colinealidad.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
