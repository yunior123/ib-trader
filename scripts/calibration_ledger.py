#!/usr/bin/env python
"""calibration_ledger.py — cierra el loop: registra cada plan/señal, lo califica
contra el resultado real, y CALCULA la probabilidad empirica por TIPO de setup
(no por ticker). Las probabilidades de los PDF dejan de ser adivinadas y pasan a
ser medidas. Nada hardcoded: el bucket es (setup_type x regimen), y una prob solo
se reporta con su n y su intervalo de confianza Wilson.

Subcomandos:
  record   — tras generar planes: apila filas a data/calib_log.jsonl (una por setup)
  grade    — al cierre (16:20): califica las filas sin resultado con el OHLC real
  calibrate— agrega el histórico -> data/calibration.json (lo lee el generador)
  report   — imprime la tabla de tasas medidas

SEÑAL-SOLAMENTE. Aditivo: si data/calibration.json no existe, el generador sigue
con sus heurísticas (degradación limpia). 2026-07-21."""
import argparse, json, math, os, time, warnings
warnings.filterwarnings("ignore")
import yfinance as yf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
LOG = "data/calib_log.jsonl"
OUT = "data/calibration.json"
BARRIER_OUT = "data/calibration_barrier.json"   # ficha #1 (aditivo, fichero aparte)
BARRIER_MIN_N = 50  # n RESUELTA minima para publicar una celda de barrera
MIN_N = 20          # muestra minima para confiar en una tasa medida
DECAY_DAYS = 120    # las filas mas viejas pesan menos (mercado cambia)

def wilson(w, n, z=1.96):
    """Intervalo de confianza Wilson (bajo) — evita creer en tasas de muestra chica."""
    if n == 0: return 0.0, 0.0, 0.0
    p = w / n
    d = 1 + z*z/n
    c = p + z*z/(2*n)
    m = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return p, (c-m)/d, (c+m)/d

# ---------- record ----------
def record(setups):
    """setups: lista de dicts con keys date,sym,setup_type,regime,direction,
       entry,target,stop,pred_prob. Apila; grade los cerrara luego."""
    with open(LOG, "a") as f:
        for s in setups:
            s.setdefault("result", None)
            f.write(json.dumps(s) + "\n")
    return len(setups)

def record_from_ranking(planes_dir):
    """Extrae setups de los x_drafts + ranking.json de un dir de planes ya generado.
    Parsea ENTRADA/TARGET/STOP de los drafts (formato del x_draft actual)."""
    import re, glob
    rows = []
    date = os.path.basename(planes_dir).replace("planes-", "")
    try:
        rank = {r["sym"]: r for r in json.load(open(os.path.join(planes_dir, "ranking.json")))}
    except Exception:
        rank = {}
    for dpath in glob.glob(os.path.join(planes_dir, "x_drafts", "*.txt")):
        sym = os.path.basename(dpath)[:-4]
        if sym == "COMBO": continue
        txt = open(dpath).read()
        def num(pat):
            m = re.search(pat, txt)
            return float(m.group(1)) if m else None
        entry = num(r"ENTRADA:\s*reclaim de ([\d.]+)")
        target = num(r"TARGET:\s*([\d.]+)")
        stop = num(r"STOP MENTAL:\s*([\d.]+)")
        prob = num(r"prob ~(\d+)%")
        pisoB = num(r"piso ([\d.]+); si rompe")
        tgtB = num(r"target ([\d.]+)\.")
        reg = "POSITIVO" if "🧲" in txt else "NEGATIVO"
        if entry and target and stop:
            rows.append(dict(date=date, sym=sym, setup_type="reclaim_wall", regime=reg,
                             direction="bull", entry=entry, target=target, stop=stop,
                             pred_prob=(prob or 50)/100, result=None))
        if pisoB and tgtB:
            rows.append(dict(date=date, sym=sym, setup_type="breakdown", regime=reg,
                             direction="bear", entry=pisoB, target=tgtB, stop=pisoB*1.004,
                             pred_prob=0.45, result=None))
    return record(rows)

# ---------- grade ----------
def grade():
    """Para cada fila sin result, baja el OHLC de su fecha y decide:
    no_entry (nunca imprimio la entrada), win (target antes que stop), loss (stop antes)."""
    if not os.path.exists(LOG): return 0
    rows = [json.loads(l) for l in open(LOG) if l.strip()]
    cache = {}
    graded = 0
    for s in rows:
        if s.get("result") is not None: continue
        key = (s["sym"], s["date"])
        if key not in cache:
            try:
                h = yf.Ticker(s["sym"]).history(start=s["date"], period="5d", interval="15m")
                cache[key] = h
            except Exception:
                cache[key] = None
        h = cache[key]
        if h is None or len(h) == 0: continue
        # solo barras del propio dia
        d = h[h.index.strftime("%Y-%m-%d") == s["date"]]
        if len(d) < 3: continue
        bull = s["direction"] == "bull"
        # ¿imprimio la entrada en algun momento del dia?
        printed = (d.High >= s["entry"]) if bull else (d.Low <= s["entry"])
        if not printed.any():
            s["result"] = "no_entry"; graded += 1; continue
        # CORTE TEMPORAL desde la barra que IMPRIME la entrada, no una mascara.
        #
        # Aqui vivia el defecto A (hunt 2026-07-24): `after = d[d.High >= entry]`
        # seleccionaba "las barras cuyo High supera la entrada", no "las barras
        # posteriores a la entrada". Las barras del retroceso —donde vive el
        # STOP— tienen el High por debajo de la entrada, asi que la mascara las
        # BORRABA y el recorrido secuencial nunca veia el stop: la perdida se
        # registraba como GANANCIA. Simetrico en bear con el rebote.
        # Medido sobre el ledger vivo del 2026-07-21 replayado contra poly_bars:
        # ver docs/ + el mensaje del commit.
        i0 = int(printed.values.argmax())      # primera barra que imprime
        after = d.iloc[i0:]                    # todo lo que pasa DESPUES, en orden
        # Nota de honestidad: en la barra de entrada no hay ruta sub-barra, asi
        # que si esa misma barra toca el stop se resuelve STOP PRIMERO
        # (conservador). Es la misma regla que barrier_labels.triple_barrier.
        res = "open"
        for _, bar in after.iterrows():
            if bull:
                if bar.Low <= s["stop"]: res = "loss"; break
                if bar.High >= s["target"]: res = "win"; break
            else:
                if bar.High >= s["stop"]: res = "loss"; break
                if bar.Low <= s["target"]: res = "win"; break
        s["result"] = res if res != "open" else ("win" if (
            (float(d.Close.iloc[-1]) >= s["target"]) if bull else (float(d.Close.iloc[-1]) <= s["target"])) else "loss")
        graded += 1
    with open(LOG, "w") as f:
        for s in rows: f.write(json.dumps(s) + "\n")
    return graded

# ---------- calibrate ----------
def calibrate():
    """Agrega por (setup_type x regimen) con decaimiento temporal y Wilson.
    Escribe data/calibration.json que el generador lee para reemplazar la prob adivinada."""
    if not os.path.exists(LOG): return {}
    rows = [json.loads(l) for l in open(LOG) if l.strip()]
    now = time.time()
    buckets = {}
    for s in rows:
        if s.get("result") not in ("win", "loss"): continue  # no_entry no cuenta para acierto direccional
        try:
            age = (now - time.mktime(time.strptime(s["date"], "%Y-%m-%d"))) / 86400
        except Exception:
            age = 0
        w = math.exp(-age / DECAY_DAYS)  # decaimiento suave
        k = f"{s['setup_type']}|{s['regime']}"
        b = buckets.setdefault(k, dict(wsum=0.0, nsum=0.0, raw_w=0, raw_n=0))
        b["nsum"] += w; b["raw_n"] += 1
        if s["result"] == "win": b["wsum"] += w; b["raw_w"] += 1
    out = {}
    for k, b in buckets.items():
        p, lo, hi = wilson(b["raw_w"], b["raw_n"])
        # tasa efectiva ponderada por decaimiento
        eff = b["wsum"] / b["nsum"] if b["nsum"] else p
        out[k] = dict(rate=round(eff, 3), ci_low=round(lo, 3), ci_high=round(hi, 3),
                      n=b["raw_n"], wins=b["raw_w"], trust=b["raw_n"] >= MIN_N)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, OUT)   # order_engine/direction_view/daily_fleet_plans lo leen en vivo
    return out

# ---------- barrera (ficha #1, ADITIVO — no toca calibrate() ni OUT) ----------
def wilson_lb_expectancy(wins, n, k_tp, k_sl, z=1.96):
    """Expectancia en unidades de ATR y su CI, derivados del Wilson del win rate.
        E = p*k_tp - (1-p)*k_sl
    La ficha #1 manda elegir (k_tp,k_sl,H) por el LIMITE INFERIOR de la
    EXPECTANCIA, no por el win rate: un 0.60 con k_tp=0.5 y k_sl=1.0 pierde.
    Devuelve None si n==0 (no hay expectancia plausible que inventar)."""
    if n <= 0:
        return None
    p, lo, hi = wilson(wins, n, z)
    exp = lambda q: q * k_tp - (1 - q) * k_sl
    return dict(p=p, exp=exp(p), exp_lo=exp(lo), exp_hi=exp(hi),
                wr_ci=(lo, hi), n=n, wins=wins, k_tp=k_tp, k_sl=k_sl)


def calibrate_barrier(db=None, min_n=BARRIER_MIN_N, out=BARRIER_OUT):
    """Agrega trades.db barrier_outcomes por (source, k_tp, k_sl, H).
    El TIMEOUT no entra en el denominador (es NULL, no una victoria) — se cuenta
    aparte como `timeouts`. Escribe BARRIER_OUT (fichero PROPIO: no contamina
    data/calibration.json, que sigue siendo la calibracion por setup x regimen).
    Devuelve {} si la tabla no existe: el consumidor degrada, pero NUNCA recibe
    una probabilidad inventada."""
    import sqlite3
    db = db or os.path.join(REPO, "trades.db")
    c = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30)
    try:
        have = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                         "name='barrier_outcomes'").fetchone()
        if not have:
            return {}
        rows = c.execute("SELECT source,k_tp,k_sl,H,label,ambig FROM barrier_outcomes").fetchall()
    finally:
        c.close()
    cells = {}
    for source, k_tp, k_sl, H, label, ambig in rows:
        b = cells.setdefault((source, k_tp, k_sl, H),
                             dict(n=0, wins=0, timeouts=0, ambig=0))
        b["ambig"] += ambig or 0
        if label is None:
            b["timeouts"] += 1
        else:
            b["n"] += 1
            b["wins"] += label
    res = {}
    for (source, k_tp, k_sl, H), b in cells.items():
        e = wilson_lb_expectancy(b["wins"], b["n"], k_tp, k_sl)
        key = "barrier:%s|%s/%s/%s" % (source, k_tp, k_sl, H)
        if e is None:
            res[key] = dict(source=source, k_tp=k_tp, k_sl=k_sl, H=H, n=0,
                            timeouts=b["timeouts"], rate=None,
                            verdict="DATA-INSUFFICIENT")
            continue
        res[key] = dict(source=source, k_tp=k_tp, k_sl=k_sl, H=H,
                        n=b["n"], wins=b["wins"], timeouts=b["timeouts"],
                        rate=round(e["p"], 4),
                        ci_low=round(e["wr_ci"][0], 4), ci_high=round(e["wr_ci"][1], 4),
                        expectancy=round(e["exp"], 4),
                        exp_ci=[round(e["exp_lo"], 4), round(e["exp_hi"], 4)],
                        ambig=b["ambig"],
                        ambig_pct=round(b["ambig"] / b["n"], 4),
                        trust=b["n"] >= min_n,
                        verdict=("APTA" if e["exp_lo"] > 0 else
                                 "NO-TRADE" if e["exp_hi"] >= 0 else "NEGATIVA")
                                if b["n"] >= min_n else "DATA-INSUFFICIENT")
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    os.replace(tmp, out)
    return res


def report():
    if not os.path.exists(OUT):
        print("sin calibracion aun — correr grade+calibrate tras algunos dias"); return
    d = json.load(open(OUT))
    print(f"{'setup|regimen':32} {'n':>4} {'win%':>6} {'CI95':>13} {'confiable':>9}")
    for k, v in sorted(d.items(), key=lambda x: -x[1]["n"]):
        print(f"{k:32} {v['n']:>4} {v['rate']*100:>5.0f}% [{v['ci_low']*100:>3.0f}-{v['ci_high']*100:>3.0f}]% {'SI' if v['trust'] else 'no (provisional)':>9}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "grade", "calibrate", "report", "eod",
                                    "barrier"])
    _hoy = os.environ.get("IBT_DESKTOP_HOY", os.path.expanduser("~/Desktop/ib-trader/hoy"))
    _pd = os.path.join(_hoy, f"planes-{time.strftime('%Y-%m-%d')}")
    if not os.path.isdir(_pd):   # legado pre-repunto (Desktop raiz)
        _old = os.path.expanduser(f"~/Desktop/planes-{time.strftime('%Y-%m-%d')}")
        if os.path.isdir(_old):
            _pd = _old
    ap.add_argument("--dir", default=_pd)
    a = ap.parse_args()
    if a.cmd == "record":
        print("registradas", record_from_ranking(a.dir), "filas")
    elif a.cmd == "grade":
        print("calificadas", grade(), "filas")
    elif a.cmd == "calibrate":
        c = calibrate(); print(json.dumps(c, indent=1))
    elif a.cmd == "report":
        report()
    elif a.cmd == "barrier":
        b = calibrate_barrier()
        if not b:
            print("sin barrier_outcomes — correr scripts/barrier_labels.py build")
        else:
            print(f"{len(b)} celdas de barrera -> {BARRIER_OUT}")
            for k, v in sorted(b.items(), key=lambda x: -(x[1].get("n") or 0))[:15]:
                print(f"  {k:38} n={v.get('n')} WR={v.get('rate')} "
                      f"exp={v.get('expectancy')} {v.get('verdict')}")
    elif a.cmd == "eod":  # cierre: califica ayer + recalibra
        print("calificadas", grade(), "| buckets", len(calibrate()))
        report()

if __name__ == "__main__":
    main()
