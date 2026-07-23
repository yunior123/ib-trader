#!/usr/bin/env python3
"""dip_backtest.py — backtest HONESTO de la señal de dip de la flota
(2026-07-22, mision B5). Probabilidades MEDIDAS, sin maquillaje.

Aproximacion DIARIA documentada (el vigia vivo usa NBBO intradia + gate de
valuacion; aqui solo la geometria del dip con barras diarias yfinance 1 año):
  SEÑAL en el dia D si al cierre:
      (high5d - close) >= max(2.0 * ATR14, 1.5% * high5d)
  con high5d = maximo de los HIGH de las ultimas 5 sesiones (incluida D) y
  ATR14 = media simple del True Range de 14 sesiones. Solo el PRIMER dia de
  cada episodio (condicion False->True) cuenta — igual que la alerta viva,
  que canta max 1 vez por ticker por dia y el episodio suele durar dias.
  NO se aplica aqui el gate intradia (estabilizacion NBBO ni band-walk 5m):
  eso FILTRA señales en vivo, asi que las probs medidas son el PISO honesto.

Medimos por ticker, entrando al CIERRE del dia de señal:
  P(rebote >= +1.5% en 3 dias)  = frac. señales con max(high D+1..D+3) >= close*1.015
  P(sigue cayendo >= -2%)       = frac. señales con min(low  D+1..D+3) <= close*0.980
  medianas de mejor/peor excursion forward 3d.
Ticker con P(rebote) < 50% y n >= 10 -> "enabled": false (la alerta lo salta).

Salida: data/dip_probs.json + tabla por stdout (para el doc).
"""
import json, math, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "dip_probs.json")
ATR_MULT = 2.0
PCT_FLOOR = 0.015
REBOUND = 0.015
CONTINUE = -0.02
FWD_DAYS = 3
MIN_N_DISABLE = 10

def fleet():
    try:
        return [s.upper() for s in
                open(os.path.join(REPO, "data", "fleet.txt")).read().split()]
    except Exception:
        return ["QQQ", "SPY", "NVDA", "MU", "SMH", "DRAM"]

def median(v):
    s = sorted(v); n = len(s)
    if not n: return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

def backtest_one(highs, lows, closes):
    """-> lista de (fwd_max, fwd_min) por señal (episodio nuevo)."""
    n = len(closes)
    out = []
    prev_sig = False
    for i in range(18, n - FWD_DAYS):     # 14 TR + arranque limpio
        trs = []
        for j in range(i - 13, i + 1):
            trs.append(max(highs[j] - lows[j],
                           abs(highs[j] - closes[j - 1]),
                           abs(lows[j] - closes[j - 1])))
        atr14 = sum(trs) / 14
        high5 = max(highs[i - 4:i + 1])
        drop = high5 - closes[i]
        sig = drop >= max(ATR_MULT * atr14, PCT_FLOOR * high5)
        if sig and not prev_sig:
            fmax = max(highs[i + 1:i + 1 + FWD_DAYS]) / closes[i] - 1
            fmin = min(lows[i + 1:i + 1 + FWD_DAYS]) / closes[i] - 1
            out.append((fmax, fmin))
        prev_sig = sig
    return out

def main():
    import yfinance as yf
    syms = fleet()
    data = yf.download(" ".join(syms), period="1y", interval="1d",
                       group_by="ticker", auto_adjust=False,
                       progress=False, threads=True)
    probs, rows = {}, []
    for sym in syms:
        try:
            df = data[sym].dropna(subset=["High", "Low", "Close"])
            highs = df["High"].tolist()
            lows = df["Low"].tolist()
            closes = df["Close"].tolist()
        except Exception:
            highs = []
        if len(highs) < 40:
            probs[sym] = {"n": 0, "enabled": True, "note": "sin datos yfinance"}
            rows.append((sym, 0, None, None, None, None, True))
            continue
        sigs = backtest_one(highs, lows, closes)
        n = len(sigs)
        if n == 0:
            probs[sym] = {"n": 0, "enabled": True, "note": "0 señales en 1 año"}
            rows.append((sym, 0, None, None, None, None, True))
            continue
        p_reb = sum(1 for m, _ in sigs if m >= REBOUND) / n
        p_con = sum(1 for _, m in sigs if m <= CONTINUE) / n
        med_max = median([m for m, _ in sigs])
        med_min = median([m for _, m in sigs])
        enabled = not (n >= MIN_N_DISABLE and p_reb < 0.5)
        probs[sym] = {"n": n, "p_rebound_3d": round(p_reb, 3),
                      "p_continue_3d": round(p_con, 3),
                      "med_fwd_max": round(med_max, 4),
                      "med_fwd_min": round(med_min, 4),
                      "enabled": enabled}
        rows.append((sym, n, p_reb, p_con, med_max, med_min, enabled))
    meta = {"_meta": {"generated_epoch": int(time.time()),
                      "period": "1y daily yfinance",
                      "signal": f"drop>=max({ATR_MULT}xATR14, {PCT_FLOOR*100:.1f}% del high5d), episodio nuevo, entrada al cierre",
                      "rebound_def": f">=+{REBOUND*100:.1f}% en {FWD_DAYS}d (high)",
                      "continue_def": f"<={CONTINUE*100:.1f}% en {FWD_DAYS}d (low)",
                      "disable_rule": f"p_rebound<50% con n>={MIN_N_DISABLE}"}}
    meta.update(probs)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    os.replace(tmp, OUT)
    print(f"{'TICKER':7s} {'n':>3s} {'P(reb+1.5%/3d)':>15s} {'P(cae-2%/3d)':>13s} "
          f"{'medMax':>7s} {'medMin':>7s}  estado")
    for sym, n, pr, pc, mm, mn, en in rows:
        if pr is None:
            print(f"{sym:7s} {n:3d} {'-':>15s} {'-':>13s} {'-':>7s} {'-':>7s}  sin señales/datos")
        else:
            print(f"{sym:7s} {n:3d} {pr*100:14.0f}% {pc*100:12.0f}% "
                  f"{mm*100:6.1f}% {mn*100:6.1f}%  {'OK' if en else 'DISABLED (p<50, n>=10)'}")
    print(f"\n-> {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
