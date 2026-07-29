#!/usr/bin/env python3
"""x_postmortem.py — repaso HONESTO del dia en X (launchd 16:20 ET).

Lee ~/Desktop/planes-YYYY-MM-DD/ranking.json + x_drafts/<SYM>.txt (lo que se
planeo), baja el OHLC del dia via yfinance para los top-5 del ranking y
califica cada plan sin maquillaje: ¿imprimio la entrada (piso)? ¿target
(techo)? ¿stop? Postea 1-2 posts (ledger compartido data/x_plan_budget.json,
10/dia $4/mes): preferencia 1 ganador + 1 error; si todo fallo, se dice.
Ademas anexa el repaso completo (los 5) a docs/POSTMORTEM-X.md.

SEÑAL-SOLAMENTE. Uso: x_postmortem.py [--dry-run] [--date YYYY-MM-DD]
Log: x_postmortem.log
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_post_common as xc

ROOT = xc.ROOT
LOG_FILE = os.path.join(ROOT, "logs", "x_postmortem.log")
DOC_FILE = os.path.join(ROOT, "docs", "POSTMORTEM-X.md")
MAX_POSTS = 2
TOP_N = 5
STOP_PAD = 0.004  # piso roto >0.4% = stop

log = xc.make_logger(LOG_FILE)
FLOAT = r"(\d+(?:\.\d+)?)"


def parse_draft(path):
    """Extrae precio/techo/piso/iman del draft x_drafts/<SYM>.txt."""
    try:
        with open(path) as f:
            txt = f.read()
    except FileNotFoundError:
        return None
    out = {}
    for key, pat in (("precio", r"Precio\s+" + FLOAT),
                     ("techo", r"Techo\s+" + FLOAT),
                     ("piso", r"Piso\s+" + FLOAT),
                     ("iman", r"Iman\s+" + FLOAT)):
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            out[key] = float(m.group(1))
    return out if out.get("piso") and out.get("techo") else None


def day_ohlc(sym, date_s):
    """(open, high, low, close, pct_vs_prev) del dia via yfinance."""
    import yfinance as yf
    h = yf.Ticker(sym).history(period="5d", interval="1d")
    if h is None or not len(h):
        return None
    h = h[h.index.strftime("%Y-%m-%d") <= date_s]
    if not len(h) or h.index[-1].strftime("%Y-%m-%d") != date_s:
        return None
    row = h.iloc[-1]
    prev = float(h["Close"].iloc[-2]) if len(h) > 1 else float(row["Open"])
    pct = (float(row["Close"]) / prev - 1) * 100 if prev else 0.0
    return (float(row["Open"]), float(row["High"]), float(row["Low"]),
            float(row["Close"]), pct)


def grade(plan, ohlc):
    """Califica el plan largo-desde-piso contra el OHLC real del dia."""
    o, hi, lo, cl, pct = ohlc
    piso, techo = plan["piso"], plan["techo"]
    printed = lo <= piso <= hi
    target_hit = printed and hi >= techo > piso
    stop_hit = printed and lo <= piso * (1 - STOP_PAD)
    if target_hit and not stop_hit:
        verdict = "GANADOR"
    elif stop_hit:
        verdict = "STOP"
    elif printed:
        verdict = "NEUTRO"
    else:
        verdict = "SIN-ENTRADA"
    return {"printed": printed, "target_hit": target_hit,
            "stop_hit": stop_hit, "verdict": verdict,
            "o": o, "hi": hi, "lo": lo, "cl": cl, "pct": pct}


LESSON = {
    "GANADOR": ("the floor print paid; patience > FOMO",
                "same playbook, wait for the print"),
    "STOP": ("floor broken = out, no negotiating",
             "don't insist if the retest fails"),
    "NEUTRO": ("not every print pays the same day",
               "watch whether the level holds"),
    "SIN-ENTRADA": ("no print, no trade",
                    "re-arm levels and wait"),
}


def build_post(sym, plan, g):
    ok = g["verdict"] == "GANADOR"
    z = {"GANADOR": f"Win: floor printed and ceiling {plan['techo']} tagged",
         "STOP": f"Miss: floor {plan['piso']} broken (low {g['lo']:.2f})",
         "NEUTRO": "Neither target nor stop: sideways day after the print",
         "SIN-ENTRADA": f"floor {plan['piso']} never printed: zero trades"
         }[g["verdict"]]
    lesson, manana = LESSON[g["verdict"]]
    text = (f"📚 ${sym} daily review: plan was to enter at floor {plan['piso']}"
            f", target ceiling {plan['techo']}. "
            f"What happened: range {g['lo']:.2f}-{g['hi']:.2f}, close {g['cl']:.2f} "
            f"({g['pct']:+.1f}%). {z}. "
            f"Lesson: {lesson}. Tomorrow: {manana}. Not financial advice.")
    if len(text) > xc.MAX_CHARS:   # compactar sin cortar a mitad de frase
        text = (f"📚 ${sym} review: floor {plan['piso']} / ceiling {plan['techo']}"
                f". Range {g['lo']:.2f}-{g['hi']:.2f}, close {g['cl']:.2f}. "
                f"{z}. Lesson: {lesson}. Not financial advice.")
    return text[:xc.MAX_CHARS], ok


def append_doc(date_s, results, dry_run=False):
    doc_file = DOC_FILE + ".dry" if dry_run else DOC_FILE
    os.makedirs(os.path.dirname(doc_file), exist_ok=True)
    lines = [f"\n## {date_s} — repaso de planes (top {len(results)})\n"]
    for sym, plan, g in results:
        lines.append(
            f"- **${sym}** [{g['verdict']}] plan piso {plan['piso']} / "
            f"techo {plan['techo']} (precio plan {plan.get('precio', '?')}). "
            f"Real O {g['o']:.2f} H {g['hi']:.2f} L {g['lo']:.2f} "
            f"C {g['cl']:.2f} ({g['pct']:+.1f}%). "
            f"Print entrada: {'si' if g['printed'] else 'no'} | "
            f"target: {'si' if g['target_hit'] else 'no'} | "
            f"stop: {'si' if g['stop_hit'] else 'no'}.")
    header = "# POSTMORTEM-X — repasos diarios publicados/calificados\n"
    exists = os.path.exists(doc_file)
    with open(doc_file, "a") as f:
        if not exists:
            f.write(header)
        f.write("\n".join(lines) + "\n")
    return doc_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--dir", default=None,
                    help="ruta planes-... (default ~/Desktop/planes-<date>)")
    a = ap.parse_args()

    plan_dir = a.dir or os.path.expanduser(f"~/Desktop/planes-{a.date}")
    rank_path = os.path.join(plan_dir, "ranking.json")
    if not os.path.exists(rank_path):
        log(f"SKIP sin ranking.json en {plan_dir}")
        return 0
    with open(rank_path) as f:
        ranking = json.load(f)
    if not ranking:
        log("SKIP ranking vacio")
        return 0
    ranking.sort(key=lambda r: r.get("score", 0), reverse=True)

    env = xc.load_env()
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN",
                           "X_ACCESS_SECRET") if not env.get(k)]
    if missing and not a.dry_run:
        log(f"ERROR faltan credenciales en x.env: {','.join(missing)}")
        return 1
    auth = None if (a.dry_run or missing) else xc.make_auth(env)

    results = []
    for row in ranking[:TOP_N]:
        sym = row.get("sym", "?")
        plan = parse_draft(os.path.join(plan_dir, "x_drafts", f"{sym}.txt"))
        if not plan:
            log(f"SKIP {sym} sin draft/niveles")
            continue
        try:
            ohlc = day_ohlc(sym, a.date)
        except Exception as e:
            log(f"SKIP {sym} yfinance fallo: {str(e)[:80]}")
            continue
        if not ohlc:
            log(f"SKIP {sym} sin OHLC de hoy")
            continue
        g = grade(plan, ohlc)
        results.append((sym, plan, g))
        log(f"GRADE {sym} {g['verdict']} print={g['printed']} "
            f"tgt={g['target_hit']} stop={g['stop_hit']} pct={g['pct']:+.1f}%")

    if not results:
        log("DONE sin resultados que calificar")
        return 0

    doc_file = append_doc(a.date, results, a.dry_run)
    log(f"DOC anexado {doc_file} ({len(results)} planes)")

    # eleccion honesta: 1 ganador + 1 error; si no hay ganadores, los fallos
    winners = [r for r in results if r[2]["verdict"] == "GANADOR"]
    losers = [r for r in results if r[2]["verdict"] in ("STOP", "SIN-ENTRADA")]
    others = [r for r in results if r not in winners and r not in losers]
    if winners:
        picks = winners[:1] + (losers[:1] or others[:1])
    else:  # honestidad: si todo fallo, se cuentan los fallos
        picks = losers[:2] or others[:2]
    picks = picks[:MAX_POSTS]

    posted = 0
    for sym, plan, g in picks:
        text, _ = build_post(sym, plan, g)
        if xc.post_text(text, f"postmortem {sym} [{g['verdict']}]",
                        log, a.dry_run, auth):
            posted += 1
    b = xc.load_budget()
    log(f"DONE {posted} posts {'dry-run' if a.dry_run else 'reales'} | "
        f"mes {b['month']}: {b['posts']} posts ${b['spent']:.3f}"
        f"/{xc.MAX_SPEND_PER_MONTH:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
