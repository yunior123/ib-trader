"""notify_short.py — sidecar de notificaciones CORTAS (Yunior 2026-07-28: "los mensajes en
notificaciones deben ser cortos y precisos, en ntfy, macos, all over, keep it simple").

`data/trading-signals/<fecha>.txt` sigue con el mensaje COMPLETO — lo leen signals_db.py,
regen_signals.py, signal_conditioning.py, eod_signal_validation.py, options_enrich.py,
x_signal_poster.py y no se toca. Este fichero aparte (`data/notify_push.txt`) es SOLO lo que
de verdad se le mostro al humano (voz+banner ya disparados): notify_relay.sh lo sigue en vez
de re-derivar por regex sobre el log completo. Rotacion diaria implicita: se trunca a las
ultimas 500 lineas en cada escritura para que no crezca sin limite.
"""
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO, "data", "notify_push.txt")
MAX_LINES = 500


def push(title, corto):
    lt = time.localtime()
    line = f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {corto}"
    try:
        lines = []
        if os.path.exists(PATH):
            with open(PATH) as f:
                lines = f.readlines()[-(MAX_LINES - 1):]
        lines.append(line + "\n")
        tmp = PATH + f".tmp{os.getpid()}"
        with open(tmp, "w") as f:
            f.writelines(lines)
        os.replace(tmp, PATH)
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        push(sys.argv[1], sys.argv[2])
