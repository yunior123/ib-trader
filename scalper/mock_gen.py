#!/usr/bin/env python3
"""mock_gen.py — fabrica de escenarios SINTETICOS para el whale scalper.

Genera archivos JSONL en formato --replay: datos inventados pero con la forma
esperada del patron real (pop-then-pullback tras BALLENA CALLS, etc.).
Orden Yunior 2026-07-21: "we create the data we are expecting... then we test
with that locally without connecting to ibkr yet".

Uso:
  python3 scalper/mock_gen.py --scenario pop_pullback --seed 3 > /tmp/esc.jsonl
  ./scalper/whale_scalper --replay /tmp/esc.jsonl
  python3 scalper/mock_gen.py --suite --outdir /tmp/mock_suite   # 20 variantes
Escenarios: pop_pullback (gana), band_walk (continua = pierde -> HALT),
whipsaw (picadora), flat (nada pasa), pop_grande, pullback_lento.
"""
import argparse, os, random, sys

SPOT = 70850          # cents
TICK_MS = 250

def w(lines, t, ev, **kw):
    kv = ",".join(f'"{k}":{v if not isinstance(v, str) else chr(34)+v+chr(34)}' for k, v in kw.items())
    lines.append(f'{{"t_ms":{t},"ev":"{ev}"{"," if kv else ""}{kv}}}')

def preamble(lines, hhmm=1005, spot=SPOT, iv=0.20, spread=4):
    w(lines, 0, "hhmm", v=hhmm)
    w(lines, 0, "chain", spot_c=spot, iv=iv, spread_c=spread, exp=20260721)
    w(lines, 0, "und", bid_c=spot - 2, ask_c=spot + 2)

def path(lines, t0, t1, px0, px1, rng, noise_c=3):
    """camino de precio con ruido entre t0..t1, px0->px1 (cents del subyacente)."""
    t = t0
    n = max(1, (t1 - t0) // TICK_MS)
    for i in range(n + 1):
        px = px0 + (px1 - px0) * i / n + rng.randint(-noise_c, noise_c)
        px = max(int(px), 100)
        w(lines, t, "und", bid_c=px - 2, ask_c=px + 2)
        t += TICK_MS

def pop_pullback(rng, pop_c, pullback_c, pop_ms=2000, pull_ms=20000):
    """el patron objetivo: alerta CALLS, pop corto arriba, pullback abajo."""
    L = []
    preamble(L)
    w(L, 100, "alert", side="CALLS", sym=rng.choice(["QQQ", "NVDA", "MU", "MSFT"]))
    # pop durante el WAIT del bot (2.5s): sube pop_c
    path(L, 200, 200 + pop_ms, SPOT, SPOT + pop_c, rng)
    # pullback: baja pullback_c desde el pico
    path(L, 200 + pop_ms, 200 + pop_ms + pull_ms, SPOT + pop_c, SPOT + pop_c - pullback_c, rng)
    # veredicto: pullback >= ~40c en el subyacente deberia dar profit al PUT
    if pullback_c >= 40:
        w(L, 200 + pop_ms + pull_ms + 8000, "expect_trades", v=1)
        w(L, 200 + pop_ms + pull_ms + 8000, "expect_state", v="IDLE")
    return L

def band_walk(rng, run_c=120):
    """el caso que nos mata: la ballena era CONTINUACION; QQQ sigue subiendo.
    El PUT muere, 60s -> salida forzada con perdida -> HALT."""
    L = []
    preamble(L)
    w(L, 100, "alert", side="CALLS", sym="QQQ")
    path(L, 200, 70000, SPOT, SPOT + run_c, rng)
    w(L, 75000, "expect_trades", v=1)
    w(L, 75000, "expect_state", v="HALTED")
    return L

def whipsaw(rng, amp_c=15):
    """picadora: oscila sin direccion; el trade probablemente muere en 60s."""
    L = []
    preamble(L)
    w(L, 100, "alert", side="PUTS", sym="QQQ")     # -> CALL
    t, px = 200, SPOT
    for _ in range(280):
        px = SPOT + rng.randint(-amp_c, amp_c)
        w(L, t, "und", bid_c=px - 2, ask_c=px + 2)
        t += TICK_MS
    return L

def flat(rng):
    L = []
    preamble(L)
    path(L, 100, 30000, SPOT, SPOT, rng, noise_c=2)
    w(L, 31000, "expect_state", v="IDLE")
    w(L, 31000, "expect_trades", v=0)
    return L

def pullback_lento(rng):
    """pullback existe pero tarda: llega dentro de la extension de 30s."""
    L = []
    preamble(L)
    w(L, 100, "alert", side="CALLS", sym="QQQ")
    path(L, 200, 2200, SPOT, SPOT + 25, rng)
    path(L, 2200, 40000, SPOT + 25, SPOT - 55, rng)   # lento pero profundo
    w(L, 50000, "expect_trades", v=1)
    return L

GEN = {
    "pop_pullback":   lambda r: pop_pullback(r, pop_c=30, pullback_c=60),
    "pop_grande":     lambda r: pop_pullback(r, pop_c=60, pullback_c=120, pull_ms=15000),
    "band_walk":      band_walk,
    "whipsaw":        whipsaw,
    "flat":           flat,
    "pullback_lento": pullback_lento,
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=sorted(GEN))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--suite", action="store_true", help="genera variantes de todos")
    ap.add_argument("--outdir", default="/tmp/mock_suite")
    a = ap.parse_args()
    if a.suite:
        os.makedirs(a.outdir, exist_ok=True)
        n = 0
        for name, gen in GEN.items():
            for seed in (1, 2, 3):
                L = gen(random.Random(seed))
                p = os.path.join(a.outdir, f"{name}_s{seed}.jsonl")
                open(p, "w").write(f"# {name} seed {seed}\n" + "\n".join(L) + "\n")
                n += 1
        print(f"{n} escenarios en {a.outdir}", file=sys.stderr)
        return
    if not a.scenario:
        ap.error("--scenario o --suite")
    L = GEN[a.scenario](random.Random(a.seed))
    print(f"# {a.scenario} seed {a.seed}")
    print("\n".join(L))

if __name__ == "__main__":
    main()
