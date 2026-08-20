#!/usr/bin/env python3
"""low_iv_hunter.py — cazador de PRIMA BARATA a 10-15 DTE saltandose el bulto de earnings.

Orden Yunior 2026-08-12: "find contracts with low vix up to 10-15 dte to skip earnings high vix".

QUE PROBLEMA RESUELVE (medido el mismo dia sobre 6 nombres):
  CSCO con earnings esa tarde cotizaba IV ATM 127% a 2 dias y 69% a 9 dias, contra una HV20
  realizada del 32%. Comprar ahi es pagar 4x la volatilidad que el subyacente entrega de verdad,
  y el crush se lleva el 42-100% del boleto con el move MEDIANO. El mismo dia AMAT (earnings
  al dia siguiente) cotizaba 122% y KLAR 118%. La prima barata no estaba en ninguno de los tres:
  estaba en los vencimientos que NO contienen el evento.

METODO (3 filtros duros, en orden):
  1. VENCIMIENTO LIMPIO — si la fecha de earnings cae entre hoy y el vencimiento, ese vencimiento
     se DESCARTA entero. Es el filtro que pidio Yunior y el que mas prima ahorra.
  2. IV/HV — la unica medida de "cara o barata" que se puede calcular sin archivo historico de IV:
     IV ATM del vencimiento contra la volatilidad REALIZADA del subyacente (HV20 y HV60,
     close-to-close anualizada). IV/HV20 <= UMBRAL = el mercado cobra menos de lo que el nombre
     se mueve. Se publican las dos: un IV/HV20 bajo con IV/HV60 alto es una calma reciente, no
     una ganga.
  3. GATE DE SPREAD canonico de la casa (gate_core.hpp): spread <= 5% del MID, o peaje
     (ask-bid)/(|delta|*spot) <= 0.60%. mid < $0.20 = veto directo.

Y ademas se declara el BUMP de term-structure: IV del vencimiento corto / IV del largo. Un bump
> 1.25 con vencimiento limpio significa que el evento esta en OTRO vencimiento y este ya esta
al otro lado del crush — que es exactamente donde se quiere comprar.

LOTE FUERA DE SESION (~/CLAUDE.md): Python legitimo aqui. No esta en camino de señal, no
dispara nada, se corre a mano o por cron. Reglas de frontera aplicadas: rutas desde __file__,
ningun except devuelve un numero plausible (o el dato, o None y se CUENTA).

FUENTES: cadena + griegas + NBBO de CBOE (delayed y DESIGUAL — la edad se mide y se declara por
simbolo, ver docs/LATENCIA-FUENTES.md), spot de Finnhub, barras diarias de Polygon (HV),
calendario de earnings de Finnhub. Ninguna dispara una orden: esto SELECCIONA candidatos, el
print lo confirma IBKR.

USO:
    python3 scripts/low_iv_hunter.py                      # flota completa, 10-15 DTE
    python3 scripts/low_iv_hunter.py MRVL AVGO CRDO       # simbolos sueltos
    python3 scripts/low_iv_hunter.py --dte 7 20 --max-iv-hv 1.2 --budget 300
    python3 scripts/low_iv_hunter.py --json               # para encadenar
"""
import argparse
import datetime as dt
import json
import math
import os
import statistics
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

CBOE_CHAIN = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
CBOE_VIX = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"
FINNHUB_Q = "https://finnhub.io/api/v1/quote?symbol={sym}&token={k}"
FINNHUB_EARN = "https://finnhub.io/api/v1/calendar/earnings?from={a}&to={b}&symbol={sym}&token={k}"
POLY_AGG = ("https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{a}/{b}"
            "?adjusted=true&sort=asc&limit=200&apiKey={k}")

SPREAD_MAX_PCT = 5.0      # gate_core.hpp: (ask-bid)/mid
PEAJE_MAX_PCT = 0.60      # gate_core.hpp: (ask-bid)/(|delta|*spot), rescata delta alta
MID_MIN = 0.20            # medido: 0/821 contratos con mid<$0.20 pasaron el gate
CHAIN_MAX_AGE_S = 3 * 3600


def _env():
    """feeds.env -> dict. Sin key no se inventa: se levanta."""
    out = {}
    for p in (os.path.join(REPO, "feeds.env"), os.path.join(REPO, "config", "feeds.env")):
        if not os.path.exists(p):
            continue
        for line in open(p):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "ib-trader/low_iv_hunter"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def parse_occ(t):
    """'MRVL260814C00235000' -> (root, 'YYYYMMDD', 'C', 235.0). None si no parsea.

    Se cuenta desde el FINAL (6 fecha + 1 tipo + 8 strike = 15 fijos), no desde el primer
    digito: las raices AJUSTADAS llevan digito (CIFR1, SMCI2 tras split/spin-off) y el parser
    ingenuo partia por ese digito -> exp '20126081' y `int('C00003000')` reventando el barrido
    entero. Medido el 2026-08-12 sobre la cadena de CIFR."""
    if len(t) < 15 or t[-9] not in "CP":
        return None
    q = t[-15:]
    try:
        return t[:-15], "20" + q[:6], q[6], int(q[7:]) / 1000.0
    except ValueError:
        return None


def chain(sym):
    """Cadena CBOE -> (filas, edad_s del ULTIMO TRADE del subyacente, ts). None si no hay."""
    try:
        d = _get(CBOE_CHAIN.format(sym=sym))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None
    data = d.get("data") or {}
    opts = data.get("options") or []
    if not opts:
        return None
    ltt = data.get("last_trade_time")
    age = None
    if ltt:
        try:
            age = (dt.datetime.now() - dt.datetime.strptime(ltt[:19], "%Y-%m-%dT%H:%M:%S")).total_seconds()
        except ValueError:
            age = None
    rows = []
    for o in opts:
        p = parse_occ(o["option"])
        if not p:
            continue
        _, exp, right, strike = p
        rows.append(dict(exp=exp, right=right, strike=strike,
                         bid=float(o.get("bid") or 0), ask=float(o.get("ask") or 0),
                         iv=(float(o.get("iv") or 0) or None),
                         oi=float(o.get("open_interest") or 0),
                         vol=float(o.get("volume") or 0),
                         delta=float(o.get("delta") or 0)))
    return rows, age, d.get("timestamp")


def spot(sym, key):
    try:
        q = _get(FINNHUB_Q.format(sym=sym, k=key))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None, None
    c = q.get("c")
    if not c:                       # 0 = Finnhub sin dato. NO es un precio.
        return None, None
    return float(c), q.get("t")


def earnings_date(sym, key, horizon_days=90):
    """Proxima fecha de earnings, o None si la API no la da. None != 'no hay earnings':
    el consumidor decide, aqui no se afirma que el vencimiento este limpio."""
    a = dt.date.today().isoformat()
    b = (dt.date.today() + dt.timedelta(days=horizon_days)).isoformat()
    try:
        d = _get(FINNHUB_EARN.format(sym=sym, a=a, b=b, k=key))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None
    cal = d.get("earningsCalendar") or []
    if not cal:
        return None
    e = sorted(cal, key=lambda x: x["date"])[0]
    return e["date"], (e.get("hour") or "").lower()


def hist_vol(sym, key):
    """(HV20, HV60) close-to-close anualizadas. (None, None) si no hay barras suficientes."""
    b = (dt.date.today()).isoformat()
    a = (dt.date.today() - dt.timedelta(days=140)).isoformat()
    try:
        d = _get(POLY_AGG.format(sym=sym, a=a, b=b, k=key))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None, None
    res = d.get("results") or []
    cl = [x["c"] for x in res]
    if len(cl) < 25:
        return None, None
    r = [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]
    def hv(n):
        if len(r) < n:
            return None
        return statistics.pstdev(r[-n:]) * math.sqrt(252) * 100
    return hv(20), hv(60)


def atm_iv(rows, exp, S):
    """IV ATM del vencimiento = media call/put del strike mas cercano. None si no hay IV medida."""
    sub = [r for r in rows if r["exp"] == exp and r["iv"]]
    if not sub:
        return None
    ks = sorted({r["strike"] for r in sub})
    k = min(ks, key=lambda x: abs(x - S))
    ivs = [r["iv"] for r in sub if r["strike"] == k]
    return 100 * sum(ivs) / len(ivs) if ivs else None


def dte_of(exp):
    return (dt.date(int(exp[:4]), int(exp[4:6]), int(exp[6:])) - dt.date.today()).days


def gate(bid, ask, delta, S):
    """(pasa, spread_pct, peaje_pct). Canonico de gate_core.hpp: /MID, no /ask."""
    if ask <= 0 or bid <= 0:
        return False, None, None
    mid = (ask + bid) / 2
    if mid < MID_MIN:
        return False, 100 * (ask - bid) / mid, None
    spr = 100 * (ask - bid) / mid
    pj = 100 * (ask - bid) / (abs(delta) * S) if delta else None
    return (spr <= SPREAD_MAX_PCT or (pj is not None and pj <= PEAJE_MAX_PCT)), spr, pj


def hunt(sym, env, args, vix):
    k_fin, k_poly = env.get("FINNHUB_KEY"), env.get("POLYGON_KEY")
    out = dict(sym=sym, skip=None, expiries=[], contracts=[])
    S, _ = spot(sym, k_fin)
    if S is None:
        out["skip"] = "sin spot"
        return out
    out["spot"] = S
    ch = chain(sym)
    if ch is None:
        out["skip"] = "sin cadena CBOE"
        return out
    rows, age, ts = ch
    out["chain_ts"], out["chain_age_s"] = ts, age
    out["chain_stale"] = age is not None and age > CHAIN_MAX_AGE_S
    hv20, hv60 = hist_vol(sym, k_poly)
    out["hv20"], out["hv60"] = hv20, hv60
    if hv20 is None:
        out["skip"] = "sin HV (barras insuficientes)"
        return out
    ed = earnings_date(sym, k_fin)
    out["earnings"] = ed
    ed_date = dt.date.fromisoformat(ed[0]) if ed else None

    exps = sorted({r["exp"] for r in rows})
    ivs = {e: atm_iv(rows, e, S) for e in exps}
    lo, hi = args.dte
    # se MUESTRA la term structure hasta 45d (para ver donde esta el bulto), pero solo se
    # buscan contratos en la ventana pedida. Sin esto, "sin candidatos" no dice por que.
    desc = dict(fuera_ventana=0, earnings_dentro=0, prima_cara=0, oi=0, presupuesto=0,
                spread=0, delta=0)
    out["descartes"] = desc
    for e in exps:
        d = dte_of(e)
        if d < 0 or d > max(hi, 45):
            continue
        en_ventana = lo <= d <= hi
        iv = ivs.get(e)
        if iv is None:
            out["expiries"].append(dict(exp=e, dte=d, skip="sin IV medida", en_ventana=en_ventana))
            continue
        exp_date = dt.date(int(e[:4]), int(e[4:6]), int(e[6:]))
        sucio = ed_date is not None and dt.date.today() <= ed_date <= exp_date
        # bump de term structure contra el vencimiento limpio mas lejano que tengamos
        largos = [ivs[x] for x in exps if dte_of(x) > d + 20 and ivs.get(x)]
        bump = (iv / largos[0]) if largos else None
        rec = dict(exp=e, dte=d, iv_atm=iv, iv_hv20=iv / hv20,
                   iv_hv60=(iv / hv60 if hv60 else None), bump=bump,
                   earnings_dentro=sucio, en_ventana=en_ventana)
        out["expiries"].append(rec)
        if not en_ventana:
            desc["fuera_ventana"] += 1
            continue
        if sucio:
            desc["earnings_dentro"] += 1
            continue                                  # FILTRO 1: vencimiento con evento dentro
        if iv / hv20 > args.max_iv_hv:
            desc["prima_cara"] += 1
            continue                                  # FILTRO 2: prima cara contra lo realizado
        for r in rows:
            if r["exp"] != e:
                continue
            if r["oi"] < args.min_oi:
                desc["oi"] += 1
                continue
            if r["ask"] <= 0 or r["ask"] * 100 > args.budget:
                desc["presupuesto"] += 1
                continue
            if abs(r["delta"]) < args.min_delta or abs(r["delta"]) > args.max_delta:
                desc["delta"] += 1
                continue
            ok, spr, pj = gate(r["bid"], r["ask"], r["delta"], S)
            if not ok:
                desc["spread"] += 1
                continue                              # FILTRO 3: gate de spread de la casa
            be = r["strike"] + r["ask"] if r["right"] == "C" else r["strike"] - r["ask"]
            out["contracts"].append(dict(
                sym=sym, exp=e, dte=d, right=r["right"], strike=r["strike"],
                bid=r["bid"], ask=r["ask"], cost=round(r["ask"] * 100),
                spread_pct=round(spr, 1), peaje_pct=(round(pj, 2) if pj else None),
                oi=int(r["oi"]), vol=int(r["vol"]), iv=round(100 * (r["iv"] or 0), 1),
                iv_atm=round(iv, 1), iv_hv20=round(iv / hv20, 2), delta=round(r["delta"], 3),
                be=round(be, 2), need_pct=round(100 * (be - S) / S, 2)))
    out["contracts"].sort(key=lambda c: (c["iv_hv20"], c["spread_pct"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="prima barata 10-15 DTE, sin el bulto de earnings")
    ap.add_argument("syms", nargs="*", help="simbolos (default: data/fleet.txt)")
    ap.add_argument("--dte", nargs=2, type=int, default=[10, 15], metavar=("LO", "HI"))
    ap.add_argument("--max-iv-hv", type=float, default=1.15,
                    help="IV ATM / HV20 maximo (1.0 = el mercado cobra lo que el nombre se mueve)")
    ap.add_argument("--budget", type=float, default=200.0, help="$ maximos por contrato")
    ap.add_argument("--min-oi", type=int, default=200)
    ap.add_argument("--min-delta", type=float, default=0.15)
    ap.add_argument("--max-delta", type=float, default=0.45)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    env = _env()
    for need in ("FINNHUB_KEY", "POLYGON_KEY"):
        if not env.get(need):
            sys.exit(f"falta {need} en feeds.env — sin key no se inventa nada")

    syms = args.syms
    if not syms:
        fp = os.path.join(REPO, "data", "fleet.txt")
        syms = [s for s in open(fp).read().split() if s] if os.path.exists(fp) else []
    if not syms:
        sys.exit("sin universo: pasa simbolos o crea data/fleet.txt")

    try:
        v = _get(CBOE_VIX)["data"]
        vix, vix_chg = v.get("current_price"), v.get("price_change")
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError):
        vix, vix_chg = None, None

    res = [hunt(s, env, args, vix) for s in syms]

    if args.json:
        print(json.dumps(dict(vix=vix, vix_chg=vix_chg, dte=args.dte,
                              max_iv_hv=args.max_iv_hv, results=res), indent=1))
        return

    band = "n/d" if vix is None else ("CALM" if vix < 17 else "ELEVADO" if vix < 25 else "ALTO")
    print(f"VIX {vix} ({vix_chg}) banda {band}   ventana {args.dte[0]}-{args.dte[1]} DTE"
          f"   IV/HV20 <= {args.max_iv_hv}   presupuesto ${args.budget:.0f}")
    print("=" * 112)
    todos = []
    for r in res:
        if r.get("skip"):
            print(f"{r['sym']:>6}  — {r['skip']}")
            continue
        e = r.get("earnings")
        etxt = f"earnings {e[0]} {e[1]}" if e else "earnings: sin dato"
        stale = "  ⚠CADENA RANCIA" if r.get("chain_stale") else ""
        print(f"{r['sym']:>6}  spot {r['spot']:8.2f}  HV20 {r['hv20']:5.1f}%  HV60 "
              f"{(r['hv60'] or 0):5.1f}%  {etxt}{stale}")
        for x in r["expiries"]:
            w = "→" if x.get("en_ventana") else " "
            if x.get("skip"):
                print(f"       {w} {x['exp']} {x['dte']:>3}d  — {x['skip']}")
                continue
            mark = "🚫 earnings dentro" if x["earnings_dentro"] else (
                "✅ limpio" if x["iv_hv20"] <= args.max_iv_hv else "💸 prima cara")
            bump = f" bump {x['bump']:.2f}x" if x.get("bump") else ""
            print(f"       {w} {x['exp']} {x['dte']:>3}d  IV {x['iv_atm']:6.1f}%  "
                  f"IV/HV20 {x['iv_hv20']:5.2f}  IV/HV60 {(x['iv_hv60'] or 0):5.2f}{bump}  {mark}")
        d = r.get("descartes") or {}
        if any(d.values()):
            print("         descartes: " + "  ".join(f"{k}={v}" for k, v in d.items() if v))
        todos += r["contracts"]
    if not todos:
        print("\nSIN CANDIDATOS. No es un fallo: con esta ventana y este VIX no hay prima barata"
              " que pase el gate. NO-TRADE es posicion. (los descartes de arriba dicen por que)")
        return
    print("\n" + "=" * 112)
    print(f"{'sym':>6} {'exp':>9} {'dte':>4} {'K':>8} {'R':>2} {'bid':>5} {'ask':>5} {'$':>5} "
          f"{'spr%':>5} {'peaje':>6} {'OI':>6} {'vol':>5} {'IV%':>6} {'IV/HV':>6} {'delta':>6} {'BE':>8} {'need%':>7}")
    for c in sorted(todos, key=lambda x: (x["iv_hv20"], x["spread_pct"]))[:40]:
        print(f"{c['sym']:>6} {c['exp']:>9} {c['dte']:>4} {c['strike']:8g} {c['right']:>2} "
              f"{c['bid']:5.2f} {c['ask']:5.2f} {c['cost']:5.0f} {c['spread_pct']:5.1f} "
              f"{(c['peaje_pct'] or 0):6.2f} {c['oi']:6d} {c['vol']:5d} {c['iv']:6.1f} "
              f"{c['iv_hv20']:6.2f} {c['delta']:6.3f} {c['be']:8.2f} {c['need_pct']:+7.2f}")


if __name__ == "__main__":
    main()
