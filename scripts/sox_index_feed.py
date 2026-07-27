#!/usr/bin/env python3
"""sox_index_feed.py — nivel del INDICE SOX (PHLX Semiconductor) en vivo.
Creado 2026-07-16 noche (orden Yunior: "add sox to track semis performance").

SOX es indice, no operable: NO lleva bot (el motor v6 necesita volumen/NBBO).
Este feed liviano escribe data/nbbo_sox.txt (ts, nivel, nivel) cada ~5s en RTH
para que price_alarm pueda gritar los niveles que las mesas citan (ej. el
soporte 12,022 del research 2026-07-16). Sirena: "sox 12022 down" en
~/Desktop/price-alerts.txt. SEÑAL-SOLAMENTE, readonly, clientId 45.
"""
import datetime as dt
import time

from ib_insync import IB, Index
from ib_mode import get_port  # fuente unica: data/ib_mode.txt (paper/live), no 4002 a ciegas

OUT = "data/nbbo_sox.txt"

ib = IB()
ib.connect("127.0.0.1", get_port(), clientId=45, timeout=15)
sox = Index("SOX", "NASDAQ", "USD")
q = ib.qualifyContracts(sox)
if not q or not q[0].conId:
    print("SOX: contrato no califica en TWS — revisar simbolo/exchange", flush=True)
    raise SystemExit(1)
t = ib.reqMktData(sox, "", False, False)
print(f"SOX index feed VIVO (conId {q[0].conId})", flush=True)
while True:
    ib.sleep(5)
    now = dt.datetime.now()
    # el indice solo computa en RTH; fuera de horario no escribir (frescura honesta)
    if now.weekday() >= 5 or not (9 <= now.hour < 16 or (now.hour == 16 and now.minute < 5)):
        continue
    px = t.last if t.last == t.last else t.close
    if px and px == px and px > 0:
        with open(OUT, "w") as f:
            f.write(f"{int(time.time())} {px:.2f} {px:.2f}\n")
