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

PRIORIDAD = re.compile(r"SELL|STOP|TERREMOTO|DANGER|🌋|🚨", re.IGNORECASE)
LINE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}) \| (.*?) \| (.*)$")


def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX:
            with open(LOG) as f:
                keep = f.readlines()[-2000:]
            with open(LOG, "w") as f:
                f.writelines(keep)
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), dc.redact(msg)))
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
    lastsent = 0.0
    for line in follow(FUNNEL):
        if line is None:
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
            continue
        prioritaria = bool(PRIORIDAD.search(payload))
        if now - lastsent < CAP_S and not prioritaria:
            log("CAP 1/%ds: %s" % (CAP_S, title[:50]))
            continue
        # TODO 32: dedup SOLO tras pasar el cap — un capado debe poder reenviarse en <60s.
        dedup[payload] = now
        if len(dedup) > 500:
            dedup = {k: v for k, v in dedup.items() if now - v < DEDUP_S * 4}
        lastsent = now
        ch, sev, mirrors = route(title, body, universe)
        emb = S.build_embed(title, body, sev, source="ib-trader")
        ok, err = S.send(ch, emb, mention_id(role_ids, sev), hooks=hooks)
        if not ok:
            log("FALLO #%s: %s | %s" % (ch, err, title[:50]))
            continue
        log("ENVIADA #%s [%s] %s" % (ch, sev, title[:50]))
        for m in mirrors:
            mok, merr = S.send(m, emb, hooks=hooks)
            if not mok:
                log("FALLO espejo #%s: %s" % (m, merr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
