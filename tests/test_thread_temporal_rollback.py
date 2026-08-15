from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import thread_temporal_index as index  # noqa: E402

SPEC = importlib.util.spec_from_file_location("thread_temporal_rollback", SCRIPTS / "thread_temporal_rollback.py")
assert SPEC and SPEC.loader
rollback_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rollback_module
SPEC.loader.exec_module(rollback_module)


def make_event(text: str, stamp: str, line: int) -> dict[str, object]:
    event_id = index.sha256("\x00".join(["rollback-thread", "user", stamp, text]))
    return {
        "recordType": "event",
        "contractVersion": index.CONTRACT,
        "eventId": event_id,
        "threadId": "rollback-thread",
        "role": "user",
        "timestampUtc": stamp,
        "text": text,
        "textDigest": index.sha256(text),
        "sourceRef": {"sourceKind": "active", "sourceFileDigest": "rollback-source", "lineNumber": line},
    }


def write_handoff(path: Path, events: list[dict[str, object]], manifest: str) -> None:
    header = {
        "recordType": "header",
        "contractVersion": index.CONTRACT,
        "policyVersion": index.POLICY,
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": 1,
        "manifestDigest": manifest,
    }
    lines = [json.dumps(header, separators=(",", ":")) + "\n"]
    digest = hashlib.sha256()
    for event in events:
        line = json.dumps(event, separators=(",", ":")) + "\n"
        lines.append(line)
        digest.update(line.encode("utf-8"))
    lines.append(json.dumps({
        "recordType": "trailer",
        "contractVersion": index.CONTRACT,
        "eventCount": len(events),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": digest.hexdigest(),
    }, separators=(",", ":")) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


class TemporalRollbackTests(unittest.TestCase):
    def test_restores_verified_previous_pair_without_touching_canonical_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            temporal = root / "temporal"
            temporal.mkdir()
            baseline_handoff = root / "baseline.ndjson"
            current_handoff = root / "current.ndjson"
            baseline_event = make_event("baseline", "2026-01-01T12:00:00.000Z", 1)
            current_event = make_event("current", "2026-01-01T12:01:00.000Z", 2)
            write_handoff(baseline_handoff, [baseline_event], "baseline-manifest")
            write_handoff(current_handoff, [baseline_event, current_event], "current-manifest")
            database = temporal / "temporal.sqlite3"
            index.build_index(current_handoff, database, rebuild=True)
            shutil.copy2(baseline_handoff, temporal / "temporal-events.ndjson.previous")
            baseline_database = root / "baseline.sqlite3"
            index.build_index(baseline_handoff, baseline_database, rebuild=True)
            shutil.copy2(baseline_database, temporal / "temporal.sqlite3.previous")
            shutil.copy2(current_handoff, temporal / "temporal-events.ndjson")
            canonical_marker = root / "canonical-marker.jsonl"
            canonical_marker.write_text("canonical source remains untouched\n", encoding="utf-8")
            canonical_before = canonical_marker.read_bytes()

            result = rollback_module.rollback(temporal)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["restored"]["eventCount"], 1)
            self.assertFalse(result["canonicalStateTouched"])
            self.assertEqual(canonical_marker.read_bytes(), canonical_before)
            self.assertEqual(index.verify_database(database)["eventCount"], 1)
            self.assertEqual((temporal / "temporal-events.ndjson").read_bytes(), baseline_handoff.read_bytes())

    def test_mismatched_previous_pair_fails_closed_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            temporal = root / "temporal"
            temporal.mkdir()
            baseline = root / "baseline.ndjson"
            current = root / "current.ndjson"
            write_handoff(baseline, [make_event("baseline", "2026-01-01T12:00:00.000Z", 1)], "baseline")
            write_handoff(current, [make_event("current", "2026-01-01T12:01:00.000Z", 2)], "current")
            database = temporal / "temporal.sqlite3"
            index.build_index(current, database, rebuild=True)
            shutil.copy2(current, temporal / "temporal-events.ndjson")
            shutil.copy2(baseline, temporal / "temporal-events.ndjson.previous")
            shutil.copy2(database, temporal / "temporal.sqlite3.previous")
            before = (temporal / "temporal-events.ndjson").read_bytes()
            with self.assertRaises(rollback_module.TemporalRollbackError) as caught:
                rollback_module.rollback(temporal)
            self.assertEqual(caught.exception.code, "ROLLBACK_GENERATION_MISMATCH")
            self.assertEqual((temporal / "temporal-events.ndjson").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

