#!/usr/bin/env python3
"""flow_scalp_backtest.py — MISION 1 (2026-07-23): el SPIKE de flujo NO es opcion
semanal a +100%; es un SCALP de minutos (espada-ballena). Este backtest mide,
con DATA REAL, si el spike de flujo tiene edge como FADE rapido.

Fuente flujo: data/backtest/flow_5min_<sym>.csv (fallback flow_intraday_<sym>.csv;
misma reconstruccion Polygon, formato epoch,volC_acum_dia,volP_acum_dia,pc,spot;
volumen ACUMULADO del dia -> el detector ve el RITMO igual que flow_pulse en vivo).
Fuente subyacente: data/backtest/bars3mo5m_<sym>.csv (5m).
Fuente opcion: Polygon (helpers de scripts/real_option_scorer.py).

Detector de spike (por barra, dentro del dia):
  dC = incremento de volC en la barra; dP idem puts. EMA(alfa=0.40) del propio dC/dP.
  SPIKE_CALLS: dC >= 3x EMA_prev(dC)  Y  dC >= 2x dP (dominancia)  Y  no-artefacto.
  SPIKE_PUTS : dP >= 3x EMA_prev(dP)  Y  dP >= 2x dC  Y  no-artefacto.
  Anti-artefacto: bilateral (ambos disparan) = mudo; dX > 50x EMA = mudo (glitch).
  Jerarquia capitanes: si un capitan (SMH memoria / SPY|QQQ mercado) disparo el lado
  OPUESTO en <=3 barras, se suprime el spike del nombre (nvda/mu) — evita fade contra
  el capitan. SPIKE_CALLS -> fade BAJISTA; SPIKE_PUTS -> fade ALCISTA.

Salidas: la curva de reversion (MFE por horizonte), WR scalp subyacente y opcion,
Wilson honesto, n declarado. Señal-solamente. Sin look-ahead (entrada = open de la
barra POSTERIOR al epoch del spike).
"""
import csv, os, sys, time, math

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

SYMS = ["spy", "qqq", "smh", "nvda", "mu"]
CAPTAINS = {"smh", "spy", "qqq"}
ALPHA = 0.40
SPIKE_MULT = 3.0
DOM = 2.0
ARTIFACT = 50.0
HORIZONS = [1, 2, 3, 6, 12]          # barras 5m -> 5,10,15,30,60 min
TP_LEVELS = [0.003, 0.005]           # +0.3% / +0.5% a favor del fade
STOP = 0.003                          # -0.3%
OPT_HORIZON_BARS = 6                  # ~30 min de prima 5m


def load_flow(sym):
    for stem in (f"flow_5min_{sym}", f"flow_intraday_{sym}"):
        p = f"data/backtest/{stem}.csv"
        if os.path.exists(p):
            rows = []
            for r in csv.reader(open(p)):
                if not r or not r[0][0].isdigit():
                    continue
                try:
                    rows.append((int(r[0]), float(r[1]), float(r[2])))
                except Exception:
                    continue
            rows.sort()
            return rows, os.path.basename(p)
    return [], None


def load_bars(sym):
    out = []
    p = f"data/backtest/bars3mo5m_{sym}.csv"
    for r in csv.reader(open(p)):
        if not r or not r[0][0].isdigit():
            continue
        out.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    out.sort()
    return out


def daykey(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def detect_spikes(flow):
    """Devuelve lista de (epoch, side) donde side in {CALLS,PUTS}."""
    spikes = []
    prevC = prevP = None
    prevday = None
    emaC = emaP = None
    nday = 0
    for (t, volC, volP) in flow:
        d = daykey(t)
        if d != prevday:
            prevday = d
            prevC = volC
            prevP = volP
            emaC = emaP = None
            nday = 0
            continue
        dC = max(volC - prevC, 0.0)
        dP = max(volP - prevP, 0.0)
        prevC, prevP = volC, volP
        nday += 1
        # necesita warmup (EMA previa)
        sig = None
        if emaC and emaP and nday >= 2:
            rC = dC / emaC if emaC > 0 else 0
            rP = dP / emaP if emaP > 0 else 0
            calls = rC >= SPIKE_MULT and dC >= DOM * max(dP, 1)
            puts = rP >= SPIKE_MULT and dP >= DOM * max(dC, 1)
            bilateral = calls and puts
            artifact = rC > ARTIFACT or rP > ARTIFACT
            if not bilateral and not artifact:
                if calls:
                    sig = "CALLS"
                elif puts:
                    sig = "PUTS"
        # actualizar EMA con el delta actual
        emaC = dC if emaC is None else ALPHA * dC + (1 - ALPHA) * emaC
        emaP = dP if emaP is None else ALPHA * dP + (1 - ALPHA) * emaP
        if sig:
            spikes.append((t, sig))
    return spikes


def captain_filter(all_spikes):
    """all_spikes: dict sym -> [(t,side)]. Suprime spike de NOMBRE si un capitan
    disparo el lado OPUESTO en <=3 barras (aprox 3h en flujo horario)."""
    WIN = 3 * 3600 + 600  # ventana temporal ~3 barras horarias + holgura
    cap_events = []  # (t, side_fade)  side_fade = direccion del fade del capitan
    for s in CAPTAINS:
        for (t, side) in all_spikes.get(s, []):
            cap_events.append((t, "DOWN" if side == "CALLS" else "UP"))
    cap_events.sort()
    kept = {}
    for sym, sp in all_spikes.items():
        if sym in CAPTAINS:
            kept[sym] = sp
            continue
        keep = []
        for (t, side) in sp:
            my = "DOWN" if side == "CALLS" else "UP"
            opp = any(abs(t - ct) <= WIN and cs != my for (ct, cs) in cap_events)
            if not opp:
                keep.append((t, side))
        kept[sym] = keep
    return kept


def wilson(w, n):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    z = 1.96
    d = 1 + z * z / n
    c = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = max(0.0, (p + z * z / (2 * n) - c) / d)
    hi = min(1.0, (p + z * z / (2 * n) + c) / d)
    return (lo, hi)


def scalp_underlying(bars, spikes):
    """Para cada spike: entrada = open de la barra posterior. MFE del fade por
    horizonte + resultado TP/stop. Devuelve (mfe_by_h, tp_stats, samples)."""
    ep = [b[0] for b in bars]
    import bisect
    mfe = {h: [] for h in HORIZONS}
    adverse = {h: [] for h in HORIZONS}
    tpres = {tp: [0, 0] for tp in TP_LEVELS}  # [wins, n]
    ret12 = []
    for (t, side) in spikes:
        i = bisect.bisect_right(ep, t)
        if i >= len(bars):
            continue
        entry = bars[i][1]  # open barra posterior (sin look-ahead)
        if entry <= 0:
            continue
        down = (side == "CALLS")  # fade bajista
        # MFE por horizonte
        for h in HORIZONS:
            seg = bars[i:i + h]
            if len(seg) < h:
                continue
            if down:
                fav = max((entry - b[3]) / entry for b in seg)  # low
                adv = max((b[2] - entry) / entry for b in seg)  # high (contra)
            else:
                fav = max((b[2] - entry) / entry for b in seg)
                adv = max((entry - b[3]) / entry for b in seg)
            mfe[h].append(fav)
            adverse[h].append(adv)
        # TP/stop sobre 12 barras, primer toque
        seg = bars[i:i + 12]
        r12 = None
        for tp in TP_LEVELS:
            res = None
            for b in seg:
                hi, lo = b[2], b[3]
                if down:
                    if (entry - lo) / entry >= tp:
                        res = 1; break
                    if (hi - entry) / entry >= STOP:
                        res = 0; break
                else:
                    if (hi - entry) / entry >= tp:
                        res = 1; break
                    if (entry - lo) / entry >= STOP:
                        res = 0; break
            if res is None:  # ni TP ni stop -> cierre final vs fade
                if seg:
                    last = seg[-1][4]
                    fav_ret = (entry - last) / entry if down else (last - entry) / entry
                    res = 1 if fav_ret > 0 else 0
                else:
                    res = 0
            tpres[tp][0] += res
            tpres[tp][1] += 1
        if seg:
            last = seg[-1][4]
            r12 = (entry - last) / entry if down else (last - entry) / entry
            ret12.append(r12)
    return mfe, adverse, tpres, ret12


def scalp_option(spikes, sym):
    """Opcion ATM real: fade CALLS->PUT, fade PUTS->CALL. Entrada al open de la
    barra 5m posterior; mide el PICO de prima en OPT_HORIZON_BARS (~30 min). WR."""
    try:
        import real_option_scorer as ros
    except Exception:
        return None
    wins = n = 0
    rets = []
    for (t, side) in spikes:
        cp = "P" if side == "CALLS" else "C"
        exp = ros.next_friday(t)
        # spot desde barras
        spot = None
        # resolver contrato ATM
        # usar spot aproximado desde el flujo? mejor barras:
        spot = _spot_at(sym, t)
        if not spot:
            continue
        otk, strike = ros.resolve(sym.upper(), exp, cp, spot)
        if not otk:
            continue
        day = time.strftime("%Y-%m-%d", time.localtime(t))
        pth = ros.opt_path(otk, day, exp)
        # entrada: primer bar de opcion con open valido en/after t
        entry = None
        idx = 0
        for k, (et, o, h, l, c) in enumerate(pth):
            if et >= t and o and o > 0.02:
                entry = (et, o); idx = k; break
        if not entry:
            continue
        e_t, e_px = entry
        window = pth[idx:idx + 1 + OPT_HORIZON_BARS]
        peak = max((h for (et, o, h, l, c) in window if h), default=None)
        if not peak:
            continue
        r = peak / e_px - 1.0
        rets.append(r)
        # scalp gana si el pico da >= +20% de prima (objetivo scalp realista)
        wins += int(r >= 0.20)
        n += 1
    if n == 0:
        return None
    return {"n": n, "wr20": wins / n, "mean_peak_ret": sum(rets) / n,
            "median_peak_ret": sorted(rets)[n // 2]}


_spot_cache = {}
def _spot_at(sym, t):
    if sym not in _spot_cache:
        import bisect
        bars = load_bars(sym)
        _spot_cache[sym] = ([b[0] for b in bars], bars)
    ep, bars = _spot_cache[sym]
    import bisect
    i = bisect.bisect_right(ep, t)
    if i >= len(bars):
        return None
    return bars[i][4]


def pct(x):
    return f"{x*100:+.2f}%"


def main():
    do_opt = "--opt" in sys.argv
    all_spikes = {}
    sources = {}
    for sym in SYMS:
        flow, src = load_flow(sym)
        sources[sym] = src
        if not flow:
            all_spikes[sym] = []
            continue
        all_spikes[sym] = detect_spikes(flow)
    kept = captain_filter(all_spikes)

    lines = []
    lines.append("# FLOW-SCALP backtest — MISION 1 (spike de flujo = scalp rapido)")
    lines.append("")
    lines.append(f"Generado: {time.strftime('%Y-%m-%d %H:%M')}  |  detector: spike>= {SPIKE_MULT}x EMA(a={ALPHA}), dom {DOM}x, anti-artefacto {ARTIFACT}x/bilateral")
    lines.append("")
    lines.append("Fuentes de flujo por simbolo:")
    for s in SYMS:
        lines.append(f"  - {s}: {sources[s] or 'FALTA'}  | spikes crudos={len(all_spikes[s])} | tras filtro-capitan={len(kept[s])}")
    lines.append("")

    # === agregados globales de reversion ===
    glob = {h: [] for h in HORIZONS}
    globadv = {h: [] for h in HORIZONS}
    globtp = {tp: [0, 0] for tp in TP_LEVELS}
    per_sym = {}
    total_spikes = 0
    for sym in SYMS:
        sp = kept[sym]
        total_spikes += len(sp)
        if not sp:
            continue
        bars = load_bars(sym)
        mfe, adv, tpres, ret12 = scalp_underlying(bars, sp)
        per_sym[sym] = (mfe, tpres, ret12, len(sp))
        for h in HORIZONS:
            glob[h] += mfe[h]
            globadv[h] += adv[h]
        for tp in TP_LEVELS:
            globtp[tp][0] += tpres[tp][0]
            globtp[tp][1] += tpres[tp][1]

    lines.append(f"## Curva de reversion (MFE favorable al FADE, subyacente) — n total spikes={total_spikes}")
    lines.append("")
    lines.append("| horizonte | min | n | MFE medio | MFE mediana | adverso medio | edge (MFE-adv) |")
    lines.append("|---|---|---|---|---|---|---|")
    for h in HORIZONS:
        v = glob[h]; a = globadv[h]
        if not v:
            continue
        vm = sum(v) / len(v)
        vmed = sorted(v)[len(v) // 2]
        am = sum(a) / len(a) if a else 0
        lines.append(f"| {h} barra | {h*5} | {len(v)} | {pct(vm)} | {pct(vmed)} | {pct(am)} | {pct(vm-am)} |")
    lines.append("")

    lines.append("## Scalp subyacente (TP a favor del fade / stop -0.3% / 12 barras)")
    lines.append("")
    lines.append("| TP | n | WR | Wilson95 | ")
    lines.append("|---|---|---|---|")
    for tp in TP_LEVELS:
        w, n = globtp[tp]
        if n == 0:
            continue
        lo, hi = wilson(w, n)
        lines.append(f"| +{tp*100:.1f}% | {n} | {w/n*100:.0f}% | [{lo*100:.0f}%, {hi*100:.0f}%] |")
    lines.append("")

    lines.append("### Por simbolo (WR al TP +0.3%)")
    lines.append("")
    lines.append("| sym | n | WR+0.3% | Wilson95 | ret medio 12b (fade) |")
    lines.append("|---|---|---|---|---|")
    for sym in SYMS:
        if sym not in per_sym:
            continue
        mfe, tpres, ret12, n = per_sym[sym]
        w, nn = tpres[0.003]
        if nn == 0:
            continue
        lo, hi = wilson(w, nn)
        rm = sum(ret12) / len(ret12) if ret12 else 0
        lines.append(f"| {sym} | {nn} | {w/nn*100:.0f}% | [{lo*100:.0f}%, {hi*100:.0f}%] | {pct(rm)} |")
    lines.append("")

    # === opcion real (opcional, red) ===
    if do_opt:
        lines.append("## Scalp OPCION ATM real (Polygon) — pico de prima en ~30 min")
        lines.append("")
        lines.append("| sym | n | WR>=+20% prima | pico medio | pico mediana |")
        lines.append("|---|---|---|---|---|")
        og_n = og_w = 0
        for sym in SYMS:
            sp = kept[sym]
            if not sp:
                continue
            r = scalp_option(sp, sym)
            if not r:
                lines.append(f"| {sym} | 0 | (sin datos) | | |")
                continue
            og_n += r["n"]; og_w += int(r["wr20"] * r["n"])
            lines.append(f"| {sym} | {r['n']} | {r['wr20']*100:.0f}% | {pct(r['mean_peak_ret'])} | {pct(r['median_peak_ret'])} |")
        if og_n:
            lo, hi = wilson(og_w, og_n)
            lines.append(f"| GLOBAL | {og_n} | {og_w/og_n*100:.0f}% [{lo*100:.0f}%,{hi*100:.0f}%] | | |")
        lines.append("")

    # veredicto
    w03, n03 = globtp[0.003]
    lo03, hi03 = wilson(w03, n03) if n03 else (0, 0)
    lines.append("## VEREDICTO")
    lines.append("")
    if n03 < 30:
        lines.append(f"**DATA-INSUFFICIENT** (n={n03} < 30). Muestra chica: NO es conclusion. "
                     "El detector reconstruye flujo HORARIO (no 5min fino en vivo) -> pocos spikes limpios en 3 meses.")
    else:
        edge = "SI" if lo03 > 0.5 else "NO"
        lines.append(f"Edge del scalp (TP+0.3%): WR {w03/n03*100:.0f}%, Wilson95 [{lo03*100:.0f}%,{hi03*100:.0f}%]. "
                     f"¿Batir 50% con confianza? {edge}.")
    lines.append("")

    out = "docs/FLOW-SCALP-2026-07-23.md"
    open(out, "w").write("\n".join(lines))
    print("\n".join(lines))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
