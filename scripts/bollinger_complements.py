#!/usr/bin/env python3
"""bollinger_complements.py — MISION B6: complementos de Bollinger, ticker por
ticker, con evidencia (2026-07-22).

Replica EXACTA de la deteccion elastic-1m de scripts/bollinger_alarm.py:
  - BB(20,2) 1m, std POBLACIONAL (/N), banda calculada sobre los 20 cierres
    ANTERIORES a la vela actual (bars[-21:-1] en el alarm).
  - PIERCE: high>banda_sup o low<banda_inf. Si el cierre queda FUERA -> arma.
  - RE-ENTRADA: vela posterior (<=10 min) que sigue perforando pero CIERRA
    dentro -> FIRE. Cooldown 30 min por simbolo+lado.
  - Si el cierre 5m actual tambien esta fuera de su BB(20,2) 5m -> BAND-WALK
    (el alarm NO canta elastico; aqui se tabula aparte y queda FUERA de la base).
  - RTH only; señales 9:50-15:30 ET (>=20 barras de la sesion para que la BB
    sea 100% intradia; <=15:30 para tener 30 min de outcome).

Outcomes (ventana 30 barras 1m, misma sesion):
  - hit_mid30: toca la MEDIA BB20-1m congelada al fire (dn: high>=mid; up: low<=mid).
  - hit_half30: avanza >=50% del gap |mid-close_fire|.
  - mfe/mae 15 y 30 min en % del cierre de entrada (a favor de la reversion).

Filtros F1-F8 (grid completo, sin cherry-picking) + combos de a 2.
Resultados incrementales: data/backtest/bcomp_results.json (no se pierde nada
si muere a mitad). Analisis: --analyze -> data/bollinger_plus.PROPUESTO.json + grid md.

MULTIPLICIDAD (corregido 2026-07-26) — el defecto y su medida
-------------------------------------------------------------
El criterio original de seleccion era `n>=15 y |uplift|>=5pts`: un umbral de
TAMAÑO DE EFECTO, sin p-valor, sin correccion por multiplicidad y sobre la n
CRUDA. El grid hace ~400 pruebas. Medido el 2026-07-26 con las mismas señales:

  - criterio viejo sobre los datos REALES ......... 150 celdas (70 veto + 80 best)
  - criterio viejo sobre RUIDO PURO (etiqueta
    barajada dentro de cada ticker, 10 semillas) .. 112.9 celdas de media
  - celdas ticker x filtro con p<0.05 ............ 14 de 387 (por azar: 19.4)
  - BH-FDR q=0.10 sobre n_eff .................... 0 de 401 sobreviven
  - señales que bb_engine desbloquea al dejar de
    aplicar esos vetos (30 tickers x 30 dias) ..... 5865 -> 7582 (+1717, +29%)

O sea: ~3 de cada 4 "hallazgos" del criterio viejo los reproduce el azar, y el
grid entero contiene MENOS señal que una moneda. Un veto no es una opinion:
APAGA la señal y no deja rastro auditable, asi que publicar ruido como veto es
daño invisible.

Procedimiento nuevo (skill `measured-probability`):
  1. p-valor por celda = z-test de dos proporciones celda vs SU COMPLEMENTO
     dentro del mismo ticker (grupos independientes; el `uplift` contra la base
     es anidado y no es testeable asi).
  2. muestra EFECTIVA antes de testear: `n_eff = n / (1 + (m̄-1)·ρ̄)` topado por
     el numero de clusters (sym,fecha), con ρ̄ = 0.41 MEDIDA en la flota y
     m̄ = señales por sesion de la celda. Misma funcion que null_control.py:214.
  3. BH-FDR q=0.10 sobre TODA la familia de pruebas del grid (por-ticker +
     flota + combos), no sobre una celda suelta.
  4. se publica una celda solo si pasa BH-FDR **y** n_eff >= 30 (el minimo de
     'medido' de la casa, K::CALIB_MIN_N).

La salida va a `data/bollinger_plus.PROPUESTO.json`: cambiar lo que la flota
VETA hoy es decision del lead, no de este script. `bollinger_plus.json` NO se
toca. Cada celda lleva su `why` DENTRO del dato (patron signal_enable.json).

SEÑAL-SOLAMENTE. Aditivo. Sin daemons.
"""
import csv, json, math, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data", "backtest")
RESULTS = os.path.join(DATA, "bcomp_results.json")
ET = ZoneInfo("America/New_York")
COOLDOWN_S = 1800
ARM_EXPIRE_S = 600
OUT_BARS = 30

# --- multiplicidad / correlacion (skill measured-probability) ---------------
RHO_FLOTA = 0.41      # ρ̄ MEDIDA (docs/NULL-CONTROL-2026-07-25.md); no es un prior
FDR_Q = 0.10          # BH-FDR de la casa
MIN_N_EFF = 30.0      # 'medido' pide n>=30 en la celda PROPIA (K::CALIB_MIN_N)
CRITERIO_VIEJO_N = 15
CRITERIO_VIEJO_UPLIFT = 5.0


# ------------------------------------------- multiplicidad: motores prestados
# Ni el n_eff ni el BH-FDR se reimplementan aqui: se usan los de la casa. Si no
# estan, esto LEVANTA — sin correccion por multiplicidad este grid no publica.
def _mt():
    """(effective_n, two_prop_p, benjamini_hochberg). Fail-loud."""
    d = os.path.dirname(os.path.abspath(__file__))
    if d not in sys.path:
        sys.path.insert(0, d)
    import null_control as nc                      # levanta si falta la skill
    return nc.effective_n, nc.two_prop_p, nc.stats()["mt"].benjamini_hochberg


def clusters(sigs):
    """Clusters de informacion independiente: la SESION.

    ρ̄=0.41 es la correlacion media por pares MEDIDA ENTRE SIMBOLOS de la flota,
    asi que las 30 señales de un dia en que todo cae junto NO son 30
    observaciones. Agrupar por (sym,fecha) dejaria esa correlacion fuera justo
    en las celdas agregadas de flota, que son las que mas se benefician de
    ella. Para una celda de un solo ticker (sym,fecha) y fecha coinciden."""
    return {s["date"] for s in sigs}


def n_efectiva(sigs, tope_clusters=False):
    """n_eff de una celda por el design effect de Kish sobre clusters
    (sym,fecha): `n_eff = n / (1 + (m̄-1)·ρ̄)` con ρ̄ = RHO_FLOTA MEDIDA y
    m̄ = señales por cluster. Devuelve None si la celda esta vacia (jamas un
    numero plausible).

    `effective_n` trunca su `k` a entero, asi que m̄ se redondea HACIA ARRIBA:
    ante la duda la muestra efectiva sale mas pequeña, nunca mas grande.

    `tope_clusters=True` aplica ademas el techo `n_eff <= n_clusters` de
    null_control.effective_n. OJO: ese techo equivale a ρ=1 y con ρ̄=0.41 muerde
    SIEMPRE que m̄>1 (n/(1+(m̄-1)ρ) >= n/m̄ para todo ρ<=1), dejando n_eff
    identico al numero de clusters y tirando a la basura la ρ̄ medida. Por eso
    aqui es una SENSIBILIDAD que se reporta, no el criterio."""
    if not sigs:
        return None
    effective_n, _, _ = _mt()
    n = len(sigs)
    nc = len(clusters(sigs))
    return effective_n(n, math.ceil(n / nc), RHO_FLOTA, nc if tope_clusters else None)


# ---------------------------------------------------------------- utilidades
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - hw), min(1.0, c + hw))


def bb_pop(closes, k=2.0):
    m = sum(closes) / len(closes)
    sd = math.sqrt(sum((c - m) ** 2 for c in closes) / len(closes))
    return m - k * sd, m, m + k * sd


def load_bars(sym):
    """[(epoch, o,h,l,c,v, date_str, et_min)] solo RTH 9:30-16:00, ordenado."""
    path = os.path.join(DATA, f"bars30d_{sym}.csv")
    out = []
    with open(path) as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if len(row) < 6:
                continue
            t = int(float(row[0]))
            dt = datetime.fromtimestamp(t, ET)
            mins = dt.hour * 60 + dt.minute
            if not (570 <= mins < 960):        # 9:30 <= t < 16:00
                continue
            out.append((t, float(row[1]), float(row[2]), float(row[3]),
                        float(row[4]), float(row[5]), dt.strftime("%Y-%m-%d"), mins))
    out.sort(key=lambda x: x[0])
    return out


class Wilder:
    """RSI(n) de Wilder incremental."""
    def __init__(self, n):
        self.n = n; self.prev = None; self.ag = None; self.al = None; self.seed = []

    def update(self, c):
        if self.prev is None:
            self.prev = c; return None
        ch = c - self.prev; self.prev = c
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if self.ag is None:
            self.seed.append((g, l))
            if len(self.seed) < self.n:
                return None
            self.ag = sum(x for x, _ in self.seed) / self.n
            self.al = sum(y for _, y in self.seed) / self.n
        else:
            self.ag = (self.ag * (self.n - 1) + g) / self.n
            self.al = (self.al * (self.n - 1) + l) / self.n
        if self.ag + self.al == 0:
            return 50.0
        if self.al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + self.ag / self.al)


class ADX:
    """ADX(14) de Wilder, alimentado con barras COMPLETAS (5m)."""
    def __init__(self, n=14):
        self.n = n; self.prev = None
        self.atr = None; self.pdm = None; self.ndm = None
        self.seed = []; self.dx_seed = []; self.adx = None

    def update(self, h, l, c):
        if self.prev is None:
            self.prev = (h, l, c); return self.adx
        ph, pl, pc = self.prev; self.prev = (h, l, c)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        pdm = up if (up > dn and up > 0) else 0.0
        ndm = dn if (dn > up and dn > 0) else 0.0
        if self.atr is None:
            self.seed.append((tr, pdm, ndm))
            if len(self.seed) < self.n:
                return self.adx
            self.atr = sum(x[0] for x in self.seed)
            self.pdm = sum(x[1] for x in self.seed)
            self.ndm = sum(x[2] for x in self.seed)
        else:
            self.atr = self.atr - self.atr / self.n + tr
            self.pdm = self.pdm - self.pdm / self.n + pdm
            self.ndm = self.ndm - self.ndm / self.n + ndm
        if self.atr == 0:
            return self.adx
        pdi = 100.0 * self.pdm / self.atr
        ndi = 100.0 * self.ndm / self.atr
        s = pdi + ndi
        dx = 100.0 * abs(pdi - ndi) / s if s > 0 else 0.0
        if self.adx is None:
            self.dx_seed.append(dx)
            if len(self.dx_seed) >= self.n:
                self.adx = sum(self.dx_seed) / self.n
        else:
            self.adx = (self.adx * (self.n - 1) + dx) / self.n
        return self.adx


# ---------------------------------------------------------------- deteccion
def run_ticker(sym):
    bars = load_bars(sym)
    if len(bars) < 200:
        return {"error": f"solo {len(bars)} barras", "signals": [], "n_bars": len(bars)}
    signals, walk_signals, walks = [], [], 0

    rsi2 = Wilder(2)
    adx5 = ADX(14)
    bw_hist = []                       # bandwidth 1m
    b5, b15 = [], []                   # buckets [key,o,h,l,c] cross-sesion RTH
    cur_date = None
    sess_start_i = 0
    vwap_pv = vwap_v = 0.0
    dev_s = dev_s2 = dev_n = 0
    armed = {"up": None, "dn": None}   # (idx, epoch, max_depth)
    last_fire = {"up": 0.0, "dn": 0.0}
    dates = sorted({b[6] for b in bars})

    for i, (t, o, h, l, c, v, d, mins) in enumerate(bars):
        if d != cur_date:
            cur_date = d
            sess_start_i = i
            vwap_pv = vwap_v = 0.0
            dev_s = dev_s2 = dev_n = 0
            armed = {"up": None, "dn": None}   # sin arrastre nocturno
        sess_idx = i - sess_start_i

        # --- buckets 5m / 15m (incluyen la barra actual; el anterior completa)
        for blist, secs, adx in ((b5, 300, adx5), (b15, 900, None)):
            k = t - t % secs
            if not blist or blist[-1][0] != k:
                if blist and secs == 300:
                    _, po, ph, pl, pc = blist[-1]
                    adx5.update(ph, pl, pc)    # bucket 5m completado
                blist.append([k, o, h, l, c])
            else:
                bk = blist[-1]
                bk[2] = max(bk[2], h); bk[3] = min(bk[3], l); bk[4] = c

        # --- rsi2 / vwap (antes de decidir: todo al cierre de la barra i)
        r2 = rsi2.update(c)
        tp = (h + l + c) / 3.0
        vwap_pv += tp * v; vwap_v += v
        vwap = vwap_pv / vwap_v if vwap_v > 0 else c
        dev = c - vwap
        dev_s += dev; dev_s2 += dev * dev; dev_n += 1
        zv = None
        if dev_n >= 20:
            mu = dev_s / dev_n
            var = dev_s2 / dev_n - mu * mu
            sd = math.sqrt(var) if var > 1e-12 else 0.0
            zv = (dev - mu) / sd if sd > 0 else 0.0

        if sess_idx < 20:
            continue
        closes20 = [b[4] for b in bars[i - 20:i]]
        lo, mid, up = bb_pop(closes20)
        width = up - lo
        bw = width / mid if mid else 0.0
        bw_hist.append(bw)
        bw_pct = None
        if len(bw_hist) >= 100:
            window = bw_hist[-125:]
            bw_pct = 100.0 * sum(1 for x in window if x <= bw) / len(window)

        vol20 = [b[5] for b in bars[i - 20:i]]
        vsma = sum(vol20) / 20.0
        rvol = v / vsma if vsma > 0 else None

        # walk 5m/15m (BB sobre los 20 buckets ANTERIORES al actual)
        def tf_state(blist):
            if len(blist) < 21:
                return None, None
            cl = [b[4] for b in blist[-21:-1]]
            tlo, tmid, tup = bb_pop(cl)
            cc = blist[-1][4]
            return ("up" if cc > tup else "dn" if cc < tlo else "in"), (tlo, tmid, tup)
        w5, _ = tf_state(b5)
        w15, _ = tf_state(b15)

        # --- deteccion por lado (estructura del alarm)
        for side in ("up", "dn"):
            pierced = h > up if side == "up" else l < lo
            depth = ((h - up) if side == "up" else (lo - l)) / width if width > 0 else 0.0
            if pierced:
                back = c < up if side == "up" else c > lo
                if not back:
                    prev = armed[side]
                    armed[side] = (i, t, max(depth, prev[2] if prev else 0.0))
                elif armed[side] and t - last_fire[side] > COOLDOWN_S:
                    ai, at, adep = armed[side]
                    armed[side] = None
                    if t - at > ARM_EXPIRE_S:
                        continue
                    last_fire[side] = t
                    walk = (w5 == side)
                    if walk:
                        walks += 1                  # el alarm canta BAND-WALK, no elastico
                    if mins > 930:                  # <=15:30 para outcome completo
                        continue
                    # outcomes: 30 barras, misma sesion
                    fut = [b for b in bars[i + 1:i + 1 + OUT_BARS] if b[6] == d]
                    if len(fut) < OUT_BARS:
                        continue
                    gap = abs(mid - c)
                    # --- etiqueta de TRIPLE BARRERA (skill measured-probability)
                    # TP = la media BB (el objetivo que la propia señal declara)
                    # SL = medio gap EN CONTRA. Primer toque manda; barra que
                    # contiene los dos -> SL (conservador, se cuenta ambigua).
                    # timeout = None, JAMAS 1: es el bug que esto evita.
                    if side == "dn":
                        tp_px, sl_px = mid, c - 0.5 * gap
                    else:
                        tp_px, sl_px = mid, c + 0.5 * gap
                    bar_lab, bar_ambig = None, False
                    for fb in fut:
                        hit_tp = fb[2] >= tp_px if side == "dn" else fb[3] <= tp_px
                        hit_sl = fb[3] <= sl_px if side == "dn" else fb[2] >= sl_px
                        if hit_tp and hit_sl:
                            bar_lab, bar_ambig = 0, True
                            break
                        if hit_sl:
                            bar_lab = 0
                            break
                        if hit_tp:
                            bar_lab = 1
                            break
                    if side == "dn":                # fade LONG hacia la media
                        hit_mid = any(fb[2] >= mid for fb in fut)
                        hit_half = any(fb[2] >= c + 0.5 * gap for fb in fut)
                        mfe15 = (max(fb[2] for fb in fut[:15]) - c) / c * 100
                        mae15 = (c - min(fb[3] for fb in fut[:15])) / c * 100
                        mfe30 = (max(fb[2] for fb in fut) - c) / c * 100
                        mae30 = (c - min(fb[3] for fb in fut)) / c * 100
                    else:                           # fade SHORT hacia la media
                        hit_mid = any(fb[3] <= mid for fb in fut)
                        hit_half = any(fb[3] <= c - 0.5 * gap for fb in fut)
                        mfe15 = (c - min(fb[3] for fb in fut[:15])) / c * 100
                        mae15 = (max(fb[2] for fb in fut[:15]) - c) / c * 100
                        mfe30 = (c - min(fb[3] for fb in fut)) / c * 100
                        mae30 = (max(fb[2] for fb in fut) - c) / c * 100
                    hb = ("0945_1030" if 585 <= mins < 630 else
                          "1030_1130" if 630 <= mins < 690 else
                          "1130_1400" if 690 <= mins < 840 else
                          "1400_1530" if 840 <= mins <= 930 else "otras")
                    (walk_signals if walk else signals).append({
                        "sym": sym, "date": d, "et": f"{mins // 60:02d}:{mins % 60:02d}",
                        "side": side, "close": round(c, 4), "mid": round(mid, 4),
                        "gap_pct": round(gap / c * 100, 3),
                        "rvol": round(rvol, 2) if rvol is not None else None,
                        "rsi2": round(r2, 1) if r2 is not None else None,
                        "depth": round(max(adep, depth), 3),
                        "zvwap": round(zv, 2) if zv is not None else None,
                        "bw_pct": round(bw_pct, 1) if bw_pct is not None else None,
                        "hour": hb,
                        "f7_in15": (w15 == "in") if w15 is not None else None,
                        # 15m ROTO en el MISMO lado del pierce (la pregunta de
                        # Yunior: "¿nos aseguramos de que rompa en 1m Y 15m?").
                        # w15 None = el 15m aun no tiene 21 buckets -> se dice.
                        "tf15_roto": (w15 == side) if w15 is not None else None,
                        "adx5": round(adx5.adx, 1) if adx5.adx is not None else None,
                        "barrera": bar_lab, "barrera_ambig": bar_ambig,
                        "hit_mid30": hit_mid, "hit_half30": hit_half,
                        "mfe15": round(mfe15, 3), "mae15": round(mae15, 3),
                        "mfe30": round(mfe30, 3), "mae30": round(mae30, 3),
                    })
            elif armed[side] and (t - armed[side][1]) > ARM_EXPIRE_S:
                armed[side] = None

    # `signals` = elastic puro (5m NO en band-walk), la base de todo el estudio.
    # `signals_bandwalk5` = el otro brazo, tabulado APARTE para poder contestar
    # la pregunta del 2TF-vs-3TF sin contaminar la base historica.
    return {"n_bars": len(bars), "n_days": len(dates), "band_walks_5m": walks,
            "signals": signals, "signals_bandwalk5": walk_signals}


# ---------------------------------------------------------------- filtros
def fdefs():
    """nombre -> (descripcion, predicado(sig)->bool|None)."""
    def side_rsi(s):
        if s["rsi2"] is None:
            return None
        return s["rsi2"] < 10 if s["side"] == "dn" else s["rsi2"] > 90

    def side_z(s):
        if s["zvwap"] is None:
            return None
        return s["zvwap"] <= -1.5 if s["side"] == "dn" else s["zvwap"] >= 1.5

    F = {
        "F1_rvol15":   ("RVOL vela fire >= 1.5", lambda s: None if s["rvol"] is None else s["rvol"] >= 1.5),
        "F2_rsi2_ext": ("RSI(2) extremo (dn<10 / up>90)", side_rsi),
        "F3a_depth05": ("pierce depth > 0.05 del ancho", lambda s: s["depth"] > 0.05),
        "F3b_depth15": ("pierce depth > 0.15 del ancho", lambda s: s["depth"] > 0.15),
        "F4_zvwap15":  ("z-VWAP >= |1.5| contra el lado", side_z),
        "F5_squeeze":  ("bandwidth 1m pctile <= 20 (post-squeeze)", lambda s: None if s["bw_pct"] is None else s["bw_pct"] <= 20),
        "F6_0945":     ("hora 9:50-10:30", lambda s: s["hour"] == "0945_1030"),
        "F6_1030":     ("hora 10:30-11:30", lambda s: s["hour"] == "1030_1130"),
        "F6_1130":     ("picadora 11:30-14:00", lambda s: s["hour"] == "1130_1400"),
        "F6_1400":     ("hora 14:00-15:30", lambda s: s["hour"] == "1400_1530"),
        "F7_15m_in":   ("cierre 15m DENTRO de su banda", lambda s: s["f7_in15"]),
        "F8a_adx_lt20": ("ADX(14) 5m < 20 (rango)", lambda s: None if s["adx5"] is None else s["adx5"] < 20),
        "F8b_adx_ge25": ("ADX(14) 5m >= 25 (tendencia)", lambda s: None if s["adx5"] is None else s["adx5"] >= 25),
    }
    return F


def cell(sigs, key="hit_mid30"):
    """Celda con su Wilson sobre la muestra EFECTIVA. El Wilson crudo es
    anticonservador ~3-4x cuando las observaciones comparten sesion."""
    n = len(sigs)
    k = sum(1 for s in sigs if s[key])
    ne = n_efectiva(sigs)
    p, lo, hi = wilson(k, n)
    if ne is not None:
        _, lo, hi = wilson(p * ne, ne)
    net = n_efectiva(sigs, tope_clusters=True)
    return {"n": n, "k": k, "n_eff": round(ne, 1) if ne is not None else None,
            "n_eff_tope_clusters": round(net, 1) if net is not None else None,
            "n_clusters": len(clusters(sigs)),
            "p": round(p * 100, 1),
            "wilson_lo": round(lo * 100, 1), "wilson_hi": round(hi * 100, 1)}


def prueba(sub, comp, key="hit_mid30"):
    """p-valor de la celda: z-test de dos proporciones celda vs SU COMPLEMENTO
    (grupos disjuntos) sobre las muestras EFECTIVAS. None = no testeable (algun
    grupo vacio) -> esa celda no puede publicarse jamas."""
    if not sub or not comp:
        return None
    _, two_prop_p, _ = _mt()
    es, ec = n_efectiva(sub), n_efectiva(comp)
    ps = sum(1 for s in sub if s[key]) / len(sub)
    pc = sum(1 for s in comp if s[key]) / len(comp)
    return two_prop_p(ps * es, es, pc * ec, ec)


def aplicar_fdr(familia, q=FDR_Q):
    """BH-FDR q sobre TODA la familia de pruebas del grid. `familia` es una
    lista de dicts-celda con 'pval'; se anota 'fdr_reject' y 'fdr_q' EN el dict.
    Las celdas sin pval quedan marcadas como no testeables (jamas se publican).
    Devuelve (n_pruebas, n_sobreviven)."""
    _, _, bh = _mt()
    testeables = [c for c in familia if c.get("pval") is not None]
    for c in familia:
        if c.get("pval") is None:
            c["fdr_reject"] = False
            c["fdr_q"] = None
    if not testeables:
        return 0, 0
    rej, adj = bh([c["pval"] for c in testeables], alpha=q)
    for c, r, qq in zip(testeables, rej, adj):
        c["fdr_reject"] = bool(r)
        c["fdr_q"] = round(float(qq), 4)
    return len(testeables), sum(1 for c in testeables if c["fdr_reject"])


def avg(sigs, key):
    xs = [s[key] for s in sigs if s.get(key) is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def analyze(results):
    F = fdefs()
    grid = {}          # ticker -> {base:..., filters:{fname:cell}}
    pooled = []
    familia = []       # TODAS las pruebas del grid -> una sola correccion BH
    for sym, res in sorted(results.items()):
        sigs = res.get("signals", [])
        pooled.extend(sigs)
        base = cell(sigs)
        base.update({"p_half": cell(sigs, "hit_half30")["p"],
                     "mfe15": avg(sigs, "mfe15"), "mae15": avg(sigs, "mae15"),
                     "mfe30": avg(sigs, "mfe30"), "mae30": avg(sigs, "mae30"),
                     "n_days": res.get("n_days"), "band_walks_5m": res.get("band_walks_5m")})
        filts = {}
        for fname, (desc, pred) in F.items():
            sub = [s for s in sigs if pred(s) is True]
            comp = [s for s in sigs if pred(s) is False]
            cc = cell(sub)
            cc["uplift"] = round(cc["p"] - base["p"], 1) if cc["n"] else None
            cc["p_half"] = cell(sub, "hit_half30")["p"] if cc["n"] else None
            cc["n_comp"] = len(comp)
            cc["p_comp"] = round(100.0 * sum(1 for s in comp if s["hit_mid30"]) / len(comp), 1) if comp else None
            cc["pval"] = prueba(sub, comp)
            cc["scope"] = "ticker"
            cc["cell_id"] = "%s|%s" % (sym.upper(), fname)
            familia.append(cc)
            filts[fname] = cc
        grid[sym] = {"base": base, "filters": filts,
                     "by_side": {sd: cell([s for s in sigs if s["side"] == sd])
                                 for sd in ("up", "dn")}}

    fleet_base = cell(pooled)
    fleet = {"base": fleet_base, "filters": {}, "by_side": {
        sd: cell([s for s in pooled if s["side"] == sd]) for sd in ("up", "dn")}}
    for fname, (desc, pred) in F.items():
        sub = [s for s in pooled if pred(s) is True]
        comp = [s for s in pooled if pred(s) is False]
        cc = cell(sub)
        cc["uplift"] = round(cc["p"] - fleet_base["p"], 1) if cc["n"] else None
        cc["desc"] = desc
        cc["pval"] = prueba(sub, comp)
        cc["scope"] = "flota"
        cc["cell_id"] = "FLOTA|%s" % fname
        familia.append(cc)
        fleet["filters"][fname] = cc

    # combos: filtros con uplift flota >= 5 y n>=15, pares, max 6
    elig = [f for f, c in fleet["filters"].items()
            if c["n"] >= 15 and c["uplift"] is not None and c["uplift"] >= 5.0]
    elig.sort(key=lambda f: -fleet["filters"][f]["uplift"])
    combos = {}
    import itertools
    for a, b in itertools.combinations(elig, 2):
        if len(combos) >= 6:
            break
        pa, pb = F[a][1], F[b][1]
        sub = [s for s in pooled if pa(s) is True and pb(s) is True]
        comp = [s for s in pooled if not (pa(s) is True and pb(s) is True)]
        cc = cell(sub)
        cc["uplift"] = round(cc["p"] - fleet_base["p"], 1) if cc["n"] else None
        cc["pval"] = prueba(sub, comp)
        cc["scope"] = "combo"
        cc["cell_id"] = "COMBO|%s+%s" % (a, b)
        familia.append(cc)
        combos[f"{a}+{b}"] = cc
    fleet["combos"] = combos

    # --- UNA SOLA correccion BH sobre la familia entera del grid -------------
    n_pruebas, n_surv = aplicar_fdr(familia)
    fleet["multiplicidad"] = {
        "rho_flota": RHO_FLOTA, "fdr_q": FDR_Q, "min_n_eff": MIN_N_EFF,
        "n_celdas_familia": len(familia), "n_pruebas_testeables": n_pruebas,
        "n_sobreviven_bh": n_surv,
        "nota": ("BH-FDR q=%.2f sobre las %d pruebas del grid, con Wilson y z-test "
                 "sobre muestra EFECTIVA (rho=%.2f medida). Sin esto el criterio "
                 "viejo (n>=%d, |uplift|>=%.0f) publica ~113 celdas sobre RUIDO PURO."
                 % (FDR_Q, n_pruebas, RHO_FLOTA, CRITERIO_VIEJO_N, CRITERIO_VIEJO_UPLIFT)),
    }
    return grid, fleet, pooled


def sobrevive(c):
    """¿La celda puede publicarse? BH-FDR + n_eff minima. Devuelve (bool, why).
    El `why` viaja DENTRO del dato (patron data/signal_enable.json)."""
    if c.get("pval") is None:
        return False, ("no testeable: el complemento del filtro esta vacio dentro "
                       "del ticker -> no hay contraste posible")
    if not c.get("fdr_reject"):
        return False, ("NO pasa BH-FDR q=%.2f (q=%s) sobre las pruebas del grid: "
                       "indistinguible del ruido. El criterio viejo (n>=%d, "
                       "|uplift|>=%.0f) la habria publicado."
                       % (FDR_Q, c.get("fdr_q"), CRITERIO_VIEJO_N, CRITERIO_VIEJO_UPLIFT))
    if c.get("n_eff") is None or c["n_eff"] < MIN_N_EFF:
        return False, ("pasa BH-FDR pero n_eff=%s < %.0f: DATA-INSUFFICIENT "
                       "(la n cruda %d se reparte en pocas sesiones)"
                       % (c.get("n_eff"), MIN_N_EFF, c["n"]))
    return True, ("pasa BH-FDR q=%.2f (q=%.4g) con n_eff=%.1f y uplift %+.1fpts"
                  % (FDR_Q, c["fdr_q"], c["n_eff"], c["uplift"]))


def write_outputs(grid, fleet):
    """Escribe la PROPUESTA. `bollinger_plus.json` NO se toca: cambiar lo que la
    flota veta hoy lo decide el lead (regla de la casa)."""
    plus = {}
    viejo_best = viejo_veto = nuevo_best = nuevo_veto = 0
    caidas = []
    for sym, g in grid.items():
        base = g["base"]
        best, veto, descartadas = [], [], []
        for fname, c in g["filters"].items():
            viejo = (c["n"] >= CRITERIO_VIEJO_N and c["uplift"] is not None
                     and abs(c["uplift"]) >= CRITERIO_VIEJO_UPLIFT)
            if viejo:
                if c["uplift"] > 0:
                    viejo_best += 1
                else:
                    viejo_veto += 1
            ok, why = sobrevive(c)
            item = {"filtro": fname, "n": c["n"], "n_eff": c["n_eff"], "p": c["p"],
                    "uplift": c["uplift"], "wilson": [c["wilson_lo"], c["wilson_hi"]],
                    "pval": None if c["pval"] is None else round(c["pval"], 5),
                    "fdr_q": c.get("fdr_q"), "fdr_ok": ok, "why": why}
            if ok:
                (best if c["uplift"] > 0 else veto).append(item)
                if c["uplift"] > 0:
                    nuevo_best += 1
                else:
                    nuevo_veto += 1
            elif viejo:
                descartadas.append(item)
                caidas.append((sym.upper(), fname, c["uplift"]))
        best.sort(key=lambda x: -x["uplift"]); veto.sort(key=lambda x: x["uplift"])
        plus[sym.upper()] = {"base": {"n": base["n"], "n_eff": base["n_eff"], "p": base["p"],
                                      "wilson": [base["wilson_lo"], base["wilson_hi"]]},
                             "best_filters": best, "veto_filters": veto,
                             "descartadas_por_multiplicidad": descartadas}
    plus["_meta"] = {"generado": datetime.now(ET).strftime("%Y-%m-%d %H:%M ET"),
                     "outcome": "P(toca media BB20-1m congelada, 30min)",
                     "criterio": ("BH-FDR q=%.2f sobre las pruebas del grid + n_eff>=%.0f "
                                  "(rho=%.2f medida). Solo se publica lo que sobrevive."
                                  % (FDR_Q, MIN_N_EFF, RHO_FLOTA)),
                     "criterio_anterior": ("n>=%d y |uplift|>=%.0fpts vs base del ticker — "
                                           "SIN p-valor, SIN correccion por multiplicidad y "
                                           "sobre n CRUDA. Reproducia ~113 celdas sobre ruido puro."
                                           % (CRITERIO_VIEJO_N, CRITERIO_VIEJO_UPLIFT)),
                     "antes_despues": {"best_viejo": viejo_best, "best_nuevo": nuevo_best,
                                       "veto_viejo": viejo_veto, "veto_nuevo": nuevo_veto},
                     "multiplicidad": fleet["multiplicidad"],
                     "fleet_base": fleet["base"], "fleet_filters": fleet["filters"],
                     "fleet_combos": fleet["combos"]}
    out = os.path.join(REPO, "data", "bollinger_plus.PROPUESTO.json")
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(plus, f, indent=1, ensure_ascii=False)
    os.replace(tmp, out)                      # escritura atomica
    print("PROPUESTA escrita en %s (bollinger_plus.json NO se ha tocado)" % out)
    print("  BEST: %d -> %d    VETO: %d -> %d   (%d celdas caen por multiplicidad)"
          % (viejo_best, nuevo_best, viejo_veto, nuevo_veto, len(caidas)))
    for sym, fname, up in sorted(caidas, key=lambda x: (x[0], x[1]))[:200]:
        print("    cae %-6s %-14s uplift %+.1f" % (sym, fname, up))
    return plus


# ------------------------------------------------ hipotesis multi-TF (1m Y 15m)
def analizar_tf15(results):
    """¿Exigir que el 15m TAMBIEN rompa mejora el edge, o solo recorta muestra?

    Pregunta de Yunior (2026-07-25): "with BB, are we making sure it breaks in
    1 min and 15 min? to avoid noise?". La regla viva en los signal bots cuenta
    2-de-3 TF (1m+5m+15m) y el 5m se agrega DESDE las mismas barras de 1m, asi
    que 1m+5m basta y el 15m puede no romper nunca (medido por el lead:
    148 señales BB-2TF vs 4 BB-3TF en 501 sesiones -> el 15m participa 2.6%).

    Aqui se mide sobre la deteccion elastic con DOS outcomes:
      - toque: P(toca la media BB20-1m en 30 min)  [el de siempre]
      - barrera: triple barrera TP=media / SL=medio gap en contra, timeout=NULL
    Variantes: TODAS (regla actual) vs 15m TAMBIEN ROTO vs 15m DENTRO, mas el
    brazo band-walk 5m separado en BB-2TF (1m+5m) y BB-3TF (1m+5m+15m), que es
    el 2-de-3 REAL de los bots.

    RESULTADO MEDIDO 2026-07-26 (30 tickers x 30 dias) — P(toque):
        67.2%  solo el 1m roto        (n=4031)
        49.4%  BB-2TF  1m+5m rotos    (n= 409)
        43.0%  BB-3TF  1m+5m+15m      (n= 200)
    Monotona a la BAJA: cuantos MAS timeframes rotos, PEOR va la reversion —
    porque romper en varios TF es band-walk (continuacion), no capitulacion.
    Exigir el 15m no quita ruido: recorta el 92% de la muestra y empeora. Con
    n_eff ~40 ningun contraste llega a p<0.05 -> UNPROVEN, banner-solamente.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from calibration_ledger import wilson_lb_expectancy
    pooled, walk5 = [], []
    for _sym, res in sorted(results.items()):
        pooled.extend(res.get("signals", []))
        walk5.extend(res.get("signals_bandwalk5", []))
    conocidos = [s for s in pooled if s.get("tf15_roto") is not None]
    w5c = [s for s in walk5 if s.get("tf15_roto") is not None]
    variantes = [
        ("TODAS (regla actual: 1m rompe)", conocidos),
        ("1m Y 15m rotos (mismo lado)", [s for s in conocidos if s["tf15_roto"] is True]),
        ("1m roto, 15m NO roto", [s for s in conocidos if s["tf15_roto"] is False]),
        # Brazo band-walk 5m = el 2-de-3 REAL de los signal bots: el 5m se
        # agrega desde las MISMAS barras de 1m, asi que 1m+5m van casi siempre
        # juntos y el 15m es el unico voto independiente.
        ("BB-2TF bot (1m+5m rotos, 15m NO)", [s for s in w5c if s["tf15_roto"] is False]),
        ("BB-3TF bot (1m+5m+15m rotos)", [s for s in w5c if s["tf15_roto"] is True]),
    ]
    filas = []
    for nombre, sub in variantes:
        if not sub:
            filas.append({"variante": nombre, "n": 0, "why": "sin señales"})
            continue
        c_toque = cell(sub, "hit_mid30")
        conres = [s for s in sub if s.get("barrera") is not None]
        nb = len(conres)
        wb = sum(1 for s in conres if s["barrera"] == 1)
        ne_b = n_efectiva(conres)
        exp = wilson_lb_expectancy(wb, max(nb, 1), 1.0, 0.5) if nb else None
        exp_eff = wilson_lb_expectancy(round(wb / nb * ne_b), round(ne_b), 1.0, 0.5) if nb else None
        filas.append({
            "variante": nombre, "n": len(sub), "n_eff": c_toque["n_eff"],
            "p_toque": c_toque["p"], "wilson_toque": [c_toque["wilson_lo"], c_toque["wilson_hi"]],
            "n_barrera": nb, "n_eff_barrera": None if ne_b is None else round(ne_b, 1),
            "sin_resolver": len(sub) - nb,
            "p_barrera": round(100.0 * wb / nb, 1) if nb else None,
            "exp_barrera_crudo": None if exp is None else round(exp["exp"], 4),
            "exp_lb_n_eff": None if exp_eff is None else round(exp_eff["exp_lo"], 4),
            "ambiguas_pct": round(100.0 * sum(1 for s in conres if s.get("barrera_ambig")) / nb, 1) if nb else None,
        })
    # contraste directo: 15m roto vs 15m no roto (grupos disjuntos)
    a = [s for s in conocidos if s["tf15_roto"] is True]
    b = [s for s in conocidos if s["tf15_roto"] is False]
    pv_toque = prueba(a, b, "hit_mid30")
    ab = [s for s in a if s.get("barrera") is not None]
    bb = [s for s in b if s.get("barrera") is not None]
    pv_barr = prueba(ab, bb, "barrera") if ab and bb else None
    a2 = [s for s in w5c if s["tf15_roto"] is False]
    a3 = [s for s in w5c if s["tf15_roto"] is True]
    pv_23 = prueba(a3, a2, "hit_mid30") if a2 and a3 else None
    out = {"variantes": filas,
           "contraste_15m_roto_vs_no": {"pval_toque": pv_toque, "pval_barrera": pv_barr},
           "contraste_bot_3TF_vs_2TF": {"pval_toque": pv_23, "n_2tf": len(a2), "n_3tf": len(a3)},
           "cobertura_15m": {
               "n_total": len(pooled), "n_con_15m_conocido": len(conocidos),
               "n_15m_roto": len(a),
               "pct_15m_roto": round(100.0 * len(a) / len(conocidos), 1) if conocidos else None},
           "nota": ("Barrera: TP=media BB congelada, SL=medio gap en contra, "
                    "primer toque manda, barra ambigua -> SL, timeout=NULL (no es "
                    "victoria). NO se ha corrido el null de entrada aleatoria de "
                    "scripts/null_control.py sobre estas variantes: esto es un "
                    "CONTRASTE CONDICIONADO, no un veredicto PROVEN.")}
    return out


def emit_grid_md(grid, fleet):
    F = fdefs()
    lines = []
    fn = list(F.keys())
    hdr = "| ticker | base n | base P% | " + " | ".join(f.split('_')[0] + "_" + "_".join(f.split('_')[1:]) for f in fn) + " |"
    lines.append("Celdas: `P% (n) [uplift]` — outcome = toca la media BB20-1m en 30 min.")
    lines.append("")
    lines.append(hdr)
    lines.append("|" + "---|" * (3 + len(fn)))
    for sym, g in sorted(grid.items()):
        b = g["base"]
        row = [sym.upper(), str(b["n"]), f"{b['p']}"]
        for f in fn:
            c = g["filters"][f]
            row.append(f"{c['p']} ({c['n']}) [{c['uplift']:+.0f}]" if c["n"] else "—")
        lines.append("| " + " | ".join(row) + " |")
    fb = fleet["base"]
    row = ["**FLOTA**", str(fb["n"]), f"{fb['p']}"]
    for f in fn:
        c = fleet["filters"][f]
        row.append(f"{c['p']} ({c['n']}) [{c['uplift']:+.1f}]" if c["n"] else "—")
    lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main():
    fleet_syms = [s.lower() for s in
                  open(os.path.join(REPO, "data", "fleet.txt")).read().split()]
    results = {}
    if os.path.exists(RESULTS):
        results = json.load(open(RESULTS))

    if "--tf15" in sys.argv:
        results = {k: v for k, v in results.items() if not v.get("error")}
        tf = analizar_tf15(results)
        cov = tf["cobertura_15m"]
        print("cobertura 15m: %d señales, %d con estado 15m conocido, %d con el 15m "
              "TAMBIEN roto (%.1f%%)" % (cov["n_total"], cov["n_con_15m_conocido"],
                                         cov["n_15m_roto"], cov["pct_15m_roto"]))
        print("%-34s %6s %7s %8s %16s %8s %9s %11s" %
              ("variante", "n", "n_eff", "P_toque", "wilson_toque", "n_barr", "P_barr", "expLB_neff"))
        for r in tf["variantes"]:
            if not r.get("n"):
                print("%-34s %6d  (sin señales)" % (r["variante"], 0)); continue
            print("%-34s %6d %7.1f %8.1f %16s %8d %9s %11s" %
                  (r["variante"], r["n"], r["n_eff"], r["p_toque"],
                   "[%.1f, %.1f]" % tuple(r["wilson_toque"]), r["n_barrera"],
                   r["p_barrera"], r["exp_lb_n_eff"]))
        c = tf["contraste_15m_roto_vs_no"]
        print("contraste 15m-roto vs 15m-no-roto: pval toque=%s  pval barrera=%s"
              % (None if c["pval_toque"] is None else round(c["pval_toque"], 4),
                 None if c["pval_barrera"] is None else round(c["pval_barrera"], 4)))
        c2 = tf["contraste_bot_3TF_vs_2TF"]
        print("contraste BOT 3TF vs 2TF (n=%d vs %d): pval toque=%s"
              % (c2["n_3tf"], c2["n_2tf"],
                 None if c2["pval_toque"] is None else round(c2["pval_toque"], 4)))
        print(tf["nota"])
        out = os.path.join(DATA, "bcomp_tf15.json")
        with open(out, "w") as f:
            json.dump(tf, f, indent=1, ensure_ascii=False)
        print("escrito %s" % out)
        return

    if "--analyze" in sys.argv:
        results = {k: v for k, v in results.items() if not v.get("error")}
        grid, fleet, pooled = analyze(results)
        write_outputs(grid, fleet)
        print(emit_grid_md(grid, fleet))
        json.dump({"grid": grid, "fleet": fleet},
                  open(os.path.join(DATA, "bcomp_grid.json"), "w"), indent=1)
        return

    todo = [s for s in fleet_syms if s not in results or "--force" in sys.argv]
    for sym in todo:
        path = os.path.join(DATA, f"bars30d_{sym}.csv")
        if not os.path.exists(path):
            print(f"{sym}: sin datos ({path}) — pendiente")
            continue
        try:
            res = run_ticker(sym)
        except Exception as e:
            res = {"error": str(e), "signals": []}
        results[sym] = res
        json.dump(results, open(RESULTS, "w"))
        ns = len(res.get("signals", []))
        print(f"{sym}: {ns} señales elastic | {res.get('band_walks_5m', '?')} band-walks | "
              f"{res.get('n_days', '?')} dias | {res.get('error', '')}")


if __name__ == "__main__":
    main()
