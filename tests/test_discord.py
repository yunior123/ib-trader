"""Tests del puente Discord: enrutado, saneado, dedup y contratos de fichero.

Cero red: todo lo que sale a Discord se monkeypatchea. Un test que dispare un POST real
publicaria en el servidor de Yunior cada vez que corre la suite.
"""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load("discord_layout")
S = _load("discord_send")
W = _load("discord_webhooks")
C = _load("discord_client")
R = _load("discord_relay")


# --- estructura ------------------------------------------------------------------------
def test_todo_canal_de_regla_existe_en_la_estructura():
    """Una regla que enruta a un canal inexistente pierde la alerta en silencio."""
    declarados = set(L.all_channel_keys())
    for _, ch, _ in L.RULES:
        assert ch in declarados, "regla enruta a #%s, que no existe en CATEGORIES" % ch
    assert L.FALLBACK_CHANNEL in declarados
    for ch, _ in L.MIRRORS:
        assert ch in declarados


def test_no_hay_claves_de_canal_duplicadas():
    keys = L.all_channel_keys()
    assert len(keys) == len(set(keys))


def test_canales_con_webhook_son_subconjunto_de_los_declarados():
    assert L.webhook_channels() <= set(L.all_channel_keys())


def test_nombres_de_canal_validos_para_discord():
    """Discord exige minusculas, sin espacios, <=100 caracteres."""
    for k in L.all_channel_keys():
        assert k == k.lower() and " " not in k and 1 <= len(k) <= 100


# --- enrutado --------------------------------------------------------------------------
@pytest.mark.parametrize("linea,canal", [
    ("🚨 order_engine | orden rechazada", "criticas"),
    ("🌋 TERREMOTO | qqq se desploma", "criticas"),
    ("🐋 ALERTA BALLENA CALLS | mu 37k calls", "ballenas-flujo"),
    ("🚀 SPIKE CALLS TSLA | premium x4", "ballenas-flujo"),
    ("🐺 MANADA A PUTS | 5 de 30", "manada"),
    ("FINVIZ BUFFETT · WEATHER · BUY 1 SELL 0 | FSLR BUY $234", "finviz-screeners"),
    ("🇰🇷 KRX BRIDGE SIN GATEWAY | sin puerto", "estado-proveedores"),
    ("INTRINIO WS | socket CAIDO en overnight", "estado-proveedores"),
    ("🕳 CINTA CIEGA | smh sin barras", "estado-proveedores"),
    ("🎈 BB REBOTE | mu puede bajar un poco.", "senales-flota"),
    ("🎯 APERTURA FUERA DE BANDA | nvda", "senales-flota"),
    ("⏰ EXPIRA HOY | qqq 580C", "earnings-catalizadores"),
])
def test_clasificacion_de_titulos_reales(linea, canal):
    assert L.classify(linea)[0] == canal


def test_sistema_gana_a_corea_cuando_es_infraestructura():
    """KRX SIN GATEWAY lleva bandera coreana pero es un fallo de feed, no una senal."""
    ch, sev = L.classify("🇰🇷 KRX BRIDGE SIN GATEWAY | sin puerto 4001")
    assert ch == "estado-proveedores" and sev == L.SISTEMA


def test_critica_gana_a_ballena():
    """Una ballena dentro de un mensaje critico sigue siendo critica: el orden de RULES manda."""
    assert L.classify("🚨 DANGER | 🐋 ballena puts masiva")[0] == "criticas"


def test_lo_no_reconocido_va_al_fallback_y_nunca_se_pierde():
    ch, sev = L.classify("XYZ MENSAJE NUEVO | algo que nadie previo")
    assert ch == L.FALLBACK_CHANNEL and sev == L.SISTEMA


def test_severidad_critica_solo_para_lo_critico():
    assert L.classify("🎈 BB REBOTE | mu sube")[1] == L.NORMAL
    assert L.classify("🚨 x | y")[1] == L.CRITICA


# --- espejos por simbolo ---------------------------------------------------------------
def test_espejo_spy_qqq():
    uni = {"QQQ", "SPY", "MU", "NVDA"}
    assert "spy-qqq" in L.mirror_channels("🎈 BB REBOTE | qqq puede bajar un poco.", uni)


def test_espejo_semis():
    uni = {"MU", "QQQ"}
    assert L.mirror_channels("🐋 BALLENA | mu 37k calls", uni) == ["semis-memoria"]


def test_simbolo_solo_como_palabra_suelta():
    """'MUCHO' no es MU. Sin esto, cada palabra con el ticker dentro dispara un espejo falso."""
    assert L.symbols_in("hay MUCHO volumen", {"MU"}) == []
    assert L.symbols_in("MU rompe", {"MU"}) == ["MU"]


def test_relay_no_espeja_lo_de_sistema():
    """El ruido de infraestructura no debe inundar las watchlists."""
    _, sev, mirrors = R.route("INTRINIO WS", "socket CAIDO qqq", {"QQQ"})
    assert sev == L.SISTEMA and mirrors == []


# --- saneado y formato -----------------------------------------------------------------
def test_sanitize_neutraliza_menciones_masivas():
    """Se parte el token con un ancho-cero: Discord ya no lo lee como mencion masiva."""
    for txt in ("@everyone corre", "@here mira", "@EveryOne"):
        out = S.sanitize(txt)
        assert "@everyone" not in out.lower() and "@here" not in out.lower()
        assert "​" in out


def test_sanitize_conserva_el_texto_legible():
    assert "corre" in S.sanitize("@everyone corre")


def test_embed_respeta_los_topes_de_discord():
    emb = S.build_embed("T" * 400, "B" * 9000, L.NORMAL)
    assert len(emb["title"]) <= 256 and len(emb["description"]) <= 4096


def test_color_por_direccion():
    assert S.build_embed("🎈 BB", "mu puede subir", L.NORMAL)["color"] == L.ALCISTA_COLOR
    assert S.build_embed("🎈 BB", "mu puede bajar", L.NORMAL)["color"] == L.BAJISTA_COLOR
    assert S.build_embed("x", "y", L.CRITICA)["color"] == L.SEV_COLOR[L.CRITICA]


def test_ambiguo_no_inventa_direccion():
    """Un texto con calls Y puts no tiene direccion: azul neutro, no una apuesta fabricada."""
    assert S.build_embed("x", "calls y puts a la vez", L.NORMAL)["color"] == L.NEUTRO_COLOR


def test_send_sin_webhook_devuelve_motivo_no_excepcion():
    ok, err = S.send("criticas", S.build_embed("t", "b"), hooks={})
    assert ok is False and "webhook" in err


def test_send_no_publica_mensaje_vacio():
    ok, err = S.send("criticas", embed=None, content=None, hooks={"criticas": "https://x"})
    assert ok is False and "vacio" in err


def test_send_desactiva_menciones_por_defecto(monkeypatch):
    capt = {}

    def fake_post(url, body, headers):
        capt.update(json.loads(body.decode()))
        return True, None

    monkeypatch.setattr(S, "_post", fake_post)
    S.send("criticas", S.build_embed("t", "@everyone b"), hooks={"criticas": "https://x"})
    assert capt["allowed_mentions"] == {"parse": [], "roles": []}


def test_send_menciona_solo_el_rol_declarado(monkeypatch):
    capt = {}
    monkeypatch.setattr(S, "_post",
                        lambda u, b, h: (capt.update(json.loads(b.decode())), (True, None))[1])
    S.send("criticas", S.build_embed("t", "b"), mention_role_id="999",
           hooks={"criticas": "https://x"})
    assert capt["allowed_mentions"]["roles"] == ["999"] and "<@&999>" in capt["content"]


def test_send_long_trocea_sin_perder_texto(monkeypatch):
    trozos = []
    monkeypatch.setattr(S, "send",
                        lambda ch, emb, **kw: (trozos.append(emb["description"]), (True, None))[1])
    texto = "\n".join("linea %d" % i for i in range(2000))
    ok, _ = S.send_long("backtests", "T", texto)
    assert ok and len(trozos) > 1
    assert "".join(t.replace("\n", "") for t in trozos) == texto.replace("\n", "")


# --- relay -----------------------------------------------------------------------------
def test_parse_del_formato_del_embudo():
    p = R.parse("15:29:41 | 🎈 BB REBOTE | mu puede bajar un poco.")
    assert p is not None
    age, title, body = p
    assert title == "🎈 BB REBOTE" and body == "mu puede bajar un poco."


def test_parse_rechaza_basura():
    assert R.parse("linea sin formato") is None
    assert R.parse("") is None


def test_mention_solo_en_criticas():
    ids = {L.MENTION_ROLE: "42"}
    assert R.mention_id(ids, L.CRITICA) == "42"
    assert R.mention_id(ids, L.NORMAL) is None
    assert R.mention_id(ids, L.SISTEMA) is None


def test_mention_sin_rol_no_revienta():
    assert R.mention_id({}, L.CRITICA) is None


def test_prioridad_reconoce_lo_que_salta_el_cap():
    for t in ("SELL ahora", "STOP tocado", "TERREMOTO", "DANGER", "🌋", "🚨"):
        assert R.PRIORIDAD.search(t)
    assert not R.PRIORIDAD.search("🎈 BB REBOTE mu")


# --- secretos ---------------------------------------------------------------------------
def test_redact_tapa_el_token(monkeypatch):
    monkeypatch.setattr(C, "secret", lambda n: "SUPERSECRETO123456" if n == "DISCORD_BOT_TOKEN" else None)
    out = C.redact("fallo con token SUPERSECRETO123456 dentro")
    assert "SUPERSECRETO123456" not in out and "<DISCORD_BOT_TOKEN>" in out


def test_redact_aguanta_none():
    assert C.redact(None) is None


def test_mask_de_webhook_no_filtra_el_token():
    url = "https://discord.com/api/webhooks/123456789/tokenSUPERsecreto"
    assert "tokenSUPERsecreto" not in W.mask(url)


def test_store_de_webhooks_se_guarda_con_permisos_600(tmp_path):
    p = str(tmp_path / "h.json")
    W.save({"criticas": "https://discord.com/api/webhooks/1/x"}, p)
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    assert W.load(p)["criticas"].endswith("/x")


def test_load_de_webhooks_inexistente_no_revienta(tmp_path):
    assert W.load(str(tmp_path / "no-existe.json")) == {}


def test_secret_vacio_devuelve_none(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
    monkeypatch.setattr(C, "_feeds_env", lambda: {})
    assert C.token() is None


# --- contrato con el embudo real ---------------------------------------------------------
def test_el_embudo_real_se_enruta_entero():
    """Contra data/notify_push.txt de verdad: ninguna linea puede caer al fallback en masa."""
    path = os.path.join(REPO, "data", "notify_push.txt")
    if not os.path.exists(path):
        pytest.skip("sin data/notify_push.txt en esta maquina")
    with open(path, errors="replace") as f:
        lineas = [l for l in f if R.parse(l)]
    if len(lineas) < 50:
        pytest.skip("embudo demasiado corto para medir")
    sin_clasificar = sum(1 for l in lineas
                         if L.classify(l)[0] == L.FALLBACK_CHANNEL)
    ratio = sin_clasificar / float(len(lineas))
    assert ratio < 0.05, "%.1f%% de las lineas reales sin regla (%d de %d)" % (
        ratio * 100, sin_clasificar, len(lineas))


def test_confluencia_gana_a_senales_flota():
    """'🔗 FLUJO + BB QQQ' lleva 'BB' dentro: sin prioridad caeria en senales-flota."""
    assert L.classify("🔗 FLUJO + BB QQQ | flujo y banda de acuerdo")[0] == "confluencia"


def test_capitan_tiene_canal_propio():
    assert L.classify("🎖 CAPITAN REVIERTE SMH | puts del capitan")[0] == "capitanes"


# --- resolucion por ID: renombrar un canal no debe crear un duplicado huerfano ------------
def test_resolve_prefiere_el_id_cacheado_sobre_el_nombre():
    """Si #criticas se renombra a #critical, el id sigue apuntando al canal con su historial."""
    chans = [{"id": "111", "name": "critical", "type": 0},
             {"id": "222", "name": "criticas", "type": 0}]
    assert L.resolve("criticas", chans, {"criticas": "111"})["id"] == "111"


def test_resolve_cae_al_nombre_sin_cache():
    chans = [{"id": "222", "name": "criticas", "type": 0}]
    assert L.resolve("criticas", chans, {})["id"] == "222"


def test_resolve_id_rancio_no_impide_encontrar_por_nombre():
    """Canal borrado a mano: el id cacheado ya no existe, pero el nombre sigue valiendo."""
    chans = [{"id": "333", "name": "criticas", "type": 0}]
    assert L.resolve("criticas", chans, {"criticas": "borrado"})["id"] == "333"


def test_resolve_devuelve_none_si_no_existe():
    assert L.resolve("criticas", [], {}) is None


def test_resolve_respeta_el_tipo():
    """Una categoria y un canal de texto pueden llamarse igual: el tipo desempata."""
    chans = [{"id": "1", "name": "analisis", "type": 4}]
    assert L.resolve("analisis", chans, {}, 0) is None
    assert L.resolve("analisis", chans, {}, 4)["id"] == "1"


def test_ids_se_guardan_atomicos(tmp_path):
    p = str(tmp_path / "ids.json")
    L.save_ids({"criticas": "111"}, p)
    assert L.load_ids(p) == {"criticas": "111"}
    assert not os.path.exists(p + ".tmp")


def test_load_ids_inexistente_no_revienta(tmp_path):
    assert L.load_ids(str(tmp_path / "nada.json")) == {}


# --- alertas de OPCIONES separadas (Yunior 2026-08-04, referencia Spartan Trading) ----------
@pytest.mark.parametrize("linea", [
    "🟢 NVDA CALL BOUNCE | NVDA BOUNCE en abs_wall 210 — 🟢 GO 212C 0DTE @1.85 | OPCIONES OK (spread 2%)",
    "🟡 MU PUT RETEST_REJECT | ficha CAUTION 180P @0.95 | OPCIONES OK (spread 4%)",
])
def test_la_ficha_operable_va_a_su_canal_de_opciones(linea):
    """order_ticket arma un CONTRATO ejecutable; no puede diluirse entre las senales de precio."""
    assert L.classify(linea)[0] == "opciones-contratos"


@pytest.mark.parametrize("linea", [
    "🔴 QQQ CALL BOUNCE | 🔴 NO-GO — sale muy caro | OPCIONES VETADAS spread 15% — usar ACCIONES",
    "🔴 SPY PUT BREAK | ❌ SPY: sin cadena — no puedo armar ficha | OPCIONES s/d (sin cadena fresca)",
    "🔴 NVDA CALL BOUNCE | 🔴 NVDA 177.5C 0DTE — sin bid/ask válido (ilíquido), OI 26. NO-GO.",
    "🔴 MU PUT BREAK | ❌ MU: sin puts 0DTE en la cadena",
])
def test_la_ficha_RECHAZADA_no_ensucia_el_canal_de_opciones(linea):
    """Un NO-GO no es una idea: es una idea muerta. Se archiva para auditar el veto, no se canta.

    Medido en Spartan Trading (docs/DISCORD-REFERENCIA-2026-08-04.md): 11 ideas de opciones al
    dia en una sala de pago. Un canal de contratos lleno de vetos deja de leerse.
    """
    ch, sev = L.classify(linea)
    assert ch == "senales-rechazadas" and sev == L.SISTEMA


def test_ballena_calls_no_se_va_al_canal_de_opciones():
    """'🐋 ALERTA BALLENA CALLS' lleva CALLS pero es FLUJO, no un contrato operable."""
    assert L.classify("🐋 ALERTA BALLENA CALLS | mu 37k calls")[0] == "ballenas-flujo"


def test_spike_calls_sigue_en_flujo():
    assert L.classify("🚀 SPIKE CALLS TSLA | premium x4")[0] == "ballenas-flujo"


def test_critica_sigue_ganando_a_la_ficha():
    assert L.classify("🚨 DANGER | NO-GO en todo, OPCIONES VETADAS")[0] == "criticas"


# --- un test JAMAS notifica al humano (bug medido 2026-08-04: 52 alarmas reales) -----------
def test_notify_short_no_publica_bajo_pytest():
    """Si esto falla, `pytest tests/` vuelve a mandar DANGER a ntfy, email y Discord."""
    import importlib.util as _il
    sp = _il.spec_from_file_location("ibt_notify_short_t",
                                     os.path.join(SCRIPTS, "notify_short.py"))
    ns = _il.module_from_spec(sp)
    sp.loader.exec_module(ns)
    antes = os.path.getsize(ns.PATH) if os.path.exists(ns.PATH) else 0
    ns.push("🕳 CINTA CIEGA", "esto NO puede llegar al embudo desde un test")
    despues = os.path.getsize(ns.PATH) if os.path.exists(ns.PATH) else 0
    assert ns.under_pytest() is True
    assert despues == antes, "notify_short escribio en el embudo real durante la suite"


# --- reglas R1-R8 de la auditoria de cobertura (2026-08-04) --------------------------------
@pytest.mark.parametrize("linea,canal", [
    ("QQQ: BUY 683.20 tp 685 (compass UP)", "senales-flota"),        # R1: los 21 bots C++
    ("MU: SELL 178.9 (STOP)", "criticas"),                           # STOP mayuscula = evento
    ("STOP tocado | fuera de NVDA", "criticas"),
    ("🎯 ZONA NVDA | compra 212.5 stop 211", "senales-flota"),       # stop minuscula = precio
    ("🚨 ALARMA PRECIO | SPY 630 impreso", "criticas"),              # R2
    ("🛑 SCALPER | stop del scalper", "criticas"),                   # R5
    ("🐻 READ-THROUGH | kospi -3% -> semis", "corea-overnight"),     # R3
    ("🔪 VETO | capitan coreano en contra", "corea-overnight"),      # R3 antes que capitanes
    ("🎖 CAPITAN REVIERTE SMH | puts del capitan", "capitanes"),
    ("QQQ X-RAY | RETEST_REJECT en muro 690", "gamma-niveles"),      # R8
    ("DRAM GUARD | dram guard activo", "senales-flota"),             # R8
    ("X POSTED premarket | ok", "bot-logs"),                         # R7
    ("🩺 HEALTHCHECK | 3 criticos", "estado-flota"),                 # R7
    ("TA BUY | bargain FSLR", "finviz-screeners"),                   # R4
])
def test_reglas_de_la_auditoria_de_cobertura(linea, canal):
    assert L.classify(linea)[0] == canal


def test_stop_minuscula_de_ficha_no_es_critica():
    """El bug cazado el 2026-08-04: 'compra 212.5 stop 211' se iba a #criticas por \\bSTOP\\b."""
    ch, sev = L.classify("🎯 ZONA NVDA | compra 212.5 stop 211")
    assert sev != L.CRITICA


# --- frontera de medianoche (revision 2026-08-04): edad -86099 tiraba alertas frescas ------
def test_parse_a_medianoche_no_tira_la_alerta_de_ayer(monkeypatch):
    """A las 00:05, una linea de las 23:59 parecia del FUTURO y el filtro la descartaba."""
    import time as _t
    real_lt = _t.localtime
    madrugada = _t.mktime((2026, 8, 4, 0, 5, 0, 1, 216, 1))
    monkeypatch.setattr(R.time, "localtime", lambda: real_lt(madrugada))
    monkeypatch.setattr(R.time, "time", lambda: madrugada)
    p = R.parse("23:59:00 | 🚨 DANGER | qqq rompe")
    assert p is not None
    age = p[0]
    assert 300 <= age <= 400, "la linea de las 23:59 debe tener ~6 min, no -24h (age=%s)" % age


def test_parse_no_desplaza_lineas_normales(monkeypatch):
    import time as _t
    real_lt = _t.localtime
    tarde = _t.mktime((2026, 8, 4, 15, 30, 0, 1, 216, 1))
    monkeypatch.setattr(R.time, "localtime", lambda: real_lt(tarde))
    monkeypatch.setattr(R.time, "time", lambda: tarde)
    age = R.parse("15:29:30 | 🎈 BB REBOTE | mu")[0]
    assert 25 <= age <= 35


# --- PRIVACIDAD (Yunior 2026-08-04): lo nuestro no sale del Mac ----------------------------
@pytest.mark.parametrize("linea", [
    "🚨 order_engine | orden rechazada por safety",
    "⏰ EXPIRA HOY | NOK 10C queda 1 dia",
    "NOK CERRADA | SELL 1 @ 8.90 realizedPnl +0.35 comision 0.09",
    "cuenta | U26942420 posiciones abiertas 2",
    "ORDEN ENVIADA | QQQ 709C limite 5.31",
])
def test_lo_personal_es_privado(linea):
    assert L.is_private(linea) is True


@pytest.mark.parametrize("linea", [
    "UW FLOW TSLA | PUTS bid-side strike 322.5 — vol/OI 26.9 (posicion nueva) $534k",
    "🎈 BB REBOTE | mu puede bajar un poco.",
    "FINVIZ BUFFETT · WEATHER · BUY 1 | FSLR BUY $234",
    "🐋 ALERTA BALLENA CALLS | mu 37k calls",
])
def test_el_dato_de_mercado_no_es_privado(linea):
    """'posicion nueva' del vendor es vol/OI de MERCADO, no nuestra posicion."""
    assert L.is_private(linea) is False
