#!/usr/bin/env python3
"""discord_webhooks.py — un webhook por canal publicable. IDEMPOTENTE (reusa por nombre).

Las URLs van a config/discord_webhooks.json (chmod 600, gitignored). Una URL de webhook ES
una credencial: quien la tenga publica en el canal. Nunca se imprime entera.

El relé usa webhooks y no el bot: si el proceso del bot muere, publicar sigue siendo un POST
sin estado. Es la parte del sistema que no puede depender de una sesion Gateway viva.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_client as dc          # noqa: E402
import discord_layout as L           # noqa: E402

REPO = dc.REPO
STORE = os.path.join(REPO, "config", "discord_webhooks.json")
HOOK_NAME = "ib-trader"


def load(path=STORE):
    """{canal: url}. {} si no existe todavia (aun no es un error: se crea al arrancar)."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(hooks, path=STORE):
    """Escritura atomica + 600. El fichero es una credencial."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(hooks, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def mask(url):
    """Nunca se imprime una URL de webhook entera."""
    if not url:
        return "(vacia)"
    tail = url.rsplit("/", 1)[0].rsplit("/", 1)[-1]
    return ".../webhooks/%s/<token oculto>" % tail


def ensure(gid=None, dry=False):
    """Crea o reusa un webhook por canal publicable. Devuelve (hooks, creados, reusados)."""
    gid = gid or dc.guild_id()
    chans = dc.channels(gid)
    ids = L.load_ids()
    hooks = load()
    creados = reusados = 0
    faltan = []
    for key in sorted(L.webhook_channels()):
        ch = L.resolve(key, chans, ids)      # por id primero: renombrar no debe crear duplicados
        if ch is None:
            faltan.append(key)
            continue
        existing = dc.request("GET", "/channels/%s/webhooks" % ch["id"])
        mine = next((w for w in existing if w.get("name") == HOOK_NAME and w.get("url")), None)
        if mine:
            hooks[key] = mine["url"]
            reusados += 1
            continue
        if dry:
            print("  [dry] CREAR webhook en #%s" % key)
            creados += 1
            continue
        w = dc.request("POST", "/channels/%s/webhooks" % ch["id"], {"name": HOOK_NAME},
                       reason="ib-trader: publicacion de alertas")
        hooks[key] = w["url"]
        creados += 1
        print("  + webhook #%s -> %s" % (key, mask(w["url"])))
    if not dry:
        save(hooks)
    return hooks, creados, reusados, faltan


def main():
    ap = argparse.ArgumentParser(description="webhooks por canal (idempotente)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true", help="lista los guardados, enmascarados")
    a = ap.parse_args()

    if a.list:
        hooks = load()
        if not hooks:
            print("sin webhooks todavia (%s)" % STORE)
            return 1
        for k in sorted(hooks):
            print("  %-24s %s" % ("#" + k, mask(hooks[k])))
        return 0

    gid = dc.guild_id()
    ok, info = dc.in_guild(gid)
    if not ok:
        print("EL BOT NO ESTA EN EL SERVIDOR: %s" % info, file=sys.stderr)
        return 2
    hooks, creados, reusados, faltan = ensure(gid, a.dry_run)
    print("webhooks: %d creados, %d reusados, %d guardados en %s"
          % (creados, reusados, len(hooks), STORE))
    if faltan:
        print("CANALES QUE FALTAN (corre discord_setup.py primero): %s"
              % ", ".join(faltan), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
