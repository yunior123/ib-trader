"""fleet_healthcheck: el contrato de salida y el fin del bucle auto-referencial.

Bug cazado el 2026-07-25: el healthcheck salia exit 1 con CUALQUIER aviso 🟡, launchd
lo grababa como job fallido (LastExitStatus=1) y la corrida siguiente auditaba
`launchctl list`, veia su PROPIO exit 1 y lo reportaba como aviso nuevo. Bucle sobre
si mismo: nunca podia volver a verde. Dos arreglos, ambos fijados aqui:
  (a) exit 0 con solo avisos, non-zero SOLO con 🔴 real (no se pierde el fallo duro).
  (b) el propio label launchd queda fuera del audit de exit codes.
"""
import importlib.util
import os
import plistlib
import signal
import subprocess
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hc():
    return _load("fleet_healthcheck")


# --- (a) contrato de salida ---------------------------------------------------

def test_verde_sale_cero(hc):
    assert hc.exit_code([], []) == 0


def test_solo_avisos_sale_cero(hc):
    """Un healthcheck que informa de avisos NO ha fallado: launchd no debe verlo rojo."""
    assert hc.exit_code([], ["gexa snapshot: RANCIO 58h", "X ledger: no leible"]) == 0


def test_critico_sale_non_zero(hc):
    """La señal de fallo duro NO se pierde con el fix."""
    assert hc.exit_code(["launchd com.ibtrader.dailyplans: NO CARGADO"], []) != 0


def test_critico_con_avisos_sigue_non_zero(hc):
    assert hc.exit_code(["bar_bridge: MUERTO en horario activo"], ["aviso cualquiera"]) != 0


# --- (b) el healthcheck no se audita a si mismo -------------------------------

def test_audit_excluye_mi_propio_label(hc):
    """El escenario exacto del bucle: yo soy el unico job con exit!=0."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.healthcheck": "1"}
    ok, warn, crit = hc.audit_launchd(ld, "com.ibtrader.healthcheck")
    assert not crit
    assert not any("healthcheck" in w for w in warn), warn
    assert hc.exit_code(crit, warn) == 0  # verde de verdad: el bucle esta roto
    assert len(ok) == 2


def test_audit_sigue_cantando_a_los_demas(hc):
    """Excluirme a mi no debe amordazar el audit del resto de la flota."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.healthcheck": "1", "com.ibtrader.fence": "78"}
    _ok, warn, crit = hc.audit_launchd(ld, "com.ibtrader.healthcheck")
    assert not crit
    assert [w for w in warn if "com.ibtrader.fence" in w and "78" in w], warn
    assert not any("healthcheck" in w for w in warn), warn


def test_audit_job_critico_ausente_es_rojo(hc):
    ld = {"com.ibtrader.postmortem": "0"}
    _ok, _warn, crit = hc.audit_launchd(ld, "com.ibtrader.healthcheck")
    assert any("dailyplans" in c and "NO CARGADO" in c for c in crit), crit
    assert hc.exit_code(crit, []) != 0


def test_audit_excusa_el_exit_1_de_un_job_con_portero_propio(hc):
    """Medido 2026-08-03 07:00: polychains.intraday y tracecube salen 1 por su PROPIA
    guarda horaria (`[ "$H" -ge 0935 ]` / ./bin/fleet_hours) y el informe los cantaba
    "exit 1 (revisar config)" en cada corrida. Gritar por el comportamiento correcto
    entrena a ignorar los avisos."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.tracecube": "1"}
    ok, warn, crit = hc.audit_launchd(ld, None, gated={"com.ibtrader.tracecube"})
    assert not crit and not warn, (warn, crit)
    assert any("tracecube" in o and "portero" in o for o in ok), ok


def test_audit_no_excusa_otro_exit_de_un_job_con_portero(hc):
    """El portero devuelve 1. Un 78 (EX_CONFIG, el de la mudanza a ~/ib-trader) o un 127
    siguen siendo avisos aunque el job tenga guarda horaria."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.tracecube": "78"}
    _ok, warn, _crit = hc.audit_launchd(ld, None, gated={"com.ibtrader.tracecube"})
    assert any("tracecube" in w and "78" in w for w in warn), warn


def test_audit_sin_gated_se_comporta_como_antes(hc):
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.tracecube": "1"}
    _ok, warn, _crit = hc.audit_launchd(ld, None)
    assert any("tracecube" in w for w in warn), warn


def test_gated_jobs_se_deriva_del_plist_no_de_una_lista(hc, tmp_path):
    """Si mañana otro job se pone portero, el audit lo respeta solo."""
    for lbl, cmd in [
            ("com.ibtrader.conguarda", ['/bin/zsh', '-lc', 'H=$(date +%H%M) && [ "$H" -ge 0935 ] && ./x.sh']),
            ("com.ibtrader.conportero", ['/bin/zsh', '-lc', 'cd ~/ib-trader && ./bin/fleet_hours && ./y.sh']),
            ("com.ibtrader.singuarda", ['/bin/zsh', '/ruta/z.sh'])]:
        with open(tmp_path / f"{lbl}.plist", "wb") as fh:
            plistlib.dump({"Label": lbl, "ProgramArguments": cmd}, fh)
    g = hc.gated_jobs(agents_dir=str(tmp_path))
    assert g == {"com.ibtrader.conguarda", "com.ibtrader.conportero"}, g


def test_gated_jobs_reales_incluyen_los_dos_medidos(hc):
    """Contra los plists instalados de verdad: los dos que Yunior ya verifico a mano."""
    g = hc.gated_jobs()
    if os.path.exists(os.path.expanduser("~/Library/LaunchAgents/com.ibtrader.tracecube.plist")):
        assert "com.ibtrader.tracecube" in g, g
        assert "com.ibtrader.polychains.intraday" in g, g


# --- jobs COLGADOS: el audit de exit codes es ciego a esto ------------------------
# launchd no relanza un job periodico mientras la instancia anterior siga viva. Un
# proceso colgado deja de correr para siempre SIN cambiar de exit code.

def test_parse_etime_formatos(hc):
    assert hc.parse_etime("03:06:52") == 3 * 3600 + 6 * 60 + 52
    assert hc.parse_etime("  12:30 ") == 750
    assert hc.parse_etime("2-01:00:00") == 2 * 86400 + 3600


def test_parse_etime_none_nunca_cero(hc):
    """Un 0 se leeria como 'acaba de arrancar' y taparia justo el proceso colgado."""
    for basura in ("", None, "no-soy-un-tiempo", "??:??"):
        assert hc.parse_etime(basura) is None, basura


def test_stuck_jobs_caza_el_intrinioprobe_real(hc):
    """El caso medido: StartInterval 600 s y 3h06m en la misma corrida = 18 sondas
    perdidas en silencio, mientras el informe solo decia 'exit 1'."""
    avisos = hc.stuck_jobs(intervals={"com.ibtrader.intrinioprobe": 600},
                           edades={"com.ibtrader.intrinioprobe": 11212})
    assert len(avisos) == 1 and "COLGADO" in avisos[0] and "186 min" in avisos[0], avisos


def test_stuck_jobs_no_grita_por_una_corrida_normal(hc):
    """Un job periodico que tarda algo mas de un ciclo no esta colgado (histeresis x3)."""
    assert hc.stuck_jobs(intervals={"com.ibtrader.prints": 120},
                         edades={"com.ibtrader.prints": 200}) == []


def test_stuck_jobs_ignora_los_de_calendario(hc):
    """Sin StartInterval no hay presupuesto de tiempo: no se inventa uno."""
    assert hc.stuck_jobs(intervals={}, edades={"com.ibtrader.dailyplans": 99999}) == []


# --- el feed NO es siempre IBKR: condicional por proveedor -------------------------

def test_bar_feed_ibkr(hc):
    assert hc.bar_feed("ibkr") == ("bar_bridge (feed IBKR)", "ibkr_bar_bridge.py")


def test_bar_feed_otro_proveedor_vigila_el_provider_bridge(hc):
    """Con market_source=intrinio el healthcheck cantaba 🔴 'bar_bridge (feed IBKR):
    MUERTO' 3 veces al dia por algo CORRECTO, y ademas relanzaba la flota para resucitar
    un puente prohibido esta semana. El camino IBKR sigue entero (regla 10: condicional,
    no amputacion)."""
    lbl, pat = hc.bar_feed("intrinio")
    assert pat == "provider_bridge.py"
    assert "intrinio" in lbl


def test_market_source_default_igual_que_el_lanzador(hc, tmp_path):
    """Mismo default que fleet_keepalive_start.sh:14 y fleet_up.sh:19 (`|| echo ibkr`):
    divergir seria la misma clase de bug que las 4 definiciones del horario."""
    assert hc.market_source(path=str(tmp_path / "no_existe.txt")) == "ibkr"
    p = tmp_path / "ms.txt"
    p.write_text("")
    assert hc.market_source(path=str(p)) == "ibkr"
    p.write_text("intrinio\n")
    assert hc.market_source(path=str(p)) == "intrinio"


def test_audit_sin_label_propio_no_excluye_nada(hc):
    """me_label=None (plist no encontrado) => no se excluye a nadie por error."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.healthcheck": "1"}
    _ok, warn, _crit = hc.audit_launchd(ld, None)
    assert any("healthcheck" in w for w in warn), warn


def test_self_label_derivado_del_plist_no_hardcodeado(hc, tmp_path):
    """self_label() lee el Label del plist cuyos ProgramArguments apuntan a este script."""
    plist = {"Label": "com.ibtrader.renombrado",
             "ProgramArguments": ["/usr/bin/python3", hc.SELF_PATH]}
    with open(tmp_path / "com.ibtrader.renombrado.plist", "wb") as fh:
        plistlib.dump(plist, fh)
    assert hc.self_label(agents_dir=str(tmp_path), me=hc.SELF_PATH) == "com.ibtrader.renombrado"


def test_self_label_none_si_no_aparece(hc, tmp_path):
    """Sin plist propio devuelve None — jamas una cadena inventada que excluiria
    del audit el job de otro."""
    plist = {"Label": "com.ibtrader.otro",
             "ProgramArguments": ["/usr/bin/python3", "/otro/script.py"]}
    with open(tmp_path / "com.ibtrader.otro.plist", "wb") as fh:
        plistlib.dump(plist, fh)
    assert hc.self_label(agents_dir=str(tmp_path), me=hc.SELF_PATH) is None
    assert hc.self_label(agents_dir=str(tmp_path / "no-existe"), me=hc.SELF_PATH) is None


def test_self_label_plist_corrupto_no_mata_el_audit(hc, tmp_path, capsys):
    """Un plist ilegible se CANTA (fail-loud) y se sigue; no aborta el healthcheck."""
    (tmp_path / "roto.plist").write_bytes(b"no soy un plist")
    good = {"Label": "com.ibtrader.healthcheck",
            "ProgramArguments": [hc.SELF_PATH]}
    with open(tmp_path / "zz.plist", "wb") as fh:
        plistlib.dump(good, fh)
    assert hc.self_label(agents_dir=str(tmp_path), me=hc.SELF_PATH) == "com.ibtrader.healthcheck"
    assert "roto.plist" in capsys.readouterr().out


# --- fail-loud: nada de ceros/conjuntos plausibles ---------------------------

def test_canonical_fleet_none_si_falta(hc, monkeypatch):
    """None, no set(): un conjunto vacio saltaba los checks de cobertura en silencio."""
    monkeypatch.setattr(hc.os.path, "exists", lambda p: False)
    assert hc.canonical_fleet() is None


def test_canonical_fleet_real_tiene_la_flota(hc):
    canon = hc.canonical_fleet()
    assert canon is not None and {"QQQ", "SPY", "NVDA"} <= canon


def test_env_none_sin_clave(hc):
    assert hc.env("CLAVE_QUE_NO_EXISTE_JAMAS") is None


# --- gexa: el reloj de pared miente en fin de semana ------------------------------
# Un snapshot del cierre del viernes leido el sabado son "60h rancio" y NO le falta ni
# una sesion. El aviso se mide en SESIONES DE MERCADO abiertas desde la captura, no en
# horas, para que el healthcheck no grite por un mercado que estaba cerrado.

def _ts(y, m, d, hh=16, mm=0):
    import datetime as dt
    return dt.datetime(y, m, d, hh, mm).timestamp()


def test_sessions_since_no_cuenta_el_fin_de_semana(hc, monkeypatch):
    """Viernes 2026-07-24 al cierre, leido el sabado 25: 0 sesiones perdidas."""
    import datetime as dt

    class _Sab(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2026, 7, 25)

    monkeypatch.setattr(dt, "date", _Sab)
    assert hc.sessions_since(_ts(2026, 7, 24)) == 0


def test_sessions_since_cuenta_las_sesiones_realmente_perdidas(hc, monkeypatch):
    """Miercoles 22 leido el sabado 25: faltan jueves 23 y viernes 24 = 2 sesiones.
    Son 72h de reloj, pero lo que importa son las 2 sesiones — el caso real de hoy."""
    import datetime as dt

    class _Sab(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2026, 7, 25)

    monkeypatch.setattr(dt, "date", _Sab)
    assert hc.sessions_since(_ts(2026, 7, 22, 10, 44)) == 2


def test_sessions_since_devuelve_None_si_no_puede_contar(hc, monkeypatch):
    """La tabla de festivos de em_envelope LEVANTA fuera de rango. Eso no puede volverse
    un 0 plausible ('esta fresco') — se devuelve None y quien llama lo canta."""
    import em_envelope

    def _boom(_d):
        raise RuntimeError("tabla de festivos agotada")

    monkeypatch.setattr(em_envelope, "is_market_day", _boom)
    assert hc.sessions_since(_ts(2026, 7, 20)) is None


def test_poly_chains_today_cuenta_cadenas_con_griegas_reales(hc, tmp_path, monkeypatch):
    """La alternativa MEDIDA a gexa: si poly_chain_archive dejo cadenas hoy, el mapa gamma
    no depende del scraping y el aviso baja a informativo."""
    import datetime as dt
    monkeypatch.setattr(hc, "REPO", str(tmp_path))
    d = tmp_path / "data" / "history" / dt.date.today().isoformat()
    d.mkdir(parents=True)
    for s in ("qqq", "spy", "nvda"):
        (d / f"chain_full_{s}.json").write_text("{}")
    (d / "poly_chain_qqq_1018.txt").write_text("no es una cadena json")
    assert hc.poly_chains_today() == 3


def test_poly_chains_today_sin_carpeta_es_cero_no_una_excepcion(hc, tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "REPO", str(tmp_path))
    assert hc.poly_chains_today() == 0


# --- el mapa gamma PROPIO (gexa jubilado el 2026-07-25) ---------------------------
# gexa.ai desaparecio: ya no hay nada que "conectar". Lo que se vigila es
# data/gex_snapshot.json, calculado en casa con las griegas MEDIDAS de Polygon. Su
# AUSENCIA es 🔴 (los planes se quedan sin regimen gamma, y ese fallo estuvo dos dias
# en verde el 2026-07-24); su cobertura a medias es 🟡. Nunca se rellena con un cero.

def _mapa(tmp_path, syms, meta=None, asof=None):
    """Escribe un data/gex_snapshot.json de juguete y devuelve su ruta."""
    import json
    import time
    d = {s: {"flip": 100.0, "score": -1.2, "poc": 99.0, "regime": "NEGATIVE"} for s in syms}
    m = {"cobertura": f"{len(syms)}/30", "asof": asof if asof is not None else int(time.time())}
    m.update(meta or {})
    d["_meta"] = m
    p = tmp_path / "gex_snapshot.json"
    p.write_text(json.dumps(d))
    return str(p)


def test_mapa_gamma_ausente_es_ROJO(hc, tmp_path):
    """Sin mapa los planes van ciegos: 🔴, no un aviso informativo."""
    nivel, msg = hc.gex_map_status(path=str(tmp_path / "no_existe.json"), canon_n=30, poly_n=0)
    assert nivel == "crit"
    assert "NO EXISTE" in msg
    assert hc.exit_code([msg], []) != 0          # y el contrato de salida lo propaga


def test_mapa_gamma_roto_es_ROJO_no_cero_simbolos_en_silencio(hc, tmp_path):
    p = tmp_path / "gex_snapshot.json"
    p.write_text("{esto no es json valido")
    nivel, msg = hc.gex_map_status(path=str(p), canon_n=30, poly_n=25)
    assert nivel == "crit"
    assert "0 simbolos usables" in msg


def test_mapa_gamma_bajo_media_flota_es_ROJO(hc, tmp_path):
    """14/30 no es "casi": es media flota sin regimen gamma."""
    p = _mapa(tmp_path, [f"S{i}" for i in range(14)])
    nivel, msg = hc.gex_map_status(path=p, canon_n=30, poly_n=14)
    assert nivel == "crit"
    assert "MITAD" in msg


def test_mapa_gamma_le_faltan_simbolos_es_AMARILLO_y_sale_cero(hc, tmp_path):
    """25/30 avisa y NOMBRA a los que faltan, pero no es un fallo del job."""
    p = _mapa(tmp_path, [f"S{i}" for i in range(25)],
              meta={"cobertura": "25/30", "skipped": {"NOK": "sin cadena", "QCOM": "sin cadena"}})
    nivel, msg = hc.gex_map_status(path=p, canon_n=30, poly_n=25)
    assert nivel == "warn"
    assert "NOK" in msg and "QCOM" in msg
    assert hc.exit_code([], [msg]) == 0


def test_mapa_gamma_completo_y_fresco_es_VERDE_y_dice_que_es_medido(hc, tmp_path):
    p = _mapa(tmp_path, [f"S{i}" for i in range(30)], meta={"cobertura": "30/30"})
    nivel, msg = hc.gex_map_status(path=p, canon_n=30, poly_n=30)
    assert nivel == "ok"
    assert "MEDIDA" in msg          # procedencia en el propio aviso, no "GEXA verificado"


def test_mapa_gamma_rancio_por_SESIONES_no_por_horas(hc, tmp_path, monkeypatch):
    """3 sesiones por detras = 🟡 RANCIO aunque la cobertura sea perfecta."""
    monkeypatch.setattr(hc, "sessions_since", lambda _ts: 3)
    p = _mapa(tmp_path, [f"S{i}" for i in range(30)], meta={"cobertura": "30/30"})
    nivel, msg = hc.gex_map_status(path=p, canon_n=30, poly_n=30)
    assert nivel == "warn"
    assert "RANCIO" in msg and "3 sesion" in msg


def test_mapa_gamma_sin_asof_usa_mtime_y_LO_DICE(hc, tmp_path):
    """Si el mapa no trae _meta.asof se mide por mtime, pero se confiesa cual de los dos
    se uso: no se finge que la marca de tiempo venia dentro del dato."""
    import json
    p = tmp_path / "gex_snapshot.json"
    p.write_text(json.dumps({f"S{i}": {"flip": 1.0} for i in range(30)}))
    nivel, msg = hc.gex_map_status(path=str(p), canon_n=30, poly_n=30)
    assert nivel == "ok"
    assert "mtime" in msg


def test_mapa_gamma_sesiones_no_contables_avisa_sin_inventar_frescura(hc, tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "sessions_since", lambda _ts: None)
    p = _mapa(tmp_path, [f"S{i}" for i in range(30)], meta={"cobertura": "30/30"})
    nivel, msg = hc.gex_map_status(path=p, canon_n=30, poly_n=30)
    assert nivel == "warn"
    assert "NO contables" in msg


def test_mapa_gamma_dice_por_que_falta_cobertura(hc, tmp_path):
    """Sin cadenas archivadas hoy, el aviso apunta al culpable (poly_chain_archive)."""
    p = _mapa(tmp_path, [f"S{i}" for i in range(25)], meta={"cobertura": "25/30"})
    _, msg = hc.gex_map_status(path=p, canon_n=30, poly_n=0)
    assert "poly_chain_archive" in msg



# --- (c) el auto-curado: "REVIVIDO" tiene que ser VERDAD --------------------------
# Defecto cazado el 2026-07-26. heal() revivia el keepalive con
#     subprocess.Popen(["nohup", "zsh", f"scripts/{keepalive}"])   # sin start_new_session
# y el plist com.ibtrader.healthcheck no llevaba AbandonProcessGroup. Lo dice la propia
# launchd.plist(5) de macOS: "When a job dies, launchd kills any remaining processes with
# the same process group ID as the job." El healthcheck termina segundos despues de curar
# -> launchd barre el grupo -> el keepalive recien nacido muere con el. Y el informe ya
# habia cantado "REVIVIDO". `nohup` no salva de nada: solo ignora SIGHUP, no el SIGTERM
# al grupo. Creer que hay red de seguridad y no tenerla es peor que no tenerla.

_LATIDO = """#!/bin/zsh
while :; do print tick >> "{hb}"; sleep 0.1; done
"""

_PADRE_LEGACY = """
import subprocess
p = subprocess.Popen(["nohup", "zsh", "{ka}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.pid)
"""

_PADRE_FIX = """
import importlib.util
spec = importlib.util.spec_from_file_location("hc", "{mod}")
hc = importlib.util.module_from_spec(spec); spec.loader.exec_module(hc)
print(hc.spawn_keepalive("{ka}").pid)
"""


def _cura_y_muere(tmp_path, plantilla, mod_path):
    """Reproduce una corrida de launchd: un 'healthcheck' de juguete, lider de SU PROPIO
    grupo de procesos, revive un keepalive que late en un fichero y muere acto seguido;
    entonces cae la escoba de launchd sobre el grupo del job.
    Devuelve (el keepalive sigue latiendo?, quedaba alguien en el grupo del job?)."""
    hb = tmp_path / "latido.txt"
    hb.write_text("")
    ka = tmp_path / "keepalive_juguete.sh"
    ka.write_text(_LATIDO.format(hb=hb))
    padre_py = tmp_path / "padre.py"
    padre_py.write_text(plantilla.format(ka=ka, mod=mod_path))

    # start_new_session: el padre es lider de grupo, su pid ES el pgid del "job".
    padre = subprocess.Popen([sys.executable, str(padre_py)], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    out, err = padre.communicate(timeout=60)
    assert padre.returncode == 0, err
    hijo = int(out.split()[0])
    time.sleep(0.5)                       # que late un poco antes de la escoba

    en_el_grupo = True
    try:
        os.killpg(padre.pid, signal.SIGTERM)      # <- exactamente lo que hace launchd
    except ProcessLookupError:
        en_el_grupo = False                       # no quedaba nadie: el hijo escapo

    antes = len(hb.read_bytes())
    time.sleep(0.6)
    sigue_latiendo = len(hb.read_bytes()) > antes
    if sigue_latiendo:                            # limpieza del superviviente
        try:
            os.killpg(os.getpgid(hijo), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return sigue_latiendo, en_el_grupo


def test_el_popen_legacy_muere_con_el_healthcheck(tmp_path):
    """EL DAÑO, medido: el keepalive lanzado como lo hacia heal() comparte grupo con el
    job y la escoba de launchd se lo lleva. Nada revivio; el correo decia que si."""
    sigue_latiendo, en_el_grupo = _cura_y_muere(tmp_path, _PADRE_LEGACY, "")
    assert en_el_grupo, "el hijo legacy deberia seguir en el grupo del job (por eso muere)"
    assert not sigue_latiendo, "sin start_new_session el keepalive NO puede sobrevivir"


def test_spawn_keepalive_sobrevive_a_la_escoba_de_launchd(hc, tmp_path):
    """El arreglo: sesion propia -> pgid propio -> la escoba de launchd no lo alcanza."""
    sigue_latiendo, en_el_grupo = _cura_y_muere(tmp_path, _PADRE_FIX, hc.SELF_PATH)
    assert not en_el_grupo, "el keepalive tiene que haber SALIDO del grupo del job"
    assert sigue_latiendo, "el keepalive revivido debe seguir vivo tras morir el healthcheck"


def test_spawn_keepalive_pone_sesion_propia(hc, monkeypatch):
    """Blindaje contra regresiones silenciosas: el flag es el arreglo entero."""
    visto = {}

    class _Fake:
        pid = 4242

    def _popen(cmd, **kw):
        visto["cmd"] = cmd
        visto["kw"] = kw
        return _Fake()

    monkeypatch.setattr(hc.subprocess, "Popen", _popen)
    assert hc.spawn_keepalive("/x/y.sh").pid == 4242
    assert visto["kw"].get("start_new_session") is True
    assert visto["kw"].get("cwd") == hc.REPO      # ruta absoluta + cwd fijo, no relativa
    assert "/x/y.sh" in visto["cmd"]


# --- heal(): "REVIVIDO" solo si se VERIFICA que revivio ---------------------------

def test_heal_no_canta_revivido_si_el_keepalive_no_aparece(hc, monkeypatch):
    """Popen puede tener exito y el keepalive morir al instante (script movido, zsh 127).
    El informe NO puede decir REVIVIDO por el mero hecho de haber lanzado algo."""
    class _Muerto:
        pid = 1
        returncode = 127

        def poll(self):
            return 127

    monkeypatch.setattr(hc, "proc_alive", lambda _p: False)
    monkeypatch.setattr(hc, "spawn_keepalive", lambda _p: _Muerto())
    monkeypatch.setattr(hc.os.path, "exists", lambda _p: True)
    msg = hc.heal("relay", "notify_relay.sh", verify_s=1.0)
    assert "REVIVIDO" not in msg, msg
    assert "127" in msg


def test_heal_falta_el_script_lo_dice_y_no_miente(hc, monkeypatch):
    monkeypatch.setattr(hc, "proc_alive", lambda _p: False)
    msg = hc.heal("relay", "keepalive_que_no_existe.sh", verify_s=1.0)
    assert "REVIVIDO" not in msg, msg
    assert "keepalive_que_no_existe.sh" in msg


def test_heal_verificado_canta_revivido(hc, monkeypatch):
    """Cuando de verdad aparece, se dice — y se dice que esta VERIFICADO."""
    estados = iter([False, True, True, True])

    class _Vivo:
        pid = 777

        def poll(self):
            return None

    monkeypatch.setattr(hc, "proc_alive", lambda _p: next(estados, True))
    monkeypatch.setattr(hc, "spawn_keepalive", lambda _p: _Vivo())
    monkeypatch.setattr(hc.os.path, "exists", lambda _p: True)
    msg = hc.heal("relay", "notify_relay.sh", verify_s=3.0)
    assert "REVIVIDO" in msg and "777" in msg


def test_heal_no_toca_lo_que_ya_esta_vivo(hc, monkeypatch):
    monkeypatch.setattr(hc, "proc_alive", lambda _p: True)
    assert hc.heal("relay", "notify_relay.sh") is None


def test_el_plist_del_healthcheck_abandona_el_grupo():
    """Cinturon y tirantes: aunque el hijo ya salga del grupo, el job declara que no
    quiere que launchd barra su grupo al terminar."""
    fuente = os.path.join(REPO, "scripts", "com.ibtrader.healthcheck.plist")
    with open(fuente, "rb") as fh:
        assert plistlib.load(fh).get("AbandonProcessGroup") is True, fuente
    vivo = os.path.expanduser("~/Library/LaunchAgents/com.ibtrader.healthcheck.plist")
    if os.path.exists(vivo):
        with open(vivo, "rb") as fh:
            assert plistlib.load(fh).get("AbandonProcessGroup") is True, (
                f"{vivo}: instalado sin AbandonProcessGroup (recargalo tras el fix)")


def test_el_informe_no_pone_palomita_a_una_cura_fallida(hc, tmp_path, monkeypatch, capsys):
    """Un intento de cura FALLIDO no puede salir con ✅ ni contar como 'curado':
    esa palomita era la que hacia creer que habia red de seguridad."""
    monkeypatch.setattr(hc, "proc_alive", lambda _p: False)
    # el test parchea subprocess.Popen entero (subprocess.run lo usa) -> pgrep se queda mudo y
    # saltaria la guarda de VISTA CIEGA. Aqui se simula "veo bien Y el daemon esta muerto".
    monkeypatch.setattr(hc, "pgrep_ciego", lambda: False)
    monkeypatch.setattr(hc, "launchd_state", lambda: {"com.ibtrader.dailyplans": "0",
                                                      "com.ibtrader.postmortem": "0"})
    monkeypatch.setattr(hc, "fleet_window_live", lambda: True)
    monkeypatch.setattr(hc, "premarket_or_session", lambda: False)
    monkeypatch.setattr(hc, "spawn_keepalive", lambda _p: _MuertoAlInstante())
    monkeypatch.setattr(hc.sys, "argv", ["fleet_healthcheck.py", "--no-email"])
    monkeypatch.setattr(hc.subprocess, "Popen", _PopenMudo)   # sin banner osascript
    try:
        hc.main()
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "AUTO-CURADO:" in out, out
    for ln in out.splitlines():
        if "NO revivido" in ln:
            assert "✅" not in ln, ln
            break
    else:
        raise AssertionError("no aparecio ninguna cura fallida en el informe:\n" + out)


class _MuertoAlInstante:
    pid = 1

    def poll(self):
        return 127


class _PopenMudo:
    """Popen inerte: silencia el banner de osascript sin romper subprocess.run."""

    def __init__(self, *a, **k):
        self.returncode = 0
        self.pid = 1
        self.args = a[0] if a else []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def communicate(self, *a, **k):
        return ("", "")

    def poll(self):
        return 0

    def wait(self, *a, **k):
        return 0


# --- (z) vista de procesos CIEGA != "todo muerto" ----------------------------
# 2026-08-03: 222 lineas de 🔴 CRITICO falso en logs/healthcheck.log (notify_relay y
# x_signal_poster "MUERTO" + heals con exit 127) mientras `pgrep` desde una shell normal
# los veia VIVOS (pids 95547/95972), y 111 "launchd NO CARGADO" con dailyplans dejando
# sus 30 PDFs de las 04:00. Causa medida: el pgrep de macOS EXCLUYE al invocante y a sus
# ANCESTROS salvo con `-a`, y un entorno aislado deja a launchctl sin ver ningun job.

def test_pgrep_usa_a_para_no_perder_ancestros(hc, monkeypatch):
    visto = {}

    class _R:
        returncode, stdout, stderr = 0, "123\n", ""

    def _run(args, **k):
        visto["args"] = args
        return _R()

    monkeypatch.setattr(hc.subprocess, "run", _run)
    assert hc.proc_alive("lo_que_sea") is True
    assert visto["args"][:3] == ["pgrep", "-a", "-f"]


def test_pgrep_que_falla_LEVANTA_no_dice_muerto(hc, monkeypatch):
    class _R:
        returncode, stdout, stderr = 2, "", "pgrep: illegal option"

    monkeypatch.setattr(hc.subprocess, "run", lambda *a, **k: _R())
    with pytest.raises(RuntimeError):
        hc.proc_alive("x")


def test_sin_ver_launchd_es_vista_ciega(hc, monkeypatch):
    monkeypatch.setattr(hc, "_pgrep", lambda pat: [])
    assert hc.pgrep_ciego() is True
    monkeypatch.setattr(hc, "_pgrep", lambda pat: ["1"])
    assert hc.pgrep_ciego() is False


def test_launchctl_vacio_no_declara_NO_CARGADO(hc):
    ok, warn, crit = hc.audit_launchd({}, "com.ibtrader.healthcheck")
    assert crit == [] and any("VISTA CIEGA" in w for w in warn)


def test_con_vista_ciega_no_hay_daemon_MUERTO_ni_cura(hc, monkeypatch, capsys):
    monkeypatch.setattr(hc, "pgrep_ciego", lambda: True)
    monkeypatch.setattr(hc, "proc_alive", lambda _p: False)
    monkeypatch.setattr(hc, "count_proc", lambda _p: 0)
    monkeypatch.setattr(hc, "fleet_window_live", lambda: True)
    monkeypatch.setattr(hc, "premarket_or_session", lambda: True)
    curas = []
    monkeypatch.setattr(hc, "heal", lambda *a, **k: curas.append(a))
    monkeypatch.setattr(hc, "spawn_keepalive", lambda _p: curas.append(_p))
    monkeypatch.setattr(hc.sys, "argv", ["fleet_healthcheck.py", "--no-email"])
    monkeypatch.setattr(hc.subprocess, "Popen", _PopenMudo)
    try:
        hc.main()
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "VISTA CIEGA" in out
    assert not [ln for ln in out.splitlines()
                if "MUERTO" in ln and "VISTA CIEGA" not in ln], out
    assert curas == []
