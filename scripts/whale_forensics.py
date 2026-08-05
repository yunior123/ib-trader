#!/usr/bin/env python3
"""whale_forensics.py — forense de ballenas: la metodologia del analisis MSFT 2026-08-04.

El flujo de prima intradia MIENTE solo (el "roll 460C->510C" no sobrevivio al OI): el
veredicto exige cruzar (1) per-strike UW del dia, (2) delta-OI overnight de las cadenas
Polygon archivadas, (3) gamma+charm por expiry. Lote de analisis (no camino de senal).

Uso:
  ./venv/bin/python scripts/whale_forensics.py MSFT
  ./venv/bin/python scripts/whale_forensics.py MSFT --fecha 2026-08-04 --prev 2026-08-03
  ./venv/bin/python scripts/whale_forensics.py MU --top 8
"""
import argparse
import glob
import json
import os
import sys
from datetime import date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(REPO, "data", "history")


def die(msg):
    sys.exit(f"whale_forensics: {msg} (fail-loud, nada se inventa)")


def _find_rows(obj):
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = _find_rows(v)
            if r is not None:
                return r
    return None


def load_per_strike(sym, fecha):
    p = os.path.join(HIST, fecha, f"uw_flow_per_strike_{sym.lower()}.json")
    if not os.path.exists(p):
        die(f"sin {p} — el per-strike UW de ese dia no esta archivado")
    rows = _find_rows(json.load(open(p)))
    return rows or die(f"{p} sin filas")


def load_oi(sym, fecha):
    """{(strike, expiry, right): OI} de chain_full_<sym>.json (Polygon, OI asentado)."""
    p = os.path.join(HIST, fecha, f"chain_full_{sym.lower()}.json")
    if not os.path.exists(p):
        die(f"sin {p} — cadena Polygon de ese dia no archivada")
    out = {}

    def walk(o):
        if isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            det = o.get("details") or {}
            if det.get("strike_price") is not None and det.get("contract_type") in ("call", "put"):
                k = (float(det["strike_price"]), det.get("expiration_date", "?"),
                     "C" if det["contract_type"] == "call" else "P")
                out[k] = float(o.get("open_interest") or 0)
            else:
                for v in o.values():
                    walk(v)
    walk(json.load(open(p)))
    return out or die(f"{p} sin contratos")


def tabla(headers, rows):
    w = [max(len(str(headers[i])), max((len(str(r[i])) for r in rows), default=0)) for i in range(len(headers))]
    sep = "  ".join("-" * x for x in w)
    print("  ".join(str(headers[i]).ljust(w[i]) for i in range(len(headers))))
    print(sep)
    for r in rows:
        print("  ".join(str(r[i]).ljust(w[i]) for i in range(len(r))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sym")
    ap.add_argument("--fecha", default=str(date.today()), help="dia del flujo (default hoy)")
    ap.add_argument("--prev", default="", help="dia del ASIENTO para delta-OI (default: siguiente dia archivado)")
    ap.add_argument("--top", type=int, default=10, help="strikes por volumen a mostrar")
    ap.add_argument("--min-doi", type=int, default=200, help="delta-OI minimo a listar")
    a = ap.parse_args()
    sym = a.sym.upper()

    # el OI del dia del flujo se ASIENTA overnight: ΔOI va de a.fecha al siguiente dia archivado
    sig = a.prev
    if not sig:
        dias = sorted(d for d in os.listdir(HIST)
                      if d > a.fecha and os.path.exists(os.path.join(HIST, d, f"chain_full_{sym.lower()}.json")))
        sig = dias[0] if dias else die(f"sin cadena archivada posterior a {a.fecha} para {sym} (el OI del flujo asienta al dia siguiente)")

    print(f"\n=== WHALE FORENSICS {sym} — flujo {a.fecha} · ΔOI {a.fecha} -> {sig} ===\n")

    # 1) per-strike del dia: volumen, lado agresor
    rows = load_per_strike(sym, a.fecha)
    flujo = []
    for r in rows:
        for right, vk, akk, bkk in (("C", "call_volume", "call_volume_ask_side", "call_volume_bid_side"),
                                    ("P", "put_volume", "put_volume_ask_side", "put_volume_bid_side")):
            v = int(r.get(vk) or 0)
            if v > 0:
                ask, bid = int(r.get(akk) or 0), int(r.get(bkk) or 0)
                lado = "COMPRA" if ask > bid * 1.2 else ("VENTA" if bid > ask * 1.2 else "mixto")
                flujo.append((float(r["strike"]), right, v, ask, bid, lado))
    flujo.sort(key=lambda x: -x[2])
    print(f"1) FLUJO DEL DIA (per-strike UW, top {a.top} por volumen; lado por ask/bid 1.2x):")
    tabla(("strike", "right", "vol", "al_ask", "al_bid", "lado"),
          [(f"{s:g}", r, f"{v:,}", f"{ak:,}", f"{bd:,}", ld) for s, r, v, ak, bd, ld in flujo[:a.top]])

    # 2) delta-OI por (strike, expiry): que quedo ABIERTO de verdad
    oi_a, oi_b = load_oi(sym, a.fecha), load_oi(sym, sig)
    top_strikes = {(s, r) for s, r, *_ in flujo[:a.top]}
    deltas = []
    for k in set(oi_a) | set(oi_b):
        d = oi_b.get(k, 0) - oi_a.get(k, 0)
        if abs(d) >= a.min_doi or (k[0], k[2]) in top_strikes and abs(d) > 0:
            deltas.append((k, oi_a.get(k, 0), oi_b.get(k, 0), d))
    deltas.sort(key=lambda x: -abs(x[3]))
    print(f"\n2) ΔOI OVERNIGHT (|Δ|>={a.min_doi} o strike del top-flujo). El OI asienta de noche:")
    print("   vol alto + ΔOI≈0 = INTRADIA/cierre compensado · vol VENTA + ΔOI>0 = APERTURA de cortos (overwriter)")
    tabla(("contrato", "OI_prev", "OI_hoy", "ΔOI", "lectura"),
          [(f"{k[0]:g}{k[2]} {k[1]}", f"{int(pa):,}", f"{int(pb):,}", f"{int(d):+,}",
            ("APERTURA" if d > 0 else "CIERRE") if abs(d) >= a.min_doi else "intradia")
           for k, pa, pb, d in deltas[:14]])

    # 3) gamma + charm por expiry (UW greek-exposure ya cacheado)
    try:
        ge = json.load(open(os.path.join(REPO, "data", "uw_gex_expiry.json")))["syms"][sym]
        tot = ge["net_gex_total"] or 1
        print(f"\n3) GAMMA+CHARM POR EXPIRY (UW, asof {ge.get('asof_date')}; net_gex_total {tot:,.0f}):")
        tabla(("expiry", "dte", "net_gex", "%tot", "net_charm", "lectura_charm"),
              [(r["expiry"], r["dte"], f"{r['net_gex']:,.0f}", f"{100*r['net_gex']/tot:.1f}%",
                f"{r['net_charm']/1e6:+.1f}M",
                "drift-UP al decaer (doctrina)" if r["net_charm"] > 0 else
                ("drift-DOWN al decaer (doctrina)" if r["net_charm"] < 0 else "-"))
               for r in ge["rows"][:8]])
        vier = next((r for r in ge["rows"] if r["dte"] <= 4 and r["expiry"].endswith(("07", "08", "14", "21"))), None)
        vivo = sum(r["net_gex"] for r in ge["rows"] if r["dte"] > 4)
        print(f"   gamma que SOBREVIVE mas alla de esta semana: {100*vivo/tot:.0f}%")
    except (OSError, KeyError, ValueError) as e:
        print(f"\n3) gamma/charm: NO MEDIBLE ({e.__class__.__name__}) — uw_gex_expiry.json sin {sym}")

    print("\n4) VEREDICTO: cruzar a mano — (a) prima dominante del dia, (b) ΔOI que la confirma o")
    print("   desmiente, (c) donde vive la gamma. Regla: prima sin ΔOI no es posicion; ΔOI manda.")


if __name__ == "__main__":
    main()
