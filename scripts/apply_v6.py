#!/usr/bin/env python3
"""Aplica el motor v6 MTF a los 20 *_signal_bot.cpp (V6_SPEC.md §3).

Pasos por bot (idempotente: salta si ya tiene 'MOTOR v6'):
  1. detecta prefijo env (envd("XXX_BB_STD")) y nombre humano de voz
  2. inserta scripts/v6_block.cpp.tmpl DESPUES de '// ===== FIN MOTOR v5 ====='
     (fallback: antes del ancla '// ---- cierre seguro: SIGTERM/SIGINT')
  3. hook v6_on_bar() en la linea siguiente al hook v5 existente
  4. neutraliza el disparo v5: default V5_MIN 5.0 -> 99.0 (v6 manda; el humano
     puede reactivar v5 con <SYM>_V5_MIN=5 en el keepalive)
  5. elimina flatten programado: branch EOD gated por <SYM>_EOD_FLATTEN (default
     0 = NUNCA venta por reloj; ley "sin flatten" 2026-07-16)
  6. renombres residuales de titulos (BUY CALL->BUY etc, por si quedo alguno)
  7. bots KRX (kospi/samsung/skhynix): export <SYM>_KRX=1 en su keepalive
  8. compila SECUENCIAL (8GB RAM: jamas 2 clang++ a la vez); --no-compile lo salta
  9. smoke replay: bars sinteticos por --stdin en tmpdir, exit 0 y sin basura

SEÑAL-SOLAMENTE: este script no toca nada de ordenes (no existe nada que tocar).
Uso: python3 scripts/apply_v6.py [--no-compile] [--only dram,nvda] [--update]

--update (v6.1, 2026-07-16 noche): reemplaza el bloque v6 existente por el
template actual (remocion por los marcadores MOTOR v6 / FIN MOTOR v6 + hook)
y re-inserta. Los pasos 4 (V5_MIN) y 5 (EOD_FLATTEN) son idempotentes: si ya
estan aplicados se saltan sin warning.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
BOTS = ["aapl", "amd", "asml", "cper", "dram", "gld", "intc", "kospi", "nok",
        "nvda", "qqq", "samsung", "skhy", "skhynix", "slv", "spcx", "tsla",
        "tsm", "txn", "uso",
        "mu", "smh"]     # añadidos post-spec (v6 ya vivo en ellos; flota = 22)
KRX = {"kospi", "samsung", "skhynix"}          # sesion KST: open min 540

TEMPLATE = f"{ROOT}/scripts/v6_block.cpp.tmpl"
V5_END = "// ===== FIN MOTOR v5 ====="
ANCHOR_FALLBACK = "// ---- cierre seguro: SIGTERM/SIGINT"
HOOK = "        v6_on_bar(b, alert_hours, H, M);   // motor v6 (2026-07-16)\n"
V5_HOOK_RE = re.compile(r"^([ \t]*v5_on_bar\(b, alert_hours, H, M\);[^\n]*\n)", re.M)
V6_START = "// ==================== MOTOR v6 MTF (2026-07-16) ===================="
V6_END = "// ==================== FIN MOTOR v6 ===================="
V6_BLOCK_RE = re.compile(re.escape(V6_START) + r".*?" + re.escape(V6_END) + r"\n?",
                         re.S)
V6_HOOK_RE = re.compile(r"^[ \t]*v6_on_bar\(b, alert_hours, H, M\);[^\n]*\n", re.M)


def human_name(src, sym):
    # nombre humano de voz ("Nokia", "SK Hynix"...) del speak() existente
    mm = re.search(r'speak\("buy (.+?) now', src)
    return mm.group(1) if mm else sym


def renames(s, SYM):
    # residuales que apply_v5 no cubrio (mirror 2026-07-15 aun mostraba
    # BUY CALL / PUT-STOP en binarios viejos): titulos solo BUY/SELL — ley
    m = {
        f'"{SYM}: BUY NOW"': f'"{SYM}: BUY"',
        f'"{SYM}: SELL NOW"': f'"{SYM}: SELL"',
        f'"{SYM}: BUY PUT"': f'"{SYM}: SELL"',
        f'"{SYM}: BUY CALL"': f'"{SYM}: BUY"',
        f'"{SYM}: SELL-STOP"': f'"{SYM}: SELL (STOP)"',
        f'"{SYM}: PUT-STOP"': f'"{SYM}: BUY (STOP)"',
    }
    for a, b in m.items():
        s = s.replace(a, b)
    return s


def patch_source(src, sym, SYM, human, block, update=False):
    """Devuelve (src_parcheado, [warnings]). Puro: testeable sobre una copia."""
    warns = []
    if "MOTOR v6" in src:
        if not update:
            return src, ["ya tiene v6"]
        # --update: quitar bloque viejo (marcadores) + hook y re-insertar
        src, nb = V6_BLOCK_RE.subn("", src, count=1)
        src, nh = V6_HOOK_RE.subn("", src, count=1)
        if nb != 1 or nh != 1:
            return src, [f"update: remocion fallo (bloque={nb} hook={nh}) — revisar a mano"]
    blk = (block.replace("@SYM@", SYM).replace("@sym@", sym))
    # voz con nombre humano (formato snprintf del template)
    blk = blk.replace(f'"buy {sym} now, probability', f'"buy {human} now, probability')
    blk = blk.replace(f'"sell {sym} now, probability', f'"sell {human} now, probability')
    # 2) bloque despues del FIN v5 (fallback: antes del cierre seguro)
    if V5_END in src:
        src = src.replace(V5_END, V5_END + "\n\n" + blk, 1)
    elif ANCHOR_FALLBACK in src:
        src = src.replace(ANCHOR_FALLBACK, blk + "\n" + ANCHOR_FALLBACK, 1)
    else:
        return src, ["SIN ANCLA para el bloque — revisar a mano"]
    # 3) hook despues del hook v5
    src, n = V5_HOOK_RE.subn(lambda m: m.group(1) + HOOK, src, count=1)
    if n != 1:
        warns.append("hook v5 AUSENTE — hook v6 no insertado")
    # 4) neutralizar disparo v5 (v5 sigue calculando como feeder de v6)
    if f'envd("{SYM}_V5_MIN", 99.0)' not in src:       # idempotente (--update)
        src, n = re.subn(rf'envd\("({SYM}_V5_MIN)",\s*5\.0\)', r'envd("\1", 99.0)', src)
        if n != 1:
            warns.append(f"V5_MIN default no neutralizado (matches={n})")
    # 5) flatten EOD gated por env, default 0 (ley: sin ventas por reloj)
    if f"{SYM}_EOD_FLATTEN" not in src:                # idempotente (--update)
        gate = f' && envd("{SYM}_EOD_FLATTEN", 0) > 0.5'
        for lit in ["(b.c >= floor_px || EOD_FORCE > 0)", "(b.c <= s_floor || EOD_FORCE > 0)"]:
            if lit in src:
                src = src.replace(lit, "(" + lit + gate + ")", 1)
            else:
                warns.append(f"literal EOD no hallado: {lit} — flatten NO gated, revisar")
    # 6) renombres residuales
    src = renames(src, SYM)
    return src, warns


def patch_krx_keepalive(bot, SYM):
    p = f"{ROOT}/scripts/{bot}_keepalive.sh"
    if not os.path.exists(p):
        return f"{bot}: keepalive ausente ({p})"
    s = open(p).read()
    if f"{SYM}_KRX=" in s:
        return None
    lines = s.split("\n")
    # export tras el shebang (offsets de sesion KST en el motor v6)
    lines.insert(1, f"export {SYM}_KRX=1   # sesion KRX (open 9:00 KST) para motor v6")
    open(p, "w").write("\n".join(lines))
    return f"{bot}: export {SYM}_KRX=1 añadido al keepalive"


def compile_bot(bot):
    # comando canonico del repo, desde el root, SECUENCIAL
    r = subprocess.run(["clang++", "-std=c++23", "-O3", "-march=native", "-o", f"{bot}_signal_bot",
                        f"{bot}_signal_bot.cpp"], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stderr


def synth_bars(n=500, epoch0=1780315800, px=100.0):
    # bars 1m sinteticos deterministicos (dia habil 9:30 ET aprox)
    import math
    out, t, p = [], epoch0, px
    for i in range(n):
        d = math.sin(i / 7.0) * 0.15 + math.sin(i / 23.0) * 0.3
        o = p; c = p + d; h = max(o, c) + 0.05; l = min(o, c) - 0.05
        v = 50000 + int(20000 * abs(math.sin(i / 5.0)))
        out.append(f"{t} {o:.2f} {h:.2f} {l:.2f} {c:.2f} {v}")
        p = c; t += 60
        if (i + 1) % 390 == 0:
            t += 86400 - 390 * 60      # dia siguiente
    return "\n".join(out) + "\n"


def smoke(bot):
    exe = f"{ROOT}/{bot}_signal_bot"
    if not os.access(exe, os.X_OK):
        return "binario ausente"
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(f"{td}/data", exist_ok=True)
        r = subprocess.run([exe, "--stdin"], input=synth_bars(), cwd=td,
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return f"exit {r.returncode}: {r.stderr[:200]}"
        # señales malformadas: toda linea V6 debe matchear el contrato §2.11
        pat = re.compile(r"\*\*\* \w+ V6 (BUY|SELL) \*\*\* prob \d+% clase \w+ "
                         r"score [\d.]+ \S+ t=\d+")
        for ln in r.stdout.splitlines():
            if "V6 BUY" in ln or "V6 SELL" in ln:
                if not pat.search(ln):
                    return f"señal malformada: {ln[:160]}"
    return None


def main():
    args = sys.argv[1:]
    do_compile = "--no-compile" not in args
    update = "--update" in args
    only = None
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    block = open(TEMPLATE).read()
    ok = 0
    for bot in BOTS:
        if only and bot not in only:
            continue
        p = f"{ROOT}/{bot}_signal_bot.cpp"
        src = open(p).read()
        SYM = bot.upper()
        m = re.search(r'envd\("([A-Z]+)_BB_STD"', src)
        if m:
            SYM = m.group(1)
        human = human_name(src, SYM)
        new, warns = patch_source(src, bot, SYM, human, block, update=update)
        for w in warns:
            print(f"{bot}: WARN {w}")
        if new == src:
            continue
        open(p, "w").write(new)
        if bot in KRX:
            msg = patch_krx_keepalive(bot, SYM)
            if msg:
                print(msg)
        if do_compile:
            rc, err = compile_bot(bot)
            if rc != 0:
                print(f"{bot}: COMPILACION FALLO — ABORTO TODO\n{err[:800]}")
                return 1
            sm = smoke(bot)
            if sm:
                print(f"{bot}: SMOKE FALLO — ABORTO TODO: {sm}")
                return 1
        ok += 1
        print(f"{bot}: v6 OK (prefijo {SYM}, voz '{human}'"
              f"{', compilado+smoke' if do_compile else ''})")
    print(f"{ok} bots parcheados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
