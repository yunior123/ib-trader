"""test_finviz_auth_check.py — el token de Finviz caduca EN SILENCIO.

Lo que se prueba es la parte que decide, sin red: `judge()` (que convierte una
respuesta HTTP en sano/caducado) y `effective_token()` (que dice cual de los dos
tokens usara DE VERDAD la flota).

El caso que da sentido al fichero entero: Finviz **no devuelve 401** cuando el token
caduca — devuelve 200 con el cuerpo vacio o una pagina de login. Un chequeo que solo
mirase el status code diria "sano" con la flota ciega.

Y el caso que se cazo el 2026-07-25: todos los consumidores prueban FINVIZ_AUTH3
ANTES que FINVIZ_AUTH, asi que poner el token nuevo solo en FINVIZ_AUTH no surte
efecto en nadie. Hay un test que lo fija para que no se vuelva a repetir.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import finviz_auth_check as fac  # noqa: E402

CAB = '"No.","Ticker","Company","Sector"'


def _csv(n):
    return "\n".join([CAB] + [f'{i},"SYM{i}","X","Tech"' for i in range(1, n + 1)])


# ---------- judge(): que es un token sano ----------

def test_200_con_filas_es_sano():
    sano, motivo = fac.judge(200, _csv(3))
    assert sano is True
    assert "3 filas" in motivo


def test_200_con_cuerpo_vacio_es_CADUCADO_no_sano():
    """EL caso real: Finviz no da 401, da 200 vacio. Mirar solo el status miente."""
    sano, motivo = fac.judge(200, "")
    assert sano is False
    assert "VACIO" in motivo


def test_200_con_pagina_de_login_es_caducado():
    sano, motivo = fac.judge(200, "<html><body>Please log in</body></html>")
    assert sano is False
    assert "cabecera CSV" in motivo


def test_200_con_menos_filas_de_las_pedidas_es_caducado():
    """3 simbolos pedidos, 1 devuelto = feed roto, no 'sano con poco dato'."""
    sano, motivo = fac.judge(200, _csv(1), min_rows=3)
    assert sano is False
    assert "1 filas" in motivo


def test_401_es_caducado():
    sano, motivo = fac.judge(401, "")
    assert sano is False
    assert "401" in motivo


def test_sin_respuesta_no_es_sano():
    sano, _ = fac.judge(None, "")
    assert sano is False


def test_solo_cabecera_sin_filas_es_caducado():
    sano, motivo = fac.judge(200, CAB)
    assert sano is False
    assert "0 filas" in motivo


# ---------- effective_token(): cual usa DE VERDAD la flota ----------

def test_AUTH3_gana_a_AUTH_porque_es_lo_que_leen_los_consumidores():
    """finviz_scout.cpp:91, x_whale_bot.cpp:366, options_hunter.py:34 prueban AUTH3 primero.

    Si este test se pone al reves, el token nuevo de Yunior deja de usarse en silencio.
    """
    tok, key, origen = fac.effective_token(
        env={}, files={"FINVIZ_AUTH3": "tres", "FINVIZ_AUTH": "uno"})
    assert (tok, key) == ("tres", "FINVIZ_AUTH3")
    assert origen == "fichero"


def test_sin_AUTH3_cae_a_AUTH():
    tok, key, _ = fac.effective_token(env={}, files={"FINVIZ_AUTH": "uno"})
    assert (tok, key) == ("uno", "FINVIZ_AUTH")


def test_el_entorno_manda_sobre_el_fichero():
    tok, key, origen = fac.effective_token(
        env={"FINVIZ_AUTH3": "del-entorno"}, files={"FINVIZ_AUTH3": "del-fichero"})
    assert tok == "del-entorno"
    assert origen == "entorno"


def test_sin_token_devuelve_None_no_cadena_vacia():
    """Ningun cero plausible: 'no hay token' no puede parecerse a 'token vacio valido'."""
    assert fac.effective_token(env={}, files={}) == (None, None, None)


def test_token_en_blanco_no_cuenta_como_token():
    tok, key, _ = fac.effective_token(env={}, files={"FINVIZ_AUTH3": "   ", "FINVIZ_AUTH": "uno"})
    assert (tok, key) == ("uno", "FINVIZ_AUTH")


# ---------- caducidad declarada ----------

def test_expiry_ausente_es_None_no_una_fecha_inventada():
    assert fac.declared_expiry(files={}) is None


def test_expiry_ilegible_es_None():
    assert fac.declared_expiry(files={"FINVIZ_AUTH_EXPIRES": "el sabado que viene"}) is None


def test_expiry_valida_se_parsea():
    assert fac.declared_expiry(
        files={"FINVIZ_AUTH_EXPIRES": "2026-08-01"}) == dt.date(2026, 8, 1)


# ---------- el orden real del repo, no el que creamos recordar ----------

def test_el_orden_declarado_coincide_con_el_de_los_consumidores():
    assert fac.TOKEN_KEYS == ("FINVIZ_AUTH3", "FINVIZ_AUTH")


def test_los_dos_ficheros_de_entorno_se_miran():
    assert set(fac.ENV_FILES) == {"feeds.env", "llm.env"}


# ---------- el veredicto que consume el healthcheck (funcion pura) ----------

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import fleet_healthcheck as fh  # noqa: E402

AHORA = 1_785_000_000


def _rec(**kw):
    base = {"sano": True, "token_cola": "8625", "clave_efectiva": "FINVIZ_AUTH3",
            "ts": AHORA, "dias_restantes": 7, "motivo": "3 filas"}
    base.update(kw)
    return base


def test_healthcheck_token_caducado_es_CRIT():
    nivel, msg = fh.finviz_token_status(rec=_rec(sano=False, motivo="HTTP 200 con cuerpo VACIO"),
                                        now=AHORA)
    assert nivel == "crit"
    assert "CADUCADO" in msg


def test_healthcheck_sin_registro_es_WARN_no_ok():
    """No saber NO es estar sano: un fichero ausente jamas puede dar verde."""
    nivel, msg = fh.finviz_token_status(path="/no/existe/nada.json", now=AHORA)
    assert nivel == "warn"
    assert "SIN COMPROBAR" in msg


def test_healthcheck_no_se_pudo_comprobar_es_WARN():
    nivel, _ = fh.finviz_token_status(rec=_rec(sano=None, motivo="sin red"), now=AHORA)
    assert nivel == "warn"


def test_healthcheck_registro_rancio_es_WARN():
    """Si el chequeo dejo de correr, el 'sano' de hace 3 dias no vale."""
    nivel, msg = fh.finviz_token_status(rec=_rec(ts=AHORA - 72 * 3600), now=AHORA)
    assert nivel == "warn"
    assert "sin correr" in msg


def test_healthcheck_avisa_dos_dias_antes():
    nivel, msg = fh.finviz_token_status(rec=_rec(dias_restantes=1), now=AHORA)
    assert nivel == "warn"
    assert "caduca en 1" in msg


def test_healthcheck_sano_es_ok():
    nivel, msg = fh.finviz_token_status(rec=_rec(), now=AHORA)
    assert nivel == "ok"
    assert "OK" in msg


def test_registro_ausente_se_considera_rancio():
    """Si nunca se ha comprobado, hay que comprobar — no dar por bueno el silencio."""
    assert fh.finviz_health_is_stale(path="/no/existe/nada.json") is True


def test_registro_fresco_no_se_recomprueba(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("{}")
    assert fh.finviz_health_is_stale(path=str(p)) is False


def test_registro_de_hace_un_dia_se_recomprueba(tmp_path):
    import os as _os
    p = tmp_path / "h.json"
    p.write_text("{}")
    viejo = _os.path.getmtime(str(p)) - 24 * 3600
    _os.utime(str(p), (viejo, viejo))
    assert fh.finviz_health_is_stale(path=str(p)) is True
