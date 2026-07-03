#!/usr/bin/env python3
"""Auditable realtime integrity state for walls, magnets and gamma flip.

The tracker consumes measured price contacts and option-level refreshes.  It never
turns volume into dealer inventory: ``metric`` and ``source_label`` are preserved in
the payload so a London gamma×volume wall stays an activity wall.
"""
from __future__ import annotations

import math
import time


LEVEL_SPECS = {
    "call_wall": ("CW", "call_wall_gex"),
    "put_wall": ("PW", "put_wall_gex"),
    "magnet": ("MAG", "abs_wall_gex"),
    "flip": ("FLIP", "net_gex"),
    "activity_flip": ("A-FLIP", "activity_flip_strength"),
}


def _num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _profile_max(levels):
    values = []
    for key in ("profile", "call_profile", "put_profile"):
        for row in levels.get(key) or []:
            value = _num(row.get("gamma_volume", row.get("gex")))
            if value is not None:
                values.append(abs(value))
    return max(values, default=0.0)


class WallIntegrityTracker:
    """Track distinct tests, exhaustion, breaks and relative reinforcement.

    Three tests to exhaustion is a display convention, not a measured win-rate.
    A test needs an outside→near transition and a cooldown; a break needs three
    consecutive prices beyond the wall tolerance.  A relative activity increase of
    at least 10% restores one hit-sized brick cluster.
    """

    version = 1

    def __init__(self, symbol, *, cooldown_s=20.0, break_votes=3,
                 proximity_bps=5.0, reinforcement_ratio=0.10):
        self.symbol = str(symbol).upper()
        self.cooldown_s = float(cooldown_s)
        self.break_votes_needed = int(break_votes)
        self.proximity_bps = float(proximity_bps)
        self.reinforcement_ratio = float(reinforcement_ratio)
        self.rows = {}
        self.last_price = None
        self.last_price_ts = None
        self._level_signature = None

    @staticmethod
    def _expected_side(key, price, level):
        if key == "call_wall":
            return price <= level
        if key == "put_wall":
            return price >= level
        return True

    @staticmethod
    def _is_beyond(key, price, level, tol):
        if key == "call_wall":
            return price > level + tol
        if key == "put_wall":
            return price < level - tol
        return abs(price - level) > tol

    def _new_row(self, key, level, mass, intensity, levels, now):
        capacity = max(6, min(12, 6 + int(round(6 * intensity))))
        chunk = max(1, int(math.ceil(capacity / 3.0)))
        metric = levels.get("profile_metric") or (
            "dealer_gex" if levels.get("oi_available", True) else "gamma_volume")
        source_label = ("LSE Γ×volume activity" if metric == "gamma_volume"
                        else "OI dealer-GEX structure")
        if key == "flip":
            metric = "dealer_gex"
            source_label = ("Polygon OI × IV · London spot" if
                            levels.get("oi_source") == "polygon_options_snapshot"
                            else "OI dealer-GEX structure")
        return {
            "key": key, "label": LEVEL_SPECS[key][0], "level": level,
            "metric": metric, "source_label": source_label,
            "state": "FRESH", "hits": 0, "capacity": capacity,
            "bricks_remaining": capacity, "brick_chunk": chunk,
            "mass": mass, "intensity": round(intensity, 4),
            "near": False, "armed": False, "break_votes": 0,
            "last_hit_ts": None, "last_event_ts": int(now),
            "last_event": "NEW", "reinforcements": 0,
            "convention": "three_distinct_tests_to_exhaustion",
        }

    def update_levels(self, levels, *, now=None):
        """Install a level refresh and return True when visible state changed."""
        if not isinstance(levels, dict):
            return False
        now = float(now if now is not None else time.time())
        max_mass = _profile_max(levels)
        signature = tuple(
            (key, _num(levels.get(key)), _num(levels.get(mass_key)))
            for key, (_, mass_key) in LEVEL_SPECS.items()
        ) + ((levels.get("chain_ts"), levels.get("ws_events")),)
        if signature == self._level_signature:
            return False
        self._level_signature = signature
        changed = False
        next_rows = {}
        for key, (_, mass_key) in LEVEL_SPECS.items():
            level = _num(levels.get(key))
            mass = _num(levels.get(mass_key))
            if key == "magnet" and mass is None:
                mass = _num(levels.get("magnet_gamma_volume"))
            if level is None:
                if key == "flip":
                    next_rows[key] = {
                        "key": key, "label": "FLIP", "level": None,
                        "state": "DATA", "hits": 0, "capacity": 0,
                        "bricks_remaining": 0, "near": False,
                        "metric": "dealer_gex_required",
                        "source_label": "OI required",
                        "last_event": "DATA", "last_event_ts": int(now),
                        "why": levels.get("flip_why") or "gamma flip requires fresh OI",
                    }
                continue
            intensity = min(1.0, abs(mass or 0.0) / max_mass) if max_mass else 0.5
            if key == "flip":
                intensity = 1.0  # a zero crossing has no meaningful local mass to rank
            old = self.rows.get(key)
            old_level = _num(old.get("level")) if old is not None else None
            if (old is None or old_level is None or
                    abs(old_level - level) > max(0.01, level * 1e-6)):
                next_rows[key] = self._new_row(key, level, mass, intensity, levels, now)
                changed = True
                continue
            row = dict(old)
            old_mass = abs(_num(old.get("mass")) or 0.0)
            new_mass = abs(mass or 0.0)
            reinforced = old_mass > 0 and new_mass >= old_mass * (1.0 + self.reinforcement_ratio)
            refreshed_metric = ("dealer_gex" if key == "flip" else
                                (levels.get("profile_metric") or row.get("metric")))
            row.update(mass=mass, intensity=round(intensity, 4), metric=refreshed_metric)
            if reinforced and row.get("state") not in ("BROKEN", "DATA"):
                before = int(row.get("bricks_remaining") or 0)
                row["bricks_remaining"] = min(
                    int(row["capacity"]), before + int(row["brick_chunk"]))
                if row["bricks_remaining"] > before:
                    row["reinforcements"] = int(row.get("reinforcements") or 0) + 1
                    row["last_event"] = "REINFORCED"
                    row["last_event_ts"] = int(now)
                    row["state"] = "REINFORCED"
                    changed = True
            next_rows[key] = row
        if set(next_rows) != set(self.rows):
            changed = True
        self.rows = next_rows
        return changed

    def on_price(self, price, *, now=None):
        """Consume a realtime price and return True only on a visible transition."""
        price = _num(price)
        if price is None or price <= 0:
            return False
        now = float(now if now is not None else time.time())
        if self.last_price == price and self.last_price_ts == now:
            return False
        previous = self.last_price
        changed = False
        for key, old in list(self.rows.items()):
            if old.get("level") is None or old.get("state") == "DATA":
                continue
            row = dict(old)
            level = float(row["level"])
            tol = max(0.01, level * self.proximity_bps / 10000.0)
            distance = abs(price - level)
            was_near = bool(row.get("near"))
            near = distance <= tol
            if distance >= 2.0 * tol and self._expected_side(key, price, level):
                row["armed"] = True

            last_hit = float(row.get("last_hit_ts") or -1e30)
            distinct_hit = (near and not was_near and row.get("armed") and
                            now - last_hit >= self.cooldown_s)
            if distinct_hit and row.get("state") != "BROKEN":
                row["hits"] = int(row.get("hits") or 0) + 1
                row["bricks_remaining"] = max(
                    0, int(row.get("bricks_remaining") or 0) - int(row["brick_chunk"]))
                row["last_hit_ts"] = now
                row["last_event_ts"] = int(now)
                row["last_event"] = "HIT"
                row["armed"] = False
                row["state"] = ("EXHAUSTED" if row["bricks_remaining"] <= 0
                                else "WEAKENING" if row["hits"] >= 2 else "TESTED")
                changed = True

            beyond = self._is_beyond(key, price, level, tol)
            crossed_from_expected = (previous is not None and
                                     self._expected_side(key, previous, level) and beyond)
            if key in ("magnet", "flip", "activity_flip"):
                crossed_from_expected = (previous is not None and
                                         (previous - level) * (price - level) < 0 and
                                         abs(price - level) > tol)
            row["break_votes"] = (int(row.get("break_votes") or 0) + 1
                                  if beyond and (crossed_from_expected or row.get("break_votes"))
                                  else 0)
            if (row["break_votes"] >= self.break_votes_needed and
                    row.get("state") != "BROKEN"):
                row["state"] = "BROKEN"
                row["bricks_remaining"] = 0
                row["last_event"] = "BROKEN"
                row["last_event_ts"] = int(now)
                changed = True
            row["near"] = near
            self.rows[key] = row
        self.last_price = price
        self.last_price_ts = now
        return changed

    def payload(self, *, now=None):
        now = int(now if now is not None else time.time())
        return {
            "name": "Realtime Level Integrity", "version": self.version,
            "symbol": self.symbol, "asof": now,
            "price": self.last_price,
            "levels": {key: {k: v for k, v in row.items()
                              if k not in ("armed", "break_votes")}
                       for key, row in self.rows.items()},
            "truth": ("hits are measured price contacts; reinforcement is relative option "
                      "activity; no dealer inventory is inferred"),
            "thresholds": {
                "proximity_bps": self.proximity_bps,
                "hit_cooldown_s": self.cooldown_s,
                "break_consecutive_ticks": self.break_votes_needed,
                "reinforcement_ratio": self.reinforcement_ratio,
                "thresholds_are_display_conventions": True,
            },
            "validation": "DESCRIPTIVE_FORWARD_AUDIT_ONLY",
        }
