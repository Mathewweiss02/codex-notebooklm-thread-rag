from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_source_scoped_benchmark.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_source_scoped_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class SourceScopedBenchmarkTests(unittest.TestCase):
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
