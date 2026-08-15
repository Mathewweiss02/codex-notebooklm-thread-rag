from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_source_scoped_benchmark.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_source_scoped_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class SourceScopedBenchmarkTests(unittest.TestCase):
    def test_parser_defaults_transport_retries_to_zero(self):
        with patch(
            "sys.argv",
            [
                "benchmark",
                "--state", "state.json",
                "--cases", "cases.json",
                "--profile", "personal",
                "--notebook-id", "notebook",
                "--out", "report.json",
                "--confirm-disposable-retrieval-notebook",
            ],
        ):
            args = benchmark.parse_args()
        self.assertEqual(args.transport_max_retries, 0)

    def test_parser_rejects_unbounded_transport_retries(self):
        with patch(
            "sys.argv",
            [
                "benchmark",
                "--state", "state.json",
                "--cases", "cases.json",
                "--profile", "personal",
                "--notebook-id", "notebook",
                "--out", "report.json",
                "--transport-max-retries", "4",
                "--confirm-disposable-retrieval-notebook",
            ],
        ):
            with self.assertRaises(SystemExit):
                benchmark.parse_args()

    def test_make_client_passes_explicit_transport_retry_budget(self):
        args = SimpleNamespace(profile="personal", timeout=240, transport_max_retries=0)
        with patch.object(benchmark.NotebookLMClient, "from_storage", return_value="client") as factory:
            self.assertEqual(benchmark.make_client(args), "client")
        factory.assert_called_once_with(
            profile="personal",
            chat_timeout=240,
            rate_limit_max_retries=0,
            server_error_max_retries=0,
        )

    def test_build_source_map_rejects_unuploaded_parts(self):
        with self.assertRaisesRegex(ValueError, "unuploaded"):
            benchmark.build_source_map({"threads": {"thread-a": {"parts": [{"part": 1}]}}})

    def test_select_scope_uses_only_current_mapped_threads(self):
        source_to_thread = {"source-a": "thread-a", "source-b": "thread-b"}
        thread_to_sources = {"thread-a": ["source-a"], "thread-b": ["source-b"]}
        with patch.object(
            benchmark,
            "local_candidate_surface",
            return_value={"candidates": [{"threadId": "thread-b"}, {"threadId": "untracked"}], "elapsedMs": 4},
        ):
            scope = benchmark.select_scope(
                "query",
                source_to_thread,
                thread_to_sources,
                width=2,
                node_path="node",
                codex_root=Path("C:/codex"),
                timeout=30,
            )
        self.assertEqual(scope["localCandidateCount"], 1)
        self.assertEqual(scope["sourceCount"], 1)
        self.assertEqual(scope["sourceIds"], ["source-b"])

    def test_percentile_is_bounded_and_deterministic(self):
        self.assertEqual(benchmark.percentile([3.0, 1.0, 2.0], 0.5), 2.0)
        self.assertEqual(benchmark.percentile([3.0], 0.95), 3.0)
        self.assertIsNone(benchmark.percentile([], 0.5))

    def test_sparse_semantic_output_abstains_at_the_candidate_gate(self):
        record = {}
        gated = benchmark.enforce_semantic_candidate_gate(
            {"thread-a": {"threadId": "thread-a"}},
            2,
            record,
            0,
        )
        self.assertEqual(gated, {})
        self.assertEqual(record["semanticAbstentionReason"], "sparse-initial-response-gate")

    def test_rate_limit_classifier_is_specific_to_pinned_chat_error(self):
        self.assertTrue(benchmark.is_rate_limited_error(benchmark.ChatError("rate limited")))
        self.assertFalse(benchmark.is_rate_limited_error(RuntimeError("rate limited")))

    def test_rate_limit_circuit_breaker_requires_terminal_error(self):
        self.assertTrue(benchmark.should_abort_rate_limit({
            "error": "all semantic attempts failed",
            "attempts": [{"kind": "rate-limit"}],
        }))
        self.assertFalse(benchmark.should_abort_rate_limit({
            "attempts": [{"kind": "rate-limit"}],
        }))
        self.assertFalse(benchmark.should_abort_rate_limit({
            "error": "other failure",
            "attempts": [{"kind": "transport"}],
        }))

    def test_summary_scores_sealed_records_before_hiding_case_details(self):
        records = [
            {
                "expectation": "match",
                "remoteCandidateHit": True,
                "hybridTop1": True,
                "hybridAbstained": False,
                "sourceScopeValid": True,
                "elapsedMs": 120.5,
                "attempts": [{"referenceCount": 2}],
            },
            {
                "expectation": "no_match",
                "remoteCandidateHit": False,
                "hybridTop1": False,
                "hybridAbstained": True,
                "sourceScopeValid": True,
                "elapsedMs": 80.25,
                "attempts": [{"referenceCount": 0}],
            },
        ]
        summary, gates = benchmark.summarize_results(records, expected_case_count=2, threshold=0.975)
        self.assertEqual(summary["completedCases"], 2)
        self.assertEqual(summary["latencyMs"]["count"], 2)
        self.assertEqual(summary["semanticCandidateRecall"]["rate"], 1.0)
        self.assertEqual(summary["hybridTop1"]["rate"], 1.0)
        self.assertTrue(all(gates.values()))

    def test_summary_fails_closed_for_rate_limit_partial_run(self):
        summary, gates = benchmark.summarize_results(
            [{
                "expectation": "match",
                "remoteCandidateHit": False,
                "hybridTop1": False,
                "hybridAbstained": True,
                "sourceScopeValid": True,
                "elapsedMs": 10.0,
                "error": "all semantic attempts failed",
                "attempts": [{"kind": "rate-limit", "error": "redacted"}],
            }],
            expected_case_count=40,
            threshold=0.975,
        )
        self.assertEqual(summary["rateLimitEvents"], 1)
        self.assertFalse(gates["complete"])
        self.assertFalse(gates["candidateRecall100"])
        self.assertFalse(gates["errors"])
