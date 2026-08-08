from __future__ import annotations

import importlib.util
import unittest
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
        value, count = search.sanitize_query("Find AKIAABCDEFGHIJKLMNOP and token=supersecretvalue")
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", value)
        self.assertNotIn("supersecretvalue", value)
        self.assertGreaterEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
