#!/usr/bin/env python3
"""cboe_chain_snap.py — foto de cadena desde CBOE en el formato que ya leen todos.

PUENTE, no camino de senal: mueve bytes de CBOE al formato de foto del repo. Cero computo.

POR QUE EXISTE (medido 2026-08-23): Polygon dejo de servir /v3/snapshot/options (403 en TODOS
los simbolos) e IBKR esta apagado, asi que `data/opt_chain_<sym>.txt` llevaba desde el 14-ago
sin refrescarse y con el se quedaron ciegos gex_core, chart_levels y trace_cube. CBOE sirve la
cadena COMPLETA con gamma, delta, IV y OI por contrato, gratis y sin clave.

VENTAJA SOBRE TWS FUERA DE RTH: TWS escribe -1.00 en bid/ask/griegas con el mercado cerrado y
el lector lo trata como ausente (correcto). CBOE sigue publicando griegas y OI, asi que la foto
de fin de semana SIRVE para el mapa. Lo que NO da es realtime: es delayed y DESIGUAL entre
simbolos, por eso la cabecera lleva `src cboe` y el `last_trade_time` que declara la propia
CBOE. Ningun disparo puede colgar de esto (ver docs/LATENCIA-FUENTES.md).

Uso:
  ./venv/bin/python scripts/cboe_chain_snap.py QQQ SPY          # foto viva + historico
  ./venv/bin/python scripts/cboe_chain_snap.py --fleet          # todo data/fleet.txt
  ./venv/bin/python scripts/cboe_chain_snap.py QQQ --stdout     # no escribe nada
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
HIST = os.path.join(DATA, "history")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
INDICES = {"SPX", "VIX", "NDX", "RUT", "XSP"}
RE_OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def cboe_sym(sym):
    return "_" + sym.upper() if sym.upper() in INDICES else sym.upper()


def bajar(sym, timeout=45):
    url = "https://cdn.cboe.com/api/global/delayed_quotes/options/%s.json" % cboe_sym(sym)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def filas(doc, sym):
    """(spot, last_trade_time, [filas]) — levanta si falta el spot: sin spot no se firma el GEX."""
    d = doc.get("data") or {}
    spot = d.get("current_price") or d.get("close")
    if not spot or spot <= 0:
        raise ValueError("%s: cadena sin spot utilizable (%r)" % (sym, spot))
    out = []
    for o in d.get("options") or []:
        m = RE_OCC.match(o.get("option") or "")
        if not m:
            continue
        yy, mm, dd = m.group(2)[:2], m.group(2)[2:4], m.group(2)[4:]
        out.append({
            "strike": int(m.group(4)) / 1000.0,
            "right": m.group(3),
            "exp": "20%s%s%s" % (yy, mm, dd),
            "bid": o.get("bid"), "ask": o.get("ask"),
            "vol": o.get("volume"), "oi": o.get("open_interest"),
            # iv 0 NO es una volatilidad medida: CBOE la publica asi en los contratos sin
            # actividad. Se escribe como ausente para que nadie la lea como un dato.
            "iv": (o.get("iv") or None) if (o.get("iv") or 0) > 0 else None,
            "delta": o.get("delta"), "gamma": o.get("gamma"),
        })
    if not out:
        raise ValueError("%s: cadena sin contratos legibles" % sym)
    return float(spot), d.get("last_trade_time"), out


def texto(sym, spot, fuente_ts, rows, epoch):
    """Formato de foto del repo (chain_cube_archive.parse_ibkr_text + gex_core.parse_chain_header).

    La cabecera declara `fuente cboe` y la `band` REAL de los datos: sin band, gex_core aplica su
    default de 0,035 y recorta 530 strikes a 56 — y sobre una ventana estrecha el flip es el borde
    y el regimen sale al reves (medido en el repo el 2026-07-27)."""
    exps = sorted({r["exp"] for r in rows})
    local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))
    ks = [r["strike"] for r in rows]
    band = (max(ks) - min(ks)) / 2.0 / spot if len(ks) > 1 and spot else None
    con_g = sum(1 for r in rows if isinstance(r.get("gamma"), (int, float)))
    con_q = sum(1 for r in rows if isinstance(r.get("bid"), (int, float))
                and isinstance(r.get("ask"), (int, float)))
    spot_age = _edad(fuente_ts, epoch)
    cab = ["# opt_chain %s | epoch %d | %s | spot %.4f | exps %s"
           % (sym.upper(), epoch, local, spot, " ".join(exps[:12])),
           "# fuente cboe | spot_src cboe%s | band %.4f | greeks_ok_pct %.4f | bidask_ok_pct %.4f"
           " | fuente_ts %s | delayed y DESIGUAL: NO dispara ninguna orden"
           % ((" | spot_age %d" % spot_age) if spot_age is not None else "",
              band if band else 0.0, con_g / len(rows), con_q / len(rows), fuente_ts or "?"),
           "# strike right exp bid ask vol oi iv delta gamma"]
    cuerpo = []
    for r in sorted(rows, key=lambda x: (x["exp"], x["strike"], x["right"])):
        def n(v, d=2):
            # ausente se escribe -1, que es lo que el lector del repo entiende como "no hay".
            return ("%.*f" % (d, v)) if isinstance(v, (int, float)) else ("%.*f" % (d, -1))
        cuerpo.append(" ".join([
            "%.2f" % r["strike"], r["right"], r["exp"],
            n(r["bid"]), n(r["ask"]),
            "%d" % (r["vol"] or 0), "%d" % (r["oi"] or 0),
            n(r["iv"], 4), n(r["delta"], 4), n(r["gamma"], 6)]))
    return "\n".join(cab + cuerpo) + "\n"


def _edad(fuente_ts, epoch):
    """Segundos entre lo que declara CBOE y ahora. None si no se puede leer: la edad no se inventa."""
    if not fuente_ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return max(0, int(epoch - time.mktime(time.strptime(fuente_ts[:19], fmt))))
        except ValueError:
            continue
    return None


def escribir_atomico(path, contenido):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(contenido)
    os.replace(tmp, path)


def foto(sym, escribir=True):
    doc = bajar(sym)
    spot, fuente_ts, rows = filas(doc, sym)
    epoch = int(time.time())
    txt = texto(sym, spot, fuente_ts, rows, epoch)
    con_gamma = sum(1 for r in rows if isinstance(r.get("gamma"), (int, float)))
    if escribir:
        escribir_atomico(os.path.join(DATA, "opt_chain_%s.txt" % sym.lower()), txt)
        dia = time.strftime("%Y-%m-%d", time.localtime(epoch))
        hhmm = time.strftime("%H%M", time.localtime(epoch))
        escribir_atomico(os.path.join(HIST, dia, "opt_chain_%s_%s.txt" % (sym.lower(), hhmm)), txt)
    return {"sym": sym.upper(), "spot": spot, "contratos": len(rows),
            "con_gamma": con_gamma, "fuente_ts": fuente_ts, "bytes": len(txt)}


def main():
    ap = argparse.ArgumentParser(description="Foto de cadena desde CBOE")
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--fleet", action="store_true", help="todos los de data/fleet.txt")
    ap.add_argument("--mapa", action="store_true", help="todos los de data/universe_gamma.txt")
    ap.add_argument("--stdout", action="store_true", help="no escribe: saca la foto por pantalla")
    a = ap.parse_args()

    syms = list(a.syms)
    if a.fleet or a.mapa:
        f = "universe_gamma.txt" if a.mapa else "fleet.txt"
        syms += open(os.path.join(DATA, f)).read().split()
    if not syms:
        ap.error("da al menos un simbolo, o --fleet / --mapa")

    fallos = 0
    for sym in dict.fromkeys(s.upper() for s in syms):
        try:
            if a.stdout:
                doc = bajar(sym)
                spot, fts, rows = filas(doc, sym)
                sys.stdout.write(texto(sym, spot, fts, rows, int(time.time())))
                continue
            r = foto(sym)
            print("  %-6s spot %-10.2f %5d contratos  %5d con gamma  fuente %s"
                  % (r["sym"], r["spot"], r["contratos"], r["con_gamma"], r["fuente_ts"]))
        except Exception as e:
            fallos += 1
            print("  %-6s FALLO: %s: %s" % (sym.upper(), e.__class__.__name__, e), file=sys.stderr)
    if fallos:
        print("%d simbolo(s) sin foto" % fallos, file=sys.stderr)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
