"""Tests de notify_relay.sh (TODO 32 dedup-tras-cap, TODO 20 privacidad por config).

Arnes real: se lanza el zsh con overrides de env (funnel/log/priv/cap) y un `curl` stub en
PATH que captura los envios — cero red, cero ficheros reales del repo.
"""
import os
import re
import signal
import subprocess
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY = os.path.join(REPO, "scripts", "notify_relay.sh")
sys.path.insert(0, os.path.join(REPO, "scripts"))
import discord_layout as L  # noqa: E402


def _stamp():
    # Sello del minuto SIGUIENTE: edad negativa (>-60) pasa frescura sin depender del segundo.
    lt = time.localtime(time.time() + 60)
    return "%02d:%02d:00" % (lt.tm_hour, lt.tm_min)


def _wait(fn, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fn():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def relay(tmp_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    curl_log = tmp_path / "curl.log"
    c = stub / "curl"
    c.write_text('#!/bin/sh\necho "$@" >> "%s"\nprintf 204\n' % curl_log)
    c.chmod(0o755)
    funnel = tmp_path / "push.txt"
    funnel.write_text("")
    rlog = tmp_path / "relay.log"
    priv = tmp_path / "priv.txt"
    priv.write_text("# test\nSECRETO_TEST\nrealizedPnl\n")
    env = dict(os.environ)
    env.update({
        "PATH": "%s:%s" % (stub, env["PATH"]),
        "NOTIFY_PUSH_FILE": str(funnel),
        "NOTIFY_RELAY_LOG": str(rlog),
        "NOTIFY_PRIVATE_FILE": str(priv),
        # Hermetico (2026-08-23): el interruptor data/notify_off del operador NO debe decidir
        # si los tests pasan — apuntamos el apagado a un path que nunca existe en el sandbox.
        "NOTIFY_OFF_FILE": str(tmp_path / "notify_off"),
        "NOTIFY_CAP_S": "2",
        "NOTIFY_DEDUP_S": "60",
        "NTFY_TOPIC": "test-topic",
    })
    p = subprocess.Popen(["/bin/zsh", RELAY], env=env, cwd=REPO,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    time.sleep(1.0)  # que el tail -F arranque antes del primer append
    yield funnel, rlog, curl_log
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        p.wait(timeout=5)
    except ProcessLookupError:
        pass  # el relay ya murio solo (p.ej. apagado): no enmascarar el fallo real del test


def _push(funnel, title, body):
    with open(funnel, "a") as f:
        f.write("%s | %s | %s\n" % (_stamp(), title, body))


def test_capado_se_reenvia_sin_morir_en_dedup(relay):
    """TODO 32: el dedup se registra SOLO tras envio OK; un capado reintenta en <60s."""
    funnel, rlog, curl_log = relay
    _push(funnel, "T UNO", "abre la ventana")
    assert _wait(lambda: curl_log.exists() and "abre la ventana" in curl_log.read_text())
    _push(funnel, "T DOS", "taiwan despega")  # dentro del cap de 2s -> CAP
    assert _wait(lambda: rlog.exists() and "CAP 1/2s" in rlog.read_text())
    assert "taiwan despega" not in curl_log.read_text()
    time.sleep(2.2)  # pasa el cap, sigue MUY dentro del dedup de 60s
    _push(funnel, "T DOS", "taiwan despega")
    assert _wait(lambda: "taiwan despega" in curl_log.read_text()), \
        "el reintento tras el cap murio en DEDUP_AT (bug TODO 32)"
    assert len(re.findall("taiwan despega", curl_log.read_text())) == 1


def test_privada_por_config_no_sale_del_mac(relay):
    """TODO 20: patron del fichero de config (no hardcode) manda la linea a PRIVADA."""
    funnel, rlog, curl_log = relay
    _push(funnel, "SECRETO_TEST", "pnl +5 en NOK")
    assert _wait(lambda: rlog.exists() and "PRIVADA (solo local)" in rlog.read_text())
    assert "pnl" not in (curl_log.read_text() if curl_log.exists() else "")


def test_dedup_sigue_funcionando_tras_envio(relay):
    """El fix no rompe el dedup normal: dos envios identicos en 60s = uno solo."""
    funnel, rlog, curl_log = relay
    _push(funnel, "T TRES", "mu rebota")
    assert _wait(lambda: curl_log.exists() and "mu rebota" in curl_log.read_text())
    time.sleep(2.2)  # fuera del cap: solo el dedup puede frenarla
    _push(funnel, "T TRES", "mu rebota")
    time.sleep(1.5)
    assert len(re.findall("mu rebota", curl_log.read_text())) == 1


def test_infra_repetida_se_reduce_a_una_por_hora(relay):
    """La telemetría repetitiva queda en Discord estado; el teléfono recibe una/hora."""
    funnel, _rlog, curl_log = relay
    _push(funnel, "🕳 CINTA CIEGA", "sin prints 10m")
    assert _wait(lambda: curl_log.exists() and "CINTA CIEGA" in curl_log.read_text())
    time.sleep(2.2)
    _push(funnel, "🕳 CINTA CIEGA", "sin prints 11m")
    time.sleep(1.5)
    assert len(re.findall("CINTA CIEGA", curl_log.read_text())) == 1


def test_fallo_http_no_se_declara_enviado_y_permite_reintento(relay):
    funnel, rlog, curl_log = relay
    # Sustituir el stub mientras el relay corre: primera entrega falla, segunda funciona.
    curl = curl_log.parent / "bin" / "curl"
    curl.write_text('#!/bin/sh\necho "$@" >> "%s"\nprintf 503\n' % curl_log)
    curl.chmod(0o755)
    _push(funnel, "T HTTP", "prueba verificable")
    assert _wait(lambda: rlog.exists() and "FALLO ntfy HTTP 503" in rlog.read_text())
    curl.write_text('#!/bin/sh\necho "$@" >> "%s"\nprintf 204\n' % curl_log)
    curl.chmod(0o755)
    time.sleep(2.2)
    _push(funnel, "T HTTP", "prueba verificable")
    assert _wait(lambda: "ENVIADA ntfy=204" in rlog.read_text())


# --- discord_layout.is_private: patrones desde config -------------------------------------
def test_layout_privado_lee_config(tmp_path, monkeypatch):
    p = tmp_path / "priv.txt"
    p.write_text("# c\nSECRETO_LAYOUT\n")
    monkeypatch.setattr(L, "PRIV_FILE", str(p))
    rx = L._priv_regex()
    assert rx.search("10:00:00 | SECRETO_LAYOUT | x")
    assert not rx.search("🎈 BB REBOTE | mu")


def test_layout_privado_sin_config_usa_respaldo(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "PRIV_FILE", str(tmp_path / "no-existe.txt"))
    rx = L._priv_regex()
    assert rx.search("🚨 order_engine | open AAPL NO enviado")
    assert rx.search("cuenta | U26942420 posiciones abiertas 2")


def test_layout_privado_produccion_cubre_titulos_reales():
    """El PRIVADO de PRODUCCION (fichero config presente o fallback embebido si fue borrado,
    p.ej. en la limpieza REGLA CERO del 2026-08-23) cubre los titulos reales."""
    for linea in ("🚨 order_engine | open AAPL NO enviado",
                  "⏰ EXPIRA HOY | Tu opción de AAPL 300P vence hoy",
                  "NOK CERRADA | SELL 1 @ 8.90 realizedPnl +0.35 comisión 0.09"):
        assert L.is_private(linea), linea
