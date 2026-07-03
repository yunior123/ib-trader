"""notify_short.py — sidecar de notificaciones CORTAS (Yunior 2026-07-28: "los mensajes en
notificaciones deben ser cortos y precisos, en ntfy, macos, all over, keep it simple").

`data/trading-signals/<fecha>.txt` sigue con el mensaje COMPLETO — lo leen signals_db.py,
regen_signals.py, signal_conditioning.py, eod_signal_validation.py, options_enrich.py,
x_signal_poster.py y no se toca. Este fichero aparte (`data/notify_push.txt`) es SOLO lo que
de verdad se le mostro al humano (voz+banner ya disparados): notify_relay.sh lo sigue en vez
de re-derivar por regex sobre el log completo.

IMPORTANTE: append-only. La versión anterior reescribía un anillo de 500 líneas en CADA push;
`tail -F` detectaba el encogimiento/cambio de inode y releía el backlog completo. Eso produjo
305.845 descartes y un log de 196 MB en una semana. El relay rota a 20 MB; el productor nunca
reescribe ni hace read-modify-write, así que tampoco pierde alertas concurrentes.
"""
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO, "data", "notify_push.txt")


ALLOW_ENV = "IBT_NOTIFY_ALLOW_IN_TESTS"


def under_pytest():
    """True si estamos dentro de la suite y NO se ha pedido explicitamente escribir.

    La puerta es para los tests DE ESTE fichero, que verifican el append-only y la
    concurrencia y por tanto necesitan que push() escriba de verdad (en su tmp_path).
    Cualquier otro test la deja cerrada y no puede despertar a nadie.
    """
    if os.environ.get(ALLOW_ENV) == "1":
        return False
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "PYTEST_VERSION" in os.environ


OFF = os.path.join(REPO, "data", "notify_off")


def silenciado():
    """Interruptor duro de TODAS las notificaciones (Yunior 2026-08-23: "kill email, mac, all
    notifications, discord too"). Se comprueba en cada push, no al arrancar: crear o borrar el
    fichero surte efecto sin reiniciar nada.

    Bajo pytest NO aplica: quien impide que un test despierte al humano es under_pytest(), y los
    tests que la levantan a proposito escriben en su tmp_path, nunca en el embudo de produccion.
    Si el interruptor mandara aqui, apagar las notificaciones cambiaria lo que mide la suite."""
    if os.environ.get("PYTEST_CURRENT_TEST") or "PYTEST_VERSION" in os.environ:
        return False
    return os.path.exists(OFF)


def push(title, corto):
    # Un TEST jamas notifica al humano. Medido 2026-08-04: `pytest tests/` metio 52 alarmas
    # "🕳 CINTA CIEGA | No veo las ballenas de 3 acciones." en el embudo real -> ntfy, email y
    # (desde hoy) Discord. tests/test_whale_tape.py:110 parchea subprocess.Popen pero no esto,
    # y el monkeypatch.chdir no aisla nada porque PATH se deriva de __file__. Crying wolf puro:
    # es la regla 3 (senal marginal != decisiva) rota por nuestro propio arnes de test.
    if under_pytest():
        return
    if silenciado():
        return
    lt = time.localtime()
    line = f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {corto}"
    try:
        payload = (line.replace("\n", " ") + "\n").encode("utf-8", "replace")
        fd = os.open(PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        push(sys.argv[1], sys.argv[2])
