#!/usr/bin/env python3
"""level_events_ingest.py — el sumidero de `level_react`: JSONL -> `trades.db level_events`.

Python legitimo: lote fuera de sesion (CLAUDE.md). Cero computo de señal aqui — los eventos ya
vienen calculados por el binario C++ `./level_react`. Esto solo mueve bytes y aplica retencion.

POR QUE LA INGESTA ES UN PASO APARTE Y NO VIVE DENTRO DEL BINARIO
----------------------------------------------------------------
`trades.db` pesa **1,53 GB** (medido 2026-07-25) y tiene escritores en background. El primitivo
lo van a incluir ~30 signal bots: meter un writer sqlite dentro de el seria poner 30 procesos a
pelearse por el mismo lock **en el camino de señal**, donde el retraso es el negocio. El binario
escribe JSONL (append, lock-free) y esto ingiere fuera de sesion.

POR QUE ESTE FICHERO IMPORTA MAS DE LO QUE PARECE
El backtest de `level_react` solo puede medir los niveles RECONSTRUIBLES desde barras (POC_DOM,
ROUND, PDH/PDL). Los cuatro que mas nos importan — OI_CALL_WALL, OI_PUT_WALL, ABS_WALL,
FLIP_OPEN — **no se pueden reconstruir para el pasado**: no hay historia de OI a ningun precio
en este plan. La UNICA via para que esas celdas se vuelvan medibles algun dia es acumularlas
HACIA ADELANTE, una sesion cada vez. Esta tabla es esa acumulacion.

Retencion: 180 dias en la tabla (contrato de la ficha #8), 30 dias en el JSONL.
SEÑAL-SOLAMENTE: no habla, no ordena, no habilita ninguna voz.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
BIN = os.path.join(REPO, "level_react")
DB = os.path.join(REPO, "trades.db")
JSONL = os.path.join(REPO, "data", "level_events.jsonl")

RETENTION_DAYS_DB = 180
RETENTION_DAYS_JSONL = 30

DDL = """
CREATE TABLE IF NOT EXISTS level_events(
    ts              INTEGER NOT NULL,
    sym             TEXT    NOT NULL,
    level_type      TEXT    NOT NULL,
    level_px        REAL    NOT NULL,
    event           TEXT    NOT NULL,
    is_round        INTEGER NOT NULL,
    touch_ord       INTEGER NOT NULL,
    dist_atr        REAL,
    printed         INTEGER NOT NULL,
    tradeable       INTEGER NOT NULL,
    regime          TEXT,
    hour            INTEGER,
    bar_close_epoch INTEGER NOT NULL,
    PRIMARY KEY(sym, ts, level_type, event)
)
"""


def fleet():
    """Simbolos con fichero de barras. Sin barras no hay eventos — no se inventa nada."""
    d = os.path.join(REPO, "data")
    out = []
    for f in sorted(os.listdir(d)):
        if f.startswith("bars_") and f.endswith("_ibkr.txt"):
            out.append(f[len("bars_"):-len("_ibkr.txt")].upper())
    return out


def regime_of(sym):
    """Regimen gamma del mapa del dia. `None` si no hay mapa — JAMAS 'NEG' ni 'POS' por defecto:
    afirmar un regimen sin mapa es exactamente lo que los tests de gex_consumers prohiben."""
    p = os.path.join(REPO, "charts", "data", "levels_%s.json" % sym.lower())
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("regime")
    except (OSError, ValueError):
        return None


def events_for(sym):
    """Corre el binario C++. Devuelve None si no hay veredicto — nunca una lista vacia que se
    confunda con 'no paso nada'."""
    p = subprocess.run([BIN, "--sym", sym, "--root", REPO],
                       capture_output=True, text=True, cwd=REPO, timeout=120)
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout).get("events")
    except ValueError:
        return None


def main():
    if not os.path.exists(BIN):
        print("level_events_ingest: falta ./level_react (corre scripts/build_level_react.sh)",
              file=sys.stderr)
        return 2

    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else fleet()
    rows = []
    skipped = []
    for sym in syms:
        evs = events_for(sym)
        if evs is None:
            skipped.append(sym)          # fail-loud: se reporta, no se traga
            continue
        reg = regime_of(sym)
        for e in evs:
            ts = int(e["ts"])
            rows.append((ts, sym, e["level_type"], e["level_px"], e["event"],
                         1 if e["is_round"] else 0, e["touch_ord"], e["dist_atr"],
                         1 if e["printed"] else 0, 1 if e["tradeable"] else 0,
                         reg, time.localtime(ts).tm_hour, ts))

    con = sqlite3.connect(DB, timeout=60)
    try:
        con.execute("PRAGMA busy_timeout=60000")
        con.execute(DDL)
        con.executemany(
            "INSERT OR IGNORE INTO level_events(ts,sym,level_type,level_px,event,is_round,"
            "touch_ord,dist_atr,printed,tradeable,regime,hour,bar_close_epoch) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        cutoff = int(time.time()) - RETENTION_DAYS_DB * 86400
        con.execute("DELETE FROM level_events WHERE ts < ?", (cutoff,))
        con.commit()
        total = con.execute("SELECT count(*) FROM level_events").fetchone()[0]
        trad = con.execute("SELECT count(*) FROM level_events WHERE tradeable=1").fetchone()[0]
        walls = con.execute(
            "SELECT count(*) FROM level_events WHERE level_type IN "
            "('OI_CALL_WALL','OI_PUT_WALL','ABS_WALL','FLIP_OPEN')").fetchone()[0]
    finally:
        con.close()

    # JSONL rotado (escritura atomica del fichero del dia)
    os.makedirs(os.path.dirname(JSONL), exist_ok=True)
    day = time.strftime("%Y-%m-%d")
    tmp = JSONL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"ts": r[0], "sym": r[1], "level_type": r[2], "level_px": r[3],
                                "event": r[4], "touch_ord": r[6], "printed": bool(r[8]),
                                "tradeable": bool(r[9]), "regime": r[10], "day": day}) + "\n")
    os.replace(tmp, JSONL)

    print(json.dumps({
        "ingested": len(rows), "syms": len(syms), "sin_veredicto": skipped,
        "tabla_total": total, "tabla_operables": trad,
        "tabla_celdas_de_muro": walls,
        "nota": "las celdas de muro (OI_*/ABS_WALL/FLIP_OPEN) NO son reconstruibles hacia "
                "atras; esta tabla es su unica via de acumulacion forward-only",
        "retencion_dias": RETENTION_DAYS_DB, "voz": "OFF",
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
