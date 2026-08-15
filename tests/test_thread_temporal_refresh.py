from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "thread_temporal_refresh.py"
SPEC = importlib.util.spec_from_file_location("thread_temporal_refresh", SCRIPT)
assert SPEC and SPEC.loader
refresh = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = refresh
SPEC.loader.exec_module(refresh)


def make_handoff(path: Path, *, event_text: str = "hello", quarantine: bool = False) -> None:
    event = {
        "recordType": "event",
        "contractVersion": "temporal-event-v1",
        "threadId": "thread-a",
        "role": "user",
        "timestampUtc": "2026-01-01T12:00:00.000Z",
        "text": event_text,
        "textDigest": hashlib.sha256(event_text.encode()).hexdigest(),
        "sourceRef": {
            "sourceKind": "active",
            "sourceFileDigest": "source-digest",
            "lineNumber": 1,
        },
    }
    event["eventId"] = hashlib.sha256(
        "\x00".join([event["threadId"], event["role"], event["timestampUtc"], event["text"]]).encode()
    ).hexdigest()
    event_line = json.dumps(event, separators=(",", ":")) + "\n"
    event_digest = hashlib.sha256(event_line.encode()).hexdigest()
    rows = [
        {
            "recordType": "header",
            "contractVersion": "temporal-event-v1",
            "policyVersion": "visible-messages-secrets-redacted-v4",
            "generatedAt": "2026-01-01T00:00:00.000Z",
            "threadCount": 1,
            "manifestDigest": "manifest-digest",
        },
        event,
    ]
    if quarantine:
        rows.append(
            {
                "recordType": "quarantine",
                "contractVersion": "temporal-event-v1",
                "threadId": "thread-a",
                "reason": "missing-timestamp",
                "sourceRef": {
                    "sourceKind": "active",
                    "sourceFileDigest": "source-digest",
                    "lineNumber": 2,
                },
            }
        )
    rows.append(
        {
            "recordType": "trailer",
            "contractVersion": "temporal-event-v1",
            "eventCount": 1,
            "quarantineCount": 1 if quarantine else 0,
            "malformedLines": 0,
            "overflowLines": 0,
            "overflowVisibleLines": 0,
            "duplicateMessages": 0,
            "eventDigest": event_digest,
        }
    )
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


class TemporalRefreshTests(unittest.TestCase):
    def make_state(self, root: Path) -> Path:
        state = root / "state.json"
        state.write_text(
            json.dumps(
                {
                    "policyVersion": "visible-messages-secrets-redacted-v4",
                    "threads": {"thread-a": {}},
                }
            ),
            encoding="utf-8",
        )
        return state

    def fake_child(self, fixture: Path, *, quarantine: bool = False):
        def run(_executable, arguments, _label, _timeout):
            if "--out" not in arguments:
                self.fail("staged command missing output")
            output = Path(arguments[arguments.index("--out") + 1])
            if "--state" in arguments:
                source = output.parent / "source.jsonl"
                source.write_text("source\n", encoding="utf-8")
                output.write_text(
                    json.dumps(
                        {
                            "threadCount": 1,
                            "missingThreadCount": 0,
                            "threads": [{"id": "thread-a", "path": str(source), "updatedAt": 1}],
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                if quarantine:
                    make_handoff(output, quarantine=True)
                else:
                    output.write_bytes(fixture.read_bytes())
        return run

    def test_refresh_stages_and_promotes_verified_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self.make_state(root)
            fixture = root / "fixture.ndjson"
            make_handoff(fixture, event_text="new")
            with patch.object(refresh, "_run_child", side_effect=self.fake_child(fixture)):
                result = refresh.refresh(
                    state_path=state,
                    root=root / "temporal",
                    node_path="node",
                    dry_run=False,
                )
            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["changed"])
            self.assertEqual(result["eventCount"], 1)
            self.assertTrue((root / "temporal" / "temporal.sqlite3").is_file())
            self.assertTrue((root / "temporal" / "temporal-events.ndjson").is_file())
            self.assertEqual(refresh.temporal_index.verify_database(root / "temporal" / "temporal.sqlite3")["eventCount"], 1)

    def test_diagnostics_fail_closed_before_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self.make_state(root)
            temporal_root = root / "temporal"
            temporal_root.mkdir()
            old_handoff = temporal_root / "temporal-events.ndjson"
            make_handoff(old_handoff, event_text="old")
            refresh.temporal_index.build_index(old_handoff, temporal_root / "temporal.sqlite3", rebuild=True)
            before = (temporal_root / "temporal.sqlite3").read_bytes()
            with patch.object(refresh, "_run_child", side_effect=self.fake_child(old_handoff, quarantine=True)):
                with self.assertRaises(refresh.TemporalRefreshError) as caught:
                    refresh.refresh(state_path=state, root=temporal_root, node_path="node")
            self.assertEqual(caught.exception.code, "SOURCE_DIAGNOSTICS")
            self.assertEqual((temporal_root / "temporal.sqlite3").read_bytes(), before)
            self.assertEqual(refresh.temporal_index.verify_database(temporal_root / "temporal.sqlite3")["eventCount"], 1)

    def test_invalid_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.json"
            state.write_text(json.dumps({"policyVersion": "wrong", "threads": {"a": {}}}), encoding="utf-8")
            with self.assertRaises(refresh.TemporalRefreshError) as caught:
                refresh.refresh(state_path=state, root=root / "temporal", node_path="node")
            self.assertEqual(caught.exception.code, "POLICY_MISMATCH")

    def test_overlapping_refreshes_serialize_and_leave_paired_verified_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self.make_state(root)
            fixture = root / "fixture.ndjson"
            make_handoff(fixture, event_text="overlap")
            temporal_root = root / "temporal"
            activity_lock = threading.Lock()
            active = 0
            maximum_active = 0

            def overlapping_child(_executable, arguments, _label, _timeout):
                nonlocal active, maximum_active
                with activity_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                try:
                    time.sleep(0.06)
                    output = Path(arguments[arguments.index("--out") + 1])
                    if "--state" in arguments:
                        source = output.parent / "source.jsonl"
                        source.write_text("source\n", encoding="utf-8")
                        output.write_text(
                            json.dumps({"threadCount": 1, "missingThreadCount": 0, "threads": [{"id": "thread-a", "path": str(source), "updatedAt": 1}]}),
                            encoding="utf-8",
                        )
                    else:
                        output.write_bytes(fixture.read_bytes())
                finally:
                    with activity_lock:
                        active -= 1

            with patch.object(refresh, "_run_child", side_effect=overlapping_child):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(
                        lambda _: refresh.refresh(state_path=state, root=temporal_root, node_path="node"),
                        range(2),
                    ))

            self.assertEqual(maximum_active, 1)
            self.assertTrue(all(result["status"] == "ok" for result in results))
            verified = refresh.temporal_index.verify_database(temporal_root / "temporal.sqlite3")
            summary = refresh._summarize_handoff(refresh.temporal_index.load_handoff(temporal_root / "temporal-events.ndjson"))
            self.assertEqual(verified["eventDigest"], summary["eventDigest"])
            self.assertEqual(verified["manifestDigest"], summary["manifestDigest"])


if __name__ == "__main__":
    unittest.main()
