#!/usr/bin/env python3
"""uw_oi_delta.py — ¿la ballena de ayer ABRIA o CERRABA? volumen vs ΔOI, DESCRIPTIVO Y SIN VOZ.

Regla (Kochuba): V ≈ +ΔOI -> posicion NUEVA · V ≈ −ΔOI -> SALIDA · V >> |ΔOI| -> churn.
Un movimiento brusco suele ser un cambio de posicion, no una noticia.

EL OI NO ES EN TIEMPO REAL. Durante la sesion el OI que se ve es el CIERRE DE AYER: la OCC lo
publica a la mañana siguiente. Por eso aqui TODO es DIA-SOBRE-DIA y nunca intradia (killlist #16:
prohibida cualquier derivada temporal de un dato congelado). El emparejamiento se decide por la
fecha as-of del OI de cada snapshot, no por el nombre de la carpeta.

  snapshot del cierre de la sesion S  -> volumen de S   + OI del cierre de S-1
  cualquier snapshot del dia S+1      -> OI del cierre de S
  ΔOI(S) = OI(S) − OI(S-1)            y se compara con V(S)

Dos fuentes, la primera es la que sobrevive:
  polygon : data/history/<fecha>/chain_full_<sym>.json (nuestro, permanente)
  uw      : data/history/<fecha>/uw_oi_change_<sym>.json (trial con reloj, ya viene alineado)

CERO probabilidad publicada: sin bucket medido no hay numero (skill measured-probability).
SEÑAL-SOLAMENTE: no habla, no ordena, nadie lo consume todavia.

  uso:
    ./venv/bin/python scripts/uw_oi_delta.py --source uw --syms QQQ SPY
    ./venv/bin/python scripts/uw_oi_delta.py --source polygon --session 2026-07-27
    ./venv/bin/python scripts/uw_oi_delta.py --source uw --top 5 --write
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import em_envelope  # noqa: E402

HIST = os.path.join(REPO, "data", "history")
OUT_F = os.path.join(REPO, "data", "oi_delta.json")

# Umbrales DESCRIPTIVOS (etiquetan, no predicen). Se barren en el estudio; no son un edge.
R_NEW = 0.55    # ΔOI/V por encima: casi todo el volumen dejo posicion abierta
R_EXIT = -0.55  # por debajo: casi todo el volumen cerro posicion
R_CHURN = 0.15  # |ΔOI|/V por debajo: el dia se lo llevaron ida y vuelta
MIN_VOL = 250   # menos volumen que esto no se etiqueta (queda N/D, jamas CHURN por defecto)
# OI del dia S aparece a la mañana siguiente; a las 07:00 ET ya esta servido (verificado:
# los snapshots del sabado 16:20 y del lunes 08:45 traen los dos el OI del viernes).
OI_PUBLISH_H = 7

CONTRACT_RE = re.compile(r"^O?:?([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def prev_market_day(d):
    d -= dt.timedelta(days=1)
    while not em_envelope.is_market_day(d):
        d -= dt.timedelta(days=1)
    return d


def oi_asof(ts):
    """Fecha de cierre a la que corresponde el OI de un snapshot tomado en `ts` (naive local).
    Es el ultimo dia de mercado cuyo OI ya estaba publicado a esa hora."""
    d = ts.date()
    if not em_envelope.is_market_day(d):
        d = prev_market_day(d)
    elif ts.hour < OI_PUBLISH_H:
        d = prev_market_day(d)
    # El OI de `d` se publica el dia siguiente: a las <07:00 del dia natural siguiente aun no esta.
    pub = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(OI_PUBLISH_H))
    while ts < pub:
        d = prev_market_day(d)
        pub = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(OI_PUBLISH_H))
    return d


def parse_contract(t):
    """('QQQ', date, 'C', 605.0) o None si el formato no es el de OCC — nunca se adivina."""
    m = CONTRACT_RE.match(t.strip().upper())
    if not m:
        return None
    sym, yy, mm, dd, side, strike = m.groups()
    try:
        exp = dt.date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None
    return sym, exp, side, int(strike) / 1000.0


def classify(delta_oi, volume):
    """(etiqueta, ratio). N/D si el volumen no da para afirmar nada."""
    if volume is None or delta_oi is None:
        return "N/D", None
    if volume < MIN_VOL:
        return "N/D", (delta_oi / volume if volume else None)
    r = delta_oi / volume
    if r >= R_NEW:
        return "NUEVA", r
    if r <= R_EXIT:
        return "SALIDA", r
    if abs(r) <= R_CHURN:
        return "CHURN", r
    return "MIXTO", r


# ---------- fuente uw (ya alineada por el vendor) ----------

def _rows(payload):
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"forma inesperada: {type(payload)}")
    return rows


def from_uw(sym, archive_date):
    """Lee data/history/<archive_date>/uw_oi_change_<sym>.json. LEVANTA si falta o esta vacio."""
    p = os.path.join(HIST, archive_date, f"uw_oi_change_{sym.lower()}.json")
    with open(p) as f:
        doc = json.load(f)
    rows = _rows(doc.get("payload"))
    if not rows:
        raise RuntimeError(f"{p}: 0 filas — no se etiqueta nada (fichero vacio, no 'sin cambios')")
    out = []
    for r in rows:
        vol = r.get("volume")
        d_oi = r.get("oi_diff_plain")
        if vol is None or d_oi is None:
            continue   # sin los dos campos no hay ratio; se omite, no se rellena
        vol, d_oi = int(vol), int(d_oi)
        lab, ratio = classify(d_oi, vol)
        pc = parse_contract(r.get("option_symbol", ""))
        ask = r.get("prev_ask_volume")
        bid = r.get("prev_bid_volume")
        ask_share = (int(ask) / (int(ask) + int(bid))
                     if ask is not None and bid is not None and int(ask) + int(bid) > 0 else None)
        out.append({
            "contract": r.get("option_symbol"),
            "side": pc[2] if pc else None,
            "strike": pc[3] if pc else None,
            "expiry": pc[1].isoformat() if pc else None,
            "session": r.get("curr_date"),
            "oi_prev": r.get("last_oi"),
            "oi_curr": r.get("curr_oi"),
            "delta_oi": d_oi,
            "volume": vol,
            "ratio": ratio,
            "label": lab,
            "ask_share": ask_share,
            "premium": r.get("prev_total_premium"),
        })
    return out


# ---------- fuente polygon (nuestra, permanente) ----------

def _load_chain(date_s, sym):
    p = os.path.join(HIST, date_s, f"chain_full_{sym.lower()}.json")
    with open(p) as f:
        doc = json.load(f)
    meta = doc.get("meta") or {}
    snap = meta.get("snapshot_local")
    if not snap:
        raise RuntimeError(f"{p}: sin meta.snapshot_local — no se puede fechar el OI")
    ts = dt.datetime.fromisoformat(snap)
    by_ticker = {}
    for r in doc.get("results") or []:
        det = r.get("details") or {}
        t = det.get("ticker")
        if not t:
            continue
        by_ticker[t] = {"oi": r.get("open_interest"),
                        "vol": (r.get("day") or {}).get("volume"),
                        "expiry": det.get("expiration_date"),
                        "side": (det.get("contract_type") or "")[:1].upper(),
                        "strike": det.get("strike_price")}
    if not by_ticker:
        raise RuntimeError(f"{p}: 0 contratos")
    return ts, oi_asof(ts), by_ticker


def from_polygon(sym, date_a, date_b):
    """date_a = snapshot del cierre de la sesion S (volumen + OI de S-1);
    date_b = snapshot posterior cuyo OI ya es el del cierre de S. LEVANTA si no encajan."""
    ts_a, asof_a, ca = _load_chain(date_a, sym)
    ts_b, asof_b, cb = _load_chain(date_b, sym)
    sesion = asof_b
    if asof_a != prev_market_day(sesion):
        raise RuntimeError(
            f"{sym}: OI as-of {asof_a} ({date_a} {ts_a:%H:%M}) y {asof_b} ({date_b} {ts_b:%H:%M}) "
            f"no son sesiones consecutivas — ΔOI NO interpretable (entre medias no hubo UNA sesion)")
    if ts_a.date() != sesion:
        raise RuntimeError(f"{sym}: el snapshot de volumen es de {ts_a.date()} pero la sesion "
                           f"con ΔOI es {sesion} — el volumen no corresponde")
    out = []
    for t, b in cb.items():
        a = ca.get(t)
        if a is None:
            continue   # no estaba en el snapshot previo (banda adaptativa): OI_prev AUSENTE, no 0
        if a["oi"] is None or b["oi"] is None or a["vol"] is None:
            continue
        exp = b["expiry"] or a["expiry"]
        if exp and exp <= sesion.isoformat():
            continue   # vencido en/antes de S: su OI cae a 0 por mecanica, no por flujo
        d_oi = int(b["oi"]) - int(a["oi"])
        lab, ratio = classify(d_oi, int(a["vol"]))
        out.append({"contract": t, "side": b["side"], "strike": b["strike"], "expiry": exp,
                    "session": sesion.isoformat(), "oi_prev": a["oi"], "oi_curr": b["oi"],
                    "delta_oi": d_oi, "volume": a["vol"], "ratio": ratio, "label": lab})
    if not out:
        raise RuntimeError(f"{sym}: ningun contrato comparable entre {date_a} y {date_b}")
    return out


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def fleet():
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        syms = f.read().split()
    if not syms:
        raise RuntimeError("data/fleet.txt VACIA")
    return [s.upper() for s in syms]


def main():
    ap = argparse.ArgumentParser(description="volumen vs ΔOI dia-sobre-dia (descriptivo, sin voz)")
    ap.add_argument("--source", choices=("uw", "polygon"), default="uw")
    ap.add_argument("--syms", nargs="*")
    ap.add_argument("--date", help="carpeta de archivo para --source uw (default: hoy)")
    ap.add_argument("--pair", nargs=2, metavar=("DIA_A", "DIA_B"),
                    help="--source polygon: carpetas de los dos snapshots")
    ap.add_argument("--top", type=int, default=8, help="filas por simbolo a imprimir")
    ap.add_argument("--write", action="store_true", help="escribe data/oi_delta.json")
    a = ap.parse_args()

    syms = [s.upper() for s in a.syms] if a.syms else fleet()
    date_s = a.date or dt.date.today().isoformat()
    res, fallos = {}, []
    for sym in syms:
        try:
            rows = (from_uw(sym, date_s) if a.source == "uw"
                    else from_polygon(sym, *(a.pair or (None, None))))
        except Exception as e:
            fallos.append(f"{sym}: {e.__class__.__name__}: {e}")
            continue
        rows.sort(key=lambda r: -(r["volume"] or 0))
        res[sym] = rows
        print(f"{sym}  ({len(rows)} contratos)")
        for r in rows[:a.top]:
            rr = "  N/D" if r["ratio"] is None else f"{r['ratio']:+.2f}"
            print(f"   {r['contract']:24s} S={r['session']} V={r['volume']:>8,} "
                  f"ΔOI={r['delta_oi']:>+8,} r={rr}  {r['label']}")

    if a.write:
        if not res:
            print("uw_oi_delta: 0 simbolos utilizables — NO se escribe oi_delta.json", file=sys.stderr)
        else:
            write_atomic(OUT_F, {
                "_meta": {"generado": dt.datetime.now().isoformat(timespec="seconds"),
                          "source": a.source, "archive_date": date_s if a.source == "uw" else None,
                          "pair": a.pair, "n_syms": len(res),
                          "umbrales": {"R_NEW": R_NEW, "R_EXIT": R_EXIT, "R_CHURN": R_CHURN,
                                       "MIN_VOL": MIN_VOL},
                          "aviso": ("OI = cierre del dia anterior (OCC publica a la mañana "
                                    "siguiente): esto es DIA-SOBRE-DIA, jamas intradia. "
                                    "DESCRIPTIVO: sin probabilidad y sin voz.")},
                "por_symbolo": res})
            print(f"-> data/oi_delta.json ({len(res)} simbolos)")

    if fallos:
        print(f"-> {len(fallos)} simbolos sin ΔOI:", file=sys.stderr)
        for f in fallos[:12]:
            print("   " + f, file=sys.stderr)
        return 1 if not res else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
