#!/usr/bin/env python3
"""Zero-cost, keyless structural option open interest for the cockpit.

Nasdaq's public option-chain response supplies strike-level start-of-day OI but
not model IV.  The cockpit joins this book to the same-expiry/same-strike London
rows before calculating GEX.  Missing OI is omitted (never converted to zero),
and incomplete requested expiries fail closed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo("America/New_York")
CACHE_DIR = os.path.join(REPO, "data", "free_oi")
BAND = 0.20
MIN_SWEEP_BAND = 0.15
CACHE_MAX_AGE_S = 36 * 3600
TIMEOUT_S = 25
MAX_BYTES = 8 * 1024 * 1024
OSI_TAIL_RE = re.compile(r"(\d{6})([CP])(\d{8})$", re.I)
ETFS = frozenset({
    "DIA", "DRAM", "EWY", "GLD", "IWM", "QQQ", "SLV", "SMH", "SPY",
    "TLT", "USO", "XLE", "XLK",
})


class FreeOIError(RuntimeError):
    pass


def _num(value):
    if value in (None, "", "--", "N/A"):
        return None
    try:
        value = float(str(value).replace(",", "").replace("$", ""))
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def _cache_path(sym):
    return os.path.join(CACHE_DIR, "%s.json" % str(sym).lower())


def _atomic_write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%s" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _cache_usable(payload, sym, expiries, spot, now):
    if not isinstance(payload, dict) or payload.get("status") != "OK":
        return False
    if str(payload.get("symbol") or "").upper() != str(sym).upper():
        return False
    if not set(expiries).issubset(set(payload.get("expiries") or [])):
        return False
    fetched = _num(payload.get("fetched_at"))
    if fetched is None or fetched > now + 60 or now - fetched > CACHE_MAX_AGE_S:
        return False
    low, high = _num(payload.get("strike_low")), _num(payload.get("strike_high"))
    return bool(low is not None and high is not None and
                low <= spot * (1.0 - MIN_SWEEP_BAND) and
                high >= spot * (1.0 + MIN_SWEEP_BAND))


def _read_cache(sym, expiries, spot, now):
    try:
        with open(_cache_path(sym), encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError, TypeError):
        return None
    return payload if _cache_usable(payload, sym, expiries, spot, now) else None


def _url(sym, assetclass, expiries):
    query = urllib.parse.urlencode({
        "assetclass": assetclass, "limit": 5000,
        "fromdate": min(expiries), "todate": max(expiries),
    })
    return "https://api.nasdaq.com/api/quote/%s/option-chain?%s" % (
        urllib.parse.quote(sym), query)


def _download(sym, expiries, opener=None):
    """Try the expected asset class, then the other class for newer symbols."""
    opener = opener or urllib.request.urlopen
    order = ("etf", "stocks") if sym in ETFS else ("stocks", "etf")
    last_error = None
    for assetclass in order:
        url = _url(sym, assetclass, expiries)
        request = urllib.request.Request(url, headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/market-activity/%s/%s/option-chain" %
                       (assetclass, sym.lower()),
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 Chrome/126 Safari/537.36"),
        })
        try:
            with opener(request, timeout=TIMEOUT_S) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FreeOIError("%s Nasdaq option chain exceeded byte cap" % sym)
            payload = json.loads(raw.decode("utf-8"))
            status = payload.get("status") or {}
            if status.get("rCode") == 200 and payload.get("data"):
                return payload, assetclass, url
            last_error = status.get("bCodeMessage") or "empty option-chain response"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
    raise FreeOIError("%s Nasdaq public option chain unavailable (%s)" %
                      (sym, last_error or "unknown response"))


def _parse(sym, payload, assetclass, expiries, spot, now):
    wanted = set(expiries)
    low, high = spot * (1.0 - BAND), spot * (1.0 + BAND)
    data = payload.get("data") or {}
    rows = ((data.get("table") or {}).get("rows") or [])
    contracts = []
    observed = {expiry: {"rows": 0, "calls": 0, "puts": 0,
                         "call_oi_unknown": 0, "put_oi_unknown": 0}
                for expiry in expiries}
    for row in rows:
        match = OSI_TAIL_RE.search(str(row.get("drillDownURL") or ""))
        strike = _num(row.get("strike"))
        if not match or strike is None or not (low <= strike <= high):
            continue
        stamp = match.group(1)
        expiry = "20%s-%s-%s" % (stamp[:2], stamp[2:4], stamp[4:6])
        if expiry not in wanted:
            continue
        observed[expiry]["rows"] += 1
        for prefix, right in (("c", "call"), ("p", "put")):
            oi = _num(row.get(prefix + "_Openinterest"))
            if oi is None:
                observed[expiry][right + "_oi_unknown"] += 1
                continue
            contracts.append({
                "expiry": expiry, "right": right, "strike": strike,
                "open_interest": oi, "iv": None,
            })
            observed[expiry][right + "s"] += 1

    missing = [expiry for expiry, info in observed.items()
               if info["rows"] < 3 or info["calls"] < 3 or info["puts"] < 3]
    if missing:
        raise FreeOIError("%s incomplete Nasdaq OI expiries: %s" %
                          (sym, ",".join(missing)))
    fetched_date = dt.datetime.fromtimestamp(now, tz=ET).date().isoformat()
    return {
        "status": "OK", "symbol": sym, "fetched_at": now,
        "fetch_date_et": fetched_date,
        "source": "nasdaq_public_option_chain",
        "dataset": "public_delayed_option_chain",
        "assetclass": assetclass,
        "oi_semantics": "start_of_day_open_interest",
        "last_trade_label": data.get("lastTrade"),
        "spot_at_fetch": spot, "strike_low": low, "strike_high": high,
        "band": BAND, "expiries": expiries, "contracts": contracts,
        "coverage": observed,
        "note": ("Keyless Nasdaq public OI; London supplies live spot and matching "
                 "contract IV. Missing Nasdaq OI remains unknown."),
    }


def fetch(sym, expiries, spot, *, now=None, opener=None):
    sym = str(sym).upper()
    expiries = sorted(set(str(item) for item in expiries if item))
    spot = _num(spot)
    now = float(now if now is not None else time.time())
    if not expiries or spot is None or spot <= 0:
        raise FreeOIError("free OI requires symbol, spot and explicit expiries")
    payload, assetclass, _ = _download(sym, expiries, opener=opener)
    out = _parse(sym, payload, assetclass, expiries, spot, now)
    _atomic_write(_cache_path(sym), out)
    return out


def load_or_fetch(sym, expiries, spot, *, now=None, opener=None, force=False):
    now = float(now if now is not None else time.time())
    if not force:
        cached = _read_cache(sym, expiries, float(spot), now)
        if cached is not None:
            cached = dict(cached)
            cached["cache"] = "HIT"
            return cached
    payload = fetch(sym, expiries, spot, now=now, opener=opener)
    payload["cache"] = "MISS"
    return payload
