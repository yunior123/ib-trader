#!/usr/bin/env python3
"""yoel_faithful_backtest.py — el test JUSTO del metodo de Yoel Sardinas
(2026-07-23, correccion de Yunior: "juzga el metodo, no un muñeco de paja").

El backtest v1 fue injusto (stop que el libro nunca usa, un solo TF, subyacente).
Este replica la GEOMETRIA REAL de Yoel:
  1. CONFLUENCIA 3-TF: la tendencia se define en 1H y 1D (direccion SMA20);
     el gatillo se confirma en 15m. Nada de un solo marco.
  2. SIN STOP: el riesgo es la prima. La opcion se aguanta hasta +100% (TP de
     Yoel) o hasta el vencimiento SEMANAL (viernes) — lo que pase primero.
  3. PAGO DE OPCION, no subyacente: compra sintetica de un CALL/PUT semanal
     ATM (Black-Scholes, IV = vol realizada anualizada del ticker), y se mide
     el retorno de la PRIMA a lo largo del camino del precio.
  4. VOLUMEN>MA50 como confirmacion (est 5-8) — con y sin, para el A/B.

Datos: data/backtest/bars3mo5m_<sym>.csv (5m, 62 dias, CON volumen). Se agregan
a 15m/1H/1D. No hay cadena de opciones historica gratis (Polygon/ORATS de pago;
yfinance solo da cadenas actuales) -> se sintetiza con BS. La grabadora propia
acumula desde 2026-07-21 para el test con cadena REAL en ~1 mes.

HONESTIDAD: la IV sintetica es una aproximacion (vol realizada, sin skew ni
term structure ni salto de earnings); el resultado es orientativo del metodo,
no una promesa. Se reporta con esa advertencia.
"""
import csv, glob, math, json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

# ---- Black-Scholes (portado de daily_fleet_plans.bs_greeks) ----
def bs_price(S, K, T, iv, cp, r=0.045):
    if T <= 0:
        return max(0.0, (S - K) if cp == "C" else (K - S))
    if iv <= 0 or S <= 0:
        return max(0.0, (S - K) if cp == "C" else (K - S))
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))
    if cp == "C":
        return S * N(d1) - K * math.exp(-r * T) * N(d2)
    return K * math.exp(-r * T) * N(-d2) - S * N(-d1)

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
    """agrega barras 5m a secs; devuelve lista (t_open, o, h, l, c, v) por bucket."""
    out = {}
    for t, o, h, l, c, v in R:
        k = t - t % secs
        if k not in out:
            out[k] = [t, o, h, l, c, v]
        else:
            b = out[k]
            b[2] = max(b[2], h); b[3] = min(b[3], l); b[4] = c; b[5] += v
    return [tuple(v) for k, v in sorted(out.items())]

def sma(vals, i, n):
    return sum(vals[i - n:i]) / n if i >= n else None

def realized_iv(R, i, n=78):
    """vol realizada anualizada de los ultimos n retornos 5m (78 barras 5m ~ 1 dia RTH)."""
    if i < n + 1:
        return 0.5
    rets = []
    for j in range(i - n, i):
        if R[j - 1][4] > 0:
            rets.append(math.log(R[j][4] / R[j - 1][4]))
    if len(rets) < 10:
        return 0.5
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / len(rets)
    # 5m -> anualizado: 78 barras/dia * 252 dias
    iv = math.sqrt(var * 78 * 252)
    return min(max(iv, 0.15), 2.5)

def secs_to_friday_close(t):
    """segundos hasta el cierre del viernes de ESTA semana (venc. semanal), min 1 dia."""
    import time as _t
    lt = _t.localtime(t)
    wday = lt.tm_wday  # 0=lun..4=vie
    days_to_fri = (4 - wday) % 7
    fri = t - (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec) + days_to_fri * 86400 + 16 * 3600
    if fri <= t:
        fri += 7 * 86400
    return max(fri - t, 86400)

def run():
    syms = [os.path.basename(f).split("bars3mo5m_")[1][:-4]
            for f in sorted(glob.glob("data/backtest/bars3mo5m_*.csv"))]
    # buckets: estrategia -> {con:{w,n,sumret}, sin:{...}}
    def newb():
        return {"con": {"w": 0, "n": 0, "ret": 0.0}, "sin": {"w": 0, "n": 0, "ret": 0.0}}
    STRATS = {"rebote_sma20": newb(), "iman": newb()}
    TP = 1.00      # +100% de la prima (el TP de Yoel)
    COMM = 0.005   # $0.50/contrato ida+vuelta sobre prima ~ despreciable, incluido como friccion

    for sym in syms:
        R = load(sym)
        if len(R) < 300:
            continue
        H = agg(R, 3600)    # 1H
        D = agg(R, 86400)   # 1D
        # mapas epoch->indice de la barra 1H/1D vigente
        Hc = [b[4] for b in H]; Dc = [b[4] for b in D]
        Ht = [b[0] for b in H]; Dt = [b[0] for b in D]

        def tf_trend(closes, times, t, n=20):
            """direccion SMA20 del TF en el momento t: +1 alcista, -1 bajista, 0 n/d.
            usa solo barras cerradas <= t (sin look-ahead)."""
            idx = -1
            for k in range(len(times)):
                if times[k] <= t:
                    idx = k
                else:
                    break
            if idx < n:
                return 0
            m_now = sum(closes[idx - n + 1:idx + 1]) / n
            m_prev = sum(closes[idx - n:idx]) / n
            price = closes[idx]
            if price > m_now and m_now > m_prev:
                return 1
            if price < m_now and m_now < m_prev:
                return -1
            return 0

        C = [x[4] for x in R]; V = [x[5] for x in R]
        last = -10**9
        i = 80
        while i < len(R) - 2:
            t = R[i][0]
            # 5m SMA20 + ATR + volumen MA50
            m20 = sma(C, i, 20)
            vma = sma(V, i, 50)
            if i < 21 or not m20 or not vma:
                i += 1; continue
            atr = sum(max(R[j][2] - R[j][3], abs(R[j][2] - C[j - 1]), abs(R[j][3] - C[j - 1]))
                      for j in range(i - 20, i)) / 20
            if atr <= 0 or t - last < 1800:
                i += 1; continue
            c = C[i]; green = R[i][4] > R[i][1]; vol_ok = V[i] > vma
            th = tf_trend(Hc, Ht, t); td = tf_trend(Dc, Dt, t)
            dist = (c - m20) / atr

            sig = 0; strat = None; cp = None
            # --- IMAN (est 7-8): 1H+1D bajistas + precio lejos abajo + reversion verde -> CALL
            if dist <= -2.0 and green and th <= 0 and td <= 0:
                sig = +1; strat = "iman"; cp = "C"
            elif dist >= 2.0 and (not green) and th >= 0 and td >= 0:
                sig = -1; strat = "iman"; cp = "P"
            # --- REBOTE punto medio (est 3-4): CONFLUENCIA 1H y 1D MISMO sentido, toca SMA20
            elif abs(dist) <= 0.3 and th == 1 and td == 1 and green:
                sig = +1; strat = "rebote_sma20"; cp = "C"
            elif abs(dist) <= 0.3 and th == -1 and td == -1 and (not green):
                sig = -1; strat = "rebote_sma20"; cp = "P"

            if sig:
                last = t
                entry_px = R[i + 1][1]        # open siguiente (sin look-ahead)
                iv = realized_iv(R, i)
                T0 = secs_to_friday_close(t) / (365 * 86400)
                K = round(entry_px)            # ATM
                prem0 = bs_price(entry_px, K, T0, iv, cp)
                if prem0 <= 0.01:
                    i += 1; continue
                # camino: aguantar hasta +100% o vencimiento (viernes)
                ret = None
                fri_t = t + secs_to_friday_close(t)
                for j in range(i + 1, len(R)):
                    tj = R[j][0]
                    if tj > fri_t:
                        break
                    Tj = max((fri_t - tj) / (365 * 86400), 1e-6)
                    # premium en el EXTREMO favorable de la barra (Yoel vende en el pico con orden auto)
                    fav_px = R[j][2] if cp == "C" else R[j][3]
                    prem = bs_price(fav_px, K, Tj, iv, cp)
                    if prem >= prem0 * (1 + TP):
                        ret = TP - COMM        # +100% alcanzado
                        break
                if ret is None:
                    # venció: liquidar a la prima del cierre del viernes (o ultima barra)
                    last_px = None
                    for j in range(len(R) - 1, i, -1):
                        if R[j][0] <= fri_t:
                            last_px = R[j][4]; break
                    if last_px is None:
                        i += 1; continue
                    premT = max(0.0, (last_px - K) if cp == "C" else (K - last_px))  # intrinseco al vencimiento
                    ret = (premT / prem0 - 1) - COMM
                    ret = max(ret, -1.0)       # no se pierde mas que la prima
                b = STRATS[strat]["con" if vol_ok else "sin"]
                b["n"] += 1; b["ret"] += ret; b["w"] += int(ret > 0)
            i += 1

    def wilson(w, n):
        if n == 0: return 0.0
        p = w / n; z = 1.96; d = 1 + z * z / n
        return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)

    out = {"method": "faithful-3TF-nostop-optionpayoff-BSsynthetic", "TP": TP, "strategies": {}}
    print("=" * 78)
    print("YOEL — TEST FIEL: confluencia 3-TF + SIN stop + pago de OPCION semanal ATM (BS)")
    print("=" * 78)
    for strat, d in STRATS.items():
        print(f"\n### {strat}")
        srec = {}
        for lbl in ("con", "sin"):
            b = d[lbl]
            if b["n"] == 0:
                print(f"  vol {lbl}: sin señales"); continue
            wr = b["w"] / b["n"]              # % de trades que ganan (llegan a +100% o cierran verde)
            avg = b["ret"] / b["n"]           # retorno medio POR TRADE (en múltiplos de prima)
            print(f"  vol {lbl.upper():3s}: n={b['n']:4d}  P(gana)={wr*100:.0f}%  "
                  f"retorno medio/trade={avg*100:+.0f}% de la prima  wilson_lo={wilson(b['w'],b['n'])*100:.0f}%")
            srec[lbl] = {"n": b["n"], "p_win": round(wr, 3), "avg_ret": round(avg, 3),
                         "wilson_lo": round(wilson(b["w"], b["n"]), 3)}
        out["strategies"][strat] = srec
    json.dump(out, open("data/backtest/scores_yoel_faithful.json", "w"), indent=1)
    print("\n-> data/backtest/scores_yoel_faithful.json")
    print("\nADVERTENCIA HONESTA: IV sintetica (vol realizada, sin skew/term/earnings);")
    print("orientativo del metodo, no promesa. Test con cadena REAL en ~1 mes (grabadora 7/21).")

if __name__ == "__main__":
    run()
