#!/usr/bin/env python3
"""x_signal_poster.py — daemon que postea en X las señales FUERTES de la flota.

SEÑAL-SOLAMENTE: jamas ejecuta ordenes; solo publica texto educativo.

Lee en vivo ~/ib-trader/data/trading-signals/YYYY-MM-DD.txt (lineas
"HH:MM:SS | TITULO | mensaje"). Una señal califica SOLO si:
  - contiene "prob" con numero >= 70, o
  - titulo BALLENA con ratio >= 3:1 (puts "N a 1" o calls "P C <=0.33"), o
  - contiene "retest-ok" / "reclaim" / "ruptura confirmada".

Limites: max 5 posts realtime/dia (dentro del cap compartido 10/dia del
ledger data/x_plan_budget.json), min 25 min entre posts, jamas repetir el
mismo ticker+nivel en el dia. Premarket 8:00-9:25 ET: max 1 post.
Estado diario: data/x_signal_state.json (se resetea solo al cambiar de dia).

COMBOS: data/x_combo_triggers.txt, lineas "QQQ>=705 & MSFT>=403 : mensaje".
Cada loop evalua las patas contra el ultimo close de data/bars_<sym>_ibkr.txt
(fallback yfinance si el archivo esta viejo >5min). Cuando TODAS las patas
son ciertas a la vez, postea "🎯 COMBO: ..." una vez al dia por linea.

Uso: x_signal_poster.py [--dry-run]   |  log: x_signal_poster.log
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_post_common as xc

ROOT = xc.ROOT
LOG_FILE = os.path.join(ROOT, "logs", "x_signal_poster.log")
STATE_FILE = os.path.join(ROOT, "data", "x_signal_state.json")
COMBO_FILE = os.path.join(ROOT, "data", "x_combo_triggers.txt")
SIGNAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")

ET = ZoneInfo("America/New_York")
LOOP_SEC = 60
MAX_REALTIME_PER_DAY = 5
MIN_GAP_SEC = 25 * 60
MAX_PREMARKET = 1
FRESH_SEC = 600            # ignorar lineas de hace >10 min (arranques tardios)
BARS_STALE_SEC = 300       # bars viejos >5 min -> fallback yfinance

log = xc.make_logger(LOG_FILE)

FLOAT = r"(\d+(?:\.\d+)?)"


# ---------------------------------------------------------------- estado
def load_state():
    today = time.strftime("%Y-%m-%d")
    st = {"date": today, "offset": 0, "posts": 0, "pm_posts": 0,
          "last_post_epoch": 0, "posted_keys": [], "combos": []}
    try:
        with open(STATE_FILE) as f:
            cur = json.load(f)
        if cur.get("date") == today:
            st.update(cur)
    except Exception:
        pass
    return st


def save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)


# ---------------------------------------------------------------- parsing
def known_syms():
    syms = set()
    try:
        for fn in os.listdir(os.path.join(ROOT, "data")):
            m = re.match(r"bars_([a-z0-9]+)_ibkr\.txt$", fn)
            if m:
                syms.add(m.group(1).upper())
    except Exception:
        pass
    return syms


def extract_sym(title, msg, syms):
    text = f"{title} {msg}"
    for tok in re.findall(r"[A-Z][A-Z0-9]{1,5}", text):
        if tok in syms:
            return tok
    m = re.match(r"[^A-Za-z]*([A-Z][A-Z0-9]{1,5})", title)
    return m.group(1) if m else None


def qualifies(title, msg):
    """(bool, prob, motivo)"""
    line = f"{title} {msg}"
    low = line.lower()
    m = re.search(r"prob[^0-9]{0,4}(\d{1,3})", low)
    if m and int(m.group(1)) >= 70:
        return True, int(m.group(1)), f"prob {m.group(1)}%"
    if "BALLENA" in title.upper():
        mp = re.search(FLOAT + r"\s+a\s+1", msg)
        if mp and float(mp.group(1)) >= 3.0:
            return True, 70, f"ballena {mp.group(1)}:1"
        mc = re.search(r"P\s*[/ ]?\s*C\s+" + FLOAT, msg)
        if mc and float(mc.group(1)) > 0 and 1.0 / float(mc.group(1)) >= 3.0:
            return True, 70, f"ballena calls 1:{mc.group(1)}"
        return False, 0, "ballena ratio <3:1"
    for kw in ("retest-ok", "reclaim", "ruptura confirmada"):
        if kw in low:
            return True, int(m.group(1)) if m else 70, kw
    return False, 0, ""


def extract_levels(msg, line_low):
    """entry, target, stop (target/stop None si no derivables)."""
    entry = None
    for pat in (r"@ " + FLOAT, r"toco " + FLOAT, r"px[= ]" + FLOAT,
                FLOAT):
        m = re.search(pat, msg)
        if m:
            entry = float(m.group(1))
            break
    if entry is None:
        return None, None, None
    tgt = None
    m = re.search(r"target\s+" + FLOAT, line_low)
    if m:
        tgt = float(m.group(1))
    stp = None
    m = re.search(r"(?:floor|stop)\s+" + FLOAT, line_low)
    if m:
        stp = float(m.group(1))
    short = any(k in line_low for k in ("sell", "puts", "caida", "down", "bajista"))
    if tgt is None:
        tgt = entry * (0.996 if short else 1.004)
    if stp is None:
        stp = entry * (1.004 if short else 0.996)
    return entry, tgt, stp


def fmt(x):
    return f"{x:.2f}" if x >= 10 else f"{x:.3f}"


def build_post(sym, title, msg, entry, tgt, stp, prob):
    que_paso = re.sub(r"\s+", " ", f"{title}: {msg}").strip()
    base = ("🎯 ${sym} live signal: {q}. ENTRY: {e} (printed level, 2 reads). "
            "TARGET: {t}. MENTAL STOP: {s} (if the path fails, out). "
            "Prob ~{p}%. Not financial advice.")
    fixed = base.format(sym=sym, q="", e=fmt(entry), t=fmt(tgt),
                        s=fmt(stp), p=prob)
    room = xc.MAX_CHARS - len(fixed)
    if len(que_paso) > room:
        que_paso = que_paso[:max(0, room - 1)].rstrip() + "…"
    return base.format(sym=sym, q=que_paso, e=fmt(entry), t=fmt(tgt),
                       s=fmt(stp), p=prob)


# ---------------------------------------------------------------- señales
def process_signals(st, now_et, dry_run, auth):
    path = os.path.join(SIGNAL_DIR, now_et.strftime("%Y-%m-%d") + ".txt")
    if not os.path.exists(path):
        return
    size = os.path.getsize(path)
    if size < st["offset"]:          # archivo recreado
        st["offset"] = 0
    if size == st["offset"]:
        return
    with open(path, errors="replace") as f:
        f.seek(st["offset"])
        chunk = f.read()
        st["offset"] = f.tell()
    save_state(st)
    syms = known_syms()
    premarket = now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 25)

    for raw in chunk.splitlines():
        parts = raw.split("|", 2)
        if len(parts) != 3:
            continue
        ts_s, title, msg = (p.strip() for p in parts)
        # frescura: no postear señales viejas tras un arranque tardio
        try:
            h, mi, s = (int(x) for x in ts_s.split(":"))
            age = (now_et.hour * 3600 + now_et.minute * 60 + now_et.second) \
                - (h * 3600 + mi * 60 + s)
            if age > FRESH_SEC:
                continue
        except Exception:
            continue

        ok, prob, why = qualifies(title, msg)
        if not ok:
            continue
        sym = extract_sym(title, msg, syms)
        if not sym:
            log(f"SKIP sin ticker: {title}")
            continue
        entry, tgt, stp = extract_levels(msg, f"{title} {msg}".lower())
        if entry is None:
            log(f"SKIP {sym} sin nivel numerico: {msg[:60]}")
            continue

        key = f"{sym}:{fmt(entry)}"
        if key in st["posted_keys"]:
            log(f"SKIP {key} duplicado hoy")
            continue
        if st["posts"] >= MAX_REALTIME_PER_DAY:
            log(f"SKIP {key} cap realtime {MAX_REALTIME_PER_DAY}/dia")
            continue
        if premarket and st["pm_posts"] >= MAX_PREMARKET:
            log(f"SKIP {key} cap premarket {MAX_PREMARKET}")
            continue
        gap = time.time() - st["last_post_epoch"]
        if gap < MIN_GAP_SEC:
            log(f"SKIP {key} espaciado {gap/60:.0f}<25 min")
            continue

        text = build_post(sym, title, msg, entry, tgt, stp, prob)
        # ADITIVO: linea del mapa gamma PROPIO antes de postear (degrade limpio si falta:
        # sin mapa no se menciona regimen). gexa jubilado el 2026-07-25.
        text = xc.append_gex(text, sym)
        if xc.post_text(text, f"señal {key} [{why}]", log, dry_run, auth):
            st["posts"] += 1
            if premarket:
                st["pm_posts"] += 1
            st["last_post_epoch"] = time.time()
            st["posted_keys"].append(key)
            save_state(st)


# ---------------------------------------------------------------- combos
COMBO_TEMPLATE = """# x_combo_triggers.txt — combos multi-ticker para posts X (señal-solamente)
# Formato: COND & COND [& COND...] : mensaje del post
# COND = SYM>=NUM | SYM<=NUM | SYM>NUM | SYM<NUM  (close 1m de data/bars_<sym>_ibkr.txt)
# El combo dispara cuando TODAS las patas son ciertas a la vez; 1 post/dia por linea.
#QQQ>=705 & MSFT>=403 : going long tech, target QQQ 708
"""


def latest_close(sym):
    """Ultimo close 1m; bars ibkr, fallback yfinance si stale >5min."""
    path = os.path.join(ROOT, "data", f"bars_{sym.lower()}_ibkr.txt")
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 400))
            last = f.read().decode(errors="replace").strip().splitlines()[-1]
        fields = last.split()
        epoch, close = int(fields[0]), float(fields[4])
        if time.time() - epoch <= BARS_STALE_SEC:
            return close
    except Exception:
        pass
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period="1d", interval="1m")
        if len(h):
            return float(h["Close"].iloc[-1])
    except Exception as e:
        log(f"COMBO {sym} sin precio (yf: {str(e)[:60]})")
    return None


def process_combos(st, dry_run, auth):
    if not os.path.exists(COMBO_FILE):
        return
    with open(COMBO_FILE) as f:
        lines = [l.strip() for l in f]
    for line in lines:
        if not line or line.startswith("#") or ":" not in line:
            continue
        cid = hashlib.md5(line.encode()).hexdigest()[:10]
        if cid in st["combos"]:
            continue
        conds_s, _, message = line.partition(":")
        legs, all_true, legs_txt = [], True, []
        for cond in conds_s.split("&"):
            m = re.match(r"\s*([A-Za-z0-9]+)\s*(>=|<=|>|<)\s*" + FLOAT,
                         cond)
            if not m:
                all_true = False
                break
            sym, op, lvl = m.group(1).upper(), m.group(2), float(m.group(3))
            legs.append((sym, op, lvl))
        if not legs or not all_true:
            continue
        for sym, op, lvl in legs:
            px = latest_close(sym)
            ok = px is not None and {
                ">=": px >= lvl, "<=": px <= lvl,
                ">": px > lvl, "<": px < lvl}[op]
            if not ok:
                all_true = False
                break
            legs_txt.append(f"{sym} {fmt(px)}")
        if not all_true:
            continue
        text = (f"🎯 COMBO: {message.strip()}. Simultaneously: "
                f"{', '.join(legs_txt)}. Not financial advice.")
        if xc.post_text(text, f"combo {cid}", log, dry_run, auth):
            st["combos"].append(cid)
            save_state(st)


# ---------------------------------------------------------------- main
def in_window(now_et):
    if now_et.weekday() >= 5:
        return False
    hm = now_et.hour * 60 + now_et.minute
    return 8 * 60 <= hm <= 16 * 60 + 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="un solo ciclo (test), ignora la ventana horaria")
    a = ap.parse_args()

    if not os.path.exists(COMBO_FILE):
        os.makedirs(os.path.dirname(COMBO_FILE), exist_ok=True)
        with open(COMBO_FILE, "w") as f:
            f.write(COMBO_TEMPLATE)
        log(f"creado template {COMBO_FILE}")

    env = xc.load_env()
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN",
                           "X_ACCESS_SECRET") if not env.get(k)]
    if missing and not a.dry_run:
        log(f"ERROR faltan credenciales en x.env: {','.join(missing)}")
        return 1
    auth = None if (a.dry_run or missing) else xc.make_auth(env)

    log(f"x_signal_poster arriba (dry_run={a.dry_run}) — señal-solamente, "
        f"caps: {MAX_REALTIME_PER_DAY} realtime/dia dentro de "
        f"{xc.MAX_POSTS_PER_DAY}/dia compartidos")
    while True:
        try:
            now_et = datetime.now(ET)
            if a.once or in_window(now_et):
                st = load_state()
                process_signals(st, now_et, a.dry_run, auth)
                process_combos(st, a.dry_run, auth)
            if a.once:
                return 0
        except Exception as e:
            log(f"LOOP-ERROR {type(e).__name__}: {str(e)[:120]} — sigo")
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    sys.exit(main())
