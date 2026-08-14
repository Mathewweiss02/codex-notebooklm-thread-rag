from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from notebooklm_isolated_ramp import (  # noqa: E402
    RampError,
    clone_state_for_replica,
    current_source_map,
    main,
    run_queries,
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

    def test_query_waves_use_distinct_replicas_and_preserve_scope(self) -> None:
        class FakeChat:
            def __init__(self) -> None:
                self.active = 0
                self.peak = 0

            async def get_conversation_id(self, _notebook_id: str) -> None:
                return None

            async def ask(self, notebook_id: str, _query: str) -> object:
                self.active += 1
                self.peak = max(self.peak, self.active)
                await asyncio.sleep(0.01)
                self.active -= 1
                source_id = "source-0" if notebook_id == "notebook-0" else "source-1"
                return SimpleNamespace(
                    answer="answer",
                    is_follow_up=False,
                    references=[SimpleNamespace(citation_number=1, source_id=source_id)],
                )

            def clear_cache(self) -> None:
                return None

        class FakeClient:
            def __init__(self) -> None:
                self.chat = FakeChat()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zero").mkdir()
            (root / "one").mkdir()
            state0 = self.make_state(root / "zero")
            state1 = self.make_state(root / "one")
            state0["threads"]["thread-one"]["parts"][0]["sourceId"] = "source-0"
            state1["threads"]["thread-one"]["parts"][0]["sourceId"] = "source-1"
            paths = []
            for index, state in enumerate((state0, state1)):
                state_root = root / str(index)
                state_root.mkdir(parents=True, exist_ok=True)
                state_path = state_root / "state.json"
                state_path.write_text(json.dumps(state), encoding="utf-8")
                paths.append(state_path)
            from notebooklm_isolated_ramp import Replica

            replicas = [
                Replica(0, "notebook-0", paths[0], {"source-0": "thread-one"}, frozenset({"thread-one-p1"}), "a" * 64, True),
                Replica(1, "notebook-1", paths[1], {"source-1": "thread-one"}, frozenset({"thread-one-p1"}), "b" * 64, False),
            ]
            cases = [
                {"caseId": "case-0", "query": "zero", "expectedThreadIds": ["thread-one"], "expectation": "match"},
                {"caseId": "case-1", "query": "one", "expectedThreadIds": ["thread-one"], "expectation": "match"},
            ]
            fake = FakeClient()
            with patch("notebooklm_isolated_ramp.local_rerank_candidates", side_effect=lambda _q, candidates, **_kw: (candidates, {"abstained": False})):
                result = asyncio.run(
                    run_queries(fake, replicas, cases, runs=1, node_path=None, timeout_seconds=1)
                )
            self.assertEqual(fake.chat.peak, 2)
            self.assertEqual(result["summary"]["total"], 2)
            self.assertEqual(result["summary"]["passedExpectation"], 2)
            self.assertEqual(result["summary"]["sourceScopeFailures"], 0)
            self.assertEqual(result["summary"]["crossTalkReferenceCount"], 0)


if __name__ == "__main__":
    unittest.main()
