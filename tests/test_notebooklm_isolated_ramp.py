from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from notebooklm_isolated_ramp import (  # noqa: E402
    RampError,
    clone_state_for_replica,
    current_source_map,
    main,
    safe_error,
    validate_live_sources,
    validate_retrieval_config,
)


class IsolatedRampTests(unittest.TestCase):
    def make_state(self, root: Path) -> dict[str, object]:
        source = root / "projection.md"
        source.write_text("sanitized projection\n", encoding="utf-8")
        return {
            "policyVersion": "visible-messages-secrets-redacted-v4",
            "notebookId": "parent-notebook-id",
            "threads": {
                "thread-one": {
                    "title": "A thread",
                    "parts": [
                        {
                            "part": 1,
                            "title": "thread-one-p1",
                            "file": str(source),
                            "bytes": source.stat().st_size,
                            "sourceId": "parent-source-id",
                            "status": "ready",
                        }
                    ],
                    "previousSources": [{"sourceId": "old-source-id"}],
                    "notebookId": "parent-notebook-id",
                    "uploadRevision": "r1",
                    "uploadStatus": "ready",
                }
            },
        }

    def test_retrieval_config_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            config = {
                "NotebookRole": "retrieval",
                "ConversationPolicy": "dedicated-retrieval-disposable-v1",
                "DisposableSearchChat": True,
                "RejectUntrackedSources": True,
                "Profile": "personal",
            }
            validate_retrieval_config(config, state_path)
            config["NotebookRole"] = "chat"
            with self.assertRaises(RampError):
                validate_retrieval_config(config, state_path)

    def test_clone_removes_parent_source_and_notebook_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.make_state(Path(directory))
            clone = clone_state_for_replica(state)
            self.assertNotIn("notebookId", clone)
            thread = clone["threads"]["thread-one"]
            self.assertNotIn("notebookId", thread)
            self.assertNotIn("previousSources", thread)
            self.assertNotIn("sourceId", thread["parts"][0])
            self.assertEqual(thread["uploadStatus"], "pending")
            self.assertEqual(state["threads"]["thread-one"]["parts"][0]["sourceId"], "parent-source-id")

    def test_live_source_validation_requires_exact_title_fingerprint(self) -> None:
        sources = [SimpleNamespace(id="new-source", title="thread-one-p1")]
        by_id, titles = validate_live_sources(
            sources,
            expected_titles=frozenset({"thread-one-p1"}),
            expected_count=1,
        )
        self.assertEqual(set(by_id), {"new-source"})
        self.assertEqual(titles, frozenset({"thread-one-p1"}))
        with self.assertRaises(RampError):
            validate_live_sources(
                [SimpleNamespace(id="new-source", title="wrong-title")],
                expected_titles=frozenset({"thread-one-p1"}),
                expected_count=1,
            )

    def test_error_evidence_does_not_retain_message_text(self) -> None:
        evidence = safe_error(RuntimeError("Authorization: Bearer do-not-retain"))
        self.assertNotIn("do-not-retain", json.dumps(evidence))
        self.assertEqual(evidence["type"], "RuntimeError")

    def test_dry_run_writes_aggregate_plan_without_live_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.make_state(root)
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            config_path = root / "sync_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "ProjectionRoot": str(root),
                        "Profile": "personal",
                        "NotebookRole": "retrieval",
                        "ConversationPolicy": "dedicated-retrieval-disposable-v1",
                        "DisposableSearchChat": True,
                        "RejectUntrackedSources": True,
                    }
                ),
                encoding="utf-8",
            )
            output = root / "report.json"
            self.assertEqual(main(["--config", str(config_path), "--out", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "dry-run")
            self.assertEqual(report["sourcePartCount"], 1)
            self.assertNotIn("parent-source-id", output.read_text(encoding="utf-8"))

    def test_current_source_map_requires_uploaded_parts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.make_state(Path(directory))
            source_to_thread, titles, fingerprint = current_source_map(state)
            self.assertEqual(source_to_thread, {"parent-source-id": "thread-one"})
            self.assertEqual(titles, frozenset({"thread-one-p1"}))
            self.assertEqual(len(fingerprint), 64)


if __name__ == "__main__":
    unittest.main()
