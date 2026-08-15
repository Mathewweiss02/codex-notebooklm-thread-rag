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


def make_event(thread_id: str, timestamp: str, text: str, line: int, role: str = "user") -> dict[str, object]:
    event_id = index.sha256("\x00".join([thread_id, role, timestamp, text]))
    return {
        "recordType": "event",
        "contractVersion": "temporal-event-v1",
        "eventId": event_id,
        "threadId": thread_id,
        "role": role,
        "timestampUtc": timestamp,
        "text": text,
        "textDigest": index.sha256(text),
        "sourceRef": {"sourceKind": "active", "sourceFileDigest": "fixture-context", "lineNumber": line},
    }


def write_handoff(path: Path, events: list[dict[str, object]], thread_metadata: dict[str, dict[str, object]] | None = None) -> None:
    header = {
        "recordType": "header",
        "contractVersion": "temporal-event-v1",
        "policyVersion": "visible-messages-secrets-redacted-v4",
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": len({event["threadId"] for event in events}),
        "manifestDigest": "fixture-context-manifest",
    }
    if thread_metadata is not None:
        header["threadMetadata"] = thread_metadata
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

    def test_signals_are_conservative_and_point_only_to_included_evidence(self) -> None:
        events = [
            make_event("thread-signals", "2026-02-02T12:00:00.000Z", "I need to build scripts/thread_temporal_cli.py for this project.", 1),
            make_event("thread-signals", "2026-02-02T12:05:00.000Z", "Implemented and verified the migration; tests passed.", 2, "assistant"),
            make_event("thread-signals", "2026-02-02T12:10:00.000Z", "Still need to resolve the scheduler overlap; TODO for rollback.", 3),
            make_event("thread-signals", "2026-02-02T12:15:00.000Z", "We decided to keep local authority as the default policy.", 4, "assistant"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, events)
            index.build_index(handoff, database, rebuild=True)
            result = context.build_context(
                database,
                "2026-02-02T11:00:00.000Z",
                "2026-02-02T13:00:00.000Z",
                "America/New_York",
                node_path=self.node,
            )

        included_ids = {message["eventId"] for message in result["messages"]}
        self.assertGreaterEqual(result["signals"]["counts"]["intent"], 1)
        self.assertGreaterEqual(result["signals"]["counts"]["completion"], 1)
        self.assertGreaterEqual(result["signals"]["counts"]["unresolved"], 1)
        self.assertGreaterEqual(result["signals"]["counts"]["artifact"], 1)
        self.assertGreaterEqual(result["signals"]["counts"]["decision"], 1)
        for values in result["signals"]["signals"].values():
            for signal in values:
                self.assertIn(signal["eventId"], included_ids)
                self.assertEqual(signal["confidence"], "heuristic")
                self.assertTrue(signal["sourceRef"]["sourceFileDigest"])
        self.assertEqual(result["verification"]["signalsProvenanceComplete"], True)

    def test_project_filter_uses_path_free_workspace_metadata(self) -> None:
        metadata = {
            "thread-a": {"workspaceLabel": "Hermes", "workspaceHash": "hermes123", "archived": False, "source": "vscode"},
            "thread-b": {"workspaceLabel": "Other", "workspaceHash": "other456", "archived": False, "source": "vscode"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, self.events, metadata)
            index.build_index(handoff, database, rebuild=True)
            result = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-02T04:00:00.000Z",
                "America/New_York",
                project="Hermes",
                node_path=self.node,
            )
            # Equal boundaries are an empty period, but the filter still reports
            # the matched thread scope for diagnostics.
            filtered = context.build_context(
                database,
                "2026-02-02T04:00:00.000Z",
                "2026-02-04T00:00:00.000Z",
                "America/New_York",
                project="hermes123",
                node_path=self.node,
            )

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["projectFilter"]["matchedThreadIds"], ["thread-a"])
        self.assertEqual(filtered["projectFilter"]["matchedThreadIds"], ["thread-a"])
        self.assertEqual(set(filtered["selection"]["threadIds"]), {"thread-a"})
        self.assertTrue(all(message["threadId"] == "thread-a" for message in filtered["messages"]))

    def test_project_filter_fails_closed_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary))
            with self.assertRaises(index.TemporalIndexError) as caught:
                context.build_context(
                    database,
                    "2026-02-02T04:00:00.000Z",
                    "2026-02-04T00:00:00.000Z",
                    "America/New_York",
                    project="Hermes",
                    node_path=self.node,
                )
        self.assertEqual(caught.exception.code, "PROJECT_METADATA_UNAVAILABLE")

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
