#!/usr/bin/env python3
"""ib_mode.py — FUENTE ÚNICA DE VERDAD del modo IBKR (paper vs live).

Yunior 2026-07-24: "make it easy to switch from one to the other and no bugs" +
"asegura que podemos leer options chain in both live and paper". Un solo archivo
manda: `data/ib_mode.txt` = "paper" | "live". Todo lector de TWS (opt_chain_cache,
el order_engine, cualquier bot) resuelve puerto/cuenta desde AQUÍ, sin hardcodear.

Mapa:  paper -> puerto 7497   |   live -> 7496.  La CUENTA sale de la config del
Override puntual: env IBKR_PORT (gana sobre el archivo) para pruebas.

CLI:  python3 scripts/ib_mode.py            -> imprime modo/puerto/cuenta
      python3 scripts/ib_mode.py paper|live -> cambia el modo (o usar ib_mode.sh)
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODE_FILE = os.path.join(REPO, "data", "ib_mode.txt")

# Puertos por modo. SOLO IB GATEWAY (orden Yunior 2026-07-27 "only ib gateway"):
# 4002 paper / 4001 live. TWS (7497/7496) queda FUERA del sondeo a proposito.
# Configurable sin tocar codigo: IBT_PAPER_PORTS / IBT_LIVE_PORTS = "4002,7497".
def _ports_env(key, default):
    got = [int(x) for x in os.environ.get(key, "").replace(";", ",").split(",")
           if x.strip().isdigit()]
    return got or default


PAPER_PORTS = _ports_env("IBT_PAPER_PORTS", [4002])
LIVE_PORTS = _ports_env("IBT_LIVE_PORTS", [4001])
PAPER_PORT, LIVE_PORT = PAPER_PORTS[0], LIVE_PORTS[0]   # primario (gateway) para display
# Cuenta del USUARIO, no del codigo (2026-07-25). Mismo orden que account_cfg.h:
# env -> config.json de la .app -> data/account.txt. Vacio = sin configurar.
def _acct(live):
    import json
    k = "IBTRADER_ACCOUNT_LIVE" if live else "IBTRADER_ACCOUNT_PAPER"
    if os.environ.get(k): return os.environ[k].strip()
    cfg = os.path.expanduser("~/Library/Application Support/ib-trader/config.json")
    try:
        j = json.load(open(cfg))
        sep = (j.get("accountLive" if live else "accountPaper") or "").strip()
        if sep: return sep
        a = (j.get("account") or "").strip()          # config vieja de una sola cuenta
        if a and (a.startswith("DU") != live): return a
    except Exception:
        pass
    try:
        want = "live=" if live else "paper="
        for ln in open(os.path.join(REPO, "data", "account.txt")):
            ln = ln.strip()
            if ln.startswith(want): return ln[len(want):].strip()
    except Exception:
        pass
    return ""

PAPER_ACCT, LIVE_ACCT = _acct(False), _acct(True)


def _listening(port):
    import socket
    s = socket.socket(); s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", int(port))); return True
    except Exception:
        return False
    finally:
        s.close()


def _ports_for(mode):
    return PAPER_PORTS if mode == "paper" else LIVE_PORTS


def any_up(mode):
    """¿Hay ALGÚN puerto (gateway o tws) escuchando para ese modo?"""
    return any(_listening(p) for p in _ports_for(mode))


def get_mode():
    """'paper' o 'live'. Default paper (seguro) si el archivo falta/está corrupto."""
    try:
        m = open(MODE_FILE).read().strip().lower()
        return m if m in ("paper", "live") else "paper"
    except Exception:
        return "paper"


def set_mode(mode):
    mode = (mode or "").strip().lower()
    if mode not in ("paper", "live"):
        raise ValueError("mode debe ser 'paper' o 'live'")
    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    tmp = MODE_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(mode + "\n")
    os.replace(tmp, MODE_FILE)          # atómico
    return mode


def get_port():
    """Puerto IBKR del modo. env IBKR_PORT gana. Si no, AUTO-DETECTA: el primer puerto
    del modo que esté escuchando (gateway 4002/4001 preferido, tws 7497/7496 fallback).
    Si ninguno escucha, devuelve el primario (gateway) para que el error sea claro."""
    ev = os.environ.get("IBKR_PORT") or os.environ.get("IB_PORT")
    if ev and ev.isdigit():
        return int(ev)
    ports = _ports_for(get_mode())
    for p in ports:
        if _listening(p):
            return p
    return ports[0]


def get_account():
    ev = os.environ.get("IBKR_ACCOUNT") or os.environ.get("IB_ACCOUNT")
    if ev:
        return ev
    return PAPER_ACCT if get_mode() == "paper" else LIVE_ACCT


def is_paper():
    return get_port() == PAPER_PORT


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            print(f"modo -> {set_mode(sys.argv[1])}")
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
    print(f"mode={get_mode()}  port={get_port()}  account={get_account()}"
          f"  (IBKR_PORT override={'sí' if (os.environ.get('IBKR_PORT') or os.environ.get('IB_PORT')) else 'no'})")
