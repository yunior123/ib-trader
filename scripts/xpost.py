#!/usr/bin/env python
"""xpost.py — herramienta REUTILIZABLE para postear a X on-demand, respetando el
ledger compartido (10/dia $4/mes) y con imagen + gexa opcionales.

Uso:
  ./venv/bin/python scripts/xpost.py "texto del tweet"
  ./venv/bin/python scripts/xpost.py "plan $NVDA..." --image ~/Desktop/planes-X/x_media/NVDA_tree.png
  ./venv/bin/python scripts/xpost.py --draft NVDA          # postea el x_draft de hoy + su arbol PNG + gexa
  ./venv/bin/python scripts/xpost.py "..." --sym QQQ       # añade linea gamma de gexa si hay snapshot
  ...cualquiera + --dry-run para NO postear (solo mostrar)

SEÑAL-SOLAMENTE. Reusa x_post_common (misma auth, mismo ledger, mismos caps)."""
import argparse, os, sys, time, glob
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
import x_post_common as xc

def today_dir():
    return os.path.expanduser(f"~/Desktop/planes-{time.strftime('%Y-%m-%d')}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--image", default=None)
    ap.add_argument("--sym", default=None, help="añade linea gamma gexa de ese ticker")
    ap.add_argument("--draft", default=None, help="postea el x_draft de hoy de ese ticker (texto+arbol+gexa)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    text = a.text; image = a.image; sym = a.sym
    if a.draft:
        sym = a.draft.upper()
        dpath = os.path.join(today_dir(), "x_drafts", f"{sym}.txt")
        if not os.path.exists(dpath):
            print(f"sin draft para {sym} hoy ({dpath})"); return 1
        text = open(dpath).read().strip()
        png = os.path.join(today_dir(), "x_media", f"{sym}_tree.png")
        if os.path.exists(png): image = png
    if not text:
        print("nada que postear (dar texto o --draft SYM)"); return 1

    # añadir la linea del mapa gamma PROPIO si hay ticker (append_gex recorta a <=275).
    # gexa jubilado el 2026-07-25 -> scripts/gex_snapshot.py (griegas medidas de Polygon).
    if sym:
        try:
            text = xc.append_gex(text, sym)
        except Exception as e:      # nunca `pass`: si el mapa falla se DICE y se postea sin gamma
            print(f"⚠ sin linea gamma ({type(e).__name__}: {e}) — el post no afirma regimen")

    print(f"--- {'DRY-RUN' if a.dry_run else 'POSTEAR'} ({len(text)} chars){' +imagen' if image else ''} ---")
    print(text)
    if image: print(f"[media: {image}]")
    if a.dry_run:
        print("(dry-run: no se posteo, no se gasto)"); return 0
    # postear real via x_post_common (respeta ledger/caps)
    # FIRMA COMPLETA (fix 2026-07-24): post_text(text, tag, log, dry_run, auth,
    # media_path) exige `tag` y `log` POSICIONALES y el `auth` firmado. Antes se
    # llamaba post_text(text, media_path=...) -> TypeError que el except de abajo
    # se tragaba, y con auth=None la peticion salia SIN FIRMAR (el 401 fantasma
    # que se achacaba a make_auth, que en realidad esta bien).
    try:
        if not hasattr(xc, "post_text"):
            print("x_post_common.post_text no encontrado"); return 1
        env  = xc.load_env()
        auth = xc.make_auth(env)
        log  = xc.make_logger("xpost.log")
        r = xc.post_text(text, "xpost-cli", log, dry_run=False, auth=auth, media_path=image)
        print("resultado:", r)
        if not r:
            print("post_text devolvio False (ledger/cap o fallo de red) — revisa el log")
            return 1
    except Exception as e:
        import traceback; traceback.print_exc()
        print("error al postear:", e); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
