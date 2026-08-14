from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

import thread_temporal_context as context  # noqa: E402
import thread_temporal_index as index  # noqa: E402


def make_event(thread_id: str, timestamp: str, text: str, line: int) -> dict[str, object]:
    event_id = index.sha256("\x00".join([thread_id, "user", timestamp, text]))
    return {
        "recordType": "event",
        "contractVersion": "temporal-event-v1",
        "eventId": event_id,
        "threadId": thread_id,
        "role": "user",
        "timestampUtc": timestamp,
        "text": text,
        "textDigest": index.sha256(text),
        "sourceRef": {"sourceKind": "active", "sourceFileDigest": "fixture-context", "lineNumber": line},
    }


def write_handoff(path: Path, events: list[dict[str, object]]) -> None:
    header = {
        "recordType": "header",
        "contractVersion": "temporal-event-v1",
        "policyVersion": "visible-messages-secrets-redacted-v4",
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": len({event["threadId"] for event in events}),
        "manifestDigest": "fixture-context-manifest",
    }
    lines = [json.dumps(header, separators=(",", ":")) + "\n"]
    event_digest = hashlib.sha256()
    for event in events:
        line = json.dumps(event, separators=(",", ":")) + "\n"
        lines.append(line)
        event_digest.update(line.encode("utf-8"))
    trailer = {
        "recordType": "trailer",
        "contractVersion": "temporal-event-v1",
        "eventCount": len(events),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": event_digest.hexdigest(),
    }
    lines.append(json.dumps(trailer, separators=(",", ":")) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


class TemporalContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.node = shutil.which("node") or "node"
        self.events = [
            make_event("thread-a", "2026-02-02T04:50:00.000Z", "before local midnight", 1),
            make_event("thread-a", "2026-02-02T05:05:00.000Z", "after local midnight", 2),
            make_event("thread-a", "2026-02-02T05:20:00.000Z", "same activity", 3),
            make_event("thread-a", "2026-02-02T06:30:00.000Z", "new activity", 4),
            make_event("thread-b", "2026-02-03T14:00:00.000Z", "another thread", 5),
            make_event("thread-b", "2026-02-03T14:45:00.000Z", "same thread activity", 6),
            make_event("thread-b", "2026-02-03T16:00:00.000Z", "later activity", 7),
        ]

    def build_database(self, root: Path) -> Path:
        handoff = root / "handoff.jsonl"
        database = root / "temporal.sqlite3"
        write_handoff(handoff, self.events)
        index.build_index(handoff, database, rebuild=True)
        return database

    def test_full_pack_is_exhaustive_and_keeps_cross_midnight_segment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary))
            result = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                mode="standard",
                node_path=self.node,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["coverage"]["canonicalEventCount"], 7)
        self.assertEqual(result["coverage"]["includedEventCount"], 7)
        self.assertEqual(result["coverage"]["omittedEventCount"], 0)
        self.assertEqual(result["coverage"]["segmentCount"], 4)
        self.assertEqual(result["coverage"]["localDayCount"], 3)
        self.assertEqual(result["verification"]["outOfWindowEventCount"], 0)
        cross_midnight = next(segment for segment in result["segments"] if segment["threadId"] == "thread-a")
        self.assertEqual(cross_midnight["localDates"], ["2026-02-01", "2026-02-02"])
        self.assertFalse(cross_midnight["truncatedBefore"])

    def test_subset_uses_full_thread_history_and_budget_omissions_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary))
            full = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                node_path=self.node,
            )
            subset = context.build_context(
                database,
                "2026-02-02T05:00:00.000Z",
                "2026-02-02T06:00:00.000Z",
                "America/New_York",
                max_messages=2,
                max_chars=10_000,
                node_path=self.node,
            )
            budgeted = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                max_messages=2,
                max_chars=10_000,
                node_path=self.node,
            )

        full_first = next(segment for segment in full["segments"] if segment["threadId"] == "thread-a")
        subset_first = next(segment for segment in subset["segments"] if segment["threadId"] == "thread-a")
        self.assertEqual(subset["status"], "ok")
        self.assertEqual(subset["coverage"]["canonicalEventCount"], 2)
        self.assertEqual(subset["coverage"]["includedEventCount"], 2)
        self.assertEqual(subset["coverage"]["omittedEventCount"], 0)
        self.assertEqual(subset_first["segmentId"], full_first["segmentId"])
        self.assertTrue(subset_first["truncatedBefore"])

        self.assertEqual(budgeted["status"], "degraded")
        self.assertEqual(budgeted["coverage"]["includedEventCount"], 2)
        self.assertEqual(budgeted["coverage"]["omittedEventCount"], 5)
        self.assertEqual(sum(segment["omittedEventCount"] for segment in budgeted["segments"]), 5)
        self.assertEqual(budgeted["coverage"]["omissionReasons"]["message-budget"], 5)

    def test_drill_down_is_a_scoped_evidence_pack_and_equal_range_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary))
            full = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                node_path=self.node,
            )
            target = full["segments"][0]["segmentId"]
            drill = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                drill_down=target,
                node_path=self.node,
            )
            empty = context.build_context(
                database,
                "2026-02-04T00:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                node_path=self.node,
            )

        self.assertEqual(drill["selection"]["scope"], "activity-segment")
        self.assertEqual(drill["selection"]["segmentId"], target)
        self.assertEqual(drill["status"], "ok")
        self.assertEqual(drill["coverage"]["periodCanonicalEventCount"], 7)
        self.assertLess(drill["coverage"]["canonicalEventCount"], 7)
        self.assertEqual(drill["coverage"]["omittedEventCount"], 0)
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(empty["coverage"]["canonicalEventCount"], 0)

    def test_stale_resolver_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary))
            with self.assertRaises(context.TemporalContextError) as caught:
                context.build_context(
                    database,
                    "2026-02-04T00:00:00.000Z",
                    "2026-02-04T00:00:00.000Z",
                    "America/New_York",
                    range_metadata={"startUtc": "2026-02-03T00:00:00.000Z", "endUtc": "2026-02-04T00:00:00.000Z", "timezone": "America/New_York"},
                    node_path=self.node,
                )
        self.assertEqual(caught.exception.code, "INVALID_RANGE_METADATA")


if __name__ == "__main__":
    unittest.main()
