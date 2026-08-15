from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "thread_rag_benchmark_contract.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_benchmark_contract", MODULE_PATH)
contract = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(contract)


def suite(cases):
    return {"schemaVersion": 1, "suiteId": "test-v1", "split": "development", "cases": cases}


class BenchmarkContractTests(unittest.TestCase):
    def test_match_and_no_match_cases_are_valid(self):
        normalized = contract.normalize_suite(suite([
            {"caseId": "a", "name": "match", "query": "find alpha", "stratum": "vague", "expectedThreadIds": ["t1"]},
            {"caseId": "b", "name": "negative", "query": "nonexistent zephyr", "stratum": "negative", "expectation": "no_match"},
        ]))
        self.assertEqual(normalized["cases"][1]["expectedThreadIds"], [])

    def test_no_match_rejects_expected_ids(self):
        with self.assertRaisesRegex(ValueError, "cannot contain"):
            contract.normalize_suite(suite([
                {"caseId": "a", "name": "bad", "query": "nothing", "stratum": "negative", "expectation": "no_match", "expectedThreadIds": ["t1"]},
            ]))

    def test_normalized_duplicate_query_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate normalized query"):
            contract.normalize_suite(suite([
                {"caseId": "a", "name": "one", "query": "Find   Alpha", "stratum": "vague", "expectedThreadIds": ["t1"]},
                {"caseId": "b", "name": "two", "query": " find alpha ", "stratum": "exact", "expectedThreadIds": ["t2"]},
            ]))

    def test_seal_detects_label_mutation(self):
        original = contract.normalize_suite(suite([
            {"caseId": "a", "name": "one", "query": "find alpha", "stratum": "vague", "expectedThreadIds": ["t1"]},
        ]))
        seal = contract.make_seal(original)
        changed = contract.normalize_suite(suite([
            {"caseId": "a", "name": "one", "query": "find alpha", "stratum": "vague", "expectedThreadIds": ["t2"]},
        ]))
        self.assertIn("labelSha256", contract.verify_seal(changed, seal))

    def test_wilson_interval_reports_uncertainty(self):
        interval = contract.wilson_interval(24, 24)
        self.assertEqual(interval["rate"], 1.0)
        self.assertLess(interval["lower95"], 1.0)


if __name__ == "__main__":
    unittest.main()
