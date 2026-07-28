#!/usr/bin/env python3
"""dip_alert.py — ALERTA DE DIP DE LA FLOTA con GATE DE VALUACION
(2026-07-22, mision B5, orden Yunior: "no queremos comprar una empresa
inflada; Forward P/E entre otros factores; sin ruido, alertas reales").

DIP TECNICO real (anti-ruido, nada de cada -1%):
  precio cae >= max(2.0 x ATR14 diario, 1.5%) desde el high de 5 dias
  Y estabilizacion IMPRESA: 2 lecturas NBBO consecutivas (>=60s) sin nuevo
  minimo (no agarrar el cuchillo). Ademas VETO si el 5m esta en band-walk
  bajista BB(20,2) — un dip DENTRO de un desplome no es dip, es cuchillo.

GATE DE VALUACION (data/finviz_valuation.csv, 1x/dia via finviz_valuation.py):
  inflada = Forward P/E > FPE_MAX o PEG > PEG_MAX -> banner "DIP VETADO" SIN voz.
  Sin datos de valuacion (ETFs: QQQ SPY SMH GLD XLK EWY DRAM SPCX) -> gate n/a,
  el dip tecnico igual canta. (SKHY en Finviz es el ADR de SK Hynix y SI trae
  Forward P/E — el gate le aplica.)

UMBRALES (elegidos mirando la flota REAL 2026-07-22 — tabla en
docs/DIP-ALERT-2026-07-22.md): Forward P/E de la flota va de 5.28 (SKHY) a
150.97 (TSLA) con mediana ~22; FPE_MAX=40 deja fuera solo los outliers
caros (TSLA 151, INTC 63, AMD 40.8 marginal). PEG mediana ~0.8; PEG_MAX=2.5
veta crecimiento sobre-pagado (TSLA 5.91, QCOM 4.16, AAPL 2.61 marginal).

Probabilidades MEDIDAS: data/dip_probs.json (dip_backtest.py, 1 año diario).
Ticker "enabled": false (P(rebote)<50% con n>=10) -> la alerta LO SALTA.

Anti-ruido: max 1 alerta/ticker/dia (persistido, sobrevive restart);
nada 9:30-9:45; RTH 9:45-16:00, loop 60s, muere 16:00.
DIP_TEST=1 -> una pasada sin voz/banner/log, imprime que haria, sale.
SEÑAL-SOLAMENTE (jamas ordenes). Degradacion limpia por dato faltante.
"""
import csv, json, os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
try:
    from optgate import opt_vehicle
except Exception:                                   # degradacion limpia
    def opt_vehicle(sym): return "OPCIONES s/d — default ACCIONES"

# ------- umbrales configurables (razonados arriba, doc con la tabla real) ---
FPE_MAX = 40.0          # Forward P/E: > esto = inflada (outliers de la flota)
PEG_MAX = 2.5           # PEG: > esto = crecimiento sobre-pagado
ATR_MULT = 2.0          # dip = caida >= max(2 x ATR14d, 1.5%) desde high 5d
PCT_FLOOR = 0.015
STABLE_READS = 2        # lecturas NBBO sin nuevo minimo (>=60s entre si)
NBBO_MAX_AGE = 180      # s; NBBO mas viejo = ticker mudo esta vuelta
LOOP_S = 60
TEST = os.environ.get("DIP_TEST") == "1"

def fleet():
    try:
        return [s.upper() for s in open("data/fleet.txt").read().split()]
    except Exception:
        return ["QQQ", "SPY", "NVDA", "MU", "SMH", "DRAM"]

def say(title, msg, voice=True, prio="SIGNAL", sound="ProAlert", voice_msg=None):
    """Patron bollinger_alarm.say(): voz speak.sh + banner osascript + log Desktop.
    voice_msg: version corta para la voz (Yunior 2026-07-28 "sencillo, que un niño
    pequeño pueda entender"); el banner y el log se quedan con el `msg` completo."""
    if TEST:
        print(f"[DIP_TEST {'VOZ' if voice else 'banner'}] {title} | {msg}")
        return
    corto = voice_msg or msg
    if voice:
        subprocess.Popen(["/bin/bash", "scripts/speak.sh", prio, corto],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      f'display notification "{corto}" with title "{title}" sound name "{sound}"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt = time.localtime()
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")
    if voice:
        import notify_short; notify_short.push(title, corto)

# ------------------- fuentes de datos (todas con fallback) ------------------
def load_valuation():
    """ticker -> {fpe, peg, pe, ...} floats o None. {} si no hay CSV."""
    out = {}
    try:
        lines = [l for l in open("data/finviz_valuation.csv") if not l.startswith("#")]
        rd = csv.DictReader(lines)
        for row in rd:
            def num(k):
                v = (row.get(k) or "").replace("%", "").strip()
                try: return float(v)
                except ValueError: return None
            out[row["Ticker"].upper()] = {
                "fpe": num("Forward P/E"), "pe": num("P/E"), "peg": num("PEG"),
                "ps": num("P/S"), "pfcf": num("P/Free Cash Flow"),
                "epsny": num("EPS Growth Next Year"), "shortf": num("Short Float"),
                "rsi": num("Relative Strength Index (14)")}
    except Exception:
        pass
    return out

def load_probs():
    try:
        return json.load(open("data/dip_probs.json"))
    except Exception:
        return {}

def load_daily(syms):
    """yfinance 3mo diario UNA vez al arrancar -> {sym: (atr14, high5d)}."""
    out = {}
    try:
        import yfinance as yf
        data = yf.download(" ".join(syms), period="3mo", interval="1d",
                           group_by="ticker", auto_adjust=False,
                           progress=False, threads=True)
        for sym in syms:
            try:
                df = data[sym].dropna(subset=["High", "Low", "Close"])
                h, l, c = df["High"].tolist(), df["Low"].tolist(), df["Close"].tolist()
                if len(c) < 16:
                    continue
                trs = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1]))
                       for j in range(len(c) - 14, len(c))]
                out[sym] = (sum(trs) / 14, max(h[-5:]))
            except Exception:
                continue
    except Exception as e:
        print(f"dip_alert: yfinance diario fallo ({type(e).__name__}) — "
              f"sigo solo con los tickers que tenga", file=sys.stderr)
    return out

def nbbo_mid(sym):
    """data/nbbo_<sym>.txt 'EPOCH BID ASK' (1 linea, sobre-escrita). None si viejo."""
    try:
        f = open(f"data/nbbo_{sym.lower()}.txt").read().split()
        ts, bid, ask = int(float(f[0])), float(f[1]), float(f[2])
        if time.time() - ts > NBBO_MAX_AGE or bid <= 0 or ask <= 0:
            return None
        return (bid + ask) / 2
    except Exception:
        return None

def bars_of(sym, n=140):
    try:
        rows = [l.split() for l in open(f"data/bars_{sym.lower()}_ibkr.txt").readlines()[-n:]]
        return [(int(float(r[0])), float(r[1]), float(r[2]), float(r[3]), float(r[4]))
                for r in rows if len(r) >= 6]
    except Exception:
        return []

def bandwalk_down_5m(sym):
    """True = ultimo cierre 5m bajo la banda inferior BB(20,2) 5m (cuchillo)."""
    bars = bars_of(sym)
    agg = {}
    for t, o, h, l, c in bars:
        k = t - t % 300
        if k not in agg: agg[k] = [o, h, l, c]
        else:
            agg[k][1] = max(agg[k][1], h); agg[k][2] = min(agg[k][2], l); agg[k][3] = c
    A = sorted(agg.items())
    if len(A) < 21:
        return False                       # sin barras suficientes: no vetar
    cl = [v[3] for _, v in A[-21:-1]]
    m = sum(cl) / len(cl)
    sd = (sum((x - m) ** 2 for x in cl) / len(cl)) ** .5
    return A[-1][1][3] < m - 2 * sd

def intraday_high(sym):
    """High de HOY de las barras 1m (para no quedarnos con el high5d de las 9:45)."""
    bars = bars_of(sym, 500)
    lt = time.localtime()
    day0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    hs = [h for t, o, h, l, c in bars if t >= day0]
    return max(hs) if hs else None

# ------------------------------ gate de valuacion ---------------------------
def valuation_verdict(sym, val):
    """-> (inflada:bool|None, texto). None = sin datos (ETF / CSV ausente)."""
    d = val.get(sym)
    if not d or (d["fpe"] is None and d["peg"] is None):
        return None, "ETF/s-d: gate valuacion n/a"
    fpe, peg = d["fpe"], d["peg"]
    if (fpe is not None and fpe > FPE_MAX) or (peg is not None and peg > PEG_MAX):
        parts = []
        if fpe is not None and fpe > FPE_MAX: parts.append(f"FPE {fpe:.0f}")
        if peg is not None and peg > PEG_MAX: parts.append(f"PEG {peg:.1f}")
        return True, " ".join(parts)
    t = f"Forward PE {fpe:.0f}" if fpe is not None else "Forward PE s/d"
    if peg is not None:
        t += f", PEG {peg:.1f}"
    return False, t

def alerted_path():
    lt = time.localtime()
    return f"data/dip_alerted_{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt"

def load_alerted():
    try:
        return set(open(alerted_path()).read().split())
    except Exception:
        return set()

def mark_alerted(sym):
    if TEST:
        return
    with open(alerted_path(), "a") as f:
        f.write(sym + "\n")

# ---------------------------------- main ------------------------------------
def main():
    syms = fleet()
    val = load_valuation()
    probs = load_probs()
    daily = load_daily(syms)
    disabled = sorted(s for s in syms
                      if isinstance(probs.get(s), dict) and probs[s].get("enabled") is False)
    if disabled:
        print(f"dip_alert: tickers DISABLED por backtest (p<50, n>=10): {' '.join(disabled)}")
    if not val:
        print("dip_alert: sin data/finviz_valuation.csv — gate valuacion degradado a n/a",
              file=sys.stderr)
    print(f"dip_alert arriba: {len(syms)} tickers, daily={len(daily)}, "
          f"valuacion={len(val)}, probs={len([k for k in probs if not k.startswith('_')])}"
          f"{' [DIP_TEST]' if TEST else ''}")
    alerted = load_alerted()
    state = {}      # sym -> {"min": float, "stable": int, "last": ts}
    while True:
        lt = time.localtime()
        hm = lt.tm_hour * 100 + lt.tm_min
        if not TEST:
            if hm >= 1600 or lt.tm_wday >= 5:
                break
            if hm < 945:                       # jamas 9:30-9:45 (subasta)
                time.sleep(30); continue
        now = time.time()
        for sym in syms:
            if sym in alerted or sym in disabled:
                if TEST and sym in disabled:
                    print(f"[DIP_TEST] {sym}: SALTADO (disabled por backtest)")
                continue
            if sym not in daily:
                if TEST: print(f"[DIP_TEST] {sym}: sin daily yfinance — mudo")
                continue
            mid = nbbo_mid(sym)
            if mid is None:
                if TEST: print(f"[DIP_TEST] {sym}: NBBO viejo/ausente — mudo")
                continue
            atr14, high5_yf = daily[sym]
            ih = intraday_high(sym)
            high5 = max(high5_yf, ih) if ih else high5_yf
            drop = high5 - mid
            need = max(ATR_MULT * atr14, PCT_FLOOR * high5)
            st = state.setdefault(sym, {"min": mid, "stable": 0, "last": 0.0})
            # estabilizacion impresa: lecturas >=60s sin nuevo minimo
            if mid <= st["min"]:
                st["min"] = mid; st["stable"] = 0; st["last"] = now
            elif now - st["last"] >= 55:
                st["stable"] += 1; st["last"] = now
            if drop < need:
                if TEST:
                    print(f"[DIP_TEST] {sym}: sin dip (-{drop/high5*100:.2f}% vs "
                          f"umbral -{need/high5*100:.2f}% del high5d {high5:.2f})")
                continue
            if st["stable"] < STABLE_READS and not TEST:
                continue                        # dip aun sin estabilizar (cuchillo)
            if bandwalk_down_5m(sym):
                if TEST: print(f"[DIP_TEST] {sym}: dip PERO band-walk bajista 5m — cuchillo, mudo")
                continue
            if TEST and st["stable"] < STABLE_READS:
                print(f"[DIP_TEST] {sym}: DIP {drop/high5*100:.1f}% pero estabilizacion "
                      f"{st['stable']}/{STABLE_READS} lecturas — esperaria")
                continue
            pct = drop / high5 * 100
            inflada, vtxt = valuation_verdict(sym, val)
            pd = probs.get(sym) if isinstance(probs.get(sym), dict) else {}
            pr, n = pd.get("p_rebound_3d"), pd.get("n", 0)
            ptxt = (f" Prob medida de rebote {pr*100:.0f} por ciento en 3 dias (n={n})."
                    if pr is not None else "")
            zona = st["min"]
            if inflada:
                say("🩸 DIP VETADO", f"DIP VETADO por valuacion en {sym}: -{pct:.1f}% "
                    f"desde el high de 5 dias, pero inflada ({vtxt}).", voice=False)
            else:
                say("🩸 DIP REAL", f"DIP REAL en {sym}: -{pct:.1f}% desde el high de "
                    f"5 dias, estabilizado. "
                    f"{'Valuacion sana: ' + vtxt if inflada is False else vtxt}.{ptxt} "
                    f"Zona de compra tecnica {zona:.2f}. {opt_vehicle(sym)}",
                    voice=True, prio="SIGNAL",
                    voice_msg=f"{sym} bajó y se calmó. Buen momento para comprar.")
            alerted.add(sym); mark_alerted(sym)
        if TEST:
            print("[DIP_TEST] pasada unica completa — salgo.")
            return 0
        time.sleep(LOOP_S)
    say("🩸 DIP VIGIA", "16:00 — vigia de dips fuera hasta mañana", voice=False)
    return 0

if __name__ == "__main__":
    sys.exit(main())
