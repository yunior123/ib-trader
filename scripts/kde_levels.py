#!/usr/bin/env python3
"""kde_levels.py — ficha 27 `kde-levels`: el UNICO rescate del motor de trendlines matado.

NO SE CONSTRUYE (muerto #8, O(pivotes^2)): enumeracion de pivotes, scoring de
trendlines, pesos de confluencia ajustados. Aqui solo hay la mitad KDE.

Que hace:
  * KDE gaussiano sobre log(close) de las ultimas 365 barras por TF (1m/5m/15m)
  * ancho de banda = 3.0*ATR14 expresado en espacio log
  * pesos = rampa lineal de recencia 0.2 (mas viejo) -> 1.0 (mas nuevo)
  * 200 puntos de rejilla, picos con prominencia >= 0.15*max
  * dedup dentro de 0.25*ATR, TOPE DURO de 5 niveles por sym por TF
  * CONSCIENTE DE ISLAS: la ventana jamas abarca un hueco > 3*ATR (cortes de gaps.py)

Un nivel KDE siempre CEDE ante muros OI y ante el capitan, y NUNCA se canta solo.
SEÑAL-SOLAMENTE: este fichero no ordena y no habilita ninguna voz.

TEST DE MUERTE: `--deathtest`. Tasa de BOUNCE en niveles KDE contra 1000 niveles
aleatorios por sesion, y contra POC + PDH/PDL del dia previo. Si no bate a
POC+PDH/PDL la feature SE BORRA. ~90% de redundancia es el caso ESPERADO.

Uso:
  python3 scripts/kde_levels.py                # data/levels_auto_<sym>.json
  python3 scripts/kde_levels.py --deathtest    # el veredicto, con numeros
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gaps as G  # noqa: E402  (ATR, carga de barras, cortes de isla, escritura atomica)

DATA = os.path.join(REPO, "data")

WINDOW_BARS = 365
BW_ATR = 3.0
GRID = 200
PROM_FRAC = 0.15
DEDUP_ATR = 0.25
CAP = 5
ISLAND_MULT = 3.0
TFS = (1, 5, 15)

# print-o-nada (skill homonima)
TOL_ATR = 0.15          # buffer s = 0.15*ATR14_1m
REARM_ATR = 0.5         # histeresis: sin excursion de 0.5*ATR no hay segundo toque


# ------------------------------------------------------------------ agregacion
def aggregate(bars, tf):
    """Agrega barras 1m [(ts,o,h,l,c,v), ...] a `tf` minutos. Las MISMAS barras."""
    if tf == 1:
        return list(bars)
    out = []
    for i in range(0, len(bars), tf):
        ch = bars[i:i + tf]
        if not ch:
            continue
        out.append((ch[0][0], ch[0][1], max(b[2] for b in ch), min(b[3] for b in ch),
                    ch[-1][4], sum((b[5] or 0.0) for b in ch)))
    return out


# ------------------------------------------------------------------ prominencia
def peak_prominences(y):
    """Prominencia topografica de cada maximo local de `y`.

    Para cada pico: se desciende a izquierda y derecha hasta encontrar una muestra
    MAS ALTA (o el borde); la prominencia es la altura del pico menos el MAYOR de
    los dos minimos de esos dos trayectos. Es la definicion estandar.
    """
    n = len(y)
    idx = [i for i in range(1, n - 1) if y[i] > y[i - 1] and y[i] >= y[i + 1]]
    out = []
    for i in idx:
        j = i - 1
        lmin = y[i]
        while j >= 0 and y[j] <= y[i]:
            lmin = min(lmin, y[j])
            j -= 1
        j = i + 1
        rmin = y[i]
        while j < n and y[j] <= y[i]:
            rmin = min(rmin, y[j])
            j += 1
        out.append((i, y[i] - max(lmin, rmin)))
    return out


# ------------------------------------------------------------------- islas
def truncate_at_island(bars, cuts):
    """La ventana KDE JAMAS abarca un hueco > 3*ATR: se recorta a las barras
    POSTERIORES al ultimo corte de isla que caiga dentro de la ventana.

    `cuts` = [{"lo","hi"}, ...] en precio. Se corta en la ULTIMA barra cuyo salto
    respecto al cierre previo SALTE POR ENCIMA DEL CENTRO de un corte.

    OJO — el criterio es "saltar por encima", no "solapar". Con el solape de
    `gaps.crosses_island` (que es el correcto para preguntar si una LINEA cruza un
    hueco) cualquier barra que oscile sobre un borde cuenta como salto y la ventana
    se recorta a UNA barra. Medido con dos clusters sinteticos. Y "cubrir el corte
    entero" es fragil por igualdad en coma flotante en los bordes: el CENTRO no lo es.
    """
    if not cuts or len(bars) < 2:
        return bars
    last = 0
    for i in range(1, len(bars)):
        prev_c, op = bars[i - 1][4], bars[i][1]
        a, b = min(prev_c, op), max(prev_c, op)
        if any(a <= (c["lo"] + c["hi"]) / 2.0 <= b for c in cuts):
            last = i
    return bars[last:] if last else bars


def island_cuts_from_bars(bars, atr, mult=ISLAND_MULT):
    """Cortes de isla DERIVADOS de las propias barras de la ventana: cualquier
    discontinuidad barra-a-barra mayor que `mult`*ATR.

    OJO — `atr` DEBE ser el ATR14 DIARIO (el de la ficha 26), no el del TF.
    Medido 2026-07-25: con el ATR del propio TF (QQQ 1m = 0.11) CUALQUIER frontera
    overnight supera 3*ATR, la ventana se recorta a la sesion en curso y el KDE de
    5m se quedaba en `null`. El corte de isla es un concepto de escala DIARIA.
    """
    if atr is None or atr <= 0:
        return None            # sin ATR no se afirma que haya (ni que no haya) islas
    out = []
    for i in range(1, len(bars)):
        prev_c, op = bars[i - 1][4], bars[i][1]
        if abs(op - prev_c) > mult * atr:
            out.append({"lo": min(prev_c, op), "hi": max(prev_c, op),
                        "size_atr": round(abs(op - prev_c) / atr, 3)})
    return out


# ---------------------------------------------------------------------- KDE
def kde_levels(bars, atr=None, cuts=None, window=WINDOW_BARS, cap=CAP,
               island_atr=None):
    """Niveles KDE de una serie de barras [(ts,o,h,l,c,v), ...].

    `atr`        — ATR14 del PROPIO TF: fija el ancho de banda y la dedup.
    `cuts`       — cortes de isla de gaps.py (escala diaria).
    `island_atr` — ATR14 DIARIO, para detectar islas dentro de la ventana. Si es
                   None no se detectan islas propias y solo mandan `cuts`.

    Devuelve None si no hay ATR o no hay barras suficientes — NUNCA [] por fallo,
    que seria afirmar "he mirado y no hay niveles".
    """
    if not bars or len(bars) < 30:
        return None
    if atr is None:
        atr = G.atr14([(b[1], b[2], b[3], b[4]) for b in bars])
    if atr is None or atr <= 0:
        return None

    w = list(bars[-window:])
    # islas de gaps.py (diarias) + las propias de la ventana SOLO si hay ATR diario
    own = island_cuts_from_bars(w, island_atr) if island_atr else None
    allcuts = list(cuts or []) + list(own or [])
    w = truncate_at_island(w, allcuts)
    if len(w) < 30:
        return None

    closes = np.array([b[4] for b in w], dtype=float)
    if not np.all(closes > 0):
        return None
    x = np.log(closes)
    px_ref = float(np.median(closes))
    h = BW_ATR * atr / px_ref                 # 3*ATR llevado a espacio log (d ln p = dp/p)
    if not (h > 0) or not math.isfinite(h):
        return None

    n = len(x)
    wt = np.linspace(0.2, 1.0, n)             # rampa de recencia 0.2 -> 1.0

    lo, hi = float(x.min()), float(x.max())
    if hi <= lo:
        return None
    # Padding de 3 anchos de banda. MEDIDO 2026-07-25: con 0.5*h la cola del pico mas
    # EXTERIOR no llega a decaer antes del borde de la rejilla, el descenso se corta en
    # un valor alto y su prominencia sale artificialmente pequeña (dos clusters
    # sinteticos limpios devolvian UN solo nivel). Con 3*h la cola vale exp(-4.5)~1%.
    pad = 3.0 * h
    grid = np.linspace(lo - pad, hi + pad, GRID)
    z = (grid[:, None] - x[None, :]) / h
    dens = (np.exp(-0.5 * z * z) * wt[None, :]).sum(axis=1)

    mx = float(dens.max())
    if not (mx > 0):
        return None
    proms = peak_prominences(dens)
    cand = [(float(dens[i]), float(np.exp(grid[i]))) for i, p in proms
            if p >= PROM_FRAC * mx]
    cand.sort(key=lambda t: -t[0])            # los mas densos primero

    out = []
    for _, px in cand:
        if any(abs(px - q) < DEDUP_ATR * atr for q in out):
            continue
        out.append(round(px, 4))
        if len(out) >= cap:
            break
    return sorted(out)


# -------------------------------------------------------- print-o-nada (numpy)
EXC_ATR = 0.5           # barrera de excursion favorable/adversa
EXC_BARS = 15           # horizonte de la barrera


def bounce_stats(sess, levels, atr1m):
    """Estadistica de reaccion a `levels` en la sesion `sess` = [(ts,o,h,l,c,v), ...].

    DOS metricas, porque la primera esta casi SATURADA (medido 2026-07-25: niveles
    ALEATORIOS ya rebotan al ~82% con ella, asi que apenas discrimina):

    1) `bounces` — la definicion de la skill print-o-nada:
         s      = TOL_ATR * ATR14_1m
         TOUCH  = la barra cruza la banda [L-s, L+s] Y cierra del lado del que venia
         BREAK  = open y close en lados OPUESTOS de la banda
         BOUNCE = TOUCH en t y NO BREAK en t+1
    2) `exc_win` — barrera triple con poder real: tras el toque, ¿el precio alcanza
       EXC_ATR*ATR a FAVOR (de vuelta al lado del que venia) antes que EXC_ATR*ATR
       EN CONTRA, dentro de EXC_BARS barras? Empate en la misma barra = adverso
       (conservador). Sin resolver dentro del horizonte = no cuenta.

    Histeresis: tras un toque, no cuenta otro hasta una excursion de REARM_ATR*ATR.
    Devuelve None si falta ATR o niveles — nunca ceros.
    """
    if atr1m is None or atr1m <= 0 or levels is None or len(levels) == 0:
        return None
    n = len(sess)
    if n < 5:
        return None
    L = np.asarray(levels, dtype=float)
    o = np.array([b[1] for b in sess]); hi = np.array([b[2] for b in sess])
    lo = np.array([b[3] for b in sess]); c = np.array([b[4] for b in sess])
    s = TOL_ATR * atr1m

    in_band = (lo[:, None] <= L[None, :] + s) & (hi[:, None] >= L[None, :] - s)
    side_c = np.sign(np.where(np.abs(c[:, None] - L[None, :]) <= s, 0.0,
                              c[:, None] - L[None, :]))
    side_o = np.sign(np.where(np.abs(o[:, None] - L[None, :]) <= s, 0.0,
                              o[:, None] - L[None, :]))
    brk = (side_o != 0) & (side_c != 0) & (side_o != side_c)

    # lado del que se VIENE = ultimo cierre estrictamente fuera de la banda
    prev_side = np.zeros_like(side_c)
    cur = np.zeros(len(L))
    for t in range(n):
        prev_side[t] = cur
        nz = side_c[t] != 0
        cur = np.where(nz, side_c[t], cur)

    touch = in_band & (side_c != 0) & (side_c == prev_side)

    m = len(L)
    touches = np.zeros(m, dtype=np.int64)
    bounces = np.zeros(m, dtype=np.int64)
    exc_n = np.zeros(m, dtype=np.int64)      # toques resueltos por la barrera
    exc_w = np.zeros(m, dtype=np.int64)      # resueltos A FAVOR
    armed = np.ones(m, dtype=bool)
    pend = np.zeros(m, dtype=np.int64)       # barras restantes de la barrera
    pside = np.zeros(m)
    e = EXC_ATR * atr1m

    for t in range(n):
        # --- resolucion de barreras abiertas (se evalua ANTES de abrir nuevas)
        act_p = pend > 0
        if act_p.any():
            fav = np.where(pside > 0, hi[t] >= L + e, lo[t] <= L - e)
            adv = np.where(pside > 0, lo[t] <= L - e, hi[t] >= L + e)
            done_a = act_p & adv                      # empate -> adverso
            done_f = act_p & fav & ~adv
            exc_n += done_f + done_a
            exc_w += done_f
            pend = np.where(done_f | done_a, 0, pend - act_p)

        # --- toques
        act = touch[t] & armed
        if act.any():
            if t + 1 < n:
                touches += act
                bounces += act & ~brk[t + 1]
                nuevo = act & (pend == 0)
                pside = np.where(nuevo, side_c[t], pside)
                pend = np.where(nuevo, EXC_BARS, pend)
            armed = np.where(act, False, armed)
        armed = armed | (np.abs(c[t] - L) >= REARM_ATR * atr1m)

    return {"toques": int(touches.sum()), "rebotes": int(bounces.sum()),
            "exc_n": int(exc_n.sum()), "exc_win": int(exc_w.sum())}


# -------------------------------------------------------------- niveles rivales
def prev_session_levels(prev):
    """POC de volumen + PDH/PDL de la sesion previa. `poc_dom` de
    charts/data/levels_<sym>.json es un porcentaje ("97%P"), NO un precio, y no
    existe historico: aqui se usa el POC de VOLUMEN de la sesion previa como
    PROXY MEDIBLE, marcado como proxy."""
    if not prev or len(prev) < 30:
        return None
    hi = max(b[2] for b in prev)
    lo = min(b[3] for b in prev)
    if hi <= lo:
        return None
    nb = 50
    edges = np.linspace(lo, hi, nb + 1)
    vol = np.zeros(nb)
    for b in prev:
        mid = (b[2] + b[3]) / 2.0
        k = min(nb - 1, max(0, int((mid - lo) / (hi - lo) * nb)))
        vol[k] += (b[5] or 0.0)
    if vol.sum() <= 0:
        return None
    poc = float((edges[int(vol.argmax())] + edges[int(vol.argmax()) + 1]) / 2.0)
    return {"POC_PROXY": poc, "PDH": float(hi), "PDL": float(lo)}


# --------------------------------------------------------------------- build
def build(syms=None, db=G.DB, out_dir=DATA):
    conn = G._ro(db)
    syms = syms or G.fleet()
    gapfile = os.path.join(DATA, "gaps.json")
    gj = json.load(open(gapfile)) if os.path.exists(gapfile) else {}
    written = []
    for sym in syms:
        rows = conn.execute(
            "SELECT ts,o,h,l,c,v FROM poly_bars WHERE sym=? ORDER BY ts DESC LIMIT ?",
            (sym, WINDOW_BARS * 20)).fetchall()
        rows = list(reversed(rows))
        sg = gj.get(sym) or {}
        cuts = sg.get("island_cuts") or []
        atr_d = sg.get("atr14")          # ATR14 DIARIO de gaps.py: la escala de las islas
        payload = {"sym": sym, "lock_ts": int(dt.datetime.now(dt.timezone.utc).timestamp()),
                   "src": "poly_bars 1m (ts en ms)", "n_bars_1m": len(rows),
                   "window_bars": WINDOW_BARS, "cap": CAP, "atr14_diario": atr_d,
                   "tfs": {}}
        for tf in TFS:
            b = aggregate(rows, tf)
            atr = G.atr14([(x[1], x[2], x[3], x[4]) for x in b[-WINDOW_BARS:]])
            lv = kde_levels(b, atr=atr, cuts=cuts, island_atr=atr_d)
            payload["tfs"][f"{tf}m"] = {
                "tf": f"{tf}m", "atr14": round(atr, 4) if atr is not None else None,
                "kde": lv,
                "why": None if lv else "sin ATR o sin barras suficientes",
            }
        p = os.path.join(out_dir, f"levels_auto_{sym}.json")
        G.atomic_write(p, payload)
        written.append(sym)
    conn.close()
    return written


# ---------------------------------------------------------------- TEST DE MUERTE
def deathtest(syms=None, db=G.DB, n_random=1000, max_sessions=250, seed=7):
    """KDE vs 1000 niveles aleatorios/sesion vs POC_PROXY+PDH/PDL. Sin look-ahead:
    todo nivel se construye con barras ESTRICTAMENTE ANTERIORES a la sesion."""
    rng = np.random.default_rng(seed)
    conn = G._ro(db)
    syms = syms or ["QQQ", "SPY", "NVDA", "AMD", "MU", "SMH", "AAPL", "MSFT",
                    "META", "TSLA"]
    acc = {}

    def bump(key, r):
        if r is None:
            return
        a = acc.setdefault(key, [0, 0, 0, 0, 0])
        a[0] += r["toques"]
        a[1] += r["rebotes"]
        a[2] += 1
        a[3] += r["exc_n"]
        a[4] += r["exc_win"]

    for sym in syms:
        rows = conn.execute("SELECT ts,o,h,l,c,v FROM poly_bars WHERE sym=? ORDER BY ts",
                            (sym,)).fetchall()
        days = {}
        for ts, o, h, l, c, v in rows:
            d = dt.datetime.fromtimestamp(ts / 1000, G.ET)
            m = d.hour * 60 + d.minute
            if not (G.RTH_OPEN_MIN <= m <= G.RTH_CLOSE_MIN):
                continue
            days.setdefault(d.strftime("%Y-%m-%d"), []).append((ts, o, h, l, c, v))
        keys = sorted(days)
        if len(keys) < 60:
            continue
        keys = keys[-max_sessions:] if len(keys) > max_sessions else keys
        allkeys = sorted(days)
        for kd in keys:
            i = allkeys.index(kd)
            if i < 20:
                continue
            sess = days[kd]
            hist = []
            for j in range(max(0, i - 20), i):
                hist.extend(days[allkeys[j]])
            if len(hist) < 400:
                continue
            atr1m = G.atr14([(x[1], x[2], x[3], x[4]) for x in hist[-400:]])
            if atr1m is None:
                continue
            prev = days[allkeys[i - 1]]
            rivals = prev_session_levels(prev)
            if rivals is None:
                continue
            for tf in TFS:
                hb = aggregate(hist, tf)
                atr_tf = G.atr14([(x[1], x[2], x[3], x[4]) for x in hb[-WINDOW_BARS:]])
                lv = kde_levels(hb, atr=atr_tf)
                if lv:
                    bump(f"KDE_{tf}m", bounce_stats(sess, lv, atr1m))
            bump("POC_PROXY", bounce_stats(sess, [rivals["POC_PROXY"]], atr1m))
            bump("PDH_PDL", bounce_stats(sess, [rivals["PDH"], rivals["PDL"]], atr1m))
            bump("RIVALES_JUNTOS", bounce_stats(sess, list(rivals.values()), atr1m))
            base = prev[-1][4]
            rl = base + rng.uniform(-2.0, 2.0, n_random) * atr1m
            bump("ALEATORIO", bounce_stats(sess, rl, atr1m))
    conn.close()

    res = {}
    for k, (t, b, ns, en, ew) in sorted(acc.items()):
        p, lo, hi = G._wilson(b, t)
        q, qlo, qhi = G._wilson(ew, en)
        res[k] = {
            "sesiones": ns, "toques": t, "rebotes": b,
            "tasa": round(p, 4) if p is not None else None,
            "wilson_lb": round(lo, 4) if lo is not None else None,
            "wilson_ub": round(hi, 4) if hi is not None else None,
            "exc_n": en, "exc_win": ew,
            "tasa_exc": round(q, 4) if q is not None else None,
            "exc_lb": round(qlo, 4) if qlo is not None else None,
            "exc_ub": round(qhi, 4) if qhi is not None else None,
        }

    def _delta(field, ref_key, out_key):
        ref = res.get(ref_key, {}).get(field)
        for v in res.values():
            v[out_key] = (round(100 * (v[field] - ref), 2)
                          if ref is not None and v.get(field) is not None else None)

    _delta("tasa", "ALEATORIO", "vs_aleatorio_pp")
    _delta("tasa", "RIVALES_JUNTOS", "vs_rivales_pp")
    _delta("tasa_exc", "ALEATORIO", "exc_vs_aleatorio_pp")
    _delta("tasa_exc", "RIVALES_JUNTOS", "exc_vs_rivales_pp")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--deathtest", action="store_true")
    ap.add_argument("--n-random", type=int, default=1000)
    ap.add_argument("--max-sessions", type=int, default=250)
    a = ap.parse_args(argv)
    syms = [s.upper() for s in a.syms] or None
    if a.deathtest:
        r = deathtest(syms, n_random=a.n_random, max_sessions=a.max_sessions)
        print(json.dumps(r, indent=1))
        return 0
    w = build(syms)
    print(f"levels_auto_<sym>.json: {len(w)} syms · tope {CAP}/TF · "
          f"consciente de islas (>{ISLAND_MULT}*ATR)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
