"""Cobertura del embudo -> Discord: los productores enchufados el 2026-08-04.

Auditoria en docs/DISCORD-COBERTURA-2026-08-04.md. Aqui se blinda lo que se cambio:
todo titulo nuevo tiene que (a) salir de verdad por notify_short y (b) casar con una
regla de discord_layout.RULES — si cae en #sin-clasificar la alerta llega, pero al canal
equivocado, y eso no lo detecta nadie en produccion.

Cero red, cero voz: speak.sh/osascript se monkeypatchean y notify_short escribe a tmp_path.
Python 3.9 (./venv): nada de sintaxis 3.10+.
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name, path=None):
    path = path or os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("cob_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load("discord_layout")
NS = _load("notify_short")


@pytest.fixture
def embudo(tmp_path, monkeypatch):
    """notify_short redirigido a un fichero temporal. Devuelve un lector de lineas.

    notify_short.push() se corta solo bajo pytest (notify_short.py:33, tras meter 52 alarmas
    reales en el embudo de produccion el 2026-08-04). Aqui se levanta esa guarda a proposito
    y SOLO contra tmp_path: sin ella estos tests no podrian comprobar que el push existe.
    """
    path = tmp_path / "notify_push.txt"
    monkeypatch.setattr(NS, "PATH", str(path))
    monkeypatch.setattr(NS, "under_pytest", lambda: False)
    sys.modules["notify_short"] = NS          # el `import notify_short` de los productores

    def leer():
        if not path.exists():
            return []
        return [ln for ln in path.read_text().splitlines() if ln.strip()]
    return leer


@pytest.fixture(autouse=True)
def _sin_voz(monkeypatch):
    """Ningun test puede lanzar speak.sh ni osascript."""
    import subprocess

    def prohibido(*a, **kw):
        raise AssertionError("un test intento lanzar un proceso: %r" % (a,))
    monkeypatch.setattr(subprocess, "Popen", prohibido)


def test_la_suite_no_puede_notificar_al_humano_sin_levantar_la_guarda():
    """Sin la fixture `embudo`, un push dentro de pytest NO escribe nada (notify_short.py:33)."""
    assert NS.under_pytest() is True
    antes = os.path.getsize(NS.PATH) if os.path.exists(NS.PATH) else 0
    NS.push("TEST COBERTURA", "esto jamas puede llegar al telefono")
    despues = os.path.getsize(NS.PATH) if os.path.exists(NS.PATH) else 0
    assert antes == despues


def _partes(linea):
    """'HH:MM:SS | titulo | cuerpo' -> (titulo, cuerpo)."""
    trozos = linea.split(" | ", 2)
    assert len(trozos) == 3, "linea del embudo mal formada: %r" % linea
    return trozos[1], trozos[2]


# --- titulos nuevos: enrutado ----------------------------------------------------------
# (titulo, canal esperado). Si alguno cayera en el fallback, la alerta llega a Discord
# pero al canal de descarte, que nadie mira.
TITULOS_NUEVOS = [
    ("🇰🇷 KRX NAVER BRIDGE CIEGO", "estado-proveedores"),
    # 2026-08-05: MOVIDA a #manada. Es el DENOMINADOR de la senal mas selectiva de la
    # casa (precedente 21/26=80,8% disparando DANGER cuando 21/30=70% no debia): quien lee
    # #manada tiene que ver ahi que la manada esta muda, no enterrado en un canal privado.
    ("🕳 MANADA MUDA", "manada"),
    ("FINNHUB WS", "estado-proveedores"),
    ("🩸 EARNINGS-FALL TGTX -8.0%", "earnings-catalizadores"),
    ("🎯 ZONA NVDA", "senales-flota"),
]


@pytest.mark.parametrize("titulo,canal", TITULOS_NUEVOS)
def test_titulo_nuevo_no_cae_en_sin_clasificar(titulo, canal):
    ch, _ = L.classify(titulo + " | cuerpo cualquiera")
    assert ch != L.FALLBACK_CHANNEL, "%r cae en #%s" % (titulo, L.FALLBACK_CHANNEL)
    assert ch == canal, "%r -> #%s, se esperaba #%s" % (titulo, ch, canal)


@pytest.mark.parametrize("titulo,canal", TITULOS_NUEVOS)
def test_canal_destino_existe_y_tiene_webhook(titulo, canal):
    assert canal in L.all_channel_keys()
    assert canal in L.webhook_channels()


# --- korea_naver_bridge: el respaldo KRX era mudo fuera del Mac -------------------------
def test_korea_naver_grita_con_titulo_llega_al_embudo(embudo, monkeypatch):
    kn = _load("korea_naver_bridge")
    monkeypatch.setattr(kn, "subprocess", _SubprocessMudo())
    kn.grita("Puente Corea de respaldo caido: 3 sondeos fallidos seguidos.",
             titulo="🇰🇷 KRX NAVER BRIDGE CIEGO", corto="Corea sin datos.")
    lineas = embudo()
    assert len(lineas) == 1
    titulo, cuerpo = _partes(lineas[0])
    assert titulo == "🇰🇷 KRX NAVER BRIDGE CIEGO"
    assert cuerpo == "Corea sin datos."


def test_korea_naver_grita_sin_titulo_no_toca_el_embudo(embudo, monkeypatch):
    """Retrocompatible: las llamadas viejas siguen siendo solo voz."""
    kn = _load("korea_naver_bridge")
    monkeypatch.setattr(kn, "subprocess", _SubprocessMudo())
    kn.grita("un aviso cualquiera")
    assert embudo() == []


def test_korea_naver_dispara_a_los_FAILS_LOUD_fallos():
    """El aviso sigue gateado por FAILS_LOUD; no es una linea por sondeo fallido."""
    src = open(os.path.join(SCRIPTS, "korea_naver_bridge.py")).read()
    assert "if fallos == FAILS_LOUD:" in src
    assert 'titulo="🇰🇷 KRX NAVER BRIDGE CIEGO"' in src


# --- finnhub_ws_bridge -----------------------------------------------------------------
def test_finnhub_grita_con_titulo_llega_al_embudo(embudo, monkeypatch):
    fb = _load("finnhub_ws_bridge")
    monkeypatch.setattr(fb, "subprocess", _SubprocessMudo())
    fb.grita("Puente Finnhub caido 5 veces seguidas.", titulo="FINNHUB WS",
             corto="socket CAIDO 5 veces")
    lineas = embudo()
    assert len(lineas) == 1
    titulo, cuerpo = _partes(lineas[0])
    assert titulo == "FINNHUB WS" and "socket CAIDO" in cuerpo


def test_finnhub_grita_sin_titulo_no_toca_el_embudo(embudo, monkeypatch):
    fb = _load("finnhub_ws_bridge")
    monkeypatch.setattr(fb, "subprocess", _SubprocessMudo())
    fb.grita("aviso suelto")
    assert embudo() == []


def test_finnhub_cada_5_caidas_solo_deja_log_sin_notificar():
    src = open(os.path.join(SCRIPTS, "finnhub_ws_bridge.py")).read()
    assert "if caidas % 5 == 0:" in src
    bloque = src.split("if caidas % 5 == 0:", 1)[1].split("if vivo >=", 1)[0]
    assert "notificaciones muertas por orden" in bloque
    assert "grita(" not in bloque and "notify_short" not in bloque


# --- provider_bridge: exige py>=3.11 (datetime.UTC), se audita por fuente --------------
def test_provider_bridge_empuja_manada_muda_al_embudo():
    """No se puede importar bajo ./venv (py3.9): se verifica el contrato en el fuente."""
    src = open(os.path.join(SCRIPTS, "provider_bridge.py")).read()
    assert "import notify_short" in src
    assert 'notify_short.push("🕳 MANADA MUDA"' in src
    # el push va DENTRO de grita_si_manada_muda, detras de su triple guarda
    cuerpo = src.split("def grita_si_manada_muda")[1].split("\ndef ")[0]
    assert 'notify_short.push("🕳 MANADA MUDA"' in cuerpo
    assert 'if v["operativa"] or not _rth() or time.time() - _grito_manada < 1800' in cuerpo
    # y el throttle ademas PERSISTE a disco: el crash-loop de com.ibtrader.fleet (StartInterval
    # 300) reseteaba el de memoria -> 1 aviso por relanzamiento (revision 2026-08-04)
    assert "_grito_manada_reciente()" in cuerpo
    assert "_GRITO_MANADA_F.touch()" in cuerpo


def test_provider_bridge_no_inventa_numeros_en_el_push():
    """El cuerpo cita votan/universo MEDIDOS; jamas un 0 o un 50 plausibles."""
    src = open(os.path.join(SCRIPTS, "provider_bridge.py")).read()
    cuerpo = src.split("def grita_si_manada_muda")[1].split("\ndef ")[0]
    assert "v['votan']" in cuerpo and "v['universo']" in cuerpo


# --- earnings_fall_scout: la voz exige OPCIONES OK, el push ya no -----------------------
def _ef(monkeypatch):
    monkeypatch.setenv("EF_TEST", "")          # TEST se lee en import; se fuerza a False
    mod = _load("earnings_fall_scout")
    monkeypatch.setattr(mod, "TEST", False)
    monkeypatch.setattr(mod, "subprocess", _SubprocessMudo())
    return mod


def test_earnings_push_sigue_a_la_voz_por_defecto(embudo, monkeypatch):
    ef = _ef(monkeypatch)
    ef.say("🩸 EARNINGS-FALL ROTO", "export Finviz caido", voice=False)
    assert embudo() == []
    ef.say("🩸 EARNINGS-FALL AAA -9.0%", "largo", voice=True, voice_msg="AAA cayo fuerte.")
    assert len(embudo()) == 1


def test_earnings_push_true_llega_aunque_la_voz_este_vetada(embudo, monkeypatch):
    """El caso del 08-03: IBKR caido -> OPCIONES s/d -> voice=False. La senal existia."""
    ef = _ef(monkeypatch)
    ef.say("🩸 EARNINGS-FALL TGTX -8.0%", "linea tecnica larga con score 68",
           voice=False, push=True, voice_msg="TGTX cayó fuerte tras resultados. BUY.")
    lineas = embudo()
    assert len(lineas) == 1
    titulo, cuerpo = _partes(lineas[0])
    assert titulo == "🩸 EARNINGS-FALL TGTX -8.0%"
    assert cuerpo == "TGTX cayó fuerte tras resultados. BUY."   # corto, no la linea tecnica
    assert L.classify(lineas[0])[0] == "earnings-catalizadores"


def test_earnings_el_gate_de_ruido_sigue_en_pie():
    """SCORE_FEED + un aviso por simbolo y dia: 3 lineas en 12 sesiones medidas."""
    src = open(os.path.join(SCRIPTS, "earnings_fall_scout.py")).read()
    assert 'if c["sym"] in alerted or (c["score"] or 0) < SCORE_FEED:' in src
    assert "push=True" in src


# --- chart_bridge: la ficha de zona solo salia del navegador ----------------------------
def test_ficha_de_zona_va_al_embudo():
    """chart_bridge exige py>=3.10 (venv-chart): contrato verificado en el fuente."""
    src = open(os.path.join(SCRIPTS, "chart_bridge.py")).read()
    cuerpo = src.split("def _signals_file_line")[1].split("\ndef ")[0]
    assert "import notify_short" in cuerpo
    assert 'notify_short.push(f"🎯 ZONA {sym.upper()}", text[:180])' in cuerpo
    # la guarda de MOCK esta ANTES: un feed sintetico no puede empujar al telefono
    assert cuerpo.index("if MOCK:") < cuerpo.index("notify_short.push")


def test_ficha_de_zona_enruta_segun_el_veredicto():
    """Los DOS veredictos que emite order_ticket.build tienen canal propio y ninguno cae en
    el fallback: la operable a #opciones-contratos, la muerta a #senales-rechazadas (privado,
    para poder auditar el veto). Textos literales de order_ticket.py:131 y :135-137."""
    nogo = ("🎯 ZONA NVDA | 🔴 NVDA 207.5C 0DTE — sin bid/ask válido (ilíquido), "
            "OI 35436. NO-GO. No cotizable.")
    go = ("🎯 ZONA MU | 🟢 COMPRA 1x MU 800C 0DTE @ límite $1.25 (prima $125, spread 4%, "
          "OI 900, prob 61%) — GO. Ejecuta TÚ en IBKR.")
    assert L.classify(go)[0] == "opciones-contratos"
    assert L.classify(nogo)[0] == "senales-rechazadas"
    for linea in (go, nogo):
        assert L.classify(linea)[0] != L.FALLBACK_CHANNEL


def test_ficha_de_zona_conserva_la_histeresis():
    src = open(os.path.join(SCRIPTS, "chart_bridge.py")).read()
    assert "ZONE_REFIRE_S = 30" in src
    assert "if now - state._zone_fired.get(zid, 0) < ZONE_REFIRE_S:" in src


def test_estructural_sigue_FUERA_del_embudo():
    """179 pin + 52 magnet el 08-03, hit 0.041 vs null 0.021 (KILL en el backtest).
    Si alguien la enchufa, este test lo caza."""
    src = open(os.path.join(SCRIPTS, "chart_bridge.py")).read()
    cuerpo = src.split("def _log_structural")[1].split("\ndef ")[0]
    assert "notify_short" not in cuerpo


# --- planes diarios -> Discord ----------------------------------------------------------
def test_dailyplans_publica_los_planes_en_discord():
    src = open(os.path.join(SCRIPTS, "dailyplans_run.sh")).read()
    assert "scripts/discord_post.py --plans --status" in src
    # solo en la pasada FULL de las 04:00, no en REFRESH ni APERTURA
    bloque = src.split("if [[ $MODE == FULL ]]; then")[-1]
    assert "discord_post.py" in bloque.split("\nfi\n")[0]


def test_dailyplans_no_puede_abortar_por_discord():
    """Redirigido al log: sin webhooks imprime ROTO y el 4AM sigue."""
    src = open(os.path.join(SCRIPTS, "dailyplans_run.sh")).read()
    linea = [ln for ln in src.splitlines()
             if "discord_post.py" in ln and not ln.lstrip().startswith("#")][0]
    assert ">> logs/dailyplans.log 2>&1" in linea
    assert "set -e" not in src


# --- no-regresion del embudo -------------------------------------------------------------
def test_ningun_titulo_nuevo_pisa_una_regla_mas_especifica():
    """Orden de RULES: la primera que casa gana. Ningun titulo nuevo puede robar
    alertas a #criticas ni a #manada."""
    assert L.classify("🕳 MANADA MUDA | solo 21 de 30 votan")[0] == "manada"
    assert L.classify("🐘 MANADA ALCISTA | 25/30 alineados")[0] == "manada"
    assert L.classify("🇰🇷 KRX NAVER BRIDGE CIEGO | Corea sin datos")[0] == "estado-proveedores"
    assert L.classify("🇰🇷 KOSPI TERREMOTO ALZA | CUSUM +2%")[0] == "criticas"


class _SubprocessMudo(object):
    """Sustituto de subprocess dentro de un productor: Popen registra y no ejecuta."""

    def __init__(self):
        self.llamadas = []
        self.DEVNULL = -3

    def Popen(self, *a, **kw):
        self.llamadas.append(a)
        return None


def test_finnhub_helper_conserva_throttle_pero_caidas_no_lo_invocan():
    """El helper manual conserva throttle; la orden 2026-08-06 apagó el push automático."""
    src = open(os.path.join(SCRIPTS, "finnhub_ws_bridge.py")).read()
    assert "_PUSH_THROTTLE_S" in src and "_ultimo_push" in src
    assert "except Exception" in src.split("def grita")[1].split("\ndef ")[0]
    main = src.split("async def main", 1)[1]
    assert "grita(" not in main and "notify_short" not in main


def test_korea_no_grita_con_krx_cerrado():
    """Naver en mantenimiento a mediodia US no es una emergencia coreana."""
    src = open(os.path.join(SCRIPTS, "korea_naver_bridge.py")).read()
    assert "def krx_en_horario" in src
    assert "fallos == FAILS_LOUD and krx_en_horario()" in src


def test_korea_krx_en_horario_es_correcto():
    import importlib.util as _il
    sp = _il.spec_from_file_location("ibt_knb_t", os.path.join(SCRIPTS, "korea_naver_bridge.py"))
    knb = _il.module_from_spec(sp)
    sp.loader.exec_module(knb)
    import calendar, time as _t
    # martes 2026-08-04 11:00 KST = lunes 2026-08-04 02:00 UTC
    kst_11 = calendar.timegm((2026, 8, 4, 2, 0, 0, 0, 0, 0))
    assert knb.krx_en_horario(kst_11) is True
    # martes 2026-08-04 17:00 KST (cerrado)
    kst_17 = calendar.timegm((2026, 8, 4, 8, 0, 0, 0, 0, 0))
    assert knb.krx_en_horario(kst_17) is False
    # sabado KST
    kst_sab = calendar.timegm((2026, 8, 8, 2, 0, 0, 0, 0, 0))
    assert knb.krx_en_horario(kst_sab) is False


def test_chart_bridge_capa_el_push_de_zona():
    """120/h posibles con el precio serruchando la zona; el embudo se capa a N/dia/simbolo."""
    src = open(os.path.join(SCRIPTS, "chart_bridge.py")).read()
    assert "ZONE_PUSH_MAX_DIA" in src and "_ZONE_PUSHED" in src
    assert "if d not in sys.path" in src                   # sin duplicar sys.path por disparo
