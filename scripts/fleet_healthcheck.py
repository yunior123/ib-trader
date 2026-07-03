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
import argparse, hashlib, json, os, plistlib, subprocess, sys, time, warnings

import os as _os  # portero de banners
_OSA = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "osa_gate")  # respeta data/notify_off
warnings.filterwarnings("ignore")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))   # em_envelope: tabla de festivos real
SELF_PATH = os.path.abspath(__file__)
LAUNCHAGENTS = os.path.expanduser("~/Library/LaunchAgents")
HEALTH_EMAIL_STATE = os.path.join(REPO, "data", "healthcheck_email_state.json")
CRITICAL_JOBS = ("com.ibtrader.dailyplans", "com.ibtrader.postmortem")
SESSION_PROBE_JOBS = ("com.ibtrader.intrinioprobe", "com.ibtrader.uwlatency")
os.chdir(REPO)

def env(k):
    """Valor de `k` en feeds.env, o None si no existe la clave o el fichero.
    Cualquier otro error de E/S LEVANTA: 'ilegible' no se disfraza de 'sin clave'."""
    p = os.path.join(REPO, "config", "feeds.env")
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        for ln in fh:
            if ln.startswith(k + "="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def _pgrep(pat):
    """PIDs que casan `pat`. `-a` porque el pgrep de macOS EXCLUYE por defecto al invocante y a
    TODOS sus ancestros (medido 2026-08-03: `pgrep -f x.py` desde dentro de x.py devuelve vacio,
    `pgrep -a -f x.py` devuelve sus pids) — un monitor no puede tener un punto ciego con su
    propio arbol. Se lee solo el primer campo numerico por linea (en Linux `-a` añade el cmdline).
    Un fallo de pgrep LEVANTA: "no puedo mirar" no es "no hay".
    """
    r = subprocess.run(["pgrep", "-a", "-f", pat], capture_output=True, text=True)
    if r.returncode not in (0, 1):
        raise RuntimeError("pgrep -a -f %r fallo (rc=%d): %s" % (pat, r.returncode, r.stderr.strip()[:120]))
    out = []
    for ln in r.stdout.splitlines():
        tok = ln.split(None, 1)[0] if ln.strip() else ""
        if tok.isdigit():
            out.append(tok)
    return out


def proc_alive(pat):
    return bool(_pgrep(pat))


def pgrep_ciego():
    """True si `pgrep` no ve NI a launchd (pid 1): vista de procesos ciega, no vacia.

    Medido 2026-08-03: corridas desde un entorno aislado dieron notify_relay/x_signal_poster
    "MUERTO" + 🔴 CRITICO y heals que morian con exit 127, mientras `pgrep` desde una shell
    normal los encontraba VIVOS (pids 95547/95972). 222 lineas de ese falso critico en
    logs/healthcheck.log desde 2026-07-26. "No puedo ver" no es "esta muerto".
    """
    try:
        return not _pgrep("launchd")
    except (RuntimeError, OSError):
        return True

def count_proc(pat):
    return len(_pgrep(pat))

def launchd_state():
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    out = {}
    for ln in r.stdout.splitlines():
        if "ibtrader" in ln:
            p = ln.split()
            if len(p) >= 3: out[p[2]] = p[1]  # label -> last exit
    return out


GATE_MARCAS = ("fleet_hours", "date +%H%M", "date +%H%M%S")


def gated_jobs(agents_dir=LAUNCHAGENTS):
    """Labels cuyo PROPIO comando lleva un portero horario -> su exit 1 es el portero
    diciendo "fuera de ventana", no un fallo.

    Se DERIVA del plist (como self_label), jamas una lista de nombres a mano: si mañana
    otro job se pone su portero, este audit lo respeta solo. Marcas buscadas en
    ProgramArguments: `./bin/fleet_hours` (el portero de la casa) o un `date +%H%M` usado
    como guarda (`H=$(date +%H%M) && [ "$H" -ge 0935 ] ...`).

    Medido 2026-08-03 07:00: com.ibtrader.polychains.intraday y com.ibtrader.tracecube
    salian 1 por su propia guarda horaria y el healthcheck los cantaba
    "exit 1 (revisar config)" en cada corrida. Crying-wolf sobre el comportamiento correcto.
    Solo se excusa el exit 1: cualquier otro codigo sigue siendo aviso."""
    out = set()
    if not os.path.isdir(agents_dir):
        return out
    for fn in sorted(os.listdir(agents_dir)):
        if not fn.endswith(".plist"):
            continue
        try:
            with open(os.path.join(agents_dir, fn), "rb") as fh:
                pl = plistlib.load(fh)
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue          # self_label ya canta los plists ilegibles; no duplicar voz
        cmd = " ".join(x for x in (pl.get("ProgramArguments") or []) if isinstance(x, str))
        lbl = pl.get("Label")
        if isinstance(lbl, str) and lbl and any(m in cmd for m in GATE_MARCAS):
            out.add(lbl)
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

def audit_launchd(ld, me_label, gated=None, fleet_live=True):
    """Clasifica los exit codes de launchd -> (ok, warn, crit).
    `me_label` (nuestro propio job) se EXCLUYE: un healthcheck no puede auditar su
    propia corrida — solo ve el LastExitStatus de la ANTERIOR, se lo canta como aviso
    nuevo y se realimenta. Ese era el bucle del 2026-07-25.
    `gated` (ver gated_jobs): jobs con portero horario propio; su exit 1 es el portero,
    no un fallo — sale OK y no ensucia el informe."""
    gated = gated or set()
    ok, warn, crit = [], [], []
    # `launchctl list` sin NINGUN job de ib-trader, ni el nuestro, es vista CIEGA (otro dominio
    # de arranque / entorno aislado), no "todos descargados": 111 lineas de "NO CARGADO" falso
    # en logs/healthcheck.log mientras los jobs corrian (dailyplans dejo sus 30 PDFs de las 04:00).
    if not ld:
        return ok, ["launchd: VISTA CIEGA — launchctl no lista ni un job de ib-trader (ni el mio); "
                    "no declaro NO CARGADO a ciegas"], crit
    for job in CRITICAL_JOBS:
        if job in ld:
            (ok if ld[job] in ("0", "-") else warn).append(f"launchd {job}: exit {ld[job]}")
        else:
            crit.append(f"launchd {job}: NO CARGADO")
    # resto de jobs de la flota con exit!=0 (aviso, no critico — pre-existente)
    for job, ex in sorted(ld.items()):
        if job in CRITICAL_JOBS or (me_label is not None and job == me_label):
            continue
        if ex in ("0", "-"):
            continue
        if ex == "-15":
            ok.append(f"launchd {job}: terminado por SIGTERM/reinicio controlado")
        elif ex == "1" and job in gated:
            ok.append(f"launchd {job}: exit 1 = su propio portero horario (fuera de ventana, correcto)")
        elif ex == "1" and fleet_live is False and job in SESSION_PROBE_JOBS:
            ok.append(f"launchd {job}: exit 1 = probe sin sesión (fuera de ventana, correcto)")
        else:
            warn.append(f"launchd {job}: exit {ex} (ultima corrida fallo)")
    return ok, warn, crit

def parse_etime(s):
    """Segundos de `ps -o etime=` ([[DD-]HH:]MM:SS). None si no se puede leer — nunca 0,
    que se leeria como "acaba de arrancar" y taparia justo el proceso colgado."""
    s = (s or "").strip()
    if not s:
        return None
    dias, _, resto = s.rpartition("-")
    partes = resto.split(":")
    if not all(p.isdigit() for p in partes) or not 2 <= len(partes) <= 3:
        return None
    if dias and not dias.isdigit():
        return None
    seg = 0
    for p in partes:
        seg = seg * 60 + int(p)
    return seg + (int(dias) * 86400 if dias else 0)


def job_intervals(agents_dir=LAUNCHAGENTS):
    """label -> StartInterval (s) de los jobs periodicos. Derivado del plist."""
    out = {}
    if not os.path.isdir(agents_dir):
        return out
    for fn in sorted(os.listdir(agents_dir)):
        if not fn.endswith(".plist"):
            continue
        try:
            with open(os.path.join(agents_dir, fn), "rb") as fh:
                pl = plistlib.load(fh)
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        lbl, iv = pl.get("Label"), pl.get("StartInterval")
        if isinstance(lbl, str) and lbl and isinstance(iv, int) and iv > 0:
            out[lbl] = iv
    return out


def stuck_jobs(ld=None, intervals=None, edades=None, factor=3):
    """Jobs periodicos COLGADOS: llevan corriendo mas de `factor` x su StartInterval.

    launchd NO relanza un job mientras su instancia anterior siga viva, asi que un
    proceso colgado deja de correr para siempre SIN cambiar de exit code — el audit de
    exit codes es CIEGO a esto. Cazado el 2026-08-03 07:02: com.ibtrader.intrinioprobe
    (StartInterval 600) llevaba 3h06m en el mismo proceso y su log no escribia desde las
    03:45; el informe solo decia "exit 1". 18 sondas perdidas en silencio.

    `edades` inyectable (label -> segundos) para poder testear sin procesos reales."""
    del ld  # el PID se lee aqui de launchctl: `launchd_state` solo trae el exit code
    intervals = job_intervals() if intervals is None else intervals
    if edades is None:
        edades = {}
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            p = ln.split()
            if len(p) < 3 or "ibtrader" not in ln or not p[0].isdigit():
                continue
            ps = subprocess.run(["ps", "-o", "etime=", "-p", p[0]], capture_output=True, text=True)
            e = parse_etime(ps.stdout)
            if e is not None:
                edades[p[2]] = e
    avisos = []
    for lbl, edad in sorted(edades.items()):
        iv = intervals.get(lbl)
        if iv and edad > factor * iv:
            avisos.append(f"launchd {lbl}: COLGADO — {edad//60} min en la misma corrida "
                          f"(StartInterval {iv}s); launchd no lo relanza hasta que muera")
    return avisos


def exit_code(crit, warn):
    """CONTRATO DE SALIDA (fix 2026-07-25): non-zero SOLO con 🔴 real.
    Los avisos 🟡 salen 0: launchd trata cualquier non-zero como job FALLIDO, lo graba
    en LastExitStatus (y puede throttlear), y este mismo script lo leia en la corrida
    siguiente y lo reportaba como aviso nuevo — nunca podia volver a verde.
    Un healthcheck que informa de avisos no ha fallado; uno que ve un 🔴 si."""
    del warn  # deliberadamente IGNORADO: un aviso 🟡 no es un fallo del job
    return 2 if crit else 0


def health_email_due(crit, warn, today, path=HEALTH_EMAIL_STATE):
    """Un mismo diagnóstico se manda una vez al día; cambios reales se mandan al instante."""
    signature = hashlib.sha256(json.dumps(
        {"crit": sorted(crit), "warn": sorted(warn)}, ensure_ascii=False,
        sort_keys=True).encode("utf-8")).hexdigest()
    try:
        with open(path) as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = {}
    return old.get("date") != today or old.get("signature") != signature, signature


def mark_health_email_sent(today, signature, path=HEALTH_EMAIL_STATE):
    rec = {"date": today, "signature": signature, "sent_at": time.time()}
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rec, fh, sort_keys=True)
    os.replace(tmp, path)

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


def fuente_de_baja(nombre):
    """True si la fuente esta declarada de baja en data/fuentes_de_pago_baja.txt.
    Una baja decidida no es una averia: degrada el critico a aviso, no lo esconde."""
    try:
        p = _os.path.join(REPO, "data", "fuentes_de_pago_baja.txt")
        with open(p) as fh:
            for ln in fh:
                ln = ln.strip()
                if ln and not ln.startswith("#") and ln.lower() == nombre.lower():
                    return True
    except Exception:
        pass
    return False


def finviz_health_is_stale(path=None, now=None, max_age_s=12 * 3600):
    """PURA salvo el stat: True si hay que re-comprobar el token. Ausente o ilegible = True."""
    import time as _time
    p = path or os.path.join(REPO, "data", "finviz_auth_health.json")
    now = _time.time() if now is None else now
    try:
        return (now - os.path.getmtime(p)) > max_age_s
    except OSError:
        return True


def refresh_finviz_health(timeout=40):
    """Re-corre scripts/finviz_auth_check.py si el registro esta rancio. Best-effort:
    si falla, `finviz_token_status` lo vera rancio y avisara — jamas se finge frescura.

    SIN --quiet a proposito (bug real, TODOS.md "GRITAR cuando el token caduque"): ese
    flag es "para tests" (finviz_auth_check.py:38) y este es el UNICO caller automatico
    en produccion (cron 3x/dia). Pasarlo aqui silenciaba para siempre la voz DANGER/SIGNAL
    del propio script — la flota se quedaba ciega sin que sonara nada."""
    if not finviz_health_is_stale():
        return False
    try:
        subprocess.run(
            [os.path.join(REPO, "venv", "bin", "python"),
             os.path.join(REPO, "scripts", "finviz_auth_check.py")],
            cwd=REPO, timeout=timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except Exception:
        return False


def finviz_token_status(rec=None, path=None, now=None):
    """Veredicto del TOKEN de Finviz: ("crit"|"warn"|"ok", mensaje). Funcion PURA si se
    le pasa `rec` — por eso se puede testear sin red ni disco.

    Lee data/finviz_auth_health.json, que escribe scripts/finviz_auth_check.py. Reglas:
      - registro ausente o ilegible -> WARN "no se ha comprobado" (NO 'ok': no saber
        no es estar sano; y NO 'crit': puede que el chequeo aun no se haya instalado).
      - sano is False                -> CRIT (token caducado: la flota esta ciega).
      - sano is None                 -> WARN (no se pudo comprobar: sin red).
      - registro mas viejo de 48h    -> WARN (el chequeo dejo de correr).
      - sano con pocos dias por delante -> WARN con los dias que quedan.
    """
    import json as _json
    import time as _time
    p = path or os.path.join(REPO, "data", "finviz_auth_health.json")
    now = _time.time() if now is None else now
    if rec is None:
        try:
            with open(p) as fh:
                rec = _json.load(fh)
        except Exception as e:
            return "warn", (f"finviz token: SIN COMPROBAR ({e.__class__.__name__}) — "
                            f"corre scripts/finviz_auth_check.py")
    if not isinstance(rec, dict):
        return "warn", "finviz token: registro ilegible — sin comprobar"

    sano = rec.get("sano")
    cola = rec.get("token_cola") or "????"
    clave = rec.get("clave_efectiva") or "?"
    if sano is False:
        if fuente_de_baja("finviz"):
            return "warn", (f"finviz DADO DE BAJA ({clave}, ...{cola}): {rec.get('motivo')} — "
                            f"scout/valuation/x_bot ciegos POR DECISION, no por averia")
        return "crit", (f"🔴 finviz token CADUCADO ({clave}, ...{cola}): "
                        f"{rec.get('motivo')} — scout/valuation/x_bot CIEGOS, renovar")
    if sano is None:
        return "warn", f"finviz token: no se pudo comprobar ({rec.get('motivo')})"

    ts = rec.get("ts")
    if isinstance(ts, (int, float)) and now - ts > 48 * 3600:
        edad_h = (now - ts) / 3600
        return "warn", f"finviz token: el chequeo lleva {edad_h:.0f}h sin correr"

    dias = rec.get("dias_restantes")
    if isinstance(dias, int) and dias <= 2:
        cuando = (f"caducidad declarada hace {-dias} día(s)" if dias < 0
                  else f"caduca en {dias} día(s)")
        return "warn", f"finviz token responde sano pero {cuando} — renovar/verificar"
    extra = f", caduca en {dias} dias" if isinstance(dias, int) else ""
    return "ok", f"finviz token OK ({clave}, ...{cola}){extra}"


def gex_map_status(path=None, canon_n=None, poly_n=None):
    """Veredicto del MAPA GAMMA PROPIO: ("crit"|"warn"|"ok", mensaje).

    gexa.ai murio el 2026-07-25 y con el el scraping por Chrome: ya no hay nada que
    "conectar". Lo que se vigila es data/gex_snapshot.json, que gex_snapshot.py calcula
    desde las cadenas archivadas con griegas MEDIDAS de Polygon. Si ese fichero no esta,
    los planes se quedan SIN regimen gamma -> 🔴, no un aviso: fue exactamente el fallo
    que el 2026-07-24 estuvo dos dias en verde mientras los planes iban ciegos.
    Tambien 🔴 si la cobertura baja de la MITAD de la flota; 🟡 si solo le faltan simbolos
    o si esta rancio. Nunca se rellena un hueco con un numero plausible.

    El reloj de pared miente en fin de semana: un mapa del cierre del viernes leido el
    sabado son "60h" y no le falta NI UNA sesion, asi que la frescura se mide en SESIONES
    DE MERCADO (sessions_since), no en horas.
    Parametrizado para poder testearlo sin tocar el repo real."""
    if path is None:
        path = os.path.join(REPO, "data", "gex_snapshot.json")
    if canon_n is None:
        canon_n = len(canonical_fleet() or [])
    if not (os.path.exists(path) and os.path.getsize(path) > 5):
        return "crit", (f"mapa gamma ({os.path.basename(path)}): NO EXISTE — los planes se "
                        "quedan sin regimen gamma. Corre scripts/gex_snapshot.py DESPUES de "
                        "archivar las cadenas (poly_chain_archive.py)")
    import gex_snapshot              # fuente unica del contrato: filtra `_meta` y la edad
    gsyms = gex_snapshot.load(path=path)            # None si falta/roto, JAMAS {}
    meta, meta_roto = {}, None
    try:
        with open(path) as fh:
            meta = (json.load(fh) or {}).get("_meta") or {}
    except (OSError, ValueError) as e:
        meta_roto = f"`_meta` ilegible ({type(e).__name__})"
    n_ok = len(gsyms) if gsyms else 0
    if poly_n is None:
        poly_n = poly_chains_today()
    # Diagnostico de POR QUE cae la cobertura: sin cadenas archivadas no hay mapa.
    why = (f"cadenas Polygon con griegas REALES hoy: {poly_n}/{canon_n}" if poly_n
           else "sin cadenas Polygon archivadas hoy (poly_chain_archive no corrio?)")
    if n_ok == 0:
        return "crit", f"mapa gamma: 0 simbolos usables ({path} roto o vacio) — {why}"
    if canon_n and n_ok * 2 < canon_n:
        return "crit", (f"mapa gamma: cobertura {n_ok}/{canon_n}, por debajo de la MITAD de "
                        f"la flota — {why}")
    # frescura desde `_meta.asof`; si el mapa no lo trae se usa el mtime y se DICE cual de
    # los dos se midio (no se finge que la marca venia dentro del dato).
    asof, asof_src = meta.get("asof"), "_meta.asof"
    if not isinstance(asof, (int, float)):
        asof, asof_src = os.path.getmtime(path), "mtime (el mapa no trae _meta.asof)"
    gedad = time.time() - asof
    faltan = sessions_since(asof)
    cobertura = meta.get("cobertura") or f"{n_ok}/{canon_n or '?'}"
    edad = (f"{gedad/3600:.0f}h por {asof_src}, "
            + ("0 sesiones perdidas" if faltan == 0 else
               "sesiones NO contables" if faltan is None else
               f"{faltan} sesion(es) por detras"))
    if meta_roto:
        return "warn", f"mapa gamma: cobertura {n_ok}/{canon_n or '?'} pero {meta_roto} — {why}"
    if faltan is None:
        return "warn", (f"mapa gamma: cobertura {cobertura} pero {edad} (tabla de festivos "
                        f"agotada) — {why}")
    if faltan >= 1:
        return "warn", (f"mapa gamma: RANCIO ({edad}) con cobertura {cobertura} — reejecuta "
                        f"scripts/gex_snapshot.py. {why}")
    if canon_n and n_ok < canon_n:
        sk = meta.get("skipped") or {}
        faltantes = ",".join(sorted(sk)[:8]) if sk else "?"
        return "warn", (f"mapa gamma: cobertura {cobertura} ({edad}) — sin mapa: "
                        f"{faltantes}{' ...' if len(sk) > 8 else ''} | {why}")
    return "ok", f"mapa gamma: ok, cobertura {cobertura} MEDIDA ({edad})"


def market_source(path=None):
    """Proveedor de market data vigente, de data/market_source.txt.

    MISMO default que el lanzador (fleet_keepalive_start.sh:14 y fleet_up.sh:19: `|| echo
    ibkr`): este chequeo tiene que mirar lo que el lanzador ARRANCO, no lo que a el le
    parezca. Divergir del default seria la misma clase de bug que las cuatro definiciones
    del horario (ver fleet_window.py)."""
    p = path or os.path.join(REPO, "data", "market_source.txt")
    try:
        with open(p) as fh:
            return fh.read().strip() or "ibkr"
    except OSError:
        return "ibkr"


def bar_feed(ms=None):
    """(etiqueta, patron_pgrep) del daemon que ALIMENTA las barras con el proveedor vigente.

    Condicional por proveedor, no amputacion (orden de Yunior 2026-08-03 #10): el camino
    IBKR sigue entero y vuelve solo con poner "ibkr" en data/market_source.txt. Espeja la
    bifurcacion que ya hacen fleet_up.sh:30-36 y fleet_keepalive_start.sh:201-224.

    POR QUE: este fichero era el ULTIMO que daba por hecho que el feed es IBKR. Con
    market_source=intrinio (semana del 2026-08-03, Gateway prohibido) cantaba 🔴 CRITICO
    "bar_bridge (feed IBKR): MUERTO" en cada corrida — 3 al dia — por algo CORRECTO, y
    ademas relanzaba la flota para resucitar un puente que no debe existir."""
    ms = market_source() if ms is None else ms
    if ms == "ibkr":
        return "bar_bridge (feed IBKR)", "ibkr_bar_bridge.py"
    return f"provider_bridge (feed {ms})", "provider_bridge.py"


def market_hours():
    lt = time.localtime()
    return lt.tm_wday < 5 and 930 <= lt.tm_hour*100+lt.tm_min < 1600

def premarket_or_session():
    lt = time.localtime()
    return lt.tm_wday < 5 and 400 <= lt.tm_hour*100+lt.tm_min < 1600

def fleet_window_live():
    """True/False segun el PORTERO (./fleet_hours), None si no se puede saber.

    UNA SOLA VERDAD. Este fichero tenia su propia idea del horario (`market_hours()`,
    lun-vie 09:30-16:00) que NO es la ventana de la flota (domingo 20:00 -> viernes 20:00
    hora de Toronto, orden de Yunior 2026-07-25). Dos definiciones divergentes = el
    healthcheck REVIVIENDO lo que el portero acaba de apagar, cada 5 minutos.

    Medido hoy sabado 16:42 con el mercado cerrado: el healthcheck revivia notify_relay y
    x_signal_poster y acto seguido los cantaba 🔴 CRITICOS por estar muertos — que fuera de
    ventana es justo lo correcto. Deshacia el apagado y ademas mentia sobre su gravedad.

    None (portero ausente) NO se degrada a "pues estara vivo": se canta y NO se revive
    nada, igual que hace `fleet_keepalive_start.sh`. Ante la duda, callar, nunca arrancar.

    El calculo vive en `fleet_hours.cpp` y el puente en `scripts/fleet_window.py`: aqui no
    se reimplementa: era justo la duplicacion lo que causaba el bug.
    """
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import fleet_window
    return fleet_window.live()


def spawn_keepalive(path):
    """Lanza un keepalive DESPEGADO de este proceso: sesion propia => grupo propio.

    Sin `start_new_session=True` el hijo hereda el process group del healthcheck, y
    launchd.plist(5) es explicito: "When a job dies, launchd kills any remaining
    processes with the same process group ID as the job". El healthcheck termina
    segundos despues de curar, launchd barre el grupo y se lleva por delante al
    keepalive recien nacido. `nohup` NO protegia: solo ignora SIGHUP, no el
    SIGTERM/SIGKILL al grupo. Resultado medido: auto-curado NO-OP que cantaba
    "REVIVIDO" — peor que no tener red de seguridad, porque nadie mira.

    Ruta ABSOLUTA y cwd explicito: con "scripts/<x>.sh" relativo, un cwd distinto
    hacia que zsh muriera con 127 sin que Popen levantara nada (otro REVIVIDO falso)."""
    return subprocess.Popen(["zsh", path],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            cwd=REPO, start_new_session=True)

def heal(name, keepalive, verify_s=6.0):
    """Revive un daemon via su keepalive si esta muerto. Idempotente.

    Solo se canta REVIVIDO si se VERIFICA que el keepalive esta corriendo: lanzar un
    proceso no es revivirlo. Si no aparece, se dice lo que paso (murio al instante,
    falta el script, sigue sin aparecer) — jamas un exito plausible."""
    if proc_alive(keepalive):
        return None
    path = os.path.join(REPO, "scripts", keepalive)
    if not os.path.exists(path):
        return f"{name}: NO revivido — falta el keepalive {path}"
    try:
        p = spawn_keepalive(path)
    except OSError as e:
        return f"{name}: fallo revivir ({e})"
    deadline = time.time() + verify_s
    while time.time() < deadline:
        time.sleep(0.3)
        if proc_alive(keepalive):
            return f"{name}: REVIVIDO (verificado, pid {p.pid})"
        rc = p.poll()
        if rc is not None:
            return f"{name}: NO revivido — el keepalive murio al instante (exit {rc})"
    return f"{name}: NO revivido — sigue sin aparecer {verify_s:.0f}s despues del lanzamiento"

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

    # Portero calculado una vez: launchd y los daemons deben juzgar el mismo horario.
    ventana = fleet_window_live()

    # 1) launchd jobs criticos (excluyendo nuestro propio job: ver audit_launchd)
    ld = launchd_state()
    me_label = self_label()
    if me_label is None:
        warn.append("launchd: no encuentro mi propio plist en ~/Library/LaunchAgents "
                    "(no puedo excluirme del audit de exit codes)")
    lok, lwarn, lcrit = audit_launchd(ld, me_label, gated_jobs(), fleet_live=ventana)
    ok += lok; warn += lwarn; crit += lcrit
    warn += stuck_jobs(ld)

    # 2) daemons criticos (con auto-cura)
    checks = [
        ("notify_relay (notificaciones)", "scripts/notify_relay.sh", "notify_relay.sh", True),
        ("x_signal_poster (X realtime)", "scripts/x_signal_poster.py", "x_signal_keepalive.sh", True),
    ]
    if ventana is None:
        warn.append("portero horario AUSENTE (./fleet_hours): no revivo daemons a ciegas — "
                    "compila con scripts/build_fleet_hours.sh")
    ciego = pgrep_ciego()
    if ciego:
        warn.append("VISTA CIEGA: pgrep no ve ni a launchd — no declaro nada MUERTO ni revivo a "
                    "ciegas (entorno aislado/sandbox, no un fallo de la flota)")
    for name, pat, ka, critical in checks:
        if ciego:
            continue
        always_live = "notify_relay" in pat
        if proc_alive(pat):
            # Vivo FUERA de ventana no es "ok": es algo que el apagado no alcanzo.
            (ok if ventana is not False or always_live else warn).append(
                f"{name}: vivo" if ventana is not False or always_live
                else f"{name}: VIVO fuera de ventana (el apagado no lo alcanzo)")
        elif ventana is False and not always_live:
            ok.append(f"{name}: muerto (fuera de ventana, correcto)")
        elif ventana is None:
            warn.append(f"{name}: muerto y sin portero para saber si toca — no lo revivo")
        else:
            recovered = False
            if not a.no_heal:
                h = heal(name, ka)
                if h:
                    healed.append(h)
                    recovered = "REVIVIDO" in h
            if recovered:
                ok.append(f"{name}: vivo tras auto-cura verificada")
            else:
                (crit if critical else warn).append(f"{name}: MUERTO")

    # 3) feed de datos + bots (solo critico en horario de mercado/premarket)
    feed_lbl, feed_pat = bar_feed()
    bridge = proc_alive(feed_pat)
    bots = count_proc("signal_bot")
    if ciego:
        pass   # sin vista de procesos no se afirma ni vivo ni muerto (ya avisado arriba)
    elif premarket_or_session():
        if not bridge and not a.no_heal:
            try:
                # start_new_session: si no, launchd barre este arranque con el grupo del
                # job en cuanto el healthcheck termina (ver spawn_keepalive).
                spawn_keepalive(os.path.join(REPO, "scripts", "fleet_keepalive_start.sh"))
                time.sleep(4); bridge = proc_alive(feed_pat); bots = count_proc("signal_bot")
                healed.append(f"flota: REVIVIDA (verificado: {feed_lbl} vivo, {bots} bots)" if bridge
                              else f"flota: NO revivida — {feed_lbl} sigue sin aparecer 4s despues "
                                   f"del relanzado ({bots} bots)")
            except Exception as e:
                crit.append(f"flota: fallo relanzar ({e})")
        (ok if bridge else crit).append(f"{feed_lbl}: {'vivo' if bridge else 'MUERTO en horario activo'}")
        (ok if bots >= 1 else warn).append(f"signal bots: {bots} vivos")
    else:
        ok.append(f"{feed_lbl} {'vivo' if bridge else 'dormido (fuera de horario, normal)'} | bots {bots}")
    if not ciego:
        ow = proc_alive("opt_whale_watch")
        (ok if ow else (warn if market_hours() else ok)).append(
            "opt_whale (ballenas opciones): vivo" if ow else
            "opt_whale (ballenas opciones): MUERTO en horario de mercado" if market_hours() else
            "opt_whale (ballenas opciones): parado fuera de horario (correcto)")

    # 4) frescura de salidas del dia
    today = time.strftime("%Y-%m-%d")
    _hoy = os.environ.get("IBT_DESKTOP_HOY", os.path.expanduser("~/Desktop/ib-trader/hoy"))
    pdir = os.path.join(_hoy, f"planes-{today}")
    if not os.path.isdir(pdir):   # legado pre-repunto (Desktop raiz)
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

    # 5) el mapa gamma PROPIO: escrito, con cobertura y del dia de mercado vigente?
    #
    # gexa.ai murio el 2026-07-25 y con el el scraping por Chrome: ya no hay nada que
    # "conectar". Lo que se vigila ahora es data/gex_snapshot.json, que gex_snapshot.py
    # calcula desde las cadenas archivadas con griegas MEDIDAS de Polygon. Si ese fichero
    # no esta, los planes se quedan SIN regimen gamma -> es 🔴, no un aviso: era justo el
    # fallo que el 2026-07-24 estuvo dos dias en verde mientras los planes iban ciegos.
    #
    # El reloj de pared miente en fin de semana: un mapa del cierre del viernes leido el
    # sabado son "60h" y no le falta NI UNA sesion. Se cuentan SESIONES DE MERCADO, no horas.
    nivel, msg = gex_map_status()
    {"crit": crit, "warn": warn, "ok": ok}[nivel].append(msg)

    # 5b) token de Finviz: caduca cada semana y Finviz NO devuelve 401 — devuelve 200
    # con el cuerpo vacio. Sin esto el scout, finviz_valuation y el bot de X se quedan
    # mudos sin que nadie se entere.
    # El registro se refresca AQUI cuando esta rancio (una peticion, 3x/dia) en vez de
    # crear otro plist: asi el chequeo no depende de que alguien se acuerde de lanzarlo.
    refresh_finviz_health()
    nivel, msg = finviz_token_status()
    {"crit": crit, "warn": warn, "ok": ok}[nivel].append(msg)

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
            miss_txt = ",".join(sorted(missing))
            (ok if not missing else warn).append(f"cobertura generador: {len(gen)}/{len(canon)}" + (f" FALTAN [{miss_txt}]" if missing else ""))
        # skills
        sk = set(x.replace("ticker-", "").upper() for x in os.listdir(os.path.expanduser("~/.claude/skills")) if x.startswith("ticker-"))
        smiss = canon - sk
        smiss_txt = ",".join(sorted(smiss))
        (ok if not smiss else warn).append(f"skills ticker: {len(sk & canon)}/{len(canon)}" + (f" FALTAN [{smiss_txt}]" if smiss else ""))

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
    # Un intento de cura FALLIDO no lleva ✅ ni cuenta como "curado": era justo esa
    # palomita la que hacia creer que habia red de seguridad (ver spawn_keepalive).
    curados = [h for h in healed if "REVIVID" in h]
    if healed:
        lines += ["AUTO-CURADO:"] + [f"  {'✅' if h in curados else '🔴'} {h}" for h in healed]
    if crit: lines += ["CRITICO:"] + [f"  🔴 {c}" for c in crit]
    if warn: lines += ["AVISOS:"] + [f"  🟡 {w}" for w in warn]
    lines += ["OK:"] + [f"  🟢 {o}" for o in ok]
    rc = exit_code(crit, warn)
    lines += [f"SALIDA: exit {rc} ({'FALLO DURO' if rc else 'job OK'}) — "
              f"{len(crit)} crit / {len(warn)} avisos"
              + ("" if me_label is None else f" | mi label launchd: {me_label} (excluido del audit)")]
    report = "\n".join(lines)
    print(report)
    with open(os.path.join(REPO, "logs", "healthcheck.log"), "a") as f:
        f.write(f"\n{report}\n")

    # notificacion Mac (siempre) + email (si critico o avisos, o diario)
    subprocess.Popen([_OSA, "-e",
        f'display notification "{status}: {len(crit)} crit, {len(warn)} avisos, '
        f'{len(curados)}/{len(healed)} curados" with title "🩺 ib-trader healthcheck"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    email_due, email_signature = health_email_due(crit, warn, today)
    if not a.no_email and env("RESEND_KEY") and email_due:
        try:
            import requests
            subj = f"{status} Healthcheck ib-trader {today}"
            resp = requests.post("https://api.resend.com/emails", timeout=20,
                headers={"Authorization": f"Bearer {env('RESEND_KEY')}", "Content-Type": "application/json"},
                json={"from": "onboarding@resend.dev", "to": [env("RESEND_TO")],
                      "subject": subj, "text": report})
            resp.raise_for_status()
            mark_health_email_sent(today, email_signature)
        except Exception as e:
            print("email fallo:", e)
    return rc

if __name__ == "__main__":
    import sys; sys.exit(main())
