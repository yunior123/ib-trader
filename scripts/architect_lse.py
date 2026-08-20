#!/usr/bin/env python3
"""Architect-style options activity from London Strategic Edge rows.

This is an honest activity indicator, not dealer positioning. LSE exposes model
greeks, ``volume_today`` and ``premium_today`` but no open interest. Consequently
the module never emits GEX, a gamma flip, or dealer-long/dealer-short claims.
"""
import datetime as dt
import glob
import json
import math
import os
from zoneinfo import ZoneInfo

from gex_core import bs_charm, bs_vanna

MIN_T_YEARS = 5.0 / (365.0 * 24.0 * 60.0)
SCORE_THRESHOLD = 20.0  # display convention; not validated by the historical study


def _num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _balance(net, gross):
    return None if not gross else max(-1.0, min(1.0, net / gross))


def _years(row, expiry, now):
    try:
        source = dt.datetime.fromisoformat(
            str(row.get("last_trade_at") or row.get("updated_at")).replace("Z", "+00:00"))
        if source.tzinfo is None:
            source = source.replace(tzinfo=dt.timezone.utc)
        end = dt.datetime.combine(dt.date.fromisoformat(expiry), dt.time(16),
                                  tzinfo=ZoneInfo("America/New_York"))
        return max(MIN_T_YEARS, (end.timestamp() - source.timestamp()) / (365.0 * 86400.0))
    except (TypeError, ValueError):
        return None  # dte entero no recupera las horas restantes de 0DTE honestamente


def _rr25(rows):
    calls, puts = [], []
    for row in rows:
        iv, delta = _num(row.get("iv")), _num(row.get("delta"))
        right = str(row.get("contract_type") or "").lower()
        if iv is None or not (0 < iv <= 5) or delta is None:
            continue
        if right == "call" and 0 < delta < 1:
            calls.append((abs(delta - 0.25), iv, delta, _num(row.get("strike"))))
        elif right == "put" and -1 < delta < 0:
            puts.append((abs(abs(delta) - 0.25), iv, delta, _num(row.get("strike"))))
    if not calls or not puts:
        return None
    call, put = min(calls), min(puts)
    if call[0] > 0.15 or put[0] > 0.15:
        return None
    return {
        "rr25_vol_points": round(100.0 * (call[1] - put[1]), 3),
        "call_iv": round(call[1], 6), "put_iv": round(put[1], 6),
        "call_delta": round(call[2], 4), "put_delta": round(put[2], 4),
        "call_strike": call[3], "put_strike": put[3],
    }


def _model_expected_move(rows, spot, expiry, now):
    candidates = []
    for row in rows:
        iv, delta = _num(row.get("iv")), _num(row.get("delta"))
        if iv is None or not (0 < iv <= 5) or delta is None:
            continue
        dist = abs(abs(delta) - 0.5)
        if dist <= 0.2:
            candidates.append((dist, iv, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    chosen = candidates[:2]
    iv = sum(item[1] for item in chosen) / len(chosen)
    years = _years(chosen[0][2], expiry, now)
    if years is None:
        return None
    move = spot * iv * math.sqrt(years)
    return {"move": round(move, 4), "move_pct": round(100.0 * move / spot, 3),
            "dte_model": round(years * 365.0, 4),
            "atm_iv": round(iv, 6), "method": "spot*ATM_IV*sqrt(T); no es straddle"}


def compute(rows_by_expiry, spot, now, option_source_ts=None, source_session_dates=None):
    """Return a descriptive Architect activity payload.

    The score equally weights available gamma-volume, delta-volume and premium
    call/put balances. Vanna/charm stay separate because their realized effect needs
    an observed volatility or time shock.
    """
    spot = _num(spot)
    if spot is None or spot <= 0:
        raise ValueError("spot London invalido")
    now = float(now)
    gamma_net = gamma_gross = delta_net = delta_gross = 0.0
    premium_call = premium_put = 0.0
    vanna_net = vanna_gross = charm_net = charm_gross = 0.0
    used = 0
    expiries = []

    for expiry, rows in sorted(rows_by_expiry.items()):
        expiries.append({"expiry": expiry, "rr25": _rr25(rows),
                         "expected_move_model": _model_expected_move(rows, spot, expiry, now)})
        for row in rows:
            volume = _num(row.get("volume_today"))
            right = str(row.get("contract_type") or "").lower()
            if volume is None or volume <= 0 or right not in ("call", "put"):
                continue
            used += 1
            side = 1.0 if right == "call" else -1.0
            gamma = _num(row.get("gamma"))
            if gamma is not None and gamma >= 0:
                value = side * gamma * volume * 100.0
                gamma_net += value; gamma_gross += abs(value)
            delta = _num(row.get("delta"))
            if delta is not None and -1 <= delta <= 1:
                value = delta * volume * 100.0
                delta_net += value; delta_gross += abs(value)
            premium = _num(row.get("premium_today"))
            if premium is not None and premium >= 0:
                if right == "call": premium_call += premium
                else: premium_put += premium
            strike, iv = _num(row.get("strike")), _num(row.get("iv"))
            years = _years(row, expiry, now)
            if strike is None or iv is None or not (0 < iv <= 5) or years is None:
                continue
            # Call-plus/put-minus is an activity convention, not a dealer inventory sign.
            vanna = side * bs_vanna(spot, strike, years, iv) * volume * 100.0
            charm = side * bs_charm(spot, strike, years, iv, right[0].upper()) * volume * 100.0
            if math.isfinite(vanna): vanna_net += vanna; vanna_gross += abs(vanna)
            if math.isfinite(charm): charm_net += charm; charm_gross += abs(charm)

    premium_gross = premium_call + premium_put
    components = {
        "gamma_volume_balance": _balance(gamma_net, gamma_gross),
        "delta_volume_balance": _balance(delta_net, delta_gross),
        "premium_balance": _balance(premium_call - premium_put, premium_gross),
    }
    available = [value for value in components.values() if value is not None]
    score = 100.0 * sum(available) / len(available) if available else None
    side = ("NO_DATA" if score is None else "CALL_ACTIVITY" if score > SCORE_THRESHOLD
            else "PUT_ACTIVITY" if score < -SCORE_THRESHOLD else "MIXED")
    rr_values = [item["rr25"]["rr25_vol_points"] for item in expiries if item["rr25"]]
    vb, cb = _balance(vanna_net, vanna_gross), _balance(charm_net, charm_gross)
    return {
        "name": "Architect LSE Activity", "version": 1, "src": "lse",
        "asof": int(now), "fetch_ts": int(now), "spot": spot, "contracts_used": used,
        "option_source_ts": int(option_source_ts) if option_source_ts else None,
        "source_session_dates": source_session_dates or {},
        "oi_available": False, "dealer_gex_available": False,
        "activity_score": round(score, 2) if score is not None else None,
        "activity_side": side,
        "components": {key: (round(value, 6) if value is not None else None)
                       for key, value in components.items()},
        "vanna_volume_balance": round(vb, 6) if vb is not None else None,
        "charm_volume_balance": round(cb, 6) if cb is not None else None,
        "raw": {
            "gamma_volume_net": round(gamma_net, 6),
            "gamma_volume_gross": round(gamma_gross, 6),
            "delta_volume_net": round(delta_net, 6),
            "delta_volume_gross": round(delta_gross, 6),
            "call_premium": round(premium_call, 2),
            "put_premium": round(premium_put, 2),
        },
        "rr25_mean_vol_points": (round(sum(rr_values) / len(rr_values), 3)
                                  if rr_values else None),
        "expiries": expiries,
        "score_weights": "equal among available gamma-volume, delta-volume, premium balances",
        "threshold": SCORE_THRESHOLD, "threshold_is_convention_not_measured": True,
        "validation": "UNPROVEN_DESCRIPTIVE_SIGNAL_ONLY",
        "note": "actividad de opciones London; sin OI no es posicionamiento dealer ni GEX",
    }


def load_prior_distinct(repo, sym, current_source_ts):
    """Return the newest archived payload from a different upstream option snapshot."""
    pattern = os.path.join(repo, "data", "history", "*",
                           "lse_architect_%s_5m.jsonl" % str(sym).lower())
    for path in sorted(glob.glob(pattern), reverse=True)[:4]:
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()[-600:]
        except OSError:
            continue
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            source_ts = row.get("option_source_ts")
            if source_ts and source_ts != current_source_ts:
                return row
    return None


def _value_rejection(bars, levels, now):
    """Detect completed-bar rejection of a measured London wall/magnet."""
    completed = [b for b in (bars or []) if len(b) >= 5 and b[0] + 60 <= now][-12:]
    if not completed:
        return {"available": False, "state": "DATA", "reason": "sin velas 1m cerradas"}
    candidates = []
    cw, pw, mag = (_num(levels.get("call_wall")), _num(levels.get("put_wall")),
                   _num(levels.get("magnet")))
    if cw is not None:
        candidates.append(("BEARISH", "CALL_WALL", cw))
    if pw is not None:
        candidates.append(("BULLISH", "PUT_WALL", pw))
    ref = _num(levels.get("spot"))
    if mag is not None and mag not in (cw, pw) and ref is not None:
        candidates.append(("BEARISH" if mag >= ref else "BULLISH", "MAGNET", mag))
    events = []
    for direction, kind, level in candidates:
        for bar in completed:
            epoch, high, low, close = int(bar[0]), _num(bar[2]), _num(bar[3]), _num(bar[4])
            if None in (high, low, close):
                continue
            rejected = (direction == "BEARISH" and high >= level and close < level) or (
                direction == "BULLISH" and low <= level and close > level)
            if rejected:
                events.append((epoch, direction, kind, level, close))
    if not events:
        return {"available": True, "state": "NONE", "direction": None,
                "reason": "sin cierre de rechazo en los últimos 12 minutos"}
    epoch, direction, kind, level, close = max(events)
    return {"available": True, "state": "CONFIRMED", "direction": direction,
            "level_kind": kind, "level": level, "bar_ts": epoch, "close": close,
            "reason": "tocó/cruzó valor y cerró de vuelta"}


def _snapshot_comparison(current, prior):
    if not prior:
        return None, "sin snapshot London previo con option_source_ts distinto"
    cur_dates = current.get("source_session_dates") or {}
    old_dates = prior.get("source_session_dates") or {}
    if not cur_dates or cur_dates != old_dates:
        return None, "cobertura/sesión de contratos cambió; no comparar acumulados"
    cur_raw, old_raw = current.get("raw") or {}, prior.get("raw") or {}
    needed = (cur_raw.get("delta_volume_net"), cur_raw.get("delta_volume_gross"),
              old_raw.get("delta_volume_net"), old_raw.get("delta_volume_gross"),
              current.get("spot"), prior.get("spot"))
    if any(_num(value) is None for value in needed):
        return None, "snapshot sin totales delta×volume o spot"
    gross = max(float(cur_raw["delta_volume_gross"]),
                float(old_raw["delta_volume_gross"]), 1.0)
    return {
        "delta_impulse": (float(cur_raw["delta_volume_net"])
                          - float(old_raw["delta_volume_net"])) / gross,
        "price_change_pct": 100.0 * (float(current["spot"]) / float(prior["spot"]) - 1.0),
        "prior_source_ts": prior.get("option_source_ts"),
    }, None


def reversal_triad(current, prior, bars, levels, now):
    """Order-flow reversal contract at Architect value; LSE context stays separate."""
    value = _value_rejection(bars, levels, now)
    comparison, why = _snapshot_comparison(current, prior)
    missing = "LSE no entrega ejecuciones Bid×Ask ni aggressor side"
    absorption = {"available": False, "state": "DATA", "direction": None,
                  "reason": missing + "; OHLCV/volume_today no prueban absorción"}
    delta_change = {"available": False, "state": "DATA", "direction": None,
                    "reason": missing + "; Delta footprint = Ask ejecutado - Bid ejecutado"}
    imbalance = {"available": False, "state": "DATA", "direction": None,
                 "reason": missing + "; no se puede medir ratio diagonal 3:1"}
    options_proxy = {"available": False, "state": "DATA", "direction": None,
                     "counts_toward_triad": False, "reason": why or "sin comparación"}
    if comparison:
        impulse, price = comparison["delta_impulse"], comparison["price_change_pct"]
        direction = ("BEARISH" if impulse >= 0.05 and price <= 0.02 else
                     "BULLISH" if impulse <= -0.05 and price >= -0.02 else None)
        score = _num(current.get("activity_score"))
        imbalance_direction = (
            "BEARISH" if score is not None and score >= SCORE_THRESHOLD and price <= 0.02
            else "BULLISH" if score is not None and score <= -SCORE_THRESHOLD and price >= -0.02
            else None)
        options_proxy = {
            "available": True, "state": "CONFIRMED" if direction else "NONE",
            "direction": direction or imbalance_direction,
            "delta_activity_direction": direction,
            "activity_exhaustion_direction": imbalance_direction,
            "delta_impulse": round(impulse, 6),
            "price_change_pct": round(price, 4),
            "prior_source_ts": comparison["prior_source_ts"],
            "activity_score": score,
            "threshold": SCORE_THRESHOLD, "threshold_unvalidated": True,
            "counts_toward_triad": False,
            "reason": ("ARCH_OPTIONS_CONTEXT_PROXY; no es Delta/imbalance de footprint"
                       if direction or imbalance_direction else "sin divergencia de contexto"),
        }
    confirmed = [x for x in (absorption, delta_change, imbalance)
                 if x.get("state") == "CONFIRMED" and x.get("direction")]
    directions = {x["direction"] for x in confirmed}
    value_dir = value.get("direction") if value.get("state") == "CONFIRMED" else None
    agrees = sum(1 for x in confirmed if x.get("direction") == value_dir) if value_dir else 0
    pattern_available = sum(bool(x.get("available")) for x in
                            (absorption, delta_change, imbalance))
    if pattern_available < 2:
        label, direction = "DATA", None
    elif value_dir and agrees >= 2:
        label, direction = "REVERSAL", value_dir
    elif value_dir:
        label, direction = "WATCH", value_dir
    else:
        label, direction = "NONE", None
    return {
        "name": "Architect Reversal Triad", "version": 1,
        "label": label, "direction": direction, "confirmed": agrees if value_dir else 0,
        "available": pattern_available,
        "value_context": value,
        "components": {"absorption": absorption, "delta_change": delta_change,
                       "bid_ask_imbalance": imbalance},
        "architect_options_context": options_proxy,
        "validation": "UNPROVEN_FORWARD_AUDIT_ONLY",
        "guard": "reversal exige value + 2/3: absorption, delta change, bid/ask imbalance",
        "directions_seen": sorted(directions),
    }


def append_history(repo, sym, payload):
    """Archive one observation per symbol for a future full-indicator backtest."""
    day = dt.datetime.fromtimestamp(payload["asof"]).date().isoformat()
    path = os.path.join(repo, "data", "history", day,
                        "lse_architect_%s_5m.jsonl" % str(sym).lower())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return path
