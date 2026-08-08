from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_plan.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_plan", MODULE_PATH)
planner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(planner)


class PlannerTests(unittest.TestCase):
    def test_first_fit_plan_reserves_rolling_revision_headroom(self):
        state = {
            "policyVersion": planner.REQUIRED_POLICY,
            "threads": {
                "a": {"revision": 1, "parts": [{}, {}, {}]},
                "b": {"revision": 2, "parts": [{}, {}]},
                "c": {"revision": 1, "parts": [{}, {}]},
            },
        }
        result = planner.plan_shards(state, source_limit=8, requested_reserve=2, prefix="Test")
        self.assertEqual(result["effectiveReserve"], 3)
        self.assertEqual(result["shardCapacity"], 5)
        self.assertEqual(result["shardCount"], 2)
        self.assertEqual(sum(item["sourceParts"] for item in result["shards"]), 7)
        self.assertTrue(all(item["steadyHeadroom"] >= 3 for item in result["shards"]))

    def test_thread_larger_than_capacity_is_rejected(self):
        state = {"policyVersion": planner.REQUIRED_POLICY, "threads": {"huge": {"revision": 1, "parts": [{}, {}, {}, {}]}}}
        with self.assertRaisesRegex(ValueError, "above shard capacity"):
            planner.plan_shards(state, source_limit=7, requested_reserve=3, prefix="Test")


if __name__ == "__main__":
    unittest.main()
