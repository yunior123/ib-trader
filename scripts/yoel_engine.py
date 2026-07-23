#!/usr/bin/env python3
"""yoel_engine.py — ENGINE YOEL PURO (2026-07-23, Mision 3).

Implementa las estrategias MECANIZABLES del libro de Yoel Sardinas TAL CUAL,
top-down 15m -> 1H -> 1D, SIN stop (la prima es la perdida maxima), TP +100%.
Reusa la geometria ya VALIDADA en yoel_faithful_backtest.py (rebote 3-TF, iman)
y yoel_real_options_backtest.py (rebote fiel: DIA=tendencia, HORA=correccion,
toque SMA20 diaria).

Estrategias implementadas (las que salen de OHLCV puro, sin trendlines a mano):
  S1 rebote_sma20  — confluencia 1H+1D mismo sentido, HORA cruza su SMA20 de
                     vuelta y el precio toca la SMA20 DIARIA (rebote punto medio).
  S2 iman          — precio lejos de la media (>=2 ATR) + 15m FUERA de banda BB +
                     volumen>MA50 + vela de reversion, TF mayores en contra -> fade
                     hacia la media (efecto iman de Yoel).
  S3 cambio_tend   — la SMA20 de 1H voltea de pendiente y el precio la cruza,
                     confirmado por 15m -> operar la nueva tendencia (cambio de
                     tendencia con ruptura de estructura).
  S4 fuera_banda   — la primera vela del dia abre/cierra FUERA de la BB(20,2)
                     DIARIA -> fade de vuelta a la banda (fuera-de-banda apertura).

Emite el FORMATO COMPARTIDO de señales para real_option_scorer.py:
    epoch,sym,side,kind,ref_px,target_px,stop_px   (side LONG->CALL, SHORT->PUT)
-> data/backtest/signals_yoel_pure.csv

Señal-solamente. Sin look-ahead: cada gatillo usa solo barras CERRADAS <= t y la
referencia de entrada es el OPEN de la barra siguiente. Muestra chica se declara.
"""
import csv, glob, math, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

# ------------------------------------------------------------------ carga/agg
def load(sym):
    R = []
    try:
        for r in csv.reader(open(f"data/backtest/bars3mo5m_{sym}.csv")):
            try:
                R.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
            except Exception:
                continue
    except Exception:
        return []
    return R

def agg(R, secs):
    out = {}
    for t, o, h, l, c, v in R:
        k = t - t % secs
        if k not in out:
            out[k] = [t, o, h, l, c, v]
        else:
            b = out[k]; b[2] = max(b[2], h); b[3] = min(b[3], l); b[4] = c; b[5] += v
    return [tuple(v) for k, v in sorted(out.items())]

# ------------------------------------------------------------- indicadores TF
def _idx_at(times, t):
    idx = -1
    for k in range(len(times)):
        if times[k] <= t:
            idx = k
        else:
            break
    return idx

def sma_dir_at(closes, times, t, n=20):
    """(sma, subiendo?, px, px_prev, idx) del TF en t usando barras cerradas <= t."""
    idx = _idx_at(times, t)
    if idx < n:
        return None
    mn = sum(closes[idx - n + 1:idx + 1]) / n
    mp = sum(closes[idx - n:idx]) / n
    return mn, (mn > mp), closes[idx], (closes[idx - 1] if idx > 0 else closes[idx]), idx

def bb_at(closes, times, t, n=20, k=2.0):
    """(mid, upper, lower, px, idx) BB(n,k) del TF en t, barras cerradas <= t."""
    idx = _idx_at(times, t)
    if idx < n:
        return None
    win = closes[idx - n + 1:idx + 1]
    mid = sum(win) / n
    var = sum((x - mid) ** 2 for x in win) / n
    sd = math.sqrt(var)
    return mid, mid + k * sd, mid - k * sd, closes[idx], idx

# ------------------------------------------------------------------ detector
def detect(sym):
    """devuelve lista de señales (epoch_ref, side, kind, ref_px). ref_px = open de
    la barra 5m siguiente al gatillo (sin look-ahead)."""
    R = load(sym)
    if len(R) < 300:
        return []
    M15 = agg(R, 900); H = agg(R, 3600); D = agg(R, 86400)
    M15t = [b[0] for b in M15]; M15c = [b[4] for b in M15]; M15v = [b[5] for b in M15]
    M15o = [b[1] for b in M15]; M15h = [b[2] for b in M15]; M15l = [b[3] for b in M15]
    Hc = [b[4] for b in H]; Ht = [b[0] for b in H]
    Dc = [b[4] for b in D]; Dt = [b[0] for b in D]
    Do = [b[1] for b in D]; Dtt = [b[0] for b in D]

    # mapa epoch 5m -> open de la barra 5m siguiente (referencia de entrada)
    R5t = [x[0] for x in R]; R5o = [x[1] for x in R]
    def next_open(t):
        for j in range(len(R5t)):
            if R5t[j] > t:
                return R5o[j]
        return None

    sigs = []
    last = {"rebote_sma20": -10**9, "iman": -10**9, "cambio_tend": -10**9, "fuera_banda": -10**9}
    COOL = 3600  # 1 gatillo por estrategia por hora como maximo

    # --- recorrido por barras 15m cerradas (el marco de gatillo de Yoel) ---
    for gi in range(21, len(M15) - 1):
        t = M15t[gi]
        px = M15c[gi]; op = M15o[gi]; hi = M15h[gi]; lo = M15l[gi]
        green = px > op
        vma = sum(M15v[gi - 50:gi]) / 50 if gi >= 50 else None
        vol_ok = bool(vma and M15v[gi] > vma)
        # ATR 15m (14)
        atr = sum(max(M15h[j] - M15l[j], abs(M15h[j] - M15c[j - 1]), abs(M15l[j] - M15c[j - 1]))
                  for j in range(gi - 14, gi)) / 14 if gi >= 15 else None

        dr = sma_dir_at(Dc, Dt, t); hr = sma_dir_at(Hc, Ht, t)
        m15 = sma_dir_at(M15c, M15t, t)
        bb15 = bb_at(M15c, M15t, t)
        if not dr or not hr or not m15 or not bb15 or not atr:
            continue
        dsma, dup, dpx, dprev, didx = dr
        hsma, hup, hpx, hprev, hidx = hr
        msma, mup, mpx, mprev, midx = m15
        bmid, bup, blo, bpx, bidx = bb15

        # ---------- S1 rebote_sma20 (rebote punto medio, confluencia 1H+1D) ----------
        near_daily = abs(dpx - dsma) / dsma <= 0.006
        if t - last["rebote_sma20"] >= COOL:
            if dup and near_daily and hpx > hsma and hprev <= hsma:      # dia up, hora corrige y recupera
                ref = next_open(t)
                if ref: sigs.append((t, "LONG", "rebote_sma20", ref)); last["rebote_sma20"] = t; continue
            if (not dup) and near_daily and hpx < hsma and hprev >= hsma:
                ref = next_open(t)
                if ref: sigs.append((t, "SHORT", "rebote_sma20", ref)); last["rebote_sma20"] = t; continue

        # ---------- S2 iman (precio lejos + 15m fuera de banda + vol>MA50 + reversion) ----------
        dist = (mpx - msma) / atr
        if t - last["iman"] >= COOL and vol_ok:
            # sobre-extendido ABAJO -> imán tira hacia arriba -> CALL
            if dist <= -2.0 and bpx <= blo and green and not hup:
                ref = next_open(t)
                if ref: sigs.append((t, "LONG", "iman", ref)); last["iman"] = t; continue
            # sobre-extendido ARRIBA -> imán tira hacia abajo -> PUT
            if dist >= 2.0 and bpx >= bup and (not green) and hup:
                ref = next_open(t)
                if ref: sigs.append((t, "SHORT", "iman", ref)); last["iman"] = t; continue

        # ---------- S3 cambio_tend (la SMA20 de 1H voltea pendiente y el precio la cruza) ----------
        if t - last["cambio_tend"] >= COOL and hidx >= 22:
            # pendiente 1H previa vs ahora
            m_now = sum(Hc[hidx - 19:hidx + 1]) / 20
            m_old = sum(Hc[hidx - 21:hidx - 1]) / 20
            slope_up = m_now > m_old
            # cruce de precio por la SMA20 1H en esta ventana + 15m acompaña
            crossed_up = hpx > hsma and hprev <= hsma
            crossed_dn = hpx < hsma and hprev >= hsma
            if slope_up and crossed_up and mup and green:
                ref = next_open(t)
                if ref: sigs.append((t, "LONG", "cambio_tend", ref)); last["cambio_tend"] = t; continue
            if (not slope_up) and crossed_dn and (not mup) and (not green):
                ref = next_open(t)
                if ref: sigs.append((t, "SHORT", "cambio_tend", ref)); last["cambio_tend"] = t; continue

        # ---------- S4 fuera_banda (primera vela del dia fuera de la BB diaria) ----------
        # gatillo solo en la 1a barra 15m del dia de sesion
        is_first = (gi == 0) or (M15t[gi] // 86400 != M15t[gi - 1] // 86400)
        if is_first and t - last["fuera_banda"] >= COOL:
            bbd = bb_at(Dc, Dt, t)
            if bbd:
                dmid, dupb, dlob, dcpx, _ = bbd
                # abre por debajo de la banda inferior diaria -> fade largo
                if op < dlob:
                    ref = next_open(t)
                    if ref: sigs.append((t, "LONG", "fuera_banda", ref)); last["fuera_banda"] = t; continue
                if op > dupb:
                    ref = next_open(t)
                    if ref: sigs.append((t, "SHORT", "fuera_banda", ref)); last["fuera_banda"] = t; continue
    return sigs

def main():
    syms = sys.argv[1:] or [os.path.basename(f).split("bars3mo5m_")[1][:-4]
                            for f in sorted(glob.glob("data/backtest/bars3mo5m_*.csv"))]
    out = "data/backtest/signals_yoel_pure.csv"
    n_by = {}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "sym", "side", "kind", "ref_px", "target_px", "stop_px"])
        for sym in syms:
            for (t, side, kind, ref) in detect(sym):
                w.writerow([t, sym.upper(), side, kind, round(ref, 2), "", ""])
                n_by[kind] = n_by.get(kind, 0) + 1
    total = sum(n_by.values())
    print(f"YOEL PURO -> {out}  ({total} señales)")
    for k, n in sorted(n_by.items()):
        print(f"  {k:16s} n={n}")

if __name__ == "__main__":
    main()
