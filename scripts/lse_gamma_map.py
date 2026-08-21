#!/usr/bin/env python3
"""London-only option gamma activity map.

LSE's chain provides model gamma and volume_today but not open interest.  This module
therefore computes gamma x traded volume, never dealer GEX.  The result is chart context;
it must not drive order execution or be labelled as Net GEX/gamma flip.
"""
import datetime as dt
import json
import math
import os
import re
import time
from zoneinfo import ZoneInfo

from lse_client import LSE
import architect_lse
from gex_core import bs_gamma, build_gex

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(REPO, "data")
MAX_EXPIRIES = 3
MAX_ROWS = 17
DISCOVERY_DAYS = 18
REFRESH_S = 300
STALE_S = 900
ET = ZoneInfo("America/New_York")
DMM_START = dt.time(9, 45)
OPTION_ROLL_TIME = dt.time(16, 0)
OSI_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,9})(\d{6})([CP])(\d{8})$")


def _num(value):
    try:
        value = float(value)
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def _epoch(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _expiry_years(expiry, now):
    """Years to the 16:00 ET option close, with the same 5-minute 0DTE floor."""
    try:
        close = dt.datetime.combine(dt.date.fromisoformat(expiry), dt.time(16), tzinfo=ET)
    except (TypeError, ValueError):
        return None
    floor = 5.0 / (365.0 * 24.0 * 60.0)
    return max(floor, (close.timestamp() - float(now)) / (365.0 * 86400.0))


def _activity_flip(rows_by_expiry, spot, now):
    """Zero crossing of repriced signed gamma×volume activity.

    This deliberately is *not* the dealer gamma flip: ``volume_today`` is a tape
    weight, not inventory, and the call-positive/put-negative sign is only a
    disclosed geometry convention.  The output is useful as an animated reference
    while the real OI flip remains DATA-locked.
    """
    contracts, strikes = [], []
    call_count = put_count = 0
    call_volume = put_volume = 0.0
    for expiry, rows in (rows_by_expiry or {}).items():
        years = _expiry_years(expiry, now)
        if years is None:
            continue
        for row in rows:
            strike = _num(row.get("strike"))
            iv = _num(row.get("iv"))
            volume = _num(row.get("volume_today"))
            right = str(row.get("contract_type") or "").lower()
            if (strike is None or strike <= 0 or iv is None or not (0 < iv <= 5) or
                    volume is None or volume <= 0 or right not in ("call", "put")):
                continue
            sign = 1.0 if right == "call" else -1.0
            contracts.append((strike, years, iv, volume, sign))
            strikes.append(strike)
            if sign > 0:
                call_count += 1
                call_volume += volume
            else:
                put_count += 1
                put_volume += volume

    detail = {
        "status": "DATA", "level": None, "metric": "gamma_volume",
        "method": "zero crossing of BS-repriced signed gamma×volume_today",
        "dealer_gamma_flip": False, "oi_available": False,
        "contracts_used": len(contracts), "call_contracts": call_count,
        "put_contracts": put_count, "call_volume": round(call_volume, 2),
        "put_volume": round(put_volume, 2),
        "validation": "UNPROVEN_DESCRIPTIVE_CONTEXT_ONLY",
        "why": None,
    }
    if call_count < 1 or put_count < 1 or len(set(strikes)) < 2:
        detail["why"] = "need usable IV and volume_today on both calls and puts"
        return detail

    low = max(min(strikes), spot * 0.85)
    high = min(max(strikes), spot * 1.15)
    if not (low < high):
        detail["why"] = "observed strike coverage does not bracket a price sweep"
        return detail

    def exposure(candidate):
        net = gross = 0.0
        for strike, years, iv, volume, sign in contracts:
            gamma = bs_gamma(candidate, strike, years, iv)
            if gamma is None or not math.isfinite(gamma) or gamma <= 0:
                continue
            mass = gamma * volume * 100.0
            net += sign * mass
            gross += mass
        return net, gross

    points = [low + (high - low) * i / 120.0 for i in range(121)]
    values = [(price,) + exposure(price) for price in points]
    roots = []
    for left, right in zip(values, values[1:]):
        lp, ln, lg = left
        rp, rn, rg = right
        if min(lg, rg) <= 0:
            continue
        if ln == 0:
            roots.append((lp, lg))
            continue
        if ln * rn > 0:
            continue
        lo, hi, nlo = lp, rp, ln
        for _ in range(40):
            mid = (lo + hi) / 2.0
            nmid, _ = exposure(mid)
            if nlo * nmid <= 0:
                hi = mid
            else:
                lo, nlo = mid, nmid
        root = (lo + hi) / 2.0
        _, gross = exposure(root)
        roots.append((root, gross))

    # De-duplicate roots that landed on the same coarse-grid boundary.
    unique = []
    for root, gross in sorted(roots):
        if not unique or abs(root - unique[-1][0]) > max(0.01, spot * 1e-5):
            unique.append((root, gross))
    if not unique:
        detail["why"] = "signed gamma×volume_today has no zero crossing in observed strike range"
        detail["sweep_low"] = round(low, 4)
        detail["sweep_high"] = round(high, 4)
        return detail
    root, gross = min(unique, key=lambda item: abs(item[0] - spot))
    detail.update({
        "status": "OK", "level": round(root, 4),
        "gross_gamma_volume_at_level": round(gross * root * root * 0.01, 2),
        "roots": [round(item[0], 4) for item in unique],
        "sweep_low": round(low, 4), "sweep_high": round(high, 4),
        "why": "activity zero-crossing only; no dealer inventory claim",
    })
    return detail


def _record_option_print(snapshot, row, message, size, price, stamp):
    """Forward-audit an LSE print without promoting inferred side to Bid×Ask truth."""
    audit = snapshot.setdefault("option_tape_audit", {
        "prints": 0, "quote_rule": 0, "tick_rule": 0, "unknown": 0,
        "signed_contracts": 0.0, "signed_premium": 0.0,
        "signed_option_delta": 0.0, "first_ts": None, "last_ts": None,
    })
    states = snapshot.setdefault("option_tick_rule_state", {})
    ticker = str(message.get("symbol") or row.get("ticker") or "").upper()
    bid, ask = _num(message.get("bid")), _num(message.get("ask"))
    previous = _num(row.get("last_price"))
    side, method = 0, "unknown"
    if (price is not None and bid is not None and ask is not None and 0 <= bid <= ask):
        if price >= ask and ask > 0:
            side, method = 1, "quote_rule"
        elif price <= bid and bid > 0:
            side, method = -1, "quote_rule"
    if method == "unknown" and price is not None and previous is not None:
        if price > previous:
            side, method = 1, "tick_rule"
        elif price < previous:
            side, method = -1, "tick_rule"
        elif states.get(ticker) in (-1, 1):
            side, method = states[ticker], "tick_rule"
    if side:
        states[ticker] = side
    audit["prints"] += 1
    audit[method] += 1
    audit["signed_contracts"] += side * size
    if price is not None:
        audit["signed_premium"] += side * price * size * 100.0
    delta = _num(row.get("delta"))
    if delta is not None:
        audit["signed_option_delta"] += side * delta * size * 100.0
    epoch = _epoch(stamp) or time.time()
    audit["first_ts"] = audit["first_ts"] or epoch
    audit["last_ts"] = epoch


def _option_tape_context(snapshot):
    audit = (snapshot or {}).get("option_tape_audit") or {}
    prints = int(audit.get("prints") or 0)
    quote = int(audit.get("quote_rule") or 0)
    tick = int(audit.get("tick_rule") or 0)
    unknown = int(audit.get("unknown") or 0)
    return {
        "status": "AUDIT" if prints else "DATA",
        "prints": prints, "quote_rule_prints": quote, "tick_rule_prints": tick,
        "unknown_prints": unknown,
        "quote_coverage_pct": round(100.0 * quote / prints, 2) if prints else 0.0,
        "classified_pct": round(100.0 * (quote + tick) / prints, 2) if prints else 0.0,
        "signed_contracts_inferred": round(float(audit.get("signed_contracts") or 0.0), 2),
        "signed_premium_inferred": round(float(audit.get("signed_premium") or 0.0), 2),
        "signed_option_delta_inferred": round(float(audit.get("signed_option_delta") or 0.0), 2),
        "first_ts": audit.get("first_ts"), "last_ts": audit.get("last_ts"),
        "source": "lse_websocket_option_prints",
        "guard": ("quote/tick-rule inference only; not exchange-sealed aggressor side, "
                  "not Bid×Ask footprint confirmation"),
        "reversal_triad_eligible": False,
        "validation": "FORWARD_AUDIT_ONLY",
    }


def attach_polygon_oi(snapshot, overlay):
    """Attach a complete Polygon structural snapshot to an LSE REST snapshot."""
    if not snapshot or not isinstance(overlay, dict) or overlay.get("status") != "OK":
        return False
    snapshot["polygon_oi_overlay"] = overlay
    return True


def attach_oi(snapshot, overlay):
    """Attach a provider-neutral OI book to the coherent London snapshot."""
    if not snapshot or not isinstance(overlay, dict) or overlay.get("status") != "OK":
        return False
    snapshot["oi_overlay"] = overlay
    return True


def _oi_overlay(snapshot):
    """Prefer the free lane while retaining the explicit Polygon rollback shape."""
    snapshot = snapshot or {}
    if snapshot.get("oi_overlay"):
        return snapshot["oi_overlay"]
    if snapshot.get("polygon_oi_disabled"):
        return {}
    return snapshot.get("polygon_oi_overlay") or {}


def _lse_iv_lookup(snapshot):
    """IV keyed by the same expiry/strike/right as the structural OI contract."""
    out = {}
    for expiry, rows in ((snapshot or {}).get("rows_by_expiry") or {}).items():
        for row in rows:
            strike = _num(row.get("strike"))
            right = str(row.get("contract_type") or "").lower()
            iv = _num(row.get("iv"))
            if (strike is not None and right in ("call", "put") and
                    iv is not None and 0 < iv <= 5):
                out[(str(expiry), strike, right)] = iv
    return out


def _polygon_oi_structure(snapshot, spot, now):
    """Build OI-weighted GEX from a structural OI book and live London inputs.

    This is isolated from the London gamma×volume map: it may populate Net GEX,
    regime and the true OI flip, but it never replaces London walls or magnets.
    """
    overlay = _oi_overlay(snapshot)
    disabled_reason = (snapshot or {}).get("polygon_oi_disabled")
    legacy_polygon = bool((snapshot or {}).get("polygon_oi_overlay")) and bool(overlay)
    source = str(overlay.get("source") or
                 ("polygon_options_snapshot" if legacy_polygon else
                  ("disabled_polygon" if disabled_reason else "oi_overlay_unavailable")))
    base = {
        "status": "DATA",
        "source": source,
        "spot_source": "lse_realtime", "oi_semantics": "start_of_day_open_interest",
        "dealer_sign_convention": "calls_positive_puts_negative",
        "net_gex": None, "gross_gex": None, "flip": None, "roots": [],
        "regime": None, "contracts_total": 0, "contracts_oi_positive": 0,
        "contracts_usable": 0, "greeks_ok_pct_oi": None,
        "validation": "STRUCTURAL_CONTEXT_NOT_DIRECTIONAL_BACKTEST",
        "why": None,
    }
    if disabled_reason and not overlay:
        base["why"] = disabled_reason
        return base
    if overlay.get("status") != "OK":
        base["why"] = ((snapshot or {}).get("oi_overlay_error") or
                       (snapshot or {}).get("polygon_oi_error") or
                       "structural open_interest overlay unavailable")
        return base
    fetched = _num(overlay.get("fetched_at"))
    age = None if fetched is None else max(0.0, now - fetched)
    base.update({
        "fetched_at": fetched, "age_s": age, "fetch_date_et": overlay.get("fetch_date_et"),
        "expiries": overlay.get("expiries") or [], "coverage": overlay.get("coverage") or {},
        "pages": overlay.get("pages"), "cache": overlay.get("cache"),
        "strike_low": overlay.get("strike_low"), "strike_high": overlay.get("strike_high"),
    })
    if fetched is None or age > 36 * 3600:
        base["why"] = "%s OI snapshot stale or missing fetch timestamp" % source
        return base

    candidates, positive, usable = [], [], []
    lse_iv = _lse_iv_lookup(snapshot)
    for row in overlay.get("contracts") or []:
        strike = _num(row.get("strike"))
        oi = _num(row.get("open_interest"))
        iv = _num(row.get("iv"))
        expiry = str(row.get("expiry") or "")
        right = str(row.get("right") or "").lower()
        if iv is None:
            iv = lse_iv.get((expiry, strike, right))
        years = _expiry_years(expiry, now)
        if strike is None or oi is None or right not in ("call", "put"):
            continue
        contract = {"strike": strike, "right": "C" if right == "call" else "P",
                    "oi": oi, "iv": iv, "T": years, "exp": expiry}
        candidates.append(contract)
        if oi > 0:
            positive.append(contract)
            if iv is not None and 0 < iv <= 5 and years is not None:
                usable.append(contract)
    base["contracts_total"] = len(candidates)
    base["contracts_oi_positive"] = len(positive)
    base["contracts_usable"] = len(usable)
    base["greeks_ok_pct_oi"] = (len(usable) / len(positive) if positive else None)
    calls = sum(c["right"] == "C" for c in usable)
    puts = sum(c["right"] == "P" for c in usable)
    base["usable_calls"], base["usable_puts"] = calls, puts
    if len(usable) < 10 or calls < 3 or puts < 3:
        base["why"] = "insufficient positive-OI contracts with IV on both sides"
        return base
    if base["greeks_ok_pct_oi"] is None or base["greeks_ok_pct_oi"] < 0.50:
        base["why"] = "fewer than 50% of positive-OI contracts have usable IV"
        return base

    gex = build_gex(usable, spot, scale="dollar1pct")
    if gex.get("net_gex") is None:
        base["why"] = "OI book produced no usable gamma profile"
        return base
    base.update({
        "status": "OK", "net_gex": round(gex["net_gex"], 2),
        "gross_gex": round(gex.get("gross_gex") or 0.0, 2),
        "flip": round(gex["flip"], 4) if gex.get("flip") is not None else None,
        "roots": [round(value, 4) for value in (gex.get("roots") or [])],
        "regime": gex.get("regime"), "strike_span_pct": gex.get("strike_span_pct"),
        "oi_call_wall": gex.get("oi_call_wall"), "oi_put_wall": gex.get("oi_put_wall"),
        "gex_call_wall": gex.get("call_wall"), "gex_put_wall": gex.get("put_wall"),
        "flip_method": ("BS gamma repriced across hypothetical LSE spots; %s "
                         "start-of-day OI joined to matching London IV" % source),
        "why": ("measured OI zero crossing" if gex.get("flip") is not None else
                "complete OI profile has no zero crossing in observed strike range"),
    })
    return base


def _squeeze_fuel_structure(snapshot, spot, now, oi_structure=None):
    """Measure the *potential* upside options accelerator around live spot.

    This deliberately does not claim that equity shorts are covering, nor that
    dealers are short the calls.  The structural lane supplies start-of-day OI and
    London supplies matching IV plus spot; the metric is the share of nearby OI gamma sitting in
    calls above spot.  Live price velocity is attached separately by
    :func:`update_squeeze_fuel`.
    """
    oi_structure = oi_structure or _polygon_oi_structure(snapshot, spot, now)
    base = {
        "status": "DATA", "label": "DATA", "active": False,
        "source": ("disabled_polygon" if oi_structure.get("source") == "disabled_polygon"
                   else "%s_lse_iv_spot" % oi_structure.get("source", "oi")),
        "metric": "overhead_call_oi_gamma_share",
        "call_convexity_share_pct": None,
        "overhead_call_gex": None, "nearby_put_gex": None,
        "nearby_gross_gex": None, "book_gross_gex": None,
        "ladder": [], "next_fuel_strike": None,
        "corridor_pct": 5.0, "dealer_inventory_confirmed": False,
        "equity_short_interest_status": "DATA",
        "short_covering_confirmed": False,
        "validation": "UNPROVEN_FORWARD_AUDIT_ONLY",
        "guard": ("options convexity potential, not proof of dealer inventory or "
                  "equity short covering"),
        "why": None,
    }
    if oi_structure.get("status") != "OK":
        base["why"] = oi_structure.get("why") or "usable structural OI unavailable"
        return base

    calls, puts, book_gross = [], [], 0.0
    lse_iv = _lse_iv_lookup(snapshot)
    for row in _oi_overlay(snapshot).get("contracts") or []:
        strike = _num(row.get("strike"))
        oi = _num(row.get("open_interest"))
        iv = _num(row.get("iv"))
        right = str(row.get("right") or "").lower()
        expiry = str(row.get("expiry") or "")
        if iv is None:
            iv = lse_iv.get((expiry, strike, right))
        years = _expiry_years(expiry, now)
        if (strike is None or oi is None or oi <= 0 or iv is None or
                not (0 < iv <= 5) or years is None or right not in ("call", "put")):
            continue
        gamma = bs_gamma(spot, strike, years, iv)
        if gamma is None or not math.isfinite(gamma) or gamma <= 0:
            continue
        mass = gamma * oi * 100.0 * spot * spot * 0.01
        book_gross += mass
        item = {"strike": strike, "gex": mass, "expiry": row.get("expiry")}
        (calls if right == "call" else puts).append(item)

    upper, lower = spot * 1.05, spot * 0.95
    overhead = [item for item in calls if spot <= item["strike"] <= upper]
    downside = [item for item in puts if lower <= item["strike"] <= spot]
    call_mass = sum(item["gex"] for item in overhead)
    put_mass = sum(item["gex"] for item in downside)
    nearby = call_mass + put_mass
    if nearby <= 0 or not overhead:
        base["why"] = "no positive-OI call gamma above spot inside the +5% corridor"
        return base

    # Aggregate expiries at each strike so the UI can show a clean fuel ladder.
    by_strike = {}
    for item in overhead:
        by_strike[item["strike"]] = by_strike.get(item["strike"], 0.0) + item["gex"]
    strongest = sorted(by_strike.items(), key=lambda item: item[1], reverse=True)[:6]
    ladder = [{"strike": round(strike, 4), "gex": round(gex, 2)}
              for strike, gex in sorted(strongest)]
    share = 100.0 * call_mass / nearby
    state = "HIGH" if share >= 60 else "MED" if share >= 40 else "LOW"
    base.update({
        "status": "OK", "label": "POTENTIAL" if state != "LOW" else "LOW",
        "structural_state": state,
        "call_convexity_share_pct": round(share, 1),
        "overhead_call_gex": round(call_mass, 2),
        "nearby_put_gex": round(put_mass, 2),
        "nearby_gross_gex": round(nearby, 2),
        "book_gross_gex": round(book_gross, 2),
        "ladder": ladder,
        "next_fuel_strike": min(by_strike) if by_strike else None,
        "reference_spot": round(spot, 4), "reference_ts": int(now),
        "why": ("nearby overhead call OI gamma is %.1f%% of the symmetric ±5%% corridor; "
                "inventory sign remains unknown" % share),
    })
    return base


def update_squeeze_fuel(levels, spot, bars=None, now=None):
    """Attach live London velocity to the fixed Polygon OI fuel ladder.

    Thresholds are display conventions held in forward audit, not a backtested
    probability.  The percentage shown is a measured gamma share, never a win rate.
    """
    fuel = (levels or {}).get("squeeze_fuel")
    spot = _num(spot)
    if not isinstance(fuel, dict) or not spot or spot <= 0:
        return False
    before = (fuel.get("label"), fuel.get("active"), fuel.get("live_spot"),
              fuel.get("return_1m_pct"), fuel.get("return_5m_pct"),
              fuel.get("negative_gamma_accelerator"))
    fuel["live_spot"] = round(spot, 4)
    fuel["live_ts"] = int(now if now is not None else time.time())

    clean = []
    for row in bars or []:
        try:
            stamp, close = float(row[0]), float(row[4])
            if stamp > 0 and close > 0:
                clean.append((stamp, close))
        except (IndexError, TypeError, ValueError):
            continue
    clean.sort()
    r1 = r5 = None
    if clean:
        latest_ts = clean[-1][0]
        def prior(seconds):
            candidates = [close for stamp, close in clean if stamp <= latest_ts - seconds]
            return candidates[-1] if candidates else None
        p1, p5 = prior(60), prior(300)
        r1 = (spot / p1 - 1.0) * 100.0 if p1 else None
        r5 = (spot / p5 - 1.0) * 100.0 if p5 else None
    fuel["return_1m_pct"] = round(r1, 3) if r1 is not None else None
    fuel["return_5m_pct"] = round(r5, 3) if r5 is not None else None

    flip = _num((levels or {}).get("flip"))
    negative_gamma = flip is not None and spot < flip
    fuel["negative_gamma_accelerator"] = negative_gamma
    fuel["gamma_zone"] = "NEG" if negative_gamma else ("POS" if flip is not None else "DATA")
    share = _num(fuel.get("call_convexity_share_pct"))
    if fuel.get("status") != "OK" or share is None:
        fuel["label"], fuel["active"] = "DATA", False
    else:
        moving_up = r5 is not None and r5 >= 0.15 and (r1 is None or r1 > 0)
        active = moving_up and (negative_gamma or share >= 50.0)
        building = r5 is not None and r5 > 0 and share >= 40.0
        fuel["active"] = active
        fuel["label"] = ("ACTIVE" if active else "BUILD" if building else
                         "POTENTIAL" if negative_gamma or share >= 50.0 else "LOW")
    fuel["activation_rule"] = ("London return_5m >= +0.15%, return_1m > 0, and "
                               "(spot below OI flip or overhead call share >= 50%)")
    fuel["threshold_status"] = "UNVALIDATED_DISPLAY_CONVENTION_FORWARD_AUDIT"
    after = (fuel.get("label"), fuel.get("active"), fuel.get("live_spot"),
             fuel.get("return_1m_pct"), fuel.get("return_5m_pct"),
             fuel.get("negative_gamma_accelerator"))
    return before != after
def candidate_expiries(today=None, days=DISCOVERY_DAYS, *, include_today=True):
    today = today or dt.date.today()
    start = 0 if include_today else 1
    return [(today + dt.timedelta(days=i)).isoformat()
            for i in range(start, days + 1) if (today + dt.timedelta(days=i)).weekday() < 5]


def _next_friday(today, include_today=True):
    days = (4 - today.weekday()) % 7
    if days == 0 and not include_today:
        days = 7
    return (today + dt.timedelta(days=days)).isoformat()


def _fetch_expiries(client, sym, known, today, *, include_today=True):
    rows_by_expiry = {}
    floor = today if include_today else today + dt.timedelta(days=1)
    known = [e for e in (known or []) if e >= floor.isoformat()]
    # Preserve the closest known expiry but place the standard weekly Friday next.
    # This guarantees the weekly overlays without expanding three vault downloads
    # per symbol into five (important for the user's LSE byte quota).
    priority = ([known[0]] if known else []) + [_next_friday(today, include_today)] + known[1:]
    candidates = []
    for expiry in priority + candidate_expiries(today, include_today=include_today):
        if expiry not in candidates:
            candidates.append(expiry)
    for expiry in candidates:
        rows = client.options_chain(sym, expiry=expiry, limit=5000)
        if rows:
            rows_by_expiry[expiry] = rows
        if len(rows_by_expiry) >= MAX_EXPIRIES:
            break
    return rows_by_expiry


def _latest_trade_session(rows):
    """Keep one coherent option session from LSE's per-contract latest-trade rows."""
    dated = []
    for row in rows:
        ts = _epoch(row.get("last_trade_at"))
        if ts is not None:
            dated.append((dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date(), row))
    if not dated:
        return [], None, len(rows)
    latest = max(item[0] for item in dated)
    kept = [row for day, row in dated if day == latest]
    return kept, latest.isoformat(), len(rows) - len(kept)


def atomic_write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    os.replace(tmp, path)


def append_proxy_history(repo, sym, levels):
    """Archive one distinct London option fit for future untouched OOS tests."""
    asof = int(levels.get("asof") or time.time())
    day = dt.datetime.fromtimestamp(asof, tz=ET).date().isoformat()
    folder = os.path.join(repo, "data", "history", day)
    os.makedirs(folder, exist_ok=True)
    dealer_day = levels.get("dealer_activity_daily") or {}
    dealer_week = (levels.get("dealer_activity_weekly") or
                   levels.get("weekly_dealer_activity") or {})
    mm_day = levels.get("mm_top_profit_daily") or {}
    mm_week = (levels.get("mm_top_profit_weekly") or
               levels.get("mm_top_profit") or {})
    payload = {
        "name": "Milk public-geometry LSE proxies", "version": 1,
        "src": "lse", "sym": str(sym).upper(), "asof": asof,
        "spot": levels.get("spot"), "option_source_ts": levels.get("chain_ts"),
        "dealer_activity_daily": dealer_day,
        "dealer_activity_weekly": dealer_week,
        "mm_top_profit_daily": mm_day,
        "mm_top_profit_weekly": mm_week,
        "validation": "UNPROVEN_FORWARD_OOS_AUDIT_ONLY",
        "proprietary_replication": False,
    }
    path = os.path.join(folder, "lse_milk_proxies_%s.jsonl" % str(sym).lower())
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return path


def _weighted_quantile(weights, quantile):
    """Return a strike quantile from non-negative activity weights."""
    items = sorted((float(k), float(v)) for k, v in weights.items() if v > 0)
    total = sum(v for _, v in items)
    if not items or total <= 0:
        return None
    target, running = total * max(0.0, min(1.0, quantile)), 0.0
    for strike, value in items:
        running += value
        if running >= target:
            return strike
    return items[-1][0]


def _volume_pain(call_volume, put_volume, spot):
    """Volume-weighted max-profit strike proxy (never labelled as OI max pain)."""
    candidates = sorted(set(call_volume) | set(put_volume))
    if not candidates:
        return None
    def payout(price):
        calls_due = sum(v * max(price - strike, 0.0) for strike, v in call_volume.items())
        puts_due = sum(v * max(strike - price, 0.0) for strike, v in put_volume.items())
        return calls_due + puts_due
    return min(candidates, key=lambda price: (payout(price), abs(price - spot)))


def _activity_structure(rows_by_expiry, expiry, spot, now, source_ts,
                        next_refresh, horizon):
    """Return two disclosed, volume-only reference lines for one expiry.

    LSE does not expose open interest or dealer position signs.  Consequently:

    * ``delta_neutral_activity`` is the local price that zeroes
      sum(delta * volume) after first-order gamma linearisation.
    * ``mm_top_profit_volume_proxy`` minimizes terminal option payout using
      ``volume_today`` as weights.

    Neither value is dealer inventory, Net Dealer, OI max pain, nor RCG's PML.
    """
    if not expiry or expiry not in rows_by_expiry:
        return {
            "expiry": None, "status": "DATA", "level": None,
            "top_profit_level": None,
            "horizon": horizon,
            "why": "%s expiry was not returned by LSE" % horizon,
            "proprietary_replication": False,
        }
    rows = rows_by_expiry[expiry]
    expiry_source_ts = max((_epoch(row.get("last_trade_at") or row.get("updated_at")) or 0
                            for row in rows), default=0) or source_ts
    delta_net = gamma_gross = gamma_spot_mass = 0.0
    call_volume, put_volume, strikes = {}, {}, []
    usable_delta = usable_gamma = 0
    for row in rows:
        strike = _num(row.get("strike"))
        volume = _num(row.get("volume_today"))
        right = str(row.get("contract_type") or "").lower()
        if strike is None or volume is None or volume <= 0 or right not in ("call", "put"):
            continue
        strikes.append(strike)
        target = call_volume if right == "call" else put_volume
        target[strike] = target.get(strike, 0.0) + volume
        delta = _num(row.get("delta"))
        if delta is not None:
            delta_net += delta * volume * 100.0
            usable_delta += 1
        gamma = _num(row.get("gamma"))
        if gamma is not None and gamma > 0:
            gamma_mass = gamma * volume * 100.0
            gamma_gross += gamma_mass
            # Each LSE contract is a latest-trade record whose Greek was evaluated
            # at its own underlying_price. Linearise each delta from that recorded
            # base instead of today's live price; otherwise the target follows spot
            # one-for-one and ceases to be an independently useful reference.
            row_spot = _num(row.get("underlying_price")) or spot
            gamma_spot_mass += gamma_mass * row_spot
            usable_gamma += 1
    reference_spot = gamma_spot_mass / gamma_gross if gamma_gross > 0 else None
    raw_neutral = (reference_spot - delta_net / gamma_gross
                   if reference_spot is not None and usable_delta else None)
    low, high = (min(strikes), max(strikes)) if strikes else (None, None)
    plausible = (raw_neutral is not None and low is not None and low <= raw_neutral <= high)
    neutral = raw_neutral if plausible else None
    payout_min = _volume_pain(call_volume, put_volume, spot)
    status = "OK" if neutral is not None else "DATA"
    why = None
    if raw_neutral is None:
        why = "%s contracts lack usable delta/gamma activity" % horizon
    elif not plausible:
        why = "linearized neutral lies outside observed %s strike range" % horizon
    return {
        "expiry": expiry, "horizon": horizon, "asof": int(now),
        "option_source_ts": int(expiry_source_ts) if expiry_source_ts else None,
        "next_refresh_ts": int(next_refresh),
        "status": status,
        "level": round(neutral, 4) if neutral is not None else None,
        "raw_level": round(raw_neutral, 4) if raw_neutral is not None else None,
        "top_profit_level": round(payout_min, 4) if payout_min is not None else None,
        "delta_volume_net": round(delta_net, 4),
        "gamma_volume_gross": round(gamma_gross, 4),
        "gamma_weighted_reference_spot": (round(reference_spot, 4)
                                            if reference_spot is not None else None),
        "observed_strike_low": low, "observed_strike_high": high,
        "contracts_with_delta": usable_delta, "contracts_with_gamma": usable_gamma,
        "method": "sum(gamma*volume*underlying_price)/sum(gamma*volume) - sum(delta*volume)/sum(gamma*volume)",
        "top_profit_method": "volume_today-weighted terminal-payout minimizer",
        "price_relation_updates": "LSE underlying WebSocket",
        "option_refit_interval_s": REFRESH_S,
        "why": why,
        "proprietary_replication": False,
        "validation": "UNPROVEN_LSE_ACTIVITY_PROXY_CONTEXT_ONLY",
    }


def _weekly_activity_structure(rows_by_expiry, spot, now, source_ts, next_refresh):
    """Compatibility wrapper for the standard-Friday structure."""
    fridays = sorted(expiry for expiry in rows_by_expiry
                     if dt.date.fromisoformat(expiry).weekday() == 4)
    expiry = fridays[0] if fridays else None
    return _activity_structure(rows_by_expiry, expiry, spot, now, source_ts,
                               next_refresh, "weekly Friday")


def _mm_snapshot(sym, spot, calls, puts, call_volume, put_volume,
                 source_ts, source_date, now):
    """Reproducible London proxy for the four lines in the supplied MM chart.

    Russell Capital Group's MM calculation is proprietary.  We preserve its public
    geometry while publishing the exact substitute: gamma×volume weighted deciles
    and median, plus a volume-weighted terminal-payout minimizer.
    """
    mass = {strike: calls.get(strike, 0.0) + puts.get(strike, 0.0)
            for strike in set(calls) | set(puts)}
    floor = _weighted_quantile(mass, 0.10)
    green = _weighted_quantile(mass, 0.50)
    ceiling = _weighted_quantile(mass, 0.90)
    pml = _volume_pain(call_volume, put_volume, spot)
    if None in (floor, green, ceiling, pml):
        return None
    dead_low, dead_high = sorted((green, pml))
    pivot = (green + pml) / 2.0
    q = {
        "puts_at_or_above_green": sum(v for strike, v in put_volume.items() if strike >= green),
        "puts_below_green": sum(v for strike, v in put_volume.items() if strike < green),
        "calls_at_or_above_green": sum(v for strike, v in call_volume.items() if strike >= green),
        "calls_below_green": sum(v for strike, v in call_volume.items() if strike < green),
    }
    return {
        "sym": sym, "spot": round(spot, 4), "asof": int(now),
        "source_ts": int(source_ts) if source_ts else None,
        "source_date": source_date,
        "ceiling": round(ceiling, 4), "floor": round(floor, 4),
        "green_line": round(green, 4), "pml": round(pml, 4),
        "dead_zone_low": round(dead_low, 4), "dead_zone_high": round(dead_high, 4),
        "dead_zone_mid": round(pivot, 4),
        "quadrants": q,
        "call_volume": round(sum(call_volume.values()), 2),
        "put_volume": round(sum(put_volume.values()), 2),
        "gamma_volume_mass": round(sum(mass.values()), 6),
        "method": "LSE gamma×volume q10/q50/q90 + volume-weighted payout minimizer",
        "proprietary_replication": False,
    }


def _mm_fractal_state(sym, snapshot, now, next_refresh, state_path=None):
    """Freeze the prior-session OMM pivot and update the post-09:45 DMM magnet."""
    if not snapshot:
        return None
    local = dt.datetime.fromtimestamp(now, tz=ET)
    market_date = local.date().isoformat()
    source_date = snapshot.get("source_date") or market_date
    lane = "OMM" if source_date < market_date or local.time() < DMM_START else "DMM"
    state = {"market_date": market_date, "overnight": None, "intraday": None}
    if state_path:
        try:
            with open(state_path, encoding="utf-8") as fh:
                saved = json.load(fh)
            if saved.get("market_date") == market_date:
                state.update(saved)
        except (OSError, TypeError, ValueError):
            pass
    snap = dict(snapshot)
    snap["lane"] = lane
    if lane == "OMM":
        state["overnight"] = snap
    else:
        state["intraday"] = snap
    omm, dmm = state.get("overnight"), state.get("intraday")
    omm_pivot = omm.get("dead_zone_mid") if omm else None
    dmm_magnet = dmm.get("dead_zone_mid") if dmm else None
    if omm_pivot is None:
        bias = "DATA"
    elif snapshot["spot"] > omm_pivot:
        bias = "BULLISH"
    elif snapshot["spot"] < omm_pivot:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    payload = {
        "name": "London MM Fractal Proxy", "version": 1, "src": "lse",
        "market_date": market_date, "asof": int(now), "next_refresh_ts": next_refresh,
        "overnight": omm, "intraday": dmm, "active_lane": lane,
        "active": dmm if lane == "DMM" else omm,
        "omm_pivot": omm_pivot, "dmm_magnet": dmm_magnet,
        "bias": bias,
        "omm_rule": "overnight dead zone = pivot; above bullish, below bearish",
        "dmm_rule": "intraday dead zone after 09:45 ET = magnet",
        "proprietary_replication": False,
        "validation": "UNPROVEN_LSE_PROXY_CONTEXT_ONLY",
        "note": "RCG geometry with disclosed London substitutes; no dealer inventory claim",
    }
    if state_path:
        atomic_write(state_path, {"market_date": market_date,
                                  "overnight": omm, "intraday": dmm})
    return payload


def _snapshot_from_raw(raw_by_expiry):
    """Normalize latest-per-contract rows and reject whole stale expiries.

    A coherent expiry can still belong to yesterday while another expiry has
    already traded today.  Mixing both makes yesterday's 0DTE volume move today's
    walls.  The newest session present in the requested chain is the active one;
    older expiries are retained only in the audit metadata, never in calculations.
    """
    coherent_by_expiry, session_dates, dropped_rows = {}, {}, 0
    for expiry, rows in (raw_by_expiry or {}).items():
        coherent, session_date, n_dropped = _latest_trade_session(rows)
        if coherent and session_date:
            coherent_by_expiry[expiry] = [dict(row) for row in coherent]
            session_dates[expiry] = session_date
            dropped_rows += n_dropped
    if not coherent_by_expiry:
        return None
    active_session = max(session_dates.values())
    excluded = {
        expiry: {"session_date": session_dates[expiry], "reason": "older_than_active_session"}
        for expiry in coherent_by_expiry if session_dates[expiry] != active_session
    }
    rows_by_expiry = {
        expiry: rows for expiry, rows in coherent_by_expiry.items()
        if session_dates[expiry] == active_session
    }
    active_dates = {expiry: session_dates[expiry] for expiry in rows_by_expiry}
    return {
        "rows_by_expiry": rows_by_expiry,
        "session_dates": active_dates,
        "active_session_date": active_session,
        "excluded_expiries": excluded,
        "stale_session_rows_dropped": dropped_rows,
    }


def apply_option_tick(snapshot, sym, message):
    """Apply one official LSE option-print tick to a REST Greek baseline.

    WebSocket ticks carry print size but no Greeks.  We therefore increment the
    REST row's cumulative ``volume_today`` and keep its last model gamma.  Unknown
    contracts are ignored until the next REST reconciliation instead of inventing
    a Greek.
    """
    if not snapshot or not isinstance(message, dict):
        return False
    ticker = str(message.get("symbol") or "").upper()
    match = OSI_RE.match(ticker)
    if not match or match.group(1) != str(sym).upper():
        return False
    expiry = "20%s-%s-%s" % (match.group(2)[:2], match.group(2)[2:4], match.group(2)[4:6])
    rows = snapshot.get("rows_by_expiry", {}).get(expiry)
    if not rows:
        return False
    size = _num(message.get("volume"))
    price = _num(message.get("price"))
    if size is None or size <= 0:
        return False
    row = next((item for item in rows
                if str(item.get("ticker") or item.get("symbol") or "").upper() == ticker), None)
    if row is None:
        strike = int(match.group(4)) / 1000.0
        right = "call" if match.group(3) == "C" else "put"
        row = next((item for item in rows
                    if _num(item.get("strike")) == strike and
                    str(item.get("contract_type") or "").lower() == right), None)
    if row is None or _num(row.get("gamma")) is None:
        return False
    stamp = message.get("ts") or message.get("timestamp")
    _record_option_print(snapshot, row, message, size, price, stamp)
    row["volume_today"] = max(0.0, _num(row.get("volume_today")) or 0.0) + size
    if price is not None and price >= 0:
        row["last_price"] = price
        row["premium_today"] = (_num(row.get("premium_today")) or 0.0) + price * size * 100.0
    if stamp:
        row["last_trade_at"] = str(stamp)
    snapshot["last_ws_tick_ts"] = _epoch(stamp) or time.time()
    snapshot["ws_events"] = int(snapshot.get("ws_events") or 0) + 1
    return True


def reprice_levels(levels, spot):
    """Move wall-side selection with live spot using the latest option profiles."""
    spot = _num(spot)
    if not levels or not spot or spot <= 0:
        return False
    calls = {float(x["strike"]): abs(float(x["gamma_volume"]))
             for x in levels.get("call_profile", []) if x.get("gamma_volume") is not None}
    puts = {float(x["strike"]): abs(float(x["gamma_volume"]))
            for x in levels.get("put_profile", []) if x.get("gamma_volume") is not None}
    call_candidates = {k: v for k, v in calls.items() if k >= spot}
    put_candidates = {k: v for k, v in puts.items() if k <= spot}
    call_wall = max(call_candidates, key=call_candidates.get) if call_candidates else None
    put_wall = max(put_candidates, key=put_candidates.get) if put_candidates else None
    before = (levels.get("call_wall"), levels.get("put_wall"))
    levels["spot"] = spot
    levels["call_wall"] = call_wall
    levels["call_wall_gex"] = calls.get(call_wall)
    levels["put_wall"] = put_wall
    levels["put_wall_gex"] = -puts[put_wall] if put_wall is not None else None
    return before != (call_wall, put_wall)


def build(sym, spot, known_expiries=None, client=None, now=None, refresh_s=REFRESH_S,
          mm_state_path=None, snapshot=None, return_snapshot=False):
    """Return ``(heatmap, levels, expiries)`` using only LSE option-chain rows."""
    sym = str(sym).upper()
    spot = _num(spot)
    if not spot or spot <= 0:
        raise RuntimeError("%s sin spot London válido" % sym)
    now = float(now if now is not None else time.time())
    local_now = dt.datetime.fromtimestamp(now, tz=ET)
    today = local_now.date()
    # At 16:00 ET today's contracts have expired.  LSE returns each contract's latest
    # trade, so retaining the old 0DTE after the close silently mixes an expired session
    # into tomorrow's live profile and can move walls/magnets with yesterday's volume.
    include_today = local_now.time() < OPTION_ROLL_TIME
    owns_client = client is None and snapshot is None
    if snapshot is None:
        client = client or LSE()
        raw_by_expiry = _fetch_expiries(client, sym, known_expiries, today,
                                        include_today=include_today)
        if not raw_by_expiry:
            raise RuntimeError("%s sin vencimientos LSE con contratos en %d días"
                               % (sym, DISCOVERY_DAYS))
        snapshot = _snapshot_from_raw(raw_by_expiry)
    if not snapshot or not snapshot.get("rows_by_expiry"):
        raise RuntimeError("%s LSE sin contratos de una sesión activa coherente" % sym)
    rows_by_expiry = snapshot["rows_by_expiry"]
    session_dates = snapshot.get("session_dates") or {}
    dropped = int(snapshot.get("stale_session_rows_dropped") or 0)

    grid, calls, puts, call_volume, put_volume = {}, {}, {}, {}, {}
    source_epochs = []
    contracts = 0
    for expiry, rows in rows_by_expiry.items():
        for row in rows:
            strike, gamma, volume = (_num(row.get("strike")), _num(row.get("gamma")),
                                     _num(row.get("volume_today")))
            right = str(row.get("contract_type") or "").lower()
            if strike is None or not volume or volume <= 0:
                continue
            if right not in ("call", "put"):
                continue
            volume_target = call_volume if right == "call" else put_volume
            volume_target[strike] = volume_target.get(strike, 0.0) + volume
            ts = _epoch(row.get("last_trade_at") or row.get("updated_at"))
            if ts is not None:
                source_epochs.append(ts)
            if gamma is None or gamma < 0:
                continue
            raw = gamma * volume * 100.0
            signed = raw if right == "call" else -raw
            grid.setdefault(strike, {})[expiry] = grid.setdefault(strike, {}).get(expiry, 0.0) + signed
            target = calls if right == "call" else puts
            target[strike] = target.get(strike, 0.0) + raw
            contracts += 1
    if not grid:
        raise RuntimeError("%s LSE sin contratos con gamma y volume_today" % sym)

    expiries = sorted(rows_by_expiry)
    live = [k for k, row in grid.items() if any(abs(row.get(e, 0.0)) > 0 for e in expiries)]
    strikes = sorted(sorted(live, key=lambda k: abs(k - spot))[:MAX_ROWS], reverse=True)
    cells, mvc = [], None
    for strike in strikes:
        line = []
        for expiry in expiries:
            value = grid.get(strike, {}).get(expiry)
            line.append(value)
            if value is not None and (mvc is None or abs(value) > abs(mvc[2])):
                mvc = (strike, expiry, value)
        cells.append(line)

    scale = spot * spot * 0.01
    profile_raw = {k: sum(row.values()) for k, row in grid.items()}
    profile = [{"strike": k, "gex": round(v * scale, 2),
                "gamma_volume": round(v * scale, 2)}
               for k, v in sorted(profile_raw.items())]
    call_profile = [{"strike": k, "gamma_volume": round(v * scale, 2)}
                    for k, v in sorted(calls.items())]
    put_profile = [{"strike": k, "gamma_volume": round(v * scale, 2)}
                   for k, v in sorted(puts.items())]
    # A wall has a side. The old global maximum could put a call wall below spot
    # or a put wall above spot, which is not a usable wall definition.
    call_candidates = {k: v for k, v in calls.items() if k >= spot}
    put_candidates = {k: v for k, v in puts.items() if k <= spot}
    call_wall = max(call_candidates, key=call_candidates.get) if call_candidates else None
    put_wall = max(put_candidates, key=put_candidates.get) if put_candidates else None
    magnet = max(profile_raw, key=lambda k: abs(profile_raw[k])) if profile_raw else None
    source_ts = max(source_epochs) if source_epochs else None
    if snapshot.get("rest_refresh_due") is None:
        snapshot["rest_refresh_due"] = int(now + refresh_s)
    next_refresh = int(snapshot["rest_refresh_due"])
    stale = source_ts is None or now - source_ts > STALE_S
    col_totals = [sum(grid.get(k, {}).get(e) or 0.0 for k in grid) for e in expiries]

    architect = architect_lse.compute(rows_by_expiry, spot, now, source_ts, session_dates)
    activity_flip_detail = _activity_flip(rows_by_expiry, spot, now)
    activity_flip = activity_flip_detail.get("level")
    option_tape = _option_tape_context(snapshot)
    oi_structure = _polygon_oi_structure(snapshot, spot, now)
    squeeze_fuel = _squeeze_fuel_structure(snapshot, spot, now, oi_structure)
    daily_expiry = expiries[0]
    friday_expiries = [expiry for expiry in expiries
                       if dt.date.fromisoformat(expiry).weekday() == 4]
    weekly_expiry = friday_expiries[0] if friday_expiries else None
    daily_activity = _activity_structure(
        rows_by_expiry, daily_expiry, spot, now, source_ts, next_refresh,
        "daily nearest-active")
    weekly_activity = _activity_structure(
        rows_by_expiry, weekly_expiry, spot, now, source_ts, next_refresh,
        "weekly Friday")
    source_date = max(session_dates.values()) if session_dates else None
    mm_snapshot = _mm_snapshot(sym, spot, calls, puts, call_volume, put_volume,
                               source_ts, source_date, now)
    if mm_state_path is None and owns_client:
        mm_state_path = os.path.join(OUTDIR, "lse_mm_fractal_%s.json" % sym.lower())
    mm_fractal = _mm_fractal_state(sym, mm_snapshot, now, next_refresh, mm_state_path)
    nearest_em = next((item.get("expected_move_model") for item in architect["expiries"]
                       if item.get("expected_move_model")), None)
    nearest_expiry = next((item.get("expiry") for item in architect["expiries"]
                           if item.get("expected_move_model")), None)
    oi_source = oi_structure.get("source") or "oi_overlay_unavailable"
    heatmap = {
        "sym": sym, "spot": spot,
        "date": (dt.datetime.fromtimestamp(source_ts).date().isoformat() if source_ts else None),
        "ts": int(now), "fetch_ts": int(now), "source_ts": int(source_ts) if source_ts else None,
        "next_refresh_ts": next_refresh, "refresh_interval_s": int(refresh_s),
        "expiries": expiries, "strikes": strikes, "cells": cells,
        "mvc": ({"strike": mvc[0], "expiry": mvc[1], "gamma_volume_raw": mvc[2]}
                if mvc else None),
        "col_totals": col_totals, "gamma_volume_total_raw": sum(col_totals),
        "src": "lse", "metric": "gamma_volume",
        "oi_available": oi_structure.get("status") == "OK",
        "oi_source": oi_source,
        "contracts_used": contracts, "stale": stale,
        "session_dates": session_dates, "stale_session_rows_dropped": dropped,
        "active_session_date": snapshot.get("active_session_date"),
        "excluded_expiries": snapshot.get("excluded_expiries") or {},
        "update_mode": "websocket_prints_rest_greeks",
        "ws_events": int(snapshot.get("ws_events") or 0),
        "magnet": magnet,
        "magnet_gamma_volume": round(profile_raw[magnet] * scale, 2) if magnet is not None else None,
        "architect": architect,
        "daily_activity": daily_activity,
        "weekly_activity": weekly_activity,
        "mm_fractal": mm_fractal,
        "activity_flip": activity_flip_detail,
        "option_tape": option_tape,
        "oi_structure": oi_structure,
        "squeeze_fuel": squeeze_fuel,
        "note": ("heatmap gamma × volume_today de LSE; OI/flip estructural separado de %s" %
                 oi_source
                 if oi_structure.get("status") == "OK" else
                 "gamma × volume_today; sin open interest válido, no es Net GEX"),
    }
    refresh = {k: next_refresh for k in ("heatmap", "walls", "magnets", "gamma_flip")}
    refresh["interval_s"] = int(refresh_s)
    levels = {
        "sym": sym, "spot": spot, "asof": int(now),
        "chain_ts": int(source_ts) if source_ts else None,
        "chain_src": "lse_gamma_volume", "profile_metric": "gamma_volume",
        "profile": profile, "net_gex": oi_structure.get("net_gex"),
        "gamma_volume_total": round(sum(col_totals) * scale, 2),
        "call_profile": call_profile, "put_profile": put_profile,
        "call_wall": call_wall,
        "call_wall_gex": round(calls[call_wall] * scale, 2) if call_wall is not None else None,
        "call_wall_kind": None,
        "put_wall": put_wall,
        "put_wall_gex": round(-puts[put_wall] * scale, 2) if put_wall is not None else None,
        "put_wall_kind": None,
        "abs_wall": magnet,
        "abs_wall_gex": round(profile_raw[magnet] * scale, 2) if magnet is not None else None,
        "abs_wall_kind": None,
        "magnet": magnet, "magnet_metric": "gamma_volume",
        "architect": architect,
        "mm_fractal": mm_fractal,
        "em": nearest_em.get("move") if nearest_em else None,
        "em_why": nearest_em.get("method") if nearest_em else "LSE sin IV ATM util",
        "exp": nearest_expiry.replace("-", "") if nearest_expiry else None,
        "dte": nearest_em.get("dte_model") if nearest_em else None,
        "scope": (("LSE realtime · OI DATA · %d expiries" % len(expiries))
                  if oi_structure.get("status") != "OK" else
                  ("LSE realtime + %s · %d expiries" % (oi_source, len(expiries)))),
        "flip": oi_structure.get("flip"),
        "flip_why": oi_structure.get("why"),
        "flip_src": ("%s_lse_spot_repriced" % oi_source if oi_structure.get("status") == "OK"
                     else "none"),
        "regime": oi_structure.get("regime"),
        "oi_available": oi_structure.get("status") == "OK",
        "oi_source": oi_source,
        "oi_structure": oi_structure,
        "oi_gross_gex": oi_structure.get("gross_gex"),
        "squeeze_fuel": squeeze_fuel,
        "activity_flip": activity_flip,
        "activity_flip_strength": activity_flip_detail.get("gross_gamma_volume_at_level"),
        "activity_flip_detail": activity_flip_detail,
        "option_tape": option_tape,
        "refresh": refresh, "stale": stale, "contracts_used": contracts,
        "active_session_date": snapshot.get("active_session_date"),
        "excluded_expiries": snapshot.get("excluded_expiries") or {},
        "update_mode": "websocket_prints_rest_greeks",
        "ws_events": int(snapshot.get("ws_events") or 0),
        "source_note": "LSE gamma × volume_today; contexto, no dealer GEX ni gatillo",
    }
    update_squeeze_fuel(levels, spot, now=now)
    def dealer_proxy(activity):
        return {
            "level": activity.get("level"),
            "raw_level": activity.get("raw_level"),
            "gamma_weighted_reference_spot": activity.get("gamma_weighted_reference_spot"),
            "expiry": activity.get("expiry"), "horizon": activity.get("horizon"),
            "status": activity.get("status"), "why": activity.get("why"),
            "option_source_ts": activity.get("option_source_ts"),
            "next_refresh_ts": next_refresh, "method": activity.get("method"),
            "validation": activity.get("validation"), "proprietary_replication": False,
        }
    def mm_proxy(activity):
        level = activity.get("top_profit_level")
        return {
            "level": level, "expiry": activity.get("expiry"),
            "horizon": activity.get("horizon"),
            "status": "OK" if level is not None else "DATA",
            "why": (None if level is not None else
                    "%s calls/puts lack usable volume_today" % activity.get("horizon", "selected")),
            "option_source_ts": activity.get("option_source_ts"),
            "next_refresh_ts": next_refresh, "method": activity.get("top_profit_method"),
            "validation": activity.get("validation"), "proprietary_replication": False,
        }
    levels["dealer_activity_daily"] = dealer_proxy(daily_activity)
    levels["dealer_activity_weekly"] = dealer_proxy(weekly_activity)
    levels["mm_top_profit_daily"] = mm_proxy(daily_activity)
    levels["mm_top_profit_weekly"] = mm_proxy(weekly_activity)
    # Old weekly keys remain aliases for saved clients and downstream readers.
    levels["weekly_dealer_activity"] = levels["dealer_activity_weekly"]
    levels["mm_top_profit"] = levels["mm_top_profit_weekly"]
    result = (heatmap, levels, expiries)
    return result + (snapshot,) if return_snapshot else result
