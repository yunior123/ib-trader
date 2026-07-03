#!/usr/bin/env python
"""D0 — 3 meses de barras 5m para la flota: IBKR y LSE histórico.

Señal-solamente: SOLO lectura de datos historicos, cero ordenes.
TWS live puerto 7496, clientId 41. Salida: data/backtest/bars3mo5m_<sym>.csv
formato "epoch,o,h,l,c,v" (epoch segundos, cronologico, sin duplicados).
Con IBKR apagado usa London Strategic Edge. Yahoo/datos delayed opacos no participan.
"""
import argparse
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "backtest"
FLEET = (REPO / "data" / "fleet.txt").read_text().split()

import os as _o, sys as _s
_s.path.insert(0, _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))), 'scripts'))
from ib_insync import IB, Stock, util
from ib_mode import get_port  # fuente unica: scripts/ib_mode.py (CLAUDE.md #7)  # noqa: E402
import lse_client  # noqa: E402  histórico ilimitado; limitador/cuota compartidos en disco

NY = ZoneInfo("America/New_York")


def bars_to_rows(bars):
    rows = []
    for b in bars:
        # b.date es datetime tz-aware para barras intradia
        epoch = int(b.date.timestamp())
        rows.append((epoch, b.open, b.high, b.low, b.close, int(b.volume)))
    return rows


def fetch_ibkr(ib, sym):
    """3 ventanas de 1M encadenadas. Devuelve rows o None si fallo total."""
    contract = Stock(sym, "SMART", "USD")
    try:
        q = ib.qualifyContracts(contract)
        if not q:
            print(f"  {sym}: no cualifica en IBKR", flush=True)
            return None
    except Exception as e:
        print(f"  {sym}: qualify error {e}", flush=True)
        return None

    all_rows = {}
    end_dt = ""  # ahora
    for window in range(3):
        bars = None
        for attempt in range(2):  # 1 intento + 1 reintento
            try:
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime=end_dt,
                    durationStr="1 M",
                    barSizeSetting="5 mins",
                    whatToShow="TRADES",
                    useRTH=True,
                    formatDate=2,
                    timeout=60,
                )
                break
            except Exception as e:
                print(f"  {sym} win{window} intento{attempt}: {e}", flush=True)
                time.sleep(5)
        if not bars:
            print(f"  {sym} win{window}: sin barras (end={end_dt})", flush=True)
            if window == 0:
                return None  # ni la ventana reciente -> fallback
            break
        rows = bars_to_rows(bars)
        for r in rows:
            all_rows[r[0]] = r
        earliest = min(r[0] for r in rows)
        # siguiente ventana termina donde empieza esta
        import datetime as _dt
        end_dt = _dt.datetime.fromtimestamp(earliest, _dt.timezone.utc)
        print(f"  {sym} win{window}: {len(rows)} barras, earliest {end_dt.isoformat()}", flush=True)
        time.sleep(3)  # pacing IBKR
    return sorted(all_rows.values()) if all_rows else None


def fetch_lse(client, sym, days=93):
    """Barras 5m LSE por tramos de 14d (<5000 incluso en mercados 24/7), filtradas RTH US."""
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=days)
    got = {}
    try:
        cursor = start
        while cursor < end:
            stop = min(cursor + dt.timedelta(days=14), end)
            # El vault acepta fechas YYYY-MM-DD (no timestamps ISO completos).
            bars = client.candles(sym, "5m", start=cursor.date().isoformat(),
                                  end=stop.date().isoformat(), limit=5000, order="asc")
            for b in bars:
                stamp = str(b.get("ts") or b.get("timestamp") or "")
                when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                local = when.astimezone(NY)
                minute = local.hour * 60 + local.minute
                if local.weekday() >= 5 or not (570 <= minute < 960):
                    continue
                row = (int(when.timestamp()), float(b["open"]), float(b["high"]),
                       float(b["low"]), float(b["close"]), int(float(b.get("volume") or 0)))
                if row[4] > 0:
                    got[row[0]] = row
            cursor = stop
    except (lse_client.LSEError, KeyError, TypeError, ValueError) as e:
        print(f"  {sym}: LSE error {e}", flush=True)
        return None
    return [got[k] for k in sorted(got)] or None


def write_csv(sym, rows):
    path = OUT / f"bars3mo5m_{sym.lower()}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "o", "h", "l", "c", "v"])
        for r in rows:
            w.writerow(r)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="default: data/fleet.txt")
    ap.add_argument("--lse-only", action="store_true", help="no intenta conectar IBKR")
    args = ap.parse_args(argv)
    fleet = [s.upper() for s in args.symbols] or FLEET
    report = {}
    ib = None
    lse = lse_client.LSE()
    try:
        if not args.lse_only:
            candidate = IB()
            try:
                candidate.connect("127.0.0.1", get_port(), clientId=41,
                                  readonly=True, timeout=5)
                ib = candidate
                print(f"Conectado TWS readonly. Flota: {len(fleet)}", flush=True)
            except Exception as e:
                print(f"IBKR no disponible ({e}); backfill completo por LSE", flush=True)
        for sym in fleet:
            print(f"== {sym} ==", flush=True)
            rows = fetch_ibkr(ib, sym) if ib is not None else None
            source = "IBKR" if rows else "LSE"
            if not rows:
                print(f"  {sym}: fallback LSE", flush=True)
                rows = fetch_lse(lse, sym)
                source = "LSE" if rows else "FALLO"
            if rows:
                path = write_csv(sym, rows)
                import datetime as _dt
                days = len({_dt.datetime.fromtimestamp(r[0]).date() for r in rows})
                first = _dt.datetime.fromtimestamp(rows[0][0]).date().isoformat()
                last = _dt.datetime.fromtimestamp(rows[-1][0]).date().isoformat()
                report[sym] = {"source": source, "bars": len(rows), "days": days,
                               "first": first, "last": last}
                print(f"  {sym}: {len(rows)} barras, {days} dias, {first} -> {last} [{source}]", flush=True)
            else:
                report[sym] = {"source": "FALLO", "bars": 0, "days": 0,
                               "first": None, "last": None}
                print(f"  {sym}: FALLO total (IBKR + LSE)", flush=True)
            time.sleep(2)
    finally:
        try:
            if ib is not None:
                ib.disconnect()
            print("IB desconectado.", flush=True)
        except Exception:
            pass
    report_name = "bars3mo5m_report.json" if fleet == FLEET else "bars3mo5m_report_subset.json"
    (OUT / report_name).write_text(json.dumps(report, indent=2))
    print("\n=== TABLA ticker -> dias ===", flush=True)
    for sym in fleet:
        r = report.get(sym, {})
        print(f"{sym:6s} {r.get('days',0):3d} dias  {r.get('first')} -> {r.get('last')}  [{r.get('source')}]", flush=True)


if __name__ == "__main__":
    main()
