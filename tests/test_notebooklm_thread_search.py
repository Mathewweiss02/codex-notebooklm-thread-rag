from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_search.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_search", MODULE_PATH)
search = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(search)


class SearchTests(unittest.TestCase):
    def test_local_authority_can_promote_a_second_semantic_candidate(self):
        candidates = [
            {"threadId": "decoy", "citationRank": 1},
            {"threadId": "target", "citationRank": 2},
        ]
        local = [
            {"id": "target", "score": 80, "coverage": {"thread": 1}},
            {"id": "decoy", "score": 40, "coverage": {"thread": 0.5}},
        ]
        ranked = search.merge_local_ranking(candidates, local)
        self.assertEqual(ranked[0]["threadId"], "target")
        self.assertEqual(ranked[0]["semanticRank"], 2)
        self.assertEqual(ranked[0]["finalRank"], 1)
        self.assertTrue(ranked[0]["locallyVerified"])

    def test_unmatched_semantic_candidates_are_retained_but_not_verified(self):
        ranked = search.merge_local_ranking(
            [{"threadId": "target"}, {"threadId": "unmatched"}],
            [{"id": "target", "score": 20}],
        )
        self.assertEqual([item["threadId"] for item in ranked], ["target", "unmatched"])
        self.assertFalse(ranked[1]["locallyVerified"])

    def test_semantic_title_match_resists_generic_local_false_positive(self):
        candidates = [
            {"threadId": "target", "title": "Research data broker opt-outs", "citationRank": 1},
            {"threadId": "decoy", "title": "Research OhMyCodex setup", "citationRank": 2},
        ]
        local = [{"id": "decoy", "score": 70, "coverage": {"thread": 1}}]
        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="Find the research on removing my information from data brokers.",
        )
        self.assertEqual(ranked[0]["threadId"], "target")
        self.assertFalse(ranked[0]["locallyVerified"])
        self.assertGreater(ranked[0]["titleQueryOverlap"], ranked[1]["titleQueryOverlap"])

    def test_title_and_local_evidence_can_recover_later_semantic_candidate(self):
        candidates = [
            {"threadId": "decoy", "title": "Audio direction", "citationRank": 1},
            {"threadId": "target", "title": "Build game with image2three.js", "citationRank": 2},
        ]
        local = [{"id": "target", "score": 50, "coverage": {"thread": 0.6}}]
        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="Find the game built from images with image2three.js.",
        )
        self.assertEqual(ranked[0]["threadId"], "target")
        self.assertEqual(ranked[0]["semanticRank"], 2)

    def test_explicit_exact_title_cue_wins_over_content_near_duplicate(self):
        candidates = [
            {"threadId": "original", "title": "Pull ADS proxy audience"},
            {"threadId": "copy", "title": "Pull ADS proxy audience (2)"},
        ]
        local = [{"id": "copy", "score": 90}, {"id": "original", "score": 80}]
        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="Find the task titled exactly Pull ADS proxy audience, without the (2) suffix.",
        )
        self.assertEqual(ranked[0]["threadId"], "original")
        self.assertTrue(ranked[0]["exactTitleMatch"])

    def test_query_sanitization_removes_credential_shapes(self):
        value, count = search.sanitize_query(
            "Find AKIAABCDEFGHIJKLMNOP access_token=supersecretvalue\n"
            "ghp_abcdefghijklmnopqrstuvwxyz1234\nCookie: SID=private-cookie-value\n"
            "https://user:password@example.com?a=1&api_key=private-value\n"
            "C:\\Users\\private-user\\Documents\\trace.txt"
        )
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", value)
        self.assertNotIn("supersecretvalue", value)
        self.assertNotIn("private-cookie-value", value)
        self.assertNotIn("private-user", value)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz1234", value)
        self.assertGreaterEqual(count, 6)

    def test_query_and_projection_share_remote_redaction_contract(self):
        self.assertEqual(search.REMOTE_REDACTION_POLICY, "remote-notebooklm-secrets-redacted-v1")

    def test_registered_chat_notebooks_are_not_automatic_search_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            retrieval = root / "retrieval.json"
            chat = root / "chat.json"
            retrieval.write_text(json.dumps({"NotebookRole": "retrieval"}), encoding="utf-8")
            chat.write_text(json.dumps({"NotebookRole": "chat"}), encoding="utf-8")
            registry = root / "thread-rag" / "registry.json"
            registry.parent.mkdir()
            registry.write_text(json.dumps({"Configs": [{"ConfigPath": str(retrieval)}, {"ConfigPath": str(chat)}]}), encoding="utf-8")
            self.assertEqual(search.discover_configs([], root), [retrieval.resolve()])

    def test_state_source_id_collision_is_rejected_before_remote_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = {
                "policyVersion": search.REQUIRED_POLICY,
                "threads": {
                    "a": {"revision": 1, "uploadRevision": 1, "parts": [{"part": 1, "sourceId": "shared", "title": "a"}]},
                    "b": {"revision": 1, "uploadRevision": 1, "parts": [{"part": 1, "sourceId": "shared", "title": "b"}]},
                },
            }
            (root / "state.json").write_text(json.dumps(state), encoding="utf-8")
            (root / "runner_state.json").write_text(json.dumps({"LastSuccessAt": datetime.now(UTC).isoformat()}), encoding="utf-8")
            config = root / "config.json"
            config.write_text(json.dumps({"ProjectionRoot": str(root), "NotebookRole": "retrieval"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate projected source id"):
                search.load_instance(config, 45, False)


if __name__ == "__main__":
    unittest.main()
