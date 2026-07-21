#!/usr/bin/env python3
"""x_post_common.py — post/ledger compartido para TODOS los posters de X.

Mismo patron que x_plan_poster.py (OAuth1 + x.env + data/x_plan_budget.json).
UN solo ledger para toda la flota: $0.015/post, HARD caps 10 posts/dia y
$4.00/mes. El conteo diario se hace escaneando los logs de todos los
componentes (" POSTED " lineas de hoy), asi ningun poster puede saltarse
el cap de otro. SEÑAL-SOLAMENTE: esto solo publica texto, jamas ordena.
"""
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDGET_FILE = os.path.join(ROOT, "data", "x_plan_budget.json")
ENV_FILE = os.path.join(ROOT, "x.env")

COST_PER_POST = 0.015
MAX_POSTS_PER_DAY = 10       # cap compartido entre TODOS los posters
MAX_SPEND_PER_MONTH = 4.00
MAX_CHARS = 275
API_URL = "https://api.x.com/2/tweets"

# logs de todos los componentes que postean (mismo formato de linea que
# x_plan_poster.py: "YYYY-MM-DD HH:MM:SS ... POSTED ...")
POSTER_LOGS = [
    os.path.join(ROOT, "x_plan_poster.log"),
    os.path.join(ROOT, "x_signal_poster.log"),
    os.path.join(ROOT, "x_postmortem.log"),
]


def make_logger(log_file):
    # stdout SOLO si es TTY: los keepalives/launchd redirigen stdout al mismo
    # log y duplicarian lineas (" POSTED " se cuenta por linea para el cap).
    import sys
    tty = sys.stdout.isatty()

    def log(msg):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        if tty:
            print(line, flush=True)
        try:
            with open(log_file, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass
    return log


def load_env(path=ENV_FILE):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_budget():
    month = time.strftime("%Y-%m")
    b = {"month": month, "posts": 0, "spent": 0.0}
    try:
        with open(BUDGET_FILE) as f:
            cur = json.load(f)
        if cur.get("month") == month:
            b = cur
    except Exception:
        pass
    return b


def save_budget(b):
    os.makedirs(os.path.dirname(BUDGET_FILE), exist_ok=True)
    with open(BUDGET_FILE, "w") as f:
        json.dump(b, f)


def posts_today_all():
    """Posts OK de HOY sumando los logs de todos los posters (cap 10/dia)."""
    today = time.strftime("%Y-%m-%d")
    n = 0
    for path in POSTER_LOGS:
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith(today) and " POSTED " in line:
                        n += 1
        except FileNotFoundError:
            pass
    return n


def budget_refusal():
    """None si se puede postear; si no, string con el motivo."""
    if posts_today_all() >= MAX_POSTS_PER_DAY:
        return f"cap diario compartido alcanzado ({MAX_POSTS_PER_DAY}/dia)"
    b = load_budget()
    if b["spent"] + COST_PER_POST > MAX_SPEND_PER_MONTH:
        return (f"cap mensual alcanzado (${b['spent']:.3f}+${COST_PER_POST} "
                f"> ${MAX_SPEND_PER_MONTH:.2f})")
    return None


def make_auth(env):
    from requests_oauthlib import OAuth1
    return OAuth1(env["X_API_KEY"], env["X_API_SECRET"],
                  env["X_ACCESS_TOKEN"], env["X_ACCESS_SECRET"])


def post_text(text, tag, log, dry_run=False, auth=None):
    """Publica un post respetando ledger compartido. True si se posteo
    (o dry-run lo habria hecho). `tag` identifica el post en el log."""
    text = text.strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    reason = budget_refusal()
    if reason:
        log(f"REFUSE {tag} {reason}")
        return False
    if dry_run:
        log(f"DRY-RUN {tag} ({len(text)} chars):")
        print(text, flush=True)
        print("-" * 40, flush=True)
        return True
    import requests
    try:
        r = requests.post(API_URL, json={"text": text}, auth=auth, timeout=30)
        body = r.text.replace("\n", " ")[:100]
        if r.status_code == 201:
            b = load_budget()
            b["posts"] += 1
            b["spent"] = round(b["spent"] + COST_PER_POST, 4)
            save_budget(b)
            log(f"POSTED {tag} 201 {body}")
            return True
        log(f"FAIL {tag} {r.status_code} {body}")
    except Exception as e:
        log(f"ERROR {tag} exc {str(e)[:100]}")
    return False
