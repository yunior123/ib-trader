import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gameplan", ROOT / "gameplan.py")
gameplan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gameplan)


class GameplanContractTests(unittest.TestCase):
    def setUp(self):
        self.now = gameplan.parse_now("2026-08-27T16:30:00Z")
        self.tz = ZoneInfo("America/New_York")
        self.levels = gameplan.load_json(ROOT / "fixtures" / "levels.json", [])
        self.flow = gameplan.load_json(ROOT / "fixtures" / "flow.json", [])
        self.compass = gameplan.load_compass(ROOT / "fixtures" / "compass")
        self.consensus = gameplan.load_last_jsonl(ROOT / "fixtures" / "consensus.jsonl")
        self.breadth = gameplan.load_json(ROOT / "fixtures" / "breadth.json", {})

    def snapshot(self):
        return gameplan.build_snapshot(
            self.levels,
            self.flow,
            self.compass,
            self.consensus,
            self.breadth,
            self.now,
            self.tz,
            ZoneInfo("UTC"),
            30,
            5,
            10,
            "offline",
        )

    def test_fresh_stale_and_crossed_walls_are_explicit(self):
        snapshot = self.snapshot()
        rows = {row["symbol"]: row for row in snapshot["levels"]}
        self.assertEqual(rows["QQQ"]["freshness"]["status"], "fresh")
        self.assertEqual(rows["SPY"]["freshness"]["status"], "stale")
        self.assertIn("crossed_walls", rows["TEST"]["quality_issues"])
        self.assertIn("put_wall_above_spot", rows["TEST"]["quality_issues"])
        self.assertIn("call_wall_below_spot", rows["TEST"]["quality_issues"])
        self.assertIsNone(rows["TEST"]["flip"])
        self.assertEqual(snapshot["health"]["fresh_level_rows"], 2)

    def test_only_declared_measured_probability_is_carried(self):
        rows = {row["symbol"]: row for row in self.snapshot()["levels"]}
        self.assertEqual(rows["QQQ"]["measured_probability"], 0.61)
        self.assertIsNone(rows["SPY"]["measured_probability"])
        self.assertIsNone(rows["SPY"]["direction"], "stale compass direction must not leak")

    def test_flow_does_not_infer_direction_and_marks_stale(self):
        rows = {row["underlying"]: row for row in self.snapshot()["flow"]}
        self.assertEqual(rows["QQQ"]["freshness"]["status"], "fresh")
        self.assertEqual(rows["SPY"]["freshness"]["status"], "stale")
        self.assertEqual(rows["QQQ"]["interpretation"], "activity_only_side_not_observed")
        self.assertNotIn("direction", rows["QQQ"])

    def test_markdown_contains_boundaries_and_quality(self):
        markdown = gameplan.render_markdown(self.snapshot(), "2026-08-27", False)
        self.assertIn("not financial advice", markdown.lower())
        self.assertIn("aggressor side is not observed", markdown)
        self.assertIn("crossed_walls", markdown)
        self.assertIn("stale", markdown)

    def test_invalid_future_timestamp_is_not_fresh(self):
        result = gameplan.freshness("2026-08-27T13:00:00", self.now, 30, self.tz)
        self.assertEqual(result["status"], "invalid_future")

    def test_naive_level_and_flow_timestamps_use_distinct_contracts(self):
        level = gameplan.freshness(
            "2026-08-27 12:20:00", self.now, 30, ZoneInfo("America/New_York")
        )
        flow = gameplan.freshness(
            "2026-08-27 16:20:00", self.now, 30, ZoneInfo("UTC")
        )
        self.assertEqual(level["source_time"], "2026-08-27T16:20:00Z")
        self.assertEqual(flow["source_time"], "2026-08-27T16:20:00Z")
        self.assertEqual(level["age_minutes"], 10.0)
        self.assertEqual(flow["age_minutes"], 10.0)

    def test_invalid_future_flow_is_counted_separately(self):
        payload = [{"ts": "2026-08-27 17:00:00", "underlying": "QQQ", "premium": 1}]
        rows = gameplan.normalize_flow(payload, self.now, ZoneInfo("UTC"), 5)
        self.assertEqual(rows[0]["freshness"]["status"], "invalid_future")
        snapshot = gameplan.build_snapshot(
            self.levels,
            payload,
            self.compass,
            self.consensus,
            self.breadth,
            self.now,
            self.tz,
            ZoneInfo("UTC"),
            30,
            5,
            10,
            "offline",
        )
        self.assertEqual(snapshot["health"]["fresh_flow_rows"], 0)
        self.assertEqual(snapshot["health"]["invalid_future_flow_rows"], 1)


class GameplanCliTests(unittest.TestCase):
    def command(self, output, now="2026-08-27T16:30:00Z", strict=False):
        command = [
            sys.executable,
            str(ROOT / "gameplan.py"),
            "--offline",
            "--levels-file", str(ROOT / "fixtures" / "levels.json"),
            "--flow-file", str(ROOT / "fixtures" / "flow.json"),
            "--compass-dir", str(ROOT / "fixtures" / "compass"),
            "--consensus-file", str(ROOT / "fixtures" / "consensus.jsonl"),
            "--breadth-file", str(ROOT / "fixtures" / "breadth.json"),
            "--now", now,
            "--date", "2026-08-27",
            "--output", str(output),
        ]
        if strict:
            command.append("--strict")
        return command

    def test_offline_cli_writes_json_markdown_and_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            result = subprocess.run(self.command(output), capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "gameplan-2026-08-27.json").is_file())
            self.assertTrue((output / "gameplan-2026-08-27.md").is_file())
            self.assertEqual(
                json.loads((output / "latest.json").read_text())["schema_version"],
                "1.0",
            )

    def test_strict_cli_rejects_all_stale_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                self.command(pathlib.Path(directory), now="2026-08-29T16:30:00Z", strict=True),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("no fresh structural-level rows", result.stderr)


if __name__ == "__main__":
    unittest.main()
