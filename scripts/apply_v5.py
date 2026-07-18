#!/usr/bin/env python3
"""Aplica el motor v5 + renombres BUY/SELL a los 20 *_signal_bot.cpp.
Sym-aware (no regenera desde el master: los bots KRX tienen logica KST propia).
Idempotente: salta archivos que ya tienen 'MOTOR v5'."""
import re
import sys

ROOT = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
BOTS = ["aapl", "amd", "asml", "cper", "dram", "gld", "intc", "kospi", "nok",
        "nvda", "qqq", "samsung", "skhy", "skhynix", "slv", "spcx", "tsla",
        "tsm", "txn", "uso"]
BLOCK = open(f"{ROOT}/scripts/v5_block.cpp.tmpl").read()

ANCHOR_BLOCK = "// ---- cierre seguro: SIGTERM/SIGINT"
ANCHOR_HOOK = "        // ===== DETECTION LAYERS ====="
HOOK = "        v5_on_bar(b, alert_hours, H, M);   // motor v5 MTF (2026-07-15)\n"

# renombres solo-BUY/SELL (orden: "just buy or sell, the human will understand")
def renames(s, SYM, sym, human):
    m = {
        f'"{SYM}: BUY NOW"': f'"{SYM}: BUY"',
        f'"{SYM}: SELL NOW"': f'"{SYM}: SELL"',
        f'"{SYM}: BUY PUT"': f'"{SYM}: SELL"',
        f'"{SYM}: BUY CALL"': f'"{SYM}: BUY"',
        f'"{SYM}: SELL-STOP"': f'"{SYM}: SELL (STOP)"',
        f'"{SYM}: PUT-STOP"': f'"{SYM}: BUY (STOP)"',
        f'"buy {human} put now"': f'"sell {human} now"',
        f'"buy {human} call now"': f'"buy {human} now"',
        "COMPRAR PUT ": "VENDER ",
        "COMPRAR CALL ": "COMPRAR ",
        " (shares o CALL)": "",
    }
    for a, b in m.items():
        s = s.replace(a, b)
    return s


def human_name(src, sym):
    # el speak() usa el nombre humano ("Nokia", "SK Hynix"...): sacarlo del
    # primer speak("buy X now") existente
    mm = re.search(r'speak\("buy (.+?) now"\)', src)
    return mm.group(1) if mm else sym


def main():
    ok = 0
    for b in BOTS:
        p = f"{ROOT}/{b}_signal_bot.cpp"
        s = open(p).read()
        if "MOTOR v5" in s:
            print(f"{b}: ya tiene v5, salto")
            continue
        SYM = b.upper()
        # prefijo env real (p.ej. envd("NOK_BB_STD")):
        m = re.search(r'envd\("([A-Z]+)_BB_STD"', s)
        if m:
            SYM = m.group(1)
        human = human_name(s, SYM)
        if ANCHOR_BLOCK not in s or ANCHOR_HOOK not in s:
            print(f"{b}: ANCLA AUSENTE — salto (revisar a mano)")
            continue
        blk = (BLOCK.replace("@SYM@", SYM)
                    .replace("@sym@", b if b != SYM.lower() else SYM.lower())
                    .replace('speak("buy @sym@'.replace("@sym@", b), f'speak("buy {human}'))
        # voz con nombre humano
        blk = blk.replace(f'speak("buy {b} now")', f'speak("buy {human} now")')
        blk = blk.replace(f'speak("sell {b} now")', f'speak("sell {human} now")')
        s = s.replace(ANCHOR_BLOCK, blk + "\n" + ANCHOR_BLOCK, 1)
        s = s.replace(ANCHOR_HOOK, HOOK + ANCHOR_HOOK, 1)
        s = renames(s, SYM, b, human)
        open(p, "w").write(s)
        ok += 1
        print(f"{b}: v5 + renombres OK (prefijo {SYM}, voz '{human}')")
    print(f"{ok}/{len(BOTS)} parcheados")


if __name__ == "__main__":
    sys.exit(main())
