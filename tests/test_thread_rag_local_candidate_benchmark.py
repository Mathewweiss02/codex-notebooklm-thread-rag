import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "thread_rag_local_candidate_benchmark.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_local_candidate_benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class LocalCandidateBenchmarkTests(unittest.TestCase):
    def test_expected_rank_accepts_any_authoritative_sibling(self):
        results = [{"id": "decoy"}, {"id": "sibling-b"}, {"id": "sibling-a"}]
        self.assertEqual(benchmark.expected_rank(results, {"sibling-a", "sibling-b"}), 2)

    def test_expected_rank_reports_miss(self):
        self.assertIsNone(benchmark.expected_rank([{"id": "decoy"}], {"expected"}))


if __name__ == "__main__":
    unittest.main()
