#!/usr/bin/env python3
"""x_plan_poster.py — publica en X los TOP-N drafts de los planes diarios de flota.

Lee ~/Desktop/planes-YYYY-MM-DD/ranking.json + x_drafts/<SYM>.txt y postea los
TOP-N (por score) como posts de texto simple (sin URLs, sin media) via X API v2.
SEÑAL-SOLAMENTE: los drafts ya incluyen "No es consejo financiero".

Presupuesto PROPIO (separado de x_whale_bot): data/x_plan_budget.json
{month, posts, spent}. $0.015/post. HARD caps: 3 posts/dia, $4.00/mes.
Log: x_plan_poster.log en la raiz del repo.

Uso: x_plan_poster.py [--top 3] [--dry-run] [--dir /ruta/planes-...]
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_post_common as xc   # upload_media + append_gexa (aditivo, degrade limpio)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDGET_FILE = os.path.join(ROOT, "data", "x_plan_budget.json")
LOG_FILE = os.path.join(ROOT, "x_plan_poster.log")
ENV_FILE = os.path.join(ROOT, "x.env")

COST_PER_POST = 0.015
MAX_POSTS_PER_DAY = 3
MAX_SPEND_PER_MONTH = 2.00
MAX_CHARS = 275
API_URL = "https://api.x.com/2/tweets"


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_env(path):
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


def posts_today():
    """Cuenta posts OK de hoy en el log (hard cap diario)."""
    today = time.strftime("%Y-%m-%d")
    n = 0
    try:
        with open(LOG_FILE) as f:
            for line in f:
                if line.startswith(today) and " POSTED " in line:
                    n += 1
    except FileNotFoundError:
        pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dir", default=os.path.expanduser(
        f"~/Desktop/planes-{time.strftime('%Y-%m-%d')}"))
    a = ap.parse_args()

    rank_path = os.path.join(a.dir, "ranking.json")
    if not os.path.exists(rank_path):
        log(f"SKIP sin ranking.json en {a.dir}")
        return 0
    with open(rank_path) as f:
        ranking = json.load(f)
    if not ranking:
        log(f"SKIP ranking.json vacio en {a.dir}")
        return 0
    ranking.sort(key=lambda r: r.get("score", 0), reverse=True)

    env = load_env(ENV_FILE)
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN",
                           "X_ACCESS_SECRET") if not env.get(k)]
    if missing and not a.dry_run:
        log(f"ERROR faltan credenciales en x.env: {','.join(missing)}")
        return 1

    budget = load_budget()
    done_today = posts_today()
    posted = 0

    auth = None
    if not a.dry_run:
        from requests_oauthlib import OAuth1
        import requests
        auth = OAuth1(env["X_API_KEY"], env["X_API_SECRET"],
                      env["X_ACCESS_TOKEN"], env["X_ACCESS_SECRET"])

    for row in ranking[:max(0, a.top)]:
        sym = row.get("sym", "?")
        # HARD caps — este poster tiene su propio ledger
        if done_today + posted >= MAX_POSTS_PER_DAY:
            log(f"REFUSE {sym} cap diario alcanzado ({MAX_POSTS_PER_DAY}/dia)")
            break
        if budget["spent"] + COST_PER_POST > MAX_SPEND_PER_MONTH:
            log(f"REFUSE {sym} cap mensual alcanzado "
                f"(${budget['spent']:.3f}+${COST_PER_POST} > ${MAX_SPEND_PER_MONTH:.2f})")
            break

        draft_path = os.path.join(a.dir, "x_drafts", f"{sym}.txt")
        if not os.path.exists(draft_path):
            log(f"SKIP {sym} sin draft {draft_path}")
            continue
        with open(draft_path) as f:
            text = f.read().strip()
        if not text:
            log(f"SKIP {sym} draft vacio")
            continue
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
        # ADITIVO: linea del mapa gamma PROPIO (griegas medidas de Polygon; gexa jubilado
        # el 2026-07-25). Se salta sola si no hay snapshot/ticker: el post calla el regimen
        # antes que afirmar uno que no medimos.
        text = xc.append_gex(text, sym, max_chars=MAX_CHARS)

        # ADITIVO: imagen del arbol de escenarios si el PDF la genero; si falta,
        # se postea texto-solo (comportamiento previo intacto).
        media_path = os.path.join(a.dir, "x_media", f"{sym}_tree.png")
        if not os.path.exists(media_path):
            media_path = None

        if a.dry_run:
            note = f" +media {media_path}" if media_path else " (texto-solo)"
            log(f"DRY-RUN {sym} ({len(text)} chars){note}:")
            print(text)
            print("-" * 40)
            posted += 1
            continue

        import requests
        try:
            body = {"text": text}
            if media_path:
                media_id = xc.upload_media(media_path, auth, log)
                if media_id:
                    body["media"] = {"media_ids": [media_id]}
                else:
                    log(f"MEDIA-SKIP {sym} subida fallo -> texto-solo")
            r = requests.post(API_URL, json=body, auth=auth, timeout=30)
            resp = r.text.replace("\n", " ")[:100]
            if r.status_code == 201:
                posted += 1
                budget["posts"] += 1
                budget["spent"] = round(budget["spent"] + COST_PER_POST, 4)
                save_budget(budget)
                media_tag = " +media" if "media" in body else ""
                log(f"POSTED {sym}{media_tag} 201 {resp}")
            else:
                log(f"FAIL {sym} {r.status_code} {resp}")
        except Exception as e:
            log(f"ERROR {sym} exc {str(e)[:100]}")

    tag = "dry-run" if a.dry_run else "reales"
    log(f"DONE {posted} posts {tag} | mes {budget['month']}: "
        f"{budget['posts']} posts ${budget['spent']:.3f}/{MAX_SPEND_PER_MONTH:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
