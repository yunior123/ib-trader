#!/usr/bin/env python3
"""send_ticker_email.py — UN email por ticker (Yunior 2026-08-03: "one email per ticker").

Toma ficheros <SYM>.html ya renderizados y los manda como CUERPO del correo (no adjunto):
Yunior los lee en el movil antes de la apertura y un PDF adjunto exige abrirlo.
Distinto de daily_fleet_plans.send_email, que manda UN correo con N PDFs pegados.

  scripts/send_ticker_email.py --dir data/analisis_2026-08-03 [--syms QQQ SPY] [--dry]
"""
import argparse
import glob
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NOTIFY_OFF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "notify_off")
if os.path.exists(_NOTIFY_OFF):
    raise SystemExit("notificaciones apagadas (data/notify_off)")

API = "https://api.resend.com/emails"
FROM = "onboarding@resend.dev"
PAUSA_S = 0.7          # Resend limita ~2 req/s; por debajo del limite a proposito
TIMEOUT_S = 30


def env():
    """config/feeds.env -> dict. Levanta si falta el fichero: sin claves no hay correo."""
    path = os.path.join(ROOT, "config", "feeds.env")
    out = {}
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def asunto(sym, html):
    """Cabecera del correo desde el <h1>/<title>; si no hay, el simbolo y la fecha."""
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    t = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return f"📈 {t}" if t else f"📈 {sym} — plan {time.strftime('%Y-%m-%d')}"


def enviar(key, to, sym, html, dry=False):
    if dry:
        return f"DRY {sym} ({len(html)} bytes) -> {to}"
    r = requests.post(
        API, timeout=TIMEOUT_S,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"from": FROM, "to": [to], "subject": asunto(sym, html), "html": html},
    )
    return f"{r.status_code} {r.text[:160]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="directorio con los <SYM>.html")
    ap.add_argument("--syms", nargs="*", help="subconjunto; por defecto todos los .html del dir")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    d = a.dir if os.path.isabs(a.dir) else os.path.join(ROOT, a.dir)
    e = env()
    key, to = e.get("RESEND_KEY"), e.get("RESEND_TO")
    if not key or not to:
        sys.exit("sin RESEND_KEY/RESEND_TO en config/feeds.env")

    if a.syms:
        paths = [os.path.join(d, f"{s.upper()}.html") for s in a.syms]
    else:
        paths = sorted(glob.glob(os.path.join(d, "*.html")))
    if not paths:
        sys.exit(f"ningun .html en {d}")

    fallos = 0
    for p in paths:
        sym = os.path.splitext(os.path.basename(p))[0].upper()
        if not os.path.exists(p):
            print(f"{sym}: AUSENTE {p}")
            fallos += 1
            continue
        with open(p, encoding="utf-8") as f:
            html = f.read()
        if len(html) < 200:
            print(f"{sym}: HTML de {len(html)} bytes — sospechoso, NO se manda")
            fallos += 1
            continue
        try:
            res = enviar(key, to, sym, html, a.dry)
        except requests.RequestException as ex:
            print(f"{sym}: RED {ex}")
            fallos += 1
            continue
        print(f"{sym}: {res}")
        if not res.startswith(("200", "DRY")):
            fallos += 1
        time.sleep(PAUSA_S)

    print(f"\n{len(paths) - fallos}/{len(paths)} enviados a {to}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
