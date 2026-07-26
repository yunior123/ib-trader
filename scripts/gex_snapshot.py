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

CUBRE EL UNIVERSO DEL MAPA (`data/universe_gamma.txt`, 35 = la flota + SPX/XSP/NDX/DIA/IWM),
NO la flota de señales (`data/fleet.txt`, 30). Este script solo MAPEA: no vota, no habla, no
dispara — mezclar las dos listas fue el bug del denominador fabricado que rompio MANADA el
2026-07-25 (doctrina completa en docs/UNIVERSOS.md).

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
import universe  # noqa: E402  (universo del mapa vs flota de señales, docs/UNIVERSOS.md)


def keep_sign(x, nd=0):
    """Redondea `x` a `nd` decimales PERO nunca convierte un valor no nulo en cero.

    round(-40000/1e6, 1) == -0.0, y en Python `-0.0 < 0` es False: un nombre pequeño en
    regimen NEG se leeria como POSITIVO en los planes, porque los consumidores heredaron de
    gexa la logica "el signo del score fija el regimen". El signo es la informacion; los
    decimales son estetica. Si el redondeo se come el signo, se devuelve el valor sin tocar.
    """
    if not isinstance(x, (int, float)):
        return None
    r = round(float(x), nd) if nd else round(float(x))
    if r == 0 and x != 0:
        return x
    return r


MIN_GREEKS_PCT = 0.50    # por debajo de esto el libro no se puede leer: se omite el simbolo
MIN_STRIKES = 8          # menos strikes poblados que esto y el perfil es ruido
OUT = os.path.join(REPO, "data", "gex_snapshot.json")


def universo():
    """El universo del MAPA gamma (35), fuente unica data/universe_gamma.txt via
    scripts/universe.py. NO es la flota de señales (data/fleet.txt) — ese denominador lo
    lee fleet_consensus aparte y no se toca aqui."""
    return universe.gamma_universe()


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


def flip_history(sym, max_days=10):
    """(ts, flip) archivados por levels_5min_archive.py para `sym`, ultimos `max_days`.
    Lista vacia si no hay historia -- flip_migration_trail ya declara 'insuficiente_datos'."""
    sym = sym.upper()
    hoy = dt.date.today()
    out = []
    for k in range(max_days, -1, -1):
        d = (hoy - dt.timedelta(days=k)).isoformat()
        p = os.path.join(REPO, "data", "history", d, "levels_5m.jsonl")
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for ln in f:
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                if row.get("sym") != sym or row.get("stale"):
                    continue
                fl = (row.get("levels") or {}).get("flip")
                ts = row.get("ts")
                if fl is not None and ts is not None:
                    out.append((ts, fl))
    return out


def contracts_from(path):
    """Traduce la cadena de Polygon al dict que espera gex_core, quedandose SOLO con contratos
    que tengan gamma medida y OI real. Devuelve (contratos, spot, meta, n_candidatos).

    `n_candidatos` = contratos con OI>0, NO el total de filas. Es el unico denominador
    honesto para "% de griegas usables": con la banda adaptativa (2026-07-26) el fichero
    trae strikes a +-60%, donde la mitad de los contratos tiene OI=0 y por tanto no puede
    entrar nunca en el perfil. Con el total, ensanchar la banda hundia el porcentaje y el
    simbolo se omitia por "libro ilegible" cuando el libro estaba perfecto."""
    with open(path) as f:
        d = json.load(f)
    meta = d.get("meta") or {}
    spot = meta.get("spot")
    res = d.get("results") or []
    # epoch de la FOTO: es el reloj contra el que se mide el plazo de cada contrato.
    # Si falta, se usa el de ahora y queda dicho en el _meta del mapa.
    ref_ts = meta.get("snapshot_epoch")
    try:
        ref_ts = float(ref_ts) if ref_ts is not None else None
    except (TypeError, ValueError):
        ref_ts = None
    cs = []
    n_cand = 0
    for c in res:
        det = c.get("details") or {}
        g = (c.get("greeks") or {}).get("gamma")
        oi = c.get("open_interest")
        k = det.get("strike_price")
        ct = det.get("contract_type")
        exp = det.get("expiration_date")
        if oi and k is not None and ct and exp:
            n_cand += 1
        if g is None or not oi or k is None or not ct or not exp:
            continue
        # `T` (años al vencimiento) es OBLIGATORIA, no opcional. Sin ella gex_core caia
        # a un default de 0.02 = 7,3 dias PARA TODOS los vencimientos, 0DTE incluido, y
        # el flip repreciado salia de ese plazo inventado. Como el flip decide
        # abs_wall_kind (pin vs trampilla) y eso es VETO DURO sobre 0DTE comprado
        # (compass.cpp:630, book_quality:317), el numero plausible llegaba hasta la voz.
        # El reloj de referencia es el del SNAPSHOT, no el de ahora: si el mapa se
        # recalcula al dia siguiente sobre la misma cadena, el plazo debe ser el que
        # tenia cuando se tomo la foto.
        exp_c = exp.replace("-", "")
        T = gex_core._T_of(exp_c, ref_ts)
        if T is None:
            continue
        dl = (c.get("greeks") or {}).get("delta")
        cs.append({"strike": float(k), "right": ct[0].upper(), "oi": int(oi),
                   "gamma": float(g), "delta": dl, "iv": c.get("implied_volatility"),
                   "exp": exp_c, "T": T})
    return cs, spot, meta, n_cand


FLIP_GRID = (0.6, 1.5, 240)   # el barrido por defecto de gex_core es solo +-15% del spot


def honest_flip(cs, spot, gi):
    """(flip, procedencia). Solo se publica un flip que sea RAIZ MEDIDA del barrido.

    `gex_core._flip` cae al EXTREMO del rango de strikes cuando el perfil acumulado no
    cambia de signo, y ese extremo LO FIJA LA BANDA DEL FICHERO: medido el 2026-07-26,
    SKHY daba "flip" 207,5 / 230 / 270 / 305 / 390 segun donde se cortase la cadena. Eso
    no es un nivel de mercado, es el borde del recorte — y de ahi salen pin-vs-trampilla
    y el veto de 0DTE. Si no hay cruce ni en +-15% ni en el barrido ancho: None."""
    rc = gi.get("flip_recompute")
    if rc is not None:
        return rc, "recompute_15pct"
    lo, hi, steps = FLIP_GRID
    roots = gex_core.flip_recompute(cs, spot, lo=lo, hi=hi, steps=steps, all_roots=True)
    if roots:
        return roots[0], f"recompute_{lo:.2f}_{hi:.2f}"
    return None, "sin_cruce_de_signo_en_la_banda"


def wall_kind(gi, flip, key):
    """pin (POS, el nivel aguanta) o trampilla (NEG, el precio lo atraviesa) para el muro
    `key`, recalculado con el flip HONESTO — el de `build_gex` puede venir del borde."""
    k = gi.get(key)
    if k is None or flip is None:
        return None
    reg = gex_core.regime_at(dict(gi, flip=flip), k)[0]
    return None if reg is None else ("pin" if reg == "POS" else "trampilla")


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
        return None, (f"griegas usables {pct*100:.0f}% (<{MIN_GREEKS_PCT*100:.0f}%) "
                      f"sobre {n_total} contratos con OI>0")
    gi = gex_core.build_gex(cs, spot)
    if gi.get("n_strikes_populated", 0) < MIN_STRIKES:
        return None, (f"{gi.get('n_strikes_populated', 0)} strikes poblados "
                      f"(<{MIN_STRIKES}): perfil sin lectura")
    net = gi.get("net_gex")
    if net is None:
        return None, f"gex_core no dio net_gex sobre la cadena {fecha}"
    # Un libro sin cruce de signo SIGUE teniendo muros, POC, regimen y net medidos: se
    # publica con flip=None (y el motivo), no se tira el simbolo entero.
    flip, flip_src = honest_flip(cs, spot, gi)

    call_usd = sum(v for v in (gi.get("call_gex") or {}).values())
    put_usd = sum(v for v in (gi.get("put_gex") or {}).values())
    # `score` reproduce la SEMANTICA que consumian los planes de gexa (su signo fijaba el
    # regimen), pero con nuestra magnitud auditable: net GEX en millones de $ por punto.
    # keep_sign: el redondeo no puede comerse el signo (ver su docstring).
    score = keep_sign(net / 1e6, 3)
    neg = gi.get("regime") == "NEG"
    magnets = sorted({x for x in (gi.get("abs_wall"), gi.get("call_wall"),
                                  gi.get("put_wall")) if x})
    def _r(x, n=2):
        return round(float(x), n) if isinstance(x, (int, float)) else None
    dx = gex_core.build_dex(cs, spot)
    pin_risk = gex_core.pin_risk_score(gi, cs, spot)
    flip_trail = gex_core.flip_migration_trail(flip_history(sym))
    return {
        "flip": _r(flip),
        "flip_all": _r(flip),            # se calcula sobre TODOS los vencimientos del fichero
        "flip_src": flip_src,
        "flip_dist_pct": _r((flip - spot) / spot * 100) if flip else None,
        "score": score,
        "bias": "PUT" if abs(put_usd) > abs(call_usd) else "CALL",
        "poc": gi.get("abs_wall"),
        "magnets": magnets,
        "regime": "NEGATIVE" if neg else "POSITIVE",
        "regime_short": gi.get("regime"),
        "call_usd": keep_sign(call_usd),
        "put_usd": keep_sign(put_usd),
        "net_gex": keep_sign(net),
        # el mundo (CBOE, TradingFlow, SpotGamma) cita el GEX en $ por 1% de movimiento;
        # `net_gex` va en la escala de la casa (x spot). Son la MISMA medida a distinta
        # escala (factor spot/100) y sin este campo la comparacion con un referee sale
        # ~7x corta: eso fue la mitad del "13x por debajo" del 2026-07-26.
        "net_gex_dollar1pct": keep_sign(net * spot * 0.01),
        "gross_gex": keep_sign(gi.get("gross_gex") or 0),
        "call_wall": gi.get("call_wall"),
        "put_wall": gi.get("put_wall"),
        "abs_wall": gi.get("abs_wall"),
        "abs_wall_kind": wall_kind(gi, flip, "abs_wall"),
        # DEX: DOS campos de signo, jamas uno. `dex_sentiment` es el CLIENTE (dueño del OI),
        # `dex_flow_impact` es lo que el CREADOR hizo en el subyacente para quedar neutral —
        # son opuestos, y publicar solo uno invierte la lectura la mitad de las veces.
        "net_dex": keep_sign(dx["net_dex"]),
        "net_dex_shares": keep_sign(dx["net_dex_shares"]),
        "dex_sentiment": dx["dex_sentiment"],
        "dex_flow_impact": dx["dex_flow_impact"],
        "dex_convention": dx["dex_convention"],
        "abs_dex_wall": dx["abs_dex_wall"],
        "delta_ok_pct": _r(dx["delta_ok_pct_oi"], 3),
        "spot": _r(spot),
        "ts": int(time.time()),
        # --- procedencia: MEDIDO vs reconstruido, dicho en el propio dato ---
        "src": f"gex_core + chain_full (griegas MEDIDAS: {meta.get('greeks', 'n/d')})",
        "chain_date": fecha,
        "chain_snapshot_local": meta.get("snapshot_local"),
        "chain_band": meta.get("band"),
        "chain_band_convergida": meta.get("band_convergida"),
        "chain_exp_hasta": meta.get("exp_hasta"),
        "greeks_ok_pct": round(pct, 3),
        "n_contracts": len(cs),
        "n_strikes_populated": gi.get("n_strikes_populated"),
        "pin_risk": pin_risk,          # None si falta HHI/POC/T -- protocolo oi-magnets-protocol
        "flip_migration": flip_trail,  # forma del flip 5min (horizontal/inclinada/dentada)
    }, None


def build():
    syms = universo()
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
        # la fuente de las griegas va por SIMBOLO en `src` (Polygon no sirve griegas de
        # opciones de indice: SPX/XSP/NDX vienen de CBOE, y eso no se dice en global)
        "griegas": "MEDIDAS por el proveedor de cada cadena (ver `src` de cada simbolo) "
                   "— nada reconstruido por Black-Scholes",
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
        fl = f"{v['flip']:9.2f}" if v["flip"] is not None else "  SIN FLIP"
        print(f"  {s:6s} flip {fl} {v['regime_short']:>3s}  net {v['score']:+9.1f}M/pt "
              f"({(v['net_gex_dollar1pct'] or 0)/1e9:+6.2f}B $/1%) bias {v['bias']:4s} "
              f"POC {str(v['poc']):>9s}  banda +-{(v['chain_band'] or 0)*100:.0f}% "
              f"({v['n_contracts']} contratos, griegas {v['greeks_ok_pct']*100:.0f}%, "
              f"cadena {v['chain_date']})")
    if m["skipped"]:
        print(f"  OMITIDOS ({len(m['skipped'])}) — sin dato, no con un cero fingido:")
        for s, why in m["skipped"].items():
            print(f"    {s:6s} {why}")


if __name__ == "__main__":
    _cli()
