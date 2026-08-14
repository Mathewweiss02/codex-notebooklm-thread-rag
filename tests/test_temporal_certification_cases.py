from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_index as temporal_index  # noqa: E402
import thread_temporal_context as temporal_context  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "thread_temporal_cli.py"


def make_event(thread_id: str, timestamp: str, text: str) -> dict[str, object]:
    event_id = temporal_index.sha256("\x00".join([thread_id, "user", timestamp, text]))
    return {
        "recordType": "event",
        "contractVersion": temporal_index.CONTRACT,
        "eventId": event_id,
        "threadId": thread_id,
        "role": "user",
        "timestampUtc": timestamp,
        "text": text,
        "textDigest": temporal_index.sha256(text),
        "sourceRef": {"sourceKind": "active", "sourceFileDigest": "certification-fixture", "lineNumber": 1},
    }


def write_handoff(path: Path, events: list[dict[str, object]]) -> None:
    header = {
        "recordType": "header",
        "contractVersion": temporal_index.CONTRACT,
        "policyVersion": temporal_index.POLICY,
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": len({str(event["threadId"]) for event in events}),
        "manifestDigest": hashlib.sha256(b"temporal-certification-fixture").hexdigest(),
    }
    lines = [json.dumps(header, separators=(",", ":")) + "\n"]
    digest = hashlib.sha256()
    for event in events:
        line = json.dumps(event, separators=(",", ":")) + "\n"
        lines.append(line)
        digest.update(line.encode("utf-8"))
    lines.append(json.dumps({
        "recordType": "trailer",
        "contractVersion": temporal_index.CONTRACT,
        "eventCount": len(events),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": digest.hexdigest(),
    }, separators=(",", ":")) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


class TemporalRangeCertificationTests(unittest.TestCase):
    def run_cli(self, *arguments: str, expected_code: int = 0) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, expected_code, completed.stderr or completed.stdout)
        return json.loads(completed.stdout)

    def when(self, expression: str, *, now: str = "2026-08-12T16:00:00.000Z", timezone: str = "America/New_York") -> dict[str, object]:
        return self.run_cli(
            "when",
            "--expression", expression,
            "--timezone", timezone,
            "--now", now,
        )["result"]

    def test_time_001_today_is_local_midnight_to_capture(self) -> None:
        result = self.when("today")
        self.assertEqual(result["startUtc"], "2026-08-12T04:00:00.000Z")
        self.assertEqual(result["endUtc"], "2026-08-12T16:00:00.000Z")
        self.assertEqual(result["boundary"], "half-open [start,end)")

    def test_time_002_yesterday_is_a_calendar_day(self) -> None:
        result = self.when("yesterday")
        self.assertEqual((result["startUtc"], result["endUtc"]), ("2026-08-11T04:00:00.000Z", "2026-08-12T04:00:00.000Z"))

    def test_time_003_past_24_hours_is_rolling(self) -> None:
        result = self.when("past 24 hours")
        self.assertEqual((result["startUtc"], result["endUtc"], result["durationSeconds"]), ("2026-08-11T16:00:00.000Z", "2026-08-12T16:00:00.000Z", 86400))

    def test_time_004_past_7_days_is_explicitly_rolling(self) -> None:
        result = self.when("past 7 days")
        self.assertEqual((result["startUtc"], result["endUtc"], result["durationSeconds"]), ("2026-08-05T16:00:00.000Z", "2026-08-12T16:00:00.000Z", 604800))

    def test_time_005_last_week_uses_monday_calendar_boundary(self) -> None:
        result = self.when("last week")
        self.assertEqual((result["startUtc"], result["endUtc"]), ("2026-08-03T04:00:00.000Z", "2026-08-10T04:00:00.000Z"))

    def test_time_006_week_to_date_stops_at_capture(self) -> None:
        result = self.when("week to date")
        self.assertEqual((result["startUtc"], result["endUtc"]), ("2026-08-10T04:00:00.000Z", "2026-08-12T16:00:00.000Z"))

    def test_time_007_explicit_date_is_one_local_day(self) -> None:
        result = self.when("2026-08-12")
        self.assertEqual((result["startUtc"], result["endUtc"]), ("2026-08-12T04:00:00.000Z", "2026-08-13T04:00:00.000Z"))

    def test_time_008_explicit_timestamp_range_is_half_open(self) -> None:
        result = self.run_cli(
            "when",
            "--start", "2026-08-12T16:00:00.000Z",
            "--end", "2026-08-12T17:00:00.000Z",
            "--timezone", "America/New_York",
            "--now", "2026-08-13T00:00:00.000Z",
        )["result"]
        self.assertEqual((result["startUtc"], result["endUtc"], result["boundary"]), ("2026-08-12T16:00:00.000Z", "2026-08-12T17:00:00.000Z", "half-open [start,end)"))

    def test_time_009_adjacent_midnight_ranges_do_not_overlap(self) -> None:
        first = self.when("2026-08-12")
        second = self.when("2026-08-13")
        self.assertEqual(first["endUtc"], second["startUtc"])

    def test_time_010_end_of_day_millisecond_is_retained(self) -> None:
        result = self.run_cli(
            "when",
            "--start", "2026-08-12T23:59:59.999Z",
            "--end", "2026-08-13T00:00:00.000Z",
            "--timezone", "UTC",
            "--now", "2026-08-13T00:01:00.000Z",
        )["result"]
        self.assertEqual(result["durationSeconds"], 0.001)
        self.assertEqual(result["boundary"], "half-open [start,end)")

    def test_time_011_spring_gap_is_rejected(self) -> None:
        result = self.run_cli(
            "when",
            "--start", "2026-03-08 02:30",
            "--end", "2026-03-08 03:30",
            "--timezone", "America/New_York",
            "--now", "2026-03-09T16:00:00.000Z",
            expected_code=1,
        )
        self.assertEqual(result["code"], "NONEXISTENT_LOCAL_TIME")

    def test_time_012_fall_overlap_requires_offset(self) -> None:
        result = self.run_cli(
            "when",
            "--start", "2026-11-01 01:30",
            "--end", "2026-11-01 02:30",
            "--timezone", "America/New_York",
            "--now", "2026-11-02T17:00:00.000Z",
            expected_code=1,
        )
        self.assertEqual(result["code"], "AMBIGUOUS_LOCAL_TIME")

    def test_time_013_leap_day_is_a_valid_local_day(self) -> None:
        result = self.when("2024-02-29", now="2024-03-02T12:00:00.000Z")
        self.assertEqual((result["startUtc"], result["endUtc"], result["durationSeconds"]), ("2024-02-29T05:00:00.000Z", "2024-03-01T05:00:00.000Z", 86400))

    def test_time_014_month_year_boundary_advances_to_next_year(self) -> None:
        result = self.when("2025-12-31", now="2026-01-02T12:00:00.000Z")
        self.assertEqual((result["startUtc"], result["endUtc"]), ("2025-12-31T05:00:00.000Z", "2026-01-01T05:00:00.000Z"))

    def test_time_015_timezone_override_changes_grouping_not_instant_contract(self) -> None:
        utc = self.when("2026-08-12", timezone="UTC")
        new_york = self.when("2026-08-12", timezone="America/New_York")
        self.assertEqual(utc["durationSeconds"], new_york["durationSeconds"])
        self.assertNotEqual(utc["startUtc"], new_york["startUtc"])

    def test_time_016_invalid_natural_phrase_fails_closed(self) -> None:
        result = self.run_cli(
            "when",
            "--expression", "sometime later",
            "--timezone", "America/New_York",
            "--now", "2026-08-12T16:00:00.000Z",
            expected_code=1,
        )
        self.assertEqual(result["code"], "INVALID_TIME_RANGE")

    def test_time_017_missing_period_has_a_safe_find_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.ndjson"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, [make_event("thread-default", "2026-08-12T12:00:00.000Z", "default period")])
            temporal_index.build_index(handoff, database, rebuild=True)
            result = self.run_cli(
                "find",
                "--db", str(database),
                "--timezone", "America/New_York",
                "--now", "2026-08-12T16:00:00.000Z",
                "--query", "default",
            )["result"]
        self.assertEqual(result["resolvedRange"]["kind"], "today")
        self.assertEqual(result["coverage"]["matchedEventCount"], 1)

    def test_time_018_future_period_is_explicitly_empty_unless_time_advances(self) -> None:
        result = self.when("tomorrow")
        self.assertTrue(result["future"])
        self.assertEqual(result["expectedActivity"], "empty-unless-now-advances")


class TemporalContextCertificationTests(unittest.TestCase):
    def build_database(self, root: Path, events: list[dict[str, object]]) -> Path:
        handoff = root / "handoff.ndjson"
        database = root / "temporal.sqlite3"
        write_handoff(handoff, events)
        temporal_index.build_index(handoff, database, rebuild=True)
        return database

    def build_context(self, database: Path, *, start: str = "2026-08-12T04:00:00.000Z", end: str = "2026-08-13T04:00:00.000Z", mode: str = "standard") -> dict[str, object]:
        return temporal_context.build_context(
            database,
            start,
            end,
            "America/New_York",
            mode=mode,
            node_path="node",
        )

    def test_ctx_002_single_message_is_one_activity_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.build_context(
                self.build_database(Path(temporary), [make_event("thread-one", "2026-08-12T12:00:00.000Z", "one message")])
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["coverage"]["canonicalEventCount"], 1)
        self.assertEqual(result["coverage"]["includedEventCount"], 1)
        self.assertEqual(result["coverage"]["segmentCount"], 1)

    def test_ctx_004_many_threads_one_day_are_all_represented(self) -> None:
        events = [
            make_event("thread-a", "2026-08-12T12:00:00.000Z", "a"),
            make_event("thread-b", "2026-08-12T12:05:00.000Z", "b"),
            make_event("thread-c", "2026-08-12T12:10:00.000Z", "c"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            result = self.build_context(self.build_database(Path(temporary), events))
        self.assertEqual(result["coverage"]["canonicalEventCount"], 3)
        self.assertEqual(result["coverage"]["includedEventCount"], 3)
        self.assertEqual({message["threadId"] for message in result["messages"]}, {"thread-a", "thread-b", "thread-c"})

    def test_ctx_007_concurrent_thread_ties_are_stable(self) -> None:
        events = [
            make_event("thread-z", "2026-08-12T12:00:00.000Z", "z"),
            make_event("thread-a", "2026-08-12T12:00:00.000Z", "a"),
            make_event("thread-m", "2026-08-12T12:00:00.000Z", "m"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary), events)
            first = self.build_context(database)
            second = self.build_context(database)
        first_order = [(message["timestampUtc"], message["threadId"], message["eventId"]) for message in first["messages"]]
        second_order = [(message["timestampUtc"], message["threadId"], message["eventId"]) for message in second["messages"]]
        self.assertEqual(first_order, second_order)
        self.assertEqual([item[1] for item in first_order], ["thread-a", "thread-m", "thread-z"])

    def test_ctx_010_brief_standard_deep_are_monotonic(self) -> None:
        events = [
            make_event("thread-long", f"2026-08-12T{12 + (index // 60):02d}:{index % 60:02d}:00.000Z", f"message {index}")
            for index in range(60)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary), events)
            brief = self.build_context(database, mode="brief")
            standard = self.build_context(database, mode="standard")
            deep = self.build_context(database, mode="deep")
        brief_ids = {message["eventId"] for message in brief["messages"]}
        standard_ids = {message["eventId"] for message in standard["messages"]}
        deep_ids = {message["eventId"] for message in deep["messages"]}
        self.assertTrue(brief_ids <= standard_ids <= deep_ids)
        self.assertLessEqual(len(brief_ids), len(standard_ids))
        self.assertLessEqual(len(standard_ids), len(deep_ids))

    def test_ctx_016_time_scope_is_applied_before_topic_filter(self) -> None:
        events = [
            make_event("thread-in", "2026-08-12T12:00:00.000Z", "temporal topic inside"),
            make_event("thread-in", "2026-08-12T12:05:00.000Z", "different inside"),
            make_event("thread-out", "2026-08-13T12:00:00.000Z", "temporal topic outside"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = self.build_database(root, events)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "find",
                    "--db", str(database),
                    "--expression", "2026-08-12",
                    "--timezone", "America/New_York",
                    "--now", "2026-08-14T12:00:00.000Z",
                    "--query", "temporal topic",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        result = json.loads(completed.stdout)["result"]
        self.assertEqual(result["coverage"]["canonicalEventCount"], 2)
        self.assertEqual(result["coverage"]["matchedEventCount"], 1)
        self.assertEqual(result["matches"][0]["threadId"], "thread-in")

    def test_ux_004_empty_period_is_honest_and_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(
                Path(temporary),
                [make_event("thread-outside", "2026-08-11T12:00:00.000Z", "outside period")],
            )
            result = self.build_context(database)
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["coverage"]["canonicalEventCount"], 0)
        self.assertEqual(result["coverage"]["includedEventCount"], 0)
        self.assertEqual(result["resolvedRange"]["boundary"], "half-open [start,end)")
        self.assertEqual(result["verification"]["status"], "local-authoritative")

    def test_ux_006_diagnostics_expose_mode_range_coverage_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(
                Path(temporary),
                [make_event("thread-diagnostics", "2026-08-12T12:00:00.000Z", "diagnostic event")],
            )
            result = self.build_context(database, mode="deep")
        self.assertEqual(result["mode"], "deep")
        self.assertIn("resolvedRange", result)
        self.assertIn("coverage", result)
        self.assertIn("verification", result)
        self.assertIn("latency", result)
        self.assertTrue(result["verification"]["provenanceComplete"])


if __name__ == "__main__":
    unittest.main()
