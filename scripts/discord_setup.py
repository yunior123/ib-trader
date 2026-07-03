#!/usr/bin/env python3
"""discord_setup.py — crea/actualiza el servidor segun discord_layout.py. IDEMPOTENTE.

Reejecutarlo no duplica nada: categorias, canales y roles se buscan por NOMBRE y solo se
parchea lo que difiere. Nunca borra (salvo --delete-obsolete explicito, que solo ARCHIVA
renombrando; borrar de verdad es cosa de Yunior en la UI).

  ./venv/bin/python scripts/discord_setup.py --invite-url   # enlace OAuth2 para invitar el bot
  ./venv/bin/python scripts/discord_setup.py --dry-run      # que haria, sin tocar nada
  ./venv/bin/python scripts/discord_setup.py                # aplica
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_client as dc          # noqa: E402
import discord_layout as L           # noqa: E402

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
ADD_REACTIONS = 1 << 6
READ_HISTORY = 1 << 16
CREATE_THREADS = 1 << 35
SEND_IN_THREADS = 1 << 38
MANAGE_CHANNELS = 1 << 4
MANAGE_ROLES = 1 << 28
MANAGE_WEBHOOKS = 1 << 29
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
MANAGE_MESSAGES = 1 << 13

INVITE_PERMS = (VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES | READ_HISTORY
                | MANAGE_CHANNELS | MANAGE_ROLES | MANAGE_WEBHOOKS | MANAGE_MESSAGES
                | CREATE_THREADS | SEND_IN_THREADS | ADD_REACTIONS)

TYPE_TEXT = 0
TYPE_CATEGORY = 4
OW_ROLE = 0
REASON = "ib-trader: estructura de sala de alertas (discord_setup.py)"


def invite_url(app_id=None, gid=None):
    app_id = app_id or dc.secret("DISCORD_APP_ID")
    gid = gid or dc.guild_id()
    if not app_id:
        raise dc.DiscordError("sin DISCORD_APP_ID en config/feeds.env")
    url = ("https://discord.com/oauth2/authorize?client_id=%s&scope=bot+applications.commands"
           "&permissions=%d" % (app_id, INVITE_PERMS))
    if gid:
        url += "&guild_id=%s&disable_guild_select=true" % gid
    return url


def _by_name(items, name, ctype=None):
    for it in items:
        if it.get("name") == name and (ctype is None or it.get("type") == ctype):
            return it
    return None


def ensure_roles(gid, existing, dry):
    """Crea los roles que falten. Devuelve {nombre: id}. No toca los que ya existen."""
    out = {}
    for name, color, mentionable, motivo in L.ROLES:
        found = _by_name(existing, name)
        if found:
            out[name] = found["id"]
            continue
        if dry:
            print("  [dry] CREAR rol %s (%s)" % (name, motivo))
            out[name] = "dry-" + name
            continue
        r = dc.request("POST", "/guilds/%s/roles" % gid,
                       {"name": name, "color": color, "mentionable": mentionable,
                        "permissions": "0", "hoist": False}, reason=REASON)
        out[name] = r["id"]
        print("  + rol %s" % name)
    return out


def overwrites(everyone_id, role_ids, private, is_alert):
    """Permisos del canal. Miembros NO publican en canales automaticos; privados no se ven."""
    ow = []
    deny = 0
    allow = 0
    if private:
        deny |= VIEW_CHANNEL
    if is_alert:
        deny |= SEND_MESSAGES | CREATE_THREADS
        allow |= READ_HISTORY | ADD_REACTIONS
    ow.append({"id": everyone_id, "type": OW_ROLE, "deny": str(deny), "allow": str(allow)})
    full = VIEW_CHANNEL | READ_HISTORY | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES
    for rname in ("Admin", "Bot Alertas"):
        if rname in role_ids:
            ow.append({"id": role_ids[rname], "type": OW_ROLE,
                       "allow": str(full | SEND_IN_THREADS), "deny": "0"})
    if "Trader" in role_ids:
        ow.append({"id": role_ids["Trader"], "type": OW_ROLE,
                   "allow": str(VIEW_CHANNEL | READ_HISTORY | ADD_REACTIONS),
                   "deny": str(SEND_MESSAGES if is_alert else 0)})
    if "Muted" in role_ids:
        ow.append({"id": role_ids["Muted"], "type": OW_ROLE, "allow": "0",
                   "deny": str(SEND_MESSAGES | ADD_REACTIONS)})
    return ow


def ensure_structure(gid, dry=False):
    """Crea categorias y canales que falten; parchea topic/permisos de los existentes."""
    existing_roles = dc.roles(gid)
    everyone = _by_name(existing_roles, "@everyone") or {"id": gid}
    role_ids = ensure_roles(gid, existing_roles, dry)
    chans = dc.channels(gid)
    alert_keys = L.alert_channels()
    ids = L.load_ids()
    created = patched = 0

    for pos, (cat_key, cat_name, children) in enumerate(L.CATEGORIES):
        cat = L.resolve("cat:" + cat_key, chans, ids, TYPE_CATEGORY) or \
            _by_name(chans, cat_name, TYPE_CATEGORY)
        if cat is None:
            if dry:
                print("[dry] CREAR categoria %s" % cat_name)
                cat = {"id": "dry-" + cat_key}
            else:
                cat = dc.request("POST", "/guilds/%s/channels" % gid,
                                 {"name": cat_name, "type": TYPE_CATEGORY, "position": pos},
                                 reason=REASON)
                print("+ categoria %s" % cat_name)
            created += 1
        if not dry:
            ids["cat:" + cat_key] = cat["id"]
        for cpos, (key, topic, private) in enumerate(children):
            ch = L.resolve(key, chans, ids, TYPE_TEXT)
            is_alert = key in alert_keys
            ow = overwrites(everyone["id"], role_ids, private, is_alert)
            if ch is None:
                if dry:
                    print("  [dry] CREAR #%s%s%s" % (key, " [privado]" if private else "",
                                                     " [solo-bot]" if is_alert else ""))
                else:
                    ch = dc.request("POST", "/guilds/%s/channels" % gid,
                                    {"name": key, "type": TYPE_TEXT, "topic": topic,
                                     "parent_id": cat["id"], "position": cpos,
                                     "permission_overwrites": ow}, reason=REASON)
                    print("  + #%s" % key)
                created += 1
            elif ch.get("topic") != topic or ch.get("parent_id") != cat["id"]:
                if dry:
                    print("  [dry] PARCHEAR #%s (topic/categoria)" % key)
                else:
                    dc.request("PATCH", "/channels/%s" % ch["id"],
                               {"topic": topic, "parent_id": cat["id"]}, reason=REASON)
                    print("  ~ #%s" % key)
                patched += 1
            if not dry and ch:
                ids[key] = ch["id"]
    if not dry:
        L.save_ids(ids)                # el nombre puede cambiar; el id no
    return created, patched


def main():
    ap = argparse.ArgumentParser(description="estructura del servidor Discord (idempotente)")
    ap.add_argument("--dry-run", action="store_true", help="dice que haria, no toca nada")
    ap.add_argument("--invite-url", action="store_true", help="imprime el enlace OAuth2 y sale")
    a = ap.parse_args()

    if a.invite_url:
        print(invite_url())
        return 0

    gid = dc.guild_id()
    if not gid:
        print("discord_setup ROTO: sin DISCORD_GUILD_ID", file=sys.stderr)
        return 1
    ok, info = dc.in_guild(gid)
    if not ok:
        print("EL BOT NO ESTA EN EL SERVIDOR (%s).\nAutoriza con:\n  %s"
              % (info, invite_url()), file=sys.stderr)
        return 2
    print("servidor: %s (%s)%s" % (info, gid, "  [DRY-RUN]" if a.dry_run else ""))
    created, patched = ensure_structure(gid, a.dry_run)
    print("resumen: %d por crear/creados, %d parcheados" % (created, patched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
