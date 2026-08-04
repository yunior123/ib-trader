#!/usr/bin/env python3
"""discord_send.py — publica en un canal por webhook. Formato CORTO a proposito.

Ley de la casa (memoria `feedback_signals-keep-simple`): compra/vende + ticker +
rebote-o-tendencia en UNA linea. Aqui no se hace analisis: se transporta lo que la alarma
ya decidio mostrar. Cero computo de senal.

Saneado obligatorio: @everyone/@here se neutralizan SIEMPRE — una alerta automatica no
despierta a un servidor entero por un texto que venga de un feed.
"""
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_layout as L           # noqa: E402
import discord_webhooks as W         # noqa: E402

UA = "ib-trader-discord (1.0)"
TIMEOUT_S = 20
MAX_RETRY = 4
MAX_DESC = 4000                      # tope de Discord: 4096 en description, margen de sobra
MAX_CONTENT = 1900                   # tope 2000
MAX_FILE_BYTES = 8 * 1024 * 1024     # limite de subida sin boost

_MENTION = re.compile(r"@(everyone|here)", re.IGNORECASE)
_ALCISTA = re.compile(r"\b(sube|subir|subiendo|alcista|calls?|buy|comprar|rebote al alza|long)\b",
                      re.IGNORECASE)
_BAJISTA = re.compile(r"\b(baja|bajar|bajando|bajista|puts?|sell|vender|short|caida|caída)\b",
                      re.IGNORECASE)


def sanitize(text):
    """Neutraliza menciones masivas sin perder el texto legible."""
    return _MENTION.sub(lambda m: "@​" + m.group(1), text or "")


def direction_color(text, sev):
    """Color por severidad primero; si es normal, por direccion declarada en el propio texto."""
    if sev == L.CRITICA:
        return L.SEV_COLOR[L.CRITICA]
    if sev == L.SISTEMA:
        return L.SEV_COLOR[L.SISTEMA]
    up, down = bool(_ALCISTA.search(text)), bool(_BAJISTA.search(text))
    if up and not down:
        return L.ALCISTA_COLOR
    if down and not up:
        return L.BAJISTA_COLOR
    return L.NEUTRO_COLOR


def build_embed(title, body, sev=L.NORMAL, source=None, ts=None, fields=None, url=None):
    """Embed corto. `fields` es opcional y solo se usa para lo que ya venia estructurado."""
    emb = {"title": sanitize(title)[:250],
           "description": sanitize(body)[:MAX_DESC],
           "color": direction_color(title + " " + (body or ""), sev)}
    if url:
        emb["url"] = url
    if fields:
        emb["fields"] = [{"name": sanitize(str(n))[:250],
                          "value": sanitize(str(v))[:1000],
                          "inline": bool(i)} for n, v, i in fields][:25]
    foot = source or "ib-trader"
    emb["footer"] = {"text": sanitize(foot)[:2000]}
    emb["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                     time.localtime(ts if ts else time.time()))
    return emb


def _post(url, body, headers):
    """POST con reintentos y respeto del 429. (True, None) o (False, motivo). Nunca levanta."""
    last = None
    for attempt in range(MAX_RETRY):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                if 200 <= r.status < 300:
                    return True, None
                last = "status %d" % r.status
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code == 429:
                try:
                    wait = float(json.loads(raw).get("retry_after", 1.0))
                except (ValueError, AttributeError, TypeError):
                    wait = 1.0
                # Tope 10 s, no el retry_after entero: el rele es sincrono, y un sleep de
                # 60 s dejaria las alertas siguientes mas viejas que FRESH_S=45 -> se
                # tirarian todas. Mejor perder ESTE mensaje que atascar la cola entera.
                time.sleep(min(wait + 0.25, 10.0))
                last = "429"
                continue
            if e.code in (401, 403, 404):
                return False, "webhook invalido o borrado (%d)" % e.code
            if 500 <= e.code < 600:
                time.sleep(1.5 * (attempt + 1))
                last = "%d servidor" % e.code
                continue
            return False, "%d %s" % (e.code, raw[:160])
        except Exception as e:
            last = "%s: %s" % (e.__class__.__name__, str(e)[:80])
            time.sleep(1.0 * (attempt + 1))
    return False, "agotados %d intentos: %s" % (MAX_RETRY, last)


def send(channel, embed=None, content=None, mention_role_id=None, hooks=None):
    """Publica en el canal. (True, None) o (False, motivo). Sin webhook -> motivo, no excepcion."""
    hooks = hooks if hooks is not None else W.load()
    url = hooks.get(channel)
    if not url:
        return False, "sin webhook para #%s (corre discord_webhooks.py)" % channel
    payload = {"allowed_mentions": {"parse": [], "roles": []}}
    if content:
        payload["content"] = sanitize(content)[:MAX_CONTENT]
    if mention_role_id:
        payload["content"] = ("<@&%s> " % mention_role_id) + payload.get("content", "")
        payload["content"] = payload["content"][:MAX_CONTENT]
        payload["allowed_mentions"]["roles"] = [str(mention_role_id)]
    if embed:
        payload["embeds"] = [embed]
    if "content" not in payload and "embeds" not in payload:
        return False, "mensaje vacio: no se publica"
    body = json.dumps(payload).encode("utf-8")
    return _post(url + "?wait=true", body,
                 {"Content-Type": "application/json", "User-Agent": UA})


def send_file(channel, path, content=None, embed=None, hooks=None):
    """Adjunta un fichero (PDF de plan, informe). multipart a mano: sin dependencias nuevas."""
    hooks = hooks if hooks is not None else W.load()
    url = hooks.get(channel)
    if not url:
        return False, "sin webhook para #%s" % channel
    if not os.path.isfile(path):
        return False, "no existe %s" % path
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        return False, "%s pesa %.1f MB (tope %.0f MB)" % (
            os.path.basename(path), size / 1e6, MAX_FILE_BYTES / 1e6)
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    payload = {"allowed_mentions": {"parse": [], "roles": []}}
    if content:
        payload["content"] = sanitize(content)[:MAX_CONTENT]
    if embed:
        payload["embeds"] = [embed]
    boundary = "----ibtrader" + uuid.uuid4().hex
    b = boundary.encode()
    parts = [b"--" + b + b"\r\n",
             b'Content-Disposition: form-data; name="payload_json"\r\n',
             b"Content-Type: application/json\r\n\r\n",
             json.dumps(payload).encode("utf-8") + b"\r\n",
             b"--" + b + b"\r\n",
             ('Content-Disposition: form-data; name="files[0]"; filename="%s"\r\n'
              % name.replace('"', "_")).encode("utf-8"),
             ("Content-Type: %s\r\n\r\n" % ctype).encode(),
             data, b"\r\n", b"--" + b + b"--\r\n"]
    return _post(url + "?wait=true", b"".join(parts),
                 {"Content-Type": "multipart/form-data; boundary=" + boundary,
                  "User-Agent": UA})


def send_long(channel, title, text, sev=L.NORMAL, source=None, hooks=None):
    """Trocea un texto largo en varios embeds numerados; nunca se corta a lo bruto."""
    text = text or ""
    chunks = []
    while text:
        cut = text[:MAX_DESC]
        if len(text) > MAX_DESC:
            nl = cut.rfind("\n")
            if nl > MAX_DESC // 2:
                cut = cut[:nl]
        chunks.append(cut)
        text = text[len(cut):].lstrip("\n")
    total = len(chunks)
    for i, c in enumerate(chunks, 1):
        t = title if total == 1 else "%s (%d/%d)" % (title, i, total)
        ok, err = send(channel, build_embed(t, c, sev, source), hooks=hooks)
        if not ok:
            return False, err
        if i < total:
            time.sleep(0.4)
    return True, None
