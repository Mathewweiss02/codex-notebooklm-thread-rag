from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_search.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_search", MODULE_PATH)
search = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(search)


class FakeChat:
    def __init__(self, attempts):
        self.attempts = list(attempts)
        self.ask_count = 0

    async def get_conversation_id(self, _notebook_id):
        return None

    async def delete_conversation(self, _notebook_id, _conversation_id):
        return None

    def clear_cache(self):
        return None

    async def ask(self, _notebook_id, _query):
        references = self.attempts[self.ask_count]
        self.ask_count += 1
        return SimpleNamespace(answer="answer", references=references, is_follow_up=False)


class FakeClientContext:
    def __init__(self, attempts):
        self.chat = FakeChat(attempts)
        self.sources = SimpleNamespace(list=self.list_sources)

    async def list_sources(self, _notebook_id, strict=True):
        self.assert_strict = strict
        return [SimpleNamespace(id="source-a"), SimpleNamespace(id="source-b")]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class SearchTests(unittest.TestCase):
    @staticmethod
    def retry_instance():
        return {
            "configPath": Path("config.json"),
            "config": {
                "Profile": "test",
                "NotebookId": "notebook",
                "NotebookRole": "retrieval",
                "DisposableSearchChat": True,
                "Device": "test-device",
            },
            "state": {
                "threads": {
                    "thread-a": {"title": "Alpha"},
                    "thread-b": {"title": "Beta"},
                }
            },
            "sourceToThread": {"source-a": "thread-a", "source-b": "thread-b"},
            "lastSuccess": datetime.now(UTC),
        }

    def test_sparse_semantic_result_triggers_one_fresh_retry(self):
        context = FakeClientContext([
            [SimpleNamespace(source_id="source-a", citation_number=1)],
            [
                SimpleNamespace(source_id="source-a", citation_number=1),
                SimpleNamespace(source_id="source-b", citation_number=2),
            ],
        ])
        with patch.object(search.NotebookLMClient, "from_storage", return_value=context):
            result = asyncio.run(search.search_instance(self.retry_instance(), "query", False, 5, 2))
        self.assertEqual(result["attemptsUsed"], 2)
        self.assertEqual([item["threadId"] for item in result["candidates"]], ["thread-a", "thread-b"])

    def test_two_semantic_candidates_stop_after_first_attempt(self):
        context = FakeClientContext([[
            SimpleNamespace(source_id="source-a", citation_number=1),
            SimpleNamespace(source_id="source-b", citation_number=2),
        ]])
        with patch.object(search.NotebookLMClient, "from_storage", return_value=context):
            result = asyncio.run(search.search_instance(self.retry_instance(), "query", False, 5, 2))
        self.assertEqual(result["attemptsUsed"], 1)
        self.assertEqual(context.chat.ask_count, 1)

    def test_fast_transport_disables_library_retries(self):
        context = FakeClientContext([[
            SimpleNamespace(source_id="source-a", citation_number=1),
        ]])
        with patch.object(search.NotebookLMClient, "from_storage", return_value=context) as factory:
            result = asyncio.run(search.search_instance(
                self.retry_instance(),
                "query",
                False,
                5,
                max_semantic_attempts=1,
                transport_max_retries=0,
            ))
        self.assertEqual(context.chat.ask_count, 1)
        self.assertEqual(result["maxSemanticAttempts"], 1)
        self.assertEqual(result["transportMaxRetries"], 0)
        self.assertEqual(factory.call_args.kwargs["rate_limit_max_retries"], 0)
        self.assertEqual(factory.call_args.kwargs["server_error_max_retries"], 0)

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

    def test_title_overlap_recognizes_common_prefix_abbreviation(self):
        overlap = search.title_query_overlap(
            "work out what a repository was for",
            "Identify repo purpose",
        )
        self.assertGreaterEqual(overlap, 0.25)

    def test_compound_title_overlap_matches_camel_case_product_names(self):
        overlap = search.compound_title_query_overlap(
            "install and configure Oh My Codex",
            "Research OhMyCodex setup",
        )
        self.assertGreaterEqual(overlap, 0.25)

    def test_title_overlap_splits_underscore_identifiers(self):
        chat = search.title_query_overlap(
            "the T3MP3ST chat success token",
            "Reply exactly: T3MP3ST_CODEX_CHAT_OK",
        )
        non_chat = search.title_query_overlap(
            "the T3MP3ST chat success token",
            "Reply exactly: T3MP3ST_CODEX_OK",
        )
        self.assertGreater(chat, non_chat)

    def test_unique_candidate_consensus_accepts_moderate_independent_evidence(self):
        confidence = search.candidate_confidence({
            "titleQueryOverlap": 0,
            "localScore": 50,
            "localCoverage": {"bestWindow": 0.6},
        }, candidate_count=1)
        self.assertTrue(confidence["accepted"])
        self.assertEqual(confidence["reason"], "unique-candidate-consensus")

    def test_duplicate_title_consensus_accepts_bounded_group_evidence(self):
        confidence = search.candidate_confidence({
            "titleQueryOverlap": 0.05,
            "duplicateTitleCount": 3,
            "duplicateGroupQueryOverlap": 0.1,
        }, candidate_count=4)
        self.assertTrue(confidence["accepted"])
        self.assertEqual(confidence["reason"], "duplicate-title-consensus")

    def test_duplicate_title_group_can_beat_one_related_unique_title(self):
        long_title = "codex thread ops pull the full markdowns of each chat thread with additional implementation details"
        candidates = [
            {"threadId": "related", "title": "Export Codex Thread Markdown", "citationRank": 1},
            {"threadId": "sibling-a", "title": long_title, "citationRank": 2},
            {"threadId": "sibling-b", "title": long_title, "citationRank": 3},
        ]
        ranked = search.merge_local_ranking(
            candidates,
            [],
            query="which repeated chats exported the whole task history through codex thread ops",
        )
        self.assertIn(ranked[0]["threadId"], {"sibling-a", "sibling-b"})

    def test_duplicate_title_group_yields_to_stronger_competing_title(self):
        duplicate_title = "catalog cleanup"
        candidates = [
            {"threadId": "expected", "title": "Catalog video subscriptions", "citationRank": 1},
            {"threadId": "sibling-a", "title": duplicate_title, "citationRank": 2},
            {"threadId": "sibling-b", "title": duplicate_title, "citationRank": 3},
        ]
        local = [
            {"id": "sibling-a", "score": 53.22, "coverage": {"bestWindow": 0.735}},
            {"id": "sibling-b", "score": 42.89, "coverage": {"bestWindow": 0.47}},
            {"id": "expected", "score": 59.23, "coverage": {"bestWindow": 0.735}},
        ]

        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="the task that organized or inventoried all video subscriptions",
        )

        self.assertEqual(ranked[0]["threadId"], "expected")
        sibling = next(item for item in ranked if item["threadId"] == "sibling-a")
        self.assertTrue(sibling["duplicateGroupBlockedByCompetingEvidence"])

    def test_three_way_duplicate_consensus_can_override_one_competing_title(self):
        repeated = "Pull the full markdowns of each chat thread with implementation details"
        candidates = [
            {"threadId": "related", "title": "Export Codex Thread Markdown", "citationRank": 1},
            {"threadId": "sibling-a", "title": repeated, "citationRank": 2},
            {"threadId": "sibling-b", "title": repeated, "citationRank": 3},
            {"threadId": "sibling-c", "title": repeated, "citationRank": 4},
        ]
        local = [
            {"id": "related", "score": 53, "coverage": {"bestWindow": 0.7}},
            {"id": "sibling-a", "score": 21, "coverage": {"bestWindow": 0.26}},
            {"id": "sibling-b", "score": 20, "coverage": {"bestWindow": 0.25}},
            {"id": "sibling-c", "score": 13, "coverage": {"bestWindow": 0.12}},
        ]

        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="which repeated chats pulled the full markdowns through codex thread ops",
        )

        self.assertIn(ranked[0]["threadId"], {"sibling-a", "sibling-b", "sibling-c"})
        self.assertFalse(ranked[0]["duplicateGroupBlockedByCompetingEvidence"])

    def test_strong_two_way_group_can_override_correlated_unique_title(self):
        repeated = "pull the full markdown of each chat thread"
        candidates = [
            {"threadId": "related", "title": "Export Chat Thread Markdown", "citationRank": 1},
            {"threadId": "sibling-a", "title": repeated, "citationRank": 2},
            {"threadId": "sibling-b", "title": repeated, "citationRank": 3},
        ]
        local = [
            {"id": "related", "score": 51, "coverage": {"bestWindow": 0.55}},
            {"id": "sibling-a", "score": 43, "coverage": {"bestWindow": 0.38}},
            {"id": "sibling-b", "score": 42, "coverage": {"bestWindow": 0.38}},
        ]

        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="which repeated chats pulled the full markdown of each thread",
        )

        self.assertIn(ranked[0]["threadId"], {"sibling-a", "sibling-b"})
        self.assertFalse(ranked[0]["duplicateGroupBlockedByCompetingEvidence"])

    def test_weak_three_way_group_yields_to_correlated_unique_title(self):
        repeated = "generic authentication setup with several unrelated details"
        candidates = [
            {"threadId": "duplicate-a", "title": repeated, "citationRank": 1},
            {"threadId": "duplicate-b", "title": repeated, "citationRank": 2},
            {"threadId": "expected", "title": "Plan Pi Codex integration", "citationRank": 3},
            {"threadId": "duplicate-c", "title": repeated, "citationRank": 4},
        ]
        local = [
            {"id": "duplicate-a", "score": 40, "coverage": {"bestWindow": 0.33}},
            {"id": "duplicate-b", "score": 49, "coverage": {"bestWindow": 0.58}},
            {"id": "duplicate-c", "score": 40, "coverage": {"bestWindow": 0.33}},
            {"id": "expected", "score": 48, "coverage": {"bestWindow": 0.58}},
        ]

        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="where did we plan how Codex would integrate with a Raspberry Pi",
        )

        self.assertEqual(ranked[0]["threadId"], "expected")
        duplicate = next(item for item in ranked if item["threadId"] == "duplicate-a")
        self.assertTrue(duplicate["duplicateGroupBlockedByCompetingEvidence"])

    def test_near_tie_with_equal_title_evidence_defers_to_semantic_rank(self):
        candidates = [
            {"threadId": "semantic-first", "title": "Explore repo structure", "citationRank": 1},
            {"threadId": "local-first", "title": "Inspect repo contents", "citationRank": 2},
        ]
        local = [
            {"id": "local-first", "score": 28.55, "coverage": {"bestWindow": 0.35}},
            {"id": "semantic-first", "score": 14.52, "coverage": {"bestWindow": 0.15}},
        ]

        ranked = search.merge_local_ranking(
            candidates,
            local,
            query="which task explored the repository structure",
        )

        self.assertEqual(ranked[0]["threadId"], "semantic-first")

    def test_confidence_gate_rejects_moderate_unanchored_local_match(self):
        confidence = search.candidate_confidence({
            "titleQueryOverlap": 0,
            "localScore": 57.88,
            "localCoverage": {"bestWindow": 0.739},
        })
        self.assertFalse(confidence["accepted"])
        self.assertEqual(confidence["reason"], "insufficient-evidence")

    def test_confidence_gate_accepts_title_or_strong_local_evidence(self):
        title = search.candidate_confidence({"titleQueryOverlap": 0.25})
        local = search.candidate_confidence({
            "titleQueryOverlap": 0,
            "localScore": 70,
            "localCoverage": {"bestWindow": 0.9},
        })
        self.assertTrue(title["accepted"])
        self.assertTrue(local["accepted"])

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
        aws_key = "".join(("AKIA", "ABCDEFGHIJKLMNOP"))
        github_token = "".join(("ghp_", "abcdefghijklmnopqrstuvwxyz1234"))
        value, count = search.sanitize_query(
            f"Find {aws_key} access_token=supersecretvalue\n"
            f"{github_token}\nCookie: SID=private-cookie-value\n"
            "https://user:password@example.com?a=1&api_key=private-value\n"
            "C:\\Users\\private-user\\Documents\\trace.txt"
        )
        self.assertNotIn(aws_key, value)
        self.assertNotIn(github_token, value)
        self.assertNotIn("supersecretvalue", value)
        self.assertNotIn("private-cookie-value", value)
        self.assertNotIn("private-user", value)
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
