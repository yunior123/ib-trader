#!/usr/bin/env python3
# make_fire_alarm.py — genera sounds/fire_alarm.wav (M5, 2026-07-16).
# Sirena de incendio sintetica: barrido 600->1200->600 Hz con vibrato 6 Hz,
# 3.0 s, 44100 Hz 16-bit mono, amplitud alta (LOUD, orden Yunior).
# Solo stdlib (wave + math): cero dependencias, cero red.
import math
import os
import struct
import wave

RATE = 44100
DUR = 3.0            # segundos
AMP = 0.90           # LOUD (el limite antes de clipear con los armonicos)
F_LO, F_HI = 600.0, 1200.0
SWEEPS = 3           # ciclos completos lo->hi->lo dentro de DUR (urgencia)
VIB_HZ, VIB_DEPTH = 6.0, 18.0   # vibrato 6 Hz, +-18 Hz

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "sounds", "fire_alarm.wav")


def main():
    n = int(RATE * DUR)
    frames = bytearray()
    phase = 0.0
    for i in range(n):
        t = i / RATE
        # posicion del barrido triangular 0..1..0 (SWEEPS ciclos)
        cyc = (t * SWEEPS / DUR) % 1.0
        tri = 1.0 - abs(2.0 * cyc - 1.0)          # 0->1->0
        f = F_LO + (F_HI - F_LO) * tri
        f += VIB_DEPTH * math.sin(2 * math.pi * VIB_HZ * t)   # vibrato
        phase += 2 * math.pi * f / RATE            # integracion de fase (sin clicks)
        # fundamental + 2do armonico suave = timbre de sirena mas "metalico"
        s = 0.85 * math.sin(phase) + 0.15 * math.sin(2 * phase)
        # ataque/decay 30 ms para evitar pops al empezar/terminar
        env = min(1.0, t / 0.03, (DUR - t) / 0.03)
        v = int(max(-1.0, min(1.0, AMP * env * s)) * 32767)
        frames += struct.pack("<h", v)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with wave.open(OUT, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    print(f"OK {OUT} ({len(frames)//2} muestras, {DUR}s)")


if __name__ == "__main__":
    main()
