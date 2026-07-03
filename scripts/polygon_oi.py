#!/usr/bin/env python3
"""Bounded Polygon option-OI snapshot for the London-only cockpit.

London remains the realtime source.  This module supplies the missing structural
book (OI + IV) only, cached for the trading day because OPRA OI is a start-of-day
statistic.  Every network page must succeed; partial chains are never published.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.parse
from zoneinfo import ZoneInfo

from poly_client import Polygon, PolygonError, RateLimiter


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo("America/New_York")
CACHE_DIR = os.path.join(REPO, "data", "polygon_oi")
BAND = 0.20
MIN_SWEEP_BAND = 0.15
MAX_PAGES = 80
CACHE_MAX_AGE_S = 36 * 3600
RATE_STATE = os.path.join(REPO, "data", "poly_rate_state_oi.json")


def _num(value):
    try:
        value = float(value)
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
    if payload.get("realtime") is not False:
        return False  # cache anterior a los campos de retraso: refetch, no claim silencioso
    if str(payload.get("symbol") or "").upper() != str(sym).upper():
        return False
    if not set(expiries).issubset(set(payload.get("expiries") or [])):
        return False
    fetched = _num(payload.get("fetched_at"))
    if fetched is None or now - fetched > CACHE_MAX_AGE_S or fetched > now + 60:
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


def fetch(sym, expiries, spot, *, now=None, client=None):
    """Fetch exact requested expiries in a ±20% strike window, fail-closed."""
    sym = str(sym).upper()
    expiries = sorted(set(str(item) for item in expiries if item))
    spot = _num(spot)
    now = float(now if now is not None else time.time())
    if not expiries or spot is None or spot <= 0:
        raise PolygonError("Polygon OI requires symbol, spot and explicit expiries")
    low, high = spot * (1.0 - BAND), spot * (1.0 + BAND)
    params = {
        "limit": 250,
        "expiration_date.gte": expiries[0],
        "expiration_date.lte": expiries[-1],
        "strike_price.gte": round(low, 4),
        "strike_price.lte": round(high, 4),
    }
    url = ("https://api.polygon.io/v3/snapshot/options/%s?%s" %
           (urllib.parse.quote(sym), urllib.parse.urlencode(params)))
    if client is None:
        limiter = RateLimiter(n=60, window=62, path=RATE_STATE)
        client = Polygon(limiter=limiter, verbose=False)
    rows, pages = [], 0
    for page in client.paginate(url, max_pages=MAX_PAGES):
        rows.extend(page.get("results") or [])
        pages += 1
    if pages >= MAX_PAGES:
        raise PolygonError("%s Polygon OI hit page cap; refusing partial chain" % sym)

    wanted = set(expiries)
    contracts = []
    for item in rows:
        detail = item.get("details") or {}
        expiry = str(detail.get("expiration_date") or "")
        right = str(detail.get("contract_type") or "").lower()
        strike = _num(detail.get("strike_price"))
        oi = _num(item.get("open_interest"))
        iv = _num(item.get("implied_volatility"))
        greeks = item.get("greeks") or {}
        if expiry not in wanted or right not in ("call", "put") or strike is None:
            continue
        # Missing OI is unknown, not zero.  Preserve it so coverage can fail loudly.
        contracts.append({
            "ticker": detail.get("ticker"), "expiry": expiry, "right": right,
            "strike": strike, "open_interest": oi,
            "iv": iv if iv is not None and 0 < iv <= 5 else None,
            "gamma": _num(greeks.get("gamma")), "delta": _num(greeks.get("delta")),
        })
    by_expiry = {}
    for expiry in expiries:
        group = [row for row in contracts if row["expiry"] == expiry]
        by_expiry[expiry] = {
            "contracts": len(group),
            "calls": sum(row["right"] == "call" for row in group),
            "puts": sum(row["right"] == "put" for row in group),
            "oi_fields": sum(row["open_interest"] is not None for row in group),
        }
    missing = [expiry for expiry, info in by_expiry.items()
               if not info["calls"] or not info["puts"] or
               info["oi_fields"] != info["contracts"]]
    if missing:
        raise PolygonError("%s incomplete Polygon OI expiries: %s" %
                           (sym, ",".join(missing)))
    payload = {
        "status": "OK", "symbol": sym, "fetched_at": now,
        "fetch_date_et": dt.datetime.fromtimestamp(now, tz=ET).date().isoformat(),
        "source": "polygon_options_snapshot", "dataset": "OPRA",
        "oi_semantics": "start_of_day_open_interest",
        "spot_at_fetch": spot, "strike_low": low, "strike_high": high,
        "band": BAND, "expiries": expiries, "pages": pages,
        "contracts": contracts, "coverage": by_expiry,
        "note": "Polygon OI+IV structural overlay; London remains realtime price/activity",
        # Starter es 15 min delayed por tarifa; no se mide por contrato, se declara.
        "realtime": False,
        "structural_delay_minutes": 15,
        "observed_quote_lag_minutes": None,
        "structural_delay_basis": "vendor_documented_starter_15min",
        "delay_policy": "structural_only_never_fires_an_order",
    }
    _atomic_write(_cache_path(sym), payload)
    return payload


def load_or_fetch(sym, expiries, spot, *, now=None, client=None, force=False):
    now = float(now if now is not None else time.time())
    if not force:
        cached = _read_cache(sym, expiries, float(spot), now)
        if cached is not None:
            cached = dict(cached)
            cached["cache"] = "HIT"
            return cached
    payload = fetch(sym, expiries, spot, now=now, client=client)
    payload["cache"] = "MISS"
    return payload

