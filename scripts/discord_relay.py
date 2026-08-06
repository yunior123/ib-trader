#!/usr/bin/env python3
"""discord_relay.py — espejo de data/notify_push.txt -> Discord. 100% del sistema de alertas.

Consumidor INDEPENDIENTE del mismo embudo que ya sigue notify_relay.sh (ntfy + Resend): no
se toca el relé existente, asi que Discord no puede añadir latencia ni romper la voz/ntfy.
Los 19 llamadores de notify_short.py (bots, bollinger, ballenas, manada, finviz, corea,
proveedores) desembocan aqui sin tocar ni uno.

Hereda TODAS las leyes anti-ruido medidas del relé de ntfy:
  - frescura: mas viejo que 45 s no se publica (el retraso es dinero, y una alerta tardia miente)
  - backlog (>300 s): se salta en SILENCIO — es relectura/arranque, no una alerta
  - dedup por payload en 60 s
  - cap 1/5 s, con bypass para SELL/STOP/TERREMOTO/DANGER/🌋
Y añade una propia, medida el 2026-08-04: 168 de 676 lineas del embudo (25%) eran
infraestructura (INTRINIO WS, CINTA CIEGA, KRX SIN GATEWAY). Eso va a #estado-proveedores
(privado, sin mencion), no a los canales de alerta.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_client as dc          # noqa: E402
import discord_layout as L           # noqa: E402
import discord_send as S             # noqa: E402
import discord_webhooks as W         # noqa: E402

REPO = dc.REPO
FUNNEL = os.path.join(REPO, "data", "notify_push.txt")
LOG = os.path.join(REPO, "logs", "discord_relay.log")
LOG_MAX = 20 * 1024 * 1024

FRESH_S = 45          # mas viejo que esto: no se publica
BACKLOG_S = 300       # mas viejo que esto: ni se registra (relectura)
DEDUP_S = 60
CAP_S = 5
POLL_S = 0.5
COLA_MAX = 60         # rafaga retenida por el cap; mas que esto es una tormenta, no una rafaga

# Las tres senales MAS selectivas de la casa (confluencia, manada, capitan) tambien saltan el
# cap: medido 2026-08-05, el cap se comio 6 de #confluencia, 8 de #manada y 1 de #capitanes.
PRIORIDAD = re.compile(r"SELL|STOP|TERREMOTO|DANGER|🌋|🚨|🔗|🐺|🐘|🎖", re.IGNORECASE)
LINE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}) \| (.*?) \| (.*)$")


def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX:
            with open(LOG) as f:
                keep = f.readlines()[-2000:]
            with open(LOG, "w") as f:
                f.writelines(keep)
        with open(LOG, "a") as f:
            # con FECHA: sin ella era imposible datar un evento del log (la propia auditoria
            # del 2026-08-05 tuvo que apoyarse en los separadores del keepalive)
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), dc.redact(msg)))
    except OSError:
        pass


def parse(line):
    """(edad_s, titulo, cuerpo) o None si la linea no tiene el formato del embudo."""
    m = LINE.match(line.strip())
    if not m:
        return None
    hh, mm, ss, title, body = m.groups()
    lt = time.localtime()
    t = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, int(hh), int(mm), int(ss),
                     0, 0, lt.tm_isdst))
    # El sello solo lleva HH:MM:SS: a las 00:05, una linea de las 23:59 parecia venir del
    # FUTURO (edad -86099 s) y el filtro age<-60 la tiraba en silencio. Si el sello queda
    # mas de 60 s por delante del reloj, era de ayer.
    if t - time.time() > 60:
        t -= 86400.0
    return time.time() - t, title.strip(), body.strip()


def mention_id(role_ids, sev):
    """Solo las criticas mencionan, y solo al rol declarado. Nunca @everyone."""
    if sev != L.CRITICA:
        return None
    return role_ids.get(L.MENTION_ROLE)


def route(title, body, universe=None):
    """(canal_principal, severidad, canales_espejo). Todo el enrutado vive en discord_layout."""
    full = title + " | " + body
    ch, sev = L.classify(full)
    mirrors = [] if sev == L.SISTEMA else [m for m in L.mirror_channels(full, universe)
                                           if m != ch]
    return ch, sev, mirrors


def load_role_ids():
    """{nombre: id} de los roles del servidor. {} si no se puede leer: se publica sin mencion."""
    try:
        return {r["name"]: r["id"] for r in dc.roles()}
    except Exception as e:
        log("roles no legibles (%s): se publicara sin menciones" % e.__class__.__name__)
        return {}


def enviar(item, role_ids, hooks):
    """Publica UNA alerta en su canal y sus espejos. True si el canal principal la acepto."""
    ok, err = S.send(item["ch"], item["emb"], mention_id(role_ids, item["sev"]), hooks=hooks)
    if not ok:
        log("FALLO #%s: %s | %s" % (item["ch"], err, item["title"][:50]))
        return False
    log("ENVIADA #%s [%s] %s" % (item["ch"], item["sev"], item["title"][:50]))
    for m in item["mirrors"]:
        mok, merr = S.send(m, item["emb"], hooks=hooks)
        if not mok:
            log("FALLO espejo #%s: %s" % (m, merr))
    return True


def drenar(estado, role_ids, hooks, ahora=None):
    """Vacia la cola del cap agrupando por canal en un solo POST multi-embed por canal.

    Antes esto era un `continue`: 200 de 909 alertas (18%) se tiraban en 34,5 h, y 44 de ellas
    dentro de la ventana de oro 09:00-10:00 (auditoria 2026-08-05). Ahora se retienen y salen
    juntas en el siguiente hueco. La ley de frescura SIGUE mandando: lo que espero mas de
    FRESH_S se descarta igual, porque una alerta tardia miente.
    """
    now = time.time() if ahora is None else ahora
    if not estado["cola"] or now - estado["lastsent"] < CAP_S:
        return 0
    vivos, viejos = [], 0
    for it in estado["cola"]:
        if now - it["ts"] > FRESH_S:
            viejos += 1
            log("DESCARTADA en cola (%ds vieja): %s" % (int(now - it["ts"]), it["title"][:50]))
        else:
            vivos.append(it)
    estado["cola"] = []
    if not vivos:
        return 0
    por_canal = {}
    for it in vivos:
        por_canal.setdefault(it["ch"], []).append(it)
        for m in it["mirrors"]:
            por_canal.setdefault(m, []).append(dict(it, ch=m, mirrors=[], sev=L.SISTEMA))
    enviados = 0
    for ch, items in por_canal.items():
        for i in range(0, len(items), S.MAX_EMBEDS):
            lote = items[i:i + S.MAX_EMBEDS]
            mid = next((mention_id(role_ids, x["sev"]) for x in lote
                        if x["sev"] == L.CRITICA), None)
            ok, err = S.send_many(ch, [x["emb"] for x in lote], mid, hooks=hooks)
            if ok:
                enviados += len(lote)
                log("COLA -> #%s: %d agrupadas (%s)"
                    % (ch, len(lote), " · ".join(x["title"][:24] for x in lote[:4])))
            else:
                log("FALLO cola #%s: %s" % (ch, err))
    estado["lastsent"] = now
    return enviados


def follow(path):
    """Generador de lineas nuevas. Empieza AL FINAL (como `tail -n0 -F`) y sigue rotaciones."""
    f = None
    inode = None
    while True:
        try:
            if f is None:
                f = open(path, "r", errors="replace")
                f.seek(0, os.SEEK_END)
                inode = os.fstat(f.fileno()).st_ino
            line = f.readline()
            if line:
                yield line
                continue
            try:
                if os.stat(path).st_ino != inode or os.stat(path).st_size < f.tell():
                    f.close()
                    f = None
                    continue
            except OSError:
                pass
            yield None
        except OSError:
            if f:
                f.close()
            f = None
            yield None


def main():
    ap = argparse.ArgumentParser(description="espejo notify_push.txt -> Discord")
    ap.add_argument("--once", action="store_true", help="procesa la ultima linea y sale (prueba)")
    ap.add_argument("--replay", type=int, metavar="N",
                    help="publica las N ultimas lineas SALTANDO la ley de frescura (solo pruebas)")
    ap.add_argument("--dry-run", action="store_true", help="clasifica e imprime, no publica")
    a = ap.parse_args()

    hooks = W.load()
    if not hooks and not a.dry_run:
        print("discord_relay ROTO: sin webhooks (corre scripts/discord_webhooks.py)",
              file=sys.stderr)
        return 1
    universe = set(L.fleet_symbols()) | set(L.SPY_QQQ) | set(L.SEMIS)
    role_ids = {} if a.dry_run else load_role_ids()

    if a.replay or a.once:
        try:
            with open(FUNNEL, errors="replace") as f:
                lines = f.readlines()[-(a.replay or 1):]
        except OSError as e:
            print("no se puede leer %s: %s" % (FUNNEL, e), file=sys.stderr)
            return 1
        n = 0
        for line in lines:
            p = parse(line)
            if not p:
                continue
            _, title, body = p
            ch, sev, mirrors = route(title, body, universe)
            if a.dry_run:
                print("%-22s %-9s %-40s %s" % ("#" + ch, sev, title[:40],
                                               ("espejo: " + ",".join(mirrors)) if mirrors else ""))
                n += 1
                continue
            emb = S.build_embed(title, body, sev, source="ib-trader · replay")
            ok, err = S.send(ch, emb, mention_role_id=None, hooks=hooks)
            print("#%-22s %s" % (ch, "OK" if ok else "FALLO: " + str(err)))
            n += 1
            time.sleep(0.5)
        print("%d lineas procesadas" % n)
        return 0

    print("discord_relay: siguiendo %s -> %d canales" % (FUNNEL, len(hooks)))
    log("arranque: %d webhooks, %d roles" % (len(hooks), len(role_ids)))
    dedup = {}
    estado = {"lastsent": 0.0, "cola": []}
    for line in follow(FUNNEL):
        if line is None:
            drenar(estado, role_ids, hooks)            # la rafaga se vacia aunque no llegue nada
            time.sleep(POLL_S)
            continue
        p = parse(line)
        if not p:
            continue
        age, title, body = p
        if age > BACKLOG_S or age < -60:
            continue                                  # relectura/arranque: ni log
        if age > FRESH_S:
            log("DESCARTADA (%ds vieja): %s" % (int(age), title[:50]))
            continue
        payload = title + " | " + body
        # PRIVACIDAD: nuestras operaciones jamas salen del Mac (solo banner/voz local).
        if L.is_private(payload):
            log("PRIVADA (solo local): %s" % title[:50])
            continue
        now = time.time()
        if now - dedup.get(payload, 0) < DEDUP_S:
            log("DEDUP (%ds): %s" % (DEDUP_S, title[:50]))   # antes moria en silencio
            continue
        # TODO 32: dedup SOLO tras pasar el cap — un capado debe poder reenviarse en <60s.
        dedup[payload] = now
        if len(dedup) > 500:
            dedup = {k: v for k, v in dedup.items() if now - v < DEDUP_S * 4}
        ch, sev, mirrors = route(title, body, universe)
        emb = S.build_embed(title, body, sev, source="ib-trader")
        item = {"ts": now, "ch": ch, "sev": sev, "emb": emb, "mirrors": mirrors,
                "title": title}
        if PRIORIDAD.search(payload) or (now - estado["lastsent"] >= CAP_S
                                         and not estado["cola"]):
            enviar(item, role_ids, hooks)
            estado["lastsent"] = now
        else:
            # CAP: NO se tira. Se encola y sale agrupada en el siguiente hueco (multi-embed).
            estado["cola"].append(item)
            if len(estado["cola"]) > COLA_MAX:
                muerta = estado["cola"].pop(0)
                log("COLA LLENA, perdida: %s" % muerta["title"][:50])
        drenar(estado, role_ids, hooks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
