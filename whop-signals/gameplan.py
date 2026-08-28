#!/usr/bin/env python3
"""Build an educational market-structure snapshot for the Whop product preview.

The generator is deliberately signal-only. It never creates orders, trade entries,
stops, targets, win claims, or inferred dealer positioning. Live HTTP is optional;
fixtures/local files make the complete pipeline testable without network access.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys
import urllib.error
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo

BASE = pathlib.Path(__file__).resolve().parent
REPO = BASE.parent
DATA = REPO / "data"
API = "https://ibtrader.quant-academy.workers.dev"
COCKPIT = ["QQQ", "SPY", "SMH", "NVDA", "TSLA", "SPCX"]
DISCLAIMER = (
    "Educational market-structure context only. This is not financial advice, "
    "a recommendation, an execution signal, or a performance claim."
)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_json(path: pathlib.Path, default: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def load_last_jsonl(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            lines = [line.strip() for line in handle if line.strip()]
        return json.loads(lines[-1]) if lines else None
    except (OSError, json.JSONDecodeError):
        return None


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "la-manada-preview/1.0", "Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"source unavailable: {url}: {exc}") from exc


def parse_time(value: Any, source_tz: ZoneInfo) -> dt.datetime | None:
    if is_number(value):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_tz)
    return parsed.astimezone(dt.timezone.utc)


def freshness(
    value: Any,
    now: dt.datetime,
    max_age_minutes: int,
    source_tz: ZoneInfo,
) -> dict[str, Any]:
    parsed = parse_time(value, source_tz)
    if parsed is None:
        return {"status": "unknown", "age_minutes": None, "source_time": None}
    age = (now - parsed).total_seconds() / 60
    if age < -5:
        status = "invalid_future"
    elif age <= max_age_minutes:
        status = "fresh"
    else:
        status = "stale"
    return {
        "status": status,
        "age_minutes": round(age, 1),
        "source_time": parsed.isoformat().replace("+00:00", "Z"),
    }


def load_compass(directory: pathlib.Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return result
    for path in directory.glob("compass_*.json"):
        payload = load_json(path, None)
        if isinstance(payload, dict):
            symbol = str(payload.get("sym") or path.stem.removeprefix("compass_")).upper()
            result[symbol] = payload
    return result


def level_quality(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    spot, put_wall, call_wall = row.get("spot"), row.get("put_wall"), row.get("call_wall")
    if not is_number(spot):
        issues.append("missing_spot")
    if not is_number(put_wall):
        issues.append("missing_put_wall")
    if not is_number(call_wall):
        issues.append("missing_call_wall")
    if is_number(put_wall) and is_number(call_wall) and put_wall > call_wall:
        issues.append("crossed_walls")
    if is_number(put_wall) and is_number(spot) and put_wall > spot:
        issues.append("put_wall_above_spot")
    if is_number(call_wall) and is_number(spot) and call_wall < spot:
        issues.append("call_wall_below_spot")
    return issues


def normalize_levels(
    payload: Any,
    compass: dict[str, dict[str, Any]],
    now: dt.datetime,
    source_tz: ZoneInfo,
    max_age_minutes: int,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict) or not raw.get("sym"):
            continue
        symbol = str(raw["sym"]).upper()
        age = freshness(raw.get("fuente_ts", raw.get("ts")), now, max_age_minutes, source_tz)
        compass_raw = compass.get(symbol, {})
        compass_age = freshness(compass_raw.get("ts"), now, max_age_minutes, source_tz)
        direction = compass_raw.get("dir") if compass_age["status"] == "fresh" else None
        probability = None
        probability_source = str(compass_raw.get("prob_source") or "")
        if (
            is_number(compass_raw.get("prob"))
            and probability_source.lower().startswith(("measured", "calibrated", "medido"))
        ):
            probability = compass_raw["prob"]
        result.append(
            {
                "symbol": symbol,
                "spot": raw.get("spot") if is_number(raw.get("spot")) else None,
                "call_wall": raw.get("call_wall") if is_number(raw.get("call_wall")) else None,
                "put_wall": raw.get("put_wall") if is_number(raw.get("put_wall")) else None,
                "flip": raw.get("flip") if is_number(raw.get("flip")) else None,
                "max_pain": raw.get("max_pain") if is_number(raw.get("max_pain")) else None,
                "net_gex_house_scale": raw.get("gex_total")
                if is_number(raw.get("gex_total"))
                else None,
                "pressure": raw.get("pressure") if is_number(raw.get("pressure")) else None,
                "expected_move": raw.get("em") if is_number(raw.get("em")) else None,
                "direction": direction,
                "measured_probability": probability,
                "freshness": age,
                "compass_freshness": compass_age,
                "quality_issues": level_quality(raw),
            }
        )
    order = {symbol: index for index, symbol in enumerate(COCKPIT)}
    result.sort(key=lambda row: (order.get(row["symbol"], len(order)), row["symbol"]))
    return result


def normalize_flow(
    payload: Any,
    now: dt.datetime,
    flow_source_tz: ZoneInfo,
    max_age_minutes: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict) or not raw.get("underlying"):
            continue
        result.append(
            {
                "underlying": str(raw["underlying"]).upper(),
                "contract": raw.get("ticker"),
                "option_type": raw.get("tipo") if raw.get("tipo") in {"call", "put"} else None,
                "strike": raw.get("strike") if is_number(raw.get("strike")) else None,
                "expiry": raw.get("expiry"),
                "dte": raw.get("dte") if is_number(raw.get("dte")) else None,
                "premium": raw.get("premium") if is_number(raw.get("premium")) else None,
                "delta": raw.get("delta") if is_number(raw.get("delta")) else None,
                "gamma": raw.get("gamma") if is_number(raw.get("gamma")) else None,
                "freshness": freshness(raw.get("ts"), now, max_age_minutes, flow_source_tz),
                "interpretation": "activity_only_side_not_observed",
            }
        )
    freshness_order = {"fresh": 0, "stale": 1, "unknown": 2, "invalid_future": 3}
    result.sort(
        key=lambda row: (
            freshness_order.get(row["freshness"]["status"], 4),
            -(row["premium"] or 0),
        )
    )
    return result[:limit]


def normalize_context(
    consensus: dict[str, Any] | None,
    breadth: dict[str, Any] | None,
    now: dt.datetime,
    levels_source_tz: ZoneInfo,
    max_age_minutes: int,
) -> dict[str, Any]:
    consensus = consensus or {}
    qqq = (breadth or {}).get("QQQ", {}) if isinstance(breadth, dict) else {}
    return {
        "consensus_direction": consensus.get("dir"),
        "aligned": consensus.get("aligned") if is_number(consensus.get("aligned")) else None,
        "fleet_size": consensus.get("n_fleet") if is_number(consensus.get("n_fleet")) else None,
        "momentum_count": consensus.get("momentum")
        if is_number(consensus.get("momentum"))
        else None,
        "consensus_freshness": freshness(
            consensus.get("ts"), now, max_age_minutes, levels_source_tz
        ),
        "breadth_score": qqq.get("score") if is_number(qqq.get("score")) else None,
        "breadth_verdict": qqq.get("verdict"),
        "breadth_freshness": freshness(
            qqq.get("ts"), now, max_age_minutes, levels_source_tz
        ),
        "note": "Counts and descriptive scores are not probabilities or forecasts.",
    }


def money(value: Any) -> str:
    if not is_number(value):
        return "—"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    return f"${value:,.0f}"


def number(value: Any, digits: int = 2) -> str:
    return "—" if not is_number(value) else f"{value:,.{digits}f}"


def age_label(value: dict[str, Any]) -> str:
    age = value.get("age_minutes")
    return value.get("status", "unknown") if age is None else f"{value['status']} · {age:.1f}m"


def build_snapshot(
    levels_payload: Any,
    flow_payload: Any,
    compass_payload: dict[str, dict[str, Any]],
    consensus_payload: dict[str, Any] | None,
    breadth_payload: dict[str, Any] | None,
    now: dt.datetime,
    levels_source_tz: ZoneInfo,
    flow_source_tz: ZoneInfo,
    level_age: int,
    flow_age: int,
    context_age: int,
    mode: str,
) -> dict[str, Any]:
    levels = normalize_levels(
        levels_payload, compass_payload, now, levels_source_tz, level_age
    )
    flow = normalize_flow(flow_payload, now, flow_source_tz, flow_age)
    context = normalize_context(
        consensus_payload, breadth_payload, now, levels_source_tz, context_age
    )
    return {
        "schema_version": "1.0",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "disclaimer": DISCLAIMER,
        "freshness_thresholds_minutes": {
            "levels": level_age,
            "flow": flow_age,
            "context": context_age,
        },
        "source_notes": [
            "Levels are structural context; their timestamp is shown and they do not trigger trades.",
            "Options flow is activity only; call/put type does not reveal aggressor side or direction.",
            "Missing data remains null and stale data remains visible as stale.",
            "Put walls above spot and call walls below spot are flagged as side-semantic violations.",
        ],
        "context": context,
        "levels": levels,
        "flow": flow,
        "health": {
            "level_rows": len(levels),
            "fresh_level_rows": sum(row["freshness"]["status"] == "fresh" for row in levels),
            "stale_level_rows": sum(row["freshness"]["status"] == "stale" for row in levels),
            "unknown_level_rows": sum(row["freshness"]["status"] == "unknown" for row in levels),
            "invalid_future_level_rows": sum(
                row["freshness"]["status"] == "invalid_future" for row in levels
            ),
            "quality_issue_rows": sum(bool(row["quality_issues"]) for row in levels),
            "flow_rows": len(flow),
            "fresh_flow_rows": sum(row["freshness"]["status"] == "fresh" for row in flow),
            "stale_flow_rows": sum(row["freshness"]["status"] == "stale" for row in flow),
            "unknown_flow_rows": sum(row["freshness"]["status"] == "unknown" for row in flow),
            "invalid_future_flow_rows": sum(
                row["freshness"]["status"] == "invalid_future" for row in flow
            ),
        },
    }


def render_markdown(snapshot: dict[str, Any], report_date: str, close: bool) -> str:
    phase = "Close review" if close else "Daily structure map"
    context = snapshot["context"]
    lines = [
        f"# {phase} — {report_date}",
        "",
        f"> {snapshot['disclaimer']}",
        "",
        "## Data health",
        "",
        f"- Generated: `{snapshot['generated_at']}` ({snapshot['mode']} mode)",
        f"- Levels: {snapshot['health']['fresh_level_rows']} fresh / "
        f"{snapshot['health']['stale_level_rows']} stale / "
        f"{snapshot['health']['unknown_level_rows']} unknown / "
        f"{snapshot['health']['invalid_future_level_rows']} invalid-future / "
        f"{snapshot['health']['quality_issue_rows']} with quality flags",
        f"- Options-flow rows: {snapshot['health']['fresh_flow_rows']} fresh / "
        f"{snapshot['health']['stale_flow_rows']} stale / "
        f"{snapshot['health']['unknown_flow_rows']} unknown / "
        f"{snapshot['health']['invalid_future_flow_rows']} invalid-future",
        "",
        "## Market context",
        "",
        f"- Fleet direction: **{context['consensus_direction'] or 'unavailable'}** "
        f"({age_label(context['consensus_freshness'])})",
        f"- Aligned: {context['aligned'] if context['aligned'] is not None else '—'} / "
        f"{context['fleet_size'] if context['fleet_size'] is not None else '—'}; "
        f"momentum count: {context['momentum_count'] if context['momentum_count'] is not None else '—'}",
        f"- Breadth: {context['breadth_verdict'] or 'unavailable'} "
        f"({age_label(context['breadth_freshness'])})",
        "- Counts and descriptive scores are not probabilities or forecasts.",
        "",
        "## Structural levels",
        "",
        "| Symbol | Spot | Put wall | Call wall | Flip | Expected move | Freshness | Quality |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in snapshot["levels"]:
        quality = ", ".join(row["quality_issues"]) if row["quality_issues"] else "ok"
        lines.append(
            f"| {row['symbol']} | {number(row['spot'])} | {number(row['put_wall'])} | "
            f"{number(row['call_wall'])} | {number(row['flip'])} | "
            f"{number(row['expected_move'])} | {age_label(row['freshness'])} | {quality} |"
        )
    lines.extend(
        [
            "",
            "## Options activity",
            "",
            "> Contract activity is not labeled bullish or bearish because aggressor side is not observed.",
            "",
            "| Underlying | Contract | Type | Strike | DTE | Notional activity | Freshness |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in snapshot["flow"]:
        lines.append(
            f"| {row['underlying']} | {row['contract'] or '—'} | {row['option_type'] or '—'} | "
            f"{number(row['strike'])} | {number(row['dte'], 0)} | {money(row['premium'])} | "
            f"{age_label(row['freshness'])} |"
        )
    lines.extend(["", "---", "", snapshot["disclaimer"], ""])
    return "\n".join(lines)


def parse_now(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=BASE / "output")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--offline", action="store_true", help="require fixture/local inputs")
    parser.add_argument("--levels-file", type=pathlib.Path)
    parser.add_argument("--flow-file", type=pathlib.Path)
    parser.add_argument("--compass-dir", type=pathlib.Path, default=DATA)
    parser.add_argument("--consensus-file", type=pathlib.Path, default=DATA / "consensus_signals.jsonl")
    parser.add_argument("--breadth-file", type=pathlib.Path, default=DATA / "breadth.json")
    parser.add_argument("--now", help="ISO-8601 clock override for deterministic tests")
    parser.add_argument(
        "--levels-source-timezone",
        default="America/New_York",
        help="timezone for naive level timestamps (default: America/New_York)",
    )
    parser.add_argument(
        "--flow-source-timezone",
        default="UTC",
        help="timezone for naive /api/flujo timestamps (default: UTC)",
    )
    parser.add_argument("--max-level-age-min", type=int, default=30)
    parser.add_argument("--max-flow-age-min", type=int, default=5)
    parser.add_argument("--max-context-age-min", type=int, default=10)
    parser.add_argument("--strict", action="store_true", help="fail if there are no fresh level rows")
    args = parser.parse_args(argv)

    if args.offline and (not args.levels_file or not args.flow_file):
        parser.error("--offline requires --levels-file and --flow-file")

    try:
        levels_payload = (
            load_json(args.levels_file, [])
            if args.levels_file
            else fetch_json(f"{API}/api/niveles")
        )
        flow_payload = (
            load_json(args.flow_file, [])
            if args.flow_file
            else fetch_json(f"{API}/api/flujo?limite=40")
        )
        now = parse_now(args.now)
        levels_source_tz = ZoneInfo(args.levels_source_timezone)
        flow_source_tz = ZoneInfo(args.flow_source_timezone)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(
        levels_payload,
        flow_payload,
        load_compass(args.compass_dir),
        load_last_jsonl(args.consensus_file),
        load_json(args.breadth_file, None),
        now,
        levels_source_tz,
        flow_source_tz,
        args.max_level_age_min,
        args.max_flow_age_min,
        args.max_context_age_min,
        "offline" if args.offline else "live-fetch",
    )
    if args.strict and snapshot["health"]["fresh_level_rows"] == 0:
        print("ERROR: no fresh structural-level rows", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"gameplan-{args.date}"
    json_path = args.output / f"{stem}.json"
    markdown_path = args.output / f"{stem}.md"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(snapshot, args.date, args.close), encoding="utf-8")
    shutil.copyfile(json_path, args.output / "latest.json")
    print(
        f"OK {markdown_path} | levels={snapshot['health']['level_rows']} "
        f"fresh={snapshot['health']['fresh_level_rows']} flow={snapshot['health']['flow_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
