#!/usr/bin/env python3
"""v6_backtest.py — M3: calibracion de prob por clase del motor v6 (V6_SPEC §4).

SEÑAL-SOLAMENTE: este script SOLO lee data/bt_*.txt existentes y corre los
bots C++ en replay --stdin dentro de un tmpdir aislado. Cero red, cero
Alpaca/Yahoo, cero ordenes.

Metodo (fijado ex-ante, CALIB-2):
  1. Recorte: ultimas 30 sesiones (fechas locales ET, reloj del Mac = ET,
     identico a et_hm() del bot) de data/bt_<sym>.txt.
  2. Split temporal 60/40 por sesiones: primeras 60% = TRAIN, ultimas 40% = OOS.
  3. Pass A (sin tabla, <PREFIX>_V6_PROB_MIN=0 para observar TODAS las clases,
     incluidas las de prior<55 como ORB): parsear lineas `*** SYM V6 BUY|SELL ***`.
     El resto del env = keepalive de produccion (load_keepalive_env).
  4. Outcome triple-barrier identico para todas las clases y train/OOS:
     entry = open del bar siguiente; WIN si toca entry+0.75*ATR14_1m antes de
     entry-0.75*ATR14_1m (BUY; SELL espejo); ambiguo (toca ambas en el mismo
     bar 1m) = LOSS pesimista; a 60 min sin toque: WIN si close>entry (BUY).
     ATR14_1m Wilder recalculado por el harness con la misma formula V6ATR.
  5. Tabla TRAIN-only -> pass B con la tabla congelada en tmpdir/data/ (el set
     de señales es identico con PROB_MIN=0; pass B da las prob impresas OOS).
  6. Veredictos por clase-ticker:
       CALIBRADA : n_train>=20 y WR_train>=55 y n_oos>=5 y WR_oos>=0.5*WR_train
                   y WR_oos>=55
       DEGRADADA : n_oos>=5 y WR_oos<55 — LA HONESTIDAD MANDA (orden Yunior
                   2026-07-16): la fila de la tabla lleva stats train+OOS
                   COMBINADAS (crudas) para que el shrinkage del bot muestre la
                   prob real baja. NO se usa #FAIL_OOS->prior (eso ocultaria la
                   degradacion detras de un prior optimista 55-62).
       SIN_OOS   : n_oos<5 — sin validacion; fila train-only (shrinkage manda).
       PRIOR     : n_train<20 o WR_train<55 — fila presente pero el shrinkage
                   k=20 la mantiene cerca del prior.
  7. Salidas: data/prob_table_<sym>.txt (leidas en runtime por los bots, sin
     recompilar), data/v6_wfo_report.txt, docs/V6_BACKTEST.md.

Grid WFO de 3 params (§4.3, 27 combos) NO se corre por defecto (8GB, en serie
ya son 32 replays): queda `--grid` como fase 2 manual.

Uso:  python3 scripts/v6_backtest.py all
      python3 scripts/v6_backtest.py NVDA
SECUENCIAL: un replay a la vez, jamas paralelo (8GB).
"""

import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 16 US con historia bt_<sym>.txt (~90d Alpaca IEX, fetch 2026-07-11 pre-veda).
# skhy: solo ~2 sesiones de bars_skhy_ibkr.txt -> queda en priors (estado valido).
# kospi/samsung/skhynix: 1 sesion KRX -> priors.
SYMS = ["aapl", "amd", "asml", "cper", "dram", "gld", "intc", "nok",
        "nvda", "qqq", "slv", "spcx", "tsla", "tsm", "txn", "uso"]

N_SESSIONS = 30          # ventana de calibracion
TRAIN_FRAC = 0.60        # split 60/40 por sesiones
ATR_MULT = 0.75          # barreras +-0.75*ATR14_1m
HORIZON_S = 3600         # 60 min
K_SHRINK = 20.0          # shrinkage bayesiano del bot (V6Prob::prob)

PRIORS = {"TREND_PULLBACK_LONG": 62, "TREND_PULLBACK_SHORT": 62,
          "VWAP_RECLAIM_LONG": 60, "VWAP_LOSS_SHORT": 60,
          "SQUEEZE_BREAK_LONG": 56, "SQUEEZE_BREAK_SHORT": 56,
          "ORB_LONG": 53, "ORB_SHORT": 53,
          "MTF_BB_REV_LONG": 55, "MTF_BB_REV_SHORT": 55,
          "TLINE_BREAK_LONG": 55, "TLINE_BREAK_SHORT": 55,
          "TREND_REVERSAL_LONG": 55, "TREND_REVERSAL_SHORT": 55}

SIG_RE = re.compile(r"\*\*\* (\w+) V6 (BUY|SELL) \*\*\* prob (\d+)% clase (\w+) "
                    r"score ([\d.]+) (\S+) t=(\d+)")


def load_keepalive_env(sym):
    """export FOO=bar de scripts/<sym>_keepalive.sh (mismo parser que fleet_backtest_audit)."""
    path = os.path.join(ROOT, "scripts", f"{sym}_keepalive.sh")
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith("export ") or "=" not in line[7:]:
                continue
            k, v = line[7:].split("=", 1)
            v = v.strip().strip("'").strip('"')
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            env[k.strip()] = v
    return env


def env_prefix(sym):
    src = os.path.join(ROOT, f"{sym}_signal_bot.cpp")
    with open(src, errors="ignore") as f:
        m = re.search(r'envd\("([A-Z0-9]+)_V6",', f.read())
    return m.group(1) if m else sym.upper()


def load_bars(sym):
    """[(epoch,o,h,l,c,v), ...] recortado a las ultimas N_SESSIONS fechas locales."""
    path = os.path.join(ROOT, "data", f"bt_{sym}.txt")
    if not os.path.exists(path):
        return [], []
    bars = []
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 6:
                bars.append((int(float(p[0])), float(p[1]), float(p[2]),
                             float(p[3]), float(p[4]), float(p[5])))
    days = sorted({time.strftime("%Y-%m-%d", time.localtime(b[0])) for b in bars})
    keep = set(days[-N_SESSIONS:])
    bars = [b for b in bars if time.strftime("%Y-%m-%d", time.localtime(b[0])) in keep]
    return bars, sorted(keep)


def wilder_atr14(bars):
    """ATR14 identico a V6ATR (add por bar); atr[i] = valor tras procesar bar i."""
    out, atr, prev_c, n = [], 0.0, 0.0, 0
    for (_, o, h, l, c, _) in bars:
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c)) if n else h - l
        atr = (atr * n + tr) / (n + 1) if n < 14 else (atr * 13 + tr) / 14
        prev_c = c
        n += 1
        out.append(atr)
    return out


def replay(sym, bars_text, env_extra, table_text=None):
    """Corre <sym>_signal_bot --stdin en tmpdir aislado. Devuelve stdout."""
    env = dict(os.environ)
    env.update(load_keepalive_env(sym))
    env.update(env_extra)
    with tempfile.TemporaryDirectory(prefix=f"v6bt_{sym}_") as tmp:
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        if table_text is not None:
            with open(os.path.join(tmp, "data", f"prob_table_{sym}.txt"), "w") as f:
                f.write(table_text)
        r = subprocess.run([os.path.join(ROOT, f"{sym}_signal_bot"), "--stdin"],
                           input=bars_text, capture_output=True, text=True,
                           env=env, cwd=tmp, timeout=600)
    return r.stdout


def eval_outcome(bars, atrs, idx, side):
    """Triple-barrier §4.1. -> (win:bool, ret:float) o None si irresoluble."""
    if idx + 1 >= len(bars):
        return None
    atr = atrs[idx]
    if atr <= 0:
        return None
    entry = bars[idx + 1][1]                       # open del bar siguiente
    if entry <= 0:
        return None
    up, dn = entry + ATR_MULT * atr, entry - ATR_MULT * atr
    t_end = bars[idx + 1][0] + HORIZON_S
    last_close = None
    for b in bars[idx + 1:]:
        if b[0] > t_end:
            break
        last_close = b[4]
        hi_hit, lo_hit = b[2] >= up, b[3] <= dn
        if hi_hit and lo_hit:                      # ambiguo = LOSS pesimista
            return (False, -ATR_MULT * atr / entry)
        if side == "BUY":
            if hi_hit:
                return (True, ATR_MULT * atr / entry)
            if lo_hit:
                return (False, -ATR_MULT * atr / entry)
        else:
            if lo_hit:
                return (True, ATR_MULT * atr / entry)
            if hi_hit:
                return (False, -ATR_MULT * atr / entry)
    if last_close is None:
        return None
    ret = (last_close - entry) / entry if side == "BUY" else (entry - last_close) / entry
    return (ret > 0, ret)


def shrink(n, w, prior):
    return 100.0 * ((w + prior / 100.0 * K_SHRINK) / (n + K_SHRINK))


def run_sym(sym):
    bars, days = load_bars(sym)
    if len(days) < 10:
        return {"sym": sym, "ok": False, "why": f"solo {len(days)} sesiones"}
    n_train_days = max(1, int(round(TRAIN_FRAC * len(days))))
    train_days = set(days[:n_train_days])
    bars_text = "".join(f"{b[0]} {b[1]} {b[2]} {b[3]} {b[4]} {b[5]:.0f}\n" for b in bars)
    atrs = wilder_atr14(bars)
    idx_of = {b[0]: i for i, b in enumerate(bars)}
    pfx = env_prefix(sym)
    env0 = {f"{pfx}_V6_PROB_MIN": "0"}             # capturar TODAS las clases (ORB prior 53<55)

    def parse(stdout):
        sigs = []
        for m in SIG_RE.finditer(stdout):
            t = int(m.group(7))
            if t not in idx_of:
                continue
            sigs.append({"side": m.group(2), "prob": int(m.group(3)),
                         "cls": m.group(4), "score": float(m.group(5)),
                         "t": t, "idx": idx_of[t],
                         "day": time.strftime("%Y-%m-%d", time.localtime(t))})
        return sigs

    # Pass A: sin tabla (priors), señales + outcomes
    sigs = parse(replay(sym, bars_text, env0))
    for s in sigs:
        s["out"] = eval_outcome(bars, atrs, s["idx"], s["side"])

    res = [s for s in sigs if s["out"] is not None]
    train = [s for s in res if s["day"] in train_days]

    def agg(rows):
        d = defaultdict(lambda: {"n": 0, "w": 0, "rets_w": [], "rets_l": []})
        for s in rows:
            e = d[s["cls"]]
            e["n"] += 1
            win, ret = s["out"]
            if win:
                e["w"] += 1
                e["rets_w"].append(ret)
            else:
                e["rets_l"].append(ret)
        return d

    tr = agg(train)

    # tabla congelada TRAIN-only -> pass B (OOS evaluado CON la tabla presente,
    # spec §4.3: la prob impresa cambia y con ella los tie-breaks BUY/SELL y la
    # cadena de cooldowns — el set OOS legitimo es el de pass B)
    hdr = (f"# v6 prob table {sym} | generado {datetime.now():%Y-%m-%d} por v6_backtest.py"
           f" | train {days[0]}..{days[n_train_days-1]} (60% de {len(days)} sesiones)\n")
    train_tbl = hdr + "".join(
        f"{c} {v['n']} {v['w']} {100.0*v['w']/v['n']:.1f}\n" for c, v in sorted(tr.items()))
    sigs_b = parse(replay(sym, bars_text, env0, table_text=train_tbl))
    for s in sigs_b:
        s["out"] = eval_outcome(bars, atrs, s["idx"], s["side"])
    oos = [s for s in sigs_b if s["out"] is not None and s["day"] not in train_days]
    same_set = [(s["t"], s["cls"], s["side"]) for s in sigs] == \
               [(s["t"], s["cls"], s["side"]) for s in sigs_b]
    oo = agg(oos)

    # veredictos + tabla final
    classes = sorted(set(tr) | set(oo))
    rows, final_lines = [], [hdr]
    for c in classes:
        t, o = tr.get(c), oo.get(c)
        nt, wt = (t["n"], t["w"]) if t else (0, 0)
        no, wo = (o["n"], o["w"]) if o else (0, 0)
        wrt = 100.0 * wt / nt if nt else 0.0
        wro = 100.0 * wo / no if no else 0.0
        if no >= 5 and wro < 55.0:
            verdict = "DEGRADADA"
            # honestidad: fila con datos train+OOS combinados (prob real baja)
            n_all, w_all = nt + no, wt + wo
            final_lines.append(f"{c} {n_all} {w_all} {100.0*w_all/n_all:.1f} "
                               f"# DEGRADADA wr_oos={wro:.0f}% n_oos={no}\n")
        else:
            if nt >= 20 and wrt >= 55.0 and no >= 5 and wro >= 0.5 * wrt and wro >= 55.0:
                verdict = "CALIBRADA"
            elif nt >= 20 and wrt >= 55.0 and no < 5:
                verdict = "SIN_OOS"
            else:
                verdict = "PRIOR"
            if nt > 0:
                final_lines.append(f"{c} {nt} {wt} {wrt:.1f}\n")
        aw = (t["rets_w"] if t else []) + (o["rets_w"] if o else [])
        al = (t["rets_l"] if t else []) + (o["rets_l"] if o else [])
        rows.append({"cls": c, "n_train": nt, "w_train": wt, "wr_train": wrt,
                     "n_oos": no, "w_oos": wo, "wr_oos": wro, "verdict": verdict,
                     "avg_win": 100.0 * sum(aw) / len(aw) if aw else 0.0,
                     "avg_loss": 100.0 * sum(al) / len(al) if al else 0.0,
                     "prob_shown": shrink(nt + no if verdict == "DEGRADADA" else nt,
                                          wt + wo if verdict == "DEGRADADA" else wt,
                                          PRIORS.get(c, 55))})

    with open(os.path.join(ROOT, "data", f"prob_table_{sym}.txt"), "w") as f:
        f.writelines(final_lines)

    used = train + oos                      # train de pass A + OOS de pass B
    n_all = len(used)
    w_all = sum(1 for s in used if s["out"][0])
    return {"sym": sym, "ok": True, "days": len(days), "train_days": n_train_days,
            "day0": days[0], "day_last": days[-1], "bars": len(bars),
            "n_signals_raw": len(sigs), "n": n_all, "w": w_all,
            "wr": 100.0 * w_all / n_all if n_all else 0.0,
            "n_train": len(train), "n_oos": len(oos),
            "w_oos": sum(1 for s in oos if s["out"][0]),
            "same_set": same_set, "rows": rows}


def write_reports(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # ---- data/v6_wfo_report.txt ----
    L = [f"# v6_wfo_report | {now} | v6_backtest.py (ventana {N_SESSIONS} sesiones, "
         f"split 60/40, triple-barrier 0.75xATR14_1m/60min, PROB_MIN=0 en replay "
         f"para observar todas las clases)",
         "# grid WFO 27-combos (V6_MIN/V6_RVOL/V6_RETR_CONT) NO corrido — fase 2 "
         "manual (`--grid`); este reporte = calibracion con defaults.", ""]
    fleet = defaultdict(lambda: {"nt": 0, "wt": 0, "no": 0, "wo": 0})
    for r in results:
        if not r["ok"]:
            L.append(f"{r['sym'].upper()}: SIN CALIBRACION ({r['why']}) -> priors")
            continue
        L.append(f"{r['sym'].upper()}: {r['days']} sesiones {r['day0']}..{r['day_last']} | "
                 f"{r['n']} trades WR {r['wr']:.0f}% (train {r['n_train']} / oos {r['n_oos']})"
                 + ("" if r["same_set"] else " | WARN set señales difiere entre pasadas"))
        for w in r["rows"]:
            L.append(f"  {w['cls']:<24} train {w['n_train']:>3}n {w['wr_train']:5.1f}% | "
                     f"oos {w['n_oos']:>3}n {w['wr_oos']:5.1f}% | "
                     f"avgW {w['avg_win']:+.2f}% avgL {w['avg_loss']:+.2f}% | "
                     f"prob_bot {w['prob_shown']:.0f}% | {w['verdict']}")
            f = fleet[w["cls"]]
            f["nt"] += w["n_train"]; f["wt"] += w["w_train"]
            f["no"] += w["n_oos"]; f["wo"] += w["w_oos"]
    L.append("")
    L.append("# RESUMEN FLOTA por clase (agregado 16 US)")
    for c, f in sorted(fleet.items()):
        wrt = 100.0 * f["wt"] / f["nt"] if f["nt"] else 0.0
        wro = 100.0 * f["wo"] / f["no"] if f["no"] else 0.0
        L.append(f"  {c:<24} train {f['nt']:>4}n {wrt:5.1f}% | oos {f['no']:>4}n {wro:5.1f}%")
    with open(os.path.join(ROOT, "data", "v6_wfo_report.txt"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    return fleet


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    syms = SYMS if (not args or args[0].lower() == "all") else [args[0].lower()]
    results = []
    for s in syms:                                  # SECUENCIAL — 8GB
        t0 = time.time()
        r = run_sym(s)
        results.append(r)
        if r["ok"]:
            print(f"{s.upper():6} {r['n']:4d} trades WR {r['wr']:5.1f}% "
                  f"(oos {r['n_oos']}) tabla -> data/prob_table_{s}.txt "
                  f"[{time.time()-t0:.1f}s]", flush=True)
        else:
            print(f"{s.upper():6} SKIP: {r['why']}", flush=True)
    if len(syms) > 1:
        write_reports(results)
        print("reporte -> data/v6_wfo_report.txt")
    return results


if __name__ == "__main__":
    main()
