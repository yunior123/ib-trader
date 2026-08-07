#!/usr/bin/env python3
"""night_monitor.py — LOTE fuera de sesion: un punto de control nocturno. Rearma el arbol
(night_tree), lo compara con el control anterior y solo GRITA si algo material cambio.
En el ultimo control (--final) publica el post de X del simbolo, con lo acumulado de la
noche + el flujo premarket si existe.

Regla #3: lo que no se mide sale None y se dice; nada de ceros plausibles.
Uso: night_monitor.py [--sym SPY] [--final] [--deadline 2026-08-07T09:30] [--dry-run]"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo("America/New_York")
STATE = os.path.join(REPO, "data", "night_monitor_state.json")
LOG = os.path.join(REPO, "logs", "night_monitor.log")
PUSH = os.path.join(REPO, "scripts", "notify_short.py")
PY = os.path.join(REPO, "venv", "bin", "python")
# umbrales de "esto merece despertar a alguien" (no de senal: de VIGILANCIA)
MAT_SPOT_PCT = 0.35        # movimiento del subyacente en extendida desde el control anterior
MAT_FUT_PCT = 0.40         # futuros desde el cierre RTH
MAT_KOREA_PCT = 1.50       # deterioro/mejora del lider coreano desde el control anterior


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, **kw)


def jload(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return default


def jwrite(p, obj):
    tmp = f"{p}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, p)


def arbol(sym):
    r = sh([PY, os.path.join(REPO, "scripts", "night_tree.py"), "--sym", sym, "--tag", "monitor"])
    t = jload(os.path.join(REPO, "data", "night_tree.json"))
    if t is None or t.get("sym") != sym.upper():
        raise SystemExit(f"night_monitor: night_tree no dejo arbol de {sym} — rc={r.returncode} "
                         f"{r.stderr[-300:]}")
    return t


def korea_lider(t):
    k = (t.get("korea") or {}).get("skhynix")
    return None if not k or not k["sesiones"] else k["sesiones"][-1]


def deltas(t, prev):
    """Que cambio desde el control anterior. Cada campo es None si no se puede comparar."""
    d = {"spot": None, "es": None, "nq": None, "korea": None, "flip": None, "muro": None}
    if prev:
        if t.get("spot") and prev.get("spot"):
            d["spot"] = round((t["spot"] / prev["spot"] - 1) * 100, 3)
        for k, campo in (("es", "es_pct"), ("nq", "nq_pct")):
            a = (t.get("futuros") or {}).get(campo)
            b = (prev.get("futuros") or {}).get(campo)
            if a is not None and b is not None:
                d[k] = round(a - b, 3)
        ka, kb = korea_lider(t), korea_lider(prev)
        if ka and kb and ka["fecha"] == kb["fecha"]:
            d["korea"] = round(ka["pct"] - kb["pct"], 2)
        fa, fb = (t.get("gex") or {}).get("flip"), (prev.get("gex") or {}).get("flip")
        if fa and fb and fa != fb:
            d["flip"] = round(fa - fb, 2)
        ma, mb = (t.get("mapa") or {}).get("abs_wall"), (prev.get("mapa") or {}).get("abs_wall")
        if ma and mb and ma != mb:
            d["muro"] = [mb, ma]
    return d


def material(t, d):
    """Lista de motivos por los que este control SI merece un push. Vacia = silencio."""
    m, g, spot = [], t.get("gex") or {}, t.get("spot")
    flip, muro = g.get("flip"), (t.get("mapa") or {}).get("abs_wall")
    if spot and flip:
        if spot < flip:
            m.append(f"{t['sym']} {spot:.2f} POR DEBAJO del flip {flip}: gamma negativa")
    if spot and muro and spot > muro:
        m.append(f"{t['sym']} {spot:.2f} POR ENCIMA del muro {muro}")
    if d["spot"] is not None and abs(d["spot"]) >= MAT_SPOT_PCT:
        m.append(f"{t['sym']} {d['spot']:+.2f}% desde el control anterior")
    for k, nom in (("es", "ES"), ("nq", "NQ")):
        v = (t.get("futuros") or {}).get(f"{k}_pct")
        if v is not None and abs(v) >= MAT_FUT_PCT:
            m.append(f"{nom} {v:+.2f}% desde el cierre 16:00")
    if d["korea"] is not None and abs(d["korea"]) >= MAT_KOREA_PCT:
        m.append(f"Hynix {d['korea']:+.2f} pts desde el control anterior")
    if d["flip"]:
        m.append(f"flip movido {d['flip']:+.2f}")
    if d["muro"]:
        m.append(f"muro {d['muro'][0]} -> {d['muro'][1]}")
    return m


def push(txt):
    if not os.path.exists(PUSH):
        return False
    r = sh([PY, PUSH, txt[:180]])
    return r.returncode == 0


def flujo_premarket(sym):
    """La flecha premarket de bin/premarket_arrow, si es de HOY y el binario la dio por usable.
    Devuelve (dict, None) o (None, motivo). Un fichero de otra sesion NO se usa: pintaria la
    apertura de hoy con el premarket de ayer."""
    p = os.path.join(REPO, "data", f"premarket_arrow_{sym.lower()}.json")
    f = jload(p)
    if not f:
        return None, "sin fichero de flecha premarket (bin/premarket_arrow no ha corrido)"
    hoy = datetime.datetime.now(ET).strftime("%Y-%m-%d")
    if f.get("session_date") != hoy:
        return None, f"flecha premarket de otra sesion ({f.get('session_date')})"
    edad = time.time() - (f.get("ts") or 0)
    if edad > 900:
        return None, f"flecha premarket rancia ({edad/60:.0f} min)"
    if not f.get("usable"):
        return None, f"flecha premarket NO usable: {f.get('unusable_reason')}"
    return f, None


def texto_post(t, hist, flujo, motivo_sin_flujo):
    """Post de X del control final. Numeros MEDIDOS; lo que falte se calla, no se rellena."""
    sym, spot, g = t["sym"], t["spot"], t.get("gex") or {}
    m, v, fu = t.get("mapa") or {}, t.get("valla") or {}, t.get("futuros") or {}
    L = [f"${sym} pre-open read"]
    if fu.get("es_pct") is not None:
        L.append(f"ON: ES {fu['es_pct']:+.2f}% NQ {fu['nq_pct']:+.2f}% (vs 16:00 close)")
    k = korea_lider(t)
    if k:
        L.append(f"Korea: Hynix {k['pct']:+.1f}% (opened {k['abrio_pct']:+.1f}%)")
    if flujo:
        # n_prints es trade_count (equities_edge no da volumen premarket): se dice tal cual
        L.append(f"Premkt {flujo['n_bars']}m, {int(flujo['n_prints']):,} prints, "
                 f"drift {flujo['drift_pct']:+.2f}%, arrow {flujo['dir']}")
    elif motivo_sin_flujo:
        L.append(f"Premkt flow: n/a ({motivo_sin_flujo[:40]})")
    if g.get("flip") and m.get("abs_wall"):
        L.append(f"Box {g['flip']}-{m['abs_wall']} | spot {spot:.2f}")
    if v.get("em_pct"):
        L.append(f"Fence ±{v['em_pct']:.2f}% -> {v['lo']:.0f}-{v['hi']:.0f}")
    L.append("")
    L.append("Not financial advice")
    txt = "\n".join(L)
    return txt[:280]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="SPY")
    ap.add_argument("--final", action="store_true", help="ultimo control: publica en X")
    ap.add_argument("--deadline", default=None, help="ISO local; pasada esta hora no se hace nada")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ahora = datetime.datetime.now(ET)
    if a.deadline:
        lim = datetime.datetime.fromisoformat(a.deadline).replace(tzinfo=ET)
        if ahora > lim:
            print(f"night_monitor: pasada la fecha limite {a.deadline}; nada que hacer")
            return 0
    st = jload(STATE, {}) or {}
    prev = st.get(a.sym.upper())
    t = arbol(a.sym)
    d = deltas(t, prev)
    mot = material(t, d)
    cab = (f"[{ahora.strftime('%Y-%m-%d %H:%M ET')}] {t['sym']} {t['spot']:.2f} "
           f"d={d['spot'] if d['spot'] is not None else 'n/d'}% "
           f"ES={(t.get('futuros') or {}).get('es_pct')} "
           f"Hynix={(korea_lider(t) or {}).get('pct')} "
           f"| {'MATERIAL: ' + ' ; '.join(mot) if mot else 'sin cambios materiales'}")
    print(cab)
    print(t["render"])
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(cab + "\n" + t["render"] + "\n\n")
    if mot and not a.dry_run:
        push(f"🌙 {t['sym']} {t['spot']:.2f} — " + " ; ".join(mot))
    st[a.sym.upper()] = {k: t.get(k) for k in ("ts", "spot", "futuros", "korea", "gex", "mapa")}
    jwrite(STATE, st)
    if not a.final:
        return 0
    flujo, motivo = flujo_premarket(a.sym)
    if motivo:
        print(f"night_monitor: {motivo} — el post sale sin la linea de flujo")
    txt = texto_post(t, st, flujo, motivo)
    print(f"--- POST FINAL ({len(txt)} chars) ---\n{txt}")
    cmd = [PY, os.path.join(REPO, "scripts", "xpost.py"), txt]
    if a.dry_run:
        cmd.append("--dry-run")
    r = sh(cmd)
    print(r.stdout[-600:] or r.stderr[-600:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
