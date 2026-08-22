#!/usr/bin/env python3
"""Structural option open interest for the cockpit, without Polygon.

Nasdaq's public option-chain response supplies strike-level start-of-day OI but
not model IV.  The cockpit joins this book to the same-expiry/same-strike London
rows before calculating GEX.  Missing OI is omitted (never converted to zero),
and incomplete requested expiries fail closed.

Fallbacks run in cost-then-reliability order (IBT_FREE_OI_PROVIDERS overrides it):
keyless Nasdaq, keyless CBOE delayed chain, Tradier with a free developer token,
then metered Databento OPRA statistics for only the exact London contracts on screen,
quoted first and rejected above a small hard cap.

Polygon Starter, the lane this replaced, was itself 15 minutes delayed, so a delayed
free source is no downgrade for STRUCTURE.  It stays a downgrade for FIRING, so every
payload carries realtime=False plus a measured (never invented) delay, and spot, NBBO
and the confirming print remain London realtime.
"""
from __future__ import annotations

import base64
import csv
import datetime as dt
import io
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
OSI_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,9})(\d{6})([CP])(\d{8})$", re.I)
DATABENTO_BASE = "https://hist.databento.com/v0"
DATABENTO_DATASET = "OPRA.PILLAR"
DATABENTO_MAX_COST_USD = 0.05
DATABENTO_OI_END_UTC = "13:30:00Z"
DATABENTO_SYMBOLS_PER_REQUEST = 100
CBOE_CHAIN_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/%s.json"
CBOE_INDEX_SYMBOLS = {"SPX": "_SPX", "XSP": "_XSP", "NDX": "_NDX",
                      "VIX": "_VIX", "DJI": "_DJI", "RUT": "_RUT"}
CBOE_MAX_BYTES = 48 * 1024 * 1024
CBOE_OCC_RE = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
TRADIER_SANDBOX_BASE = "https://sandbox.tradier.com/v1"
TRADIER_TIMEOUT_S = 20
# Ordered by COST first, then reliability.  Both keyless lanes cost nothing; Tradier
# needs a free developer token; Databento is metered and quoted before every download.
DEFAULT_PROVIDERS = ("nasdaq", "cboe", "tradier", "databento")
# A quote lag beyond this is not a feed delay, it is a closed/holiday session.
MAX_MEASURABLE_LAG_MIN = 120.0
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


def _secret(name):
    value = str(os.environ.get(name) or "").strip()
    if value:
        return value
    try:
        with open(os.path.join(REPO, "config", "feeds.env"), encoding="utf-8") as fh:
            for raw in fh:
                key, sep, value = raw.strip().partition("=")
                if sep and key.strip() == name:
                    value = value.strip().strip("\"'")
                    return value or None
    except OSError:
        pass
    return None


def _rth_open(moment):
    """Regular US session window.  No holiday table: a huge lag disproves it anyway."""
    if moment.weekday() > 4:
        return False
    minutes = moment.hour * 60 + moment.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def _delay_from_quote_stamp(stamp_epoch, now):
    """Measure the vendor's quote lag; refuse to invent one outside the session.

    Returns (structural_delay_minutes, observed_lag_minutes, basis).  Every delayed
    provider publishes this, so nothing downstream can read a delayed structural book
    as if it were the realtime London tape.
    """
    if stamp_epoch is None:
        return None, None, "unmeasured_public_delayed_feed"
    lag = round((now - float(stamp_epoch)) / 60.0, 1)
    now_et = dt.datetime.fromtimestamp(now, tz=ET)
    if _rth_open(now_et) and 0.0 <= lag <= MAX_MEASURABLE_LAG_MIN:
        return lag, lag, "measured_in_session"
    return None, lag, "not_measurable_outside_rth"


def _delay_fields(structural_delay_minutes, observed_lag_minutes, basis):
    """The delay travels IN the payload, never in a comment."""
    return {
        "realtime": False,
        "structural_delay_minutes": structural_delay_minutes,
        "observed_quote_lag_minutes": observed_lag_minutes,
        "structural_delay_basis": basis,
        "delay_policy": "structural_only_never_fires_an_order",
    }


def _cache_usable(payload, sym, expiries, spot, now):
    if not isinstance(payload, dict) or payload.get("status") != "OK":
        return False
    if payload.get("realtime") is not False:
        return False  # pre-delay-field cache: refetch instead of publishing a silent claim
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
    out = {
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
    # Nasdaq stamps only a DATE on lastTrade, so the minute lag is not measurable here.
    out.update(_delay_fields(None, None, "unmeasured_public_delayed_feed"))
    return out


# ------------------------------------------------------- CBOE keyless delayed chain
def _cboe_download(sym, opener=None):
    opener = opener or urllib.request.urlopen
    url = CBOE_CHAIN_URL % urllib.parse.quote(
        CBOE_INDEX_SYMBOLS.get(sym, sym))
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "ib-trader-free-oi/1",
    })
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            raw = response.read(CBOE_MAX_BYTES + 1)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise FreeOIError("%s CBOE delayed chain unavailable (%s: %s)" %
                          (sym, type(exc).__name__, exc)) from exc
    if len(raw) > CBOE_MAX_BYTES:
        raise FreeOIError("%s CBOE delayed chain exceeded byte cap" % sym)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FreeOIError("%s CBOE returned invalid JSON" % sym) from exc
    if not (payload.get("data") or {}).get("options"):
        raise FreeOIError("%s CBOE delayed chain returned no options" % sym)
    return payload, url


def _cboe_quote_epoch(data):
    stamp = str(data.get("last_trade_time") or "").strip()
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(stamp).replace(tzinfo=ET).timestamp()
    except ValueError:
        return None


def fetch_cboe(sym, expiries, spot, *, now=None, opener=None):
    """Keyless full CBOE chain: OI for exactly the requested expiries.

    CBOE also serves IV and greeks, but they are DELAYED: only open interest — a
    start-of-day figure that a delay cannot change — crosses into the book.  London
    still supplies spot and the matching contract IV that reprices gamma.
    """
    sym = str(sym).upper()
    expiries = sorted(set(str(item) for item in expiries if item))
    spot = _num(spot)
    now = float(now if now is not None else time.time())
    if not expiries or spot is None or spot <= 0:
        raise FreeOIError("CBOE OI requires symbol, spot and explicit expiries")
    payload, _ = _cboe_download(sym, opener=opener)
    data = payload.get("data") or {}
    wanted = set(expiries)
    low, high = spot * (1.0 - BAND), spot * (1.0 + BAND)
    observed = {expiry: {"rows": 0, "calls": 0, "puts": 0,
                         "call_oi_unknown": 0, "put_oi_unknown": 0}
                for expiry in expiries}
    contracts = []
    for row in data.get("options") or []:
        match = CBOE_OCC_RE.match(str(row.get("option") or ""))
        if not match:
            continue
        _root, stamp, cp, strike_code = match.groups()
        expiry = "20%s-%s-%s" % (stamp[:2], stamp[2:4], stamp[4:6])
        if expiry not in wanted:
            continue
        strike = int(strike_code) / 1000.0
        if not (low <= strike <= high):
            continue
        right = "call" if cp == "C" else "put"
        observed[expiry]["rows"] += 1
        oi = _num(row.get("open_interest"))
        if oi is None or oi < 0:
            observed[expiry][right + "_oi_unknown"] += 1
            continue
        observed[expiry][right + "s"] += 1
        contracts.append({"expiry": expiry, "right": right, "strike": strike,
                          "open_interest": oi, "iv": None})
    missing = [expiry for expiry, info in observed.items()
               if info["rows"] < 6 or info["calls"] < 3 or info["puts"] < 3]
    if missing:
        raise FreeOIError("%s incomplete CBOE OI expiries: %s" %
                          (sym, ",".join(missing)))
    delay, lag, basis = _delay_from_quote_stamp(_cboe_quote_epoch(data), now)
    out = {
        "status": "OK", "symbol": sym, "fetched_at": now,
        "fetch_date_et": dt.datetime.fromtimestamp(now, tz=ET).date().isoformat(),
        "source": "cboe_delayed_chain",
        "dataset": "cboe_global_delayed_quotes",
        "oi_semantics": "start_of_day_open_interest",
        "last_trade_label": data.get("last_trade_time"),
        "spot_at_fetch": spot, "strike_low": low, "strike_high": high,
        "band": BAND, "expiries": expiries, "contracts": contracts,
        "coverage": observed,
        "note": ("Keyless CBOE delayed chain, open interest only; its delayed IV and "
                 "greeks are discarded so London keeps supplying spot and IV."),
    }
    out.update(_delay_fields(delay, lag, basis))
    return out


# ------------------------------------------- Tradier (free developer token, delayed)
def _tradier_base():
    return str(os.environ.get("TRADIER_API_BASE") or TRADIER_SANDBOX_BASE).rstrip("/")


def _tradier_token():
    return _secret("TRADIER_TOKEN") or _secret("TRADIER_ACCESS_TOKEN")


def fetch_tradier(sym, expiries, spot, *, now=None, opener=None):
    """Tradier chain OI.  Documented delayed; the payload says so and measures it."""
    sym = str(sym).upper()
    expiries = sorted(set(str(item) for item in expiries if item))
    spot = _num(spot)
    now = float(now if now is not None else time.time())
    token = _tradier_token()
    if not token:
        raise FreeOIError("Tradier lane has no configured TRADIER_TOKEN")
    if not expiries or spot is None or spot <= 0:
        raise FreeOIError("Tradier OI requires symbol, spot and explicit expiries")
    opener = opener or urllib.request.urlopen
    low, high = spot * (1.0 - BAND), spot * (1.0 + BAND)
    observed = {expiry: {"rows": 0, "calls": 0, "puts": 0,
                         "call_oi_unknown": 0, "put_oi_unknown": 0}
                for expiry in expiries}
    contracts = []
    newest_trade_epoch = None
    for expiry in expiries:
        url = "%s/markets/options/chains?%s" % (_tradier_base(), urllib.parse.urlencode(
            {"symbol": sym, "expiration": expiry, "greeks": "true"}))
        request = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "User-Agent": "ib-trader-free-oi/1",
        })
        try:
            with opener(request, timeout=TRADIER_TIMEOUT_S) as response:
                raw = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise FreeOIError("Tradier HTTP %s" % exc.code) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise FreeOIError("Tradier unavailable (%s)" % type(exc).__name__) from exc
        if len(raw) > MAX_BYTES:
            raise FreeOIError("Tradier chain exceeded byte cap")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise FreeOIError("Tradier returned invalid JSON") from exc
        rows = ((body.get("options") or {}) or {}).get("option") or []
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            strike = _num(row.get("strike"))
            right = str(row.get("option_type") or "").lower()
            if strike is None or right not in ("call", "put"):
                continue
            if not (low <= strike <= high):
                continue
            observed[expiry]["rows"] += 1
            traded = _num(row.get("trade_date"))
            if traded:
                epoch = traded / 1000.0
                newest_trade_epoch = (epoch if newest_trade_epoch is None
                                      else max(newest_trade_epoch, epoch))
            oi = _num(row.get("open_interest"))
            if oi is None or oi < 0:
                observed[expiry][right + "_oi_unknown"] += 1
                continue
            observed[expiry][right + "s"] += 1
            contracts.append({"expiry": expiry, "right": right, "strike": strike,
                              "open_interest": oi, "iv": None})
    missing = [expiry for expiry, info in observed.items()
               if info["rows"] < 6 or info["calls"] < 3 or info["puts"] < 3]
    if missing:
        raise FreeOIError("%s incomplete Tradier OI expiries: %s" %
                          (sym, ",".join(missing)))
    delay, lag, basis = _delay_from_quote_stamp(newest_trade_epoch, now)
    out = {
        "status": "OK", "symbol": sym, "fetched_at": now,
        "fetch_date_et": dt.datetime.fromtimestamp(now, tz=ET).date().isoformat(),
        "source": "tradier", "dataset": _tradier_base(),
        "oi_semantics": "start_of_day_open_interest",
        "spot_at_fetch": spot, "strike_low": low, "strike_high": high,
        "band": BAND, "expiries": expiries, "contracts": contracts,
        "coverage": observed,
        "note": ("Tradier delayed chain, open interest only; London keeps supplying "
                 "spot and matching IV."),
    }
    out.update(_delay_fields(delay, lag, basis))
    return out


def _databento_raw_symbol(sym, expiry, right, strike, ticker=None):
    """Return Databento's six-character-root OCC symbol."""
    compact = str(ticker or "").strip().upper()
    match = OSI_RE.match(compact)
    if match:
        root, stamp, cp, strike_code = match.groups()
    else:
        root = str(sym).upper()
        stamp = str(expiry)[2:].replace("-", "")
        cp = "C" if str(right).lower() == "call" else "P"
        strike_code = "%08d" % int(round(float(strike) * 1000.0))
    if len(root) > 6:
        raise FreeOIError("Databento OPRA root exceeds six characters: %s" % root)
    return root.ljust(6) + stamp + cp.upper() + strike_code


def _databento_contracts(sym, expiries, spot, rows_by_expiry):
    wanted = set(expiries)
    low, high = spot * (1.0 - BAND), spot * (1.0 + BAND)
    contracts = {}
    for expiry, rows in (rows_by_expiry or {}).items():
        if expiry not in wanted:
            continue
        for row in rows or []:
            strike = _num(row.get("strike"))
            right = str(row.get("contract_type") or row.get("right") or "").lower()
            if (strike is None or not (low <= strike <= high) or
                    right not in ("call", "put")):
                continue
            raw = _databento_raw_symbol(
                sym, expiry, right, strike, row.get("ticker") or row.get("symbol"))
            contracts[raw] = {
                "expiry": expiry, "right": right, "strike": strike,
            }
    return contracts


def _databento_request(url, key, data=None, *, opener=None, max_bytes=MAX_BYTES):
    opener = opener or urllib.request.urlopen
    headers = {
        "Accept": "text/csv, application/json",
        "Authorization": "Basic " + base64.b64encode((key + ":").encode()).decode(),
        "User-Agent": "ib-trader-free-oi/1",
    }
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=encoded, headers=headers)
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        # Do not include the response body: it may echo request/account details.
        raise FreeOIError("Databento HTTP %s" % exc.code) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise FreeOIError("Databento unavailable (%s)" % type(exc).__name__) from exc
    if len(raw) > max_bytes:
        raise FreeOIError("Databento OI response exceeded byte cap")
    return raw


def _databento_cost(params, key, *, opener=None):
    url = DATABENTO_BASE + "/metadata.get_cost?" + urllib.parse.urlencode(params)
    raw = _databento_request(url, key, opener=opener, max_bytes=4096)
    try:
        cost = float(raw.decode("utf-8").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise FreeOIError("Databento returned an invalid cost quote") from exc
    if cost < 0:
        raise FreeOIError("Databento returned a negative cost quote")
    return cost


def fetch_databento(sym, expiries, spot, rows_by_expiry, *, now=None, opener=None):
    """Fetch official OPRA OI only for the London contracts being displayed."""
    sym = str(sym).upper()
    expiries = sorted(set(str(item) for item in expiries if item))
    spot = _num(spot)
    now = float(now if now is not None else time.time())
    key = _secret("DATABENTO_API_KEY")
    if not key:
        raise FreeOIError("Databento fallback has no configured API key")
    if not expiries or spot is None or spot <= 0:
        raise FreeOIError("Databento OI requires symbol, spot and explicit expiries")
    requested = _databento_contracts(sym, expiries, spot, rows_by_expiry)
    if not requested:
        raise FreeOIError("Databento fallback has no matching London contracts")

    fetch_date = dt.datetime.fromtimestamp(now, tz=ET).date().isoformat()
    base_params = {
        "dataset": DATABENTO_DATASET,
        "schema": "statistics", "stype_in": "raw_symbol",
        "start": fetch_date + "T00:00:00Z",
        "end": fetch_date + "T" + DATABENTO_OI_END_UTC,
    }
    symbols = sorted(requested)
    batches = [symbols[i:i + DATABENTO_SYMBOLS_PER_REQUEST]
               for i in range(0, len(symbols), DATABENTO_SYMBOLS_PER_REQUEST)]
    quoted_cost = 0.0
    quoted_params = []
    for batch in batches:
        params = dict(base_params, symbols=",".join(batch))
        quoted_cost += _databento_cost(params, key, opener=opener)
        quoted_params.append(params)
    cost_cap = _num(os.environ.get("IBT_DATABENTO_MAX_OI_COST_USD"))
    cost_cap = DATABENTO_MAX_COST_USD if cost_cap is None else max(0.0, cost_cap)
    if quoted_cost > cost_cap:
        raise FreeOIError("Databento OI quote $%.6f exceeds $%.6f hard cap" %
                          (quoted_cost, cost_cap))

    latest = {}
    for params in quoted_params:
        body = dict(params)
        body.update({"encoding": "csv", "pretty_ts": "true", "map_symbols": "true"})
        raw = _databento_request(
            DATABENTO_BASE + "/timeseries.get_range", key, body, opener=opener)
        try:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        except UnicodeDecodeError as exc:
            raise FreeOIError("Databento returned invalid statistics CSV") from exc
        try:
            for row in reader:
                if str(row.get("stat_type")) != "9":
                    continue
                symbol = str(row.get("symbol") or "")
                oi = _num(row.get("quantity"))
                if symbol in requested and oi is not None and oi >= 0:
                    # OPRA repeats the consolidated statistic through its publishers.
                    # Databento's official example keeps the final record per symbol.
                    latest[symbol] = oi
        except csv.Error as exc:
            raise FreeOIError("Databento returned invalid statistics CSV") from exc

    observed = {expiry: {"rows": 0, "calls": 0, "puts": 0,
                         "call_oi_unknown": 0, "put_oi_unknown": 0}
                for expiry in expiries}
    contracts = []
    for raw_symbol, meta in requested.items():
        expiry, right = meta["expiry"], meta["right"]
        observed[expiry]["rows"] += 1
        oi = latest.get(raw_symbol)
        if oi is None:
            observed[expiry][right + "_oi_unknown"] += 1
            continue
        observed[expiry][right + "s"] += 1
        contracts.append({**meta, "open_interest": oi, "iv": None,
                          "oi_date": fetch_date})
    missing = [expiry for expiry, info in observed.items()
               if info["rows"] < 6 or info["calls"] < 3 or info["puts"] < 3]
    if missing:
        raise FreeOIError("%s incomplete Databento OI expiries: %s" %
                          (sym, ",".join(missing)))
    strikes = [row["strike"] for row in contracts]
    strike_low, strike_high = min(strikes), max(strikes)
    if (strike_low > spot * (1.0 - MIN_SWEEP_BAND) or
            strike_high < spot * (1.0 + MIN_SWEEP_BAND)):
        raise FreeOIError("%s Databento/London contracts do not cover flip sweep" % sym)
    out = {
        "status": "OK", "symbol": sym, "fetched_at": now,
        "fetch_date_et": fetch_date, "source": "databento_opra_statistics",
        "dataset": DATABENTO_DATASET,
        "oi_semantics": "exchange_published_start_of_day_open_interest",
        "spot_at_fetch": spot, "strike_low": strike_low, "strike_high": strike_high,
        "band": BAND, "expiries": expiries, "contracts": contracts,
        "coverage": observed, "quoted_cost_usd": quoted_cost,
        "request_cost_cap_usd": cost_cap, "requested_contracts": len(requested),
        "note": ("Official OPRA OI via existing Databento free credits; exact London "
                 "contracts only. Missing OI remains unknown."),
    }
    # OPRA publishes this statistic once per session before the open: it is not a
    # quote whose lag can shrink, so no minute figure is invented for it.
    out.update(_delay_fields(None, None, "exchange_published_start_of_day"))
    return out


def providers():
    """Cost first, then reliability.  Override with IBT_FREE_OI_PROVIDERS."""
    raw = str(os.environ.get("IBT_FREE_OI_PROVIDERS") or "").strip()
    if not raw:
        return list(DEFAULT_PROVIDERS)
    wanted = [item.strip().lower() for item in raw.split(",") if item.strip()]
    unknown = [item for item in wanted if item not in DEFAULT_PROVIDERS]
    if unknown or not wanted:
        raise FreeOIError("IBT_FREE_OI_PROVIDERS lists unknown providers: %s" %
                          ",".join(unknown or ["<empty>"]))
    return wanted


def _nasdaq(sym, expiries, spot, now, opener):
    payload, assetclass, _ = _download(sym, expiries, opener=opener)
    return _parse(sym, payload, assetclass, expiries, spot, now)


def fetch(sym, expiries, spot, *, now=None, opener=None, london_rows=None,
          databento_opener=None, cboe_opener=None, tradier_opener=None):
    sym = str(sym).upper()
    expiries = sorted(set(str(item) for item in expiries if item))
    spot = _num(spot)
    now = float(now if now is not None else time.time())
    if not expiries or spot is None or spot <= 0:
        raise FreeOIError("free OI requires symbol, spot and explicit expiries")
    lanes = {
        "nasdaq": lambda: _nasdaq(sym, expiries, spot, now, opener),
        "cboe": lambda: fetch_cboe(sym, expiries, spot, now=now, opener=cboe_opener),
        "tradier": lambda: fetch_tradier(sym, expiries, spot, now=now,
                                         opener=tradier_opener),
        "databento": lambda: fetch_databento(sym, expiries, spot, london_rows,
                                             now=now, opener=databento_opener),
    }
    order = providers()
    errors = []
    for name in order:
        try:
            out = lanes[name]()
        except FreeOIError as exc:
            errors.append("%s: %s" % (name, str(exc)[:160]))
            continue
        if out.get("realtime") is not False:
            # A structural provider that claims realtime would let delayed data reach
            # the firing lane.  Refuse it instead of publishing the claim.
            raise FreeOIError("%s provider %s did not declare itself delayed" %
                              (sym, name))
        out["provider_order"] = order
        out["provider_errors"] = errors
        _atomic_write(_cache_path(sym), out)
        return out
    raise FreeOIError("%s free OI unavailable; %s" % (sym, "; ".join(errors)))


def load_or_fetch(sym, expiries, spot, *, now=None, opener=None, force=False,
                  london_rows=None, databento_opener=None, cboe_opener=None,
                  tradier_opener=None):
    now = float(now if now is not None else time.time())
    if not force:
        cached = _read_cache(sym, expiries, float(spot), now)
        if cached is not None:
            cached = dict(cached)
            cached["cache"] = "HIT"
            return cached
    payload = fetch(sym, expiries, spot, now=now, opener=opener,
                    london_rows=london_rows, databento_opener=databento_opener,
                    cboe_opener=cboe_opener, tradier_opener=tradier_opener)
    payload["cache"] = "MISS"
    return payload
