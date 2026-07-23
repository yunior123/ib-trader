#!/usr/bin/env python3
"""bollinger_backtest.py — replica EXACTA de la logica de bollinger_alarm.py
sobre 30 dias de barras 1m (cache data/backtest/bars30d_<sym>.csv) y mide
forward honesto por señal:

Tipos (identicos al vigia):
  elastic  : pierce 1m + re-entrada, 5m NO reventado mismo lado -> tesis FADE
             hacia la media 1m.
  bandwalk : pierce 1m + re-entrada con 5m tambien fuera -> tesis CONTINUACION
             (NO fade). Exito = el fade HABRIA fallado / avance a favor.
  re15     : pierce 15m + re-entrada -> tesis elastico mayor hacia media 15m.

Metricas forward (30 barras 1m tras la señal, mismo dia):
  p_mid30 : elastic/re15 = P(toca la media en 30min). bandwalk = P(NO toca la
            media 1m en 30min) — continuacion aguanta.
  p_half  : elastic/re15 = P(avanza >=50% del gap a la media). bandwalk =
            P(avanza a favor del walk >= 50% del gap-a-media como magnitud).
  mfe/mae : medianos a 15 y 30 min EN LA DIRECCION DE LA TESIS, % del spot.

Replicacion fiel: BB(20,2) sobre closes[-21:-1], ventana 140 barras 1m para
la capa 1m/5m, 460 para 15m, bucket 15m PARCIAL incluido (igual que agg15 en
vivo), cooldown 30min por simbolo+lado, expiry pierce 600s (1m) / 2700s (15m),
RTH 9:35-15:55 ET, estado reseteado por dia (el vigia muere cada 15:55).
Nota: en vivo el escaneo cada 30s puede armar el pierce INTRA-barra; aqui una
barra que revienta (h>banda) y cierra dentro cuenta como pierce+re-entrada en
la misma barra (el escaneo de 30s la habria cazado fuera).

Grid honesto (todas las celdas se reportan): sigma {2.0, 2.5} x cooldown
{1800s, 900s}. La celda BASE (2.0, 1800) es la de produccion y alimenta
data/bollinger_probs.json. SEÑAL-SOLAMENTE: esto solo mide, jamas ordena.
"""
import json, math, os, statistics, sys
from zoneinfo import ZoneInfo

REPO = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
CACHE = os.path.join(REPO, "data", "backtest")
ET = ZoneInfo("America/New_York")
FWD = 30          # barras 1m forward requeridas


def load_bars(sym):
    path = os.path.join(CACHE, f"bars30d_{sym.lower()}.csv")
    if not os.path.exists(path):
        return None
    bars = []
    with open(path) as f:
        next(f)
        for ln in f:
            p = ln.strip().split(",")
            if len(p) >= 6:
                bars.append((int(p[0]), float(p[1]), float(p[2]),
                             float(p[3]), float(p[4])))
    return bars or None


def by_day(bars):
    days = {}
    for b in bars:
        import datetime as dt
        d = dt.datetime.fromtimestamp(b[0], ET)
        hm = d.hour * 100 + d.minute
        if 930 <= hm < 1600 and d.weekday() < 5:
            days.setdefault(d.date(), []).append(b)
    return [days[k] for k in sorted(days)]


def bb(closes, sigma):
    m = sum(closes) / len(closes)
    sd = (sum((c - m) ** 2 for c in closes) / len(closes)) ** .5
    return m - sigma * sd, m, m + sigma * sd


def agg_tf(bars, secs):
    out = {}
    for t, o, h, l, c in bars:
        k = t - t % secs
        if k not in out:
            out[k] = [o, h, l, c]
        else:
            out[k][1] = max(out[k][1], h)
            out[k][2] = min(out[k][2], l)
            out[k][3] = c
    return sorted(out.items())


def wilson_lb(p, n, z=1.96):
    if n == 0:
        return 0.0
    den = 1 + z * z / n
    ctr = p + z * z / (2 * n)
    adj = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (ctr - adj) / den


def detect_day(day_bars, sigma, cooldown):
    """Devuelve señales [(idx, tipo, lado, close, mid, mid15)] del dia."""
    import datetime as dt
    st = {}
    sigs = []
    for i in range(len(day_bars)):
        window = day_bars[:i + 1]
        d = dt.datetime.fromtimestamp(window[-1][0], ET)
        hm = d.hour * 100 + d.minute
        if hm < 935 or hm >= 1555:
            continue
        bars1 = window[-140:]
        if len(bars1) < 25:
            continue
        now = window[-1][0] + 60          # cierre de la barra actual
        closes = [c for *_, c in bars1[-21:-1]]
        lo, mid, up = bb(closes, sigma)
        t, o, h, l, c = bars1[-1]
        # capa 15m (ventana 460, bucket parcial incluido — igual que en vivo)
        A15 = agg_tf(window[-460:], 900)
        if len(A15) >= 21:
            cl15 = [v[3] for k, v in A15[-21:-1]]
            lo15, mid15, up15 = bb(cl15, sigma)
            h15, l15, c15 = A15[-1][1][1], A15[-1][1][2], A15[-1][1][3]
            for s15, p15, band15 in (("up15", h15 > up15, up15),
                                     ("dn15", l15 < lo15, lo15)):
                if p15:
                    back = c15 < band15 if s15 == "up15" else c15 > band15
                    if not back:
                        st[s15] = t
                    elif now - st.get(f"last_{s15}", 0) > cooldown:
                        st[f"last_{s15}"] = now
                        st[s15] = None
                        sigs.append((i, "re15", s15[:2], c15, mid, mid15))
                elif st.get(s15) and (now - st[s15]) > 2700:
                    st[s15] = None
        # 5m band-walk
        A5 = agg_tf(bars1, 300)
        walk_up = walk_dn = False
        if len(A5) >= 21:
            cl5 = [v[3] for k, v in A5[-21:-1]]
            lo5, _, up5 = bb(cl5, sigma)
            walk_up = A5[-1][1][3] > up5
            walk_dn = A5[-1][1][3] < lo5
        # capa 1m
        for side, pierced, band, walk in (("up", h > up, up, walk_up),
                                          ("dn", l < lo, lo, walk_dn)):
            if pierced:
                back_inside = c < band if side == "up" else c > band
                if not back_inside:
                    st[side] = t
                elif now - st.get(f"last_{side}", 0) > cooldown:
                    st[f"last_{side}"] = now
                    st[side] = None
                    sigs.append((i, "bandwalk" if walk else "elastic",
                                 side, c, mid, mid))
            elif st.get(side) and (now - st[side]) > 600:
                st[side] = None
    return sigs


def measure(day_bars, sig):
    """Metricas forward de una señal; None si <FWD barras restantes."""
    i, typ, side, c, mid, tgt_mid = sig
    fwd = day_bars[i + 1:i + 1 + FWD]
    if len(fwd) < FWD:
        return None
    tgt = tgt_mid if typ == "re15" else mid
    gap = abs(c - tgt)
    # tesis: elastic/re15 = fade hacia tgt; bandwalk = continuacion del walk
    fade_dir = -1 if side == "up" else +1      # up-pierce -> tesis bajista
    thesis = -fade_dir if typ == "bandwalk" else fade_dir

    def reached(price_level, direction, bars_slice):
        for _, _, h, l, _ in bars_slice:
            if direction < 0 and l <= price_level:
                return True
            if direction > 0 and h >= price_level:
                return True
        return False

    touch_mid = reached(tgt, fade_dir, fwd)
    if typ == "bandwalk":
        p_mid30 = 0 if touch_mid else 1        # exito = NO toca la media
        half_lvl = c + (0.5 * gap if thesis > 0 else -0.5 * gap)
        p_half = 1 if reached(half_lvl, thesis, fwd) else 0
    else:
        p_mid30 = 1 if touch_mid else 0
        half_lvl = c + (0.5 * gap if thesis > 0 else -0.5 * gap)
        p_half = 1 if reached(half_lvl, thesis, fwd) else 0

    def mfe_mae(bars_slice):
        hi = max(h for _, _, h, _, _ in bars_slice)
        lo_ = min(l for _, _, _, l, _ in bars_slice)
        if thesis > 0:
            return (hi - c) / c * 100, (c - lo_) / c * 100
        return (c - lo_) / c * 100, (hi - c) / c * 100

    mfe15, mae15 = mfe_mae(fwd[:15])
    mfe30, mae30 = mfe_mae(fwd)
    return dict(type=typ, side=side, p_mid30=p_mid30, p_half=p_half,
                mfe15=mfe15, mae15=mae15, mfe30=mfe30, mae30=mae30)


def run_config(fleet_days, sigma, cooldown):
    """-> {sym: {tipo: {n, trunc, p_mid30, p_half, medians...}}}"""
    res = {}
    for sym, days in fleet_days.items():
        acc = {}
        for day_bars in days:
            for sig in detect_day(day_bars, sigma, cooldown):
                m = measure(day_bars, sig)
                t = sig[1]
                a = acc.setdefault(t, dict(n=0, trunc=0, mid=0, half=0,
                                           mfe15=[], mae15=[], mfe30=[], mae30=[]))
                if m is None:
                    a["trunc"] += 1
                    continue
                a["n"] += 1
                a["mid"] += m["p_mid30"]
                a["half"] += m["p_half"]
                for k in ("mfe15", "mae15", "mfe30", "mae30"):
                    a[k].append(m[k])
        out = {}
        for t, a in acc.items():
            n = a["n"]
            p_mid = a["mid"] / n if n else 0.0
            p_half = a["half"] / n if n else 0.0
            out[t] = dict(
                n=n, trunc=a["trunc"],
                p_mid30=round(p_mid, 3), p_half=round(p_half, 3),
                wilson_lb=round(wilson_lb(p_mid, n), 3),
                mfe15=round(statistics.median(a["mfe15"]), 3) if n else None,
                mae15=round(statistics.median(a["mae15"]), 3) if n else None,
                mfe30=round(statistics.median(a["mfe30"]), 3) if n else None,
                mae30=round(statistics.median(a["mae30"]), 3) if n else None)
        res[sym] = out
    return res


def main():
    fleet = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    fleet_days, missing = {}, []
    for sym in fleet:
        bars = load_bars(sym)
        if bars is None:
            missing.append(sym)
            continue
        fleet_days[sym] = by_day(bars)

    grid = {}
    for sigma in (2.0, 2.5):
        for cd in (1800, 900):
            key = f"s{sigma}_cd{cd // 60}"
            print(f"[grid] {key} ...", flush=True)
            grid[key] = run_config(fleet_days, sigma, cd)

    out = dict(generated=os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip(),
               days=30, fwd_min=FWD, missing=missing, grid=grid)
    path = os.path.join(CACHE, "bollinger_backtest_grid.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"grid -> {path}  (missing: {missing or 'ninguno'})")

    # probs de produccion (sigma 2.0, cooldown 30) -> data/bollinger_probs.json
    base = grid["s2.0_cd30"]
    probs = {}
    for sym, types in base.items():
        e = {}
        for t in ("elastic", "bandwalk", "re15"):
            d = types.get(t)
            if d is None:
                e[t] = dict(n=0, p_mid30=0.0, p_half=0.0, enabled=False)
            else:
                e[t] = dict(n=d["n"], p_mid30=d["p_mid30"], p_half=d["p_half"],
                            wilson_lb=d["wilson_lb"],
                            enabled=bool(d["p_mid30"] >= 0.55 and d["n"] >= 8))
        probs[sym] = e
    ppath = os.path.join(REPO, "data", "bollinger_probs.json")
    with open(ppath, "w") as f:
        json.dump(probs, f, indent=1)
    print(f"probs -> {ppath}")


if __name__ == "__main__":
    main()
