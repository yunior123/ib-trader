#!/usr/bin/env python3
"""yoel_backtest.py — BACKTEST HONESTO del subconjunto MEDIBLE de la doctrina
Yoel Sardinas (caps X-XII). SEÑAL-SOLAMENTE. Jamas look-ahead.

Genera señales en el formato compartido (docs/ENGINE-SCORING-SPEC.md):
    epoch,sym,side,kind,ref_px,target_px,stop_px
y las puntua con scripts/scorer.py (subproceso). WR + Wilson por estrategia y
por ticker, neto de spread. Escribe:
    data/backtest/scores_yoel.json   (agregado de todas las estrategias)
    data/backtest/scores_yoel_<estr>.json (por estrategia)
    data/yoel_probs.json             (por estrategia x ticker, para gateo futuro)

======================= DECLARACION DE HONESTIDAD =======================
El libro usa 4 herramientas (BB 20/2, medias simples 20/40/100/200, VOLUMEN
con MA50, velas+trendlines), proceso TOP-DOWN 15m->1H->1D, instrumento opciones
semanales con take-profit +100% de la PRIMA y SIN stop. Nada de eso es medible
1:1 sobre barras del subyacente. Lo que SI medimos, y lo que aproximamos u
omitimos, queda declarado abajo por estrategia. La doctrina de la casa manda:
las probabilidades son MEDIDAS, no las afirmaciones del autor (el libro dice
">80% fiable" / "88% dentro de 2sigma" — NO lo medimos como verdad, lo testeamos).

DATOS: data/backtest/bars3mo5m_<sym>.csv (5m nativo CON volumen, 62 dias RTH
9:30-15:55 ET; SPCX 27d, SKHY 9d = series cortas, se marcan). El volumen del
5m nativo es lo que habilita el FILTRO TRANSVERSAL (vol>MA50), la pieza nueva
y testeable de las estrategias 5-8.

APROXIMACIONES (declaradas):
 * "1D SMA20" del libro (rebote punto medio, est 3-4) -> lo aproximamos con
   SMA20 sobre barras de ~1H (bucket epoch%3600), que es el TF intermedio que
   el libro usa para confirmar la entrada. No hay 1D suficiente (62 dias) para
   una SMA20 diaria util; el 1H captura el mismo concepto "toca la media y
   rebota sin cruzarla" a resolucion medible.
 * Barras 1H por bucket de reloj (9:30 cae en el bucket de 9:00, parcial) — es
   una aproximacion; el libro dibuja velas 1H alineadas a la sesion. Declarado.
 * TARGET/STOP: el libro cierra la OPCION a +100% de prima, sin stop. Eso no se
   mide en el subyacente. Estandarizamos target/stop = +-0.35% (35 bps) sobre
   el subyacente, LA MISMA convencion de scalp que ya usan flow (62.5%) y
   band-open — asi el WR es DIRECTAMENTE comparable a nuestros baselines y el
   A/B de volumen queda limpio (solo cambia el filtro, no el objetivo).
 * Trendline-break (est 1-2): NO se codifica 1:1 una linea de tendencia sobre
   pivotes. Se APROXIMA con ruptura del maximo/minimo de N barras tras cruce de
   la SMA20-1H (cambio de tendencia). Marcado 'APROX' — es la pieza mas debil.

FILTRO TRANSVERSAL (est 5-8) — LA PREGUNTA DE YUNIOR: se mide CON y SIN el
filtro vol>MA50 para responder: el volumen AÑADE edge sobre el band-open que ya
medimos (56%)? Ambos buckets se reportan.

Sin look-ahead: cada señal se decide con el OHLC de una barra 5m YA CERRADA y
se estampa con epoch = inicio de esa barra; el scorer entra al OPEN de la barra
siguiente (start>epoch). Indicadores 1H usan solo horas COMPLETADAS antes del
inicio de la barra de señal.
"""
import datetime as dt
import json
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

REPO = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
CACHE = os.path.join(REPO, "data", "backtest")
ET = ZoneInfo("America/New_York")

TARGET_PCT = 0.0035   # +-0.35% scalp, convencion de la casa (comparable a flow/band-open)
COOLDOWN_BARS = 6     # 30 min por sym+estrategia+lado (anti-cluster)
SHORT_SERIES = {"SPCX", "SKHY"}  # se marcan como series cortas


def load_5m(sym):
    """Barras 5m RTH (epoch,o,h,l,c,v) ordenadas. None si no hay fichero."""
    path = os.path.join(CACHE, f"bars3mo5m_{sym.lower()}.csv")
    if not os.path.exists(path):
        return None
    bars = []
    with open(path) as f:
        for ln in f:
            p = ln.strip().split(",")
            if len(p) < 6 or not p[0].isdigit():
                continue
            try:
                bars.append((int(p[0]), float(p[1]), float(p[2]),
                             float(p[3]), float(p[4]), float(p[5])))
            except ValueError:
                continue
    if not bars:
        return None
    bars.sort(key=lambda b: b[0])
    # RTH weekday only (por seguridad; el cache ya viene RTH)
    out = []
    for b in bars:
        d = dt.datetime.fromtimestamp(b[0], ET)
        hm = d.hour * 100 + d.minute
        if d.weekday() < 5 and 930 <= hm < 1600:
            out.append(b)
    return out or None


def hourly_bars(bars5):
    """Agrega 5m -> ~1H por bucket epoch%3600. Devuelve lista
    (start, o, h, l, c) ordenada. Bucket parcial incluido (declarado)."""
    agg = {}
    for e, o, h, l, c, v in bars5:
        k = e - e % 3600
        cur = agg.get(k)
        if cur is None:
            agg[k] = [k, o, h, l, c]
        else:
            cur[2] = max(cur[2], h)
            cur[3] = min(cur[3], l)
            cur[4] = c
    return [tuple(x) for _, x in sorted(agg.items())]


def sma(vals):
    return sum(vals) / len(vals) if vals else None


def atr_of(hbars, n=14):
    """ATR simple sobre barras 1H completadas (lista de closes de TR)."""
    if len(hbars) < 2:
        return None
    trs = []
    for i in range(1, len(hbars)):
        _, o, h, l, c = hbars[i]
        pc = hbars[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    trs = trs[-n:]
    return sum(trs) / len(trs) if trs else None


class HourlyView:
    """Indicadores 1H sin look-ahead: dado un epoch de barra 5m, devuelve
    SMA20/SMA40/ATR/slope usando SOLO horas cuyo bucket termino antes del
    inicio de esa barra (bucket_end = k+3600 <= epoch)."""

    def __init__(self, bars5):
        self.hb = hourly_bars(bars5)

    def completed_upto(self, epoch):
        return [b for b in self.hb if b[0] + 3600 <= epoch]

    def snapshot(self, epoch):
        h = self.completed_upto(epoch)
        if len(h) < 21:
            return None
        closes = [b[4] for b in h]
        sma20 = sma(closes[-20:])
        sma40 = sma(closes[-40:]) if len(closes) >= 40 else None
        sma20_prev = sma(closes[-24:-4]) if len(closes) >= 24 else None  # ~4h antes
        atr = atr_of(h)
        last_close = closes[-1]
        return {"sma20": sma20, "sma40": sma40, "sma20_prev": sma20_prev,
                "atr": atr, "last_close": last_close, "nhours": len(h)}


def vol_ma(bars5, j, n=50):
    """MA de volumen sobre las ultimas n barras 5m hasta j inclusive."""
    lo = max(0, j - n + 1)
    vs = [bars5[k][5] for k in range(lo, j + 1)]
    return sum(vs) / len(vs) if vs else None


def bb20(bars5, j, sigma=2.0):
    """BB(20,2) sobre closes de las 20 barras 5m HASTA j inclusive."""
    if j < 19:
        return None
    closes = [bars5[k][4] for k in range(j - 19, j + 1)]
    m = sma(closes)
    sd = (sum((c - m) ** 2 for c in closes) / len(closes)) ** 0.5
    return m - sigma * sd, m, m + sigma * sd


def day_index(bars5):
    """Devuelve lista paralela con el indice de barra dentro del dia RTH
    (0 = primera barra 9:30 del dia)."""
    idx = []
    prev_day = None
    k = 0
    for b in bars5:
        d = dt.datetime.fromtimestamp(b[0], ET).date()
        if d != prev_day:
            k = 0
            prev_day = d
        idx.append(k)
        k += 1
    return idx


def mk(epoch, sym, side, kind, ref):
    tp = ref * (1 + TARGET_PCT) if side == "LONG" else ref * (1 - TARGET_PCT)
    sp = ref * (1 - TARGET_PCT) if side == "LONG" else ref * (1 + TARGET_PCT)
    return f"{epoch},{sym},{side},{kind},{ref:.4f},{tp:.4f},{sp:.4f}"


# ------------------------- ESTRATEGIAS -------------------------

def gen_signals(sym, bars5):
    """Devuelve dict estrategia -> lista de lineas de señal."""
    hv = HourlyView(bars5)
    didx = day_index(bars5)
    out = {
        "rebote_sma20": [], "iman": [], "iman_novol": [],
        "bandopen": [], "bandopen_novol": [], "trendbreak_aprox": [],
    }
    cd = {}  # (estr, side) -> ultimo j

    def ok_cd(estr, side, j):
        key = (estr, side)
        last = cd.get(key)
        if last is not None and j - last < COOLDOWN_BARS:
            return False
        cd[key] = j
        return True

    n = len(bars5)
    for j in range(n):
        e, o, h, l, c, v = bars5[j]
        snap = hv.snapshot(e)
        vma = vol_ma(bars5, j)
        vol_cross = vma is not None and v > vma

        # ---- est 3-4: REBOTE punto medio SMA20 (~1H) ----
        if snap and snap["sma20"] and snap["atr"] and snap["sma20_prev"]:
            sma20, atr, slope = snap["sma20"], snap["atr"], snap["sma20"] - snap["sma20_prev"]
            near = (l <= sma20 <= h) or (abs(c - sma20) <= 0.2 * atr)
            if near and atr > 0:
                # UPTREND: precio sobre SMA20 y SMA20 subiendo; toca y NO cierra debajo
                if slope > 0 and c >= sma20 and c > snap["sma20"] * 0.999:
                    if ok_cd("rebote_sma20", "LONG", j):
                        out["rebote_sma20"].append(mk(e, sym, "LONG", "REBOTE_SMA20", c))
                # DOWNTREND: precio bajo SMA20 y SMA20 bajando; toca y NO cierra encima
                elif slope < 0 and c <= sma20:
                    if ok_cd("rebote_sma20", "SHORT", j):
                        out["rebote_sma20"].append(mk(e, sym, "SHORT", "REBOTE_SMA20", c))

        # ---- est 7-8: IMAN lejos de SMA20 + vela de reversion (+/- filtro vol) ----
        if snap and snap["sma20"] and snap["atr"] and snap["atr"] > 0:
            sma20, atr = snap["sma20"], snap["atr"]
            dist = c - sma20
            bearish = c < o
            bullish = c > o
            # A/B LIMPIO: ambos buckets con SU PROPIO cooldown; difieren SOLO por
            # el filtro de volumen (novol = poblacion base; iman = subconjunto vol>MA50)
            if dist <= -2 * atr and bullish:      # est 7: muy por DEBAJO, vela verde -> LONG (call rebote)
                if ok_cd("iman_novol", "LONG", j):
                    out["iman_novol"].append(mk(e, sym, "LONG", "IMAN_UP", c))
                if vol_cross and ok_cd("iman", "LONG", j):
                    out["iman"].append(mk(e, sym, "LONG", "IMAN_UP_VOL", c))
            elif dist >= 2 * atr and bearish:     # est 8: muy por ENCIMA, vela roja -> SHORT (put correccion)
                if ok_cd("iman_novol", "SHORT", j):
                    out["iman_novol"].append(mk(e, sym, "SHORT", "IMAN_DN", c))
                if vol_cross and ok_cd("iman", "SHORT", j):
                    out["iman"].append(mk(e, sym, "SHORT", "IMAN_DN_VOL", c))

        # ---- est 5-6: FUERA DE BANDA en APERTURA (+/- filtro vol) ----
        # primeras 2 barras RTH del dia (9:30-9:40); tendencia lateral aproximada
        if didx[j] < 2:
            bb = bb20(bars5, j)
            if bb:
                lo_b, mid_b, up_b = bb
                # sobrecompra: barra ENTERA sobre la banda -> fade SHORT (est 5, put)
                if l > up_b:
                    out["bandopen_novol"].append(mk(e, sym, "SHORT", "BANDOPEN_DN", c))
                    if vol_cross:
                        out["bandopen"].append(mk(e, sym, "SHORT", "BANDOPEN_DN_VOL", c))
                # sobreventa: barra ENTERA bajo la banda -> fade LONG (est 6, call)
                elif h < lo_b:
                    out["bandopen_novol"].append(mk(e, sym, "LONG", "BANDOPEN_UP", c))
                    if vol_cross:
                        out["bandopen"].append(mk(e, sym, "LONG", "BANDOPEN_UP_VOL", c))

        # ---- est 1-2: TRENDLINE-BREAK (APROX: ruptura N-barras + cruce SMA20-1H) ----
        if snap and snap["sma20"] and j >= 12:
            sma20 = snap["sma20"]
            prior_hi = max(bars5[k][2] for k in range(j - 12, j))
            prior_lo = min(bars5[k][3] for k in range(j - 12, j))
            # cambio AL ALZA: venia debajo de SMA20, ahora cierra encima y rompe max 12b
            if c > sma20 and c > prior_hi and o <= sma20:
                if ok_cd("trendbreak_aprox", "LONG", j):
                    out["trendbreak_aprox"].append(mk(e, sym, "LONG", "TRENDBREAK_UP", c))
            elif c < sma20 and c < prior_lo and o >= sma20:
                if ok_cd("trendbreak_aprox", "SHORT", j):
                    out["trendbreak_aprox"].append(mk(e, sym, "SHORT", "TRENDBREAK_DN", c))

    return out


def score(name, signals_lines):
    """Escribe CSV y llama scorer.py; devuelve el JSON parseado o None."""
    if not signals_lines:
        return None
    csv_path = os.path.join(CACHE, f"signals_yoel_{name}.csv")
    with open(csv_path, "w") as f:
        f.write("epoch,sym,side,kind,ref_px,target_px,stop_px\n")
        f.write("\n".join(signals_lines) + "\n")
    py = os.path.join(REPO, "venv", "bin", "python")
    if not os.path.exists(py):
        py = sys.executable
    r = subprocess.run(
        [py, os.path.join(REPO, "scripts", "scorer.py"), csv_path,
         "--name", f"yoel_{name}", "--bars-dir", CACHE,
         "--engine", f"yoel:{name}"],
        capture_output=True, text=True, cwd=REPO)
    print(r.stdout, end="")
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return None
    jp = os.path.join(CACHE, f"scores_yoel_{name}.json")
    with open(jp) as f:
        return json.load(f)


def main():
    fleet = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    STRATS = ["rebote_sma20", "iman", "iman_novol",
              "bandopen", "bandopen_novol", "trendbreak_aprox"]
    all_lines = {s: [] for s in STRATS}
    missing = []
    for sym in fleet:
        bars5 = load_5m(sym)
        if bars5 is None:
            missing.append(sym)
            continue
        sig = gen_signals(sym, bars5)
        for s in STRATS:
            all_lines[s].extend(sig[s])

    scores = {}
    for s in STRATS:
        js = score(s, all_lines[s])
        if js:
            scores[s] = js

    # yoel_probs.json: por estrategia x ticker (para gateo futuro)
    probs = {}
    for s, js in scores.items():
        probs[s] = {"global": js["global"], "por_ticker": js["por_ticker"]}
    with open(os.path.join(REPO, "data", "yoel_probs.json"), "w") as f:
        json.dump(probs, f, indent=1)

    # scores_yoel.json agregado
    agg = {
        "spec": "docs/ENGINE-SCORING-SPEC.md",
        "target_pct": TARGET_PCT,
        "missing_symbols": missing,
        "short_series": sorted(SHORT_SERIES),
        "por_estrategia": {s: {"global": js["global"],
                               "spread_impact_global": js.get("spread_impact_global"),
                               "por_ticker": js["por_ticker"]}
                           for s, js in scores.items()},
    }
    with open(os.path.join(CACHE, "scores_yoel.json"), "w") as f:
        json.dump(agg, f, indent=1)

    print("\n=================== RESUMEN YOEL ===================")
    base = {"elastic_1m": 0.58, "band_open": 0.56, "combo": 0.69, "toque_ligero": 0.60}
    print(f"baselines casa: {base}")
    for s in STRATS:
        js = scores.get(s)
        if not js:
            print(f"{s:18s}  sin señales")
            continue
        g = js["global"]
        wr = g["wr"]
        wl = g["wilson_lo"]
        wr_s = "s/d" if wr is None else f"{wr*100:.1f}%"
        wl_s = "s/d" if wl is None else f"{wl*100:.1f}%"
        print(f"{s:18s} n={g['n']:4d} win={g['wins']:3d} loss={g['losses']:3d} "
              f"tout={g['timeouts']:3d} WR={wr_s:>6} Wilson={wl_s:>6} "
              f"PnL={g['pnl_bps_median']}")
    print(f"\nescrito: data/backtest/scores_yoel.json + scores_yoel_*.json + data/yoel_probs.json")
    if missing:
        print(f"sin barras 5m: {missing}")


if __name__ == "__main__":
    main()
