#!/usr/bin/env python
"""fleet_healthcheck.py — verificador diario de que TODO este vivo: flota de bots,
posters X, alarmas, notificaciones, relay, launchd, frescura de datos, cobertura de
la flota (que nadie quede atras), y presupuesto X. Reporta por email + notificacion,
GRITA si algo critico esta caido, y se AUTO-CURA (revive relay/x_signal si mueren).

Uso: ./venv/bin/python scripts/fleet_healthcheck.py [--no-email] [--no-heal]
Programado por launchd com.ibtrader.healthcheck (diario). SEÑAL-SOLAMENTE."""
import argparse, base64, json, os, subprocess, time, warnings
warnings.filterwarnings("ignore")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

def env(k):
    for f in ("feeds.env",):
        try:
            for ln in open(f):
                if ln.startswith(k + "="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception: pass
    return None

def proc_alive(pat):
    return subprocess.run(["pgrep", "-f", pat], capture_output=True).returncode == 0

def count_proc(pat):
    r = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True)
    return len([x for x in r.stdout.split() if x])

def launchd_state():
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    out = {}
    for ln in r.stdout.splitlines():
        if "ibtrader" in ln:
            p = ln.split()
            if len(p) >= 3: out[p[2]] = p[1]  # label -> last exit
    return out

def fresh(path, max_age_s):
    try: return (time.time() - os.path.getmtime(path)) < max_age_s
    except Exception: return False

def market_hours():
    lt = time.localtime()
    return lt.tm_wday < 5 and 930 <= lt.tm_hour*100+lt.tm_min < 1600

def premarket_or_session():
    lt = time.localtime()
    return lt.tm_wday < 5 and 400 <= lt.tm_hour*100+lt.tm_min < 1600

def heal(name, keepalive):
    """Revive un daemon via su keepalive si esta muerto. Idempotente."""
    if not proc_alive(keepalive):
        try:
            subprocess.Popen(["nohup", "zsh", f"scripts/{keepalive}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"{name}: REVIVIDO"
        except Exception as e:
            return f"{name}: fallo revivir ({e})"
    return None

def canonical_fleet():
    try: return set(open("data/fleet.txt").read().split())
    except Exception: return set()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--no-heal", action="store_true")
    a = ap.parse_args()
    ok, warn, crit, healed = [], [], [], []
    now = time.strftime("%Y-%m-%d %H:%M ET")

    # 1) launchd jobs criticos
    ld = launchd_state()
    for job in ("com.ibtrader.dailyplans", "com.ibtrader.postmortem"):
        if job in ld:
            (ok if ld[job] in ("0", "-") else warn).append(f"launchd {job}: exit {ld[job]}")
        else:
            crit.append(f"launchd {job}: NO CARGADO")
    # jobs de flota con exit!=0 (aviso, no critico — pre-existente)
    for job, ex in ld.items():
        if job not in ("com.ibtrader.dailyplans", "com.ibtrader.postmortem") and ex not in ("0", "-"):
            warn.append(f"launchd {job}: exit {ex} (revisar config)")

    # 2) daemons criticos (con auto-cura)
    checks = [
        ("notify_relay (notificaciones)", "scripts/notify_relay.sh", "notify_relay.sh", True),
        ("x_signal_poster (X realtime)", "scripts/x_signal_poster.py", "x_signal_keepalive.sh", True),
    ]
    for name, pat, ka, critical in checks:
        if proc_alive(pat):
            ok.append(f"{name}: vivo")
        else:
            (crit if critical else warn).append(f"{name}: MUERTO")
            if not a.no_heal:
                h = heal(name, ka)
                if h: healed.append(h)

    # 3) feed de datos + bots (solo critico en horario de mercado/premarket)
    bridge = proc_alive("ibkr_bar_bridge.py")
    bots = count_proc("signal_bot")
    if premarket_or_session():
        if not bridge and not a.no_heal:
            try:
                subprocess.Popen(["nohup", "zsh", "scripts/fleet_keepalive_start.sh"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(4); bridge = proc_alive("ibkr_bar_bridge.py"); bots = count_proc("signal_bot")
                healed.append(f"flota: relanzada (bridge {'vivo' if bridge else 'aun no'}, {bots} bots)")
            except Exception as e:
                crit.append(f"flota: fallo relanzar ({e})")
        (ok if bridge else crit).append(f"bar_bridge (feed IBKR): {'vivo' if bridge else 'MUERTO en horario activo'}")
        (ok if bots >= 1 else warn).append(f"signal bots: {bots} vivos")
    else:
        ok.append(f"bar_bridge {'vivo' if bridge else 'dormido (fuera de horario, normal)'} | bots {bots}")
    ow = proc_alive("opt_whale_watch")
    (ok if (ow or not market_hours()) else warn).append(f"opt_whale (ballenas opciones): {'vivo' if ow else 'muerto'}")

    # 4) frescura de salidas del dia
    today = time.strftime("%Y-%m-%d")
    pdir = os.path.expanduser(f"~/Desktop/planes-{today}")
    npdf = len([f for f in os.listdir(pdir) if f.endswith(".pdf")]) if os.path.isdir(pdir) else 0
    lt = time.localtime()
    if lt.tm_hour >= 5:  # tras el run FULL de 4am
        (ok if npdf >= 20 else crit).append(f"planes de hoy: {npdf} PDFs {'(el run de 4am fallo?)' if npdf<20 else ''}")
    for jf, age, lbl in [("data/patterns.json", 36*3600, "patrones"),
                         ("data/breadth.json", 24*3600, "engranaje"),
                         ("data/calibration.json", 30*24*3600, "calibracion")]:
        (ok if os.path.exists(jf) else warn).append(f"{lbl}: {'ok' if os.path.exists(jf) else 'FALTA'}")

    # 5) gexa conecto?
    gx = os.path.exists("data/gexa_snapshot.json") and os.path.getsize("data/gexa_snapshot.json") > 5
    (ok if gx else warn).append(f"gexa snapshot: {'ok' if gx else 'no conecto (usa GEX estimado)'}")

    # 6) cobertura: cada modulo cubre la flota canonica?
    canon = canonical_fleet()
    if canon:
        gen = set()
        try:
            import re
            gen = set(re.findall(r'"([A-Z]+)":\s*dict', open("scripts/daily_fleet_plans.py").read()))
        except Exception: pass
        missing = canon - gen
        (ok if not missing else warn).append(f"cobertura generador: {len(gen)}/{len(canon)}" + (f" FALTAN {missing}" if missing else ""))
        # skills
        sk = set(x.replace("ticker-", "").upper() for x in os.listdir(os.path.expanduser("~/.claude/skills")) if x.startswith("ticker-"))
        smiss = canon - sk
        (ok if not smiss else warn).append(f"skills ticker: {len(sk & canon)}/{len(canon)}" + (f" FALTAN {smiss}" if smiss else ""))

    # 7) presupuesto X
    try:
        b = json.load(open("data/x_plan_budget.json"))
        ok.append(f"X ledger: {b.get('posts','?')} posts, ${b.get('spent',0):.2f} gastados este mes")
    except Exception:
        warn.append("X ledger: no leible")

    # 8) email/Resend configurado
    (ok if env("RESEND_KEY") and env("RESEND_TO") else crit).append(
        f"Resend email: {'configurado' if env('RESEND_KEY') else 'SIN KEY'}")

    # --- reporte ---
    status = "🔴 CRITICO" if crit else ("🟡 AVISOS" if warn else "🟢 TODO OK")
    lines = [f"HEALTHCHECK ib-trader {now} — {status}", "="*50]
    if healed: lines += ["AUTO-CURADO:"] + [f"  ✅ {h}" for h in healed]
    if crit: lines += ["CRITICO:"] + [f"  🔴 {c}" for c in crit]
    if warn: lines += ["AVISOS:"] + [f"  🟡 {w}" for w in warn]
    lines += ["OK:"] + [f"  🟢 {o}" for o in ok]
    report = "\n".join(lines)
    print(report)
    with open("healthcheck.log", "a") as f:
        f.write(f"\n{report}\n")

    # notificacion Mac (siempre) + email (si critico o avisos, o diario)
    subprocess.Popen(["osascript", "-e",
        f'display notification "{status}: {len(crit)} crit, {len(warn)} avisos, {len(healed)} curados" with title "🩺 ib-trader healthcheck"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not a.no_email and env("RESEND_KEY"):
        try:
            import requests
            subj = f"{status} Healthcheck ib-trader {today}"
            requests.post("https://api.resend.com/emails", timeout=20,
                headers={"Authorization": f"Bearer {env('RESEND_KEY')}", "Content-Type": "application/json"},
                json={"from": "onboarding@resend.dev", "to": [env("RESEND_TO")],
                      "subject": subj, "text": report})
        except Exception as e:
            print("email fallo:", e)
    return 2 if crit else (1 if warn else 0)

if __name__ == "__main__":
    import sys; sys.exit(main())
