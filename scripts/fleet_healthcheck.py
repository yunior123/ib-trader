#!/usr/bin/env python
"""fleet_healthcheck.py — verificador diario de que TODO este vivo: flota de bots,
posters X, alarmas, notificaciones, relay, launchd, frescura de datos, cobertura de
la flota (que nadie quede atras), y presupuesto X. Reporta por email + notificacion,
GRITA si algo critico esta caido, y se AUTO-CURA (revive relay/x_signal si mueren).

Uso: ./venv/bin/python scripts/fleet_healthcheck.py [--no-email] [--no-heal]
Programado por launchd com.ibtrader.healthcheck (diario). SEÑAL-SOLAMENTE.

CONTRATO DE SALIDA: exit 0 si no hay 🔴 (aunque haya avisos 🟡), exit 2 si hay 🔴.
Antes salia 1 con cualquier aviso: launchd lo grababa como job FALLIDO y la corrida
siguiente leia su propio LastExitStatus=1, lo cantaba como aviso nuevo y se
realimentaba — nunca podia volver a verde. Ademas se EXCLUYE del audit de exit codes
de launchd (self_label() lo lee del plist, no hardcodeado)."""
import argparse, json, os, plistlib, subprocess, sys, time, warnings
warnings.filterwarnings("ignore")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))   # em_envelope: tabla de festivos real
SELF_PATH = os.path.abspath(__file__)
LAUNCHAGENTS = os.path.expanduser("~/Library/LaunchAgents")
CRITICAL_JOBS = ("com.ibtrader.dailyplans", "com.ibtrader.postmortem")
os.chdir(REPO)

def env(k):
    """Valor de `k` en feeds.env, o None si no existe la clave o el fichero.
    Cualquier otro error de E/S LEVANTA: 'ilegible' no se disfraza de 'sin clave'."""
    p = os.path.join(REPO, "feeds.env")
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        for ln in fh:
            if ln.startswith(k + "="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def proc_alive(pat):
    return subprocess.run(["pgrep", "-f", pat], capture_output=True).returncode == 0

def count_proc(pat):
    r = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True)
    return len([x for x in r.stdout.split() if x])

def launchd_state():
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    out = {}
    for ln in r.stdout.splitlines():
        if "ibtrader" in ln:
            p = ln.split()
            if len(p) >= 3: out[p[2]] = p[1]  # label -> last exit
    return out

def self_label(agents_dir=LAUNCHAGENTS, me=SELF_PATH):
    """Label launchd de ESTE script, LEIDO del plist que lo invoca (jamas hardcodeado:
    si se renombra el job, esto lo sigue). None si no aparece en ningun plist —
    nunca una cadena inventada, que excluiria del audit al job de otro."""
    if not os.path.isdir(agents_dir):
        return None
    for fn in sorted(os.listdir(agents_dir)):
        if not fn.endswith(".plist"):
            continue
        path = os.path.join(agents_dir, fn)
        try:
            with open(path, "rb") as fh:
                pl = plistlib.load(fh)
        except (OSError, ValueError, plistlib.InvalidFileException) as e:
            print(f"aviso: plist ilegible {fn}: {e}")  # fail-loud, nunca silencio
            continue
        args = [x for x in (pl.get("ProgramArguments") or []) if isinstance(x, str)]
        if any(os.path.abspath(x) == me for x in args):
            lbl = pl.get("Label")
            if isinstance(lbl, str) and lbl:
                return lbl
    return None

def audit_launchd(ld, me_label):
    """Clasifica los exit codes de launchd -> (ok, warn, crit).
    `me_label` (nuestro propio job) se EXCLUYE: un healthcheck no puede auditar su
    propia corrida — solo ve el LastExitStatus de la ANTERIOR, se lo canta como aviso
    nuevo y se realimenta. Ese era el bucle del 2026-07-25."""
    ok, warn, crit = [], [], []
    for job in CRITICAL_JOBS:
        if job in ld:
            (ok if ld[job] in ("0", "-") else warn).append(f"launchd {job}: exit {ld[job]}")
        else:
            crit.append(f"launchd {job}: NO CARGADO")
    # resto de jobs de la flota con exit!=0 (aviso, no critico — pre-existente)
    for job, ex in sorted(ld.items()):
        if job in CRITICAL_JOBS or (me_label is not None and job == me_label):
            continue
        if ex not in ("0", "-"):
            warn.append(f"launchd {job}: exit {ex} (revisar config)")
    return ok, warn, crit

def exit_code(crit, warn):
    """CONTRATO DE SALIDA (fix 2026-07-25): non-zero SOLO con 🔴 real.
    Los avisos 🟡 salen 0: launchd trata cualquier non-zero como job FALLIDO, lo graba
    en LastExitStatus (y puede throttlear), y este mismo script lo leia en la corrida
    siguiente y lo reportaba como aviso nuevo — nunca podia volver a verde.
    Un healthcheck que informa de avisos no ha fallado; uno que ve un 🔴 si."""
    del warn  # deliberadamente IGNORADO: un aviso 🟡 no es un fallo del job
    return 2 if crit else 0

def sessions_since(epoch):
    """Cuantas SESIONES DE MERCADO han abierto desde `epoch` (dias de mercado estrictamente
    posteriores a la fecha de la captura y no posteriores a hoy).

    Un snapshot del cierre del viernes leido el sabado devuelve 0: no le falta ninguna
    sesion, aunque el reloj de pared diga 60h. Reutiliza la tabla de festivos real de
    em_envelope.is_market_day, que LEVANTA si se le pide una fecha fuera de tabla — asi que
    aqui se traduce a None ("no se puede contar") y quien llama lo canta. Nunca 0 fingido.
    """
    import datetime as dt
    try:
        import em_envelope
    except ImportError:
        return None
    d0 = dt.datetime.fromtimestamp(epoch).date()
    hoy = dt.date.today()
    n = 0
    d = d0 + dt.timedelta(days=1)
    while d <= hoy:
        try:
            if em_envelope.is_market_day(d):
                n += 1
        except Exception:
            return None
        d += dt.timedelta(days=1)
    return n


def poly_chains_today():
    """Cuantas cadenas de Polygon con griegas REALES se han archivado HOY (poly_chain_archive).
    Es la alternativa MEDIDA a gexa: gamma + OI de verdad, de los que gex_core saca
    flip/regimen/muros sin depender de scraping. Devuelve un entero (0 si no hay carpeta)."""
    import datetime as dt
    import glob
    d = os.path.join(REPO, "data", "history", dt.date.today().isoformat())
    if not os.path.isdir(d):
        return 0
    return len(glob.glob(os.path.join(d, "chain_full_*.json")))


def market_hours():
    lt = time.localtime()
    return lt.tm_wday < 5 and 930 <= lt.tm_hour*100+lt.tm_min < 1600

def premarket_or_session():
    lt = time.localtime()
    return lt.tm_wday < 5 and 400 <= lt.tm_hour*100+lt.tm_min < 1600

def heal(name, keepalive):
    """Revive un daemon via su keepalive si esta muerto. Idempotente."""
    if not proc_alive(keepalive):
        try:
            subprocess.Popen(["nohup", "zsh", f"scripts/{keepalive}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"{name}: REVIVIDO"
        except Exception as e:
            return f"{name}: fallo revivir ({e})"
    return None

def canonical_fleet():
    """Flota canonica de data/fleet.txt, o None si no se puede leer.
    None != set() a proposito: un conjunto vacio saltaba los checks de cobertura en
    silencio (guarda muerta). None obliga a cantarlo."""
    p = os.path.join(REPO, "data", "fleet.txt")
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        syms = set(fh.read().split())
    return syms or None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--no-heal", action="store_true")
    a = ap.parse_args()
    ok, warn, crit, healed = [], [], [], []
    now = time.strftime("%Y-%m-%d %H:%M ET")

    # 1) launchd jobs criticos (excluyendo nuestro propio job: ver audit_launchd)
    ld = launchd_state()
    me_label = self_label()
    if me_label is None:
        warn.append("launchd: no encuentro mi propio plist en ~/Library/LaunchAgents "
                    "(no puedo excluirme del audit de exit codes)")
    lok, lwarn, lcrit = audit_launchd(ld, me_label)
    ok += lok; warn += lwarn; crit += lcrit

    # 2) daemons criticos (con auto-cura)
    checks = [
        ("notify_relay (notificaciones)", "scripts/notify_relay.sh", "notify_relay.sh", True),
        ("x_signal_poster (X realtime)", "scripts/x_signal_poster.py", "x_signal_keepalive.sh", True),
    ]
    for name, pat, ka, critical in checks:
        if proc_alive(pat):
            ok.append(f"{name}: vivo")
        else:
            (crit if critical else warn).append(f"{name}: MUERTO")
            if not a.no_heal:
                h = heal(name, ka)
                if h: healed.append(h)

    # 3) feed de datos + bots (solo critico en horario de mercado/premarket)
    bridge = proc_alive("ibkr_bar_bridge.py")
    bots = count_proc("signal_bot")
    if premarket_or_session():
        if not bridge and not a.no_heal:
            try:
                subprocess.Popen(["nohup", "zsh", "scripts/fleet_keepalive_start.sh"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(4); bridge = proc_alive("ibkr_bar_bridge.py"); bots = count_proc("signal_bot")
                healed.append(f"flota: relanzada (bridge {'vivo' if bridge else 'aun no'}, {bots} bots)")
            except Exception as e:
                crit.append(f"flota: fallo relanzar ({e})")
        (ok if bridge else crit).append(f"bar_bridge (feed IBKR): {'vivo' if bridge else 'MUERTO en horario activo'}")
        (ok if bots >= 1 else warn).append(f"signal bots: {bots} vivos")
    else:
        ok.append(f"bar_bridge {'vivo' if bridge else 'dormido (fuera de horario, normal)'} | bots {bots}")
    ow = proc_alive("opt_whale_watch")
    (ok if (ow or not market_hours()) else warn).append(f"opt_whale (ballenas opciones): {'vivo' if ow else 'muerto'}")

    # 4) frescura de salidas del dia
    today = time.strftime("%Y-%m-%d")
    pdir = os.path.expanduser(f"~/Desktop/planes-{today}")
    # TCC macOS puede vetar Desktop a launchd (PermissionError 2026-07-22):
    # degradacion limpia — npdf=-1 = "no pude mirar", no un CRIT falso.
    try:
        npdf = len([f for f in os.listdir(pdir) if f.endswith(".pdf")]) if os.path.isdir(pdir) else 0
    except PermissionError:
        npdf = -1
    lt = time.localtime()
    if lt.tm_hour >= 5:  # tras el run FULL de 4am
        if npdf < 0:
            warn.append("planes de hoy: Desktop vetado por TCC (dar Full Disk Access al runner) — no pude contar PDFs")
        else:
            (ok if npdf >= 20 else crit).append(f"planes de hoy: {npdf} PDFs {'(el run de 4am fallo?)' if npdf<20 else ''}")
    # FRESCURA DE VERDAD (fix 2026-07-24): este bucle declaraba un umbral `age` por
    # archivo y NO LO USABA — solo miraba os.path.exists, asi que un JSON de hace
    # semanas salia "ok". Guarda muerta, el mismo olor que ya cazamos en
    # index_breadth.py y en el verify de gexa de dailyplans_run.sh.
    for jf, age, lbl in [("data/patterns.json", 36*3600, "patrones"),
                         ("data/breadth.json", 24*3600, "engranaje"),
                         ("data/calibration.json", 30*24*3600, "calibracion")]:
        if not os.path.exists(jf):
            warn.append(f"{lbl}: FALTA")
            continue
        edad = time.time() - os.path.getmtime(jf)
        if edad > age:
            warn.append(f"{lbl}: RANCIO {edad/3600:.0f}h (umbral {age/3600:.0f}h)")
        else:
            ok.append(f"{lbl}: ok ({edad/3600:.0f}h)")

    # 5) gexa conecto Y esta fresco? (el 2026-07-24 llevaba 58h rancio y decia "ok":
    # dos dias de planes con GEX estimado, en silencio, con el healthcheck en verde)
    #
    # PERO el reloj de pared miente en fin de semana: un snapshot del cierre del viernes
    # leido el sabado son "60h rancio" y no le falta NI UNA sesion. Lo que importa no son
    # las horas, son las SESIONES DE MERCADO que han abierto desde la captura (2026-07-25).
    gf = "data/gexa_snapshot.json"
    if not (os.path.exists(gf) and os.path.getsize(gf) > 5):
        warn.append("gexa snapshot: no conecto (usa GEX estimado)")
    else:
        gedad = time.time() - os.path.getmtime(gf)
        faltan = sessions_since(os.path.getmtime(gf))
        # Y el coste de un gexa viejo depende de si hay ALTERNATIVA MEDIDA: desde que
        # poly_chain_archive guarda las cadenas con griegas REALES de Polygon, el fallback
        # ya no es "GEX estimado" — se calcula con gex_core sobre gamma+OI de verdad.
        poly_n = poly_chains_today()
        alt = (f"cadenas Polygon con griegas REALES hoy: {poly_n}/{len(canonical_fleet() or [])}"
               if poly_n else "sin cadenas Polygon hoy: los planes usan GEX estimado")
        if faltan is None:
            warn.append(f"gexa snapshot: {gedad/3600:.0f}h y no se pueden contar sesiones "
                        f"(tabla de festivos agotada) — {alt}")
        elif faltan == 0:
            ok.append(f"gexa snapshot: ok ({gedad/3600:.0f}h, 0 sesiones perdidas — "
                      f"mercado cerrado desde la captura)")
        elif poly_n:
            # informativo: le faltan sesiones, pero el mapa gamma no depende de gexa
            ok.append(f"gexa snapshot: {faltan} sesion(es) por detras ({gedad/3600:.0f}h) — "
                      f"NO bloquea: {alt}")
        else:
            warn.append(f"gexa snapshot: RANCIO {faltan} sesion(es) ({gedad/3600:.0f}h) — {alt}")

    # 6) cobertura: cada modulo cubre la flota canonica?
    canon = canonical_fleet()
    if canon is None:
        crit.append("data/fleet.txt: ILEGIBLE o VACIA — sin flota canonica no hay cobertura que medir")
    else:
        gen = None
        gpath = os.path.join(REPO, "scripts", "daily_fleet_plans.py")
        try:
            import re
            with open(gpath) as fh:
                gen = set(re.findall(r'"([A-Z]+)":\s*dict', fh.read()))
        except OSError as e:
            # jamas gen=set(): eso fabricaba "cobertura 0/30 FALTAN <toda la flota>",
            # un 🟡 inventado que tapaba el fallo real (no pude leer el generador).
            warn.append(f"cobertura generador: NO PUDE LEER {gpath} ({e})")
        if gen is not None:
            missing = canon - gen
            (ok if not missing else warn).append(f"cobertura generador: {len(gen)}/{len(canon)}" + (f" FALTAN {missing}" if missing else ""))
        # skills
        sk = set(x.replace("ticker-", "").upper() for x in os.listdir(os.path.expanduser("~/.claude/skills")) if x.startswith("ticker-"))
        smiss = canon - sk
        (ok if not smiss else warn).append(f"skills ticker: {len(sk & canon)}/{len(canon)}" + (f" FALTAN {smiss}" if smiss else ""))

    # 7) presupuesto X
    try:
        with open(os.path.join(REPO, "data", "x_plan_budget.json")) as fh:
            b = json.load(fh)
        spent = b.get("spent")  # sin clave -> "?" ; jamas $0.00 inventado
        ok.append(f"X ledger: {b.get('posts','?')} posts, "
                  f"{'$%.2f' % spent if isinstance(spent, (int, float)) else '$?'} gastados este mes")
    except (OSError, ValueError) as e:
        warn.append(f"X ledger: no leible ({e})")

    # 8) email/Resend configurado
    (ok if env("RESEND_KEY") and env("RESEND_TO") else crit).append(
        f"Resend email: {'configurado' if env('RESEND_KEY') else 'SIN KEY'}")

    # --- reporte ---
    status = "🔴 CRITICO" if crit else ("🟡 AVISOS" if warn else "🟢 TODO OK")
    lines = [f"HEALTHCHECK ib-trader {now} — {status}", "="*50]
    if healed: lines += ["AUTO-CURADO:"] + [f"  ✅ {h}" for h in healed]
    if crit: lines += ["CRITICO:"] + [f"  🔴 {c}" for c in crit]
    if warn: lines += ["AVISOS:"] + [f"  🟡 {w}" for w in warn]
    lines += ["OK:"] + [f"  🟢 {o}" for o in ok]
    rc = exit_code(crit, warn)
    lines += [f"SALIDA: exit {rc} ({'FALLO DURO' if rc else 'job OK'}) — "
              f"{len(crit)} crit / {len(warn)} avisos"
              + ("" if me_label is None else f" | mi label launchd: {me_label} (excluido del audit)")]
    report = "\n".join(lines)
    print(report)
    with open(os.path.join(REPO, "healthcheck.log"), "a") as f:
        f.write(f"\n{report}\n")

    # notificacion Mac (siempre) + email (si critico o avisos, o diario)
    subprocess.Popen(["osascript", "-e",
        f'display notification "{status}: {len(crit)} crit, {len(warn)} avisos, {len(healed)} curados" with title "🩺 ib-trader healthcheck"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not a.no_email and env("RESEND_KEY"):
        try:
            import requests
            subj = f"{status} Healthcheck ib-trader {today}"
            requests.post("https://api.resend.com/emails", timeout=20,
                headers={"Authorization": f"Bearer {env('RESEND_KEY')}", "Content-Type": "application/json"},
                json={"from": "onboarding@resend.dev", "to": [env("RESEND_TO")],
                      "subject": subj, "text": report})
        except Exception as e:
            print("email fallo:", e)
    return rc

if __name__ == "__main__":
    import sys; sys.exit(main())
