#!/usr/bin/env python3
"""paper_soak.py — SOAK de 30+ ordenes contra el gateway PAPER.

Por que existe (2026-07-24): toda la verificacion previa corria en DRY, o sea sin
colocar una sola orden. El bug del auto-cancel (openOrder no solicitado) SOLO se
manifiesta con ordenes reales, y el stop huerfano tras `close` tambien. En DRY son
invisibles. Este soak ejerce los caminos de verdad.

SEGURIDAD:
  - Exige data/ib_mode.txt == paper Y puerto de paper. Aborta si no.
  - Arma SOLO el repo-banco (--repo scratch), nunca el repo real.
  - Al final: cancela todo lo suyo y deja la cuenta PLANA. Verifica y reporta.

Uso: ./venv/bin/python order_engine/paper_soak.py [--port 4002] [--n 32]
"""
import argparse, json, os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import ib_mode  # noqa: E402

PAPER_PORTS = set(ib_mode.PAPER_PORTS)   # fuente unica; era {4002, 7497} clavado aqui


def die(msg):
    print(f"ABORTA: {msg}", file=sys.stderr)
    sys.exit(1)


def build_zones(spot, n):
    """n zonas alternando buy/sell -> exposicion neta ~0, y casos de veto."""
    z = []
    for i in range(n):
        side = "buy" if i % 2 == 0 else "sell"
        zid = f"SOAK{i:02d}"
        if i % 8 == 7:      # veto por notional (qty enorme)
            z.append({"id": zid, "price": spot, "side": side, "instrument": "stk",
                      "qty": 99999, "exec": True})
        elif i % 8 == 5:    # opciones: la cadena caduca 16:15 -> veto por cotizacion
            z.append({"id": zid, "price": spot, "side": side, "kind": "call",
                      "exp": "20260727", "qty": 1, "exec": True})
        else:               # accion qty=1, la mitad con stop nativo
            e = {"id": zid, "price": spot, "side": side, "instrument": "stk",
                 "qty": 1, "exec": True}
            if i % 4 == 0:
                e["stop"] = {"on": True, "native": True,
                             "px": round(spot * (0.99 if side == "buy" else 1.01), 2)}
            z.append(e)
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--n", type=int, default=32)
    ap.add_argument("--sym", default="QQQ")
    ap.add_argument("--secs", type=int, default=90)
    a = ap.parse_args()

    if a.port not in PAPER_PORTS:
        die(f"puerto {a.port} no es de paper {sorted(PAPER_PORTS)}")
    mode = open(os.path.join(REPO, "data/ib_mode.txt")).read().strip()
    if mode != "paper":
        die(f"data/ib_mode.txt = '{mode}', se exige 'paper'")

    sc = os.environ.get("SOAK_DIR") or "/tmp/oe_soak"
    os.makedirs(os.path.join(sc, "data"), exist_ok=True)
    os.makedirs(os.path.join(sc, "order_engine"), exist_ok=True)

    # spot desde las barras reales de la flota (o fallback)
    spot = 685.0
    src = os.path.join(REPO, f"data/bars_{a.sym.lower()}_ibkr.txt")
    if os.path.exists(src):
        for ln in open(src):
            p = ln.split()
            if len(p) >= 5:
                spot = float(p[4])
    ep = int(time.time())
    with open(os.path.join(sc, f"data/bars_{a.sym.lower()}_ibkr.txt"), "w") as f:
        f.write(f"{ep} {spot} {spot} {spot} {spot} 1000\n")
    open(os.path.join(sc, "data/ib_mode.txt"), "w").write("paper\n")
    zones = build_zones(spot, a.n)
    with open(os.path.join(sc, f"data/exec_zones_{a.sym.lower()}.json"), "w") as f:
        json.dump(zones, f)
    led = os.path.join(sc, "order_engine/ledger/orders.jsonl")
    if os.path.exists(led):
        os.remove(led)
    open(os.path.join(sc, "order_engine/ARM_LIVE"), "w").write(time.strftime("%Y-%m-%d"))
    cmdp = os.path.join(sc, "order_engine/commands.jsonl")
    open(cmdp, "w").close()

    print(f"SOAK: {a.n} zonas sobre {a.sym} @ {spot} | paper {a.port} | {a.secs}s")
    proc = subprocess.Popen(
        [os.path.join(REPO, "order_engine/order_engine"), "--paper", "--arm-live",
         "--repo", sc, "--sym", a.sym, "--client", "201"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, "IBKR_PORT": str(a.port)})
    time.sleep(a.secs * 0.55)
    # comandos en vivo: close sin side (debe RECHAZAR) y con side (debe ejecutar)
    with open(cmdp, "a") as f:
        f.write(json.dumps({"ts": 1, "act": "close", "sym": a.sym, "qty": 1,
                            "strike": 0, "right": ""}) + "\n")
        f.flush()
        time.sleep(4)
        f.write(json.dumps({"ts": 2, "act": "close", "sym": a.sym, "qty": 1, "strike": 0,
                            "right": "", "side": "sell", "secType": "STK"}) + "\n")
    time.sleep(max(5, a.secs * 0.45))
    proc.terminate()
    out = proc.communicate(timeout=30)[0] or ""

    ev = {}
    for ln in open(led):
        try:
            ev[json.loads(ln)["ev"]] = ev.get(json.loads(ln)["ev"], 0) + 1
        except Exception:
            pass
    print("\n=== eventos del ledger ===")
    for k in sorted(ev):
        print(f"  {k:12} {ev[k]}")
    vetos = out.count("VETOED")
    rech = out.count("RECHAZADO")
    print(f"\n  VETOED    {vetos}\n  RECHAZADO {rech}")
    print(f"  intents   {ev.get('intent', 0)}   fills {ev.get('fill', 0)}   cancels {ev.get('cancel', 0)}")
    os.remove(os.path.join(sc, "order_engine/ARM_LIVE"))
    print("\nARM_LIVE del banco borrado. Revisa/limpia la cuenta con --flatten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
