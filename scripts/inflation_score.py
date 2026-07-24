#!/usr/bin/env python3
"""inflation_score.py — score CONTINUO de "cuán inflada" está cada empresa de la flota
(orden Yunior 2026-07-24: "descarga technicals como Forward P/E, P/E... para tener idea de
cuán infladas están; inflado acelera la caída, bueno acelera la subida").

Doctrina de la casa (CLAUDE.md): "no queremos comprar una empresa inflada; Forward P/E entre
otros factores". Hoy `dip_alert.valuation_verdict()` solo da un GATE BINARIO (FPE>40 o PEG>2.5)
que silencia dips; esto lo convierte en un score CONTINUO [-1..+1] que alimenta la
probabilidad de las señales:
   score > 0  = INFLADA  -> amplifica señal BAJISTA / frena la ALCISTA
   score < 0  = BARATA/creciendo -> amplifica señal ALCISTA / frena la BAJISTA

Método MEDIDO, no hardcoded: z-score robusto (mediana + MAD) de Forward P/E y PEG DENTRO del
grupo sectorial del ticker (semis vs mega-cap: comparar TSLA con AAPL, no con MU), corregido
por crecimiento (EPS Growth Next Year alto justifica múltiplo), y aplastado con tanh a [-1,+1].
Degradación limpia: ETFs y tickers sin fundamentals válidos -> score None (no se inventan).

Fuente: data/finviz_valuation.csv (lo baja finviz_valuation.py, ya idempotente 1x/día 4am).
Salida: data/inflation_score.json  -> consumido por signal_conditioning.py y daily_fleet_plans.

Uso:
  python3 scripts/inflation_score.py            calcula + guarda + imprime tabla
  python3 scripts/inflation_score.py --quiet     solo guarda
SEÑAL-SOLAMENTE.
"""
import os, sys, csv, json, math, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
CSV = "data/finviz_valuation.csv"
OUT = "data/inflation_score.json"

# Grupos sectoriales para el z-score relativo (comparar peras con peras).
GROUPS = {
    "semis": ["NVDA", "AMD", "AVGO", "ASML", "TSM", "TXN", "QCOM", "LRCX", "INTC",
              "MU", "SKHY", "SNDK", "STX", "WDC", "NOK"],
    "megacap": ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "TSLA"],
}
# ETFs / vehículos sin P/E propio -> None (Finviz mete basura en esas columnas).
ETFS = {"QQQ", "SPY", "SMH", "GLD", "XLK", "EWY", "DRAM", "SPCX"}


def group_of(sym):
    for g, members in GROUPS.items():
        if sym in members:
            return g
    return "other"


def load_valuation():
    """ticker -> {fpe, pe, peg, pfcf, epsny} floats o None. Reusa el patrón de dip_alert."""
    out = {}
    try:
        lines = [l for l in open(CSV) if not l.startswith("#")]
    except FileNotFoundError:
        return out
    for row in csv.DictReader(lines):
        def num(k):
            v = (row.get(k) or "").replace("%", "").replace(",", "").strip()
            try:
                return float(v)
            except ValueError:
                return None
        out[row["Ticker"].upper()] = {
            "fpe": num("Forward P/E"), "pe": num("P/E"), "peg": num("PEG"),
            "pfcf": num("P/Free Cash Flow"), "epsny": num("EPS Growth Next Year")}
    return out


def _valid_fundamentals(sym, v):
    """True si el ticker tiene P/E-forward y PEG creíbles (filtra ETFs y basura shift-eada)."""
    if sym in ETFS:
        return False
    fpe, peg = v.get("fpe"), v.get("peg")
    # Un Forward P/E válido es un múltiplo positivo y no minúsculo (los % shift-eados de los
    # ETFs caen negativos o <2). PEG puede ser <0 sólo por EPS negativo -> descartar.
    if fpe is None or peg is None:
        return False
    if fpe <= 1.0 or fpe > 1000:
        return False
    if peg < 0:
        return False
    return True


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0.0
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2


def _mad(xs, med):
    """Median absolute deviation escalado a ~sigma (1.4826). Robusto a outliers como TSLA."""
    if not xs:
        return 1.0
    dev = _median([abs(x - med) for x in xs])
    return max(dev * 1.4826, 1e-6)


def compute():
    val = load_valuation()
    valid = {s: v for s, v in val.items() if _valid_fundamentals(s, v)}
    # estadísticos por grupo (mediana + MAD) para Forward P/E y PEG
    stats = {}
    for g in set(group_of(s) for s in valid):
        members = [s for s in valid if group_of(s) == g]
        if len(members) < 3:                      # grupo chico -> usa universo entero
            members = list(valid.keys())
        fpes = [valid[s]["fpe"] for s in members]
        pegs = [valid[s]["peg"] for s in members]
        mf, mp = _median(fpes), _median(pegs)
        stats[g] = dict(mf=mf, sf=_mad(fpes, mf), mp=mp, sp=_mad(pegs, mp))

    rows = {}
    for s, v in val.items():
        if s not in valid:
            rows[s] = dict(score=None, group=group_of(s),
                           note="sin fundamentals (ETF o dato inválido)")
            continue
        g = group_of(s)
        st = stats[g]
        zf = (v["fpe"] - st["mf"]) / st["sf"]     # + = más caro que sus pares
        zp = (v["peg"] - st["mp"]) / st["sp"]
        raw = 0.55 * zf + 0.45 * zp               # PEG ya normaliza por crecimiento
        # corrección por crecimiento explícito: EPS-growth alto rebaja la inflación percibida
        eps = v.get("epsny")
        growth_adj = 0.0
        if eps is not None:
            growth_adj = -max(-0.5, min(0.5, (eps - 20.0) / 60.0))   # >20% baja, <20% sube
        score = math.tanh(0.6 * raw + growth_adj)  # -> [-1,+1]
        rows[s] = dict(
            score=round(score, 3), group=g,
            fpe=v["fpe"], peg=v["peg"], pfcf=v.get("pfcf"), epsny=eps,
            inflada=bool(score > 0.33),
            barata=bool(score < -0.33),
            note=("INFLADA" if score > 0.33 else "BARATA/creciendo" if score < -0.33 else "neutra"))
    return rows, stats


def main():
    quiet = "--quiet" in sys.argv
    rows, stats = compute()
    meta = {"ts": time.time(), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_scored": sum(1 for r in rows.values() if r.get("score") is not None),
            "groups": {g: {k: round(x, 2) for k, x in st.items()} for g, st in stats.items()}}
    payload = {"_meta": meta, **rows}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=1)
    os.replace(tmp, OUT)
    if quiet:
        print(f"inflation_score OK: {meta['n_scored']} scored -> {OUT}")
        return
    print(f"=== INFLATION SCORE (medido, {meta['n_scored']} tickers) — {meta['at']} ===")
    print(f"{'sym':6s} {'grp':8s} {'fwdPE':>7s} {'PEG':>6s} {'epsNY%':>7s} {'score':>7s}  veredicto")
    scored = [(s, r) for s, r in rows.items() if r.get("score") is not None]
    for s, r in sorted(scored, key=lambda x: -(x[1]["score"])):
        eps = f"{r['epsny']:.0f}" if r.get("epsny") is not None else "  -"
        print(f"{s:6s} {r['group']:8s} {r['fpe']:>7.1f} {r['peg']:>6.2f} {eps:>7s} "
              f"{r['score']:>+7.2f}  {r['note']}")
    skipped = [s for s, r in rows.items() if r.get("score") is None]
    print(f"\nsin score (ETF/sin datos): {', '.join(sorted(skipped))}")


if __name__ == "__main__":
    main()
