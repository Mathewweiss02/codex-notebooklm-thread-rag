from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import notebooklm_temporal_source_map as source_map  # noqa: E402


class NotebookLMTemporalSourceMapTests(unittest.TestCase):
    def make_fixture(self, root: Path, role: str = "retrieval") -> tuple[Path, Path]:
        projection = root / "projection"
        projection.mkdir()
        source_file = projection / "thread-a-p1.md"
        source_file.write_text("sanitized projected source\n", encoding="utf-8")
        digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        state = {
            "schemaVersion": 1,
            "policyVersion": "visible-messages-secrets-redacted-v4",
            "deviceId": "fixture-device",
            "notebookId": "notebook-a",
            "updatedAt": "2026-08-14T00:00:00.000Z",
            "threads": {
                "thread-a": {
                    "threadId": "thread-a",
                    "revision": 2,
                    "uploadRevision": 2,
                    "uploadStatus": "ready",
                    "parts": [{
                        "part": 1,
                        "totalParts": 1,
                        "file": str(source_file),
                        "title": "Thread A revision 2 part 1",
                        "sha256": digest,
                        "sourceId": "source-a",
                        "status": "ready",
                    }],
                    "previousSources": [{"sourceId": "old-source-a", "title": "Thread A revision 1 part 1"}],
                }
            },
        }
        (projection / "state.json").write_text(json.dumps(state), encoding="utf-8")
        config = {
            "Device": "fixture-device",
            "ProjectionRoot": str(projection),
            "Profile": "personal",
            "NotebookId": "notebook-a",
            "NotebookRole": role,
            "DisposableSearchChat": True,
            "ConversationPolicy": "disposable",
            "RejectUntrackedSources": True,
        }
        config_path = root / "sync_config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path, source_file

    def test_current_ready_part_maps_without_previous_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = self.make_fixture(Path(temporary))
            result = source_map.map_sources(config, ["thread-a"])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["coverage"]["mappedThreadCount"], 1)
        self.assertEqual(result["coverage"]["mappedPartCount"], 1)
        self.assertEqual(result["mapping"][0]["sourceId"], "source-a")
        self.assertEqual(result["liveVerification"]["status"], "not-run")

    def test_missing_thread_degrades_and_strict_boundary_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = self.make_fixture(Path(temporary))
            result = source_map.map_sources(config, ["thread-missing"])

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["problems"][0]["code"], "THREAD_NOT_ENROLLED")
        self.assertEqual(result["coverage"]["mappedPartCount"], 0)

    def test_projection_digest_drift_degrades_before_remote_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, source_file = self.make_fixture(Path(temporary))
            source_file.write_text("changed after projection\n", encoding="utf-8")
            result = source_map.map_sources(config, ["thread-a"])

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["problems"][0]["code"], "SOURCE_DRIFT")

    def test_chat_config_is_never_accepted_for_automated_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = self.make_fixture(Path(temporary), role="chat")
            with self.assertRaises(source_map.SourceMapError) as caught:
                source_map.map_sources(config, ["thread-a"])
        self.assertEqual(caught.exception.code, "NOTEBOOK_ROLE_UNSAFE")

    def test_live_mapping_rejects_untracked_sources_but_allows_previous_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = self.make_fixture(Path(temporary))
            payload = {
                "sources": [
                    {"id": "source-a", "title": "Thread A revision 2 part 1", "status": "ready"},
                    {"id": "old-source-a", "title": "Thread A revision 1 part 1", "status": "ready"},
                    {"id": "unrelated", "title": "Unrelated", "status": "ready"},
                ]
            }
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
            with patch.object(source_map.subprocess, "run", return_value=completed):
                result = source_map.map_sources(config, ["thread-a"], live=True, notebooklm="notebooklm")

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["liveVerification"]["missing"], 0)
        self.assertEqual(result["liveVerification"]["allowedLineage"], 1)
        self.assertEqual(result["liveVerification"]["untracked"], 1)
        self.assertEqual(result["problems"][0]["code"], "REMOTE_SOURCE_DRIFT")

    def test_public_payload_removes_identifiers_from_cli_reports(self) -> None:
        payload = {
            "contractVersion": "temporal-source-map-v1",
            "status": "ok",
            "config": {"device": "fixture", "profile": "personal", "notebookId": "secret-notebook"},
            "selection": {"requestedThreadCount": 1, "requestedThreadIds": ["secret-thread"]},
            "mapping": [{"threadId": "secret-thread", "sourceId": "secret-source", "title": "private title"}],
            "problems": [],
            "liveVerification": {"status": "ok"},
            "state": {"policyVersion": "visible-messages-secrets-redacted-v4", "notebookId": "secret-notebook"},
            "coverage": {"mappedPartCount": 1},
            "latency": {"totalMs": 1},
        }
        safe = source_map.public_payload(payload)
        serialized = json.dumps(safe)
        self.assertNotIn("secret-notebook", serialized)
        self.assertNotIn("secret-thread", serialized)
        self.assertNotIn("secret-source", serialized)
        self.assertNotIn("private title", serialized)


if __name__ == "__main__":
    unittest.main()
