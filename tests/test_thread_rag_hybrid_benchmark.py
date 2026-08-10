from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "thread_rag_hybrid_benchmark.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_hybrid_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class HybridBenchmarkTests(unittest.TestCase):
    def test_expected_rank_uses_current_multi_id_ground_truth(self):
        expected = benchmark.normalized_expected_ids({"expectedThreadIds": ["original", "sibling"]})
        self.assertEqual(benchmark.first_expected_rank(["sibling", "decoy"], expected), 1)

    def test_unverified_semantic_candidate_still_has_a_rank(self):
        self.assertEqual(benchmark.first_expected_rank(["target"], {"target"}), 1)


if __name__ == "__main__":
    unittest.main()
