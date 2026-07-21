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
# v1.1 media upload (multipart). Los posts CON media pueden tener limites/costos
# distintos a los de texto en algunos planes de la API; aqui contamos igual que un
# post de texto (COST_PER_POST) porque no hay constante de costo con-media separada.
UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
GEXA_FILE = os.path.join(ROOT, "data", "gexa_snapshot.json")

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


# ------------------------------------------------------------------ media
def upload_media(image_path, auth, log=None):
    """Sube una imagen via X API v1.1 (multipart 'media'), devuelve
    media_id_string o None. ADITIVO: si algo falla devuelve None y el caller
    cae limpio a texto-solo. Nota: los posts con media pueden costar/limitarse
    distinto en la API v2; el ledger los cuenta como un post normal."""
    if not image_path or not os.path.exists(image_path):
        return None
    if auth is None:
        return None
    try:
        import requests
        with open(image_path, "rb") as f:
            r = requests.post(UPLOAD_URL, files={"media": f}, auth=auth,
                              timeout=60)
        if r.status_code in (200, 201):
            mid = r.json().get("media_id_string")
            if mid:
                return mid
        if log:
            log(f"MEDIA-FAIL {r.status_code} {r.text[:80].replace(chr(10), ' ')}")
    except Exception as e:
        if log:
            log(f"MEDIA-ERROR {str(e)[:80]}")
    return None


# ------------------------------------------------------------------ gexa
def load_gexa(path=GEXA_FILE):
    """dict {SYM: {flip, flip_all, score, bias, poc}} o {} si falta/roto."""
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def gexa_line(sym, gexa=None):
    """Linea compacta de gamma para `sym`, o '' si no hay datos (degrade limpio).
    Ej: '📊 gamma: flip 705 · dealer -1.2 · POC 702'."""
    if gexa is None:
        gexa = load_gexa()
    d = gexa.get(sym) or gexa.get(sym.upper())
    if not isinstance(d, dict):
        return ""
    parts = []
    if d.get("flip") is not None:
        parts.append(f"flip {d['flip']}")
    if d.get("score") is not None:
        parts.append(f"dealer {d['score']}")
    if d.get("poc") is not None:
        parts.append(f"POC {d['poc']}")
    return "📊 gamma: " + " · ".join(parts) if parts else ""


def append_gexa(text, sym, gexa=None, max_chars=MAX_CHARS):
    """Agrega la linea de gamma a `text` manteniendo <=max_chars. Trunca la
    COLA del texto (quip) si hace falta, jamas la linea de gamma; los niveles
    viven al frente asi que se preservan. Sin datos gexa: devuelve text igual."""
    line = gexa_line(sym, gexa)
    if not line:
        return text
    text = text.rstrip()
    add = "\n" + line
    if len(text) + len(add) <= max_chars:
        return text + add
    keep = max_chars - len(add) - 1      # -1 por la elipsis
    if keep < 0:
        return text[:max_chars]
    return text[:keep].rstrip() + "…" + add


def sanitize_cashtags(text):
    """X rechaza (403) posts con 2+ cashtags $SYM — conservar solo el PRIMERO.
    Error repetido 2x el 2026-07-21 → docs/ERRORES.md. Los demas pierden el $."""
    import re
    seen = [0]
    def rep(m):
        seen[0] += 1
        return m.group(0) if seen[0] == 1 else m.group(0)[1:]
    return re.sub(r"\$(?=[A-Za-z]{1,5}\b)", lambda m: "$" if seen.__setitem__(0, seen[0]+1) or seen[0] == 1 else "", text) if False else re.sub(r"\$([A-Za-z]{1,5}\b)", rep, text)

def post_text(text, tag, log, dry_run=False, auth=None, media_path=None):
    """Publica un post respetando ledger compartido. True si se posteo
    (o dry-run lo habria hecho). `tag` identifica el post en el log.
    `media_path` (opcional): si se pasa y la subida v1.1 tiene exito, adjunta la
    imagen al post v2; si la subida falla, cae limpio a texto-solo (no crashea).
    El ledger cuenta un post con media igual que uno de texto (COST_PER_POST)."""
    text = sanitize_cashtags(text.strip())
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    reason = budget_refusal()
    if reason:
        log(f"REFUSE {tag} {reason}")
        return False
    if dry_run:
        has_media = bool(media_path and os.path.exists(media_path))
        note = f" +media {media_path}" if has_media else ""
        log(f"DRY-RUN {tag} ({len(text)} chars){note}:")
        print(text, flush=True)
        print("-" * 40, flush=True)
        return True
    import requests
    body = {"text": text}
    if media_path:
        media_id = upload_media(media_path, auth, log)
        if media_id:
            body["media"] = {"media_ids": [media_id]}
        else:
            log(f"MEDIA-SKIP {tag} subida fallo -> texto-solo")
    try:
        r = requests.post(API_URL, json=body, auth=auth, timeout=30)
        resp = r.text.replace("\n", " ")[:100]
        if r.status_code == 201:
            b = load_budget()
            b["posts"] += 1
            b["spent"] = round(b["spent"] + COST_PER_POST, 4)
            save_budget(b)
            media_tag = " +media" if "media" in body else ""
            log(f"POSTED {tag}{media_tag} 201 {resp}")
            return True
        log(f"FAIL {tag} {r.status_code} {resp}")
    except Exception as e:
        log(f"ERROR {tag} exc {str(e)[:100]}")
    return False
