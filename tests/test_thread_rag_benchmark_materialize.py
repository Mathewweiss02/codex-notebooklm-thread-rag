from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "thread_rag_benchmark_materialize.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_benchmark_materialize", MODULE_PATH)
materializer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(materializer)


class BenchmarkMaterializeTests(unittest.TestCase):
    def test_duplicate_titles_become_acceptable_siblings(self):
        state = {"threads": {
            "t2": {"title": "Same task", "contentDigest": "b", "revision": 1},
            "t1": {"title": "Same task", "contentDigest": "a", "revision": 1},
        }}
        spec = {
            "schemaVersion": 1,
            "suiteId": "dev-v1",
            "split": "development",
            "cases": [{"caseId": "a", "name": "a", "query": "remember the same one", "stratum": "sibling", "expectedTitle": "Same task"}],
        }
        suite = materializer.materialize(spec, state)
        self.assertEqual(suite["cases"][0]["expectedThreadIds"], ["t1", "t2"])
        self.assertEqual(suite["cases"][0]["labelProvenance"]["acceptableSiblingCount"], 2)

    def test_missing_title_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            materializer.materialize({
                "schemaVersion": 1,
                "suiteId": "dev-v1",
                "split": "development",
                "cases": [{"caseId": "a", "name": "a", "query": "missing", "stratum": "vague", "expectedTitle": "Absent"}],
            }, {"threads": {}})

    def test_unique_prefix_can_select_long_private_title(self):
        state = {"threads": {"t1": {"title": "Very long private title and details", "contentDigest": "a", "revision": 1}}}
        suite = materializer.materialize({
            "schemaVersion": 1,
            "suiteId": "holdout-v1",
            "split": "holdout",
            "cases": [{"caseId": "a", "name": "a", "query": "remember the details", "stratum": "vague", "expectedTitlePrefix": "Very long private"}],
        }, state)
        self.assertEqual(suite["cases"][0]["expectedThreadIds"], ["t1"])


if __name__ == "__main__":
    unittest.main()
