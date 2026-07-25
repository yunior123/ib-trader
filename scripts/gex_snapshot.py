#!/usr/bin/env python3
"""gex_snapshot.py — el mapa gamma de la flota, CALCULADO EN CASA.

gexa.ai desaparecio (orden Yunior 2026-07-25: "gexa is gone now, we are on our own"), y con
el el scraping por Chrome del que dependian los planes diarios. Este script lo sustituye SIN
perder nada, porque la materia prima ya la tenemos mejor:

  · `poly_chain_archive.py` archiva a diario `data/history/<fecha>/chain_full_<sym>.json` con
    las griegas REALES de Polygon (gamma medida, no reconstruida) y el open interest real:
    medido el 25/07, 94-98% de los contratos con gamma+OI para los 30 simbolos de la flota.
  · `gex_core.build_gex` saca de ahi flip, regimen, muros, POC y net GEX — la misma fuente
    unica que ya usan el chart, ./compass y los gates.

Ventaja sobre lo que se jubila, medido el 2026-07-25 comparando ambos:
  · cobertura: 30 simbolos (la flota entera) frente a los 16 que scrapeabamos.
  · el campo `regime` venia NULL en 15 de los 16 del snapshot de gexa — justo el campo del
    que vive la doctrina `gamma-regime-walls`. Aqui sale para todos, calculado.
  · gexa daba AAPL flip 208.0 con spot 333.47 (-37.6%): imposible para un flip de gamma.
    Un scrape roto que nadie podia auditar. Esto es auditable strike por strike.

Lo unico que gexa aportaba y aqui NO se reproduce es su score/bias propietario y el Market
Narrator: eran SALIDA DE MODELO ajeno, no dato medido. No se imita un numero que no podemos
medir (skill `anti-overfit-killlist`).

CONTRATO: escribe `data/gex_snapshot.json` con la MISMA forma por simbolo que el difunto
`gexa_snapshot.json` ({flip, flip_all, score, bias, poc, magnets, regime, call_usd, put_usd,
ts}), para que los consumidores no tengan que adivinar, MAS los campos de procedencia.

REGLA DE LA CASA: un simbolo sin cadena, o con menos del 50% de griegas usables, NO aparece.
No se rellena con 0 ni con el ultimo valor conocido — un numero plausible convierte "no se"
en "se, y es cero". Queda listado en `skipped` con el motivo.
"""
import datetime as dt
import glob
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core  # noqa: E402  (fuente unica de flip/regimen/muros)

MIN_GREEKS_PCT = 0.50    # por debajo de esto el libro no se puede leer: se omite el simbolo
MIN_STRIKES = 8          # menos strikes poblados que esto y el perfil es ruido
OUT = os.path.join(REPO, "data", "gex_snapshot.json")


def fleet():
    """La flota canonica, fuente unica data/fleet.txt. Levanta si no se puede leer: sin flota
    no hay mapa que construir, y un fallback silencioso ocultaria simbolos enteros."""
    p = os.path.join(REPO, "data", "fleet.txt")
    syms = []
    with open(p) as f:
        for ln in f:                      # el fichero es una sola linea separada por espacios,
            ln = ln.strip()               # pero se admite tambien uno por linea
            if not ln or ln.startswith("#"):
                continue
            syms.extend(t.upper() for t in ln.split())
    if not syms:
        raise RuntimeError(f"{p} vacia: sin flota canonica no hay mapa gamma")
    return syms


def latest_chain(sym, max_days=5):
    """La cadena archivada mas reciente de `sym`, hasta `max_days` atras (el fin de semana no
    hay archivo nuevo y el del viernes sigue siendo el mapa vigente).
    Devuelve (ruta, fecha) o (None, None) — nunca una ruta inventada."""
    hoy = dt.date.today()
    for k in range(max_days + 1):
        d = (hoy - dt.timedelta(days=k)).isoformat()
        p = os.path.join(REPO, "data", "history", d, f"chain_full_{sym.lower()}.json")
        if os.path.exists(p) and os.path.getsize(p) > 64:
            return p, d
    return None, None


def contracts_from(path):
    """Traduce la cadena de Polygon al dict que espera gex_core, quedandose SOLO con contratos
    que tengan gamma medida y OI real. Devuelve (contratos, spot, meta, n_total)."""
    with open(path) as f:
        d = json.load(f)
    meta = d.get("meta") or {}
    spot = meta.get("spot")
    res = d.get("results") or []
    cs = []
    for c in res:
        det = c.get("details") or {}
        g = (c.get("greeks") or {}).get("gamma")
        oi = c.get("open_interest")
        k = det.get("strike_price")
        ct = det.get("contract_type")
        exp = det.get("expiration_date")
        if g is None or not oi or k is None or not ct or not exp:
            continue
        cs.append({"strike": float(k), "right": ct[0].upper(), "oi": int(oi),
                   "gamma": float(g), "iv": c.get("implied_volatility"),
                   "exp": exp.replace("-", "")})
    return cs, spot, meta, len(res)


def snapshot_sym(sym):
    """El mapa gamma de un simbolo, o (None, motivo). Jamas un dict a medias."""
    path, fecha = latest_chain(sym)
    if not path:
        return None, "sin cadena chain_full archivada (<=5 dias)"
    cs, spot, meta, n_total = contracts_from(path)
    if not spot:
        return None, f"cadena {fecha} sin spot en meta"
    if not n_total:
        return None, f"cadena {fecha} vacia"
    pct = len(cs) / n_total
    if pct < MIN_GREEKS_PCT:
        return None, (f"griegas+OI usables {pct*100:.0f}% (<{MIN_GREEKS_PCT*100:.0f}%) "
                      f"sobre {n_total} contratos")
    gi = gex_core.build_gex(cs, spot)
    if gi.get("n_strikes_populated", 0) < MIN_STRIKES:
        return None, (f"{gi.get('n_strikes_populated', 0)} strikes poblados "
                      f"(<{MIN_STRIKES}): perfil sin lectura")
    net = gi.get("net_gex")
    if net is None or gi.get("flip") is None:
        return None, f"gex_core no dio flip/net_gex sobre la cadena {fecha}"

    call_usd = sum(v for v in (gi.get("call_gex") or {}).values())
    put_usd = sum(v for v in (gi.get("put_gex") or {}).values())
    # `score` reproduce la SEMANTICA que consumian los planes de gexa (su signo fijaba el
    # regimen), pero con nuestra magnitud auditable: net GEX en millones de $ por punto.
    score = round(net / 1e6, 1)
    neg = gi.get("regime") == "NEG"
    magnets = sorted({x for x in (gi.get("abs_wall"), gi.get("call_wall"),
                                  gi.get("put_wall")) if x})
    def _r(x, n=2):
        return round(float(x), n) if isinstance(x, (int, float)) else None
    return {
        "flip": _r(gi.get("flip")),
        "flip_all": _r(gi.get("flip")),      # calculamos sobre TODOS los vencimientos de la cadena
        "score": score,
        "bias": "PUT" if abs(put_usd) > abs(call_usd) else "CALL",
        "poc": gi.get("abs_wall"),
        "magnets": magnets,
        "regime": "NEGATIVE" if neg else "POSITIVE",
        "regime_short": gi.get("regime"),
        "call_usd": round(call_usd),
        "put_usd": round(put_usd),
        "net_gex": round(net),
        "gross_gex": round(gi.get("gross_gex") or 0),
        "call_wall": gi.get("call_wall"),
        "put_wall": gi.get("put_wall"),
        "abs_wall": gi.get("abs_wall"),
        "abs_wall_kind": gi.get("abs_wall_kind"),
        "spot": _r(spot),
        "ts": int(time.time()),
        # --- procedencia: MEDIDO vs reconstruido, dicho en el propio dato ---
        "src": "gex_core + chain_full (griegas Polygon MEDIDAS)",
        "chain_date": fecha,
        "chain_snapshot_local": meta.get("snapshot_local"),
        "greeks_ok_pct": round(pct, 3),
        "n_contracts": len(cs),
        "n_strikes_populated": gi.get("n_strikes_populated"),
    }, None


def build():
    syms = fleet()
    out = {}
    skipped = {}
    for s in syms:
        try:
            snap, why = snapshot_sym(s)
        except Exception as e:            # fail-loud POR SIMBOLO: uno roto no tumba el mapa,
            snap, why = None, f"{type(e).__name__}: {e}"   # pero se dice cual y por que
        if snap:
            out[s] = snap
        else:
            skipped[s] = why
    out["_meta"] = {
        "generado_por": "scripts/gex_snapshot.py",
        "asof": int(time.time()),
        "asof_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "fuente": "data/history/<fecha>/chain_full_<sym>.json (Polygon /v3/snapshot/options)",
        "griegas": "MEDIDAS (gamma y OI reales de Polygon) — nada reconstruido por Black-Scholes",
        "sustituye_a": "data/gexa_snapshot.json (gexa.ai jubilado el 2026-07-25)",
        "cobertura": f"{len(out)}/{len(syms)}",
        "skipped": skipped,
    }
    return out


def write(d, path=OUT):
    """Escritura ATOMICA: un lector nunca ve un JSON a medias."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1, sort_keys=False)
    os.replace(tmp, path)
    return path


def load(path=OUT, max_age_h=None):
    """El mapa gamma para los consumidores. Devuelve dict {SYM: {...}} sin `_meta`, o None si
    falta, esta roto o excede `max_age_h`. NUNCA {} — un dict vacio se confunde con
    "no hay gamma hoy" y ya nos costo una vez (fleet_consensus, denominador fabricado)."""
    if not os.path.exists(path):
        return None
    if max_age_h is not None:
        if (time.time() - os.path.getmtime(path)) > max_age_h * 3600:
            return None
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    syms = {k: v for k, v in d.items() if k != "_meta" and isinstance(v, dict)}
    return syms or None


def _cli():
    ap_sym = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]
    d = build()
    if "--dry-run" not in sys.argv:
        p = write(d)
        print(f"escrito {p}")
    m = d["_meta"]
    print(f"cobertura {m['cobertura']}  ({m['griegas']})")
    for s, v in d.items():
        if s == "_meta" or (ap_sym and s not in ap_sym):
            continue
        print(f"  {s:6s} flip {v['flip']:>9.2f} {v['regime_short']:>3s}  net {v['score']:+9.1f}M/pt "
              f"bias {v['bias']:4s} POC {str(v['poc']):>9s}  "
              f"({v['n_contracts']} contratos, griegas {v['greeks_ok_pct']*100:.0f}%, "
              f"cadena {v['chain_date']})")
    if m["skipped"]:
        print(f"  OMITIDOS ({len(m['skipped'])}) — sin dato, no con un cero fingido:")
        for s, why in m["skipped"].items():
            print(f"    {s:6s} {why}")


if __name__ == "__main__":
    _cli()
