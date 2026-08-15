from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "thread_temporal_index.py"
SPEC = importlib.util.spec_from_file_location("thread_temporal_index", MODULE_PATH)
index = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(index)


def event(thread_id: str, timestamp: str, text: str, source_kind: str, source_digest: str, line: int) -> dict[str, object]:
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
        "sourceRef": {"sourceKind": source_kind, "sourceFileDigest": source_digest, "lineNumber": line},
    }


def write_handoff(path: Path, events: list[dict[str, object]], quarantines: list[dict[str, object]] | None = None, manifest_digest: str = "manifest-a") -> None:
    quarantines = quarantines or []
    header = {
        "recordType": "header",
        "contractVersion": "temporal-event-v1",
        "policyVersion": "visible-messages-secrets-redacted-v4",
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": 1,
        "manifestDigest": manifest_digest,
    }
    lines = [json.dumps(header, separators=(",", ":"), ensure_ascii=False) + "\n"]
    event_hash = hashlib.sha256()
    for record in events:
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
        lines.append(line)
        event_hash.update(line.encode("utf-8"))
    for record in quarantines:
        lines.append(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
    trailer = {
        "recordType": "trailer",
        "contractVersion": "temporal-event-v1",
        "eventCount": len(events),
        "quarantineCount": len(quarantines),
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": event_hash.hexdigest(),
    }
    lines.append(json.dumps(trailer, separators=(",", ":"), ensure_ascii=False) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


class TemporalIndexTests(unittest.TestCase):
    def test_build_deduplicates_lineage_and_queries_half_open_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            active = event("thread-a", "2026-08-12T04:00:00.000Z", "first", "active", "file-active", 1)
            archived = event("thread-a", "2026-08-12T04:00:00.000Z", "first", "archive", "file-archive", 8)
            second = event("thread-a", "2026-08-12T05:00:00.000Z", "second", "active", "file-active", 2)
            write_handoff(handoff, [active, archived, second])

            result = index.build_index(handoff, database, rebuild=True)
            self.assertTrue(result["rebuilt"])
            self.assertEqual(result["eventCount"], 2)
            self.assertEqual(result["sourceReferenceCount"], 3)

            rows = index.query_events(database, "2026-08-12T04:00:00.000Z", "2026-08-12T05:00:00.000Z")
            self.assertEqual([row["text"] for row in rows], ["first"])
            self.assertEqual(rows[0]["sourceRef"]["sourceKind"], "active")

            no_op = index.build_index(handoff, database)
            self.assertTrue(no_op["noOp"])
            self.assertFalse(no_op["changed"])

    def test_unchanged_handoff_is_an_exact_incremental_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            records = [
                event("thread-a", "2026-08-12T04:00:00.000Z", "stable", "active", "file-a", 1),
                event("thread-a", "2026-08-12T05:00:00.000Z", "state", "active", "file-a", 2),
            ]
            write_handoff(handoff, records)
            index.build_index(handoff, database, rebuild=True)
            before = index.verify_database(database)
            result = index.build_index(handoff, database)
            after = index.verify_database(database)

            self.assertTrue(result["noOp"])
            self.assertFalse(result["changed"])
            self.assertEqual(after["eventDigest"], before["eventDigest"])
            self.assertEqual(after["eventCount"], before["eventCount"])

    def test_active_to_archive_move_keeps_one_canonical_event_and_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            record = event("moving-thread", "2026-08-12T04:00:00.000Z", "stable identity", "active", "active-file", 1)
            write_handoff(handoff, [record], manifest_digest="active-manifest")
            index.build_index(handoff, database, rebuild=True)

            archived = event("moving-thread", "2026-08-12T04:00:00.000Z", "stable identity", "archive", "archive-file", 1)
            write_handoff(handoff, [archived], manifest_digest="archive-manifest")
            result = index.build_index(handoff, database)
            rows = index.query_events(database, "2026-08-12T00:00:00.000Z", "2026-08-13T00:00:00.000Z")

            self.assertTrue(result["changed"])
            self.assertEqual(result["eventCount"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["threadId"], "moving-thread")
            self.assertEqual(rows[0]["sourceRef"]["sourceKind"], "archive")

    def test_incremental_update_removes_stale_events_and_retains_last_good_on_bad_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            first = event("thread-a", "2026-08-12T04:00:00.000Z", "first", "active", "file-a", 1)
            second = event("thread-a", "2026-08-12T05:00:00.000Z", "second", "active", "file-a", 2)
            write_handoff(handoff, [first, second])
            index.build_index(handoff, database, rebuild=True)
            old_digest = index.verify_database(database)["eventDigest"]

            third = event("thread-a", "2026-08-12T06:00:00.000Z", "third", "active", "file-a", 3)
            write_handoff(handoff, [second, third], manifest_digest="manifest-b")
            updated = index.build_index(handoff, database)
            self.assertTrue(updated["changed"])
            self.assertEqual(updated["eventCount"], 2)
            self.assertEqual([row["text"] for row in index.query_events(database, "2026-08-12T00:00:00.000Z", "2026-08-13T00:00:00.000Z")], ["second", "third"])

            bad = root / "bad.jsonl"
            write_handoff(bad, [first])
            bad_text = bad.read_text(encoding="utf-8").replace("eventDigest", "eventDigest-broken", 1)
            bad.write_text(bad_text, encoding="utf-8")
            with self.assertRaises(index.TemporalIndexError) as caught:
                index.build_index(bad, database)
            self.assertEqual(caught.exception.code, "HANDOFF_DIGEST_MISMATCH")
            self.assertEqual(index.verify_database(database)["eventCount"], 2)
            self.assertNotEqual(index.verify_database(database)["eventDigest"], old_digest)

    def test_corruption_fails_closed_until_explicit_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, [event("thread-a", "2026-08-12T04:00:00.000Z", "recover", "active", "file-a", 1)])
            index.build_index(handoff, database, rebuild=True)
            database.write_bytes(b"not a sqlite database")
            with self.assertRaises(index.TemporalIndexError) as caught:
                index.verify_database(database)
            self.assertEqual(caught.exception.code, "INDEX_CORRUPT")
            with self.assertRaises(index.TemporalIndexError):
                index.build_index(handoff, database)
            rebuilt = index.build_index(handoff, database, rebuild=True)
            self.assertTrue(rebuilt["rebuilt"])
            self.assertEqual(index.verify_database(database)["eventCount"], 1)
            self.assertTrue((root / "temporal.sqlite3.pre-rebuild").exists())

    def test_unsupported_schema_fails_closed_and_rebuild_restores_supported_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, [event("thread-a", "2026-08-12T04:00:00.000Z", "schema", "active", "file-a", 1)])
            index.build_index(handoff, database, rebuild=True)
            connection = sqlite3.connect(database)
            connection.execute("UPDATE meta SET value='99' WHERE key='schemaVersion'")
            connection.commit()
            connection.close()
            with self.assertRaises(index.TemporalIndexError) as caught:
                index.verify_database(database)
            self.assertEqual(caught.exception.code, "INDEX_SCHEMA_MISMATCH")
            rebuilt = index.build_index(handoff, database, rebuild=True)
            self.assertTrue(rebuilt["rebuilt"])
            self.assertEqual(index.verify_database(database)["schemaVersion"], 2)

    def test_schema_v1_migrates_in_place_and_rebuild_restores_supported_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            records = [event("thread-a", "2026-08-12T04:00:00.000Z", "migration", "active", "file-a", 1)]
            write_handoff(handoff, records)
            index.build_index(handoff, database, rebuild=True)
            connection = sqlite3.connect(database)
            connection.execute("DROP TABLE thread_metadata")
            connection.execute("DROP TABLE schema_migrations")
            connection.execute("DELETE FROM meta WHERE key='threadMetadata'")
            connection.execute("UPDATE meta SET value='1' WHERE key='schemaVersion'")
            connection.commit()
            connection.close()

            migrated = index.build_index(handoff, database)
            self.assertTrue(migrated["noOp"])
            self.assertEqual(index.verify_database(database)["schemaVersion"], 2)
            connection = sqlite3.connect(database)
            try:
                migration = connection.execute("SELECT version FROM schema_migrations WHERE version=2").fetchone()
                self.assertIsNotNone(migration)
                self.assertIsNotNone(connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='thread_metadata'").fetchone())
            finally:
                connection.close()

            rebuilt = index.build_index(handoff, database, rebuild=True)
            self.assertTrue(rebuilt["rebuilt"])
            self.assertEqual(index.verify_database(database)["eventCount"], len(records))

    def test_missing_v2_metadata_tables_fail_closed_until_explicit_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            records = [event("thread-a", "2026-08-12T04:00:00.000Z", "metadata table", "active", "file-a", 1)]
            write_handoff(handoff, records)
            index.build_index(handoff, database, rebuild=True)
            connection = sqlite3.connect(database)
            connection.execute("DROP TABLE thread_metadata")
            connection.commit()
            connection.close()

            with self.assertRaises(index.TemporalIndexError) as caught:
                index.verify_database(database)
            self.assertEqual(caught.exception.code, "INDEX_SCHEMA_MISMATCH")
            with self.assertRaises(index.TemporalIndexError):
                index.build_index(handoff, database)
            rebuilt = index.build_index(handoff, database, rebuild=True)
            self.assertTrue(rebuilt["rebuilt"])
            self.assertEqual(index.verify_database(database)["schemaVersion"], 2)

    def test_redaction_policy_change_fails_closed_until_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, [event("thread-a", "2026-08-12T04:00:00.000Z", "policy", "active", "file-a", 1)])
            index.build_index(handoff, database, rebuild=True)
            connection = sqlite3.connect(database)
            connection.execute("UPDATE meta SET value='visible-messages-secrets-redacted-v3' WHERE key='policyVersion'")
            connection.commit()
            connection.close()
            with self.assertRaises(index.TemporalIndexError) as caught:
                index.build_index(handoff, database)
            self.assertEqual(caught.exception.code, "INDEX_POLICY_MISMATCH")
            rebuilt = index.build_index(handoff, database, rebuild=True)
            self.assertEqual(rebuilt["policyVersion"], index.POLICY)

    def test_process_kill_during_transaction_preserves_last_good_and_rebuilds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.jsonl"
            incoming = root / "incoming.jsonl"
            database = root / "temporal.sqlite3"
            first = event("thread-a", "2026-08-12T04:00:00.000Z", "first", "active", "file-a", 1)
            second = event("thread-a", "2026-08-12T05:00:00.000Z", "second", "active", "file-a", 2)
            write_handoff(baseline, [first], manifest_digest="baseline")
            write_handoff(incoming, [first, second], manifest_digest="incoming")
            index.build_index(baseline, database, rebuild=True)
            worker = """
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
import thread_temporal_index as index

def crash(connection, _handoff):
    connection.execute('BEGIN IMMEDIATE')
    connection.execute("UPDATE meta SET value='crash' WHERE key='eventDigest'")
    os._exit(86)

index._apply_handoff = crash
index.build_index(Path(sys.argv[2]), Path(sys.argv[3]))
"""
            completed = subprocess.run(
                [sys.executable, "-c", worker, str(MODULE_PATH.parents[1]), str(incoming), str(database)],
                cwd=MODULE_PATH.parents[1],
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 86)
            recovered = index.verify_database(database)
            self.assertEqual(recovered["eventCount"], 1)
            rebuilt = index.build_index(incoming, database, rebuild=True)
            self.assertEqual(rebuilt["eventCount"], 2)

    def test_removed_derived_index_rebuilds_without_changing_canonical_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            records = [
                event("thread-a", "2026-08-12T04:00:00.000Z", "canonical one", "active", "file-a", 1),
                event("thread-a", "2026-08-12T05:00:00.000Z", "canonical two", "active", "file-a", 2),
            ]
            write_handoff(handoff, records)
            canonical_before = handoff.read_bytes()
            index.build_index(handoff, database, rebuild=True)
            database.unlink()

            rebuilt = index.build_index(handoff, database)

            self.assertTrue(rebuilt["rebuilt"])
            self.assertEqual(handoff.read_bytes(), canonical_before)
            self.assertEqual(index.verify_database(database)["eventCount"], len(records))

    def test_incremental_write_failure_rolls_back_to_last_good_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            first = event("thread-a", "2026-08-12T04:00:00.000Z", "first", "active", "file-a", 1)
            second = event("thread-a", "2026-08-12T05:00:00.000Z", "second", "active", "file-a", 2)
            write_handoff(handoff, [first])
            index.build_index(handoff, database, rebuild=True)
            old = index.verify_database(database)
            write_handoff(handoff, [first, second], manifest_digest="manifest-b")
            with patch.object(index, "_apply_handoff", side_effect=sqlite3.OperationalError("database or disk is full")):
                with self.assertRaises(index.TemporalIndexError) as caught:
                    index.build_index(handoff, database)
            self.assertEqual(caught.exception.code, "INDEX_BUILD_FAILED")
            self.assertEqual(index.verify_database(database)["eventDigest"], old["eventDigest"])

    def test_rebuild_promotion_failure_preserves_last_good_database_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            first = event("thread-a", "2026-08-12T04:00:00.000Z", "first", "active", "file-a", 1)
            second = event("thread-a", "2026-08-12T05:00:00.000Z", "second", "active", "file-a", 2)
            write_handoff(handoff, [first])
            index.build_index(handoff, database, rebuild=True)
            old = index.verify_database(database)
            write_handoff(handoff, [first, second], manifest_digest="manifest-b")
            with patch.object(index.os, "replace", side_effect=OSError("simulated promotion failure")):
                with self.assertRaises(index.TemporalIndexError) as caught:
                    index.build_index(handoff, database, rebuild=True)
            self.assertEqual(caught.exception.code, "INDEX_BUILD_FAILED")
            self.assertEqual(index.verify_database(database)["eventDigest"], old["eventDigest"])
            self.assertFalse(any(root.glob("temporal.sqlite3.rebuild-*")))

    def test_concurrent_writers_serialize_and_leave_a_valid_committed_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "temporal.sqlite3"
            handoffs = []
            for suffix in ("one", "two"):
                handoff = root / f"handoff-{suffix}.jsonl"
                write_handoff(handoff, [event(f"thread-{suffix}", "2026-08-12T04:00:00.000Z", suffix, "active", f"file-{suffix}", 1)], manifest_digest=f"manifest-{suffix}")
                handoffs.append(handoff)

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda path: index.build_index(path, database, rebuild=True), handoffs))

            self.assertEqual(len(results), 2)
            verified = index.verify_database(database)
            self.assertEqual(verified["eventCount"], 1)
            self.assertTrue((root / "temporal.sqlite3.writer-lock.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
