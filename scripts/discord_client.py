#!/usr/bin/env python3
"""discord_client.py — cliente REST minimo de Discord (stdlib, sin dependencias nuevas).

Mueve bytes y nada mas: cero computo de senal aqui dentro (regla PYTHON ES PELIGROSO).
El token NUNCA se imprime, ni se loguea, ni se escribe en un fichero del repo:
vive en config/feeds.env (chmod 600, gitignored) y solo viaja en la cabecera.
Rate limit: Discord responde 429 con retry_after en segundos; se respeta tal cual.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://discord.com/api/v10"
UA = "ib-trader-discord (https://github.com/ib-trader, 1.0)"
TIMEOUT_S = 20
MAX_RETRY = 4


class DiscordError(RuntimeError):
    """Fallo de la API. Lleva el status para que el llamador decida; jamas fabrica datos."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def _feeds_env():
    """config/feeds.env -> dict. Formato KEY=VALOR, ignora comentarios y lineas vacias."""
    path = os.path.join(REPO, "config", "feeds.env")
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out


def secret(name):
    """Valor del entorno o de feeds.env. None si no existe (jamas cadena vacia plausible)."""
    v = os.environ.get(name)
    if v:
        return v
    v = _feeds_env().get(name)
    return v or None


def token():
    return secret("DISCORD_BOT_TOKEN")


def guild_id():
    return secret("DISCORD_GUILD_ID")


def redact(text):
    """Quita de un texto cualquier secreto conocido antes de imprimirlo o loguearlo."""
    if not text:
        return text
    for name in ("DISCORD_BOT_TOKEN", "UW_TOKEN", "POLYGON_KEY", "RESEND_KEY",
                 "FINNHUB_KEY", "INTRINIO_API_KEY"):
        v = secret(name)
        if v and len(v) > 8:
            text = text.replace(v, "<" + name + ">")
    return text


def request(method, path, payload=None, tok=None, reason=None):
    """Llamada autenticada. Devuelve el JSON (o None en 204). Levanta DiscordError si falla."""
    tok = tok or token()
    if not tok:
        raise DiscordError("sin DISCORD_BOT_TOKEN (entorno ni config/feeds.env)")
    url = path if path.startswith("http") else API + path
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": "Bot " + tok, "User-Agent": UA,
               "Content-Type": "application/json"}
    if reason:
        headers["X-Audit-Log-Reason"] = reason[:400]
    last = None
    for attempt in range(MAX_RETRY):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                raw = r.read()
                if r.status == 204 or not raw:
                    return None
                return json.loads(raw.decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code == 429:
                try:
                    wait = float(json.loads(raw).get("retry_after", 1.0))
                except (ValueError, AttributeError, TypeError):
                    wait = 1.0
                time.sleep(min(wait + 0.25, 60.0))
                last = "429 rate limit"
                continue
            if 500 <= e.code < 600:
                time.sleep(1.5 * (attempt + 1))
                last = "%d servidor" % e.code
                continue
            raise DiscordError("%s %s -> %d %s" % (method, path, e.code, redact(raw)[:300]),
                               status=e.code)
        except Exception as e:                                   # red caida, DNS, timeout
            last = "%s: %s" % (e.__class__.__name__, str(e)[:80])
            time.sleep(1.0 * (attempt + 1))
    raise DiscordError("%s %s agotados %d intentos: %s" % (method, path, MAX_RETRY, last))


def me(tok=None):
    return request("GET", "/users/@me", tok=tok)


def guild(gid=None, tok=None):
    gid = gid or guild_id()
    if not gid:
        raise DiscordError("sin DISCORD_GUILD_ID")
    return request("GET", "/guilds/%s" % gid, tok=tok)


def guilds(tok=None):
    return request("GET", "/users/@me/guilds", tok=tok)


def channels(gid=None, tok=None):
    gid = gid or guild_id()
    return request("GET", "/guilds/%s/channels" % gid, tok=tok)


def roles(gid=None, tok=None):
    gid = gid or guild_id()
    return request("GET", "/guilds/%s/roles" % gid, tok=tok)


def bot_member(gid=None, tok=None):
    gid = gid or guild_id()
    return request("GET", "/guilds/%s/members/@me" % gid, tok=tok)


def in_guild(gid=None, tok=None):
    """(True, None) si el bot esta dentro; (False, motivo) si no. Nunca levanta por 403/404."""
    gid = gid or guild_id()
    try:
        g = guild(gid, tok)
        return True, g.get("name")
    except DiscordError as e:
        if e.status in (401, 403, 404):
            return False, "status %s: el bot no esta en el servidor o le falta acceso" % e.status
        raise


def main():
    """Diagnostico: identidad del bot, servidores y permisos efectivos. Sin secretos."""
    try:
        u = me()
    except DiscordError as e:
        print("discord_client ROTO: %s" % e, file=sys.stderr)
        return 1
    print("bot: %s (id %s)" % (u.get("username"), u.get("id")))
    gs = guilds()
    print("servidores: %d" % len(gs))
    for g in gs:
        print("  - %s (%s)" % (g.get("name"), g.get("id")))
    gid = guild_id()
    if not gid:
        print("sin DISCORD_GUILD_ID configurado", file=sys.stderr)
        return 1
    ok, info = in_guild(gid)
    if not ok:
        print("guild %s: NO ACCESIBLE -> %s" % (gid, info), file=sys.stderr)
        print("invita al bot con el enlace OAuth2 (scripts/discord_setup.py --invite-url)",
              file=sys.stderr)
        return 2
    chans = channels(gid)
    print("guild %s: %s | %d canales | %d roles" % (gid, info, len(chans), len(roles(gid))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
