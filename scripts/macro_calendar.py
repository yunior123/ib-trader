#!/usr/bin/env python3
"""macro_calendar.py — CPI/FOMC/NFP para "no operar el print" (TODOS.md IDEAS 2026-07-26,
scripts/daily_fleet_plans.py tenia 0 hits de CPI/FOMC/NFP).

Fuente unica: data/macro_calendar_2026.json, fechas OFICIALES CONFIRMADAS (FOMC
federalreserve.gov 8/8, CPI via BLS schedule 12/12, NFP 5/12 — bls.gov bloquea scraping
directo con 403 y no hay tabla completa verificable; los 7 meses restantes se quedan
AUSENTES a proposito). MEDIDO que "primer viernes del mes" (la regla BLS habitual)
falla 2/5 veces contra los NFP confirmados (feriado/ajuste) -> NO se usa como relleno:
mezclar confirmado con adivinado sin decirlo esta prohibido (doctrina ~/CLAUDE.md).

SEÑAL-SOLAMENTE: contexto para el PDF, jamas gatillo ni orden."""
import datetime as dt
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL_PATH = os.path.join(REPO, "data", "macro_calendar_2026.json")


def load_confirmed(year):
    """FOMC+CPI+NFP confirmados de data/macro_calendar_2026.json.
    None si el fichero falta o no cubre `year` (jamas {} fabricado)."""
    try:
        with open(CAL_PATH) as f:
            d = json.load(f)
    except Exception as e:
        print(f"AVISO macro_calendar: {CAL_PATH} no cargable ({type(e).__name__}: {e})",
              file=sys.stderr)
        return None
    if d.get("year") != year:
        print(f"AVISO macro_calendar: {CAL_PATH} cubre {d.get('year')}, no {year} — refrescar",
              file=sys.stderr)
        return None
    return d


def macro_events_near(date_, window_days=2):
    """Eventos CPI/FOMC/NFP confirmados a <=window_days de `date_` (datetime.date),
    ordenados por cercania. None si el calendario no cubre el año — nunca [] disfrazado
    de 'sin eventos' cuando en realidad es 'no medido'. [] SI cubre el año y no hay
    eventos cerca (eso si es una medicion real, no un vacio)."""
    d = load_confirmed(date_.year)
    if d is None:
        return None
    out = []
    for row in d.get("cpi", []):
        ed = dt.date.fromisoformat(row["date"])
        days = (ed - date_).days
        if abs(days) <= window_days:
            out.append({"kind": "CPI", "date": row["date"], "hora": "8:30am ET",
                        "days_away": days, "source": row["source"]})
    for row in d.get("fomc", []):
        end = dt.date.fromisoformat(row["end"])
        days = (end - date_).days
        if abs(days) <= window_days:
            out.append({"kind": "FOMC", "date": row["end"], "hora": "2:00pm ET (decision)",
                        "days_away": days, "source": row["source"]})
    for row in d.get("nfp", []):
        nd = dt.date.fromisoformat(row["date"])
        days = (nd - date_).days
        if abs(days) <= window_days:
            out.append({"kind": "NFP", "date": row["date"], "hora": "8:30am ET",
                        "days_away": days, "source": row["source"]})
    out.sort(key=lambda e: abs(e["days_away"]))
    return out


def main():
    d = dt.date.today()
    evs = macro_events_near(d, window_days=int(sys.argv[1]) if len(sys.argv) > 1 else 2)
    if evs is None:
        print("SIN CALENDARIO CONFIRMADO para este año", file=sys.stderr)
        return 1
    if not evs:
        print("sin eventos CPI/FOMC/NFP confirmados en la ventana")
        return 0
    for ev in evs:
        print(f"{ev['kind']} {ev['date']} {ev['hora']} (days_away={ev['days_away']}) [{ev['source']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
