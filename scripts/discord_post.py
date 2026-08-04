#!/usr/bin/env python3
"""discord_post.py — publicador de UN disparo: planes, arboles, estrategias, informes.

Lo que el relé NO cubre: los PDFs y textos que se generan por lote (los planes de las 04:00,
los arboles de horizonte, el post-mortem de cierre, los informes de backtest). El relé sigue
alertas vivas; esto publica documentos.

  discord_post.py --plans                       # PDFs del dia -> #planes-premarket
  discord_post.py --trees                       # arboles de horizonte -> #arboles-escenarios
  discord_post.py --guide                       # regenera #guia-alertas desde discord_layout
  discord_post.py --status                      # salud de la flota -> #estado-flota
  discord_post.py --channel backtests --file docs/X.md --caption "..."
  discord_post.py --channel estrategias --title "Plan MU" --text "..."
"""
import argparse
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_layout as L           # noqa: E402
import discord_send as S             # noqa: E402
import discord_webhooks as W         # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOY = os.environ.get("IBT_DESKTOP_HOY", os.path.expanduser("~/Desktop/ib-trader/hoy"))
TREES = os.path.join(REPO, "data", "trees_horizonte")


def plans_dir(day=None):
    """Carpeta de planes del dia. None si no existe: no se inventa una vacia."""
    day = day or time.strftime("%Y-%m-%d")
    d = os.path.join(HOY, "planes-" + day)
    return d if os.path.isdir(d) else None


def latest_plans_dir():
    dirs = sorted(glob.glob(os.path.join(HOY, "planes-*")))
    return dirs[-1] if dirs else None


def post_files(channel, paths, caption_fmt, hooks):
    """Sube fichero a fichero (Discord no acepta un lote grande). Devuelve (ok, fallos)."""
    ok = 0
    fails = []
    for p in paths:
        cap = caption_fmt % os.path.basename(p)
        good, err = S.send_file(channel, p, content=cap, hooks=hooks)
        if good:
            ok += 1
        else:
            fails.append((os.path.basename(p), err))
        time.sleep(0.6)
    return ok, fails


def cmd_plans(a, hooks):
    d = plans_dir(a.day) or (latest_plans_dir() if a.latest else None)
    if not d:
        print("sin carpeta de planes para %s en %s" % (a.day or "hoy", HOY), file=sys.stderr)
        return 1
    pdfs = sorted(glob.glob(os.path.join(d, "*_plan.pdf")))
    arboles = sorted(glob.glob(os.path.join(d, "ARBOLES_*.pdf")))
    if not pdfs and not arboles:
        print("carpeta %s sin PDFs" % d, file=sys.stderr)
        return 1
    day = os.path.basename(d).replace("planes-", "")
    S.send("planes-premarket",
           S.build_embed("📄 Planes del %s" % day,
                         "%d planes por ticker%s. Cada uno: mapa de muros/griegas, árbol de "
                         "escenarios y plan pícaro." % (
                             len(pdfs), " + %d hojas de árboles" % len(arboles) if arboles else ""),
                         L.NORMAL, source="daily_fleet_plans.py"), hooks=hooks)
    ok, fails = post_files("planes-premarket", pdfs + arboles, "`%s`", hooks)
    print("planes: %d/%d subidos desde %s" % (ok, len(pdfs) + len(arboles), d))
    for name, err in fails:
        print("  FALLO %s: %s" % (name, err), file=sys.stderr)
    return 0 if not fails else 1


def cmd_trees(a, hooks):
    pdfs = sorted(glob.glob(os.path.join(TREES, "*.pdf")))
    if not pdfs:
        print("sin árboles en %s" % TREES, file=sys.stderr)
        return 1
    edad_h = (time.time() - max(os.path.getmtime(p) for p in pdfs)) / 3600.0
    S.send("arboles-escenarios",
           S.build_embed("🌳 Árboles de horizonte",
                         "%d árboles (mañana / viernes / 2 semanas). Más reciente: hace %.1f h."
                         % (len(pdfs), edad_h)
                         + ("\n⚠️ **RANCIOS** — más de 24 h; regenera antes de operar con ellos."
                            if edad_h > 24 else ""),
                         L.NORMAL if edad_h <= 24 else L.SISTEMA,
                         source="adhoc_horizon_trees.py"), hooks=hooks)
    ok, fails = post_files("arboles-escenarios", pdfs, "`%s`", hooks)
    print("árboles: %d/%d subidos (antigüedad %.1f h)" % (ok, len(pdfs), edad_h))
    for name, err in fails:
        print("  FALLO %s: %s" % (name, err), file=sys.stderr)
    return 0 if not fails else 1


def guide_text():
    """La guia se DERIVA del router: si cambia el enrutado, la guia cambia sola."""
    out = ["**Cómo se lee esta sala**", "",
           "Todo lo que ves aquí sale del mismo embudo que la voz y las notificaciones del "
           "Mac (`data/notify_push.txt`): si sonó en casa, está aquí.",
           "Leyes heredadas del relé de ntfy, medidas, no opinadas:",
           "· alerta con más de **45 s** = no se publica (una alerta tardía miente)",
           "· payload idéntico en **60 s** = una sola vez",
           "· tope **1 cada 5 s**, salvo SELL/STOP/TERREMOTO/DANGER que lo saltan",
           "· lo de infraestructura (sockets, cintas ciegas) va a #estado-proveedores, "
           "no a los canales de alerta", "",
           "**Qué va a cada canal**", ""]
    seen = []
    for pat, ch, sev in L.RULES:
        legible = (pat.replace(r"\b", "").replace("|", " · ").replace(r"\s", " ")
                   .replace("(?i)", "").replace("?", ""))
        seen.append("`#%s` %s— %s" % (ch, "🚨 " if sev == L.CRITICA else
                                      ("⚙️ " if sev == L.SISTEMA else ""), legible[:150]))
    out += seen
    out += ["", "`#%s` — lo que ninguna regla reconoció. Si crece, falta una regla."
            % L.FALLBACK_CHANNEL,
            "", "**Espejos por símbolo**",
            "· `#spy-qqq`: " + " ".join(L.SPY_QQQ),
            "· `#semis-memoria`: " + " ".join(L.SEMIS), "",
            "**Lo que esta sala NO hace**: no ejecuta órdenes. La flota es SEÑAL-SOLAMENTE; "
            "el motor de órdenes vive aparte y con doble llave. No es consejo financiero."]
    return "\n".join(out)


def cmd_guide(a, hooks):
    ok, err = S.send_long("guia-alertas", "📖 Guía de alertas (autogenerada)",
                          guide_text(), L.NORMAL, source="discord_layout.py", hooks=hooks)
    print("guía: %s" % ("publicada" if ok else "FALLO: %s" % err))
    return 0 if ok else 1


def cmd_status(a, hooks):
    """Salud de la flota via fleet_up.sh --status. Si el script falla, se dice; no se finge OK."""
    script = os.path.join(REPO, "scripts", "fleet_up.sh")
    if not os.path.isfile(script):
        print("no existe %s" % script, file=sys.stderr)
        return 1
    try:
        p = subprocess.run(["zsh", script, "--status"], cwd=REPO, capture_output=True,
                           text=True, timeout=120)
        txt = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        txt = "fleet_up.sh --status NO RESPONDIÓ en 120 s"
    except OSError as e:
        txt = "fleet_up.sh --status no se pudo ejecutar: %s" % e
    ok, err = S.send_long("estado-flota", "🩺 Estado de la flota", "```\n%s\n```" % txt.strip(),
                          L.SISTEMA, source="fleet_up.sh --status", hooks=hooks)
    print("estado: %s" % ("publicado" if ok else "FALLO: %s" % err))
    return 0 if ok else 1


def cmd_manual(a, hooks):
    if a.channel not in L.webhook_channels():
        print("canal '%s' no publicable. Válidos: %s"
              % (a.channel, ", ".join(sorted(L.webhook_channels()))), file=sys.stderr)
        return 1
    if a.file:
        path = a.file if os.path.isabs(a.file) else os.path.join(REPO, a.file)
        if path.lower().endswith((".md", ".txt")) and os.path.getsize(path) < 200000:
            with open(path, errors="replace") as f:
                body = f.read()
            ok, err = S.send_long(a.channel, a.title or os.path.basename(path), body,
                                  L.NORMAL, source=a.caption or "ib-trader", hooks=hooks)
        else:
            ok, err = S.send_file(a.channel, path, content=a.caption or ("`%s`"
                                  % os.path.basename(path)), hooks=hooks)
        print("#%s %s" % (a.channel, "OK" if ok else "FALLO: %s" % err))
        return 0 if ok else 1
    if a.text:
        ok, err = S.send_long(a.channel, a.title or "ib-trader", a.text, L.NORMAL,
                              source=a.caption or "ib-trader", hooks=hooks)
        print("#%s %s" % (a.channel, "OK" if ok else "FALLO: %s" % err))
        return 0 if ok else 1
    print("nada que publicar: usa --text o --file", file=sys.stderr)
    return 1


def main():
    ap = argparse.ArgumentParser(description="publica documentos en Discord")
    ap.add_argument("--plans", action="store_true", help="PDFs de planes del día")
    ap.add_argument("--trees", action="store_true", help="árboles de horizonte")
    ap.add_argument("--guide", action="store_true", help="regenera la guía de alertas")
    ap.add_argument("--status", action="store_true", help="salud de la flota")
    ap.add_argument("--day", help="YYYY-MM-DD para --plans")
    ap.add_argument("--latest", action="store_true", help="con --plans: usa la carpeta más reciente")
    ap.add_argument("--channel", help="canal destino para --text/--file")
    ap.add_argument("--title")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--caption")
    a = ap.parse_args()

    hooks = W.load()
    if not hooks:
        print("discord_post ROTO: sin webhooks (corre scripts/discord_webhooks.py)",
              file=sys.stderr)
        return 1
    rc = 0
    hecho = False
    for flag, fn in (("plans", cmd_plans), ("trees", cmd_trees),
                     ("guide", cmd_guide), ("status", cmd_status)):
        if getattr(a, flag):
            rc |= fn(a, hooks)
            hecho = True
    if a.channel:
        rc |= cmd_manual(a, hooks)
        hecho = True
    if not hecho:
        ap.print_help()
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
