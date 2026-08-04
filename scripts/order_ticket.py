#!/usr/bin/env python3
"""order_ticket.py — FICHA DE ORDEN 0DTE lista para que el HUMANO la ejecute en IBKR con un
tap (orden Yunior 2026-07-24: "comprar/vender 0DTE desde el chart, rápido y seguro, mejor que
TradingView"). NO ejecuta NADA: solo lee la cadena de opciones y arma la ficha con todos los
gates ya resueltos. La ley SEÑAL-SOLAMENTE queda intacta — el software prepara, el humano
da el clic final en IBKR.

Dado (símbolo, nivel-gatillo, lado buy/sell, tipo call/put) arma:
  - contrato 0DTE: strike más cercano al nivel, expiry más próxima (0DTE si existe hoy)
  - límite marketable (ask para comprar / bid para vender) + spread% (gate CLAUDE.md #4 <=5%)
  - size por presupuesto (<= $200 por contrato, ENMIENDA 2026-07-22 cualquier ticker de flota)
  - OI (>500 liquidez) y prob CONDICIONADA (signal_conditioning: hora×flota×inflación)
  - veredicto: GO / CAUTION / NO-GO con las razones

  build(sym, level, side, kind) -> dict con todo + `ticket` (str legible para voz/banner/chart)

Fuente: data/opt_chain_<sym>.txt (cache IBKR, refrescada por opt_chain_cache). Degrada limpio.
Uso CLI: python3 scripts/order_ticket.py NVDA 210 buy call
SEÑAL-SOLAMENTE.
"""
import os, sys, time, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
MAX_SPREAD_PCT = 5.0
MAX_AGE_S = 900
BUDGET_USD = float(os.environ.get("OPT_BUDGET_USD", "200"))
MIN_OI = 500


def _parse_chain(sym):
    path = os.path.join(REPO, "data", f"opt_chain_{sym.lower()}.txt")
    try:
        lines = open(path).readlines()
    except Exception:
        return None
    spot = epoch = None
    exps = []
    rows = []
    for ln in lines:
        if ln.startswith("#"):
            if "spot " in ln:
                try:
                    spot = float(ln.split("spot ")[1].split(" |")[0].split()[0])
                    epoch = int(ln.split("epoch ")[1].split(" |")[0])
                    exps = ln.split("exps ")[1].split()
                except Exception:
                    pass
            continue
        p = ln.split()
        if len(p) < 7:
            continue
        try:
            rows.append(dict(strike=float(p[0]), right=p[1], exp=p[2],
                             bid=float(p[3]), ask=float(p[4]),
                             vol=int(p[5]), oi=int(p[6]),
                             iv=float(p[7]) if len(p) > 7 else None,
                             delta=float(p[8]) if len(p) > 8 else None))
        except Exception:
            continue
    return dict(spot=spot, epoch=epoch, exps=exps, rows=rows)


CBOE_NBBO_MAX_AGE_S = 900.0


def _cboe_nbbo(sym, right, exp, strike):
    """(bid, ask, edad_s) del cache del sidecar CBOE, o None. Rancio (>15 min) = None."""
    path = os.path.join(REPO, "data", f"cboe_nbbo_{sym.lower()}.json")
    try:
        with open(path) as f:
            d = json.load(f)
        age = time.time() - float(d["asof"])
        if age > CBOE_NBBO_MAX_AGE_S:
            return None
        # clave del sidecar: "C|YYYYMMDD|strike" (exp de la cadena ya viene YYYYMMDD)
        q = d["quotes"].get("%s|%s|%g" % (right, exp, float(strike)))
        if not q:
            return None
        return float(q[0]), float(q[1]), age
    except (OSError, ValueError, KeyError, TypeError):
        return None


def build(sym, level, side, kind):
    """side: buy|sell ; kind: call|put. level: nivel-gatillo (precio del subyacente)."""
    sym = sym.upper(); side = side.lower(); kind = kind.lower()
    right = "C" if kind.startswith("c") else "P"
    ch = _parse_chain(sym)
    if not ch or not ch["rows"]:
        return dict(ok=False, verdict="NO-GO", why=["sin cadena de opciones fresca"],
                    ticket=f"❌ {sym}: sin cadena — no puedo armar ficha")
    age = time.time() - (ch["epoch"] or 0)
    exp = ch["exps"][0] if ch["exps"] else None       # 0DTE = expiry más próxima
    cand = [r for r in ch["rows"] if r["right"] == right and (exp is None or r["exp"] == exp)]
    if not cand:
        return dict(ok=False, verdict="NO-GO", why=[f"sin {kind}s 0DTE en la cadena"],
                    ticket=f"❌ {sym}: sin {kind}s 0DTE")
    # strike más cercano al nivel-gatillo
    c = min(cand, key=lambda r: abs(r["strike"] - float(level)))
    bid, ask = c["bid"], c["ask"]
    # IBKR usa bid/ask = -1.00 (o 0) como "sin cotización" -> opción ilíquida, no cotizable
    quote_ok = bid > 0 and ask > 0 and ask >= bid
    # RESPALDO CBOE (2026-08-04): sin IBKR la cadena Polygon trae 0 bid/ask en TODA la flota
    # (bidask_ok_pct 0.0000 en cabecera) y ninguna ficha podia armarse. CBOE es DELAYED ->
    # doctrina LATENCIA-FUENTES "bid/ask de respaldo": sirve para dimensionar y para el gate
    # de spread, pero JAMAS aprueba un GO (tope CAUTION mas abajo). Etiquetado siempre.
    nbbo_src = "chain"
    if not quote_ok:
        cb = _cboe_nbbo(sym, right, exp, c["strike"])
        if cb is not None:
            bid, ask, nbbo_age = cb
            quote_ok = bid > 0 and ask > 0 and ask >= bid
            nbbo_src = "cboe_delayed"
    if quote_ok:
        mid = (bid + ask) / 2
        spread_pct = round((ask - bid) / mid * 100, 1)
    else:
        mid = None; spread_pct = None
    limit = ask if side == "buy" else bid              # marketable: paga oferta / cobra demanda
    prem = round(limit * 100, 2) if limit and limit > 0 else 0
    size = max(1, int(BUDGET_USD // prem)) if prem > 0 else 0
    budget_ok = 0 < prem <= BUDGET_USD
    spread_ok = quote_ok and 0 < spread_pct <= MAX_SPREAD_PCT
    oi_ok = c["oi"] >= MIN_OI
    fresh = age <= MAX_AGE_S

    # prob condicionada: comprar call/vender put = alcista ; comprar put/vender call = bajista
    direction = 1 if (kind == "call") == (side == "buy") else -1
    prob = None; speak = False; cond_why = []
    try:
        import signal_conditioning as SC
        r = SC.conditioned_prob("ticket", sym, direction, 60)   # base 60 neutral -> condiciona
        prob = r["prob"]; speak = r["speak"]; cond_why = r["why"]
        veto = r["veto"]
    except Exception:
        veto = False

    why = []
    if not fresh:
        why.append(f"cadena vieja ({int(age)}s)")
    if not quote_ok:
        why.append("⛔ sin bid/ask válido — opción ilíquida, no cotizable")
    else:
        why.append(f"spread {spread_pct}% {'OK' if spread_ok else '⛔ >5% NO PAGAR'}")
    if not oi_ok:
        why.append(f"OI {c['oi']} < {MIN_OI} (poca liquidez)")
    if not budget_ok:
        why.append(f"prima ${prem} > ${BUDGET_USD:.0f} presupuesto")
    why += cond_why

    if nbbo_src == "cboe_delayed":
        why.append("spread de CBOE DELAYED — verifica el NBBO real en IBKR")

    # veredicto. Con NBBO delayed el techo es CAUTION: un GO exige cotizacion viva.
    if not spread_ok or veto or not fresh:
        verdict = "NO-GO"
    elif not budget_ok or not oi_ok or not speak or nbbo_src == "cboe_delayed":
        verdict = "CAUTION"
    else:
        verdict = "GO"

    action = f"{'COMPRA' if side == 'buy' else 'VENDE'} {size}x {sym} {c['strike']:g}{right} 0DTE"
    icon = '🟢' if verdict == 'GO' else '🟡' if verdict == 'CAUTION' else '🔴'
    if not quote_ok:
        ticket = (f"🔴 {sym} {c['strike']:g}{right} 0DTE — sin bid/ask válido (ilíquido), "
                  f"OI {c['oi']}. NO-GO. No cotizable.")
    else:
        etiqueta_nbbo = " [spread CBOE delayed]" if nbbo_src == "cboe_delayed" else ""
        ticket = (f"{icon} {action} @ límite ${limit:.2f} (prima ${prem:.0f}, spread {spread_pct}%"
                  f"{etiqueta_nbbo}, OI {c['oi']}, prob {prob if prob is not None else '?'}%) — "
                  f"{verdict}. Ejecuta TÚ en IBKR.")
    return dict(ok=True, verdict=verdict, sym=sym, side=side, kind=kind, nbbo_src=nbbo_src,
                strike=c["strike"], right=right, exp=exp, limit=round(limit, 2),
                premium=prem, size=size, spread_pct=spread_pct, spread_ok=spread_ok,
                oi=c["oi"], oi_ok=oi_ok, budget_ok=budget_ok, fresh=fresh,
                delta=c["delta"], prob=prob, speak=speak, direction=direction,
                level=float(level), spot=ch["spot"], why=why, ticket=ticket)


def _cli():
    a = sys.argv[1:]
    if len(a) < 4:
        print("uso: order_ticket.py SYM LEVEL buy|sell call|put"); return
    r = build(a[0], a[1], a[2], a[3])
    print(r["ticket"])
    for w in r.get("why", []):
        print(f"    · {w}")
    print("\n" + json.dumps({k: v for k, v in r.items() if k not in ("why",)}, default=str, indent=1))


if __name__ == "__main__":
    _cli()
