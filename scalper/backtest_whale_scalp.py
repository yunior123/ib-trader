#!/usr/bin/env python3
"""backtest_whale_scalp.py — estudio HONESTO de la tactica espada-ballena.

Une las alertas 🐋 reales (Desktop trading-signals) con las barras 1m de QQQ
y mide el retorno en la DIRECCION DEL FADE (CALLS->corto/PUT, PUTS->largo/CALL)
a +1/+2/+5/+15 min. Convierte a P&L de opcion 0DTE primer-OTM via BS con
costos completos (spread + comisiones $1.30 RT).

HONESTIDAD (leer antes de creer):
 - granularidad 1 MINUTO: la mecanica de 2.5s/30s/60s NO es medible aqui;
   eso se valida en sim (--replay / sim_feed). Esto mide si el fade 1-5 min
   tiene edge direccional tras costos.
 - n ~ 15-25 alertas en scope = Wilson CI de +/-20 pts. Veredicto esperado:
   DATA-INSUFFICIENT -> acumular con whale_flow_hist.jsonl (hook 2026-07-21)
   >=2 semanas antes de cualquier go/no-go.
 - max 6 variantes (3 holds x 2 spreads) para no overfittear 43 puntos.

Uso: python3 scalper/backtest_whale_scalp.py [--out docs/BACKTEST-WHALE-SCALP-2026-07.md]
"""
import argparse, math, os, re, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPACT = {"QQQ", "NVDA", "MSFT", "AAPL", "AVGO", "AMZN", "META", "GOOGL", "TSLA", "MU"}
COMMISSION_RT = 1.30
HOLDS_MIN = [1, 2, 5]
SPREADS = [0.03, 0.05]
IV_BY_HOUR = {9: 0.28, 10: 0.24, 11: 0.20, 12: 0.18, 13: 0.18, 14: 0.20, 15: 0.26}

def N(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))

def bs(S, K, T, iv, right):
    if T <= 0 or iv <= 0:
        return max(0.0, (S - K) if right == "C" else (K - S))
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / sq
    d2 = d1 - sq
    return S * N(d1) - K * N(d2) if right == "C" else K * N(-d2) - S * N(-d1)

def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (p, max(0.0, c - h), min(1.0, c + h))

def load_bars():
    bars = {}
    with open(os.path.join(REPO, "data", "bars_qqq_ibkr.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) >= 6:
                ep = int(float(p[0]))
                bars[ep - ep % 60] = tuple(float(x) for x in p[1:5])
    return bars

def load_alerts():
    rx = re.compile(r"^(\d\d):(\d\d):(\d\d) \| 🐋 BALLENA (CALLS|PUTS) \| ([A-Z]+):")
    out = []
    d = os.path.expanduser("~/ib-trader/data/trading-signals")
    for fn in sorted(os.listdir(d)):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})\.txt$", fn)
        if not m:
            continue
        day0 = int(time.mktime((int(m[1]), int(m[2]), int(m[3]), 0, 0, 0, 0, 0, -1)))
        for line in open(os.path.join(d, fn), encoding="utf-8"):
            a = rx.match(line)
            if a:
                ep = day0 + int(a[1]) * 3600 + int(a[2]) * 60 + int(a[3])
                out.append({"ep": ep, "hh": int(a[1]), "side": a[4], "sym": a[5], "day": fn[:10]})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "BACKTEST-WHALE-SCALP-2026-07.md"))
    a = ap.parse_args()
    bars = load_bars()
    alerts = load_alerts()
    in_scope = [x for x in alerts if x["sym"] in IMPACT]
    skipped_sym = len(alerts) - len(in_scope)
    # ventanas del scalper: 9:45-11:30, 14:00-15:30
    def in_window(ep):
        lt = time.localtime(ep)
        hm = lt.tm_hour * 100 + lt.tm_min
        return (945 <= hm < 1130) or (1400 <= hm < 1530)
    tradeable = [x for x in in_scope if in_window(x["ep"])]

    rows, results = [], {}
    for hold in HOLDS_MIN:
        for spr in SPREADS:
            results[(hold, spr)] = []
    used = 0
    for al in tradeable:
        m0 = al["ep"] - al["ep"] % 60
        if m0 not in bars:
            continue
        S0 = bars[m0][3]  # close del minuto de la alerta ~ entrada tras el wait
        right = "P" if al["side"] == "CALLS" else "C"
        K = math.floor(S0) if right == "P" else math.ceil(S0)
        lt = time.localtime(al["ep"])
        iv = IV_BY_HOUR.get(lt.tm_hour, 0.20)
        secs_to_close = max((16 - lt.tm_hour) * 3600 - lt.tm_min * 60 - lt.tm_sec, 60)
        T0 = secs_to_close / (365.0 * 24 * 3600)
        prem0 = bs(S0, K, T0, iv, right)
        if prem0 > 2.00 or prem0 < 0.03:
            continue  # fuera del presupuesto del bot (primer OTM <= $2.00)
        used += 1
        row = {"al": al, "S0": S0, "K": K, "right": right, "prem0": prem0, "fwd": {}}
        for hold in HOLDS_MIN:
            mh = m0 + hold * 60
            if mh not in bars:
                continue
            S1 = bars[mh][3]
            T1 = max(T0 - hold * 60 / (365.0 * 24 * 3600), 0)
            prem1 = bs(S1, K, T1, iv, right)
            row["fwd"][hold] = (S1, prem1)
            for spr in SPREADS:
                # compra al ask (mid+spr/2), vende al bid (mid-spr/2)
                pnl = ((prem1 - spr / 2) - (prem0 + spr / 2)) * 100 - COMMISSION_RT
                results[(hold, spr)].append(pnl)
        rows.append(row)

    # tambien: retorno del subyacente en fade a +15 para contexto
    fade15 = []
    for r in rows:
        m0 = r["al"]["ep"] - r["al"]["ep"] % 60
        if m0 + 900 in bars:
            d = bars[m0 + 900][3] - r["S0"]
            fade15.append(-d if r["right"] == "P" else d)  # fade: PUT gana si cae... signo:
    # OJO: right P = apostamos caida -> fade return = S0 - S1 = -d cuando right P
    # (arreglado arriba: -d para P, +d para C... d = S1-S0; P gana si d<0 -> -d>0 correcto)

    L = []
    L.append("# Backtest espada-ballena — 0DTE QQQ primer-OTM (2026-07)")
    L.append("")
    L.append("**Criterio pre-registrado**: pasar a shadow-sim en vivo si expectancy neta > 0")
    L.append("en >=1 horizonte Y el limite inferior Wilson 95% del WR > 50%. Si n < 30: DATA-INSUFFICIENT.")
    L.append("")
    L.append(f"- Alertas 🐋 totales: {len(alerts)} | en IMPACT_SYMS: {len(in_scope)} "
             f"(descartadas por simbolo: {skipped_sym}) | en ventanas del bot: {len(tradeable)} "
             f"| con barra y premium valido: {used}")
    L.append(f"- Granularidad: **1 minuto** — la mecanica de segundos NO se mide aqui (se valida en sim).")
    L.append(f"- Premium sintetico BS (IV por hora {IV_BY_HOUR}), costos: spread completo + ${COMMISSION_RT:.2f} RT.")
    L.append("")
    L.append("| hold | spread | n | WR | Wilson 95% | media $ | mediana $ | total $ |")
    L.append("|---|---|---|---|---|---|---|---|")
    verdict_pass = False
    for hold in HOLDS_MIN:
        for spr in SPREADS:
            pnls = results[(hold, spr)]
            n = len(pnls)
            wins = sum(1 for p in pnls if p > 0)
            p, lo, hi = wilson(wins, n)
            mean = sum(pnls) / n if n else 0
            med = sorted(pnls)[n // 2] if n else 0
            L.append(f"| {hold}m | {spr*100:.0f}c | {n} | {p*100:.0f}% | [{lo*100:.0f}%, {hi*100:.0f}%] "
                     f"| {mean:+.2f} | {med:+.2f} | {sum(pnls):+.2f} |")
            if n >= 30 and mean > 0 and lo > 0.5:
                verdict_pass = True
    L.append("")
    if fade15:
        mf = sum(fade15) / len(fade15)
        wf = sum(1 for x in fade15 if x > 0)
        L.append(f"Contexto subyacente: fade a +15m gana {wf}/{len(fade15)} veces, media {mf:+.3f} $QQQ.")
    L.append("")
    n_any = max(len(results[(h, s)]) for h in HOLDS_MIN for s in SPREADS) if rows else 0
    if verdict_pass:
        L.append("## VEREDICTO: PASA el criterio — proceder a shadow-sim en vivo (fills simulados).")
    else:
        L.append(f"## VEREDICTO: **DATA-INSUFFICIENT** (n={n_any} < 30 o edge no separable de ruido).")
        L.append("Accion: dejar acumular `data/whale_flow_hist.jsonl` + `data/nbbo_hist_qqq_*.txt`")
        L.append("(hooks activos desde 2026-07-21) >=2 semanas y re-correr. Mientras: shadow-sim")
        L.append("diario con `--sim --data data` para validar mecanica, SIN veredicto de edge.")
    L.append("")
    L.append("### Detalle por alerta (entrada = close del minuto de la alerta)")
    L.append("")
    L.append("| dia | hora | sym | lado | K | prem0 | +1m | +2m | +5m |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        al = r["al"]
        f = lambda h: f"{(r['fwd'][h][1] - r['prem0']) * 100:+.0f}c" if h in r["fwd"] else "—"
        lt = time.localtime(al["ep"])
        L.append(f"| {al['day']} | {lt.tm_hour:02d}:{lt.tm_min:02d} | {al['sym']} | {al['side']} "
                 f"| {r['K']}{r['right']} | ${r['prem0']:.2f} | {f(1)} | {f(2)} | {f(5)} |")
    out = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write(out)
    print(out)
    print(f"-> {a.out}")

if __name__ == "__main__":
    main()
