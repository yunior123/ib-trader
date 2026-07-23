#!/usr/bin/env python
"""D0 — 3 meses de barras 5m para la flota via IBKR historico.

Señal-solamente: SOLO lectura de datos historicos, cero ordenes.
TWS live puerto 7496, clientId 41. Salida: data/backtest/bars3mo5m_<sym>.csv
formato "epoch,o,h,l,c,v" (epoch segundos, cronologico, sin duplicados).
Fallback yfinance (interval=5m period=60d) para tickers que IBKR no sirva.
"""
import csv
import json
import sys
import time
from pathlib import Path

REPO = Path("/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader")
OUT = REPO / "data" / "backtest"
FLEET = (REPO / "data" / "fleet.txt").read_text().split()
LIKELY_MISSING = {"SKHY", "DRAM", "SPCX"}  # ETFs que IBKR puede no servir

from ib_insync import IB, Stock, util  # noqa: E402


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


def fetch_yf(sym):
    """Fallback yfinance: 5m x 60d (maximo que da yfinance en 5m)."""
    import yfinance as yf
    try:
        df = yf.Ticker(sym).history(interval="5m", period="60d", prepost=False,
                                    auto_adjust=False)
    except Exception as e:
        print(f"  {sym}: yfinance error {e}", flush=True)
        return None
    if df is None or df.empty:
        return None
    rows = []
    for ts, r in df.iterrows():
        rows.append((int(ts.timestamp()), float(r["Open"]), float(r["High"]),
                     float(r["Low"]), float(r["Close"]), int(r["Volume"])))
    return sorted(dict((r[0], r) for r in rows).values())


def write_csv(sym, rows):
    path = OUT / f"bars3mo5m_{sym.lower()}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "o", "h", "l", "c", "v"])
        for r in rows:
            w.writerow(r)
    return path


def main():
    report = {}
    ib = IB()
    try:
        ib.connect("127.0.0.1", 7496, clientId=41, readonly=True, timeout=20)
        print(f"Conectado TWS 7496 clientId 41 (readonly). Flota: {len(FLEET)}", flush=True)
        for sym in FLEET:
            print(f"== {sym} ==", flush=True)
            rows = fetch_ibkr(ib, sym)
            source = "IBKR"
            if not rows:
                print(f"  {sym}: fallback yfinance", flush=True)
                rows = fetch_yf(sym)
                source = "yfinance-60d" if rows else "FALLO"
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
                print(f"  {sym}: FALLO total (IBKR + yfinance)", flush=True)
            time.sleep(2)
    finally:
        try:
            ib.disconnect()
            print("IB desconectado.", flush=True)
        except Exception:
            pass
    (OUT / "bars3mo5m_report.json").write_text(json.dumps(report, indent=2))
    print("\n=== TABLA ticker -> dias ===", flush=True)
    for sym in FLEET:
        r = report.get(sym, {})
        print(f"{sym:6s} {r.get('days',0):3d} dias  {r.get('first')} -> {r.get('last')}  [{r.get('source')}]", flush=True)


if __name__ == "__main__":
    main()
